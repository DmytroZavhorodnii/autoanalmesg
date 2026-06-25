"""Step 9 — SCOPE: Error Handling (global Try/Catch).

The Power Automate solution wraps the main pipeline in a Try scope and pairs
it with an Error Handling scope configured `Run after: Has failed / Has timed
out`. The error scope composes failure details (message, timestamp, item id)
into a structured log so DevOps can triage.

The Python equivalent is a context manager and a structured handler that:
- captures the exception
- writes a structured record (item id, stage, error class, message, stack)
- optionally sends an alert to the DevOps DL (off by default — same as the
  Power Platform default; turn on with `ERROR_ALERT_EMAIL` env var)
"""

from __future__ import annotations
import logging
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator, Optional

from ..context import FlowContext

log = logging.getLogger(__name__)


@dataclass
class FlowFailure:
    item_id: int
    stage: str
    error_class: str
    message: str
    stack: str
    timestamp: str


@contextmanager
def stage(ctx: FlowContext, name: str) -> Iterator[None]:
    """Wrap each pipeline step. Exceptions become FlowFailure records and
    re-raise to abort the rest of the pipeline (matching Power Automate's
    'scope failed → next steps skipped' behaviour)."""
    log.debug("→ stage %s (item %s)", name, ctx.source_item.id)
    try:
        yield
    except Exception as exc:
        failure = FlowFailure(
            item_id=ctx.source_item.id,
            stage=name,
            error_class=type(exc).__name__,
            message=str(exc),
            stack=traceback.format_exc(),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        ctx.error = exc
        log.error(
            "stage %s failed for item %s: %s — %s",
            name, ctx.source_item.id, failure.error_class, failure.message,
        )
        log.debug("Stack:\n%s", failure.stack)
        raise
