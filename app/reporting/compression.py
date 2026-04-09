"""
Phase 15 — Mandatory compression pass on synthesized Markdown (LLM).
"""

from __future__ import annotations

import os

from app.ai_insights import LLMClient
from app.db.models import AppSetting
from app.db.session import SessionLocal

_TASK_KEY = "prompt.task.compression.system"

_DEFAULT_PROMPT = """Reduce this executive Markdown report by about 30%.

- Remove repetition
- Remove filler
- Tighten language
- Keep meaning identical
- Do not add anything new
- Preserve every ## section heading exactly (same titles, same order)
- Do not add new sections
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


def compress_report(md: str) -> str:
    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        raise RuntimeError("Compression requires OPENAI_API_KEY to be set.")
    text = (md or "").strip()
    if not text:
        raise RuntimeError("Nothing to compress.")

    system = _get_or_seed_prompt()
    prompt = f"""{system}

---
REPORT:
{text}
---
Output only the compressed Markdown.
"""
    llm = LLMClient()
    out = llm.generate(prompt).strip()
    if not out:
        raise RuntimeError("Compression returned empty output.")
    return out
