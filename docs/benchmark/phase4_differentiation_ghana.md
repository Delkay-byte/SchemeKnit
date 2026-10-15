# Phase 4 — differentiation anchoring, Ghana context, resource realism (2026-10-15)

Deterministic-only change set (AI OFF, Zeli OFF). Frozen corpora rerun unchanged;
no thresholds, floors or fixtures were modified.

## Edits

1. `patterns.py` — pattern 13 `creative_demo_creation_critique`: step 3
   `activity_key` `discussion` → `critique`, so creative-arts lessons route to
   the subject's own critique/feedback move instead of falling through to the
   CREATION move (which repeated the creation instruction as the "share and
   critique" step). Career/english chains unchanged by construction (no
   `critique` key → same fall-through as before).
2. `lesson_builder.py` — differentiation block: lowercase the first word of the
   core-evidence clause after "the teacher checks that …" (bank evidence
   entries are full sentences); `_anchor_tier()` names THIS indicator's task
   ("… on {focus_short}.") when a support/challenge template does not already
   interpolate `{focus…}`.
3. `lesson_builder.py` `_PHASE_BANK` — targeted specificity + resource realism:
   comparison rows (grouping, quantities, "chart paper"), classification rows
   (each-learner list, "writes one sentence … using {resource}"), demonstration
   row ("one worked example … to the whole class"), writing row ("checklist of
   three points").
4. `pedagogy.py` english — demonstration/reading moves reworded with grouping
   (whole class / pairs), quantities (one/two) and product verbs
   (note/write/underline).
5. `activity_library.py` — `ghana_context` added to three ICT activities
   (`label_annotate_diagram`, `sequence_the_steps`, `troubleshoot_and_fix`),
   each naming community/local settings learners can actually point to.
6. DOCX/PDF export hygiene (pre-existing failures fixed in this phase):
   DoK prompts no longer wrapped in bare square brackets (approved-template
   content check forbids `[`/`]` anywhere), and the Phase 3 rubric is emitted
   as text lines instead of a table so the approved-source table-topology
   contract (generated table count must be an exact multiple of the source's)
   holds on every export path. `structured_pdf.py` bracket fix included.

## Frozen-corpus results (before = `current_*_2026-10-15.json`, after = raw
`current_*_phase4_2026-10-15.json` in this directory)

| corpus | teacher-ready | mean rubric | activity_specificity | resource_realism |
|---|---|---|---|---|
| 11-lesson | 11/11 → 11/11 | 73.7 → 74.2 | 4.64 → 4.91 | 4.55 → 4.73 |
| expanded-40 | 40/40 → 40/40 | 72.7 → 73.2 | 4.58 → 4.92 | 4.55 → 4.78 |
| messy-19 | 19/19 → 19/19 | 71.1 → 4.79* | 4.21 → 4.79 | 4.47 → 4.74 |

*mean rubric messy-19: 71.1 → 71.9. Every other criterion mean was unchanged
on all three corpora (no regressions). No hard-failure counts changed.

## Verification

- Full backend suite: 2419 passed, 16 skipped (includes the four previously
  failing DOCX content-hygiene/topology acceptance tests, now green).
- PG quota driver gate: 22 passed (postgres:16, container `schemeknit-pg-quota`).
- No production data touched; no thresholds, rubric floors or frozen fixtures
  changed.
