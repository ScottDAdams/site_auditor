"""
Execute Word report build in a worker thread (see report_build_jobs for status).
"""

from __future__ import annotations

import json

from app.db.models import AuditReport
from app.db.session import SessionLocal
from app.report_build_jobs import set_report_build_state
from app.reporting.audit_signal import load_audit_signal, save_audit_signal_file
from app.reporting.compression import compress_report
from app.reporting.executive_content import (
    executive_docx_path,
    validate_executive_content,
)
from app.reporting.executive_pov import derive_strategic_pov
from app.reporting.evidence_selection import select_top_proof
from app.reporting.executive_writer import build_core_argument, write_executive_report
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

        audit_signal = load_audit_signal(snapshot)
        out_dir = executive_docx_path(report_id).parent
        out_dir.mkdir(parents=True, exist_ok=True)
        save_audit_signal_file(report_id, audit_signal)

        try:
            strategic_pov = derive_strategic_pov(audit_signal)
        except RuntimeError as exc:
            set_report_build_state(report_id, "error", [str(exc)])
            return

        pov_path = out_dir / "strategic_pov.json"
        pov_path.write_text(
            json.dumps(strategic_pov, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        proof = select_top_proof(audit_signal, strategic_pov)
        core_argument = build_core_argument(strategic_pov)

        try:
            draft_md = write_executive_report(core_argument, proof)
            synthesized_md = compress_report(draft_md)
        except RuntimeError as exc:
            set_report_build_state(report_id, "error", [str(exc)])
            return

        val = validate_executive_content(synthesized_md)
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
