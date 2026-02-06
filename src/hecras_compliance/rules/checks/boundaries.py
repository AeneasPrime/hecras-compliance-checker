"""Custom check handler for boundary-condition existence."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hecras_compliance.rules.engine import ModelData


def check_boundary_conditions_defined(
    rule: dict, model_data: ModelData,
) -> list[dict]:
    """Verify that boundary conditions are defined in the flow file."""
    if model_data.flow is None:
        return [{
            "rule_id": rule["id"],
            "rule_name": rule["name"],
            "status": "SKIPPED",
            "severity": rule["severity"],
            "actual_value": "no flow data",
            "expected_value": "boundary conditions defined",
            "citation": rule["citation"],
            "message": "No flow file loaded; cannot check boundary conditions.",
        }]

    flow = model_data.flow

    if flow.is_steady:
        count = len(flow.steady_boundaries)
        bc_type = "steady"
    else:
        count = len(flow.unsteady_boundaries)
        bc_type = "unsteady"

    if count > 0:
        return [{
            "rule_id": rule["id"],
            "rule_name": rule["name"],
            "status": "PASS",
            "severity": rule["severity"],
            "actual_value": f"{count} {bc_type} boundary conditions",
            "expected_value": "at least 1 boundary condition",
            "citation": rule["citation"],
            "message": f"{count} {bc_type} boundary condition(s) defined.",
        }]

    return [{
        "rule_id": rule["id"],
        "rule_name": rule["name"],
        "status": "FAIL",
        "severity": rule["severity"],
        "actual_value": f"0 {bc_type} boundary conditions",
        "expected_value": "at least 1 boundary condition",
        "citation": rule["citation"],
        "message": (
            f"No {bc_type} boundary conditions found. Every reach endpoint "
            f"must have an assigned boundary condition."
        ),
    }]
