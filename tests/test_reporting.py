"""Tests for compliance report generation (Markdown and PDF)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hecras_compliance.parsers.geometry import (
    BankStations,
    Bridge,
    BridgeDeck,
    CrossSection,
    DeckPoint,
    GeometryFile,
    ManningRegion,
)
from hecras_compliance.parsers.plan import EncroachmentSettings, PlanFile
from hecras_compliance.parsers.flow import (
    FlowFile,
    FlowProfile,
    SteadyBoundaryCondition,
)
from hecras_compliance.rules.engine import ComplianceEngine, ModelData, RuleResult
from hecras_compliance.reporting.markdown_report import generate_markdown_report
from hecras_compliance.reporting.pdf_report import generate_pdf_report

FIXTURES = Path(__file__).parent / "fixtures"


# ===================================================================
# Helpers — reuse model builders from test_engine
# ===================================================================


def _xs(
    station: float,
    n_channel: float = 0.035,
    n_left: float = 0.06,
    n_right: float = 0.06,
    expansion: float = 0.3,
    contraction: float = 0.1,
) -> CrossSection:
    return CrossSection(
        river_station=station,
        river="Beargrass Creek",
        reach="Upper Reach",
        bank_stations=BankStations(left=100.0, right=300.0),
        manning_regions=[
            ManningRegion(n_value=n_left, start_station=0.0),
            ManningRegion(n_value=n_channel, start_station=100.0),
            ManningRegion(n_value=n_right, start_station=300.0),
        ],
        expansion=expansion,
        contraction=contraction,
    )


def _good_model() -> ModelData:
    return ModelData(
        geometry=GeometryFile(
            title="Test",
            cross_sections=[_xs(5000), _xs(4000), _xs(3000)],
            bridges=[Bridge(
                river_station=3500, river="Beargrass Creek", reach="Upper Reach",
                deck=BridgeDeck(width=40.0, points=[
                    DeckPoint(100.0, 460.0, 450.0),
                    DeckPoint(300.0, 460.0, 450.0),
                ]),
            )],
        ),
        plan=PlanFile(
            title="Test Plan", plan_type=1,
            encroachment=EncroachmentSettings(
                enabled=True, method=4, values=[1.0, 0.0, 0.0, 0.0],
            ),
        ),
        flow=FlowFile(
            title="Test Flow", is_steady=True,
            profiles=[FlowProfile(n) for n in ["10yr", "50yr", "100yr", "500yr"]],
            steady_boundaries=[
                SteadyBoundaryCondition("Beargrass Creek", "Upper Reach", i + 1, downstream_type=3)
                for i in range(4)
            ],
        ),
    )


def _failing_model() -> ModelData:
    """Model with deliberate failures for testing failure reporting."""
    return ModelData(
        geometry=GeometryFile(
            title="Bad Model",
            cross_sections=[
                _xs(5000, n_channel=0.001, expansion=0.0),  # bad n + bad expansion
                _xs(4000, n_channel=0.035),                  # good
            ],
        ),
        plan=PlanFile(
            title="Test Plan", plan_type=1,
            encroachment=EncroachmentSettings(
                enabled=True, method=4, values=[2.0, 0.0, 0.0, 0.0],
            ),
        ),
        flow=FlowFile(
            title="Test Flow", is_steady=True,
            profiles=[FlowProfile("50yr")],  # missing 100yr
            steady_boundaries=[
                SteadyBoundaryCondition("Beargrass Creek", "Upper Reach", 1, downstream_type=3),
            ],
        ),
    )


# ===================================================================
# Markdown report tests
# ===================================================================


class TestMarkdownReport:
    def test_returns_string(self):
        engine = ComplianceEngine()
        results = engine.evaluate(_good_model())
        md = generate_markdown_report(results)
        assert isinstance(md, str)
        assert len(md) > 100

    def test_has_title(self):
        results = ComplianceEngine().evaluate(_good_model())
        md = generate_markdown_report(results)
        assert "# HEC-RAS Compliance Report" in md

    def test_has_model_filename(self):
        results = ComplianceEngine().evaluate(_good_model())
        md = generate_markdown_report(results, model_filename="sample.prj")
        assert "sample.prj" in md

    def test_has_date(self):
        results = ComplianceEngine().evaluate(_good_model())
        md = generate_markdown_report(results)
        from datetime import date
        assert date.today().isoformat() in md

    def test_has_state_label(self):
        results = ComplianceEngine(state="texas").evaluate(_good_model())
        md = generate_markdown_report(results, state="Texas")
        assert "Texas" in md

    def test_has_executive_summary(self):
        results = ComplianceEngine().evaluate(_good_model())
        md = generate_markdown_report(results)
        assert "## Executive Summary" in md
        assert "PASS" in md

    def test_has_disclaimer(self):
        results = ComplianceEngine().evaluate(_good_model())
        md = generate_markdown_report(results)
        assert "Professional Engineer" in md
        assert "automated compliance checking tool" in md

    def test_has_detailed_results(self):
        results = ComplianceEngine().evaluate(_good_model())
        md = generate_markdown_report(results)
        assert "## Detailed Results" in md
        assert "Manning's n" in md

    def test_critical_failures_section(self):
        results = ComplianceEngine().evaluate(_failing_model())
        md = generate_markdown_report(results)
        assert "## Critical Failures" in md

    def test_recommendations_section(self):
        results = ComplianceEngine().evaluate(_failing_model())
        md = generate_markdown_report(results)
        assert "## Recommendations" in md

    def test_no_failures_no_critical_section(self):
        results = ComplianceEngine().evaluate(_good_model())
        md = generate_markdown_report(results)
        assert "## Critical Failures" not in md

    def test_writes_to_file(self, tmp_path: Path):
        results = ComplianceEngine().evaluate(_good_model())
        out = tmp_path / "report.md"
        generate_markdown_report(results, output_path=out)
        assert out.exists()
        content = out.read_text()
        assert "# HEC-RAS Compliance Report" in content

    def test_citation_in_detailed_table(self):
        results = ComplianceEngine().evaluate(_good_model())
        md = generate_markdown_report(results)
        assert "FEMA" in md

    def test_fail_shows_actual_and_expected(self):
        results = ComplianceEngine().evaluate(_failing_model())
        md = generate_markdown_report(results)
        assert "0.001" in md

    def test_good_model_pass_count(self):
        results = ComplianceEngine().evaluate(_good_model())
        passes = [r for r in results if r.status == "PASS"]
        md = generate_markdown_report(results)
        assert f"| PASS | {len(passes)} |" in md

    def test_empty_results(self):
        md = generate_markdown_report([])
        assert "# HEC-RAS Compliance Report" in md
        assert "| **Total** | **0** |" in md


# ===================================================================
# PDF report tests
# ===================================================================


class TestPDFReport:
    def test_generates_pdf_file(self, tmp_path: Path):
        results = ComplianceEngine().evaluate(_good_model())
        out = tmp_path / "report.pdf"
        returned = generate_pdf_report(results, output_path=out)
        assert out.exists()
        assert returned == out
        assert out.stat().st_size > 1000

    def test_pdf_starts_with_header(self, tmp_path: Path):
        results = ComplianceEngine().evaluate(_good_model())
        out = tmp_path / "report.pdf"
        generate_pdf_report(results, output_path=out)
        content = out.read_bytes()
        assert content[:5] == b"%PDF-"

    def test_pdf_with_failures(self, tmp_path: Path):
        results = ComplianceEngine().evaluate(_failing_model())
        out = tmp_path / "fail_report.pdf"
        generate_pdf_report(
            results, model_filename="bad_model.prj",
            state="Texas", output_path=out,
        )
        assert out.exists()
        assert out.stat().st_size > 1000

    def test_pdf_with_empty_results(self, tmp_path: Path):
        out = tmp_path / "empty.pdf"
        generate_pdf_report([], output_path=out)
        assert out.exists()

    def test_pdf_with_texas_rules(self, tmp_path: Path):
        results = ComplianceEngine(state="texas").evaluate(_good_model())
        out = tmp_path / "texas.pdf"
        generate_pdf_report(results, state="Texas", output_path=out)
        assert out.exists()
        assert out.stat().st_size > 1000

    def test_returns_path_object(self, tmp_path: Path):
        results = ComplianceEngine().evaluate(_good_model())
        out = tmp_path / "report.pdf"
        result = generate_pdf_report(results, output_path=out)
        assert isinstance(result, Path)


# ===================================================================
# Full pipeline: parse → evaluate → report
# ===================================================================


class TestFullPipeline:
    def test_parse_evaluate_markdown(self, tmp_path: Path):
        from hecras_compliance.parsers import parse_geometry, parse_plan, parse_flow

        geom = parse_geometry(FIXTURES / "sample.g01")
        plan = parse_plan(FIXTURES / "sample.p01")
        flow = parse_flow(FIXTURES / "sample.f01")
        model = ModelData(geometry=geom, plan=plan, flow=flow)

        engine = ComplianceEngine()
        results = engine.evaluate(model)

        out = tmp_path / "pipeline_report.md"
        md = generate_markdown_report(
            results, model_filename="sample.prj", output_path=out,
        )
        assert out.exists()
        assert "## Executive Summary" in md
        assert len(results) > 0

    def test_parse_evaluate_pdf(self, tmp_path: Path):
        from hecras_compliance.parsers import parse_geometry, parse_plan, parse_flow

        geom = parse_geometry(FIXTURES / "sample.g01")
        plan = parse_plan(FIXTURES / "sample.p01")
        flow = parse_flow(FIXTURES / "sample.f01")
        model = ModelData(geometry=geom, plan=plan, flow=flow)

        engine = ComplianceEngine()
        results = engine.evaluate(model)

        out = tmp_path / "pipeline_report.pdf"
        generate_pdf_report(
            results, model_filename="sample.prj", output_path=out,
        )
        assert out.exists()
        assert out.stat().st_size > 1000
