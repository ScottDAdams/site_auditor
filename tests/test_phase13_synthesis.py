"""Phase 13: executive synthesis validation and DOCX from synthesized Markdown only."""

import json
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.db.models import AuditReport
from app.db.session import SessionLocal
from app.main import app
from app.reporting.executive_content import (
    executive_docx_path,
    executive_synthesized_md_path,
    validate_executive_content,
)
from app.reporting.report_builder import build_executive_docx


def _docx_available() -> bool:
    try:
        import docx  # noqa: F401

        return True
    except Exception:
        return False


_SYNTH_OK = """## Executive Summary

The dominant issue is structural overlap across buyer journeys. Multiple URLs compete for the same decision, which fragments demand and weakens conversion. The audit shows meaningful cluster concentration that should be resolved before scaling content production.

## Audit Scorecard

Overlap intensity is elevated relative to a healthy site baseline, meaning paid and organic traffic may land on competing pages. Cluster count indicates several distinct duplication themes rather than one-off duplicates.

## If You Do One Thing

Consolidate or differentiate the top overlapping cluster first. This must happen first because it removes the largest source of split demand before you invest in new pages or campaigns.

## What Is Breaking Performance

### Theme one — Competing landing paths
Problem: Two routes answer the same buyer question.
Business impact: Conversion credit scatters and optimization becomes noisy.
Action: Pick one primary URL and redirect or merge the alternate.
Outcome: One owner per decision with clearer measurement.

### Theme two — Thin differentiation
Problem: Pages repeat the same narrative with minor variants.
Business impact: Search and internal discovery dilute authority.
Action: Merge redundant copy and strengthen one canonical narrative.
Outcome: Stronger relevance signals and less crawl waste.

## Growth Opportunities

You can capture leverage by turning duplicated coverage into one authoritative page and using freed capacity for net-new intent gaps identified in the technical findings.

## 30-Day Execution Plan

Week one: Inventory overlaps and lock canonical targets. Week two: Implement merges and redirects with analytics validation. Week three: Refresh internal links and sitemaps. Week four: Measure conversion and search visibility shifts.

## Risks of Delay

Delay means continued spend against competing URLs, slower experiment readouts, and harder attribution during seasonal demand.

## Expected Outcomes

Resolving overlap first should improve capture efficiency on priority journeys and align teams around a single narrative per buyer decision, consistent with the structural issues above.
"""


class TestSynthesisValidation(unittest.TestCase):
    def test_validate_rejects_not_provided(self):
        bad = _SYNTH_OK.replace("dominant issue", "Not provided")
        r = validate_executive_content(bad)
        self.assertFalse(r["ok"])

    def test_validate_requires_sections(self):
        short = "## Executive Summary\n\nToo short.\n\n" + "\n".join(
            f"## {t}\n\n" + ("x " * 30) for t in (
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
        dup = _SYNTH_OK + "\n## Executive Summary\n\nMore text " + "x " * 40
        r = validate_executive_content(dup)
        self.assertFalse(r["ok"])


@unittest.skipUnless(_docx_available(), "python-docx not installed")
class TestBuildUsesSynthesisOnly(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.main.synthesize_executive_report", return_value=_SYNTH_OK)
    def test_build_writes_synthesized_and_docx(self, _mock_syn):
        snap = json.dumps(
            {
                "executive_report_md": "legacy md",
                "technical_report_md": "tech md",
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
            r = self.client.post(f"/reports/{rid}/build")
            self.assertEqual(r.status_code, 200, msg=r.content)
            syn = executive_synthesized_md_path(rid)
            self.assertTrue(syn.is_file())
            self.assertNotIn("Not provided", syn.read_text(encoding="utf-8").lower())
            p = executive_docx_path(rid)
            self.assertTrue(p.is_file())
        finally:
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
        "app.main.synthesize_executive_report",
        return_value="## Executive Summary\n\nShort.",
    )
    def test_build_422_when_validation_fails(self, _mock_syn):
        snap = json.dumps(
            {
                "executive_report_md": "x",
                "technical_report_md": "",
                "executive_summary_data": {},
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
            r = self.client.post(f"/reports/{rid}/build")
            self.assertEqual(r.status_code, 422)
            self.assertFalse(executive_docx_path(rid).is_file())
        finally:
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
