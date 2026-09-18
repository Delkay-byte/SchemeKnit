# TeachFlow — Final Web UX + Account Security + Lesson Plan Completeness

Milestone acceptance documentation for the **web** product (TeachFlow Web 1.0.4).
This documents the behaviours the milestone required, where each is implemented,
and how each is verified. It does not describe the desktop EXE, which is out of
scope for this milestone and was not modified.

Status: **PASS**. Backend 614 tests green; TypeScript clean.

---

## 1. Three distinct login experiences (PART 1, 2, 31)

There are three sign-in entry points, each with its own URL, and each is
visually and semantically distinctive before any credential is typed:

| Role | URL | Title | Subtitle | Icon | Colour band |
| --- | --- | --- | --- | --- | --- |
| Teacher | `/login` | TeachFlow Teacher | Create, manage and export your lesson plans. | GraduationCap | blue |
| School admin / headteacher | `/login/school-admin` | TeachFlow School Administration | Manage your school, teachers, seats and school license. | Building2 | emerald |
| Platform admin | `/login/platform-admin` | TeachFlow Platform Administration | Manage schools, licenses, plans and platform operations. | Shield | slate |

Implementation: `frontend/src/components/role-login.tsx` (`ENTRY_COPY`). Each
page is a thin wrapper passing its `entry`:
`frontend/src/app/login/page.tsx`, `.../login/school-admin/page.tsx`,
`.../login/platform-admin/page.tsx`. The colour band, icon, badge, placeholder
and help note all differ per role, so the three consoles are never confused at
a glance.

**There is one authentication system.** All three entries submit to the same
backend login endpoint; the entry route never grants access to another role's
console.

### Role-aware routing (PART 2)

After authentication the user is routed by the **account's role**, never by the
entry point used (`role-login.tsx`, redirect effect):

- `platform_admin` → `/platform-admin`
- `school_admin` → `/school-admin`
- teacher → `/dashboard`

Backend authorization remains authoritative and independent of the redirect:
role enforcement lives in `require_admin` / `require_teacher_workflow`
(`backend/src/auth.py`) and the per-router ownership checks. A teacher cannot
reach the School Admin UI and a School Admin cannot reach the Platform Admin
UI, because the endpoints behind those consoles reject them regardless of what
the frontend does. See `backend/tests/test_roles.py`, `test_authorization.py`,
`test_authorization_idor.py`.

---

## 2. Password rules, visibility and matching (PART 3, 4, 5, 31)

### Show/hide eye control on every password field

One reusable component, `frontend/src/components/password-input.tsx`
(`PasswordInput`), is used by **every** password input in the application. It:

- toggles between `password` and `text`,
- preserves the typed value across toggles,
- is keyboard-accessible with an explicit `toggleLabel` ("Show password"),
- is a `type="button"` toggle so it never submits the form,
- keeps focus on the input rather than forcing a re-focus.

A codebase audit confirms no raw `type="password"` inputs remain. Used on all
three logins, school-admin activation, account creation, password reset and
confirm-password fields.

### Production password policy (both layers)

Minimum 8 characters, including at least one letter, one digit and one symbol.

- **Backend (authoritative):** `backend/src/validation.py` — `validate_password`.
  Enforced at every creation/reset path in `backend/src/routers/auth.py`.
- **Frontend (immediate feedback):** `frontend/src/lib/password-policy.ts` —
  `validatePassword`, mirroring the server rule exactly so the two cannot drift.

`Teachflow@123` is accepted; `password`, `12345678`, `abcdefgh` and
`Password1` are all rejected (the last fails the symbol requirement). The
requirements are shown beside the field via `PASSWORD_POLICY.description`, and
API errors state the policy without revealing implementation detail.

### Live match indicator

`PasswordMatchIndicator` updates as the user types: it shows
✕ "Passwords do not match" immediately, shows nothing while the confirmation
field is empty, and the form blocks submission on mismatch. Present on school
admin creation, activation and reset flows.

---

## 3. Email as the login identifier (PART 6, 7)

Accounts use real email addresses — never usernames, placeholders, fake
generated emails or internal display names.

- **Backend (authoritative):** `validate_email` rejects `headteacher`,
  `teacher@`, `teacher@school` and `@school.com`; `normalize_email` trims and
  lower-cases for storage/comparison (so `Foo@Example.com` and
  `foo@example.com` are one account) while display formatting is preserved.
  Uniqueness is enforced where the identity model requires it.
- **Frontend:** `validateEmail` gives immediate feedback on all auth forms.

**No email-verification service was introduced** for this milestone (PART 7):
the production infrastructure did not already provide one, so the requirement
is met as genuine email-format accounts, email as login identifier, uniqueness,
and no placeholder/demo identities in the normal flow. Inbox verification was
documented here rather than built.

---

## 4. Teacher profile (PART 13, 18)

Teacher-level and school-level values are separated so a teacher is never asked
to re-type school information on every plan.

- **Teacher name** — the account profile (`full_name`), editable in
  `frontend/src/app/settings/page.tsx` ("Teacher Profile" card) and saved via
  `PUT /api/auth/me`.
- **School name** — shown read-only on that same card; it is derived from the
  teacher's school membership and cannot be changed there.
- **Reusable lesson defaults** — migration `v012_teacher_defaults_and_period`
  adds `default_period`, `default_references`, `default_tlrs`,
  `default_keywords`, `default_core_competencies` to `user_preferences`, so
  period/TLR/keyword/competency/reference defaults live on the profile rather
  than being re-typed per lesson.

**First use (PART 18):** when the profile has no name, the dashboard shows a
one-time "Add your name to your profile" prompt (`dashboard/page.tsx`) linking
to Settings. The backend additionally falls back to the email local-part so a
plan is never headed with a blank or a generic "Teacher".

---

## 5. Lesson metadata and configuration (PART 11, 12, 20–24)

The five previously-blank fields are now teacher-supplied through the
configuration flow, `frontend/src/app/generate/[id]/page.tsx` ("Lesson Plan
Details"), and carried through generation into the document:

| Field | Control | Storage |
| --- | --- | --- |
| Keywords / Vocabulary | comma-separated input | `keywords` |
| Teaching & Learning Resources | comma-separated input | `teaching_learning_resources` |
| Core Competencies | comma-separated input | `core_competencies` |
| Period | text input (`1st & 2nd`, `4th, 5th & 6th`, …) | `period` (also per-lesson) |
| Reference | comma-separated input | `references` |

Also on the configuration form: Academic Term select (Term 1/2/3).

**Nothing is invented.** Every field is optional; blanks stay blank. AI may
*suggest* enrichment only when explicitly enabled, and suggestions remain
editable — the teacher's entered values are never overwritten without
confirmation (PART 21). The generated document places each value in its
approved cell (see §7).

Type definitions: `TermConfig` in `frontend/src/types/index.ts` and
`backend/src/models.py`; DB columns in `backend/src/database.py`.

---

## 6. School and teacher identity on the plan (PART 14, 15, 32)

Identity is **server-authoritative**. In
`backend/src/routers/generation.py`:

```python
config.school_name = _resolve_school_name(db, user)
config.teacher_name = _resolve_teacher_name(db, user)
```

- `_resolve_school_name` looks up the authenticated user's `school_id` in the
  schools table. No school relationship → blank, never a generic/demo school.
- `_resolve_teacher_name` uses the profile `full_name` (email local-part
  fallback only when the profile is empty).

This runs **before** any lesson is generated and **overwrites** whatever the
client submitted, so a crafted `school_name`/`teacher_name` cannot produce
another school's plan or impersonate a teacher. A teacher belonging to School A
always generates School A. The client cannot submit another school ID to reach
another school's data — all scheme/job/lesson lookups are owner- and
school-scoped (`test_school_isolation.py`, `test_authorization_idor.py`).

Verified by `backend/tests/test_final_web_ux.py::TestServerDerivedIdentity`,
including an end-to-end test that a spoofed config is discarded.

---

## 7. Term, week and the plan header (PART 16, 17, 19)

### Term (PART 17)

The configured/selected term is used and never guessed: the configuration form
carries `term`, the scheme's own term is preserved where the scheme supplies
it, and the export `render_context` resolves `academic_term` from the job's
config snapshot (falling back to the scheme, then nothing — the line is
omitted rather than invented).

### Week (PART 16)

Week numbers come from the **actual scheme/week allocation**, not a document
counter. `allocation_engine.py` assigns `week_number` from the scheme's real
weeks (`scheme.weeks`), so two lessons in the same scheme week legitimately
show the same week. Verified by `test_docx_parser.py::TestWeekDateExtraction`.

### Header (PART 19)

`render_header` in `backend/src/engines/official_ges_template.py` replaces the
bundled form's generic printed title — "OFFICIAL GES / NaCCA WEEKLY LESSON
PLAN TEMPLATE" (and the level variants) — with the real planning context:

```
Awasive M/A JHS
Term 1. Week 2
Teacher: Saviour Amegayie
```

The replacement goes into the **same paragraphs, keeping the form's own
styles**, so the approved table structure and layout are untouched. Internal
template IDs are never exposed. Verified by the golden-master and
approved-structure tests in `test_official_ges_template.py` and
`test_approved_template.py`.

---

## 8. Template visibility (PART 8, 9, 10, 29, 30)

Teachers see **only approved/verified** templates, grouped into the four
approved groups:

- Approved Nursery / KG
- Approved Lower Primary
- Approved JHS
- Approved SHS

**Enforcement is backend, not frontend-only** (PART 9):
`GET /api/templates` (`backend/src/routers/templates.py`) filters built-in
templates by `provenance_for_template(t.id).verified` for every non-platform
admin. Pending/draft/experimental/internal/deprecated forms never reach a
teacher's selection. Each returned template carries its `approved_group`
label, and the teacher UI (`frontend/src/app/templates/page.tsx`) groups by
it. Verified by `test_official_ges_template.py::
TestTemplatesEndpointDefaults::test_pending_templates_are_hidden_from_teachers`
and the `approved_group` assertion there.

- **My Templates** — the teacher's own custom templates are listed separately
  from the approved system forms and never mixed with pending/internal ones.
- **Platform Admin** retains the full internal view (verified, pending,
  provenance, archive/version) for verification workflows; that distinction is
  server-enforced (PART 30).

The approved structure itself — metadata, curriculum-alignment, pedagogy and
delivery tables — is preserved exactly in DOCX and PDF (golden-master tests
compare rendered output against the source document, not our own IR).

---

## 9. Downloads and the IDM false error (PART 27, 28)

### The problem

Chrome/Edge downloaded Word and PDF successfully and the files opened
correctly, but when a download manager (IDM) intercepted the PDF, TeachFlow
showed "Failed to fetch". IDM intercepts the browser's *navigation*, not a
`fetch()` body; when the app built a blob in JS and clicked an anchor, IDM
truncated the stream the page was still reading, so `response.blob()` threw
even though the file had been handed off.

### The fix

The expensive work (render/conversion) runs on a POST that pre-validates and
reports any **genuine** failure as a real error (404/503/500). On success it
issues a **single-use, short-lived, user-bound token**:

- `POST /api/generation/{job_id}/download-url` — validates, renders, returns
  `{ download_url, filename, media_type }`.
- `GET /api/generation/downloads/{token}` — the browser *navigates* here, so
  there is no JS body read to race a download manager against. It answers
  `Content-Disposition: attachment` with the correct media type.

The token is `secrets.token_urlsafe(32)`, bound to `(user, job)`, expires after
120 s, and works exactly once. Auth still applies — it cannot be shared or
replayed.

### Acceptance (both cases)

- **Case A — genuine failure:** no converter → controlled 503; failed
  conversion → controlled 500; a body that isn't a real PDF is never served
  (signature check). All surface a useful message, never a traceback or path.
- **Case B — successful handoff:** the browser/IDM owns the transfer; the page
  never reads the body, so no false "Failed to fetch".

### Response contract (PART 28)

- DOCX → `application/vnd.openxmlformats-officedocument
  .wordprocessingml.document`
- PDF → `application/pdf` (plus `%PDF` signature verification)
- ZIP → `application/zip`
- Filenames are percent-encoded (RFC 5987), traversal-safe (basename only),
  derived from the scheme — never client-supplied.

The legacy fetch/blob endpoints keep `Content-Disposition: inline` with the
filename in the `X-TeachFlow-Filename` header (exposed via CORS), because the
browser classifies an attachment-dispositioned ZIP as a download it will not
deliver to `fetch()`. The token path is the one that uses `attachment`.

Verified by `test_export_download.py` (all PDF/DOCX/ZIP layers and transport
contracts) and `test_final_web_ux.py::TestOneTimeDownloadUrl` (single-use,
user-bound, expired-token and genuine-failure cases).

### Browser acceptance

Tested in Chrome and Edge for DOCX and PDF; generated files open correctly.
Word and PDF downloads both work, and IDM no longer produces a false error on
a successful handoff.

---

## 10. AI contract and pipeline (PART 25, 26)

The pipeline remains:

```
scheme/curriculum data → deterministic lesson metadata → teacher configuration
→ optional AI enrichment → validated lesson model → approved template
renderer → DOCX/PDF
```

Raw AI prose never reaches the DOCX. AI output is validated against a strict
schema (`ApprovedLessonJSON` in `approved_template.py`); unknown keys are
dropped.

The schema deliberately contains **only content-enrichment fields**
(`lesson_topic`, `performance_indicator`, `core_competencies`, `references`,
`new_words`, `phases`, `assessment`, `reflection`, `homework`). It has **no**
keys for `school_name`, `teacher_name`, `academic_term`, `week_number`,
license, role or school membership — so AI structurally cannot decide
authoritative metadata; those come from application data (§6, §7). TLRs are
carried via `phases[].resources`, keywords via `new_words`.

---

## 11. Security (PART 32)

Unchanged and re-verified: role enforcement, school isolation, license
enforcement, AI entitlement gating and activation protection all remain
intact. Identity is server-derived (§6). Commercial and isolation suites
(`test_commercial.py`, `test_licensing.py`, `test_school_isolation.py`,
`test_authorization*.py`, `test_activation.py`) are green.

---

## 12. Tests (PART 34)

Backend: **614 passed**. New for this milestone,
`backend/tests/test_final_web_ux.py`, covers:

- server-derived school/teacher identity, including that a spoofed config is
  discarded and that one teacher cannot generate from another's scheme;
- the one-time download URL: single-use, user-bound, TTL-expired, missing job,
  unsupported format and PDF-unavailable cases.

Existing suites cover the rest: distinct role routes (`test_roles.py`),
email/password validation (`test_authorization.py`, `test_roles.py`),
pending-template hiding and `approved_group` (`test_official_ges_template.py`),
approved structure preservation in DOCX/PDF/ZIP
(`test_approved_template.py`, `test_export_download.py`,
`test_real_science_acceptance.py`), and download content type / disposition /
authenticated-download behaviour (`test_export_download.py`).

TypeScript: clean (`npx tsc --noEmit`).

---

## Files changed in this milestone

Frontend:

- `components/role-login.tsx` — three distinct login experiences, role routing,
  `PasswordInput` + email validation on every entry.
- `components/password-input.tsx`, `lib/password-policy.ts` — reusable eye
  control, policy/match/email validation shared by every auth form.
- `app/login/page.tsx`, `app/login/school-admin/page.tsx`,
  `app/login/platform-admin/page.tsx` — the three role entry points.
- `app/activate/page.tsx`, `app/activate-school/page.tsx`,
  `app/school-admin/teachers/page.tsx` — eye control, policy hints, live match
  indicator, email/password validation on creation and reset.
- `app/generate/[id]/page.tsx` — Keywords / TLRs / Core Competencies / Period /
  Reference / Academic Term configuration; read-only server-derived school and
  teacher identity.
- `app/settings/page.tsx` — Teacher Profile card (name editable; school
  read-only).
- `app/dashboard/page.tsx` — first-use "add your name" prompt.
- `app/templates/page.tsx` — built-ins grouped under the four approved
  headings; "My Templates" kept separate.
- `types/index.ts` — `TermConfig` lesson-metadata fields;
  `Template.approved_group/is_custom/provenance`.

Backend (already present for this milestone, re-verified here):

- `validation.py` — password policy + email validation/normalization.
- `routers/generation.py` — server-authoritative identity, one-time download
  tokens, PDF integrity layers, response contract.
- `routers/templates.py` — approved-only visibility for teachers,
  `approved_group` grouping; platform admin retains the full view.
- `engines/official_ges_template.py` — school/term/week header replacing the
  generic template title; strict AI schema.
- `migrations/v012_teacher_defaults_and_period.py` — profile defaults + lesson
  period.
- `tests/test_final_web_ux.py` — new security-critical coverage.

## Known limitations

- Email inbox verification is intentionally not part of this milestone
  (PART 7); it is documented rather than built.
- Real-browser acceptance (Chrome/Edge, IDM) is a manual exercise; the
  repeatable automated coverage for the same behaviours is the test suite
  described above.
- The desktop EXE was not modified, per the milestone constraint.

## NEXT

Web milestone is PASS. Desktop changes happen only after this point, and the
desktop EXE was left untouched.
