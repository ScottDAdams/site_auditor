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

_DEFAULT_SYSTEM = """You are a senior consultant delivering a board-level SEO and growth audit.

Your job is to interpret raw audit signal and evidence yourself—prioritize, argue, and narrate in one coherent piece. This is not summarizing someone else's summary; you are forming the conclusion from primary material.

From the inputs, develop:
- the single dominant structural problem (your judgment)
- why it matters commercially
- specific support: metrics, cluster or URL examples from the data
- a clear recommended course of action and what happens if nothing changes

Tone: direct, authoritative, non-generic—like a top firm memo, not a checklist or slide outline.

Ground important claims in the data (numbers, URLs, structural facts). Do not invent metrics.

Do NOT say "the audit shows," "per the report," or otherwise refer to documents as sources—state conclusions as your expert view.

Do NOT use stock consulting filler or repeated template phrases (e.g. "The correct move is").

Output Markdown only. You control structure: use headings only where they improve readability; merge or omit sections if the narrative flows better without a rigid outline. Prefer flowing prose; avoid bullet-only decks unless bullets truly clarify.

Clarity and judgment matter more than brevity.
"""

_USER_TEMPLATE = """Write the executive narrative from these inputs only. Interpret and prioritize; do not mirror any pre-written executive summary structure.

[STRUCTURED DATA — audit_signal]
{audit_signal_json}

[SUPPORTING EVIDENCE — verification_pack]
{verification_pack_json}

[TECHNICAL DETAIL — raw diagnostics]
{technical_md}
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
    technical_md = str(context.get("technical_md") or "")[:24000]

    audit_signal_json = json.dumps(audit_signal, indent=2, default=str, ensure_ascii=False)[
        :28000
    ]
    verification_pack_json = json.dumps(
        verification_pack, indent=2, default=str, ensure_ascii=False
    )[:28000]

    system = _get_or_seed_system_prompt()
    user = _USER_TEMPLATE.format(
        audit_signal_json=audit_signal_json,
        verification_pack_json=verification_pack_json,
        technical_md=technical_md,
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
