"""Parser for HEC-RAS plan files (.p01 through .p99).

Reads the keyword=value text format and returns Python dataclasses
covering simulation type, computational settings, encroachment /
floodway configuration, and output intervals.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLAN_TYPES: dict[int, str] = {
    1: "Steady Flow",
    2: "Unsteady Flow",
    3: "Quasi-Unsteady Flow",
}

FRICTION_SLOPE_METHODS: dict[int, str] = {
    1: "Average Conveyance",
    2: "Average Friction Slope",
    3: "Geometric Mean Friction Slope",
    4: "Harmonic Mean Friction Slope",
}

ENCROACHMENT_METHODS: dict[int, str] = {
    1: "Specified Stations",
    2: "Fixed Top Width",
    3: "Percent Reduction in Conveyance",
    4: "Target Surcharge",
    5: "Optimized Surcharge and Energy",
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ComputationalSettings:
    """Solver tolerances and algorithmic options."""
    flow_tolerance: float = 0.01
    ws_tolerance: float = 0.01
    critical_always: bool = False
    friction_slope_method: int = 1
    flow_ratio: float = 0.01
    split_flow: bool = False
    warm_up: bool = False
    computation_interval: str = ""
    flow_tolerance_method: int = 0
    check_data: bool = False

    @property
    def friction_slope_method_name(self) -> str:
        return FRICTION_SLOPE_METHODS.get(
            self.friction_slope_method,
            f"Unknown ({self.friction_slope_method})",
        )


@dataclass
class EncroachmentSettings:
    """Global floodplain-encroachment parameters.

    For *FEMA floodway* analysis the typical configuration is
    ``method = 4`` with ``values[0] = 1.0`` (1-foot allowable surcharge).
    """
    enabled: bool = False
    method: int = 0
    values: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])

    @property
    def method_name(self) -> str:
        return ENCROACHMENT_METHODS.get(
            self.method, f"Unknown ({self.method})"
        )

    @property
    def is_floodway(self) -> bool:
        """True when encroachment is a FEMA-style floodway analysis
        (Method 4 *Target Surcharge* or Method 5 *Optimized*)."""
        return self.enabled and self.method in (4, 5)

    @property
    def target_surcharge(self) -> float | None:
        """Allowable water-surface rise (ft) for Methods 4/5, else ``None``."""
        if self.is_floodway and self.values:
            return self.values[0]
        return None


@dataclass
class OutputSettings:
    """Run flags and output-interval configuration."""
    run_htab: bool = False
    run_post_process: bool = False
    run_sediment: bool = False
    run_unet: bool = False
    run_ras_mapper: bool = False
    write_ic_file: bool = False
    write_detailed: bool = False
    echo_input: bool = False
    echo_parameters: bool = False
    echo_output: bool = False
    log_output_level: int = 0
    output_interval: str = ""
    mapping_interval: str = ""
    hydrograph_output_interval: str = ""
    detailed_output_interval: str = ""
    instantaneous_interval: str = ""


@dataclass
class PlanFile:
    """Parsed contents of a HEC-RAS plan file."""
    title: str = ""
    program_version: str = ""
    short_identifier: str = ""
    simulation_date: str = ""
    geom_file: str = ""
    flow_file: str = ""
    flow_regime: str = ""
    plan_type: int = 0
    profiles: list[str] = field(default_factory=list)
    computation: ComputationalSettings = field(
        default_factory=ComputationalSettings
    )
    encroachment: EncroachmentSettings = field(
        default_factory=EncroachmentSettings
    )
    output: OutputSettings = field(default_factory=OutputSettings)
    paused: bool = False

    @property
    def plan_type_name(self) -> str:
        return PLAN_TYPES.get(self.plan_type, f"Unknown ({self.plan_type})")

    @property
    def is_steady(self) -> bool:
        return self.plan_type == 1

    @property
    def is_floodway_analysis(self) -> bool:
        return self.encroachment.is_floodway


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _flag(value: str) -> bool:
    """Interpret a HEC-RAS boolean flag.

    HEC-RAS uses ``0`` for *off* and either ``1`` or ``-1`` for *on*.
    """
    value = value.strip()
    if not value:
        return False
    try:
        return int(value) != 0
    except ValueError:
        return value.lower() in ("true", "yes")


def _float(value: str, default: float = 0.0) -> float:
    value = value.strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _int(value: str, default: int = 0) -> int:
    value = value.strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _comma_floats(text: str) -> list[float]:
    out: list[float] = []
    for part in text.split(","):
        part = part.strip()
        if part:
            try:
                out.append(float(part))
            except ValueError:
                pass
    return out


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_FLOW_REGIMES = {
    "Subcritical Flow": "Subcritical",
    "Supercritical Flow": "Supercritical",
    "Mixed Flow": "Mixed",
    "Mixed Flow Regime": "Mixed",
}


def parse_plan(filepath: str | Path) -> PlanFile:
    """Parse a HEC-RAS plan file and return structured data.

    Args:
        filepath: Path to a ``.p01`` … ``.p99`` file.

    Returns:
        A :class:`PlanFile` with simulation type, computational settings,
        encroachment/floodway parameters, and output intervals.
        Missing keywords are left at their dataclass defaults.
    """
    filepath = Path(filepath)
    text = filepath.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    plan = PlanFile()
    comp = plan.computation
    enc = plan.encroachment
    out = plan.output

    for raw_line in lines:
        stripped = raw_line.strip()

        # ---- bare keywords (no '=') ------------------------------------
        if stripped in _FLOW_REGIMES:
            plan.flow_regime = _FLOW_REGIMES[stripped]
            continue

        if "=" not in stripped:
            continue

        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()

        # ---- metadata --------------------------------------------------
        if key == "Plan Title":
            plan.title = value
        elif key == "Program Version":
            plan.program_version = value
        elif key == "Short Identifier":
            plan.short_identifier = value
        elif key == "Simulation Date":
            plan.simulation_date = value
        elif key == "Geom File":
            plan.geom_file = value
        elif key == "Flow File":
            plan.flow_file = value
        elif key == "Plan Type":
            plan.plan_type = _int(value)
        elif key == "Profiles":
            pass  # just a count; names are on the next keyword
        elif key == "Profile Names":
            plan.profiles = [p.strip() for p in value.split(",") if p.strip()]
        elif key == "Paused":
            plan.paused = _flag(value)

        # ---- computational settings ------------------------------------
        elif key == "Flow Tolerance":
            comp.flow_tolerance = _float(value, 0.01)
        elif key == "Wl Tolerance":
            comp.ws_tolerance = _float(value, 0.01)
        elif key == "Critical Always Calculated":
            comp.critical_always = _flag(value)
        elif key == "Friction Slope Method":
            comp.friction_slope_method = _int(value, 1)
        elif key == "Flow Ratio":
            comp.flow_ratio = _float(value, 0.01)
        elif key == "Split Flow Opt":
            comp.split_flow = _flag(value)
        elif key == "Warm Up":
            comp.warm_up = _flag(value)
        elif key == "Computation Interval":
            comp.computation_interval = value
        elif key == "Flow Tolerance Method":
            comp.flow_tolerance_method = _int(value)
        elif key == "Check Data":
            comp.check_data = _flag(value)

        # ---- encroachment / floodway -----------------------------------
        elif key == "Encroach Param":
            vals = _comma_floats(value)
            if vals and vals[0] != 0:
                enc.enabled = True
        elif key == "Encroach Method":
            enc.method = _int(value)
        elif key == "Encroach Val 1":
            _set_enc_val(enc, 0, value)
        elif key == "Encroach Val 2":
            _set_enc_val(enc, 1, value)
        elif key == "Encroach Val 3":
            _set_enc_val(enc, 2, value)
        elif key == "Encroach Val 4":
            _set_enc_val(enc, 3, value)

        # ---- output / run flags ----------------------------------------
        elif key == "Run HTab":
            out.run_htab = _flag(value)
        elif key == "Run Post Process":
            out.run_post_process = _flag(value)
        elif key == "Run Sed":
            out.run_sediment = _flag(value)
        elif key == "Run UNET":
            out.run_unet = _flag(value)
        elif key == "Run RAS Mapper":
            out.run_ras_mapper = _flag(value)
        elif key == "Write IC File":
            out.write_ic_file = _flag(value)
        elif key == "Write Detailed":
            out.write_detailed = _flag(value)
        elif key == "Echo Input":
            out.echo_input = _flag(value)
        elif key == "Echo Parameters":
            out.echo_parameters = _flag(value)
        elif key == "Echo Output":
            out.echo_output = _flag(value)
        elif key == "Log Output Level":
            out.log_output_level = _int(value)
        elif key == "Output Interval":
            out.output_interval = value
        elif key == "Mapping Interval":
            out.mapping_interval = value
        elif key == "Hydrograph Output Interval":
            out.hydrograph_output_interval = value
        elif key == "Detailed Output Interval":
            out.detailed_output_interval = value
        elif key == "Instantaneous Interval":
            out.instantaneous_interval = value

    return plan


def _set_enc_val(enc: EncroachmentSettings, index: int, raw: str) -> None:
    """Set one of the four encroachment value slots, growing the list if needed."""
    v = _float(raw)
    while len(enc.values) <= index:
        enc.values.append(0.0)
    enc.values[index] = v
