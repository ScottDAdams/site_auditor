"""Phase 12/16: report build and light validation."""

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
from tests.fixtures_executive_synth import SYNTH_OK


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

def _delete_build_job_row(report_id: int) -> None:
    with SessionLocal() as db:
        row = db.get(AppSetting, f"report.build.job.{report_id}")
        if row:
            db.delete(row)
            db.commit()


class TestExecutiveContent(unittest.TestCase):
    def test_validate_rejects_too_short(self):
        short = "x" * (MIN_SYNTHESIS_CHARS - 1)
        r = validate_light(short, _AUDIT)
        self.assertFalse(r["ok"])

    def test_validate_ok(self):
        v = validate_light(SYNTH_OK, _AUDIT)
        self.assertTrue(v["ok"], msg=v.get("errors"))

    def test_validate_ok_without_h2_headings(self):
        body = SYNTH_OK.replace("## Stance\n\n", "")
        self.assertGreaterEqual(len(body.strip()), MIN_SYNTHESIS_CHARS)
        r = validate_light(body, _AUDIT)
        self.assertTrue(r["ok"], msg=r.get("errors"))


@unittest.skipUnless(_docx_available(), "python-docx not installed")
class TestReportBuilderEndpoint(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.report_build_runner.write_executive_report", return_value=SYNTH_OK)
    def test_docx_404_until_built(self, _mock_write):
        snap = json.dumps(
            {
                "executive_report_md": "prior",
                "technical_report_md": "tech",
                "verification_pack": {"cluster_proofs": []},
                "executive_summary_data": {
                    "_metrics_snapshot": {"overlap_rate": 0.2, "avg_cluster_similarity": 0.88},
                    "boardroom_summary": {"slides": []},
                    "audit_signal": _AUDIT,
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
            r = self.client.get(f"/reports/{rid}/download/executive.docx")
            self.assertEqual(r.status_code, 404)
            body = r.json()
            self.assertIn("not built", body.get("message", "").lower())

            rmd = self.client.get(
                f"/reports/{rid}/download/executive_synthesized.md"
            )
            self.assertEqual(rmd.status_code, 404)

            built = self.client.post(f"/reports/{rid}/build?sync=1")
            self.assertEqual(built.status_code, 200, msg=built.content)
            data = built.json()
            self.assertEqual(data.get("status"), "success")
            self.assertIn("download_url", data)
            self.assertIn("synthesized_md_url", data)

            syn = executive_synthesized_md_path(rid)
            self.assertTrue(syn.is_file())
            p = executive_docx_path(rid)
            self.assertTrue(p.is_file())
            dl = self.client.get(f"/reports/{rid}/download/executive.docx")
            self.assertEqual(dl.status_code, 200)
            mdl = self.client.get(
                f"/reports/{rid}/download/executive_synthesized.md"
            )
            self.assertEqual(mdl.status_code, 200)
            self.assertIn(b"20.0%", mdl.content)
            self.assertIn(b"The problem is", mdl.content)
        finally:
            _delete_build_job_row(rid)
            with SessionLocal() as db:
                row = db.get(AuditReport, rid)
                if row:
                    db.delete(row)
                    db.commit()
            p = executive_docx_path(rid)
            if p.parent.is_dir():
                for f in p.parent.glob("*"):
                    f.unlink(missing_ok=True)
                try:
                    p.parent.rmdir()
                except OSError:
                    pass


if __name__ == "__main__":
    unittest.main()
