"""
Phase 13–14 — Strategic POV then executive synthesis (LLM).

Prompts are stored in app_settings (seed defaults here), not hardcoded in app logic.
"""

from __future__ import annotations

import json
import os
from typing import Any

from app.ai_insights import LLMClient
from app.db.models import AppSetting
from app.db.session import SessionLocal

_SYNTHESIS_TASK_KEY = "prompt.task.executive_synthesis.system"
_POV_TASK_KEY = "prompt.task.strategic_pov.system"

_DEFAULT_POV_PROMPT = """You are a principal strategist. From the audit inputs, derive ONE dominant strategic point of view.

Answer explicitly: What is the ONE thing this company is doing wrong (structurally or strategically)? That answer becomes core_thesis — exactly one crisp sentence (max 40 words).

Output JSON only (no markdown fences) with keys:
- core_thesis: string, one sentence — the single mistake or failure pattern
- mechanism: string — how the structure or operating model causes it (causal chain)
- consequence: string — business impact (demand, conversion, cost, velocity, trust)
- priority_action: string — the highest-leverage fix in one sentence

Rules:
- Ground every field in the supplied data; no placeholders or generic consulting filler
- core_thesis must be quotable as the executive answer to "what is wrong?"
- Do not list metrics; interpret them only inside mechanism or consequence if needed
"""


_DEFAULT_SYNTHESIS_PROMPT = """You are a senior strategy consultant.

Your task is NOT to write a generic report. Your task is to ARGUE a clear point of view using the data as evidence.

You are given strategic_pov (the locked thesis and causal chain) and supporting_evidence (structured facts) and metrics_for_proof (numbers to weave in as proof, never as bullet lists).

STRICT RULES:
- Build the ENTIRE document from strategic_pov. Every section reinforces the SAME thesis.
- No section may introduce a new central idea or contradict strategic_pov.
- Embed metrics only as supporting proof inside sentences (interpreted), never as naked lists or scorecard dumps.
- Do NOT paste or summarize raw executive/technical markdown; those informed strategic_pov already.
- No placeholders like "Not provided" or "TBD".
- Ban these phrases and close variants: "this highlights", "it is important to", "organizations should", "it is worth noting", "leverage synergies".

Write like a human expert defending one decision, not a template.

OUTPUT FORMAT (mandatory):
GitHub-flavored Markdown with exactly these level-2 headings in this order:

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


def build_evidence_digest(
    verification_pack: dict[str, Any],
    boardroom_brief: dict[str, Any],
    *,
    max_cluster_snippets: int = 10,
) -> dict[str, Any]:
    """
    Structured proof snippets only (no full markdown). Used to ground synthesis without raw MD passthrough.
    """
    out: dict[str, Any] = {"cluster_snippets": [], "boardroom_notes": []}
    for proof in (verification_pack.get("cluster_proofs") or [])[:max_cluster_snippets]:
        if not isinstance(proof, dict):
            continue
        cid = proof.get("cluster_id")
        urls = proof.get("urls") or []
        ds = str(proof.get("diff_summary") or "")[:600]
        out["cluster_snippets"].append(
            {
                "cluster_id": cid,
                "url_count": len(urls) if isinstance(urls, list) else 0,
                "diff_summary": ds,
            }
        )
    slides = boardroom_brief.get("slides")
    if isinstance(slides, list):
        for s in slides[:14]:
            if isinstance(s, dict):
                t = s.get("title") or s.get("headline") or s.get("slide_title")
                if t:
                    out["boardroom_notes"].append(str(t)[:240])
            elif isinstance(s, str) and s.strip():
                out["boardroom_notes"].append(s.strip()[:240])
    return out


def _get_or_seed_prompt(key: str, default: str) -> str:
    with SessionLocal() as db:
        row = db.get(AppSetting, key)
        if row and (row.value or "").strip():
            return str(row.value).strip()
        value = default.strip()
        if row:
            row.value = value
        else:
            db.add(AppSetting(key=key, value=value))
        db.commit()
        return value


def _get_pov_prompt() -> str:
    return _get_or_seed_prompt(_POV_TASK_KEY, _DEFAULT_POV_PROMPT)


def _get_synthesis_prompt() -> str:
    return _get_or_seed_prompt(_SYNTHESIS_TASK_KEY, _DEFAULT_SYNTHESIS_PROMPT)


REQUIRED_POV_KEYS = ("core_thesis", "mechanism", "consequence", "priority_action")


def validate_strategic_pov(pov: dict[str, Any] | None) -> list[str]:
    """Return list of errors; empty means OK."""
    errors: list[str] = []
    if not isinstance(pov, dict):
        return ["strategic_pov must be a dict"]
    for k in REQUIRED_POV_KEYS:
        v = pov.get(k)
        if not isinstance(v, str) or len(v.strip()) < 15:
            errors.append(f"Missing or too short: {k}")
    ct = (pov.get("core_thesis") or "").strip()
    if ct:
        words = len(ct.split())
        if words > 45:
            errors.append("core_thesis must be a single crisp sentence (max 45 words)")
        if words < 6:
            errors.append("core_thesis is too vague (min 6 words)")
    return errors


def one_thing_wrong_sentence(strategic_pov: dict[str, Any]) -> str:
    """Programmatic answer to 'what is the ONE thing wrong?' — for checks and APIs."""
    if not isinstance(strategic_pov, dict):
        return ""
    return (strategic_pov.get("core_thesis") or "").strip()


def derive_strategic_pov(
    executive_md: str,
    technical_md: str,
    boardroom_brief: dict[str, Any],
    verification_pack: dict[str, Any],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    """
    Pre-synthesis step: one dominant thesis from all inputs. Requires OPENAI_API_KEY.
    """
    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        raise RuntimeError("Strategic POV requires OPENAI_API_KEY to be set.")

    system = _get_pov_prompt()
    payload = {
        "executive_markdown_excerpt": (executive_md or "")[:16000],
        "technical_markdown_excerpt": (technical_md or "")[:16000],
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
Return only a JSON object with keys: core_thesis, mechanism, consequence, priority_action.
"""
    llm = LLMClient()
    raw = llm.generate_json(prompt)
    if not isinstance(raw, dict):
        raise RuntimeError("Strategic POV returned invalid JSON shape.")
    out: dict[str, Any] = {}
    for k in REQUIRED_POV_KEYS:
        v = raw.get(k)
        out[k] = str(v).strip() if v is not None else ""
    errs = validate_strategic_pov(out)
    if errs:
        raise RuntimeError("Strategic POV failed validation: " + "; ".join(errs))
    return out


def synthesize_executive_report(
    strategic_pov: dict[str, Any],
    metrics: dict[str, Any],
    evidence_digest: dict[str, Any],
) -> str:
    """
    Final narrative from strategic_pov only; metrics and digest are supporting proof.
    """
    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        raise RuntimeError("Executive synthesis requires OPENAI_API_KEY to be set.")

    errs = validate_strategic_pov(strategic_pov)
    if errs:
        raise RuntimeError("Invalid strategic_pov: " + "; ".join(errs))

    system = _get_synthesis_prompt()
    bundle = {
        "strategic_pov": strategic_pov,
        "metrics_for_proof": metrics or {},
        "supporting_evidence": evidence_digest or {},
    }
    user = json.dumps(bundle, default=str, ensure_ascii=False)
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
