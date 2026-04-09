"""
10-slide boardroom narrative derived from executive summary_data (deterministic, no LLM).
"""

from __future__ import annotations

from typing import Any


def _pts(*items: str) -> list[str]:
    return [x.strip() for x in items if x and str(x).strip()]


def build_boardroom_summary(summary_data: dict[str, Any] | None) -> dict[str, Any]:
    """
    Strict 10-slide structure for internal defense / exec readouts.

    Slides: title, headline, points (list of strings).
    """
    sd = summary_data or {}
    slides: list[dict[str, Any]] = []

    sh = sd.get("site_health") or {}
    es = sd.get("ceo_summary") or {}
    paras = es.get("paragraphs") if isinstance(es, dict) else None
    situation = ""
    if isinstance(paras, list) and paras:
        situation = str(paras[0]).strip()
    if not situation:
        situation = (
            f"Structural focus is {sh.get('primary_issue_type', 'mixed')} with "
            f"{sh.get('risk_level', 'moderate')} risk in this crawl."
        )

    issues = [i for i in (sd.get("top_issues") or []) if isinstance(i, dict)]
    first = issues[0] if issues else {}
    core_problem = (first.get("problem") or first.get("cluster_skim") or "").strip()
    if not core_problem:
        core_problem = "No dominant cluster surfaced in this crawl slice."

    bc0 = (first.get("business_consequence") or first.get("impact") or "").strip()
    ie = sd.get("impact_estimate") or {}
    imp_line = (ie.get("reasoning") or "").strip()
    why_matters_pts = _pts(
        bc0,
        imp_line,
        "Overlap splits demand across URLs instead of compounding on one winner per decision.",
    )

    ev = (first.get("evidence") or {}) if first else {}
    m = sd.get("site_health") or {}
    overlap_note = ""
    metrics = sd.get("_metrics_snapshot") or {}
    if isinstance(metrics, dict):
        orate = metrics.get("overlap_rate")
        asim = metrics.get("avg_cluster_similarity")
        if orate is not None:
            overlap_note = f"Crawl overlap rate {float(orate) * 100:.1f}% of sampled pages sit in conflict clusters."
        if asim is not None:
            overlap_note = (
                f"{overlap_note} Average within-cluster similarity {float(asim) * 100:.1f}%."
            ).strip()
    if not overlap_note:
        overlap_note = "Similarity and overlap metrics are captured in the technical audit packet."
    sim = ev.get("similarity_score")
    sim_line = (
        f"Representative combined similarity signal: {int(round(float(sim) * 100))}%."
        if sim is not None
        else "Similarity is summarized per issue in the evidence pack."
    )
    shared = ev.get("shared_sections") or []
    ev_pts = _pts(sim_line, overlap_note, *(str(s) for s in shared[:4]))

    ps = sd.get("primary_strategy") or {}
    decision_headline = (ps.get("label") or "Align structure to primary strategy").strip()
    decision_pts = _pts(str(ps.get("reasoning") or ""))

    rat = (first.get("decision_rationale") or "").strip()
    why_dec_pts = _pts(rat, ps.get("reasoning") or "")

    pb = sd.get("primary_bet") or {}
    changes_pts = _pts(
        str(pb.get("action") or ""),
        *(str(x) for x in (sd.get("expected_outcome") or {}).get("bullets") or []),
    )

    plan = sd.get("execution_plan") or []
    exec_pts: list[str] = []
    for step in plan[:5]:
        if not isinstance(step, dict):
            continue
        focus = step.get("focus") or step.get("intent") or "Step"
        for a in (step.get("actions") or [])[:2]:
            exec_pts.append(f"{focus}: {a}")
    if not exec_pts:
        exec_pts = ["Use the execution plan in the decision brief; steps are ordered by structural priority."]

    risks = sd.get("strategic_risks") or []
    risk_pts = [
        f"{r.get('risk', '')}: {r.get('consequence', '')}"
        for r in risks
        if isinstance(r, dict) and (r.get("risk") or r.get("consequence"))
    ]
    if not risk_pts:
        risk_pts = [
            "Delay keeps split demand and unclear page roles.",
            "Paid channels mask structural gaps that the site can fix directly.",
        ]

    outcome_bullets = (sd.get("expected_outcome") or {}).get("bullets") or []
    out_pts = [str(b).strip() for b in outcome_bullets if str(b).strip()]
    if not out_pts:
        out_pts = [
            "Stronger authority on key pages.",
            "Clearer user paths.",
            "Better conversion capture.",
        ]

    slides = [
        {
            "title": "Situation",
            "headline": "What is happening at a high level",
            "points": _pts(situation),
        },
        {
            "title": "Core problem",
            "headline": "Single dominant structural issue",
            "points": _pts(core_problem),
        },
        {
            "title": "Why it matters",
            "headline": "Business impact",
            "points": why_matters_pts[:5],
        },
        {
            "title": "Evidence",
            "headline": "Proof from crawl and similarity",
            "points": ev_pts[:6],
        },
        {
            "title": "Decision",
            "headline": "Primary strategy",
            "points": _pts(decision_headline, *decision_pts[:3]),
        },
        {
            "title": "Why this decision",
            "headline": "Reasoning tied to evidence",
            "points": why_dec_pts[:5],
        },
        {
            "title": "What changes",
            "headline": "After execution",
            "points": changes_pts[:6],
        },
        {
            "title": "Execution plan",
            "headline": "Ordered actions",
            "points": exec_pts[:5],
        },
        {
            "title": "Risks of inaction",
            "headline": "Direct consequences",
            "points": risk_pts[:5],
        },
        {
            "title": "Expected outcome",
            "headline": "Business outcomes",
            "points": out_pts[:5],
        },
    ]

    return {"slides": slides}
