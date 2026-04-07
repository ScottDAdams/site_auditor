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
from app.analyzer import analyze_clusters, is_valid_cluster
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

    report = generate_report(findings)

    STATE.update({
        "status": "done",
        "pages": pages,
        "clusters": [c for c in clusters if is_valid_cluster(c)],
        "findings": findings,
        "report": report
    })

    return RedirectResponse(url="/", status_code=303)
