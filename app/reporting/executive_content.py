"""
Phase 13: validation for synthesized executive Markdown only.

No enrichment, padding, or section stitching. Source audit artifacts stay unchanged.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _generated_dir(report_id: int) -> Path:
    root = Path(__file__).resolve().parent.parent.parent / "generated_reports"
    return root / str(report_id)


def executive_docx_path(report_id: int) -> Path:
    return _generated_dir(report_id) / "executive.docx"


def executive_synthesized_md_path(report_id: int) -> Path:
    return _generated_dir(report_id) / "executive_synthesized.md"


REQUIRED_SECTION_TITLES = (
    "Executive Summary",
    "Audit Scorecard",
    "If You Do One Thing",
    "What Is Breaking Performance",
    "Growth Opportunities",
    "30-Day Execution Plan",
    "Risks of Delay",
    "Expected Outcomes",
)


def _extract_h2_titles(md: str) -> list[str]:
    titles: list[str] = []
    for m in re.finditer(r"(?m)^##\s+(.+?)\s*$", md or ""):
        titles.append(m.group(1).strip())
    return titles


def _body_after_h2(md: str, title: str) -> str:
    """Text from after ## title until next ## or EOF."""
    pattern = re.compile(
        rf"(?ms)^##\s+{re.escape(title)}\s*$(.*?)(?=^##\s+|\Z)"
    )
    m = pattern.search(md or "")
    return (m.group(1) or "").strip() if m else ""


def validate_executive_content(md: str) -> dict[str, Any]:
    """
    Validate synthesized executive report Markdown.

    Requires eight ## sections (exact titles), non-empty bodies, no placeholder filler.
    """
    text = (md or "").strip()
    if not text:
        return {"ok": False, "errors": ["Report is empty"]}

    titles = _extract_h2_titles(text)
    errors: list[str] = []

    lower = (text or "").lower()
    if "not provided" in lower or "tbd" in lower:
        errors.append("Contains placeholder language (e.g. Not provided, TBD)")

    seen: set[str] = set()
    for t in titles:
        if t in seen:
            errors.append(f"Duplicate section heading: {t}")
        seen.add(t)

    for req in REQUIRED_SECTION_TITLES:
        if req not in titles:
            errors.append(f"Missing required section: ## {req}")
        else:
            body = _body_after_h2(text, req)
            if len(body) < 40:
                errors.append(f"Section too short or empty: ## {req}")

    return {"ok": len(errors) == 0, "errors": errors}
