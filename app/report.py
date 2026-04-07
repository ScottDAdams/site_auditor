from html import escape

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
    "differentiate": "Clarify positioning between pages",
    "reposition": "Adjust intent targeting",
    "none": "No structural content change in this step",
}


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
    return (
        f"<div {_SECTION}>"
        f'<h2 style="margin: 0 0 12px 0; font-size: 1.2rem;">'
        f'{esc("Technical SEO fixes")}</h2>'
        f'<p style="margin: 0 0 14px 0; color: #5c6370; font-size: 0.92rem;">'
        f"{esc('Canonical duplicates, trailing-slash or hostname variants, and homepage aliases—not content strategy items.')}</p>"
        f"{body}"
        "</div>"
    )


def render_methodology() -> str:
    esc = escape
    items = [
        (
            "Exact duplication",
            "Identical or near-identical content across URLs (high embedding similarity).",
        ),
        (
            "Intent overlap",
            "Different pages competing for the same user goal or search intent.",
        ),
        (
            "Structural duplication",
            "Same page pattern or section with minimal substantive differentiation.",
        ),
        (
            "Cross-market reuse",
            "Content reused across regions without sufficient localization.",
        ),
        (
            "Navigational redundancy",
            "Parallel or competing entry points (e.g. mirrored structural paths).",
        ),
    ]
    rows = "".join(
        f"<li style=\"margin-bottom: 10px;\"><strong>{esc(t)}</strong> — {esc(d)}</li>"
        for t, d in items
    )
    return (
        f"<div {_SECTION}>"
        f'<h2 style="margin: 0 0 12px 0; font-size: 1.15rem;">'
        f'{esc("How to read this report")}</h2>'
        f'<p style="margin: 0 0 12px 0; color: #5c6370;">'
        f"{esc('Duplication types used in this audit:')}</p>"
        f'<ul style="margin: 0; padding-left: 1.2em;">{rows}</ul>'
        f"</div>"
    )


def _score_color(label: str) -> str:
    return {
        "Strong": "#5cb85c",
        "Good": "#5bc0de",
        "Moderate Risk": "#f0ad4e",
        "High Risk": "#d9534f",
    }.get(label, "#d9534f")


def _metrics_explained_table(esc, rows: list, fallback_metrics: dict) -> str:
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
                "implication": "Mean embedding similarity inside duplicate clusters.",
            },
            {
                "metric": "content_uniqueness_score",
                "value": str(fallback_metrics.get("content_uniqueness_score", "")),
                "implication": "Higher means more distinct copy between competing URLs.",
            },
        ]
    inner = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        inner.append(
            '<div style="margin-bottom: 14px; padding: 14px 16px; background: #fff; '
            'border: 1px solid #e4e7ec; border-radius: 8px;">'
            f'<p style="margin: 0 0 4px 0; font-size: 0.72rem; text-transform: uppercase; '
            f'color: #868e96;">{esc(str(row.get("metric", "")))}</p>'
            f'<p style="margin: 0 0 8px 0; font-size: 1.2rem; font-weight: 700;">'
            f'{esc(str(row.get("value", "")))}</p>'
            f'<p style="margin: 0; font-size: 0.92rem; color: #343a40;">'
            f'<strong>{esc("Why it matters")}:</strong> {esc(str(row.get("implication", "")))}</p>'
            "</div>"
        )
    return "".join(inner) or f"<p>{esc('(No metrics rows.)')}</p>"


def _primary_drivers_block(esc, primary_clusters: list) -> str:
    if not primary_clusters:
        return ""
    lis = "".join(
        f"<li style=\"margin-bottom: 8px;\">{esc(str(x))}</li>" for x in primary_clusters
    )
    return (
        '<div style="margin-top: 18px; padding: 14px 16px; background: #f8f9fa; '
        'border-radius: 8px; border: 1px solid #e9ecef;">'
        f'<p style="margin: 0 0 10px 0; font-weight: 700;">{esc("Primary drivers of this issue")}</p>'
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

    parts = [
        f"<div {_WRAPPER}>",
        '<h1 style="margin: 0 0 6px 0; font-size: 1.85rem; font-weight: 800;">'
        f'{esc("Site audit")}</h1>',
        '<p style="margin: 0 0 20px 0; color: #5c6370; font-size: 0.95rem;">'
        f"{esc('POV backed by URLs and metrics — execution sequenced below.')}</p>",
    ]

    parts.append(render_methodology())
    parts.append(render_technical_seo_fixes(esc, clusters))

    # Verdict
    verdict = ai.get("verdict") or "No verdict available."
    parts.append(
        '<div style="margin-bottom: 28px; padding: 22px 26px; background: #1a1d24; '
        'color: #f8f9fa; border-radius: 10px;">'
        f'<p style="margin: 0 0 8px 0; font-size: 0.7rem; text-transform: uppercase; '
        f'letter-spacing: 0.12em; color: #adb5bd;">{esc("Verdict")}</p>'
        f'<p style="margin: 0; font-size: 1.35rem; font-weight: 700; line-height: 1.35;">'
        f"{esc(verdict)}</p>"
        "</div>"
    )

    # Key metrics (interpreted)
    parts.append(f"<div {_SECTION}>")
    parts.append(
        f'<h2 style="margin: 0 0 14px 0; font-size: 1.2rem;">{esc("Key metrics")}</h2>'
    )
    parts.append(
        _metrics_explained_table(
            esc, ai.get("metrics_explained") or [], metrics
        )
    )
    parts.append("</div>")

    # Core analysis
    parts.append(f"<div {_SECTION}>")
    parts.append(
        f'<h2 style="margin: 0 0 16px 0; font-size: 1.2rem;">{esc("Core analysis")}</h2>'
    )
    parts.append(_core_block(esc, "Core problem", ai.get("core_problem", "")))
    parts.append(_core_block(esc, "Recommendation", ai.get("recommendation", "")))
    parts.append(_core_block(esc, "Business impact", ai.get("business_impact", "")))
    parts.append(_core_block(esc, "If no action is taken", ai.get("inaction_risk", "")))
    parts.append(_primary_drivers_block(esc, ai.get("primary_clusters") or []))
    parts.append("</div>")

    # 30-day roadmap
    parts.append(f"<div {_SECTION}>")
    parts.append(
        f'<h2 style="margin: 0 0 14px 0; font-size: 1.2rem;">'
        f'{esc("30-day execution plan")}</h2>'
    )
    parts.append(
        '<p style="margin: 0 0 16px 0; color: #5c6370; font-size: 0.92rem;">'
        f"{esc('Ordered by impact — concrete steps only.')}</p>"
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
        badge = (
            f'<span style="display: inline-block; padding: 2px 8px; border-radius: 4px; '
            f'background: #198754; color: #fff; font-size: 0.75rem; font-weight: 600; '
            f'margin-right: 8px;">{esc(str(at).upper())}</span>'
        )
        hint = ACTION_TYPE_HINTS.get(str(at).lower().strip(), "")
        parts.append(
            '<div style="border-left: 4px solid #198754; padding: 14px 16px; margin-bottom: 12px; '
            'background: #f6fff9; border-radius: 0 8px 8px 0;">'
            f'<p style="margin: 0 0 8px 0;">{badge}'
            f'<span style="font-weight: 700;">{esc(str(step))}. {esc(title)}</span></p>'
        )
        if hint:
            parts.append(
                f'<p style="margin: -4px 0 10px 4px; font-size: 0.82rem; color: #495057;">'
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

    # Supporting evidence
    parts.append(f"<div {_SECTION}>")
    parts.append(
        f'<h2 style="margin: 0 0 14px 0; font-size: 1.2rem;">'
        f'{esc("Supporting evidence")}</h2>'
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

    # Content health score
    parts.append(f"<div {_SECTION}>")
    parts.append(
        f'<h2 style="margin: 0 0 14px 0; font-size: 1.2rem;">'
        f'{esc("Content health score")}</h2>'
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
    parts.append(f"<p style=\"margin: 0; font-size: 0.9em;\"><strong>{esc('Grouped themes:')}</strong></p><ul>")
    if grouped_issues:
        for g in grouped_issues[:4]:
            parts.append(f"<li>{esc(g.get('title', ''))}</li>")
    else:
        parts.append(f"<li>{esc('None detected in this run')}</li>")
    parts.append("</ul></div></div>")

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
