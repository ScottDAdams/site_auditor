"""
Rule-based duplication judgment. Rules are loaded from the `decision_rules` table
(see Admin → Decision Rules) or passed explicitly for tests.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DecisionRule


def cluster_decision_context(cluster: dict) -> dict[str, Any]:
    """
    Flat dict for condition matching. Keys align with rule JSON `conditions`.
    """
    from app.analyzer import summarize_cluster_classification

    csum = cluster.get("classification_summary") or summarize_cluster_classification(
        cluster
    )
    return {
        "page_type": csum.get("dominant_type", "landing"),
        "intent": csum.get("dominant_intent", "informational"),
        "decision_stage": csum.get("dominant_stage", "awareness"),
    }


def match_conditions(flat: dict[str, Any], conditions: dict[str, Any]) -> bool:
    """All condition keys must equal the corresponding value on the context dict."""
    for key, value in conditions.items():
        if flat.get(key) != value:
            return False
    return True


def evaluate_rules(cluster: dict, rules: list[dict[str, Any]]) -> dict[str, Any]:
    """
    First matching rule (by ascending priority) wins.
    `rules` items: { "conditions": dict, "outcomes": dict, "priority": int, ... }
    """
    ordered = sorted(rules, key=lambda r: int(r.get("priority", 100)))
    ctx = cluster_decision_context(cluster)
    for rule in ordered:
        cond = rule.get("conditions") or {}
        if not isinstance(cond, dict):
            continue
        if match_conditions(ctx, cond):
            out = rule.get("outcomes")
            return dict(out) if isinstance(out, dict) else {"duplication": "needs_review"}
    return {"duplication": "needs_review", "action": "review"}


def load_active_rules(session: Session) -> list[dict[str, Any]]:
    """ORM rows → dicts for evaluate_rules."""
    stmt = (
        select(DecisionRule)
        .where(DecisionRule.active.is_(True))
        .order_by(DecisionRule.priority.asc(), DecisionRule.id.asc())
    )
    rows = session.scalars(stmt).all()
    out: list[dict[str, Any]] = []
    for r in rows:
        try:
            conditions = json.loads(r.conditions_json)
            outcomes = json.loads(r.outcomes_json)
        except (json.JSONDecodeError, TypeError):
            continue
        out.append(
            {
                "id": r.id,
                "name": r.name,
                "conditions": conditions,
                "outcomes": outcomes,
                "priority": r.priority,
                "active": r.active,
            }
        )
    return out


def classify_duplication_from_rules(cluster: dict, rules: list[dict[str, Any]]) -> str:
    """Return duplication class: acceptable | competitive | needs_review."""
    outcomes = evaluate_rules(cluster, rules)
    dup = outcomes.get("duplication") or "needs_review"
    if dup in ("acceptable", "competitive", "needs_review"):
        return dup
    return "needs_review"


def decision_reason_from_outcomes(outcomes: dict[str, Any], dup_class: str) -> str:
    custom = (outcomes.get("reason") or "").strip()
    if custom:
        return custom
    return {
        "acceptable": "Duplication is appropriate for this content type",
        "competitive": "Pages compete for the same decision-stage intent",
        "needs_review": "Duplication may require strategic differentiation",
    }.get(dup_class, "Duplication may require strategic differentiation")
