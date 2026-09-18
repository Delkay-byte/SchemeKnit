# Public Entry & Installation — TeachFlow Web 1.0.4

Public entry points, role routing, PWA installation, the brand/icon system,
and the rules that keep development tooling out of production.

## Public landing page

The single public entry point presents the three audiences TeachFlow serves,
in order of audience size. Role is decided by the backend after login, never
by the card a visitor picks.

| Audience | Route | Notes |
|---|---|---|
| Teacher | `/login` | Primary card. Also offers `/signup` (individual free). |
| School Administration | `/activate-school` and `/login/school-admin` | Activate first, or sign in to an existing school. |
| Platform Administration | `/login/platform-admin` | Deliberately last and visually muted — an administrative entry, **not** a product tier. |

The landing page intentionally avoids the full Free-vs-Pro comparison; that
detail lives on `/login` and in the individual teacher dashboard.

## Role routing (unchanged)

```
PUBLIC LANDING
    |
    +-- Platform Admin   -> /platform-admin
    +-- School Admin     -> /school-admin
    +-- Teacher          -> /dashboard
```

- Platform Admin remains a **separate login interface** at `/login/platform-admin`
  and is never offered as a self-registration option.
- Teacher login is unified: School Teacher, Individual Free and Individual Pro
  all sign in at `/login`. There is no separate teacher PWA.
- School Admin flow: `/activate-school` (activation code) → account setup →
  `/school-admin`; or `/login/school-admin` for an existing account.

## PWA installation

TeachFlow is installable as a Progressive Web App on supported browsers.

- **Manifest:** `/manifest.webmanifest` — `name`/`short_name` "TeachFlow",
  `display: standalone`, relative `start_url` and `scope` (no localhost
  references anywhere in the manifest, so it resolves against whichever origin
  it is served from).
- **Install affordance:** a subtle, dismissible "Install TeachFlow" prompt
  (`src/components/pwa/install-prompt.tsx`) shown only when the browser itself
  fires `beforeinstallprompt` and the user has not dismissed it recently
  (persisted 30 days in `localStorage`). It never force-installs and never
  blocks content. Browsers with their own install UI (e.g. iOS Safari) never
  trigger the event, so nothing extra is shown there.
- **Service worker:** `/sw.js`, registered only in production builds
  (`src/components/pwa/pwa-manager.tsx`). It caches same-origin static app
  assets (`/_next/static`, `/icons`, the manifest) with a
  stale-while-revalidate strategy. It **never** caches `/api/*`, authentication
  tokens, private API responses, generated lessons or private documents, and
  navigation requests always go network-first so a stale authenticated view is
  never served. This is fast-open + install support, **not** full offline
  support — the app still requires a network connection to sign in and work.

### Physical-device acceptance

Manifest validity, icon assets, install-prompt wiring and responsive behavior
are verified by `frontend/e2e/pwa-public-entry.js` (76 checks) and
`frontend/e2e/browser-brand-check.js` (Chrome + Edge). **Install-to-home-screen
on a physical phone remains outstanding** — it requires mobile hardware and a
real production HTTPS origin, and is not falsely reported as passed here.

## Brand / icon system

One master mark, used everywhere. The mark is "Layered Ascent": an upward
chevron (progress/flow) rising from a structured base (curriculum), reading as
an open book (education) — minimal, geometric, legible at 16px, no text.

Canonical source and generated assets:

| Purpose | Path |
|---|---|
| **Master brand asset** | `assets/brand/teachflow-mark.svg` |
| Master raster (1024) | `assets/brand/teachflow-mark-1024.png` |
| Favicon (web) | `frontend/public/icons/favicon.ico` (16/32/48/64/128/256) |
| Favicon PNGs | `frontend/public/icons/icon-16/32/48.png` |
| Apple touch icon | `frontend/public/icons/apple-touch-icon.png` (180) |
| PWA icons | `frontend/public/icons/icon-192.png`, `icon-512.png` |
| Maskable PWA icons | `frontend/public/icons/icon-192-maskable.png`, `icon-512-maskable.png` |
| Inline UI mark | `frontend/public/icons/mark-mono-blue.png` |
| **Windows EXE icon** | `assets/brand/teachflow-windows.ico` (16/24/32/48/64/128/256) |
| Wordmark (optional) | `assets/brand/teachflow-wordmark.svg` |
| Generator | `assets/brand/generate_brand_assets.py` |

All raster assets are derived from the same geometry as the master SVG
(4x supersampled, LANCZOS downscaled). The icon is wired through Next.js
metadata in `frontend/src/app/layout.tsx` (favicon set, apple-touch-icon,
manifest icons), so the browser tab, installed app and future EXE share one
symbol.

### Desktop (EXE) — NOT modified in this milestone

The Windows EXE was **not** rebuilt. `assets/brand/teachflow-windows.ico` is
prepared for the subsequent desktop packaging milestone to consume as the
Electron/Windows application icon.

## Development-only controls and production safety

The demo commercial-data reset is the only development tool that existed in
the Platform Admin UI. It is now gated by three independent layers:

1. **Compiled out of production builds.** `frontend/src/lib/dev-tools.ts`
   resolves `DEV_TOOLS_ENABLED` at build time
   (`NODE_ENV === 'development' && NEXT_PUBLIC_DEV_TOOLS === 'true'`). In a
   production build this folds to `false` and the control, its handler and its
   API payload are tree-shaken away — verified by string-searching the
   production bundles (no `RESET DEMO COMMERCIAL DATA`, `resetDemoData`,
   `Development only` or `backend/src` strings survive). This is not a CSS
   hide.
2. **Runtime short-circuit.** `ApiService.resetDemoData()` returns a disabled
   response unless `DEV_TOOLS_ENABLED`.
3. **Backend 403.** `POST /api/platform-admin/reset-demo-data` raises 403
   whenever `Settings.DEBUG` is false, even for a platform admin supplying the
   correct confirmation phrase. Locked by
   `backend/tests/test_production_ui_safety.py`.

The local dev flag lives in `frontend/.env.local` (gitignored) and is never
present in a production build; even if it were, the `NODE_ENV` term dominates.

Production UI sweep result — none of these appear in any rendered production
page: `Development only`, `create_platform_admin.py`, `backend/src`, `RESET
DEMO COMMERCIAL DATA`, `localhost`, `teachflow.db`. The Platform Admin login
now reads "Authorized TeachFlow platform administrators only. Access is
restricted and cannot be self-registered." (no CLI commands or source paths).

The Platform Admin dashboard shows only operational concepts: Dashboard,
Schools, Plans, Licenses, Activation Codes, Payments, Audit.

## Verification commands

```bash
# Frontend
cd frontend
npx tsc --noEmit                        # 0 errors
npm run build                           # production build
node e2e/pwa-public-entry.js http://localhost:3001   # 76 PWA + entry checks
node e2e/browser-brand-check.js http://localhost:3000 # Chrome + Edge brand
PLAYWRIGHT_BROWSERS_PATH=$HOME/AppData/Local/ms-playwright \
  node e2e/final-production-acceptance.js            # 65 end-to-end

# Backend
cd backend
venv/Scripts/python -m pytest tests -q  # 710 tests, 0 failures
```

## Related documents

- `docs/PUBLIC_ENTRY_AND_ROLE_ARCHITECTURE.md` — role routing detail
- `docs/PLATFORM_ADMIN_ARCHITECTURE.md` — platform admin provisioning (CLI)
- `docs/COMMERCIAL_LIFECYCLE_ACCEPTANCE.md` — school activation lifecycle
- `docs/INDIVIDUAL_TEACHER_PLAN.md` — free vs Pro
- `docs/DEPLOYMENT.md` — production deployment (HTTPS origin for installability)
