"""Tests for HEC-RAS geometry parser against the sample.g01 fixture.

Covers:
  1. Correct number of cross sections extracted
  2. Manning's n values match what is in the file
  3. Bridge data is captured
  4. Parser handles missing / malformed sections without crashing
"""

from pathlib import Path
from textwrap import dedent

import pytest

from hecras_compliance.parsers.geometry import (
    Bridge,
    BridgeDeck,
    CrossSection,
    GeometryFile,
    parse_geometry,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample.g01"


@pytest.fixture
def geom() -> GeometryFile:
    return parse_geometry(FIXTURE)


# ===================================================================
# 1.  Correct number of cross sections extracted
# ===================================================================

class TestCrossSectionCounts:
    """Verify every node in sample.g01 is discovered and categorised."""

    def test_total_cross_sections(self, geom: GeometryFile):
        assert len(geom.cross_sections) == 6

    def test_total_bridges(self, geom: GeometryFile):
        assert len(geom.bridges) == 1

    def test_expected_river_stations(self, geom: GeometryFile):
        stations = sorted(xs.river_station for xs in geom.cross_sections)
        assert stations == pytest.approx([1000, 2000, 2900, 3100, 4000, 5000])

    def test_no_duplicate_stations(self, geom: GeometryFile):
        stations = [xs.river_station for xs in geom.cross_sections]
        assert len(stations) == len(set(stations))

    def test_cross_sections_ordered_by_appearance(self, geom: GeometryFile):
        """Parser should return XS in file order (upstream → downstream)."""
        stations = [xs.river_station for xs in geom.cross_sections]
        assert stations == [5000, 4000, 3100, 2900, 2000, 1000]

    def test_all_belong_to_same_reach(self, geom: GeometryFile):
        for xs in geom.cross_sections:
            assert xs.river == "Beargrass Creek"
            assert xs.reach == "Upper Reach"

    def test_station_elevation_counts_per_section(self, geom: GeometryFile):
        expected = {5000: 13, 4000: 11, 3100: 11, 2900: 11, 2000: 11, 1000: 11}
        for xs in geom.cross_sections:
            assert len(xs.station_elevation) == expected[xs.river_station], (
                f"RS {xs.river_station}"
            )


# ===================================================================
# 2.  Manning's n values match the fixture file
# ===================================================================

class TestManningValues:
    """
    Fixture Manning's n (LOB / Channel / ROB):
      RS 5000 : 0.060 / 0.035 / 0.060   (good natural channel)
      RS 4000 : 0.080 / 0.040 / 0.080   (slightly high overbank)
      RS 3100 : 0.050 / 0.035 / 0.050   (bridge approach)
      RS 2900 : 0.050 / 0.035 / 0.050   (bridge departure)
      RS 2000 : 0.001 / 0.001 / 0.001   (obviously wrong)
      RS 1000 : 0.060 / 0.035 / 0.060   (good)
    """

    EXPECTED = {
        5000: (0.060, 0.035, 0.060),
        4000: (0.080, 0.040, 0.080),
        3100: (0.050, 0.035, 0.050),
        2900: (0.050, 0.035, 0.050),
        2000: (0.001, 0.001, 0.001),
        1000: (0.060, 0.035, 0.060),
    }

    def test_all_manning_n_values(self, geom: GeometryFile):
        for station, (exp_l, exp_c, exp_r) in self.EXPECTED.items():
            xs = geom.get_cross_section(station)
            assert xs is not None, f"RS {station} not found"
            assert xs.manning_n_left == pytest.approx(exp_l), f"RS {station} LOB"
            assert xs.manning_n_channel == pytest.approx(exp_c), f"RS {station} Ch"
            assert xs.manning_n_right == pytest.approx(exp_r), f"RS {station} ROB"

    def test_manning_n_values_tuple(self, geom: GeometryFile):
        xs = geom.get_cross_section(5000)
        assert xs.manning_n_values == pytest.approx((0.06, 0.035, 0.06))

    def test_every_section_has_three_regions(self, geom: GeometryFile):
        for xs in geom.cross_sections:
            assert len(xs.manning_regions) == 3, f"RS {xs.river_station}"

    def test_region_start_stations_match_bank_stations(self, geom: GeometryFile):
        """The second Manning region should start at the left bank station."""
        for xs in geom.cross_sections:
            assert xs.bank_stations is not None
            channel_region = xs.manning_regions[1]
            assert channel_region.start_station == pytest.approx(
                xs.bank_stations.left
            ), f"RS {xs.river_station}"

    def test_bad_manning_n_detectable(self, geom: GeometryFile):
        """RS 2000 has 0.001 — a compliance checker should flag this."""
        xs = geom.get_cross_section(2000)
        for region in xs.manning_regions:
            assert region.n_value < 0.01  # well below any physical surface


# ===================================================================
# 3.  Bridge data is captured
# ===================================================================

class TestBridgeData:

    @pytest.fixture(autouse=True)
    def _setup(self, geom: GeometryFile):
        self.br: Bridge = geom.get_bridge(3000)
        assert self.br is not None

    # -- identification --

    def test_node_name(self):
        assert self.br.node_name == "Main St Bridge"

    def test_description(self):
        assert "Main Street Bridge" in self.br.description

    def test_reach_assignment(self):
        assert self.br.river == "Beargrass Creek"
        assert self.br.reach == "Upper Reach"

    def test_river_station(self):
        assert self.br.river_station == pytest.approx(3000)

    # -- deck geometry --

    def test_deck_exists(self):
        assert self.br.deck is not None

    def test_deck_width(self):
        assert self.br.deck.width == pytest.approx(40)

    def test_deck_station_count(self):
        assert len(self.br.deck.points) == 5

    def test_deck_low_chord_at_center(self):
        """Station 250 is the centre — low chord should be 522 (the minimum)."""
        centre = [p for p in self.br.deck.points if p.station == pytest.approx(250)]
        assert len(centre) == 1
        assert centre[0].low_chord == pytest.approx(522)

    def test_deck_high_chord_uniform(self):
        for p in self.br.deck.points:
            assert p.high_chord == pytest.approx(528)

    def test_min_low_chord(self):
        assert self.br.min_low_chord == pytest.approx(522)

    # -- weir and distance coefficients --

    def test_weir_coefficients(self):
        assert self.br.deck.us_weir_coef == pytest.approx(2.6)
        assert self.br.deck.ds_weir_coef == pytest.approx(2.6)

    def test_deck_distances(self):
        assert self.br.deck.us_dist == pytest.approx(20)
        assert self.br.deck.ds_dist == pytest.approx(20)

    # -- pier data --

    def test_pier_count(self):
        assert len(self.br.piers) == 1

    def test_pier_centre_stations(self):
        pier = self.br.piers[0]
        assert pier.center_sta_upstream == pytest.approx(245)
        assert pier.center_sta_downstream == pytest.approx(245)

    def test_pier_elevation_width_table(self):
        pier = self.br.piers[0]
        assert len(pier.elevations) == 3
        # bottom (507 ft) → 3 ft wide, mid (515) → 3.5, cap (522) → 5
        assert pier.elevations[0].elevation == pytest.approx(507)
        assert pier.elevations[0].width == pytest.approx(3.0)
        assert pier.elevations[1].width == pytest.approx(3.5)
        assert pier.elevations[2].elevation == pytest.approx(522)
        assert pier.elevations[2].width == pytest.approx(5.0)

    def test_pier_width_interpolation_at_low_chord(self):
        assert self.br.total_pier_width_at_low_chord == pytest.approx(5.0)

    # -- opening --

    def test_opening_width(self):
        assert self.br.opening_width == pytest.approx(145)  # 320 − 175

    def test_us_boundary_stations(self):
        assert self.br.us_boundary_sta == pytest.approx((175, 320))

    def test_ds_boundary_stations(self):
        assert self.br.ds_boundary_sta == pytest.approx((170, 320))

    # -- bridge coefficients --

    def test_skew(self):
        assert self.br.skew == pytest.approx(0)

    def test_yarnell_coefficients(self):
        assert self.br.yarnell_coefs[0] == pytest.approx(0.9)
        assert len(self.br.yarnell_coefs) == 4

    def test_energy_coefficients(self):
        assert len(self.br.energy_coefs) == 10
        assert self.br.energy_coefs[0] == pytest.approx(0.28)

    def test_momentum_coefficient(self):
        assert self.br.momentum_coef == pytest.approx(0)

    def test_wspro_coefficients(self):
        assert self.br.wspro_coefs == pytest.approx([0.9, 5.1])

    def test_modeling_approach(self):
        assert self.br.modeling_approach == [0, 0, 0, 0]

    # -- reach lengths --

    def test_reach_lengths(self):
        rl = self.br.reach_lengths
        assert rl.left == pytest.approx(150)
        assert rl.channel == pytest.approx(100)
        assert rl.right == pytest.approx(150)


# ===================================================================
# 4.  Expansion / contraction and ineffective flow extras
# ===================================================================

class TestExpansionContraction:
    """Verify Exp/Cntr parsed for every XS, including the 0.0 trigger."""

    EXPECTED = {
        5000: (0.3, 0.1),
        4000: (0.3, 0.1),
        3100: (0.5, 0.3),
        2900: (0.5, 0.3),
        2000: (0.0, 0.1),
        1000: (0.3, 0.1),
    }

    def test_all_expansion_contraction(self, geom: GeometryFile):
        for station, (exp, cntr) in self.EXPECTED.items():
            xs = geom.get_cross_section(station)
            assert xs.expansion == pytest.approx(exp), f"RS {station} expansion"
            assert xs.contraction == pytest.approx(cntr), f"RS {station} contraction"

    def test_zero_expansion_detectable(self, geom: GeometryFile):
        xs = geom.get_cross_section(2000)
        assert xs.expansion == 0.0


class TestIneffectiveFlow:

    def test_rs4000_single_left_overbank(self, geom: GeometryFile):
        xs = geom.get_cross_section(4000)
        assert len(xs.ineffective_areas) == 1
        ia = xs.ineffective_areas[0]
        assert ia.left_station == pytest.approx(0)
        assert ia.right_station == pytest.approx(100)
        assert ia.left_elevation == pytest.approx(520)
        assert ia.left_permanent is False

    def test_rs2900_both_overbanks(self, geom: GeometryFile):
        xs = geom.get_cross_section(2900)
        assert len(xs.ineffective_areas) == 2
        left, right = xs.ineffective_areas
        assert left.left_station == pytest.approx(0)
        assert left.right_station == pytest.approx(100)
        assert right.left_station == pytest.approx(380)
        assert right.right_station == pytest.approx(480)

    def test_sections_without_ineffective(self, geom: GeometryFile):
        for station in [5000, 3100, 2000, 1000]:
            xs = geom.get_cross_section(station)
            assert xs.ineffective_areas == [], f"RS {station}"


# ===================================================================
# 5.  Robustness — missing / malformed data does not crash
# ===================================================================

def _write_and_parse(tmp_path: Path, content: str) -> GeometryFile:
    f = tmp_path / "test.g01"
    f.write_text(dedent(content))
    return parse_geometry(f)


class TestRobustnessEmptyInputs:

    def test_empty_file(self, tmp_path: Path):
        geom = _write_and_parse(tmp_path, "")
        assert geom.title == ""
        assert geom.cross_sections == []
        assert geom.bridges == []

    def test_title_only(self, tmp_path: Path):
        geom = _write_and_parse(tmp_path, "Geom Title=My Model\n")
        assert geom.title == "My Model"
        assert geom.cross_sections == []

    def test_header_only(self, tmp_path: Path):
        geom = _write_and_parse(tmp_path, """\
            Geom Title=Header Only
            BEGIN HEADER:
            END HEADER:
        """)
        assert geom.title == "Header Only"
        assert geom.cross_sections == []


class TestRobustnessMissingSections:
    """A cross section with some keywords absent should still parse."""

    MINIMAL_XS = """\
        River Reach=Test River,Main
        Type RM Length L Ch R = 1 ,100   ,0   ,0   ,0
    """

    def test_bare_type_line_only(self, tmp_path: Path):
        geom = _write_and_parse(tmp_path, self.MINIMAL_XS)
        assert len(geom.cross_sections) == 1
        xs = geom.cross_sections[0]
        assert xs.river_station == pytest.approx(100)
        assert xs.station_elevation == []
        assert xs.manning_regions == []
        assert xs.bank_stations is None
        assert xs.ineffective_areas == []
        assert xs.levee_stations == []

    def test_no_manning_still_parses(self, tmp_path: Path):
        geom = _write_and_parse(tmp_path, """\
            River Reach=Test,Main
            Type RM Length L Ch R = 1 ,200   ,0   ,0   ,0
            #Sta/Elev= 3
                   0     100      50      95     100     100
            Bank Sta=20,80
        """)
        xs = geom.cross_sections[0]
        assert len(xs.station_elevation) == 3
        assert xs.manning_regions == []
        assert xs.manning_n_left is None
        assert xs.manning_n_channel is None

    def test_no_bank_stations_channel_n_is_none(self, tmp_path: Path):
        geom = _write_and_parse(tmp_path, """\
            River Reach=Test,Main
            Type RM Length L Ch R = 1 ,300   ,0   ,0   ,0
            #Mann= 2 , 0
                 .05       0       0    .035      50       0
        """)
        xs = geom.cross_sections[0]
        assert len(xs.manning_regions) == 2
        assert xs.manning_n_left == pytest.approx(0.05)
        assert xs.manning_n_channel is None  # no bank stations
        assert xs.manning_n_right == pytest.approx(0.035)

    def test_no_exp_cntr_defaults_to_zero(self, tmp_path: Path):
        geom = _write_and_parse(tmp_path, self.MINIMAL_XS)
        xs = geom.cross_sections[0]
        assert xs.expansion == 0.0
        assert xs.contraction == 0.0

    def test_no_description(self, tmp_path: Path):
        geom = _write_and_parse(tmp_path, self.MINIMAL_XS)
        assert geom.cross_sections[0].description == ""


class TestRobustnessBridge:

    def test_bridge_no_deck(self, tmp_path: Path):
        geom = _write_and_parse(tmp_path, """\
            River Reach=Test,Main
            Type RM Length L Ch R = 6 ,500   ,0   ,0   ,0
            Node Name=Empty Bridge
        """)
        assert len(geom.bridges) == 1
        br = geom.bridges[0]
        assert br.node_name == "Empty Bridge"
        assert br.deck is None
        assert br.piers == []
        assert br.min_low_chord is None
        assert br.opening_width is None
        assert br.total_pier_width_at_low_chord == 0.0

    def test_bridge_no_piers(self, tmp_path: Path):
        geom = _write_and_parse(tmp_path, """\
            River Reach=Test,Main
            Type RM Length L Ch R = 6 ,500   ,0   ,0   ,0
            #Deck/Roadway= 2 ,   30
                   0     520     518     100     520     518
        """)
        br = geom.bridges[0]
        assert br.deck is not None
        assert len(br.deck.points) == 2
        assert br.piers == []
        assert br.total_pier_width_at_low_chord == 0.0


class TestRobustnessMalformedData:

    def test_garbage_after_header_ignored(self, tmp_path: Path):
        geom = _write_and_parse(tmp_path, """\
            Geom Title=OK
            some random junk line
            more junk !@#$%
            River Reach=Test,Main
            Type RM Length L Ch R = 1 ,100   ,0   ,0   ,0
            #Sta/Elev= 2
                   0     100      50      95
        """)
        assert len(geom.cross_sections) == 1
        assert len(geom.cross_sections[0].station_elevation) == 2

    def test_windows_line_endings(self, tmp_path: Path):
        content = (
            "Geom Title=CRLF Test\r\n"
            "River Reach=Test,Main\r\n"
            "Type RM Length L Ch R = 1 ,100   ,0   ,0   ,0\r\n"
            "#Sta/Elev= 2\r\n"
            "       0     100      50      95\r\n"
            "#Mann= 1 , 0\r\n"
            "    .035       0       0\r\n"
            "Bank Sta=10,40\r\n"
        )
        f = tmp_path / "crlf.g01"
        f.write_text(content)
        geom = parse_geometry(f)
        xs = geom.cross_sections[0]
        assert len(xs.station_elevation) == 2
        assert xs.manning_n_left == pytest.approx(0.035)

    def test_multiple_reaches(self, tmp_path: Path):
        geom = _write_and_parse(tmp_path, """\
            Geom Title=Two Reaches
            River Reach=Creek,Upper
            Type RM Length L Ch R = 1 ,200   ,0   ,0   ,0
            River Reach=Creek,Lower
            Type RM Length L Ch R = 1 ,100   ,0   ,0   ,0
        """)
        assert len(geom.cross_sections) == 2
        assert geom.cross_sections[0].reach == "Upper"
        assert geom.cross_sections[1].reach == "Lower"

    def test_xs_and_bridge_intermixed(self, tmp_path: Path):
        geom = _write_and_parse(tmp_path, """\
            River Reach=Test,Main
            Type RM Length L Ch R = 1 ,300   ,0   ,0   ,0
            Type RM Length L Ch R = 6 ,200   ,0   ,0   ,0
            Node Name=Test Bridge
            Type RM Length L Ch R = 1 ,100   ,0   ,0   ,0
        """)
        assert len(geom.cross_sections) == 2
        assert len(geom.bridges) == 1
        assert geom.bridges[0].river_station == pytest.approx(200)


class TestLookupHelpers:

    def test_get_cross_section_found(self, geom: GeometryFile):
        assert geom.get_cross_section(5000) is not None

    def test_get_cross_section_missing(self, geom: GeometryFile):
        assert geom.get_cross_section(9999) is None

    def test_get_bridge_found(self, geom: GeometryFile):
        assert geom.get_bridge(3000) is not None

    def test_get_bridge_missing(self, geom: GeometryFile):
        assert geom.get_bridge(9999) is None

    def test_get_cross_section_close_match(self, geom: GeometryFile):
        """Station lookup uses a 0.01 tolerance."""
        assert geom.get_cross_section(5000.005) is not None
        assert geom.get_cross_section(5000.02) is None
