"""
Strict, deterministic validation for AI insight JSON (core narrative + alignment).
Used after two-pass insight generation merges with report shell fields.
"""

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

    if pt == "acceptable" and any(x in action for x in ["differentiate", "reposition"]):
        raise ValueError("Acceptable problems cannot require strategic-style actions")

    if pt == "technical" and any(x in action for x in ["reposition", "differentiate"]):
        raise ValueError("Technical problems cannot require strategic actions")

    if pt == "strategic" and any(x in action for x in ["redirect", "canonical"]):
        raise ValueError("Strategic problems should not default to technical fixes")


def validate_no_vague_language(data: dict) -> None:
    for key in ["core_problem", "why_it_matters", "primary_action", "execution_example"]:
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


def validate_ai_output_strict(
    data,
    dominant_problem_type: str | None = None,
) -> bool:
    if not isinstance(data, dict):
        raise ValueError("Output must be a JSON object")
    validate_required_fields(data)
    validate_confidence_impact(data)
    validate_no_vague_language(data)
    validate_problem_type_matches_dominant(data, dominant_problem_type)
    validate_problem_action_alignment(data)
    validate_length(data)

    return True
