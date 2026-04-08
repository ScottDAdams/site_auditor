"""Phase 6 executive summary layer (deterministic + validation)."""

import unittest

from app.executive_summary import (
    build_executive_summary_data,
    build_execution_plan,
    map_action_to_outcome,
    map_problem_to_business_impact,
    render_executive_summary,
    render_executive_summary_llm,
    validate_executive_alignment,
    validate_executive_output,
)


class TestExecutiveBusinessTranslation(unittest.TestCase):
    def test_map_problem_merge(self):
        s = map_problem_to_business_impact("merge", {})
        self.assertIn("ranking", s.lower())
        self.assertNotIn("overlap_rate", s.lower())

    def test_map_problem_differentiate(self):
        s = map_problem_to_business_impact("differentiate", {})
        self.assertIn("conversion", s.lower())

    def test_map_action_outcome_redirect(self):
        s = map_action_to_outcome("redirect")
        self.assertIn("canonical", s.lower())


class TestExecutiveTopIssues(unittest.TestCase):
    def _payload_base(self):
        u1 = "https://a.example.com/p1"
        u2 = "https://b.example.com/p2"
        return {
            "site_health_score": 62,
            "metrics": {"overlap_rate": 0.4, "avg_cluster_similarity": 0.9, "content_uniqueness_score": 0.3},
            "priority_score": 55.0,
            "priority_level": "medium",
            "structural_execution_order": [
                {
                    "cluster_index": 0,
                    "dominant_url": u1,
                    "priority_score": 60.0,
                    "priority_level": "medium",
                    "transformation_type": "merge",
                },
                {
                    "cluster_index": 1,
                    "dominant_url": u2,
                    "priority_score": 50.0,
                    "priority_level": "medium",
                    "transformation_type": "redirect",
                },
            ],
            "clusters": [
                {
                    "decision_type": "differentiate",
                    "similarity": 0.95,
                    "dominant_url": u1,
                    "competing_urls": [u2],
                    "pages": [u1, u2],
                },
                {
                    "decision_type": "differentiate",
                    "similarity": 0.85,
                    "dominant_url": u2,
                    "competing_urls": [u1],
                    "pages": [u2, u1],
                },
            ],
        }

    def test_top_issues_limited_and_ordered(self):
        p = self._payload_base()
        insights = {"problem_type": "strategic"}
        data = build_executive_summary_data(p, insights)
        self.assertLessEqual(len(data["top_issues"]), 5)
        self.assertEqual(data["top_issues"][0]["transformation_type"], "merge")
        self.assertIn("competing", data["top_issues"][0]["problem"].lower())

    def test_no_metric_first_in_render(self):
        p = self._payload_base()
        insights = {"problem_type": "strategic"}
        data = build_executive_summary_data(p, insights)
        text = render_executive_summary(data)
        validate_executive_alignment(data)
        validate_executive_output(text, data)
        self.assertNotRegex(text.lower(), r"overlap_rate\s+[0-9.]")
        self.assertNotIn("avg_cluster_similarity", text.lower())


class TestExecutionPlanOrdering(unittest.TestCase):
    def test_merge_bucket_before_redirect(self):
        summary_data = {
            "top_issues": [
                {
                    "transformation_type": "redirect",
                    "recommended_action": "Redirect X to Y",
                    "urls": ["https://y.com", "https://x.com"],
                },
                {
                    "transformation_type": "merge",
                    "recommended_action": "Merge A and B",
                    "urls": ["https://a.com", "https://b.com"],
                },
            ]
        }
        plan = build_execution_plan(summary_data)
        focuses = [s["focus"] for s in plan]
        self.assertIn("Consolidate duplicate pages", focuses)
        self.assertIn("Normalize technical duplicates", focuses)
        self.assertLess(focuses.index("Consolidate duplicate pages"), focuses.index("Normalize technical duplicates"))


class TestExecutiveValidation(unittest.TestCase):
    def test_rejects_metric_first_prose(self):
        with self.assertRaises(ValueError):
            validate_executive_output(
                "overlap_rate 0.37 causes signal fragmentation across pages.",
                None,
            )

    def test_llm_polish_consistency_mock(self):
        class MockLLM:
            def generate(self, prompt: str) -> str:
                return (
                    "Opening stays business-focused.\n\n"
                    "Top issues\n"
                    "1. [merge] These pages compete for the same purpose.\n"
                    "   Consequence: Search visibility splits.\n"
                    "   Action: Merge content into one page.\n"
                )

        p = {
            "site_health_score": 70,
            "metrics": {},
            "priority_score": 40.0,
            "priority_level": "low",
            "structural_execution_order": [],
            "clusters": [],
        }
        data = build_executive_summary_data(p, {"problem_type": "acceptable"})
        validate_executive_alignment(data)
        polished = render_executive_summary_llm(data, MockLLM())
        self.assertTrue(polished)
        validate_executive_output(polished, data)


if __name__ == "__main__":
    unittest.main()
