"""Phase 16: light validation and grounding rules."""

import unittest

from app.reporting.executive_content import MIN_SYNTHESIS_CHARS, validate_light


_BASE_AUDIT = {
    "key_metrics": {"overlap_rate": 0.2, "avg_cluster_similarity": 0.88},
    "core_problem_candidates": [],
    "top_clusters": [],
    "priority_actions": [],
}

_DOC = """Roughly 20.0% overlap and 0.8800 similarity drive the diagnosis. Twin URLs split credit; sample pairs repeat blocks. Canonicalize the top cluster first. Week 1–4 rollout. Noise persists without action. Clearer paths follow consolidation. """ * 8


class TestValidateLight(unittest.TestCase):
    def test_min_length_constant_sane(self):
        self.assertGreaterEqual(MIN_SYNTHESIS_CHARS, 200)

    def test_grounding_allows_percent_from_decimal_rate(self):
        r = validate_light(_DOC, _BASE_AUDIT)
        self.assertTrue(r["ok"], msg=r.get("errors"))

    def test_too_many_ungrounded_numbers_fails(self):
        bad = _DOC.replace("20.0%", "99.9%").replace("0.8800", "0.1234")
        bad = bad.replace("Week 1–4", "Week 1–4 with 77.7% drag")
        r = validate_light(bad, _BASE_AUDIT)
        self.assertFalse(r["ok"])


if __name__ == "__main__":
    unittest.main()
