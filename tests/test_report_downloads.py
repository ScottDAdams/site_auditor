"""Markdown downloads for executive and technical reports."""

import json
import unittest

from app.report_downloads import build_executive_markdown, build_technical_markdown


class TestReportMarkdownBuilders(unittest.TestCase):
    def test_executive_contains_sections(self):
        es = {
            "primary_bet": {
                "action": "Do the main thing",
                "why_this_over_others": "Because",
                "expected_effect": "Win",
            },
            "site_health": {"primary_issue_type": "strategic", "risk_level": "moderate"},
            "ceo_summary": {"paragraphs": ["Line one " * 5, "Line two " * 5]},
            "top_issues": [
                {
                    "cluster_key": "overlap_same_intent",
                    "transformation_type": "differentiate",
                    "problem": "Many pages overlap.",
                    "impact": "Splits demand.",
                    "decision": "You should separate roles.",
                    "risk_if_ignored": "Keeps splitting.",
                    "outcome": "Clearer paths.",
                    "urls": ["https://a.com/x"],
                }
            ],
            "execution_plan": [
                {"step": 1, "focus": "Clarify", "actions": ["Act one"]},
            ],
            "primary_strategy": {
                "label": "Differentiate",
                "reasoning": "Regions differ.",
            },
        }
        md = build_executive_markdown(
            es,
            domains="a.com",
            score=70,
            priority_level="medium",
            report_id=99,
        )
        self.assertIn("# Executive report", md)
        self.assertIn("## Primary decision", md)
        self.assertIn("### What's breaking performance", md)
        self.assertIn("overlap same intent", md.lower())
        self.assertIn("https://a.com/x", md)

    def test_technical_wraps_html_as_markdown(self):
        html = (
            '<div class="audit-report"><h2>Section</h2><p>Body <strong>bold</strong>.</p>'
            '<ul><li>One</li></ul></div>'
        )
        md = build_technical_markdown(
            html,
            domains="x.com",
            score=65,
            priority_level="low",
            report_id=3,
        )
        self.assertIn("# Technical audit", md)
        self.assertIn("## Full technical output", md)
        self.assertIn("Section", md)
        self.assertIn("bold", md)


if __name__ == "__main__":
    unittest.main()
