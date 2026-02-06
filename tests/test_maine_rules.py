"""Tests for the Maine state compliance rules YAML configuration."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

STATES_DIR = (
    Path(__file__).parent.parent
    / "src"
    / "hecras_compliance"
    / "config"
    / "states"
)
MAINE_PATH = STATES_DIR / "maine.yaml"

VALID_SEVERITIES = {"error", "warning", "info"}
VALID_CHECK_TYPES = {"range", "exact", "exists", "custom"}
REQUIRED_FIELDS = {
    "id", "name", "description", "severity",
    "citation", "check_type", "parameters", "applies_to",
}


@pytest.fixture(scope="module")
def maine() -> dict:
    return yaml.safe_load(MAINE_PATH.read_text())


@pytest.fixture(scope="module")
def rules(maine: dict) -> list[dict]:
    return maine["rules"]


def _get_rule(rules: list[dict], rule_id: str) -> dict:
    for r in rules:
        if r["id"] == rule_id:
            return r
    pytest.fail(f"Rule {rule_id} not found")


# ===================================================================
# File existence
# ===================================================================


class TestFilesExist:
    def test_maine_yaml_exists(self):
        assert MAINE_PATH.exists()


# ===================================================================
# Maine metadata
# ===================================================================


class TestMaineMetadata:
    def test_state_name(self, maine: dict):
        assert maine["state"] == "Maine"

    def test_state_abbreviation(self, maine: dict):
        assert maine["state_abbreviation"] == "ME"

    def test_supersedes_is_list(self, maine: dict):
        assert isinstance(maine["supersedes"], list)

    def test_supersedes_is_empty(self, maine: dict):
        assert len(maine["supersedes"]) == 0

    def test_does_not_supersede_fema_fw_001(self, maine: dict):
        assert "FEMA-FW-001" not in maine["supersedes"]


# ===================================================================
# Schema validation
# ===================================================================


class TestMaineRulesSchema:
    def test_rules_is_list(self, rules: list[dict]):
        assert isinstance(rules, list)

    def test_has_rules(self, rules: list[dict]):
        assert len(rules) >= 3

    def test_all_required_fields_present(self, rules: list[dict]):
        for rule in rules:
            missing = REQUIRED_FIELDS - rule.keys()
            assert not missing, f"Rule {rule.get('id', '???')} missing: {missing}"

    def test_ids_are_unique(self, rules: list[dict]):
        ids = [r["id"] for r in rules]
        assert len(ids) == len(set(ids))

    def test_ids_start_with_me(self, rules: list[dict]):
        for rule in rules:
            assert rule["id"].startswith("ME-"), (
                f"{rule['id']} should start with ME-"
            )

    def test_severity_values(self, rules: list[dict]):
        for rule in rules:
            assert rule["severity"] in VALID_SEVERITIES

    def test_check_type_values(self, rules: list[dict]):
        for rule in rules:
            assert rule["check_type"] in VALID_CHECK_TYPES

    def test_descriptions_nonempty(self, rules: list[dict]):
        for rule in rules:
            assert rule["description"].strip()

    def test_citations_nonempty(self, rules: list[dict]):
        for rule in rules:
            assert rule["citation"].strip()

    def test_applies_to_nonempty(self, rules: list[dict]):
        for rule in rules:
            assert rule["applies_to"].strip()

    def test_custom_rules_have_handler(self, rules: list[dict]):
        for rule in rules:
            if rule["check_type"] == "custom":
                assert "handler" in rule["parameters"]


# ===================================================================
# Required flood events
# ===================================================================


class TestRequiredFloodEvents:
    def test_100yr_rule_exists(self, rules):
        rule = _get_rule(rules, "ME-EVENT-001")
        assert rule["severity"] == "error"
        assert rule["check_type"] == "custom"

    def test_100yr_accepted_names(self, rules):
        rule = _get_rule(rules, "ME-EVENT-001")
        lower_names = [n.lower() for n in rule["parameters"]["accepted_names"]]
        assert "100yr" in lower_names
        assert "1% annual chance" in lower_names
        assert "base flood" in lower_names

    def test_100yr_applies_to_profiles(self, rules):
        rule = _get_rule(rules, "ME-EVENT-001")
        assert "profile" in rule["applies_to"]

    def test_100yr_cites_maine(self, rules):
        rule = _get_rule(rules, "ME-EVENT-001")
        assert "Maine" in rule["citation"]

    def test_500yr_rule_exists(self, rules):
        rule = _get_rule(rules, "ME-EVENT-002")
        assert rule["severity"] == "warning"
        assert rule["check_type"] == "custom"

    def test_500yr_accepted_names(self, rules):
        rule = _get_rule(rules, "ME-EVENT-002")
        lower_names = [n.lower() for n in rule["parameters"]["accepted_names"]]
        assert "500yr" in lower_names
        assert "0.2% annual chance" in lower_names

    def test_500yr_applies_to_profiles(self, rules):
        rule = _get_rule(rules, "ME-EVENT-002")
        assert "profile" in rule["applies_to"]

    def test_500yr_cites_maine(self, rules):
        rule = _get_rule(rules, "ME-EVENT-002")
        assert "Maine" in rule["citation"] or "Dam Safety" in rule["citation"]


# ===================================================================
# Freeboard
# ===================================================================


class TestFreeboard:
    def test_rule_exists(self, rules):
        rule = _get_rule(rules, "ME-FB-001")
        assert rule["severity"] == "info"
        assert rule["check_type"] == "custom"

    def test_handler_is_manual_review(self, rules):
        rule = _get_rule(rules, "ME-FB-001")
        assert rule["parameters"]["handler"] == "flag_for_manual_review"

    def test_has_review_note(self, rules):
        rule = _get_rule(rules, "ME-FB-001")
        assert "review_note" in rule["parameters"]
        assert rule["parameters"]["review_note"].strip()

    def test_review_note_mentions_freeboard(self, rules):
        rule = _get_rule(rules, "ME-FB-001")
        note = rule["parameters"]["review_note"].lower()
        assert "freeboard" in note

    def test_review_note_mentions_one_foot(self, rules):
        rule = _get_rule(rules, "ME-FB-001")
        note = rule["parameters"]["review_note"].lower()
        assert "1 foot" in note

    def test_review_note_mentions_crs(self, rules):
        rule = _get_rule(rules, "ME-FB-001")
        note = rule["parameters"]["review_note"].lower()
        assert "crs" in note

    def test_cites_maine_ordinance(self, rules):
        rule = _get_rule(rules, "ME-FB-001")
        assert "Maine" in rule["citation"]


# ===================================================================
# Engine integration
# ===================================================================


class TestEngineIntegration:
    def test_engine_loads_maine_rules(self):
        from hecras_compliance.rules.engine import ComplianceEngine

        engine = ComplianceEngine(state="maine")
        rule_ids = [r["id"] for r in engine.rules]
        assert "ME-EVENT-001" in rule_ids
        assert "ME-EVENT-002" in rule_ids
        assert "ME-FB-001" in rule_ids

    def test_engine_does_not_supersede_fema_fw(self):
        from hecras_compliance.rules.engine import ComplianceEngine

        engine = ComplianceEngine(state="maine")
        rule_ids = [r["id"] for r in engine.rules]
        assert "FEMA-FW-001" in rule_ids

    def test_engine_includes_federal_rules(self):
        from hecras_compliance.rules.engine import ComplianceEngine

        engine = ComplianceEngine(state="maine")
        rule_ids = [r["id"] for r in engine.rules]
        fema_ids = [rid for rid in rule_ids if rid.startswith("FEMA-")]
        assert len(fema_ids) >= 6

    def test_engine_total_rule_count(self):
        from hecras_compliance.rules.engine import ComplianceEngine

        engine = ComplianceEngine(state="maine")
        assert len(engine.rules) >= 11  # 8 FEMA + 3 Maine

    def test_cli_resolves_me_abbreviation(self):
        from hecras_compliance.cli import _resolve_state

        assert _resolve_state("ME") == "maine"
        assert _resolve_state("me") == "maine"
        assert _resolve_state("Maine") == "maine"
        assert _resolve_state("MAINE") == "maine"

    def test_cli_display_name(self):
        from hecras_compliance.cli import _state_display_name

        assert _state_display_name("maine") == "Maine"
