"""
Phase 13 — Executive synthesis: one coherent narrative from audit artifacts (LLM).

Prompt text is stored in app_settings, not hardcoded in application logic beyond the initial seed.
"""

from __future__ import annotations

import json
import os
from typing import Any

from app.ai_insights import LLMClient
from app.db.models import AppSetting
from app.db.session import SessionLocal

_TASK_KEY = "prompt.task.executive_synthesis.system"

_DEFAULT_SYSTEM_PROMPT = """You are a senior strategy consultant.

Your task is to write a complete executive report based on structured audit inputs.

Do NOT summarize section-by-section.
Do NOT repeat inputs verbatim.
Do NOT use placeholders.

Build a coherent narrative with:

1. Executive Summary
   - Identify the single dominant structural issue
   - Explain it clearly in business terms
   - Integrate key metrics naturally (translate numbers into meaning)

2. Audit Scorecard
   - Present key metrics with interpretation (not just values)

3. If You Do One Thing
   - State the highest-leverage action
   - Explain why it must happen first

4. What Is Breaking Performance
   - Group issues into 3–5 themes
   - For each theme: Problem, Business impact, Action, Outcome

5. Growth Opportunities
   - Identify missed leverage points from the data

6. 30-Day Execution Plan
   - Sequence actions logically
   - Show compounding effect

7. Risks of Delay
   - Make consequences concrete

8. Expected Outcomes
   - Tie directly to earlier issues

STRICT RULES:
- No repetition across sections
- No placeholders like "Not provided" or "TBD"
- No generic filler language
- Every claim must align with input data
- Write like a human expert, not a template

OUTPUT FORMAT (mandatory):
Use GitHub-flavored Markdown with exactly these level-2 headings in this order (## followed by title):

## Executive Summary
## Audit Scorecard
## If You Do One Thing
## What Is Breaking Performance
## Growth Opportunities
## 30-Day Execution Plan
## Risks of Delay
## Expected Outcomes

Body text under each heading. No other level-2 headings.
"""


def extract_metrics(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Pull scorecard-style numbers from the audit snapshot for synthesis."""
    metrics: dict[str, Any] = {}
    es = snapshot.get("executive_summary_data") if isinstance(snapshot, dict) else None
    if not isinstance(es, dict):
        es = {}
    ms = es.get("_metrics_snapshot") or {}
    if isinstance(ms, dict):
        metrics.update(ms)
    vp = snapshot.get("verification_pack")
    if not isinstance(vp, dict):
        vp = es.get("verification_pack") if isinstance(es.get("verification_pack"), dict) else {}
    if isinstance(vp.get("cluster_proofs"), list):
        metrics.setdefault("cluster_count", len(vp["cluster_proofs"]))
    return metrics


def _get_or_seed_system_prompt() -> str:
    with SessionLocal() as db:
        row = db.get(AppSetting, _TASK_KEY)
        if row and (row.value or "").strip():
            return str(row.value).strip()
        value = _DEFAULT_SYSTEM_PROMPT.strip()
        if row:
            row.value = value
        else:
            db.add(AppSetting(key=_TASK_KEY, value=value))
        db.commit()
        return value


def synthesize_executive_report(
    executive_md: str,
    technical_md: str,
    boardroom_brief: dict[str, Any],
    verification_pack: dict[str, Any],
    metrics: dict[str, Any],
) -> str:
    """
    Produce a single synthesized Markdown document. Requires OPENAI_API_KEY at runtime.
    """
    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        raise RuntimeError("Executive synthesis requires OPENAI_API_KEY to be set.")

    system = _get_or_seed_system_prompt()
    payload = {
        "executive_markdown": (executive_md or "")[:14000],
        "technical_markdown": (technical_md or "")[:14000],
        "boardroom_brief": boardroom_brief or {},
        "verification_pack": verification_pack or {},
        "metrics": metrics or {},
    }
    user = json.dumps(payload, default=str, ensure_ascii=False)
    prompt = f"""{system}

---
INPUT JSON:
{user}

---
Output only the final Markdown document. Use the required ## headings exactly.
"""
    llm = LLMClient()
    out = llm.generate(prompt).strip()
    if not out:
        raise RuntimeError("Synthesis returned empty output.")
    return out
