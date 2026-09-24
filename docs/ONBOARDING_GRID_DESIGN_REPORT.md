# ONBOARDING GRID DESIGN — SCHEMEKNIT GRID SYSTEM V3

**Project:** SchemeKnit (repo folder: `TeachFlow`)  
**Date:** 2026-09-24  
**Branch:** `main`  
**Remote:** `https://github.com/Delkay-byte/SchemeKnit.git`  
**Scope:** Extend the login grid visual language (V2) to signup + all onboarding/activation pages; upgrade `GridSignal` to 3–4 simultaneous moving signals; fix decorative-card text legibility.  
**Out of scope (untouched):** hero mesh V4, auth API, backend, curriculum, generation, parser, quotas, AI providers, database, migrations.

---

## A. Problem (V3)

V2 shipped a dark technical grid + single moving signal on the three logins only. Signup, activation, recovery, and setup pages still sat on light/warm V1 surfaces with no shared grid language. Decorative cards used low-opacity white text (`text-white/30`) that failed contrast on dark fields. `GridSignal` drove one node — static screenshots often looked frozen.

V3 mandate: **one grid family across all 10 auth/onboarding surfaces**, **3–4 simultaneous signals**, and **readable decorative text** — visual/animation only.

---

## B. Design decisions

### Dark fields (distinct per surface, all verified unique)

| Surface | Route | Background | Hex | GridSignal variant |
|---|---|---|---|---|
| Teacher Login | `/login` | Deep SchemeKnit navy | `#071826` `rgb(7,24,38)` | `teacher` |
| School Admin Login | `/login/school-admin` | Institutional navy | `#0B1F3A` `rgb(11,31,58)` | `school` |
| Platform Admin Login | `/login/platform-admin` | Near-black ops | `#050E18` `rgb(5,14,24)` | `platform` |
| Signup | `/signup` | Registration navy | `#0A1F35` `rgb(10,31,53)` | `register` |
| School Activation | `/activate-school` | Institutional activation | `#0A2240` `rgb(10,34,64)` | `school_activate` |
| Teacher License | `/activate` | License slate | `#0E1C2E` `rgb(14,28,46)` | `teacher_license` |
| Password Reset | `/reset-password` | Recovery ink | `#0A1628` `rgb(10,22,40)` | `password_reset` |
| First-Run Setup | `/setup` | Init indigo | `#0D1630` `rgb(13,22,48)` | `first_run` |
| Platform Admin Setup | `/setup/platform-admin` | Near-black ops | `#050E18` `rgb(5,14,24)` | `platform` |

`setup` loading bg darkened `#F8F7FC` → `#0D1630` (spinner violet-400 retained). Platform-admin complete/success states also render `GridSignal variant="platform"`.

### Multi-signal model (V3 core)

| Property | Value |
|---|---|
| Default desktop signals | **4** (`DEFAULT_SIGNALS`) |
| Default mobile signals | **3** (`MOBILE_SIGNALS`, width < 640) |
| `signalCount` prop | Optional override, clamped 2–6 |
| Travel | Grid-aligned only (up/down/left/right), intersection → intersection |
| Easing | `easeMove` = `0.42·t + 0.58·smoothstep(t)` — never stalls at endpoints |
| Edge duration | Per-variant base ± ~14% jitter; mobile × `1.28` (`MOBILE_SPEED_SCALE`) |
| Per-signal phase | Distinct PRNG seeds + `speedMul` 0.88–1.23 so edges desynchronize |
| Start anchors | Six distinct open-field nodes (left field, lower-right, upper-right, center, etc.) — no stacking |
| Halo accents | Alternating primary / `altHalo` per signal index |
| Trails | Per-signal max 8 samples, alpha ramp, width ramp |
| Proximity illumination | Lines brighten within ~2.4 cells of **any** signal |
| Intersection flash | 1 → 700 ms decay on arrival |
| Diagnostics | `data-grid-signal`, `data-signal-count`, `data-signal-frame` (every 3rd), `data-signal-positions="x,y x,y…"` |
| Reduced motion | Static frozen grid + parked heads; no rAF |
| Perf | Canvas 2D + rAF only; DPR ≤ 2; pause on `visibilitychange`; ResizeObserver rebuild |

### Variant personalities

| Variant | Cell | Line RGB | Core / Alt |
|---|---|---|---|
| `teacher` | 44 | `110,165,205` steel | `#04A9CE` / cyan |
| `school` | 48 | `126,220,240` cyan | `#7EDCF0` / emerald |
| `platform` | 56 | `90,130,170` slate | `#04A9CE` / indigo |
| `register` | 46 | `100,155,200` | `#04A9CE` / sky |
| `school_activate` | 52 | `120,200,220` | `#34D399` / cyan |
| `teacher_license` | 48 | `140,170,200` | `#04A9CE` / amber |
| `password_reset` | 50 | `110,150,190` | `#38BDF8` / cyan |
| `first_run` | 50 | `120,140,200` | `#04A9CE` / violet |

### Decorative-card legibility

- **No** `text-white/30` (or lower) on meaningful labels.
- Light cards keep dark ink: teacher lesson stack `bg-white/96` + `#102A43`/`#3D5A75`; signup chips `bg-white/95`; license card warm gradient + navy; recovery lock plate `bg-white/92`; init console `bg-white/95`.
- Dark-field rails use `text-white` or `text-white/80` (notebook tabs, school step rail, recovery path).
- Platform status ticks `text-slate-400` (was too dim), moved `left-8 top-8` → `bottom-28 left-8` to clear the aside BrandCapsule.
- Cards sit above the canvas (`z-10` content layer); decor is `aria-hidden` + `pointer-events-none`.
- Wide-layout header (school/license) moved **outside** the card onto the dark field: white wordmark, white badge, `StepRail onDark`.

### What was explicitly avoided

- Landing `MeshBackground` on any auth/onboarding route (still `data-mesh="landing"` only).
- Sci-fi/neon/particles/WebGL/Three/GSAP; random diagonal drift.
- Any change to form logic, labels, validation, step logic, redirects, error handling, role permissions, or API surface.
- Public Platform Admin CTA; forgot-password remains `/contact`; logo geometry frozen.

---

## C. Implementation map

| File | Change |
|---|---|
| `frontend/src/components/auth/grid-signal.tsx` | Multi-signal engine (4/3 defaults), 8 variants, per-signal seeds/speeds/halos/trails/anchors, proximity across all signals, diagnostics attrs, reduced-motion static draw |
| `frontend/src/components/auth/auth-shell.tsx` | Dark `THEMES` ×8, `DARK_ROLES`, all decors restyled + GridSignal wired, `StepRail onDark`, wide-layout white header, `DepthCard dark`, contrast fixes |
| `frontend/src/app/setup/platform-admin/page.tsx` | GridSignal in decorOverride + complete + success states; status-tick contrast + position fix |
| `frontend/src/app/setup/page.tsx` | Loading bg `#F8F7FC` → `#0D1630`; info-card text darkened |
| `frontend/e2e/login-grid-acceptance.js` | Rewritten 10-page matrix, signal-count, independent-motion, legibility, reduced-motion, landing-mesh exclusivity |
| `frontend/e2e/auth-role-design-acceptance.js` | 8 dark bgs, 8 LOGIN_SIGNALS routes, signal-count + no-mesh checks |
| `frontend/e2e/hero-v3-acceptance.js` | Same bg + signal expansion for the hero matrix |

### DOM markers

- Landing mesh: `[data-mesh="landing"]`
- Signal canvas: `canvas[data-grid-signal="teacher|school|platform|register|school_activate|teacher_license|password_reset|first_run"]`
- Count / positions: `data-signal-count`, `data-signal-positions`
- Root: `[data-grid-signal-root="…"]`

---

## D. Acceptance results

Gates (local production build, `next start -p 3003`):

| Gate | Result |
|---|---|
| `npx tsc --noEmit` | Clean |
| `npm run build` | **35/35** pages |
| `e2e/login-grid-acceptance.js` | **534 pass / 0 fail** |
| `e2e/auth-role-design-acceptance.js` | **131 pass / 0 fail** |
| `e2e/hero-v3-acceptance.js` | **151 pass / 0 fail** |

`login-grid-acceptance` checks (10 pages × viewports):

- Load, title, exact dark bg, no landing mesh, correct variant, light logo capsule, readable card, form present (or bootstrap-complete bypass), grid painted.
- **Signal count 3–4** via `data-signal-count`.
- **Independent motion**: timed samples of `data-signal-positions`; ≥2 signals moved (`anyMoved`), not just brightest-pixel probe.
- **Decor-text legibility** probe on each page.
- Responsive matrix 390/430/768/1024/1280/1440: no overflow, dark, signal, logo.
- Reduced motion: static multi-signal grid painted; positions frozen.
- Landing: mesh present, no login signal.

`auth-role-design` / `hero-v3`: all 8 dark backgrounds exact; 8 routes expose GridSignal; landing mesh exclusive.

### Bug fixes during V3

1. **`nodeXY` wrong row origin** — used bare `r` instead of `oy + n.r * cell`.
2. **Brightest-pixel probe jumps** between equal-brightness signals → false “static” fails. Motion helpers now prefer `data-signal-positions[0]` + `anyMoved()` across all positions; brightest probe kept only as fallback.
3. **`DARK_ROLES` typing** — `new Set<AuthShellRole>([...])` (annotation `ReadonlySet` caused TS2322).
4. **Platform status ticks overlapped aside logo** — repositioned to `bottom-28 left-8` in both `PlatformOpsDecor` and `setup/platform-admin` decorOverride.
5. **tsx opacity class on `<svg>`** — use `style={{ opacity }}` to satisfy TS.

### Screenshot review (manual, 6 widths)

Captured under `frontend/e2e/login-grid-review/` (not committed) at **390 / 430 / 768 / 1024 / 1280 / 1440** for Teacher Login, Signup, School Activation, Teacher License, Platform Admin:

- **Teacher:** navy field, steel grid, 4 cyan signals in open field, lesson card + notebook tabs readable, form dominant.
- **Signup:** step rail above card, curriculum chips dark-on-white, multi-signal trails.
- **School Activation:** emerald/cyan signals, building glyph, right-edge rail `text-white/80`.
- **Teacher License:** amber license card legible, topo underlay, amber+cyan signals.
- **Platform Admin:** ticks clear of logo, shield/horizon intact, restrained slate grid.
- **Mobile 390:** large cells, logo + step rail clear, no overflow, 3 signals.
- Form remains above decor on every surface; light BrandCapsule readable on all dark fields.

---

## E. Explicit non-changes

- No backend, API, auth logic, session, or permission changes.
- Signup API/flow/fields/validation/step logic/redirects/error handling frozen (visual only).
- Landing page mesh and hero motion (V4) untouched.
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

Manual: open `/login`, `/signup`, `/activate-school`, `/activate`, `/login/platform-admin` — expect a dark technical grid with **3–4 cyan/green signals** walking intersections; toggle OS reduced-motion and confirm the grid freezes with signals parked.

---

## G. Commits

| Type | Message |
|---|---|
| feat | `feat: extend interactive grid system across onboarding` |
| docs | `docs: document interactive onboarding grid system` |
