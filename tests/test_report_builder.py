import tempfile
import unittest
from pathlib import Path

from app.reporting.report_builder import build_executive_docx


def _docx_available() -> bool:
    try:
        import docx  # noqa: F401

        return True
    except Exception:
        return False


@unittest.skipUnless(_docx_available(), "python-docx not installed")
class TestReportBuilder(unittest.TestCase):
    def test_build_executive_docx_creates_file(self):
        md = """01 Executive Summary
Core Problem: Pages overlap and split demand.
Primary Action: The correct move is to consolidate duplicate pages.
Business Impact: Conversion is suppressed by mixed page ownership.

02 What Is Breaking Performance
01 — Duplicate Product Pages
Problem: Two pages serve the same decision.
Business Impact: Demand splits across competing URLs.
Action: Consolidate and redirect.
On Success: One page captures demand.

03 If You Do One Thing
PRIMARY ACTION: Consolidate duplicate pages.
WHY THIS FIRST: This is the highest leverage blocker.
EXPECTED RESULT: Clear ownership and stronger conversion flow.

04 Execution Plan
Week 1: Lock canonical ownership.
Week 2: Merge and redirect.
Week 3: Validate internal links.
Week 4: Review impact.

05 Risks of Inaction
- Ongoing demand leakage.
- Wasted paid spend.

06 Expected Outcomes
- Higher conversion capture.
- Stronger authority.
"""
        technical = """Cluster: Overlap 1
URLs:
https://a.com/x
https://a.com/y
Example: NZ and AU pages repeat the same coverage explanation.
Interpretation: Structure is effectively identical.
"""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            md_path = tdp / "executive_report.md"
            out_path = tdp / "executive_report_final.docx"
            tech_path = tdp / "technical_report.md"
            md_path.write_text(md, encoding="utf-8")
            tech_path.write_text(technical, encoding="utf-8")

            build_executive_docx(str(md_path), str(out_path))
            self.assertTrue(out_path.exists())
            self.assertGreater(out_path.stat().st_size, 2048)


if __name__ == "__main__":
    unittest.main()

