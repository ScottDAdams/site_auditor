"""Unit tests for strict AI insight validation (no API calls)."""

import unittest

from app.ai_validator import (
    validate_ai_output_strict,
)


def _minimal_valid() -> dict:
    return {
        "problem_type": "technical",
        "core_problem": "Duplicate URLs serve the same content and split crawl signals.",
        "why_it_matters": "Search engines may index multiple URLs for one intent.",
        "primary_action": "Apply 301 redirects and set one canonical URL per topic.",
        "execution_example": "Redirect duplicate paths to https://example.com/a using server rules.",
        "confidence": "Medium",
        "impact": "Moderate",
    }


_DOM = "technical"


class TestStrictValidator(unittest.TestCase):
    def test_case_1_banned_word_rejected(self):
        d = _minimal_valid()
        d["core_problem"] = "We should clarify which URL is canonical."
        with self.assertRaises(ValueError) as ctx:
            validate_ai_output_strict(d, _DOM)
        self.assertIn("Banned language", str(ctx.exception))

    def test_case_2_problem_action_mismatch(self):
        d = _minimal_valid()
        d["problem_type"] = "technical"
        d["primary_action"] = "Reposition the brand narrative on both URLs."
        with self.assertRaises(ValueError) as ctx:
            validate_ai_output_strict(d, _DOM)
        self.assertIn("strategic", str(ctx.exception).lower())

    def test_case_3_overlong_rejected(self):
        d = _minimal_valid()
        d["core_problem"] = "word " * 50
        with self.assertRaises(ValueError) as ctx:
            validate_ai_output_strict(d, _DOM)
        self.assertIn("too long", str(ctx.exception))

    def test_case_4_valid_passes(self):
        d = _minimal_valid()
        self.assertTrue(validate_ai_output_strict(d, _DOM))

    def test_problem_type_must_match_dominant(self):
        d = _minimal_valid()
        d["problem_type"] = "strategic"
        with self.assertRaises(ValueError) as ctx:
            validate_ai_output_strict(d, "technical")
        self.assertIn("dominant_problem_type", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
