"""
Phase 16: paths for generated reports + consulting-grade post-validation.
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

# Phase 16.2 — generic filler (substring match, case-insensitive).
BANNED_PHRASES = (
    "significant",
    "various",
    "in order to",
    "plays a key role",
    "important to note",
    "helps to",
    "ensures that",
)

# At least one required (POV / opening stance).
_POV_RES = (
    re.compile(r"\bthis is not\b", re.I),
    re.compile(r"\bthe primary issue\b", re.I),
    re.compile(r"\bthe correct move\b", re.I),
    re.compile(r"\bthe problem is\b", re.I),
)

# At least one required (hierarchy / prioritization).
_PRIORITY_RES = (
    re.compile(r"\bissue\s*1\b", re.I),
    re.compile(r"\bprimary\b", re.I),
    re.compile(r"\bcritical\b", re.I),
)

# Defined action direction (decisive recommendation).
_ACTION_PATTERNS = (
    re.compile(r"\brecommend\b", re.I),
    re.compile(r"\bmust\b", re.I),
    re.compile(r"\bnext step\b", re.I),
    re.compile(r"\bcourse of action\b", re.I),
    re.compile(r"\bthe move is\b", re.I),
    re.compile(r"\baction:\s", re.I),
)

# Consequence of inaction.
_INACTION_PATTERNS = (
    re.compile(r"\binaction\b", re.I),
    re.compile(r"\bwithout action\b", re.I),
    re.compile(r"\bif nothing\b", re.I),
    re.compile(r"\bdo nothing\b", re.I),
    re.compile(r"\brisk\b", re.I),
    re.compile(r"\bconsequence\b", re.I),
    re.compile(r"\bcost of\b", re.I),
)


def _grounding_blob(audit_signal: dict[str, Any]) -> str:
    return json.dumps(audit_signal or {}, default=str)


def _metric_tokens_in_report(md: str) -> list[str]:
    """Percentages and similarity-style decimals worth checking."""
    toks: list[str] = []
    toks.extend(re.findall(r"\d+(?:\.\d+)?\s*%", md or ""))
    toks.extend(re.findall(r"\b0\.\d{2,4}\b", md or ""))
    return toks


def _has_numeric_metric(text: str) -> bool:
    """At least one concrete number (metric), beyond optional grounding check."""
    if _metric_tokens_in_report(text):
        return True
    if re.search(r"\b\d+(?:\.\d+)?\s*%", text):
        return True
    if re.search(r"\b0\.\d{2,}\b", text):
        return True
    if re.search(r"\b\d{1,3}\.\d+\b", text):
        return True
    return False


def _url_count(text: str) -> int:
    return len(re.findall(r"https?://[^\s\)<>\]\"']+", text, re.I))


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
    if re.match(r"^0\.\d+$", t):
        try:
            v = float(t)
            for cand in (t, f"{v:.4f}", f"{v:.3f}", f"{v:.2f}", str(v)):
                if cand in compact:
                    return True
        except ValueError:
            pass
    return False


def _find_banned_phrases(text: str) -> list[str]:
    lower = text.lower()
    found: list[str] = []
    for phrase in BANNED_PHRASES:
        if phrase.lower() in lower:
            found.append(phrase)
    return found


def validate_light(
    md: str,
    audit_signal: dict[str, Any],
    *,
    verification_pack: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Post-check: length, consulting signals, specificity (URLs + metrics),
    banned filler, soft numeric grounding vs audit_signal.
    """
    text = (md or "").strip()
    errors: list[str] = []
    if not text:
        return {"ok": False, "errors": ["Report is empty"]}
    if len(text) < MIN_SYNTHESIS_CHARS:
        errors.append(
            f"Report is too short (minimum {MIN_SYNTHESIS_CHARS} characters)"
        )

    banned = _find_banned_phrases(text)
    if banned:
        errors.append(
            "Banned filler phrasing present: " + ", ".join(sorted(set(banned)))
        )

    if not any(r.search(text) for r in _POV_RES):
        errors.append(
            "Missing point-of-view signal (need one of: "
            '"This is not", "The primary issue", "The correct move", "The problem is")'
        )

    if not any(r.search(text) for r in _PRIORITY_RES):
        errors.append(
            "Missing prioritization signal (need one of: Issue 1, Primary, Critical)"
        )

    n_urls = _url_count(text)
    if n_urls < 2:
        errors.append(
            f"At least two http(s) URLs are required (found {n_urls})"
        )

    if not _has_numeric_metric(text):
        errors.append(
            "At least one numeric metric is required (percent, similarity decimal, etc.)"
        )

    if not any(p.search(text) for p in _ACTION_PATTERNS):
        errors.append(
            "Missing defined action direction "
            "(e.g. recommend, must, next step, course of action)"
        )

    if not any(p.search(text) for p in _INACTION_PATTERNS):
        errors.append(
            "Missing consequence of inaction (e.g. inaction, risk, consequence, cost of)"
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
