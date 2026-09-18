# SchemeKnit Desktop 1.0.5 — Local Evaluation Build

**Build:** SchemeKnit-Setup-1.0.5-x64.exe
**Date:** 18 September 2026
**Purpose:** Local Windows evaluation of the frozen Web 1.0.5 application.
This is **not** the public production-connected installer — it runs the full
stack locally with no external infrastructure.

---

## Installer

| Field | Value |
|-------|-------|
| File | `SchemeKnit-Setup-1.0.5-x64.exe` |
| Size | 111.99 MB (117,427,576 bytes) |
| SHA-256 | `8f57d74247ac80df909c51c31ee4c37d8b7091130ef7012844f73f6043ecc7d6` |
| Architecture | x64 |
| Signing | Unsigned (evaluation build; `sign: false`) |
| Clean install | Requires **no** Node, Python, conda, PostgreSQL, or Docker |

The SHA-256 is recorded alongside the installer in
`SchemeKnit-Setup-1.0.5-x64.exe.sha256`.

---

## Local Architecture

| Layer | Technology | Verified |
|-------|-----------|----------|
| Shell | Electron 33 (single-instance, context-isolated) | Yes |
| Frontend | Next.js static export, served by local HTTP on 127.0.0.1:18235 | Yes |
| Backend | FastAPI frozen with PyInstaller → `schemeknit-backend.exe` on 127.0.0.1:18234 | Yes |
| Database | SQLite (fresh, per-user app data) | Yes |
| Storage | Local filesystem (uploads/exports/temp under userData) | Yes |
| AI | Local Ollama only (optional); no external API key | See below |

All services bind to `127.0.0.1` only. The bundled frontend contains **no
cloud URLs** (verified by scanning every shipped asset for
`schemeknit.com`, `vercel.app`, `railway.app` — zero matches), so the
deterministic features are fully offline-capable.

### Fresh local database
On first launch the backend creates a fresh SQLite database and applies all
15 migrations (v001–v015). Verified state after clean install:

- 28 tables created
- **0 users** — no bundled test schools, teachers, licenses, lessons,
  payments, or activation codes
- 15 migrations recorded

Platform Admin is created through the existing local bootstrap flow
(`/setup/platform-admin`); no credentials are hard-coded.

### Per-user data
Mutable data lives in `%APPDATA%\schemeknit-desktop\data\` (never Program
Files, never the source repo):

- `teachflow.db` — local database
- `.secrets.json` — strong per-installation secrets (48 random bytes),
  generated once and reused for token continuity across restarts
- `uploads/`, `exports/`, `temp/` — local file storage
- `diagnostics.log` — startup and runtime diagnostics

---

## Acceptance Results

### Process management — PASS
- Electron launches and creates the window
- Local frontend server starts (127.0.0.1:18235 → 200)
- Local backend starts and passes health check
  (127.0.0.1:18234 → `{"status":"healthy","service":"SchemeKnit","version":"1.0.5"}`)
- Single-instance lock works; second instance focuses the first
- Clean shutdown terminates the backend child process
- Backend startup failures surface in a retry/close dialog

### Restart / persistence — PASS
Two consecutive launches verified:

- Secrets identical across restarts (`ccaf0341392758d2` unchanged) —
  sessions survive restart
- Database byte-identical after restart (372,736 bytes) — users, schemes,
  lessons, templates, and configuration persist

### Offline — PASS (by architecture)
Every runtime dependency is local: the shell, the static frontend server,
the frozen backend, SQLite, and local file storage all bind to 127.0.0.1.
The bundled frontend resolves its API base to `127.0.0.1:18234` via the
`electronAPI` bridge exposed by the preload script. Deterministic
generation (AI OFF) requires no network. The only optional external
dependency is a locally-running Ollama instance.

### AI / Ollama — PASS
- The desktop sets `AI_MODE=OFF`; deterministic generation is fully
  functional without any AI provider (proven by the real-scheme
  generation + export acceptance).
- Ollama is wired as an optional provider. If Ollama is not running, AI
  enrichment degrades gracefully; deterministic generation is unaffected.
- **Commercial entitlement is never granted by Ollama existence.**
  `require_ai_entitlement()` inspects the user's database entitlement
  record (plan + credits), independent of provider availability.
  There is no "if Ollama exists → Pro" path anywhere.

### Package scan — PASS
Scanned 1,148 files (289 text files) in the packaged payload for:

- Resend / OpenAI / Anthropic / AWS / GitHub / Slack API keys → **none**
- Platform-admin bootstrap secret values → **none**
- Test/acceptance databases (`.db`, `.sqlite`) → **none**
- Docker artifacts → **none**
- Embedded developer paths (`C:\Users\SAVIOUR`, repo paths) → **none**

The only `.pem` file present is `certifi/cacert.pem`, the standard public
CA certificate bundle required for TLS — not a secret.

### Web regression — PASS
The `DESKTOP_MODE` addition is purely additive and does not alter frozen
Web 1.0.5 behavior (public web deployments leave it unset, so
`validate_production()` is unchanged for them):

- Backend tests: **780 passed, 7 skipped, 0 failed**
- TypeScript: clean
- Web production build (`build:web`): compiled successfully
- Desktop static export (`build:desktop`): succeeds

### Branding — PASS
Installer, uninstaller, header, start-menu shortcut, and executable all
use `assets/icon.ico`, which is the new SchemeKnit brand asset
(`assets/brand/schemeknit-windows.ico`, navy #102A43 + cyan #04A9CE).
Old TeachFlow-branded installers were removed from `release/`.

---

## How to Rebuild

```
cd desktop
build.bat
```

Requires Node.js + npm and the `build-venv` Python environment (with
PyInstaller installed). Outputs to `release\SchemeKnit-Setup-1.0.5-x64.exe`.

---

## Known Limitations

1. **Unsigned installer** — Windows SmartScreen may warn. This is expected
   for a local evaluation build; code signing is deferred to the public
   production release.
2. **No email password reset** — the local build has no Resend dependency
   by design. Password recovery uses the local Platform Admin bootstrap /
   reset flow instead.
3. **No cloud AI** — AI enrichment uses local Ollama only. External AI
   providers are for the public deployment.
4. **PDF export** depends on the bundled converter availability, same as
   the web build.
5. **Local entitlements** — Free/Pro/School entitlement gating is enforced
   through the local database. For evaluation, entitlements are configured
   locally (the commercial logic is exercised, not bypassed).

---

## Next Steps

This is the **local evaluation** desktop build. The next rebuild occurs
after production infrastructure is supplied (domain, hosting, PostgreSQL,
object storage, Resend, production AI configuration), at which point the
desktop will package the production-connected configuration.
