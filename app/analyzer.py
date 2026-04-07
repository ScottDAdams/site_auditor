def analyze_clusters(clusters):
    findings = []

    for c in clusters:
        findings.append({
            "type": "duplication",
            "severity": "high",
            "description": f"{len(c['pages'])} similar pages detected",
            "pages": [p["url"] for p in c["pages"]]
        })

    return findings
