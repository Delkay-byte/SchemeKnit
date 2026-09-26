# Real-Use Remediation — Downloads, Resources, AI Truth, Monthly AI Quota

Production-testing remediation (Parts 1–28). Scope: repair the three download
paths, make scheme resources canonical structured data, kill serialized-array
leakage, make AI provenance truthful end to end, and convert the Free Tier AI
allowance from a lifetime bucket to a calendar-month quota. No redesign of the
application, WAPEF, or KG/Nursery/Basic 1–3 semantics.

## PART 1–4 / 22 — Downloads (DOCX / PDF / Register XLSX)

### Root cause
The download pipeline itself was sound: the UI's export buttons already go
through `POST /api/generation/{id}/download-url` (render + validate server-side)
→ one-time, user-bound token GET (`/api/generation/downloads/{token}`) that
answers `Content-Disposition: attachment`. Verified end-to-end at the API level:
DOCX 200 (valid zip), PDF 200 (real PDF when LibreOffice is present), XLSX 200
(valid zip). The "Generation problem / Failed to fetch" experience traced to
two client-side gaps:

1. **Environment drift** — the frontend served on :3000 was a stale dev build
   whose auth/session wiring predates tab-isolated auth; a production `next
   start` on a clean `.next` build resolved it.
2. **Error opacity** — when a download *does* fail (401 expired session, 403
   plan gate, 503 missing LibreOffice, 500 conversion failure), the frontend
   collapsed every case into a generic message.

### Fixes
* `frontend/src/lib/api.ts` — `exportErrorMessage()` maps the real HTTP status
  + backend `detail` to a truthful message (session expiry, plan gate,
  LibreOffice 503, server 5xx). The binary-response handling (Blob, never
  `response.json()`) was already correct and is unchanged.
* `frontend/src/app/(app)/generate/[id]/page.tsx` — the export error banner is
  no longer titled "Generation problem" (it serves export failures too).
* PDF keeps the documented LibreOffice environment contract: 503 with
  `PDF_CONVERTER_REQUIREMENT` text; DOCX/XLSX are unaffected by PDF-only
  limitations (verified: DOCX/XLSX succeed in the same environment).

### PART 2 verification
* Tokens are user-bound + single-use; a second fetch of the same token 404s,
  another user's token 404s (tests `test_real_use_remediation.py::
  TestDownloadEndpoints`).
* The tab's own sessionStorage token is used for the POST; the GET is a plain
  navigation — no cookie reintroduction, no localStorage.

## PART 5–11 — Canonical resources & empty-field contract

### Root cause (raw value inspected, not CSS)
The parser stored each scheme cell's resources text as ONE item
(`"Counters, sticks, flash cards"`), and the specific document in the
production screenshot carried an already-corrupted cell
(`["PicturesshowingCreatedthings,HolyBible,HolyQuran."]`) whose damage
propagated verbatim through allocation → lesson → API → UI.

### Fix — one canonical normalizer
New `backend/src/ai_resource_text.py`:
* `normalize_text_items()` — canonical `list[str]` for ANY stored list value:
  JSON/python serialized payloads are parsed, brackets are unwrapped,
  comma/semicolon/pipe/bullet separators split safely (a comma only splits
  when both fragments are plausible standalone items, so
  "Pictures showing Created things" stays one resource), empty forms
  (`[]`, `[,]`, `[""]`, `[" "]`, null, "N/A") collapse to `[]`, and jammed
  words are reconstructed (dictionary-lite TLR word list + camel-hump splits):
  `PicturesshowingCreatedthings,HolyBible` →
  `["Pictures showing Created things", "Holy Bible"]`.
* `clean_serialized_text()` / `normalize_text()` for single-string display.

Wired at every layer so legacy rows heal on read without touching teacher edits:
* parser `_merge_week_rows` (source), allocation (`source_resources`),
  lesson builder (`source_tlrs`),
  API `_serialize_lesson` + `_db_to_lesson_model` (review payloads; also
  `keywords`, `core_competencies`, `references`, `teaching_learning_resources`),
  draft save path (`other_tlrs`/`keywords` never store `""` placeholders),
  GES DOCX export (`_lesson_field_value`), WAPEF template `_text_items`.

### PART 9/10 verification
`other_tlrs` default `[]`; the review UI renders chips for source TLRs and a
blank teacher-additions input; browser acceptance asserts blank input, no
`[]`/`[,]`/`[""]` text, and Other-TLR persistence after save+reload.

## PART 12–15 / 20–21 — AI provider truth (single source of truth)

### Root cause
* Generate page queried `/api/settings/ai-status` per mode (correct resolution).
* Review page derived provenance from the generation job's `ai` payload.
* A real CASE-C bug: with no provider configured, `resolve_provider_mode()`
  returns `"ENHANCED"`, which `get_provider()` maps to **MockProvider**
  (`is_available() == True`) — a status path could report "AI active · provider:
  mock" while every lesson was deterministic.
* CASE D was unreported: a reachable provider whose real calls fail (live 429)
  left `reason: null`, inviting the reader to assume AI participated.

### Fixes
* `/api/settings/ai-status` refuses to report non-provider tokens as active
  (CASE C → `active: false, state: NOT_CONFIGURED`) and now returns
  `provider_label` — a display-quality backend-computed label ("Gemini") —
  the single source both pages render.
* Batch `ai_info` (generation.py) only marks `active` for real providers,
  names the tried provider in CASE B, and emits an explicit CASE D reason:
  "AI provider gemini did not produce usable content (…) — every lesson was
  generated by the deterministic engine. No AI generation was consumed."
* Frontend (generate page, lessons page) renders CASE A/B/C/D labels from the
  backend fields; no client-side provider inference remains.

## PART 16–19 — Monthly AI quota

### Design (explicit unit statement)
**AI quota unit = ONE successful AI-assisted generation REQUEST** (the unit the
previous lifetime counter already used — a 12-lesson batch consumes 1 unit, not
12). Allowance: **5 per calendar month** (`YYYY-MM` server-clock bucket,
`ai_generation_periods` table, migration `v027`), mirroring the lesson-plan
monthly ledger shape (`usage_quota.py`).

### Enforcement
* `backend/src/ai_quota.py` — guarded atomic increment (never exceeds the cap
  under races), per-user isolation, separate `ai_calendar_month` period type
  (independent of the lesson-plan quota).
* `consume_ai_generation()` writes to the monthly ledger only AFTER a
  successful AI-assisted generation (`ai_enrichment_succeeded > 0` for batch,
  post-quality-gate for section regeneration). Provider failure, 429/503,
  malformed output, quality-gate failure and deterministic fallback consume 0.
* `_entitlement_ai_decision` / `can_use_ai` read the monthly ledger; the legacy
  `ai_credits_used` lifetime counter is no longer any Free Tier gate.
* Paid plans (`ai_credits == 0`) and school licenses remain unlimited (-1).

### UI (PART 18)
Dashboard shows "X / 5 AI generations this month"; "lifetime" wording removed
from dashboard, signup, plan comparison, license pages; the exhaustion message
now says the allowance resets at the start of the next month.

## PART 24 — Browser acceptance (19/19 PASS)

`frontend/e2e/real-use-remediation-acceptance.js` →
`frontend/e2e/real-use-remediation-acceptance/`:
signup → dashboard monthly label (no "lifetime", 5/5) → upload WAPEF KG scheme
through the real UI → subject confirm → ENHANCED provider status (resolved
"Gemini") → 2-lesson batch → review page chips (9), no serialized text, blank
Other TLRs, Other-TLR persistence after save+reload, reference slots →
DOCX/PDF/XLSX downloads through the one-time URL flow (38 KB / 156 KB /
5.5 KB, real bytes) → no horizontal overflow at 1024/390.

## PART 25 — Live Gemini proof

`backend/live_gemini_proof.py` (14/15; the single "fail" is a benign 409
re-running against an existing user):

| Step | Result |
|---|---|
| Requested / resolved | gemini (ENHANCED auto-resolution), state CONFIGURED, label "Gemini" |
| Provider call | Live API returned **429 (rate-limited)** on every generateContent |
| Outcome | `lessons_ai=0`, `lessons_deterministic=1` — honest CASE D |
| Review payload | "AI provider gemini did not produce usable content … No AI generation was consumed." |
| AI quota | `ai_quota_used: 0 / 5`, period `2026-09`, `ai_lifetime: false` — **failure consumed nothing (PART 19)** |
| Lesson quota | Separate ledger (PART 30): lesson-plan monthly allowance decremented independently |

## PART 26 — Export verification

Downloaded DOCX unzipped; `word/document.xml` contains
`TEACHING & LEARNING RESOURCES (TLRs): Colours … Counters / sticks / flash
cards` as readable text — no `["`, `"]`, `[]`, `[,]`, no space-stripped words.
XLSX register and PDF bytes validated (zip / `%PDF-1.7`).

## PART 27 — Regression

* Backend: **1458 passed, 12 skipped** (includes new
  `tests/test_real_use_remediation.py` — 38 tests across downloads, canonical
  resources, AI status truth, monthly quota; plus updated lifetime→monthly,
  nursery/KG/phase16 canonical-resource expectations).
* Frontend: `tsc --noEmit` clean; `next build` succeeds (clean `.next`).
* Prior suites (special periods, template catalog, per-lesson metadata)
  remain green.
