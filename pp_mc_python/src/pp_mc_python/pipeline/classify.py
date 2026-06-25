"""Step 5 — SCOPE: AI Classification ("The Brain").

This is the only stage where intelligence enters the system. It mirrors the
Power Automate Run a Prompt + Parse JSON pair:

1. Send the cleaned text to an LLM with the same system prompt that AI Builder
   uses (see SYSTEM_PROMPT below — keep this in sync with the AI Builder prompt)
2. Receive a JSON string back
3. Parse it strictly: any deviation from the expected schema raises and is
   captured by the global error handler in Step 9

The contract the LLM must respect is the JSON schema from section 4.3 of the
technical documentation.
"""

from __future__ import annotations
import json
import logging
import re
from typing import Any, Dict
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import OpenAI, OpenAIError

from ..config import Config
from ..context import FlowContext
from ..models import (
    ClassificationResult, Category, Priority, ImpactLevel, Status,
)

log = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are an expert Microsoft 365 governance analyst classifying
Message Center announcements for Power Platform.

Read the announcement below and return ONLY a JSON object. No preamble, no Markdown
code fences, no trailing prose. Failing to return strict JSON will cause downstream
errors.

Required JSON schema:
{
  "title": string,
  "category": "Maintenance" | "New Feature" | "Breaking Change" | "Other",
  "priority": "High" | "Medium" | "Low",
  "impact": "High" | "Medium" | "Low",
  "summary": string,            // 1-2 sentences, English
  "actionsTaken": string,       // recommendation for administrators
  "status": "Open" | "Closed"   // Open = action required, Closed = routine
}

Classification rules:
- "critical", "immediately", "ASAP", "must take action" → priority = High
- Planned maintenance window → category = Maintenance, status = Closed
- New feature / improvement   → category = New Feature, status = Closed
- Deprecation / breaking change → category = Breaking Change, status = Open
- Unclear or non-Power-Platform → category = Other, status = Open

Summary must be in English. If the source text is not in English, summarise in English."""


class InvalidAIResponse(RuntimeError):
    """Raised when the LLM returns something that is not parseable JSON or
    does not match the expected schema."""


class ClassifierClient:
    """Thin wrapper around the LLM call. Holds the OpenAI client so it can be
    reused across runs (saves the TLS handshake)."""

    def __init__(self, config: Config) -> None:
        self._client = OpenAI(
            api_key=config.openai_api_key,
            base_url=config.openai_base_url,
        )
        self._model = config.openai_model

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(OpenAIError),
        reraise=True,
    )
    def _call_llm(self, user_text: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        return resp.choices[0].message.content or ""

    def classify(self, clean_text: str) -> ClassificationResult:
        raw = self._call_llm(clean_text)
        return _parse_json_strict(raw)


def _parse_json_strict(raw: str) -> ClassificationResult:
    """Parse the LLM output into a ClassificationResult.

    Mirrors the Power Automate Parse JSON step: a parsing or schema failure
    is an exception that the global Error Handling scope (Step 9) will catch.
    """
    text = raw.strip()
    # Defensive: strip code fences if the model misbehaves anyway
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE)

    try:
        data: Dict[str, Any] = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidAIResponse(f"LLM did not return valid JSON: {exc}") from exc

    try:
        return ClassificationResult(
            title=str(data["title"]),
            category=Category(data["category"]),
            priority=Priority(data["priority"]),
            impact=ImpactLevel(data["impact"]),
            summary=str(data.get("summary", "")),
            actions_taken=str(data.get("actionsTaken", "")),
            status=Status(data["status"]),
        )
    except (KeyError, ValueError) as exc:
        raise InvalidAIResponse(f"LLM JSON did not match schema: {exc}") from exc


def classify(ctx: FlowContext, client: ClassifierClient) -> None:
    """Step 5 in-place: populates `ctx.classification` and the var_* fields."""
    result = client.classify(ctx.var_clean_message)
    ctx.classification = result
    ctx.var_title = result.title
    ctx.var_category = result.category.value
    ctx.var_status = result.status.value
    log.info("Classified item %s as %s / %s / %s", ctx.source_item.id,
             result.category.value, result.priority.value, result.status.value)
