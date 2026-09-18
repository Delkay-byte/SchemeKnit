# Export & Browser Acceptance

Status: **PARTIAL PASS** (browser tests require a live environment)

## Backend export (PASS)

All backend export paths work correctly through the HTTP API:

- **DOCX export** — returns valid DOCX bytes with correct content-type
- **ZIP export** — returns a valid ZIP containing structurally correct DOCX members
- **PDF export** — returns controlled 503 when no LibreOffice converter is
  installed (never a raw 500, never a fake PDF body)

### HTTP acceptance tests

Three tests in `tests/test_web_acceptance_http.py` exercise the full
browser-like workflow through the real ASGI app:

1. `test_full_workflow_and_approved_docx` — upload → review → approve →
   generate → edit → export DOCX → structural comparison against source
2. `test_zip_export_member_structurally_valid` — same workflow ending
   with ZIP export and member validation
3. `test_no_converter_is_a_controlled_503` — confirms 503 with
   `LibreOffice` in the detail string

All three use `StaticPool` in-memory SQLite to avoid the per-thread
connection problem with TestClient.

## Frontend download transport (PASS — code review)

The `downloadFile()` function in `frontend/src/lib/api.ts` correctly:

- Creates a temporary `<a>` element with `URL.createObjectURL`
- Triggers a click to download
- Revokes the object URL after a short delay (Chrome fix)

This is the standard pattern and handles the Chrome blob-revoke timing issue.

## Visual browser testing (BLOCKED)

Actual rendering in Chrome / Edge cannot be automated in a headless CI
environment without a browser stack. These items require a manual sign-off:

- DOCX opens correctly in Microsoft Word / Google Docs
- Table formatting renders as expected
- Phase headers are legible
- Exported file matches the approved template layout

Documented here for completeness; cannot be completed in this environment.
