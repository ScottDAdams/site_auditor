"""
Phase 15 — Strategic POV from audit_signal only (LLM + strict validation).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from app.ai_insights import LLMClient
from app.db.models import AppSetting
from app.db.session import SessionLocal

_TASK_KEY = "prompt.task.executive_pov.system"

_DEFAULT_PROMPT = """You are diagnosing a business.

You must identify ONE core failure.

Rules:
- Pick ONE problem only
- It must explain most of the performance loss
- Ignore secondary issues

Return JSON only (no markdown) with keys:
- core_thesis: answer "What is the ONE thing this company is doing wrong?" in one sentence, max 25 words
- mechanism: why this causes failure (concrete, no buzzwords)
- consequence: what this breaks in business terms
- priority_action: what fixes it (one sentence, concrete)

Constraints:
- core_thesis must be one sentence, max 25 words
- no vague language
- no buzzwords: do not use misalignment, opportunity, leverage, strategy (or strategic)
- be concrete: reference pages, URLs, products, regions, or duplicate content where the audit_signal supports it
"""


REQUIRED_KEYS = ("core_thesis", "mechanism", "consequence", "priority_action")

_BUZZ = re.compile(
    r"\b(misalignment|opportunity|leverage|strategy|strategic)\b",
    re.I,
)

_CONCRETE = re.compile(
    r"\b(page|pages|url|urls|site|sites|product|products|customer|customers|conversion|"
    r"cluster|crawl|duplicate|duplicates|region|regions|route|routes|path|paths|content|"
    r"copy|policy|policies|chapter|navigation|landing)\w*\b",
    re.I,
)


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


def validate_strategic_pov(pov: dict[str, Any] | None) -> list[str]:
    errors: list[str] = []
    if not isinstance(pov, dict):
        return ["strategic_pov must be a dict"]
    for k in REQUIRED_KEYS:
        v = pov.get(k)
        if not isinstance(v, str) or len(v.strip()) < 12:
            errors.append(f"Missing or too short: {k}")
    ct = (pov.get("core_thesis") or "").strip()
    if ct:
        words = ct.split()
        if len(words) > 25:
            errors.append("core_thesis exceeds 25 words")
        if len(words) < 5:
            errors.append("core_thesis is too vague (min 5 words)")
        if _BUZZ.search(ct):
            errors.append("core_thesis contains banned buzzwords")
        if not _CONCRETE.search(ct):
            errors.append("core_thesis must name concrete site/page/product/region/crawl elements")
    for k in ("mechanism", "consequence", "priority_action"):
        block = (pov.get(k) or "")
        if _BUZZ.search(block):
            errors.append(f"{k} contains banned buzzwords")
    return errors


def one_thing_wrong_sentence(strategic_pov: dict[str, Any]) -> str:
    if not isinstance(strategic_pov, dict):
        return ""
    return (strategic_pov.get("core_thesis") or "").strip()


def derive_strategic_pov(audit_signal: dict[str, Any]) -> dict[str, Any]:
    """LLM: single POV from audit_signal JSON only. No raw markdown."""
    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        raise RuntimeError("Strategic POV requires OPENAI_API_KEY to be set.")

    system = _get_or_seed_prompt()
    payload = json.dumps(audit_signal or {}, default=str, ensure_ascii=False)
    prompt = f"""{system}

---
AUDIT_SIGNAL JSON:
{payload}

---
Return only JSON: core_thesis, mechanism, consequence, priority_action.
"""
    llm = LLMClient()
    raw = llm.generate_json(prompt)
    if not isinstance(raw, dict):
        raise RuntimeError("Strategic POV returned invalid JSON shape.")
    out: dict[str, Any] = {}
    for k in REQUIRED_KEYS:
        v = raw.get(k)
        out[k] = str(v).strip() if v is not None else ""
    errs = validate_strategic_pov(out)
    if errs:
        raise RuntimeError("Strategic POV failed validation: " + "; ".join(errs))
    return out
