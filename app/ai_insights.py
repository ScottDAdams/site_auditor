import json
import os

from openai import OpenAI


def compute_audit_metrics(pages, clusters, all_findings):
    """
    Quantitative signals for the AI layer and payload.

    overlap_rate: share of crawled pages that appear in at least one overlap signal
    (cluster membership or a finding).
    avg_cluster_similarity: mean avg_similarity across multi-page clusters.
    content_uniqueness_score: 0–1, higher when duplicate clusters are less similar
    (no clusters → 1.0).
    """
    n = len(pages)
    if n == 0:
        return {
            "overlap_rate": 0.0,
            "avg_cluster_similarity": 0.0,
            "content_uniqueness_score": 1.0,
        }

    involved = set()
    for c in clusters:
        for p in c.get("pages", []):
            u = p.get("url") if isinstance(p, dict) else p
            if u:
                involved.add(u)
    for f in all_findings:
        for u in f.get("pages", []):
            if isinstance(u, dict):
                u = u.get("url")
            if u:
                involved.add(u)

    overlap_rate = round(min(1.0, len(involved) / n), 4)

    sims = [
        float(c.get("avg_similarity", 0))
        for c in clusters
        if c.get("pages") and len(c["pages"]) > 1
    ]
    avg_sim = round(sum(sims) / len(sims), 4) if sims else 0.0

    if not sims:
        uniqueness = 1.0
    else:
        uniqueness = round(max(0.0, min(1.0, 1.0 - avg_sim)), 4)

    return {
        "overlap_rate": overlap_rate,
        "avg_cluster_similarity": avg_sim,
        "content_uniqueness_score": uniqueness,
    }


class LLMClient:
    """Thin wrapper for chat completion (same API key as embeddings)."""

    def __init__(self):
        self._client = OpenAI()

    def generate(self, prompt: str) -> str:
        model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
        response = self._client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.35,
        )
        msg = response.choices[0].message
        return (msg.content or "").strip()


def generate_ai_insights(payload, llm_client):
    data = json.dumps(payload, indent=2, default=str)
    prompt = f"""You are a senior digital strategy consultant.

Based on the data, you must:

1. Identify the single most important structural problem
2. Take a clear stance on what should change (not multiple options)
3. Explain why this change matters for business performance
4. Describe what will happen if no action is taken

You must reference at least 2 quantitative signals from the metrics in your reasoning (for example: overlap rate, average cluster similarity, content uniqueness score). Use these metrics to justify your conclusions—cite the actual values from the data; do not invent numbers.

Be decisive. Avoid hedging language. Do not list possibilities. Recommend a direction.

Do not merely restate the payload. Synthesize.

DATA:
{data}
"""
    return llm_client.generate(prompt)


def generate_execution_roadmap(payload, llm_client):
    data = json.dumps(payload, indent=2, default=str)
    prompt = f"""You are a digital strategy consultant.

Based on this audit, create a 30-day execution plan.

Requirements:
- 3–5 steps only
- ordered by impact (highest first)
- each step must be concrete (not vague)
- focus on structural improvements, not minor tweaks
- tie steps to the audit where possible (grouped issues, top actions, metrics)

DATA:
{data}
"""
    return llm_client.generate(prompt)
