# Approved Template Acceptance

Status: **PASS**

## What was verified

The approved organizational lesson plan template (`tpl-approved-org-headteacher`) is
rendered directly from the real DOCX source document — `ges_jhs_lesson_plan_template.docx`
— not from a hand-written competing structure.

### Structural fidelity (4 tables, zero merges)

| Table | Purpose | Rows |
|-------|---------|------|
| 1 | Header fields (school, teacher, dates) | 4 |
| 2 | Column headers (Topic, Duration, Aim, etc.) | 1 |
| 3 | Phase 1 – Starter / Intro | 5 |
| 4 | Phase 2 – Main Learning + Phase 3 – Plenary / Reflection | 8 |

All 4 tables have zero merge cells. The previous `approved_template.py` hand-wrote
a wrong 3-table / 8-column / merged-cell structure that drifted from the real source.
This is now fixed: the golden-master IR is derived from the real DOCX via
`analyze_docx_document` + token-field pinning.

### Phase names match the source exactly

- "PHASE 1: STARTER / INTRO"
- "PHASE 2: MAIN LEARNING"
- "PHASE 3: PLENARY / REFLECTION"

Phase durations "(10 Mins)"/"(40 Mins)"/"(10 Mins)" are printed by the source
document itself, not by TeachFlow logic.

### Alias routing

`tpl-approved-org-headteacher` → `is_ges_form_template()` returns `True` →
`spec_for_template_id()` returns `JHS_SPEC` → in-place render of the real form.

No competing structure exists. The generation router's `_custom_structure_for()`
no longer special-cases the approved template ID; single-lesson + template_id
routes to the combined document.

### Golden-master regeneration tooling

- `src/tools/regenerate_golden_master.py` — regenerate `ges_jhs_golden_master.json`
  from the real DOCX
- `src/tools/docx_structure.py` — structural fingerprint tool
- `src/validators/docx_structure_compare.py` — structural + content comparison
  against the approved source

### Test coverage

- `test_approved_template.py` — 18 tests against real 4-table topology
- `test_no_synthetic_content.py` — 4 tests for no-fabrication rule
- `test_export_download.py` — topology assertions + structural validator
- `test_real_science_acceptance.py` — uses `validate_generated` against source

### What is NOT verified (requires live browser)

- Visual rendering in Chrome / Edge (section 16-17)
- These are documented in `EXPORT_BROWSER_ACCEPTANCE.md`
