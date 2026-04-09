"""
Phase 15 — Executive report draft from core argument + proof (LLM).
"""

from __future__ import annotations

import os
from typing import Any

from app.ai_insights import LLMClient
from app.db.models import AppSetting
from app.db.session import SessionLocal

_TASK_KEY = "prompt.task.executive_writer.system"

_DEFAULT_PROMPT = """You are not writing a report.

You are making a case.

Your job:
- reinforce this argument from multiple angles
- remove anything that does not support it
- simplify aggressively

Structure (exact ## headings, in order):

## Executive Summary (max 120 words)
## Audit Scorecard (max 120 words)
## If You Do One Thing (max 80 words)
## What Is Breaking Performance (max 150 words)
## Growth Opportunities (max 120 words)
## 30-Day Execution Plan (max 150 words)
## Risks of Delay (max 100 words)
## Expected Outcomes (max 100 words)

Rules:
- Every section must reinforce the SAME argument
- Do not introduce new ideas
- Do not restate the same sentence in different words across sections
- Use metrics only as woven proof inside prose, never as bullet lists of numbers
- No filler language

Banned words (and close variants): significant, critical, important, key, strategic, opportunity, misalignment

Tone: direct, confident, no hedging.

Output only Markdown with those eight ## sections. No other level-2 headings.
"""


def _get_or_seed_prompt() -> str:
    with SessionLocal() as db:
        row = db.get(AppSetting, _TASK_KEY)
        if row and (row.value or "").strip():
            return str(row.value).strip()
        value = _DEFAULT_PROMPT.strip()
        if row:
            row.value = value
        else:
            db.add(AppSetting(key=_TASK_KEY, value=value))
        db.commit()
        return value


def build_core_argument(pov: dict[str, Any]) -> str:
    """Single chained argument string for the writer."""
    return (
        f"{pov['core_thesis']} because {pov['mechanism']}, which leads to "
        f"{pov['consequence']}. The fix is {pov['priority_action']}."
    )


def write_executive_report(core_argument: str, proof: list[str]) -> str:
    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        raise RuntimeError("Executive writer requires OPENAI_API_KEY to be set.")

    system = _get_or_seed_prompt()
    proof_block = "\n".join(f"- {p}" for p in (proof or [])[:3])
    prompt = f"""{system}

Core argument:
{core_argument}

Supporting proof:
{proof_block}
"""
    llm = LLMClient()
    out = llm.generate(prompt).strip()
    if not out:
        raise RuntimeError("Executive writer returned empty output.")
    return out
