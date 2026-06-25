"""Step 3 — SCOPE: Check If Needs Processing.

The Power Automate scope checks whether the source item has already been
classified. If it has, the flow terminates immediately (no re-classify,
no re-notify, no duplicate AdminList row, no AI credit burn).

The cheapest signal we have is `Processed` on the source row, set in Step 8.
"""

from __future__ import annotations
import logging
from ..context import FlowContext

log = logging.getLogger(__name__)


def needs_processing(ctx: FlowContext) -> bool:
    """Return True only when the item should continue down the pipeline.

    Mirrors the Power Automate condition: continue if not already processed.
    """
    item = ctx.source_item
    if item.processed:
        ctx.skipped = True
        ctx.skip_reason = "already processed (dedup gate)"
        log.info("Skipping item %s — %s", item.id, ctx.skip_reason)
        return False
    return True
