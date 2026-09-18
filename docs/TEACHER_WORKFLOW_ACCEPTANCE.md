# Teacher Workflow Acceptance — Browser-Verified

**Date:** 2026-09-15
**Scope:** The exact teacher journey: LOGIN → DASHBOARD → UPLOAD → REVIEW → APPROVE → CONFIGURE → GENERATE → LESSON PLANS → EDIT → EXPORT
**Method:** Real browser automation (Playwright/Chromium) clicking the actual running UI. Screenshots in `%TEMP%\tf_shots\`. No curl-only or API-only evidence is used for any step below. The acceptance script lives at `desktop/tests/teacher_workflow.acceptance.js` and is re-runnable.

---

## 1. Environment under test (§19)

| Item | Value | Verified how |
|---|---|---|
| Frontend URL | http://localhost:3000 (`next dev`, web build target) | HTTP 200 on /login/, /dashboard/, /upload/, /lessons/ |
| Backend URL | http://127.0.0.1:8000 (dev API) | `/api/health` → `{"status":"healthy","version":"1.0.2"}` |
| Frontend version | 1.0.2 | settings page + layout metadata |
| Backend version | 1.0.2 | `/api/health` |
| Build target safety | Web build defaults API to :8000; desktop build (`npm run build:desktop`) to :18234 | `next.config.js` now keys off `NEXT_PUBLIC_BUILD_TARGET` |

### Critical environment defect found and fixed (§19)
The server previously running on :3000 was a **stale `next start` serving the desktop static export**, which had `http://localhost:18234` (the desktop backend) baked in. The web UI was silently authenticating against the **desktop's separate database** — that is why logins that worked via curl failed in the browser. `next.config.js` also unconditionally set `output: 'export'`, which broke direct loads of dynamic routes.

**Fixes applied**
- `output: 'export'` is now applied **only** for `NEXT_PUBLIC_BUILD_TARGET=desktop`.
- API URL defaults: `:8000` for web, `:18234` for desktop (no cross-target drift possible).
- `desktop/package.json` build:frontend now runs `npm run build:desktop` explicitly (with `cross-env` for Windows).
- Stale desktop-build server killed; web dev server runs with the correct target.

---

## 2. Root causes (required by the brief)

| Defect | Exact root cause | Fix |
|---|---|---|
| **"Review Curriculum" loops back / blank (§3, §4)** | Two stacked causes: (a) `output: 'export'` made `next dev` reject direct loads of `/review/[id]` — a 500 page `Page "/review/[id]/page" is missing param ... in generateStaticParams()`; (b) the stale desktop-target server on :3000 aimed the app at the wrong backend. | Conditional export per build target; correct API base per target; review page already fetches by persisted scheme ID and now survives refresh (verified in run step 7). |
| **"Pending Review" card inert (§5)** | Earlier refactor had made the card a plain statistic; current code links to `/review/<pendingScheme.id>`. Verified by real click → navigates to the review page of the pending scheme. With multiple pending schemes it opens the first pending scheme's review page. | Confirmed working by click test; card is disabled (non-clickable, greyed) at 0. |
| **"Ready to Generate" card (§6)** | Links to `/generate/<approvedScheme.id>`. Verified by real click → opens the configuration/generation page. | Confirmed working by click test. |
| **"Generate failure" (§9–§11)** | After a reload the generate page never restored the existing job, so exports disappeared; the success banner read `coverage?.total_generated_lessons` but the coverage endpoint never returned that field (would show "0 lesson plans generated"); regeneration left orphaned duplicate lesson rows because the cleanup deleted by a nonexistent TermConfig-id. | New `GET /api/generation/scheme/{id}/status` restores job state on mount; coverage/status responses now include `total_generated_lessons`; regeneration now deletes previous lessons for the scheme before creating a new job. |
| **Original filename showing as UUID (§7)** | Upload stored the storage filename (`<user>_<timestamp>.docx`) as the scheme's display name; nothing preserved `file.filename`. | Parser accepts `original_filename`, upload passes it through, every UI surface (upload success, dashboard, review, lessons, filter) renders it, and DOCX/XLSX/ZIP downloads use human-readable names (`Lesson_Plans_BASIC_9_SCIENCE_SCHEME_OF_LEARNING.docx`). |
| **Exports 403 in the browser (§13)** | The four export methods used raw `fetch()` without the `Authorization` header; FastAPI's HTTPBearer returns **403 (not 401)** when the header is missing. | Shared `exportBlob()` helper now sends the bearer token; verified DOCX (39,608 B), XLSX (7,198 B), ZIP (424,398 B) download as real files. |
| **ZIP endpoint 500 (§13)** | Pre-existing bug: `GenerationPipeline.export_zip` called `zip_engine.export_batch(lesson_plans, template_type, output_path)` but the engine signature is `(lesson_plans, output_path, template_type)` → `'TemplateType' object has no attribute 'parent'`. | Argument order corrected; ZIP export verified end-to-end from the UI. |
| **Dead Edit button on lessons (§12)** | Row buttons linked to `/generate/<scheme>?edit=<id>`, a query the generate page ignores. | New lesson detail page `/lessons/[id]` (open, edit, save, persist); lessons row has a single unambiguous "Open" action. |

---

## 3. Acceptance matrix — Basic 9 SCIENCE (§20)

All steps performed in Chromium against the running UI.

| # | Step | Expected | Actual | Status |
|---|---|---|---|---|
| 1 | Login (teacher.acc@awasive.edu.gh) | Dashboard loads | `http://localhost:3000/dashboard/`, "Welcome back" | PASS |
| 2 | Dashboard renders | Workflow visible | Workflow strip + cards render | PASS |
| 3 | Upload real DOCX | File accepted | BASIC 9 SCIENCE SCHEME OF LEARNING.docx (33.6 KB) staged | PASS |
| 4 | Upload success | Original filename | Shows "BASIC 9 SCIENCE SCHEME OF LEARNING.docx" | PASS |
| 5 | Weeks detected | 15 | "Weeks detected: 15" | PASS |
| 6 | Review click | Real scheme ID in URL | `/review/0e42a682-43c7-48a7-a9ee-5503b86f3b0c/` (36-char UUID) | PASS |
| 7 | Review survives refresh | Same scheme reloads | Filename + data render after F5 | PASS |
| 8 | Weeks list | 15 weeks navigable | "Weeks (15)" sidebar | PASS |
| 9 | Curriculum columns | Strand/indicators visible | Strand + Sub-strand + Content Standards + Indicators + Resources | PASS |
| 10 | Approve & Configure | Navigates to config | `/generate/0e42a682.../` | PASS |
| 11 | Configuration shows fields | Class/Subject/Term | All shown | PASS |
| 12 | Generate | Success message | "12 lesson plans generated" | PASS |
| 13 | Lesson plans visible | Table with rows | Weeks, lessons, topics, scheme name, statuses | PASS |
| 14 | Open lesson | Detail page opens | `/lessons/2f5fada3-.../` with Curriculum Context | PASS |
| 15 | Edit lesson | Fields editable, save works | "Saved" confirmation | PASS |
| 16 | Persistence | Edit survives navigation | Re-opened lesson shows edited content | PASS |
| 17.1 | Export DOCX | Real file downloads | 39,608 bytes | PASS |
| 17.2 | Export XLSX | Real file downloads | 7,198 bytes | PASS |
| 17.3 | Export ZIP | Real file downloads | 424,398 bytes | PASS |
| 18 | Console errors | None critical | Zero | PASS |

**Science: 20/20 PASS**

## 4. Acceptance matrix — Basic 9 MATH (repeat core flow)

| # | Step | Actual | Status |
|---|---|---|---|
| 1–5 | Login → upload MATH scheme | Original filename + "Weeks detected: 15" | PASS |
| 6–9 | Review page | `/review/6c60e230-2d6c-44f3-9891-4eaa1e7d3366/`, refresh-safe, curriculum columns | PASS |
| 10–12 | Approve → configure → generate | "12 lesson plans generated" | PASS |
| 13–16 | Lessons open/edit/persist | Save + re-open verified | PASS |
| 17.1–17.3 | Exports | DOCX 39,525 B, XLSX 7,179 B, ZIP 424,593 B | PASS |
| 18 | Console errors | Zero | PASS |

**Math: 20/20 PASS**

## 5. Dashboard card clicks (§5, §6) — verified with real clicks

| Card | State shown | Click result |
|---|---|---|
| Pending Review | 2 | Navigated to `/review/d8a02faf-.../` (pending scheme's review page) |
| Ready to Generate | 4 | Navigated to `/generate/6c60e230-.../` (approved scheme's config page) |

## 6. Backend stability (§22)

- Backend PID `16244` remained alive across both full browser runs (upload → review → approve → generate → edit → 6 exports).
- `unhandled_exception` count in backend log during the acceptance runs: **0**.
- Regression suite after all changes: **246/246 tests pass** (21.2s).

## 7. Account provenance (§17, §18)

- Teacher account `teacher.acc@awasive.edu.gh` was created through product endpoints only: activation-code activation → `setup-school-admin` → school-admin `POST /api/auth/users` (the same network calls the UI makes). No SQL edits, no direct DB manipulation.
- The journey was executed as **TEACHER**, not platform_admin.

## 8. Remaining limitations

1. **PDF export** was not exercised (Windows box lacks a DOCX→PDF converter; button present but converter-dependent). DOCX/XLSX/ZIP are fully verified.
2. Screenshots and downloaded artifacts are in `%TEMP%\tf_shots\` (science-01..09.png, math-01..09.png, export files, results JSON).
3. The stale-server defect (§1) means any long-running `next start` from an old desktop build must be killed before web testing; the config fix prevents the build from being produced wrong again.

## 9. How to re-run

```bash
# servers
cd backend  && python run.py                      # API :8000
cd frontend && NEXT_PUBLIC_API_URL=http://localhost:8000 npx next dev -p 3000

# acceptance (browser)
cd desktop/tests
NODE_PATH=../frontend/node_modules node teacher_workflow.acceptance.js \
  "C:/Users/SAVIOUR/Documents/DScience/Lesson Plan/BASIC 9 SCIENCE SCHEME OF LEARNING.docx" Science
```
