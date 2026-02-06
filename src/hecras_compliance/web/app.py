"""Flask web application for the HEC-RAS compliance checker."""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import yaml
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from hecras_compliance.parsers import parse_geometry, parse_plan, parse_flow, parse_project
from hecras_compliance.reporting.pdf_report import generate_pdf_report
from hecras_compliance.rules.engine import ComplianceEngine, ModelData, RuleResult

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
_STATES_DIR = _CONFIG_DIR / "states"
_PDF_DIR = Path(tempfile.gettempdir()) / "hecras_pdfs"
_PDF_DIR.mkdir(exist_ok=True)

# Category grouping (shared with reporting modules)
_CATEGORY_ORDER = [
    "Manning's n",
    "Expansion / Contraction Coefficients",
    "Floodway / Surcharge",
    "Required Flood Events",
    "Bridge / Culvert",
    "Boundary Conditions",
    "Freeboard",
    "Other",
]

_PREFIX_TO_CATEGORY: dict[str, str] = {
    "MANN": "Manning's n",
    "COEF": "Expansion / Contraction Coefficients",
    "FW": "Floodway / Surcharge",
    "EVENT": "Required Flood Events",
    "BRG": "Bridge / Culvert",
    "BC": "Boundary Conditions",
    "FB": "Freeboard",
}


def _categorize(rule_id: str) -> str:
    for part in rule_id.split("-"):
        if part in _PREFIX_TO_CATEGORY:
            return _PREFIX_TO_CATEGORY[part]
    return "Other"


# ---------------------------------------------------------------------------
# State discovery
# ---------------------------------------------------------------------------

def _available_states() -> list[dict[str, str]]:
    """Discover state rule files from config/states/."""
    states: list[dict[str, str]] = []
    for f in sorted(_STATES_DIR.glob("*.yaml")):
        if f.stem.startswith("_"):
            continue
        data = yaml.safe_load(f.read_text())
        states.append({
            "key": f.stem,
            "name": data.get("state", f.stem.title()),
        })
    return states


# ---------------------------------------------------------------------------
# Model loading (same logic as CLI)
# ---------------------------------------------------------------------------

def _load_model_from_dir(upload_dir: Path) -> tuple[ModelData, str]:
    """Find the .prj in upload_dir, parse it and all referenced files."""
    prj_files = list(upload_dir.glob("*.prj"))
    if not prj_files:
        raise FileNotFoundError("No .prj file found among uploaded files.")

    prj_path = prj_files[0]
    project = parse_project(prj_path)
    stem = prj_path.stem

    geometry = None
    plan = None
    flow = None

    for ext in project.geom_files:
        gpath = upload_dir / f"{stem}.{ext}"
        if gpath.exists():
            geometry = parse_geometry(gpath)
            break

    plan_exts: list[str] = []
    if project.current_plan:
        plan_exts.append(project.current_plan)
    plan_exts.extend(project.plan_files)
    for ext in plan_exts:
        ppath = upload_dir / f"{stem}.{ext}"
        if ppath.exists():
            plan = parse_plan(ppath)
            break

    for ext in project.all_flow_files:
        fpath = upload_dir / f"{stem}.{ext}"
        if fpath.exists():
            flow = parse_flow(fpath)
            break

    model = ModelData(geometry=geometry, plan=plan, flow=flow, project=project)
    return model, prj_path.name


# ---------------------------------------------------------------------------
# Flask app factory
# ---------------------------------------------------------------------------

def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "hecras-compliance-checker-dev")

    @app.after_request
    def _no_cache(response):
        if response.content_type != "application/pdf":
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response

    @app.route("/")
    def index():
        states = _available_states()
        return render_template("index.html", states=states)

    @app.route("/review", methods=["POST"])
    def review():
        state_key = request.form.get("state", "")
        if not state_key:
            state_key = None

        files = request.files.getlist("files")
        if not files or all(f.filename == "" for f in files):
            flash("Please upload at least one file.", "error")
            return redirect(url_for("index"))

        # Save uploads to temp dir
        upload_dir = Path(tempfile.mkdtemp(prefix="hecras_"))
        try:
            for f in files:
                if f.filename:
                    dest = upload_dir / f.filename
                    f.save(str(dest))

            # Parse model
            try:
                model, model_name = _load_model_from_dir(upload_dir)
            except FileNotFoundError:
                flash("No .prj file found. Please include your project file.", "error")
                return redirect(url_for("index"))

            # Evaluate
            engine = ComplianceEngine(state=state_key or None)
            results = engine.evaluate(model)

            # Counts
            counts = Counter(r.status for r in results)
            n_pass = counts.get("PASS", 0)
            n_fail = counts.get("FAIL", 0)
            n_warn = counts.get("WARNING", 0)
            n_skip = counts.get("SKIPPED", 0)
            total = len(results)

            # Group by category
            grouped: dict[str, list[RuleResult]] = defaultdict(list)
            for r in results:
                grouped[_categorize(r.rule_id)].append(r)

            categories = [
                (cat, grouped[cat])
                for cat in _CATEGORY_ORDER
                if cat in grouped
            ]

            failures = [r for r in results if r.status == "FAIL"]
            actionable = [r for r in results if r.status in ("FAIL", "WARNING")]

            # State display name
            state_label = None
            if state_key:
                for s in _available_states():
                    if s["key"] == state_key:
                        state_label = s["name"]
                        break
                if not state_label:
                    state_label = state_key.title()

            # Generate PDF to a persistent location
            session_id = uuid.uuid4().hex[:12]
            pdf_path = _PDF_DIR / f"{session_id}.pdf"
            generate_pdf_report(
                results,
                model_filename=model_name,
                state=state_label,
                output_path=pdf_path,
            )

            return render_template(
                "report.html",
                model_name=model_name,
                state_label=state_label,
                today=date.today().isoformat(),
                n_pass=n_pass,
                n_fail=n_fail,
                n_warn=n_warn,
                n_skip=n_skip,
                total=total,
                failures=failures,
                categories=categories,
                actionable=actionable,
                results=results,
                session_id=session_id,
            )
        finally:
            shutil.rmtree(upload_dir, ignore_errors=True)

    @app.route("/download-pdf/<session_id>")
    def download_pdf(session_id: str):
        pdf_path = _PDF_DIR / f"{session_id}.pdf"
        if pdf_path.exists():
            return send_file(
                str(pdf_path),
                mimetype="application/pdf",
                as_attachment=True,
                download_name="compliance_report.pdf",
            )
        flash("PDF not found. Please run a new review.", "error")
        return redirect(url_for("index"))

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

# Module-level app instance for gunicorn (gunicorn hecras_compliance.web.app:app)
app = create_app()


def run_web():
    """Entry point for the ``hecras-web`` console script."""
    app.run(debug=True, port=5000)
