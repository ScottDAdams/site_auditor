"""Phase 12: report builder validation, enrichment, on-demand DOCX."""

import json
import unittest

from fastapi.testclient import TestClient

from app.db.models import AuditReport
from app.db.session import SessionLocal
from app.main import app
from app.reporting.executive_content import (
    enrich_executive_content,
    executive_docx_path,
    validate_executive_content,
)


def _docx_available() -> bool:
    try:
        import docx  # noqa: F401

        return True
    except Exception:
        return False


_MIN_MD = """01 Executive Summary
Core Problem: Overlap splits demand.
Primary Action: The correct move is to consolidate duplicate routes.
Business Impact: Conversion weakens when multiple URLs compete.

02 What Is Breaking Performance
1 — Issue
Problem: Duplicate paths.
Business impact: Demand scatters.
Action: Merge or redirect.

03 If You Do One Thing
The correct move is to pick one primary URL per decision.
Do this now because it removes the largest blocker.

04 Execution Plan
Week 1: Lock targets.

05 Risks of Inaction
- Spend rises without conversion lift.

06 Expected Outcomes
- Clearer capture on priority journeys.
"""


class TestExecutiveContent(unittest.TestCase):
    def test_validate_rejects_not_provided(self):
        bad = _MIN_MD.replace("Overlap splits demand.", "Not provided.")
        r = validate_executive_content(bad)
        self.assertFalse(r["ok"])

    def test_enrich_then_validate_ok(self):
        md, tech = enrich_executive_content(
            _MIN_MD,
            {
                "cluster_proofs": [
                    {
                        "cluster_id": "c1",
                        "urls": ["https://a.com/x", "https://a.com/y"],
                        "diff_summary": "Same structure.",
                        "similarity_score": 0.91,
                        "overlap_sections": [{"heading": "Coverage"}],
                    }
                ]
            },
            None,
            {"overlap_rate": 0.35, "cluster_count": 3},
        )
        self.assertIn("Cluster:", tech)
        v = validate_executive_content(md)
        self.assertTrue(v["ok"], msg=v.get("errors"))


@unittest.skipUnless(_docx_available(), "python-docx not installed")
class TestReportBuilderEndpoint(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_docx_404_until_built(self):
        snap = json.dumps(
            {
                "executive_report_md": _MIN_MD,
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
