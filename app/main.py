from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.crawler import crawl_sites
from app.embeddings import generate_embeddings
from app.clustering import cluster_pages
from app.analyzer import analyze_clusters
from app.report import generate_report

app = FastAPI()
templates = Jinja2Templates(directory="templates")

STATE = {
    "status": "idle",
    "pages": [],
    "clusters": [],
    "findings": [],
    "report": ""
}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "state": STATE})


@app.post("/run-audit")
def run_audit(sites: str = Form(...)):
    STATE["status"] = "running"

    site_list = [s.strip() for s in sites.split(",")]

    pages = crawl_sites(site_list)
    embeddings = generate_embeddings(pages)
    clusters = cluster_pages(pages, embeddings)
    findings = analyze_clusters(clusters)
    report = generate_report(findings)

    STATE.update({
        "status": "done",
        "pages": pages,
        "clusters": clusters,
        "findings": findings,
        "report": report
    })

    return RedirectResponse(url="/", status_code=303)
