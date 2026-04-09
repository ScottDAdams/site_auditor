"""
Phase 10 — Narrative consolidation: cluster related signals, one insight per problem shape.

Reduces repeated per-cluster cards into a small set of strategic summaries aligned with
primary_strategy (no conflicting merge vs differentiate language).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.analyzer import REMEDIATION_DECISION_TYPES, classify_page
from app.business_context import is_cross_domain
from app.evidence_engine import build_decision_rationale, build_evidence_pack
from app.priority_scoring import issue_priority_score
from app.transformation_types import infer_transformation_type_for_cluster_row


CLUSTER_KEYS = frozenset(
    {
        "overlap_same_intent",
        "thin_content_cluster",
        "internal_linking_gap",
        "structural_conflict",
    }
)


def _strategic_rows(payload: dict) -> list[dict]:
    rows = [c for c in (payload.get("clusters") or []) if isinstance(c, dict)]
    return [r for r in rows if r.get("decision_type") in REMEDIATION_DECISION_TYPES]


def _all_cluster_rows(payload: dict) -> list[dict]:
    return [c for c in (payload.get("clusters") or []) if isinstance(c, dict)]


def _urls_from_row(row: dict, cap: int = 12) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for u in (row.get("pages") or []):
        s = str(u).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
        if len(out) >= cap:
            break
    if not out and row.get("dominant_url"):
        out.append(str(row["dominant_url"]).strip())
    for u in (row.get("competing_urls") or []):
        s = str(u).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
        if len(out) >= cap:
            break
    return out


def cluster_findings(findings: list[dict] | None, payload: dict | None = None) -> list[dict[str, Any]]:
    """
    Group related signals into narrative clusters.

    `findings` is optional audit findings (e.g. topic_overlap rows). When absent,
    clustering uses payload clusters + pages only.

    Returns cluster dicts with: cluster_key, members (rows or synthetic), urls, meta.
    """
    payload = payload or {}
    findings = findings or []
    metrics = payload.get("metrics") or {}
    out: list[dict[str, Any]] = []

    strategic = _strategic_rows(payload)
    sample_urls: list[str] = []
    seen_u: set[str] = set()
    for r in strategic[:6]:
        for u in _urls_from_row(r, 8):
            if u not in seen_u:
                seen_u.add(u)
                sample_urls.append(u)

    # --- 1) Overlap / same intent: all remediation rows as one narrative group
    if strategic:
        all_urls: list[str] = []
        seen2: set[str] = set()
        for r in strategic:
            for u in _urls_from_row(r, 10):
                if u not in seen2:
                    seen2.add(u)
                    all_urls.append(u)
        intent_keys: set[str] = set()
        for r in strategic:
            ik = str(r.get("intent") or "mixed")
            intent_keys.add(ik)
        out.append(
            {
                "cluster_key": "overlap_same_intent",
                "members": strategic,
                "urls": all_urls[:10],
                "meta": {
                    "remediation_cluster_count": len(strategic),
                    "intent_labels": sorted(intent_keys),
                    "cross_market_hint": _cluster_cross_market(strategic, payload),
                },
            }
        )

    # --- 2) Structural / technical conflicts
    tech_rows = [
        r
        for r in _all_cluster_rows(payload)
        if r.get("decision_type") == "technical_fix"
    ]
    if tech_rows:
        turls: list[str] = []
        seen3: set[str] = set()
        for r in tech_rows:
            for u in _urls_from_row(r, 6):
                if u not in seen3:
                    seen3.add(u)
                    turls.append(u)
        out.append(
            {
                "cluster_key": "structural_conflict",
                "members": tech_rows,
                "urls": turls[:8],
                "meta": {"technical_cluster_count": len(tech_rows)},
            }
        )

    # --- 3) Thin high-intent pages (crawl-only, deterministic)
    pages = [p for p in (payload.get("pages") or []) if isinstance(p, dict)]
    thin_urls = _collect_thin_high_intent_urls(pages, metrics)
    if thin_urls:
        out.append(
            {
                "cluster_key": "thin_content_cluster",
                "members": [],
                "urls": thin_urls[:8],
                "meta": {"page_count": len(thin_urls)},
            }
        )

    # --- 4) Internal linking gaps
    link_urls = _collect_internal_linking_gap_urls(pages)
    if link_urls:
        out.append(
            {
                "cluster_key": "internal_linking_gap",
                "members": [],
                "urls": link_urls[:8],
                "meta": {"page_count": len(link_urls)},
            }
        )

    # Optional: refine overlap using topic_overlap findings (intent / market tags)
    overlap_pairs = [f for f in findings if f.get("type") == "topic_overlap"]
    if overlap_pairs and out and out[0].get("cluster_key") == "overlap_same_intent":
        out[0]["meta"]["topic_overlap_pairs"] = min(len(overlap_pairs), 20)

    return out


def _cluster_cross_market(rows: list[dict], payload: dict) -> bool:
    bc = payload.get("business_context") or {}
    if not (bc.get("market_context") or {}).get("separate_regions"):
        return False
    urls: list[str] = []
    for r in rows[:4]:
        urls.extend(_urls_from_row(r, 4))
    for i, a in enumerate(urls):
        for b in urls[i + 1 :]:
            if is_cross_domain(a, b):
                return True
    return False


def _collect_thin_high_intent_urls(pages: list[dict], metrics: dict) -> list[str]:
    try:
        uniq = float(metrics.get("content_uniqueness_score") or 0.5)
    except (TypeError, ValueError):
        uniq = 0.5
    site_thin = uniq < 0.42
    out: list[str] = []
    seen: set[str] = set()
    for p in pages:
        url = str(p.get("url") or "").strip()
        if not url:
            continue
        cl = p.get("classification")
        if not isinstance(cl, dict) or not cl:
            cl = classify_page(
                url,
                str(p.get("title") or ""),
                str(p.get("text_sample") or ""),
            )
        intent = str(cl.get("intent") or "")
        stage = str(cl.get("decision_stage") or "")
        wc = int(p.get("word_count") or 0)
        outn = len(p.get("internal_links_out") or [])
        high_intent = intent in ("transactional", "commercial") or stage == "decision"
        if not high_intent:
            continue
        if wc < 450 and (outn < 2 or site_thin) and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _inbound_counts(pages: list[dict]) -> dict[str, int]:
    from app.utils import canonicalize_url

    canon = {canonicalize_url(str(p.get("url") or "")) for p in pages if p.get("url")}
    inbound: dict[str, int] = defaultdict(int)
    for p in pages:
        for raw in p.get("internal_links_out") or []:
            c = canonicalize_url(str(raw))
            if c in canon:
                inbound[c] += 1
    return inbound


def _collect_internal_linking_gap_urls(pages: list[dict]) -> list[str]:
    if len(pages) < 2:
        return []
    from app.utils import canonicalize_url

    inbound = _inbound_counts(pages)
    out: list[str] = []
    seen: set[str] = set()
    for p in pages:
        url = str(p.get("url") or "").strip()
        if not url:
            continue
        cl = p.get("classification")
        if not isinstance(cl, dict) or not cl:
            cl = classify_page(
                url,
                str(p.get("title") or ""),
                str(p.get("text_sample") or ""),
            )
        wc = int(p.get("word_count") or 0)
        intent = str(cl.get("intent") or "")
        stage = str(cl.get("decision_stage") or "")
        ptype = str(p.get("type") or "")
        high_value = (
            intent == "transactional"
            or stage == "decision"
            or ptype in ("product", "guide")
            or wc >= 650
        )
        if not high_value:
            continue
        ic = inbound.get(canonicalize_url(url), 0)
        if ic < 2 and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _dominant_transformation_for_overlap_cluster(
    members: list[dict], payload: dict, sample_urls: list[str]
) -> str:
    if not members:
        return "differentiate"
    scores: list[tuple[float, str]] = []
    metrics = payload.get("metrics") or {}
    for row in members:
        tt = infer_transformation_type_for_cluster_row(row, payload, sample_urls)
        ps = issue_priority_score(row, metrics)
        scores.append((ps, tt))
    scores.sort(key=lambda x: -x[0])
    return scores[0][1] if scores else "differentiate"


def _apply_strategy_to_tt(
    cluster_key: str,
    tt: str,
    primary_strategy: dict | None,
    meta: dict,
) -> str:
    ps = primary_strategy or {}
    strategy = str(ps.get("strategy") or "").lower()
    rules = ps.get("rules") if isinstance(ps.get("rules"), dict) else {}

    if cluster_key != "overlap_same_intent":
        return tt

    if strategy == "differentiate" and rules.get("enforce_primary_direction"):
        if meta.get("cross_market_hint") or not rules.get("allow_merge", True):
            return "differentiate" if tt in ("merge", "consolidate", "redirect") else tt
    if strategy == "merge" and not rules.get("allow_differentiation", True):
        if tt in ("differentiate", "isolate", "split"):
            return "merge"
    return tt


def _cluster_problem_line(cluster_key: str, meta: dict, tt: str) -> str:
    if cluster_key == "overlap_same_intent":
        n = int(meta.get("remediation_cluster_count") or 1)
        cluster_word = "cluster" if n == 1 else "clusters"
        intents = meta.get("intent_labels") or []
        intent_phrase = ""
        if len(intents) == 1:
            intent_phrase = f" under {intents[0]} intent"
        elif len(intents) > 1:
            intent_phrase = " across overlapping buyer intents"
        return (
            f"You have {n} duplicate group{'' if n == 1 else 's'} of pages competing for the same "
            f"decision{intent_phrase}."
        )
    if cluster_key == "structural_conflict":
        n = int(meta.get("technical_cluster_count") or 1)
        return (
            f"You have {n} technical URL pattern conflict{'' if n == 1 else 's'} that split signals "
            f"across duplicate routes."
        )
    if cluster_key == "thin_content_cluster":
        n = int(meta.get("page_count") or 0)
        return (
            f"You have {n} high-intent page{'s' if n != 1 else ''} that under-deliver depth for the job "
            f"they target."
        )
    if cluster_key == "internal_linking_gap":
        n = int(meta.get("page_count") or 0)
        return (
            f"You have {n} important destination{'s' if n != 1 else ''} with weak internal support from "
            f"the rest of the site."
        )
    return _fallback_problem(tt)


def _fallback_problem(tt: str) -> str:
    if tt in ("merge", "consolidate"):
        return "Overlapping pages fight for the same buyer job."
    if tt == "redirect":
        return "Multiple URLs tell the same story."
    return "Similar pages blur which one should win."


def _cluster_decision_line(
    cluster_key: str,
    tt: str,
    urls: list[str],
    primary_strategy: dict | None,
    _decision_line_fn,
) -> str:
    strategy = str((primary_strategy or {}).get("strategy") or "").lower()
    if cluster_key == "overlap_same_intent" and strategy == "differentiate":
        if urls:
            return (
                "The correct move is to separate regional and role signals clearly: give each live URL a distinct "
                "buyer job, then consolidate true duplicates inside each region so you do not repeat "
                f"the same story twice. Start with: {', '.join(urls[:2])}."
            )
        return (
            "The correct move is to separate regional and role signals, then consolidate duplicates within each "
            "market so parallel URLs stop competing for the same decision."
        )
    if cluster_key == "structural_conflict":
        u0 = urls[0] if urls else "the canonical URL"
        rest = f", {urls[1]}" if len(urls) > 1 else ""
        return (
            f"The correct move is to normalize technical duplicates with redirects or canonical rules so one route "
            f"wins—begin with {u0}{rest}."
        )
    if cluster_key == "thin_content_cluster":
        ex = ", ".join(urls[:3]) if urls else "those URLs"
        return (
            f"The correct move is to expand proof, pricing context, and next steps on {ex} so each page earns its "
            f"high-intent job."
        )
    if cluster_key == "internal_linking_gap":
        ex = ", ".join(urls[:3]) if urls else "those destinations"
        return (
            f"The correct move is to add contextual internal links from related pages pointing to {ex} so priority "
            f"URLs collect attention."
        )
    return _decision_line_fn(tt, urls)


def consolidate_clusters(
    clusters: list[dict[str, Any]],
    payload: dict,
    primary_strategy: dict | None,
) -> list[dict[str, Any]]:
    """
    One executive insight per narrative cluster (same keys as legacy top_issues rows).

    Respects primary_strategy for overlap recommendations (differentiate vs merge).
    """
    from app.executive_summary import (
        _decision_line,
        _problem_title,
        _risk_if_ignored_line,
        _why_line,
        map_action_to_outcome,
        map_problem_to_business_impact,
    )

    payload = payload or {}
    metrics = payload.get("metrics") or {}
    sample_urls: list[str] = []
    seen: set[str] = set()
    for c in clusters:
        for u in c.get("urls") or []:
            if u not in seen:
                seen.add(u)
                sample_urls.append(str(u))

    insights: list[dict[str, Any]] = []
    for c in clusters:
        ck = str(c.get("cluster_key") or "")
        if ck not in CLUSTER_KEYS:
            continue
        members = list(c.get("members") or [])
        urls = list(c.get("urls") or [])
        meta = dict(c.get("meta") or {})

        if ck == "overlap_same_intent":
            tt = _dominant_transformation_for_overlap_cluster(members, payload, sample_urls)
        elif ck == "structural_conflict":
            tt = "redirect"
        elif ck == "thin_content_cluster":
            tt = "differentiate"
        else:
            tt = "differentiate"

        tt = _apply_strategy_to_tt(ck, tt, primary_strategy, meta)

        summary_line = _cluster_problem_line(ck, meta, tt)
        business = map_problem_to_business_impact(tt, metrics)
        decision = _cluster_decision_line(ck, tt, urls, primary_strategy, _decision_line)
        why = _why_line(tt)
        risk = _risk_if_ignored_line(tt)
        outcome = map_action_to_outcome(tt)
        skim = _problem_title(tt)

        try:
            ps_f = (
                max(issue_priority_score(r, metrics) for r in members)
                if members
                else float(payload.get("priority_score") or 0)
            )
        except ValueError:
            ps_f = float(payload.get("priority_score") or 0)

        pl = str(payload.get("priority_level") or "medium")

        evidence = build_evidence_pack(c, payload)
        decision_rationale = build_decision_rationale(ck, tt, evidence, urls[:6], primary_strategy)

        insights.append(
            {
                "cluster_key": ck,
                "problem": summary_line,
                "cluster_skim": skim,
                "impact": business,
                "decision": decision,
                "risk": risk,
                "outcome": outcome,
                "why": why,
                "business_consequence": business,
                "risk_if_ignored": risk,
                "urls": urls[:6],
                "transformation_type": tt,
                "priority_score": ps_f,
                "priority_level": pl,
                "recommended_action": decision,
                "evidence": evidence,
                "decision_rationale": decision_rationale,
            }
        )

    return insights


def build_consolidated_top_issues(
    payload: dict,
    primary_strategy: dict | None,
    findings: list[dict] | None = None,
    max_issues: int = 3,
) -> list[dict[str, Any]]:
    """
    End-to-end: cluster findings + payload, consolidate, cap count for executive UI.
    """
    raw = cluster_findings(findings, payload)
    consolidated = consolidate_clusters(raw, payload, primary_strategy)
    return consolidated[:max_issues]
