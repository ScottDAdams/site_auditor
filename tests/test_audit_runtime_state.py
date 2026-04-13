"""DB-backed audit progress for multi-worker deploys."""

import unittest

from app.audit_runtime_state import get_audit_runtime, merge_audit_runtime
from app.db.models import AppSetting
from app.db.session import SessionLocal


class TestAuditRuntimeState(unittest.TestCase):
    def tearDown(self):
        with SessionLocal() as db:
            row = db.get(AppSetting, "audit.runtime.v1")
            if row:
                db.delete(row)
                db.commit()

    def test_merge_and_get_roundtrip(self):
        merge_audit_runtime(
            {
                "status": "running",
                "phase": "Crawling pages…",
                "error": None,
                "last_report_id": None,
                "summary_metrics": None,
            }
        )
        rt = get_audit_runtime()
        self.assertEqual(rt["status"], "running")
        self.assertIn("Crawling", rt["phase"])

        merge_audit_runtime({"phase": "Clustering…"})
        rt2 = get_audit_runtime()
        self.assertEqual(rt2["status"], "running")
        self.assertEqual(rt2["phase"], "Clustering…")


if __name__ == "__main__":
    unittest.main()
