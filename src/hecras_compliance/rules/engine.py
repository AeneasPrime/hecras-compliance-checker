"""Compliance rules engine.

Loads YAML rules from the federal baseline and an optional state overlay,
evaluates each rule against parsed HEC-RAS model data, and returns a list
of :class:`RuleResult` objects.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from hecras_compliance.parsers.geometry import GeometryFile
from hecras_compliance.parsers.plan import PlanFile
from hecras_compliance.parsers.flow import FlowFile
from hecras_compliance.parsers.project import ProjectFile

from .checks import HANDLER_REGISTRY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths to built-in rule files
# ---------------------------------------------------------------------------

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
_FEMA_RULES = _CONFIG_DIR / "fema_rules.yaml"
_STATES_DIR = _CONFIG_DIR / "states"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ModelData:
    """Container for all parsed HEC-RAS data fed into the engine."""
    geometry: GeometryFile | None = None
    plan: PlanFile | None = None
    flow: FlowFile | None = None
    project: ProjectFile | None = None


@dataclass
class RuleResult:
    """Outcome of evaluating a single rule (possibly at a single location)."""
    rule_id: str
    rule_name: str
    status: str         # PASS | FAIL | WARNING | SKIPPED
    severity: str       # error | warning | info
    actual_value: str
    expected_value: str
    citation: str
    citation_url: str
    message: str
    location: str = ""


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _getattr_path(obj: Any, path: str) -> Any:
    """Walk a dot-separated attribute path, returning ``None`` on failure."""
    for part in path.split("."):
        if obj is None:
            return None
        obj = getattr(obj, part, None)
    return obj


def _resolve_values(
    model: ModelData, applies_to: str,
) -> list[tuple[Any, str]]:
    """Resolve an ``applies_to`` path to a list of ``(value, location)`` pairs.

    For iterable paths (containing ``[]``), one entry per collection item.
    For scalar paths, a single entry.
    """
    if "[]" in applies_to:
        # e.g. "geometry.cross_sections[].manning_n_channel"
        container_path, _, field_path = applies_to.partition("[]")
        container_path = container_path.rstrip(".")
        field_path = field_path.lstrip(".")

        container = _getattr_path(model, container_path)
        if container is None or not hasattr(container, "__iter__"):
            return []

        results: list[tuple[Any, str]] = []
        for item in container:
            station = getattr(item, "river_station", None)
            loc = f"RS {station}" if station is not None else ""

            if field_path == "manning_n_overbank":
                # Special case: check both left and right overbank
                left = getattr(item, "manning_n_left", None)
                right = getattr(item, "manning_n_right", None)
                if left is not None:
                    results.append((left, f"{loc} LOB" if loc else "LOB"))
                if right is not None:
                    results.append((right, f"{loc} ROB" if loc else "ROB"))
            else:
                val = _getattr_path(item, field_path)
                results.append((val, loc))

        return results

    # Scalar path — e.g. "plan.encroachment.target_surcharge"
    val = _getattr_path(model, applies_to)
    return [(val, "")]


# ---------------------------------------------------------------------------
# Rule loading
# ---------------------------------------------------------------------------

def load_rules(
    state: str | None = None,
    fema_path: Path | None = None,
    state_path: Path | None = None,
) -> list[dict]:
    """Load FEMA baseline rules and optionally merge a state overlay.

    Args:
        state: Lowercase state name (e.g. ``"texas"``).  Used to locate
            ``config/states/{state}.yaml``.  Ignored when *state_path*
            is provided.
        fema_path: Override path to the FEMA rules file.
        state_path: Override path to the state rules file.

    Returns:
        Merged list of rule dicts ready for evaluation.
    """
    fema_file = fema_path or _FEMA_RULES
    fema_data = yaml.safe_load(fema_file.read_text())
    rules: list[dict] = list(fema_data.get("rules", []))

    # State overlay
    st_file = state_path
    if st_file is None and state:
        st_file = _STATES_DIR / f"{state.lower()}.yaml"

    if st_file and st_file.exists():
        st_data = yaml.safe_load(st_file.read_text())
        supersedes = set(st_data.get("supersedes", []) or [])
        if supersedes:
            rules = [r for r in rules if r["id"] not in supersedes]
        rules.extend(st_data.get("rules", []) or [])

    return rules


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ComplianceEngine:
    """Evaluate YAML-defined compliance rules against parsed model data."""

    def __init__(
        self,
        state: str | None = None,
        fema_path: Path | None = None,
        state_path: Path | None = None,
    ) -> None:
        self.rules = load_rules(
            state=state, fema_path=fema_path, state_path=state_path,
        )

    def evaluate(self, model: ModelData) -> list[RuleResult]:
        """Run every loaded rule against *model* and return results."""
        results: list[RuleResult] = []
        for rule in self.rules:
            try:
                results.extend(self._evaluate_rule(rule, model))
            except Exception:
                logger.warning(
                    "Error evaluating rule %s", rule.get("id", "?"),
                    exc_info=True,
                )
                results.append(RuleResult(
                    rule_id=rule.get("id", "?"),
                    rule_name=rule.get("name", "?"),
                    status="SKIPPED",
                    severity=rule.get("severity", "error"),
                    actual_value="",
                    expected_value="",
                    citation=rule.get("citation", ""),
                    citation_url=rule.get("citation_url", ""),
                    message="Internal error evaluating rule.",
                ))
        return results

    # ------------------------------------------------------------------

    def _evaluate_rule(
        self, rule: dict, model: ModelData,
    ) -> list[RuleResult]:
        check_type = rule.get("check_type", "")

        if check_type == "custom":
            return self._run_custom(rule, model)

        # Generic checks work on resolved values
        values = _resolve_values(model, rule.get("applies_to", ""))

        if not values:
            return [self._skipped(rule, "Data not available")]

        out: list[RuleResult] = []
        for val, location in values:
            if val is None:
                out.append(self._skipped(rule, "Value is None", location))
                continue

            if check_type == "range":
                out.append(self._check_range(rule, val, location))
            elif check_type == "exact":
                out.append(self._check_exact(rule, val, location))
            elif check_type == "exists":
                out.append(self._check_exists(rule, val, location))
            else:
                out.append(self._skipped(
                    rule, f"Unknown check_type: {check_type}", location,
                ))

        return out

    # ------------------------------------------------------------------
    # Generic checks
    # ------------------------------------------------------------------

    def _check_range(
        self, rule: dict, val: Any, location: str,
    ) -> RuleResult:
        params = rule.get("parameters", {})
        lo = params.get("min", float("-inf"))
        hi = params.get("max", float("inf"))
        passed = lo <= val <= hi

        status = "PASS" if passed else (
            "WARNING" if rule["severity"] == "warning" else "FAIL"
        )
        expected = f"{lo} – {hi}"

        if passed:
            msg = f"Value {val} is within range [{lo}, {hi}]."
        else:
            msg = f"Value {val} is outside range [{lo}, {hi}]."

        return RuleResult(
            rule_id=rule["id"],
            rule_name=rule["name"],
            status=status,
            severity=rule["severity"],
            actual_value=str(val),
            expected_value=expected,
            citation=rule["citation"],
            citation_url=rule.get("citation_url", ""),
            message=msg,
            location=location,
        )

    def _check_exact(
        self, rule: dict, val: Any, location: str,
    ) -> RuleResult:
        expected = rule.get("parameters", {}).get("value")
        passed = val == expected

        status = "PASS" if passed else (
            "WARNING" if rule["severity"] == "warning" else "FAIL"
        )

        return RuleResult(
            rule_id=rule["id"],
            rule_name=rule["name"],
            status=status,
            severity=rule["severity"],
            actual_value=str(val),
            expected_value=str(expected),
            citation=rule["citation"],
            citation_url=rule.get("citation_url", ""),
            message=f"Value {val} {'matches' if passed else 'does not match'} expected {expected}.",
            location=location,
        )

    def _check_exists(
        self, rule: dict, val: Any, location: str,
    ) -> RuleResult:
        return RuleResult(
            rule_id=rule["id"],
            rule_name=rule["name"],
            status="PASS",
            severity=rule["severity"],
            actual_value=str(val),
            expected_value="present",
            citation=rule["citation"],
            citation_url=rule.get("citation_url", ""),
            message="Value is present.",
            location=location,
        )

    # ------------------------------------------------------------------
    # Custom handler dispatch
    # ------------------------------------------------------------------

    def _run_custom(
        self, rule: dict, model: ModelData,
    ) -> list[RuleResult]:
        handler_name = rule.get("parameters", {}).get("handler", "")
        handler = HANDLER_REGISTRY.get(handler_name)

        if handler is None:
            return [self._skipped(
                rule, f"Unknown handler: {handler_name}",
            )]

        raw_results = handler(rule, model)
        return [
            RuleResult(
                rule_id=r["rule_id"],
                rule_name=r["rule_name"],
                status=r["status"],
                severity=r["severity"],
                actual_value=r.get("actual_value", ""),
                expected_value=r.get("expected_value", ""),
                citation=r.get("citation", ""),
                citation_url=r.get("citation_url", rule.get("citation_url", "")),
                message=r.get("message", ""),
                location=r.get("location", ""),
            )
            for r in raw_results
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _skipped(rule: dict, reason: str, location: str = "") -> RuleResult:
        return RuleResult(
            rule_id=rule["id"],
            rule_name=rule["name"],
            status="SKIPPED",
            severity=rule["severity"],
            actual_value="",
            expected_value="",
            citation=rule["citation"],
            citation_url=rule.get("citation_url", ""),
            message=reason,
            location=location,
        )
