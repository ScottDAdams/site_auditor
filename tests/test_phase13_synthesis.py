"""Phase 13/15: executive validation and DOCX from synthesized Markdown."""

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
    strategic_pov_path,
    validate_executive_content,
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


class TestSynthesisValidation(unittest.TestCase):
    def test_validate_rejects_not_provided(self):
        bad = _SYNTH_OK.replace("buyer question", "Not provided")
        r = validate_executive_content(bad)
        self.assertFalse(r["ok"])

    def test_validate_requires_sections(self):
        short = "## Executive Summary\n\nToo short words here.\n\n" + "\n".join(
            f"## {t}\n\n" + ("word " * 20) for t in (
                "Audit Scorecard",
                "If You Do One Thing",
                "What Is Breaking Performance",
                "Growth Opportunities",
                "30-Day Execution Plan",
                "Risks of Delay",
                "Expected Outcomes",
            )
        )
        r = validate_executive_content(short)
        self.assertFalse(r["ok"])

    def test_validate_ok_full_doc(self):
        r = validate_executive_content(_SYNTH_OK)
        self.assertTrue(r["ok"], msg=r.get("errors"))

    def test_duplicate_h2_fails(self):
        dup = _SYNTH_OK + "\n## Executive Summary\n\nMore padding " + "word " * 40
        r = validate_executive_content(dup)
        self.assertFalse(r["ok"])

    def test_validate_rejects_banned_filler(self):
        bad = _SYNTH_OK.replace(
            "instead of a tie between twins.",
            "instead of a tie between twins. This highlights the failure mode.",
        )
        r = validate_executive_content(bad)
        self.assertFalse(r["ok"])

    def test_validate_still_allows_common_business_words(self):
        ok = _SYNTH_OK.replace(
            "clearer credit",
            "clearer credit and a strategic shift in how pages earn demand",
        )
        r = validate_executive_content(ok)
        self.assertTrue(r["ok"], msg=r.get("errors"))

    def test_validate_rejects_excessive_percent_metrics(self):
        spam = " ".join(f"{i}.0%" for i in range(20))
        bad = _SYNTH_OK.replace("The site keeps", spam + " The site keeps")
        r = validate_executive_content(bad)
        self.assertFalse(r["ok"])


@unittest.skipUnless(_docx_available(), "python-docx not installed")
class TestBuildUsesSynthesisOnly(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.report_build_runner.compress_report", side_effect=lambda x: x)
    @patch("app.report_build_runner.write_executive_report", return_value=_SYNTH_OK)
    @patch("app.report_build_runner.derive_strategic_pov", return_value=_VALID_POV)
    def test_build_writes_artifacts_and_docx(self, _mock_pov, _mock_write, _mock_comp):
        snap = json.dumps(
            {
                "executive_report_md": "legacy",
                "technical_report_md": "tech",
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
            r = self.client.post(f"/reports/{rid}/build?sync=1")
            self.assertEqual(r.status_code, 200, msg=r.content)
            self.assertEqual(r.json().get("status"), "success")
            self.assertTrue(strategic_pov_path(rid).is_file())
            syn = executive_synthesized_md_path(rid)
            self.assertTrue(syn.is_file())
            self.assertNotIn("not provided", syn.read_text(encoding="utf-8").lower())
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
    @patch("app.report_build_runner.compress_report", side_effect=lambda x: x)
    @patch(
        "app.report_build_runner.write_executive_report",
        return_value="## Executive Summary\n\nToo few words.",
    )
    @patch("app.report_build_runner.derive_strategic_pov", return_value=_VALID_POV)
    def test_build_422_when_validation_fails(self, _mock_pov, _mock_write, _mock_comp):
        snap = json.dumps(
            {
                "executive_report_md": "x",
                "technical_report_md": "",
                "executive_summary_data": {},
                "verification_pack": {},
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
