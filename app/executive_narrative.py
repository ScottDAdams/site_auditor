"""
Phase 11 executive narrative generator.

LLM narrative with deterministic validation and proof-grounded fallback.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.ai_insights import LLMClient
from app.db.models import AppSetting
from app.db.session import SessionLocal

_TASK_KEY = "prompt.task.executive_narrative.system"

_DEFAULT_SYSTEM_PROMPT = """You are a senior strategy consultant writing for a CEO.

Your job is not to summarize. Your job is to make a clear, defensible business argument.

You must:
- Be decisive
- Remove ambiguity
- Translate technical findings into business impact
- Drive toward ONE primary decision

You must NOT:
- Hedge (no "may", "might", "could")
- List multiple competing strategies
- Use unexplained technical metrics
- Write filler or generic consulting language

Structure (mandatory):
01 Executive Summary
02 What Is Breaking Performance
03 If You Do One Thing
04 Execution Plan
05 Risks of Inaction
06 Expected Outcomes

Style rules:
- Max sentence length: 20 words
- No jargon unless explained
- No em dash
- No fluff
- Every paragraph must explain business relevance.
"""

_RAW_METRIC_RE = re.compile(
    r"\b(overlap_rate|avg_cluster_similarity|content_uniqueness_score|embedding similarity|cluster_similarity)\b",
    re.I,
)
# Telemetry-style scores (0.93) — do not blanket-ban all decimals (years, URLs, ordinals).
_TELEMETRY_SCORE_RE = re.compile(r"\b0\.\d{2,}\b")
_HEDGE_RE = re.compile(r"\b(may|might|could|consider)\b", re.I)
_CONFLICT_RE = re.compile(
    r"\b(merge|consolidate|redirect|differentiate|split|isolate)\b",
    re.I,
)
_SECTIONS = (
    "01 Executive Summary",
    "02 What Is Breaking Performance",
    "03 If You Do One Thing",
    "04 Execution Plan",
    "05 Risks of Inaction",
    "06 Expected Outcomes",
)


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


def _sentence_too_long(text: str, max_words: int = 20) -> bool:
    chunks = re.split(r"[.!?]\s+", (text or "").strip())
    for ch in chunks:
        words = [w for w in re.findall(r"[A-Za-z0-9']+", ch) if w]
        if len(words) > max_words:
            return True
    return False


def _extract_primary_decision_count(text: str) -> int:
    # Count in section 03 only so issue action lists do not look like conflicts.
    t = (text or "")
    m = re.search(
        r"03 If You Do One Thing\s*(.*?)\s*04 Execution Plan",
        t,
        flags=re.I | re.S,
    )
    scope = m.group(1) if m else t
    n = len(re.findall(r"the correct move is to", scope.lower()))
    if n:
        return n
    # Fallback anchor if phrasing drifts.
    return len(re.findall(r"primary decision", (text or "").lower()))


def validate_executive_narrative(output: str) -> None:
    t = (output or "").strip()
    if not t:
        raise ValueError("executive narrative is empty")
    for sec in _SECTIONS:
        if sec.lower() not in t.lower():
            raise ValueError(f"missing mandatory section: {sec}")
    if _RAW_METRIC_RE.search(t) or _TELEMETRY_SCORE_RE.search(t):
        raise ValueError("contains raw metric language")
    if _HEDGE_RE.search(t):
        raise ValueError("contains hedging language")
    if " -- " in t or "—" in t:
        raise ValueError("contains forbidden dash style")
    if _sentence_too_long(t):
        raise ValueError("contains sentence longer than 20 words")
    decisions = _extract_primary_decision_count(t)
    if decisions != 1:
        raise ValueError(f"must contain exactly one primary decision, found {decisions}")
    # Guard against summary-like output with no argument pressure.
    if not re.search(r"\b(because|therefore|so|this means)\b", t.lower()):
        raise ValueError("reads like summary, missing business argument transitions")
    m = re.search(
        r"03 If You Do One Thing\s*(.*?)\s*04 Execution Plan",
        t,
        flags=re.I | re.S,
    )
    scope = m.group(1) if m else t
    action_words = set(w.lower() for w in _CONFLICT_RE.findall(scope))
    if len(action_words) > 2:
        raise ValueError("recommends multiple conflicting strategies")


def _sanitize_narrative_field(s: str) -> str:
    """
    Strip telemetry-style numbers from deterministic engine text so narrative validation
    does not fight overlap % and similarity scores embedded in rationales.
    """
    t = (s or "").strip()
    if not t:
        return ""
    # Percentages and similarity-style decimals from evidence packs
    t = re.sub(r"\b\d{1,3}\.\d+%\b", "strong overlap", t)
    t = re.sub(r"\b\d{1,3}%\b", "a material portion", t)
    t = re.sub(r"\b0\.\d{2,}\b", "high similarity", t)
    return t


def _clip_sentence_words(s: str, max_words: int = 18) -> str:
    words = [w for w in (s or "").split() if w]
    if len(words) <= max_words:
        return (s or "").strip()
    return " ".join(words[:max_words]).rstrip(",;:") + "."


def _proof_block(executive_brief_json: dict[str, Any]) -> str:
    pack = executive_brief_json.get("verification_pack") or {}
    proofs = pack.get("cluster_proofs") if isinstance(pack, dict) else []
    if not isinstance(proofs, list):
        proofs = []
    lines: list[str] = []
    for pr in proofs[:3]:
        if not isinstance(pr, dict):
            continue
        urls = pr.get("urls") or []
        lines.append(f"- URLs: {', '.join(str(u) for u in urls[:2])}")
        lines.append(f"- Proof: {str(pr.get('diff_summary') or '').strip()}")
        for sec in (pr.get("overlap_sections") or [])[:2]:
            if isinstance(sec, dict):
                h = str(sec.get("heading") or "").strip()
                if h:
                    lines.append(f"- Overlap section: {h}")
    return "\n".join(lines).strip()


def _fallback_narrative(executive_brief_json: dict[str, Any]) -> str:
    es = executive_brief_json or {}
    issues = [i for i in (es.get("top_issues") or []) if isinstance(i, dict)]
    first = issues[0] if issues else {}
    dec = _sanitize_narrative_field(
        str(first.get("decision") or es.get("primary_bet", {}).get("action") or "").strip()
    )
    if "the correct move is to" not in dec.lower():
        dec = f"The correct move is to {dec[0].lower() + dec[1:]}" if dec else "The correct move is to establish one owner per buyer decision."
    dec_plain = re.sub(r"(?i)^the correct move is to\s*", "", dec).strip()
    impact = _sanitize_narrative_field(str(first.get("business_consequence") or "").strip())
    risk = _sanitize_narrative_field(str(first.get("risk_if_ignored") or "").strip())
    out = _sanitize_narrative_field(str(first.get("outcome") or "").strip())
    why = re.sub(
        r"(?i)the correct move is to",
        "This move",
        _sanitize_narrative_field(str(first.get("decision_rationale") or "").strip()),
    )
    lines = [
        "01 Executive Summary",
        _clip_sentence_words(
            f"The primary decision is {dec_plain}. This matters because structure suppresses demand capture."
        ),
        _clip_sentence_words(
            impact or "Current overlap splits demand and weakens conversion capture."
        ),
        "",
        "02 What Is Breaking Performance",
    ]
    for i, iss in enumerate(issues[:5], 1):
        problem = _sanitize_narrative_field(str(iss.get("problem") or "").strip())
        bi = _sanitize_narrative_field(
            str(iss.get("business_consequence") or iss.get("impact") or "").strip()
        )
        action = str(iss.get("decision") or iss.get("recommended_action") or "").strip()
        action = _sanitize_narrative_field(action)
        action = re.sub(r"(?i)^the correct move is to\s*", "", action).strip()
        lines.append(f"{i}. Problem: {_clip_sentence_words(problem)}")
        lines.append(f"Business impact: {_clip_sentence_words(bi)}")
        lines.append(f"Action: {_clip_sentence_words(action)}")
    lines += [
        "",
        "03 If You Do One Thing",
        dec,
        "Do this now because it removes the highest-value structural blocker first.",
        "",
        "04 Execution Plan",
    ]
    for s in (es.get("execution_plan") or [])[:5]:
        if isinstance(s, dict):
            focus = str(s.get("focus") or s.get("intent") or "Step").strip()
            acts = [
                _sanitize_narrative_field(str(a).strip())
                for a in (s.get("actions") or [])[:2]
                if str(a).strip()
            ]
            lines.append(
                _clip_sentence_words(f"{focus}: {'; '.join(acts)}")
            )
    lines += [
        "",
        "05 Risks of Inaction",
        _clip_sentence_words(
            risk or "Demand stays fragmented, spend rises, and conversion remains suppressed."
        ),
        "",
        "06 Expected Outcomes",
        _clip_sentence_words(
            out or "Authority and conversion concentration improve on priority journeys."
        ),
        _clip_sentence_words(
            why
            or "The evidence ties duplicated structure to lost momentum in core buyer journeys."
        ),
    ]
    return "\n".join(lines).strip()


def generate_executive_narrative(
    payload: dict[str, Any],
    technical_report_md: str,
    executive_brief_json: dict[str, Any],
) -> dict[str, str]:
    """
    Returns dict with:
      - executive_report_md (boardroom-ready markdown)
    """
    system_prompt = _get_or_seed_system_prompt()
    proof = _proof_block(executive_brief_json)
    prompt = f"""{system_prompt}

Use these proof snippets as supporting evidence, but explain them in business terms:
{proof or "- Proof snippets unavailable in this run. Use executive brief facts only."}

Executive brief JSON:
{json.dumps(executive_brief_json, default=str)[:18000]}

Technical report markdown:
{(technical_report_md or "")[:18000]}

Write markdown output only. Use the exact six section headers.
Keep every sentence at 20 words or less.
Include exactly one line containing: "The correct move is to ..."
"""
    llm = LLMClient() if payload.get("openai_enabled") else None
    if llm is None:
        txt = _fallback_narrative(executive_brief_json)
        validate_executive_narrative(txt)
        return {"executive_report_md": txt}

    last_err = ""
    for _ in range(3):
        try:
            out = llm.generate(prompt).strip()
            validate_executive_narrative(out)
            return {"executive_report_md": out}
        except Exception as exc:  # keep retries deterministic
            last_err = str(exc)
            prompt += (
                "\n\nRETRY CONSTRAINTS:\n"
                "- remove metric tokens and percentages\n"
                "- keep one primary decision only\n"
                "- remove hedging words\n"
                "- keep sentences <= 20 words\n"
            )
    fb = _fallback_narrative(executive_brief_json)
    try:
        validate_executive_narrative(fb)
    except ValueError:
        # Never fail the audit pipeline on narrative validation; ship safe minimal brief.
        fb = (
            "01 Executive Summary\n"
            "The correct move is to fix structural overlap first. "
            "This matters because split demand weakens conversion.\n"
            "Therefore prioritize one owner page per buyer decision.\n"
            "\n"
            "02 What Is Breaking Performance\n"
            "1. Problem: Overlapping pages compete for the same job.\n"
            "Business impact: Demand scatters across routes.\n"
            "Action: Consolidate or differentiate with clear roles.\n"
            "\n"
            "03 If You Do One Thing\n"
            "The correct move is to name one primary page per major decision.\n"
            "Do this now because it unlocks cleaner capture.\n"
            "\n"
            "04 Execution Plan\n"
            "Week 1: Lock page roles and targets.\n"
            "Week 2: Apply merges or redirects.\n"
            "\n"
            "05 Risks of Inaction\n"
            "- Spend rises while conversion stays flat.\n"
            "\n"
            "06 Expected Outcomes\n"
            "- Clearer paths and stronger capture.\n"
        )
    if last_err:
        fb += f"\n\n<!-- fallback_after_validation_error: {last_err} -->"
    return {"executive_report_md": fb}

