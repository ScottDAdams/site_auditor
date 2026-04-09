"""Phase 12/13: synthesized report validation and on-demand DOCX."""

import json
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.db.models import AuditReport
from app.db.session import SessionLocal
from app.main import app
from app.reporting.executive_content import executive_docx_path, validate_executive_content


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

_VALID_POV = {
    "core_thesis": "The company fragments demand by operating multiple URLs for the same buyer decision.",
    "mechanism": "Overlapping coverage and weak canonical ownership let teams optimize competing surfaces for one job-to-be-done.",
    "consequence": "Conversion credit splinters and paid spend feeds pages that compete with each other.",
    "priority_action": "Choose one primary page per major decision and merge or differentiate alternates explicitly.",
}


class TestExecutiveContent(unittest.TestCase):
    def test_validate_rejects_not_provided(self):
        bad = _SYNTH_OK.replace("dominant issue", "Not provided")
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
    @patch("app.main.synthesize_executive_report", return_value=_SYNTH_OK)
    @patch("app.main.derive_strategic_pov", return_value=_VALID_POV)
    def test_docx_404_until_built(self, _mock_pov, _mock_syn):
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

            built = self.client.post(f"/reports/{rid}/build")
            self.assertEqual(built.status_code, 200)
            data = built.json()
            self.assertEqual(data.get("status"), "success")
            self.assertIn("download_url", data)

            p = executive_docx_path(rid)
            self.assertTrue(p.is_file())
            dl = self.client.get(f"/reports/{rid}/download/executive.docx")
            self.assertEqual(dl.status_code, 200)
        finally:
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
