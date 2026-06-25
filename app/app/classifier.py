"""
Core classification engine.
Pipeline: cache → keyword rules → Ollama/Gemma3 AI.
Shared singletons (result_cache, feedback_store) are safe to use
from multiple threads simultaneously.
"""

import json
import re
import time
import threading
import requests

import app.config as cfg
from app.cache import ResultCache
from app.feedback import FeedbackStore
from app.rules import rule_classify, extract_date, extract_serwis

# Shared singletons
result_cache   = ResultCache()
feedback_store = FeedbackStore()

# Runtime-configurable state (changed via Settings UI)
_extra_criteria: str = ""
_custom_criteria: list = []
_lock_criteria = threading.Lock()


def set_extra_criteria(text: str):
    global _extra_criteria
    with _lock_criteria:
        _extra_criteria = text


def set_custom_criteria(criteria: list):
    global _custom_criteria
    with _lock_criteria:
        _custom_criteria = criteria


def get_extra_criteria() -> str:
    with _lock_criteria:
        return _extra_criteria


def get_custom_criteria() -> list:
    with _lock_criteria:
        return list(_custom_criteria)


# Text utilities

def strip_html(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;",  " ",  text)
    text = re.sub(r"&amp;",   "&",  text)
    text = re.sub(r"&lt;",    "<",  text)
    text = re.sub(r"&gt;",    ">",  text)
    return re.sub(r"\s+", " ", text).strip()


def truncate(text: str, max_chars: int = cfg.MAX_MESSAGE_CHARS) -> str:
    return text if len(text) <= max_chars else text[:max_chars] + " [...]"


# Business logic

def determine_status(typ: str, priorytet: str) -> str:
    if typ in ("breaking_change", "security", "unclear"):
        return "open"
    if typ == "deprecation" and priorytet in ("medium", "high"):
        return "open"
    return "closed"


def should_notify_email(typ: str, priorytet: str) -> bool:
    if typ == "maintenance" and priorytet in ("high", "medium"):
        return True
    return priorytet == "high"


def normalize_enum(value: str, allowed: list, default: str) -> str:
    if not isinstance(value, str):
        return default
    v = value.strip().lower()
    for a in allowed:
        if a.lower() == v:
            return a
    return default


def check_ollama() -> bool:
    try:
        requests.get("http://localhost:11434/api/tags", timeout=3)
        return True
    except Exception:
        return False


# Dynamic timeout tracker

class TimeoutTracker:
    BASE   = 120
    MAX    = 600
    FACTOR = 2.0
    WINDOW = 5

    def __init__(self):
        self._times: list[float] = []
        self._lock = threading.Lock()

    def record(self, elapsed: float):
        with self._lock:
            self._times.append(elapsed)
            if len(self._times) > self.WINDOW:
                self._times.pop(0)

    def get(self) -> float:
        with self._lock:
            if not self._times:
                return self.BASE
            dynamic = max(self._times) * self.FACTOR
            return max(self.BASE, min(dynamic, self.MAX))


_timeout_tracker = TimeoutTracker()


# Ollama warmup

def warmup_model():
    """Load the model into RAM before batch processing. Non-fatal on failure."""
    try:
        payload = {
            "model": cfg.MODEL,
            "messages": [{"role": "user", "content": "ping"}],
            "stream": False, "keep_alive": -1,
            "options": {"num_predict": 1},
        }
        requests.post(cfg.OLLAMA_URL, json=payload, timeout=cfg.REQUEST_TIMEOUT)
    except Exception:
        pass


# Prompt builder

def build_prompt(message: str) -> str:
    custom_criteria = get_custom_criteria()
    extra_criteria  = get_extra_criteria()

    custom_block      = ""
    custom_json_fields = ""
    if custom_criteria:
        lines = ["CUSTOM CRITERIA (also return these fields in JSON):"]
        for crit in custom_criteria:
            vals_str = " | ".join(crit["values"])
            lines.append(f'- {crit["name"]}: {vals_str}')
        custom_block = "\n" + "\n".join(lines) + "\n"
        custom_json_fields = "," + ",".join(
            f'"{c["name"]}":"..."' for c in custom_criteria
        )

    extra_block = (
        f"\nADDITIONAL INSTRUCTIONS:\n{extra_criteria}\n" if extra_criteria else ""
    )

    examples = feedback_store.get_examples(message)
    examples_block = ""
    if examples:
        lines = ["CORRECTED EXAMPLES (admin-verified — follow these):"]
        for ex in examples:
            o, c = ex["original"], ex["corrected"]
            lines.append(
                f'  Text: "{ex["snippet"][:120]}..."'
                f'\n  Was:     typ={o["typ"]}, priorytet={o["priorytet"]}'
                f'\n  Correct: typ={c["typ"]}, priorytet={c["priorytet"]}, '
                f'serwis={c["serwis"]}, akcja={c["akcja"]}'
            )
        examples_block = "\n".join(lines) + "\n\n"

    return f"""You are an expert Microsoft Power Platform administrator.
Analyze the Microsoft 365 Message Center announcement and classify it.
Return ONLY a JSON object — no explanation, no markdown, no extra text.

{examples_block}MESSAGE:
{message}

CLASSIFICATION RULES:
- typ: {" | ".join(cfg.TYP_VALUES)}
  maintenance=planned window, new_feature=new functionality,
  breaking_change=backward-incompatible, service_update=routine update,
  deprecation=feature being retired, security=security/permissions change,
  unclear=cannot classify

- priorytet: {" | ".join(cfg.PRIORYTET_VALUES)}
  high=immediate action, breaking/security, maintenance<48h
  medium=action needed within 30 days
  low=informational, no action needed

- serwis: {" | ".join(cfg.SERWIS_VALUES)}
  Pick the primary Power Platform component; use "inne" if none matches.

- akcja: {" | ".join(cfg.AKCJA_VALUES)}
  required=must act before deadline, recommended=advised, none=informational

- data_wazna: YYYY-MM-DD or null
- streszczenie: 1-2 sentences in the SAME LANGUAGE as the message
- confidence: integer 1-10 (10=unambiguous, 1=very unclear)
{custom_block}{extra_block}
Return JSON:
{{"typ":"...","priorytet":"...","serwis":"...","akcja":"...","data_wazna":"...","streszczenie":"...","confidence":10{custom_json_fields}}}"""


# Ollama HTTP call with retry

def _call_ollama(messages: list, timeout: float) -> str:
    payload = {
        "model": cfg.MODEL,
        "messages": messages,
        "stream": True,
        "format": "json",
        "keep_alive": -1,
        "options": {"temperature": 0, "num_predict": 256, "num_ctx": 2048},
    }
    for attempt in range(1, cfg.MAX_RETRIES + 1):
        full = ""
        try:
            with requests.post(
                cfg.OLLAMA_URL, json=payload, stream=True, timeout=timeout
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    full += chunk.get("message", {}).get("content", "")
                    if chunk.get("done"):
                        break
            return full
        except requests.exceptions.ConnectionError:
            raise  # fatal — Ollama not running
        except (requests.exceptions.Timeout, requests.exceptions.ReadTimeout):
            timeout = min(timeout * 2, TimeoutTracker.MAX)
            time.sleep(cfg.RETRY_BACKOFF * attempt)
        except Exception:
            time.sleep(cfg.RETRY_BACKOFF * attempt)
    return ""


# Main classify function

def classify_message(raw_message: str) -> dict:
    """
    Classify a single MC message.
    Pipeline: cache → keyword rules → Gemma3 AI.
    """
    clean     = strip_html(raw_message)
    truncated = truncate(clean)

    # 1 — Cache
    cached = result_cache.get(truncated)
    if cached:
        return {**cached, "_source": "cache"}

    # 2 — Keyword rules
    ruled = rule_classify(
        truncated,
        determine_status_fn=determine_status,
        should_notify_fn=should_notify_email,
    )
    if ruled:
        result_cache.set(truncated, ruled)
        return ruled

    # 3 — AI
    prompt  = build_prompt(truncated)
    timeout = _timeout_tracker.get()
    t0      = time.time()
    try:
        response = _call_ollama([{"role": "user", "content": prompt}], timeout=timeout)
        _timeout_tracker.record(time.time() - t0)

        j_start = response.find('{')
        j_end   = response.rfind('}') + 1
        if j_start == -1 or j_end <= j_start:
            raise ValueError("No JSON in model response")

        result = json.loads(response[j_start:j_end])

        typ       = normalize_enum(result.get("typ",       ""), cfg.TYP_VALUES,      "unclear")
        priorytet = normalize_enum(result.get("priorytet", ""), cfg.PRIORYTET_VALUES, "medium")
        serwis    = normalize_enum(result.get("serwis",    ""), cfg.SERWIS_VALUES,    "inne")
        akcja     = normalize_enum(result.get("akcja",     ""), cfg.AKCJA_VALUES,     "none")

        data_wazna = result.get("data_wazna")
        if data_wazna in ("null", "", "N/A", "n/a", None):
            data_wazna = None

        streszczenie = str(result.get("streszczenie", "")).strip() or "No summary."
        try:
            confidence = max(1, min(10, int(result.get("confidence", 5))))
        except (TypeError, ValueError):
            confidence = 5

        if confidence <= 3 and typ != "unclear":
            typ = "unclear"

        custom_criteria = get_custom_criteria()
        custom_vals = {}
        for crit in custom_criteria:
            raw_val = result.get(crit["name"], "")
            custom_vals[crit["name"]] = normalize_enum(
                raw_val, crit["values"], crit["values"][0]
            )

        ai_result = {
            "typ":         typ,
            "priorytet":   priorytet,
            "serwis":      serwis,
            "akcja":       akcja,
            "data_wazna":  data_wazna,
            "streszczenie": streszczenie,
            "status":      determine_status(typ, priorytet),
            "email_alert": should_notify_email(typ, priorytet),
            "confidence":  confidence,
            "_source":     "ai",
            "_custom":     custom_vals,
        }
        result_cache.set(truncated, ai_result)
        return ai_result

    except requests.exceptions.ConnectionError:
        raise
    except Exception:
        return {
            "typ": "unclear", "priorytet": "medium", "serwis": "inne",
            "akcja": "none", "data_wazna": None,
            "streszczenie": "Classification failed — manual review required.",
            "status": "open", "email_alert": False, "confidence": 0,
            "_source": "fallback", "_custom": {},
        }
