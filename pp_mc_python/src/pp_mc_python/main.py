"""Main entry point — orchestrates all 9 stages for every item pulled from
the source list. One pass = one trigger fire in the Power Automate model.

CLI:
    python -m pp_mc_python.main --once    # process all pending items, exit
    python -m pp_mc_python.main --watch   # poll continuously
"""

from __future__ import annotations
import argparse
import logging
import sys
import time

from .config import Config
from .context import FlowContext
from .pipeline import dedup_gate, clean, classify as classify_mod, store as store_mod
from .pipeline import notify as notify_mod, update_source, errors
from .sources.sharepoint import SharePointSource
from .sinks.admin_list import AdminListWriter
from .sinks.email import EmailSender
from .models import MCItem

log = logging.getLogger("pp_mc_python")


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def process_one(item: MCItem, classifier: classify_mod.ClassifierClient,
                source: SharePointSource, writer: AdminListWriter,
                mailer: EmailSender) -> None:
    """One full pass through the 9-stage pipeline for a single item.

    Stage numbering matches the technical documentation exactly so the mapping
    is one-to-one when reading the Power Automate flow alongside this code.
    """
    # Step 2 — initialise variables (constructor)
    ctx = FlowContext(source_item=item)

    try:
        # Step 3 — dedup gate (skip path is a clean exit, not an error)
        with errors.stage(ctx, "3-dedup_gate"):
            if not dedup_gate.needs_processing(ctx):
                return

        # Step 4 — clean message
        with errors.stage(ctx, "4-clean"):
            clean.clean(ctx)

        # Step 5 — AI classification ("The Brain")
        with errors.stage(ctx, "5-classify"):
            classify_mod.classify(ctx, classifier)

        # Step 6 — store in Admin List
        with errors.stage(ctx, "6-store"):
            store_mod.store(ctx, writer)

        # Step 7 — notify if action required
        with errors.stage(ctx, "7-notify"):
            notify_mod.notify_if_action_required(ctx, mailer)

        # Step 8 — update original item (mark as processed)
        with errors.stage(ctx, "8-update_source"):
            update_source.mark_processed(ctx, source)

    except Exception:
        # Step 9 — global error handler. The `stage` context manager has
        # already recorded the structured failure; we swallow here so a
        # single bad item doesn't take down the batch run.
        log.exception("Pipeline aborted for item %s", item.id)


def run_once(config: Config) -> int:
    """Process every currently-pending item, then return."""
    source = SharePointSource(config)
    writer = AdminListWriter(config)
    mailer = EmailSender(config)
    classifier = classify_mod.ClassifierClient(config)

    items = source.poll_changes()
    log.info("Processing %d items", len(items))
    for item in items:
        process_one(item, classifier, source, writer, mailer)
    return len(items)


def run_watch(config: Config) -> None:
    """Poll forever until interrupted."""
    log.info("Watch mode — polling every %ds", config.poll_interval_seconds)
    while True:
        try:
            run_once(config)
        except Exception:
            log.exception("Top-level error in watch loop — continuing after interval")
        time.sleep(config.poll_interval_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pp_mc_python")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--once", action="store_true", help="Process pending items and exit")
    group.add_argument("--watch", action="store_true", help="Poll continuously")
    args = parser.parse_args(argv)

    config = Config.load()
    configure_logging(config.log_level)

    if args.once:
        run_once(config)
    else:
        run_watch(config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
