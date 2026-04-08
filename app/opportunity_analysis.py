"""
Phase 8 — Opportunity Engine: parallel to structural clusters.

Heuristic, crawl-based signals only (no GA). Emits up to three opportunity_clusters
for growth-oriented recommendations.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.analyzer import classify_page
from app.utils import canonicalize_url


def _classification_for_page(p: dict) -> dict:
    cl = p.get("classification")
    if isinstance(cl, dict) and cl:
        return cl
    return classify_page(
        str(p.get("url") or ""),
        str(p.get("title") or ""),
        str(p.get("text_sample") or p.get("text") or p.get("content") or ""),
    )


def _text_sample(p: dict) -> str:
    return str(
        p.get("text_sample") or p.get("text") or p.get("content") or ""
    )


def _faq_style_content(text: str) -> bool:
    if not text or len(text) < 80:
        return False
    t = text.lower()
    if "faq" in t[:2000] or "frequently asked" in t[:2000]:
        return True
    if text.count("?") >= 3:
        return True
    if re.search(r"\b(q\.|question\s*\d|questions?\s+and\s+answers?)\b", t):
        return True
    return False


def _howto_style(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    if "how to" in t[:1200] or "how do i" in t[:1200]:
        return True
    return bool(re.search(r"\bstep\s*\d\b", t))


def _inbound_by_canonical(pages: list[dict]) -> dict[str, int]:
    canon_pages = {canonicalize_url(str(p.get("url") or "")) for p in pages if p.get("url")}
    inbound: dict[str, int] = defaultdict(int)
    for p in pages:
        for raw in p.get("internal_links_out") or []:
            c = canonicalize_url(str(raw))
            if c in canon_pages:
                inbound[c] += 1
    return inbound


def _structured_data_opportunity(pages: list[dict]) -> dict[str, Any] | None:
    candidates: list[str] = []
    for p in pages:
        url = str(p.get("url") or "").strip()
        if not url:
            continue
        cl = _classification_for_page(p)
        pt = str(cl.get("page_type") or "")
        ptype = str(p.get("type") or "")
        text = _text_sample(p)
        wc = int(p.get("word_count") or 0)
        if wc < 60:
            continue
        eligible = (
            ptype == "faq"
            or pt == "faq"
            or ptype == "product"
            or pt == "product"
            or _faq_style_content(text)
            or _howto_style(text)
        )
        if not eligible:
            continue
        candidates.append(url)
    candidates = list(dict.fromkeys(candidates))[:10]
    if not candidates:
        return None
    return {
        "type": "structured_data",
        "title": "Missing structured data on high-value pages",
        "pages": candidates,
        "opportunity": "These pages could qualify for enhanced search results",
        "impact": "Improves visibility and click-through without new content",
        "action": "Add FAQ, HowTo, or Product JSON-LD to these URLs as appropriate",
        "confidence": "medium",
    }


def _content_depth_opportunity(pages: list[dict], metrics: dict | None) -> dict[str, Any] | None:
    metrics = metrics or {}
    try:
        uniq = float(metrics.get("content_uniqueness_score") or 0.5)
    except (TypeError, ValueError):
        uniq = 0.5
    site_thin = uniq < 0.42
    candidates: list[str] = []
    for p in pages:
        url = str(p.get("url") or "").strip()
        if not url:
            continue
        cl = _classification_for_page(p)
        intent = str(cl.get("intent") or "informational")
        stage = str(cl.get("decision_stage") or "awareness")
        wc = int(p.get("word_count") or 0)
        outn = len(p.get("internal_links_out") or [])
        high_intent = intent in ("transactional", "commercial") or stage == "decision"
        if not high_intent:
            continue
        thin = wc < 450
        low_out = outn < 2
        if thin and (low_out or site_thin):
            candidates.append(url)
    candidates = list(dict.fromkeys(candidates))[:10]
    if not candidates:
        return None
    return {
        "type": "content_depth",
        "title": "Pages under-serving high-intent queries",
        "pages": candidates,
        "opportunity": "These pages are ranking targets but lack depth",
        "impact": "Expanding them can improve conversions and capture more demand",
        "action": "Expand content and strengthen internal linking",
        "confidence": "medium",
    }


def _internal_linking_opportunity(pages: list[dict]) -> dict[str, Any] | None:
    if len(pages) < 2:
        return None
    inbound = _inbound_by_canonical(pages)
    candidates: list[str] = []
    for p in pages:
        url = str(p.get("url") or "").strip()
        if not url:
            continue
        cl = _classification_for_page(p)
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
        if ic < 2:
            candidates.append(url)
    candidates = list(dict.fromkeys(candidates))[:10]
    if not candidates:
        return None
    return {
        "type": "internal_linking",
        "title": "High-value pages lack internal support",
        "pages": candidates,
        "opportunity": "These pages are not being reinforced by the site structure",
        "impact": "Stronger linking improves discoverability and authority flow",
        "action": "Add contextual links from related pages",
        "confidence": "medium",
    }


def analyze_opportunities(payload: dict | None) -> list[dict[str, Any]]:
    """
    Build ordered opportunity_clusters (max 3) from crawl payload.

    Expects payload['pages'] as list of dicts with url, word_count, type,
    classification, internal_links_out, and optional text_sample/text.
    """
    payload = payload or {}
    pages = [p for p in (payload.get("pages") or []) if isinstance(p, dict)]
    if not pages:
        return []
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    out: list[dict[str, Any]] = []
    for block in (
        _structured_data_opportunity(pages),
        _content_depth_opportunity(pages, metrics),
        _internal_linking_opportunity(pages),
    ):
        if block:
            out.append(block)
    return out
