"""Phase 12/15: report build validation and on-demand DOCX."""

import json
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.db.models import AppSetting, AuditReport
from app.db.session import SessionLocal
from app.main import app
from app.reporting.executive_content import executive_docx_path, validate_executive_content


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


# Phase 15 validation: word caps, vague filler ban, metric spam cap, 15+ words/section
_SYNTH_OK = """## Executive Summary

The site keeps several live URLs answering the same buyer question, so teams split ownership and measurement before any campaign change can read clearly.

## Audit Scorecard

Roughly four in ten crawled routes sit inside overlap clusters while paired pages mirror the same body story, which means the crawl repeats one narrative across multiple doors.

## If You Do One Thing

Pick one canonical URL for the strongest overlap pair and merge or visibly separate the twin page before funding more net-new routes.

## What Is Breaking Performance

Parallel paths carry near-identical copy for one job. Internal owners disagree on which surface should win. Paid and organic entries land in a fork. Experiments run on one URL while fixes ship on another, so lift never stacks.

## Growth Opportunities

Retiring redundant doors turns calendar time toward intents the crawl never covered because effort kept recycling the same pages under different addresses.

## 30-Day Execution Plan

Week one maps overlaps and names keepers. Week two executes merges and redirects. Week three repairs internal links and sitemaps. Week four reads conversion only after the fork closes.

## Risks of Delay

Extra weeks keep spend entering paired URLs and leave readouts noisy because the structural fork stays open.

## Expected Outcomes

One primary route per decision should restore clearer credit, calmer tests, and buyers meeting a single exhale instead of a tie between twins.
"""

_VALID_POV = {
    "core_thesis": "The site runs duplicate pages for the same buyer decision without one clear owner.",
    "mechanism": "Teams publish parallel URLs so search and ads land on competing surfaces.",
    "consequence": "Conversion credit splinters and experiments contradict each other.",
    "priority_action": "Pick one primary URL per major decision and merge or differentiate the rest.",
}


class TestExecutiveContent(unittest.TestCase):
    def test_validate_rejects_not_provided(self):
        bad = _SYNTH_OK.replace("buyer question", "Not provided")
        r = validate_executive_content(bad)
        self.assertFalse(r["ok"])

    def test_validate_ok_synthesized_shape(self):
        v = validate_executive_content(_SYNTH_OK)
        self.assertTrue(v["ok"], msg=v.get("errors"))


@unittest.skipUnless(_docx_available(), "python-docx not installed")
class TestReportBuilderEndpoint(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.report_build_runner.compress_report", side_effect=lambda x: x)
    @patch("app.report_build_runner.write_executive_report", return_value=_SYNTH_OK)
    @patch("app.report_build_runner.derive_strategic_pov", return_value=_VALID_POV)
    def test_docx_404_until_built(self, _mock_pov, _mock_write, _mock_comp):
        snap = json.dumps(
            {
                "executive_report_md": _SYNTH_OK,
                "technical_report_md": "",
                "verification_pack": {"cluster_proofs": []},
                "executive_summary_data": {
                    "_metrics_snapshot": {"overlap_rate": 0.2},
                    "boardroom_summary": {"slides": []},
                },
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
