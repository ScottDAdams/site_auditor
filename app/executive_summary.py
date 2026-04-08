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
from app.decision_arbitration import resolve_primary_strategy, validate_narrative_against_strategy
from app.narrative_consolidation import build_consolidated_top_issues
from app.opportunity_analysis import analyze_opportunities

if TYPE_CHECKING:
    from app.ai_insights import LLMClient

# Executive prose must not read like raw telemetry or internal schema.
_FORBIDDEN_EXECUTIVE_TERMS = (
    "overlap_rate",
    "avg_cluster_similarity",
    "content_uniqueness_score",
    "embedding similarity",
    "embedding",
    "avg_similarity",
    "cluster_similarity",
    "duplicate_groups",
    "content_uniqueness",
)

_SEO_JARGON_TERMS = (
    "serp",
    "backlink",
    "canonicalization",
    "cannibalization",
    "keyword cannibal",
    "meta description",
    "title tag",
)

# Opening must not read like multiple competing directives.
_DIRECTION_WORDS_RE = re.compile(
    r"\b(merge|consolidat|redirect|301|differentiate|split|isolate|assign distinct|"
    r"retire duplicate|canonicalize)\b",
    re.I,
)

_TECH_CAUSE_LEAD = re.compile(
    r"(?m)^\s*(?:\d+\.|[-*•])?\s*"
    r"(crawl|indexing|indexable|http status|server response|query string|"
    r"rel=canonical|duplicate url|telemetry)\b",
    re.I,
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
            "Your ability to be found and capture demand is split across competing pages. "
            "Traffic and attention scatter instead of compounding on one winner."
        )
    if tt in ("isolate", "differentiate", "split"):
        return (
            "Buyers see similar pages with unclear roles. Conversion suffers at the moment of choice."
        )
    if tt == "redirect":
        return "The same story lives on multiple URLs. Attention and demand leak across copies."
    if tt == "retain":
        return "Overlap is contained for now, but without guardrails it can creep back."
    if tt == "elevate":
        return "The hub is not yet the obvious front door for this topic—navigation and pull stay fragmented."
    if tt == "demote":
        return "Supporting pages steal attention from the paths that should close business."
    return (
        "Overlapping pages fight for the same job. You compete against yourself instead of the market."
    )


def map_action_to_outcome(transformation_type: str) -> str:
    tt = (transformation_type or "").strip().lower()
    if tt in ("merge", "consolidate"):
        return "One primary page captures demand. You stop competing against yourself on the same story."
    if tt in ("differentiate", "isolate", "split"):
        return "Each page owns a clear job. Buyers move forward with less friction."
    if tt == "redirect":
        return "One live URL holds the full story. Demand and handoffs stay concentrated."
    if tt == "retain":
        return "Scope stays explicit; drift is visible before it spreads."
    if tt == "elevate":
        return "The hub becomes the obvious entry; downstream pages support one narrative."
    if tt == "demote":
        return "Primary paths stay clean; detail stays available without stealing the decision."
    return "One clear owner per intent. Less internal competition, clearer capture."


def _problem_title(transformation_type: str) -> str:
    """One-line skim title for UI slots (not a paragraph)."""
    tt = (transformation_type or "").strip().lower()
    if tt in ("merge", "consolidate"):
        return "Overlapping pages fight for the same buyer job."
    if tt == "redirect":
        return "Multiple URLs tell the same story."
    if tt in ("isolate", "differentiate", "split"):
        return "Similar pages blur which one should win."
    if tt == "retain":
        return "Overlap is under control—for now."
    if tt == "elevate":
        return "The hub is not yet the obvious front door."
    if tt == "demote":
        return "Detail pages are stealing attention from closers."
    return "Split focus across competing surfaces."


def _decision_line(transformation_type: str, urls: list[str]) -> str:
    """Direct advisory language (you are not merely suggesting)."""
    tt = (transformation_type or "").strip().lower()
    u0 = urls[0] if urls else "your primary URL"
    u1 = urls[1] if len(urls) > 1 else ""
    if tt in ("merge", "consolidate"):
        if u1:
            return (
                f"You should merge these pages into a single primary page; fold overlapping content from "
                f"{u0} and {u1} into one winner."
            )
        return f"You should merge duplicate surfaces into one primary page anchored at {u0}."
    if tt == "redirect":
        if u1:
            return (
                f"You should redirect the duplicate route to one canonical destination "
                f"({u0} as primary, {u1} as alternate)."
            )
        return (
            f"You should redirect duplicate routes so only {u0} remains the customer-facing destination."
        )
    if tt in ("isolate", "differentiate", "split"):
        if u1:
            return (
                f"You should split roles: make {u0} and {u1} serve different buyer decisions "
                f"with different proof and offers."
            )
        return (
            f"You should give {u0} a distinct job so it stops fighting sibling pages for the same decision."
        )
    if tt == "retain":
        return (
            f"You should keep {u0} live, document its scope, and watch for drift—no structural merge now."
        )
    return (
        "You should pick one page to own this decision and align the rest as support or redirects."
    )


def _why_line(transformation_type: str) -> str:
    tt = (transformation_type or "").strip().lower()
    if tt in ("merge", "consolidate"):
        return "Competing intent is splitting authority and blurring which page should win the buyer."
    if tt == "redirect":
        return "Two doors to the same story dilute focus and waste attention you could spend on conversion."
    if tt in ("isolate", "differentiate", "split"):
        return "Similar pages force trade-offs in messaging and weaken clarity at the moment of choice."
    if tt == "retain":
        return "Structure is acceptable; the risk is silent drift that recreates overlap later."
    return "Without a single owner for this intent, marketing and product narratives stay out of sync."


def _risk_if_ignored_line(transformation_type: str) -> str:
    _ = transformation_type
    return (
        "You keep competing against yourself—paid spend papers over a structural hole you could fix in the site."
    )


def build_primary_bet(summary_data: dict) -> dict[str, str]:
    """Single call that matters — derived from the highest-priority decision."""
    issues = [i for i in (summary_data.get("top_issues") or []) if isinstance(i, dict)]
    if not issues:
        return {
            "action": (
                "You should name one primary page for each major buyer decision before you fund more content "
                "or paid reach."
            ),
            "why_this_over_others": (
                "Every other initiative depends on that clarity; without it, teams optimize different pages for the same job."
            ),
            "expected_effect": (
                "Faster alignment, cleaner handoffs, and less spend re-teaching the same story in ads and sales."
            ),
        }
    first = issues[0]
    dec = str(first.get("decision") or "").strip()
    out = str(first.get("outcome") or "").strip()
    return {
        "action": dec or "You should resolve the lead structural conflict before you scale anything else.",
        "why_this_over_others": (
            "It targets the highest-priority split this audit surfaced—before you add inventory or buy more reach."
        ),
        "expected_effect": out or "Clearer ownership per journey and less internal competition for the same buyer.",
    }


def estimate_impact(summary_data: dict) -> dict[str, str]:
    """
    Heuristic materiality (no GA). Signals overlap cost, not revenue.
    """
    issues = [i for i in (summary_data.get("top_issues") or []) if isinstance(i, dict)]
    n_issues = len(issues)
    max_ps = 0.0
    for i in issues:
        try:
            max_ps = max(max_ps, float(i.get("priority_score") or 0))
        except (TypeError, ValueError):
            pass
    sh = summary_data.get("site_health") or {}
    risk = str(sh.get("risk_level") or "moderate").lower()

    severity = 0
    if n_issues >= 4:
        severity += 2
    elif n_issues >= 2:
        severity += 1
    if max_ps >= 65:
        severity += 2
    elif max_ps >= 45:
        severity += 1
    if risk in ("high",) or (risk == "moderate" and max_ps >= 55):
        severity += 2
    elif risk == "moderate":
        severity += 1

    if severity >= 5:
        level = "High"
    elif severity >= 3:
        level = "Medium"
    else:
        level = "Low"

    confidence = "Strong" if n_issues >= 2 and max_ps >= 50 else "Directional"
    reasoning = (
        f"{n_issues} competing decision group(s), peak structural signal {max_ps:.0f}, and risk profile "
        f"({risk}) indicate how material overlap is for this crawl—a materiality flag, not a revenue model."
    )
    return {
        "impact_level": level,
        "confidence": confidence,
        "reasoning": reasoning,
    }


EXPECTED_OUTCOME_BULLETS = (
    "Stronger authority on key pages.",
    "Clearer user paths.",
    "Better conversion capture.",
)


def build_ceo_summary_struct(num_issue_groups: int) -> dict[str, Any]:
    """Skimmable CEO copy as discrete paragraphs (UI slots, not one blob)."""
    areas = max(int(num_issue_groups or 0), 1)
    area_word = "area" if areas == 1 else "areas"
    return {
        "paragraphs": [
            (
                f"Your site splits focus across {areas} key {area_word}. "
                f"That caps how well you can be found and capture demand."
            ),
            (
                "Fix the lead conflict before you add pages or paid reach. "
                "Otherwise you compound the split."
            ),
            (
                "Ignore this and you keep competing against yourself—paid acquisition replaces "
                "clarity you could fix in structure."
            ),
        ]
    }


def render_ceo_summary(summary_data: dict) -> str:
    """
    Section 1 only (CEO summary): bottom line + cost of inaction.
    Primary decision is surfaced in the UI hero via primary_bet on summary_data.
    """
    sd = summary_data or {}
    block = sd.get("ceo_summary")
    if isinstance(block, dict):
        paras = block.get("paragraphs") or []
        paras = [str(p).strip() for p in paras if str(p).strip()]
        if paras:
            s1 = "SECTION 1: CEO SUMMARY"
            body = "\n\n".join(paras)
            return f"{s1}\n\n{body}".strip()

    issues = [i for i in (sd.get("top_issues") or []) if isinstance(i, dict)]
    areas = max(len(issues), 1)
    area_word = "area" if areas == 1 else "areas"

    s1 = "SECTION 1: CEO SUMMARY"
    bottom = (
        f"Your site is splitting focus across {areas} key {area_word}.\n\n"
        f"This caps your ability to be found and capture demand.\n\n"
        f"Fix the lead conflict first—then content and spend compound."
    )
    stall = (
        f"If you do nothing, you keep competing against yourself.\n\n"
        f"Growth plateaus even with more pages.\n\n"
        f"Paid acquisition fills a gap that structure could have closed."
    )
    return f"{s1}\n\n{bottom}\n\n{stall}".strip()


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


def _build_legacy_top_issues(
    payload: dict,
    insights: dict,
    top_n: list[dict],
    strategic: list[dict],
    metrics: dict,
) -> list[dict[str, Any]]:
    """Per-cluster cards (pre Phase 10) when consolidation yields nothing."""
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

        decision = _decision_line(tt, urls)
        why = _why_line(tt)
        risk_if_ignored = _risk_if_ignored_line(tt)
        outcome = map_action_to_outcome(tt)
        business_consequence = map_problem_to_business_impact(tt, metrics)
        problem_title = _problem_title(tt)
        top_issues.append(
            {
                "problem": problem_title,
                "impact": business_consequence,
                "decision": decision,
                "risk": risk_if_ignored,
                "outcome": outcome,
                "why": why,
                "business_consequence": business_consequence,
                "risk_if_ignored": risk_if_ignored,
                "urls": urls,
                "transformation_type": tt,
                "priority_score": ps_f,
                "priority_level": pl,
                "recommended_action": decision,
            }
        )
    return top_issues


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

    opps_early = payload.get("opportunities")
    if opps_early is None:
        opps_early = analyze_opportunities(payload)
    opps_early = opps_early[:3]
    ps_early = payload.get("primary_strategy") or resolve_primary_strategy(
        payload, insights, opps_early
    )

    findings = list(payload.get("audit_findings") or [])
    top_issues = build_consolidated_top_issues(
        payload,
        ps_early,
        findings,
        max_issues=3,
    )
    if not top_issues:
        top_issues = _build_legacy_top_issues(
            payload, insights, top_n, strategic, metrics
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
    summary_data["primary_bet"] = build_primary_bet(summary_data)
    summary_data["impact_estimate"] = estimate_impact(summary_data)
    summary_data["ceo_summary"] = build_ceo_summary_struct(len(top_issues))
    summary_data["expected_outcome"] = {"bullets": list(EXPECTED_OUTCOME_BULLETS)}
    summary_data["opportunities"] = opps_early
    summary_data["primary_strategy"] = payload.get("primary_strategy") or ps_early
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
            ck = str(iss.get("cluster_key") or "").strip()
            prefix = (
                f"{ck.replace('_', ' ').title()}: "
                if ck
                else ""
            )
            if act:
                actions.append(f"{prefix}{act}")
            elif urls:
                actions.append(
                    f"{prefix}Address URLs: {', '.join(urls[:3])}"
                )
        actions = actions[:4]
        out0 = map_action_to_outcome(str(group[0].get("transformation_type") or ""))
        plan.append(
            {
                "step": step_no,
                "focus": focus,
                "intent": _execution_step_tagline(focus),
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
                "consequence": "You keep splitting demand and competing against yourself on the same story.",
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


_EXEC_FOCUS_TAGLINE: dict[str, str] = {
    "Consolidate duplicate pages": "Unify overlapping pages so one surface owns each decision.",
    "Normalize technical duplicates": "Send every duplicate URL to one live destination.",
    "Clarify page roles": "Give each page a distinct job, proof, and next step.",
    "Retain scope and cleanup": "Lock what stays published and prevent drift back into overlap.",
}


def _execution_step_tagline(focus: str) -> str:
    f = (focus or "").strip()
    return _EXEC_FOCUS_TAGLINE.get(f, "Close this cluster before you add more surface area.")


def render_executive_summary(summary_data: dict) -> str:
    """Sections 3–5: breaking issues, execution plan, expected outcome (plain text)."""
    sd = summary_data or {}
    lines: list[str] = []

    issues = sd.get("top_issues") or []
    if issues:
        lines.append("SECTION 3: WHAT'S BREAKING PERFORMANCE")
        lines.append("")
        lines.append("")
        for i, iss in enumerate(issues, 1):
            if not isinstance(iss, dict):
                continue
            dec = (iss.get("decision") or iss.get("recommended_action") or "").strip()
            bc = (iss.get("business_consequence") or iss.get("business_impact") or "").strip()
            why = (iss.get("why") or "").strip()
            risk = (iss.get("risk_if_ignored") or "").strip()
            out = (iss.get("outcome") or "").strip()
            urls = iss.get("urls") or []
            tt = iss.get("transformation_type", "")
            prob = (iss.get("problem") or why).strip()
            lines.append(f"{i}. [{tt}]")
            lines.append(f"Problem: {prob}")
            lines.append(f"What it's doing to the business: {bc}")
            lines.append(f"What to do: {dec}")
            lines.append(f"What happens if you ignore it: {risk}")
            lines.append(f"On success: {out}")
            if urls:
                lines.append(f"URLs: {', '.join(str(u) for u in urls[:4])}")
            lines.append("")
            lines.append("")

    plan = sd.get("execution_plan") or []
    if plan:
        lines.append("SECTION 4: EXECUTION PLAN")
        lines.append("")
        lines.append("")
        for step in plan:
            if not isinstance(step, dict):
                continue
            sn = step.get("step", "")
            focus = str(step.get("focus") or "")
            tag = _execution_step_tagline(focus)
            try:
                sn_i = int(sn)
            except (TypeError, ValueError):
                sn_i = sn
            lines.append(f"Step {sn_i}. {tag}")
            for a in (step.get("actions") or [])[:4]:
                lines.append(f"  • {a}")
            lines.append("")
            lines.append("")

    qw = sd.get("quick_wins") or []
    if qw:
        lines.append("QUICK FIXES")
        lines.append("")
        lines.append("")
        for q in qw:
            if not isinstance(q, dict):
                continue
            act = (q.get("action") or "").strip()
            if act:
                lines.append(f"  • {act}")
        lines.append("")
        lines.append("")

    risks = sd.get("strategic_risks") or []
    if risks:
        lines.append("DELAY RISKS")
        lines.append("")
        lines.append("")
        for r in risks:
            if not isinstance(r, dict):
                continue
            lines.append(f"  • {r.get('risk', '')}: {r.get('consequence', '')}")
        lines.append("")
        lines.append("")

    lines.append("SECTION 5: EXPECTED OUTCOME")
    lines.append("")
    lines.append("")
    bullets = (sd.get("expected_outcome") or {}).get("bullets") or list(EXPECTED_OUTCOME_BULLETS)
    for b in bullets:
        lines.append(str(b).strip())
    return "\n".join(lines).strip()


def render_executive_summary_llm(summary_data: dict, llm_client: LLMClient | None = None) -> str:
    """
    Optional polish only. Preserves CEO + execution structure separated by a --- line.
    """
    if llm_client is None:
        if not os.getenv("OPENAI_API_KEY"):
            return ""
        from app.ai_insights import LLMClient

        llm_client = LLMClient()

    sd = summary_data or {}
    ceo_draft = render_ceo_summary(sd)
    exec_draft = render_executive_summary(sd)
    combined = f"{ceo_draft}\n---\n{exec_draft}"
    blob = json.dumps(sd, indent=2, default=str)
    prompt = f"""You are an editor. Polish wording only for the client brief below.

RULES (strict):
- Do NOT add new facts, URLs, issues, steps, or recommendations.
- Do NOT change which issues appear or their transformation types.
- Do NOT introduce internal metric or schema tokens (overlap_rate, avg_cluster_similarity, content_uniqueness_score, embedding, duplicate_groups).
- Do NOT start any sentence with a metric name or number-led telemetry.
- Do NOT use SERP/backlink/cannibalization/meta description/title tag jargon.
- Keep exactly one "---" separator on its own line between Part A (CEO / decision brief) and Part B (execution plan).
- Part A must stay business-led; do not drag crawl or indexing-led explanations into Part A.
- Part B keeps sections in order: SECTION 3 WHAT'S BREAKING PERFORMANCE, SECTION 4 EXECUTION PLAN, QUICK FIXES, DELAY RISKS, SECTION 5 EXPECTED OUTCOME (keep the three closing outcome lines verbatim in meaning).
- Keep every URL that appears in the input; do not invent URLs.
- Output plain text only (no markdown code fences).

STRUCTURED INPUT (for reference only):
{blob}

TEXT TO POLISH (source of truth for facts and URLs):
{combined}
"""
    return llm_client.generate(prompt).strip()


def split_ceo_and_operational(full_text: str) -> tuple[str, str]:
    sep = "\n---\n"
    if sep in (full_text or ""):
        a, b = full_text.split(sep, 1)
        return a.strip(), b.strip()
    return (full_text or "").strip(), ""


def _first_paragraph(text: str) -> str:
    t = (text or "").strip()
    if "\n\n" in t:
        return t.split("\n\n", 1)[0].strip()
    return t


def _direction_count_in_opening(operational_brief: str) -> int:
    return len(_DIRECTION_WORDS_RE.findall(_first_paragraph(operational_brief)))


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


def validate_executive_output(
    text: str,
    summary_data: dict | None = None,
    *,
    operational_brief: str | None = None,
) -> None:
    """
    Client-facing brief: no telemetry tokens, no SEO jargon, no technical-led sentences
    in the operational layer opening, and at most one directional call in that opening.
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
    for term in _SEO_JARGON_TERMS:
        if term in low:
            raise ValueError(f"[rule:executive_no_seo_jargon] executive text must not contain {term!r}")
    if _METRIC_LEAD.search(t):
        raise ValueError("[rule:executive_metric_lead] line starts with metric-style token")
    if _TELEMETRY_PHRASE.search(t):
        raise ValueError("[rule:executive_metric_first_sentence] metric-led explanation forbidden")

    op = (operational_brief or "").strip()
    if not op and "\n---\n" in t:
        _, op = split_ceo_and_operational(t)
    if op:
        if _TECH_CAUSE_LEAD.search(op):
            raise ValueError(
                "[rule:executive_tech_cause_lead] operational brief must not lead lines with crawl/indexing-style causes"
            )
        if _direction_count_in_opening(op) > 1:
            raise ValueError(
                "[rule:executive_single_direction_opening] operational opening must not contain multiple directional calls"
            )

    if summary_data:
        issues = summary_data.get("top_issues") or []
        for iss in issues:
            if not isinstance(iss, dict):
                continue
            bc = (iss.get("business_consequence") or iss.get("business_impact") or "").strip()
            if len(bc.split()) < 6:
                raise ValueError(
                    "[rule:executive_issue_consequence] each issue needs a substantive business_consequence"
                )
            dec = (iss.get("decision") or iss.get("recommended_action") or "").strip()
            if len(dec.split()) < 4:
                raise ValueError("[rule:executive_issue_decision] each issue needs a clear decision line")
            why = (iss.get("why") or "").strip()
            if len(why.split()) < 4:
                raise ValueError("[rule:executive_issue_why] each issue needs a substantive why")
            risk = (iss.get("risk_if_ignored") or "").strip()
            if len(risk.split()) < 6:
                raise ValueError("[rule:executive_issue_risk] each issue needs risk_if_ignored detail")
            out = (iss.get("outcome") or "").strip()
            if len(out.split()) < 4:
                raise ValueError("[rule:executive_issue_outcome] each issue needs a substantive outcome")
            tt = str(iss.get("transformation_type") or "").lower()
            act = dec.lower()
            if tt in ("merge", "consolidate") and "merge" not in act and "consolidat" not in act:
                raise ValueError(
                    "[rule:executive_action_vs_type] merge/consolidate issue needs matching decision wording"
                )
            if tt == "redirect" and "301" not in act and "redirect" not in act and "canonical" not in act:
                raise ValueError(
                    "[rule:executive_action_vs_type] redirect issue needs redirect or canonical wording"
                )

        pb = summary_data.get("primary_bet")
        if not isinstance(pb, dict):
            raise ValueError("[rule:executive_primary_bet] primary_bet object is required")
        for k in ("action", "why_this_over_others", "expected_effect"):
            if len(str(pb.get(k) or "").split()) < 4:
                raise ValueError(f"[rule:executive_primary_bet_field] primary_bet.{k} must be substantive")

        imp = summary_data.get("impact_estimate")
        if not isinstance(imp, dict):
            raise ValueError("[rule:executive_impact_estimate] impact_estimate object is required")
        for k in ("impact_level", "confidence", "reasoning"):
            if not str(imp.get(k) or "").strip():
                raise ValueError(f"[rule:executive_impact_field] impact_estimate.{k} is required")

        ps = summary_data.get("primary_strategy")
        if isinstance(ps, dict) and str(ps.get("strategy") or "").strip():
            validate_narrative_against_strategy(t, ps)


def validate_executive_alignment(summary_data: dict) -> None:
    """Structured checks before render."""
    cs = summary_data.get("ceo_summary")
    if not isinstance(cs, dict):
        raise ValueError("[rule:ceo_summary_shape] ceo_summary must be an object")
    paras = cs.get("paragraphs") or []
    if not (2 <= len(paras) <= 4):
        raise ValueError("[rule:ceo_summary_paragraphs] ceo_summary needs 2–4 paragraphs")
    for p in paras:
        if len(str(p).split()) < 8:
            raise ValueError("[rule:ceo_summary_paragraph_density] each CEO paragraph must be substantive")

    eo = summary_data.get("expected_outcome")
    if not isinstance(eo, dict) or len(eo.get("bullets") or []) < 3:
        raise ValueError("[rule:expected_outcome] expected_outcome.bullets (3+) required")

    issues = summary_data.get("top_issues") or []
    for iss in issues:
        if not isinstance(iss, dict):
            raise ValueError("[rule:executive_issue_shape] top_issues entries must be objects")
        prob_slot = (iss.get("problem") or "").strip()
        if not prob_slot:
            raise ValueError("[rule:executive_problem_slot] missing problem title")
        dec = (iss.get("decision") or iss.get("recommended_action") or "").strip()
        if not dec:
            raise ValueError("[rule:executive_decision] missing decision")
        for term in _FORBIDDEN_EXECUTIVE_TERMS:
            if term in dec.lower():
                raise ValueError(f"[rule:executive_decision_clean] decision must not contain {term!r}")
        why = (iss.get("why") or "").strip()
        if not why:
            raise ValueError("[rule:executive_why] missing why")
        bc = (iss.get("business_consequence") or iss.get("business_impact") or "").strip()
        if not bc:
            raise ValueError("[rule:executive_business_consequence] missing business_consequence")
        risk = (iss.get("risk_if_ignored") or "").strip()
        if not risk:
            raise ValueError("[rule:executive_risk_if_ignored] missing risk_if_ignored")
        out = (iss.get("outcome") or "").strip()
        if not out:
            raise ValueError("[rule:executive_outcome] missing outcome")
        for term in _SEO_JARGON_TERMS:
            blob = f"{dec} {why} {bc} {risk} {out}".lower()
            if term in blob:
                raise ValueError(f"[rule:executive_issue_no_seo_jargon] issue text must not contain {term!r}")

    pb = summary_data.get("primary_bet")
    if not isinstance(pb, dict):
        raise ValueError("[rule:align_primary_bet] primary_bet required")
    for k in ("action", "why_this_over_others", "expected_effect"):
        if not str(pb.get(k) or "").strip():
            raise ValueError(f"[rule:align_primary_bet_field] primary_bet.{k} required")

    imp = summary_data.get("impact_estimate")
    if not isinstance(imp, dict):
        raise ValueError("[rule:align_impact_estimate] impact_estimate required")
    for k in ("impact_level", "confidence", "reasoning"):
        if not str(imp.get(k) or "").strip():
            raise ValueError(f"[rule:align_impact_field] impact_estimate.{k} required")

    ps = summary_data.get("primary_strategy")
    if not isinstance(ps, dict):
        raise ValueError("[rule:summary_primary_strategy_shape] primary_strategy object required")
    if not str(ps.get("strategy") or "").strip():
        raise ValueError("[rule:summary_primary_strategy_key] primary_strategy.strategy required")
    if not str(ps.get("label") or "").strip():
        raise ValueError("[rule:summary_primary_strategy_label] primary_strategy.label required")
