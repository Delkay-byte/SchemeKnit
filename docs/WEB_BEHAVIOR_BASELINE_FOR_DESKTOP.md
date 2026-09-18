# Web Behavior Baseline for Desktop Parity

Status: authoritative. The web application is the canonical reference implementation.
Desktop 1.0.4 is **not** changed by the milestone that produced this document; the next
desktop milestone must make the EXE behave as described here.

Every rule below is enforced server-side and covered by tests under `backend/tests/`.
Nothing here depends on the desktop client's local state.

---

## 1. License lifecycle

```
PLATFORM ADMIN
  Create School (status=active, no license yet)
  Create License        -> status=pending, activated_at=NULL, one activation code issued
  (optional) Activate   -> status=active, activated_at stays NULL (admin action, not a school claim)
  Suspend / Renew       -> status=suspended / expiry pushed out
  Generate Code         -> additional activation code (30-day expiry, one-time use)
        |
        v
SCHOOL ACTIVATION (public, logged out)
  Validate code  -> display-only: school, plan, status, seats, start/expiry
  Create School Admin -> in ONE transaction:
        code.status      = "used"
        code.used_by_school_id = <school from the code's license>
        code.used_at     = now
        license.status   = "active"   (only if it was pending)
        license.activated_at      = now      <-- first claim wins
        license.activation_code_id = <code id>
        user.role = "school_admin", user.school_id = <school>
        school_membership row created
        school_admin_claimed written to the school audit log
        |
        v
SCHOOL ADMIN  -> creates teachers (role + school forced server-side, never trusted from client)
        |
        v
TEACHER -> upload -> review -> approve -> configure -> generate -> edit -> export
```

Rules:

* The school is **always** derived server-side from the activation code's license. A
  `school_id` supplied by the client is accepted for backward compatibility but ignored.
* Redemption is single-winner and replay-proof: a `used` code returns **403**, a revoked
  code **403**, an expired code **403**, an unknown code **404**. The code is locked for
  update inside the same transaction that creates the admin account.
* `activated_at` records **when the school claimed the license**, and is written by both
  the web activation path and the desktop `POST /api/platform-admin/activate` path.
  An admin-side `Activate` only flips `status`; it deliberately leaves `activated_at`
  NULL so "created for a school" stays distinguishable from "claimed by a school".
* A replacement activation code must never rewrite `activated_at`/`activation_code_id`.
  If a license has no tracking columns populated (rows created before this existed), the
  view falls back to the earliest `used` code on that license.

### What Platform Admin sees (`GET /api/platform-admin/licenses`)

Derived on every request from stored rows — never cached, never client-computed:

| Field | Meaning |
|---|---|
| `status` | raw lifecycle column (`pending`/`active`/`suspended`/`cancelled`) |
| `effective_status` | `status` with elapsed expiry folded in (`active` + past expiry -> `expired`) |
| `is_active` | `effective_status == "active"` |
| `activated_at`, `activation_code`, `activation_code_status`, `claimed_by_school` | activation evidence |
| `seats_used` | count of **all** active accounts provisioned into the school (every role) |
| `seats_available` | `seat_limit - seats_used`, floored at 0 |
| `seat_limit`, `plan_name`, `expiry_date`, `start_date`, `school_name` | commercial terms |

`seats_used` counts every role on purpose. Counting only `role == "teacher"` reported 0
usage for a school whose school-admin account was created *by* the activation, which made
an activated license look unused in the UI.

`GET /api/platform-admin/schools/{id}` returns the same license view, preferring the
license the school actually claimed, then any active license, then the newest license —
so a pending license no longer looks absent.

---

## 2. AI entitlement (commercial) vs provider availability

Availability and entitlement are different questions and are decided by different code.
**An installed AI provider never grants access by itself.**

| Situation | AI allowed? | Reason code |
|---|---|---|
| Active, in-date school license | yes | `school_license` |
| Unexpired paid `EntitlementDB` row with `ai_enabled`/`advanced_ai_enabled` | yes | `paid_entitlement` |
| License suspended / cancelled | no (403) | `no_active_license` |
| Active license row whose `expiry_date` has passed | no (403) | `license_expired` |
| School membership but no license row | no (403) | `no_active_license` |
| No school membership (free tier), no paid entitlement | no (403) | `no_entitlement` |
| Expired paid entitlement row | no (403) | `no_entitlement` |

* Denial is **403** with `AI assistance requires an active school license or a paid AI
  entitlement.`
* The gate runs **before any provider object is constructed**, at every AI entry point:
  section regeneration (`POST /api/ai/regenerate-section`), lesson enrichment
  (`POST /api/ai/enrich-lesson`), and generation-time enrichment
  (`POST /api/generation/{scheme_id}/generate` when `ai_mode != OFF`). A reachable local
  Ollama daemon cannot bypass it.
* **Product decision (owner-approved):** the free tier keeps the full deterministic
  lesson workflow — upload, review, approve, configure, generate, edit, export — but not
  AI. AI is licence-gated, consistent with generation/export gating.
* **AI OFF is always available** and always produces a complete deterministic lesson
  plan. The AI gate is not consulted at all when `ai_mode == OFF`.
* Invalid AI JSON never reaches the renderer: AI output is validated against the approved
  schema, unknown keys are dropped, and on failure the existing deterministic content is
  preserved and a controlled error is returned.
* Provider-unreachable is separate and reports **503**.

---

## 3. Scheme deletion

| Case | Behavior |
|---|---|
| Own scheme, no generation jobs / lesson plans | **200**, row deleted, and the uploaded source file is removed |
| Own scheme with generated lessons/jobs | **409** `Cannot delete a scheme with generated lesson plans. Its lessons and history are preserved.` Nothing is deleted, **including the stored source file** |
| Scheme owned by another teacher | **403** |
| Scheme id does not exist | **404** |
| Storage file missing / unreadable | deletion still succeeds (cleanup is best-effort) |
| Storage file shared by two schemes | file is kept until the last referencing scheme is deleted |

Historical generated content is never cascade-deleted automatically. Archiving is not part
of the product model yet and must not be invented by the desktop client.

---

## 4. Approved lesson-plan structure (canonical organizational template)

Provenance: the headteacher-supplied approved weekly-lesson-notes format. It carries no
GES/NaCCA designation in the source, so the app must not label it officially "GES".

* Template id: `tpl-approved-org-headteacher`
* Name: `Approved Organizational Lesson Plan (Headteacher Source)`
* Selectable during generation/export (`template_id`) and it drives the real DOCX
  renderer — it is not a preview.

Topology (grid columns, not logical columns):

| Table | Rows x grid cols | Layout |
|---|---|---|
| 0 — metadata | 7 x 8 | r0 Week Ending(2)/Day(3)/Subject(3) · r1 Duration(5)/Strand(3) · r2 Class(2)/Class Size(3)/Sub Strand(3) · r3 Content Standard(3)/Indicator(4)/Lesson(1) · r4 Performance Indicator(4)/Core Competencies(4) · r5 Reference(8) · r6 New words(8) |
| 1 — delivery | 3 x 8 | header Phase/Duration(1)/Learners Activities(5)/Resources(2) · PHASE 1: STARTER · PHASE 2: NEW LEARNING |
| 2 — continuation | 2 x 3 | overflow main-activity row · PHASE 3: REFLECTION |

* Title block is the paragraph set `{term}` / `WEEKLY LESSON NOTES` / `WEEK {week}`.
* Content stays in table cells. Activity text goes in the activity column, resources in
  the resources column, assessment in the assessment block within the lesson cell,
  reflection/plenary in the PHASE 3 row. The document must never be flattened into
  `Label | Value` or `Phase | Activity | Resources` rows, and table content must not be
  converted to plain paragraphs.
* Exactly the phases the approved source defines. No invented phases, time allocations,
  competencies, curriculum references, or fields.
* Field mapping: subject, class_level, class_size, duration_minutes, strand, sub_strand,
  content_standard, indicators, lesson_number, learning_objectives, core_competencies,
  references, keywords. `Week Ending` and `Day` have no model backing and render blank —
  they are never fabricated.

### Data contract

Curriculum facts are **deterministic-only** and are never accepted from AI: school,
teacher, subject, class, class size, date, duration, week/lesson numbering, strand,
sub-strand, content standard, indicators, curriculum references.

AI may fill activity-family fields only, inside the approved schema:

```
lesson_topic, performance_indicator, core_competencies, references,
new_words, phases[{name, teacher_activities, learner_activities, resources}],
assessment, reflection, homework
```

Unknown keys are dropped (strict schema); item shapes are coerced; lengths are bounded.
The server-side system prompt enforces the approved structure only and must not invent
external curriculum rules.

### Structural validator

`validate_custom_docx(source_structure, generated_path, expected_values, forbidden_values)`
produces an explicit PASS/FAIL report comparing the approved source structure with the
generated document: table count, table order, rows, columns, merge/span map, key labels,
section order, populated fields, and absence of sample/template content. It detects
"textually right, structurally wrong". Plain text extraction is not the structural test.

---

## 5. Export behavior

| Endpoint | Format | Media type |
|---|---|---|
| `POST /api/generation/{job}/export/docx` | `.docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| `POST /api/generation/{job}/export/pdf` | `.pdf` | `application/pdf` |
| `POST /api/generation/{job}/export/xlsx` | `.xlsx` | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| `POST /api/generation/{job}/export/zip` | `.zip` | `application/zip` |

* Every export requires authentication (HTTPBearer) and job ownership (404 otherwise).
* The filename is chosen server-side and sent in the `X-TeachFlow-Filename` response
  header (percent-encoded), exposed to browsers via CORS `expose_headers`. A
  `Content-Disposition: inline; filename*=UTF-8''…` header is also sent for direct
  and scripted consumers. Clients must save the server's name.
* **Exports must never use `Content-Disposition: attachment`.** Chrome and Edge
  classify an attachment-dispositioned `application/zip` response as a download, and a
  download cannot be handed to `fetch()`: the request dies the moment the response
  arrives (`TypeError: Failed to fetch` / `net::ERR_FAILED`) even though the server
  answered 200 with a valid archive. This is what made ZIP export silently produce no
  file in both browsers, and it is the same class of bug as the reported Word/PDF
  failures. Verified in real Chrome and Edge against the running app.
* Export events are recorded per format for workflow state.

### PDF has two distinct failure layers — never conflate them

1. **Toolchain missing** (no docx2pdf and no LibreOffice): controlled **503**,
   `PDF export requires a document converter on the server (LibreOffice for
   cross-platform production use).`
2. **Converter present, conversion failed**: controlled **500**,
   `PDF conversion failed on the server. Word (.docx) export is unaffected.`

Hard rules:

* The PDF path **never returns or serves an intermediate DOCX**. It used to fall back to
  the intermediate `.docx` when conversion failed, which served a DOCX body labelled
  `application/pdf` with a `.docx` filename — a silently corrupt download, not a visible
  error. That is the root cause of "PDF download fails in Chrome and Edge".
* A conversion result is only accepted if it actually starts with `%PDF-`. Anything else
  is a conversion failure. The endpoint re-checks this before responding.
* Conversion failure never yields a raw traceback, internal path, or converter stack.
  Diagnostic detail goes to the server log only.
* DOCX/XLSX/ZIP do not depend on the PDF converter and are unaffected by either layer.
* Word export keeps working exactly as before: the download mechanism was fixed without
  changing the generated document.

---

## 6. Browser behavior

* Exports are fetched with `fetch()` including the `Authorization` header, read as a
  blob, and saved through one shared helper used by both the browser and Electron.
* The object URL is revoked **on a later tick (`setTimeout`)**, never synchronously after
  `a.click()`. Chrome aborts a download whose object URL is revoked in the same task;
  Edge tolerates it. This is why Word downloads appeared to fail in Chrome but pass in
  Edge with identical server responses.
* The response must stay readable by `fetch()`: no `Content-Disposition: attachment`
  (see above). Both conditions are required; fixing only one still leaves a browser
  where no file is saved.
* Export failures must be **visible in the UI**. The error is rendered as an alert in the
  export panel whenever the page has loaded; previously it only rendered when the scheme
  itself failed to load, so a failed export looked like a dead button.
* Download filenames are taken from the server's `Content-Disposition` when present and
  sanitised (browsers/Windows rewrite `\ / : * ? " < > |` and control characters) so the
  saved name matches across Chrome, Edge, and Electron.
* In Electron the same helper opens the native save dialog.
* Export failures surface as the server's message (`403`/`500`/`503` detail), never as an
  unhandled exception or a silent no-op.

---

## 7. Role boundaries

| Capability | Platform Admin | School Admin | Teacher |
|---|---|---|---|
| Schools, licenses, plans, payments, activation codes, audit | full | none | none |
| License summary (read-only) | full | own school | own school (status only) |
| Lesson-planning workflow (upload -> export) | **403 — refused by design** | yes, licensed | yes, licensed |
| Create teachers | (uses platform register) | yes, seat-limited | no |
| Add teachers to school | — | own school only | no |
| Scheme/lesson data | read-only metadata for support | own school | own records only |

* Platform Admin is a commercial role and must not use the teacher workflow.
* Teachers with no school membership get the free-tier workflow (no AI).
* Cross-school isolation is enforced at the backend, not by frontend filtering.
* Suspended/expired/missing license blocks the teacher workflow (403) and teacher
  creation (403); all existing data, lessons and templates are preserved, and
  reactivation restores access.

---

## 8. Parity checklist for the desktop milestone

1. Enforce AI entitlement from license/entitlement state, not from whether a local
   provider is reachable.
2. Write `activated_at` / `activation_code_id` when a school activates, and treat a
   replacement code as not rewriting the first claim.
3. Show the same license view fields, including `effective_status` and all-role seat
   usage.
4. Keep the empty-scheme delete and the protected-scheme 409, including source-file
   cleanup semantics.
5. Render the approved template topology (3 tables, 7x8 / 3x8 / 2x3) and refuse to
   flatten it.
6. Never serve an intermediate DOCX as a PDF; keep the two PDF failure layers distinct.
7. Revoke blob object URLs after the click task, not during it.
8. Never send `Content-Disposition: attachment` on fetch-consumed export responses;
   carry the filename in `X-TeachFlow-Filename` and show export errors in the UI.
9. Pass the selected template id to every export format (DOCX, PDF, ZIP). ZIP used to
   omit it and silently fall back to the built-in layout while DOCX honoured it, so the
   same selection produced two different documents.
