# TeachFlow Desktop 1.0.4 — Acceptance

## Source
- Web release: TeachFlow Web 1.0.4 FINAL (frozen). No VCS in this environment; source
  identity = version strings (frontend/backend/desktop `package.json` + `APP_VERSION`,
  all `1.0.4`, Next 14.2.35).
- Desktop-only changes since freeze (no web behavior change except one declared item):
  1. `desktop/main.js`: per-installation secret generation (the web fail-fast secrets
     gate refused to boot the desktop backend — root-caused via diagnostics log, fixed
     at the desktop layer, NOT by weakening the backend).
  2. `desktop/backend.spec`: added `src/security.py` to datas/hiddenimports.
  3. **DESKTOP RELEASE-BLOCKING WEB CHANGE** (declared): `frontend/src/lib/route-params.ts`
     (new) + one-line use in `review/[id]`, `generate/[id]`, `lessons/[id]`. Cause: static
     export bakes `useParams() = 'placeholder'`; the packaged app requested
     `/api/documents/placeholder` (observed live). Fix reads the live URL only when the
     param is missing/`placeholder` — verified neutral on web (review intact, 392 tests, tsc).

## Installer
- File: `desktop/release/TeachFlow-Setup-1.0.4-x64.exe`, 116.6 MB, NSIS x64 per-user.
- SHA-256: `59a5449fc71fb228e7f0d06b3714fc7e58e55e20fdd80c2f4aa7d25d`
  (`TeachFlow-1.0.4-Windows-x64.sha256`). Unsigned (no cert — documented).
- Installs without node/python/conda/npm/repo; shortcuts (Desktop + Start Menu) created.

## Environment tested
Same Windows PC (dev-machine approximation, stated honestly): installed app runs from
`AppData\Local\Programs\TeachFlow`, data in per-user `AppData\Roaming\teachflow-desktop`
(DB + uploads/exports/temp + diagnostics.log + `.secrets.json`), backend 127.0.0.1:18234,
frontend 127.0.0.1:18235. No dev servers involved during acceptance.

## Results (installed EXE, real browser vs local servers)
- Install/launch/version 1.0.4 (API + window title)/first-run Paige Armour setup/no stale data: PASS
- Teacher workflow (upload→review→approve→generate 12→stepper→open→edit→save→refresh): PASS
- Review/generate/lesson placeholder routes resolve real IDs (route fix): PASS
- Organizational template (wizard→select→generate→DOCX: 36 tables, org dims, merges,
  new data, no leak): PASS
- Exports DOCX/XLSX valid files: PASS. ZIP bytes valid via API (12 entries, integrity OK);
  browser-click transfer shows the known machine-specific Chromium behavior (unchanged).
- Commercial: license create/suspend/activate, code validate/redeem/replay-403: PASS
- AI: Suggest works with local Ollama (default `llama3` model aliased); unavailable →
  controlled message, data intact; AI OFF default: PASS
- Offline: all observed traffic loopback-only (0 non-loopback requests during full journey)
- Restart: data + sessions persist (persisted per-install secrets); single Electron
  process tree (main+gpu+utility+renderer verified — earlier "duplicates" were subprocesses)
- Upgrade 1.0.3→1.0.4: data preserved, migrations 5→9 applied on boot: PASS
- Delete guard live: 409 on scheme with lessons; clean delete otherwise, no orphans: PASS
- Security scan (packaged tree): no .env, no shipped DB, no credentials/dev paths: PASS

## Known limitations
Unsigned installer (SmartScreen warning expected) · ZIP-click environment behavior ·
PDF converter absent (explicit 503 path) · no auto-update channel · single-user local data.
