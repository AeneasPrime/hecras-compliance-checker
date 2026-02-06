"""Tests for the Click CLI (hecras-check)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from hecras_compliance.cli import cli

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_PRJ = str(FIXTURES / "sample.prj")


@pytest.fixture
def runner():
    return CliRunner()


# ===================================================================
# hecras-check --version
# ===================================================================


class TestVersion:
    def test_shows_version(self, runner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


# ===================================================================
# hecras-check run
# ===================================================================


class TestRun:
    def test_run_federal_only(self, runner):
        result = runner.invoke(cli, ["run", SAMPLE_PRJ])
        assert result.exit_code == 0
        assert "HEC-RAS Compliance Checker" in result.output
        assert "passed" in result.output

    def test_run_with_state(self, runner):
        result = runner.invoke(cli, ["run", SAMPLE_PRJ, "--state", "TX"])
        assert result.exit_code == 0
        assert "Texas" in result.output or "texas" in result.output.lower()

    def test_run_with_state_full_name(self, runner):
        result = runner.invoke(cli, ["run", SAMPLE_PRJ, "--state", "texas"])
        assert result.exit_code == 0

    def test_run_with_markdown_output(self, runner, tmp_path):
        out = str(tmp_path / "report.md")
        result = runner.invoke(cli, ["run", SAMPLE_PRJ, "--output", out])
        assert result.exit_code == 0
        assert Path(out).exists()
        content = Path(out).read_text()
        assert "# HEC-RAS Compliance Report" in content

    def test_run_with_pdf_output(self, runner, tmp_path):
        out = str(tmp_path / "report.md")
        result = runner.invoke(cli, ["run", SAMPLE_PRJ, "--output", out, "--pdf"])
        assert result.exit_code == 0
        pdf_path = Path(out).with_suffix(".pdf")
        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 1000

    def test_run_shows_pass_counts(self, runner):
        result = runner.invoke(cli, ["run", SAMPLE_PRJ])
        assert result.exit_code == 0
        assert "passed" in result.output
        assert "failed" in result.output

    def test_run_shows_failures(self, runner):
        result = runner.invoke(cli, ["run", SAMPLE_PRJ])
        assert result.exit_code == 0
        # sample.prj has Manning's n failures at RS 2000
        assert "critical failure" in result.output.lower() or "FAIL" in result.output

    def test_run_shows_geometry_parse_info(self, runner):
        result = runner.invoke(cli, ["run", SAMPLE_PRJ])
        assert result.exit_code == 0
        assert "geometry" in result.output.lower()

    def test_run_nonexistent_file(self, runner):
        result = runner.invoke(cli, ["run", "/nonexistent/file.prj"])
        assert result.exit_code != 0

    def test_run_pdf_only_no_markdown(self, runner, tmp_path):
        """--pdf without --output uses default PDF path."""
        result = runner.invoke(cli, ["run", SAMPLE_PRJ, "--pdf"])
        assert result.exit_code == 0
        assert "PDF" in result.output or "pdf" in result.output

    def test_run_state_with_markdown_and_pdf(self, runner, tmp_path):
        out = str(tmp_path / "texas_report.md")
        result = runner.invoke(cli, ["run", SAMPLE_PRJ, "-s", "TX", "-o", out, "--pdf"])
        assert result.exit_code == 0
        assert Path(out).exists()
        pdf_path = Path(out).with_suffix(".pdf")
        assert pdf_path.exists()


# ===================================================================
# hecras-check list-rules
# ===================================================================


class TestListRules:
    def test_list_federal_rules(self, runner):
        result = runner.invoke(cli, ["list-rules"])
        assert result.exit_code == 0
        assert "FEMA-MANN-001" in result.output
        assert "FEMA-MANN-002" in result.output
        assert "FEMA-COEF-001" in result.output
        assert "FEMA-FW-001" in result.output
        assert "FEMA-EVENT-001" in result.output
        assert "FEMA-BRG-001" in result.output
        assert "FEMA-BC-001" in result.output

    def test_list_rules_count_federal(self, runner):
        result = runner.invoke(cli, ["list-rules"])
        assert result.exit_code == 0
        assert "8 rules total" in result.output

    def test_list_rules_with_state(self, runner):
        result = runner.invoke(cli, ["list-rules", "--state", "TX"])
        assert result.exit_code == 0
        # Texas adds 6 rules and supersedes FEMA-FW-001
        assert "TX-FW-001" in result.output
        assert "TX-EVENT-001" in result.output
        assert "FEMA-FW-001" not in result.output  # superseded

    def test_list_rules_texas_count(self, runner):
        result = runner.invoke(cli, ["list-rules", "-s", "texas"])
        assert result.exit_code == 0
        # 8 FEMA - 1 superseded + 6 Texas = 13
        assert "13 rules total" in result.output

    def test_list_rules_shows_severity(self, runner):
        result = runner.invoke(cli, ["list-rules"])
        assert result.exit_code == 0
        assert "error" in result.output
        assert "warning" in result.output

    def test_list_rules_shows_rule_names(self, runner):
        result = runner.invoke(cli, ["list-rules"])
        assert result.exit_code == 0
        assert "Channel Manning" in result.output
        assert "Overbank Manning" in result.output


# ===================================================================
# hecras-check summary
# ===================================================================


class TestSummary:
    def test_summary_shows_model_info(self, runner):
        result = runner.invoke(cli, ["summary", SAMPLE_PRJ])
        assert result.exit_code == 0
        assert "Model Summary" in result.output

    def test_summary_shows_project_title(self, runner):
        result = runner.invoke(cli, ["summary", SAMPLE_PRJ])
        assert result.exit_code == 0
        assert "sample.prj" in result.output

    def test_summary_shows_cross_section_count(self, runner):
        result = runner.invoke(cli, ["summary", SAMPLE_PRJ])
        assert result.exit_code == 0
        assert "Cross sections" in result.output

    def test_summary_shows_bridge_count(self, runner):
        result = runner.invoke(cli, ["summary", SAMPLE_PRJ])
        assert result.exit_code == 0
        assert "Bridges" in result.output

    def test_summary_shows_flow_profiles(self, runner):
        result = runner.invoke(cli, ["summary", SAMPLE_PRJ])
        assert result.exit_code == 0
        assert "Profiles" in result.output or "profiles" in result.output

    def test_summary_shows_plan_type(self, runner):
        result = runner.invoke(cli, ["summary", SAMPLE_PRJ])
        assert result.exit_code == 0
        assert "Steady" in result.output

    def test_summary_shows_units(self, runner):
        result = runner.invoke(cli, ["summary", SAMPLE_PRJ])
        assert result.exit_code == 0
        assert "English" in result.output

    def test_summary_shows_referenced_files(self, runner):
        result = runner.invoke(cli, ["summary", SAMPLE_PRJ])
        assert result.exit_code == 0
        assert "Geometry" in result.output
        assert "Plan" in result.output

    def test_summary_shows_encroachment(self, runner):
        result = runner.invoke(cli, ["summary", SAMPLE_PRJ])
        assert result.exit_code == 0
        assert "Encroachment" in result.output or "encroachment" in result.output

    def test_summary_nonexistent_file(self, runner):
        result = runner.invoke(cli, ["summary", "/nonexistent/file.prj"])
        assert result.exit_code != 0


# ===================================================================
# hecras-check add-state
# ===================================================================


class TestAddState:
    @pytest.fixture(autouse=True)
    def _isolate_states_dir(self, tmp_path, monkeypatch):
        """Redirect add-state output to a temp directory."""
        monkeypatch.setattr("hecras_compliance.cli._STATES_DIR", tmp_path)

    def test_add_state_basic(self, runner, tmp_path):
        """Create a minimal state file with no extra rules."""
        result = runner.invoke(cli, ["add-state"], input="Florida\nFL\nn\nn\nn\nn\n")
        assert result.exit_code == 0
        assert "Created" in result.output
        assert (tmp_path / "florida.yaml").exists()

    def test_add_state_with_zero_rise(self, runner, tmp_path):
        """Create a state file with zero-rise floodway rule."""
        result = runner.invoke(
            cli, ["add-state"],
            input="Georgia\nGA\ny\nFEMA-FW-001\ny\nn\nn\n",
        )
        assert result.exit_code == 0
        assert "GA-FW-001" in result.output
        assert (tmp_path / "georgia.yaml").exists()

    def test_add_state_with_events(self, runner, tmp_path):
        """Create a state file with flood event rules."""
        # No supersedes, no zero-rise, yes events (all 4), no freeboard
        result = runner.invoke(
            cli, ["add-state"],
            input="Ohio\nOH\nn\nn\ny\ny\ny\ny\ny\nn\n",
        )
        assert result.exit_code == 0
        assert "OH-EVENT-001" in result.output

    def test_add_state_with_freeboard(self, runner, tmp_path):
        """Create a state file with freeboard review."""
        result = runner.invoke(
            cli, ["add-state"],
            input="Nevada\nNV\nn\nn\nn\ny\n",
        )
        assert result.exit_code == 0
        assert "NV-FB-001" in result.output

    def test_add_state_full_wizard(self, runner, tmp_path):
        """Create a state file with all optional rules."""
        result = runner.invoke(
            cli, ["add-state"],
            input="Montana\nMT\ny\nFEMA-FW-001\ny\ny\ny\ny\ny\ny\ny\n",
        )
        assert result.exit_code == 0
        assert "MT-FW-001" in result.output
        assert "MT-EVENT-001" in result.output
        assert "MT-FB-001" in result.output

    def test_add_state_creates_valid_yaml(self, runner, tmp_path):
        """Verify generated YAML is valid and loadable."""
        runner.invoke(cli, ["add-state"], input="Alaska\nAK\nn\ny\nn\nn\n")
        content = (tmp_path / "alaska.yaml").read_text()
        data = yaml.safe_load(content)
        assert data["state"] == "Alaska"
        assert data["state_abbreviation"] == "AK"

    def test_add_state_overwrite_prompt(self, runner, tmp_path):
        """Declining overwrite aborts without error."""
        (tmp_path / "hawaii.yaml").write_text("existing: true")
        result = runner.invoke(cli, ["add-state"], input="Hawaii\nHI\nn\n")
        assert result.exit_code == 0
        assert "Aborted" in result.output
