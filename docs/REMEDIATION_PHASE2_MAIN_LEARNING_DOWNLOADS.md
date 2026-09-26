# Phase 2 Remediation — Editable Main Learning, Teacher-Safe AI Failures, Downloads

Production remediation for the Lesson Review experience. This phase reuses the
existing architecture end to end: **no new endpoint, no second generation
engine, no WAPEF/UI redesign, no authentication weakening.**

Canonical data stays exactly as it was:

```jsonc
main_activities: [
  { "phase": "MAIN", "description": string, "duration_minutes": number | null, "resources": string[] }
]
```

## PART A–D — Phase 2 · Main Learning is editable

`frontend/src/app/(app)/lessons/[id]/page.tsx`

* Phase 2 renders a **structured editor**, not a read-only list and not one big
  textarea: one card per activity with an editable description, a numeric
  duration, remove, and (cheap, existing primitives) move up / move down.
* `+ Add activity` appends; ordering is preserved; the array is never flattened
  or serialized into raw JSON in the UI.
* Empty state is `No main learning activities yet.` — the UI can never render
  `[]`, `[,]`, `null`, `undefined` (activities are normalized on load: entries
  without a usable description are dropped, bad durations become `null`).
* Save sends `main_activities` (non-empty activities only). Every other stored
  field is sent back unchanged, so a Main Learning edit cannot alter
  indicator/codes, content standard, strand, subject, class, week, source
  TLRs, WAPEF metadata, keywords, competencies, references, starter,
  assessment, or plenary.

## PART E–G — AI suggestion reuses the existing endpoint

* `Suggest Main Learning` calls the existing
  `api.regenerateSection(lessonId, "main_activities", …)` →
  `POST /api/ai/regenerate-section`. The backend already maps
  `main_activities → main_learning` (`SECTION_TO_PROVIDER_KEYS`); no new route.
* On success the UI replaces the current activities with the backend-normalized
  structured array, does **not** auto-save, and shows
  `AI suggestion inserted by <resolved provider>. Review and Save to keep it.`
  The provider name is the actually-resolved one, never hard-coded.

### Backend normalization (no provider parsing in the frontend)

`backend/src/routers/ai_regeneration.py`

* `_normalize_main_activities(result)` maps the V2 provider payload
  (`main_learning` object keyed by phase, a list of phase objects, or a bare
  string — including `lesson_content` wrappers) into the canonical
  `[{ phase, description, duration_minutes, resources }]`.
* Blank descriptions are dropped; durations outside `1..180` become `null`.
* `SectionRegenerateResponse.new_activities` carries the structured array;
  `new_content` remains the flat text for backward compatibility.

## PART H–K / AD — AI failures are teacher-friendly and non-destructive

### Structured, teacher-safe error contract

`_ai_error(status, code, message, diagnostic)` returns an `HTTPException` whose
`detail` is `{ code, message, diagnostic }`:

* `message` — the calm, teacher-facing text (never provider internals).
* `diagnostic` — the raw provider state / `last_error` / exception text, kept
  **server-side** for logs, diagnostics and service status.

Stable codes: `AI_UNAVAILABLE`, `AI_RATE_LIMITED`, `AI_NO_SUGGESTION`.

| Underlying cause | Safe message |
|---|---|
| 503 no provider configured | "AI suggestion is currently unavailable. Your existing content was preserved." |
| rate limit / 429 | "AI is busy right now. Your existing content was preserved. Please try again in a moment, or edit it manually." |
| malformed JSON / empty output / quality-gate reject | "AI suggestion unavailable right now. Your existing content was preserved. You can edit it manually or try again later." |
| 500 unexpected | same calm message; raw exception stays in the diagnostic |

`frontend/src/lib/api.ts` turns an object `detail` into an `ApiError`
(`message` + `code` + `diagnostic`); `frontend/src/lib/ai-feedback.ts` is the
single user-safe presentation layer (`aiFailure`) and maps any AI error —
including network `TypeError` and aborts — to that copy.

The previous teacher-visible text
`AI provider 'gemini' returned no usable content (state: LIVE_ERROR). Previous
content preserved.` is **gone** from the review page; the equivalent detail now
lives in `diagnostic` for operators. An audit (`grep`) confirms no
teacher-facing UI renders `LIVE_ERROR`, `malformed_json`, "provider returned no
usable content", or raw HTTP codes.

AI failure never blocks manual editing: the activity editor stays fully usable;
only the `Suggest Main Learning` button is disabled while a request is in
flight.

## PART L / M — Quota and quality gate

`consume_ai_generation()` is reached only after a successful, non-empty,
mapped result. Provider failure, 429/503, malformed/empty output, a
quality-gate rejection and deterministic fallback all consume **0** AI
generations. A light section-level gate drops unusable activities (blank
description, out-of-range duration); the full generation-time quality gate is
unchanged.

## PART N–T — Downloads (DOCX / PDF)

The pipeline was already the one-time-URL model: the tab-authenticated
`POST /api/generation/{job}/download-url` renders and validates server-side,
then hands back a single-use, user-bound token the browser navigates to
(`GET /api/generation/downloads/{token}` → `Content-Disposition: attachment`).
The token is the credential for the GET; the POST uses the current tab's
`Authorization: Bearer <sessionStorage token>`. No cookies, no localStorage, no
shared token.

This phase makes the *failure* path truthful (PART T):

* `getDownloadUrl` and `exportBlob` translate a browser-level fetch rejection
  (`TypeError("Failed to fetch")`) into
  `We couldn't reach the server. Check your connection and try again.`
* HTTP failures keep their real cause — 401 session expired, 403 plan gate,
  503 LibreOffice environment limitation, 500 server render failure.
* PDF without LibreOffice stays a controlled 503 with a meaningful message;
  DOCX remains independently downloadable.

## PART AC — Backend tests

`backend/tests/test_main_learning_remediation.py` (17 tests):

* normalize/main_learning: V2 object, list, string, legacy key, blanks dropped,
  out-of-range duration dropped, empty payload.
* persistence: edit, add, remove, change duration, save/reload round trip,
  isolation from other lessons and other fields.
* AI: successful structured replacement consumes one unit; empty output, rate
  limit, malformed JSON, and 503 all preserve the lesson and consume **0**.
* message contract: no `LIVE_ERROR` / provider internals in `message`; raw
  detail preserved in `diagnostic`.

Existing download coverage (`tests/test_real_use_remediation.py`,
`tests/test_final_web_ux.py`, `tests/test_export_download.py`) already locks
authenticated DOCX/PDF delivery, single-use and user-bound tokens, missing-token
rejection, and the PDF environment limitation.

## PART U / AA — Browser acceptance

`frontend/e2e/main-learning-download-acceptance.js` drives a real browser
through: Phase 2 editable → edit/save/reload persistence → add/remove/duration
→ `Suggest Main Learning` (structured success **or** calm failure with existing
content preserved) → manual edit after failure → DOCX/PDF downloads verified by
real bytes (PK zip / `%PDF-`) or the controlled PDF environment message.

## Verification

* Backend suite: **1475 passed, 12 skipped** (includes the 17 new tests).
* Frontend: `tsc --noEmit` clean; `next build` succeeds.
* No raw provider diagnostics in any teacher-facing surface.
