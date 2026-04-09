"""
Phase 15 — Deterministic top proof lines (max 3). No LLM.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


def _host_path(url: str, max_len: int = 56) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    try:
        p = urlparse(u if "://" in u else f"https://{u}")
        h = p.netloc or ""
        path = (p.path or "")[:40]
        s = f"{h}{path}".strip("/") or u[:max_len]
        return s[:max_len]
    except Exception:
        return u[:max_len]


def select_top_proof(audit_signal: dict[str, Any], pov: dict[str, Any]) -> list[str]:
    """
    Exactly up to 3 bullets: top 2 metric interpretations + 1 cluster example.
    pov is accepted for future alignment hooks; selection is deterministic from audit_signal.
    """
    _ = pov
    km = (audit_signal or {}).get("key_metrics") or {}
    bullets: list[str] = []

    orate = km.get("overlap_rate")
    if orate is not None:
        try:
            pct = round(float(orate) * 100, 1)
            bullets.append(f"{pct}% of crawled pages sit in overlapping clusters.")
        except (TypeError, ValueError):
            pass

    sim = km.get("avg_cluster_similarity")
    if sim is not None and len(bullets) < 2:
        try:
            pct = round(float(sim) * 100, 1)
            bullets.append(
                f"Average similarity between paired pages is {pct}%, so bodies track almost the same story."
            )
        except (TypeError, ValueError):
            pass

    if len(bullets) < 2 and km.get("content_uniqueness_score") is not None:
        try:
            cu = float(km["content_uniqueness_score"])
            bullets.append(
                f"Distinctness across the sample is {round(cu * 100, 1)}%—copy overlap is heavy."
            )
        except (TypeError, ValueError):
            pass

    clusters = (audit_signal or {}).get("top_clusters") or []
    if clusters and isinstance(clusters[0], dict):
        c0 = clusters[0]
        desc = (c0.get("description") or "").strip()
        urls = c0.get("urls") or []
        if isinstance(urls, list) and urls:
            bits = ", ".join(_host_path(str(u)) for u in urls[:2] if u)
            line = f"{desc} Example routes: {bits}."
        else:
            line = desc or "The strongest cluster shows near-duplicate coverage."
        bullets.append(re.sub(r"\s+", " ", line).strip())

    return bullets[:3]
