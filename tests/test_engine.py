"""Tests for the compliance rules engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from hecras_compliance.parsers.geometry import (
    BankStations,
    Bridge,
    BridgeDeck,
    CrossSection,
    DeckPoint,
    GeometryFile,
    ManningRegion,
    ReachLengths,
)
from hecras_compliance.parsers.plan import (
    EncroachmentSettings,
    PlanFile,
)
from hecras_compliance.parsers.flow import (
    FlowFile,
    FlowProfile,
    SteadyBoundaryCondition,
    UnsteadyBoundaryCondition,
)
from hecras_compliance.rules.engine import (
    ComplianceEngine,
    ModelData,
    RuleResult,
    load_rules,
    _resolve_values,
)


FIXTURES = Path(__file__).parent / "fixtures"


# ===================================================================
# Helpers — build minimal model data for targeted tests
# ===================================================================

def _xs(
    station: float,
    n_left: float = 0.06,
    n_channel: float = 0.035,
    n_right: float = 0.06,
    expansion: float = 0.3,
    contraction: float = 0.1,
) -> CrossSection:
    """Build a CrossSection with three Manning's n regions and bank stations."""
    return CrossSection(
        river_station=station,
        river="Test River",
        reach="Main",
        bank_stations=BankStations(left=100.0, right=300.0),
        manning_regions=[
            ManningRegion(n_value=n_left, start_station=0.0),
            ManningRegion(n_value=n_channel, start_station=100.0),
            ManningRegion(n_value=n_right, start_station=300.0),
        ],
        expansion=expansion,
        contraction=contraction,
    )


def _bridge(station: float, low_chord: float = 450.0) -> Bridge:
    """Build a minimal Bridge with a deck."""
    return Bridge(
        river_station=station,
        river="Test River",
        reach="Main",
        deck=BridgeDeck(
            width=40.0,
            points=[
                DeckPoint(station=100.0, high_chord=460.0, low_chord=low_chord),
                DeckPoint(station=300.0, high_chord=460.0, low_chord=low_chord),
            ],
        ),
    )


def _good_geometry() -> GeometryFile:
    return GeometryFile(
        title="Test",
        cross_sections=[
            _xs(5000),
            _xs(4000),
            _xs(3000),
        ],
        bridges=[_bridge(3500)],
    )


def _good_flow(profiles: list[str] | None = None) -> FlowFile:
    if profiles is None:
        profiles = ["10yr", "50yr", "100yr", "500yr"]
    return FlowFile(
        title="Test",
        is_steady=True,
        profiles=[FlowProfile(n) for n in profiles],
        steady_boundaries=[
            SteadyBoundaryCondition("Test River", "Main", i + 1, downstream_type=3)
            for i in range(len(profiles))
        ],
    )


def _good_plan(surcharge: float = 1.0) -> PlanFile:
    return PlanFile(
        title="Test",
        plan_type=1,
        encroachment=EncroachmentSettings(
            enabled=True, method=4, values=[surcharge, 0.0, 0.0, 0.0],
        ),
    )


def _full_model(**overrides) -> ModelData:
    return ModelData(
        geometry=overrides.get("geometry", _good_geometry()),
        plan=overrides.get("plan", _good_plan()),
        flow=overrides.get("flow", _good_flow()),
    )


# ===================================================================
# Rule loading
# ===================================================================


class TestRuleLoading:
    def test_loads_fema_rules(self):
        rules = load_rules()
        ids = {r["id"] for r in rules}
        assert "FEMA-MANN-001" in ids
        assert "FEMA-FW-001" in ids

    def test_loads_texas_overlay(self):
        rules = load_rules(state="texas")
        ids = {r["id"] for r in rules}
        assert "TX-FW-001" in ids
        assert "TX-EVENT-001" in ids

    def test_texas_supersedes_fema_fw(self):
        rules = load_rules(state="texas")
        ids = {r["id"] for r in rules}
        assert "FEMA-FW-001" not in ids, "Texas should supersede FEMA-FW-001"
        assert "TX-FW-001" in ids

    def test_fema_alone_keeps_fw_001(self):
        rules = load_rules()
        ids = {r["id"] for r in rules}
        assert "FEMA-FW-001" in ids

    def test_unknown_state_returns_fema_only(self):
        rules = load_rules(state="narnia")
        ids = {r["id"] for r in rules}
        assert "FEMA-MANN-001" in ids
        assert not any(r["id"].startswith("TX-") for r in rules)


# ===================================================================
# Path resolution
# ===================================================================


class TestPathResolution:
    def test_scalar_path(self):
        model = _full_model()
        values = _resolve_values(model, "plan.encroachment.target_surcharge")
        assert len(values) == 1
        assert values[0][0] == 1.0

    def test_iterable_path(self):
        model = _full_model()
        values = _resolve_values(
            model, "geometry.cross_sections[].manning_n_channel"
        )
        assert len(values) == 3
        assert all(v == pytest.approx(0.035) for v, _ in values)

    def test_overbank_splits_left_right(self):
        model = _full_model()
        values = _resolve_values(
            model, "geometry.cross_sections[].manning_n_overbank"
        )
        # 3 XS × 2 (left + right) = 6
        assert len(values) == 6

    def test_missing_data_returns_empty(self):
        model = ModelData()  # all None
        values = _resolve_values(model, "geometry.cross_sections[].expansion")
        assert values == []

    def test_location_label_has_station(self):
        model = _full_model()
        values = _resolve_values(
            model, "geometry.cross_sections[].expansion"
        )
        locations = [loc for _, loc in values]
        assert "RS 5000" in locations[0]


# ===================================================================
# Manning's n checks (user-requested tests)
# ===================================================================


class TestManningChecks:
    def test_good_n_passes(self):
        """Manning's n of 0.035 passes the FEMA range check."""
        model = _full_model(geometry=GeometryFile(
            cross_sections=[_xs(1000, n_channel=0.035)],
        ))
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        mann_results = [
            r for r in results if r.rule_id == "FEMA-MANN-001"
        ]
        assert len(mann_results) == 1
        assert mann_results[0].status == "PASS"

    def test_bad_n_fails(self):
        """Manning's n of 0.001 fails the FEMA range check."""
        model = _full_model(geometry=GeometryFile(
            cross_sections=[_xs(1000, n_channel=0.001)],
        ))
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        mann_results = [
            r for r in results if r.rule_id == "FEMA-MANN-001"
        ]
        assert len(mann_results) == 1
        assert mann_results[0].status == "FAIL"

    def test_n_at_lower_bound_passes(self):
        model = _full_model(geometry=GeometryFile(
            cross_sections=[_xs(1000, n_channel=0.020)],
        ))
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        mann_results = [
            r for r in results if r.rule_id == "FEMA-MANN-001"
        ]
        assert mann_results[0].status == "PASS"

    def test_n_at_upper_bound_passes(self):
        model = _full_model(geometry=GeometryFile(
            cross_sections=[_xs(1000, n_channel=0.150)],
        ))
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        mann_results = [
            r for r in results if r.rule_id == "FEMA-MANN-001"
        ]
        assert mann_results[0].status == "PASS"

    def test_overbank_bad_left_fails(self):
        model = _full_model(geometry=GeometryFile(
            cross_sections=[_xs(1000, n_left=0.001)],
        ))
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        ob_results = [
            r for r in results if r.rule_id == "FEMA-MANN-002"
        ]
        failed = [r for r in ob_results if r.status == "FAIL"]
        assert len(failed) >= 1
        assert any("LOB" in r.location for r in failed)

    def test_overbank_good_passes(self):
        model = _full_model(geometry=GeometryFile(
            cross_sections=[_xs(1000, n_left=0.06, n_right=0.06)],
        ))
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        ob_results = [
            r for r in results if r.rule_id == "FEMA-MANN-002"
        ]
        assert all(r.status == "PASS" for r in ob_results)


# ===================================================================
# Coefficient checks
# ===================================================================


class TestCoefficientChecks:
    def test_expansion_zero_gets_warning(self):
        model = _full_model(geometry=GeometryFile(
            cross_sections=[_xs(1000, expansion=0.0)],
        ))
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        exp_results = [
            r for r in results if r.rule_id == "FEMA-COEF-002"
        ]
        assert len(exp_results) == 1
        assert exp_results[0].status == "WARNING"

    def test_expansion_good_passes(self):
        model = _full_model(geometry=GeometryFile(
            cross_sections=[_xs(1000, expansion=0.3)],
        ))
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        exp_results = [
            r for r in results if r.rule_id == "FEMA-COEF-002"
        ]
        assert exp_results[0].status == "PASS"

    def test_contraction_good_passes(self):
        model = _full_model(geometry=GeometryFile(
            cross_sections=[_xs(1000, contraction=0.1)],
        ))
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        ct_results = [
            r for r in results if r.rule_id == "FEMA-COEF-001"
        ]
        assert ct_results[0].status == "PASS"


# ===================================================================
# Bridge checks
# ===================================================================


class TestBridgeChecks:
    def test_bridge_exists_passes(self):
        model = _full_model()
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        brg_results = [
            r for r in results if r.rule_id == "FEMA-BRG-001"
        ]
        assert len(brg_results) == 1
        assert brg_results[0].status == "PASS"

    def test_missing_bridge_is_skipped_not_crash(self):
        """Missing bridge section results in SKIPPED, not a crash."""
        model = _full_model(geometry=GeometryFile(
            cross_sections=[_xs(1000)],
            bridges=[],
        ))
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        brg_results = [
            r for r in results if r.rule_id == "FEMA-BRG-001"
        ]
        assert len(brg_results) == 1
        assert brg_results[0].status == "SKIPPED"

    def test_bridge_no_deck_skipped(self):
        bridge = Bridge(
            river_station=3000, river="Test", reach="Main", deck=None,
        )
        model = _full_model(geometry=GeometryFile(
            cross_sections=[],
            bridges=[bridge],
        ))
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        brg_results = [
            r for r in results if r.rule_id == "FEMA-BRG-001"
        ]
        assert brg_results[0].status == "SKIPPED"


# ===================================================================
# Floodway surcharge checks
# ===================================================================


class TestFloodwaySurcharge:
    def test_federal_1ft_passes(self):
        model = _full_model(plan=_good_plan(surcharge=1.0))
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        fw_results = [
            r for r in results if r.rule_id == "FEMA-FW-001"
        ]
        assert len(fw_results) == 1
        assert fw_results[0].status == "PASS"

    def test_federal_2ft_fails(self):
        model = _full_model(plan=_good_plan(surcharge=2.0))
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        fw_results = [
            r for r in results if r.rule_id == "FEMA-FW-001"
        ]
        assert fw_results[0].status == "FAIL"

    def test_texas_zero_rise_1ft_fails(self):
        """Texas zero-rise rule is stricter than federal 1.0 ft rule."""
        model = _full_model(plan=_good_plan(surcharge=1.0))
        engine = ComplianceEngine(state="texas")
        results = engine.evaluate(model)
        tx_fw = [r for r in results if r.rule_id == "TX-FW-001"]
        assert len(tx_fw) == 1
        assert tx_fw[0].status == "FAIL"

    def test_texas_zero_rise_0ft_passes(self):
        model = _full_model(plan=_good_plan(surcharge=0.0))
        engine = ComplianceEngine(state="texas")
        results = engine.evaluate(model)
        tx_fw = [r for r in results if r.rule_id == "TX-FW-001"]
        assert len(tx_fw) == 1
        assert tx_fw[0].status == "PASS"

    def test_texas_replaces_federal_fw(self):
        """When Texas is loaded, FEMA-FW-001 should not appear in results."""
        model = _full_model(plan=_good_plan(surcharge=1.0))
        engine = ComplianceEngine(state="texas")
        results = engine.evaluate(model)
        fema_fw = [r for r in results if r.rule_id == "FEMA-FW-001"]
        assert len(fema_fw) == 0


# ===================================================================
# Profile existence checks
# ===================================================================


class TestProfileChecks:
    def test_100yr_present_passes(self):
        model = _full_model(flow=_good_flow(["100yr"]))
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        ev_results = [
            r for r in results if r.rule_id == "FEMA-EVENT-001"
        ]
        assert len(ev_results) == 1
        assert ev_results[0].status == "PASS"

    def test_100yr_missing_fails(self):
        model = _full_model(flow=_good_flow(["10yr", "50yr"]))
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        ev_results = [
            r for r in results if r.rule_id == "FEMA-EVENT-001"
        ]
        assert ev_results[0].status == "FAIL"

    def test_base_flood_name_matches(self):
        model = _full_model(flow=_good_flow(["Base Flood"]))
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        ev_results = [
            r for r in results if r.rule_id == "FEMA-EVENT-001"
        ]
        assert ev_results[0].status == "PASS"

    def test_case_insensitive_match(self):
        model = _full_model(flow=_good_flow(["100YR"]))
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        ev_results = [
            r for r in results if r.rule_id == "FEMA-EVENT-001"
        ]
        assert ev_results[0].status == "PASS"

    def test_no_flow_data_skipped(self):
        model = ModelData(geometry=_good_geometry(), plan=_good_plan())
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        ev_results = [
            r for r in results if r.rule_id == "FEMA-EVENT-001"
        ]
        assert ev_results[0].status == "SKIPPED"

    def test_texas_requires_four_events(self):
        model = _full_model(
            flow=_good_flow(["10yr", "50yr", "100yr", "500yr"]),
        )
        engine = ComplianceEngine(state="texas")
        results = engine.evaluate(model)
        tx_events = [
            r for r in results
            if r.rule_id.startswith("TX-EVENT-")
        ]
        assert len(tx_events) == 4
        assert all(r.status == "PASS" for r in tx_events)

    def test_texas_missing_500yr_fails(self):
        model = _full_model(
            flow=_good_flow(["10yr", "50yr", "100yr"]),
        )
        engine = ComplianceEngine(state="texas")
        results = engine.evaluate(model)
        tx_500 = [
            r for r in results if r.rule_id == "TX-EVENT-004"
        ]
        assert tx_500[0].status == "FAIL"


# ===================================================================
# Boundary condition checks
# ===================================================================


class TestBoundaryChecks:
    def test_steady_boundaries_pass(self):
        model = _full_model()
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        bc_results = [
            r for r in results if r.rule_id == "FEMA-BC-001"
        ]
        assert len(bc_results) == 1
        assert bc_results[0].status == "PASS"

    def test_no_boundaries_fails(self):
        flow = FlowFile(
            title="Test", is_steady=True,
            profiles=[FlowProfile("100yr")],
            steady_boundaries=[],
        )
        model = _full_model(flow=flow)
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        bc_results = [
            r for r in results if r.rule_id == "FEMA-BC-001"
        ]
        assert bc_results[0].status == "FAIL"

    def test_unsteady_boundaries_pass(self):
        flow = FlowFile(
            title="Test", is_steady=False,
            unsteady_boundaries=[
                UnsteadyBoundaryCondition("R", "Rch", "5000", bc_type="Flow Hydrograph"),
            ],
        )
        model = _full_model(flow=flow)
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        bc_results = [
            r for r in results if r.rule_id == "FEMA-BC-001"
        ]
        assert bc_results[0].status == "PASS"


# ===================================================================
# Manual review handler
# ===================================================================


class TestManualReview:
    def test_texas_freeboard_flagged(self):
        model = _full_model()
        engine = ComplianceEngine(state="texas")
        results = engine.evaluate(model)
        fb_results = [
            r for r in results if r.rule_id == "TX-FB-001"
        ]
        assert len(fb_results) == 1
        assert fb_results[0].severity == "info"
        assert fb_results[0].status == "PASS"
        assert "freeboard" in fb_results[0].message.lower() or "review" in fb_results[0].message.lower()


# ===================================================================
# Empty / missing data — never crash
# ===================================================================


class TestEmptyModel:
    def test_empty_model_no_crash(self):
        model = ModelData()
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        assert isinstance(results, list)
        assert len(results) > 0

    def test_empty_model_all_skipped(self):
        model = ModelData()
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        for r in results:
            assert r.status == "SKIPPED", (
                f"{r.rule_id} should be SKIPPED with empty model, got {r.status}"
            )

    def test_geometry_only(self):
        model = ModelData(geometry=_good_geometry())
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        # Geometry rules should evaluate; flow/plan rules should skip
        mann_results = [r for r in results if r.rule_id == "FEMA-MANN-001"]
        assert all(r.status == "PASS" for r in mann_results)
        ev_results = [r for r in results if r.rule_id == "FEMA-EVENT-001"]
        assert ev_results[0].status == "SKIPPED"


# ===================================================================
# RuleResult dataclass
# ===================================================================


class TestRuleResult:
    def test_default_location_empty(self):
        r = RuleResult(
            rule_id="X", rule_name="X", status="PASS",
            severity="info", actual_value="", expected_value="",
            citation="", citation_url="", message="",
        )
        assert r.location == ""

    def test_all_fields_populated(self):
        r = RuleResult(
            rule_id="FEMA-MANN-001",
            rule_name="Channel Manning's n",
            status="FAIL",
            severity="error",
            actual_value="0.001",
            expected_value="0.020 – 0.150",
            citation="FEMA G&S Appendix C",
            citation_url="https://www.fema.gov/flood-maps/guidance-partners/guidelines-standards",
            message="Too low",
            location="RS 2000",
        )
        assert r.rule_id == "FEMA-MANN-001"
        assert r.location == "RS 2000"
        assert r.citation_url.startswith("https://")


# ===================================================================
# Integration — full model through engine
# ===================================================================


class TestIntegration:
    def test_full_model_fema_all_rules_evaluate(self):
        model = _full_model()
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        rule_ids = {r.rule_id for r in results}
        # All 8 FEMA rules should have at least one result
        for expected_id in [
            "FEMA-MANN-001", "FEMA-MANN-002",
            "FEMA-COEF-001", "FEMA-COEF-002",
            "FEMA-FW-001", "FEMA-EVENT-001",
            "FEMA-BRG-001", "FEMA-BC-001",
        ]:
            assert expected_id in rule_ids, f"Missing result for {expected_id}"

    def test_full_model_no_failures(self):
        """A well-configured model should pass all FEMA checks."""
        model = _full_model()
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        failures = [
            r for r in results if r.status == "FAIL"
        ]
        assert failures == [], (
            f"Unexpected failures: {[(f.rule_id, f.message) for f in failures]}"
        )

    def test_results_have_citations(self):
        model = _full_model()
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        for r in results:
            if r.status != "SKIPPED":
                assert r.citation, f"{r.rule_id} missing citation"

    def test_multiple_xs_multiple_results(self):
        """Per-XS rules produce one result per cross section."""
        geom = GeometryFile(
            cross_sections=[_xs(5000), _xs(4000), _xs(3000)],
        )
        model = _full_model(geometry=geom)
        engine = ComplianceEngine()
        results = engine.evaluate(model)
        mann_results = [r for r in results if r.rule_id == "FEMA-MANN-001"]
        assert len(mann_results) == 3
