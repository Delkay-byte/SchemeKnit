# Curriculum-Grounded Lesson Workspace — Evolution Report

Branch: `main` · Repository: `SchemeKnit` (local `TeachFlow`)
Scope: evolve SchemeKnit from a *lesson-plan generator* into a
**curriculum-grounded lesson workspace** without redesigning the app, replacing
Gemini, or weakening curriculum authority, WAPEF, auth or exports.

> **Status: NOT READY — PRODUCTION ACCEPTANCE INCOMPLETE.**
> The full teacher journey is verified end-to-end against a locally running
> production build (60/60 browser checks, real DOCX and PDF bytes). The live
> Render acceptance run could **not** be executed from this environment because
> the deployed teacher credentials are not present in the repository. See
> §15–17 and §23. Do not treat this as launch-ready.

---

## 1. Architecture audit (what the pipeline actually is)

| Stage | Module / route | State found |
|---|---|---|
| Upload | `routers/documents.py` `POST /upload` | working, multi-subject detection |
| Parsing | `parsers/*`, `curriculum/__init__.py` (Curriculum IR) | working, single IR, no second parser |
| Persistence of extracted curriculum | `WeekDB` rows written once at upload / subject-confirm | working, authoritative |
| Curriculum IR | `curriculum/__init__.py` — `Indicator`, `CurriculumEntry`, `CurriculumWeek`, `split_indicator_text` | working |
| Allocation | `engines/allocation_engine.py` + `calendar_engine`, `coverage_validator` | working: indicator→period, carry-forward, special periods |
| Allocation preview | `routers/generation.py` `POST /{scheme_id}/allocation-preview` | working |
| Generation | `engines/generation_pipeline.py`, `routers/generation.py` | working: deterministic core + optional AI enrichment |
| Quality gate | `curriculum/quality_gate.py` | working; bounded retry, 0 credits on failure |
| AI provider | `engines/ai_provider.py` (Gemini) | working, provider abstraction intact |
| Lesson persistence | `LessonPlanDB` | working |
| Scheme review page | `app/(app)/review/[id]/page.tsx` | week navigation + detail |
| Lesson review page | `app/(app)/lessons/[id]/page.tsx` | per-phase editing + AI suggest |
| Export | `engines/docx_export.py`, `pdf_export.py`, one-time `/downloads/{token}` | production-verified in a prior phase |
| Entitlement | `entitlements.py`, `routers/platform_admin.py` | server-authoritative FREE/PRO |
| Auth | `auth.py`, `security.py`, sessionStorage tab isolation | working |

## 2. What already existed

Everything in the table above, plus `lesson_review_drafts` (a teacher-editable
draft store that deliberately excludes source-authoritative fields), the
allocation carry-forward logic, special-period handling, WAPEF
(Basic 4–JHS and Basic 1–3 separately), the monthly AI quota / lesson quota, and
the DOCX/PDF export chain. **None of it was rewritten.**

## 3. What actually changed

This change set is additive: seven patterns translated into the existing
architecture.

| Layer | Change |
|---|---|
| Backend | New `curriculum/spine.py` (the Curriculum Spine) |
| Backend | `GET /api/curriculum/{scheme_id}/spine` |
| Backend | `GET /api/generation/lessons/{lesson_id}/provenance` |
| Backend | `_serialize_lesson` now carries `provenance` |
| Backend | Weeks endpoint carries `week_type_label`, special-period fields, `review_status`, `review_reasons` |
| Backend | Allocation preview rows carry `period`, `needs_review`, `source_provenance` (incl. `source_review_status`) |
| Backend | `period` added to the teacher-editable draft allow-list |
| Frontend | `components/lesson-workspace.tsx` (new) |
| Frontend | `components/source-alignment.tsx` (new) |
| Frontend | Generate page: workspace-first after generation, Quick/Guided mode, allocation period editor |
| Frontend | Review page: extraction verification table + "Needs review" banner |
| Frontend | Lesson review page: "Source & alignment" panel |
| Tests | `tests/test_curriculum_spine_and_provenance.py` (24 tests) |
| Acceptance | `e2e/curriculum-workspace-acceptance.js` |

## 4. Curriculum Spine changes (Pattern 4)

`backend/src/curriculum/spine.py` introduces the persistent representation of a
processed scheme. Design decisions, deliberately:

* **No second parser, no second store.** The spine is *derived* from the
  already-persisted `WeekDB` rows. Because it is derived on read, a source
  replacement can never leave a stale cached curriculum behind.
* **`spine_version`** is a content hash over the source filename + subject +
  class + term + every week's type/strand/sub-strand/standards/indicators/
  resources. It changes whenever the curriculum changes, so derived caches have
  a correct invalidation key (Pattern: caching).
* **`build_week_spine`** exposes strand, sub-strand, content standards,
  indicators (code + text via the canonical `split_indicator_text` — not a new
  splitter), resources, special-period metadata and a teacher-facing review
  state.
* `GET /api/curriculum/{scheme_id}/spine` is owner-enforced (403 for another
  user's scheme, 404 for unknown).

The word "spine" is internal; teachers see it as the extracted-curriculum table
and the "Source & alignment" panel.

## 5. Scheme extraction / review changes (Pattern 2)

* `classify_week_review` returns `ok` / `needs_review` / `special`:
  * non-instructional week → `special` (a real curriculum state, **not** a parse
    failure);
  * instructional week with no indicators → `needs_review`;
  * instructional week with no strand **and** no sub-strand **and** no content
    standard → `needs_review`;
  * otherwise `ok`.
* Reasons are **teacher-facing** ("No indicators were found for this week.").
  A test asserts no parser jargon (`confidence`, `parser`, `fallback`,
  `malformed`, `score`) can appear.
* The review page renders an extraction table (`data-extraction-table`) with
  Week / Strand / Sub-strand / Indicator / Status, uses "✓ Parsed" and
  "⚠ Needs review", and lists the affected weeks in a calm warning banner that
  states the weeks stay exactly as read and are never filled with guessed
  content.
* Clicking a row selects that week and populates the week pane.
* **No second parser was created** — the table reads `GET /{scheme_id}/weeks`,
  which is itself built from the spine.

## 6. Allocation changes (Pattern 1)

Allocation is now explicit and teacher-adjustable **without destroying the
existing carry-forward logic**:

* Existing allocation engine untouched (indicator → period, carry-forward,
  special periods, `week ≠ lesson count`).
* Preview rows now carry, per lesson: `period` (teacher-editable, from the saved
  draft or blank — never invented), `needs_review`, and a `source_provenance`
  record (source week, teaching week, strand, sub-strand, content standard,
  indicator code + text, carry-forward, source-week review state).
* `period` was added to the draft allow-list alongside `keywords`,
  `other_tlrs`, `core_competencies`, `structured_references`, the four WAPEF
  fields and `remarks`. Source-authoritative fields (`indicator_code`,
  `strand`, …) remain **not** writable through a draft — asserted by test.
* The generate page shows one small "Teaching period / day" input per lesson
  with an intelligent placeholder, so the teacher is reviewing rather than
  typing.

## 7. Workspace changes

`components/lesson-workspace.tsx` is the curriculum-grounded lesson workspace.
It answers the four questions at once:

1. **Context** — subject, class, week, teaching day, period.
2. **Source & alignment** — collapsed by default, and a "This week needs review"
   banner only when the source week genuinely needs review.
3. **The lesson** — topic, objectives, Phase 1 Starter, Phase 2 Main Learning
   (structured activities, editable, add/remove), Assessment, Phase 3
   Reflection, resources, references, core competencies, keywords, WAPEF.
4. **Actions** — Save, contextual per-section "Suggest", Export DOCX/PDF. No
   provider chatter, no advanced-prompt controls.

States handled: loading, generated, AI enriched / AI unavailable (via
`aiFailure`), source-needs-review, saved, **unsaved changes**, export in
progress / success / failure. A special period renders as a period banner with
**no lesson fields** — it never becomes a fake lesson.

The workspace leads the generate page's main column, so the first screen after
generation contains the real lesson — not a success toast, not an empty editor.

## 8. Quick Generate / Guided Build (Pattern 7)

* **Default: Quick Generate** — scheme → week → period → generate → complete
  draft. The default is asserted in the browser acceptance.
* **Secondary: Build with me** — opt-in, persisted in `localStorage`; the
  workspace then reveals one section at a time (objectives → starter → main →
  assessment → reflection) with "Looks good, next" and per-section Suggest.
  Accept / edit / regenerate / skip are all available.
* Guided mode is never the default and never adds setup questions before value.

## 9. Quality-gate changes (Pattern 5)

**No quality-gate changes were made.** The existing gate is preserved
unchanged: schema → curriculum → pedagogical → quality gate with bounded retry,
and 0 AI credits for a failed AI call, malformed response, provider failure,
quality-gate failure or deterministic fallback. No arbitrary score was
introduced, and no existing check was weakened. The accepted/rejected outcome
still routes to teacher review or deterministic fallback.

## 10. Provenance behaviour

* Every serialized lesson now carries `provenance` (scheme, curriculum source
  "Teacher scheme", source week, teaching week, strand, sub-strand, content
  standard, indicator code + text, period, carry-forward, generation path, AI
  provider when there was one).
* `lesson_provenance` also reports **`source_review_status`,
  `source_review_reasons` and `source_week_type`**, read from the same spine.
  With no resolvable scheme it reports `null` ("unknown") rather than claiming
  the week is fine.
* The generation path is stated honestly: "Curriculum-first (deterministic)" or
  "Curriculum-first + AI enrichment".
* UI: compact collapsed "Source & alignment" panel on the workspace **and** on
  the lesson review page.

## 11. Empty / uncertain state behaviour

* Uncertain extraction → `needs_review` with a reason (never invented).
* Special period → `special`, rendered as a period, no lesson fields.
* No scheme resolvable for provenance → empty scheme string + `null` review
  state (a test asserts this is truthful, not fabricated).
* No indicators → "No indicators were found for this week."
* Allocation uncertainty → `needs_review` on the preview row.
* Nothing substitutes generic model knowledge for missing curriculum evidence.

## 12. Entitlement compatibility

No entitlement model was added or duplicated. The FREE/PRO system remains
server-authoritative; the curriculum parser, extraction review, allocation and
provenance are **not** gated by entitlement, and AI/lesson quota concepts stay
separate. Verified by the pre-existing entitlement suite plus the production
FREE→PRO→revoke cycle recorded in `REMEDIATION_ENTITLEMENT_AND_DOWNLOADS.md`.

## 13. DOCX download root cause and fix

Root cause was identified and fixed in an earlier phase, not in this one:
exports were requested per worker but the one-time download token did not
survive multiple workers, and generic 500 responses lacked the CORS header so
the browser reported an opaque "Failed to fetch" instead of the real error.
Fix: persist one-time download tokens (`4ceb046`), echo the configured origin
from the exception handler and log the traceback, and surface real causes
(`2927890`, `cc5fc6e`). This change set re-verified the path end-to-end.

## 14. PDF download root cause and fix

Root cause: Render has neither MS Word nor LibreOffice, so every PDF was a
controlled 500. Fix (`f2b84a5`): PyMuPDF (already pinned) joins the converter
chain last (Word → LibreOffice → PyMuPDF), producing real PDFs with no infra
change. Re-verified here: 141,095 bytes, `%PDF-` header, `application/pdf`,
`.pdf` filename, and the file parses to its trailer/EOF.

## 15. Production browser acceptance

**NOT PERFORMED against the deployed environment in this run.**
`schemeknit-api.onrender.com/api/health` answers `200` (the deployment is
reachable), but the acceptance teacher credential is not present in the
repository and `accept.teacher@schemeknit.test / Accept#2026` returns `401` in
production. The harness is written and runnable:

```bash
TF_WEB_URL=https://schemeknit-frontend.onrender.com \
TF_API_URL=https://schemeknit-api.onrender.com \
TF_TEACHER_EMAIL=… TF_TEACHER_PASSWORD=… \
node frontend/e2e/curriculum-workspace-acceptance.js
```

## 16. Actual DOCX verification

Performed against a locally running production build (`next build` + `next start`),
through the workspace's own Export DOCX button:

* browser download reached disk — `Lesson_Plans_accept_single_science.docx`, 39,682 bytes
* final file request `HTTP 200`, MIME `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
* `PK\x03\x04` signature
* **opens**: contains `[Content_Types].xml` and `word/document.xml`

## 17. Actual PDF verification

* browser download reached disk — `Lesson_Plans_accept_single_science.pdf`, 141,095 bytes
* `HTTP 200`, MIME `application/pdf`, `.pdf` filename
* `%PDF-` signature
* **opens**: header + `startxref`/`trailer` + `%%EOF`

## 18. Test totals

* Full backend suite: **1549 passed, 11 skipped** (`python -m pytest -q`).
* New file `tests/test_curriculum_spine_and_provenance.py`: **24 passed**
  (extraction review status, teacher-facing reasons, spine shape, spine version
  stability and change-on-replacement, spine endpoint authorisation
  owner/other/unknown, weeks review status, provenance shape, provenance review
  state, provenance without a source, provenance endpoint owner enforcement,
  allocation period draft persistence + application, source fields not writable
  through drafts, allocation preview provenance/period round-trip, allocation
  preview review state).

## 19. Typecheck result

`npx tsc --noEmit` — **clean** (exit 0).

## 20. Build result

`NEXT_PUBLIC_BUILD_TARGET=web npx next build` — **Compiled successfully**,
38/38 static pages generated, no errors.

## 21. Browser acceptance result

`node e2e/curriculum-workspace-acceptance.js` against the local production
build — **60/60 checks passed**, covering:

* login through the real form;
* upload a real scheme → "Curriculum extracted" → Review Curriculum;
* the curriculum spine API (5 weeks, every week carrying `ok`/`needs_review`/`special`);
* the extraction table (rows, teacher-facing wording, no parser diagnostics, row click selects);
* **Quick Generate is the default** and Build with me is offered;
* editable teaching period per lesson; allocation rows carry provenance and a review state;
* generation completes and the workspace opens with the real lesson;
* every section renders (topic, objectives, Phase 1, Phase 2, Assessment, Phase 3);
* Source & alignment names scheme, week, indicator and generation path;
* provenance API answers "why this lesson?" and never fabricates a source;
* Main Learning edit → undefined-changes signal → Save → reload persistence;
* DOCX and PDF download with bytes, MIME, filename and open checks;
* no "Failed to fetch", no "Action failed", no uncaught page errors;
* mobile 390×844: lesson visible, Save and Export reachable, no horizontal
  overflow on the extraction table or the workspace, Source & alignment collapsed.

Artifacts: `frontend/e2e/curriculum-workspace-acceptance/`
(`results.txt`, `workspace-1440.png`, `workspace-390.png`, `workspace.docx`, `workspace.pdf`).

## 22. Commit hashes

**Not committed.** This change set is uncommitted in the working tree; no
`git commit` was run because committing was not explicitly authorised. Files
changed/added: see §3, plus `frontend/package.json`
(`e2e:workspace` script).

## 23. HEAD == origin/main

**Unknown/pending.** No `git push` was run (pushing can break production and was
not explicitly authorised). The local branch is `main` with uncommitted changes,
so `HEAD == origin/main` cannot be asserted for this work.

## 24. Tracked tree clean

**No.** The tracked tree has 8 modified files plus 7 new source files (the rest
of the untracked list is generated acceptance output and scratch files from
earlier phases).

---

## Regression set (quality benchmark)

The browser harness uploads a real Ghanaian scheme fixture and traces
SOURCE → CURRICULUM SPINE → ALLOCATION → GENERATED LESSON → EXPORTED DOCUMENT
for one subject; the backend suite exercises Mathematics allocation/carry-forward
and multiple indicators, special periods, WAPEF, quota and entitlement. A full
multi-subject regression corpus (Science, English, ICT, Social Studies, RME,
Creative Arts, PHE, KG, WAPEF plan, special period, multi-indicator week,
carry-forward, DOCX and PDF uploads) is **not** yet assembled as a single
repeatable benchmark — that remains outstanding.

## Honest gaps

1. **Live production acceptance was not run** (credentials unavailable) — the
   single most important outstanding item.
2. The regression benchmark corpus named in the spec is not yet a single
   repeatable fixture set.
3. Nothing has been committed or pushed.
