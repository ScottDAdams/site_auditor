"""
Downloadable report formats: Markdown with clear hierarchy for executive + technical views.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


def _md_escape_inline(s: str) -> str:
    """Normalize whitespace; keep single-line fields readable in lists."""
    if not s:
        return ""
    t = re.sub(r"\r\n|\r", "\n", str(s))
    return " ".join(t.split()) if "\n" not in t else t.strip()


def _md_block_preserve_hashes(s: str) -> str:
    """Multi-line user text: escape leading # so it is not parsed as Markdown headings."""
    if not s:
        return ""
    t = re.sub(r"\r\n|\r", "\n", str(s))
    out: list[str] = []
    for ln in t.split("\n"):
        stripped = ln.lstrip()
        if stripped.startswith("#"):
            i = ln.find("#")
            out.append(ln[:i] + "\\" + ln[i:])
        else:
            out.append(ln)
    return "\n".join(out).strip()


def _bullets(items: list[str], indent: str = "") -> str:
    out = []
    for it in items:
        if (it or "").strip():
            out.append(f"{indent}- {_md_escape_inline(str(it).strip())}")
    return "\n".join(out) + ("\n" if out else "")


def build_executive_markdown(
    es: dict[str, Any] | None,
    *,
    domains: str,
    score: int,
    priority_level: str,
    report_id: int,
    exec_text: str = "",
    roadmap: dict[str, Any] | None = None,
    created_at: datetime | None = None,
) -> str:
    """Structured Markdown mirroring the on-screen decision brief (Phase 6–10 layout)."""
    es = es or {}
    roadmap = roadmap or {}
    when = created_at or datetime.now(timezone.utc)
    ts = when.strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = [
        "---",
        f"title: Site auditor executive report",
        f"report_id: {report_id}",
        "---",
        "",
        "# Executive report",
        "",
        f"> **Sites:** {_md_escape_inline(domains)}  ",
        f"> **Health score:** {score} · **Priority:** {priority_level} · **Generated:** {ts}",
        "",
    ]

    pb = es.get("primary_bet")
    if isinstance(pb, dict) and (pb.get("action") or "").strip():
        lines += [
            "---",
            "",
            "## Primary decision",
            "",
            "> **If you do one thing**",
            "",
            f"**{_md_escape_inline(pb.get('action', ''))}**",
            "",
            f"- **Why this first:** {_md_escape_inline(pb.get('why_this_over_others', ''))}",
            f"- **Expected outcome:** {_md_escape_inline(pb.get('expected_effect', ''))}",
            "",
        ]

    lines += [
        "---",
        "",
        "## Decision brief",
        "",
        "### Snapshot",
        "",
    ]

    sh = es.get("site_health") or {}
    if isinstance(sh, dict):
        lines.append(
            f"- **Focus:** {_md_escape_inline(str(sh.get('primary_issue_type', '')))} · "
            f"**Risk:** {_md_escape_inline(str(sh.get('risk_level', '')))}"
        )
    ie = es.get("impact_estimate") or {}
    if isinstance(ie, dict) and (ie.get("reasoning") or "").strip():
        lines += [
            "",
            f"**Heuristic impact:** {_md_escape_inline(str(ie.get('impact_level', '')))} "
            f"({_md_escape_inline(str(ie.get('confidence', '')))})",
            "",
            _md_escape_inline(str(ie.get("reasoning", ""))),
            "",
        ]

    ps = es.get("primary_strategy")
    if isinstance(ps, dict) and (ps.get("label") or "").strip():
        lines += [
            "### Primary strategy",
            "",
            f"**{_md_escape_inline(str(ps.get('label', '')))}**",
            "",
            _md_escape_inline(str(ps.get("reasoning", ""))),
            "",
        ]

    cs = es.get("ceo_summary") or {}
    paras = cs.get("paragraphs") if isinstance(cs, dict) else None
    if isinstance(paras, list) and paras:
        lines += ["### CEO summary", ""]
        for p in paras:
            if str(p).strip():
                lines.append(_md_escape_inline(str(p).strip()))
                lines.append("")

    issues = es.get("top_issues") or []
    if isinstance(issues, list) and issues:
        lines += ["### What's breaking performance", ""]
        for i, iss in enumerate(issues, 1):
            if not isinstance(iss, dict):
                continue
            ck = str(iss.get("cluster_key") or "").replace("_", " ").title()
            tt = str(iss.get("transformation_type") or "")
            head = f"#### {i}. {ck or 'Issue'}" + (f" · `{tt}`" if tt else "")
            lines.append(head)
            lines.append("")
            if (iss.get("cluster_skim") or "").strip():
                lines.append(f"*{_md_escape_inline(str(iss.get('cluster_skim')))}*")
                lines.append("")
            if (iss.get("problem") or "").strip():
                prob = str(iss.get("problem")).strip()
                if "\n" in prob:
                    lines.append("**Core problem:**")
                    lines.append("")
                    lines.append(_md_block_preserve_hashes(prob))
                else:
                    lines.append(f"**Core problem:** {_md_escape_inline(prob)}")
                lines.append("")
            for label, key in (
                ("Impact", "impact"),
                ("Decision", "decision"),
                ("If ignored", "risk_if_ignored"),
                ("Outcome", "outcome"),
            ):
                val = (iss.get(key) or "").strip()
                if val:
                    lines.append(f"- **{label}:** {_md_escape_inline(val)}")
            urls = iss.get("urls") or []
            if urls:
                lines.append("")
                lines.append("**Example URLs:**")
                for u in urls[:8]:
                    lines.append(f"- `{_md_escape_inline(str(u))}`")
            ev = iss.get("evidence") if isinstance(iss.get("evidence"), dict) else {}
            if ev:
                lines.append("")
                sim = ev.get("similarity_score")
                if sim is not None:
                    try:
                        lines.append(
                            f"- **Similarity (crawl signal):** {int(round(float(sim) * 100))}%"
                        )
                    except (TypeError, ValueError):
                        pass
                for s in (ev.get("shared_sections") or [])[:5]:
                    lines.append(f"- **Shared section:** {_md_escape_inline(str(s))}")
                interp = (ev.get("interpretation") or "").strip()
                if interp:
                    lines.append(f"- **Interpretation:** {_md_escape_inline(interp)}")
            rat = (iss.get("decision_rationale") or "").strip()
            if rat:
                lines.append("")
                lines.append(f"- **Why this is the correct move:** {_md_escape_inline(rat)}")
            lines.append("")

    plan = es.get("execution_plan") or []
    if isinstance(plan, list) and plan:
        lines += ["### Execution plan", ""]
        for step in plan:
            if not isinstance(step, dict):
                continue
            n = step.get("step", "")
            focus = step.get("focus") or step.get("intent") or "Step"
            lines.append(f"#### Step {n}: {_md_escape_inline(str(focus))}")
            lines.append("")
            for a in (step.get("actions") or [])[:6]:
                if str(a).strip():
                    lines.append(f"- {_md_escape_inline(str(a))}")
            lines.append("")

    opps = es.get("opportunities") or []
    if isinstance(opps, list) and opps:
        lines += ["### Where you can grow", ""]
        for opp in opps:
            if not isinstance(opp, dict):
                continue
            lines.append(f"#### {_md_escape_inline(str(opp.get('title', 'Opportunity')))}")
            lines.append("")
            for label, key in (
                ("Lever", "lever"),
                ("Mechanism", "mechanism"),
                ("Opportunity", "opportunity"),
                ("Impact", "impact"),
                ("Action", "action"),
            ):
                v = (opp.get(key) or "").strip()
                if v:
                    lines.append(f"- **{label}:** {_md_escape_inline(v)}")
            pages = opp.get("pages") or []
            if pages:
                lines.append("")
                for u in pages[:6]:
                    lines.append(f"- `{_md_escape_inline(str(u))}`")
            lines.append("")

    qw = es.get("quick_wins") or []
    if isinstance(qw, list) and qw:
        lines += ["### Quick fixes", ""]
        for q in qw:
            if isinstance(q, dict) and (q.get("action") or "").strip():
                lines.append(f"- {_md_escape_inline(str(q['action']))}")
        lines.append("")

    risks = es.get("strategic_risks") or []
    if isinstance(risks, list) and risks:
        lines += ["### If you delay", ""]
        for r in risks:
            if isinstance(r, dict):
                lines.append(
                    f"- **{_md_escape_inline(str(r.get('risk', '')))}:** "
                    f"{_md_escape_inline(str(r.get('consequence', '')))}"
                )
        lines.append("")

    eo = es.get("expected_outcome") or {}
    bullets = eo.get("bullets") if isinstance(eo, dict) else None
    if isinstance(bullets, list) and bullets:
        lines += ["### Expected outcome", ""]
        lines.append(_bullets([str(b) for b in bullets]))
        lines.append("")

    rsteps = roadmap.get("roadmap") if isinstance(roadmap, dict) else None
    if isinstance(rsteps, list) and rsteps:
        lines += ["---", "", "## Roadmap (30-day plan)", ""]
        for item in rsteps:
            if not isinstance(item, dict):
                continue
            st = item.get("step", "")
            tit = item.get("title") or "Initiative"
            lines.append(f"### Step {st}: {_md_escape_inline(str(tit))}")
            lines.append("")
            if (item.get("description") or "").strip():
                lines.append(_md_block_preserve_hashes(str(item.get("description"))))
                lines.append("")
            turls = item.get("target_urls") or []
            if turls:
                lines.append("**Targets:** " + ", ".join(f"`{u}`" for u in turls[:6]))
                lines.append("")

    if (exec_text or "").strip():
        lines += [
            "---",
            "",
            "## Full executive brief (polished text)",
            "",
            _md_block_preserve_hashes(exec_text.strip()),
            "",
        ]

    br = es.get("boardroom_summary") or {}
    slides = br.get("slides") if isinstance(br, dict) else None
    if isinstance(slides, list) and slides:
        lines += ["---", "", "## Boardroom narrative (10 slides)", ""]
        for i, sl in enumerate(slides, 1):
            if not isinstance(sl, dict):
                continue
            lines.append(f"### Slide {i}: {_md_escape_inline(str(sl.get('title', '')))}")
            lines.append("")
            lines.append(f"**{_md_escape_inline(str(sl.get('headline', '')))}**")
            lines.append("")
            for pt in (sl.get("points") or [])[:8]:
                if str(pt).strip():
                    lines.append(f"- {_md_escape_inline(str(pt))}")
            lines.append("")

    lines.append("")
    lines.append(f"*— End of executive report · id `{report_id}` —*")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_technical_markdown(
    report_html: str,
    *,
    domains: str,
    score: int,
    priority_level: str,
    report_id: int,
    es: dict[str, Any] | None = None,
    created_at: datetime | None = None,
) -> str:
    """
    Technical packet: summary front-matter + HTML body converted to Markdown
    (headings, lists, links preserved for downstream styling).
    """
    from markdownify import markdownify as html_to_md

    es = es or {}
    when = created_at or datetime.now(timezone.utc)
    ts = when.strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = [
        "---",
        f"title: Site auditor technical report",
        f"report_id: {report_id}",
        "---",
        "",
        "# Technical audit",
        "",
        f"> **Sites:** {_md_escape_inline(domains)}  ",
        f"> **Health score:** {score} · **Priority:** {priority_level} · **Generated:** {ts}",
        "",
        "## Summary",
        "",
        "Crawl-backed findings, URLs, and structural signals. Use with the executive report for context.",
        "",
    ]

    sh = es.get("site_health") or {}
    if isinstance(sh, dict):
        lines.append(
            f"- **Structural risk:** {_md_escape_inline(str(sh.get('risk_level', '')))}"
        )
        lines.append(
            f"- **Primary pattern:** {_md_escape_inline(str(sh.get('primary_issue_type', '')))}"
        )
    ie = es.get("impact_estimate") or {}
    if isinstance(ie, dict) and (ie.get("impact_level") or "").strip():
        lines.append(
            f"- **Heuristic impact:** {_md_escape_inline(str(ie.get('impact_level')))} "
            f"({_md_escape_inline(str(ie.get('confidence', '')))})"
        )
    lines.append("")

    lines += [
        "---",
        "",
        "## Full technical output",
        "",
    ]

    body = html_to_md(
        report_html or "",
        heading_style="ATX",
        bullets="-",
        strip=["script", "style"],
    )
    body = (body or "").strip()
    if not body:
        body = "_No technical HTML body was stored for this audit._"
    lines.append(body)
    lines.append("")
    lines.append(f"*— End of technical report · id `{report_id}` —*")
    lines.append("")
    return "\n".join(lines).strip() + "\n"
