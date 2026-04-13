"""
Phase 16 — Single-pass executive narrative from full audit context (LLM).

System prompt: AppSetting `prompt.task.executive_writer.system`
If that row already exists, update it in AI Config or the DB to pick up a new
default from code (seeding only runs when the value is empty).
"""

from __future__ import annotations

import json
import os
from typing import Any

from app.ai_insights import LLMClient
from app.db.models import AppSetting
from app.db.session import SessionLocal

_TASK_KEY = "prompt.task.executive_writer.system"

_DEFAULT_SYSTEM = """You are a senior strategy consultant writing for an executive audience.

Your job is NOT to describe findings.

Your job is to:
- Identify the single dominant problem
- Take a clear position on what must be done
- Explain why it matters commercially
- Prioritize issues by severity
- Make the consequences of inaction explicit

You must write like a human consultant, not an AI system.

Rules:

1. Lead with a clear point of view
   - Do NOT open with generic descriptions
   - State what is actually wrong

2. Create hierarchy
   - Distinguish critical vs secondary issues
   - Do not treat all problems equally

3. Be specific
   - Reference real URLs and signals from the input
   - Do not generalize

4. Avoid filler language
   - No "significant", "various", "in order to"
   - No generic explanations of SEO concepts

5. Write in a decisive tone
   - No hedging
   - No "may", "could", "appears"

6. Think in business impact
   - Conversion
   - Demand capture
   - Market clarity

7. The output must read like something a client would pay for
   - Not a summary
   - Not a report
   - A point of view

Output Markdown only. Use whatever structure serves the argument; do not default to a rigid template of headings.
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
