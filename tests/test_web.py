"""Tests for the Flask web UI."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from hecras_compliance.web.app import create_app

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _upload_fixtures(client, state: str = "", filenames: list[str] | None = None):
    """POST fixture files to /review."""
    if filenames is None:
        filenames = ["sample.prj", "sample.g01", "sample.p01", "sample.f01"]

    data = {"state": state}
    files = []
    for fname in filenames:
        path = FIXTURES / fname
        files.append(
            ("files", (fname, path.open("rb"), "application/octet-stream"))
        )

    return client.post(
        "/review",
        data={**data, "files": ""},
        content_type="multipart/form-data",
        buffered=True,
        # Manually build multipart data
    ), files


def _post_review(client, state: str = "", filenames: list[str] | None = None):
    """Helper: POST fixture files to /review and return response."""
    if filenames is None:
        filenames = ["sample.prj", "sample.g01", "sample.p01", "sample.f01"]

    data = {"state": state}
    for fname in filenames:
        path = FIXTURES / fname
        data[f"files"] = []  # will be overridden

    # Build multipart form
    with client:
        file_tuples = []
        open_files = []
        for fname in filenames:
            path = FIXTURES / fname
            f = path.open("rb")
            open_files.append(f)
            file_tuples.append((io.BytesIO(f.read()), fname))
            f.close()

        mdata = {"state": state}
        file_list = []
        for content, fname in file_tuples:
            file_list.append((content, fname))

        resp = client.post(
            "/review",
            data={
                "state": state,
                **{f"files": [
                    (io.BytesIO((FIXTURES / fn).read_bytes()), fn)
                    for fn in filenames
                ]},
            },
            content_type="multipart/form-data",
        )
        return resp


# ===================================================================
# Index page
# ===================================================================


class TestIndex:
    def test_index_loads(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_index_has_upload_form(self, client):
        resp = client.get("/")
        html = resp.data.decode()
        assert '<form' in html
        assert 'enctype="multipart/form-data"' in html

    def test_index_has_state_dropdown(self, client):
        resp = client.get("/")
        html = resp.data.decode()
        assert "Federal (FEMA) only" in html
        assert "Texas" in html

    def test_index_has_file_input(self, client):
        resp = client.get("/")
        html = resp.data.decode()
        assert 'type="file"' in html
        assert "multiple" in html

    def test_index_has_review_button(self, client):
        resp = client.get("/")
        html = resp.data.decode()
        assert "Review" in html


# ===================================================================
# Review
# ===================================================================


class TestReview:
    def _post(self, client, state="", filenames=None):
        if filenames is None:
            filenames = ["sample.prj", "sample.g01", "sample.p01", "sample.f01"]

        data = {"state": state}
        files = []
        for fname in filenames:
            content = (FIXTURES / fname).read_bytes()
            files.append((io.BytesIO(content), fname))

        data["files"] = files
        return client.post(
            "/review",
            data=data,
            content_type="multipart/form-data",
        )

    def test_review_returns_200(self, client):
        resp = self._post(client)
        assert resp.status_code == 200

    def test_review_shows_model_name(self, client):
        resp = self._post(client)
        html = resp.data.decode()
        assert "sample.prj" in html

    def test_review_shows_pass_count(self, client):
        resp = self._post(client)
        html = resp.data.decode()
        assert "Passed" in html

    def test_review_shows_fail_count(self, client):
        resp = self._post(client)
        html = resp.data.decode()
        assert "Failed" in html

    def test_review_shows_critical_failures(self, client):
        resp = self._post(client)
        html = resp.data.decode()
        assert "Critical Failures" in html
        assert "FEMA-MANN-001" in html

    def test_review_shows_detailed_results(self, client):
        resp = self._post(client)
        html = resp.data.decode()
        assert "Detailed Results" in html
        assert "Manning" in html

    def test_review_shows_recommendations(self, client):
        resp = self._post(client)
        html = resp.data.decode()
        assert "Recommendations" in html

    def test_review_has_pdf_download_link(self, client):
        resp = self._post(client)
        html = resp.data.decode()
        assert "Download PDF" in html
        assert "/download-pdf/" in html

    def test_review_has_back_link(self, client):
        resp = self._post(client)
        html = resp.data.decode()
        assert "Review Another Model" in html

    def test_review_with_texas(self, client):
        resp = self._post(client, state="texas")
        html = resp.data.decode()
        assert resp.status_code == 200
        assert "Texas" in html
        # Texas has zero-rise rule
        assert "TX-FW-001" in html or "Zero-rise" in html

    def test_review_no_files_redirects(self, client):
        resp = client.post(
            "/review",
            data={"state": ""},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        html = resp.data.decode()
        assert "upload" in html.lower() or "file" in html.lower()

    def test_review_no_prj_redirects(self, client):
        """Uploading only a .g01 without .prj should show error."""
        content = (FIXTURES / "sample.g01").read_bytes()
        resp = client.post(
            "/review",
            data={
                "state": "",
                "files": [(io.BytesIO(content), "sample.g01")],
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        html = resp.data.decode()
        assert ".prj" in html.lower() or "project file" in html.lower()

    def test_review_shows_date(self, client):
        from datetime import date
        resp = self._post(client)
        html = resp.data.decode()
        assert date.today().isoformat() in html


# ===================================================================
# PDF download
# ===================================================================


class TestPDFDownload:
    def test_download_pdf(self, client):
        # First run a review to generate a PDF
        resp = self._run_review(client)
        html = resp.data.decode()

        # Extract session_id from the download link
        import re
        match = re.search(r'/download-pdf/([a-f0-9]+)', html)
        assert match, "No PDF download link found"
        session_id = match.group(1)

        # Download the PDF
        pdf_resp = client.get(f"/download-pdf/{session_id}")
        assert pdf_resp.status_code == 200
        assert pdf_resp.data[:5] == b"%PDF-"

    def test_download_invalid_session(self, client):
        resp = client.get("/download-pdf/nonexistent", follow_redirects=True)
        html = resp.data.decode()
        assert "not found" in html.lower() or "upload" in html.lower()

    def _run_review(self, client):
        filenames = ["sample.prj", "sample.g01", "sample.p01", "sample.f01"]
        data = {"state": ""}
        files = []
        for fname in filenames:
            content = (FIXTURES / fname).read_bytes()
            files.append((io.BytesIO(content), fname))
        data["files"] = files
        return client.post(
            "/review",
            data=data,
            content_type="multipart/form-data",
        )
