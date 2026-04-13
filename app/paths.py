"""
Filesystem layout for durable data (SQLite, generated_reports).

On Fly.io with multiple machines, each VM has its own disk: use a single machine
and/or Postgres (DATABASE_URL). For SQLite + local artifacts, set SITE_AUDITOR_DATA
to a mounted volume path so data survives restarts.
"""

from __future__ import annotations

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def site_auditor_data_dir() -> Path:
    """
    Directory holding ``site_auditor.db`` when using default SQLite.

    If env ``SITE_AUDITOR_DATA`` is set (e.g. ``/data/site_auditor`` on a Fly volume),
    the database file lives there. Otherwise: ``<project>/data``.
    """
    raw = os.getenv("SITE_AUDITOR_DATA", "").strip()
    if raw:
        p = Path(raw)
        p.mkdir(parents=True, exist_ok=True)
        return p
    return _PROJECT_ROOT / "data"


def sqlite_database_path() -> Path:
    return site_auditor_data_dir() / "site_auditor.db"


def generated_reports_root() -> Path:
    """
    Per-report folders (``executive_synthesized.md``, ``audit_signal.json``, …).

    With ``SITE_AUDITOR_DATA``: ``<SITE_AUDITOR_DATA>/generated_reports``.
    Otherwise legacy: ``<project>/generated_reports``.
    """
    raw = os.getenv("SITE_AUDITOR_DATA", "").strip()
    if raw:
        p = Path(raw) / "generated_reports"
        p.mkdir(parents=True, exist_ok=True)
        return p
    return _PROJECT_ROOT / "generated_reports"
