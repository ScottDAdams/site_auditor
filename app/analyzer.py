from urllib.parse import urlparse

from sklearn.metrics.pairwise import cosine_similarity


def is_homepage(url: str) -> bool:
    path = urlparse(url).path
    return path in ["", "/"]


def is_structural_match(url1: str, url2: str) -> bool:
    u1, u2 = url1.lower(), url2.lower()
    return (
        "/about-us" in u1
        and "/about-us" in u2
        or "/testimonials" in u1
        and "/testimonials" in u2
        or "/our-awards" in u1
        and "/our-awards" in u2
    )

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
    seen_pairs = set()

    for i in range(len(pages)):
        for j in range(i + 1, len(pages)):
            p1 = pages[i]
            p2 = pages[j]

            if is_homepage(p1["url"]) or is_homepage(p2["url"]):
                continue

            cid1 = url_to_cluster.get(p1["url"])
            cid2 = url_to_cluster.get(p2["url"])
            if cid1 is not None and cid2 is not None and cid1 == cid2:
                continue

            sim = float(
                cosine_similarity([embeddings[i]], [embeddings[j]])[0][0]
            )

            if sim >= threshold:
                key = tuple(sorted([p1["url"].rstrip("/"), p2["url"].rstrip("/")]))
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)

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


def get_impact(types, cross_market):
    types_set = set(types)

    # 1. PRODUCT CONFLICT (highest priority)
    if "product" in types_set:
        return (
            "These pages overlap in product positioning, which can confuse users choosing between plans, "
            "reduce conversion clarity, and weaken differentiation between offerings."
        )

    # 2. CROSS-MARKET DUPLICATION
    if cross_market:
        return (
            "This reduces localization effectiveness and may signal duplicate content across regions, "
            "weakening regional relevance."
        )

    # 3. GUIDE / SEO IMPACT
    if "guide" in types_set:
        return (
            "This overlap can dilute SEO authority, create keyword cannibalization, "
            "and reduce visibility in AI-driven search results."
        )

    # 4. DEFAULT
    return (
        "This may create redundant content and reduce overall site clarity."
    )


def analyze_overlaps(overlaps):
    findings = []
    seen_pairs = set()

    for o in overlaps:
        key = tuple(sorted([o["url_1"].rstrip("/"), o["url_2"].rstrip("/")]))
        if key in seen_pairs:
            continue
        seen_pairs.add(key)

        if is_structural_match(o["url_1"], o["url_2"]):
            continue

        cross_market = o["domain_1"] != o["domain_2"]
        types = [o["type_1"], o["type_2"]]

        if types.count("product") == 2:
            priority = "HIGH"
            action = (
                "Clarify positioning between these product offerings "
                "(coverage, audience, use case)."
            )
        elif "guide" in types:
            priority = "HIGH"
            action = "Consolidate or clearly differentiate these informational pages."
        elif cross_market and o["similarity"] > 0.90:
            priority = "HIGH"
            action = "Localize content to better differentiate AU vs NZ audiences."
        else:
            priority = "MEDIUM"
            action = "Review for overlapping intent"

        impact = get_impact(types, cross_market)

        findings.append(
            {
                "type": "topic_overlap",
                "priority": priority,
                "action": action,
                "impact": impact,
                "similarity": o["similarity"],
                "pages": [o["url_1"], o["url_2"]],
                "cross_market": cross_market,
                "overlap_types": types,
            }
        )

    findings = sorted(
        findings, key=lambda x: x["priority"] == "HIGH", reverse=True
    )
    return findings[:8]


def group_findings(findings):
    groups = {
        "product_positioning": [],
        "cross_market_duplication": [],
        "informational_overlap": [],
        "other": [],
    }

    for f in findings:
        if f.get("type") != "topic_overlap":
            continue

        types = f.get("overlap_types") or []

        if "product" in types:
            groups["product_positioning"].append(f)
        elif f.get("cross_market"):
            groups["cross_market_duplication"].append(f)
        elif "guide" in types:
            groups["informational_overlap"].append(f)
        else:
            groups["other"].append(f)

    grouped_issues = []

    for key, items in groups.items():
        if not items:
            continue

        if key == "product_positioning":
            grouped_issues.append(
                {
                    "title": "Product Positioning Overlap",
                    "priority": "HIGH",
                    "summary": (
                        "Multiple product pages overlap in positioning and may confuse "
                        "users choosing between plans."
                    ),
                    "count": len(items),
                    "examples": items[:2],
                }
            )

        elif key == "cross_market_duplication":
            grouped_issues.append(
                {
                    "title": "Cross-Market Content Duplication",
                    "priority": "HIGH",
                    "summary": (
                        "Content between AU and NZ sites lacks differentiation and "
                        "localization."
                    ),
                    "count": len(items),
                    "examples": items[:2],
                }
            )

        elif key == "informational_overlap":
            grouped_issues.append(
                {
                    "title": "Informational Content Overlap",
                    "priority": "HIGH",
                    "summary": (
                        "Multiple pages target similar informational intent, reducing "
                        "SEO effectiveness."
                    ),
                    "count": len(items),
                    "examples": items[:2],
                }
            )

        else:
            grouped_issues.append(
                {
                    "title": "General Content Overlap",
                    "priority": "MEDIUM",
                    "summary": "Some content may overlap and should be reviewed.",
                    "count": len(items),
                    "examples": items[:2],
                }
            )

    return grouped_issues


def generate_top_actions(grouped_issues):
    actions = []
    added = set()

    for issue in grouped_issues:
        title = issue["title"]

        if title == "Product Positioning Overlap":
            actions.append(
                {
                    "title": "Clarify product differentiation across policy pages",
                    "details": [
                        "Define clear distinctions between plans (coverage, audience, use case)",
                        "Update page copy to emphasize unique value of each plan",
                        "Reduce overlap in messaging across product pages",
                    ],
                }
            )
            added.add("product")

        elif title == "Cross-Market Content Duplication":
            actions.append(
                {
                    "title": "Improve AU vs NZ content localization",
                    "details": [
                        "Introduce region-specific messaging and positioning",
                        "Adjust examples, benefits, and terminology per market",
                        "Avoid identical copy across regional sites",
                    ],
                }
            )
            added.add("cross_market")

        elif title == "Informational Content Overlap":
            actions.append(
                {
                    "title": "Consolidate overlapping informational content",
                    "details": [
                        "Merge or differentiate pages targeting similar topics",
                        "Ensure each page has a distinct keyword and intent",
                        "Reduce internal competition between guides",
                    ],
                }
            )
            added.add("informational")

    if "cross_market" not in added:
        actions.append(
            {
                "title": "Improve AU vs NZ content localization",
                "details": [
                    "Introduce region-specific messaging and positioning",
                    "Adjust benefits and terminology per market",
                    "Avoid identical copy across regional sites",
                ],
            }
        )

    if "product" not in added:
        actions.append(
            {
                "title": "Clarify product structure and differentiation",
                "details": [
                    "Ensure each product page targets a distinct audience or use case",
                    "Reduce overlap between similar offerings",
                    "Improve clarity in plan comparisons",
                ],
            }
        )

    if "informational" not in added:
        actions.append(
            {
                "title": "Consolidate overlapping site structure",
                "details": [
                    "Merge or differentiate pages that compete for the same intent",
                    "Clarify internal linking and topic ownership",
                    "Reduce redundant content paths",
                ],
            }
        )

    return actions[:3]


def calculate_content_health_score(findings, grouped_issues, clusters):
    score = 100

    high = sum(1 for f in findings if f.get("priority") == "HIGH")
    medium = sum(1 for f in findings if f.get("priority") == "MEDIUM")

    score -= high * 8
    score -= medium * 4

    if len(clusters) > 5:
        score -= min(10, len(clusters))

    if len(grouped_issues) == 1:
        score -= 5

    return max(0, min(100, score))


def score_label(score):
    if score >= 85:
        return "Strong"
    elif score >= 70:
        return "Good"
    elif score >= 55:
        return "Moderate Risk"
    else:
        return "High Risk"
