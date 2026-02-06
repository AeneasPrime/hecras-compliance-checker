"""Custom check handlers for flow-profile existence rules."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hecras_compliance.rules.engine import ModelData, RuleResult


def _make_result(
    rule: dict,
    *,
    status: str,
    actual: str,
    expected: str,
    message: str,
) -> dict:
    """Build a result dict (converted to RuleResult by the engine)."""
    return {
        "rule_id": rule["id"],
        "rule_name": rule["name"],
        "status": status,
        "severity": rule["severity"],
        "actual_value": actual,
        "expected_value": expected,
        "citation": rule["citation"],
        "message": message,
    }


def check_profile_exists(rule: dict, model_data: ModelData) -> list[dict]:
    """Check that at least one flow profile matches the accepted names."""
    if model_data.flow is None:
        return [_make_result(
            rule,
            status="SKIPPED",
            actual="no flow data",
            expected="",
            message="No flow file loaded; cannot check profile names.",
        )]

    accepted = [n.lower() for n in rule["parameters"].get("accepted_names", [])]
    profile_names = model_data.flow.profile_names

    if not profile_names:
        return [_make_result(
            rule,
            status="SKIPPED",
            actual="no profiles",
            expected=", ".join(rule["parameters"].get("accepted_names", [])),
            message="Flow file contains no profiles.",
        )]

    matched = any(
        pn.strip().lower() in accepted for pn in profile_names
    )

    if matched:
        return [_make_result(
            rule,
            status="PASS",
            actual=", ".join(profile_names),
            expected=f"one of: {', '.join(rule['parameters']['accepted_names'])}",
            message=f"Required profile found in: {', '.join(profile_names)}.",
        )]

    return [_make_result(
        rule,
        status="FAIL",
        actual=", ".join(profile_names),
        expected=f"one of: {', '.join(rule['parameters']['accepted_names'])}",
        message=(
            f"No profile matching the required event was found. "
            f"Profiles present: {', '.join(profile_names)}."
        ),
    )]


# Alias — the FEMA rule references this name specifically
check_100yr_profile_exists = check_profile_exists
