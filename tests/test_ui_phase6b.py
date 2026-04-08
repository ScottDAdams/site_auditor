"""Phase 6B: app shell, routes, report structure (no audit run)."""

import json
import unittest

from fastapi.testclient import TestClient

from app.db.models import AuditReport
from app.db.session import SessionLocal
from app.main import app


class TestUIPhase6b(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_root_redirects_to_audit(self):
        r = self.client.get("/", follow_redirects=False)
        self.assertIn(r.status_code, (301, 302, 307, 308))
        self.assertIn("/audit", r.headers.get("location", ""))

    def test_audit_renders_in_layout(self):
        r = self.client.get("/audit")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Run Audit", r.content)
        self.assertIn(b"app-shell", r.content)
        self.assertIn(b"Site Auditor", r.content)
        self.assertIn(b"/reports", r.content)
        self.assertIn(b"/rules", r.content)

    def test_rules_page_loads_in_shell(self):
        r = self.client.get("/rules")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Content Rules Engine", r.content)
        self.assertIn(b"app-shell", r.content)

    def test_scoring_page_loads(self):
        r = self.client.get("/scoring")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Scoring weights", r.content)

    def test_reports_index_loads(self):
        r = self.client.get("/reports")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Reports", r.content)

    def test_report_detail_executive_and_technical_section(self):
        snap = json.dumps(
            {
                "executive_summary_data": {
                    "top_issues": [],
                    "execution_plan": [],
                    "site_health": {
                        "score": 70,
                        "primary_issue_type": "strategic",
                        "risk_level": "moderate",
                    },
                },
                "executive_summary_text": "Opening context in plain language.",
            }
        )
        with SessionLocal() as db:
            ar = AuditReport(
                domains="https://example.com",
                score=72,
                priority_level="medium",
                report_html='<div class="audit-report"><p>Technical body</p></div>',
                snapshot_json=snap,
            )
            db.add(ar)
            db.commit()
            rid = ar.id
        try:
            r = self.client.get(f"/reports/{rid}")
            self.assertEqual(r.status_code, 200)
            self.assertIn(b"Executive summary", r.content)
            self.assertIn(b"Technical details", r.content)
        finally:
            with SessionLocal() as db:
                row = db.get(AuditReport, rid)
                if row:
                    db.delete(row)
                    db.commit()

    def test_legacy_admin_redirects(self):
        r = self.client.get("/admin/decision-rules", follow_redirects=False)
        self.assertIn(r.status_code, (301, 302, 307, 308))
        self.assertIn("/rules", r.headers.get("location", ""))

    def test_ai_config_in_shell(self):
        r = self.client.get("/ai-config")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"AI configuration", r.content)


if __name__ == "__main__":
    unittest.main()
