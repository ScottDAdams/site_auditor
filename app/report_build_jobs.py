"""
Background Word report builds: state in DB so POST /build can return immediately
(avoid reverse-proxy timeouts during multi-step LLM work).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.db.models import AppSetting
from app.db.session import SessionLocal


def _key(report_id: int) -> str:
    return f"report.build.job.{report_id}"


def get_report_build_state(report_id: int) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "status": "idle",
        "errors": [],
        "updated_at": None,
    }
    with SessionLocal() as db:
        row = db.get(AppSetting, _key(report_id))
        if not row or not (row.value or "").strip():
            return defaults
        try:
            data = json.loads(row.value)
        except json.JSONDecodeError:
            return defaults
        if not isinstance(data, dict):
            return defaults
        out = {**defaults, **data}
        if not isinstance(out.get("errors"), list):
            out["errors"] = []
        return out


def set_report_build_state(
    report_id: int,
    status: str,
    errors: list[str] | None = None,
) -> None:
    payload = {
        "status": status,
        "errors": list(errors or []),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    with SessionLocal() as db:
        row = db.get(AppSetting, _key(report_id))
        val = json.dumps(payload, ensure_ascii=False)
        if row:
            row.value = val
        else:
            db.add(AppSetting(key=_key(report_id), value=val))
        db.commit()
