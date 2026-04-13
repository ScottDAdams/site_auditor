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

Roughly 20.0% overlap and 0.8800 similarity appear in the crawl sample.

## Core Problem

Overlapping URLs.

## Why It Matters

Splits demand.

## Evidence

Paired pages repeat structure.

## Recommended Action

Consolidate the top cluster.

## Execution Plan

Four weekly steps to merge and measure.

## Risks of Inaction

Noise in tests continues.

## Expected Outcomes

Clearer paths.
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
