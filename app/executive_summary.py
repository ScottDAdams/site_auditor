"""
Client-grade executive layer (Phase 6): structured decisions → narrative.

Decisions are deterministic; optional LLM only polishes wording.
"""

from __future__ import annotations

import json
import os
import re
from typing import TYPE_CHECKING, Any

from app.analyzer import REMEDIATION_DECISION_TYPES

if TYPE_CHECKING:
    from app.ai_insights import LLMClient

# Executive prose must not read like raw telemetry.
_FORBIDDEN_EXECUTIVE_TERMS = (
    "overlap_rate",
    "avg_cluster_similarity",
    "content_uniqueness_score",
    "embedding similarity",
)


def map_problem_to_business_impact(transformation_type: str, metrics: dict | None) -> str:
    """
    Business-facing consequence only (no metric-first phrasing).
    `metrics` reserved for future threshold tuning; do not embed metric names in output.
    """
    _ = metrics
    tt = (transformation_type or "").strip().lower()
    if tt in ("merge", "consolidate"):
        return (
            "Search visibility is split across competing pages, reducing ranking strength "
            "and traffic concentration."
        )
    if tt in ("isolate", "differentiate", "split"):
        return (
            "Users face unclear choices between similar pages, reducing conversion clarity."
        )
    if tt == "redirect":
        return "Crawl and indexing signals are diluted across duplicate URLs."
    if tt == "retain":
        return "Residual overlap is manageable but still worth monitoring so it does not creep upward."
    if tt == "elevate":
        return "A hub page is not yet earning the clear parent role it needs for navigation and search."
    if tt == "demote":
        return "Supporting pages may be over-visible for intents that belong elsewhere."
    return (
        "Overlapping pages compete for the same purpose, which weakens rankings and splits traffic."
    )


def map_action_to_outcome(transformation_type: str) -> str:
    tt = (transformation_type or "").strip().lower()
    if tt in ("merge", "consolidate"):
        return "Consolidates authority into a single page, improving ranking potential."
    if tt in ("differentiate", "isolate", "split"):
        return "Clarifies page purpose, improving user decision flow."
    if tt == "redirect":
        return "Funnels users and signals to one canonical URL, reducing duplicate indexing."
    if tt == "retain":
        return "Keeps the current structure while holding clarity and monitoring drift."
    if tt == "elevate":
        return "Strengthens the hub as the obvious entry point for the topic."
    if tt == "demote":
        return "Moves secondary detail out of the way of primary conversion paths."
    return "Reduces internal competition so one clear page can win for each intent."


def _problem_statement(transformation_type: str, urls: list[str]) -> str:
    """Plain-language problem; never metric-led."""
    tt = (transformation_type or "").strip().lower()
    n = len(urls)
    if tt in ("merge", "consolidate"):
        return (
            "These pages are competing for the same purpose, which weakens rankings and splits traffic."
        )
    if tt in ("isolate", "differentiate", "split"):
        return (
            "These URLs look interchangeable to visitors and search engines, so neither page fully wins."
        )
    if tt == "redirect":
        return "The same content is reachable under more than one URL, which wastes crawl budget and splits signals."
    if tt == "retain":
        return "Overlap is within an acceptable band, but consistency still matters for future changes."
    if n >= 2:
        return "Related URLs need a clearer division of responsibility so journeys stay coherent."
    return "This URL cluster needs a clearer, single-minded job in the site structure."


def _recommended_action_line(transformation_type: str, urls: list[str]) -> str:
    tt = (transformation_type or "").strip().lower()
    u0 = urls[0] if urls else "the canonical URL"
    u1 = urls[1] if len(urls) > 1 else ""
    if tt in ("merge", "consolidate") and u1:
        return f"Merge or consolidate overlapping content into one primary page; retire duplicate surfaces, starting with {u0} and {u1}."
    if tt in ("merge", "consolidate"):
        return f"Merge duplicate content into one primary destination at {u0}."
    if tt == "redirect" and u1:
        return (
            f"Redirect duplicate URLs to one canonical target (301 redirect from {u1} to {u0} "
            f"or equivalent canonical rules)."
        )
    if tt == "redirect":
        return f"Redirect or canonicalize duplicate routes so only {u0} stays indexable."
    if tt in ("isolate", "differentiate", "split") and u1:
        return f"Assign distinct roles: reshape {u0} and {u1} so each page owns a different buyer job and proof."
    if tt in ("isolate", "differentiate", "split"):
        return f"Differentiate {u0} so it no longer competes with sibling pages for the same decision."
    if tt == "retain":
        return f"Keep {u0} published; document scope and monitor for drift—no merge or redirect required now."
    return f"Execute the agreed transformation for {u0}, aligned with the audit transformation type ({tt})."


def _strategic_rows(payload: dict) -> list[dict]:
    rows = [c for c in (payload.get("clusters") or []) if isinstance(c, dict)]
    return [r for r in rows if r.get("decision_type") in REMEDIATION_DECISION_TYPES]


def _risk_level_from_health(score: int, insights: dict, payload: dict) -> str:
    pl = str(payload.get("priority_level") or insights.get("priority_level") or "").lower()
    if pl == "high":
        return "high"
    if pl == "low":
        return "low"
    if score >= 72:
        return "low"
    if score >= 52:
        return "moderate"
    return "high"


def _collect_issue_urls(row: dict | None) -> list[str]:
    if not row:
        return []
    out: list[str] = []
    seen: set[str] = set()
    dom = row.get("dominant_url")
    if dom:
        s = str(dom).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    for u in (row.get("competing_urls") or [])[:5]:
        if not u:
            continue
        s = str(u).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def build_executive_summary_data(payload: dict, insights: dict) -> dict[str, Any]:
    """Structured executive payload from deterministic engine + insights (no LLM)."""
    insights = insights or {}
    payload = payload or {}
    metrics = payload.get("metrics") or {}

    score = payload.get("site_health_score")
    try:
        score_int = int(round(float(score))) if score is not None else 70
    except (TypeError, ValueError):
        score_int = 70

    pt = (insights.get("problem_type") or payload.get("dominant_problem_type") or "unknown").strip()

    strategic = _strategic_rows(payload)
    ordered = list(payload.get("structural_execution_order") or [])
    top_n = ordered[:5]
    if not top_n and strategic:
        top_n = [
            {
                "cluster_index": i,
                "dominant_url": r.get("dominant_url"),
                "priority_score": float(payload.get("priority_score") or 0),
                "priority_level": str(payload.get("priority_level") or "medium"),
                "transformation_type": (
                    (payload.get("transformation_spec") or {}).get("transformation_type")
                    or "differentiate"
                ),
            }
            for i, r in enumerate(strategic[:5])
        ]

    top_issues: list[dict[str, Any]] = []
    for item in top_n:
        idx = item.get("cluster_index")
        row = None
        if idx is not None and isinstance(idx, int) and 0 <= idx < len(strategic):
            row = strategic[idx]
        tt = str(item.get("transformation_type") or "differentiate").strip().lower()
        urls = _collect_issue_urls(row)
        if not urls and item.get("dominant_url"):
            urls = [str(item["dominant_url"]).strip()]
        ps = item.get("priority_score")
        try:
            ps_f = float(ps) if ps is not None else float(payload.get("priority_score") or 0)
        except (TypeError, ValueError):
            ps_f = 0.0
        pl = str(item.get("priority_level") or payload.get("priority_level") or "medium")

        top_issues.append(
            {
                "problem": _problem_statement(tt, urls),
                "urls": urls,
                "transformation_type": tt,
                "priority_score": ps_f,
                "priority_level": pl,
                "business_impact": map_problem_to_business_impact(tt, metrics),
                "recommended_action": _recommended_action_line(tt, urls),
            }
        )

    summary_data: dict[str, Any] = {
        "site_health": {
            "score": score_int,
            "risk_level": _risk_level_from_health(score_int, insights, payload),
            "primary_issue_type": pt,
        },
        "top_issues": top_issues,
        "execution_plan": [],
        "quick_wins": [],
        "strategic_risks": [],
    }

    summary_data["execution_plan"] = build_execution_plan(summary_data)
    summary_data["quick_wins"] = _build_quick_wins(payload)
    summary_data["strategic_risks"] = _build_strategic_risks(summary_data["top_issues"])
    return summary_data


def build_execution_plan(summary_data: dict) -> list[dict[str, Any]]:
    """
    Step-based plan grouped by transformation family (merge/consolidate → redirect → clarify → retain).
    """
    issues = summary_data.get("top_issues") or []
    buckets: dict[str, list[dict]] = {
        "consolidate": [],
        "redirect": [],
        "clarify": [],
        "retain": [],
    }
    for iss in issues:
        if not isinstance(iss, dict):
            continue
        tt = str(iss.get("transformation_type") or "").lower()
        if tt in ("merge", "consolidate"):
            buckets["consolidate"].append(iss)
        elif tt == "redirect":
            buckets["redirect"].append(iss)
        elif tt in ("isolate", "differentiate", "split"):
            buckets["clarify"].append(iss)
        else:
            buckets["retain"].append(iss)

    steps_meta = [
        ("consolidate", "Consolidate duplicate pages"),
        ("redirect", "Normalize technical duplicates"),
        ("clarify", "Clarify page roles"),
        ("retain", "Retain scope and cleanup"),
    ]

    plan: list[dict[str, Any]] = []
    step_no = 0
    for key, focus in steps_meta:
        group = buckets[key]
        if not group:
            continue
        step_no += 1
        actions: list[str] = []
        for iss in group[:4]:
            act = (iss.get("recommended_action") or "").strip()
            urls = iss.get("urls") or []
            if act:
                actions.append(act)
            elif urls:
                actions.append(f"Address URLs: {', '.join(urls[:3])}")
        actions = actions[:4]
        out0 = map_action_to_outcome(str(group[0].get("transformation_type") or ""))
        plan.append(
            {
                "step": step_no,
                "focus": focus,
                "actions": actions,
                "expected_outcome": out0,
            }
        )
    return plan


def _build_quick_wins(payload: dict) -> list[dict[str, Any]]:
    wins: list[dict[str, Any]] = []
    for row in payload.get("clusters") or []:
        if not isinstance(row, dict):
            continue
        if row.get("decision_type") != "technical_fix":
            continue
        issue = (row.get("technical_issue") or "Duplicate URL form").strip()
        rec = (row.get("technical_fix_recommendation") or "").strip()
        dom = row.get("dominant_url") or ""
        tail = f" ({dom})" if dom else ""
        action = (rec + tail).strip() if rec else f"Resolve duplicate URL signals{tail}"
        wins.append(
            {
                "action": action,
                "reason": "Technical duplication is usually a small change with immediate crawl clarity.",
                "effort": "low",
                "impact": "high",
            }
        )
        if len(wins) >= 4:
            break

    if not wins:
        for u in (payload.get("technical_fix_urls") or [])[:2]:
            wins.append(
                {
                    "action": f"Apply canonical or redirect rules for duplicate paths including {u}.",
                    "reason": "Stops search engines from indexing multiple URLs for the same page.",
                    "effort": "low",
                    "impact": "high",
                }
            )
    if not wins:
        wins.append(
            {
                "action": "Audit trailing slash and www vs non-www consistency on high-traffic templates.",
                "reason": "Prevents accidental duplicate homepages and section entry URLs.",
                "effort": "low",
                "impact": "medium",
            }
        )
    return wins[:5]


def _build_strategic_risks(top_issues: list[dict]) -> list[dict[str, str]]:
    risks: list[dict[str, str]] = []
    types = {str(i.get("transformation_type") or "").lower() for i in top_issues if isinstance(i, dict)}
    if any(t in types for t in ("merge", "consolidate", "redirect")):
        risks.append(
            {
                "risk": "Ongoing duplication",
                "consequence": "Will continue to split rankings and waste crawl attention.",
            }
        )
    if any(t in types for t in ("differentiate", "isolate", "split")):
        risks.append(
            {
                "risk": "Unclear page roles",
                "consequence": "Will reduce conversion efficiency as users bounce between similar pages.",
            }
        )
    if not risks:
        risks.append(
            {
                "risk": "Structural drift",
                "consequence": "New pages may copy the same patterns and recreate overlap without guardrails.",
            }
        )
    return risks


def render_executive_summary(summary_data: dict) -> str:
    """Deterministic executive narrative (plain text)."""
    sd = summary_data or {}
    sh = sd.get("site_health") or {}
    lines: list[str] = []

    score = sh.get("score", "")
    risk = sh.get("risk_level", "")
    pit = sh.get("primary_issue_type", "")
    lines.append(
        f"This audit shows a site health score of {score} with {risk} structural risk. "
        f"The primary issue pattern is {pit}: overlapping or duplicated pages are shaping what to fix first."
    )
    lines.append(
        "The items below prioritize business impact—clear problems, consequences, and actions—without leaning on raw metrics in the narrative."
    )
    lines.append("")

    issues = sd.get("top_issues") or []
    if issues:
        lines.append("Top issues")
        for i, iss in enumerate(issues, 1):
            if not isinstance(iss, dict):
                continue
            prob = (iss.get("problem") or "").strip()
            bi = (iss.get("business_impact") or "").strip()
            act = (iss.get("recommended_action") or "").strip()
            urls = iss.get("urls") or []
            tt = iss.get("transformation_type", "")
            lines.append(f"{i}. [{tt}] {prob}")
            if bi:
                lines.append(f"   Consequence: {bi}")
            if act:
                lines.append(f"   Action: {act}")
            if urls:
                lines.append(f"   URLs: {', '.join(str(u) for u in urls[:4])}")
        lines.append("")

    plan = sd.get("execution_plan") or []
    if plan:
        lines.append("Execution plan")
        for step in plan:
            if not isinstance(step, dict):
                continue
            sn = step.get("step", "")
            focus = step.get("focus", "")
            lines.append(f"Step {sn} — {focus}")
            for a in (step.get("actions") or [])[:4]:
                lines.append(f"  • {a}")
            eo = (step.get("expected_outcome") or "").strip()
            if eo:
                lines.append(f"  Expected: {eo}")
        lines.append("")

    qw = sd.get("quick_wins") or []
    if qw:
        lines.append("Quick wins")
        for q in qw:
            if not isinstance(q, dict):
                continue
            lines.append(
                f"  • {q.get('action', '')} — {q.get('reason', '')} "
                f"(effort {q.get('effort', 'low')}, impact {q.get('impact', 'medium')})"
            )
        lines.append("")

    risks = sd.get("strategic_risks") or []
    if risks:
        lines.append("Key risks")
        for r in risks:
            if not isinstance(r, dict):
                continue
            lines.append(f"  • {r.get('risk', '')}: {r.get('consequence', '')}")
        lines.append("")

    lines.append(
        "Expected outcome: fewer competing URLs per intent, clearer buyer paths, "
        "and stronger concentration of authority on the pages you want to win."
    )
    return "\n".join(lines).strip()


def render_executive_summary_llm(summary_data: dict, llm_client: LLMClient | None = None) -> str:
    """
    Optional polish only. Input is structured summary_data JSON only.
    Returns empty string if no client or no API key.
    """
    if llm_client is None:
        if not os.getenv("OPENAI_API_KEY"):
            return ""
        from app.ai_insights import LLMClient

        llm_client = LLMClient()

    blob = json.dumps(summary_data, indent=2, default=str)
    prompt = f"""You are an editor. Improve clarity and flow of the executive brief below.

RULES (strict):
- Do NOT add new facts, URLs, issues, steps, or recommendations.
- Do NOT change which issues appear or their transformation types.
- Do NOT introduce raw metric names (overlap_rate, avg_cluster_similarity, content_uniqueness_score, embedding).
- Do NOT start any sentence with a metric name or number-led telemetry.
- Keep the same sections in order: opening context, Top issues, Execution plan, Quick wins, Key risks, Expected outcome.
- Keep every URL that appears in the input; do not invent URLs.
- Output plain text only (no markdown code fences).

STRUCTURED INPUT (only source of truth):
{blob}
"""
    return llm_client.generate(prompt).strip()


_METRIC_LEAD = re.compile(
    r"(?m)^\s*(?:\d+\.|[-*•])?\s*"
    r"(overlap_rate|avg_cluster_similarity|content_uniqueness_score)\b",
    re.I,
)
_TELEMETRY_PHRASE = re.compile(
    r"\b(overlap_rate|avg_cluster_similarity|content_uniqueness_score)\s+[\d.]+\s+"
    r"(causes|means|drives|creates|leads|results)\b",
    re.I,
)


def validate_executive_output(text: str, summary_data: dict | None = None) -> None:
    """
    Block metric-first / telemetry tone in client executive text.
    When summary_data is provided, require consequence-style business_impact per top issue.
    """
    t = (text or "").strip()
    if not t:
        raise ValueError("[rule:executive_empty] executive summary text is empty")
    low = t.lower()
    for term in _FORBIDDEN_EXECUTIVE_TERMS:
        if term in low:
            raise ValueError(
                f"[rule:executive_no_telemetry] executive text must not contain {term!r}"
            )
    if _METRIC_LEAD.search(t):
        raise ValueError("[rule:executive_metric_lead] line starts with metric-style token")
    if _TELEMETRY_PHRASE.search(t):
        raise ValueError("[rule:executive_metric_first_sentence] metric-led explanation forbidden")

    if summary_data:
        issues = summary_data.get("top_issues") or []
        for iss in issues:
            if not isinstance(iss, dict):
                continue
            bi = (iss.get("business_impact") or "").strip()
            if len(bi.split()) < 6:
                raise ValueError(
                    "[rule:executive_issue_consequence] each issue needs a substantive business_impact"
                )
            tt = str(iss.get("transformation_type") or "").lower()
            act = (iss.get("recommended_action") or "").lower()
            if tt in ("merge", "consolidate") and "merge" not in act and "consolidat" not in act:
                raise ValueError(
                    "[rule:executive_action_vs_type] merge/consolidate issue needs matching action wording"
                )
            if tt == "redirect" and "301" not in act and "redirect" not in act and "canonical" not in act:
                raise ValueError(
                    "[rule:executive_action_vs_type] redirect issue needs redirect or canonical wording"
                )


def validate_executive_alignment(summary_data: dict) -> None:
    """Structured checks before render."""
    issues = summary_data.get("top_issues") or []
    for iss in issues:
        if not isinstance(iss, dict):
            raise ValueError("[rule:executive_issue_shape] top_issues entries must be objects")
        prob = (iss.get("problem") or "").strip()
        if not prob:
            raise ValueError("[rule:executive_problem] missing problem")
        for term in _FORBIDDEN_EXECUTIVE_TERMS:
            if term in prob.lower():
                raise ValueError(f"[rule:executive_problem_clean] problem must not contain {term!r}")
