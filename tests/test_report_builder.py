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

The site keeps several live URLs answering the same buyer question, so teams split ownership and measurement before any campaign change can read clearly.

## Audit Scorecard

Roughly four in ten crawled routes sit inside overlap clusters while paired pages mirror the same body story, which means the crawl repeats one narrative across multiple doors.

## If You Do One Thing

Pick one canonical URL for the strongest overlap pair and merge or visibly separate the twin page before funding more net-new routes.

## What Is Breaking Performance

Parallel paths carry near-identical copy for one job. Internal owners disagree on which surface should win. Paid and organic entries land in a fork. Experiments run on one URL while fixes ship on another, so lift never stacks.

## Growth Opportunities

Retiring redundant doors turns calendar time toward intents the crawl never covered because effort kept recycling the same pages under different addresses.

## 30-Day Execution Plan

Week one maps overlaps and names keepers. Week two executes merges and redirects. Week three repairs internal links and sitemaps. Week four reads conversion only after the fork closes.

## Risks of Delay

Extra weeks keep spend entering paired URLs and leave readouts noisy because the structural fork stays open.

## Expected Outcomes

One primary route per decision should restore clearer credit, calmer tests, and buyers meeting a single exhale instead of a tie between twins.
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
