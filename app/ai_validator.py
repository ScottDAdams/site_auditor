"""
Strict, deterministic validation for AI insight JSON (core narrative + alignment).
Used after two-pass insight generation merges with report shell fields.
"""

import re
from urllib.parse import urlparse

BANNED_WORDS = [
    "clarify",
    "improve",
    "optimize",
    "enhance",
    "refine",
    "align",
    "leverage",
    "utilize",
]


def contains_banned(text: str) -> bool:
    if not text or not isinstance(text, str):
        return False
    text = text.lower()
    return any(word in text for word in BANNED_WORDS)


# Non-mechanical / SEO-fluff phrases in primary_action (substring match, lowercased).
VAGUE_PRIMARY_ACTION_PHRASES = (
    "differentiate positioning",
    "improve clarity",
    "optimize content",
    "optimise content",
    "enhance clarity",
    "refine messaging",
    "refine positioning",
    "align better",
    "better positioning",
    "improve positioning",
)

# primary_action must reference something page-structural or a URL/path.
_PAGE_LEVEL_RE = re.compile(
    r"https?://|/\w"
    r"|\b(page|pages|url|urls|domain|route|path|canonical|redirect|301|"
    r"section|sections|block|blocks|hero|h1|heading|headings|copy|cta|"
    r"metadata|pricing|policy|table|module|snippet|body|intro|footer)\b",
    re.I,
)


def validate_primary_action_hard_constraints(primary_action: str) -> None:
    """
    Reject abstract SEO phrasing; require page-level or URL/path anchoring.
    Raises ValueError with [rule:...] prefix for logging.
    """
    pa = (primary_action or "").strip()
    if not pa:
        raise ValueError("[rule:primary_action_empty] primary_action is empty")
    low = pa.lower()
    for phrase in VAGUE_PRIMARY_ACTION_PHRASES:
        if phrase in low:
            raise ValueError(
                f"[rule:vague_action_phrase] primary_action contains banned phrase {phrase!r}"
            )
    if not _PAGE_LEVEL_RE.search(pa):
        raise ValueError(
            "[rule:primary_action_page_anchor] primary_action must reference a page element, "
            "URL, path, or route (not abstract strategy only)"
        )


def count_distinct_payload_urls_in_text(text: str, candidate_urls: list[str]) -> int:
    """How many distinct candidate URLs appear as substrings in text (exact URL match)."""
    if not text or not candidate_urls:
        return 0
    seen = set()
    for u in candidate_urls:
        if not u:
            continue
        s = str(u).strip()
        if s and s in text and s not in seen:
            seen.add(s)
    return len(seen)


# Strategic actions must change structure or roles, not only stack new copy.
_STRATEGIC_RESOLUTION_RE = re.compile(
    r"\b(replace|remove|removing|restrict|split|assign|assigned|isolate|shift|strip|"
    r"merge|delete|rewrite|rewriting|consolidate|eliminate|drop)\b",
    re.I,
)
_TECHNICAL_RESOLUTION_RE = re.compile(
    r"\b(redirect|canonical|301|merge|consolidat|remove|delete|alias|host)\b",
    re.I,
)
_WHY_STAKE_RE = re.compile(
    r"overlap|similarity|cluster|uniqueness|duplicate|crawl|index|rank|ranking|conversion|"
    r"ambigu|cannibal|signal|intent|decision|path|visibility|metric",
    re.I,
)
_WHY_GENERIC_PHRASES = (
    "better user experience",
    "improve user experience",
    "improves clarity",
    "improve clarity",
    "better clarity",
    "great experience",
)
def validate_pass1_structured_roles(
    core_problem: str,
    page_a_role: str,
    page_b_role: str,
    primary_action: str,
) -> None:
    """Pass 1 schema: four separate fields, no paragraphs in one field."""
    cp = (core_problem or "").strip()
    ra = (page_a_role or "").strip()
    rb = (page_b_role or "").strip()
    pa = (primary_action or "").strip()
    for name, val in (
        ("core_problem", cp),
        ("page_a_role", ra),
        ("page_b_role", rb),
        ("primary_action", pa),
    ):
        if not val:
            raise ValueError(f"[rule:pass1_schema] missing {name}")
        if "\n\n" in val:
            raise ValueError(f"[rule:pass1_schema] {name} must not contain blank-line paragraphs")
    if len(cp.split()) > 28:
        raise ValueError("Pass 1 core_problem exceeds 28 words")
    for name, val in (("page_a_role", ra), ("page_b_role", rb)):
        if len(val.split()) > 40:
            raise ValueError(f"Pass 1 {name} exceeds 40 words")
    if len(pa.split()) > 36:
        raise ValueError("Pass 1 primary_action exceeds 36 words")


def validate_primary_action_reflects_roles(
    primary_action: str,
    page_a_role: str,
    page_b_role: str,
    context: dict | None,
) -> None:
    """primary_action must combine transformations implied by both roles when pairs compete."""
    pa = (primary_action or "").strip()
    if context is None or not context.get("competing_pages_roles_required"):
        return
    low = pa.lower()
    if ";" not in pa and " and " not in low:
        raise ValueError(
            "[rule:primary_action_roles] combine both role transforms (use ';' or ' and ')"
        )


def validate_action_resolves_conflict(primary_action: str, context: dict | None) -> None:
    """
    primary_action must resolve the URL/intent conflict, not only describe or soften it.
    context expects: dominant_problem_type, competing_pages_roles_required (bool),
    page_a_url, page_b_url (optional), problem_type_key (optional).
    """
    if context is None or not str(context.get("dominant_problem_type") or "").strip():
        return
    pa = (primary_action or "").strip()
    low = pa.lower()
    dpt = (context.get("dominant_problem_type") or "").strip().lower()

    if dpt == "acceptable":
        if not re.search(r"\b(none|no merge|no redirect|prescribe none|hold|monitor)\b", low):
            raise ValueError(
                "[rule:action_resolves_conflict] acceptable: state no structural merge/redirect "
                "or equivalent hold"
            )
        return

    if dpt == "technical":
        if not _TECHNICAL_RESOLUTION_RE.search(pa):
            raise ValueError(
                "[rule:action_resolves_conflict] technical: consolidate duplicate routes "
                "(redirect, canonical, merge, remove duplicate signals)"
            )
        return

    if dpt == "strategic":
        if re.search(r"\badd\b", low) and not _STRATEGIC_RESOLUTION_RE.search(pa):
            raise ValueError(
                "[rule:action_resolves_conflict] strategic: add-only copy does not resolve "
                "competing intent; include remove/replace/restrict/split/assign/merge/delete"
            )
        if not _STRATEGIC_RESOLUTION_RE.search(pa):
            raise ValueError(
                "[rule:action_resolves_conflict] strategic: primary_action must enforce "
                "separation (replace/remove/restrict/split/assign/isolate/merge/delete/rewrite)"
            )
        vague_diff = (
            "differentiate" in low
            and not re.search(
                r"\b(restrict|assign|split|remove|replace|only|isolate|strip)\b",
                low,
            )
        )
        if vague_diff:
            raise ValueError(
                "[rule:action_resolves_conflict] strategic: 'differentiate' must pair with a "
                "mechanism (restrict, assign, split, remove, replace, only, isolate)"
            )
        if context.get("competing_pages_roles_required"):
            a = (context.get("page_a_url") or "").strip()
            b = (context.get("page_b_url") or "").strip()
            if a and b and a != b:
                if a in pa and b in pa:
                    pass
                else:

                    def _path_sig(u: str) -> str | None:
                        pth = urlparse(u).path.strip("/")
                        if not pth:
                            return None
                        parts = pth.split("/")
                        if len(parts) >= 2:
                            return "/" + "/".join(parts[-2:])
                        return "/" + parts[-1]

                    sa, sb = _path_sig(a), _path_sig(b)
                    if not (
                        sa
                        and sb
                        and sa != sb
                        and sa in pa
                        and sb in pa
                    ):
                        raise ValueError(
                            "[rule:action_resolves_conflict] strategic: primary_action must "
                            "assign roles using both page_a and page_b (full URL or path tail)"
                        )


def validate_why_it_matters_stake(why_it_matters: str) -> None:
    """Require at least ONE of: metric reference OR explicit consequence (not both)."""
    w = (why_it_matters or "").strip()
    low = w.lower()
    for g in _WHY_GENERIC_PHRASES:
        if g in low:
            raise ValueError(
                f"[rule:why_stake] why_it_matters must not use generic phrase {g!r}; "
                "tie to metrics or ranking/decision/conversion consequence"
            )
    if not _WHY_STAKE_RE.search(w):
        raise ValueError(
            "[rule:why_stake] why_it_matters must reference a metric (overlap, similarity, "
            "cluster, crawl, …) or explicit consequence (ranking conflict, decision ambiguity, "
            "conversion friction, cannibalization)"
        )


def validate_execution_example_contrast(
    execution_example: str,
    candidate_urls: list[str],
) -> None:
    """When two URLs are cited: separate URL blocks; at least one remove/replace; differing adds."""
    ex = (execution_example or "").strip()
    cited = count_distinct_payload_urls_in_text(ex, candidate_urls)
    if cited < 2:
        return
    low = ex.lower()
    on_blocks = len(re.findall(r"on\s+https?://", low))
    if on_blocks < 2 and low.count(";") < 1:
        raise ValueError(
            "[rule:execution_contrast] use two 'On https://...' blocks or separate clauses with ';'"
        )
    if not re.search(
        r"(?:^|\n)\s*-\s*remove\s*:|\bremove\s*:|\breplace\s*:",
        ex,
        re.I | re.M,
    ):
        raise ValueError(
            "[rule:execution_structure] include at least one remove: or replace: (bullet optional)"
        )
    add_lines = len(re.findall(r"(?:^|\n)\s*-\s*add\s*:", ex, re.I | re.M))
    if add_lines < 2:
        raise ValueError(
            "[rule:execution_structure] each competing page needs a distinct - add: line "
            "so A and B are not interchangeable"
        )


def validate_execution_example_url_binding(
    execution_example: str,
    candidate_urls: list[str],
) -> None:
    """Require two payload URLs when at least two are available; else one."""
    ex = (execution_example or "").strip()
    n_allowed = len([u for u in candidate_urls if u])
    if n_allowed == 0:
        raise ValueError("[rule:execution_urls] no candidate URLs in payload for binding")
    cited = count_distinct_payload_urls_in_text(ex, candidate_urls)
    need = 2 if n_allowed >= 2 else 1
    if cited < need:
        raise ValueError(
            f"[rule:execution_two_urls] execution_example must cite {need} distinct "
            f"payload URL(s) as full strings; found {cited}"
        )


def validate_required_fields(data: dict) -> None:
    required = [
        "problem_type",
        "core_problem",
        "why_it_matters",
        "primary_action",
        "execution_example",
        "confidence",
        "impact",
    ]
    if data.get("structured_pass1"):
        required = required + ["page_a_role", "page_b_role"]
    for key in required:
        if key not in data or data[key] is None or (isinstance(data[key], str) and not str(data[key]).strip()):
            raise ValueError(f"Missing required field: {key}")


def validate_problem_type_matches_dominant(data: dict, dominant_problem_type: str | None) -> None:
    """Ensure the model echoed the server-determined type (AI does not decide problem_type)."""
    if not dominant_problem_type:
        return
    expected = str(dominant_problem_type).strip().lower()
    got = (data.get("problem_type") or "").strip().lower()
    if got != expected:
        raise ValueError(
            f"problem_type must equal dominant_problem_type ({expected!r}), got {got!r}"
        )


def validate_problem_action_alignment(data: dict) -> None:
    """primary_action must match the fixed problem_type (alignment only)."""
    pt = (data.get("problem_type") or "").strip().lower()
    action = (data.get("primary_action") or "").lower()
    tt = (data.get("transformation_type") or "").strip().lower()
    allow_tech_verbs = tt in ("merge", "redirect", "consolidate")

    if pt == "acceptable" and any(x in action for x in ["differentiate", "reposition"]):
        raise ValueError("Acceptable problems cannot require strategic-style actions")

    if pt == "technical" and any(x in action for x in ["reposition", "differentiate"]):
        raise ValueError("Technical problems cannot require strategic actions")

    if pt == "strategic" and any(x in action for x in ["redirect", "canonical"]):
        if not allow_tech_verbs:
            raise ValueError("Strategic problems should not default to technical fixes")


def validate_primary_action_matches_transformation_type(data: dict) -> None:
    """Block contradictions between transformation_type and primary_action wording."""
    tt = (data.get("transformation_type") or "").strip().lower()
    pa = (data.get("primary_action") or "").strip()
    if not tt or not pa:
        return
    low = pa.lower()
    if tt in ("merge", "redirect", "consolidate") and re.search(r"\bdifferentiate\b", low):
        raise ValueError(
            f"[rule:primary_action_vs_type] primary_action must not use 'differentiate' "
            f"when transformation_type is {tt!r}"
        )


def validate_no_vague_language(data: dict) -> None:
    keys = [
        "core_problem",
        "page_a_role",
        "page_b_role",
        "why_it_matters",
        "primary_action",
        "execution_example",
    ]
    for key in keys:
        if contains_banned(data.get(key, "")):
            raise ValueError(f"Banned language in {key}")


def validate_length(data: dict) -> None:
    for key in ["core_problem", "why_it_matters"]:
        text = data.get(key) or ""
        if len(str(text).split()) > 40:
            raise ValueError(f"{key} too long")


def validate_confidence_impact(data: dict) -> None:
    c = (data.get("confidence") or "").strip()
    i = (data.get("impact") or "").strip()
    if c not in ("High", "Medium", "Low"):
        raise ValueError("confidence must be High, Medium, or Low")
    if i not in ("High", "Moderate", "Low"):
        raise ValueError("impact must be High, Moderate, or Low")


def validate_narrative_matches_transformation_spec(data: dict) -> None:
    """
    When the pipeline rendered insights from transformation_spec, roles and execution
    bullets must match the spec exactly (no model drift).
    """
    if not data.get("insights_rendered_from_spec"):
        return
    spec = data.get("transformation_spec")
    if not isinstance(spec, dict):
        raise ValueError(
            "[rule:spec_missing] insights_rendered_from_spec requires transformation_spec object"
        )
    if (data.get("page_a_role") or "").strip() != (spec.get("page_a_role") or "").strip():
        raise ValueError("[rule:spec_page_a_role] page_a_role must match transformation_spec")
    if (data.get("page_b_role") or "").strip() != (spec.get("page_b_role") or "").strip():
        raise ValueError("[rule:spec_page_b_role] page_b_role must match transformation_spec")

    ex = (data.get("execution_example") or "").strip()
    ua = (spec.get("page_a_url") or "").strip()
    ub = (spec.get("page_b_url") or "").strip()
    if ua and ua not in ex:
        raise ValueError("[rule:spec_execution_url_a] execution_example must cite page_a_url")
    if ub and ub not in ex:
        raise ValueError("[rule:spec_execution_url_b] execution_example must cite page_b_url")

    def _parse_blocks(text: str) -> list[tuple[str, str, str]]:
        """Return list of (url, remove_text, add_text) from On URL: blocks."""
        blocks = re.split(r"\n\s*\n+", text.strip())
        out: list[tuple[str, str, str]] = []
        for blk in blocks:
            if not blk.strip():
                continue
            lines = [ln.strip() for ln in blk.splitlines() if ln.strip()]
            if not lines:
                continue
            head = lines[0]
            um = re.match(r"^On\s+(https?://\S+)\s*:\s*$", head, re.I)
            if not um:
                continue
            url = um.group(1)
            rm_txt, ad_txt = "", ""
            for ln in lines[1:]:
                rmm = re.match(r"^-\s*remove\s*:\s*(.+)$", ln, re.I)
                if rmm:
                    rm_txt = rmm.group(1).strip()
                    continue
                adm = re.match(r"^-\s*add\s*:\s*(.+)$", ln, re.I)
                if adm:
                    ad_txt = adm.group(1).strip()
            out.append((url, rm_txt, ad_txt))
        return out

    parsed = _parse_blocks(ex)
    ra_list = list(spec.get("remove_from_a") or [])
    aa_list = list(spec.get("add_to_a") or [])
    rb_list = list(spec.get("remove_from_b") or [])
    ab_list = list(spec.get("add_to_b") or [])

    if ua:
        exp_rm_a = ra_list[0] if ra_list else "overlapping shared messaging"
        exp_ad_a = aa_list[0] if aa_list else "content matched to this URL role"
        match_a = next((p for p in parsed if p[0] == ua), None)
        if not match_a:
            raise ValueError("[rule:spec_execution_block_a] missing On block for page_a_url")
        if match_a[1] != exp_rm_a or match_a[2] != exp_ad_a:
            raise ValueError(
                "[rule:spec_execution_lines_a] remove/add lines must match transformation_spec"
            )
    if ub:
        exp_rm_b = rb_list[0] if rb_list else "overlapping shared messaging"
        exp_ad_b = ab_list[0] if ab_list else "content matched to this URL role"
        match_b = next((p for p in parsed if p[0] == ub), None)
        if not match_b:
            raise ValueError("[rule:spec_execution_block_b] missing On block for page_b_url")
        if match_b[1] != exp_rm_b or match_b[2] != exp_ad_b:
            raise ValueError(
                "[rule:spec_execution_lines_b] remove/add lines must match transformation_spec"
            )


def validate_ai_output_strict(
    data,
    dominant_problem_type: str | None = None,
    conflict_context: dict | None = None,
) -> bool:
    if not isinstance(data, dict):
        raise ValueError("Output must be a JSON object")
    validate_required_fields(data)
    validate_confidence_impact(data)
    validate_no_vague_language(data)
    validate_problem_type_matches_dominant(data, dominant_problem_type)
    validate_problem_action_alignment(data)
    validate_primary_action_matches_transformation_type(data)
    validate_primary_action_hard_constraints(str(data.get("primary_action") or ""))
    validate_length(data)
    validate_why_it_matters_stake(str(data.get("why_it_matters") or ""))
    if data.get("structured_pass1"):
        validate_pass1_structured_roles(
            str(data.get("core_problem") or ""),
            str(data.get("page_a_role") or ""),
            str(data.get("page_b_role") or ""),
            str(data.get("primary_action") or ""),
        )
        validate_primary_action_reflects_roles(
            str(data.get("primary_action") or ""),
            str(data.get("page_a_role") or ""),
            str(data.get("page_b_role") or ""),
            conflict_context,
        )
    if conflict_context is not None:
        validate_action_resolves_conflict(
            str(data.get("primary_action") or ""), conflict_context
        )
        validate_execution_example_contrast(
            str(data.get("execution_example") or ""),
            list(conflict_context.get("candidate_urls") or []),
        )

    validate_narrative_matches_transformation_spec(data)

    return True
