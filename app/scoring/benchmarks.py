"""Benchmark bands and score-pillar weights for audit reporting."""

import json

_SCORING_WEIGHTS_KEY = "scoring_weights_json"

_DEFAULT_WEIGHTS: dict[str, float] = {
    "Content Quality": 0.25,
    "Crawl & index health": 0.20,
    "Authority & topical depth": 0.20,
    "Engagement readiness": 0.20,
    "Trust & clarity": 0.15,
}


def classify_overlap_rate(score: float) -> tuple[str, str]:
    if score >= 0.6:
        return ("Critical", "Top 10% worst")
    elif score >= 0.45:
        return ("High", "Top 25% worst")
    elif score >= 0.3:
        return ("Moderate", "Above average")
    else:
        return ("Low", "Healthy range")


def get_scoring_weights() -> dict[str, float]:
    """
    Pillar weights used in the content health model (should sum to 1.0).
    Overlap-driven issues map to Content Quality. Values may be overridden in app_settings.
    """
    try:
        from app.db.models import AppSetting
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            row = session.get(AppSetting, _SCORING_WEIGHTS_KEY)
            if row and row.value:
                data = json.loads(row.value)
                if isinstance(data, dict) and data:
                    return {str(k): float(v) for k, v in data.items()}
    except Exception:
        pass
    return dict(_DEFAULT_WEIGHTS)


def save_scoring_weights(weights: dict[str, float]) -> None:
    """Persist pillar weights (UI /scoring)."""
    from app.db.models import AppSetting
    from app.db.session import SessionLocal

    payload = json.dumps(weights, sort_keys=True)
    with SessionLocal() as session:
        row = session.get(AppSetting, _SCORING_WEIGHTS_KEY)
        if row:
            row.value = payload
        else:
            session.add(AppSetting(key=_SCORING_WEIGHTS_KEY, value=payload))
        session.commit()


def default_scoring_weights() -> dict[str, float]:
    return dict(_DEFAULT_WEIGHTS)
