"""Command-line interface for the HEC-RAS compliance checker.

Provides the ``hecras-check`` entry point with four commands:

- ``run``        – Full compliance check with report generation
- ``list-rules`` – Display all applicable rules
- ``summary``    – Quick model overview without compliance check
- ``add-state``  – Interactive wizard for creating a new state YAML file
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import click
import yaml

from hecras_compliance.parsers import parse_geometry, parse_plan, parse_flow, parse_project
from hecras_compliance.reporting.markdown_report import generate_markdown_report
from hecras_compliance.reporting.pdf_report import generate_pdf_report
from hecras_compliance.rules.engine import ComplianceEngine, ModelData, RuleResult, load_rules

# ---------------------------------------------------------------------------
# Symbols & colors
# ---------------------------------------------------------------------------

_PASS = click.style("\u2713 PASS", fg="green", bold=True)
_FAIL = click.style("\u2717 FAIL", fg="red", bold=True)
_WARN = click.style("\u26A0 WARN", fg="yellow", bold=True)
_SKIP = click.style("- SKIP", fg="white", dim=True)
_INFO = click.style("i INFO", fg="cyan")


def _status_styled(status: str) -> str:
    return {
        "PASS": _PASS,
        "FAIL": _FAIL,
        "WARNING": _WARN,
        "SKIPPED": _SKIP,
    }.get(status, status)


def _severity_styled(severity: str) -> str:
    return {
        "error": click.style("error", fg="red"),
        "warning": click.style("warning", fg="yellow"),
        "info": click.style("info", fg="cyan"),
    }.get(severity, severity)


# ---------------------------------------------------------------------------
# State abbreviation → full state name mapping
# ---------------------------------------------------------------------------

_STATE_ABBREVS: dict[str, str] = {
    "TX": "texas",
    "TEXAS": "texas",
    "ME": "maine",
    "MAINE": "maine",
}

_STATES_DIR = Path(__file__).resolve().parent / "config" / "states"


def _resolve_state(state: str | None) -> str | None:
    """Normalize a state argument to the lowercase name used for file lookup."""
    if state is None:
        return None
    upper = state.upper()
    if upper in _STATE_ABBREVS:
        return _STATE_ABBREVS[upper]
    return state.lower()


def _state_display_name(state_key: str | None) -> str | None:
    """Get a human-friendly state name by reading the YAML file's 'state' field."""
    if state_key is None:
        return None
    yaml_path = _STATES_DIR / f"{state_key}.yaml"
    if yaml_path.exists():
        data = yaml.safe_load(yaml_path.read_text())
        return data.get("state", state_key.title())
    return state_key.title()


# ---------------------------------------------------------------------------
# Helper: parse model from .prj
# ---------------------------------------------------------------------------

def _load_model(prj_path: Path) -> tuple[ModelData, str]:
    """Parse a .prj file and all referenced files, return (ModelData, basename)."""
    project = parse_project(prj_path)
    base_dir = prj_path.parent
    stem = prj_path.stem

    geometry = None
    plan = None
    flow = None

    # Geometry — use the first available file
    for ext in project.geom_files:
        gpath = base_dir / f"{stem}.{ext}"
        if gpath.exists():
            geometry = parse_geometry(gpath)
            break

    # Plan — use current plan, else first available
    plan_exts = []
    if project.current_plan:
        plan_exts.append(project.current_plan)
    plan_exts.extend(project.plan_files)
    for ext in plan_exts:
        ppath = base_dir / f"{stem}.{ext}"
        if ppath.exists():
            plan = parse_plan(ppath)
            break

    # Flow — prefer steady, then unsteady
    for ext in project.all_flow_files:
        fpath = base_dir / f"{stem}.{ext}"
        if fpath.exists():
            flow = parse_flow(fpath)
            break

    model = ModelData(geometry=geometry, plan=plan, flow=flow, project=project)
    return model, prj_path.name


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(version="0.1.0", prog_name="hecras-check")
def cli():
    """HEC-RAS Compliance Checker — validate hydraulic models against
    federal and state regulatory rules."""


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("project_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--state", "-s", default=None, help="State abbreviation or name (e.g. TX, texas).")
@click.option("--output", "-o", default=None, help="Path for Markdown report output.")
@click.option("--pdf", is_flag=True, help="Also generate a PDF report.")
def run(project_file: str, state: str | None, output: str | None, pdf: bool):
    """Run compliance checks on a HEC-RAS model.

    PROJECT_FILE is the path to a .prj project file.
    """
    prj_path = Path(project_file)
    state_key = _resolve_state(state)
    state_label = _state_display_name(state_key)

    click.echo()
    click.secho("HEC-RAS Compliance Checker", bold=True)
    click.secho("=" * 40, dim=True)
    click.echo(f"  Model:  {prj_path.name}")
    click.echo(f"  State:  {state_label or 'Federal only'}")
    click.echo()

    # Parse
    click.echo("Parsing model files...")
    model, model_name = _load_model(prj_path)

    parsed = []
    if model.geometry:
        parsed.append(f"geometry ({len(model.geometry.cross_sections)} XS, {len(model.geometry.bridges)} bridges)")
    if model.plan:
        parsed.append(f"plan (type {model.plan.plan_type})")
    if model.flow:
        n_profiles = len(model.flow.profiles) if model.flow.profiles else 0
        parsed.append(f"flow ({n_profiles} profiles)")
    for p in parsed:
        click.echo(f"  {click.style('\u2713', fg='green')} {p}")
    click.echo()

    # Evaluate
    click.echo("Running compliance checks...")
    engine = ComplianceEngine(state=state_key)
    results = engine.evaluate(model)

    n_pass = sum(1 for r in results if r.status == "PASS")
    n_fail = sum(1 for r in results if r.status == "FAIL")
    n_warn = sum(1 for r in results if r.status == "WARNING")
    n_skip = sum(1 for r in results if r.status == "SKIPPED")

    click.echo()
    click.secho("Results", bold=True)
    click.secho("-" * 40, dim=True)

    # Print each result
    for r in results:
        loc = f" @ {r.location}" if r.location else ""
        click.echo(f"  {_status_styled(r.status)}  {r.rule_name}{loc}")

    # Summary
    click.echo()
    click.secho("Summary", bold=True)
    click.secho("-" * 40, dim=True)
    click.echo(f"  {click.style(str(n_pass), fg='green', bold=True)} passed   "
               f"{click.style(str(n_fail), fg='red', bold=True)} failed   "
               f"{click.style(str(n_warn), fg='yellow', bold=True)} warnings   "
               f"{click.style(str(n_skip), dim=True)} skipped")

    if n_fail > 0:
        click.echo()
        click.secho(f"  {n_fail} critical failure(s) must be resolved before submission.", fg="red", bold=True)
        click.echo()
        for r in results:
            if r.status == "FAIL":
                loc = f" at {r.location}" if r.location else ""
                click.echo(f"  {click.style('\u2717', fg='red')} {r.rule_id} — {r.rule_name}{loc}")
                click.echo(f"    Model has: {r.actual_value}")
                click.echo(f"    Required:  {r.expected_value}")
                click.echo(f"    {r.message}")
                click.echo()

    # Reports
    if output or pdf:
        click.echo()
        click.secho("Reports", bold=True)
        click.secho("-" * 40, dim=True)

    if output:
        md_path = Path(output)
        generate_markdown_report(
            results, model_filename=model_name,
            state=state_label, output_path=md_path,
        )
        click.echo(f"  {click.style('\u2713', fg='green')} Markdown: {md_path}")

    if pdf:
        pdf_path = Path(output).with_suffix(".pdf") if output else Path("compliance_report.pdf")
        generate_pdf_report(
            results, model_filename=model_name,
            state=state_label, output_path=pdf_path,
        )
        click.echo(f"  {click.style('\u2713', fg='green')} PDF:      {pdf_path}")

    click.echo()


# ---------------------------------------------------------------------------
# list-rules
# ---------------------------------------------------------------------------

@cli.command("list-rules")
@click.option("--state", "-s", default=None, help="State abbreviation or name (e.g. TX, texas).")
def list_rules(state: str | None):
    """List all applicable compliance rules.

    Shows federal FEMA rules and any state-specific rules. State rules may
    supersede federal rules.
    """
    state_key = _resolve_state(state)
    state_label = _state_display_name(state_key)

    rules = load_rules(state=state_key)

    click.echo()
    click.secho("Applicable Compliance Rules", bold=True)
    if state_label:
        click.echo(f"  Federal (FEMA) + {state_label}")
    else:
        click.echo("  Federal (FEMA) only")
    click.secho("=" * 60, dim=True)
    click.echo()

    # Determine column widths
    id_w = max(len(r["id"]) for r in rules) if rules else 12
    name_w = max(len(r["name"]) for r in rules) if rules else 20
    # Cap name width for readability
    term_w = shutil.get_terminal_size((80, 24)).columns
    name_w = min(name_w, term_w - id_w - 20)

    for rule in rules:
        rid = rule["id"]
        name = rule["name"]
        severity = rule.get("severity", "")

        # Color the rule ID by origin
        if rid.startswith("FEMA"):
            id_str = click.style(rid.ljust(id_w), fg="blue", bold=True)
        else:
            id_str = click.style(rid.ljust(id_w), fg="magenta", bold=True)

        sev_str = _severity_styled(severity)
        click.echo(f"  {id_str}  {name.ljust(name_w)}  [{sev_str}]")

    click.echo()
    click.echo(f"  {len(rules)} rules total")
    click.echo()


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("project_file", type=click.Path(exists=True, dir_okay=False))
def summary(project_file: str):
    """Show a quick summary of a HEC-RAS model (no compliance check).

    PROJECT_FILE is the path to a .prj project file.
    """
    prj_path = Path(project_file)
    model, model_name = _load_model(prj_path)

    click.echo()
    click.secho("Model Summary", bold=True)
    click.secho("=" * 50, dim=True)
    click.echo(f"  File:   {model_name}")

    # Project info
    if model.project:
        p = model.project
        click.echo(f"  Title:  {p.title or 'N/A'}")
        click.echo(f"  Units:  {p.units or 'N/A'}")
        if p.description:
            desc = p.description.strip().replace("\n", " ")
            if len(desc) > 70:
                desc = desc[:67] + "..."
            click.echo(f"  Desc:   {desc}")
        click.echo()

        click.secho("  Referenced Files", bold=True)
        click.secho("  " + "-" * 30, dim=True)
        for ext in p.geom_files:
            click.echo(f"    Geometry:  {prj_path.stem}.{ext}")
        for ext in p.plan_files:
            click.echo(f"    Plan:      {prj_path.stem}.{ext}")
        for ext in p.steady_files:
            click.echo(f"    Flow (S):  {prj_path.stem}.{ext}")
        for ext in p.unsteady_files:
            click.echo(f"    Flow (U):  {prj_path.stem}.{ext}")

    # Geometry
    if model.geometry:
        g = model.geometry
        click.echo()
        click.secho("  Geometry", bold=True)
        click.secho("  " + "-" * 30, dim=True)
        click.echo(f"    Cross sections:  {len(g.cross_sections)}")
        click.echo(f"    Bridges:         {len(g.bridges)}")

        if g.cross_sections:
            stations = [xs.river_station for xs in g.cross_sections]
            click.echo(f"    Station range:   {min(stations):.1f} – {max(stations):.1f}")

            n_vals = [xs.manning_n_channel for xs in g.cross_sections if xs.manning_n_channel is not None]
            if n_vals:
                click.echo(f"    Channel n range: {min(n_vals):.3f} – {max(n_vals):.3f}")

    # Plan
    if model.plan:
        pl = model.plan
        click.echo()
        click.secho("  Plan", bold=True)
        click.secho("  " + "-" * 30, dim=True)
        ptype = {1: "Steady", 2: "Unsteady", 3: "Quasi-Unsteady"}.get(pl.plan_type, str(pl.plan_type))
        click.echo(f"    Type:        {ptype}")
        if pl.flow_regime:
            click.echo(f"    Flow regime: {pl.flow_regime}")
        if pl.encroachment:
            enc = pl.encroachment
            click.echo(f"    Encroachment enabled: {'Yes' if enc.enabled else 'No'}")
            if enc.enabled:
                click.echo(f"    Encroachment method:  {enc.method}")
                if enc.target_surcharge is not None:
                    click.echo(f"    Target surcharge:     {enc.target_surcharge} ft")

    # Flow
    if model.flow:
        f = model.flow
        click.echo()
        click.secho("  Flow", bold=True)
        click.secho("  " + "-" * 30, dim=True)
        flow_type = "Steady" if f.is_steady else "Unsteady"
        click.echo(f"    Type:     {flow_type}")
        if f.profiles:
            names = [p.name for p in f.profiles]
            click.echo(f"    Profiles: {', '.join(names)}")
        n_bc = len(f.steady_boundaries) + len(f.unsteady_boundaries)
        click.echo(f"    Boundary conditions: {n_bc}")

    click.echo()


# ---------------------------------------------------------------------------
# add-state
# ---------------------------------------------------------------------------

@cli.command("add-state")
def add_state():
    """Interactive wizard to create a new state YAML rules file.

    Walks you through creating a state-specific rules file based on
    the built-in template.
    """
    click.echo()
    click.secho("Add New State Rules", bold=True)
    click.secho("=" * 40, dim=True)
    click.echo()

    # Collect state info
    state_name = click.prompt("  State name (e.g. Florida)")
    state_abbrev = click.prompt("  State abbreviation (e.g. FL)")

    # Check if file already exists
    filename = state_name.lower().replace(" ", "_") + ".yaml"
    target_path = _STATES_DIR / filename

    if target_path.exists():
        click.echo()
        click.secho(f"  File already exists: {target_path}", fg="yellow")
        if not click.confirm("  Overwrite?", default=False):
            click.echo("  Aborted.")
            return

    # Supersedes
    click.echo()
    click.echo("  Does this state override any federal (FEMA) rules?")
    click.echo("  Common example: zero-rise floodway supersedes FEMA-FW-001")
    supersedes: list[str] = []
    if click.confirm("  Override any federal rules?", default=False):
        sup_input = click.prompt(
            "  Enter rule IDs to supersede (comma-separated)",
            default="FEMA-FW-001",
        )
        supersedes = [s.strip() for s in sup_input.split(",") if s.strip()]

    # Build YAML content
    click.echo()
    click.echo("  Building state rules file...")

    data = {
        "state": state_name,
        "state_abbreviation": state_abbrev.upper(),
        "supersedes": supersedes,
        "rules": [],
    }

    # Ask about common rule types
    click.echo()
    click.secho("  Optional: Add common rules now?", bold=True)
    click.echo("  You can always edit the YAML file later to add more rules.")
    click.echo()

    # Zero-rise floodway
    if click.confirm("  Add zero-rise floodway rule?", default=False):
        data["rules"].append({
            "id": f"{state_abbrev.upper()}-FW-001",
            "name": "Zero-rise floodway requirement",
            "description": f"{state_name} requires zero-rise in the regulatory floodway.",
            "severity": "error",
            "citation": f"{state_name} state regulations (update with specific citation)",
            "check_type": "range",
            "parameters": {"min": 0.0, "max": 0.0},
            "applies_to": "plan.encroachment.target_surcharge",
        })
        if "FEMA-FW-001" not in supersedes:
            supersedes.append("FEMA-FW-001")
            data["supersedes"] = supersedes
        click.echo(f"    {click.style('\u2713', fg='green')} Added {state_abbrev.upper()}-FW-001")

    # Required flood events
    if click.confirm("  Add required flood event rules?", default=False):
        events = [
            ("10yr", "10-percent annual chance"),
            ("50yr", "2-percent annual chance"),
            ("100yr", "1-percent annual chance"),
            ("500yr", "0.2-percent annual chance"),
        ]
        for idx, (event_name, event_desc) in enumerate(events, start=1):
            if click.confirm(f"    Require {event_desc} ({event_name}) event?", default=True):
                data["rules"].append({
                    "id": f"{state_abbrev.upper()}-EVENT-{idx:03d}",
                    "name": f"{event_desc} flood required",
                    "description": f"{state_name} requires analysis of the {event_desc} flood event.",
                    "severity": "error",
                    "citation": f"{state_name} state regulations (update with specific citation)",
                    "check_type": "custom",
                    "parameters": {
                        "handler": "check_profile_exists",
                        "accepted_names": [event_name, event_name.replace("yr", "-yr")],
                    },
                    "applies_to": "flow.profile_names",
                })
                click.echo(f"    {click.style('\u2713', fg='green')} Added {state_abbrev.upper()}-EVENT-{idx:03d}")

    # Freeboard manual review
    if click.confirm("  Add freeboard manual review flag?", default=False):
        data["rules"].append({
            "id": f"{state_abbrev.upper()}-FB-001",
            "name": "Freeboard requirement (manual review)",
            "description": f"{state_name} freeboard requirements vary by jurisdiction. Flagged for manual review.",
            "severity": "info",
            "citation": f"{state_name} state and local regulations (update with specific citation)",
            "check_type": "custom",
            "parameters": {
                "handler": "flag_for_manual_review",
                "review_note": f"Verify the applicable {state_name} local freeboard ordinance.",
            },
            "applies_to": "plan.encroachment.target_surcharge",
        })
        click.echo(f"    {click.style('\u2713', fg='green')} Added {state_abbrev.upper()}-FB-001")

    # Write file
    click.echo()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    header = (
        f"# {'=' * 77}\n"
        f"# {state_name} State Compliance Rules for HEC-RAS Models\n"
        f"# {'=' * 77}\n"
        f"#\n"
        f"# Generated by: hecras-check add-state\n"
        f"# Edit this file to add, modify, or remove rules.\n"
        f"# See _template.yaml for full documentation of all fields.\n"
        f"#\n\n"
    )

    yaml_str = yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
    target_path.write_text(header + yaml_str, encoding="utf-8")

    click.echo(f"  {click.style('\u2713', fg='green')} Created: {target_path}")
    click.echo()
    click.echo("  Next steps:")
    click.echo(f"    1. Edit {filename} to update citations and descriptions")
    click.echo(f"    2. Run: hecras-check list-rules --state {state_abbrev.upper()}")
    click.echo(f"    3. Test: hecras-check run model.prj --state {state_abbrev.upper()}")
    click.echo()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Entry point for the ``hecras-check`` console script."""
    cli()
