from html import escape


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
        '<div style="font-family: system-ui, -apple-system, sans-serif; '
        'max-width: 900px; line-height: 1.5; color: #222;">',
        f"<h1>{esc('Site Audit Report')}</h1>",
    ]

    # Executive insights
    bullets = _executive_insights_bullets(findings)
    parts.append('<div style="margin-bottom: 24px;">')
    parts.append(f"<h2>{esc('Executive insights')}</h2>")
    parts.append("<ul>")
    for b in bullets:
        parts.append(f"<li>{esc(b)}</li>")
    parts.append("</ul></div>")

    # Content health score
    parts.append('<div style="margin-bottom: 24px;">')
    parts.append(f"<h2>{esc('Content Health Score')}</h2>")
    parts.append(
        f'<p style="font-size: 24px; font-weight: bold; color: {score_color}; '
        f'margin: 8px 0 16px 0;">'
        f"{esc(str(score))} / 100 — {esc(label)}</p>"
    )
    parts.append(f"<p><strong>{esc('Primary issues:')}</strong></p>")
    parts.append("<ul>")
    if grouped_issues:
        for g in grouped_issues[:3]:
            parts.append(
                f"<li>{esc(_primary_issue_display(g.get('title', '')))}</li>"
            )
    else:
        parts.append(
            f"<li>{esc('No grouped overlap patterns detected in this run')}</li>"
        )
    parts.append("</ul></div>")

    # Key issues
    parts.append('<div style="margin-bottom: 24px;">')
    parts.append(f"<h2>{esc('Key issues')}</h2>")
    if not grouped_issues:
        parts.append(f"<p>{esc('(No grouped topic-overlap issues.)')}</p>")
    else:
        for g in grouped_issues:
            parts.append(
                '<div style="border: 1px solid #e0e0e0; border-radius: 8px; '
                'padding: 12px 16px; margin-bottom: 12px; background: #fafafa;">'
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
    parts.append('<div style="margin-bottom: 24px;">')
    parts.append(f"<h2>{esc('Top recommended actions')}</h2>")
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
    parts.append('<div style="margin-bottom: 24px;">')
    parts.append(f"<h2>{esc('Summary')}</h2>")
    parts.append("<ul>")
    parts.append(f"<li>{esc('Pages analyzed:')} {len(all_pages)}</li>")
    parts.append(f"<li>{esc('Clusters found:')} {len(clusters)}</li>")
    parts.append(f"<li>{esc('High priority issues:')} {high}</li>")
    parts.append(f"<li>{esc('Medium priority issues:')} {med}</li>")
    parts.append(f"<li>{esc('Low priority issues:')} {low}</li>")
    parts.append("</ul></div>")

    # AI readiness
    parts.append('<div style="margin-bottom: 24px;">')
    parts.append(f"<h2>{esc('AI readiness signals')}</h2>")
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
    parts.append('<div style="margin-bottom: 24px;">')
    parts.append(f"<h2>{esc('Findings')}</h2>")
    if not dup_findings:
        parts.append(f"<p>{esc('(No cluster duplication findings.)')}</p>")
    for f in dup_findings:
        lt = (f.get("type") or "unknown").upper()
        cm = f.get("cross_market")
        market = "Cross-market" if cm else "Single-market"
        pri = f.get("priority", "MEDIUM")
        sim = f.get("avg_similarity", 0)
        action = f.get("action", "")
        parts.append(
            '<div style="border-left: 4px solid #337ab7; padding-left: 12px; '
            'margin-bottom: 16px;">'
        )
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
    parts.append('<div style="margin-bottom: 24px;">')
    parts.append(f"<h2>{esc('Topic overlap (high value findings)')}</h2>")
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
            parts.append(
                '<div style="border-left: 4px solid #c9302c; padding-left: 12px; '
                'margin-bottom: 16px;">'
            )
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
