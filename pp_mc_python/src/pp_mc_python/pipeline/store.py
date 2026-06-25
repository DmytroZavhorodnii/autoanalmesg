"""Step 6 — SCOPE: Store in Admin List.

Persists the classification result as a new row on the target SharePoint list.
"""

from __future__ import annotations
import logging
from ..context import FlowContext
from ..models import AdminListItem
from ..sinks.admin_list import AdminListWriter

log = logging.getLogger(__name__)


def store(ctx: FlowContext, writer: AdminListWriter) -> None:
    if ctx.classification is None:
        raise RuntimeError("store() called without a classification — pipeline order is wrong")

    row = AdminListItem.from_result(ctx.source_item, ctx.classification)
    writer.create_item(row)
    log.info("Stored AdminList row for source id %s (status=%s)", ctx.source_item.id, row.status.value)
