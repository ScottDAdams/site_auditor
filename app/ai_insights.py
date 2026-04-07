import json
import os
import re

from openai import OpenAI

from app.business_context import (
    default_allowed_actions,
    effective_allowed_actions,
    is_cross_domain,
    roadmap_step_allowed,
    url_requires_preservation,
)
from app.utils import normalize_url


def safe_pair(a: str, b: str) -> bool:
    """True if two URLs are different resources after normalization (safe for merge/redirect copy)."""
    if not a or not b:
        return False
    return normalize_url(a) != normalize_url(b)

BANNED_VERBS_RE = re.compile(
    r"\b(improve|optimi[sz]e|enhance|refine|strengthen|align)\b",
    re.I,
)
VERDICT_FLUFF_RE = re.compile(
    r"\b(significant|various|multiple)\b",
    re.I,
)
ACTION_VERBS_RE = re.compile(
    r"\b(merge|delete|consolidate|redirect|split|rewrite|differentiate|reposition|none)\b",
    re.I,
)
URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)

ROADMAP_ACTION_TYPES = frozenset(
    {
        "merge",
        "redirect",
        "delete",
        "consolidate",
        "split",
        "rewrite",
        "differentiate",
        "reposition",
        "none",
    }
)


def compute_audit_metrics(pages, clusters, all_findings):
    n = len(pages)
    if n == 0:
        return {
            "overlap_rate": 0.0,
            "avg_cluster_similarity": 0.0,
            "content_uniqueness_score": 1.0,
        }

    involved = set()
    for c in clusters:
        if c.get("decision_type") == "ignore":
            continue
        for p in c.get("pages", []):
            u = p.get("url") if isinstance(p, dict) else p
            if u:
                involved.add(u)
    for f in all_findings:
        for u in f.get("pages", []):
            if isinstance(u, dict):
                u = u.get("url")
            if u:
                involved.add(u)

    overlap_rate = round(min(1.0, len(involved) / n), 4)

    sims = [
        float(c.get("avg_similarity", 0))
        for c in clusters
        if c.get("decision_type") != "ignore"
        and c.get("pages")
        and len(c["pages"]) > 1
    ]
    avg_sim = round(sum(sims) / len(sims), 4) if sims else 0.0

    if not sims:
        uniqueness = 1.0
    else:
        uniqueness = round(max(0.0, min(1.0, 1.0 - avg_sim)), 4)

    return {
        "overlap_rate": overlap_rate,
        "avg_cluster_similarity": avg_sim,
        "content_uniqueness_score": uniqueness,
    }


_SHARED_RULES = """
If your output could apply to another website, it is wrong.

Every statement must tie to a URL from the payload or a numeric value from payload.metrics.
Do not use: improve, optimize, enhance, refine, strengthen, align.
Use concrete operations: merge, delete, consolidate, redirect, split, rewrite, differentiate, reposition, none (only where allowed by business_context.allowed_actions). Use "none" only when no structural content action is appropriate (e.g. technical-only issues already routed elsewhere).
"""

CONSTRAINT_PROMPT = """
HARD BUSINESS RULES (payload.business_context):
- URLs whose path matches protected_paths are REQUIRED assets: NEVER delete them or remove them from the site; do not recommend merging them into one page if that eliminates a required offering page.
- Paths listed in page_roles with value "core_product" MUST remain standalone indexable URLs; do NOT delete or merge those pages away.
- When market_context.separate_regions is true and URLs belong to different domains/regions, parallel regional pages are VALID; do NOT merge or redirect across regions—use differentiate or reposition so each region keeps its URL.
- When overlap involves protected or core_product pages, choose differentiate or reposition (rewrite positioning, split intent in copy)—NOT merge/delete/redirect that would remove a required URL.
- Only use action types that are true in allowed_actions; if delete is false, never prescribe deletion.
"""


class LLMClient:
    def __init__(self):
        self._client = OpenAI()

    def generate(self, prompt: str) -> str:
        model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
        response = self._client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        msg = response.choices[0].message
        return (msg.content or "").strip()

    def generate_json(self, prompt: str) -> dict:
        model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
        response = self._client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        text = response.choices[0].message.content or "{}"
        return json.loads(text)


def generate_ai_insights(payload, llm_client):
    data = json.dumps(payload, indent=2, default=str)
    prompt = f"""{_SHARED_RULES}
{CONSTRAINT_PROMPT}

You are a senior digital strategy consultant. Return JSON only (no markdown).

The verdict MUST:
- include at least one real https URL from the payload OR name a cluster by listing its dominant_url
- describe one specific structural conflict (not generic positioning language)
- NOT use the words: significant, various, multiple

The recommendation MUST:
- name explicit actions using verbs from: merge, delete, consolidate, redirect, split, rewrite, differentiate, reposition (must respect business_context.allowed_actions and protected/core_product rules)
- cite at least one real https URL from the payload
- if protected_paths or core_product pages are in overlap, state clearly that those URLs must NOT be deleted or merged away; prescribe differentiate or reposition instead

Each metrics_explained row MUST give value + implication in plain business terms (e.g. what 0.94 similarity means for Google or conversion).

The "clusters" array in this payload contains ONLY strategic clusters (distinct canonical resources). Ignore/technical URL-alias clusters are excluded—do not recommend merging URLs that are already normalized equivalents.

DATA:
{data}

Return JSON with EXACTLY these keys:
{{
  "verdict": "",
  "core_problem": "",
  "recommendation": "",
  "business_impact": "",
  "inaction_risk": "",
  "metrics_explained": [
    {{ "metric": "", "value": "", "implication": "" }}
  ],
  "primary_clusters": [],
  "supporting_evidence": [
    {{
      "urls": [],
      "issue": "",
      "metric_refs": []
    }}
  ]
}}

primary_clusters: array of short strings, each naming one cluster using dominant_url + similarity from payload.clusters.
supporting_evidence: at least 2 items; each metric_refs lists which metrics back the claim (e.g. "overlap_rate 0.62").
"""
    return llm_client.generate_json(prompt)


def generate_execution_roadmap(payload, llm_client):
    data = json.dumps(payload, indent=2, default=str)
    prompt = f"""{_SHARED_RULES}
{CONSTRAINT_PROMPT}

You are a digital strategy operator. Return JSON only (no markdown).

Create a 30-day execution plan: 3 to 5 steps, ordered by impact.

Each step MUST:
- set action_type to exactly one of: merge, redirect, delete, consolidate, split, rewrite, differentiate, reposition, none
- target_urls[0] and target_urls[1] MUST NOT normalize to the same URL when both are present (distinct destinations only)
- obey business_context.allowed_actions (only use action types set to true)
- NEVER use delete on protected_paths or core_product URLs; NEVER merge/redirect across regions when separate_regions is true
- include target_urls with at least one real https URL from the payload
- be atomic and testable (verifiable in staging)
- avoid banned verbs: improve, optimize, enhance, refine, strengthen, align

DATA:
{data}

Return JSON:
{{
  "roadmap": [
    {{
      "step": 1,
      "action_type": "merge",
      "title": "",
      "description": "",
      "target_urls": [],
      "expected_outcome": "",
      "evidence_refs": []
    }}
  ]
}}
"""
    return llm_client.generate_json(prompt)


def _text_clean_for_banned(s: str) -> bool:
    return s is not None and not BANNED_VERBS_RE.search(s)


def _verdict_valid(verdict: str) -> bool:
    if not verdict or not isinstance(verdict, str):
        return False
    if VERDICT_FLUFF_RE.search(verdict):
        return False
    if URL_RE.search(verdict):
        return True
    return bool(re.search(r"\bcluster\b", verdict, re.I))


def _recommendation_valid(rec: str) -> bool:
    if not rec or not isinstance(rec, str):
        return False
    if BANNED_VERBS_RE.search(rec):
        return False
    if not ACTION_VERBS_RE.search(rec):
        return False
    if not URL_RE.search(rec):
        return False
    return True


def validate_ai_output(ai_output) -> bool:
    if not isinstance(ai_output, dict):
        return False
    required = (
        "verdict",
        "core_problem",
        "recommendation",
        "business_impact",
        "inaction_risk",
        "metrics_explained",
        "primary_clusters",
        "supporting_evidence",
    )
    if any(k not in ai_output for k in required):
        return False
    if not _verdict_valid(ai_output.get("verdict", "")):
        return False
    if not _recommendation_valid(ai_output.get("recommendation", "")):
        return False
    me = ai_output.get("metrics_explained")
    if not isinstance(me, list) or len(me) < 1:
        return False
    for row in me:
        if not isinstance(row, dict):
            return False
        if not (row.get("metric") and row.get("value") and row.get("implication")):
            return False
        if BANNED_VERBS_RE.search(str(row.get("implication", ""))):
            return False
    pc = ai_output.get("primary_clusters")
    if not isinstance(pc, list) or len(pc) < 1:
        return False
    ev = ai_output.get("supporting_evidence")
    if not isinstance(ev, list) or len(ev) < 2:
        return False
    for item in ev:
        if not isinstance(item, dict):
            return False
        urls = item.get("urls")
        if not isinstance(urls, list) or len(urls) < 1:
            return False
        if not item.get("issue"):
            return False
        mrefs = item.get("metric_refs")
        if not isinstance(mrefs, list):
            return False
    return True


def _roadmap_step_ok(item: dict) -> bool:
    if not isinstance(item, dict):
        return False
    at = (item.get("action_type") or "").lower().strip()
    if at not in ROADMAP_ACTION_TYPES:
        return False
    urls = item.get("target_urls")
    if not isinstance(urls, list):
        return False
    if at == "none":
        return bool(item.get("title") or item.get("description"))
    if len(urls) < 1:
        return False
    if not item.get("title") or not item.get("description"):
        return False
    if not item.get("expected_outcome"):
        return False
    desc = item.get("description", "")
    if BANNED_VERBS_RE.search(desc):
        return False
    return True


def validate_roadmap_output(obj, business_context: dict | None = None) -> bool:
    if not isinstance(obj, dict):
        return False
    r = obj.get("roadmap")
    if not isinstance(r, list) or len(r) < 3 or len(r) > 5:
        return False
    bc = business_context or {}
    for x in r:
        if not _roadmap_step_ok(x):
            return False
        turls = x.get("target_urls") or []
        if isinstance(turls, list) and len(turls) >= 2:
            if normalize_url(str(turls[0])) == normalize_url(str(turls[1])):
                return False
        if not roadmap_step_allowed(x, bc):
            return False
    return True


def _strategic_cluster_rows(payload: dict) -> list:
    sc = payload.get("strategic_clusters")
    if isinstance(sc, list) and len(sc) > 0:
        return sc
    return [
        c
        for c in (payload.get("clusters") or [])
        if c.get("decision_type") == "strategic"
    ]


def _first_urls_from_payload(payload: dict, limit: int = 8):
    """URLs from strategic clusters only — no grouped_issues or page_urls (avoids contamination)."""
    urls = []
    for c in _strategic_cluster_rows(payload):
        d = c.get("dominant_url")
        if d:
            urls.append(d)
        for u in c.get("competing_urls") or []:
            urls.append(u)
        for p in c.get("pages") or []:
            u = p if isinstance(p, str) else (p.get("url") if isinstance(p, dict) else None)
            if u:
                urls.append(u)
        if len(urls) >= limit * 2:
            break
    out = []
    seen = set()
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
        if len(out) >= limit:
            break
    return out


def _candidate_url_pairs(urls: list[str], max_urls: int = 10) -> list[tuple[str, str]]:
    u = urls[:max_urls]
    pairs = []
    for i in range(len(u)):
        for j in range(i + 1, len(u)):
            pairs.append((u[i], u[j]))
    return pairs


def _fallback_insights_technical_variants_only(
    metrics_explained: list, m: dict, payload: dict
) -> dict:
    pu = (payload.get("page_urls") or [])[:2]
    ev_urls = pu if len(pu) >= 2 else (pu + ["https://127.0.0.1/"])[:2]
    return {
        "verdict": "No strategic content conflicts detected after normalization.",
        "core_problem": (
            "Duplicate signals are caused by technical URL variants, not structural content issues."
        ),
        "recommendation": "Apply canonical tags and redirects to normalize URL variants.",
        "business_impact": (
            "Technical URL duplication can dilute crawl budget and split signals until one canonical URL is chosen."
        ),
        "inaction_risk": (
            "Without canonical normalization, equivalent URLs may continue to compete for the same intent."
        ),
        "metrics_explained": metrics_explained,
        "primary_clusters": [
            "No strategic duplicate clusters after normalization—address variants under Technical SEO fixes."
        ],
        "supporting_evidence": [
            {
                "urls": ev_urls[:1] or ["https://127.0.0.1/"],
                "issue": "Embedding overlap is driven by URL aliases, not distinct page topics.",
                "metric_refs": [f"overlap_rate {m.get('overlap_rate', 0)}"],
            },
            {
                "urls": ev_urls if len(ev_urls) >= 2 else ev_urls + ["https://127.0.0.1/"],
                "issue": "Normalize scheme, host, trailing slashes, and homepage paths before content consolidation.",
                "metric_refs": [
                    f"avg_cluster_similarity {m.get('avg_cluster_similarity', 0)}",
                    f"content_uniqueness_score {m.get('content_uniqueness_score', 0)}",
                ],
            },
        ],
    }


def _safe_evidence_urls_for_cluster(c: dict) -> list[str]:
    """Up to two URLs from a strategic cluster that are not normalization-equivalent."""
    dom = c.get("dominant_url")
    comp = c.get("competing_urls") or []
    if dom:
        for co in comp:
            if safe_pair(dom, co):
                return [dom, co]
    plist = []
    for p in c.get("pages") or []:
        u = p if isinstance(p, str) else (p.get("url") if isinstance(p, dict) else None)
        if u:
            plist.append(u)
    for i, a in enumerate(plist):
        for b in plist[i + 1 :]:
            if safe_pair(a, b):
                return [a, b]
    return []


def build_fallback_insights(payload: dict) -> dict:
    m = payload.get("metrics") or {}
    bc = payload.get("business_context") or {}
    mc = bc.get("market_context") or {}

    metrics_explained = [
        {
            "metric": "overlap_rate",
            "value": str(m.get("overlap_rate", 0)),
            "implication": (
                "Share of crawled pages that sit inside a similarity cluster or overlap "
                "finding—high values mean the crawl is dominated by tied URLs, not isolated pages."
            ),
        },
        {
            "metric": "avg_cluster_similarity",
            "value": str(m.get("avg_cluster_similarity", 0)),
            "implication": (
                "Within duplicate clusters, embeddings sit this close—close to 1.0 means "
                "search engines see one topic duplicated across URLs."
            ),
        },
        {
            "metric": "content_uniqueness_score",
            "value": str(m.get("content_uniqueness_score", 0)),
            "implication": (
                "Derived as 1 minus average cluster similarity—lower scores mean less "
                "distinct copy between competing URLs."
            ),
        },
    ]

    clusters_strategic = [
        c for c in (payload.get("clusters") or []) if c.get("decision_type") == "strategic"
    ]
    if payload.get("strategic_clusters"):
        clusters_strategic = list(payload["strategic_clusters"])

    urls_pool = _first_urls_from_payload(payload, 12)
    candidate_pairs = _candidate_url_pairs(urls_pool, 12)
    safe_pairs = [(a, b) for (a, b) in candidate_pairs if safe_pair(a, b)]

    if not clusters_strategic or not safe_pairs:
        return _fallback_insights_technical_variants_only(metrics_explained, m, payload)

    u0, u1 = safe_pairs[0]

    primary_clusters = []
    for i, c in enumerate(clusters_strategic[:5], start=1):
        dom = c.get("dominant_url") or ""
        comp = ", ".join((c.get("competing_urls") or [])[:4])
        sim = c.get("similarity", c.get("avg_similarity", ""))
        primary_clusters.append(
            f"Cluster {i} (similarity {sim}): canonical {dom}; competing {comp}"
        )

    ev = []
    for c in clusters_strategic:
        if len(ev) >= 3:
            break
        ulist = _safe_evidence_urls_for_cluster(c)
        if len(ulist) < 2:
            continue
        dom = c.get("dominant_url")
        comp = c.get("competing_urls") or []
        ev.append(
            {
                "urls": ulist,
                "issue": (
                    f"Near-duplicate cluster at similarity {c.get('similarity')}: "
                    f"{dom} competes with {', '.join(comp[:3])}."
                ),
                "metric_refs": [
                    f"avg_cluster_similarity {c.get('similarity', m.get('avg_cluster_similarity', 0))}",
                    f"content_uniqueness_score {m.get('content_uniqueness_score', 0)}",
                ],
            }
        )
    spi = 0
    while len(ev) < 2 and spi < len(safe_pairs):
        a, b = safe_pairs[spi]
        spi += 1
        ev.append(
            {
                "urls": [a, b],
                "issue": (
                    "Distinct normalized URLs share one embedding cluster—address as content strategy, "
                    "not URL-alias cleanup."
                ),
                "metric_refs": [
                    f"overlap_rate {m.get('overlap_rate', 0)}",
                    f"avg_cluster_similarity {m.get('avg_cluster_similarity', 0)}",
                ],
            }
        )

    anchor_url = u0 or "https://localhost"
    any_preserved = any(url_requires_preservation(u, bc) for u in (urls_pool or []))
    cross_regional = (
        u0
        and u1
        and u0 != u1
        and mc.get("separate_regions")
        and is_cross_domain(u0, u1)
    )

    if cross_regional:
        verdict = (
            f"Cluster spans regions ({u0} vs {u1}): both URLs stay live; overlap_rate "
            f"{m.get('overlap_rate', 0)} reflects parallel markets, not a merge target."
        )
        rec = (
            f"Reposition {u0} and {u1} with market-specific proof and offers; "
            f"do not merge or redirect across regional domains."
        )
        core_problem = (
            f"Regional domains share near-identical embeddings ({u0} vs {u1}); the issue is "
            f"undifferentiated copy, not excess URLs."
        )
    elif any_preserved:
        preserved_list = [u for u in urls_pool if url_requires_preservation(u, bc)][:4]
        pl = ", ".join(preserved_list) if preserved_list else anchor_url
        verdict = (
            f"Required URLs ({pl}) sit inside overlap at overlap_rate {m.get('overlap_rate', 0)}; "
            f"noise is structural, not permission to remove offerings."
        )
        rec = (
            f"Differentiate {pl}: rewrite H1, hero, and eligibility copy so each required "
            f"page owns one use case; do not delete or merge those routes away."
        )
        core_problem = (
            f"Required URLs participate in overlap signals while staying business-mandatory; "
            f"the issue is positioning collision, not removable pages."
        )
    else:
        verdict = (
            f"Overlap is anchored at {anchor_url}: tied URLs share one embedding cluster "
            f"at overlap_rate {m.get('overlap_rate', 0)}."
        )
        if u0 and u1 and u0 != u1:
            verdict = (
                f"Conflict sits between {u0} and {u1} under the same duplication signal "
                f"at overlap_rate {m.get('overlap_rate', 0)}."
            )
        rec = (
            f"Merge body copy from {u1} into {u0}, then redirect "
            f"secondary URLs after redundant blocks are removed."
        )
        core_problem = (
            "The crawl maps competing URLs into the same embedding cluster; canonical vs "
            "competing paths are listed per strategic cluster above."
        )

    return {
        "verdict": verdict,
        "core_problem": core_problem,
        "recommendation": rec,
        "business_impact": (
            "Split traffic and backlinks across tied URLs depresses conversion clarity and "
            "regional relevance per domain."
        ),
        "inaction_risk": (
            "Publishing more pages without consolidating duplicates repeats the same "
            "cannibalization pattern."
        ),
        "metrics_explained": metrics_explained,
        "primary_clusters": primary_clusters[:6],
        "supporting_evidence": ev[:6],
    }


def _default_no_consolidation_roadmap_step() -> dict:
    return {
        "step": 1,
        "action_type": "none",
        "title": "No structural consolidation required",
        "description": (
            "Detected duplication is due to technical URL variants, not content structure."
        ),
        "target_urls": [],
        "expected_outcome": "Improved crawl consistency after canonical normalization.",
        "evidence_refs": [],
    }


def build_fallback_roadmap(payload: dict) -> dict:
    if not _strategic_cluster_rows(payload):
        return {"roadmap": [_default_no_consolidation_roadmap_step()]}

    bc = payload.get("business_context") or {}
    allowed = effective_allowed_actions(bc)
    mc = bc.get("market_context") or {}

    urls = _first_urls_from_payload(payload, 12)
    if not urls:
        return {"roadmap": [_default_no_consolidation_roadmap_step()]}

    candidate_pairs = _candidate_url_pairs(urls, 12)
    safe_pairs = [(a, b) for (a, b) in candidate_pairs if safe_pair(a, b)]
    if not safe_pairs:
        return {"roadmap": [_default_no_consolidation_roadmap_step()]}

    u0, u1 = safe_pairs[0]
    u2 = None
    for cand in urls:
        if cand == u0:
            continue
        if safe_pair(cand, u0):
            u2 = cand
            break

    steps = []

    def push(step: dict) -> bool:
        turls = step.get("target_urls") or []
        if isinstance(turls, list) and len(turls) >= 2:
            if normalize_url(str(turls[0])) == normalize_url(str(turls[1])):
                return False
        step = {**step, "step": len(steps) + 1}
        if roadmap_step_allowed(step, bc):
            steps.append(step)
            return True
        return False

    def try_action(
        primary: str,
        title: str,
        desc: str,
        targets: list,
        outcome: str,
        refs: list,
    ) -> bool:
        if len(targets) >= 2:
            if normalize_url(str(targets[0])) == normalize_url(str(targets[1])):
                return False
        if not allowed.get(primary, False):
            return False
        if push(
            {
                "action_type": primary,
                "title": title,
                "description": desc,
                "target_urls": targets,
                "expected_outcome": outcome,
                "evidence_refs": refs,
            }
        ):
            return True
        if primary == "differentiate" and allowed.get("reposition") and len(targets) >= 1:
            if push(
                {
                    "action_type": "reposition",
                    "title": "Adjust intent targeting (fallback)",
                    "description": (
                        f"Reposition proof and offers on {targets[0]} "
                        f"{f'and {targets[1]}' if len(targets) > 1 else ''} to separate buyer intents."
                    ),
                    "target_urls": targets[:4],
                    "expected_outcome": "Clearer intent boundaries without structural merge.",
                    "evidence_refs": refs,
                }
            ):
                return True
        if primary in ("merge", "consolidate", "redirect"):
            if allowed.get("differentiate") and len(targets) >= 2:
                ddesc = (
                    f"Differentiate copy and H1 on {targets[0]} versus {targets[1]} so each "
                    f"URL owns one use case; keep both routes live."
                )
                if push(
                    {
                        "action_type": "differentiate",
                        "title": "Clarify positioning between required URLs",
                        "description": ddesc,
                        "target_urls": targets[:4],
                        "expected_outcome": "Lower intent collision without removing business URLs.",
                        "evidence_refs": refs + ["business_context.protected_paths"],
                    }
                ):
                    return True
            if allowed.get("reposition"):
                rdesc = (
                    f"Reposition hero and proof blocks on {targets[0]} to target its primary "
                    f"buyer; mirror on {targets[1] if len(targets) > 1 else targets[0]} with a distinct angle."
                )
                if push(
                    {
                        "action_type": "reposition",
                        "title": "Adjust intent targeting per URL",
                        "description": rdesc,
                        "target_urls": targets[:4],
                        "expected_outcome": "Embeddings separate while URLs stay published.",
                        "evidence_refs": refs + ["market_context.separate_regions"],
                    }
                ):
                    return True
        return False

    if u0 and u1 and safe_pair(u0, u1):
        if mc.get("separate_regions") and is_cross_domain(u0, u1):
            try_action(
                "differentiate",
                "Keep regional URLs; split messaging",
                f"Differentiate {u0} vs {u1} with locale-specific proof and pricing; no cross-domain merge.",
                [u0, u1],
                "Regional pages stay indexed with clearer intent boundaries.",
                ["market_context.separate_regions"],
            )
        elif url_requires_preservation(u0, bc) or url_requires_preservation(u1, bc):
            try_action(
                "differentiate",
                "Separate required product narratives",
                f"Differentiate {u0} and {u1} so each required page states a distinct use case and CTA.",
                [u0, u1],
                "Core offerings remain live with less cannibalization.",
                ["business_context.page_roles", "protected_paths"],
            )
        else:
            try_action(
                "merge",
                "Collapse duplicate topic into one URL",
                f"Merge body copy from {u1} into {u0}; keep one H1 and one CTA path.",
                [u0, u1],
                "One ranking URL per intent; internal links stop splitting across twins.",
                ["cluster dominant_url", "avg_cluster_similarity"],
            )
    elif urls:
        try_action(
            "rewrite",
            "Differentiate the sampled page",
            f"Rewrite headings and proof blocks on {urls[0]} so it cannot match sibling URLs verbatim.",
            [urls[0]],
            "Embeddings diverge enough to exit duplicate clusters on the next crawl.",
            ["content_uniqueness_score"],
        )

    if u0 and u2 and safe_pair(u2, u0) and len(steps) < 5:
        try_action(
            "redirect",
            "Point secondary URL to canonical",
            f"Redirect {u2} to {u0} with 301 after merge is live in staging.",
            [u2, u0],
            "Backlinks and crawlers consolidate on one destination.",
            ["roadmap prior step"],
        )

    if not steps:
        return {"roadmap": [_default_no_consolidation_roadmap_step()]}

    out = steps[:5]
    for i, s in enumerate(out, start=1):
        s["step"] = i
    return {"roadmap": out}
