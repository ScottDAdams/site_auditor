"""Phase 16 / 16.2: consulting validation rules."""

import unittest

from app.reporting.executive_content import MIN_SYNTHESIS_CHARS, validate_light
from tests.fixtures_executive_synth import SYNTH_OK


_BASE_AUDIT = {
    "key_metrics": {"overlap_rate": 0.2, "avg_cluster_similarity": 0.88},
    "core_problem_candidates": [],
    "top_clusters": [],
    "priority_actions": [],
}


class TestValidateLight(unittest.TestCase):
    def test_min_length_constant_sane(self):
        self.assertGreaterEqual(MIN_SYNTHESIS_CHARS, 200)

    def test_fixture_passes(self):
        r = validate_light(SYNTH_OK, _BASE_AUDIT)
        self.assertTrue(r["ok"], msg=r.get("errors"))

    def test_banned_phrase_fails(self):
        bad = SYNTH_OK + "\n\nThis is a significant problem."
        r = validate_light(bad, _BASE_AUDIT)
        self.assertFalse(r["ok"])
        self.assertTrue(any("Banned" in e for e in r["errors"]))

    def test_too_many_ungrounded_numbers_fails(self):
        bad = SYNTH_OK.replace("20.0%", "99.9%").replace("0.8800", "0.1234")
        bad = bad.replace("0.8800", "0.1111")  # already replaced above if duplicate
        bad += " Extra noise: 55.5% and 66.6% drag on tests."
        r = validate_light(bad, _BASE_AUDIT)
        self.assertFalse(r["ok"])


if __name__ == "__main__":
    unittest.main()
