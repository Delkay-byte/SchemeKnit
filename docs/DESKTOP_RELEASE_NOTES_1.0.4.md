# TeachFlow Desktop 1.0.4 — Release Notes

First production Windows release, packaged from frozen Web 1.0.4 (no separate implementation).

## Includes (web-verified, now desktop-verified)
Teacher workflow with persisted stepper, Platform/School Admin, licensing + activation
codes + seats, custom + organizational templates, DOCX/XLSX/ZIP, AI assist (optional
local Ollama), workflow persistence, 404-vs-403 diagnostics, guarded deletes.

## Desktop specifics
- Local backend (127.0.0.1:18234) + static frontend (127.0.0.1:18235), per-user SQLite.
- Per-installation secrets generated on first run (backend security gate compatible).
- Dynamic routes resolved via placeholder fallback + live-URL ids.
- Single-instance Electron shell; backend lifecycle tied to the app.

## Known limitations
Unsigned installer · ZIP-click behavior follows the machine-specific Chromium trait
(bytes verified valid) · PDF needs a converter (explicit message) · no auto-updates.
