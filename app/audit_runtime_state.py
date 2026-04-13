"""
Cross-worker audit progress (DB-backed).

In-memory STATE is per process; gunicorn/uvicorn multi-worker deploys otherwise show
idle on /audit and skip polling. This module is the source of truth for status/phase.
"""

from __future__ import annotations

import json
from typing import Any

from app.db.models import AppSetting
from app.db.session import SessionLocal

_RUNTIME_KEY = "audit.runtime.v1"

_DEFAULTS: dict[str, Any] = {
    "status": "idle",
    "phase": "",
    "error": None,
    "last_report_id": None,
    "summary_metrics": None,
}


def get_audit_runtime() -> dict[str, Any]:
    out = dict(_DEFAULTS)
    with SessionLocal() as db:
        row = db.get(AppSetting, _RUNTIME_KEY)
        if not row or not (row.value or "").strip():
            return out
        try:
            data = json.loads(row.value)
        except json.JSONDecodeError:
            return out
        if isinstance(data, dict):
            out.update(data)
    return out


def merge_audit_runtime(updates: dict[str, Any]) -> None:
    """Merge keys into persisted runtime (short transaction)."""
    with SessionLocal() as db:
        row = db.get(AppSetting, _RUNTIME_KEY)
        data = dict(_DEFAULTS)
        if row and (row.value or "").strip():
            try:
                loaded = json.loads(row.value)
                if isinstance(loaded, dict):
                    data.update(loaded)
            except json.JSONDecodeError:
                pass
        data.update(updates)
        payload = json.dumps(data, default=str)
        if row:
            row.value = payload
        else:
            db.add(AppSetting(key=_RUNTIME_KEY, value=payload))
        db.commit()
