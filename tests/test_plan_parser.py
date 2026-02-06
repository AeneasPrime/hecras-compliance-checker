"""Tests for HEC-RAS plan file parser against the sample.p01 fixture."""

from pathlib import Path
from textwrap import dedent

import pytest

from hecras_compliance.parsers.plan import (
    ENCROACHMENT_METHODS,
    FRICTION_SLOPE_METHODS,
    PLAN_TYPES,
    PlanFile,
    parse_plan,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample.p01"


@pytest.fixture
def plan() -> PlanFile:
    return parse_plan(FIXTURE)


def _write_and_parse(tmp_path: Path, content: str) -> PlanFile:
    f = tmp_path / "test.p01"
    f.write_text(dedent(content))
    return parse_plan(f)


# ===================================================================
# 1.  Simulation type and metadata
# ===================================================================

class TestSimulationType:

    def test_title(self, plan: PlanFile):
        assert plan.title == "Beargrass Creek Floodplain Delineation"

    def test_program_version(self, plan: PlanFile):
        assert plan.program_version == "6.10"

    def test_short_identifier(self, plan: PlanFile):
        assert plan.short_identifier == "BearFP"

    def test_simulation_date(self, plan: PlanFile):
        assert plan.simulation_date == "01Jan2024,01Jan2024"

    def test_geom_file(self, plan: PlanFile):
        assert plan.geom_file == "g01"

    def test_flow_file(self, plan: PlanFile):
        assert plan.flow_file == "f01"

    def test_plan_type_is_steady(self, plan: PlanFile):
        assert plan.plan_type == 1
        assert plan.is_steady is True

    def test_plan_type_name(self, plan: PlanFile):
        assert plan.plan_type_name == "Steady Flow"

    def test_flow_regime(self, plan: PlanFile):
        assert plan.flow_regime == "Subcritical"

    def test_profiles(self, plan: PlanFile):
        assert plan.profiles == ["10yr", "50yr", "100yr", "500yr"]

    def test_paused(self, plan: PlanFile):
        assert plan.paused is False


# ===================================================================
# 2.  Computational settings
# ===================================================================

class TestComputationalSettings:

    def test_flow_tolerance(self, plan: PlanFile):
        assert plan.computation.flow_tolerance == pytest.approx(0.01)

    def test_ws_tolerance(self, plan: PlanFile):
        assert plan.computation.ws_tolerance == pytest.approx(0.01)

    def test_critical_always(self, plan: PlanFile):
        assert plan.computation.critical_always is False

    def test_friction_slope_method(self, plan: PlanFile):
        assert plan.computation.friction_slope_method == 2

    def test_friction_slope_method_name(self, plan: PlanFile):
        assert plan.computation.friction_slope_method_name == "Average Friction Slope"

    def test_flow_ratio(self, plan: PlanFile):
        assert plan.computation.flow_ratio == pytest.approx(0.01)

    def test_split_flow(self, plan: PlanFile):
        assert plan.computation.split_flow is False

    def test_warm_up(self, plan: PlanFile):
        assert plan.computation.warm_up is False

    def test_computation_interval_empty_for_steady(self, plan: PlanFile):
        assert plan.computation.computation_interval == ""

    def test_flow_tolerance_method(self, plan: PlanFile):
        assert plan.computation.flow_tolerance_method == 0

    def test_check_data(self, plan: PlanFile):
        assert plan.computation.check_data is False


# ===================================================================
# 3.  Encroachment / floodway
# ===================================================================

class TestEncroachment:

    def test_enabled(self, plan: PlanFile):
        assert plan.encroachment.enabled is True

    def test_method(self, plan: PlanFile):
        assert plan.encroachment.method == 4

    def test_method_name(self, plan: PlanFile):
        assert plan.encroachment.method_name == "Target Surcharge"

    def test_values(self, plan: PlanFile):
        assert plan.encroachment.values[0] == pytest.approx(1.0)
        assert plan.encroachment.values[1] == pytest.approx(0.0)
        assert plan.encroachment.values[2] == pytest.approx(0.0)
        assert plan.encroachment.values[3] == pytest.approx(0.0)

    def test_is_floodway(self, plan: PlanFile):
        assert plan.encroachment.is_floodway is True
        assert plan.is_floodway_analysis is True

    def test_target_surcharge(self, plan: PlanFile):
        assert plan.encroachment.target_surcharge == pytest.approx(1.0)


class TestFloodwayDerived:
    """Floodway analysis is encroachment Method 4/5 — no separate keyword."""

    def test_method5_is_also_floodway(self, tmp_path: Path):
        plan = _write_and_parse(tmp_path, """\
            Plan Title=Method 5 plan
            Encroach Param= -1 ,0 ,0 ,0
            Encroach Method= 5
            Encroach Val 1= 0.5
            Encroach Val 2= 0.3
        """)
        assert plan.encroachment.is_floodway is True
        assert plan.encroachment.target_surcharge == pytest.approx(0.5)
        assert plan.encroachment.method_name == "Optimized Surcharge and Energy"

    def test_method1_is_not_floodway(self, tmp_path: Path):
        plan = _write_and_parse(tmp_path, """\
            Encroach Param= -1 ,0 ,0 ,0
            Encroach Method= 1
            Encroach Val 1= 100
            Encroach Val 2= 400
        """)
        assert plan.encroachment.enabled is True
        assert plan.encroachment.is_floodway is False
        assert plan.encroachment.target_surcharge is None

    def test_disabled_encroachment(self, tmp_path: Path):
        plan = _write_and_parse(tmp_path, """\
            Encroach Param= 0 ,0 ,0 ,0
            Encroach Method= 4
            Encroach Val 1= 1
        """)
        assert plan.encroachment.enabled is False
        assert plan.encroachment.is_floodway is False
        assert plan.encroachment.target_surcharge is None

    def test_no_encroachment_section(self, tmp_path: Path):
        plan = _write_and_parse(tmp_path, """\
            Plan Title=No encroachment
            Plan Type= 1
        """)
        assert plan.encroachment.enabled is False
        assert plan.encroachment.method == 0
        assert plan.is_floodway_analysis is False


# ===================================================================
# 4.  Output intervals and run flags
# ===================================================================

class TestOutputSettings:

    def test_run_htab(self, plan: PlanFile):
        assert plan.output.run_htab is True

    def test_run_post_process(self, plan: PlanFile):
        assert plan.output.run_post_process is True

    def test_run_sediment(self, plan: PlanFile):
        assert plan.output.run_sediment is False

    def test_run_unet(self, plan: PlanFile):
        assert plan.output.run_unet is False

    def test_run_ras_mapper(self, plan: PlanFile):
        assert plan.output.run_ras_mapper is False

    def test_write_flags(self, plan: PlanFile):
        assert plan.output.write_ic_file is False
        assert plan.output.write_detailed is False

    def test_echo_flags(self, plan: PlanFile):
        assert plan.output.echo_input is False
        assert plan.output.echo_parameters is False
        assert plan.output.echo_output is False

    def test_log_output_level(self, plan: PlanFile):
        assert plan.output.log_output_level == 0

    def test_intervals_empty_for_steady_flow(self, plan: PlanFile):
        assert plan.output.output_interval == ""
        assert plan.output.mapping_interval == ""
        assert plan.output.hydrograph_output_interval == ""
        assert plan.output.detailed_output_interval == ""
        assert plan.output.instantaneous_interval == ""


class TestUnsteadyOutputIntervals:
    """Verify interval keywords parse when populated (unsteady-style)."""

    def test_intervals_parsed(self, tmp_path: Path):
        plan = _write_and_parse(tmp_path, """\
            Plan Title=Unsteady plan
            Plan Type= 2
            Computation Interval=5MIN
            Output Interval=15MIN
            Mapping Interval=1HOUR
            Hydrograph Output Interval=15MIN
            Detailed Output Interval=6HOUR
            Instantaneous Interval=1HOUR
        """)
        assert plan.plan_type == 2
        assert plan.is_steady is False
        assert plan.computation.computation_interval == "5MIN"
        assert plan.output.output_interval == "15MIN"
        assert plan.output.mapping_interval == "1HOUR"
        assert plan.output.hydrograph_output_interval == "15MIN"
        assert plan.output.detailed_output_interval == "6HOUR"
        assert plan.output.instantaneous_interval == "1HOUR"


# ===================================================================
# 5.  Flow regime detection
# ===================================================================

class TestFlowRegime:

    def test_subcritical(self, plan: PlanFile):
        assert plan.flow_regime == "Subcritical"

    def test_mixed(self, tmp_path: Path):
        plan = _write_and_parse(tmp_path, "Mixed Flow Regime\n")
        assert plan.flow_regime == "Mixed"

    def test_mixed_short(self, tmp_path: Path):
        plan = _write_and_parse(tmp_path, "Mixed Flow\n")
        assert plan.flow_regime == "Mixed"

    def test_supercritical(self, tmp_path: Path):
        plan = _write_and_parse(tmp_path, "Supercritical Flow\n")
        assert plan.flow_regime == "Supercritical"

    def test_no_regime(self, tmp_path: Path):
        plan = _write_and_parse(tmp_path, "Plan Title=test\n")
        assert plan.flow_regime == ""


# ===================================================================
# 6.  Run-flag interpretation (-1 and 1 both mean True)
# ===================================================================

class TestFlagParsing:

    def test_negative_one_is_true(self, tmp_path: Path):
        plan = _write_and_parse(tmp_path, """\
            Run HTab= -1
            Run Post Process= -1
            Run UNET= -1
        """)
        assert plan.output.run_htab is True
        assert plan.output.run_post_process is True
        assert plan.output.run_unet is True

    def test_one_is_true(self, tmp_path: Path):
        plan = _write_and_parse(tmp_path, "Run HTab= 1\n")
        assert plan.output.run_htab is True

    def test_zero_is_false(self, tmp_path: Path):
        plan = _write_and_parse(tmp_path, "Run HTab= 0\n")
        assert plan.output.run_htab is False

    def test_empty_is_false(self, tmp_path: Path):
        plan = _write_and_parse(tmp_path, "Run HTab=\n")
        assert plan.output.run_htab is False


# ===================================================================
# 7.  Robustness — missing / malformed input
# ===================================================================

class TestRobustness:

    def test_empty_file(self, tmp_path: Path):
        plan = _write_and_parse(tmp_path, "")
        assert plan.title == ""
        assert plan.profiles == []
        assert plan.plan_type == 0

    def test_title_only(self, tmp_path: Path):
        plan = _write_and_parse(tmp_path, "Plan Title=Just a test\n")
        assert plan.title == "Just a test"
        assert plan.is_steady is False  # plan_type defaults to 0

    def test_unknown_keys_ignored(self, tmp_path: Path):
        plan = _write_and_parse(tmp_path, """\
            Plan Title=OK
            Some Completely Unknown Key= 42
            Another Weird Line
        """)
        assert plan.title == "OK"

    def test_windows_line_endings(self, tmp_path: Path):
        content = (
            "Plan Title=CRLF\r\n"
            "Plan Type= 1\r\n"
            "Subcritical Flow\r\n"
            "Profile Names=A,B\r\n"
        )
        f = tmp_path / "crlf.p01"
        f.write_text(content)
        plan = parse_plan(f)
        assert plan.title == "CRLF"
        assert plan.plan_type == 1
        assert plan.flow_regime == "Subcritical"
        assert plan.profiles == ["A", "B"]

    def test_extra_whitespace_in_values(self, tmp_path: Path):
        plan = _write_and_parse(tmp_path, """\
            Plan Title=  Lots Of Spaces
            Flow Tolerance=  0.05
            Friction Slope Method=  3
        """)
        assert plan.title == "Lots Of Spaces"
        assert plan.computation.flow_tolerance == pytest.approx(0.05)
        assert plan.computation.friction_slope_method == 3

    def test_bad_numeric_falls_back_to_default(self, tmp_path: Path):
        plan = _write_and_parse(tmp_path, """\
            Flow Tolerance= abc
            Friction Slope Method= xyz
            Plan Type= not_a_number
        """)
        assert plan.computation.flow_tolerance == pytest.approx(0.01)
        assert plan.computation.friction_slope_method == 1
        assert plan.plan_type == 0


# ===================================================================
# 8.  Constant look-up tables
# ===================================================================

class TestConstants:

    def test_plan_types_complete(self):
        assert 1 in PLAN_TYPES
        assert 2 in PLAN_TYPES
        assert 3 in PLAN_TYPES

    def test_friction_slope_methods(self):
        assert len(FRICTION_SLOPE_METHODS) == 4

    def test_encroachment_methods(self):
        assert len(ENCROACHMENT_METHODS) == 5
        assert ENCROACHMENT_METHODS[4] == "Target Surcharge"
