from html import escape

_WRAPPER = (
    'style="font-family: system-ui, -apple-system, Segoe UI, sans-serif; '
    "max-width: 920px; line-height: 1.55; color: #1a1a1a; padding: 28px 32px; "
    'background: #f5f6f8; border-radius: 12px;"'
)
_SECTION = (
    'style="margin-bottom: 36px; padding: 22px 26px; border-radius: 10px; '
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


def _primary_issue_display(title: str) -> str:
    mapping = {
        "Product Positioning Overlap": "Product positioning overlap",
        "Cross-Market Content Duplication": "Cross-market duplication",
        "Informational Content Overlap": "Overlapping informational content",
        "General Content Overlap": "Structural inefficiencies",
    }
    return mapping.get(title, title)


def _executive_insights_bullets(findings):
    bullets = []
    high_n = sum(1 for f in findings if f.get("priority") == "HIGH")
    med_n = sum(1 for f in findings if f.get("priority") == "MEDIUM")
    overlap = [f for f in findings if f.get("type") == "topic_overlap"]
    dup_findings = [f for f in findings if f.get("type") != "topic_overlap"]
    any_cross = any(f.get("cross_market") for f in findings)

    product_conflict_high = any(
        f.get("priority") == "HIGH"
        and "product" in (f.get("overlap_types") or [])
        for f in overlap
    )
    product_positioning_theme = any(
        "product positioning" in (f.get("impact") or "").lower() for f in overlap
    )
    cluster_product_high = any(
        f.get("type") == "product" and f.get("priority") == "HIGH"
        for f in dup_findings
    )
    product_executive = (
        product_conflict_high
        or product_positioning_theme
        or cluster_product_high
    )

    if product_executive:
        bullets.append(
            "Product positioning overlap detected, which may impact conversion "
            "and customer clarity"
        )

    if high_n > 0 and not product_executive:
        if any("SEO authority" in f.get("impact", "") for f in overlap):
            bullets.append(
                f"{high_n} high-priority content conflicts impacting SEO "
                "authority and AI visibility"
            )
        else:
            bullets.append(
                f"{high_n} high-priority content conflicts impacting site "
                "clarity and strategic positioning"
            )

    if any_cross:
        bullets.append(
            "Cross-market duplication reduces localization effectiveness "
            "between AU and NZ"
        )

    if high_n == 0 and (med_n > 0 or len(findings) > 0):
        bullets.append(
            "Content patterns suggest opportunities to sharpen differentiation "
            "across key pages"
        )

    if not bullets:
        bullets.append(
            "No major conflicts flagged; continue monitoring content drift over time"
        )

    return bullets


def _score_color(label: str) -> str:
    return {
        "Strong": "#5cb85c",
        "Good": "#5bc0de",
        "Moderate Risk": "#f0ad4e",
        "High Risk": "#d9534f",
    }.get(label, "#d9534f")


def generate_report(
    findings,
    grouped_issues,
    top_actions,
    score,
    label,
    all_pages,
    clusters,
    ai_readiness,
):
    high = sum(1 for f in findings if f.get("priority") == "HIGH")
    med = sum(1 for f in findings if f.get("priority") == "MEDIUM")
    low = sum(1 for f in findings if f.get("priority") == "LOW")

    dup_findings = [f for f in findings if f.get("type") != "topic_overlap"]
    overlap_findings = [f for f in findings if f.get("type") == "topic_overlap"]

    esc = escape
    score_color = _score_color(label)

    parts = [
        f"<div {_WRAPPER}>",
        f'<h1 style="margin: 0 0 8px 0; font-size: 1.75rem;">{esc("Site Audit Report")}</h1>',
        f'<p style="margin: 0 0 24px 0; color: #5c6370; font-size: 0.95rem;">'
        f"{esc('Structured analysis — grouped issues, not raw duplicate counts.')}</p>",
    ]

    # Executive insights
    bullets = _executive_insights_bullets(findings)
    parts.append(f"<div {_SECTION}>")
    parts.append(
        f'<h2 style="margin: 0 0 14px 0; font-size: 1.25rem;">'
        f'{esc("Executive insights")}</h2>'
    )
    parts.append("<ul style=\"margin: 0; padding-left: 1.25em;\">")
    for b in bullets:
        parts.append(f"<li style=\"margin-bottom: 8px;\">{esc(b)}</li>")
    parts.append("</ul></div>")

    # Content health score
    parts.append(f"<div {_SECTION}>")
    parts.append(
        f'<h2 style="margin: 0 0 14px 0; font-size: 1.25rem;">'
        f'{esc("Content Health Score")}</h2>'
    )
    parts.append(f"<div {_SCORE_BOX}>")
    parts.append(
        f'<p style="font-size: 32px; font-weight: 700; color: {score_color}; '
        f'margin: 0 0 6px 0; letter-spacing: -0.02em;">'
        f"{esc(str(score))} <span style=\"font-weight: 500; color: #6c757d;\">/ 100</span></p>"
    )
    parts.append(
        f'<p style="margin: 0 0 16px 0; font-size: 1.1rem; font-weight: 600; '
        f'color: #333;">{esc(label)}</p>'
    )
    parts.append(f"<p style=\"margin: 0 0 8px 0;\"><strong>{esc('Primary issues:')}</strong></p>")
    parts.append("<ul style=\"margin: 0; padding-left: 1.25em;\">")
    if grouped_issues:
        for g in grouped_issues[:3]:
            parts.append(
                f"<li>{esc(_primary_issue_display(g.get('title', '')))}</li>"
            )
    else:
        parts.append(
            f"<li>{esc('No grouped overlap patterns detected in this run')}</li>"
        )
    parts.append("</ul></div></div>")

    # Key issues
    parts.append(f"<div {_SECTION}>")
    parts.append(
        f'<h2 style="margin: 0 0 14px 0; font-size: 1.25rem;">'
        f'{esc("Key issues")}</h2>'
    )
    if not grouped_issues:
        parts.append(f"<p>{esc('(No grouped topic-overlap issues.)')}</p>")
    else:
        for g in grouped_issues:
            parts.append(
                '<div style="border: 1px solid #e8eaed; border-radius: 8px; '
                'border-left: 4px solid #5bc0de; padding: 14px 16px; margin-bottom: 14px; '
                'background: #ffffff;">'
            )
            parts.append(
                f"<p><strong>{esc(g['title'])}</strong> "
                f"<span style=\"color:#666;\">[{esc(g['priority'])}]</span></p>"
            )
            parts.append(f"<p>{esc(g['summary'])}</p>")
            parts.append(
                f"<p style=\"font-size: 0.9em;\">"
                f"{esc('Instances found:')} {g['count']}</p>"
            )
            parts.append(f"<p><strong>{esc('Example:')}</strong></p><ul>")
            examples = g.get("examples") or []
            if examples:
                for url in examples[0].get("pages", []):
                    parts.append(f"<li>{esc(url)}</li>")
            parts.append("</ul></div>")
    parts.append("</div>")

    # Top recommended actions
    parts.append(f"<div {_SECTION}>")
    parts.append(
        f'<h2 style="margin: 0 0 14px 0; font-size: 1.25rem;">'
        f'{esc("Top recommended actions")}</h2>'
    )
    if not top_actions:
        parts.append(
            f"<p>{esc('(No top actions generated from grouped issues.)')}</p>"
        )
    else:
        parts.append("<ol>")
        for action in top_actions:
            parts.append(f"<li><strong>{esc(action['title'])}</strong>")
            parts.append("<ul>")
            for d in action.get("details", []):
                parts.append(f"<li>{esc(d)}</li>")
            parts.append("</ul></li>")
        parts.append("</ol>")
    parts.append("</div>")

    # Summary
    parts.append(f"<div {_SECTION}>")
    parts.append(
        f'<h2 style="margin: 0 0 14px 0; font-size: 1.25rem;">'
        f'{esc("Summary")}</h2>'
    )
    parts.append("<ul>")
    parts.append(f"<li>{esc('Pages analyzed:')} {len(all_pages)}</li>")
    parts.append(f"<li>{esc('Clusters found:')} {len(clusters)}</li>")
    parts.append(f"<li>{esc('High priority issues:')} {high}</li>")
    parts.append(f"<li>{esc('Medium priority issues:')} {med}</li>")
    parts.append(f"<li>{esc('Low priority issues:')} {low}</li>")
    parts.append("</ul></div>")

    # AI readiness
    parts.append(f"<div {_SECTION}>")
    parts.append(
        f'<h2 style="margin: 0 0 14px 0; font-size: 1.25rem;">'
        f'{esc("AI readiness signals")}</h2>'
    )
    parts.append("<ul>")
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

    # Findings (duplication clusters)
    parts.append(f"<div {_SECTION}>")
    parts.append(
        f'<h2 style="margin: 0 0 14px 0; font-size: 1.25rem;">'
        f'{esc("Findings")}</h2>'
    )
    if not dup_findings:
        parts.append(f"<p>{esc('(No cluster duplication findings.)')}</p>")
    for f in dup_findings:
        lt = (f.get("type") or "unknown").upper()
        cm = f.get("cross_market")
        market = "Cross-market" if cm else "Single-market"
        pri = f.get("priority", "MEDIUM")
        sim = f.get("avg_similarity", 0)
        action = f.get("action", "")
        parts.append(f"<div {_FINDING_CARD}>")
        parts.append(
            f"<p><strong>{esc(lt)} {esc('duplication')}</strong> "
            f"({esc(market)}) <span>[{esc(pri)}]</span></p>"
        )
        parts.append(f"<p>{esc('Action:')} {esc(action)}</p>")
        parts.append(f"<p>{esc('Similarity:')} {esc(str(sim))}</p>")
        parts.append("<ul>")
        for p in f["pages"]:
            parts.append(f"<li>{esc(p)}</li>")
        parts.append("</ul></div>")
    parts.append("</div>")

    # Topic overlap
    parts.append(f"<div {_SECTION}>")
    parts.append(
        f'<h2 style="margin: 0 0 14px 0; font-size: 1.25rem;">'
        f'{esc("Topic overlap (high value findings)")}</h2>'
    )
    if not overlap_findings:
        parts.append(
            f"<p>{esc('(No cross-cluster topic overlaps above threshold.)')}</p>"
        )
    else:
        for f in overlap_findings:
            cm = f.get("cross_market")
            market = "Cross-market" if cm else "Single-market"
            pri = f.get("priority", "MEDIUM")
            sim = f.get("similarity", 0)
            action = f.get("action", "")
            impact = f.get("impact", "")
            parts.append(f"<div {_FINDING_CARD}>")
            parts.append(
                f"<p><strong>{esc('Potential topic overlap')}</strong> "
                f"({esc(market)}) <span>[{esc(pri)}]</span></p>"
            )
            parts.append(f"<p>{esc('Action:')} {esc(action)}</p>")
            if impact:
                parts.append(f"<p>{esc('Impact:')} {esc(impact)}</p>")
            parts.append(f"<p>{esc('Similarity:')} {esc(f'{sim:.3f}')}</p>")
            parts.append("<ul>")
            for p in f["pages"]:
                parts.append(f"<li>{esc(p)}</li>")
            parts.append("</ul></div>")
    parts.append("</div>")

    parts.append("</div>")
    return "".join(parts)
