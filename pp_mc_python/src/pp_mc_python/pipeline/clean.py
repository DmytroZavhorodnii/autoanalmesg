"""Step 4 — SCOPE: Clean Message.

The source `FullMessage` field is raw HTML (sometimes Latin1-encoded, often
inconsistent across older announcements). The Power Automate scope runs the
built-in `Html to Text` data operation to strip tags and preserve logical
content. Here we do the same with BeautifulSoup.

The output is assigned to `ctx.var_clean_message` — the only thing the AI
prompt ever sees.
"""

from __future__ import annotations
import logging
import re
from bs4 import BeautifulSoup
from ..context import FlowContext

log = logging.getLogger(__name__)

_WHITESPACE = re.compile(r"\s+")
_BLOCK_LEVEL = {"p", "div", "li", "br", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}


def html_to_text(html: str) -> str:
    """Strip HTML, preserve the logical content structure."""
    if not html:
        return ""

    soup = BeautifulSoup(html, "lxml")

    # Drop noise that never carries content
    for tag in soup(["style", "script", "head", "meta", "link"]):
        tag.decompose()

    # Break block-level elements with newlines so they don't run together
    for tag in soup.find_all(_BLOCK_LEVEL):
        tag.append("\n")

    text = soup.get_text()

    # Collapse whitespace - keep paragraph structure with double newlines
    paragraphs = [
        _WHITESPACE.sub(" ", line).strip()
        for line in text.split("\n")
    ]
    paragraphs = [p for p in paragraphs if p]
    return "\n\n".join(paragraphs)


def clean(ctx: FlowContext) -> None:
    """Step 4 in-place: populates `ctx.var_clean_message`."""
    ctx.var_clean_message = html_to_text(ctx.source_item.full_message_html)
    log.debug("Cleaned message for item %s: %d chars", ctx.source_item.id, len(ctx.var_clean_message))
