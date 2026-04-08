# AI output — Phase 3 (structured generation scaffolding)

Phase 3 constrains **how** the model fills fields (templates + schema), not more retries or banned-word lists.

## Pass 1 JSON (strict fill-in)

| Field | Purpose |
|--------|---------|
| `core_problem` | One sentence: conflict from framing + `dominant_problem_type`. |
| `page_a_role` | What page A should represent after the change. |
| `page_b_role` | What page B (or alias/single-peer case) should represent. |
| `primary_action` | **One sentence**: exact transformation from overlap → those roles; when two URLs compete, use `;` or ` and ` and cite both URLs or path tails. |

`primary_action` is described in the prompt as **derived from** the two roles (transform A → role A, B → role B), not invented separately.

## Pass 2

- **`why_it_matters`**: include **one** of — a metric reference (`overlap_rate`, similarity, cluster, …) **or** an explicit consequence (ranking conflict, decision ambiguity, conversion friction, …). Not both required.
- **`execution_example`**: multi-line **transformation map**:

```text
On https://…:
- remove: …
- add: …

On https://…:
- remove: …
- add: …
```

Validation (relaxed vs Phase 2): still requires URL binding and structure when two URLs exist, but **does not** require multiple abstract “contrast tokens” — only `remove:`/`replace:` once and **two** distinct `- add:` lines when two URLs are cited.

## Merge output

`generate_ai_insights` sets `structured_pass1: True` and keeps `page_a_role` / `page_b_role` on the insight dict for traceability (report body unchanged).

## Example that passes full strict + `validate_ai_output`

See `tests/test_ai_validator.py` → `test_structured_pass1_passes_full_strict` (NZ/AU comprehensive URLs, restrict/remove language, templated execution).
