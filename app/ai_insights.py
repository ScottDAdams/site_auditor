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


_SHARED_RULES = """
Every statement must be tied to a real URL from the data or a real numeric metric from the payload.
Avoid generic verbs alone such as "improve", "optimize", or "enhance" without saying what changes on which URL or path.
If your response could apply to any website, it is wrong.
"""


class LLMClient:
    """OpenAI chat with JSON object responses for structured outputs."""

    def __init__(self):
        self._client = OpenAI()

    def generate(self, prompt: str) -> str:
        model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
        response = self._client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.25,
        )
        msg = response.choices[0].message
        return (msg.content or "").strip()

    def generate_json(self, prompt: str) -> dict:
        model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
        response = self._client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.25,
            response_format={"type": "json_object"},
        )
        text = response.choices[0].message.content or "{}"
        return json.loads(text)


def generate_ai_insights(payload, llm_client):
    data = json.dumps(payload, indent=2, default=str)
    prompt = f"""We are upgrading the site auditor from a detection tool into a decision engine.
The output must take a clear stance, be grounded in real data (URLs + metrics), and avoid generic consulting filler.

{_SHARED_RULES}

You are a senior digital strategy consultant.

Analyze the dataset and return structured JSON only (no markdown).

RULES:
- Take a clear stance (no hedging)
- Identify ONE core structural problem
- Recommend ONE primary strategic direction
- Use real URLs from the payload as examples (cite them in core_problem and supporting_evidence)
- Reference at least 2 quantitative metrics from payload.metrics in metric_anchors and weave values into your reasoning
- Do NOT give advice that could apply unchanged to any domain

DATA:
{data}

Return JSON with exactly these keys:
{{
  "verdict": "one bold sentence stating the core issue",
  "core_problem": "detailed explanation grounded in specific URLs",
  "recommendation": "clear strategic direction (single path)",
  "business_impact": "why this matters commercially",
  "inaction_risk": "what happens if ignored",
  "supporting_evidence": [
    {{
      "urls": ["url1", "url2"],
      "issue": "specific explanation of overlap or conflict for these URLs"
    }}
  ],
  "metric_anchors": [
    "string citing an actual metric value from the payload"
  ]
}}
"""
    return llm_client.generate_json(prompt)


def generate_execution_roadmap(payload, llm_client):
    data = json.dumps(payload, indent=2, default=str)
    prompt = f"""We are upgrading the site auditor from a detection tool into a decision engine.

{_SHARED_RULES}

You are a digital strategy operator.

Create a 30-day execution plan. Return structured JSON only (no markdown).

RULES:
- 3 to 5 steps max
- Ordered by impact (highest first)
- Each step must be specific and executable (name pages, sections, or URL patterns from the data)
- Must reference real pages or structures from the payload where possible
- No vague language

DATA:
{data}

Return JSON:
{{
  "roadmap": [
    {{
      "step": 1,
      "title": "short action title",
      "description": "exact work to be done",
      "expected_impact": "business outcome",
      "affected_urls": ["url1", "url2"]
    }}
  ]
}}
"""
    return llm_client.generate_json(prompt)


def validate_ai_output(ai_output) -> bool:
    if not isinstance(ai_output, dict):
        return False
    if not ai_output.get("verdict"):
        return False
    ev = ai_output.get("supporting_evidence")
    if not isinstance(ev, list) or len(ev) < 1:
        return False
    for item in ev:
        if not isinstance(item, dict):
            return False
        if "issue" not in item or "urls" not in item:
            return False
        if not isinstance(item.get("urls"), list):
            return False
    return True


def validate_roadmap_output(obj) -> bool:
    if not isinstance(obj, dict):
        return False
    r = obj.get("roadmap")
    if not isinstance(r, list) or len(r) < 1 or len(r) > 6:
        return False
    for item in r:
        if not isinstance(item, dict):
            return False
        if not item.get("title") or not item.get("description"):
            return False
        if "affected_urls" in item and not isinstance(item["affected_urls"], list):
            return False
    return True


def build_fallback_insights(payload: dict) -> dict:
    m = payload.get("metrics") or {}
    anchors = [
        f"overlap_rate: {m.get('overlap_rate', 0)}",
        f"avg_cluster_similarity: {m.get('avg_cluster_similarity', 0)}",
        f"content_uniqueness_score: {m.get('content_uniqueness_score', 0)}",
    ]
    evidence = []
    for g in payload.get("grouped_issues", [])[:3]:
        urls = []
        examples = g.get("examples") or []
        if examples:
            urls = (examples[0].get("pages") or [])[:4]
        evidence.append(
            {
                "urls": urls,
                "issue": f"{g.get('title', 'Issue')}: {(g.get('summary') or '')[:400]}",
            }
        )
    for cl in payload.get("clusters", []):
        if len(evidence) >= 4:
            break
        urls = cl.get("pages") or []
        if len(urls) >= 2:
            evidence.append(
                {
                    "urls": urls[:4],
                    "issue": (
                        f"Embedding cluster at similarity {cl.get('similarity')} "
                        f"links these URLs as near-duplicates."
                    ),
                }
            )
    if not evidence:
        evidence.append(
            {
                "urls": [],
                "issue": "No overlap clusters or grouped issues in this crawl sample.",
            }
        )
    return {
        "verdict": (
            "This crawl shows measurable content overlap; detailed URLs and "
            "metrics below define where to act first."
        ),
        "core_problem": (
            "Multiple URLs participate in similarity clusters or overlap pairs—see "
            "supporting evidence and detailed findings for specifics."
        ),
        "recommendation": (
            "Assign ownership of each intent to a single primary URL per topic or "
            "market, then differentiate or consolidate the rest."
        ),
        "business_impact": (
            "Overlapping destinations split authority, confuse choice, and weaken "
            "conversion and regional relevance."
        ),
        "inaction_risk": (
            "New pages will stack onto the same patterns, increasing cannibalization "
            "and maintenance cost."
        ),
        "supporting_evidence": evidence[:5],
        "metric_anchors": anchors,
    }


def build_fallback_roadmap(payload: dict) -> dict:
    steps = []
    for i, g in enumerate(payload.get("grouped_issues", [])[:5], start=1):
        urls = []
        ex = (g.get("examples") or [])[:1]
        if ex:
            urls = ex[0].get("pages", [])[:5]
        steps.append(
            {
                "step": i,
                "title": (g.get("title") or "Resolve overlap")[:100],
                "description": (g.get("summary") or "Triage and edit affected URLs.")[
                    :500
                ],
                "expected_impact": (
                    "Clearer user paths and stronger topical signals per URL."
                ),
                "affected_urls": urls,
            }
        )
    if not steps:
        steps.append(
            {
                "step": 1,
                "title": "Validate crawl scope",
                "description": (
                    "Re-run the audit with full priority URLs if none were flagged."
                ),
                "expected_impact": "Ensures decisions are based on representative pages.",
                "affected_urls": [],
            }
        )
    return {"roadmap": steps[:5]}
