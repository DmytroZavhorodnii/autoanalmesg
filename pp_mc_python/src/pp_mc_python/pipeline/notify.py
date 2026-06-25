"""Step 7 — SCOPE: Notify if Action Required.

The Power Automate condition: if Status == Open, send an alert email;
otherwise Terminate 1 (file the item and move on, no notification noise).
"""

from __future__ import annotations
import logging
from ..context import FlowContext
from ..sinks.email import EmailSender

log = logging.getLogger(__name__)


def notify_if_action_required(ctx: FlowContext, mailer: EmailSender) -> None:
    if ctx.classification is None:
        raise RuntimeError("notify_if_action_required() called without a classification")

    if not ctx.classification.action_required():
        log.debug("No alert for item %s (status=Closed)", ctx.source_item.id)
        return

    mailer.send_alert(ctx.source_item, ctx.classification)
    log.info("Alert email sent for item %s", ctx.source_item.id)
