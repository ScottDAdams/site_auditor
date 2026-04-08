"""Unit tests for strict AI insight validation (no API calls)."""

import unittest

from app.ai_validator import (
    validate_action_resolves_conflict,
    validate_ai_output_strict,
    validate_execution_example_contrast,
    validate_execution_example_url_binding,
    validate_primary_action_hard_constraints,
    validate_why_it_matters_stake,
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

    def test_vague_primary_action_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_primary_action_hard_constraints(
                "Differentiate positioning across the site without naming URLs"
            )
        self.assertIn("vague_action_phrase", str(ctx.exception))

    def test_primary_action_requires_page_anchor(self):
        with self.assertRaises(ValueError) as ctx:
            validate_primary_action_hard_constraints("Do the needful")
        self.assertIn("page_anchor", str(ctx.exception))

    def test_execution_example_requires_two_payload_urls(self):
        u1 = "https://a.example.com/p1"
        u2 = "https://b.example.com/p2"
        with self.assertRaises(ValueError):
            validate_execution_example_url_binding(
                f"Rewrite pages to be more distinct using {u1} only.",
                [u1, u2],
            )
        validate_execution_example_url_binding(
            f"On {u1} add NZ limits; on {u2} add AU pricing; remove shared hero copy.",
            [u1, u2],
        )

    def test_why_rejects_generic_ux(self):
        with self.assertRaises(ValueError) as ctx:
            validate_why_it_matters_stake(
                "This improves clarity and gives a better user experience."
            )
        self.assertIn("why_stake", str(ctx.exception))

    def test_why_requires_stake_signal(self):
        with self.assertRaises(ValueError) as ctx:
            validate_why_it_matters_stake("The site should be good for customers.")
        self.assertIn("why_stake", str(ctx.exception))

    def test_strategic_add_only_action_rejected(self):
        actx = {
            "dominant_problem_type": "strategic",
            "competing_pages_roles_required": False,
        }
        with self.assertRaises(ValueError) as ctx_exc:
            validate_action_resolves_conflict(
                "Add two new FAQ sections to each competing page.",
                actx,
            )
        self.assertIn("action_resolves_conflict", str(ctx_exc.exception))

    def test_execution_contrast_template(self):
        u1 = "https://a.example.com/p1"
        u2 = "https://b.example.com/p2"
        with self.assertRaises(ValueError):
            validate_execution_example_contrast(
                f"On {u1} update content. On {u2} update content the same way.",
                [u1, u2],
            )
        good = (
            f"On {u1}:\n"
            f"- remove: generic travel intro shared with AU\n"
            f"- add: NZ-specific claims examples\n\n"
            f"On {u2}:\n"
            f"- remove: shared global messaging\n"
            f"- add: AU pricing and local proof only\n"
        )
        validate_execution_example_contrast(good, [u1, u2])

    def test_structured_pass1_passes_full_strict(self):
        u1 = "https://www.scti.co.nz/our-policies/comprehensive"
        u2 = "https://www.scti.com.au/our-policies/comprehensive"
        d = {
            "structured_pass1": True,
            "problem_type": "strategic",
            "core_problem": (
                "AU and NZ policy pages serve the same decision intent with no market separation."
            ),
            "page_a_role": (
                "NZ policy page represents coverage, pricing, and claims for New Zealand residents."
            ),
            "page_b_role": (
                "AU policy page represents coverage, pricing, and claims for Australian residents."
            ),
            "primary_action": (
                f"Restrict {u1} to NZ-only messaging and remove shared blocks; "
                f"restrict {u2} to AU pricing and strip NZ references."
            ),
            "why_it_matters": (
                "High overlap_rate splits ranking signals and causes decision ambiguity between URLs."
            ),
            "execution_example": (
                f"On {u1}:\n"
                f"- remove: generic travel coverage intro used on AU pages\n"
                f"- add: NZ-specific claims examples and coverage limits\n\n"
                f"On {u2}:\n"
                f"- remove: shared global messaging\n"
                f"- add: AU pricing, testimonials, and policy details\n"
            ),
            "confidence": "High",
            "impact": "Moderate",
        }
        ctx = {
            "dominant_problem_type": "strategic",
            "competing_pages_roles_required": True,
            "page_a_url": u1,
            "page_b_url": u2,
            "candidate_urls": [u1, u2],
        }
        self.assertTrue(validate_ai_output_strict(d, "strategic", ctx))


if __name__ == "__main__":
    unittest.main()
