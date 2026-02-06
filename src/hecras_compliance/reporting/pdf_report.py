"""Generate a formatted PDF compliance report using fpdf2."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from fpdf import FPDF

from hecras_compliance.rules.engine import RuleResult

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------

_COLORS = {
    "PASS": (34, 139, 34),      # forest green
    "FAIL": (200, 30, 30),      # red
    "WARNING": (200, 150, 0),   # dark yellow / amber
    "SKIPPED": (130, 130, 130), # gray
}

_HEADER_BG = (41, 65, 106)     # dark navy
_HEADER_FG = (255, 255, 255)   # white
_ROW_ALT = (240, 244, 248)     # light blue-gray for alternating rows
_WHITE = (255, 255, 255)

# ---------------------------------------------------------------------------
# Category mapping (shared with markdown_report)
# ---------------------------------------------------------------------------

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
    parts = rule_id.split("-")
    for part in parts:
        if part in _PREFIX_TO_CATEGORY:
            return _PREFIX_TO_CATEGORY[part]
    return "Other"


# ---------------------------------------------------------------------------
# PDF builder
# ---------------------------------------------------------------------------

class _CompliancePDF(FPDF):
    """Custom PDF class with header/footer branding."""

    def __init__(self, model_filename: str = "", state: str | None = None):
        super().__init__()
        self._model = model_filename
        self._state = state
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(100, 100, 100)
        self.cell(0, 6, "HEC-RAS Compliance Report", new_x="LMARGIN", new_y="NEXT")
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(140, 140, 140)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")


def _set_color(pdf: FPDF, rgb: tuple[int, int, int]) -> None:
    pdf.set_text_color(*rgb)


def _status_label(status: str) -> str:
    return {"PASS": "PASS", "FAIL": "FAIL", "WARNING": "WARN", "SKIPPED": "SKIP"}.get(
        status, status
    )


def _safe(text: str) -> str:
    """Replace characters that Helvetica (latin-1) cannot encode."""
    return (
        text
        .replace("\u2014", "--")   # em-dash
        .replace("\u2013", "-")    # en-dash
        .replace("\u2018", "'")    # left single quote
        .replace("\u2019", "'")    # right single quote
        .replace("\u201c", '"')    # left double quote
        .replace("\u201d", '"')    # right double quote
        .replace("\u2026", "...")  # ellipsis
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_pdf_report(
    results: list[RuleResult],
    *,
    model_filename: str = "",
    state: str | None = None,
    output_path: str | Path = "compliance_report.pdf",
) -> Path:
    """Build a formatted PDF compliance report.

    Args:
        results: List of :class:`RuleResult` from the engine.
        model_filename: Name of the HEC-RAS project file checked.
        state: State ruleset applied (e.g. ``"Texas"``), or ``None``.
        output_path: Where to write the PDF.

    Returns:
        The :class:`Path` to the written PDF.
    """
    output_path = Path(output_path)
    pdf = _CompliancePDF(model_filename, state)
    pdf.alias_nb_pages()
    pdf.add_page()

    # ------------------------------------------------------------------
    # 1. Title
    # ------------------------------------------------------------------
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 14, "HEC-RAS Compliance Report", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # Metadata table
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(60, 60, 60)
    meta = [
        ("Model", model_filename or "N/A"),
        ("Date", date.today().isoformat()),
        ("Federal Rules", "FEMA Guidelines & Specifications"),
        ("State Rules", state or "None"),
    ]
    for label, value in meta:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(35, 6, f"{label}:", new_x="RIGHT")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, _safe(value), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # ------------------------------------------------------------------
    # 2. Executive summary
    # ------------------------------------------------------------------
    counts = Counter(r.status for r in results)
    total = len(results)
    n_pass = counts.get("PASS", 0)
    n_fail = counts.get("FAIL", 0)
    n_warn = counts.get("WARNING", 0)
    n_skip = counts.get("SKIPPED", 0)

    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 10, "Executive Summary", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    # Summary boxes
    box_w = 42
    box_h = 18
    start_x = pdf.get_x()
    y = pdf.get_y()

    for label, count, color in [
        ("PASS", n_pass, _COLORS["PASS"]),
        ("FAIL", n_fail, _COLORS["FAIL"]),
        ("WARNING", n_warn, _COLORS["WARNING"]),
        ("SKIPPED", n_skip, _COLORS["SKIPPED"]),
    ]:
        pdf.set_fill_color(*color)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(start_x, y)
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(box_w, box_h, str(count), border=0, fill=True, align="C")
        # Label below
        pdf.set_xy(start_x, y + box_h)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*color)
        pdf.cell(box_w, 5, label, align="C")
        start_x += box_w + 4

    pdf.set_y(y + box_h + 10)

    # Summary sentence
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(60, 60, 60)
    if n_fail == 0 and n_warn == 0:
        pdf.multi_cell(0, 5, "All checks passed. No compliance issues detected.")
    elif n_fail == 0:
        pdf.multi_cell(0, 5, f"No critical failures. {n_warn} warning(s) require review.")
    else:
        pdf.set_text_color(*_COLORS["FAIL"])
        pdf.set_font("Helvetica", "B", 10)
        pdf.multi_cell(
            0, 5,
            f"{n_fail} critical failure(s) must be resolved before submission.",
        )
    pdf.ln(4)

    # ------------------------------------------------------------------
    # 3. Critical failures
    # ------------------------------------------------------------------
    failures = [r for r in results if r.status == "FAIL"]
    if failures:
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(200, 30, 30)
        pdf.cell(0, 10, "Critical Failures", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

        for r in failures:
            loc = f" at {r.location}" if r.location else ""
            pdf.set_x(10)
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*_COLORS["FAIL"])
            pdf.multi_cell(0, 5, _safe(f"{r.rule_id} - {r.rule_name}{loc}"))
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(60, 60, 60)
            pdf.set_x(10)
            pdf.multi_cell(0, 4.5, _safe(f"  Model has: {r.actual_value}"))
            pdf.set_x(10)
            pdf.multi_cell(0, 4.5, _safe(f"  Required:  {r.expected_value}"))
            pdf.set_x(10)
            pdf.multi_cell(0, 4.5, _safe(f"  {r.message}"))
            pdf.ln(2)

        pdf.ln(2)

    # ------------------------------------------------------------------
    # 4. Detailed results by category
    # ------------------------------------------------------------------
    grouped: dict[str, list[RuleResult]] = defaultdict(list)
    for r in results:
        grouped[_categorize(r.rule_id)].append(r)

    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 10, "Detailed Results", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    col_widths = [14, 38, 18, 28, 28, 64]  # status, rule, loc, actual, expected, citation

    for category in _CATEGORY_ORDER:
        cat_results = grouped.get(category)
        if not cat_results:
            continue

        # Category heading
        pdf.set_x(10)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*_HEADER_BG)
        pdf.cell(0, 8, category, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

        # Table header
        pdf.set_x(10)
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_fill_color(*_HEADER_BG)
        pdf.set_text_color(*_HEADER_FG)
        headers = ["Status", "Rule", "Location", "Model Value", "Required", "Citation"]
        for i, h in enumerate(headers):
            pdf.cell(col_widths[i], 6, h, border=0, fill=True, align="C")
        pdf.ln()

        # Rows
        pdf.set_font("Helvetica", "", 7)
        for row_idx, r in enumerate(cat_results):
            bg = _ROW_ALT if row_idx % 2 == 1 else _WHITE
            pdf.set_fill_color(*bg)

            pdf.set_x(10)
            # Status cell — colored
            color = _COLORS.get(r.status, (60, 60, 60))
            pdf.set_text_color(*color)
            pdf.set_font("Helvetica", "B", 7)
            pdf.cell(col_widths[0], 5, _status_label(r.status), border=0, fill=True, align="C")

            # Remaining cells — dark text
            pdf.set_text_color(40, 40, 40)
            pdf.set_font("Helvetica", "", 7)

            rule_name = _safe(r.rule_name[:20] + ".." if len(r.rule_name) > 22 else r.rule_name)
            loc = _safe(r.location) if r.location else "-"
            actual = _safe((r.actual_value[:14] + "..") if len(r.actual_value) > 16 else r.actual_value) or "-"
            expected = _safe((r.expected_value[:14] + "..") if len(r.expected_value) > 16 else r.expected_value) or "-"
            citation = _safe((r.citation[:38] + "..") if len(r.citation) > 40 else r.citation) or "-"

            pdf.cell(col_widths[1], 5, rule_name, border=0, fill=True)
            pdf.cell(col_widths[2], 5, loc, border=0, fill=True, align="C")
            pdf.cell(col_widths[3], 5, actual, border=0, fill=True, align="C")
            pdf.cell(col_widths[4], 5, expected, border=0, fill=True, align="C")
            pdf.cell(col_widths[5], 5, citation, border=0, fill=True)
            pdf.ln()

        pdf.ln(4)

    # ------------------------------------------------------------------
    # 5. Recommendations
    # ------------------------------------------------------------------
    actionable = [r for r in results if r.status in ("FAIL", "WARNING")]
    if actionable:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(0, 10, "Recommendations", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        for r in actionable:
            color = _COLORS.get(r.status, (60, 60, 60))
            tag = "FAIL" if r.status == "FAIL" else "WARN"
            loc = f" at {r.location}" if r.location else ""

            pdf.set_x(10)
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*color)
            pdf.multi_cell(0, 5, _safe(f"[{tag}] {r.rule_id} - {r.rule_name}{loc}"))

            pdf.set_x(10)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(60, 60, 60)
            pdf.multi_cell(0, 4.5, _safe(f"Issue: {r.message}"))
            pdf.ln(1)

            pdf.set_x(10)
            pdf.set_font("Helvetica", "I", 8)
            pdf.set_text_color(100, 100, 100)
            pdf.multi_cell(0, 4, _safe(f"Citation: {r.citation}"))
            pdf.ln(1)

            pdf.set_x(10)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(60, 60, 60)
            if r.status == "FAIL":
                pdf.multi_cell(
                    0, 4.5,
                    _safe(
                        f"Action: Correct the value from {r.actual_value} to within "
                        f"the required range of {r.expected_value}. Re-run the model "
                        f"after making corrections."
                    ),
                )
            else:
                pdf.multi_cell(
                    0, 4.5,
                    _safe(
                        f"Action: Review the value {r.actual_value} against the expected "
                        f"{r.expected_value}. Provide justification if the current "
                        f"value is intentional."
                    ),
                )
            pdf.ln(4)

    # ------------------------------------------------------------------
    # 6. Disclaimer
    # ------------------------------------------------------------------
    pdf.ln(6)
    pdf.set_draw_color(180, 180, 180)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.multi_cell(
        0, 4,
        "This report was generated by an automated compliance checking tool. "
        "All results must be reviewed and verified by a licensed Professional "
        "Engineer (PE). This tool does not replace engineering judgment and is "
        "not a substitute for a thorough review of the hydraulic model by a "
        "qualified professional.",
    )

    pdf.output(str(output_path))
    return output_path
