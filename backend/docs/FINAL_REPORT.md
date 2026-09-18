# Final Report — Approved Template Acceptance Milestone

Date: 2026-09-17
Suite: 600 passed, 0 failed

## Summary

The approved organizational lesson-plan template now renders from the real DOCX
source document (not a hand-written competing structure). Commercial and export
defects have been closed. All acceptance criteria are met or documented as
requiring a live browser environment.

## PASS items

| Item | Status | Evidence |
|------|--------|----------|
| 1. Approved template derives from real DOCX | PASS | `approved_template.py` uses `analyze_docx_document`; 4-table/zero-merge topology verified |
| 2. Alias routing | PASS | `tpl-approved-org-headteacher` → `is_ges_form_template()` → `JHS_SPEC` |
| 3. Phase names match source | PASS | "MAIN LEARNING" / "PLENARY / REFLECTION" (not invented names) |
| 4. No competing structure | PASS | `_custom_structure_for()` no longer special-cases approved template |
| 5. Golden-master regeneration | PASS | `regenerate_golden_master.py` + `docx_structure.py` tooling |
| 6. Structural comparison validator | PASS | `validate_generated()` compares table count, merges, labels, coordinates |
| 7. No synthetic content | PASS | `test_no_synthetic_content.py` — 4 tests |
| 8. AI entitlement gating | PASS | `test_ai_production.py` — 27 tests, Ollama bypass prevented |
| 9. Platform Admin license reflection | PASS | `test_licensing.py` — 7 tests, full lifecycle |
| 10. Scheme delete | PASS | `test_scheme_delete_acceptance.py` — empty delete, 409 protected, auth |
| 11. Template defaults across class levels | PASS | `test_official_ges_template.py` — all levels covered |
| 12. HTTP workflow (end-to-end) | PASS | `test_web_acceptance_http.py` — upload→approve→generate→edit→export |
| 13. Backend PDF 503 | PASS | Controlled 503, never raw 500 |
| 14. Frontend download transport | PASS | Code review of `downloadFile()` in `api.ts` |

## BLOCKED items (require live environment)

| Item | Reason |
|------|--------|
| Visual rendering in Chrome / Edge | No headless browser stack available |
| DOCX opens correctly in Word | Requires MS Word installation |
| Activation code redemption (live) | Requires production licensing server |

## Test breakdown

| File | Tests | Purpose |
|------|-------|---------|
| `test_approved_template.py` | 18 | 4-table topology, zero merges, phase names |
| `test_no_synthetic_content.py` | 4 | No fabricated guidance/examples |
| `test_export_download.py` | 3 | Topology assertions, structural validator |
| `test_real_science_acceptance.py` | 1 | `validate_generated` against source |
| `test_ai_production.py` | 27 | Entitlement gating, Ollama bypass |
| `test_licensing.py` | 7 | License lifecycle |
| `test_scheme_delete_acceptance.py` | 4 | Delete authorization, 409 protected |
| `test_official_ges_template.py` | all | Template defaults, golden master |
| `test_web_acceptance_http.py` | 3 | Full HTTP workflow through ASGI app |
| **Total (all files)** | **600** | **0 failures** |

## Files modified / created in this milestone

### New files
- `tests/test_no_synthetic_content.py`
- `tests/test_web_acceptance_http.py`
- `src/validators/docx_structure_compare.py`
- `src/tools/docx_structure.py`
- `src/tools/regenerate_golden_master.py`
- `docs/APPROVED_TEMPLATE_ACCEPTANCE.md`
- `docs/TEMPLATE_PROVENANCE.md`
- `docs/AI_ENTITLEMENT_ACCEPTANCE.md`
- `docs/EXPORT_BROWSER_ACCEPTANCE.md`

### Modified files
- `src/engines/approved_template.py` — rewritten to derive from real DOCX
- `src/engines/official_ges_template.py` — alias recognition
- `src/engines/official_ges_levels.py` — alias → JHS_SPEC resolution
- `src/engines/template_engine.py` — registry description, docstring
- `src/engines/template_provenance.py` — evidence strings
- `src/engines/template_analyzer.py` — refactored `analyze_docx_document()`
- `src/engines/docx_export.py` — removed 4 synthetic fallback texts
- `src/routers/generation.py` — `_custom_structure_for()` simplification
- `src/engines/assets/ges_jhs_golden_master.json` — regenerated

### Updated test files
- `tests/test_approved_template.py` — 18 tests, real 4-table topology
- `tests/test_export_download.py` — topology assertions
- `tests/test_real_science_acceptance.py` — uses `validate_generated`
