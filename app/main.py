import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.crawler import crawl_sites
from app.embeddings import generate_embeddings
from app.clustering import cluster_pages
from app.analyzer import (
    analyze_clusters,
    analyze_overlaps,
    calculate_content_health_score,
    classify_cluster_decisions,
    compute_ai_readiness,
    detect_topic_overlap,
    group_findings,
    is_valid_cluster,
    score_label,
)
from app.ai_insights import (
    LLMClient,
    build_fallback_insights,
    build_fallback_roadmap,
    compute_audit_metrics,
    enrich_insights_decision_layer,
    finalize_roadmap,
    generate_ai_insights,
    generate_execution_roadmap,
    validate_ai_output,
    validate_roadmap_output,
)
from app.business_context import build_business_context
from app.report import generate_report
from app.utils import canonicalize_url


def _filter_roadmap_equivalent_targets(roadmap_obj: dict | None) -> dict:
    """Drop roadmap steps whose first two targets canonicalize to the same URL."""
    if not roadmap_obj or not isinstance(roadmap_obj, dict):
        return roadmap_obj or {"roadmap": []}
    valid = []
    for step in roadmap_obj.get("roadmap") or []:
        urls = step.get("target_urls") or []
        if len(urls) >= 2 and canonicalize_url(str(urls[0])) == canonicalize_url(
            str(urls[1])
        ):
            continue
        valid.append(step)
    for i, s in enumerate(valid, start=1):
        s["step"] = i
    return {**roadmap_obj, "roadmap": valid}

app = FastAPI()

STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

FAVICON_PATH = Path(__file__).resolve().parent.parent / "templates" / "favicon.ico"

jinja_env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html", "xml"]),
)

templates = Jinja2Templates(directory="templates")
templates.env = jinja_env

STATE = {
    "status": "idle",
    "pages": [],
    "clusters": [],
    "findings": [],
    "report": ""
}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(
        FAVICON_PATH,
        media_type="image/x-icon",
        filename="favicon.ico",
    )


def normalize_site_seed(url: str) -> str | None:
    url = url.strip()

    if not url:
        return None

    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    return url


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    safe_state = {
        "status": STATE.get("status"),
        "clusters": [
            {
                "avg_similarity": c.get("avg_similarity"),
                "dominant_url": c.get("dominant_url"),
                "competing_urls": c.get("competing_urls"),
                "decision_type": c.get("decision_type"),
                "pages": [
                    {"url": p.get("url"), "type": p.get("type")}
                    for p in c.get("pages", [])
                ],
            }
            for c in STATE.get("clusters", [])
        ],
        "report": STATE.get("report", "")
    }

    return templates.TemplateResponse(
        request,
        "index.html",
        {"state": safe_state},
    )


@app.post("/run-audit")
def run_audit(sites: str = Form(...)):
    STATE["status"] = "running"

    site_list = [normalize_site_seed(s) for s in sites.split(",")]
    site_list = [s for s in site_list if s]

    print("---- AUDIT START ----")
    print("Normalized Sites:", site_list)

    pages = crawl_sites(site_list)
    print("Pages:", len(pages))

    embeddings = generate_embeddings(pages)
    print("Embeddings:", len(embeddings))

    clusters = cluster_pages(pages, embeddings)
    classify_cluster_decisions(clusters)
    print("Clusters:", len(clusters))

    strategic_clusters = [
        c for c in clusters if c.get("decision_type") == "strategic"
    ]
    findings = analyze_clusters(strategic_clusters)
    print("Findings:", len(findings))

    overlaps = detect_topic_overlap(pages, embeddings, clusters)
    overlap_findings = analyze_overlaps(overlaps)
    print("Topic overlap pairs:", len(overlap_findings))

    all_findings = findings + overlap_findings

    grouped_issues = group_findings(all_findings)

    ai_readiness = compute_ai_readiness(pages)

    score = calculate_content_health_score(
        all_findings, grouped_issues, clusters, ai_readiness
    )
    label = score_label(score)

    metrics = compute_audit_metrics(pages, clusters, all_findings)
    business_context = build_business_context(pages)

    def _cluster_payload_row(c):
        return {
            "similarity": c["avg_similarity"],
            "dominant_url": c.get("dominant_url"),
            "competing_urls": c.get("competing_urls") or [],
            "pages": [p["url"] for p in c["pages"][:8]],
            "decision_type": c.get("decision_type"),
            "technical_issue": c.get("technical_issue"),
            "technical_fix_recommendation": c.get("technical_fix_recommendation"),
        }

    cluster_rows = [_cluster_payload_row(c) for c in clusters[:20]]
    strategic_rows = [r for r in cluster_rows if r.get("decision_type") == "strategic"]

    technical_fix_urls: list[str] = []
    for c in clusters:
        if c.get("decision_type") != "technical_fix":
            continue
        for p in c.get("pages") or []:
            u = p.get("url")
            if u:
                technical_fix_urls.append(u)
    technical_fix_urls = list(dict.fromkeys(technical_fix_urls))

    analysis_payload = {
        "business_context": business_context,
        "summary": {
            "pages": len(pages),
            "clusters": len(clusters),
            "high_issues": sum(
                1 for f in all_findings if f.get("priority") == "HIGH"
            ),
            "medium_issues": sum(
                1 for f in all_findings if f.get("priority") == "MEDIUM"
            ),
        },
        "metrics": {
            "overlap_rate": metrics["overlap_rate"],
            "avg_cluster_similarity": metrics["avg_cluster_similarity"],
            "content_uniqueness_score": metrics["content_uniqueness_score"],
        },
        "grouped_issues": grouped_issues,
        "ai_readiness": ai_readiness,
        "page_urls": [p["url"] for p in pages],
        "clusters": cluster_rows,
        "strategic_clusters": strategic_rows,
        "technical_fix_urls": technical_fix_urls,
    }

    payload_for_ai = {
        **{k: v for k, v in analysis_payload.items() if k != "strategic_clusters"},
        "clusters": list(strategic_rows),
        "technical_fix_urls": technical_fix_urls,
    }

    ai_insights = build_fallback_insights(analysis_payload)
    execution_roadmap = build_fallback_roadmap(analysis_payload)

    if os.getenv("OPENAI_API_KEY"):
        llm = LLMClient()
        try:
            raw_insights = generate_ai_insights(payload_for_ai, llm)
            if validate_ai_output(raw_insights):
                ai_insights = raw_insights
            else:
                fb = build_fallback_insights(analysis_payload)
                fb["verdict"] = (
                    "Technical duplication dominates the crawl; no structural consolidation is required."
                )
                ai_insights = fb
        except Exception as exc:
            fb = build_fallback_insights(analysis_payload)
            anchor = ""
            for c in analysis_payload.get("clusters") or []:
                if c.get("dominant_url"):
                    anchor = str(c["dominant_url"])
                    break
            if not anchor and analysis_payload.get("page_urls"):
                anchor = analysis_payload["page_urls"][0]
            fb["verdict"] = (
                f"AI call failed ({exc}); using crawl-backed narrative"
                f"{f' from {anchor}' if anchor else ''}."
            )
            ai_insights = fb
        try:
            raw_roadmap = generate_execution_roadmap(payload_for_ai, llm)
            if validate_roadmap_output(
                raw_roadmap, analysis_payload.get("business_context")
            ):
                execution_roadmap = raw_roadmap
            else:
                execution_roadmap = build_fallback_roadmap(analysis_payload)
        except Exception:
            execution_roadmap = build_fallback_roadmap(analysis_payload)

    execution_roadmap = _filter_roadmap_equivalent_targets(execution_roadmap)
    execution_roadmap = finalize_roadmap(execution_roadmap)

    ai_insights = enrich_insights_decision_layer(ai_insights, analysis_payload)

    report = generate_report(
        all_findings,
        grouped_issues,
        score,
        label,
        pages,
        clusters,
        ai_readiness,
        report_metrics=metrics,
        ai_insights=ai_insights,
        execution_roadmap=execution_roadmap,
    )

    STATE.update({
        "status": "done",
        "pages": pages,
        "clusters": [c for c in clusters if is_valid_cluster(c)],
        "findings": all_findings,
        "report": report
    })

    return RedirectResponse(url="/", status_code=303)
