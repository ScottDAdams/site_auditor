"""
Evidence packs: deterministic proof from crawl-backed text already on the payload.

No new HTTP fetches or crawl passes. Uses pages[].text_sample and cluster similarity signals.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from app.utils import canonicalize_url


def _norm_body(s: str) -> str:
    t = (s or "").lower()
    t = re.sub(r"\s+", " ", t).strip()
    return t


def compute_similarity_from_texts(text_a: str, text_b: str) -> float:
    """Deterministic body similarity 0..1 from normalized character sequences."""
    a, b = _norm_body(text_a), _norm_body(text_b)
    if not a or not b:
        return 0.0
    return round(SequenceMatcher(None, a, b).ratio(), 4)


def _paragraph_leaders(text: str, max_n: int = 14) -> list[str]:
    """Heuristic 'section' labels from first line of each paragraph block."""
    if not (text or "").strip():
        return []
    chunks = re.split(r"\n\s*\n+", text.strip())
    out: list[str] = []
    for ch in chunks[:20]:
        first = ch.strip().split("\n")[0].strip()
        if 10 <= len(first) <= 100 and not first.endswith("."):
            out.append(first[:90])
        if len(out) >= max_n:
            break
    return out


def _unique_leaders(a: list[str], b: list[str]) -> tuple[list[str], list[str]]:
    la = {x.lower().strip() for x in a}
    lb = {x.lower().strip() for x in b}
    shared = []
    for x in a:
        if x.lower().strip() in lb:
            shared.append(x)
    only_a = [x for x in a if x.lower().strip() not in lb][:4]
    only_b = [x for x in b if x.lower().strip() not in la][:4]
    return shared, only_a + only_b


def _pages_by_url(payload: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in payload.get("pages") or []:
        if not isinstance(p, dict):
            continue
        u = str(p.get("url") or "").strip()
        if u:
            out[canonicalize_url(u)] = p
    return out


def _text_for_url(pages_map: dict[str, dict], url: str) -> str:
    c = canonicalize_url(url)
    p = pages_map.get(c) or {}
    return str(
        p.get("text_sample") or p.get("text") or p.get("content") or ""
    )


def build_evidence_pack(cluster: dict[str, Any], payload: dict | None) -> dict[str, Any]:
    """
    Structured, verifiable evidence for a narrative cluster (overlap, technical, thin, linking).

    `cluster` uses narrative_consolidation shape: cluster_key, urls, members, meta.
    """
    payload = payload or {}
    cluster = cluster or {}
    ck = str(cluster.get("cluster_key") or "")
    urls = [str(u).strip() for u in (cluster.get("urls") or []) if u]
    members = list(cluster.get("members") or [])
    meta = dict(cluster.get("meta") or {})
    pages_map = _pages_by_url(payload)
    metrics = payload.get("metrics") or {}

    if ck == "overlap_same_intent":
        row_sims: list[float] = []
        for r in members:
            try:
                if r.get("similarity") is not None:
                    row_sims.append(float(r["similarity"]))
            except (TypeError, ValueError):
                pass
        fallback_sim = float(metrics.get("avg_cluster_similarity") or 0.0)

        u0 = urls[0] if urls else ""
        u1 = urls[1] if len(urls) > 1 else ""
        t0, t1 = _text_for_url(pages_map, u0), _text_for_url(pages_map, u1)
        text_sim = compute_similarity_from_texts(t0, t1) if t0 and t1 else 0.0
        if row_sims:
            structural_sim = sum(row_sims) / len(row_sims)
        else:
            structural_sim = fallback_sim
        # Blend structural cluster signal with sampled-body check when both texts exist
        if t0 and t1:
            combined = round(0.55 * structural_sim + 0.45 * text_sim, 4)
        else:
            combined = round(structural_sim, 4)

        leaders_a = _paragraph_leaders(t0)
        leaders_b = _paragraph_leaders(t1) if u1 else []
        shared, diff_hints = _unique_leaders(leaders_a, leaders_b if u1 else [])
        if not shared and leaders_a:
            shared = leaders_a[:3]
        key_differences: list[str] = []
        if diff_hints:
            key_differences.append("Distinct opening blocks between compared URLs.")
        if u1 and t0 and t1:
            if abs(len(t0) - len(t1)) > max(len(t0), len(t1)) * 0.15:
                key_differences.append("Material length delta between sampled bodies.")
        if not key_differences:
            key_differences.append("Wording and local proof differ only slightly in the sampled crawl slice.")

        interpretation = (
            "Sampled bodies and cluster similarity indicate these URLs serve the same buyer job "
            "with overlapping structure."
            if combined >= 0.72
            else "URLs show partial overlap in the crawl sample; roles still need explicit separation."
        )

        return {
            "similarity_score": min(1.0, max(0.0, combined)),
            "structural_similarity": round(structural_sim, 4),
            "body_text_similarity": round(text_sim, 4) if t0 and t1 else None,
            "compared_urls": [u0, u1] if u1 else ([u0] if u0 else []),
            "shared_sections": shared[:5],
            "key_differences": key_differences[:5],
            "interpretation": interpretation,
            "source": "crawl_text_sample_and_cluster_metrics",
        }

    if ck == "structural_conflict":
        issues: list[str] = []
        for r in members[:6]:
            ti = (r.get("technical_issue") or "").strip()
            if ti:
                issues.append(ti)
        if not issues:
            issues = ["Duplicate or ambiguous URL patterns in crawl"]
        return {
            "similarity_score": 1.0,
            "shared_sections": issues[:5],
            "key_differences": ["Multiple indexable routes resolve to the same or equivalent content."],
            "interpretation": "Crawl marks technical duplication: signals split across equivalent URLs.",
            "source": "cluster_technical_fix_rows",
        }

    if ck == "thin_content_cluster":
        samples: list[str] = []
        for u in urls[:5]:
            p = pages_map.get(canonicalize_url(u)) or {}
            wc = int(p.get("word_count") or 0)
            samples.append(f"{u}: {wc} words in crawl")
        return {
            "similarity_score": None,
            "shared_sections": ["High-intent URLs with shallow copy in crawl sample"],
            "key_differences": samples[:5] or ["Thin pages detected from stored word counts"],
            "interpretation": "Crawl shows priority URLs under-serving the decision stage they target.",
            "source": "page_word_counts",
        }

    if ck == "internal_linking_gap":
        return {
            "similarity_score": None,
            "shared_sections": ["Important destinations with low inbound internal links in crawl"],
            "key_differences": [
                f"{u}: fewer than two inbound internal links among sampled URLs" for u in urls[:5]
            ],
            "interpretation": "Site graph under-supports URLs that should collect internal attention.",
            "source": "internal_link_counts",
        }

    return {
        "similarity_score": None,
        "shared_sections": [],
        "key_differences": [],
        "interpretation": "No evidence slice computed for this cluster type.",
        "source": "none",
    }


def build_decision_rationale(
    cluster_key: str,
    transformation_type: str,
    evidence: dict[str, Any],
    urls: list[str],
    primary_strategy: dict | None,
) -> str:
    """
    Definitive, evidence-backed rationale (no hedging: no could/might/consider).
    """
    tt = (transformation_type or "").strip().lower()
    ev = evidence or {}
    sim = ev.get("similarity_score")
    shared = ev.get("shared_sections") or []
    interp = (ev.get("interpretation") or "").strip()
    strat = str((primary_strategy or {}).get("strategy") or "").lower()

    shared_txt = ", ".join(f'"{s}"' for s in shared[:3]) if shared else "the same structural blocks"

    if cluster_key == "overlap_same_intent" and sim is not None:
        pct = int(round(float(sim) * 100))
        u_pair = ""
        if urls:
            u_pair = f" Comparing {urls[0]} and {urls[1]}" if len(urls) > 1 else f" On {urls[0]}"
        if strat == "differentiate" or tt in ("differentiate", "isolate", "split"):
            return (
                f"The correct move is to separate roles per URL because crawl evidence shows {pct}% "
                f"combined similarity{u_pair}, with shared sections including {shared_txt}. "
                f"{interp} Parallel live URLs stay, but each must own a distinct decision path."
            )
        if tt in ("merge", "consolidate"):
            return (
                f"The correct move is to consolidate to one canonical surface because crawl evidence shows "
                f"{pct}% combined similarity with {shared_txt}—the same intent is duplicated across routes."
            )
        return (
            f"The correct move follows the assigned transformation ({tt}) because evidence shows {pct}% "
            f"similarity and overlapping sections {shared_txt}. {interp}"
        )

    if cluster_key == "structural_conflict":
        return (
            "The correct move is to collapse technical duplicates because crawl flags equivalent routes "
            "that split crawl and user signals; one canonical URL must win."
        )

    if cluster_key == "thin_content_cluster":
        return (
            "The correct move is to deepen high-intent pages because crawl word counts show they do not "
            "carry enough proof or decision support for the job each URL claims."
        )

    if cluster_key == "internal_linking_gap":
        return (
            "The correct move is to add contextual inbound links because crawl shows priority destinations "
            "receive weak reinforcement from the rest of the site graph."
        )

    return (
        f"The correct move aligns to the {tt or 'stated'} transformation because the audit evidence "
        f"supports a single coherent structural response for this cluster."
    )


def evidence_pack_for_legacy_row(
    row: dict | None,
    payload: dict,
    transformation_type: str,
) -> dict[str, Any]:
    """Evidence for a single remediation cluster row (legacy per-card issues)."""
    if not row:
        return build_evidence_pack({"cluster_key": "overlap_same_intent", "urls": [], "members": [], "meta": {}}, payload)
    urls = []
    if row.get("dominant_url"):
        urls.append(str(row["dominant_url"]))
    for u in (row.get("competing_urls") or [])[:3]:
        if u:
            urls.append(str(u))
    fake_cluster = {
        "cluster_key": "overlap_same_intent",
        "urls": urls,
        "members": [row],
        "meta": {},
    }
    return build_evidence_pack(fake_cluster, payload)
