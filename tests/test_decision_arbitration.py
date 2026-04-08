"""Phase 9 — decision arbitration and strategy alignment."""

import unittest

from app.decision_arbitration import (
    resolve_primary_strategy,
    validate_narrative_against_strategy,
    validate_roadmap_against_strategy,
)


class TestResolvePrimaryStrategy(unittest.TestCase):
    def test_cross_market_separate_regions_differentiate(self):
        spec = {
            "cluster_relationship": "cross_market",
            "keep_both": True,
            "transformation_type": "differentiate",
            "page_a_url": "https://a.co.nz/p",
            "page_b_url": "https://a.com.au/p",
        }
        payload = {"transformation_spec": spec, "metrics": {}}
        out = resolve_primary_strategy(payload, {}, [])
        self.assertEqual(out["strategy"], "differentiate")
        self.assertFalse(out["rules"]["allow_merge"])

    def test_merge_strategy_when_keep_both_false(self):
        spec = {
            "cluster_relationship": "intra_market",
            "keep_both": False,
            "transformation_type": "merge",
            "page_a_url": "https://x.com/a",
            "page_b_url": "https://x.com/b",
        }
        payload = {"transformation_spec": spec, "metrics": {}}
        out = resolve_primary_strategy(payload, {}, [])
        self.assertEqual(out["strategy"], "merge")
        self.assertFalse(out["rules"]["allow_differentiation"])


class TestValidateNarrativeAgainstStrategy(unittest.TestCase):
    def test_differentiate_rejects_merge_into_one(self):
        ps = {
            "strategy": "differentiate",
            "rules": {
                "allow_merge": False,
                "enforce_primary_direction": True,
            },
        }
        bad = "You should merge overlapping pages into a single primary page for this topic."
        with self.assertRaises(ValueError) as ctx:
            validate_narrative_against_strategy(bad, ps)
        self.assertIn("strategy_narrative_merge", str(ctx.exception))


class TestValidateRoadmapAgainstStrategy(unittest.TestCase):
    def test_differentiate_blocks_merge_step(self):
        ps = {
            "strategy": "differentiate",
            "rules": {
                "allow_merge": False,
                "enforce_primary_direction": True,
            },
        }
        obj = {
            "roadmap": [
                {
                    "step": 1,
                    "action_type": "merge",
                    "title": "Merge duplicates",
                    "description": "Combine into one page.",
                    "target_urls": ["https://a.com/x", "https://a.com/y"],
                    "page_changes": [],
                    "expected_outcome": "One canonical URL.",
                    "evidence_refs": [],
                },
            ]
        }
        self.assertFalse(validate_roadmap_against_strategy(obj, ps))


if __name__ == "__main__":
    unittest.main()
