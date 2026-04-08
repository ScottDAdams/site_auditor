import json
import os
import re

from openai import OpenAI

from app.analyzer import REMEDIATION_DECISION_TYPES
from app.business_context import (
    default_allowed_actions,
    effective_allowed_actions,
    is_cross_domain,
    roadmap_step_allowed,
    url_requires_preservation,
)
from app.utils import canonicalize_url

VALID_PROBLEM_TYPES = frozenset({"acceptable", "competitive", "technical", "strategic"})


def safe_pair(a: str, b: str) -> bool:
    """True if two URLs are different resources after canonicalization (safe for merge/redirect copy)."""
    return bool(
        a and b and canonicalize_url(str(a)) != canonicalize_url(str(b))
    )


def _technical_fix_canonical_set(payload: dict) -> set[str]:
    raw = payload.get("technical_fix_urls")
    if not isinstance(raw, list):
        return set()
    return {canonicalize_url(str(u)) for u in raw if u}


def _url_allowed_for_strategic(u: str, payload: dict) -> bool:
    if not u:
        return False
    return canonicalize_url(str(u)) not in _technical_fix_canonical_set(payload)


def _dedupe_steps_by_targets(steps: list) -> list:
    seen = set()
    deduped = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        urls = tuple(
            sorted(
                canonicalize_url(str(u))
                for u in (step.get("target_urls") or [])
                if u
            )
        )
        if urls in seen:
            continue
        seen.add(urls)
        deduped.append(step)
    return deduped


def _no_duplicate_targets_across_steps(steps: list) -> bool:
    seen = set()
    for step in steps:
        if not isinstance(step, dict):
            continue
        for url in step.get("target_urls") or []:
            cu = canonicalize_url(str(url))
            if not cu:
                continue
            if cu in seen:
                return False
            seen.add(cu)
    return True


def _collapse_to_single_best_step(steps: list) -> list:
    for s in steps:
        if not isinstance(s, dict):
            continue
        tu = s.get("target_urls") or []
        if len(tu) >= 2 and safe_pair(str(tu[0]), str(tu[1])):
            return [{**s, "step": 1}]
    if steps and isinstance(steps[0], dict):
        return [{**steps[0], "step": 1}]
    return []


def finalize_roadmap(roadmap_obj: dict | None) -> dict:
    """Dedupe steps by canonical target multiset; collapse if any URL is targeted in more than one step."""
    if not roadmap_obj or not isinstance(roadmap_obj, dict):
        return roadmap_obj or {"roadmap": []}
    steps = [s for s in (roadmap_obj.get("roadmap") or []) if isinstance(s, dict)]
    steps = _dedupe_steps_by_targets(steps)
    if not _no_duplicate_targets_across_steps(steps):
        steps = _collapse_to_single_best_step(steps)
    for i, s in enumerate(steps, start=1):
        s["step"] = i
    return {**roadmap_obj, "roadmap": steps}

BANNED_VERBS_RE = re.compile(
    r"\b(clarify|improve|optimi[sz]e|enhance|refine|strengthen|align)\b",
    re.I,
)
# Vague copy instructions (execution steps must state concrete edits).
PAGE_CHANGE_VAGUE_RE = re.compile(
    r"\b(clarify|improve|optimi[sz]e|enhance|refine|strengthen|align)\b",
    re.I,
)
PAGE_CHANGE_TYPES = frozenset(
    {
        "add_section",
        "remove_section",
        "rewrite_section",
        "add_comparison",
        "change_heading",
        "adjust_cta",
    }
)
MIN_INSTRUCTION_LEN = 24
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
        if c.get("decision_type") in ("ignore", "none"):
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
        if c.get("decision_type") not in ("ignore", "none")
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
FORBIDDEN WORDS (any occurrence invalidates output): clarify, improve, optimize, enhance, refine, strengthen, align.
Use concrete operations: merge, delete, consolidate, redirect, split, rewrite, differentiate, reposition, none (only where allowed by business_context.allowed_actions). Use "none" only when no structural content action is appropriate (e.g. technical-only issues already routed elsewhere).

NARRATIVE SPINE (no overlapping blurbs — each field has one job):
- core_problem = mechanism + which URLs cluster (why the signal exists).
- why_it_matters = business consequence (stake), not a repeat of core_problem.
- primary_action = single decisive move (strategy-level).
- execution_example = one concrete illustration (who changes what on which URL pattern).

PROSE STYLE (all narrative fields: verdict, primary_issue, core_problem, why_it_matters, primary_action, execution_example, recommendation, business_impact, inaction_risk, metrics_explained.implication, roadmap title/description/expected_outcome, supporting_evidence.issue):
- Each sentence: at most 22 words; aim for about 18.
- One main idea per sentence; avoid comma splices and stacked "which/that/because" clauses.
- Do not use filler phrases: "which can lead to", "indicating that", "this suggests", "it is important to note", "in order to".

REPORT LAYERING (downstream HTML shows core_problem once in the executive block):
- supporting_evidence[].issue and metrics_explained[].implication = metric/URL proof only. Never paraphrase or restate core_problem or verdict there.
- Roadmap title/description/outcome = imperative actions and verifiable results. Do not restate the site diagnosis or reopen root-cause analysis.

NARRATIVE ROLES (no duplicated phrasing across fields):
- verdict = the decision/stance only (what the business should treat as true for this crawl).
- primary_issue + core_problem = one story: primary_issue is the single canonical issue line; core_problem expands WHY (mechanism, which URLs cluster together)—do NOT restate the verdict wording.
- supporting_evidence[].issue = proof only: observable facts (URLs, similarity/overlap numbers, cluster labels). Do NOT paraphrase the verdict or primary_issue/core_problem.

When describing duplicate/overlap mechanics, do NOT lean on vague phrases like "high similarity score". Say that affected pages read as indistinguishable in purpose and are competing for the same user decision (tie to specific URLs or cluster dominant_url).

For roadmap steps with action_type "differentiate" or "reposition", each step MUST include page_changes: at least 2 objects, each with url (full https URL from payload), change_type (one of: add_section, remove_section, rewrite_section, add_comparison, change_heading, adjust_cta), and instruction (specific edit — what to add/remove/rewrite; MUST NOT use: clarify, improve, optimize, enhance, refine, strengthen, align).
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
- state the decision/stance only—do not re-explain root cause (that belongs in core_problem after merge)
- NOT use the words: significant, various, multiple
- If payload clusters show duplication_class competitive OR decision_type differentiate/review, problem_type MUST be strategic and the verdict MUST NOT claim that technical URL duplication alone dominates the issue.

primary_issue MUST:
- be exactly one sentence: the single canonical issue for this audit (no bullet points)

core_problem MUST:
- explain WHY that issue exists (mechanism: embeddings, overlap, which URLs)—without repeating the verdict sentence or copying primary_issue verbatim

why_it_matters MUST:
- state business stakes only (revenue, trust, conversion clarity)—not a repeat of core_problem or primary_action.

primary_action MUST:
- one decisive strategic move using verbs from: merge, delete, consolidate, redirect, split, rewrite, differentiate, reposition (respect business_context.allowed_actions and protected/core_product rules)
- cite at least one real https URL from the payload

execution_example MUST:
- one concrete example of what to change (role + surface + URL pattern), not a second recommendation.

The recommendation field (legacy mirror) MUST equal primary_action verbatim.

The business_impact field (legacy mirror) MUST equal why_it_matters verbatim.

Each metrics_explained row MUST give value + implication in plain business terms. For similarity, describe pages as indistinguishable in purpose and competing for the same user decision—not "high similarity score" boilerplate.

supporting_evidence[].issue MUST describe observable overlap in copy, intent, or product decision in plain language; you may cite a metric as backup but do not lead with "cluster similarity 0.896" style jargon alone.

The "clusters" array in this payload contains ONLY remediation clusters (distinct canonical resources: decision_type differentiate or review; legacy strategic may appear). Clusters include page_type, intent, decision_stage, duplication_class—use them. Ignore/technical URL-alias/none/acceptable clusters are excluded.

Duplication is not automatically bad. Classify the audit-level problem using payload clusters and business_context:
- acceptable: overlap is appropriate; little or no remediation
- competitive: pages fight for the same user decision; differentiation or repositioning
- technical: URL/canonical/slash/host duplication dominates
- strategic: structure or governance change beyond page-level copy

DATA:
{data}

Return JSON with EXACTLY these keys:
{{
  "verdict": "",
  "primary_issue": "",
  "core_problem": "",
  "why_it_matters": "",
  "primary_action": "",
  "execution_example": "",
  "recommendation": "",
  "business_impact": "",
  "inaction_risk": "",
  "problem_type": "",
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

primary_issue: one sentence; this becomes the single headline issue (merged into core_problem downstream).
recommendation and business_impact: must duplicate primary_action and why_it_matters exactly (same strings).
problem_type: exactly one of: acceptable | competitive | technical | strategic. If any cluster has duplication_class competitive OR decision_type differentiate or review, problem_type MUST be strategic—never strategic + a verdict that says technical duplication dominates the crawl.
primary_clusters: short structural labels (dominant_url + similarity)—inventory only, not a second narrative.
supporting_evidence: at least 2 items; issue text states what overlaps in the real page experience (copy, offer, decision), not raw embedding scores alone.
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
- title: short imperative phrase suitable after "Step N — " (e.g. "Differentiate these pages"). No ALL CAPS. No action_type token pasted into the title.
- description: concrete actions on named URLs only. Do not restate why the site has duplication; follow PROSE STYLE (max 22 words per sentence).
- target_urls[0] and target_urls[1] MUST NOT canonicalize to the same URL when both are present (distinct destinations only)
- obey business_context.allowed_actions (only use action types set to true)
- NEVER use delete on protected_paths or core_product URLs; NEVER merge/redirect across regions when separate_regions is true
- include target_urls with at least one real https URL from the payload
- be atomic and testable (verifiable in staging)
- avoid banned verbs in title and description: improve, optimize, enhance, refine, strengthen, align

DIFFERENTIATE and REPOSITION steps — REQUIRED shape (both action types):
- MUST include "page_changes": an array with AT LEAST 2 items.
- Each item: {{ "url": "<https URL from payload>", "change_type": "<one allowed value>", "instruction": "<specific edit>" }}
- Allowed change_type values ONLY: add_section, remove_section, rewrite_section, add_comparison, change_heading, adjust_cta
- Each instruction MUST describe WHAT to change on the page (add/remove/rewrite which block, what new copy structure, etc.)
- Instructions MUST NOT contain: clarify, improve, optimize, enhance, refine, strengthen, align (or vague phrases like "clarify positioning between pages")

GOOD instruction example: "Add a section comparing comprehensive vs annual multi-trip with explicit use cases and a decision table."
BAD instruction example: "Clarify positioning between pages."

Other action types (merge, redirect, rewrite, etc.) MAY omit page_changes or use an empty array [].

DATA:
{data}

Return JSON:
{{
  "roadmap": [
    {{
      "step": 1,
      "action_type": "differentiate",
      "title": "",
      "description": "",
      "target_urls": [],
      "page_changes": [
        {{
          "url": "https://example.com/page-a",
          "change_type": "add_comparison",
          "instruction": "Add a section comparing product tiers with explicit eligibility rules and pricing rows."
        }},
        {{
          "url": "https://example.com/page-b",
          "change_type": "rewrite_section",
          "instruction": "Rewrite the hero body paragraph to target emergency-only buyers; remove shared sentences duplicated from page-a."
        }}
      ],
      "expected_outcome": "",
      "evidence_refs": []
    }},
    {{
      "step": 2,
      "action_type": "merge",
      "title": "",
      "description": "",
      "target_urls": [],
      "page_changes": [],
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


def _execution_example_valid(text: str) -> bool:
    if not text or not isinstance(text, str) or len(text.strip()) < 16:
        return False
    if BANNED_VERBS_RE.search(text):
        return False
    return True


def _forbidden_language(*texts: str) -> bool:
    """True if any segment contains banned vocabulary."""
    for t in texts:
        if t and BANNED_VERBS_RE.search(str(t)):
            return True
    return False


def validate_ai_output(ai_output) -> bool:
    if not isinstance(ai_output, dict):
        return False
    required = (
        "verdict",
        "core_problem",
        "why_it_matters",
        "primary_action",
        "execution_example",
        "recommendation",
        "business_impact",
        "inaction_risk",
        "problem_type",
        "metrics_explained",
        "primary_clusters",
        "supporting_evidence",
    )
    if any(k not in ai_output for k in required):
        return False
    if ai_output.get("problem_type") not in VALID_PROBLEM_TYPES:
        return False
    if not _verdict_valid(ai_output.get("verdict", "")):
        return False
    if not _recommendation_valid(ai_output.get("primary_action", "")):
        return False
    if not _recommendation_valid(ai_output.get("recommendation", "")):
        return False
    if not _execution_example_valid(ai_output.get("execution_example", "")):
        return False
    if _forbidden_language(
        ai_output.get("verdict", ""),
        ai_output.get("core_problem", ""),
        ai_output.get("why_it_matters", ""),
        ai_output.get("primary_action", ""),
        ai_output.get("execution_example", ""),
        ai_output.get("business_impact", ""),
        ai_output.get("inaction_risk", ""),
    ):
        return False
    me = ai_output.get("metrics_explained")
    if not isinstance(me, list) or len(me) < 1:
        return False
    for row in me:
        if not isinstance(row, dict):
            return False
        if not (row.get("metric") and row.get("value") and row.get("implication")):
            return False
        if _forbidden_language(str(row.get("implication", ""))):
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
        if _forbidden_language(str(item.get("issue", ""))):
            return False
        mrefs = item.get("metric_refs")
        if not isinstance(mrefs, list):
            return False
    return True


def _page_changes_ok_for_step(item: dict, action_type: str) -> bool:
    if action_type not in ("differentiate", "reposition"):
        pc = item.get("page_changes")
        if pc is not None and not isinstance(pc, list):
            return False
        return True
    pc = item.get("page_changes")
    if not isinstance(pc, list) or len(pc) < 2:
        return False
    desc = str(item.get("description", ""))
    if PAGE_CHANGE_VAGUE_RE.search(desc):
        return False
    for ch in pc:
        if not isinstance(ch, dict):
            return False
        url = ch.get("url")
        ct = (ch.get("change_type") or "").strip()
        inst = ch.get("instruction")
        if not url or not isinstance(url, str) or not url.strip():
            return False
        if ct not in PAGE_CHANGE_TYPES:
            return False
        if not isinstance(inst, str) or len(inst.strip()) < MIN_INSTRUCTION_LEN:
            return False
        if PAGE_CHANGE_VAGUE_RE.search(inst) or BANNED_VERBS_RE.search(inst):
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
        if item.get("page_changes") is not None and not isinstance(item.get("page_changes"), list):
            return False
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
    if not _page_changes_ok_for_step(item, at):
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
            if canonicalize_url(str(turls[0])) == canonicalize_url(str(turls[1])):
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
        if c.get("decision_type") in REMEDIATION_DECISION_TYPES
    ]


def estimate_visibility_loss(overlap_rate: float) -> str:
    if overlap_rate >= 0.5:
        return "30–50%"
    elif overlap_rate >= 0.4:
        return "20–35%"
    elif overlap_rate >= 0.3:
        return "10–25%"
    return "<10%"


def calculate_confidence(cluster_count: int, avg_similarity: float) -> str:
    if cluster_count >= 5 and avg_similarity > 0.9:
        return "High"
    elif cluster_count >= 3:
        return "Medium"
    return "Low"


def detect_secondary_issue(payload: dict) -> str:
    """Heuristic second narrative thread for the decision summary (distinct from core_problem)."""
    summary = payload.get("summary") or {}
    m = payload.get("metrics") or {}
    try:
        avg_sim = float(m.get("avg_cluster_similarity", 0))
    except (TypeError, ValueError):
        avg_sim = 0.0
    tech_n = len(payload.get("technical_fix_urls") or [])
    high_issues = int(summary.get("high_issues", 0))

    if tech_n >= 3:
        return (
            "Many technical URL variants split crawl signals. Normalize routes before content work."
        )
    if avg_sim >= 0.92:
        return (
            "Cluster embeddings are very tight. Differentiate copy and layout on required URLs."
        )
    if high_issues >= 2:
        return (
            "Several severe duplication items compete for priority. Sequence by traffic and revenue."
        )
    try:
        uniq = float(m.get("content_uniqueness_score", 1) or 1)
    except (TypeError, ValueError):
        uniq = 1.0
    if uniq < 0.35:
        return (
            "Content-uniqueness is low. Give each URL one primary intent before adding pages."
        )
    return (
        "Tighten intent boundaries so each URL owns one primary conversion path."
    )


def enforce_single_problem(insight: dict) -> dict:
    """Collapse primary_issue + core_problem into one headline field for the report."""
    out = dict(insight)
    out["core_problem"] = (out.get("primary_issue") or out.get("core_problem") or "").strip()
    out.pop("primary_issue", None)
    return out


def apply_narrative_aliases(insight: dict) -> dict:
    """Unify collapsed narrative keys with legacy recommendation/business_impact fields."""
    o = dict(insight)
    wi = (o.get("why_it_matters") or o.get("business_impact") or "").strip()
    pa = (o.get("primary_action") or o.get("recommendation") or "").strip()
    ex = (o.get("execution_example") or "").strip()
    o["why_it_matters"] = wi
    o["business_impact"] = wi
    o["primary_action"] = pa
    o["recommendation"] = pa
    o["execution_example"] = ex
    return o


def payload_requires_strategic_problem_type(payload: dict) -> bool:
    """Competitive or remediation clusters → audit must not read as technical-only."""
    for c in _strategic_cluster_rows(payload):
        if not isinstance(c, dict):
            continue
        if c.get("duplication_class") == "competitive":
            return True
        if c.get("decision_type") in ("differentiate", "review"):
            return True
    return False


def reconcile_problem_type_and_verdict(insights: dict, payload: dict) -> dict:
    """
    Align problem_type and verdict with cluster signals: never strategic assessment +
    'technical duplication dominates' messaging when remediation clusters exist.
    """
    out = dict(insights)
    needs_strategic = payload_requires_strategic_problem_type(payload)
    v = (out.get("verdict") or "").strip()
    vl = v.lower()
    bad_tech = "technical duplication dominates" in vl

    if needs_strategic:
        out["problem_type"] = "strategic"
        if bad_tech or "no strategic content conflicts detected after normalization" in vl:
            anchor = ""
            for c in _strategic_cluster_rows(payload):
                if c.get("dominant_url"):
                    anchor = str(c["dominant_url"])
                    break
            if not anchor:
                pu = payload.get("page_urls") or []
                anchor = str(pu[0]) if pu else "a listed URL"
            out["verdict"] = (
                f"Overlapping pages around {anchor} need distinct positioning; "
                f"resolve copy and intent first—canonical fixes alone will not fix that competition."
            )
    elif not _strategic_cluster_rows(payload) and (payload.get("technical_fix_urls") or []):
        out["problem_type"] = "technical"
    return out


def enrich_insights_decision_layer(insights: dict | None, payload: dict) -> dict:
    """
    Post-process insights: visibility loss line on why_it_matters, model confidence,
    secondary issue, and reconciliation of problem_type vs crawl signals.
    """
    out = enforce_single_problem(dict(insights or {}))
    out = apply_narrative_aliases(out)
    m = payload.get("metrics") or {}
    try:
        overlap = float(m.get("overlap_rate", 0))
    except (TypeError, ValueError):
        overlap = 0.0
    loss = estimate_visibility_loss(overlap)
    loss_line = (
        f"About {loss} of organic visibility likely splits across competing pages. "
        "That blurs conversion paths and ranking focus."
    )
    wi = (out.get("why_it_matters") or "").strip()
    out["why_it_matters"] = f"{loss_line} {wi}".strip() if wi else loss_line
    out["business_impact"] = out["why_it_matters"]

    try:
        avg_sim = float(m.get("avg_cluster_similarity", 0))
    except (TypeError, ValueError):
        avg_sim = 0.0
    out["confidence"] = calculate_confidence(len(_strategic_cluster_rows(payload)), avg_sim)
    out["secondary_issue"] = detect_secondary_issue(payload)
    if overlap >= 0.45:
        out["impact_level"] = "High"
    elif overlap >= 0.28:
        out["impact_level"] = "Moderate"
    else:
        out["impact_level"] = "Low"
    return reconcile_problem_type_and_verdict(out, payload)


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
    blocked = _technical_fix_canonical_set(payload)
    if blocked:
        out = [u for u in out if canonicalize_url(str(u)) not in blocked]
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
    pu = [
        u
        for u in (payload.get("page_urls") or [])[:8]
        if _url_allowed_for_strategic(str(u), payload)
    ][:2]
    ev_urls = pu if len(pu) >= 2 else (pu + ["https://127.0.0.1/"])[:2]
    sample_u = ev_urls[0] if ev_urls else "https://127.0.0.1/"
    rec = (
        f"Redirect duplicate host and slash variants to {sample_u} using 301s and rel=canonical."
    )
    why = (
        "Technical URL duplication can dilute crawl budget and split signals until one canonical URL is chosen."
    )
    ex = (
        f"Example: pick {sample_u} as the single indexable URL; 301 every alias host, path, "
        f"and scheme variant to it and set rel=canonical on each duplicate."
    )
    return {
        "verdict": (
            f"No strategic content conflicts detected after normalization; "
            f"crawl reference URL {sample_u}."
        ),
        "core_problem": (
            "Duplicate signals are caused by technical URL variants, not structural content issues."
        ),
        "why_it_matters": why,
        "primary_action": rec,
        "execution_example": ex,
        "recommendation": rec,
        "business_impact": why,
        "inaction_risk": (
            "Without canonical normalization, equivalent URLs may continue to compete for the same intent."
        ),
        "problem_type": "technical",
        "metrics_explained": metrics_explained,
        "primary_clusters": [
            "No strategic duplicate clusters after normalization—address variants under Technical SEO fixes."
        ],
        "supporting_evidence": [
            {
                "urls": ev_urls[:1] or ["https://127.0.0.1/"],
                "issue": (
                    f"The crawl shows URL-alias overlap around {ev_urls[0] if ev_urls else 'n/a'} "
                    f"without a separate content cluster—fix normalization before scaling pages."
                ),
                "metric_refs": [f"overlap_rate {m.get('overlap_rate', 0)}"],
            },
            {
                "urls": ev_urls if len(ev_urls) >= 2 else ev_urls + ["https://127.0.0.1/"],
                "issue": (
                    f"Second sample pair shares crawl overlap signals; metrics file as "
                    f"avg_cluster_similarity {m.get('avg_cluster_similarity', 0)} for audit context."
                ),
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
                "When this approaches 1.0, paired pages read as indistinguishable in purpose "
                "and compete for the same user decision in search and on-site journeys."
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

    clusters_strategic = _strategic_cluster_rows(payload)

    urls_pool = _first_urls_from_payload(payload, 12)
    candidate_pairs = _candidate_url_pairs(urls_pool, 12)
    safe_pairs = [(a, b) for (a, b) in candidate_pairs if safe_pair(a, b)]

    print("STRATEGIC URLS:", urls_pool)
    print("SAFE PAIRS:", safe_pairs)

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
                    f"These URLs present overlapping coverage copy and the same policy decision path; "
                    f"embedding similarity is high (see metrics) but the issue is shared messaging, not the number alone."
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
                    f"Pages {a} and {b} target the same buyer job with parallel proof blocks; "
                    f"overlap_rate {m.get('overlap_rate', 0)} shows how much of the crawl sits in tied clusters."
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
        why = (
            "Splitting authority and trust between parallel regional URLs weakens each market’s relevance."
        )
        ex = (
            f"Example: differentiate policy positioning between AU and NZ pages—add region-only "
            f"coverage limits on {u0} and distinct proof on {u1}; do not reuse the same hero block."
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
        why = (
            "Mandatory URLs that overlap force buyers to compare duplicate stories and dilute conversion paths."
        )
        ex = (
            f"Example: on each required URL, replace shared bullet lists with one proof section unique "
            f"to that route; keep both URLs live."
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
        why = (
            "Split traffic and backlinks across tied URLs depresses conversion clarity and "
            "regional relevance per domain."
        )
        ex = (
            f"Example: fold redundant sections from {u1} into {u0}, then 301 {u1} once one page "
            f"owns the story end-to-end."
        )

    return {
        "verdict": verdict,
        "core_problem": core_problem,
        "why_it_matters": why,
        "primary_action": rec,
        "execution_example": ex,
        "recommendation": rec,
        "business_impact": why,
        "inaction_risk": (
            "Publishing more pages without consolidating duplicates repeats the same "
            "cannibalization pattern."
        ),
        "problem_type": "strategic",
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
        "page_changes": [],
        "expected_outcome": "Improved crawl consistency after canonical normalization.",
        "evidence_refs": [],
    }


def _fallback_page_changes_two_urls(u0: str, u1: str) -> list:
    return [
        {
            "url": u0,
            "change_type": "change_heading",
            "instruction": (
                f"Rewrite the H1 and hero subheading to name one buyer problem this URL solves only; "
                f"delete sentences duplicated verbatim from {u1}."
            ),
        },
        {
            "url": u1,
            "change_type": "rewrite_section",
            "instruction": (
                f"Rewrite the first body section after the hero with examples unique to this URL; "
                f"remove bullet lists that mirror the structure on {u0}."
            ),
        },
    ]


def _fallback_page_changes_regional(u0: str, u1: str) -> list:
    return [
        {
            "url": u0,
            "change_type": "add_section",
            "instruction": (
                f"Add a region-specific block: local contact details, currency, and coverage limits "
                f"that do not appear on {u1}."
            ),
        },
        {
            "url": u1,
            "change_type": "add_section",
            "instruction": (
                f"Add a region-specific block: local contact details, currency, and coverage limits "
                f"that do not appear on {u0}."
            ),
        },
    ]


def _fallback_page_changes_reposition_one(u: str, peer: str | None = None) -> list:
    peer_bit = f" Remove mirrored copy from {peer}." if peer else ""
    return [
        {
            "url": u,
            "change_type": "change_heading",
            "instruction": (
                f"Replace the hero H1 with one primary buyer intent for this URL only; "
                f"drop generic claims repeated across sibling pages.{peer_bit}"
            ),
        },
        {
            "url": u,
            "change_type": "adjust_cta",
            "instruction": (
                "Replace the primary CTA label and supporting line with an action tied to this page’s "
                "single offer; remove duplicate CTA copy reused from overlapping URLs."
            ),
        },
    ]


def build_fallback_roadmap(payload: dict) -> dict:
    if not _strategic_cluster_rows(payload):
        return finalize_roadmap({"roadmap": [_default_no_consolidation_roadmap_step()]})

    bc = payload.get("business_context") or {}
    allowed = effective_allowed_actions(bc)
    mc = bc.get("market_context") or {}

    urls = _first_urls_from_payload(payload, 12)
    if not urls:
        return finalize_roadmap({"roadmap": [_default_no_consolidation_roadmap_step()]})

    candidate_pairs = _candidate_url_pairs(urls, 12)
    safe_pairs = [(a, b) for (a, b) in candidate_pairs if safe_pair(a, b)]
    if not safe_pairs:
        return finalize_roadmap({"roadmap": [_default_no_consolidation_roadmap_step()]})

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
            if canonicalize_url(str(turls[0])) == canonicalize_url(str(turls[1])):
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
        page_changes: list | None = None,
    ) -> bool:
        if len(targets) >= 2:
            if canonicalize_url(str(targets[0])) == canonicalize_url(str(targets[1])):
                return False
        if not allowed.get(primary, False):
            return False
        pc = list(page_changes) if page_changes is not None else []
        body = {
            "action_type": primary,
            "title": title,
            "description": desc,
            "target_urls": targets,
            "page_changes": pc,
            "expected_outcome": outcome,
            "evidence_refs": refs,
        }
        if push(body):
            return True
        if primary == "differentiate" and allowed.get("reposition") and len(targets) >= 1:
            r1 = targets[1] if len(targets) > 1 else None
            if push(
                {
                    "action_type": "reposition",
                    "title": "Split buyer intents without merging URLs",
                    "description": (
                        f"Reassign proof blocks on {targets[0]} "
                        f"{f'and {targets[1]} ' if len(targets) > 1 else ''}"
                        f"so each page leads with a different scenario and CTA."
                    ),
                    "target_urls": targets[:4],
                    "page_changes": _fallback_page_changes_reposition_one(targets[0], r1),
                    "expected_outcome": "Distinct intent signals per URL without structural merge.",
                    "evidence_refs": refs,
                }
            ):
                return True
        if primary in ("merge", "consolidate", "redirect"):
            if allowed.get("differentiate") and len(targets) >= 2:
                ddesc = (
                    f"Split copy on {targets[0]} and {targets[1]}: each page keeps its route but "
                    f"carries unique H1, hero, and proof tied to one use case."
                )
                if push(
                    {
                        "action_type": "differentiate",
                        "title": "Separate required URLs with unique copy blocks",
                        "description": ddesc,
                        "target_urls": targets[:4],
                        "page_changes": _fallback_page_changes_two_urls(targets[0], targets[1]),
                        "expected_outcome": "Lower intent collision without removing business URLs.",
                        "evidence_refs": refs + ["business_context.protected_paths"],
                    }
                ):
                    return True
            if allowed.get("reposition"):
                u0, u1 = targets[0], targets[1] if len(targets) > 1 else targets[0]
                rdesc = (
                    f"Rework hero and proof on {u0} for its primary buyer; "
                    f"{'do the same on ' + u1 + ' with a different scenario.' if len(targets) > 1 else 'remove mirrored blocks from sibling URLs.'}"
                )
                if push(
                    {
                        "action_type": "reposition",
                        "title": "Rework hero and CTA per URL",
                        "description": rdesc,
                        "target_urls": targets[:4],
                        "page_changes": (
                            _fallback_page_changes_two_urls(u0, u1)
                            if len(targets) > 1 and safe_pair(u0, u1)
                            else _fallback_page_changes_reposition_one(u0, targets[1] if len(targets) > 1 else None)
                        ),
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
                page_changes=_fallback_page_changes_regional(u0, u1),
            )
        elif url_requires_preservation(u0, bc) or url_requires_preservation(u1, bc):
            try_action(
                "differentiate",
                "Separate required product narratives",
                f"Differentiate {u0} and {u1} so each required page states a distinct use case and CTA.",
                [u0, u1],
                "Core offerings remain live with less cannibalization.",
                ["business_context.page_roles", "protected_paths"],
                page_changes=_fallback_page_changes_two_urls(u0, u1),
            )
        else:
            try_action(
                "merge",
                "Collapse duplicate topic into one URL",
                f"Merge body copy from {u1} into {u0}; keep one H1 and one CTA path.",
                [u0, u1],
                "One ranking URL per intent; internal links stop splitting across twins.",
                ["cluster dominant_url", "avg_cluster_similarity"],
                page_changes=[],
            )
    elif urls:
        try_action(
            "rewrite",
            "Differentiate the sampled page",
            f"Rewrite headings and proof blocks on {urls[0]} so it cannot match sibling URLs verbatim.",
            [urls[0]],
            "Embeddings diverge enough to exit duplicate clusters on the next crawl.",
            ["content_uniqueness_score"],
            page_changes=[],
        )

    if u0 and u2 and safe_pair(u2, u0) and len(steps) < 5:
        try_action(
            "redirect",
            "Point secondary URL to canonical",
            f"Redirect {u2} to {u0} with 301 after merge is live in staging.",
            [u2, u0],
            "Backlinks and crawlers consolidate on one destination.",
            ["roadmap prior step"],
            page_changes=[],
        )

    if not steps:
        return finalize_roadmap({"roadmap": [_default_no_consolidation_roadmap_step()]})

    out = steps[:5]
    for i, s in enumerate(out, start=1):
        s["step"] = i
    return finalize_roadmap({"roadmap": out})
