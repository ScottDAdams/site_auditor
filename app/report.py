from html import escape

from app.analyzer import REMEDIATION_DECISION_TYPES
from app.scoring.benchmarks import classify_overlap_rate, get_scoring_weights
from app.scoring.urgency import classify_urgency

# Tooltip copy for key metrics only (keeps total report tooltips intentional; ~6 max).
_METRIC_TOOLTIPS = {
    "overlap_rate": (
        "Percent of pages that exist in duplication or overlap clusters. "
        "High values mean your site structure is competing with itself."
    ),
    "avg_cluster_similarity": (
        "How similar pages are within clusters. Values near 1.0 indicate near-identical "
        "content competing for the same intent."
    ),
    "content_uniqueness_score": (
        "Inverse of similarity. Low scores mean your pages are not differentiated enough "
        "to rank independently."
    ),
}


def _duplication_assessment_label(dup_class: str | None) -> str:
    if not dup_class:
        return "—"
    return {
        "acceptable": "No action needed",
        "competitive": "Competing pages",
        "technical": "Technical duplication",
        "needs_review": "Needs review",
    }.get(dup_class, dup_class)


def _safe_float(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def render_tooltip(text: str) -> str:
    """Small inline help icon; `text` is HTML-escaped. Use only on section/metric headers."""
    t = escape(text)
    return (
        '<span class="info-tooltip" tabindex="0" role="button" aria-label="More information">ⓘ'
        f'<span class="tooltip-content">{t}</span></span>'
    )


_WRAPPER = (
    'style="font-family: system-ui, -apple-system, Segoe UI, sans-serif; '
    "max-width: 920px; line-height: 1.55; color: #1a1a1a; padding: 28px 32px; "
    'background: #f5f6f8; border-radius: 12px;"'
)
_SECTION = (
    'class="audit-section" style="margin-bottom: 32px; padding: 22px 26px; border-radius: 10px; '
    "background: #fafbfd; border: 1px solid #e4e7ec; "
    'box-shadow: 0 1px 3px rgba(0,0,0,0.04);"'
)
_SCORE_BOX = (
    'style="padding: 18px 22px; border-radius: 8px; background: #f8f9fa; '
    'border: 1px solid #dee1e5;"'
)
_FINDING_CARD = (
    'style="border-left: 4px solid #f0ad4e; padding: 12px 14px; margin-bottom: 14px; '
    'background: #fffdf8; border-radius: 0 8px 8px 0;"'
)

ACTION_TYPE_HINTS = {
    "differentiate": "Differentiate buyer intent and proof blocks per URL",
    "reposition": "Adjust intent targeting",
    "none": "No structural content change in this step",
}


def render_insight_narrative_html(insight: dict) -> str:
    """Top-of-report narrative: what, why, action, optional example, and meta (HTML-escaped)."""
    esc = escape
    cp = (insight.get("core_problem") or "").strip()
    if insight.get("validated_ai_narrative"):
        bi = (insight.get("why_it_matters") or "").strip()
        rec = (insight.get("primary_action") or "").strip()
    else:
        bi = (
            (insight.get("why_it_matters") or insight.get("business_impact") or "")
            .strip()
        )
        rec = (
            (insight.get("primary_action") or insight.get("recommendation") or "")
            .strip()
        )
    ex = (insight.get("execution_example") or "").strip()
    conf = (insight.get("confidence") or "High").strip() or "High"
    imp = (insight.get("impact_level") or "High").strip() or "High"
    blocks = []
    if cp:
        h_whats = esc("What's happening")
        blocks.append(
            f'<h2 style="margin: 18px 0 8px 0; font-size: 1.05rem; font-weight: 700;">'
            f"{h_whats}</h2>"
            f'<p style="margin: 0; font-size: 1.02rem; line-height: 1.5;">{esc(cp)}</p>'
        )
    if bi:
        blocks.append(
            f'<h2 style="margin: 18px 0 8px 0; font-size: 1.05rem; font-weight: 700;">'
            f'{esc("Why it matters")}</h2>'
            f'<p style="margin: 0; font-size: 1.02rem; line-height: 1.5;">{esc(bi)}</p>'
        )
    if rec:
        blocks.append(
            f'<h2 style="margin: 18px 0 8px 0; font-size: 1.05rem; font-weight: 700;">'
            f'{esc("What to do")}</h2>'
            f'<p style="margin: 0; font-size: 1.02rem; line-height: 1.5;">{esc(rec)}</p>'
        )
    if ex:
        blocks.append(
            f'<h2 style="margin: 18px 0 8px 0; font-size: 1.05rem; font-weight: 700;">'
            f'{esc("Execution example")}</h2>'
            f'<p style="margin: 0; font-size: 1.02rem; line-height: 1.5;">{esc(ex)}</p>'
        )
    if not blocks:
        return ""
    meta = (
        f'<div class="exec-meta" style="display: flex; flex-wrap: wrap; gap: 16px; margin-top: 18px; '
        f'padding-top: 14px; border-top: 1px solid #dee2e6; font-size: 0.88rem; color: #495057;">'
        f"<span><strong>{esc('Confidence:')}</strong> {esc(conf)}</span>"
        f"<span><strong>{esc('Impact:')}</strong> {esc(imp)}</span>"
        f"</div>"
    )
    return (
        '<div class="exec-summary" style="margin-bottom: 28px; padding: 22px 26px; '
        "background: #ffffff; border: 1px solid #e0e3e8; border-radius: 10px; "
        'box-shadow: 0 1px 4px rgba(0,0,0,0.05);">'
        f'{"".join(blocks)}'
        f"{meta}"
        "</div>"
    )


def render_client_executive_brief_html(brief: str) -> str:
    """Phase 6 client executive layer (plain text, pre-wrapped, HTML-escaped)."""
    b = (brief or "").strip()
    if not b:
        return ""
    esc = escape
    return (
        f"<div {_SECTION}>"
        f'<h2 style="margin: 0 0 14px 0; font-size: 1.2rem;">{esc("Executive brief")}</h2>'
        '<p style="margin: 0 0 10px 0; color: #5c6370; font-size: 0.92rem;">'
        f"{esc('Prioritized issues, plan, and risks in business language.')}</p>"
        f'<div style="white-space: pre-wrap; font-size: 0.98rem; line-height: 1.5; margin: 0;">'
        f"{esc(b)}</div>"
        "</div>"
    )


def _roadmap_step_heading(esc, step, title: str) -> str:
    t = (title or "").strip()
    try:
        n = int(step)
        sn = str(n)
    except (TypeError, ValueError):
        sn = str(step).strip() if str(step).strip() else "?"
    if t:
        return esc(f"Step {sn} — {t}")
    return esc(f"Step {sn}")


def render_technical_seo_fixes(esc, clusters: list) -> str:
    technical = [
        c
        for c in (clusters or [])
        if c.get("decision_type") == "technical_fix"
    ]
    if not technical:
        return ""
    cards = []
    for c in technical:
        urls = [p.get("url") for p in c.get("pages", []) if p.get("url")]
        issue = c.get("technical_issue") or "canonical duplication"
        fix = c.get("technical_fix_recommendation") or (
            "301 redirect + rel=canonical on duplicate URLs"
        )
        ulist = "".join(f"<li>{esc(u)}</li>" for u in urls[:12])
        cards.append(
            '<div style="border: 1px solid #cfe2ff; padding: 14px 16px; margin-bottom: 12px; '
            'background: #f8fbff; border-radius: 8px;">'
            f'<p style="margin: 0 0 8px 0; font-weight: 700;">{esc("URLs")}</p>'
            f'<ul style="margin: 0 0 10px 0;">{ulist}</ul>'
            f'<p style="margin: 0 0 6px 0; font-size: 0.92rem;"><strong>{esc("Issue:")}</strong> '
            f"{esc(issue)}</p>"
            f'<p style="margin: 0; font-size: 0.92rem;"><strong>{esc("Fix:")}</strong> '
            f"{esc(fix)}</p>"
            "</div>"
        )
    body = "".join(cards)
    tech_h2 = (
        f'{esc("Technical cleanup (quick wins)")}'
        f'{render_tooltip("Canonical, slash, and hostname variants. Fix these before larger content work.")}'
    )
    return (
        f"<div {_SECTION}>"
        f'<h2 style="margin: 0 0 12px 0; font-size: 1.2rem;">{tech_h2}</h2>'
        f'<p style="margin: 0 0 14px 0; color: #5c6370; font-size: 0.92rem;">'
        f"{esc('Canonical duplicates, trailing-slash or hostname variants, and homepage aliases—not content strategy items.')}</p>"
        f"{body}"
        "</div>"
    )


def _overlap_rate_metric_block(esc, row: dict, fallback_metrics: dict) -> str:
    raw_v = row.get("value", "")
    v = _safe_float(raw_v)
    if v == 0.0 and fallback_metrics:
        v = _safe_float(fallback_metrics.get("overlap_rate"))
    level, benchmark = classify_overlap_rate(v)
    badge_class = level.lower().replace(" ", "-")
    label_line = esc("overlap_rate") + render_tooltip(_METRIC_TOOLTIPS["overlap_rate"])
    implication = esc(str(row.get("implication", "")))
    display_val = str(raw_v).strip() if str(raw_v).strip() != "" else str(v)
    return (
        '<div class="metric" style="margin-bottom: 14px; padding: 14px 16px; background: #fff; '
        'border: 1px solid #e4e7ec; border-radius: 8px;">'
        '<div class="metric-header" style="display: flex; align-items: center; flex-wrap: wrap; '
        'gap: 8px; margin-bottom: 6px; font-size: 0.72rem; text-transform: uppercase; color: #868e96;">'
        f"{label_line}"
        f'<span class="metric-badge {esc(badge_class)}">{esc(level)}</span>'
        "</div>"
        f'<div class="metric-value" style="font-size: 1.2rem; font-weight: 700;">{esc(display_val)}</div>'
        '<div class="metric-context" style="margin-top: 6px; font-size: 0.92rem; color: #495057;">'
        f"{esc(benchmark)} — {esc('high duplication footprint')}"
        "</div>"
        f'<p style="margin: 10px 0 0 0; font-size: 0.92rem; color: #343a40;">'
        f'<strong>{esc("Readout")}:</strong> {implication}</p>'
        "</div>"
    )


def _decision_frame_block(
    esc, ai: dict, metrics: dict, strategic_cluster_count: int
) -> str:
    secondary = (ai.get("secondary_issue") or "").strip()
    overlap = _safe_float(metrics.get("overlap_rate"))
    weights = get_scoring_weights()
    urgency = classify_urgency(overlap, strategic_cluster_count)
    parts_inner = []
    parts_inner.append(
        f'<p style="margin: 0 0 10px 0; font-size: 0.95rem;">'
        f"<strong>{esc('Time sensitivity:')}</strong> {esc(urgency)}</p>"
    )
    if secondary:
        parts_inner.append(
            f'<p style="margin: 0 0 10px 0; font-size: 0.95rem;">'
            f"<strong>{esc('Secondary issue:')}</strong> {esc(secondary)}</p>"
        )
    if overlap > 0.45:
        pillar = "Content Quality"
        pct = int(round(weights.get("Content Quality", 0.25) * 100))
        parts_inner.append(
            f'<p style="margin: 0; font-size: 0.95rem;">'
            f"<strong>{esc('Primary impact area:')}</strong> {esc(pillar)} "
            f"({pct}% {esc('of total score weight')})</p>"
        )
    if not parts_inner:
        return ""
    return (
        '<div class="decision-frame" style="margin-bottom: 24px; padding: 18px 20px; '
        "background: #f0f4ff; border: 1px solid #c7d2fe; border-radius: 10px;\">"
        f'{"".join(parts_inner)}'
        "</div>"
    )


def _score_color(label: str) -> str:
    return {
        "Strong": "#5cb85c",
        "Good": "#5bc0de",
        "Moderate Risk": "#f0ad4e",
        "High Risk": "#d9534f",
    }.get(label, "#d9534f")


def _metrics_explained_table(esc, rows: list, fallback_metrics: dict) -> str:
    rows = [r for r in (rows or []) if isinstance(r, dict)]
    if not rows and fallback_metrics:
        rows = [
            {
                "metric": "overlap_rate",
                "value": str(fallback_metrics.get("overlap_rate", "")),
                "implication": "Share of pages touched by overlap signals.",
            },
            {
                "metric": "avg_cluster_similarity",
                "value": str(fallback_metrics.get("avg_cluster_similarity", "")),
                "implication": (
                    "Near 1.0 means paired pages are indistinguishable in purpose and compete "
                    "for the same user decision."
                ),
            },
            {
                "metric": "content_uniqueness_score",
                "value": str(fallback_metrics.get("content_uniqueness_score", "")),
                "implication": "Higher means more distinct copy between competing URLs.",
            },
        ]
    elif fallback_metrics and not any(
        str(r.get("metric", "")) == "overlap_rate" for r in rows
    ):
        rows.insert(
            0,
            {
                "metric": "overlap_rate",
                "value": str(fallback_metrics.get("overlap_rate", "")),
                "implication": "Share of pages touched by overlap signals.",
            },
        )
    inner = []
    for row in rows:
        mkey = str(row.get("metric", ""))
        if mkey == "overlap_rate":
            inner.append(_overlap_rate_metric_block(esc, row, fallback_metrics))
            continue
        label_line = esc(mkey)
        if mkey in _METRIC_TOOLTIPS:
            label_line += render_tooltip(_METRIC_TOOLTIPS[mkey])
        inner.append(
            '<div style="margin-bottom: 14px; padding: 14px 16px; background: #fff; '
            'border: 1px solid #e4e7ec; border-radius: 8px;">'
            f'<p style="margin: 0 0 4px 0; font-size: 0.72rem; text-transform: uppercase; '
            f'color: #868e96;">{label_line}</p>'
            f'<p style="margin: 0 0 8px 0; font-size: 1.2rem; font-weight: 700;">'
            f'{esc(str(row.get("value", "")))}</p>'
            f'<p style="margin: 0; font-size: 0.92rem; color: #343a40;">'
            f'<strong>{esc("Readout")}:</strong> {esc(str(row.get("implication", "")))}</p>'
            "</div>"
        )
    return "".join(inner) or f"<p>{esc('(No metrics rows.)')}</p>"


def _cluster_inventory_block(esc, primary_clusters: list) -> str:
    if not primary_clusters:
        return ""
    lis = "".join(
        f"<li style=\"margin-bottom: 8px;\">{esc(str(x))}</li>" for x in primary_clusters
    )
    return (
        '<div style="margin-top: 18px; padding: 14px 16px; background: #f8f9fa; '
        'border-radius: 8px; border: 1px solid #e9ecef;">'
        f'<p style="margin: 0 0 10px 0; font-weight: 700;">{esc("Clusters in this crawl")}</p>'
        f'<p style="margin: 0 0 10px 0; font-size: 0.88rem; color: #5c6370;">'
        f"{esc('URL groupings from this run.')}</p>"
        f'<ul style="margin: 0; padding-left: 1.2em;">{lis}</ul>'
        "</div>"
    )


def _core_block(esc, heading: str, body: str) -> str:
    if not (body or "").strip():
        return ""
    return (
        '<div style="margin-bottom: 16px; padding: 14px 16px; background: #ffffff; '
        'border-radius: 8px; border: 1px solid #e8eaed;">'
        f'<p style="margin: 0 0 8px 0; font-size: 0.72rem; text-transform: uppercase; '
        f'letter-spacing: 0.06em; color: #868e96;">{esc(heading)}</p>'
        f'<p style="margin: 0; font-size: 0.98rem;">{esc(body.strip())}</p>'
        "</div>"
    )


def generate_report(
    findings,
    grouped_issues,
    score,
    label,
    all_pages,
    clusters,
    ai_readiness,
    report_metrics: dict,
    ai_insights: dict,
    execution_roadmap: dict,
    *,
    site_structure: dict | None = None,
    single_site_mode: bool = False,
):
    high = sum(1 for f in findings if f.get("priority") == "HIGH")
    med = sum(1 for f in findings if f.get("priority") == "MEDIUM")
    low = sum(1 for f in findings if f.get("priority") == "LOW")

    dup_findings = [f for f in findings if f.get("type") != "topic_overlap"]
    overlap_findings = [f for f in findings if f.get("type") == "topic_overlap"]

    esc = escape
    score_color = _score_color(label)
    ai = ai_insights or {}
    rm = execution_roadmap or {}
    metrics = report_metrics or {}
    strategic_cluster_count = sum(
        1 for c in (clusters or []) if c.get("decision_type") in REMEDIATION_DECISION_TYPES
    )

    parts = [
        f"<div {_WRAPPER}>",
        '<h1 style="margin: 0 0 6px 0; font-size: 1.85rem; font-weight: 800;">'
        f'{esc("Sites audit")}</h1>',
        '<p style="margin: 0 0 20px 0; color: #5c6370; font-size: 0.95rem;">'
        f"{esc('What we found and what to do next.')}</p>",
    ]

    exec_brief = (ai.get("executive_summary_text") or "").strip()
    if exec_brief:
        parts.append(render_client_executive_brief_html(exec_brief))
    parts.append(render_insight_narrative_html(ai))

    # Verdict + framing (core_problem appears only in executive summary above)
    parts.append(f"<div {_SECTION}>")
    h_wrong = esc("What's going wrong")
    parts.append(
        f'<h2 style="margin: 0 0 16px 0; font-size: 1.2rem;">{h_wrong}</h2>'
    )
    verdict = ai.get("verdict") or "No verdict available."
    parts.append(
        '<div style="margin-bottom: 20px; padding: 22px 26px; background: #1a1d24; '
        'color: #f8f9fa; border-radius: 10px;">'
        f'<p style="margin: 0 0 8px 0; font-size: 0.7rem; text-transform: uppercase; '
        f'letter-spacing: 0.12em; color: #adb5bd;">{esc("Verdict")}</p>'
        f'<p style="margin: 0; font-size: 1.35rem; font-weight: 700; line-height: 1.35;">'
        f"{esc(verdict)}</p>"
        "</div>"
    )
    pt = (ai.get("problem_type") or "").strip()
    if pt:
        parts.append(
            f'<p style="margin: 0 0 16px 0; font-size: 0.9rem; color: #495057;">'
            f"<strong>{esc('Assessment:')}</strong> {esc(pt)}</p>"
        )
    parts.append(_decision_frame_block(esc, ai, metrics, strategic_cluster_count))
    parts.append(_core_block(esc, "If you wait", ai.get("inaction_risk", "")))
    parts.append(_cluster_inventory_block(esc, ai.get("primary_clusters") or []))
    parts.append("</div>")

    roadmap_h2 = (
        f'{esc("What to do next")}'
        f'{render_tooltip("Concrete steps. Verify in staging before release.")}'
    )
    parts.append(f"<div {_SECTION}>")
    parts.append(
        f'<h2 style="margin: 0 0 14px 0; font-size: 1.2rem;">{roadmap_h2}</h2>'
    )
    for item in rm.get("roadmap") or []:
        if not isinstance(item, dict):
            continue
        step = item.get("step", "")
        title = item.get("title", "")
        desc = item.get("description", "")
        at = item.get("action_type", "")
        outcome = item.get("expected_outcome") or item.get("expected_impact") or ""
        urls = item.get("target_urls") or item.get("affected_urls") or []
        evrefs = item.get("evidence_refs") or []
        at_label = str(at).strip().lower()
        hint = ACTION_TYPE_HINTS.get(at_label, "")
        parts.append(
            '<div style="border-left: 4px solid #198754; padding: 14px 16px; margin-bottom: 12px; '
            'background: #f6fff9; border-radius: 0 8px 8px 0;">'
            f'<p style="margin: 0 0 4px 0; font-weight: 700; font-size: 1.02rem;">'
            f"{_roadmap_step_heading(esc, step, title)}</p>"
        )
        if at_label and at_label != "none":
            parts.append(
                f'<p style="margin: 0 0 8px 0; font-size: 0.78rem; color: #6c757d; '
                f'text-transform: capitalize;">{esc(at_label)}</p>'
            )
        if hint:
            parts.append(
                f'<p style="margin: 0 0 10px 0; font-size: 0.82rem; color: #495057;">'
                f"{esc(hint)}</p>"
            )
        parts.append(
            f'<p style="margin: 0 0 10px 0; font-size: 0.95rem;">{esc(desc)}</p>'
            f'<p style="margin: 0 0 8px 0; font-size: 0.88rem; color: #495057;">'
            f"<strong>{esc('Expected outcome:')}</strong> {esc(outcome)}</p>"
        )
        if urls:
            parts.append(
                f'<p style="margin: 0 0 6px 0; font-size: 0.85rem;"><strong>{esc("Target URLs:")}</strong></p><ul>'
            )
            for u in urls[:16]:
                parts.append(f"<li>{esc(u)}</li>")
            parts.append("</ul>")
        page_changes = item.get("page_changes") or []
        if isinstance(page_changes, list) and page_changes:
            parts.append(
                f'<p style="margin: 12px 0 8px 0; font-size: 0.88rem; font-weight: 700;">'
                f'{esc("Page-level changes")}</p>'
            )
            for ch in page_changes:
                if not isinstance(ch, dict):
                    continue
                cu = ch.get("url", "")
                cty = ch.get("change_type", "")
                cinstr = ch.get("instruction", "")
                parts.append(
                    '<div style="margin: 0 0 10px 0; padding: 10px 12px; background: #fff; '
                    'border: 1px solid #dee2e6; border-radius: 6px;">'
                    f'<p style="margin: 0 0 6px 0; font-size: 0.85rem;"><strong>{esc("URL:")}</strong> '
                    f"{esc(str(cu))}</p>"
                    f'<p style="margin: 0 0 6px 0; font-size: 0.85rem;"><strong>{esc("change_type:")}</strong> '
                    f"{esc(str(cty))}</p>"
                    f'<p style="margin: 0; font-size: 0.88rem;"><strong>{esc("instruction:")}</strong> '
                    f"{esc(str(cinstr))}</p>"
                    "</div>"
                )
        if evrefs:
            parts.append(
                f'<p style="margin: 8px 0 0 0; font-size: 0.82rem; color: #495057;">'
                f"<strong>{esc('Evidence refs:')}</strong> "
                f"{esc(', '.join(str(x) for x in evrefs))}</p>"
            )
        parts.append("</div>")
    parts.append("</div>")

    # Proof (URLs + metrics only; no repeat of executive narrative)
    parts.append(f"<div {_SECTION}>")
    parts.append(
        f'<h2 style="margin: 0 0 14px 0; font-size: 1.2rem;">{esc("Proof")}</h2>'
    )
    parts.append(
        '<p style="margin: 0 0 14px 0; color: #5c6370; font-size: 0.92rem;">'
        f"{esc('Numbers and URLs that back the sections above.')}</p>"
    )
    for ev in ai.get("supporting_evidence") or []:
        if not isinstance(ev, dict):
            continue
        issue = ev.get("issue", "")
        urls = ev.get("urls") or []
        mrefs = ev.get("metric_refs") or []
        parts.append(
            '<div style="border: 1px solid #dee2e6; padding: 14px 16px; margin-bottom: 12px; '
            'background: #ffffff; border-radius: 8px;">'
            f'<p style="margin: 0 0 10px 0;">{esc(issue)}</p>'
        )
        if urls:
            parts.append(
                f'<p style="margin: 0 0 6px 0; font-size: 0.85rem;"><strong>{esc("URLs")}</strong></p>'
                '<ul style="margin: 0;">'
            )
            for u in urls:
                parts.append(f"<li>{esc(u)}</li>")
            parts.append("</ul>")
        if mrefs:
            parts.append(
                f'<p style="margin: 10px 0 0 0; font-size: 0.85rem; color: #495057;">'
                f"<strong>{esc('Referenced metrics')}</strong> "
                f"{esc(', '.join(str(x) for x in mrefs))}</p>"
            )
        parts.append("</div>")
    parts.append("</div>")

    # Severity: interpreted metrics + overall score
    parts.append(f"<div {_SECTION}>")
    parts.append(
        f'<h2 style="margin: 0 0 14px 0; font-size: 1.2rem;">'
        f'{esc("How bad this is")}</h2>'
    )
    parts.append(
        _metrics_explained_table(
            esc, ai.get("metrics_explained") or [], metrics
        )
    )
    parts.append(
        f'<h3 style="margin: 22px 0 12px 0; font-size: 1.05rem;">'
        f'{esc("Content health score")}</h3>'
    )
    parts.append(f"<div {_SCORE_BOX}>")
    parts.append(
        f'<p style="font-size: 28px; font-weight: 700; color: {score_color}; '
        f'margin: 0 0 6px 0;">'
        f"{esc(str(score))} <span style=\"font-weight: 500; color: #6c757d;\">/ 100</span></p>"
    )
    parts.append(
        f'<p style="margin: 0 0 12px 0; font-weight: 600;">{esc(label)}</p>'
    )
    parts.append(
        f'<p style="margin: 0 0 14px 0; font-size: 0.95rem; color: #343a40;">'
        f"<strong>{esc('Score impact:')}</strong> "
        f"{esc('This issue is the primary driver behind the Content Quality score of')} "
        f"{esc(str(score))}{esc('.')}</p>"
    )
    parts.append(f"<p style=\"margin: 0; font-size: 0.9em;\"><strong>{esc('Grouped themes:')}</strong></p><ul>")
    if grouped_issues:
        for g in grouped_issues[:4]:
            parts.append(f"<li>{esc(g.get('title', ''))}</li>")
    else:
        parts.append(f"<li>{esc('None detected in this run')}</li>")
    parts.append("</ul></div></div>")

    parts.append(render_technical_seo_fixes(esc, clusters))

    # Summary
    parts.append(f"<div {_SECTION}>")
    parts.append(
        f'<h2 style="margin: 0 0 12px 0; font-size: 1.1rem;">{esc("Summary")}</h2>'
    )
    parts.append("<ul style=\"margin: 0;\">")
    parts.append(f"<li>{esc('Pages analyzed:')} {len(all_pages)}</li>")
    parts.append(f"<li>{esc('Clusters found:')} {len(clusters)}</li>")
    parts.append(f"<li>{esc('High priority findings:')} {high}</li>")
    parts.append(f"<li>{esc('Medium priority findings:')} {med}</li>")
    parts.append(f"<li>{esc('Low priority findings:')} {low}</li>")
    if single_site_mode and site_structure:
        dist = (site_structure.get("intent_distribution") or {}) if isinstance(site_structure, dict) else {}
        parts.append(
            f"<li>{esc('Funnel stages (page counts):')} "
            f"{esc(str(dist.get('awareness', 0)))} {esc('awareness')}, "
            f"{esc(str(dist.get('consideration', 0)))} {esc('consideration')}, "
            f"{esc(str(dist.get('decision', 0)))} {esc('decision')}"
            f"</li>"
        )
    parts.append("</ul></div>")

    # AI readiness
    parts.append(f"<div {_SECTION}>")
    parts.append(
        f'<h2 style="margin: 0 0 12px 0; font-size: 1.1rem;">'
        f'{esc("AI readiness signals")}</h2>'
    )
    parts.append("<ul style=\"margin: 0;\">")
    parts.append(
        f"<li>{esc('Guide content present:')} "
        f"{'YES' if ai_readiness['has_guide_content'] else 'NO'}</li>"
    )
    parts.append(
        f"<li>{esc('FAQ content present:')} "
        f"{'YES' if ai_readiness['has_faq_content'] else 'NO'}</li>"
    )
    parts.append(
        f"<li>{esc('Average content depth:')} "
        f"{'GOOD' if ai_readiness['content_depth_ok'] else 'LOW'}</li>"
    )
    parts.append(
        f"<li>{esc('Average words per page:')} "
        f"{ai_readiness['average_word_count']:.0f}</li>"
    )
    parts.append("</ul></div>")

    # Detailed: cluster findings
    parts.append(f"<div {_SECTION}>")
    parts.append(
        f'<h2 style="margin: 0 0 14px 0; font-size: 1.2rem;">'
        f'{esc("Detailed findings — cluster duplication")}</h2>'
    )
    if not dup_findings:
        parts.append(f"<p>{esc('(No cluster duplication findings.)')}</p>")
    for f in dup_findings:
        ctype = f.get("type") or "unknown"
        dup_t = f.get("duplication_type") or "—"
        cm = f.get("cross_market")
        market = "Cross-market" if cm else "Single-market"
        pri = f.get("priority", "MEDIUM")
        sim = f.get("avg_similarity", 0)
        action = f.get("action", "")
        parts.append(f"<div {_FINDING_CARD}>")
        parts.append(
            f"<p><strong>{esc(str(ctype))}</strong> · "
            f"<span style=\"color:#495057;\">{esc(dup_t)}</span> "
            f"({esc(market)}) <span>[{esc(pri)}]</span></p>"
        )
        cs = f.get("classification_summary") or {}
        dc = f.get("duplication_class")
        if cs or dc:
            assess = _duplication_assessment_label(dc)
            parts.append(
                '<div class="cluster-meta" style="display: flex; flex-wrap: wrap; gap: 10px; '
                'font-size: 0.86rem; color: #495057; margin: 0 0 10px 0;">'
                f'<span><strong>{esc("Type")}:</strong> {esc(str(cs.get("dominant_type", "—")))}</span>'
                f'<span><strong>{esc("Intent")}:</strong> {esc(str(cs.get("dominant_intent", "—")))}</span>'
                f'<span><strong>{esc("Stage")}:</strong> {esc(str(cs.get("dominant_stage", "—")))}</span>'
                f'<span><strong>{esc("Assessment")}:</strong> {esc(assess)}</span>'
                "</div>"
            )
        parts.append(f"<p>{esc('Action:')} {esc(action)}</p>")
        parts.append(f"<p>{esc('Similarity:')} {esc(str(sim))}</p>")
        dom = f.get("dominant_url")
        comp = f.get("competing_urls") or []
        if dom:
            parts.append(
                f'<p style="font-size: 0.9rem;"><strong>{esc("Canonical URL: ")}</strong> {esc(dom)}</p>'
            )
        if comp:
            parts.append(
                f'<p style="font-size: 0.9rem;"><strong>{esc("Competing URLs: ")}</strong> '
                f'{esc(", ".join(comp[:8]))}</p>'
            )
        parts.append("<ul>")
        for p in f["pages"]:
            parts.append(f"<li>{esc(p)}</li>")
        parts.append("</ul></div>")
    parts.append("</div>")

    # Topic overlap
    parts.append(f"<div {_SECTION}>")
    parts.append(
        f'<h2 style="margin: 0 0 14px 0; font-size: 1.2rem;">'
        f'{esc("Detailed findings — topic overlap")}</h2>'
    )
    if not overlap_findings:
        parts.append(
            f"<p>{esc('(No cross-cluster topic overlaps above threshold.)')}</p>"
        )
    else:
        for f in overlap_findings:
            dup_t = f.get("duplication_type") or "—"
            cm = f.get("cross_market")
            market = "Cross-market" if cm else "Single-market"
            pri = f.get("priority", "MEDIUM")
            sim = f.get("similarity", 0)
            action = f.get("action", "")
            impact = f.get("impact", "")
            parts.append(f"<div {_FINDING_CARD}>")
            parts.append(
                f"<p><strong>{esc('Topic overlap')}</strong> · "
                f"<span style=\"color:#495057;\">{esc(dup_t)}</span> "
                f"({esc(market)}) <span>[{esc(pri)}]</span></p>"
            )
            parts.append(f"<p>{esc('Action:')} {esc(action)}</p>")
            if impact:
                parts.append(f"<p>{esc('Impact:')} {esc(impact)}</p>")
            parts.append(f"<p>{esc('Similarity:')} {esc(f'{sim:.3f}')}</p>")
            dom = f.get("dominant_url")
            comp = f.get("competing_urls") or []
            if dom:
                parts.append(
                    f'<p style="font-size: 0.9rem;"><strong>{esc("Canonical URL: ")}</strong> {esc(dom)}</p>'
                )
            if comp:
                parts.append(
                    f'<p style="font-size: 0.9rem;"><strong>{esc("Competing URLs: ")}</strong> '
                    f'{esc(", ".join(comp))}</p>'
                )
            parts.append("<ul>")
            for p in f["pages"]:
                parts.append(f"<li>{esc(p)}</li>")
            parts.append("</ul></div>")
    parts.append("</div>")

    parts.append("</div>")
    return "".join(parts)
