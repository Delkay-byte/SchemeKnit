# Phase 7 — Final frozen benchmark + multi-subject export fidelity (2026-10-15)

Final verification run on the complete Phase 0–6 tree (AI OFF / Zeli OFF,
thresholds, floors and frozen fixtures unchanged throughout).

## Final frozen corpora (source of truth: `final_gate_metrics_2026-10-15.json`,
per-criterion detail `final_hardening_2026-10-15.json`)

| corpus | teacher-ready | first pass | mean rubric | repairs | rebuilds | rejected |
|---|---|---|---|---|---|---|
| 11-lesson | 11/11 (100%) | 11/11 | 74.2/75 | 0 | 0 | 0 |
| expanded-40 | 40/40 (100%) | 40/40 | 73.2/75 | 0 | 0 | 0 |
| messy-19 | 19/19 (100%) | 19/19 | 71.9/75 | 0 | 0 | 0 |

Per-criterion means are identical to the Phase 4 run (`current_hardening_phase4_2026-10-15.json`)
— Phases 5–6 changed no generation behavior, exactly as intended (Phase 5 was
crash-recovery only; Phase 6 was read-only).

Trajectory (frozen corpora, same harness `ae84f19`, same fixtures):
31/40 + 12/19 (P2.1 era) → 40/40 + 19/19 after the Phase 1 verb-inventory
correction (reconciled in `CURRENT_BASELINE_2026-10-15.md` §4) → held at
100% with mean rubric rising 72.7→73.2 (expanded) and 71.1→71.9 (messy)
through the Phase 4 differentiation/context/realism work.

## Multi-subject export fidelity
(`backend/tests/test_phase7_multi_subject_export_fidelity.py`, 13 passed)

Six Basic 7 subjects — Mathematics, Science, English Language, ICT, Creative
Arts and Design, Social Studies — generated on the real pipeline
(`GenerationPipeline`, AI OFF, frozen `benchmark_hardening` helpers), then:

- **Default DOCX** (`DOCXExportEngine.export_single`, level-resolved form):
  opens via python-docx; curriculum indicator code present in the document;
  no bare `[`/`]`; no unresolved `{focus…}/{skill…}/{resource…}` placeholders
  or TODO/TBA; introduction + main activities + conclusion all present.
- **Structured PDF** (`structured_pdf.render_structured_pdf`): valid `%PDF-`
  header, ≥1 page, extractable text on every subject.

Golden-master topology compare for the bundled GES form remains covered by
`test_real_science_acceptance` / `test_official_ges_template` /
`test_web_acceptance_http` (all green in the full suite), including the
Phase 4 hygiene fixes (no bare brackets, rubric as text lines so generated
table count stays an exact multiple of the approved source's).

## Verification

- Phase 7 suite: 13 passed (6 subjects × DOCX+PDF + coverage guard).
- Final gate run + hardening run: as tabulated; JSON artifacts committed.
- Full backend suite (post-Phase 4 tree, on which Phases 5–7 sit):
  2419 passed / 16 skipped; PG quota driver gate 22 passed.
- No production data touched; no thresholds, floors or fixtures changed.
