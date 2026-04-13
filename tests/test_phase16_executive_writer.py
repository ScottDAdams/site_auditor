"""Phase 16: light validation and grounding rules."""

import unittest

from app.reporting.executive_content import LIGHT_REQUIRED_SECTIONS, validate_light


_BASE_AUDIT = {
    "key_metrics": {"overlap_rate": 0.2, "avg_cluster_similarity": 0.88},
    "core_problem_candidates": [],
    "top_clusters": [],
    "priority_actions": [],
}

_DOC = """## Executive Summary

Roughly 20.0% overlap and 0.8800 similarity drive the diagnosis.

## Core Problem

Twin URLs.

## Why It Matters

Splits credit.

## Evidence

Sample pairs repeat blocks.

## Recommended Action

Canonicalize.

## Execution Plan

Week 1–4 rollout.

## Risks of Inaction

Noise persists.

## Expected Outcomes

Clearer paths.
"""


class TestValidateLight(unittest.TestCase):
    def test_required_sections_constant(self):
        self.assertEqual(len(LIGHT_REQUIRED_SECTIONS), 8)

    def test_grounding_allows_percent_from_decimal_rate(self):
        r = validate_light(_DOC, _BASE_AUDIT)
        self.assertTrue(r["ok"], msg=r.get("errors"))

    def test_too_many_ungrounded_numbers_fails(self):
        # validate_light flags when more than two metric tokens lack grounding
        bad = _DOC.replace("20.0%", "99.9%").replace("0.8800", "0.1234")
        bad = bad.replace("Week 1–4", "Week 1–4 with 77.7% drag")
        r = validate_light(bad, _BASE_AUDIT)
        self.assertFalse(r["ok"])


if __name__ == "__main__":
    unittest.main()
