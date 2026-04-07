from urllib.parse import urlparse

from sklearn.metrics.pairwise import cosine_similarity

from app.utils import canonicalize_url, infer_technical_issue, urls_equivalent


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


DUPLICATION_TYPES = [
    "Exact duplication",
    "Structural duplication",
    "Intent overlap",
    "Cross-market reuse",
    "Navigational redundancy",
]


def _resolve_content_type(types: set) -> str:
    """Pick a single page-type label for rules; never return 'mixed'."""
    if len(types) == 1:
        return next(iter(types))
    if not types:
        return "other"
    order = ["guide", "product", "support", "faq", "brand", "other"]
    for t in order:
        if t in types:
            return t
    return "other"


def classify_duplication(cluster) -> str:
    """
    Heuristic taxonomy for cluster-level duplication.
    Always returns one of DUPLICATION_TYPES.
    """
    pages = cluster.get("pages") or []
    if len(pages) < 2:
        return "Structural duplication"

    avg_sim = float(cluster.get("avg_similarity", 0))
    domains = {p.get("domain") for p in pages if p.get("domain")}
    urls = [p["url"] for p in pages]
    paths = []
    for p in pages:
        path = p.get("path")
        if path is None:
            path = urlparse(p["url"]).path
        paths.append(path or "")

    if len(domains) > 1:
        return "Cross-market reuse"

    for i, u1 in enumerate(urls):
        for u2 in urls[i + 1 :]:
            if is_structural_match(u1, u2):
                return "Navigational redundancy"

    if avg_sim >= 0.94:
        return "Exact duplication"

    stripped = [p.strip("/") for p in paths if p is not None]
    if len(set(paths)) >= 2 and stripped:
        first_segments = {s.split("/")[0] for s in stripped if s}
        if len(first_segments) == 1:
            return "Structural duplication"

    if avg_sim >= 0.89:
        return "Intent overlap"

    return "Structural duplication"


def classify_topic_overlap(o: dict) -> str:
    """Taxonomy for cross-cluster / pair overlap signals."""
    cross = o.get("domain_1") != o.get("domain_2")
    sim = float(o.get("similarity", 0))
    u1, u2 = o.get("url_1", ""), o.get("url_2", "")

    if cross:
        return "Cross-market reuse"
    if is_structural_match(u1, u2):
        return "Navigational redundancy"
    if sim >= 0.94:
        return "Exact duplication"
    t1, t2 = o.get("type_1"), o.get("type_2")
    if t1 == "guide" and t2 == "guide":
        return "Intent overlap"
    if "product" in (t1, t2):
        return "Intent overlap"
    if sim >= 0.88:
        return "Intent overlap"
    return "Structural duplication"


def classify_cluster_decisions(clusters):
    """
    Tag each cluster for downstream AI vs technical-only handling.
    - ignore: normalized URLs are identical (crawl / alias noise).
    - technical_fix: same canonical resource, different URL forms (www, scheme, slash).
    - strategic: distinct resources; needs content strategy.
    """
    for cluster in clusters or []:
        pages = cluster.get("pages") or []
        urls = [p["url"] for p in pages if p.get("url")]
        cluster["urls"] = list(urls)
        equivalent_urls = []
        distinct_urls = []
        for url in urls:
            others = [o for o in urls if o != url]
            if any(urls_equivalent(url, o) for o in others):
                equivalent_urls.append(url)
            else:
                distinct_urls.append(url)
        cluster["equivalent_urls"] = equivalent_urls
        cluster["distinct_urls"] = distinct_urls

        if len(urls) < 2:
            cluster["decision_type"] = "ignore"
            cluster["technical_issue"] = None
            cluster["technical_fix_recommendation"] = None
            continue
        norms = {canonicalize_url(u) for u in urls}
        if len(norms) == 1:
            cluster["decision_type"] = "ignore"
            cluster["technical_issue"] = None
            cluster["technical_fix_recommendation"] = None
        elif len(distinct_urls) < 2:
            cluster["decision_type"] = "technical_fix"
            cluster["technical_issue"] = infer_technical_issue(urls)
            cluster["technical_fix_recommendation"] = (
                "301 redirect to one canonical URL + rel=canonical on duplicate URLs"
            )
        else:
            cluster["decision_type"] = "strategic"
            cluster["technical_issue"] = None
            cluster["technical_fix_recommendation"] = None


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
            "faq_present": False,
            "avg_words": 0.0,
            "content_depth": "LOW",
        }

    avg_wc = sum(p.get("word_count") or 0 for p in all_pages) / len(all_pages)
    faq_present = any(p.get("type") == "faq" for p in all_pages)
    depth_ok = avg_wc > 500
    return {
        "has_faq_content": faq_present,
        "has_guide_content": any(p.get("type") == "guide" for p in all_pages),
        "content_depth_ok": depth_ok,
        "average_word_count": avg_wc,
        "faq_present": faq_present,
        "avg_words": avg_wc,
        "content_depth": "GOOD" if depth_ok else "LOW",
    }


def analyze_clusters(clusters):
    findings = []

    for c in clusters:
        if not is_valid_cluster(c):
            continue

        pages = c["pages"]
        types = set(p.get("type") for p in pages if p.get("type"))
        domains = set(p.get("domain") for p in pages if p.get("domain"))

        primary_type = _resolve_content_type(types)

        cross_market = len(domains) > 1
        dup_type = classify_duplication(c)

        if primary_type in DUPLICATION_RULES:
            rule = DUPLICATION_RULES[primary_type]
            priority = rule["priority"]
            action = rule["action"]
        else:
            priority = "MEDIUM"
            action = "Manual review required"

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
                "duplication_type": dup_type,
                "dominant_url": c.get("dominant_url"),
                "competing_urls": c.get("competing_urls") or [],
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
            action = (
                "Pick one canonical URL, then merge or redirect the other so only one page owns the intent."
            )

        impact = get_impact(types, cross_market)
        dup_type = classify_topic_overlap(o)

        u1, u2 = o["url_1"], o["url_2"]
        p1 = urlparse(u1).path or ""
        p2 = urlparse(u2).path or ""
        if get_depth(p1) <= get_depth(p2):
            dom, comp = u1, [u2]
        else:
            dom, comp = u2, [u1]

        findings.append(
            {
                "type": "topic_overlap",
                "priority": priority,
                "action": action,
                "impact": impact,
                "similarity": o["similarity"],
                "pages": [u1, u2],
                "cross_market": cross_market,
                "overlap_types": types,
                "duplication_type": dup_type,
                "dominant_url": dom,
                "competing_urls": comp,
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
                        "Product URLs in this group duplicate positioning, which dilutes "
                        "conversion rates, adds decision friction, and weakens each page in search."
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
                        "Parallel AU and NZ pages weaken localization and send muddled "
                        "relevance signals to Google, hurting rankings and trust in each "
                        "market."
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
                        "Guide URLs in this group target the same intent, causing keyword "
                        "cannibalization and split authority so neither URL ranks at full strength."
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
                    "summary": (
                        "Overlapping pages create user friction and dilute clarity for "
                        "search engines about which URL should own each topic."
                    ),
                    "count": len(items),
                    "examples": items[:2],
                }
            )

    return grouped_issues


def calculate_content_health_score(_findings, grouped_issues, clusters, ai_readiness):
    score = 70

    high = sum(1 for g in grouped_issues if g.get("priority") == "HIGH")
    medium = sum(1 for g in grouped_issues if g.get("priority") == "MEDIUM")

    score -= high * 6
    score -= medium * 3

    if len(clusters) > 5:
        score -= min(8, len(clusters))

    if len(grouped_issues) == 1:
        score -= 4

    if ai_readiness.get("faq_present"):
        score += 5

    if ai_readiness.get("avg_words", 0) > 500:
        score += 5

    if ai_readiness.get("content_depth") == "GOOD":
        score += 5

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
