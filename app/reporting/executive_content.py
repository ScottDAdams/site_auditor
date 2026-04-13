"""
Phase 13–15: validation for synthesized executive Markdown (strict).
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


def strategic_pov_path(report_id: int) -> Path:
    return _generated_dir(report_id) / "strategic_pov.json"


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

SECTION_WORD_LIMITS: dict[str, int] = {
    "Executive Summary": 120,
    "Audit Scorecard": 120,
    "If You Do One Thing": 80,
    "What Is Breaking Performance": 150,
    "Growth Opportunities": 120,
    "30-Day Execution Plan": 150,
    "Risks of Delay": 100,
    "Expected Outcomes": 100,
}


def _extract_h2_titles(md: str) -> list[str]:
    titles: list[str] = []
    for m in re.finditer(r"(?m)^##\s+(.+?)\s*$", md or ""):
        titles.append(m.group(1).strip())
    return titles


def _body_after_h2(md: str, title: str) -> str:
    pattern = re.compile(
        rf"(?ms)^##\s+{re.escape(title)}\s*$(.*?)(?=^##\s+|\Z)"
    )
    m = pattern.search(md or "")
    return (m.group(1) or "").strip() if m else ""


def _word_count(s: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", s or ""))


def _metric_mention_count(text: str) -> int:
    n = len(re.findall(r"\d+(?:\.\d+)?\s*%", text))
    n += len(re.findall(r"\b\d+(?:\.\d+)?\s+percent\b", text, re.I))
    return n


def _has_duplicate_sentences(text: str) -> bool:
    parts = re.split(r"(?<=[.!?])\s+", text or "")
    seen: set[str] = set()
    for p in parts:
        t = re.sub(r"\s+", " ", p.strip().lower())
        if len(t) < 35:
            continue
        if t in seen:
            return True
        seen.add(t)
    return False


def validate_executive_content(md: str) -> dict[str, Any]:
    """
    Validate Phase 15 compressed executive report: sections, word caps, bans, proof density.
    """
    text = (md or "").strip()
    if not text:
        return {"ok": False, "errors": ["Report is empty"]}

    titles = _extract_h2_titles(text)
    errors: list[str] = []

    lower = text.lower()
    if "not provided" in lower or "tbd" in lower:
        errors.append("Contains placeholder language (e.g. Not provided, TBD)")

    _vague = re.compile(
        r"\b(this highlights|it is important to|organizations should|it is worth noting)\b",
        re.I,
    )
    if _vague.search(text):
        errors.append("Contains vague filler phrasing")

    # Do not reject normal business words (strategic, opportunity, key, etc.): models use them
    # legitimately and the writer prompts already steer tone. Hard bans caused frequent 422s.

    # Soft guard: discourage raw metric spam (many "NN%" tokens), not woven proof across sections.
    _MAX_PERCENT_STYLE_MENTIONS = 14
    if _metric_mention_count(text) > _MAX_PERCENT_STYLE_MENTIONS:
        errors.append(
            f"Too many percentage-style metric call-outs (max {_MAX_PERCENT_STYLE_MENTIONS})"
        )

    if _has_duplicate_sentences(text):
        errors.append("Contains repeated sentences")

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
            wc = _word_count(body)
            if wc < 15:
                errors.append(f"Section too thin: ## {req}")
            lim = SECTION_WORD_LIMITS.get(req)
            if lim is not None and wc > lim:
                errors.append(f"Section exceeds {lim} words: ## {req} ({wc} words)")

    return {"ok": len(errors) == 0, "errors": errors}
