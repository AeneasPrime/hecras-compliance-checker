"""Generate a Markdown compliance report from rule evaluation results."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from hecras_compliance.rules.engine import RuleResult

# ---------------------------------------------------------------------------
# Category mapping — group rules by rule-ID prefix
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
    """Map a rule ID like ``FEMA-MANN-001`` to a display category."""
    parts = rule_id.split("-")
    for part in parts:
        if part in _PREFIX_TO_CATEGORY:
            return _PREFIX_TO_CATEGORY[part]
    return "Other"


_STATUS_ICON = {
    "PASS": "PASS",
    "FAIL": "FAIL",
    "WARNING": "WARN",
    "SKIPPED": "SKIP",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_markdown_report(
    results: list[RuleResult],
    *,
    model_filename: str = "",
    state: str | None = None,
    output_path: str | Path | None = None,
) -> str:
    """Build a Markdown compliance report and optionally write it to disk.

    Args:
        results: List of :class:`RuleResult` from the engine.
        model_filename: Name of the HEC-RAS project file checked.
        state: State ruleset applied (e.g. ``"Texas"``), or ``None``.
        output_path: If provided, the report is written to this file.

    Returns:
        The full Markdown string.
    """
    lines: list[str] = []

    # ------------------------------------------------------------------
    # 1. Header
    # ------------------------------------------------------------------
    lines.append("# HEC-RAS Compliance Report")
    lines.append("")
    lines.append(f"| Field | Value |")
    lines.append(f"|:------|:------|")
    if model_filename:
        lines.append(f"| **Model** | `{model_filename}` |")
    lines.append(f"| **Date** | {date.today().isoformat()} |")
    lines.append(f"| **Federal Rules** | FEMA Guidelines & Specifications |")
    if state:
        lines.append(f"| **State Rules** | {state} |")
    else:
        lines.append(f"| **State Rules** | None |")
    lines.append("")

    # ------------------------------------------------------------------
    # 2. Executive summary
    # ------------------------------------------------------------------
    counts = Counter(r.status for r in results)
    total = len(results)
    n_pass = counts.get("PASS", 0)
    n_fail = counts.get("FAIL", 0)
    n_warn = counts.get("WARNING", 0)
    n_skip = counts.get("SKIPPED", 0)

    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"| Status | Count |")
    lines.append(f"|:-------|------:|")
    lines.append(f"| PASS | {n_pass} |")
    lines.append(f"| FAIL | {n_fail} |")
    lines.append(f"| WARNING | {n_warn} |")
    lines.append(f"| SKIPPED | {n_skip} |")
    lines.append(f"| **Total** | **{total}** |")
    lines.append("")

    if n_fail == 0 and n_warn == 0:
        lines.append("> All checks passed. No compliance issues detected.")
    elif n_fail == 0:
        lines.append(
            f"> No critical failures. {n_warn} warning(s) require review."
        )
    else:
        lines.append(
            f"> **{n_fail} critical failure(s)** must be resolved before submission."
        )
    lines.append("")

    # ------------------------------------------------------------------
    # 3. Critical failures
    # ------------------------------------------------------------------
    failures = [r for r in results if r.status == "FAIL"]
    if failures:
        lines.append("## Critical Failures")
        lines.append("")
        for r in failures:
            loc = f" at {r.location}" if r.location else ""
            lines.append(f"- **{r.rule_id}** — {r.rule_name}{loc}")
            lines.append(f"  - Model has: `{r.actual_value}`")
            lines.append(f"  - Required: `{r.expected_value}`")
            lines.append(f"  - {r.message}")
        lines.append("")

    # ------------------------------------------------------------------
    # 4. Detailed results grouped by category
    # ------------------------------------------------------------------
    grouped: dict[str, list[RuleResult]] = defaultdict(list)
    for r in results:
        grouped[_categorize(r.rule_id)].append(r)

    lines.append("## Detailed Results")
    lines.append("")

    for category in _CATEGORY_ORDER:
        cat_results = grouped.get(category)
        if not cat_results:
            continue

        lines.append(f"### {category}")
        lines.append("")
        lines.append("| Status | Rule | Location | Model Value | Required | Citation |")
        lines.append("|:-------|:-----|:---------|:------------|:---------|:---------|")

        for r in cat_results:
            status = _STATUS_ICON.get(r.status, r.status)
            loc = r.location or "—"
            actual = r.actual_value or "—"
            expected = r.expected_value or "—"
            citation = r.citation if len(r.citation) <= 60 else r.citation[:57] + "..."
            lines.append(
                f"| {status} | {r.rule_name} | {loc} | {actual} | {expected} | {citation} |"
            )

        lines.append("")

    # ------------------------------------------------------------------
    # 5. Recommendations
    # ------------------------------------------------------------------
    actionable = [r for r in results if r.status in ("FAIL", "WARNING")]
    if actionable:
        lines.append("## Recommendations")
        lines.append("")
        for r in actionable:
            tag = "FAIL" if r.status == "FAIL" else "WARN"
            loc = f" at {r.location}" if r.location else ""
            lines.append(f"### [{tag}] {r.rule_id} — {r.rule_name}{loc}")
            lines.append("")
            lines.append(f"**Issue:** {r.message}")
            lines.append("")
            lines.append(f"**Citation:** {r.citation}")
            lines.append("")
            if r.status == "FAIL":
                lines.append(
                    f"**Action:** Correct the value from `{r.actual_value}` "
                    f"to within the required range of `{r.expected_value}`. "
                    f"Re-run the model after making corrections."
                )
            else:
                lines.append(
                    f"**Action:** Review the value `{r.actual_value}` against "
                    f"the expected `{r.expected_value}`. Provide justification "
                    f"if the current value is intentional."
                )
            lines.append("")

    # ------------------------------------------------------------------
    # 6. Disclaimer
    # ------------------------------------------------------------------
    lines.append("---")
    lines.append("")
    lines.append(
        "*This report was generated by an automated compliance checking tool. "
        "All results must be reviewed and verified by a licensed Professional "
        "Engineer (PE). This tool does not replace engineering judgment and is "
        "not a substitute for a thorough review of the hydraulic model by a "
        "qualified professional.*"
    )
    lines.append("")

    report = "\n".join(lines)

    if output_path:
        Path(output_path).write_text(report, encoding="utf-8")

    return report
