# AI output — Phase 4 (deterministic transformation spec)

## What changed

- **`transformation_spec`** is built in `app/transformation_spec.py` before any insight LLM work. It encodes URLs, roles, and `remove_from_*` / `add_to_*` lists using `dominant_problem_type`, cluster rows (`decision_type`, `duplication_class`, `page_type`, `intent`, `decision_stage`), and market relationship (`cross_market` vs `intra_market` from `business_context.market_context` + `is_cross_domain`).
- **`generate_ai_insights`** no longer calls Pass 1 / Pass 2 JSON generation for the core narrative. It **renders** `core_problem`, `primary_action`, `page_a_role`, `page_b_role`, `why_it_matters`, and `execution_example` from that spec plus payload metrics.
- **`analysis_payload`** and **`payload_for_ai`** include `transformation_spec` (assembled in `app/main.py`).
- **Strict validation** (`validate_narrative_matches_transformation_spec` in `app/ai_validator.py`) runs when `insights_rendered_from_spec` is true: roles must match the spec byte-for-byte, and each `On URL:` block’s `- remove:` / `- add:` lines must match the spec’s first list entries for that URL.

The roadmap generator (`generate_execution_roadmap`) is unchanged and may still use the LLM.

## Example (cross-market strategic)

**`transformation_spec` (abbreviated)**

- `page_a_url`: `https://www.scti.co.nz/our-policies/comprehensive`
- `page_b_url`: `https://www.scti.com.au/our-policies/comprehensive`
- `page_a_role`: New Zealand market page: coverage, pricing, and claims for New Zealand buyers.
- `page_b_role`: Australia market page: coverage, pricing, and claims for Australia buyers.
- `remove_from_a` / `add_to_a`, `remove_from_b` / `add_to_b`: region-specific shared-messaging removal and proof rows (see builder).

**Rendered narrative**

- **primary_action**:  
  `Restrict https://www.scti.co.nz/... to New Zealand-specific coverage and remove shared messaging; restrict https://www.scti.com.au/... to Australian pricing and proof.`

- **execution_example**:

```
On https://www.scti.co.nz/our-policies/comprehensive:
- remove: Shared generic messaging mirrored on the regional sibling site
- add: New Zealand-specific proof, limits, and policy rows

On https://www.scti.com.au/our-policies/comprehensive:
- remove: Copy blocks reused from the other regional policy or product page
- add: Australia-specific pricing rows and local customer proof
```

- **why_it_matters**: Interpolates `overlap_rate`, `avg_cluster_similarity`, and (if needed) `content_uniqueness_score` from `payload.metrics`, then ties them to ranking/conversion path language (validator-safe stake wording).

## Tests

- `tests/test_ai_validator.py` — `test_transformation_spec_render_passes_strict` covers NZ/AU cross-market spec build, render, and full `validate_ai_output_strict`.
