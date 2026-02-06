"""Tests for the HEC-RAS flow file parser (steady and unsteady)."""

from __future__ import annotations

from pathlib import Path
import math
import pytest
import textwrap

from hecras_compliance.parsers.flow import (
    FlowFile,
    FlowProfile,
    FlowChangeLocation,
    SteadyBoundaryCondition,
    UnsteadyBoundaryCondition,
    BOUNDARY_TYPES,
    parse_flow,
    _read_fixed_values,
    _float,
    _int,
)

FIXTURES = Path(__file__).parent / "fixtures"
STEADY_FILE = FIXTURES / "sample.f01"
UNSTEADY_FILE = FIXTURES / "sample.u01"


# ===================================================================
# Helper function tests
# ===================================================================


class TestReadFixedValues:
    def test_reads_values_from_single_line(self):
        lines = ["  100  200  300  400"]
        vals, idx = _read_fixed_values(lines, 0, 4)
        assert vals == [100.0, 200.0, 300.0, 400.0]
        assert idx == 1

    def test_reads_across_multiple_lines(self):
        lines = ["  100  200  300", "  400  500  600"]
        vals, idx = _read_fixed_values(lines, 0, 5)
        assert vals == [100.0, 200.0, 300.0, 400.0, 500.0]
        assert idx == 2

    def test_stops_at_count(self):
        lines = ["  100  200  300  400  500  600"]
        vals, idx = _read_fixed_values(lines, 0, 3)
        assert vals == [100.0, 200.0, 300.0]

    def test_stops_at_non_numeric(self):
        lines = ["  100  200", "Some Keyword=value", "  300  400"]
        vals, idx = _read_fixed_values(lines, 0, 6)
        assert vals == [100.0, 200.0]
        assert idx == 1

    def test_empty_lines(self):
        vals, idx = _read_fixed_values([], 0, 5)
        assert vals == []
        assert idx == 0

    def test_start_past_end(self):
        lines = ["100 200"]
        vals, idx = _read_fixed_values(lines, 5, 3)
        assert vals == []
        assert idx == 5


class TestFloatHelper:
    def test_normal_float(self):
        assert _float("3.14") == 3.14

    def test_integer_string(self):
        assert _float("42") == 42.0

    def test_empty_string(self):
        assert _float("") == 0.0

    def test_whitespace(self):
        assert _float("  ") == 0.0

    def test_invalid(self):
        assert _float("abc") == 0.0

    def test_custom_default(self):
        assert _float("", 99.0) == 99.0


class TestIntHelper:
    def test_normal_int(self):
        assert _int("42") == 42

    def test_empty_string(self):
        assert _int("") == 0

    def test_whitespace(self):
        assert _int("  ") == 0

    def test_invalid(self):
        assert _int("abc") == 0

    def test_custom_default(self):
        assert _int("", 5) == 5

    def test_negative(self):
        assert _int("-1") == -1


# ===================================================================
# Constants
# ===================================================================


class TestBoundaryTypes:
    def test_known_ws(self):
        assert BOUNDARY_TYPES[0] == "Known WS"

    def test_critical_depth(self):
        assert BOUNDARY_TYPES[1] == "Critical Depth"

    def test_rating_curve(self):
        assert BOUNDARY_TYPES[2] == "Rating Curve"

    def test_normal_depth(self):
        assert BOUNDARY_TYPES[3] == "Normal Depth"


# ===================================================================
# Dataclass tests
# ===================================================================


class TestFlowFileDataclass:
    def test_defaults(self):
        ff = FlowFile()
        assert ff.title == ""
        assert ff.program_version == ""
        assert ff.is_steady is True
        assert ff.profiles == []
        assert ff.flow_change_locations == []
        assert ff.steady_boundaries == []
        assert ff.unsteady_boundaries == []

    def test_profile_names(self):
        ff = FlowFile(profiles=[FlowProfile("10yr"), FlowProfile("100yr")])
        assert ff.profile_names == ["10yr", "100yr"]

    def test_num_profiles(self):
        ff = FlowFile(profiles=[FlowProfile("A"), FlowProfile("B"), FlowProfile("C")])
        assert ff.num_profiles == 3

    def test_num_profiles_empty(self):
        assert FlowFile().num_profiles == 0


class TestSteadyBoundaryConditionDataclass:
    def test_defaults(self):
        bc = SteadyBoundaryCondition("River", "Reach", 1)
        assert bc.upstream_type == 0
        assert bc.downstream_type == 0
        assert bc.downstream_slope == 0.0
        assert bc.upstream_slope == 0.0
        assert bc.downstream_known_ws == 0.0
        assert bc.upstream_known_ws == 0.0

    def test_upstream_type_name(self):
        bc = SteadyBoundaryCondition("R", "Rch", 1, upstream_type=3)
        assert bc.upstream_type_name == "Normal Depth"

    def test_downstream_type_name(self):
        bc = SteadyBoundaryCondition("R", "Rch", 1, downstream_type=1)
        assert bc.downstream_type_name == "Critical Depth"

    def test_unknown_type_name(self):
        bc = SteadyBoundaryCondition("R", "Rch", 1, downstream_type=99)
        assert "Unknown" in bc.downstream_type_name
        assert "99" in bc.downstream_type_name


class TestUnsteadyBoundaryConditionDataclass:
    def test_defaults(self):
        bc = UnsteadyBoundaryCondition("River", "Reach", "5000")
        assert bc.bc_type == ""
        assert bc.interval == ""
        assert bc.data == []
        assert bc.friction_slope is None
        assert bc.use_dss is False
        assert bc.dss_file == ""
        assert bc.dss_path == ""


# ===================================================================
# Steady flow parsing (sample.f01)
# ===================================================================


class TestSteadyFlowParsing:
    @pytest.fixture(scope="class")
    def flow(self) -> FlowFile:
        return parse_flow(STEADY_FILE)

    def test_is_steady(self, flow: FlowFile):
        assert flow.is_steady is True

    def test_title(self, flow: FlowFile):
        assert flow.title == "Beargrass Creek Steady Flow Data"

    def test_program_version(self, flow: FlowFile):
        assert flow.program_version == "6.10"

    def test_num_profiles(self, flow: FlowFile):
        assert flow.num_profiles == 4

    def test_profile_names(self, flow: FlowFile):
        assert flow.profile_names == ["10yr", "50yr", "100yr", "500yr"]

    def test_flow_change_location_count(self, flow: FlowFile):
        assert len(flow.flow_change_locations) == 1

    def test_flow_change_river(self, flow: FlowFile):
        loc = flow.flow_change_locations[0]
        assert loc.river == "Beargrass Creek"

    def test_flow_change_reach(self, flow: FlowFile):
        loc = flow.flow_change_locations[0]
        assert loc.reach == "Upper Reach"

    def test_flow_change_station(self, flow: FlowFile):
        loc = flow.flow_change_locations[0]
        assert loc.river_station == 5000.0

    def test_flow_values(self, flow: FlowFile):
        loc = flow.flow_change_locations[0]
        assert loc.flows == [1500.0, 3200.0, 5000.0, 8500.0]

    def test_10yr_flow(self, flow: FlowFile):
        assert flow.flow_change_locations[0].flows[0] == 1500.0

    def test_50yr_flow(self, flow: FlowFile):
        assert flow.flow_change_locations[0].flows[1] == 3200.0

    def test_100yr_flow(self, flow: FlowFile):
        assert flow.flow_change_locations[0].flows[2] == 5000.0

    def test_500yr_flow(self, flow: FlowFile):
        assert flow.flow_change_locations[0].flows[3] == 8500.0

    def test_boundary_count(self, flow: FlowFile):
        assert len(flow.steady_boundaries) == 4

    def test_boundary_river(self, flow: FlowFile):
        for bc in flow.steady_boundaries:
            assert bc.river == "Beargrass Creek"

    def test_boundary_reach(self, flow: FlowFile):
        for bc in flow.steady_boundaries:
            assert bc.reach == "Upper Reach"

    def test_boundary_profile_numbers(self, flow: FlowFile):
        profs = [bc.profile_number for bc in flow.steady_boundaries]
        assert profs == [1, 2, 3, 4]

    def test_boundary_upstream_type(self, flow: FlowFile):
        for bc in flow.steady_boundaries:
            assert bc.upstream_type == 0  # Known WS

    def test_boundary_downstream_type(self, flow: FlowFile):
        for bc in flow.steady_boundaries:
            assert bc.downstream_type == 3  # Normal Depth

    def test_boundary_downstream_type_name(self, flow: FlowFile):
        for bc in flow.steady_boundaries:
            assert bc.downstream_type_name == "Normal Depth"

    def test_boundary_upstream_type_name(self, flow: FlowFile):
        for bc in flow.steady_boundaries:
            assert bc.upstream_type_name == "Known WS"

    def test_boundary_downstream_slope(self, flow: FlowFile):
        for bc in flow.steady_boundaries:
            assert bc.downstream_slope == pytest.approx(0.002)

    def test_no_unsteady_boundaries(self, flow: FlowFile):
        assert flow.unsteady_boundaries == []


# ===================================================================
# Unsteady flow parsing (sample.u01)
# ===================================================================


class TestUnsteadyFlowParsing:
    @pytest.fixture(scope="class")
    def flow(self) -> FlowFile:
        return parse_flow(UNSTEADY_FILE)

    def test_is_unsteady(self, flow: FlowFile):
        assert flow.is_steady is False

    def test_title(self, flow: FlowFile):
        assert flow.title == "Beargrass Creek 100yr Unsteady Event"

    def test_program_version(self, flow: FlowFile):
        assert flow.program_version == "6.10"

    def test_boundary_count(self, flow: FlowFile):
        assert len(flow.unsteady_boundaries) == 3

    # -- First boundary: upstream flow hydrograph --
    def test_bc1_river(self, flow: FlowFile):
        bc = flow.unsteady_boundaries[0]
        assert bc.river == "Beargrass Creek"

    def test_bc1_reach(self, flow: FlowFile):
        bc = flow.unsteady_boundaries[0]
        assert bc.reach == "Upper Reach"

    def test_bc1_station(self, flow: FlowFile):
        bc = flow.unsteady_boundaries[0]
        assert bc.river_station == "5000"

    def test_bc1_type(self, flow: FlowFile):
        bc = flow.unsteady_boundaries[0]
        assert bc.bc_type == "Flow Hydrograph"

    def test_bc1_interval(self, flow: FlowFile):
        bc = flow.unsteady_boundaries[0]
        assert bc.interval == "15MIN"

    def test_bc1_data_count(self, flow: FlowFile):
        bc = flow.unsteady_boundaries[0]
        assert len(bc.data) == 10

    def test_bc1_data_values(self, flow: FlowFile):
        bc = flow.unsteady_boundaries[0]
        assert bc.data == [500, 1000, 2500, 5000, 7500, 8500, 7000, 4000, 2000, 1000]

    def test_bc1_peak(self, flow: FlowFile):
        bc = flow.unsteady_boundaries[0]
        assert max(bc.data) == 8500.0

    def test_bc1_no_friction_slope(self, flow: FlowFile):
        bc = flow.unsteady_boundaries[0]
        assert bc.friction_slope is None

    # -- Second boundary: lateral inflow --
    def test_bc2_type(self, flow: FlowFile):
        bc = flow.unsteady_boundaries[1]
        assert bc.bc_type == "Lateral Inflow Hydrograph"

    def test_bc2_station(self, flow: FlowFile):
        bc = flow.unsteady_boundaries[1]
        assert bc.river_station == "3500"

    def test_bc2_interval(self, flow: FlowFile):
        bc = flow.unsteady_boundaries[1]
        assert bc.interval == "1HOUR"

    def test_bc2_data_count(self, flow: FlowFile):
        bc = flow.unsteady_boundaries[1]
        assert len(bc.data) == 6

    def test_bc2_data_values(self, flow: FlowFile):
        bc = flow.unsteady_boundaries[1]
        assert bc.data == [0, 200, 800, 600, 300, 0]

    # -- Third boundary: normal depth --
    def test_bc3_type(self, flow: FlowFile):
        bc = flow.unsteady_boundaries[2]
        assert bc.bc_type == "Normal Depth"

    def test_bc3_station(self, flow: FlowFile):
        bc = flow.unsteady_boundaries[2]
        assert bc.river_station == "1000"

    def test_bc3_friction_slope(self, flow: FlowFile):
        bc = flow.unsteady_boundaries[2]
        assert bc.friction_slope == pytest.approx(0.002)

    def test_bc3_no_data(self, flow: FlowFile):
        bc = flow.unsteady_boundaries[2]
        assert bc.data == []

    def test_no_steady_boundaries(self, flow: FlowFile):
        assert flow.steady_boundaries == []

    def test_no_profiles(self, flow: FlowFile):
        assert flow.profiles == []


# ===================================================================
# Type detection
# ===================================================================


class TestTypeDetection:
    def test_steady_detected_from_content(self):
        flow = parse_flow(STEADY_FILE)
        assert flow.is_steady is True

    def test_unsteady_detected_from_content(self):
        flow = parse_flow(UNSTEADY_FILE)
        assert flow.is_steady is False


# ===================================================================
# Synthetic / edge-case tests
# ===================================================================


class TestSyntheticSteady:
    def test_multiple_flow_change_locations(self, tmp_path: Path):
        content = textwrap.dedent("""\
            Flow Title=Multi-Location Test
            Number of Profiles= 2
            Profile Names=Low,High

            River Rch & RM=Big River,Main Channel,10000
              500  1000

            River Rch & RM=Big River,Main Channel,5000
              300   600
        """)
        f = tmp_path / "multi.f01"
        f.write_text(content)
        flow = parse_flow(f)
        assert len(flow.flow_change_locations) == 2
        assert flow.flow_change_locations[0].river_station == 10000.0
        assert flow.flow_change_locations[0].flows == [500.0, 1000.0]
        assert flow.flow_change_locations[1].river_station == 5000.0
        assert flow.flow_change_locations[1].flows == [300.0, 600.0]

    def test_boundary_with_known_ws(self, tmp_path: Path):
        content = textwrap.dedent("""\
            Flow Title=Known WS Test
            Number of Profiles= 1
            Profile Names=Base

            Boundary for River Rch & Prof#=Test River,Test Reach, 1
            Up Type= 0
            Up Known WS= 450.5
            Dn Type= 0
            Dn Known WS= 440.2
        """)
        f = tmp_path / "knownws.f01"
        f.write_text(content)
        flow = parse_flow(f)
        assert len(flow.steady_boundaries) == 1
        bc = flow.steady_boundaries[0]
        assert bc.upstream_type == 0
        assert bc.upstream_known_ws == pytest.approx(450.5)
        assert bc.downstream_known_ws == pytest.approx(440.2)

    def test_empty_flow_file(self, tmp_path: Path):
        f = tmp_path / "empty.f01"
        f.write_text("")
        flow = parse_flow(f)
        assert flow.is_steady is True  # fallback to extension
        assert flow.num_profiles == 0
        assert flow.flow_change_locations == []

    def test_extension_fallback_unsteady(self, tmp_path: Path):
        f = tmp_path / "test.u01"
        f.write_text("Flow Title=Minimal Unsteady\n")
        flow = parse_flow(f)
        assert flow.is_steady is False

    def test_extension_fallback_steady(self, tmp_path: Path):
        f = tmp_path / "test.f01"
        f.write_text("Flow Title=Minimal Steady\n")
        flow = parse_flow(f)
        assert flow.is_steady is True

    def test_many_profiles_multiline_flows(self, tmp_path: Path):
        content = textwrap.dedent("""\
            Flow Title=Many Profiles
            Number of Profiles= 8
            Profile Names=P1,P2,P3,P4,P5,P6,P7,P8

            River Rch & RM=Creek,Reach A,1000
              100  200  300  400  500
              600  700  800
        """)
        f = tmp_path / "many.f01"
        f.write_text(content)
        flow = parse_flow(f)
        loc = flow.flow_change_locations[0]
        assert len(loc.flows) == 8
        assert loc.flows == [100, 200, 300, 400, 500, 600, 700, 800]


class TestSyntheticUnsteady:
    def test_dss_boundary(self, tmp_path: Path):
        content = textwrap.dedent("""\
            Flow Title=DSS Test
            Boundary Location=River X,Reach Y,2000
            Interval=1HOUR
            Flow Hydrograph= 0
            Use DSS= True
            DSS File=C:\\Models\\inflow.dss
            DSS Path=/RIVER X/2000/FLOW//1HOUR/RUN:BASE/
        """)
        f = tmp_path / "dss.u01"
        f.write_text(content)
        flow = parse_flow(f)
        assert flow.is_steady is False
        assert len(flow.unsteady_boundaries) == 1
        bc = flow.unsteady_boundaries[0]
        assert bc.use_dss is True
        assert "inflow.dss" in bc.dss_file
        assert bc.dss_path.startswith("/RIVER X/")

    def test_stage_hydrograph(self, tmp_path: Path):
        content = textwrap.dedent("""\
            Flow Title=Stage Test
            Boundary Location=River A,Lower,500
            Interval=30MIN
            Stage Hydrograph= 4
              450.0  452.5  451.0  450.0
        """)
        f = tmp_path / "stage.u01"
        f.write_text(content)
        flow = parse_flow(f)
        bc = flow.unsteady_boundaries[0]
        assert bc.bc_type == "Stage Hydrograph"
        assert len(bc.data) == 4
        assert bc.data[1] == pytest.approx(452.5)

    def test_initial_condition_flows(self, tmp_path: Path):
        content = textwrap.dedent("""\
            Flow Title=IC Test
            River Rch & RM=River Z,Main,8000
              500

            Boundary Location=River Z,Main,8000
            Flow Hydrograph= 3
              500  1000  500

            Boundary Location=River Z,Main,1000
            Friction Slope=0.001
        """)
        f = tmp_path / "ic.u01"
        f.write_text(content)
        flow = parse_flow(f)
        assert len(flow.flow_change_locations) == 1
        loc = flow.flow_change_locations[0]
        assert loc.river == "River Z"
        assert loc.river_station == 8000.0
        assert loc.flows[0] == 500.0

    def test_multiple_boundary_locations(self, tmp_path: Path):
        content = textwrap.dedent("""\
            Flow Title=Multi BC
            Boundary Location=R1,Upper,9000
            Interval=5MIN
            Flow Hydrograph= 3
              100  500  100

            Boundary Location=R1,Lower,1000
            Friction Slope=0.003
        """)
        f = tmp_path / "multi_bc.u01"
        f.write_text(content)
        flow = parse_flow(f)
        assert len(flow.unsteady_boundaries) == 2
        assert flow.unsteady_boundaries[0].bc_type == "Flow Hydrograph"
        assert flow.unsteady_boundaries[1].bc_type == "Normal Depth"
        assert flow.unsteady_boundaries[1].friction_slope == pytest.approx(0.003)


# ===================================================================
# Import / public API
# ===================================================================


class TestPublicAPI:
    def test_import_from_package(self):
        from hecras_compliance.parsers import parse_flow as pf
        assert callable(pf)

    def test_parse_flow_returns_flow_file(self):
        result = parse_flow(STEADY_FILE)
        assert isinstance(result, FlowFile)
