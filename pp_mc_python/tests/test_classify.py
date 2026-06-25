"""Test Step 5 — AI Classification: JSON parsing & schema validation.

We mock the LLM entirely; these tests focus on the contract enforcement,
which is what the global Error Handling scope catches when the model
misbehaves in production.
"""

import json
import pytest
from pp_mc_python.pipeline.classify import _parse_json_strict, InvalidAIResponse
from pp_mc_python.models import Category, Priority, ImpactLevel, Status


VALID_MAINTENANCE = json.dumps({
    "title": "Dataverse maintenance window",
    "category": "Maintenance",
    "priority": "Low",
    "impact": "Low",
    "summary": "Planned maintenance; no action needed.",
    "actionsTaken": "No action required.",
    "status": "Closed",
})

VALID_BREAKING = json.dumps({
    "title": "Power Automate connector deprecation",
    "category": "Breaking Change",
    "priority": "High",
    "impact": "High",
    "summary": "Connector X will be removed Aug 2026.",
    "actionsTaken": "Migrate flows to connector Y before Aug 1.",
    "status": "Open",
})


def test_maintenance_message_parses():
    """Scenario 1 from V&V table — Maintenance / Low, no alert."""
    result = _parse_json_strict(VALID_MAINTENANCE)
    assert result.category == Category.MAINTENANCE
    assert result.priority == Priority.LOW
    assert result.status == Status.CLOSED
    assert result.action_required() is False


def test_breaking_change_message_parses():
    """Scenario 3 from V&V table — Breaking Change, alert email sent."""
    result = _parse_json_strict(VALID_BREAKING)
    assert result.category == Category.BREAKING_CHANGE
    assert result.priority == Priority.HIGH
    assert result.status == Status.OPEN
    assert result.action_required() is True


def test_new_feature_message_parses():
    """Scenario 2 — New Feature, stored, no alert."""
    payload = json.dumps({
        "title": "Power Apps modern controls GA",
        "category": "New Feature", "priority": "Medium",
        "impact": "Medium", "summary": "GA.", "actionsTaken": "—",
        "status": "Closed",
    })
    result = _parse_json_strict(payload)
    assert result.category == Category.NEW_FEATURE
    assert result.status == Status.CLOSED


def test_unclear_message_parses_as_other():
    """Scenario 4 — Unrelated/unclear → Other, flagged for review."""
    payload = json.dumps({
        "title": "Service update",
        "category": "Other", "priority": "Low", "impact": "Low",
        "summary": "Unclear content.", "actionsTaken": "Manual review recommended.",
        "status": "Open",
    })
    result = _parse_json_strict(payload)
    assert result.category == Category.OTHER
    assert result.action_required() is True


def test_invalid_json_raises():
    """Scenario 6 — Invalid AI JSON (negative test). Must raise so the error
    scope picks it up."""
    with pytest.raises(InvalidAIResponse):
        _parse_json_strict("not actually json")


def test_missing_field_raises():
    payload = json.dumps({"title": "x"})  # most fields missing
    with pytest.raises(InvalidAIResponse):
        _parse_json_strict(payload)


def test_unknown_enum_raises():
    payload = json.dumps({
        "title": "x", "category": "Wat", "priority": "Low",
        "impact": "Low", "summary": "x", "actionsTaken": "x", "status": "Open",
    })
    with pytest.raises(InvalidAIResponse):
        _parse_json_strict(payload)


def test_handles_markdown_code_fence_defensively():
    """Some LLMs ignore 'no code fences' — strip them rather than fail."""
    fenced = "```json\n" + VALID_MAINTENANCE + "\n```"
    result = _parse_json_strict(fenced)
    assert result.category == Category.MAINTENANCE
