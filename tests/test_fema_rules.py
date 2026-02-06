"""Tests for the FEMA compliance rules YAML configuration."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

RULES_PATH = (
    Path(__file__).parent.parent
    / "src"
    / "hecras_compliance"
    / "config"
    / "fema_rules.yaml"
)

VALID_SEVERITIES = {"error", "warning", "info"}
VALID_CHECK_TYPES = {"range", "exact", "exists", "custom"}


@pytest.fixture(scope="module")
def rules() -> list[dict]:
    data = yaml.safe_load(RULES_PATH.read_text())
    return data["rules"]


# ===================================================================
# Schema validation
# ===================================================================


class TestRulesSchema:
    REQUIRED_FIELDS = {
        "id", "name", "description", "severity",
        "citation", "check_type", "parameters", "applies_to",
    }

    def test_rules_file_exists(self):
        assert RULES_PATH.exists()

    def test_yaml_parses(self):
        data = yaml.safe_load(RULES_PATH.read_text())
        assert "rules" in data

    def test_rules_is_list(self, rules: list[dict]):
        assert isinstance(rules, list)

    def test_at_least_8_rules(self, rules: list[dict]):
        assert len(rules) >= 8

    def test_all_required_fields_present(self, rules: list[dict]):
        for rule in rules:
            missing = self.REQUIRED_FIELDS - rule.keys()
            assert not missing, f"Rule {rule.get('id', '???')} missing: {missing}"

    def test_ids_are_unique(self, rules: list[dict]):
        ids = [r["id"] for r in rules]
        assert len(ids) == len(set(ids)), f"Duplicate IDs: {ids}"

    def test_severity_values(self, rules: list[dict]):
        for rule in rules:
            assert rule["severity"] in VALID_SEVERITIES, (
                f"{rule['id']}: invalid severity '{rule['severity']}'"
            )

    def test_check_type_values(self, rules: list[dict]):
        for rule in rules:
            assert rule["check_type"] in VALID_CHECK_TYPES, (
                f"{rule['id']}: invalid check_type '{rule['check_type']}'"
            )

    def test_descriptions_nonempty(self, rules: list[dict]):
        for rule in rules:
            assert rule["description"].strip(), f"{rule['id']}: empty description"

    def test_citations_nonempty(self, rules: list[dict]):
        for rule in rules:
            assert rule["citation"].strip(), f"{rule['id']}: empty citation"

    def test_applies_to_nonempty(self, rules: list[dict]):
        for rule in rules:
            assert rule["applies_to"].strip(), f"{rule['id']}: empty applies_to"

    def test_names_nonempty(self, rules: list[dict]):
        for rule in rules:
            assert rule["name"].strip(), f"{rule['id']}: empty name"


# ===================================================================
# Range check rules have min/max
# ===================================================================


class TestRangeRules:
    def test_range_rules_have_min_max(self, rules: list[dict]):
        for rule in rules:
            if rule["check_type"] == "range":
                params = rule["parameters"]
                assert "min" in params, f"{rule['id']}: range rule missing 'min'"
                assert "max" in params, f"{rule['id']}: range rule missing 'max'"

    def test_range_min_less_than_max(self, rules: list[dict]):
        for rule in rules:
            if rule["check_type"] == "range":
                params = rule["parameters"]
                assert params["min"] <= params["max"], (
                    f"{rule['id']}: min ({params['min']}) > max ({params['max']})"
                )

    def test_range_values_are_numeric(self, rules: list[dict]):
        for rule in rules:
            if rule["check_type"] == "range":
                params = rule["parameters"]
                assert isinstance(params["min"], (int, float))
                assert isinstance(params["max"], (int, float))


# ===================================================================
# Custom check rules have handler
# ===================================================================


class TestCustomRules:
    def test_custom_rules_have_handler(self, rules: list[dict]):
        for rule in rules:
            if rule["check_type"] == "custom":
                params = rule["parameters"]
                assert "handler" in params, (
                    f"{rule['id']}: custom rule missing 'handler'"
                )


# ===================================================================
# Individual rule content checks
# ===================================================================


def _get_rule(rules: list[dict], rule_id: str) -> dict:
    for r in rules:
        if r["id"] == rule_id:
            return r
    pytest.fail(f"Rule {rule_id} not found")


class TestManningRules:
    def test_channel_n_rule_exists(self, rules):
        rule = _get_rule(rules, "FEMA-MANN-001")
        assert rule["severity"] == "error"
        assert rule["check_type"] == "range"

    def test_channel_n_range(self, rules):
        rule = _get_rule(rules, "FEMA-MANN-001")
        assert rule["parameters"]["min"] == pytest.approx(0.020)
        assert rule["parameters"]["max"] == pytest.approx(0.150)

    def test_channel_n_applies_to(self, rules):
        rule = _get_rule(rules, "FEMA-MANN-001")
        assert "manning_n_channel" in rule["applies_to"]

    def test_channel_n_cites_fema(self, rules):
        rule = _get_rule(rules, "FEMA-MANN-001")
        assert "FEMA" in rule["citation"]
        assert "Appendix C" in rule["citation"]

    def test_overbank_n_rule_exists(self, rules):
        rule = _get_rule(rules, "FEMA-MANN-002")
        assert rule["severity"] == "error"
        assert rule["check_type"] == "range"

    def test_overbank_n_range(self, rules):
        rule = _get_rule(rules, "FEMA-MANN-002")
        assert rule["parameters"]["min"] == pytest.approx(0.020)
        assert rule["parameters"]["max"] == pytest.approx(0.200)

    def test_overbank_n_applies_to(self, rules):
        rule = _get_rule(rules, "FEMA-MANN-002")
        assert "manning_n_overbank" in rule["applies_to"]


class TestCoefficientRules:
    def test_contraction_rule_exists(self, rules):
        rule = _get_rule(rules, "FEMA-COEF-001")
        assert rule["severity"] == "warning"

    def test_contraction_range(self, rules):
        rule = _get_rule(rules, "FEMA-COEF-001")
        assert rule["parameters"]["min"] == pytest.approx(0.1)
        assert rule["parameters"]["max"] == pytest.approx(0.3)

    def test_contraction_applies_to(self, rules):
        rule = _get_rule(rules, "FEMA-COEF-001")
        assert "contraction" in rule["applies_to"]

    def test_expansion_rule_exists(self, rules):
        rule = _get_rule(rules, "FEMA-COEF-002")
        assert rule["severity"] == "warning"

    def test_expansion_range(self, rules):
        rule = _get_rule(rules, "FEMA-COEF-002")
        assert rule["parameters"]["min"] == pytest.approx(0.3)
        assert rule["parameters"]["max"] == pytest.approx(0.5)

    def test_expansion_applies_to(self, rules):
        rule = _get_rule(rules, "FEMA-COEF-002")
        assert "expansion" in rule["applies_to"]


class TestFloodwayRule:
    def test_surcharge_rule_exists(self, rules):
        rule = _get_rule(rules, "FEMA-FW-001")
        assert rule["severity"] == "error"

    def test_surcharge_range(self, rules):
        rule = _get_rule(rules, "FEMA-FW-001")
        assert rule["parameters"]["min"] == pytest.approx(0.0)
        assert rule["parameters"]["max"] == pytest.approx(1.0)

    def test_surcharge_cites_cfr(self, rules):
        rule = _get_rule(rules, "FEMA-FW-001")
        assert "44 CFR 65.12" in rule["citation"]

    def test_surcharge_applies_to(self, rules):
        rule = _get_rule(rules, "FEMA-FW-001")
        assert "target_surcharge" in rule["applies_to"]


class TestEventRule:
    def test_100yr_rule_exists(self, rules):
        rule = _get_rule(rules, "FEMA-EVENT-001")
        assert rule["severity"] == "error"
        assert rule["check_type"] == "custom"

    def test_100yr_accepted_names(self, rules):
        rule = _get_rule(rules, "FEMA-EVENT-001")
        names = rule["parameters"]["accepted_names"]
        assert isinstance(names, list)
        assert len(names) >= 3
        lower_names = [n.lower() for n in names]
        assert "100yr" in lower_names

    def test_100yr_cites_cfr(self, rules):
        rule = _get_rule(rules, "FEMA-EVENT-001")
        assert "44 CFR" in rule["citation"]

    def test_100yr_applies_to(self, rules):
        rule = _get_rule(rules, "FEMA-EVENT-001")
        assert "profile" in rule["applies_to"]


class TestBridgeRule:
    def test_bridge_rule_exists(self, rules):
        rule = _get_rule(rules, "FEMA-BRG-001")
        assert rule["severity"] == "info"
        assert rule["check_type"] == "exists"

    def test_bridge_applies_to(self, rules):
        rule = _get_rule(rules, "FEMA-BRG-001")
        assert "min_low_chord" in rule["applies_to"]


class TestBoundaryConditionRule:
    def test_bc_rule_exists(self, rules):
        rule = _get_rule(rules, "FEMA-BC-001")
        assert rule["severity"] == "error"
        assert rule["check_type"] == "custom"

    def test_bc_has_handler(self, rules):
        rule = _get_rule(rules, "FEMA-BC-001")
        assert rule["parameters"]["handler"] == "check_boundary_conditions_defined"

    def test_bc_applies_to(self, rules):
        rule = _get_rule(rules, "FEMA-BC-001")
        assert "boundaries" in rule["applies_to"]
