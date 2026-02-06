"""Parser for HEC-RAS geometry files (.g01 through .g99).

Reads the structured text format and returns Python dataclasses for
cross sections, bridges/culverts, and their associated hydraulic data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class StationElevation:
    station: float
    elevation: float


@dataclass
class ManningRegion:
    """Manning's n applied starting at a given station."""
    n_value: float
    start_station: float


@dataclass
class IneffectiveFlowArea:
    """Region where water ponds but does not actively convey flow."""
    left_station: float
    left_elevation: float
    left_permanent: bool
    right_station: float
    right_elevation: float
    right_permanent: bool


@dataclass
class LeveeStation:
    """Levee crest position — flow is blocked until water exceeds this elevation."""
    station: float
    elevation: float


@dataclass
class ReachLengths:
    """Downstream reach lengths to the next cross section."""
    left: float
    channel: float
    right: float


@dataclass
class BankStations:
    left: float
    right: float


@dataclass
class DeckPoint:
    """One station along a bridge deck / roadway."""
    station: float
    high_chord: float
    low_chord: float


@dataclass
class PierElevWidth:
    """Pier width at a given elevation."""
    elevation: float
    width: float


@dataclass
class Pier:
    skew: float = 0.0
    center_sta_upstream: float = 0.0
    center_sta_downstream: float = 0.0
    elevations: list[PierElevWidth] = field(default_factory=list)


@dataclass
class BridgeDeck:
    width: float = 0.0
    points: list[DeckPoint] = field(default_factory=list)
    us_weir_coef: float = 0.0
    ds_weir_coef: float = 0.0
    us_dist: float = 0.0
    ds_dist: float = 0.0


@dataclass
class CrossSection:
    river_station: float
    river: str
    reach: str
    description: str = ""
    reach_lengths: ReachLengths = field(
        default_factory=lambda: ReachLengths(0.0, 0.0, 0.0)
    )
    station_elevation: list[StationElevation] = field(default_factory=list)
    manning_regions: list[ManningRegion] = field(default_factory=list)
    bank_stations: BankStations | None = None
    expansion: float = 0.0
    contraction: float = 0.0
    ineffective_areas: list[IneffectiveFlowArea] = field(default_factory=list)
    levee_stations: list[LeveeStation] = field(default_factory=list)

    # -- convenience access for the three standard Manning's n zones --------

    @property
    def manning_n_left(self) -> float | None:
        """Manning's n for the left overbank (first region)."""
        return self.manning_regions[0].n_value if self.manning_regions else None

    @property
    def manning_n_channel(self) -> float | None:
        """Manning's n for the main channel.

        Identified as the first region whose start station is at or past the
        left bank station.
        """
        if not self.manning_regions or not self.bank_stations:
            return None
        left_bank = self.bank_stations.left
        for region in self.manning_regions:
            if region.start_station >= left_bank:
                return region.n_value
        return self.manning_regions[-1].n_value

    @property
    def manning_n_right(self) -> float | None:
        """Manning's n for the right overbank (last region)."""
        return self.manning_regions[-1].n_value if self.manning_regions else None

    @property
    def manning_n_values(self) -> tuple[float | None, float | None, float | None]:
        """(left_overbank, channel, right_overbank) as a convenience tuple."""
        return (self.manning_n_left, self.manning_n_channel, self.manning_n_right)


@dataclass
class Bridge:
    river_station: float
    river: str
    reach: str
    description: str = ""
    node_name: str = ""
    reach_lengths: ReachLengths = field(
        default_factory=lambda: ReachLengths(0.0, 0.0, 0.0)
    )
    skew: float = 0.0
    deck: BridgeDeck | None = None
    piers: list[Pier] = field(default_factory=list)
    us_boundary_sta: tuple[float, float] | None = None
    ds_boundary_sta: tuple[float, float] | None = None
    modeling_approach: list[int] = field(default_factory=list)
    energy_coefs: list[float] = field(default_factory=list)
    yarnell_coefs: list[float] = field(default_factory=list)
    momentum_coef: float | None = None
    wspro_coefs: list[float] = field(default_factory=list)

    @property
    def min_low_chord(self) -> float | None:
        """Lowest low-chord elevation across the deck."""
        if not self.deck or not self.deck.points:
            return None
        return min(p.low_chord for p in self.deck.points)

    @property
    def opening_width(self) -> float | None:
        """Clear opening width between upstream boundary stations."""
        if self.us_boundary_sta:
            return abs(self.us_boundary_sta[1] - self.us_boundary_sta[0])
        return None

    @property
    def total_pier_width_at_low_chord(self) -> float:
        """Sum of pier widths evaluated at the minimum low-chord elevation."""
        lc = self.min_low_chord
        if lc is None:
            return 0.0
        total = 0.0
        for pier in self.piers:
            total += _interpolate_pier_width(pier, lc)
        return total


@dataclass
class GeometryFile:
    """Top-level container for a parsed HEC-RAS geometry file."""
    title: str = ""
    cross_sections: list[CrossSection] = field(default_factory=list)
    bridges: list[Bridge] = field(default_factory=list)

    def get_cross_section(self, station: float) -> CrossSection | None:
        for xs in self.cross_sections:
            if abs(xs.river_station - station) < 0.01:
                return xs
        return None

    def get_bridge(self, station: float) -> Bridge | None:
        for br in self.bridges:
            if abs(br.river_station - station) < 0.01:
                return br
        return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _interpolate_pier_width(pier: Pier, elevation: float) -> float:
    """Linearly interpolate pier width at *elevation* from the elev/width table."""
    pts = pier.elevations
    if not pts:
        return 0.0
    if elevation <= pts[0].elevation:
        return pts[0].width
    if elevation >= pts[-1].elevation:
        return pts[-1].width
    for i in range(len(pts) - 1):
        lo, hi = pts[i], pts[i + 1]
        if lo.elevation <= elevation <= hi.elevation:
            frac = (elevation - lo.elevation) / (hi.elevation - lo.elevation)
            return lo.width + frac * (hi.width - lo.width)
    return pts[-1].width


def _read_fixed_values(
    lines: list[str], start: int, count: int
) -> tuple[list[float], int]:
    """Read *count* whitespace-separated floats from *lines* beginning at *start*.

    Returns ``(values, next_line_index)``.  Stops early when a line cannot
    yield any numeric tokens (keyword boundary or blank line).
    """
    values: list[float] = []
    idx = start
    while len(values) < count and idx < len(lines):
        tokens = lines[idx].split()
        parsed_any = False
        for tok in tokens:
            try:
                values.append(float(tok))
                parsed_any = True
            except ValueError:
                break
            if len(values) >= count:
                break
        if not parsed_any:
            break
        idx += 1
    return values[:count], idx


def _parse_comma_floats(text: str) -> list[float]:
    """Parse ``'1.2 , 3.4 , 5'`` into ``[1.2, 3.4, 5.0]``."""
    out: list[float] = []
    for part in text.split(","):
        part = part.strip()
        if part:
            try:
                out.append(float(part))
            except ValueError:
                pass
    return out


def _extract_description(lines: list[str], start: int) -> tuple[str, int]:
    """Collect text between ``BEGIN DESCRIPTION:`` and ``END DESCRIPTION:``.

    *start* should point at the ``BEGIN DESCRIPTION:`` line.
    """
    parts: list[str] = []
    idx = start + 1  # skip the BEGIN line itself
    while idx < len(lines):
        stripped = lines[idx].strip()
        if stripped.startswith("END DESCRIPTION"):
            return "\n".join(parts).strip(), idx + 1
        parts.append(stripped)
        idx += 1
    return "\n".join(parts).strip(), idx


# ---------------------------------------------------------------------------
# Block discovery
# ---------------------------------------------------------------------------

_TYPE_RE = "Type RM Length L Ch R"


def _find_node_boundaries(
    lines: list[str],
) -> list[tuple[str, str, int, int]]:
    """Return ``(river, reach, start_line, end_line)`` for every node block."""
    river, reach = "", ""
    starts: list[tuple[str, str, int]] = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("River Reach="):
            parts = stripped.split("=", 1)[1].split(",", 1)
            river = parts[0].strip()
            reach = parts[1].strip() if len(parts) > 1 else ""
        elif stripped.startswith(_TYPE_RE):
            starts.append((river, reach, i))

    boundaries: list[tuple[str, str, int, int]] = []
    for j, (r, rch, s) in enumerate(starts):
        end = starts[j + 1][2] if j + 1 < len(starts) else len(lines)
        boundaries.append((r, rch, s, end))
    return boundaries


def _parse_type_line(line: str) -> tuple[int, float, ReachLengths]:
    """Parse ``Type RM Length L Ch R = <type> ,<sta> ,<L> ,<Ch> ,<R>``."""
    rhs = line.split("=", 1)[1]
    parts = [p.strip() for p in rhs.split(",")]
    node_type = int(parts[0])
    station = float(parts[1])
    left = float(parts[2]) if len(parts) > 2 else 0.0
    chan = float(parts[3]) if len(parts) > 3 else 0.0
    right = float(parts[4]) if len(parts) > 4 else 0.0
    return node_type, station, ReachLengths(left, chan, right)


# ---------------------------------------------------------------------------
# Cross-section block parser
# ---------------------------------------------------------------------------

def _parse_cross_section(lines: list[str], river: str, reach: str) -> CrossSection:
    node_type, station, rl = _parse_type_line(lines[0])
    xs = CrossSection(river_station=station, river=river, reach=reach, reach_lengths=rl)

    i = 1
    while i < len(lines):
        s = lines[i].strip()

        if s.startswith("BEGIN DESCRIPTION"):
            xs.description, i = _extract_description(lines, i)
            continue

        if s.startswith("#Sta/Elev="):
            count = int(s.split("=")[1].strip())
            vals, i = _read_fixed_values(lines, i + 1, count * 2)
            xs.station_elevation = [
                StationElevation(vals[j], vals[j + 1])
                for j in range(0, len(vals) - 1, 2)
            ]
            continue

        if s.startswith("#Mann="):
            header = s.split("=")[1].split(",")
            n_regions = int(header[0].strip())
            vals, i = _read_fixed_values(lines, i + 1, n_regions * 3)
            xs.manning_regions = [
                ManningRegion(n_value=vals[j], start_station=vals[j + 1])
                for j in range(0, len(vals) - 2, 3)
            ]
            continue

        if s.startswith("Bank Sta="):
            parts = _parse_comma_floats(s.split("=", 1)[1])
            if len(parts) >= 2:
                xs.bank_stations = BankStations(parts[0], parts[1])
            i += 1
            continue

        if s.startswith("Exp/Cntr="):
            parts = _parse_comma_floats(s.split("=", 1)[1])
            if len(parts) >= 2:
                xs.expansion = parts[0]
                xs.contraction = parts[1]
            i += 1
            continue

        if s.startswith("#IEffective="):
            header = s.split("=")[1].split(",")
            n_areas = int(header[0].strip())
            vals, i = _read_fixed_values(lines, i + 1, n_areas * 6)
            for j in range(0, len(vals) - 5, 6):
                xs.ineffective_areas.append(
                    IneffectiveFlowArea(
                        left_station=vals[j],
                        left_elevation=vals[j + 1],
                        left_permanent=vals[j + 2] != 0,
                        right_station=vals[j + 3],
                        right_elevation=vals[j + 4],
                        right_permanent=vals[j + 5] != 0,
                    )
                )
            continue

        if s.startswith("#Levee="):
            header = s.split("=")[1].split(",")
            n_levees = int(header[0].strip())
            # Each levee entry: station, elevation, permanent flag (triplet)
            vals, i = _read_fixed_values(lines, i + 1, n_levees * 3)
            for j in range(0, len(vals) - 1, 3):
                xs.levee_stations.append(
                    LeveeStation(station=vals[j], elevation=vals[j + 1])
                )
            continue

        # Bare "Levee=" (comma-delimited, no count header)
        if s.startswith("Levee=") and not s.startswith("Levee= "):
            parts = _parse_comma_floats(s.split("=", 1)[1])
            for j in range(0, len(parts) - 1, 2):
                xs.levee_stations.append(
                    LeveeStation(station=parts[j], elevation=parts[j + 1])
                )
            i += 1
            continue

        i += 1

    return xs


# ---------------------------------------------------------------------------
# Bridge / culvert block parser
# ---------------------------------------------------------------------------

def _parse_bridge(lines: list[str], river: str, reach: str) -> Bridge:
    _, station, rl = _parse_type_line(lines[0])
    br = Bridge(river_station=station, river=river, reach=reach, reach_lengths=rl)

    current_pier: Pier | None = None
    i = 1

    while i < len(lines):
        s = lines[i].strip()

        if s.startswith("BEGIN DESCRIPTION"):
            br.description, i = _extract_description(lines, i)
            continue

        if s.startswith("Node Name="):
            br.node_name = s.split("=", 1)[1].strip()
            i += 1
            continue

        # ---- deck / roadway ------------------------------------------------
        if s.startswith("#Deck/Roadway="):
            header = s.split("=")[1].split(",")
            n_pts = int(header[0].strip())
            width = float(header[1].strip()) if len(header) > 1 else 0.0
            vals, i = _read_fixed_values(lines, i + 1, n_pts * 3)
            deck = BridgeDeck(width=width)
            for j in range(0, len(vals) - 2, 3):
                deck.points.append(
                    DeckPoint(vals[j], vals[j + 1], vals[j + 2])
                )
            br.deck = deck
            continue

        if s.startswith("BC Design Weir Coef="):
            parts = _parse_comma_floats(s.split("=", 1)[1])
            if br.deck and len(parts) >= 2:
                br.deck.us_weir_coef = parts[0]
                br.deck.ds_weir_coef = parts[1]
            i += 1
            continue

        if s.startswith("Deck Dist="):
            parts = _parse_comma_floats(s.split("=", 1)[1])
            if br.deck and len(parts) >= 2:
                br.deck.us_dist = parts[0]
                br.deck.ds_dist = parts[1]
            i += 1
            continue

        # ---- boundary stations ---------------------------------------------
        if s.startswith("US Boundary Condition Sta="):
            parts = _parse_comma_floats(s.split("=", 1)[1])
            if len(parts) >= 2:
                br.us_boundary_sta = (parts[0], parts[1])
            i += 1
            continue

        if s.startswith("DS Boundary Condition Sta="):
            parts = _parse_comma_floats(s.split("=", 1)[1])
            if len(parts) >= 2:
                br.ds_boundary_sta = (parts[0], parts[1])
            i += 1
            continue

        # ---- bridge geometry -----------------------------------------------
        if s.startswith("Bridge Skew="):
            try:
                br.skew = float(s.split("=", 1)[1].strip())
            except ValueError:
                pass
            i += 1
            continue

        # ---- piers ---------------------------------------------------------
        if s.startswith("#Pier="):
            # Just the count — actual pier objects created when Pier Skew= seen
            i += 1
            continue

        if s.startswith("Pier Skew="):
            current_pier = Pier(skew=float(s.split("=", 1)[1].strip()))
            br.piers.append(current_pier)
            i += 1
            continue

        if s.startswith("Center Sta Upstream="):
            if current_pier:
                current_pier.center_sta_upstream = float(
                    s.split("=", 1)[1].strip()
                )
            i += 1
            continue

        if s.startswith("Center Sta Downstream="):
            if current_pier:
                current_pier.center_sta_downstream = float(
                    s.split("=", 1)[1].strip()
                )
            i += 1
            continue

        if s.startswith("#Pier Elev="):
            n_pairs = int(s.split("=")[1].strip())
            vals, i = _read_fixed_values(lines, i + 1, n_pairs * 2)
            if current_pier:
                for j in range(0, len(vals) - 1, 2):
                    current_pier.elevations.append(
                        PierElevWidth(vals[j], vals[j + 1])
                    )
            continue

        # ---- modelling & coefficients --------------------------------------
        if s.startswith("Bridge Modeling Approach="):
            parts = _parse_comma_floats(s.split("=", 1)[1])
            br.modeling_approach = [int(v) for v in parts]
            i += 1
            continue

        if s.startswith("Bridge Coef Energy="):
            br.energy_coefs = _parse_comma_floats(s.split("=", 1)[1])
            i += 1
            continue

        if s.startswith("Bridge Coef PI Yarnell="):
            br.yarnell_coefs = _parse_comma_floats(s.split("=", 1)[1])
            i += 1
            continue

        if s.startswith("Bridge Coef Momentum="):
            try:
                br.momentum_coef = float(s.split("=", 1)[1].strip())
            except ValueError:
                pass
            i += 1
            continue

        if s.startswith("Bridge WSPRO Data Coef="):
            br.wspro_coefs = _parse_comma_floats(s.split("=", 1)[1])
            i += 1
            continue

        i += 1

    return br


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_geometry(filepath: str | Path) -> GeometryFile:
    """Parse a HEC-RAS geometry file and return structured data.

    Args:
        filepath: Path to a ``.g01`` … ``.g99`` file.

    Returns:
        A :class:`GeometryFile` containing all cross sections and bridges.
        Sections that cannot be parsed are skipped with a log warning.
    """
    filepath = Path(filepath)
    text = filepath.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    title = ""
    for line in lines:
        if line.strip().startswith("Geom Title="):
            title = line.split("=", 1)[1].strip()
            break

    geom = GeometryFile(title=title)

    for river, reach, start, end in _find_node_boundaries(lines):
        block = lines[start:end]
        try:
            node_type, _, _ = _parse_type_line(block[0])
        except (ValueError, IndexError):
            logger.warning("Unparseable Type line at line %d, skipping", start + 1)
            continue

        if node_type == 1:
            try:
                geom.cross_sections.append(
                    _parse_cross_section(block, river, reach)
                )
            except Exception:
                logger.warning(
                    "Failed to parse cross section at line %d", start + 1,
                    exc_info=True,
                )
        elif node_type == 6:
            try:
                geom.bridges.append(_parse_bridge(block, river, reach))
            except Exception:
                logger.warning(
                    "Failed to parse bridge at line %d", start + 1,
                    exc_info=True,
                )
        else:
            logger.debug("Skipping unknown node type %d at line %d", node_type, start + 1)

    return geom
