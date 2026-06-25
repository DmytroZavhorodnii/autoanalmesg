"""Step 8 — SCOPE: Update Original Item.

Marks the source MessageCenters row as `Processed = true`. This is the only
state that prevents the trigger from refiring for the same item — without
this step Step 3 would not block re-processing on the next modification.

If this step fails, the global error handler runs but the AdminList row is
already persisted. That is by design: a failed update means we may classify
the same item again next time (idempotent — a duplicate AdminList row at
worst). The opposite ordering (update before store) would risk losing the
classification entirely on a sink failure.
"""

from __future__ import annotations
import logging
from ..context import FlowContext
from ..sources.sharepoint import SharePointSource

log = logging.getLogger(__name__)


def mark_processed(ctx: FlowContext, source: SharePointSource) -> None:
    source.mark_processed(ctx.source_item.id)
    log.info("Marked source item %s as processed", ctx.source_item.id)
