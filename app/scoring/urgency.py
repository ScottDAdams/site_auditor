def classify_urgency(overlap_rate: float, cluster_count: int) -> str:
    if overlap_rate > 0.45 and cluster_count >= 3:
        return "Immediate"
    elif overlap_rate > 0.35:
        return "High"
    return "Moderate"
