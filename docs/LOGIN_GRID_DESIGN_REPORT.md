# LOGIN GRID DESIGN — SHARED GRID + MOVING SIGNAL SYSTEM

**Project:** SchemeKnit (repo folder: `TeachFlow`)  
**Date:** 2026-09-24  
**Branch:** `main`  
**Remote:** `https://github.com/Delkay-byte/SchemeKnit.git`  
**Scope:** Login interfaces only — Teacher (`/login`), School Administration (`/login/school-admin` = visual benchmark), Platform Administration (`/login/platform-admin`).  
**Out of scope (untouched):** registration, activation pages, password recovery, setup/bootstrap pages, backend, auth API/logic/permissions, database, generation, curriculum, AI, quota, entitlements, landing mesh design.

---

## A. Problem

The three login surfaces shared typography and form controls but had three unrelated static decorations:

| Surface | Previous decoration | Issue |
|---|---|---|
| Teacher | Static SVG pattern `teacher-grid` (32px, navy) | Flat, no sense of a living system |
| School Admin (benchmark) | Static SVG pattern `school-grid` (48px, cyan) | Benchmark composition good; zero motion |
| Platform Admin | Static SVG pattern `ops-v` (64px, slate) | Same static grid language, no signal |

The brief required one **shared visual language** — a professional grid with a **continuous moving signal node** traveling intersection-to-intersection — while keeping School Admin as the composition benchmark and the form as the dominant element.

---

## B. Design decisions

### Shared system (`GridSignal`)

One Canvas 2D component, `frontend/src/components/auth/grid-signal.tsx`, drives all three logins via a `variant` prop. Not the landing mesh: **no springs, no pointer force, no particle field, no WebGL/Three/GSAP.**

| Property | Teacher | School (benchmark) | Platform |
|---|---|---|---|
| Cell size (desktop) | 40px | 48px | 56px |
| Line RGB | `16,42,67` (navy) | `126,220,240` (cyan) | `62,90,120` (slate) |
| Line alpha | 0.075 | 0.12 | 0.14 |
| Signal core | `#04A9CE` | `#7EDCF0` | `#04A9CE` |
| Edge duration | ~1150ms | ~1050ms | ~1250ms |
| Proximity boost | 0.10 | 0.14 | 0.12 |
| Personality | Warm, soft, workspace | Institutional, refined | Darker, structured, restrained |

### Motion model

- Single signal node; path is always **grid-aligned** (up/down/left/right only — no diagonals, no floating particles).
- Edge-to-edge travel with **easeInOut cubic**; duration jittered ±15% per edge for organic feel (clamped).
- `pickNext`: never immediately reverses direction when alternatives exist; **55% preference for going straight** for long, calm runs.
- Deterministic PRNG (`mulberry32`, fixed seed per variant) — paths vary but stay reproducible.
- **Intersection flash** on arrival (intensity 1 → decay over 700ms).
- **Short fading trail** (max 7 samples) along the current path only.
- **Local line illumination**: grid lines brighten near the signal (halo color) with quadratic falloff over ~2.4 cells.
- Bounded to the viewport grid; continuous flow; pauses when tab is hidden.

### Reduced motion

`prefers-reduced-motion: reduce` → **static polished grid** + resting signal node at a fixed intersection; no `requestAnimationFrame` loop. Media-query change mid-session restarts/stops cleanly.

### Responsive

- Mobile (<640px): cell floor 56px; <420px: floor 64px → fewer intersections, calmer signal.
- Grid re-fits on `ResizeObserver`; DPR capped at 2.
- `pointer-events-none` + `aria-hidden` — form and links never blocked.

### Composition rules (benchmark preserved)

- **School Admin:** split layout, aside copy, isometric building, vertical indicator — only the static `school-grid` SVG was replaced with `<GridSignal variant="school" />`.
- **Teacher:** centered card, lesson-plan stack, notebook tabs, wash gradient — static grid replaced only.
- **Platform:** split layout, shield geometry, horizon line, status ticks, `SECURE ADMIN ACCESS` note — static `ops-v` replaced only in `mode="login"` (setup bootstrap keeps its own static pattern via `decorOverride`).
- Backgrounds unchanged: teacher `#F7F5F0`, school `#0B1F3A`, platform `#050E18`.
- Light `BrandCapsule` remains the logo treatment; form card (`DepthCard`) stays above the decor layer (`z-10`).

### What was explicitly avoided

- Landing `MeshBackground` on auth routes (still landing-exclusive).
- Sci-fi/neon/gaming aesthetics; particles; random diagonal drift.
- Any change to form logic, labels, a11y, CTA visibility, or route copy.
- Touch/pointer listeners on the login grid (signal is autonomous, not interactive).

---

## C. Implementation map

| File | Change |
|---|---|
| `frontend/src/components/auth/grid-signal.tsx` | **New** — shared grid + signal Canvas 2D component |
| `frontend/src/components/auth/auth-shell.tsx` | Import `GridSignal`; replace static patterns in teacher / school_admin / platform_admin decors |
| `frontend/src/components/mesh-background.tsx` | Add `data-mesh="landing"` on wrapper (test discrimination only; no visual change) |
| `frontend/e2e/auth-role-design-acceptance.js` | Canvas assertions split: logins expect role signal + timed motion + no landing mesh; other auth routes still expect zero canvas; reduced-motion static check; landing `data-mesh` check |
| `frontend/e2e/hero-v3-acceptance.js` | Same discrimination for auth routes; platform-admin end check now asserts grid-signal present + no landing mesh; reduced-motion login static check |

### DOM markers (for tests)

- Landing mesh: `[data-mesh="landing"]`
- Login signal canvas: `canvas[data-grid-signal="teacher|school|platform"]`
- Root: `[data-grid-signal-root="…"]`

---

## D. Acceptance results

Gates (local production build, `next start -p 3003`):

| Gate | Result |
|---|---|
| `npx tsc --noEmit` | Clean |
| `npm run build` | **35/35** pages |
| `e2e/auth-role-design-acceptance.js` | **110 pass / 0 fail** (was 89/0) |
| `e2e/hero-v3-acceptance.js` | **135 pass / 0 fail** (was 115/0) |

New/strengthened checks (both suites):

- Each login: role-specific `data-grid-signal` present; `[data-mesh]` absent.
- Each login: **two timed pixel samples (~950ms apart) differ** → signal is moving.
- Non-login auth routes (signup, activations, reset, setup): still **zero canvas**, no mesh.
- Landing: `[data-mesh]` present; mesh still painted/interactive (Hero V3/V4 checks retained).
- Reduced motion: grid signal present, **two samples identical** → static.
- No horizontal overflow at 390/430/768/1024/1280/1440 (existing checks retained).
- Existing titles, backgrounds, logo contrast, form/CTA visibility, keyboard focus, error state, public-CTA prohibitions — all retained.

### Screenshot review (manual)

Captured at 390 / 430 / 768 / 1024 / 1280 / 1440 plus motion pairs (A/B ~1.1s apart) and reduced-motion:

- Grids legible on all three surfaces; school composition unchanged vs benchmark.
- Motion pairs show the signal node at different intersections (teacher left rail; school top-right → mid-left; platform left field).
- Reduced-motion: static grid + resting node, no drift.
- Form remains dominant; light logo capsule readable on navy and near-black.
- Mobile: larger cells, no horizontal overflow, CTAs fully visible.

---

## E. Explicit non-changes

- No backend, API, auth logic, session, or permission changes.
- No registration / activate / reset / setup visual redesign (setup platform-admin keeps its own static `bootstrap-v` pattern).
- No landing page visual change (`data-mesh` attribute is inert).
- No new runtime dependencies; Canvas 2D + rAF only.
- Public Platform Admin CTA still absent; forgot-password still `/contact`; logo geometry frozen.

---

## F. How to verify

```bash
cd frontend
npx tsc --noEmit
# stop TeachFlow next processes, then:
Remove-Item -Recurse -Force .next
npm run build
node node_modules\next\dist\bin\next start -p 3003   # separate shell
node e2e/auth-role-design-acceptance.js http://localhost:3003
node e2e/hero-v3-acceptance.js http://localhost:3003
```

Manual: open `/login`, `/login/school-admin`, `/login/platform-admin` — expect a fine technical grid and a slow cyan signal walking the intersections; toggle OS reduced-motion and confirm the signal parks.

---

## G. Commits

| Type | Message |
|---|---|
| feat | `feat: add interactive grid signal to login interfaces` |
| docs | `docs: document login grid visual system` |
