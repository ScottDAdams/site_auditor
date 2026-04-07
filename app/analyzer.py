from sklearn.metrics.pairwise import cosine_similarity

DUPLICATION_RULES = {
    "guide": {
        "priority": "HIGH",
        "action": "Rewrite for market-specific differentiation",
    },
    "faq": {
        "priority": "LOW",
        "action": "Acceptable duplication; ensure answers are slightly localized",
    },
    "product": {
        "priority": "MEDIUM",
        "action": "Review for localization (pricing, coverage, regulations)",
    },
    "support": {
        "priority": "MEDIUM",
        "action": "Review for local contact and support differences",
    },
    "brand": {
        "priority": "LOW",
        "action": "Acceptable duplication",
    },
    "other": {
        "priority": "MEDIUM",
        "action": "Manual review required",
    },
}


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


def compute_ai_readiness(all_pages):
    if not all_pages:
        return {
            "has_faq_content": False,
            "has_guide_content": False,
            "content_depth_ok": False,
            "average_word_count": 0.0,
        }

    avg_wc = sum(p.get("word_count") or 0 for p in all_pages) / len(all_pages)
    return {
        "has_faq_content": any(p.get("type") == "faq" for p in all_pages),
        "has_guide_content": any(p.get("type") == "guide" for p in all_pages),
        "content_depth_ok": avg_wc > 500,
        "average_word_count": avg_wc,
    }


def analyze_clusters(clusters):
    findings = []

    for c in clusters:
        if not is_valid_cluster(c):
            continue

        pages = c["pages"]
        types = set(p.get("type") for p in pages if p.get("type"))
        domains = set(p.get("domain") for p in pages if p.get("domain"))

        if len(types) == 1:
            primary_type = next(iter(types))
        elif len(types) == 0:
            primary_type = "other"
        else:
            primary_type = "mixed"

        cross_market = len(domains) > 1

        if primary_type in DUPLICATION_RULES:
            rule = DUPLICATION_RULES[primary_type]
            priority = rule["priority"]
            action = rule["action"]
        else:
            priority = "MEDIUM"
            action = "Mixed content types require manual review"

        if cross_market and primary_type == "guide":
            priority = "HIGH"
            action = "Rewrite for distinct AU vs NZ positioning and intent"

        findings.append(
            {
                "type": primary_type,
                "priority": priority,
                "action": action,
                "cross_market": cross_market,
                "avg_similarity": c["avg_similarity"],
                "pages": [p["url"] for p in pages],
            }
        )

    return findings


def detect_topic_overlap(pages, embeddings, clusters, threshold=0.85):
    url_to_cluster = {}
    for idx, c in enumerate(clusters):
        for p in c["pages"]:
            url_to_cluster[p["url"]] = idx

    overlaps = []

    for i in range(len(pages)):
        for j in range(i + 1, len(pages)):
            p1 = pages[i]
            p2 = pages[j]

            cid1 = url_to_cluster.get(p1["url"])
            cid2 = url_to_cluster.get(p2["url"])
            if cid1 is not None and cid2 is not None and cid1 == cid2:
                continue

            sim = float(
                cosine_similarity([embeddings[i]], [embeddings[j]])[0][0]
            )

            if sim >= threshold:
                overlaps.append(
                    {
                        "url_1": p1["url"],
                        "url_2": p2["url"],
                        "similarity": sim,
                        "type_1": p1.get("type"),
                        "type_2": p2.get("type"),
                        "domain_1": p1.get("domain"),
                        "domain_2": p2.get("domain"),
                    }
                )

    overlaps = sorted(overlaps, key=lambda x: x["similarity"], reverse=True)
    return overlaps[:20]


def analyze_overlaps(overlaps):
    findings = []

    for o in overlaps:
        cross_market = o["domain_1"] != o["domain_2"]

        if "guide" in [o["type_1"], o["type_2"]]:
            priority = "HIGH"
            action = "Consolidate or clearly differentiate these pages"
        else:
            priority = "MEDIUM"
            action = "Review for overlapping intent"

        if cross_market:
            action += " with AU vs NZ positioning differences"

        findings.append(
            {
                "type": "topic_overlap",
                "priority": priority,
                "action": action,
                "similarity": o["similarity"],
                "pages": [o["url_1"], o["url_2"]],
                "cross_market": cross_market,
            }
        )

    return findings
