# AI output layer — Phase 2 (conflict resolution)

Phase 2 tightens validation and prompts so `primary_action` **resolves** competing URLs/intent, not only describes them. Clustering and `dominant_problem_type` are unchanged.

## Before vs after (illustrative)

| Field | Before (weak but valid) | After (target shape) |
|--------|-------------------------|----------------------|
| `primary_action` | “Differentiate coverage details” | “Assign AU pages to Australia pricing and claims; restrict NZ pages to NZ coverage; remove overlapping messaging.” |
| `execution_example` | “Rewrite both URLs to be more distinct.” | “On `https://…/nz/…`, remove generic intro and replace with NZ claims examples; on `https://…/au/…`, retain AU pricing and strip NZ references.” |
| `why_it_matters` | “Improves clarity for users.” | “High `overlap_rate` and tight cluster similarity split ranking signals and create decision ambiguity between URLs.” |

## New validation (`app/ai_validator.py`)

- **`validate_action_resolves_conflict(primary_action, context)`** — By `dominant_problem_type`: technical needs consolidate verbs; strategic needs remove/replace/restrict/assign/split/merge/delete/rewrite; blocks add-only strategic patches; when `competing_pages_roles_required`, both `page_a_url` and `page_b_url` (or path tails) must appear in `primary_action`.
- **`validate_why_it_matters_stake`** — Requires metric- or outcome-related terms; rejects generic UX phrases.
- **`validate_execution_example_contrast`** — With two cited URLs, requires clause separation (`;` or two `on https` segments) and at least two contrast tokens (remove/replace/retain/restrict/only/separate/distinct/etc.).

`validate_ai_output_strict(..., conflict_context=...)` runs stake checks always; conflict + execution contrast only when `conflict_context` is provided (two-pass merge path).

## Prompt / framing (`app/ai_insights.py`)

- **`ai_framing`**: adds `competing_pages_roles_required`, `page_a_url`, `page_b_url` (deduped from remediation clusters).
- **Pass 1**: conflict-resolution rules, BAD/GOOD examples, `primary_action` max **32** words, role assignment for competing pair.
- **Pass 2**: metrics snippet for `why_it_matters`; execution example explicit BEFORE/AFTER separation.
- **Retries**: stronger emphasis on resolution, contrast, and stake — rules are not relaxed.

## Report (`app/report.py`)

Unchanged in Phase 2; executive blocks still map 1:1 to validated fields when `validated_ai_narrative` is set.
