"""Phase 10 — narrative consolidation."""

import unittest

from app.narrative_consolidation import (
    build_consolidated_top_issues,
    cluster_findings,
    consolidate_clusters,
)


class TestNarrativeConsolidation(unittest.TestCase):
    def test_cluster_findings_groups_strategic(self):
        u1, u2 = "https://a.example.com/p1", "https://b.example.com/p2"
        payload = {
            "metrics": {"overlap_rate": 0.4, "content_uniqueness_score": 0.5},
            "clusters": [
                {
                    "decision_type": "differentiate",
                    "similarity": 0.9,
                    "dominant_url": u1,
                    "competing_urls": [u2],
                    "pages": [u1, u2],
                    "intent": "transactional",
                    "page_type": "product",
                }
            ],
            "pages": [],
        }
        raw = cluster_findings([], payload)
        keys = [c["cluster_key"] for c in raw]
        self.assertIn("overlap_same_intent", keys)
        self.assertEqual(raw[0]["meta"]["remediation_cluster_count"], 1)

    def test_consolidate_respects_differentiate_strategy(self):
        u1 = "https://www.scti.co.nz/p"
        u2 = "https://www.scti.com.au/p"
        payload = {
            "business_context": {"market_context": {"separate_regions": True}},
            "metrics": {"overlap_rate": 0.4, "avg_cluster_similarity": 0.88},
            "clusters": [
                {
                    "decision_type": "differentiate",
                    "similarity": 0.88,
                    "dominant_url": u1,
                    "competing_urls": [u2],
                    "pages": [u1, u2],
                    "intent": "transactional",
                    "page_type": "product",
                }
            ],
            "pages": [],
        }
        raw = cluster_findings([], payload)
        ps = {
            "strategy": "differentiate",
            "rules": {
                "allow_merge": False,
                "enforce_primary_direction": True,
            },
        }
        out = consolidate_clusters(raw, payload, ps)
        self.assertEqual(len(out), 1)
        self.assertIn("regional", out[0]["decision"].lower())
        self.assertNotRegex(
            out[0]["decision"].lower(),
            r"merge these pages into a single primary",
        )

    def test_build_consolidated_caps_three(self):
        payload = {
            "metrics": {"overlap_rate": 0.5, "content_uniqueness_score": 0.35},
            "clusters": [
                {
                    "decision_type": "differentiate",
                    "similarity": 0.9,
                    "dominant_url": "https://x.com/a",
                    "competing_urls": ["https://x.com/b"],
                    "pages": ["https://x.com/a", "https://x.com/b"],
                    "intent": "informational",
                    "page_type": "guide",
                },
                {
                    "decision_type": "technical_fix",
                    "similarity": 1.0,
                    "dominant_url": "https://x.com/c",
                    "competing_urls": ["https://x.com/c/"],
                    "pages": ["https://x.com/c", "https://x.com/c/"],
                    "technical_issue": "slash",
                    "technical_fix_recommendation": "Pick one canonical URL",
                },
            ],
            "pages": [
                {
                    "url": "https://x.com/thin",
                    "title": "Quote",
                    "word_count": 200,
                    "type": "product",
                    "classification": {
                        "intent": "transactional",
                        "decision_stage": "decision",
                    },
                    "internal_links_out": [],
                    "text_sample": "buy price quote cost " * 20,
                }
            ],
        }
        issues = build_consolidated_top_issues(payload, None, [], max_issues=3)
        self.assertLessEqual(len(issues), 3)
        self.assertGreaterEqual(len(issues), 1)


if __name__ == "__main__":
    unittest.main()
