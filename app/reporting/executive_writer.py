"""
Phase 16 — Single-pass executive narrative from full audit context (LLM).

System prompt: AppSetting `prompt.task.executive_writer.system`
"""

from __future__ import annotations

import json
import os
from typing import Any

from app.ai_insights import LLMClient
from app.db.models import AppSetting
from app.db.session import SessionLocal

_TASK_KEY = "prompt.task.executive_writer.system"

_DEFAULT_SYSTEM = """You are writing a board-level SEO and growth audit report.

Your job is to synthesize structured audit data and supporting materials into a clear, persuasive executive narrative.

This is not a summary task. This is an argument.

Use the inputs to:
- identify the single dominant structural problem
- explain why it matters commercially
- support it with concrete evidence (metrics, clusters, URLs)
- recommend a clear course of action
- describe the consequence of inaction

Write in a tone consistent with top consulting firms (McKinsey, Bain, BCG):
- direct
- structured
- non-generic
- no filler language

Avoid vague claims. Every important statement should be grounded in:
- a metric
- a concrete example
- or a structural observation

Do NOT mention "the audit shows" or refer to inputs directly.
Write as if this is your expert conclusion.

Maintain narrative flow across sections. Each section should build on the previous one.

You may reuse phrasing from inputs where useful, but do not copy blocks verbatim.

Clarity and authority are more important than brevity.

OUTPUT: Markdown only. Use exactly these level-2 headings in this order (## followed by title):

## Executive Summary
## Core Problem
## Why It Matters
## Evidence
## Recommended Action
## Execution Plan
## Risks of Inaction
## Expected Outcomes

No other level-2 headings. Body under each heading.
"""

_USER_TEMPLATE = """Write a complete executive report using the following inputs.

[STRUCTURED DATA]
{audit_signal_json}

[SUPPORTING EVIDENCE]
{verification_pack_json}

[BOARDROOM BRIEF]
{boardroom_brief_json}

[TECHNICAL DETAIL]
{technical_md}

[PRIOR EXECUTIVE SUMMARY]
{executive_md}

---

Required sections (use the ## headings specified in your instructions):

1. Executive Summary
2. Core Problem
3. Why It Matters
4. Evidence
5. Recommended Action
6. Execution Plan (30 days, ordered)
7. Risks of Inaction
8. Expected Outcomes

---

Requirements:

- Anchor claims in real metrics (overlap %, similarity, etc.)
- Reference real URLs where helpful
- Keep sections tight but not artificially constrained
- Avoid repetition across sections
- Do not default to generic consulting phrases
- Make this feel like a high-stakes business diagnosis, not an SEO checklist
"""


def _get_or_seed_system_prompt() -> str:
    with SessionLocal() as db:
        row = db.get(AppSetting, _TASK_KEY)
        if row and (row.value or "").strip():
            return str(row.value).strip()
        value = _DEFAULT_SYSTEM.strip()
        if row:
            row.value = value
        else:
            db.add(AppSetting(key=_TASK_KEY, value=value))
        db.commit()
        return value


def write_executive_report(context: dict[str, Any]) -> str:
    """
    One synthesis call: full context in, board-level Markdown out.
    """
    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        raise RuntimeError("Executive writer requires OPENAI_API_KEY to be set.")

    audit_signal = context.get("audit_signal") or {}
    verification_pack = context.get("verification_pack") or {}
    boardroom_brief = context.get("boardroom_brief") or {}
    technical_md = str(context.get("technical_md") or "")[:24000]
    executive_md = str(context.get("executive_md") or "")[:16000]

    audit_signal_json = json.dumps(audit_signal, indent=2, default=str, ensure_ascii=False)[
        :28000
    ]
    verification_pack_json = json.dumps(
        verification_pack, indent=2, default=str, ensure_ascii=False
    )[:28000]
    boardroom_brief_json = json.dumps(
        boardroom_brief, indent=2, default=str, ensure_ascii=False
    )[:16000]

    system = _get_or_seed_system_prompt()
    user = _USER_TEMPLATE.format(
        audit_signal_json=audit_signal_json,
        verification_pack_json=verification_pack_json,
        boardroom_brief_json=boardroom_brief_json,
        technical_md=technical_md,
        executive_md=executive_md,
    )
    prompt = f"""{system}

---

{user}
"""
    llm = LLMClient()
    out = llm.generate(prompt).strip()
    if not out:
        raise RuntimeError("Executive writer returned empty output.")
    return out
