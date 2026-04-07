def generate_report(findings, all_pages, clusters, ai_readiness):
    high = sum(1 for f in findings if f.get("priority") == "HIGH")
    med = sum(1 for f in findings if f.get("priority") == "MEDIUM")
    low = sum(1 for f in findings if f.get("priority") == "LOW")

    dup_findings = [f for f in findings if f.get("type") != "topic_overlap"]
    overlap_findings = [f for f in findings if f.get("type") == "topic_overlap"]

    lines = [
        "SITE AUDIT REPORT",
        "",
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
            lines.append(f"  Similarity: {sim:.3f}")
            for p in f["pages"]:
                lines.append(f"  - {p}")
            lines.append("")

    return "\n".join(lines)
