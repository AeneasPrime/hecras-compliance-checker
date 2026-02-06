"""Tests for the Texas state compliance rules YAML configuration."""

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
TEXAS_PATH = STATES_DIR / "texas.yaml"
TEMPLATE_PATH = STATES_DIR / "_template.yaml"

VALID_SEVERITIES = {"error", "warning", "info"}
VALID_CHECK_TYPES = {"range", "exact", "exists", "custom"}
REQUIRED_FIELDS = {
    "id", "name", "description", "severity",
    "citation", "check_type", "parameters", "applies_to",
}


@pytest.fixture(scope="module")
def texas() -> dict:
    return yaml.safe_load(TEXAS_PATH.read_text())


@pytest.fixture(scope="module")
def rules(texas: dict) -> list[dict]:
    return texas["rules"]


def _get_rule(rules: list[dict], rule_id: str) -> dict:
    for r in rules:
        if r["id"] == rule_id:
            return r
    pytest.fail(f"Rule {rule_id} not found")


# ===================================================================
# File existence
# ===================================================================


class TestFilesExist:
    def test_texas_yaml_exists(self):
        assert TEXAS_PATH.exists()

    def test_template_yaml_exists(self):
        assert TEMPLATE_PATH.exists()

    def test_states_directory_exists(self):
        assert STATES_DIR.is_dir()


# ===================================================================
# Texas metadata
# ===================================================================


class TestTexasMetadata:
    def test_state_name(self, texas: dict):
        assert texas["state"] == "Texas"

    def test_state_abbreviation(self, texas: dict):
        assert texas["state_abbreviation"] == "TX"

    def test_supersedes_fema_fw_001(self, texas: dict):
        assert "FEMA-FW-001" in texas["supersedes"]

    def test_supersedes_is_list(self, texas: dict):
        assert isinstance(texas["supersedes"], list)


# ===================================================================
# Schema validation (same structure as federal rules)
# ===================================================================


class TestTexasRulesSchema:
    def test_rules_is_list(self, rules: list[dict]):
        assert isinstance(rules, list)

    def test_has_rules(self, rules: list[dict]):
        assert len(rules) >= 6

    def test_all_required_fields_present(self, rules: list[dict]):
        for rule in rules:
            missing = REQUIRED_FIELDS - rule.keys()
            assert not missing, f"Rule {rule.get('id', '???')} missing: {missing}"

    def test_ids_are_unique(self, rules: list[dict]):
        ids = [r["id"] for r in rules]
        assert len(ids) == len(set(ids))

    def test_ids_start_with_tx(self, rules: list[dict]):
        for rule in rules:
            assert rule["id"].startswith("TX-"), (
                f"{rule['id']} should start with TX-"
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

    def test_range_rules_have_min_max(self, rules: list[dict]):
        for rule in rules:
            if rule["check_type"] == "range":
                assert "min" in rule["parameters"]
                assert "max" in rule["parameters"]

    def test_custom_rules_have_handler(self, rules: list[dict]):
        for rule in rules:
            if rule["check_type"] == "custom":
                assert "handler" in rule["parameters"]


# ===================================================================
# Zero-rise floodway
# ===================================================================


class TestZeroRiseFloodway:
    def test_rule_exists(self, rules):
        rule = _get_rule(rules, "TX-FW-001")
        assert rule["severity"] == "error"

    def test_zero_rise_range(self, rules):
        rule = _get_rule(rules, "TX-FW-001")
        assert rule["check_type"] == "range"
        assert rule["parameters"]["min"] == 0.0
        assert rule["parameters"]["max"] == 0.0

    def test_cites_texas_law(self, rules):
        rule = _get_rule(rules, "TX-FW-001")
        assert "Texas" in rule["citation"]
        assert "16.3145" in rule["citation"]

    def test_applies_to_surcharge(self, rules):
        rule = _get_rule(rules, "TX-FW-001")
        assert "target_surcharge" in rule["applies_to"]


# ===================================================================
# Required flood events (10%, 2%, 1%, 0.2%)
# ===================================================================


class TestRequiredFloodEvents:
    @pytest.mark.parametrize("rule_id,name_fragment", [
        ("TX-EVENT-001", "10yr"),
        ("TX-EVENT-002", "50yr"),
        ("TX-EVENT-003", "100yr"),
        ("TX-EVENT-004", "500yr"),
    ])
    def test_event_rules_exist(self, rules, rule_id, name_fragment):
        rule = _get_rule(rules, rule_id)
        assert rule["severity"] == "error"
        assert rule["check_type"] == "custom"

    @pytest.mark.parametrize("rule_id,name_fragment", [
        ("TX-EVENT-001", "10yr"),
        ("TX-EVENT-002", "50yr"),
        ("TX-EVENT-003", "100yr"),
        ("TX-EVENT-004", "500yr"),
    ])
    def test_event_accepted_names_include_common_format(
        self, rules, rule_id, name_fragment
    ):
        rule = _get_rule(rules, rule_id)
        lower_names = [n.lower() for n in rule["parameters"]["accepted_names"]]
        assert name_fragment in lower_names

    @pytest.mark.parametrize("rule_id", [
        "TX-EVENT-001", "TX-EVENT-002", "TX-EVENT-003", "TX-EVENT-004",
    ])
    def test_event_applies_to_profiles(self, rules, rule_id):
        rule = _get_rule(rules, rule_id)
        assert "profile" in rule["applies_to"]

    @pytest.mark.parametrize("rule_id", [
        "TX-EVENT-001", "TX-EVENT-002", "TX-EVENT-003", "TX-EVENT-004",
    ])
    def test_event_cites_texas(self, rules, rule_id):
        rule = _get_rule(rules, rule_id)
        assert "Texas" in rule["citation"] or "299" in rule["citation"]


# ===================================================================
# Freeboard
# ===================================================================


class TestFreeboard:
    def test_rule_exists(self, rules):
        rule = _get_rule(rules, "TX-FB-001")
        assert rule["severity"] == "info"
        assert rule["check_type"] == "custom"

    def test_handler_is_manual_review(self, rules):
        rule = _get_rule(rules, "TX-FB-001")
        assert rule["parameters"]["handler"] == "flag_for_manual_review"

    def test_has_review_note(self, rules):
        rule = _get_rule(rules, "TX-FB-001")
        assert "review_note" in rule["parameters"]
        assert rule["parameters"]["review_note"].strip()


# ===================================================================
# Template file
# ===================================================================


class TestTemplate:
    @pytest.fixture(scope="class")
    def template(self) -> dict:
        return yaml.safe_load(TEMPLATE_PATH.read_text())

    def test_template_parses(self, template: dict):
        assert template is not None

    def test_has_state_field(self, template: dict):
        assert "state" in template

    def test_has_abbreviation_field(self, template: dict):
        assert "state_abbreviation" in template

    def test_has_supersedes_field(self, template: dict):
        assert "supersedes" in template

    def test_has_rules_field(self, template: dict):
        assert "rules" in template

    def test_rules_is_empty(self, template: dict):
        assert template["rules"] == [] or template["rules"] is None

    def test_state_is_blank(self, template: dict):
        assert template["state"] == ""

    def test_abbreviation_is_blank(self, template: dict):
        assert template["state_abbreviation"] == ""

    def test_template_contains_field_docs(self):
        text = TEMPLATE_PATH.read_text()
        # Verify the template documents every required field
        for field in REQUIRED_FIELDS:
            assert field in text, f"Template should document the '{field}' field"

    def test_template_contains_examples(self):
        text = TEMPLATE_PATH.read_text()
        assert "EXAMPLE" in text

    def test_template_documents_check_types(self):
        text = TEMPLATE_PATH.read_text()
        for ct in VALID_CHECK_TYPES:
            assert ct in text, f"Template should document check_type '{ct}'"

    def test_template_documents_applies_to_paths(self):
        text = TEMPLATE_PATH.read_text()
        assert "geometry.cross_sections" in text
        assert "plan.encroachment" in text
        assert "flow.profile_names" in text
