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

BANNED_VERBS_RE = re.compile(
    r"\b(improve|optimi[sz]e|enhance|refine|strengthen|align)\b",
    re.I,
)
VERDICT_FLUFF_RE = re.compile(
    r"\b(significant|various|multiple)\b",
    re.I,
)
ACTION_VERBS_RE = re.compile(
    r"\b(merge|delete|consolidate|redirect|split|rewrite|differentiate|reposition)\b",
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
        if c.get("pages") and len(c["pages"]) > 1
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
Use concrete operations: merge, delete, consolidate, redirect, split, rewrite, differentiate, reposition (only where allowed by business_context.allowed_actions).
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
- set action_type to exactly one of: merge, redirect, delete, consolidate, split, rewrite, differentiate, reposition
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
    if not isinstance(urls, list) or len(urls) < 1:
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
        if not roadmap_step_allowed(x, bc):
            return False
    return True


def _first_urls_from_payload(payload: dict, limit: int = 8):
    urls = []
    for c in payload.get("clusters") or []:
        d = c.get("dominant_url")
        if d:
            urls.append(d)
        for u in c.get("competing_urls") or []:
            urls.append(u)
        for u in c.get("pages") or []:
            urls.append(u)
        if len(urls) >= limit:
            break
    for g in payload.get("grouped_issues") or []:
        for ex in g.get("examples") or []:
            for u in ex.get("pages") or []:
                urls.append(u)
    for u in payload.get("page_urls") or []:
        urls.append(u)
    out = []
    seen = set()
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
        if len(out) >= limit:
            break
    return out


def build_fallback_insights(payload: dict) -> dict:
    m = payload.get("metrics") or {}
    bc = payload.get("business_context") or {}
    mc = bc.get("market_context") or {}
    urls_pool = _first_urls_from_payload(payload, 12)
    u0 = urls_pool[0] if urls_pool else None
    u1 = urls_pool[1] if len(urls_pool) > 1 else u0

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

    primary_clusters = []
    for i, c in enumerate((payload.get("clusters") or [])[:5], start=1):
        dom = c.get("dominant_url") or ""
        comp = ", ".join((c.get("competing_urls") or [])[:4])
        sim = c.get("similarity", c.get("avg_similarity", ""))
        primary_clusters.append(
            f"Cluster {i} (similarity {sim}): canonical {dom}; competing {comp}"
        )

    if not primary_clusters:
        primary_clusters.append(
            "No multi-page embedding cluster in this sample—expand crawl URLs to capture overlap."
        )

    ev = []
    for g in payload.get("grouped_issues", [])[:2]:
        ulist = []
        for ex in (g.get("examples") or [])[:1]:
            ulist = (ex.get("pages") or [])[:4]
        if not ulist and urls_pool:
            ulist = urls_pool[:2]
        ev.append(
            {
                "urls": ulist or (urls_pool[:2] if urls_pool else (payload.get("page_urls") or [])[:2]),
                "issue": (g.get("title") or "Overlap") + ": " + (g.get("summary") or "")[:320],
                "metric_refs": [
                    f"overlap_rate {m.get('overlap_rate', 0)}",
                    f"avg_cluster_similarity {m.get('avg_cluster_similarity', 0)}",
                ],
            }
        )
    for c in payload.get("clusters") or []:
        if len(ev) >= 3:
            break
        dom = c.get("dominant_url")
        comp = c.get("competing_urls") or []
        pages = c.get("pages") or []
        ulist = [dom] + list(comp) if dom else pages[:4]
        ulist = [x for x in ulist if x][:4]
        if len(ulist) < 2:
            continue
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
    while len(ev) < 2:
        pu = (payload.get("page_urls") or [])[:2]
        ev.append(
            {
                "urls": pu or urls_pool[:2] or ["https://127.0.0.1/"],
                "issue": "Crawl returned sparse overlap—expand seed URLs and re-run.",
                "metric_refs": [f"overlap_rate {m.get('overlap_rate', 0)}"],
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
            f"Consolidate duplicate sections into one canonical URL (start with {anchor_url}), "
            f"then redirect secondary URLs listed under each cluster."
        )
        if urls_pool and len(urls_pool) > 1:
            rec = (
                f"Merge body copy from {urls_pool[1]} into {urls_pool[0]}, then redirect "
                f"{urls_pool[1]} after redundant blocks are removed."
            )
        elif urls_pool:
            rec = (
                f"Rewrite {urls_pool[0]} as the single canonical page, then redirect "
                f"duplicate routes that are not business-required."
            )

    core_problem = (
        "The crawl maps competing URLs into the same embedding cluster; canonical vs "
        "competing paths are listed per cluster above."
    )
    if cross_regional:
        core_problem = (
            f"Regional domains share near-identical embeddings ({u0} vs {u1}); the issue is "
            f"undifferentiated copy, not excess URLs."
        )
    elif any_preserved:
        core_problem = (
            f"Required URLs participate in overlap signals while staying business-mandatory; "
            f"the issue is positioning collision, not removable pages."
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


def build_fallback_roadmap(payload: dict) -> dict:
    bc = payload.get("business_context") or {}
    allowed = effective_allowed_actions(bc)
    mc = bc.get("market_context") or {}

    urls = _first_urls_from_payload(payload, 12)
    if not urls:
        urls = list(payload.get("page_urls") or [])[:8]
    gissues = payload.get("grouped_issues") or []
    steps = []

    def push(step: dict) -> bool:
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

    u0 = urls[0] if urls else None
    u1 = urls[1] if len(urls) > 1 else u0
    u2 = urls[2] if len(urls) > 2 else u1

    if u0 and u1 and u0 != u1:
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

    elif u0:
        try_action(
            "rewrite",
            "Differentiate the sampled page",
            f"Rewrite headings and proof blocks on {u0} so it cannot match sibling URLs verbatim.",
            [u0],
            "Embeddings diverge enough to exit duplicate clusters on the next crawl.",
            ["content_uniqueness_score"],
        )

    if u0 and u2 and u2 != u0 and len(steps) < 5:
        try_action(
            "redirect",
            "Point secondary URL to canonical",
            f"Redirect {u2} to {u0} with 301 after merge is live in staging.",
            [u2, u0],
            "Backlinks and crawlers consolidate on one destination.",
            ["roadmap prior step"],
        )

    if gissues and len(steps) < 5:
        g = gissues[0]
        exu = []
        for ex in g.get("examples") or []:
            exu.extend(ex.get("pages") or [])
        exu = exu[:4] or urls[:2]
        if exu:
            any_p = any(url_requires_preservation(u, bc) for u in exu)
            if any_p:
                try_action(
                    "reposition",
                    f"Reposition {g.get('title', 'theme')} pages",
                    f"Reposition copy on {exu[0]} (and siblings) so each required URL states a unique angle.",
                    exu[:3],
                    "Required URLs stay live with clearer intent ownership.",
                    ["grouped_issues"],
                )
            else:
                try_action(
                    "consolidate",
                    f"Address {g.get('title', 'overlap group')}",
                    f"Consolidate overlapping sections on {exu[0]} that repeat the same story as sibling URLs.",
                    exu[:3],
                    "One owned narrative per theme where URLs are not business-protected.",
                    ["grouped_issues"],
                )

    seed = (urls[0] if urls else None) or "https://127.0.0.1/"
    pad_specs = [
        (
            "split",
            "Separate intents on the first ranked URL",
            f"Split opening blocks on {seed} so product and guide intents do not share the same lead sentence.",
            [seed],
            "Distinct embeddings between intents on the next crawl.",
            ["overlap_rate"],
        ),
        (
            "merge",
            "Collapse duplicate headings on that URL",
            f"Merge repeated H2 sections on {seed} into one scannable outline.",
            [seed],
            "One heading hierarchy per page.",
            ["avg_cluster_similarity"],
        ),
        (
            "rewrite",
            "Differentiate proof and CTA lines",
            f"Rewrite testimonial and CTA lines on {seed} so they cannot match sibling routes verbatim.",
            [seed],
            "Copy diverges in embeddings versus competing URLs.",
            ["content_uniqueness_score"],
        ),
    ]
    for spec in pad_specs:
        if len(steps) >= 3:
            break
        try_action(*spec)

    out = steps[:5]
    for i, s in enumerate(out, start=1):
        s["step"] = i
    return {"roadmap": out}
