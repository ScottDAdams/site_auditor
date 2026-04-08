"""Phase 5: transformation taxonomy, keep_both, priority scoring, execution order."""

import unittest

from app.ai_insights import generate_ai_insights
from app.ai_validator import validate_primary_action_matches_transformation_type
from app.priority_scoring import assign_execution_order, compute_structural_priority
from app.transformation_spec import build_transformation_spec, render_insights_from_spec
from app.transformation_types import infer_transformation_type


class DummyLLM:
    pass


class TestPhase5TransformationType(unittest.TestCase):
    def test_merge_when_high_similarity_low_uniqueness(self):
        u1 = "https://example.com/a"
        u2 = "https://example.com/b"
        payload = {
            "dominant_problem_type": "strategic",
            "business_context": {"market_context": {"separate_regions": False}},
            "metrics": {
                "overlap_rate": 0.5,
                "avg_cluster_similarity": 0.95,
                "content_uniqueness_score": 0.05,
            },
            "clusters": [
                {
                    "decision_type": "differentiate",
                    "duplication_class": "competitive",
                    "similarity": 0.95,
                    "dominant_url": u1,
                    "competing_urls": [u2],
                    "pages": [u1, u2],
                    "page_type": "policy",
                    "intent": "coverage",
                    "decision_stage": "evaluate",
                }
            ],
            "page_urls": [u1, u2],
        }
        spec = build_transformation_spec(payload)
        self.assertEqual(spec["transformation_type"], "merge")
        self.assertFalse(spec["keep_both"])
        rendered = render_insights_from_spec(payload, "strategic", spec)
        self.assertIn("Merge", rendered["primary_action"])

    def test_redirect_technical(self):
        u1 = "https://example.com/canonical"
        u2 = "https://www.example.com/alias"
        payload = {
            "dominant_problem_type": "technical",
            "business_context": {},
            "metrics": {
                "overlap_rate": 0.3,
                "avg_cluster_similarity": 0.9,
                "content_uniqueness_score": 0.2,
            },
            "clusters": [],
            "technical_fix_urls": [u1, u2],
            "page_urls": [u1, u2],
        }
        spec = build_transformation_spec(payload)
        self.assertEqual(spec["transformation_type"], "redirect")
        self.assertFalse(spec["keep_both"])

    def test_differentiate_cross_market_not_merge(self):
        u1 = "https://www.scti.co.nz/p"
        u2 = "https://www.scti.com.au/p"
        payload = {
            "dominant_problem_type": "strategic",
            "business_context": {"market_context": {"separate_regions": True}},
            "metrics": {
                "overlap_rate": 0.4,
                "avg_cluster_similarity": 0.88,
                "content_uniqueness_score": 0.5,
            },
            "clusters": [
                {
                    "decision_type": "differentiate",
                    "duplication_class": "competitive",
                    "similarity": 0.88,
                    "dominant_url": u1,
                    "competing_urls": [u2],
                    "pages": [u1, u2],
                    "page_type": "policy",
                    "intent": "coverage",
                    "decision_stage": "evaluate",
                }
            ],
            "page_urls": [u1, u2],
        }
        spec = build_transformation_spec(payload)
        self.assertEqual(spec["transformation_type"], "differentiate")
        self.assertTrue(spec["keep_both"])
        out = render_insights_from_spec(payload, "strategic", spec)
        self.assertIn("Restrict", out["primary_action"])

    def test_cross_market_infer_wins_over_near_duplicate_merge(self):
        payload = {
            "dominant_problem_type": "strategic",
            "business_context": {"market_context": {"separate_regions": True}},
            "metrics": {
                "overlap_rate": 0.5,
                "avg_cluster_similarity": 0.94,
                "content_uniqueness_score": 0.05,
            },
        }
        tt = infer_transformation_type(
            payload, "strategic", "cross_market", 2, row_similarity=0.94
        )
        self.assertEqual(tt, "differentiate")

    def test_validator_rejects_differentiate_word_for_merge_type(self):
        with self.assertRaises(ValueError) as ctx:
            validate_primary_action_matches_transformation_type(
                {
                    "transformation_type": "merge",
                    "primary_action": "Differentiate the two URLs and merge them later.",
                }
            )
        self.assertIn("primary_action_vs_type", str(ctx.exception))

    def test_scoring_monotonic_with_overlap(self):
        base = {
            "clusters": [
                {
                    "decision_type": "differentiate",
                    "similarity": 0.8,
                    "dominant_url": "https://a.com",
                    "competing_urls": ["https://b.com"],
                    "pages": ["https://a.com", "https://b.com"],
                }
            ],
        }
        low = compute_structural_priority(
            {
                **base,
                "metrics": {
                    "overlap_rate": 0.1,
                    "avg_cluster_similarity": 0.5,
                    "content_uniqueness_score": 0.5,
                },
            }
        )
        high = compute_structural_priority(
            {
                **base,
                "metrics": {
                    "overlap_rate": 0.9,
                    "avg_cluster_similarity": 0.5,
                    "content_uniqueness_score": 0.5,
                },
            }
        )
        self.assertGreater(high["priority_score"], low["priority_score"])

    def test_assign_execution_order_by_score_then_type(self):
        issues = [
            {"priority_score": 50.0, "transformation_type": "differentiate"},
            {"priority_score": 50.0, "transformation_type": "merge"},
            {"priority_score": 30.0, "transformation_type": "redirect"},
        ]
        ordered = assign_execution_order(issues)
        self.assertEqual(ordered[0]["transformation_type"], "merge")
        self.assertEqual(ordered[1]["transformation_type"], "differentiate")
        self.assertEqual(ordered[2]["transformation_type"], "redirect")

    def test_generate_insights_includes_phase5_fields(self):
        u1 = "https://www.scti.co.nz/p"
        u2 = "https://www.scti.com.au/p"
        payload = {
            "dominant_problem_type": "strategic",
            "business_context": {"market_context": {"separate_regions": True}},
            "metrics": {
                "overlap_rate": 0.4,
                "avg_cluster_similarity": 0.88,
                "content_uniqueness_score": 0.5,
            },
            "clusters": [
                {
                    "decision_type": "differentiate",
                    "duplication_class": "competitive",
                    "similarity": 0.88,
                    "dominant_url": u1,
                    "competing_urls": [u2],
                    "pages": [u1, u2],
                    "page_type": "policy",
                    "intent": "coverage",
                    "decision_stage": "evaluate",
                }
            ],
            "page_urls": [u1, u2],
            "technical_fix_urls": [],
            "priority_score": 55.5,
            "priority_level": "medium",
            "transformation_spec": build_transformation_spec(
                {
                    "dominant_problem_type": "strategic",
                    "business_context": {"market_context": {"separate_regions": True}},
                    "metrics": {
                        "overlap_rate": 0.4,
                        "avg_cluster_similarity": 0.88,
                        "content_uniqueness_score": 0.5,
                    },
                    "clusters": [
                        {
                            "decision_type": "differentiate",
                            "duplication_class": "competitive",
                            "similarity": 0.88,
                            "dominant_url": u1,
                            "competing_urls": [u2],
                            "pages": [u1, u2],
                            "page_type": "policy",
                            "intent": "coverage",
                            "decision_stage": "evaluate",
                        }
                    ],
                    "page_urls": [u1, u2],
                }
            ),
        }
        out = generate_ai_insights(payload, DummyLLM())
        self.assertEqual(out["transformation_type"], "differentiate")
        self.assertTrue(out["keep_both"])
        self.assertEqual(out["priority_score"], 55.5)
        self.assertEqual(out["priority_level"], "medium")


if __name__ == "__main__":
    unittest.main()
