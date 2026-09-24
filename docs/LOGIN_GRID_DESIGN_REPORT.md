# LOGIN GRID DESIGN — DARK PROFESSIONAL GRID + MOVING SIGNAL

**Project:** SchemeKnit (repo folder: `TeachFlow`)  
**Date:** 2026-09-24  
**Branch:** `main`  
**Remote:** `https://github.com/Delkay-byte/SchemeKnit.git`  
**Scope:** Login interfaces only — Teacher (`/login`), School Administration (`/login/school-admin` = visual benchmark), Platform Administration (`/login/platform-admin`).  
**Out of scope (untouched):** registration, activation pages, password recovery, setup/bootstrap pages, teacher license, backend, auth API/logic/permissions, database, generation, curriculum, AI, quota, entitlements, landing mesh design.

---

## A. Problem (V2)

V1 introduced a shared Canvas 2D grid + signal (`GridSignal`) on all three logins, but:

| Issue | Detail |
|---|---|
| Near-white teacher field | Teacher login still sat on warm `#F7F5F0` — not a dark professional workspace |
| Signal too subtle | Small core + weak trail; motion often hard to see in stills |
| Easing stall | `easeInOut` cubic froze at edge endpoints → platform mobile samples looked static |
| Teacher start under card | Center-start put the node behind the centered form card |

V2 mandate: **dark navy login fields**, a **stronger grid**, a **visibly moving signal**, and a dedicated `login-grid-acceptance` suite proving motion.

---

## B. Design decisions

### Dark fields (distinct per role)

| Surface | Background | Hex |
|---|---|---|
| Teacher | Deep SchemeKnit navy | `#071826` (`rgb(7, 24, 38)`) |
| School Admin (benchmark) | Institutional navy (unchanged) | `#0B1F3A` (`rgb(11, 31, 58)`) |
| Platform Admin | Near-black ops (unchanged) | `#050E18` (`rgb(5, 14, 24)`) |

Teacher decor (`TeacherWorkspaceDecor`) restyled for dark: gradient wash `#071826 → #0B1F3A`, vignette, light lesson-plan cards / notebook tabs / cyan blurs kept as supporting motifs. `isDark` now includes teacher → dark `DepthCard`, dark badge chip, light `BrandCapsule` with wordmark. Loading state (`role-login`) teacher → `bg-[#071826]`.

### Shared system (`GridSignal`) — V2 variants

| Property | Teacher | School (benchmark) | Platform |
|---|---|---|---|
| Cell size (desktop) | 44px | 48px | 56px |
| Line RGB | `110,165,205` (steel blue) | `126,220,240` (cyan) | `90,130,170` (slate) |
| Line alpha | 0.20 | 0.17 | 0.20 |
| Signal core | `#04A9CE` | `#7EDCF0` | `#04A9CE` |
| Edge duration | ~750ms | ~720ms | ~840ms |
| Proximity boost | 0.22 | 0.24 | 0.20 |
| Personality | Workspace navy, steel grid | Institutional cyan | Dark ops, restrained |

### Motion model (V2)

- Single signal node; path always **grid-aligned** (up/down/left/right only).
- **`easeMove`**: `0.42·t + 0.58·smoothstep(t)` — smooth corners, **never stalls** at endpoints (fixes platform mobile d=0).
- Edge duration jittered ~±12% per edge; **mobile ×1.28** (`MOBILE_SPEED_SCALE`) → calmer phone travel.
- `pickNext`: no immediate reverse when alternatives exist; **55% straight** preference.
- Deterministic PRNG (`mulberry32`) per variant seed.
- **Start node** in the **open left field** (`cols × 0.18`) — clear of centered/split cards so early frames show the signal.
- Intersection flash (1 → 700ms decay), **trail max 9** samples, local line illumination (~2.4 cells), network node dots every other intersection.
- Core r=3.4 + white center; halo `cell×1.45` at 0.42 alpha — obvious in screenshots.
- Pauses when tab hidden; DPR ≤ 2; `pointer-events-none` + `aria-hidden`.

### Reduced motion

`prefers-reduced-motion: reduce` → static dark grid + resting node; no rAF. Mid-session media-query change restarts/stops cleanly.

### Composition rules (benchmark preserved)

- **School Admin:** split layout, aside copy, isometric building, vertical indicator — only the signal layer animates.
- **Teacher:** centered card, lesson-plan stack, notebook tabs — dark wash + GridSignal; curriculum cues kept, restyled for dark.
- **Platform:** split layout, shield, horizon, status ticks, `SECURE ADMIN ACCESS` — GridSignal only when `mode="login"` (setup keeps static `ops-v` via `decorOverride`).
- Light `BrandCapsule` remains; form card (`DepthCard`) stays above decor (`z-10`).

### What was explicitly avoided

- Landing `MeshBackground` on auth routes (still landing-exclusive, tagged `data-mesh="landing"`).
- Sci-fi/neon/gaming aesthetics; particles; random diagonal drift; WebGL/Three/GSAP.
- Any change to form logic, labels, a11y, CTA visibility, or route copy.
- Touch/pointer listeners on the login grid (signal is autonomous).

---

## C. Implementation map

| File | Change |
|---|---|
| `frontend/src/components/auth/grid-signal.tsx` | V2 variants (dark lines, faster edges), `easeMove`, `MOBILE_SPEED_SCALE`, stronger visuals, left-field start |
| `frontend/src/components/auth/auth-shell.tsx` | Dark `TeacherWorkspaceDecor`, teacher `pageClass` `#071826`, `isDark` includes teacher, dark badge chip |
| `frontend/src/components/role-login.tsx` | Teacher loading background `bg-[#071826]` |
| `frontend/src/components/mesh-background.tsx` | `data-mesh="landing"` (V1, retained) |
| `frontend/e2e/login-grid-acceptance.js` | **New** — 149-check dark grid + motion suite |
| `frontend/e2e/auth-role-design-acceptance.js` | Teacher bg `rgb(7, 24, 38)`, 3-sample motion, full-canvas probe |
| `frontend/e2e/hero-v3-acceptance.js` | Same teacher bg + 3-sample motion + full-canvas probe |

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
| `e2e/login-grid-acceptance.js` | **149 pass / 0 fail** (new) |
| `e2e/auth-role-design-acceptance.js` | **110 pass / 0 fail** |
| `e2e/hero-v3-acceptance.js` | **135 pass / 0 fail** |

`login-grid-acceptance` checks (per login × viewport):

- Load, title, dark field, exact bg color, no landing mesh, correct signal variant, light logo + S, readable card, form present, grid painted (>400 px).
- **3 timed position samples** (800ms gaps): found + moved ≥10px A→B and B→C.
- **Short-hop axis check** (280ms): path stays grid-edge aligned (no diagonal jumps).
- Responsive matrix 390/430/768/1024/1280/1440: no overflow, dark, signal, logo, grid visible; movement at 390/430/1440 (≥8px).
- Reduced motion: grid painted, **exact x/y frozen** across samples.
- Landing: mesh present, no login signal.

Existing suites retain titles, backgrounds, logo contrast, form/CTA visibility, keyboard focus, error state, public-CTA prohibitions, non-login zero-canvas, landing mesh interactivity.

### Bug fixes during V2

1. **Easing stall** — cubic `easeInOut` froze at endpoints → platform mobile samples identical. Replaced with `easeMove` (linear+smoothstep blend).
2. **Motion probe** — top-left pixel signature failed (signal starts center/left). All suites now use **full-canvas brightest-cyan position** (`(g+b-r)·a`, score ≥ 8000).
3. **Axis check false fail** — multi-edge 800ms intervals net-diagonal across corners. Replaced with **dense short hops** (280ms, < one edge).
4. **Teacher start under card** — center start hid the node behind the form. Start moved to **open left field** (`cols × 0.18`).

### Screenshot review (manual)

5-frame sequences (600ms apart) at 1440×900 + 390 stills for all three logins:

- **Teacher:** dark navy field, steel grid, signal glow clearly in open left field (not under card); node advances across frames (e.g. ~275,475 → ~305,485).
- **School:** cyan glow travels the aside field across frames — obvious displacement.
- **Platform:** restrained signal moves through left ops field; shield/horizon/ticks unchanged.
- Mobile stills: dark fields, large cells, card readable, no overflow; signal present (programmatic motion checks pass).
- Reduced motion: static grid + resting node, no drift.
- Form remains dominant; light logo capsule readable on all three dark fields.

---

## E. Explicit non-changes

- No backend, API, auth logic, session, or permission changes.
- No registration / activate / reset / setup visual redesign (setup platform-admin keeps its own static pattern).
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
node e2e/login-grid-acceptance.js http://localhost:3003
node e2e/auth-role-design-acceptance.js http://localhost:3003
node e2e/hero-v3-acceptance.js http://localhost:3003
```

Manual: open `/login`, `/login/school-admin`, `/login/platform-admin` — expect a dark navy technical grid and a cyan signal visibly walking the intersections; toggle OS reduced-motion and confirm the signal parks.

---

## G. Commits

| Type | Message |
|---|---|
| feat | `feat: improve login grid visual system and signal animation` |
| docs | `docs: update login grid visual system report` |
