"""Tests for the HEC-RAS project file parser."""

from __future__ import annotations

from pathlib import Path
import textwrap
import pytest

from hecras_compliance.parsers.project import (
    ProjectFile,
    parse_project,
)

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_PRJ = FIXTURES / "sample.prj"


# ===================================================================
# Dataclass tests
# ===================================================================


class TestProjectFileDataclass:
    def test_defaults(self):
        prj = ProjectFile()
        assert prj.title == ""
        assert prj.description == ""
        assert prj.units == ""
        assert prj.current_plan == ""
        assert prj.geom_files == []
        assert prj.steady_files == []
        assert prj.unsteady_files == []
        assert prj.quasi_files == []
        assert prj.plan_files == []
        assert prj.default_expansion == 0.3
        assert prj.default_contraction == 0.1

    def test_all_flow_files(self):
        prj = ProjectFile(
            steady_files=["f01"],
            unsteady_files=["u01"],
            quasi_files=["q01"],
        )
        assert prj.all_flow_files == ["f01", "u01", "q01"]

    def test_all_flow_files_empty(self):
        assert ProjectFile().all_flow_files == []

    def test_is_english(self):
        assert ProjectFile(units="English").is_english is True
        assert ProjectFile(units="SI Metric").is_english is False
        assert ProjectFile(units="").is_english is False

    def test_is_metric(self):
        assert ProjectFile(units="SI Metric").is_metric is True
        assert ProjectFile(units="English").is_metric is False
        assert ProjectFile(units="").is_metric is False


# ===================================================================
# Parsing the sample.prj fixture
# ===================================================================


class TestSamplePrjParsing:
    @pytest.fixture(scope="class")
    def prj(self) -> ProjectFile:
        return parse_project(SAMPLE_PRJ)

    def test_title(self, prj: ProjectFile):
        assert prj.title == "Beargrass Creek Compliance Study"

    def test_units(self, prj: ProjectFile):
        assert prj.units == "English"

    def test_is_english(self, prj: ProjectFile):
        assert prj.is_english is True

    def test_is_not_metric(self, prj: ProjectFile):
        assert prj.is_metric is False

    def test_current_plan(self, prj: ProjectFile):
        assert prj.current_plan == "p01"

    def test_geom_files(self, prj: ProjectFile):
        assert prj.geom_files == ["g01"]

    def test_steady_files(self, prj: ProjectFile):
        assert prj.steady_files == ["f01"]

    def test_plan_files(self, prj: ProjectFile):
        assert prj.plan_files == ["p01"]

    def test_unsteady_files_empty(self, prj: ProjectFile):
        assert prj.unsteady_files == []

    def test_quasi_files_empty(self, prj: ProjectFile):
        assert prj.quasi_files == []

    def test_all_flow_files(self, prj: ProjectFile):
        assert prj.all_flow_files == ["f01"]

    def test_default_expansion(self, prj: ProjectFile):
        assert prj.default_expansion == pytest.approx(0.3)

    def test_default_contraction(self, prj: ProjectFile):
        assert prj.default_contraction == pytest.approx(0.1)

    def test_description(self, prj: ProjectFile):
        assert "Beargrass Creek" in prj.description
        assert "Jefferson County" in prj.description

    def test_description_multiline(self, prj: ProjectFile):
        lines = prj.description.strip().splitlines()
        assert len(lines) == 3


# ===================================================================
# Synthetic / edge-case tests
# ===================================================================


class TestMultipleFiles:
    def test_multiple_geom_files(self, tmp_path: Path):
        content = textwrap.dedent("""\
            Proj Title=Multi Geom
            Geom File=g01
            Geom File=g02
            Geom File=g03
        """)
        f = tmp_path / "multi.prj"
        f.write_text(content)
        prj = parse_project(f)
        assert prj.geom_files == ["g01", "g02", "g03"]

    def test_multiple_plan_files(self, tmp_path: Path):
        content = textwrap.dedent("""\
            Proj Title=Multi Plan
            Plan File=p01
            Plan File=p02
        """)
        f = tmp_path / "multi.prj"
        f.write_text(content)
        prj = parse_project(f)
        assert prj.plan_files == ["p01", "p02"]

    def test_multiple_flow_file_types(self, tmp_path: Path):
        content = textwrap.dedent("""\
            Proj Title=Multi Flow
            Steady File=f01
            Steady File=f02
            Unsteady File=u01
            QuasiSteady File=q01
        """)
        f = tmp_path / "multi.prj"
        f.write_text(content)
        prj = parse_project(f)
        assert prj.steady_files == ["f01", "f02"]
        assert prj.unsteady_files == ["u01"]
        assert prj.quasi_files == ["q01"]
        assert prj.all_flow_files == ["f01", "f02", "u01", "q01"]

    def test_full_project_with_all_types(self, tmp_path: Path):
        content = textwrap.dedent("""\
            Proj Title=Full Project
            Current Plan=p02
            Default Exp/Contr=0.5,0.3

            English Units

            Geom File=g01
            Geom File=g02
            Steady File=f01
            Unsteady File=u01
            Plan File=p01
            Plan File=p02
            Plan File=p03

            BEGIN DESCRIPTION:
            A comprehensive model.
            END DESCRIPTION:
        """)
        f = tmp_path / "full.prj"
        f.write_text(content)
        prj = parse_project(f)
        assert prj.title == "Full Project"
        assert prj.current_plan == "p02"
        assert prj.default_expansion == pytest.approx(0.5)
        assert prj.default_contraction == pytest.approx(0.3)
        assert prj.units == "English"
        assert prj.geom_files == ["g01", "g02"]
        assert prj.steady_files == ["f01"]
        assert prj.unsteady_files == ["u01"]
        assert prj.plan_files == ["p01", "p02", "p03"]
        assert "comprehensive" in prj.description


class TestUnitsDetection:
    def test_english_units(self, tmp_path: Path):
        f = tmp_path / "eng.prj"
        f.write_text("Proj Title=Test\nEnglish Units\n")
        prj = parse_project(f)
        assert prj.units == "English"
        assert prj.is_english is True

    def test_si_units(self, tmp_path: Path):
        f = tmp_path / "si.prj"
        f.write_text("Proj Title=Test\nSI Units\n")
        prj = parse_project(f)
        assert prj.units == "SI Metric"
        assert prj.is_metric is True

    def test_si_metric(self, tmp_path: Path):
        f = tmp_path / "si2.prj"
        f.write_text("Proj Title=Test\nSI Metric\n")
        prj = parse_project(f)
        assert prj.units == "SI Metric"
        assert prj.is_metric is True

    def test_no_units(self, tmp_path: Path):
        f = tmp_path / "none.prj"
        f.write_text("Proj Title=Test\n")
        prj = parse_project(f)
        assert prj.units == ""
        assert prj.is_english is False
        assert prj.is_metric is False


class TestDescription:
    def test_empty_description(self, tmp_path: Path):
        content = textwrap.dedent("""\
            Proj Title=Test
            BEGIN DESCRIPTION:
            END DESCRIPTION:
        """)
        f = tmp_path / "empty_desc.prj"
        f.write_text(content)
        prj = parse_project(f)
        assert prj.description == ""

    def test_single_line_description(self, tmp_path: Path):
        content = textwrap.dedent("""\
            Proj Title=Test
            BEGIN DESCRIPTION:
            One-liner.
            END DESCRIPTION:
        """)
        f = tmp_path / "one.prj"
        f.write_text(content)
        prj = parse_project(f)
        assert prj.description.strip() == "One-liner."

    def test_no_description_block(self, tmp_path: Path):
        f = tmp_path / "nodesc.prj"
        f.write_text("Proj Title=Test\n")
        prj = parse_project(f)
        assert prj.description == ""


class TestDefaultCoefficients:
    def test_custom_coefficients(self, tmp_path: Path):
        f = tmp_path / "coeff.prj"
        f.write_text("Proj Title=Test\nDefault Exp/Contr=0.5,0.3\n")
        prj = parse_project(f)
        assert prj.default_expansion == pytest.approx(0.5)
        assert prj.default_contraction == pytest.approx(0.3)

    def test_no_coefficients_keeps_defaults(self, tmp_path: Path):
        f = tmp_path / "nocoeff.prj"
        f.write_text("Proj Title=Test\n")
        prj = parse_project(f)
        assert prj.default_expansion == pytest.approx(0.3)
        assert prj.default_contraction == pytest.approx(0.1)


class TestEdgeCases:
    def test_empty_file(self, tmp_path: Path):
        f = tmp_path / "empty.prj"
        f.write_text("")
        prj = parse_project(f)
        assert prj.title == ""
        assert prj.geom_files == []
        assert prj.plan_files == []

    def test_empty_file_references_skipped(self, tmp_path: Path):
        content = textwrap.dedent("""\
            Proj Title=Test
            Geom File=
            Steady File=
            Plan File=
        """)
        f = tmp_path / "empty_refs.prj"
        f.write_text(content)
        prj = parse_project(f)
        assert prj.geom_files == []
        assert prj.steady_files == []
        assert prj.plan_files == []

    def test_whitespace_in_values(self, tmp_path: Path):
        f = tmp_path / "ws.prj"
        f.write_text("Proj Title= My Project \nCurrent Plan= p02 \n")
        prj = parse_project(f)
        assert prj.title == "My Project"
        assert prj.current_plan == "p02"

    def test_unknown_keywords_ignored(self, tmp_path: Path):
        content = textwrap.dedent("""\
            Proj Title=Test
            Unknown Key=some value
            Another Random=thing
            Plan File=p01
        """)
        f = tmp_path / "unknown.prj"
        f.write_text(content)
        prj = parse_project(f)
        assert prj.title == "Test"
        assert prj.plan_files == ["p01"]


# ===================================================================
# Import / public API
# ===================================================================


class TestPublicAPI:
    def test_import_from_package(self):
        from hecras_compliance.parsers import parse_project as pp
        assert callable(pp)

    def test_parse_project_returns_project_file(self):
        result = parse_project(SAMPLE_PRJ)
        assert isinstance(result, ProjectFile)
