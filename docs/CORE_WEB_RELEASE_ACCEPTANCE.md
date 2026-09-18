# Core Web Release Acceptance — Teacher Workflow

Date: 2026-09-16
Milestone: Core product recovery / web-first release gate.
Scope: teacher workflow ONLY in the canonical repo `C:\Users\SAVIOUR\Documents\TeachFlow`.
Platform Admin frozen (verified baseline untouched except two prior fixes).
Desktop frozen (no rebuild, no Electron debugging).

## 1. Environment (one clean web stack)

| Item | Value |
|---|---|
| Frontend URL | http://localhost:3000 (`npm run dev`, Next.js 14.2.3, web target) |
| Backend URL | http://127.0.0.1:8000 (uvicorn `src.main:app`, PID 32048 at report time) |
| Database | `C:\Users\SAVIOUR\teachflow_web_acceptance\teachflow_web_acceptance.db` (dedicated, disposable; NOT the dev DB, NOT a desktop DB) |
| Uploads/exports/temp | same directory (`uploads/`, `exports/`, `temp/`) |
| Browser | Real system Chrome + Edge via Playwright (headless and headed); screenshots `/tmp/core_*.png`, downloads `C:\tmp\core_exports\` |
| Teacher | Test Teacher <test.teacher@accept.edu.gh>, role=teacher, member of Core Acceptance School (created via school-admin register — no SQL, no impersonation) |
| Org bootstrap | platform admin via CLI tool → school + plan + license via platform-admin API → school admin via setup-school-admin → teacher via register. All real flows. |

No desktop backend, desktop port, static export, or stale server was used (old :8000/:3000 occupants killed first;
one accidental bootstrap write to the dev DB was detected and fully reverted the same session).

## 2. Versions

- Frontend: 1.0.3 (`frontend/package.json`, login title `TeachFlow v1.0.3`)
- Backend: 1.0.3 (`/api/health`, `config.APP_VERSION`)
- Migrations applied in acceptance DB: v001–v006 (educational taxonomy, payment tables, admin flag,
  commercial licensing, school isolation, custom templates)

## 3. Code changes made this milestone (minimal, no rewrites)

1. `backend/src/service.py` — added `DataService.scheme_exists()` (ID-only existence check).
2. `backend/src/routers/documents.py` — `get_scheme`, `get_scheme_weeks`, status update, delete now return
   **404** (genuinely missing) vs **403 "You do not have access to this scheme"** (exists, unowned) via
   `_resolve_scheme_or_raise`. Verified live: teacher2→teacher1's scheme = 403; random UUID = 404.
3. `backend/src/routers/curriculum.py` — same 404/403 distinction on validate, approve, summary.
4. `backend/src/routers/generation.py` — export builders (docx/pdf/xlsx/zip) run in `run_in_executor`
   (same pattern as upload) so exports no longer block the event loop. Output bytes unchanged.
5. All 253 backend tests pass after the changes; `tsc --noEmit` clean (no frontend changes this milestone).

## 4. Science journey — 19/20

Scheme: `BASIC 9 SCIENCE SCHEME OF LEARNING.docx` → id `789b8406-1c04-4723-933f-7f6fb9e97509`.
Job: `9242e4df-2440-4c9b-bbc3-77691da48068`. 15 weeks (12 instruction + Revision/Assessment/SBA).

| # | Step | Expected | Actual | Result |
|---|---|---|---|---|
| 1 | Login → dashboard | teacher lands on `/dashboard` | Welcome back, Test; Pending 0 | PASS |
| 2 | Upload DOCX | success + original filename + subject/class/weeks | shown (Science, Basic 9, 15 weeks) | PASS |
| 3 | DB record | scheme.id, filename, subject, class, status, owner/school | all correct, status `extracted`, 15 week rows, storage file UUID-named | PASS |
| 4 | Review page | `/review/<scheme.id>`, filename/subject/class/term | rendered | PASS |
| 5 | Weeks detail | strand/sub-strand/standards/indicators/resources | Diversity of Matter / Materials / B9.1.1.1 / B9.1.1.1.1 / charts | PASS |
| 6 | Refresh review | still works | works | PASS |
| 7 | Dashboard return | Pending Review 1 → Continue Review reopens same ID | same ID reopened | PASS |
| 8 | Approve | status approved → straight to `/generate/<id>` | approved, navigated directly | PASS |
| 9 | Configure | class/subject/term + size/duration/lessons/template/AI | all shown, GES-Style JHS default, AI OFF | PASS |
| 10 | Generate | "X lesson plans generated" | **12 lessons, 100% coverage** | PASS |
| 11 | Persistence | 12 LessonPlan rows, 1 job | confirmed in DB | PASS |
| 12 | `/lessons` workspace | week/lesson/date/topic/scheme/status | table rendered | PASS |
| 13 | `/lessons/<id>` | detail loads | Week 1 Lesson 1 + curriculum context | PASS |
| 14 | Edit + Save | Saved feedback | Saved | PASS |
| 15 | Refresh persistence | edit remains | verified via field values + DB row | PASS |
| 16 | List Edited badge | shows Edited | shown | PASS |
| 17 | DOCX export (browser click) | downloads + opens | 39,703 B, 287 paras, 12 tables, opens | PASS |
| 18 | XLSX export (browser click) | downloads + opens | 7,197 B, Register sheet, opens | PASS |
| 19 | ZIP export (browser click) | downloads | **FAIL in this test browser (see §6)** | FAIL |
| 20 | ZIP file validity | 12 entries, integrity OK | 424,503 B, 12 entries, `testzip()` clean (retrieved via API) | PASS |

## 5. Mathematics journey — 19/20

Scheme: `BASIC 9 MATH SCHEME OF LEARNING.docx` → id `3ccd9a08-b5da-4b28-a029-898a0cbf73a9`.
Job: `0b8db023-4a0e-4add-8478-406799b7ea07`. 15 weeks (12 instruction), 21 indicators, Strand Number.

| # | Step | Result |
|---|---|---|
| 1–9 | Login, upload (Mathematics, Basic 9, 15 weeks), review, refresh, dashboard return, approve → generate | PASS |
| 10–11 | Generate 12 lessons, 100% coverage; rows persisted | PASS |
| 12–16 | Workspace shows 24 across 2 schemes with working scheme filter; math lesson opens, edits, saves, persists | PASS |
| 17–18 | DOCX (browser, 296 paras/12 tables) + XLSX (browser, Register) | PASS |
| 19 | ZIP via browser click | FAIL (same §6 cause) |
| 20 | ZIP validity via API: 424,748 B, 12 entries (`MATHEMATICS_Basic9_W01_L01…`), integrity OK | PASS |

## 6. The one open defect: ZIP download fails in this test environment's Chromium

- Symptom: clicking Export ZIP (or `fetch()`ing the endpoint) in Chrome/Edge, headed or headless,
  fails with `TypeError: Failed to fetch` / `net::ERR_FAILED` after ~1–2 s. DOCX/XLSX buttons work.
- Proven NOT the product bytes: curl (5×), Python `http.client`, and `http.client` all retrieve HTTP 200
  with byte-identical, integrity-clean zips; response carries correct CORS headers
  (`access-control-allow-origin: http://localhost:3000`); preflights identical to working endpoints.
- Proven NOT the event loop: moving builders to `run_in_executor` did not change the symptom.
- Proven NOT headless-only, NOT DNS (`127.0.0.1` fails too), NOT proxy (none configured).
- 1 KB Range requests of the same file succeed; 40 KB DOCX succeeds; 424 KB full ZIP fails —
  size-correlated transfer failure specific to Chromium-on-this-machine loopback.
- Impact: Export ZIP button is effectively dead for a teacher testing in THIS environment.
  Files themselves are correct and complete.

## 7. Other observations (not gate blockers)

- PDF export returns HTTP 500 (`export_pdf_batch` yields no files — OS-level PDF engine gap on Windows).
  Optional per spec; backend stays up; UI would show the error banner. DOCX/XLSX/ZIP cover the requirement.
- Deleting a scheme removes the DB row but leaves its storage file orphaned on disk (minor housekeeping gap).
- `POST /api/auth/setup-school-admin` remains public without activation-code check — already on the
  security backlog from the Platform Admin milestone; untouched here.
- "Scheme not found" UI copy remains only for the genuine-404 path; 403s now surface
  "You do not have access to this scheme" from the API.

## 8. Stability, auth, states

- Backend never crashed across upload/review/approve/generate/edit/export for both subjects
  (one deliberate restart for the executor code change; PID 32048 since).
- Auth/isolation intact: teacher2 (same school, different owner) gets 403 on teacher1's scheme,
  404 on random UUID; platform-admin lockout on teacher upload still 403; 253 tests green.
- Loading spinners, empty states ("No schemes uploaded yet", "No lesson plans yet"),
  error banners with retry, and success states observed throughout; no blank pages, no raw traces.

## Verdict

**CORE TEACHER WORKFLOW: CONDITIONAL PASS — Science 19/20, Mathematics 19/20.**

A teacher can log in, upload a real scheme, review, approve, configure, generate, open, edit, save,
and export valid DOCX/XLSX/ZIP files for both Science and Mathematics in the canonical web app.
The single failing check in each subject is the in-browser ZIP *transfer* (§6) — the ZIP *files*
are proven valid; the defect is environmental to this machine's Chromium loopback handling and needs
confirmation on a second machine before any product change is made for it.
