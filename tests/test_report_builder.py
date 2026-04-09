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


_MD = """## Executive Summary

The dominant issue is structural overlap. Multiple URLs compete for the same decision, which fragments demand.

## Audit Scorecard

Overlap intensity is elevated. Cluster count indicates several duplication themes.

## If You Do One Thing

Consolidate the top overlapping cluster first because it removes the largest source of split demand.

## What Is Breaking Performance

### Theme one
Problem: Competing paths.
Business impact: Credit scatters.
Action: Pick one primary URL.
Outcome: Clearer measurement.

## Growth Opportunities

Turn duplicated coverage into one authoritative page.

## 30-Day Execution Plan

Week one: Inventory overlaps. Week two: Implement merges. Week three: Fix links. Week four: Measure.

## Risks of Delay

Continued spend against competing URLs and slower readouts.

## Expected Outcomes

Improved capture efficiency on priority journeys.
"""


@unittest.skipUnless(_docx_available(), "python-docx not installed")
class TestReportBuilder(unittest.TestCase):
    def test_build_executive_docx_creates_file(self):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            md_path = tdp / "executive_synthesized.md"
            out_path = tdp / "executive.docx"
            md_path.write_text(_MD, encoding="utf-8")

            build_executive_docx(str(md_path), str(out_path))
            self.assertTrue(out_path.exists())
            self.assertGreater(out_path.stat().st_size, 2048)


if __name__ == "__main__":
    unittest.main()
