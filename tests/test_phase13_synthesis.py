"""Phase 13/16: light validation and DOCX from synthesized Markdown."""

import json
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.db.models import AppSetting, AuditReport
from app.db.session import SessionLocal
from app.main import app
from app.reporting.executive_content import (
    MIN_SYNTHESIS_CHARS,
    executive_docx_path,
    executive_synthesized_md_path,
    validate_light,
)
from app.reporting.report_builder import build_executive_docx
from tests.fixtures_executive_synth import SYNTH_OK


def _delete_build_job_row(report_id: int) -> None:
    with SessionLocal() as db:
        row = db.get(AppSetting, f"report.build.job.{report_id}")
        if row:
            db.delete(row)
            db.commit()


def _docx_available() -> bool:
    try:
        import docx  # noqa: F401

        return True
    except Exception:
        return False


_AUDIT = {
    "key_metrics": {"overlap_rate": 0.2, "avg_cluster_similarity": 0.88},
    "core_problem_candidates": [{"statement": "x", "supporting_metrics": [], "affected_urls": []}],
    "top_clusters": [],
    "priority_actions": ["act"],
}

class TestSynthesisValidation(unittest.TestCase):
    def test_validate_rejects_generic_h2_only(self):
        partial = "## Executive Summary\n\n" + ("Body paragraph. " * 80)
        self.assertGreaterEqual(len(partial.strip()), MIN_SYNTHESIS_CHARS)
        r = validate_light(partial, _AUDIT)
        self.assertFalse(r["ok"])

    def test_validate_ok_full_doc(self):
        r = validate_light(SYNTH_OK, _AUDIT)
        self.assertTrue(r["ok"], msg=r.get("errors"))

    def test_validate_rejects_prose_without_consulting_signals(self):
        prose = (
            "Structural overlap fragments how the business reads performance. "
            "Multiple routes answer equivalent buyer jobs so credit splinters and "
            "tests contradict each other. The crawl and cluster view make the "
            "pattern obvious: the same blocks repeat across paired URLs. "
            "Canonicalization per intent cluster is the lever. "
        ) * 12
        r = validate_light(prose, _AUDIT)
        self.assertFalse(r["ok"])


@unittest.skipUnless(_docx_available(), "python-docx not installed")
class TestBuildUsesSynthesisOnly(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.report_build_runner.write_executive_report", return_value=SYNTH_OK)
    def test_build_writes_artifacts_and_docx(self, _mock_write):
        snap = json.dumps(
            {
                "executive_report_md": "legacy",
                "technical_report_md": "tech",
                "verification_pack": {"cluster_proofs": []},
                "executive_summary_data": {
                    "_metrics_snapshot": {"overlap_rate": 0.2, "avg_cluster_similarity": 0.88},
                    "boardroom_summary": {"slides": []},
                },
                "audit_signal": _AUDIT,
            }
        )
        with SessionLocal() as db:
            ar = AuditReport(
                domains="https://example.com",
                score=70,
                priority_level="medium",
                report_html="<p>x</p>",
                snapshot_json=snap,
            )
            db.add(ar)
            db.commit()
            rid = ar.id
        try:
            r = self.client.post(f"/reports/{rid}/build?sync=1")
            self.assertEqual(r.status_code, 200, msg=r.content)
            self.assertEqual(r.json().get("status"), "success")
            syn = executive_synthesized_md_path(rid)
            self.assertTrue(syn.is_file())
            p = executive_docx_path(rid)
            self.assertTrue(p.is_file())
        finally:
            _delete_build_job_row(rid)
            with SessionLocal() as db:
                row = db.get(AuditReport, rid)
                if row:
                    db.delete(row)
                    db.commit()
            d = executive_docx_path(rid).parent
            if d.is_dir():
                for f in d.glob("*"):
                    f.unlink(missing_ok=True)
                try:
                    d.rmdir()
                except OSError:
                    pass

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch(
        "app.report_build_runner.write_executive_report",
        return_value="Too short.",
    )
    def test_build_error_when_validation_fails(self, _mock_write):
        snap = json.dumps(
            {
                "executive_report_md": "x",
                "technical_report_md": "",
                "executive_summary_data": {},
                "verification_pack": {},
                "audit_signal": _AUDIT,
            }
        )
        with SessionLocal() as db:
            ar = AuditReport(
                domains="https://example.com",
                score=70,
                priority_level="medium",
                report_html="<p>x</p>",
                snapshot_json=snap,
            )
            db.add(ar)
            db.commit()
            rid = ar.id
        try:
            r = self.client.post(f"/reports/{rid}/build?sync=1")
            self.assertEqual(r.status_code, 422)
            data = r.json()
            self.assertEqual(data.get("status"), "error")
            self.assertTrue(data.get("errors"))
            self.assertFalse(executive_docx_path(rid).is_file())
        finally:
            _delete_build_job_row(rid)
            with SessionLocal() as db:
                row = db.get(AuditReport, rid)
                if row:
                    db.delete(row)
                    db.commit()


class TestDocxRendering(unittest.TestCase):
    @unittest.skipUnless(_docx_available(), "python-docx not installed")
    def test_build_executive_docx_from_synthesized_shape(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            md_path = tdp / "executive_synthesized.md"
            out_path = tdp / "executive.docx"
            md_path.write_text(SYNTH_OK, encoding="utf-8")
            build_executive_docx(str(md_path), str(out_path))
            self.assertTrue(out_path.exists())
            self.assertGreater(out_path.stat().st_size, 2048)

    @unittest.skipUnless(_docx_available(), "python-docx not installed")
    def test_build_docx_from_plain_prose_md(self):
        import tempfile
        from pathlib import Path

        prose = (
            "Executive narrative without forced headings. "
            "Roughly 20.0% overlap and 0.8800 similarity appear in the crawl. "
        ) * 30
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            md_path = tdp / "executive_synthesized.md"
            out_path = tdp / "executive.docx"
            md_path.write_text(prose, encoding="utf-8")
            build_executive_docx(str(md_path), str(out_path))
            self.assertTrue(out_path.exists())
            self.assertGreater(out_path.stat().st_size, 2048)


if __name__ == "__main__":
    unittest.main()
