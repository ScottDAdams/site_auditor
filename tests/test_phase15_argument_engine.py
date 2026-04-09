"""Phase 15: audit_signal, core argument, paths."""

import unittest

from app.reporting.audit_signal import audit_signal_path, build_audit_signal, load_audit_signal
from app.reporting.executive_writer import build_core_argument


class TestAuditSignal(unittest.TestCase):
    def test_build_and_load_roundtrip(self):
        summary = {
            "top_issues": [
                {
                    "problem": "Overlap",
                    "impact": "Splits demand",
                    "urls": ["https://a.com/x"],
                }
            ],
            "_metrics_snapshot": {"overlap_rate": 0.4},
        }
        vp = {
            "cluster_proofs": [
                {
                    "cluster_id": "c1",
                    "urls": ["https://a.com/x", "https://a.com/y"],
                    "similarity_score": 0.91,
                    "diff_summary": "Same blocks.",
                }
            ]
        }
        er = {"roadmap": [{"title": "Merge twins", "description": "Pick one URL"}]}
        ai = {"primary_action": "Consolidate duplicate routes."}
        metrics = {"avg_cluster_similarity": 0.88, "content_uniqueness_score": 0.12}
        sig = build_audit_signal(
            summary_data=summary,
            verification_pack=vp,
            execution_roadmap=er,
            ai_insights=ai,
            metrics=metrics,
        )
        self.assertTrue(sig["core_problem_candidates"])
        self.assertTrue(sig["top_clusters"])
        self.assertIn("overlap_rate", sig["key_metrics"])
        snap = {"audit_signal": sig, "executive_summary_data": {}}
        self.assertEqual(load_audit_signal(snap)["key_metrics"]["overlap_rate"], 0.4)

    def test_load_rebuilds_without_embedded_signal(self):
        snap = {
            "executive_summary_data": {
                "_metrics_snapshot": {"overlap_rate": 0.3},
                "top_issues": [],
            },
            "verification_pack": {},
            "execution_roadmap": {},
        }
        sig = load_audit_signal(snap)
        self.assertTrue(sig.get("priority_actions"))

    def test_audit_signal_path_ends_with_json(self):
        p = audit_signal_path(7)
        self.assertTrue(str(p).endswith("7/audit_signal.json"))


class TestCoreArgument(unittest.TestCase):
    def test_build_core_argument(self):
        pov = {
            "core_thesis": "Duplicate pages split one job.",
            "mechanism": "Teams ship parallel URLs.",
            "consequence": "Credit splinters.",
            "priority_action": "Pick one owner page.",
        }
        s = build_core_argument(pov)
        self.assertIn("because", s)
        self.assertIn("The fix is", s)


if __name__ == "__main__":
    unittest.main()
