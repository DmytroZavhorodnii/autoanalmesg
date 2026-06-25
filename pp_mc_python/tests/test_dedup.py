"""Test Step 3 — Check If Needs Processing (dedup gate)."""

from datetime import datetime, timezone
from pp_mc_python.context import FlowContext
from pp_mc_python.models import MCItem
from pp_mc_python.pipeline.dedup_gate import needs_processing


def _item(processed: bool) -> MCItem:
    now = datetime.now(timezone.utc)
    return MCItem(id=100001, created=now, modified=now,
                  full_message_html="<p>x</p>", processed=processed)


def test_unprocessed_item_continues():
    ctx = FlowContext(source_item=_item(processed=False))
    assert needs_processing(ctx) is True
    assert ctx.skipped is False


def test_already_processed_skips():
    ctx = FlowContext(source_item=_item(processed=True))
    assert needs_processing(ctx) is False
    assert ctx.skipped is True
    assert "dedup gate" in ctx.skip_reason
