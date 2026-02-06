"""Custom check handler that flags items for manual review."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hecras_compliance.rules.engine import ModelData


def flag_for_manual_review(rule: dict, model_data: ModelData) -> list[dict]:
    """Return an INFO result directing the reviewer to check manually."""
    note = rule["parameters"].get("review_note", "Manual review required.")
    if isinstance(note, str):
        note = note.strip()

    return [{
        "rule_id": rule["id"],
        "rule_name": rule["name"],
        "status": "PASS",
        "severity": "info",
        "actual_value": "flagged for review",
        "expected_value": "manual verification",
        "citation": rule["citation"],
        "message": note,
    }]
