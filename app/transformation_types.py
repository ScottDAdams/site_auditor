"""
Deterministic transformation taxonomy and type inference (Phase 5).

No LLM — thresholds and flags only.
"""

from __future__ import annotations

from app.business_context import is_cross_domain

TRANSFORMATION_TYPES = [
    "differentiate",
    "merge",
    "redirect",
    "split",
    "consolidate",
    "isolate",
    "elevate",
    "demote",
    "retain",
]

# Lower number = execute earlier when scores tie (merge before redirect before …).
TRANSFORMATION_PRIORITY: dict[str, int] = {
    "merge": 1,
    "redirect": 2,
    "consolidate": 3,
    "isolate": 4,
    "differentiate": 5,
    "retain": 6,
    "split": 7,
    "elevate": 8,
    "demote": 9,
}


def _float_metric(payload: dict, key: str, default: float = 0.0) -> float:
    m = payload.get("metrics") or {}
    try:
        return float(m.get(key, default))
    except (TypeError, ValueError):
        return default


def _row_cross_market(row: dict, payload: dict) -> bool:
    bc = payload.get("business_context") or {}
    mc = bc.get("market_context") or {}
    if not mc.get("separate_regions"):
        return False
    dom = row.get("dominant_url")
    comp = (row.get("competing_urls") or [])[:1]
    if not dom or not comp:
        return False
    return is_cross_domain(str(dom), str(comp[0]))


def _cluster_url_count(row: dict | None, sample_urls: list[str]) -> int:
    if not row:
        return max(len(sample_urls), 1)
    pages = row.get("pages") or []
    if pages:
        return max(len(pages), 1)
    n = 1 + len(row.get("competing_urls") or [])
    return max(n, len(sample_urls), 1)


def infer_transformation_type(
    payload: dict,
    dominant: str,
    relationship: str,
    cluster_url_count: int,
    row_similarity: float | None = None,
) -> str:
    """
    Deterministic classification. Order matches Phase 5 spec (merge before cross-market differentiate, etc.).
    """
    dominant = (dominant or "acceptable").strip().lower()
    avg_sim = _float_metric(payload, "avg_cluster_similarity")
    cu = _float_metric(payload, "content_uniqueness_score", 1.0)
    sim = float(row_similarity) if row_similarity is not None else avg_sim

    if dominant == "acceptable":
        return "retain"

    if dominant == "technical":
        if cluster_url_count >= 3:
            return "consolidate"
        return "redirect"

    if dominant != "strategic":
        return "retain"

    bc = payload.get("business_context") or {}
    mc = bc.get("market_context") or {}
    separate = bool(mc.get("separate_regions"))
    # Cross-market + distinct regions: differentiate before near-duplicate merge
    # so AU/NZ mirrors are not told to collapse into one global page.
    if relationship == "cross_market" and separate:
        return "differentiate"

    # Near-identical strategic pages in the same market → collapse
    if avg_sim > 0.92 and cu < 0.1:
        return "merge"

    if relationship == "intra_market" and sim > 0.85:
        return "isolate"

    if cluster_url_count >= 3:
        return "consolidate"

    return "differentiate"


def infer_transformation_type_for_cluster_row(
    row: dict,
    payload: dict,
    sample_urls_hint: list[str],
) -> str:
    """Per-cluster execution ordering: relationship derived from this row's URLs."""
    dominant = (payload.get("dominant_problem_type") or "acceptable").strip().lower()
    rel = "intra_market"
    dom = row.get("dominant_url")
    comps = row.get("competing_urls") or []
    if dom and comps and _row_cross_market(row, payload):
        rel = "cross_market"
    elif dom and comps:
        rel = "intra_market"
    try:
        rsim = float(row.get("similarity"))
    except (TypeError, ValueError):
        rsim = None
    n = _cluster_url_count(row, sample_urls_hint)
    return infer_transformation_type(
        payload,
        dominant,
        rel,
        n,
        row_similarity=rsim,
    )


def keep_both_for_type(transformation_type: str) -> bool:
    if transformation_type in ("merge", "redirect", "consolidate"):
        return False
    return True
