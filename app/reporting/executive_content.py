"""
Phase 16: paths for generated reports + light post-validation only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _generated_dir(report_id: int) -> Path:
    root = Path(__file__).resolve().parent.parent.parent / "generated_reports"
    return root / str(report_id)


def executive_docx_path(report_id: int) -> Path:
    return _generated_dir(report_id) / "executive.docx"


def executive_synthesized_md_path(report_id: int) -> Path:
    return _generated_dir(report_id) / "executive_synthesized.md"


LIGHT_REQUIRED_SECTIONS = (
    "Executive Summary",
    "Core Problem",
    "Why It Matters",
    "Evidence",
    "Recommended Action",
    "Execution Plan",
    "Risks of Inaction",
    "Expected Outcomes",
)


def _extract_h2_titles(md: str) -> list[str]:
    titles: list[str] = []
    for m in re.finditer(r"(?m)^##\s+(.+?)\s*$", md or ""):
        titles.append(m.group(1).strip())
    return titles


def _grounding_blob(audit_signal: dict[str, Any]) -> str:
    return json.dumps(audit_signal or {}, default=str)


def _metric_tokens_in_report(md: str) -> list[str]:
    """Percentages and similarity-style decimals worth checking."""
    toks: list[str] = []
    toks.extend(re.findall(r"\d+(?:\.\d+)?\s*%", md or ""))
    toks.extend(re.findall(r"\b0\.\d{2,4}\b", md or ""))
    return toks


def _token_grounded(token: str, blob: str) -> bool:
    compact = blob.replace(" ", "")
    t = token.replace(" ", "")
    if t in compact:
        return True
    if t.endswith("%"):
        try:
            pct = float(t.rstrip("%"))
            frac = pct / 100.0
            for cand in (
                f"{frac:.4f}",
                f"{frac:.3f}",
                f"{frac:.2f}",
                str(int(round(pct))),
                str(round(pct, 1)),
            ):
                if cand in compact:
                    return True
        except ValueError:
            pass
    return False


def validate_light(
    md: str,
    audit_signal: dict[str, Any],
    *,
    verification_pack: dict[str, Any] | None = None,
    boardroom_brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Post-check only: non-empty, required ## sections, >=2 metric-like tokens,
    soft grounding against audit_signal (+ optional packs).
    """
    text = (md or "").strip()
    errors: list[str] = []
    if not text:
        return {"ok": False, "errors": ["Report is empty"]}

    titles = _extract_h2_titles(text)
    for req in LIGHT_REQUIRED_SECTIONS:
        if req not in titles:
            errors.append(f"Missing required section: ## {req}")

    metrics = _metric_tokens_in_report(text)
    if len(metrics) < 2:
        errors.append(
            "At least two metric-style values (e.g. percentages or 0.xx similarities) are required"
        )

    blob = _grounding_blob(audit_signal)
    if verification_pack:
        blob += json.dumps(verification_pack, default=str)
    if boardroom_brief:
        blob += json.dumps(boardroom_brief, default=str)

    ungrounded = [m for m in metrics if not _token_grounded(m, blob)]
    if len(ungrounded) > 2:
        errors.append(
            "Several numeric claims may not match audit_signal data: "
            + ", ".join(ungrounded[:5])
        )

    return {"ok": len(errors) == 0, "errors": errors}
