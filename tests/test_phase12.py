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
    executive_docx_path,
    validate_light,
)


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

# Metrics must ground in _AUDIT (20% from 0.2, 0.88 from similarity)
_SYNTH_OK = """## Executive Summary

Roughly 20.0% of crawled routes sit in overlap while paired pages show 0.8800 text similarity, so one narrative is being told through multiple doors.

## Core Problem

Duplicate routes answer the same buyer job without a single owner URL.

## Why It Matters

Conversion and test readouts split when demand lands on competing surfaces.

## Evidence

Cluster proofs show the same section patterns across paired URLs in the sample.

## Recommended Action

Pick one canonical URL per top cluster and merge or differentiate the twin this month.

## Execution Plan

Week 1 map overlaps. Week 2 execute merges. Week 3 fix internal links. Week 4 read conversion.

## Risks of Inaction

Spend keeps feeding both routes while lift stays unreadable.

## Expected Outcomes

One primary path per decision restores clearer credit and calmer optimization.
"""


def _delete_build_job_row(report_id: int) -> None:
    with SessionLocal() as db:
        row = db.get(AppSetting, f"report.build.job.{report_id}")
        if row:
            db.delete(row)
            db.commit()


class TestExecutiveContent(unittest.TestCase):
    def test_validate_rejects_empty_section_metric_count(self):
        bad = _SYNTH_OK.replace("20.0%", "many pages")
        r = validate_light(bad, _AUDIT)
        self.assertFalse(r["ok"])

    def test_validate_ok(self):
        v = validate_light(_SYNTH_OK, _AUDIT)
        self.assertTrue(v["ok"], msg=v.get("errors"))


@unittest.skipUnless(_docx_available(), "python-docx not installed")
class TestReportBuilderEndpoint(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.report_build_runner.write_executive_report", return_value=_SYNTH_OK)
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

            built = self.client.post(f"/reports/{rid}/build?sync=1")
            self.assertEqual(built.status_code, 200, msg=built.content)
            data = built.json()
            self.assertEqual(data.get("status"), "success")
            self.assertIn("download_url", data)

            p = executive_docx_path(rid)
            self.assertTrue(p.is_file())
            dl = self.client.get(f"/reports/{rid}/download/executive.docx")
            self.assertEqual(dl.status_code, 200)
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
