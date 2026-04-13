"""
Phase 15 — Decision-grade audit primitives (no raw MD) for executive argument pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.paths import generated_reports_root


def build_audit_signal(
    *,
    summary_data: dict[str, Any],
    verification_pack: dict[str, Any],
    execution_roadmap: dict[str, Any] | None,
    ai_insights: dict[str, Any] | None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Structured signal bundle stored on the audit snapshot as audit_signal.
    """
    es = summary_data or {}
    metrics = metrics or {}
    snap_m = es.get("_metrics_snapshot") or {}
    if not isinstance(snap_m, dict):
        snap_m = {}

    km: dict[str, float] = {}
    for key in ("overlap_rate", "avg_cluster_similarity", "content_uniqueness_score"):
        v = metrics.get(key)
        if v is None:
            v = snap_m.get(key)
        if v is not None:
            try:
                km[key] = float(v)
            except (TypeError, ValueError):
                pass

    candidates: list[dict[str, Any]] = []
    for iss in (es.get("top_issues") or [])[:3]:
        if not isinstance(iss, dict):
            continue
        stmt = (iss.get("problem") or iss.get("recommended_action") or "").strip()
        impact = (iss.get("impact") or iss.get("business_consequence") or "").strip()
        if impact and stmt:
            stmt = f"{stmt} {impact}".strip()
        elif impact:
            stmt = impact
        sm: list[str] = []
        if km.get("overlap_rate") is not None:
            sm.append(f"overlap_rate={round(km['overlap_rate'], 4)}")
        if km.get("avg_cluster_similarity") is not None:
            sm.append(f"avg_cluster_similarity={round(km['avg_cluster_similarity'], 4)}")
        urls = [str(u) for u in (iss.get("urls") or [])[:8] if u]
        candidates.append(
            {
                "statement": stmt or "Structural overlap appears in the audited crawl sample.",
                "supporting_metrics": sm[:6],
                "affected_urls": urls,
            }
        )

    if not candidates:
        sm_fallback: list[str] = []
        if km.get("overlap_rate") is not None:
            sm_fallback.append(f"overlap_rate={round(km['overlap_rate'], 4)}")
        candidates.append(
            {
                "statement": "Multiple URLs in the crawl compete for overlapping intent.",
                "supporting_metrics": sm_fallback,
                "affected_urls": [],
            }
        )

    proofs = (verification_pack or {}).get("cluster_proofs") or []
    scored = sorted(
        [p for p in proofs if isinstance(p, dict)],
        key=lambda x: float(x.get("similarity_score") or 0.0),
        reverse=True,
    )
    top_clusters: list[dict[str, Any]] = []
    for p in scored[:8]:
        top_clusters.append(
            {
                "description": str(p.get("diff_summary") or "").strip()
                or "High structural similarity between paired URLs.",
                "similarity": float(p.get("similarity_score") or 0.0),
                "urls": list(p.get("urls") or [])[:6],
            }
        )

    priority_actions: list[str] = []
    ins = ai_insights or {}
    pa = ins.get("primary_action")
    if pa:
        priority_actions.append(str(pa)[:500])
    for step in (execution_roadmap or {}).get("roadmap") or []:
        if not isinstance(step, dict):
            continue
        t = step.get("title") or step.get("description")
        if not t:
            continue
        ts = str(t).strip()[:500]
        if ts and ts not in priority_actions:
            priority_actions.append(ts)
        if len(priority_actions) >= 6:
            break
    if not priority_actions:
        priority_actions.append(
            "Resolve the dominant overlap cluster before expanding new routes."
        )

    return {
        "core_problem_candidates": candidates,
        "top_clusters": top_clusters,
        "key_metrics": km,
        "priority_actions": priority_actions[:8],
    }


def load_audit_signal(snapshot: dict[str, Any]) -> dict[str, Any]:
    """
    Prefer embedded audit_signal; otherwise rebuild from snapshot fields (pre–Phase 15 audits).
    """
    if not isinstance(snapshot, dict):
        return build_audit_signal(
            summary_data={},
            verification_pack={},
            execution_roadmap={},
            ai_insights={},
            metrics={},
        )
    raw = snapshot.get("audit_signal")
    if isinstance(raw, dict) and raw.get("key_metrics") is not None:
        return raw
    es = snapshot.get("executive_summary_data") or {}
    if not isinstance(es, dict):
        es = {}
    vp = snapshot.get("verification_pack")
    if not isinstance(vp, dict):
        vp = es.get("verification_pack") if isinstance(es.get("verification_pack"), dict) else {}
    er = snapshot.get("execution_roadmap")
    if not isinstance(er, dict):
        er = {}
    return build_audit_signal(
        summary_data=es,
        verification_pack=vp,
        execution_roadmap=er,
        ai_insights={},
        metrics=None,
    )


def audit_signal_path(report_id: int) -> Path:
    return generated_reports_root() / str(report_id) / "audit_signal.json"


def save_audit_signal_file(report_id: int, audit_signal: dict[str, Any]) -> None:
    p = audit_signal_path(report_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(audit_signal, indent=2, ensure_ascii=False), encoding="utf-8")
