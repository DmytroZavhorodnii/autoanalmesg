"""Email sink — equivalent of Step 7's Outlook V3 connector call.

Builds and sends an alert email when a classification has Status = Open.
Uses SMTP by default (works with Office 365 SMTP AUTH). Swap for Microsoft
Graph /sendMail in a production deployment if SMTP AUTH is disabled tenant-wide.
"""

from __future__ import annotations
import logging
import smtplib
from email.message import EmailMessage

from ..config import Config
from ..models import MCItem, ClassificationResult

log = logging.getLogger(__name__)


class EmailSender:
    def __init__(self, config: Config) -> None:
        self._config = config

    def _build_message(self, item: MCItem, result: ClassificationResult) -> EmailMessage:
        msg = EmailMessage()
        msg["From"] = self._config.smtp_username
        msg["To"] = self._config.admin_email_dl
        msg["Subject"] = f"[PP MC] {result.priority.value} priority — {result.title}"

        body = (
            f"Action required on a Power Platform Message Center announcement.\n\n"
            f"Source ID:   {item.id}\n"
            f"Title:       {result.title}\n"
            f"Category:    {result.category.value}\n"
            f"Priority:    {result.priority.value}\n"
            f"Impact:      {result.impact.value}\n"
            f"Status:      {result.status.value}\n\n"
            f"Summary:\n{result.summary}\n\n"
            f"Recommended actions:\n{result.actions_taken}\n\n"
            f"-- PP MC Auto-Analysis (Python edition)\n"
        )
        msg.set_content(body)
        return msg

    def send_alert(self, item: MCItem, result: ClassificationResult) -> None:
        msg = self._build_message(item, result)
        with smtplib.SMTP(self._config.smtp_host, self._config.smtp_port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(self._config.smtp_username, self._config.smtp_password)
            smtp.send_message(msg)
        log.info("Alert sent to %s for item %s", self._config.admin_email_dl, item.id)
