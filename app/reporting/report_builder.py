"""
Deterministic DOCX report builder for executive narrative output.

AI thinks. Code presents.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _load_text(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="ignore")


def _norm_heading(line: str) -> str:
    x = (line or "").strip()
    x = re.sub(r"^#+\s*", "", x)
    x = re.sub(r"^\d+\s*", "", x)
    x = x.strip(": ").lower()
    return x


def _parse_sections(md: str) -> dict[str, list[str]]:
    mapping = {
        "executive summary": "executive_summary",
        "what is breaking performance": "breaking",
        "if you do one thing": "primary_action",
        "execution plan": "execution",
        "risks of inaction": "risks",
        "risks of delay": "risks",
        "expected outcomes": "outcomes",
    }
    out: dict[str, list[str]] = {v: [] for v in mapping.values()}
    cur = ""
    for raw in (md or "").splitlines():
        h = _norm_heading(raw)
        if h in mapping:
            cur = mapping[h]
            continue
        if cur:
            line = raw.strip()
            if line:
                out[cur].append(line)
    return out


def _extract_domains(md: str) -> str:
    m = re.search(r"Sites:\s*([^\n]+)", md or "", flags=re.I)
    if m:
        return _clean(m.group(1)).strip("*`> ")
    return "N/A"


def _extract_label_value(lines: list[str], label: str) -> str:
    pat = re.compile(rf"^\s*[-*]?\s*\**{re.escape(label)}\**\s*:\s*(.+)\s*$", re.I)
    for ln in lines:
        m = pat.match(ln)
        if m:
            return _clean(m.group(1))
    return ""


def _strip_md_marks(s: str) -> str:
    t = re.sub(r"`([^`]+)`", r"\1", s or "")
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"^\s*[-*]\s*", "", t)
    return _clean(t)


def _extract_issues(lines: list[str]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    cur: dict[str, str] | None = None
    for ln in lines:
        s = _strip_md_marks(ln)
        if re.match(r"^\d{1,2}\s*[—-]\s*", s) or re.match(r"^\d+\.\s+", s):
            if cur:
                issues.append(cur)
            cur = {"title": re.sub(r"^\d{1,2}\s*[—-]\s*|^\d+\.\s*", "", s), "problem": "", "impact": "", "action": "", "success": ""}
            continue
        if cur is None:
            # Fallback issue opener.
            cur = {"title": "Issue", "problem": "", "impact": "", "action": "", "success": ""}
        low = s.lower()
        if low.startswith("problem:"):
            cur["problem"] = _clean(s.split(":", 1)[1])
        elif low.startswith("business impact:") or low.startswith("impact:"):
            cur["impact"] = _clean(s.split(":", 1)[1])
        elif low.startswith("action:"):
            cur["action"] = _clean(s.split(":", 1)[1])
        elif low.startswith("on success:") or low.startswith("outcome:"):
            cur["success"] = _clean(s.split(":", 1)[1])
    if cur:
        issues.append(cur)
    # Tight deterministic cap.
    out = [i for i in issues if i.get("title") or i.get("problem")]
    return out[:5]


def _extract_primary_action(lines: list[str]) -> dict[str, str]:
    action = _extract_label_value(lines, "PRIMARY ACTION") or _extract_label_value(lines, "Action")
    why = _extract_label_value(lines, "WHY THIS FIRST") or _extract_label_value(lines, "Why this first")
    expected = _extract_label_value(lines, "EXPECTED RESULT") or _extract_label_value(lines, "Expected outcome")
    # Fallback from free lines.
    free = [_strip_md_marks(x) for x in lines if _strip_md_marks(x)]
    if not action and free:
        action = free[0]
    if not why and len(free) > 1:
        why = free[1]
    if not expected and len(free) > 2:
        expected = free[2]
    return {
        "action": action or "No primary action provided.",
        "why": why or "This action resolves the highest-leverage structural blocker first.",
        "expected": expected or "Demand and conversion capture improve when one page owns each decision.",
    }


def _extract_execution(lines: list[str]) -> list[tuple[str, str]]:
    steps: list[tuple[str, str]] = []
    cur_week = ""
    for ln in lines:
        s = _strip_md_marks(ln)
        wk = re.match(r"^(week\s*\d+)\s*[:\-]?\s*(.*)$", s, re.I)
        if wk:
            cur_week = wk.group(1).upper()
            desc = _clean(wk.group(2))
            if desc:
                steps.append((cur_week, desc))
            else:
                steps.append((cur_week, "Execute the scoped actions for this week."))
            continue
        if cur_week and s:
            w, d = steps[-1]
            steps[-1] = (w, _clean(f"{d} {s}"))
    if not steps:
        # fallback deterministic timeline
        return [
            ("WEEK 1", "Align target pages and lock canonical ownership."),
            ("WEEK 2", "Implement page changes and internal linking updates."),
            ("WEEK 3", "Publish, redirect, and verify structural consistency."),
            ("WEEK 4", "Validate outcomes and close remaining structural gaps."),
        ]
    return steps[:6]


def _extract_bullets(lines: list[str]) -> list[str]:
    out: list[str] = []
    for ln in lines:
        s = _strip_md_marks(ln)
        if s:
            out.append(s)
    return out[:8]


def _extract_appendix(technical_md: str) -> list[dict[str, Any]]:
    if not technical_md.strip():
        return []
    blocks = []
    current = {"cluster": "", "urls": [], "example": "", "interpretation": ""}
    for raw in technical_md.splitlines():
        s = _strip_md_marks(raw)
        l = s.lower()
        if l.startswith("cluster:"):
            if current["cluster"] or current["urls"] or current["example"] or current["interpretation"]:
                blocks.append(current)
                current = {"cluster": "", "urls": [], "example": "", "interpretation": ""}
            current["cluster"] = _clean(s.split(":", 1)[1])
        elif l.startswith("urls:"):
            pass
        elif s.startswith("http://") or s.startswith("https://"):
            current["urls"].append(s)
        elif l.startswith("example:"):
            current["example"] = _clean(s.split(":", 1)[1])
        elif l.startswith("interpretation:"):
            current["interpretation"] = _clean(s.split(":", 1)[1])
    if current["cluster"] or current["urls"] or current["example"] or current["interpretation"]:
        blocks.append(current)
    return blocks[:8]


def _apply_styles(doc):
    from docx.shared import Pt, RGBColor
    from docx.enum.style import WD_STYLE_TYPE

    styles = doc.styles

    normal = styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)

    for name, size, bold in (
        ("SA Title", 30, True),
        ("SA Section Header", 17, True),
        ("SA Subheader", 13, True),
        ("SA Body", 11, False),
    ):
        if name in styles:
            st = styles[name]
        else:
            st = styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        st.font.name = "Calibri"
        st.font.size = Pt(size)
        st.font.bold = bold
        st.font.color.rgb = RGBColor(0, 0, 0)


def _add_cover(doc, md: str):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    domains = _extract_domains(md)
    p = doc.add_paragraph("AI Site Auditor", style="SA Title")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p2 = doc.add_paragraph("Executive Report", style="SA Section Header")
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("")
    for k, v in (
        ("Domains", domains),
        ("Date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
        ("Confidential", "Internal / Client Confidential"),
    ):
        row = doc.add_paragraph(style="SA Body")
        row.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = row.add_run(f"{k}: {v}")
        run.font.size = Pt(11)
    doc.add_page_break()


def _add_exec_summary(doc, sections: dict[str, list[str]]):
    lines = sections.get("executive_summary") or []
    core = _extract_label_value(lines, "Core Problem")
    action = _extract_label_value(lines, "Primary Action")
    impact = _extract_label_value(lines, "Business Impact")
    free = [_strip_md_marks(x) for x in lines if _strip_md_marks(x)]
    if not core and free:
        core = free[0]
    if not action and len(free) > 1:
        action = free[1]
    if not impact and len(free) > 2:
        impact = free[2]

    doc.add_paragraph("Executive Summary", style="SA Section Header")
    for title, value in (
        ("CORE PROBLEM", core or "No core problem provided."),
        ("PRIMARY ACTION", action or "No primary action provided."),
        ("BUSINESS IMPACT", impact or "No business impact provided."),
    ):
        doc.add_paragraph(title, style="SA Subheader")
        doc.add_paragraph(value, style="SA Body")


def _add_breaking_performance(doc, sections: dict[str, list[str]]):
    doc.add_paragraph("What Is Breaking Performance", style="SA Section Header")
    issues = _extract_issues(sections.get("breaking") or [])
    if not issues:
        issues = [{"title": "Issue", "problem": "Not provided.", "impact": "", "action": "", "success": ""}]
    for i, iss in enumerate(issues, 1):
        doc.add_paragraph(f"{i:02d} — {iss.get('title') or 'Issue'}", style="SA Subheader")
        for k, v in (
            ("Problem", iss.get("problem") or "Not provided."),
            ("Business Impact", iss.get("impact") or "Not provided."),
            ("Action", iss.get("action") or "Not provided."),
            ("On Success", iss.get("success") or "Not provided."),
        ):
            doc.add_paragraph(k, style="SA Subheader")
            doc.add_paragraph(v, style="SA Body")


def _add_primary_action(doc, sections: dict[str, list[str]]):
    from docx.shared import RGBColor

    doc.add_paragraph("Primary Action", style="SA Section Header")
    data = _extract_primary_action(sections.get("primary_action") or [])
    table = doc.add_table(rows=3, cols=2)
    table.style = "Table Grid"
    rows = (
        ("PRIMARY ACTION", data["action"]),
        ("WHY THIS FIRST", data["why"]),
        ("EXPECTED RESULT", data["expected"]),
    )
    for i, (k, v) in enumerate(rows):
        left = table.cell(i, 0)
        right = table.cell(i, 1)
        left.text = k
        right.text = v
        for r in left.paragraphs[0].runs:
            r.bold = True
        # Deterministic callout shading (light gray).
        for cell in (left, right):
            tc_pr = cell._tc.get_or_add_tcPr()  # noqa: SLF001
            shd = doc._element.makeelement("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}shd")  # noqa: SLF001
            shd.set("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}fill", "F2F2F2")
            tc_pr.append(shd)


def _add_execution_plan(doc, sections: dict[str, list[str]]):
    doc.add_paragraph("30-Day Execution Plan", style="SA Section Header")
    for week, desc in _extract_execution(sections.get("execution") or []):
        doc.add_paragraph(week, style="SA Subheader")
        doc.add_paragraph(desc, style="SA Body")


def _add_risks(doc, sections: dict[str, list[str]]):
    doc.add_paragraph("Risks of Delay", style="SA Section Header")
    bullets = _extract_bullets(sections.get("risks") or [])
    if not bullets:
        bullets = ["Demand remains split.", "Spend rises to compensate.", "Conversion stays suppressed."]
    for b in bullets:
        doc.add_paragraph(b, style="List Bullet")


def _add_outcomes(doc, sections: dict[str, list[str]]):
    doc.add_paragraph("Expected Outcomes", style="SA Section Header")
    bullets = _extract_bullets(sections.get("outcomes") or [])
    if not bullets:
        bullets = ["Clear ownership per decision page.", "Higher conversion capture.", "Lower wasted acquisition spend."]
    for b in bullets:
        doc.add_paragraph(b, style="List Bullet")


def _add_appendix(doc, technical_md: str):
    entries = _extract_appendix(technical_md)
    if not entries:
        return
    doc.add_page_break()
    doc.add_paragraph("Appendix", style="SA Section Header")
    for e in entries:
        doc.add_paragraph(f"Cluster: {e.get('cluster') or 'N/A'}", style="SA Subheader")
        doc.add_paragraph("URLs:", style="SA Subheader")
        urls = e.get("urls") or []
        if urls:
            for u in urls[:6]:
                doc.add_paragraph(_clean(str(u)), style="List Bullet")
        else:
            doc.add_paragraph("No URLs extracted.", style="SA Body")
        doc.add_paragraph(f"Example: {e.get('example') or 'N/A'}", style="SA Body")
        doc.add_paragraph(f"Interpretation: {e.get('interpretation') or 'N/A'}", style="SA Body")


def build_executive_docx(md_path: str, output_path: str) -> None:
    """
    Deterministically render executive markdown into consulting-grade DOCX.
    """
    try:
        from docx import Document
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("python-docx is required for DOCX build") from exc

    md = _load_text(md_path)
    if not md.strip():
        raise ValueError(f"executive markdown is empty or missing: {md_path}")
    sections = _parse_sections(md)

    doc = Document()
    _apply_styles(doc)
    _add_cover(doc, md)
    _add_exec_summary(doc, sections)
    _add_breaking_performance(doc, sections)
    _add_primary_action(doc, sections)
    _add_execution_plan(doc, sections)
    _add_risks(doc, sections)
    _add_outcomes(doc, sections)

    technical_path = str((Path(md_path).parent / "technical_report.md").resolve())
    technical_md = _load_text(technical_path)
    _add_appendix(doc, technical_md)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))


def build_pptx_from_json(json_path: str, template_path: str) -> None:
    """Future extension placeholder."""
    _ = (json_path, template_path)
    raise NotImplementedError("PPTX builder is reserved for a future phase.")

