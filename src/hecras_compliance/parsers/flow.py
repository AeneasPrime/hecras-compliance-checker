"""Parser for HEC-RAS flow files — steady (.f01) and unsteady (.u01).

Steady files define discrete flow profiles with per-reach magnitudes and
per-profile boundary conditions.  Unsteady files define time-series
boundary conditions (hydrographs, normal-depth, rating curves) at
specific river stations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BOUNDARY_TYPES: dict[int, str] = {
    0: "Known WS",
    1: "Critical Depth",
    2: "Rating Curve",
    3: "Normal Depth",
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class FlowProfile:
    """A named steady-flow profile (e.g. ``"100yr"``)."""
    name: str


@dataclass
class FlowChangeLocation:
    """Location where flow magnitudes are specified.

    In steady flow each entry has one value per profile.
    In unsteady flow this represents initial-condition flows (typically one value).
    """
    river: str
    reach: str
    river_station: float
    flows: list[float] = field(default_factory=list)


@dataclass
class SteadyBoundaryCondition:
    """Upstream / downstream boundary for a single reach and profile."""
    river: str
    reach: str
    profile_number: int
    upstream_type: int = 0
    downstream_type: int = 0
    downstream_slope: float = 0.0
    upstream_slope: float = 0.0
    downstream_known_ws: float = 0.0
    upstream_known_ws: float = 0.0

    @property
    def upstream_type_name(self) -> str:
        return BOUNDARY_TYPES.get(self.upstream_type, f"Unknown ({self.upstream_type})")

    @property
    def downstream_type_name(self) -> str:
        return BOUNDARY_TYPES.get(
            self.downstream_type, f"Unknown ({self.downstream_type})"
        )


@dataclass
class UnsteadyBoundaryCondition:
    """One boundary-condition block from an unsteady flow file."""
    river: str
    reach: str
    river_station: str
    bc_type: str = ""
    interval: str = ""
    data: list[float] = field(default_factory=list)
    friction_slope: float | None = None
    use_dss: bool = False
    dss_file: str = ""
    dss_path: str = ""


@dataclass
class FlowFile:
    """Parsed HEC-RAS flow data (steady *or* unsteady)."""
    title: str = ""
    program_version: str = ""
    is_steady: bool = True
    profiles: list[FlowProfile] = field(default_factory=list)
    flow_change_locations: list[FlowChangeLocation] = field(default_factory=list)
    steady_boundaries: list[SteadyBoundaryCondition] = field(default_factory=list)
    unsteady_boundaries: list[UnsteadyBoundaryCondition] = field(
        default_factory=list
    )

    @property
    def profile_names(self) -> list[str]:
        return [p.name for p in self.profiles]

    @property
    def num_profiles(self) -> int:
        return len(self.profiles)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_fixed_values(
    lines: list[str], start: int, count: int,
) -> tuple[list[float], int]:
    """Read *count* whitespace-separated floats starting at *start*.

    Returns ``(values, next_unconsumed_line_index)``.
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


def _float(raw: str, default: float = 0.0) -> float:
    raw = raw.strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _int(raw: str, default: int = 0) -> int:
    raw = raw.strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Steady-flow parser
# ---------------------------------------------------------------------------

_BOUNDARY_BLOCK_STARTS = frozenset([
    "Boundary for River Rch & Prof#",
    "River Rch & RM",
    "DSS Import",
])


def _starts_new_block(line: str) -> bool:
    stripped = line.strip()
    return any(stripped.startswith(k) for k in _BOUNDARY_BLOCK_STARTS)


def _parse_steady(lines: list[str], flow: FlowFile) -> None:
    n_profiles = 0
    i = 0
    while i < len(lines):
        s = lines[i].strip()

        if s.startswith("Number of Profiles="):
            n_profiles = _int(s.split("=", 1)[1])
            i += 1
            continue

        if s.startswith("Profile Names="):
            names = s.split("=", 1)[1].split(",")
            flow.profiles = [
                FlowProfile(n.strip()) for n in names if n.strip()
            ]
            i += 1
            continue

        if s.startswith("River Rch & RM="):
            parts = s.split("=", 1)[1].split(",")
            river = parts[0].strip()
            reach = parts[1].strip() if len(parts) > 1 else ""
            try:
                station = float(parts[2].strip()) if len(parts) > 2 else 0.0
            except ValueError:
                station = 0.0
            want = n_profiles or len(flow.profiles) or 10
            values, i = _read_fixed_values(lines, i + 1, want)
            flow.flow_change_locations.append(
                FlowChangeLocation(river, reach, station, values)
            )
            continue

        if s.startswith("Boundary for River Rch & Prof#="):
            parts = s.split("=", 1)[1].split(",")
            river = parts[0].strip()
            reach = parts[1].strip() if len(parts) > 1 else ""
            prof = _int(parts[2]) if len(parts) > 2 else 0
            bc = SteadyBoundaryCondition(river, reach, prof)
            i += 1
            while i < len(lines):
                bs = lines[i].strip()
                if _starts_new_block(bs):
                    break
                if "=" in bs:
                    key, _, val = bs.partition("=")
                    key = key.strip()
                    val = val.strip()
                    if key == "Up Type":
                        bc.upstream_type = _int(val)
                    elif key == "Dn Type":
                        bc.downstream_type = _int(val)
                    elif key == "Dn Slope":
                        bc.downstream_slope = _float(val)
                    elif key == "Up Slope":
                        bc.upstream_slope = _float(val)
                    elif key == "Dn Known WS":
                        bc.downstream_known_ws = _float(val)
                    elif key == "Up Known WS":
                        bc.upstream_known_ws = _float(val)
                i += 1
            flow.steady_boundaries.append(bc)
            continue

        i += 1


# ---------------------------------------------------------------------------
# Unsteady-flow parser
# ---------------------------------------------------------------------------

_HYDRO_KEYWORDS: dict[str, str] = {
    "Flow Hydrograph": "Flow Hydrograph",
    "Stage Hydrograph": "Stage Hydrograph",
    "Lateral Inflow Hydrograph": "Lateral Inflow Hydrograph",
    "Uniform Lateral Inflow Hydrograph": "Uniform Lateral Inflow Hydrograph",
    "Gate Openings": "Gate Openings",
    "Rating Curve": "Rating Curve",
    "Precipitation Hydrograph": "Precipitation Hydrograph",
}


def _parse_unsteady(lines: list[str], flow: FlowFile) -> None:
    # Locate block boundaries
    block_starts: list[int] = []
    for i, line in enumerate(lines):
        if line.strip().startswith("Boundary Location="):
            block_starts.append(i)

    for idx, start in enumerate(block_starts):
        end = block_starts[idx + 1] if idx + 1 < len(block_starts) else len(lines)
        block = lines[start:end]

        header = block[0].strip().split("=", 1)[1]
        parts = [p.strip() for p in header.split(",")]
        river = parts[0] if parts else ""
        reach = parts[1] if len(parts) > 1 else ""
        station = parts[2] if len(parts) > 2 else ""

        bc = UnsteadyBoundaryCondition(river=river, reach=reach, river_station=station)

        j = 1
        while j < len(block):
            s = block[j].strip()

            if s.startswith("Interval="):
                bc.interval = s.split("=", 1)[1].strip()
                j += 1
                continue

            if s.startswith("Friction Slope="):
                bc.bc_type = "Normal Depth"
                bc.friction_slope = _float(s.split("=", 1)[1])
                j += 1
                continue

            if s.startswith("Use DSS="):
                raw = s.split("=", 1)[1].strip().lower()
                bc.use_dss = raw in ("true", "-1", "1")
                j += 1
                continue

            if s.startswith("DSS File="):
                bc.dss_file = s.split("=", 1)[1].strip()
                j += 1
                continue

            if s.startswith("DSS Path="):
                bc.dss_path = s.split("=", 1)[1].strip()
                j += 1
                continue

            # Check for hydrograph / data keywords
            matched = False
            for keyword, bc_name in _HYDRO_KEYWORDS.items():
                if s.startswith(keyword + "="):
                    bc.bc_type = bc_name
                    count = _int(s.split("=", 1)[1])
                    if count > 0:
                        bc.data, j = _read_fixed_values(block, j + 1, count)
                    else:
                        j += 1
                    matched = True
                    break
            if matched:
                continue

            j += 1

        flow.unsteady_boundaries.append(bc)

    # Initial condition flows (River Rch & RM= outside Boundary Location blocks)
    boundary_ranges = set()
    for idx, start in enumerate(block_starts):
        end = block_starts[idx + 1] if idx + 1 < len(block_starts) else len(lines)
        for k in range(start, end):
            boundary_ranges.add(k)

    i = 0
    while i < len(lines):
        if i in boundary_ranges:
            i += 1
            continue
        s = lines[i].strip()
        if s.startswith("River Rch & RM="):
            parts = s.split("=", 1)[1].split(",")
            river = parts[0].strip()
            reach = parts[1].strip() if len(parts) > 1 else ""
            try:
                station = float(parts[2].strip()) if len(parts) > 2 else 0.0
            except ValueError:
                station = 0.0
            values, i = _read_fixed_values(lines, i + 1, 10)
            flow.flow_change_locations.append(
                FlowChangeLocation(river, reach, station, values)
            )
            continue
        i += 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_flow(filepath: str | Path) -> FlowFile:
    """Parse a HEC-RAS steady (.f01) or unsteady (.u01) flow file.

    File type is detected from content: the presence of
    ``Boundary Location=`` indicates unsteady; ``Number of Profiles=``
    indicates steady.  When neither is found the file extension is used
    as a fallback (``.f`` → steady, ``.u`` → unsteady).

    Args:
        filepath: Path to the flow file.

    Returns:
        A :class:`FlowFile` with profiles, flow-change locations, and
        boundary conditions populated for the detected type.
    """
    filepath = Path(filepath)
    text = filepath.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    flow = FlowFile()

    # --- metadata (shared between both formats) ---
    for line in lines:
        s = line.strip()
        if s.startswith("Flow Title="):
            flow.title = s.split("=", 1)[1].strip()
        elif s.startswith("Program Version="):
            flow.program_version = s.split("=", 1)[1].strip()

    # --- detect type ---
    has_profiles = any(
        l.strip().startswith("Number of Profiles=") for l in lines
    )
    has_boundary_loc = any(
        l.strip().startswith("Boundary Location=") for l in lines
    )

    if has_boundary_loc:
        flow.is_steady = False
    elif has_profiles:
        flow.is_steady = True
    else:
        # Fallback to extension
        ext = filepath.suffix.lower()
        flow.is_steady = not ext.startswith(".u")

    # --- delegate ---
    try:
        if flow.is_steady:
            _parse_steady(lines, flow)
        else:
            _parse_unsteady(lines, flow)
    except Exception:
        logger.warning(
            "Error parsing flow file %s", filepath, exc_info=True
        )

    return flow
