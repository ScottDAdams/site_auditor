"""Benchmark bands and score-pillar weights for audit reporting."""


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
    Pillar weights used in the content health model (must sum to 1.0).
    Overlap-driven issues map to Content Quality.
    """
    return {
        "Content Quality": 0.25,
        "Crawl & index health": 0.20,
        "Authority & topical depth": 0.20,
        "Engagement readiness": 0.20,
        "Trust & clarity": 0.15,
    }
