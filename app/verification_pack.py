"""
Phase 11 verification pack: deterministic proof for overlap and structural claims.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from app.utils import canonicalize_url


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _sim(a: str, b: str) -> float:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    return round(SequenceMatcher(None, na, nb).ratio(), 4)


def _pages_by_url(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for p in payload.get("pages") or []:
        if not isinstance(p, dict):
            continue
        u = str(p.get("url") or "").strip()
        if not u:
            continue
        out[canonicalize_url(u)] = p
    return out


def _page_text(p: dict[str, Any]) -> str:
    return str(p.get("text") or p.get("content") or p.get("text_sample") or "")


def _extract_heading_sections(text: str) -> list[tuple[str, str]]:
    """
    Heuristic sections from crawl text.
    - heading line: short line ending without punctuation
    - body: following lines until next heading-like line
    """
    raw_lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    sections: list[tuple[str, str]] = []
    cur_h = ""
    cur_body: list[str] = []
    for ln in raw_lines:
        is_heading = (
            3 <= len(ln) <= 80
            and not ln.endswith(".")
            and not ln.endswith("!")
            and not ln.endswith("?")
            and len(ln.split()) <= 8
        )
        if is_heading:
            if cur_h:
                sections.append((cur_h, " ".join(cur_body).strip()))
            cur_h = ln
            cur_body = []
        else:
            cur_body.append(ln)
    if cur_h:
        sections.append((cur_h, " ".join(cur_body).strip()))

    if not sections:
        # Paragraph fallback when headings are not visible in stored text.
        paras = [p.strip() for p in re.split(r"\n\s*\n+", text or "") if p.strip()]
        for i, para in enumerate(paras[:8], 1):
            heading = f"Section {i}"
            sections.append((heading, para[:420]))
    return sections[:10]


def _overlap_sections(text_a: str, text_b: str) -> list[dict[str, Any]]:
    a_secs = _extract_heading_sections(text_a)
    b_secs = _extract_heading_sections(text_b)
    out: list[dict[str, Any]] = []
    used_b: set[int] = set()
    for h_a, body_a in a_secs:
        best_j = -1
        best_score = 0.0
        best_h = ""
        best_body = ""
        for j, (h_b, body_b) in enumerate(b_secs):
            if j in used_b:
                continue
            hs = _sim(h_a, h_b)
            bs = _sim(body_a[:420], body_b[:420])
            score = round((0.55 * hs) + (0.45 * bs), 4)
            if score > best_score:
                best_score = score
                best_j = j
                best_h = h_b
                best_body = body_b
        heading_match = _sim(h_a, best_h) >= 0.88
        if best_j >= 0 and (best_score >= 0.58 or heading_match):
            used_b.add(best_j)
            out.append(
                {
                    "heading": h_a if _sim(h_a, best_h) >= 0.5 else f"{h_a} / {best_h}",
                    "url_a_text": body_a[:320],
                    "url_b_text": best_body[:320],
                    "similarity_estimate": best_score,
                }
            )
        if len(out) >= 6:
            break
    return out


def _diff_summary(similarity: float, overlap_count: int) -> str:
    if similarity >= 0.86:
        return (
            "Both pages follow the same structure and repeat the same explanation with minor wording changes."
        )
    if similarity >= 0.72:
        return (
            "The pages share core structure and sections, but differ in local detail and emphasis."
        )
    if overlap_count:
        return "The pages overlap in selected sections, with meaningful differences across the rest of the content."
    return "These pages show limited direct overlap in sampled sections."


def build_verification_pack(payload: dict[str, Any], clusters: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Deterministic proof pack with overlap sections and similarity for each cluster.
    """
    payload = payload or {}
    rows = [c for c in (clusters or []) if isinstance(c, dict)]
    pages = _pages_by_url(payload)
    proofs: list[dict[str, Any]] = []

    for i, row in enumerate(rows, 1):
        dom = str(row.get("dominant_url") or "").strip()
        comp = [str(u).strip() for u in (row.get("competing_urls") or []) if str(u).strip()]
        urls = [u for u in [dom, *comp] if u][:2]
        if len(urls) < 2:
            pages_list = row.get("pages") or []
            extracted = [str(u).strip() for u in pages_list if str(u).strip()]
            urls = extracted[:2]
        if len(urls) < 2:
            continue

        pa = pages.get(canonicalize_url(urls[0])) or {}
        pb = pages.get(canonicalize_url(urls[1])) or {}
        ta, tb = _page_text(pa), _page_text(pb)
        sim = _sim(ta, tb) if ta and tb else float(row.get("similarity") or 0.0)
        overlap = _overlap_sections(ta, tb) if ta and tb else []

        proofs.append(
            {
                "cluster_id": str(row.get("cluster_id") or row.get("id") or f"cluster_{i}"),
                "urls": [urls[0], urls[1]],
                "similarity_score": round(float(sim), 4),
                "overlap_sections": overlap,
                "diff_summary": _diff_summary(float(sim), len(overlap)),
            }
        )
    return {"cluster_proofs": proofs}

