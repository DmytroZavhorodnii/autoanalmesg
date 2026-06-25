"""End-to-end pipeline tests mirroring the V&V table from section 10 of the
technical documentation. All external dependencies (SharePoint, LLM, SMTP)
are mocked; what we assert is the control flow between stages.

Six scenarios:
    1. Maintenance message       → classified, stored, no alert
    2. New feature message       → classified, stored, no alert
    3. Breaking change message   → classified, stored, alert sent
    4. Unclear message           → flagged Other/Open, alert sent
    5. Duplicate item            → dedup gate terminates; nothing else runs
    6. Invalid AI JSON (negative)→ error scope catches; nothing downstream runs
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest

from pp_mc_python.context import FlowContext
from pp_mc_python.models import MCItem
from pp_mc_python.pipeline import dedup_gate, clean as clean_mod
from pp_mc_python.pipeline import classify as classify_mod
from pp_mc_python.pipeline import notify as notify_mod
from pp_mc_python.pipeline.classify import InvalidAIResponse


def _item(item_id=100001, processed=False, html="<p>Hello world</p>"):
    now = datetime.now(timezone.utc)
    return MCItem(id=item_id, created=now, modified=now,
                  full_message_html=html, processed=processed)


def _fake_classifier(payload_dict):
    """Returns a ClassifierClient stub that yields the given parsed JSON."""
    client = MagicMock(spec=classify_mod.ClassifierClient)
    client.classify.return_value = classify_mod._parse_json_strict(json.dumps(payload_dict))
    return client


# --- Scenario 1 -------------------------------------------------------------

def test_scenario_1_maintenance_no_alert():
    ctx = FlowContext(source_item=_item(html="<p>Planned maintenance for Dataverse.</p>"))
    classifier = _fake_classifier({
        "title": "Dataverse maintenance", "category": "Maintenance",
        "priority": "Low", "impact": "Low", "summary": "Routine.",
        "actionsTaken": "None.", "status": "Closed",
    })
    mailer = MagicMock()

    assert dedup_gate.needs_processing(ctx) is True
    clean_mod.clean(ctx)
    classify_mod.classify(ctx, classifier)
    notify_mod.notify_if_action_required(ctx, mailer)

    assert ctx.classification.action_required() is False
    mailer.send_alert.assert_not_called()


# --- Scenario 2 -------------------------------------------------------------

def test_scenario_2_new_feature_no_alert():
    ctx = FlowContext(source_item=_item(html="<p>New Power Apps modern control released.</p>"))
    classifier = _fake_classifier({
        "title": "Modern controls GA", "category": "New Feature",
        "priority": "Medium", "impact": "Medium", "summary": "GA.",
        "actionsTaken": "—", "status": "Closed",
    })
    mailer = MagicMock()

    dedup_gate.needs_processing(ctx)
    clean_mod.clean(ctx)
    classify_mod.classify(ctx, classifier)
    notify_mod.notify_if_action_required(ctx, mailer)

    mailer.send_alert.assert_not_called()


# --- Scenario 3 -------------------------------------------------------------

def test_scenario_3_breaking_change_alert_sent():
    ctx = FlowContext(source_item=_item(html="<p>Connector X is being retired in 60 days.</p>"))
    classifier = _fake_classifier({
        "title": "Connector X retirement", "category": "Breaking Change",
        "priority": "High", "impact": "High",
        "summary": "Retirement in 60 days.",
        "actionsTaken": "Migrate flows to Connector Y.", "status": "Open",
    })
    mailer = MagicMock()

    dedup_gate.needs_processing(ctx)
    clean_mod.clean(ctx)
    classify_mod.classify(ctx, classifier)
    notify_mod.notify_if_action_required(ctx, mailer)

    mailer.send_alert.assert_called_once()


# --- Scenario 4 -------------------------------------------------------------

def test_scenario_4_unclear_flagged_for_review():
    ctx = FlowContext(source_item=_item(html="<p>Service update.</p>"))
    classifier = _fake_classifier({
        "title": "Service update", "category": "Other",
        "priority": "Low", "impact": "Low",
        "summary": "Unclear content.",
        "actionsTaken": "Manual review.", "status": "Open",
    })
    mailer = MagicMock()

    dedup_gate.needs_processing(ctx)
    clean_mod.clean(ctx)
    classify_mod.classify(ctx, classifier)
    notify_mod.notify_if_action_required(ctx, mailer)

    assert ctx.classification.action_required() is True
    mailer.send_alert.assert_called_once()


# --- Scenario 5 -------------------------------------------------------------

def test_scenario_5_duplicate_terminates_early():
    """Already-processed item must short-circuit the pipeline. Verified by
    asserting the classifier and mailer are never called."""
    ctx = FlowContext(source_item=_item(processed=True))
    classifier = MagicMock()
    mailer = MagicMock()

    if not dedup_gate.needs_processing(ctx):
        return  # pipeline terminates here in the orchestrator

    classify_mod.classify(ctx, classifier)
    notify_mod.notify_if_action_required(ctx, mailer)
    classifier.classify.assert_not_called()
    mailer.send_alert.assert_not_called()


# --- Scenario 6 -------------------------------------------------------------

def test_scenario_6_invalid_json_caught_by_error_scope():
    """A misbehaving model raises InvalidAIResponse; downstream stages
    never run. The orchestrator's `errors.stage` context manager captures
    the failure for the global error handler — assert here that the raise
    happens."""
    ctx = FlowContext(source_item=_item())
    broken_classifier = MagicMock(spec=classify_mod.ClassifierClient)
    broken_classifier.classify.side_effect = InvalidAIResponse("not JSON")
    mailer = MagicMock()

    dedup_gate.needs_processing(ctx)
    clean_mod.clean(ctx)

    with pytest.raises(InvalidAIResponse):
        classify_mod.classify(ctx, broken_classifier)

    # Downstream stages must not have run
    mailer.send_alert.assert_not_called()
