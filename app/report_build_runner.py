"""
Execute Word report build in a worker thread (see report_build_jobs for status).
"""

from __future__ import annotations

import json

from app.db.models import AuditReport
from app.db.session import SessionLocal
from app.report_build_jobs import set_report_build_state
from app.reporting.audit_signal import load_audit_signal, save_audit_signal_file
from app.reporting.executive_content import (
    executive_docx_path,
    validate_light,
)
from app.reporting.executive_writer import write_executive_report
from app.reporting.report_builder import build_executive_docx


def run_report_build(report_id: int) -> None:
    try:
        with SessionLocal() as db:
            row = db.get(AuditReport, report_id)
        if not row:
            set_report_build_state(report_id, "error", ["Audit not found."])
            return

        try:
            snapshot = json.loads(row.snapshot_json or "{}")
        except json.JSONDecodeError:
            snapshot = {}
        if not isinstance(snapshot, dict):
            snapshot = {}

        es = snapshot.get("executive_summary_data") or {}
        if not isinstance(es, dict):
            es = {}

        audit_signal = load_audit_signal(snapshot)
        vp = snapshot.get("verification_pack")
        if not isinstance(vp, dict):
            vp = es.get("verification_pack") if isinstance(es.get("verification_pack"), dict) else {}

        technical_md = str(snapshot.get("technical_report_md") or "").strip()

        # Single-pass synthesis: only primary signal, evidence pack, and raw technical text.
        # Do not pass pre-written executive copy or boardroom brief into the writer.
        context = {
            "audit_signal": audit_signal,
            "verification_pack": vp,
            "technical_md": technical_md,
        }

        out_dir = executive_docx_path(report_id).parent
        out_dir.mkdir(parents=True, exist_ok=True)
        save_audit_signal_file(report_id, audit_signal)

        try:
            synthesized_md = write_executive_report(context)
        except RuntimeError as exc:
            set_report_build_state(report_id, "error", [str(exc)])
            return

        val = validate_light(
            synthesized_md,
            audit_signal,
            verification_pack=vp,
        )
        if not val.get("ok"):
            set_report_build_state(
                report_id,
                "error",
                val.get("errors") or ["Validation failed."],
            )
            return

        syn_path = out_dir / "executive_synthesized.md"
        docx_path = out_dir / "executive.docx"
        syn_path.write_text(synthesized_md, encoding="utf-8")
        build_executive_docx(str(syn_path), str(docx_path))

        set_report_build_state(report_id, "success", [])
    except Exception as exc:  # pragma: no cover - safety net
        set_report_build_state(report_id, "error", [str(exc)])
