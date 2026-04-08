"""Phase 8 — opportunity_clusters heuristics."""

import unittest

from app.opportunity_analysis import analyze_opportunities


class TestOpportunityAnalysis(unittest.TestCase):
    def test_empty_payload_returns_empty(self):
        self.assertEqual(analyze_opportunities({}), [])
        self.assertEqual(analyze_opportunities({"pages": []}), [])

    def test_returns_up_to_three_ordered_types(self):
        pages = [
            {
                "url": "https://example.com/faq",
                "title": "FAQ",
                "word_count": 220,
                "type": "faq",
                "classification": {
                    "page_type": "faq",
                    "intent": "informational",
                    "decision_stage": "awareness",
                },
                "internal_links_out": ["https://example.com/"],
                "text_sample": "FAQ frequently asked questions? " * 6,
            },
            {
                "url": "https://example.com/quote",
                "title": "Get a quote",
                "word_count": 120,
                "type": "product",
                "classification": {
                    "page_type": "product",
                    "intent": "transactional",
                    "decision_stage": "decision",
                },
                "internal_links_out": [],
                "text_sample": "buy now price cost quote",
            },
            {
                "url": "https://example.com/hero-product",
                "title": "Main product",
                "word_count": 900,
                "type": "product",
                "classification": {
                    "page_type": "product",
                    "intent": "transactional",
                    "decision_stage": "consideration",
                },
                "internal_links_out": ["https://example.com/faq"],
                "text_sample": "coverage policy benefits premium claim",
            },
        ]
        payload = {
            "pages": pages,
            "metrics": {"content_uniqueness_score": 0.35},
        }
        out = analyze_opportunities(payload)
        self.assertGreaterEqual(len(out), 1)
        types = [o["type"] for o in out]
        self.assertEqual(types[0], "structured_data")
        self.assertLessEqual(len(out), 3)
        for o in out:
            self.assertIn("title", o)
            self.assertIn("pages", o)
            self.assertIn("opportunity", o)
            self.assertIn("impact", o)
            self.assertIn("action", o)
            self.assertTrue(o["pages"])


if __name__ == "__main__":
    unittest.main()
