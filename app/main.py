import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.crawler import crawl_sites
from app.embeddings import generate_embeddings
from app.clustering import cluster_pages
from app.analyzer import (
    analyze_clusters,
    analyze_overlaps,
    calculate_content_health_score,
    compute_ai_readiness,
    detect_topic_overlap,
    generate_top_actions,
    group_findings,
    is_valid_cluster,
    score_label,
)
from app.ai_insights import (
    LLMClient,
    compute_audit_metrics,
    generate_ai_insights,
    generate_execution_roadmap,
)
from app.report import generate_report

app = FastAPI()

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


def normalize_url(url: str) -> str | None:
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
                "pages": [
                    {"url": p.get("url"), "type": p.get("type")}
                    for p in c.get("pages", [])
                ]
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

    site_list = [normalize_url(s) for s in sites.split(",")]
    site_list = [s for s in site_list if s]

    print("---- AUDIT START ----")
    print("Normalized Sites:", site_list)

    pages = crawl_sites(site_list)
    print("Pages:", len(pages))

    embeddings = generate_embeddings(pages)
    print("Embeddings:", len(embeddings))

    clusters = cluster_pages(pages, embeddings)
    print("Clusters:", len(clusters))

    findings = analyze_clusters(clusters)
    print("Findings:", len(findings))

    overlaps = detect_topic_overlap(pages, embeddings, clusters)
    overlap_findings = analyze_overlaps(overlaps)
    print("Topic overlap pairs:", len(overlap_findings))

    all_findings = findings + overlap_findings

    grouped_issues = group_findings(all_findings)

    top_actions = generate_top_actions(grouped_issues)

    ai_readiness = compute_ai_readiness(pages)

    score = calculate_content_health_score(
        all_findings, grouped_issues, clusters, ai_readiness
    )
    label = score_label(score)

    metrics = compute_audit_metrics(pages, clusters, all_findings)
    analysis_payload = {
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
        "top_actions": top_actions,
        "ai_readiness": ai_readiness,
        "clusters": [
            {
                "similarity": c["avg_similarity"],
                "pages": [p["url"] for p in c["pages"][:3]],
            }
            for c in clusters[:5]
        ],
    }

    ai_insights = ""
    execution_roadmap = ""
    if os.getenv("OPENAI_API_KEY"):
        llm = LLMClient()
        try:
            ai_insights = generate_ai_insights(analysis_payload, llm)
        except Exception as exc:
            ai_insights = (
                "Strategic interpretation could not be generated. "
                f"Error: {exc}"
            )
        try:
            execution_roadmap = generate_execution_roadmap(analysis_payload, llm)
        except Exception as exc:
            execution_roadmap = (
                "30-day execution plan could not be generated. "
                f"Error: {exc}"
            )
    else:
        msg = (
            "Set OPENAI_API_KEY to enable AI strategic interpretation "
            "and the 30-day execution plan for this report."
        )
        ai_insights = msg
        execution_roadmap = msg

    report = generate_report(
        all_findings,
        grouped_issues,
        top_actions,
        score,
        label,
        pages,
        clusters,
        ai_readiness,
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
