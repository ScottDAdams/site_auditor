"""
Deterministic transformation_spec for AI narrative (Phase 4).

All remove/add/role decisions are computed here — the model does not invent them.
"""

from __future__ import annotations

from urllib.parse import urlparse

from app.analyzer import REMEDIATION_DECISION_TYPES
from app.business_context import is_cross_domain
from app.transformation_types import infer_transformation_type, keep_both_for_type


def _market_label_from_url(url: str) -> str:
    if not url:
        return "Regional"
    netloc = (urlparse(str(url)).netloc or "").lower()
    path = (urlparse(str(url)).path or "").lower()
    blob = f"{netloc}{path}"
    if ".co.nz" in blob or netloc.endswith(".nz"):
        return "New Zealand"
    if ".com.au" in blob or netloc.endswith(".au"):
        return "Australia"
    if ".co.uk" in blob or ".uk" in netloc:
        return "United Kingdom"
    if ".ca" in netloc or netloc.endswith(".ca"):
        return "Canada"
    return "Regional"


def _cluster_summary_line(strategic: list[dict], limit: int = 3) -> str:
    parts = []
    for i, r in enumerate(strategic[:limit], 1):
        dom = r.get("dominant_url") or "?"
        sim = r.get("similarity", "")
        dc = r.get("duplication_class") or ""
        dt = r.get("decision_type") or ""
        parts.append(
            f"cluster_{i}: decision_type={dt} duplication_class={dc} "
            f"dominant_url={dom} similarity={sim}"
        )
    return "; ".join(parts) if parts else "no_remediation_clusters"


def _sample_urls_for_spec(payload: dict) -> tuple[list[str], str]:
    rows = [c for c in (payload.get("clusters") or []) if isinstance(c, dict)]
    strategic = [r for r in rows if r.get("decision_type") in REMEDIATION_DECISION_TYPES]
    sample_urls: list[str] = []
    seen: set[str] = set()
    for r in strategic[:4]:
        if r.get("dominant_url"):
            s = str(r["dominant_url"]).strip()
            if s and s not in seen:
                seen.add(s)
                sample_urls.append(s)
        for u in (r.get("competing_urls") or [])[:3]:
            if u:
                s = str(u).strip()
                if s and s not in seen:
                    seen.add(s)
                    sample_urls.append(s)
    if not sample_urls:
        for u in (payload.get("technical_fix_urls") or [])[:4]:
            if u:
                s = str(u).strip()
                if s and s not in seen:
                    seen.add(s)
                    sample_urls.append(s)
    if not sample_urls:
        for u in (payload.get("page_urls") or [])[:2]:
            if u:
                s = str(u).strip()
                if s and s not in seen:
                    seen.add(s)
                    sample_urls.append(s)
    dominant = (payload.get("dominant_problem_type") or "acceptable").strip().lower()
    bc = payload.get("business_context") or {}
    mc = bc.get("market_context") or {}
    rel = "unknown"
    if len(sample_urls) >= 2 and mc.get("separate_regions") and is_cross_domain(
        sample_urls[0], sample_urls[1]
    ):
        rel = "cross_market"
    elif len(sample_urls) >= 2:
        rel = "intra_market"
    elif dominant == "acceptable":
        rel = "intra_market"
    return sample_urls, rel


def _count_cluster_urls(first: dict | None, sample_urls: list[str]) -> int:
    if not first:
        return max(len(sample_urls), 1)
    pages = first.get("pages") or []
    if pages:
        return max(len(pages), len(sample_urls), 1)
    return max(1 + len(first.get("competing_urls") or []), len(sample_urls), 1)


def build_transformation_spec(payload: dict) -> dict:
    """
    Build read-only transformation_spec before any LLM call.
    Uses dominant_problem_type, cluster rows, market_context, and URL pairing.
    """
    rows = [c for c in (payload.get("clusters") or []) if isinstance(c, dict)]
    strategic = [r for r in rows if r.get("decision_type") in REMEDIATION_DECISION_TYPES]
    dominant = (payload.get("dominant_problem_type") or "acceptable").strip().lower()
    sample_urls, relationship = _sample_urls_for_spec(payload)
    page_a_url = sample_urls[0] if sample_urls else ""
    page_b_url = sample_urls[1] if len(sample_urls) > 1 else ""

    first = strategic[0] if strategic else {}
    cluster_url_count = _count_cluster_urls(first, sample_urls)
    try:
        row_sim = float(first["similarity"]) if first and first.get("similarity") is not None else None
    except (TypeError, ValueError):
        row_sim = None
    transformation_type = infer_transformation_type(
        payload,
        dominant,
        relationship,
        cluster_url_count,
        row_similarity=row_sim,
    )
    keep_both = keep_both_for_type(transformation_type)

    ptype = (first.get("page_type") or "page").strip() or "page"
    intent = (first.get("intent") or "this topic").strip() or "this topic"
    stage = (first.get("decision_stage") or "").strip()

    remove_a: list[str] = []
    remove_b: list[str] = []
    add_a: list[str] = []
    add_b: list[str] = []
    role_a = ""
    role_b = ""

    if dominant == "acceptable":
        role_a = "Published URL stays live without structural merge in this crawl slice."
        role_b = "No competing peer requires consolidation in this crawl slice."
    elif dominant == "technical":
        role_a = "Single canonical URL holds indexable HTML for this topic."
        role_b = (
            "Alias hosts and paths send users and crawl signals to that canonical URL."
            if page_b_url
            else "No second indexable peer in this sample."
        )
        remove_a = ["Duplicate indexable paths that mirror the canonical HTML"]
        remove_b = ["Extra indexable routes that compete with the canonical URL"]
        add_a = ["One rel=canonical target and consolidated internal links"]
        add_b = ["301 or canonical directives so aliases collapse to the canonical URL"]
    elif dominant == "strategic":
        if not keep_both:
            role_a = "Single canonical page holds merged content for this topic."
            role_b = "Duplicate URL retires; traffic and signals route to the canonical page."
            remove_a = ["Redundant blocks mirrored on duplicate indexable URLs"]
            remove_b = ["Indexable duplicate body that repeats the canonical intent"]
            add_a = ["Unified page body with one clear H1 and consolidated proof"]
            add_b = ["301 redirect to canonical URL and updated internal links"]
        elif relationship == "cross_market" and page_a_url and page_b_url:
            ma = _market_label_from_url(page_a_url)
            mb = _market_label_from_url(page_b_url)
            role_a = f"{ma} market page: coverage, pricing, and claims for {ma} buyers."
            role_b = f"{mb} market page: coverage, pricing, and claims for {mb} buyers."
            remove_a = ["Shared generic messaging mirrored on the regional sibling site"]
            remove_b = ["Copy blocks reused from the other regional policy or product page"]
            add_a = [f"{ma}-specific proof, limits, and policy rows"]
            add_b = [f"{mb}-specific pricing rows and local customer proof"]
        else:
            role_a = f"Primary {ptype} path owning {intent} for buyers at this URL."
            role_b = (
                f"Secondary path that must not duplicate the primary {intent} story."
                if page_b_url
                else "No competing peer URL in this crawl scope."
            )
            remove_a = [
                f"Overlapping {intent} blocks that match the peer URL's job-to-be-done"
            ]
            remove_b = [
                f"Shared hero, FAQ, or pricing snippets that blur intent with URL A"
            ]
            if page_b_url:
                add_a = [f"Unique {ptype} modules scoped to URL A only"]
                add_b = [f"Distinct {ptype} proof and CTAs scoped to URL B only"]
            else:
                add_a = [f"Scoped {ptype} content that matches this URL's single role"]
                add_b = []

    return {
        "page_a_url": page_a_url or "",
        "page_b_url": page_b_url or "",
        "page_a_role": role_a,
        "page_b_role": role_b,
        "remove_from_a": remove_a,
        "remove_from_b": remove_b,
        "add_to_a": add_a,
        "add_to_b": add_b,
        "cluster_relationship": relationship,
        "cluster_summary": _cluster_summary_line(strategic),
        "dominant_problem_type": dominant,
        "page_type_signal": ptype,
        "intent_signal": intent,
        "decision_stage_signal": stage,
        "transformation_type": transformation_type,
        "keep_both": keep_both,
        "cluster_url_count": cluster_url_count,
    }


def render_core_problem(payload: dict, spec: dict) -> str:
    dominant = (spec.get("dominant_problem_type") or "acceptable").strip().lower()
    rel = spec.get("cluster_relationship") or "unknown"
    tt = (spec.get("transformation_type") or "").strip().lower()
    if dominant == "strategic" and tt in ("merge", "redirect", "consolidate"):
        return (
            "Near-duplicate pages should collapse to one canonical indexable answer per topic."
        )
    if dominant == "strategic" and tt == "isolate":
        return "High same-market similarity blurs distinct buyer jobs per URL."
    if dominant == "strategic" and rel == "cross_market":
        return (
            "Regional URLs target the same buyer decision without market-specific separation."
        )
    if dominant == "strategic":
        return "Overlapping pages share intent signals without distinct roles per URL."
    if dominant == "technical":
        return "Duplicate routes split crawl signals for the same topic."
    return "Crawl overlap sits inside acceptable bounds for sampled URLs."


def _cross_market_restriction_clause(url: str) -> str:
    m = _market_label_from_url(url)
    if m == "New Zealand":
        return (
            f"Restrict {url} to New Zealand-specific coverage and remove shared messaging"
        )
    if m == "Australia":
        return f"Restrict {url} to Australian pricing and proof"
    return f"Restrict {url} to {m}-specific proof and remove shared messaging"


def render_primary_action(spec: dict) -> str:
    dominant = (spec.get("dominant_problem_type") or "acceptable").strip().lower()
    u1, u2 = spec.get("page_a_url") or "", spec.get("page_b_url") or ""
    tt = (spec.get("transformation_type") or "").strip().lower()
    ncc = int(spec.get("cluster_url_count") or 0) or 2
    kb = spec.get("keep_both", True)

    if dominant == "acceptable":
        anchor = u1 or u2 or "sampled URLs"
        return f"Prescribe none: no merge, redirect, or consolidate on {anchor}."

    if dominant == "technical":
        if u1 and u2:
            return (
                f"301 alias routes to {u1}; set rel=canonical on duplicate paths including {u2}."
            )
        return f"301 duplicate paths to {u1}; set rel=canonical on non-canonical URLs."

    if dominant == "strategic" and not kb and u1 and not u2:
        return f"Consolidate duplicate URLs into one canonical destination at {u1}."

    if dominant == "strategic" and not kb and u1 and u2:
        if tt == "merge":
            return (
                f"Merge overlapping content from {u2} into {u1}; remove duplicate indexable URL "
                f"and consolidate internal links."
            )
        if tt == "redirect":
            return (
                f"301 {u2} to {u1}; remove duplicate indexable surface and route signals to the canonical URL."
            )
        if tt == "consolidate":
            if ncc > 2:
                return (
                    f"Consolidate {ncc} competing URLs into one canonical destination at {u1}; "
                    f"301 or rel=canonical all alternates including {u2}."
                )
            return (
                f"Consolidate competing URLs into {u1}; 301 or rel=canonical alternates including {u2}."
            )

    if dominant == "strategic" and u1 and u2:
        if tt == "isolate":
            return (
                f"Isolate intent per URL: remove overlapping blocks on {u1} and {u2} "
                f"so each page owns a distinct buyer job."
            )
        if spec.get("cluster_relationship") == "cross_market":
            c1 = _cross_market_restriction_clause(u1)
            c2 = _cross_market_restriction_clause(u2)
            c2_lower = c2[0].lower() + c2[1:] if c2 else c2
            return f"{c1}; {c2_lower}."
        return (
            f"Restrict {u1} to its primary buyer role; remove overlapping blocks; "
            f"restrict {u2} to its secondary role; remove shared snippets."
        )

    if u1:
        return f"Restrict {u1} to its assigned role; remove overlapping blocks."
    return "Assign distinct roles per URL and remove overlapping blocks."


def render_why_it_matters(payload: dict, spec: dict) -> str:
    m = payload.get("metrics") or {}
    orate = m.get("overlap_rate")
    sim = m.get("avg_cluster_similarity")
    cu = m.get("content_uniqueness_score")
    parts = []
    if orate is not None:
        parts.append(f"overlap_rate {orate}")
    if sim is not None:
        parts.append(f"avg_cluster_similarity {sim}")
    if cu is not None and len(parts) < 2:
        parts.append(f"content_uniqueness_score {cu}")
    joined = " and ".join(parts) if parts else "Cluster metrics"
    return (
        f"{joined} split ranking signals across tied URLs and blur conversion paths."
    )


def render_execution_example(spec: dict) -> str:
    u1, u2 = spec.get("page_a_url") or "", spec.get("page_b_url") or ""
    ra = spec.get("remove_from_a") or []
    rb = spec.get("remove_from_b") or []
    aa = spec.get("add_to_a") or []
    ab = spec.get("add_to_b") or []

    def block(url: str, rlist: list[str], alist: list[str]) -> str:
        rm = rlist[0] if rlist else "overlapping shared messaging"
        ad = alist[0] if alist else "content matched to this URL role"
        return f"On {url}:\n- remove: {rm}\n- add: {ad}"

    if u1 and u2:
        return f"{block(u1, ra, aa)}\n\n{block(u2, rb, ab)}"
    if u1:
        return block(u1, ra, aa)
    return "On sampled URLs:\n- remove: duplicate signals\n- add: single canonical answer per intent"


def render_insights_from_spec(payload: dict, dominant: str, spec: dict) -> dict:
    """Full narrative fields from spec + metrics (no LLM)."""
    core_problem = render_core_problem(payload, spec)
    primary_action = render_primary_action(spec)
    why_it_matters = render_why_it_matters(payload, spec)
    execution_example = render_execution_example(spec)
    return {
        "core_problem": core_problem,
        "page_a_role": spec["page_a_role"],
        "page_b_role": spec["page_b_role"],
        "primary_action": primary_action,
        "why_it_matters": why_it_matters,
        "execution_example": execution_example,
        "transformation_spec": spec,
        "insights_rendered_from_spec": True,
    }
