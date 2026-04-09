"""Phase 14: strategic POV derivation shape and one-thesis sanity."""

import unittest

from app.reporting.executive_synthesis import (
    build_evidence_digest,
    one_thing_wrong_sentence,
    validate_strategic_pov,
)


class TestStrategicPov(unittest.TestCase):
    def test_validate_rejects_empty(self):
        self.assertGreater(len(validate_strategic_pov(None)), 0)
        self.assertGreater(len(validate_strategic_pov({})), 0)

    def test_validate_ok(self):
        pov = {
            "core_thesis": "The site splits one buyer job across competing URLs, starving conversion clarity.",
            "mechanism": "Parallel page factories and weak ownership let overlapping templates ship without reconciliation.",
            "consequence": "Demand fragments, experiments contradict, and spend scales inefficiency.",
            "priority_action": "Name one canonical owner page per major decision and retire or differentiate alternates.",
        }
        self.assertEqual(validate_strategic_pov(pov), [])

    def test_one_thing_wrong_is_single_sentence(self):
        pov = {
            "core_thesis": "They run multiple surfaces for the same purchase decision without a single owner.",
            "mechanism": "x" * 20,
            "consequence": "y" * 20,
            "priority_action": "z" * 20,
        }
        ans = one_thing_wrong_sentence(pov)
        self.assertLessEqual(len(ans.split()), 45)
        self.assertGreater(len(ans), 10)

    def test_evidence_digest_structured_only(self):
        vp = {
            "cluster_proofs": [
                {
                    "cluster_id": "c1",
                    "urls": ["https://a.com/x", "https://a.com/y"],
                    "diff_summary": "Same hero and FAQ block.",
                }
            ]
        }
        br = {"slides": [{"title": "Overlap is structural"}]}
        d = build_evidence_digest(vp, br)
        self.assertEqual(len(d["cluster_snippets"]), 1)
        self.assertEqual(d["cluster_snippets"][0]["url_count"], 2)
        self.assertIn("boardroom_notes", d)


if __name__ == "__main__":
    unittest.main()
