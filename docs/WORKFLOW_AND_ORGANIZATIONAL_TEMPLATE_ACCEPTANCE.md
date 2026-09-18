# WORKFLOW + ORGANIZATIONAL TEMPLATE FIX — FINAL REPORT

## Status
PASS

## Environment
- Frontend http://localhost:3000, backend http://127.0.0.1:8000, dedicated DB
  `teachflow_web_acceptance.db` (migrations v001–v008), v1.0.3 both layers.
- Teacher: Test Teacher. Real Chrome browser throughout.
- Note: `/mnt/data/` does not exist on this machine; the accepted file used is the
  identical teacher document `MY-SCIENCE-WEEK 2-LESSON PLAN.docx`; current outputs are
  the TeachFlow-generated DOCX files from this environment.

## Workflow
- Upload Scheme: PASS (fresh scheme → upload ✓, review ACTIVE, rest LOCKED)
- Review Curriculum: PASS (approve persists review → review ✓, configure ACTIVE)
- Approve & Configure: PASS (job creation marks configure ✓)
- Generate Plans: PASS (completed job + 12 lessons → generate ✓; only after success)
- Review & Export: PASS (export event logged → all five ✓)
- Refresh persistence: PASS (identical strip after reload; identical after fresh logout/login)

## Organizational Template
- Metadata table structure: PASS (11×8 / 2×3 / 12×8 per lesson, 36 tables total)
- 8-column layout: PASS
- Merge structure: PASS (gridSpan multisets identical per lesson block)
- Content Standard / Indicator layout: PASS (values placed: 9.1.1.1, B9.1.1.1.1)
- Performance Indicator / Competencies: PASS (labels + mapped values)
- References / New Words: PASS (labels kept; blank where no data source — never sample text)
- Phase / Learners Activities / Resources grid: PASS (header + column roles preserved)
- Phase 1 / Phase 2 / Phase 3: PASS (starter→introduction, main→activities, reflection→assessment)
- Batch rendering: PASS (same `render_custom_template` path; unit + live verified)
- ZIP rendering: PASS (12 members, each 3-table org structure, activities in cells, no leak)
- Sample content leakage: PASS (01/05/2026, Forces & Energy, B7.x, 60mins, sample prose all absent)

## Browser Evidence
- Dashboard strip after full journey: all five stages ✓ (screenshot `/tmp/wf_completed.png`,
  `/tmp/wf_final.png`); refresh-identical and fresh-login-identical verified by text comparison.
- Wizard re-run with upgraded analyzer: 15 labels / 3 tables → correction → preview →
  saved "Org Format JHS Science" → level-filtered dropdown → Start New Generation →
  12 lessons → DOCX download (`C:\tmp\core_exports\org_math2.docx`).
- Structural validator report on the downloaded DOCX: 17/17 checks PASS (table count,
  per-lesson dimensions, merge patterns, activity grids, all labels, 6 placed values,
  6 foreign-absence checks).

## Tests
- Backend: **289 passed** (was 271; +11 workflow-state, +7 structural).
- TypeScript: clean (`tsc --noEmit`).
- Structural DOCX: validator + unit tests cover 8-col grid, merges, placement, activity fill,
  batch/ZIP parity, no-leak, empty-structure fallback.
- Browser: stepper states at each transition, wizard, preview, version (→1.1), archive,
  level filter, regenerate, exports, regression (dashboard/review/lessons/generate intact).

## Files Changed
- `backend/src/service.py` — `compute_workflow_state`, `REVIEWED_STATUSES`, export-event
  helpers, `scheme_exists` (prior milestone), version/archive helpers.
- `backend/src/database.py` — `ExportEventDB`; `TemplateDefinitionDB` lifecycle columns (prior).
- `backend/src/migrations/v008_export_events.py` — new (v007 prior).
- `backend/src/routers/documents.py` — `GET /{scheme_id}/workflow`.
- `backend/src/routers/generation.py` — export-event logging (4 endpoints); `_db_to_lesson_model`
  now parses activities/objectives instead of dropping them (root cause of empty grid cells
  and of generic fallback text in built-in exports); custom-structure resolution (prior).
- `backend/src/engines/template_analyzer.py` — activity-grid detection (header + roles +
  phase kinds + continuation inference), `validate_custom_docx` with per-lesson blocks.
- `backend/src/engines/docx_export.py` — role-based cell fill (`_activity_block`,
  resources, structural headers), vertical-merge rendering.
- `backend/src/engines/generation_pipeline.py`, `zip_export.py` — custom-structure paths (prior).
- `frontend/src/app/dashboard/page.tsx` — stepper reads persisted workflow state (fixed a
  hooks-order crash found during testing).
- `frontend/src/app/generate/[id]/page.tsx` — level-filtered templates, Start New Generation (prior).
- `frontend/src/lib/api.ts` — `getSchemeWorkflow` (+ template APIs prior).
- Tests: `test_workflow_state.py`, `test_template_structure.py` new.

## Known Limitations
- ZIP *browser-click* transfer still fails in this machine's Chromium (unchanged, out of scope
  per §30; ZIP bytes proven valid repeatedly). PDF export optional and still engine-limited.
- `setup-school-admin` public-endpoint issue remains on the security backlog (untouched).
- Deleting a scheme orphans its storage file (pre-existing minor gap, untouched).
- Pixel-perfect fidelity not claimed: fonts/spacing approximate; phase-marker names
  (e.g. "PHASE 1: STARTER") are treated as template structure and kept verbatim.
- The duplicate fresh Math scheme (Part A journey vehicle) remains in the workspace;
  second teacher account likewise — both documented test records.
