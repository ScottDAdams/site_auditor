"""
Phase 16: paths for generated reports + light post-validation only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.paths import generated_reports_root


def _generated_dir(report_id: int) -> Path:
    return generated_reports_root() / str(report_id)


def executive_docx_path(report_id: int) -> Path:
    return _generated_dir(report_id) / "executive.docx"


def executive_synthesized_md_path(report_id: int) -> Path:
    return _generated_dir(report_id) / "executive_synthesized.md"


# Minimum body length so trivial or empty LLM output cannot pass as a report.
MIN_SYNTHESIS_CHARS = 400


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
                f"{frac:.1f}",
                str(frac),
                str(int(round(pct))),
                str(round(pct, 1)),
            ):
                if cand in compact:
                    return True
        except ValueError:
            pass
    # Similarity-style decimals in prose may use more digits than JSON (e.g. 0.8800 vs 0.88).
    if re.match(r"^0\.\d+$", t):
        try:
            v = float(t)
            for cand in (t, f"{v:.4f}", f"{v:.3f}", f"{v:.2f}", str(v)):
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
) -> dict[str, Any]:
    """
    Post-check only: non-empty, minimum length, and soft numeric grounding.
    Does not enforce section titles or writing shape.
    """
    text = (md or "").strip()
    errors: list[str] = []
    if not text:
        return {"ok": False, "errors": ["Report is empty"]}
    if len(text) < MIN_SYNTHESIS_CHARS:
        errors.append(
            f"Report is too short (minimum {MIN_SYNTHESIS_CHARS} characters)"
        )

    metrics = _metric_tokens_in_report(text)
    blob = _grounding_blob(audit_signal)
    if verification_pack:
        blob += json.dumps(verification_pack, default=str)

    ungrounded = [m for m in metrics if not _token_grounded(m, blob)]
    if len(ungrounded) > 2:
        errors.append(
            "Several numeric claims may not match audit_signal data: "
            + ", ".join(ungrounded[:5])
        )

    return {"ok": len(errors) == 0, "errors": errors}
