"""
Phase 9 — Decision arbitration: one coherent primary strategy for the whole report.

Resolves tension between merge-style consolidation and cross-market differentiation
so outputs do not contradict each other.
"""

from __future__ import annotations

import re
from typing import Any


def validate_narrative_against_strategy(text: str, primary_strategy: dict | None) -> None:
    """
    Raise ValueError if client or insight prose contradicts the resolved strategy
    (e.g. merge-into-one language while strategy is differentiate).
    """
    if not primary_strategy or not isinstance(primary_strategy, dict):
        return
    strategy = str(primary_strategy.get("strategy") or "").lower()
    if strategy == "hybrid":
        return
    rules = primary_strategy.get("rules") if isinstance(primary_strategy.get("rules"), dict) else {}
    low = (text or "").lower()

    if strategy == "differentiate" and rules.get("enforce_primary_direction"):
        if not rules.get("allow_merge", True):
            if re.search(
                r"\bmerge\b.*\b(into|single|one\s+primary|one\s+canonical|canonical\s+destination)\b",
                low,
            ):
                raise ValueError(
                    "[rule:strategy_narrative_merge] merge-into-one language conflicts with primary "
                    "strategy differentiate"
                )
            if re.search(r"\b(consolidate|collapse)\b.{0,80}\b(one|single)\s+(primary\s+)?page\b", low):
                raise ValueError(
                    "[rule:strategy_narrative_consolidate] consolidation language conflicts with "
                    "primary strategy differentiate"
                )
            if "near-duplicate pages should collapse" in low:
                raise ValueError(
                    "[rule:strategy_narrative_collapse] collapse framing conflicts with primary "
                    "strategy differentiate"
                )

    if strategy == "merge" and rules.get("enforce_primary_direction"):
        if not rules.get("allow_differentiation", True):
            if re.search(
                r"\bkeep\b.{0,40}\b(both|separate)\b.{0,40}\b(urls?|pages?|domains?)\b",
                low,
            ):
                raise ValueError(
                    "[rule:strategy_narrative_keep_both] keep-separate language conflicts with "
                    "primary strategy merge"
                )


def validate_roadmap_against_strategy(obj: dict | None, primary_strategy: dict | None) -> bool:
    """Return False if roadmap steps contradict the resolved primary strategy."""
    if not primary_strategy or not isinstance(primary_strategy, dict):
        return True
    strategy = str(primary_strategy.get("strategy") or "").lower()
    if strategy == "hybrid":
        return True
    rules = primary_strategy.get("rules") if isinstance(primary_strategy.get("rules"), dict) else {}
    r = obj.get("roadmap") if isinstance(obj, dict) else None
    if not isinstance(r, list):
        return True

    for step in r:
        if not isinstance(step, dict):
            continue
        at = str(step.get("action_type") or "").lower().strip()
        blob = f"{step.get('title', '')} {step.get('description', '')}".lower()

        if strategy == "differentiate" and rules.get("enforce_primary_direction"):
            if not rules.get("allow_merge", True):
                if at in ("merge", "consolidate", "delete"):
                    return False
            if not rules.get("allow_merge", True) and re.search(
                r"\bmerge\b.*\b(into|single|one\s+primary|one\s+canonical)\b", blob
            ):
                return False

        if strategy == "merge" and rules.get("enforce_primary_direction"):
            if not rules.get("allow_differentiation", True):
                if at in ("differentiate", "reposition", "split"):
                    return False

    return True


def resolve_primary_strategy(
    payload: dict | None,
    insights: dict | None,
    opportunities: list | None,
) -> dict[str, Any]:
    """
    Pick a single dominant structural strategy from deterministic signals.

    Returns:
        strategy: "merge" | "differentiate" | "hybrid"
        confidence: float 0..1
        reasoning: client-facing explanation
        label: short UI title
        rules: allow_merge, allow_differentiation, enforce_primary_direction
    """
    _ = insights
    _ = opportunities
    payload = payload or {}
    spec = payload.get("transformation_spec") if isinstance(payload.get("transformation_spec"), dict) else {}
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    bc = payload.get("business_context") if isinstance(payload.get("business_context"), dict) else {}
    mc = bc.get("market_context") if isinstance(bc.get("market_context"), dict) else {}

    try:
        overlap = float(metrics.get("overlap_rate") or 0.0)
    except (TypeError, ValueError):
        overlap = 0.0
    try:
        uniq = float(metrics.get("content_uniqueness_score") or 0.5)
    except (TypeError, ValueError):
        uniq = 0.5

    relationship = str(spec.get("cluster_relationship") or "")
    keep_both = bool(spec.get("keep_both", True))
    ttype = str(spec.get("transformation_type") or "differentiate").strip().lower()
    separate_regions = bool(mc.get("separate_regions"))

    # Cross-market with two live destinations: differentiation wins over merge.
    if relationship == "cross_market" and keep_both:
        return {
            "strategy": "differentiate",
            "confidence": 0.9,
            "reasoning": (
                "Regional audiences and domains are distinct. Keep separate URLs and enforce "
                "market-specific messaging so each destination owns its decision path instead "
                "of mirroring the same story across regions."
            ),
            "label": "Differentiate regional pages",
            "rules": {
                "allow_merge": False,
                "allow_differentiation": True,
                "enforce_primary_direction": True,
            },
        }

    # Canonical collapse: merge / redirect / consolidate without keeping both peers.
    if ttype in ("merge", "redirect", "consolidate") and not keep_both:
        return {
            "strategy": "merge",
            "confidence": 0.88,
            "reasoning": (
                "Similarity and duplication signals support a single canonical outcome for this "
                "intent. Consolidate routes and retire duplicate indexable surfaces."
            ),
            "label": "Consolidate to canonical",
            "rules": {
                "allow_merge": True,
                "allow_differentiation": False,
                "enforce_primary_direction": True,
            },
        }

    # Strong global duplication, same-market context → merge bias.
    if overlap > 0.55 and uniq < 0.35 and relationship != "cross_market":
        return {
            "strategy": "merge",
            "confidence": 0.82,
            "reasoning": (
                "High overlap and low distinctness across sampled pages favor consolidation "
                "rather than parallel competing URLs for the same decision."
            ),
            "label": "Consolidate overlapping pages",
            "rules": {
                "allow_merge": True,
                "allow_differentiation": False,
                "enforce_primary_direction": True,
            },
        }

    # Isolate / intra-market strategic overlap: separate roles, keep URLs.
    if ttype == "isolate" and keep_both:
        return {
            "strategy": "differentiate",
            "confidence": 0.8,
            "reasoning": (
                "Pages sit in the same market but blur distinct buyer jobs. Assign clear roles "
                "per URL and remove shared blocks that make them interchangeable."
            ),
            "label": "Isolate intent per page",
            "rules": {
                "allow_merge": False,
                "allow_differentiation": True,
                "enforce_primary_direction": True,
            },
        }

    # Default hybrid: technical consolidation possible while strategic rows may still need clarity.
    hybrid_reason = (
        "Use redirects and canonical rules for technical duplicates first. For strategic "
        "clusters, follow the transformation type on each issue. If regions differ, "
        "differentiate messaging; if not, consolidate where the spec calls for a single winner."
    )
    if separate_regions and relationship == "intra_market":
        hybrid_reason = (
            "Within each region, consolidate true duplicates and clarify roles where pages "
            "still compete for the same decision."
        )

    return {
        "strategy": "hybrid",
        "confidence": 0.72,
        "reasoning": hybrid_reason,
        "label": "Hybrid: consolidate technical, clarify strategic overlap",
        "rules": {
            "allow_merge": True,
            "allow_differentiation": True,
            "enforce_primary_direction": True,
        },
    }
