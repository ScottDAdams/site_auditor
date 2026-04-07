def get_depth(path):
    if not path:
        return 0
    return len([p for p in path.strip("/").split("/") if p])


def is_valid_cluster(cluster):
    pages = cluster["pages"]
    paths = [p.get("path", "") for p in pages if p.get("path") is not None]

    # Need at least 2 unique paths
    if len(set(paths)) < 2:
        return False

    # Reject ONLY extreme noise: root + deep mixed
    has_root = any(p in ["", "/"] for p in paths)
    has_deep = any(get_depth(p) > 1 for p in paths)

    if has_root and has_deep:
        return False

    return True


def analyze_clusters(clusters):
    findings = []

    for c in clusters:
        if not is_valid_cluster(c):
            continue

        pages = c["pages"]
        types = [p.get("type") for p in pages]
        unique_types = set(t for t in types if t is not None)

        if unique_types == {"guide"}:
            issue_type = "High-risk duplication (SEO / AI content)"
            priority = "HIGH"

        elif unique_types == {"faq"}:
            issue_type = "Expected duplication (FAQ content)"
            priority = "LOW"

        elif unique_types == {"product"}:
            issue_type = "Acceptable duplication (product definitions)"
            priority = "LOW"

        elif "guide" in unique_types:
            issue_type = "Mixed content duplication (needs review)"
            priority = "MEDIUM"

        else:
            issue_type = "General duplication"
            priority = "MEDIUM"

        findings.append({
            "type": issue_type,
            "priority": priority,
            "pages": [p["url"] for p in pages],
            "avg_similarity": c["avg_similarity"],
        })

    return findings
