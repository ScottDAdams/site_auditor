import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DecisionRule
from app.db.session import SessionLocal

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _parse_json_field(raw: str, label: str) -> dict:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError(f"{label} must be valid JSON")
    return json.loads(raw)


@router.get("", response_class=HTMLResponse)
def admin_root():
    return RedirectResponse(url="/admin/decision-rules", status_code=302)


@router.get("/ai-engines", response_class=HTMLResponse)
def admin_ai_engines(request: Request):
    return templates.TemplateResponse(
        request,
        "admin/placeholder.html",
        {
            "title": "AI Engines",
            "page_heading": "AI Engines",
            "body": "Configure model endpoints and parameters here (coming soon).",
        },
    )


@router.get("/ai-prompts", response_class=HTMLResponse)
def admin_ai_prompts(request: Request):
    return templates.TemplateResponse(
        request,
        "admin/placeholder.html",
        {
            "title": "AI Prompts",
            "page_heading": "AI Prompts",
            "body": "Manage prompt templates and versions (coming soon).",
        },
    )


@router.get("/scoring-weights", response_class=HTMLResponse)
def admin_scoring_weights(request: Request):
    return templates.TemplateResponse(
        request,
        "admin/placeholder.html",
        {
            "title": "Scoring Weights",
            "page_heading": "Scoring Weights",
            "body": "Tune pillar weights and thresholds (coming soon).",
        },
    )


@router.get("/decision-rules", response_class=HTMLResponse)
def admin_decision_rules_list(request: Request, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(DecisionRule).order_by(DecisionRule.priority.asc(), DecisionRule.id.asc())
    ).all()
    cards = []
    for r in rows:
        try:
            cond = json.loads(r.conditions_json)
            out = json.loads(r.outcomes_json)
        except json.JSONDecodeError:
            cond, out = {}, {}
        cards.append(
            {
                "id": r.id,
                "name": r.name,
                "conditions": cond,
                "outcomes": out,
                "conditions_json": r.conditions_json,
                "outcomes_json": r.outcomes_json,
                "priority": r.priority,
                "active": r.active,
            }
        )
    return templates.TemplateResponse(
        request,
        "admin/decision_rules.html",
        {"title": "Decision Rules", "page_heading": "Decision Rules", "rules": cards},
    )


@router.post("/decision-rules/create")
def admin_decision_rules_create(
    name: str = Form(...),
    conditions_json: str = Form(...),
    outcomes_json: str = Form(...),
    priority: int = Form(100),
    active: str | None = Form(None),
    db: Session = Depends(get_db),
):
    try:
        cond = _parse_json_field(conditions_json, "Conditions")
        out = _parse_json_field(outcomes_json, "Outcomes")
    except (json.JSONDecodeError, ValueError):
        return RedirectResponse(url="/admin/decision-rules", status_code=302)
    db.add(
        DecisionRule(
            name=name.strip() or "Untitled rule",
            conditions_json=json.dumps(cond, sort_keys=True),
            outcomes_json=json.dumps(out, sort_keys=True),
            priority=priority,
            active=(active == "on"),
        )
    )
    db.commit()
    return RedirectResponse(url="/admin/decision-rules", status_code=303)


@router.post("/decision-rules/{rule_id}/update")
def admin_decision_rules_update(
    rule_id: int,
    name: str = Form(...),
    conditions_json: str = Form(...),
    outcomes_json: str = Form(...),
    priority: int = Form(100),
    active: str = Form(""),
    db: Session = Depends(get_db),
):
    r = db.get(DecisionRule, rule_id)
    if not r:
        return RedirectResponse(url="/admin/decision-rules", status_code=302)
    try:
        cond = _parse_json_field(conditions_json, "Conditions")
        out = _parse_json_field(outcomes_json, "Outcomes")
    except (json.JSONDecodeError, ValueError):
        return RedirectResponse(url="/admin/decision-rules", status_code=302)
    r.name = name.strip() or r.name
    r.conditions_json = json.dumps(cond, sort_keys=True)
    r.outcomes_json = json.dumps(out, sort_keys=True)
    r.priority = priority
    r.active = active == "on"
    db.commit()
    return RedirectResponse(url="/admin/decision-rules", status_code=303)


@router.post("/decision-rules/{rule_id}/toggle")
def admin_decision_rules_toggle(rule_id: int, db: Session = Depends(get_db)):
    r = db.get(DecisionRule, rule_id)
    if r:
        r.active = not r.active
        db.commit()
    return RedirectResponse(url="/admin/decision-rules", status_code=303)


@router.post("/decision-rules/{rule_id}/delete")
def admin_decision_rules_delete(rule_id: int, db: Session = Depends(get_db)):
    r = db.get(DecisionRule, rule_id)
    if r:
        db.delete(r)
        db.commit()
    return RedirectResponse(url="/admin/decision-rules", status_code=303)
