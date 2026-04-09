"""Phase 14/15: strategic POV validation (audit_signal era)."""

import unittest

from app.reporting.evidence_selection import select_top_proof
from app.reporting.executive_pov import (
    one_thing_wrong_sentence,
    validate_strategic_pov,
)


class TestStrategicPov(unittest.TestCase):
    def test_validate_rejects_empty(self):
        self.assertGreater(len(validate_strategic_pov(None)), 0)
        self.assertGreater(len(validate_strategic_pov({})), 0)

    def test_validate_ok(self):
        pov = {
            "core_thesis": "The site ships duplicate product pages that answer one purchase decision.",
            "mechanism": "Parallel templates publish without a single owner URL per job.",
            "consequence": "Demand splits and tests contradict across live surfaces.",
            "priority_action": "Pick one canonical product URL and merge or split copy on the twin.",
        }
        self.assertEqual(validate_strategic_pov(pov), [])

    def test_rejects_too_long_thesis(self):
        pov = {
            "core_thesis": " ".join(["word"] * 30),
            "mechanism": "x" * 20,
            "consequence": "y" * 20,
            "priority_action": "z" * 20,
        }
        errs = validate_strategic_pov(pov)
        self.assertTrue(any("25 words" in e for e in errs))

    def test_rejects_buzzwords(self):
        pov = {
            "core_thesis": "The company has a strategic misalignment on pages.",
            "mechanism": "x" * 20,
            "consequence": "y" * 20,
            "priority_action": "z" * 20,
        }
        self.assertGreater(len(validate_strategic_pov(pov)), 0)

    def test_one_thing_wrong_is_single_sentence(self):
        pov = {
            "core_thesis": "They run twin URLs for one buyer decision without a single owner.",
            "mechanism": "x" * 20,
            "consequence": "y" * 20,
            "priority_action": "z" * 20,
        }
        ans = one_thing_wrong_sentence(pov)
        self.assertLessEqual(len(ans.split()), 25)
        self.assertGreater(len(ans), 10)

    def test_select_top_proof_max_three(self):
        signal = {
            "key_metrics": {
                "overlap_rate": 0.375,
                "avg_cluster_similarity": 0.9349,
                "content_uniqueness_score": 0.0651,
            },
            "top_clusters": [
                {
                    "description": "Policy pages repeat the same coverage copy.",
                    "similarity": 0.93,
                    "urls": ["https://a.com/nz/p", "https://a.com/au/p"],
                }
            ],
        }
        pov = {"core_thesis": "x"}
        lines = select_top_proof(signal, pov)
        self.assertLessEqual(len(lines), 3)
        self.assertTrue(any("37.5" in ln for ln in lines))


if __name__ == "__main__":
    unittest.main()
