import unittest

from app.boardroom_summary import build_boardroom_summary
from app.executive_narrative import generate_executive_narrative, validate_executive_narrative
from app.verification_pack import build_verification_pack


class TestPhase11Narrative(unittest.TestCase):
    def _brief(self):
        return {
            "top_issues": [
                {
                    "problem": "Two product pages serve the same decision.",
                    "business_consequence": "Demand splits across duplicate paths and conversion stalls.",
                    "decision": "The correct move is to merge duplicate product pages into one owner.",
                    "risk_if_ignored": "Spend rises while split demand suppresses conversion performance.",
                    "outcome": "One page captures demand and improves conversion flow.",
                    "decision_rationale": (
                        "The correct move is to merge because evidence shows repeated structure for the same buyer decision."
                    ),
                }
            ],
            "primary_bet": {
                "action": "The correct move is to merge duplicate product pages into one owner.",
                "why_this_over_others": "This removes the highest structural blocker now.",
                "expected_effect": "Demand concentration and stronger conversion flow.",
            },
            "execution_plan": [
                {
                    "focus": "Consolidate duplicate pages",
                    "actions": [
                        "Merge route A into route B.",
                        "Redirect old URL to the canonical page.",
                    ],
                }
            ],
            "verification_pack": {
                "cluster_proofs": [
                    {
                        "urls": ["https://a.com/x", "https://a.com/y"],
                        "diff_summary": "Both pages follow the same structure with minor wording differences.",
                        "overlap_sections": [
                            {"heading": "Coverage", "url_a_text": "A", "url_b_text": "B", "similarity_estimate": 0.9}
                        ],
                    }
                ]
            },
        }

    def test_narrative_rejects_raw_metrics(self):
        bad = """01 Executive Summary
The correct move is to merge.
overlap_rate 0.37 shows conflict.
02 What Is Breaking Performance
test
03 If You Do One Thing
test
04 Execution Plan
test
05 Risks of Inaction
test
06 Expected Outcomes
test"""
        with self.assertRaises(ValueError):
            validate_executive_narrative(bad)

    def test_narrative_one_primary_decision(self):
        out = generate_executive_narrative(
            {"openai_enabled": False},
            "# Technical report\n",
            self._brief(),
        )["executive_report_md"]
        self.assertEqual(out.lower().count("the correct move is to"), 1)
        validate_executive_narrative(out)


class TestPhase11Verification(unittest.TestCase):
    def test_verification_pack_includes_overlap_sections(self):
        payload = {
            "pages": [
                {
                    "url": "https://a.com/x",
                    "text_sample": "Coverage\nPlan details and limits\n\nEligibility\nWho is covered and exclusions",
                },
                {
                    "url": "https://a.com/y",
                    "text_sample": "Coverage\nPlan details with minor wording updates\n\nEligibility\nWho is covered and exclusions",
                },
            ]
        }
        clusters = [
            {
                "cluster_id": "c1",
                "dominant_url": "https://a.com/x",
                "competing_urls": ["https://a.com/y"],
                "similarity": 0.92,
            }
        ]
        vp = build_verification_pack(payload, clusters)
        self.assertEqual(len(vp["cluster_proofs"]), 1)
        proof = vp["cluster_proofs"][0]
        self.assertGreater(proof["similarity_score"], 0.5)
        self.assertTrue(len(proof["overlap_sections"]) >= 1)

    def test_end_to_end_outputs_present(self):
        brief = {
            "top_issues": [
                {
                    "problem": "Duplicate pages compete.",
                    "business_consequence": "Demand splits and conversion efficiency drops.",
                    "decision": "The correct move is to merge these duplicates.",
                    "risk_if_ignored": "Suppressed growth and wasted spend continue.",
                    "outcome": "Demand concentrates on one page.",
                    "decision_rationale": "The correct move is to merge because sampled sections are repeated.",
                }
            ],
            "primary_bet": {
                "action": "The correct move is to merge these duplicates.",
                "why_this_over_others": "This removes the largest blocker first.",
                "expected_effect": "Faster wins and less wasted effort.",
            },
            "execution_plan": [{"focus": "Consolidate", "actions": ["Merge", "Redirect"]}],
            "site_health": {"risk_level": "high", "primary_issue_type": "strategic"},
            "impact_estimate": {"impact_level": "High", "confidence": "Strong", "reasoning": "Material split in demand."},
            "ceo_summary": {"paragraphs": ["Clear issue line that matters to revenue and conversion outcomes."] * 2},
            "expected_outcome": {"bullets": ["Stronger authority", "Clear paths", "Better conversion"]},
            "strategic_risks": [{"risk": "Ongoing duplication", "consequence": "Demand stays split."}],
        }
        vp = {"cluster_proofs": [{"urls": ["https://a.com/x", "https://a.com/y"], "diff_summary": "Same structure", "overlap_sections": []}]}
        brief["verification_pack"] = vp
        br = build_boardroom_summary(brief)
        nr = generate_executive_narrative({"openai_enabled": False}, "# Technical", brief)

        self.assertIn("slides", br)
        self.assertEqual(len(br["slides"]), 10)
        self.assertTrue(nr.get("executive_report_md"))
        self.assertIn("cluster_proofs", vp)


if __name__ == "__main__":
    unittest.main()

