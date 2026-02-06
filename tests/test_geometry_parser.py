"""Tests for the HEC-RAS geometry file parser."""

from pathlib import Path

import pytest

from hecras_compliance.parsers.geometry import (
    GeometryFile,
    parse_geometry,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample.g01"


@pytest.fixture
def geom() -> GeometryFile:
    return parse_geometry(FIXTURE)


# ---- file-level ----------------------------------------------------------

def test_title(geom: GeometryFile):
    assert geom.title == "Beargrass Creek Sample Geometry"


def test_cross_section_count(geom: GeometryFile):
    assert len(geom.cross_sections) == 6


def test_bridge_count(geom: GeometryFile):
    assert len(geom.bridges) == 1


# ---- river / reach assignment --------------------------------------------

def test_river_reach(geom: GeometryFile):
    for xs in geom.cross_sections:
        assert xs.river == "Beargrass Creek"
        assert xs.reach == "Upper Reach"
    assert geom.bridges[0].river == "Beargrass Creek"


# ---- cross section: RS 5000 (upstream, good values) ----------------------

class TestRS5000:
    @pytest.fixture(autouse=True)
    def _setup(self, geom: GeometryFile):
        self.xs = geom.get_cross_section(5000)
        assert self.xs is not None

    def test_station_elevation_count(self):
        assert len(self.xs.station_elevation) == 13

    def test_first_point(self):
        p = self.xs.station_elevation[0]
        assert p.station == pytest.approx(0.0)
        assert p.elevation == pytest.approx(530.2)

    def test_thalweg(self):
        elevations = [p.elevation for p in self.xs.station_elevation]
        assert min(elevations) == pytest.approx(512.3)

    def test_reach_lengths(self):
        rl = self.xs.reach_lengths
        assert rl.left == pytest.approx(1200)
        assert rl.channel == pytest.approx(1000)
        assert rl.right == pytest.approx(1200)

    def test_manning_n_regions(self):
        assert len(self.xs.manning_regions) == 3

    def test_manning_n_lob_channel_rob(self):
        assert self.xs.manning_n_left == pytest.approx(0.06)
        assert self.xs.manning_n_channel == pytest.approx(0.035)
        assert self.xs.manning_n_right == pytest.approx(0.06)

    def test_bank_stations(self):
        assert self.xs.bank_stations is not None
        assert self.xs.bank_stations.left == pytest.approx(200)
        assert self.xs.bank_stations.right == pytest.approx(350)

    def test_expansion_contraction(self):
        assert self.xs.expansion == pytest.approx(0.3)
        assert self.xs.contraction == pytest.approx(0.1)

    def test_no_ineffective_areas(self):
        assert self.xs.ineffective_areas == []

    def test_no_levees(self):
        assert self.xs.levee_stations == []

    def test_description(self):
        assert "Upstream boundary" in self.xs.description


# ---- cross section: RS 4000 (ineffective flow on left overbank) ----------

class TestRS4000:
    @pytest.fixture(autouse=True)
    def _setup(self, geom: GeometryFile):
        self.xs = geom.get_cross_section(4000)
        assert self.xs is not None

    def test_station_elevation_count(self):
        assert len(self.xs.station_elevation) == 11

    def test_manning_values(self):
        assert self.xs.manning_n_left == pytest.approx(0.08)
        assert self.xs.manning_n_channel == pytest.approx(0.04)
        assert self.xs.manning_n_right == pytest.approx(0.08)

    def test_one_ineffective_area(self):
        assert len(self.xs.ineffective_areas) == 1

    def test_ineffective_area_bounds(self):
        ia = self.xs.ineffective_areas[0]
        assert ia.left_station == pytest.approx(0)
        assert ia.left_elevation == pytest.approx(520)
        assert ia.right_station == pytest.approx(100)
        assert ia.right_elevation == pytest.approx(520)
        assert ia.left_permanent is False
        assert ia.right_permanent is False


# ---- cross section: RS 2900 (two ineffective areas, bridge departure) ----

class TestRS2900:
    @pytest.fixture(autouse=True)
    def _setup(self, geom: GeometryFile):
        self.xs = geom.get_cross_section(2900)
        assert self.xs is not None

    def test_two_ineffective_areas(self):
        assert len(self.xs.ineffective_areas) == 2

    def test_left_ineffective(self):
        ia = self.xs.ineffective_areas[0]
        assert ia.left_station == pytest.approx(0)
        assert ia.right_station == pytest.approx(100)
        assert ia.left_elevation == pytest.approx(519)

    def test_right_ineffective(self):
        ia = self.xs.ineffective_areas[1]
        assert ia.left_station == pytest.approx(380)
        assert ia.right_station == pytest.approx(480)

    def test_bridge_departure_coefficients(self):
        assert self.xs.expansion == pytest.approx(0.5)
        assert self.xs.contraction == pytest.approx(0.3)


# ---- cross section: RS 2000 (bad Manning's n, zero expansion) -----------

class TestRS2000:
    @pytest.fixture(autouse=True)
    def _setup(self, geom: GeometryFile):
        self.xs = geom.get_cross_section(2000)
        assert self.xs is not None

    def test_bad_manning_n(self):
        """All three zones should have the unrealistically low 0.001."""
        assert self.xs.manning_n_left == pytest.approx(0.001)
        assert self.xs.manning_n_channel == pytest.approx(0.001)
        assert self.xs.manning_n_right == pytest.approx(0.001)

    def test_zero_expansion(self):
        assert self.xs.expansion == pytest.approx(0.0)
        assert self.xs.contraction == pytest.approx(0.1)


# ---- cross section: RS 1000 (downstream boundary) -----------------------

def test_rs1000_reach_lengths_zero(geom: GeometryFile):
    xs = geom.get_cross_section(1000)
    assert xs is not None
    assert xs.reach_lengths.channel == pytest.approx(0)


# ---- bridge: RS 3000 ----------------------------------------------------

class TestBridge:
    @pytest.fixture(autouse=True)
    def _setup(self, geom: GeometryFile):
        self.br = geom.get_bridge(3000)
        assert self.br is not None

    def test_node_name(self):
        assert self.br.node_name == "Main St Bridge"

    def test_reach_lengths(self):
        assert self.br.reach_lengths.channel == pytest.approx(100)

    def test_skew(self):
        assert self.br.skew == pytest.approx(0)

    def test_deck_width(self):
        assert self.br.deck is not None
        assert self.br.deck.width == pytest.approx(40)

    def test_deck_points(self):
        assert len(self.br.deck.points) == 5

    def test_min_low_chord(self):
        assert self.br.min_low_chord == pytest.approx(522)

    def test_weir_coefficients(self):
        assert self.br.deck.us_weir_coef == pytest.approx(2.6)
        assert self.br.deck.ds_weir_coef == pytest.approx(2.6)

    def test_deck_distances(self):
        assert self.br.deck.us_dist == pytest.approx(20)
        assert self.br.deck.ds_dist == pytest.approx(20)

    def test_one_pier(self):
        assert len(self.br.piers) == 1

    def test_pier_center_station(self):
        pier = self.br.piers[0]
        assert pier.center_sta_upstream == pytest.approx(245)
        assert pier.center_sta_downstream == pytest.approx(245)

    def test_pier_elevations(self):
        pier = self.br.piers[0]
        assert len(pier.elevations) == 3
        assert pier.elevations[0].elevation == pytest.approx(507)
        assert pier.elevations[0].width == pytest.approx(3.0)
        assert pier.elevations[2].elevation == pytest.approx(522)
        assert pier.elevations[2].width == pytest.approx(5.0)

    def test_pier_width_at_low_chord(self):
        # Low chord is 522, pier width at 522 = 5.0
        assert self.br.total_pier_width_at_low_chord == pytest.approx(5.0)

    def test_opening_width(self):
        # US boundary stations 175 to 320 = 145 ft
        assert self.br.opening_width == pytest.approx(145)

    def test_us_ds_boundary_stations(self):
        assert self.br.us_boundary_sta == pytest.approx((175, 320))
        assert self.br.ds_boundary_sta == pytest.approx((170, 320))

    def test_energy_coefficients(self):
        assert len(self.br.energy_coefs) == 10

    def test_yarnell_coefficients(self):
        assert len(self.br.yarnell_coefs) == 4
        assert self.br.yarnell_coefs[0] == pytest.approx(0.9)

    def test_modeling_approach(self):
        assert self.br.modeling_approach == [0, 0, 0, 0]

    def test_description(self):
        assert "Main Street Bridge" in self.br.description


# ---- convenience lookups -------------------------------------------------

def test_lookup_missing_station(geom: GeometryFile):
    assert geom.get_cross_section(9999) is None
    assert geom.get_bridge(9999) is None


# ---- robustness: empty / garbage file ------------------------------------

def test_empty_file(tmp_path: Path):
    f = tmp_path / "empty.g01"
    f.write_text("")
    geom = parse_geometry(f)
    assert geom.title == ""
    assert geom.cross_sections == []
    assert geom.bridges == []


def test_title_only_file(tmp_path: Path):
    f = tmp_path / "title.g01"
    f.write_text("Geom Title=Just a Title\n")
    geom = parse_geometry(f)
    assert geom.title == "Just a Title"
    assert geom.cross_sections == []


def test_manning_n_values_tuple(geom: GeometryFile):
    xs = geom.get_cross_section(5000)
    left, chan, right = xs.manning_n_values
    assert left == pytest.approx(0.06)
    assert chan == pytest.approx(0.035)
    assert right == pytest.approx(0.06)
