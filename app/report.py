def _executive_insights_lines(findings):
    lines = ["EXECUTIVE INSIGHTS", ""]
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
        f.get("type") == "product" and f.get("priority") == "HIGH" for f in dup_findings
    )
    product_executive = (
        product_conflict_high
        or product_positioning_theme
        or cluster_product_high
    )

    if product_executive:
        lines.append(
            "- Product positioning overlap detected, which may impact conversion "
            "and customer clarity"
        )

    if high_n > 0 and not product_executive:
        if any("SEO authority" in f.get("impact", "") for f in overlap):
            lines.append(
                f"- {high_n} high-priority content conflicts impacting SEO "
                "authority and AI visibility"
            )
        else:
            lines.append(
                f"- {high_n} high-priority content conflicts impacting site "
                "clarity and strategic positioning"
            )

    if any_cross:
        lines.append(
            "- Cross-market duplication reduces localization effectiveness "
            "between AU and NZ"
        )

    if high_n == 0 and (med_n > 0 or len(findings) > 0):
        lines.append(
            "- Content patterns suggest opportunities to sharpen differentiation "
            "across key pages"
        )

    if len(lines) == 2:
        lines.append(
            "- No major conflicts flagged; continue monitoring content drift over time"
        )

    lines.append("")
    return lines


def _key_issues_lines(grouped_issues):
    lines = ["KEY ISSUES", ""]
    if not grouped_issues:
        lines.append("(No grouped topic-overlap issues.)")
        lines.append("")
        return lines

    for g in grouped_issues:
        lines.append(f"- {g['title']} [{g['priority']}]")
        lines.append(f"  {g['summary']}")
        lines.append(f"  Instances found: {g['count']}")
        lines.append("  Example:")
        examples = g.get("examples") or []
        if examples:
            for url in examples[0].get("pages", []):
                lines.append(f"    - {url}")
        lines.append("")

    return lines


def generate_report(findings, grouped_issues, all_pages, clusters, ai_readiness):
    high = sum(1 for f in findings if f.get("priority") == "HIGH")
    med = sum(1 for f in findings if f.get("priority") == "MEDIUM")
    low = sum(1 for f in findings if f.get("priority") == "LOW")

    dup_findings = [f for f in findings if f.get("type") != "topic_overlap"]
    overlap_findings = [f for f in findings if f.get("type") == "topic_overlap"]

    lines = [
        "SITE AUDIT REPORT",
        "",
    ]
    lines.extend(_executive_insights_lines(findings))
    lines.extend(_key_issues_lines(grouped_issues))
    lines.extend(
        [
        "SUMMARY",
        "",
        f"Pages analyzed: {len(all_pages)}",
        f"Clusters found: {len(clusters)}",
        "",
        f"High priority issues: {high}",
        f"Medium priority issues: {med}",
        f"Low priority issues: {low}",
        "",
        "AI READINESS SIGNALS",
        "",
        f"Guide content present: {'YES' if ai_readiness['has_guide_content'] else 'NO'}",
        f"FAQ content present: {'YES' if ai_readiness['has_faq_content'] else 'NO'}",
        f"Average content depth: {'GOOD' if ai_readiness['content_depth_ok'] else 'LOW'}",
        f"Average words per page: {ai_readiness['average_word_count']:.0f}",
        "",
        "FINDINGS",
        "",
        ]
    )

    for f in dup_findings:
        label = (f.get("type") or "unknown").upper()
        cm = f.get("cross_market")
        market = "Cross-market" if cm else "Single-market"
        pri = f.get("priority", "MEDIUM")
        sim = f.get("avg_similarity", 0)
        action = f.get("action", "")

        lines.append(f"- {label} duplication ({market}) [{pri}]")
        lines.append(f"  Action: {action}")
        lines.append(f"  Similarity: {sim}")
        for p in f["pages"]:
            lines.append(f"  - {p}")
        lines.append("")

    lines.extend(
        [
            "TOPIC OVERLAP (HIGH VALUE FINDINGS)",
            "",
        ]
    )

    if not overlap_findings:
        lines.append("(No cross-cluster topic overlaps above threshold.)")
        lines.append("")
    else:
        for f in overlap_findings:
            cm = f.get("cross_market")
            market = "Cross-market" if cm else "Single-market"
            pri = f.get("priority", "MEDIUM")
            sim = f.get("similarity", 0)
            action = f.get("action", "")

            lines.append(f"- Potential topic overlap ({market}) [{pri}]")
            lines.append(f"  Action: {action}")
            impact = f.get("impact", "")
            if impact:
                lines.append(f"  Impact: {impact}")
            lines.append(f"  Similarity: {sim:.3f}")
            for p in f["pages"]:
                lines.append(f"  - {p}")
            lines.append("")

    return "\n".join(lines)
