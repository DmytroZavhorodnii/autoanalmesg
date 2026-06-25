"""
Rule-based (keyword) classifier — fast path before hitting the AI model.
Handles ~40-60% of MC announcements with near-zero latency.
"""

import re
from typing import Optional, Callable

# Patterns for "typ"
# Evaluated in order; first match wins.
# Each entry: (compiled_regex, typ, priorytet, akcja)
_RULES: list[tuple] = [
    (re.compile(r"maintenance window (start|end|scheduled)", re.I),
     "maintenance", "medium", "none"),
    (re.compile(r"(planned|scheduled) (maintenance|downtime|outage)", re.I),
     "maintenance", "medium", "none"),
    (re.compile(
        r"\b(deprecat|end[- ]of[- ](life|support)|being retired|will be removed)\b", re.I),
     "deprecation", "medium", "recommended"),
    (re.compile(r"\bbreaking[- ]change\b", re.I),
     "breaking_change", "high", "required"),
    (re.compile(
        r"\b(security (update|patch|vulnerability|advisory)|cve-\d{4})\b", re.I),
     "security", "high", "required"),
    (re.compile(
        r"\b(generally available|public preview|now available|new feature|introducing)\b",
        re.I),
     "new_feature", "low", "none"),
    (re.compile(
        r"\b(version \d+\.\d+|release notes?|minor update|patch release)\b", re.I),
     "service_update", "low", "none"),
]

# Patterns for "serwis"
_SERWIS_RULES: list[tuple] = [
    (re.compile(r"\bpower automate\b|\bflow\b", re.I),            "Power Automate"),
    (re.compile(r"\bpower apps?\b|\bpowerapps\b", re.I),          "Power Apps"),
    (re.compile(r"\bdataverse\b|\bcommon data service\b", re.I),  "Dataverse"),
    (re.compile(r"\bcopilot\b|\bpower virtual agents?\b|\bpva\b", re.I), "Copilot"),
    (re.compile(r"\bpower pages?\b|\bportals?\b", re.I),          "Power Pages"),
]

# Date extraction
_DATE_RE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2})"
    r"|\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(\d{4})\b"
    r"|\b(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b",
    re.I,
)
_MONTH_MAP = {m: f"{i:02d}" for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june",
     "july", "august", "september", "october", "november", "december"], 1,
)}


def extract_date(text: str) -> Optional[str]:
    """Extract the first date found in text; returns YYYY-MM-DD or None."""
    m = _DATE_RE.search(text)
    if not m:
        return None
    if m.group(1):
        return m.group(1)
    if m.group(2):
        day, mon, yr = m.group(2), m.group(3).lower(), m.group(4)
        return f"{yr}-{_MONTH_MAP[mon]}-{int(day):02d}"
    if m.group(5):
        mon, day, yr = m.group(5).lower(), m.group(6), m.group(7)
        return f"{yr}-{_MONTH_MAP[mon]}-{int(day):02d}"
    return None


def extract_serwis(text: str) -> str:
    """Detect primary Power Platform component from keywords."""
    for pattern, serwis in _SERWIS_RULES:
        if pattern.search(text):
            return serwis
    return "inne"


def _first_sentences(text: str, n: int = 2) -> str:
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return " ".join(sentences[:n]).strip() or text[:200]


def rule_classify(
    clean_text: str,
    determine_status_fn: Callable,
    should_notify_fn: Callable,
) -> Optional[dict]:
    """
    Try to classify via keyword rules.
    Returns a classification dict (same shape as AI output) or None.
    """
    for pattern, typ, priorytet, akcja in _RULES:
        if pattern.search(clean_text):
            serwis     = extract_serwis(clean_text)
            data_wazna = extract_date(clean_text)
            summary    = _first_sentences(clean_text)
            status     = determine_status_fn(typ, priorytet)
            email      = should_notify_fn(typ, priorytet)
            return {
                "typ": typ, "priorytet": priorytet, "serwis": serwis,
                "akcja": akcja, "data_wazna": data_wazna,
                "streszczenie": summary, "status": status,
                "email_alert": email, "confidence": 8, "_source": "rules",
                "_custom": {},
            }
    return None
