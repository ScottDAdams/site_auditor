"""Content rules engine (formerly admin decision rules) — mounted at /rules."""

import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DecisionRule
from app.db.session import SessionLocal

router = APIRouter(tags=["rules"])
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


@router.get("/rules", response_class=HTMLResponse)
def rules_list(request: Request, db: Session = Depends(get_db)):
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
        "rules/decision_rules.html",
        {
            "title": "Content Rules Engine",
            "page_title": "Content Rules Engine",
            "nav_active": "rules",
            "rules": cards,
        },
    )


@router.post("/rules/create")
def rules_create(
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
        return RedirectResponse(url="/rules", status_code=302)
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
    return RedirectResponse(url="/rules", status_code=303)


@router.post("/rules/{rule_id}/update")
def rules_update(
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
        return RedirectResponse(url="/rules", status_code=302)
    try:
        cond = _parse_json_field(conditions_json, "Conditions")
        out = _parse_json_field(outcomes_json, "Outcomes")
    except (json.JSONDecodeError, ValueError):
        return RedirectResponse(url="/rules", status_code=302)
    r.name = name.strip() or r.name
    r.conditions_json = json.dumps(cond, sort_keys=True)
    r.outcomes_json = json.dumps(out, sort_keys=True)
    r.priority = priority
    r.active = active == "on"
    db.commit()
    return RedirectResponse(url="/rules", status_code=303)


@router.post("/rules/{rule_id}/toggle")
def rules_toggle(rule_id: int, db: Session = Depends(get_db)):
    r = db.get(DecisionRule, rule_id)
    if r:
        r.active = not r.active
        db.commit()
    return RedirectResponse(url="/rules", status_code=303)


@router.post("/rules/{rule_id}/delete")
def rules_delete(rule_id: int, db: Session = Depends(get_db)):
    r = db.get(DecisionRule, rule_id)
    if r:
        db.delete(r)
        db.commit()
    return RedirectResponse(url="/rules", status_code=303)
