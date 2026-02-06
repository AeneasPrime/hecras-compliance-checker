"""Parser for HEC-RAS project files (.prj).

The project file is the top-level manifest that references all geometry,
plan, and flow files belonging to a study.  It also stores the active
plan, unit system, default coefficients, and a free-text description.
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
class ProjectFile:
    """Parsed contents of a HEC-RAS project (.prj) file."""

    title: str = ""
    description: str = ""
    units: str = ""  # "English" or "SI Metric"

    current_plan: str = ""

    # File references (bare extensions like "g01", "f01", "p01")
    geom_files: list[str] = field(default_factory=list)
    steady_files: list[str] = field(default_factory=list)
    unsteady_files: list[str] = field(default_factory=list)
    quasi_files: list[str] = field(default_factory=list)
    plan_files: list[str] = field(default_factory=list)

    # Default expansion / contraction coefficients
    default_expansion: float = 0.3
    default_contraction: float = 0.1

    @property
    def all_flow_files(self) -> list[str]:
        """All flow file references (steady + unsteady + quasi)."""
        return self.steady_files + self.unsteady_files + self.quasi_files

    @property
    def is_english(self) -> bool:
        return self.units.lower().startswith("english") if self.units else False

    @property
    def is_metric(self) -> bool:
        return "metric" in self.units.lower() if self.units else False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _float(raw: str, default: float = 0.0) -> float:
    raw = raw.strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse_project(filepath: str | Path) -> ProjectFile:
    """Parse a HEC-RAS project file.

    Args:
        filepath: Path to the ``.prj`` file.

    Returns:
        A :class:`ProjectFile` with file references, units, description,
        and default coefficients populated.
    """
    filepath = Path(filepath)
    text = filepath.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    prj = ProjectFile()

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        # ---- bare keywords (no '=') --------------------------------------
        if stripped == "English Units":
            prj.units = "English"
            i += 1
            continue
        if stripped in ("SI Units", "SI Metric"):
            prj.units = "SI Metric"
            i += 1
            continue

        # ---- description block --------------------------------------------
        if stripped == "BEGIN DESCRIPTION:":
            desc_lines: list[str] = []
            i += 1
            while i < len(lines) and lines[i].strip() != "END DESCRIPTION:":
                desc_lines.append(lines[i].rstrip())
                i += 1
            prj.description = "\n".join(desc_lines)
            i += 1  # skip END DESCRIPTION:
            continue

        # ---- keyword=value lines ------------------------------------------
        if "=" not in stripped:
            i += 1
            continue

        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()

        if key == "Proj Title":
            prj.title = value
        elif key == "Current Plan":
            prj.current_plan = value
        elif key == "Geom File":
            if value:
                prj.geom_files.append(value)
        elif key == "Steady File":
            if value:
                prj.steady_files.append(value)
        elif key == "Unsteady File":
            if value:
                prj.unsteady_files.append(value)
        elif key == "QuasiSteady File":
            if value:
                prj.quasi_files.append(value)
        elif key == "Plan File":
            if value:
                prj.plan_files.append(value)
        elif key == "Default Exp/Contr":
            parts = value.split(",")
            if len(parts) >= 2:
                prj.default_expansion = _float(parts[0], 0.3)
                prj.default_contraction = _float(parts[1], 0.1)

        i += 1

    return prj
