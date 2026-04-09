"""
Validate and enrich executive markdown before deterministic DOCX rendering (Phase 12).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.reporting.report_builder import parse_executive_markdown_sections

_SECTION_HEADERS = (
    "01 Executive Summary",
    "02 What Is Breaking Performance",
    "03 If You Do One Thing",
    "04 Execution Plan",
    "05 Risks of Inaction",
    "06 Expected Outcomes",
)

_NOT_PROVIDED_RE = re.compile(r"\bnot\s+provided\.?", re.I)


def generated_report_dir(report_id: int) -> Path:
    """Persisted client deliverables: generated_reports/{id}/"""
    root = Path(__file__).resolve().parent.parent.parent
    return root / "generated_reports" / str(int(report_id))


def executive_docx_path(report_id: int) -> Path:
    return generated_report_dir(report_id) / "executive.docx"


def validate_executive_content(md: str) -> dict[str, Any]:
    """
    Return structured validation result for enriched executive markdown.

    {
      "ok": bool,
      "errors": [str, ...],
    }
    """
    errors: list[str] = []
    t = (md or "").strip()
    if not t:
        return {"ok": False, "errors": ["Executive markdown is empty."]}

    low = t.lower()
    if _NOT_PROVIDED_RE.search(t):
        errors.append('Content must not contain placeholder phrasing "Not provided".')

    for h in _SECTION_HEADERS:
        if h.lower() not in low:
            errors.append(f"Missing mandatory section: {h}")

    sections = parse_executive_markdown_sections(t)
    for key, label in (
        ("executive_summary", "01 Executive Summary"),
        ("breaking", "02 What Is Breaking Performance"),
        ("primary_action", "03 If You Do One Thing"),
        ("execution", "04 Execution Plan"),
        ("risks", "05 Risks of Inaction"),
        ("outcomes", "06 Expected Outcomes"),
    ):
        lines = [x.strip() for x in (sections.get(key) or []) if x.strip()]
        if not lines:
            errors.append(f"Section has no body content: {label}")

    es_lines = sections.get("executive_summary") or []
    blob = " ".join(es_lines).lower()
    has_core = "core problem" in blob
    has_action = "primary action" in blob or "the correct move is to" in blob
    has_impact = "business impact" in blob
    if not (has_core and has_action and has_impact):
        errors.append(
            "Executive Summary must state Core Problem, Primary Action (or the correct move), "
            "and Business Impact in plain language."
        )

    return {"ok": len(errors) == 0, "errors": errors}


def _human_overlap_sentence(overlap_rate: float | None, cluster_n: int | None) -> str:
    parts: list[str] = []
    if overlap_rate is not None:
        try:
            r = float(overlap_rate)
            if 0 <= r <= 1:
                pct = int(round(r * 100))
                parts.append(
                    f"About {pct} percent of sampled pages sit in overlap or conflict groups, "
                    f"so demand and authority split instead of compounding."
                )
        except (TypeError, ValueError):
            pass
    if cluster_n is not None:
        try:
            n = int(cluster_n)
            if n > 0:
                parts.append(
                    f"The crawl surfaced {n} structural cluster(s) that need a single coherent response."
                )
        except (TypeError, ValueError):
            pass
    if not parts:
        return (
            "Structural overlap splits buyer attention across parallel URLs, which weakens conversion capture."
        )
    return " ".join(parts)


def _ensure_exec_summary_labels(md: str, metrics: dict[str, Any] | None) -> str:
    """Inject labeled lines into Executive Summary when missing."""
    sections = parse_executive_markdown_sections(md)
    es = sections.get("executive_summary") or []
    blob = "\n".join(es).lower()
    m = metrics or {}
    overlap = m.get("overlap_rate")
    clusters = m.get("cluster_count")

    extra: list[str] = []
    if "core problem:" not in blob and "core problem" not in blob:
        extra.append(
            "Core Problem: Overlapping pages compete for the same buyer decision and split demand."
        )
    if "primary action:" not in blob and "the correct move is to" not in blob:
        extra.append(
            "Primary Action: The correct move is to assign one primary URL per major decision "
            "and align the rest as support or redirects."
        )
    if "business impact:" not in blob and "business impact" not in blob:
        extra.append(f"Business Impact: {_human_overlap_sentence(overlap, clusters)}")

    if not extra:
        return md

    lines = md.splitlines()
    out: list[str] = []
    inserted = False
    for line in lines:
        out.append(line)
        if _norm_heading(line) == "executive summary" and not inserted:
            out.extend(extra)
            inserted = True
    if not inserted:
        out = ["01 Executive Summary", *extra, "", *lines]
    return "\n".join(out).strip() + "\n"


def _norm_heading(line: str) -> str:
    x = (line or "").strip()
    x = re.sub(r"^#+\s*", "", x)
    x = re.sub(r"^\d+\s*", "", x)
    return x.strip(": ").lower()


def _strip_not_provided_replacements(text: str) -> str:
    t = text or ""
    t = _NOT_PROVIDED_RE.sub(
        "See crawl-backed proof in the appendix.", t
    )
    return t


def _build_technical_appendix_from_verification(pack: dict[str, Any] | None) -> str:
    if not pack or not isinstance(pack, dict):
        return ""
    proofs = pack.get("cluster_proofs") or []
    if not isinstance(proofs, list):
        return ""
    lines: list[str] = []
    for pr in proofs[:12]:
        if not isinstance(pr, dict):
            continue
        cid = str(pr.get("cluster_id") or "cluster").strip()
        lines.append(f"Cluster: {cid}")
        urls = pr.get("urls") or []
        if isinstance(urls, list):
            for u in urls[:4]:
                if str(u).strip().startswith("http"):
                    lines.append(str(u).strip())
        diff_s = str(pr.get("diff_summary") or "").strip()
        if diff_s:
            lines.append(f"Example: {diff_s}")
        ovs = pr.get("overlap_sections") or []
        if isinstance(ovs, list) and ovs:
            first = ovs[0] if isinstance(ovs[0], dict) else {}
            h = str(first.get("heading") or "").strip()
            if h:
                lines.append(f"Overlap section: {h}")
        sim = pr.get("similarity_score")
        interp = diff_s
        if sim is not None:
            try:
                pct = int(round(float(sim) * 100))
                interp = f"Crawl similarity signal is about {pct} percent for the paired URLs. {diff_s}".strip()
            except (TypeError, ValueError):
                pass
        if interp:
            lines.append(f"Interpretation: {interp}")
        lines.append("")
    return "\n".join(lines).strip()


_DISPLAY_HEADER = {
    "breaking": "02 What Is Breaking Performance",
    "execution": "04 Execution Plan",
    "risks": "05 Risks of Inaction",
    "outcomes": "06 Expected Outcomes",
}


def _pad_section_if_empty(
    md: str, section_key: str, header_norm: str, filler_lines: list[str]
) -> str:
    sections = parse_executive_markdown_sections(md)
    if sections.get(section_key):
        return md
    lines = md.splitlines()
    out: list[str] = []
    inserted = False
    for line in lines:
        out.append(line)
        if _norm_heading(line) == header_norm and not inserted:
            out.extend(filler_lines)
            inserted = True
    if not inserted:
        dh = _DISPLAY_HEADER.get(section_key) or header_norm
        out = [dh, *filler_lines, "", *lines]
    return "\n".join(out).strip() + "\n"


def enrich_executive_content(
    md: str,
    verification_pack: dict[str, Any] | None,
    boardroom_brief: dict[str, Any] | None,
    metrics: dict[str, Any] | None,
) -> tuple[str, str]:
    """
    Return (enriched_executive_md, technical_appendix_md).

    Enrichment is deterministic: fills labels, removes placeholder phrasing,
    and builds a technical appendix string from verification_pack for DOCX rendering.
    """
    _ = boardroom_brief  # reserved for future slide alignment hints
    t = (md or "").strip()
    if not t:
        return "", ""

    m = dict(metrics or {})
    if "cluster_count" not in m and verification_pack:
        proofs = verification_pack.get("cluster_proofs") or []
        if isinstance(proofs, list):
            m["cluster_count"] = len([p for p in proofs if isinstance(p, dict)])

    out = _strip_not_provided_replacements(t)
    out = _ensure_exec_summary_labels(out, m)

    # Strengthen Business Impact line if still thin
    sections = parse_executive_markdown_sections(out)
    es = sections.get("executive_summary") or []
    es_blob = " ".join(es)
    if "Business Impact:" in es_blob and len(es_blob) < 120:
        lines = out.splitlines()
        rebuilt: list[str] = []
        for ln in lines:
            if re.match(r"^\s*Business Impact:\s*$", ln, re.I):
                rebuilt.append(
                    f"Business Impact: {_human_overlap_sentence(m.get('overlap_rate'), m.get('cluster_count'))}"
                )
            else:
                rebuilt.append(ln)
        out = "\n".join(rebuilt)

    out = _pad_section_if_empty(
        out,
        "breaking",
        "what is breaking performance",
        [
            "01 — Crawl overlap",
            "Problem: Multiple URLs compete for the same buyer decision.",
            "Business impact: Demand splits and conversion capture weakens.",
            "Action: Assign one primary URL per decision and align supporting routes.",
        ],
    )
    out = _pad_section_if_empty(
        out,
        "execution",
        "execution plan",
        [
            "Week 1: Lock canonical ownership and target URLs.",
            "Week 2: Apply merges, redirects, or differentiation edits.",
            "Week 3: Publish changes and fix internal links.",
            "Week 4: Validate outcomes and close remaining gaps.",
        ],
    )
    out = _pad_section_if_empty(
        out,
        "risks",
        "risks of inaction",
        [
            "- Demand stays fragmented across parallel URLs.",
            "- Acquisition spend rises while conversion stays flat.",
        ],
    )
    out = _pad_section_if_empty(
        out,
        "outcomes",
        "expected outcomes",
        [
            "- Clear ownership per major buyer decision.",
            "- Stronger conversion capture on priority journeys.",
            "- Less internal competition for the same story.",
        ],
    )

    tech = _build_technical_appendix_from_verification(verification_pack)
    return out.strip() + "\n", tech
