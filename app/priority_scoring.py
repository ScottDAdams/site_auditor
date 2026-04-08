"""
Deterministic structural priority and execution ordering (Phase 5).
"""

from __future__ import annotations

from app.transformation_types import TRANSFORMATION_PRIORITY


def _float(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _cluster_size_from_payload(payload: dict) -> int:
    rows = [c for c in (payload.get("clusters") or []) if isinstance(c, dict)]
    best = 1
    for r in rows:
        pages = r.get("pages") or []
        if pages:
            best = max(best, len(pages))
        else:
            n = 1 + len(r.get("competing_urls") or [])
            best = max(best, n)
    return best


def compute_structural_priority(payload: dict) -> dict:
    """
    Single audit-level score 0–100 from overlap, similarity, (1 - uniqueness), cluster size.
    """
    m = payload.get("metrics") or {}
    overlap = _float(m.get("overlap_rate"), 0.0)
    sim = _float(m.get("avg_cluster_similarity"), 0.0)
    cu = _float(m.get("content_uniqueness_score"), 0.0)
    cluster_size = _cluster_size_from_payload(payload)

    raw = (
        overlap * 0.3
        + sim * 0.3
        + (1.0 - cu) * 0.2
        + min(cluster_size / 5.0, 1.0) * 0.2
    )
    score = round(max(0.0, min(1.0, raw)) * 100.0, 2)

    if score >= 70:
        level = "high"
    elif score >= 40:
        level = "medium"
    else:
        level = "low"

    return {
        "priority_score": score,
        "priority_level": level,
    }


def issue_priority_score(row: dict, metrics: dict) -> float:
    """Per-cluster priority using row similarity + global metrics (same weights, 0–100)."""
    overlap = _float(metrics.get("overlap_rate"), 0.0)
    try:
        sim = float(row.get("similarity"))
    except (TypeError, ValueError):
        sim = _float(metrics.get("avg_cluster_similarity"), 0.0)
    cu = _float(metrics.get("content_uniqueness_score"), 0.0)
    pages = row.get("pages") or []
    cluster_size = len(pages) if pages else 1 + len(row.get("competing_urls") or [])

    raw = (
        overlap * 0.3
        + sim * 0.3
        + (1.0 - cu) * 0.2
        + min(cluster_size / 5.0, 1.0) * 0.2
    )
    return round(max(0.0, min(1.0, raw)) * 100.0, 2)


def assign_execution_order(issues: list[dict]) -> list[dict]:
    """
    Sort by priority_score DESC, then transformation_type weight (TRANSFORMATION_PRIORITY).
    Each issue should include priority_score and transformation_type.
    """
    def key(item: dict) -> tuple:
        ps = _float(item.get("priority_score"), 0.0)
        tt = str(item.get("transformation_type") or "retain").strip().lower()
        tw = TRANSFORMATION_PRIORITY.get(tt, 99)
        return (-ps, tw)

    return sorted([dict(x) for x in issues], key=key)


def build_structural_execution_issues(payload: dict, strategic_rows: list[dict]) -> list[dict]:
    """One issue dict per strategic cluster row for sequencing."""
    from app.transformation_types import infer_transformation_type_for_cluster_row

    metrics = payload.get("metrics") or {}
    sample_urls: list[str] = []
    seen: set[str] = set()
    for r in strategic_rows[:4]:
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

    issues = []
    for i, row in enumerate(strategic_rows):
        tt = infer_transformation_type_for_cluster_row(row, payload, sample_urls)
        issues.append(
            {
                "cluster_index": i,
                "dominant_url": row.get("dominant_url"),
                "priority_score": issue_priority_score(row, metrics),
                "transformation_type": tt,
            }
        )
    return assign_execution_order(issues)
