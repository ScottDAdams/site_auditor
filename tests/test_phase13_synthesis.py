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
    executive_docx_path,
    executive_synthesized_md_path,
    validate_light,
)
from app.reporting.report_builder import build_executive_docx


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


class TestSynthesisValidation(unittest.TestCase):
    def test_validate_rejects_missing_section(self):
        short = "## Executive Summary\n\n20.0% overlap and 0.8800 similarity noted.\n"
        r = validate_light(short, _AUDIT)
        self.assertFalse(r["ok"])

    def test_validate_ok_full_doc(self):
        r = validate_light(_SYNTH_OK, _AUDIT)
        self.assertTrue(r["ok"], msg=r.get("errors"))

    def test_validate_requires_two_metrics(self):
        one = _SYNTH_OK.replace("0.8800 text similarity", "high similarity")
        r = validate_light(one, _AUDIT)
        self.assertFalse(r["ok"])


@unittest.skipUnless(_docx_available(), "python-docx not installed")
class TestBuildUsesSynthesisOnly(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.report_build_runner.write_executive_report", return_value=_SYNTH_OK)
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
        return_value="## Executive Summary\n\nToo short.",
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
            md_path.write_text(_SYNTH_OK, encoding="utf-8")
            build_executive_docx(str(md_path), str(out_path))
            self.assertTrue(out_path.exists())
            self.assertGreater(out_path.stat().st_size, 2048)


if __name__ == "__main__":
    unittest.main()
