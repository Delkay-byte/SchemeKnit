# HERO V3 — LANDING MESH PHYSICS + ROLE-SPECIFIC AUTH/ACTIVATION UI

**Project:** SchemeKnit (repo folder: `TeachFlow`)  
**Date:** 2026-09-24  
**Branch:** `main` @ `35f77384f9225035cc61bc8d853b22feda98df54` (base HEAD — this report describes the changes committed on top)  
**Remote:** `https://github.com/Delkay-byte/SchemeKnit.git`  
**Scope:** Frontend design + interaction only. Backend generation, curriculum parser, quota, entitlements, AI providers, database, migrations, lesson-plan structure, Platform Admin authorization, and auth/role behavior are **unchanged**.

---

## 1. APMIX behavioral study (observed vs inferred)

**Method:** Live rendered behavior only via Playwright (`frontend/e2e/apmix-study.js`).  
**No proprietary source was inspected, scraped, or copied.**

### Observed (browser measurements)

| Finding | Detail |
|---|---|
| Renderer | **Canvas 2D only** — `hasWebGLContextType: false` on all viewports |
| Canvas count | **2** (hero 1440×836; dark footer band 1440×363) |
| Hero host | `section.relative.overflow-hidden` |
| Canvas pointer-events | `pointer-events: none` (content remains interactive above) |
| Globals | No `THREE` / `gsap` / `jQuery` / `PIXI` / `p5` / `Matter` / Framer Motion / Next |
| Pointer response | Hero canvas pixel sum changed during pointer path (`before=1599` → `during=1707`), settled after stop (`settled=1020`), changed again after leave (`left=1071`) |
| Reduced motion | Canvases still present and painted under `prefers-reduced-motion: reduce` |
| Mobile (390) | Both canvases still present; hero fills tall viewport |

### Inferred (not source-confirmed)

- Local cursor deformation with soft falloff (pixel deltas concentrate during path, not a full-page wipe).
- Static/ambient frame under reduced motion (no continuous animation loop required).
- Grid/network topology (visual only; not confirmed as springs vs particles).

Artifacts: `frontend/e2e/apmix-study/study.json` + screenshots (not committed).

---

## 2. Mesh V3 physics (landing only)

**Component:** `frontend/src/components/mesh-background.tsx`

V2 issues corrected:

1. **Falloff ring → central lens** — V2 `smoothFalloff` peaked mid-radius (ring). V3 uses `lensFalloff`: `1` at center → `0` at edge, smoothstep + `pow(power)` for a strong core.
2. **Isolated springs → membrane** — second pass Laplacian neighbor blend so deformation travels as a coherent surface.
3. **No inertia** — pointer interpolated in rAF; velocity couples into node forces (lag on fast move, settle after stop).
4. **No depth** — elevated nodes grow/glow; nearby lines thicken/brighten; soft radial cyan lens light under the cursor.

Tuning (hero): radius **200px**, `pushStrength 52`, `lensPower 2.1`, `neighborBlend 0.14`, `velocityGain 0.55`, `damping 0.86`.

| Concern | Handling |
|---|---|
| Window-level pointer | Wrapper is `pointer-events: none` — CTAs unaffected |
| Enter/leave/blur | Full restore of force + velocity |
| Resize | `ResizeObserver` rebuilds grid; pointer velocity zeroed |
| Tab hide | `visibilitychange` cancels rAF |
| DPR change | matchMedia resolution listener rebuilds |
| Coarse pointer | Interactive only when `(hover: hover) and (pointer: fine)` |
| Reduced motion | Static mesh, no loop |
| Mobile density | Hero keeps viewport-capped columns; ambient coarser |
| No WebGL | Canvas 2D only |

**Mounted only in** `landing/landing-hero.tsx`.  
**Removed from** `auth/auth-shell.tsx` (Hero V2 ambient mesh deleted).

---

## 3. Distinct auth / activation experiences (no mesh)

Shared: typography, buttons, inputs, logo capsule, spacing.  
**Not shared:** page background, decoration, accent bar, badges, aside copy.

| Role | Route | Visual concept | Page bg |
|---|---|---|---|
| Teacher login | `/login` | Warm paper + education SVG motif + audience cards | `#F7F5F0` |
| Registration | `/signup` | Bright white + cyan workflow chips + step pills | `#FFFFFF` |
| School admin | `/login/school-admin` | Dark navy split + architectural grid + value aside | `#0B1F3A` |
| Platform admin | `/login/platform-admin` | Near-black ops surface + shield SVG + restricted aside | `#050E18` |
| School activation | `/activate-school` | Cool slate + key glyph + multi-step pills | `#F3F6FA` |
| Teacher/desktop license | `/activate` | Soft ivory + amber key accent + step pills | `#FAFAF7` |
| Password reset | `/reset-password` | Soft ice + padlock glyph | `#F4F7FA` |
| First-run setup | `/setup` | Violet tint + envelope motif + step pills | `#F8F7FC` |
| Platform bootstrap | `/setup/platform-admin` | Same dark platform shell + bootstrap security note | `#050E18` |

Role styling is **cosmetic only**. API contracts, redirects, setup-status checks, and backend role checks unchanged.

Authenticated pages (`/school-admin/license`, dashboard license modal, `/upgrade`) already have no mesh and distinct authenticated chrome — no change required for mesh removal.

---

## 4. Logo contrast fix

**Root cause:** Canonical mark fills are navy `#102A43` + cyan `#04A9CE` (`SchemeKnitMark` / `assets/brand/schemeknit-mark.svg`). Navy-on-dark capsules (`#0d2740`, `bg-white/5` on `#071826`) made the S nearly invisible.

**Fix:** Light capsule (`#F4F7FA` / white) + border + cyan ring/shadow. Geometry unchanged.

| Surface | Treatment |
|---|---|
| Landing header | Light `#F4F7FA` capsule + cyan ring + soft shadow |
| Footer | Light `#F4F7FA` capsule + cyan ring |
| Auth shells | `BrandCapsule` light surface |
| Dashboard header | Already light `#F4F7FA` (unchanged) |

Acceptance: landing + footer + every auth route report light capsule luminance `> 230`.

---

## 5. Route / API preservation

- Login wrappers still thin: `/login`, `/login/school-admin`, `/login/platform-admin`.
- Same backend login; redirects by **account role**.
- Signup still `POST /api/auth/register/individual`.
- No self-service forgot-password API — helper text + `/contact` only.
- Platform Admin: **no public CTA**; direct route works; UI hiding ≠ security.
- Activation flows (`validateActivationCode`, `setupAfterActivation`, `activateDesktop`) untouched.

---

## 6. Validation

| Gate | Result |
|---|---|
| `npx tsc --noEmit` | **exit 0** |
| `npm run build` | **exit 0** · 35/35 static pages |
| Browser harness | `frontend/e2e/hero-v3-acceptance.js` vs `next start` `:3003` |
| **Acceptance** | **88 pass / 0 fail** |

Covered: landing mesh paint + cursor deformation; auth routes **canvas count = 0**; 8 distinct backgrounds; light logo on landing/footer/all auth; responsive 390/430/768/1024/1280/1440; reduced-motion static mesh; no public platform-admin link; mobile auth overflow.

Screenshots under `frontend/e2e/hero-v3-acceptance/` (not committed).

---

## 7. Files changed

**Modified**

- `frontend/src/components/mesh-background.tsx` — V3 lens + membrane + velocity physics  
- `frontend/src/components/auth/auth-shell.tsx` — mesh removed; multi-role themes + `BrandCapsule`  
- `frontend/src/components/role-login.tsx` — role-themed loading skeletons  
- `frontend/src/app/page.tsx` — light logo capsule  
- `frontend/src/components/public-footer.tsx` — light logo capsule  
- `frontend/src/app/signup/page.tsx` — step pills  
- `frontend/src/app/activate-school/page.tsx` — AuthShell `school_activate`  
- `frontend/src/app/activate/page.tsx` — AuthShell `teacher_license`  
- `frontend/src/app/reset-password/page.tsx` — AuthShell `password_reset`  
- `frontend/src/app/setup/page.tsx` — AuthShell `first_run`  
- `frontend/src/app/setup/platform-admin/page.tsx` — AuthShell `platform_admin`

**New**

- `frontend/e2e/hero-v3-acceptance.js`  
- `frontend/e2e/apmix-study.js`  

**Unchanged (intentionally):** backend/**, auth logic, role permissions, API payloads, lesson template, `SchemeKnitMark` geometry, public Platform Admin hiding.

---

## 8. Commits

| Commit | Message |
|---|---|
| *(implementation)* | `feat: refine landing mesh and role-specific auth experiences` |
| *(report)* | `docs: add Hero V3 role auth report` |

Base: `35f7738` (Hero V2 report). Both target `origin/main`.

---

## Constraints checklist

| Constraint | Status |
|---|---|
| No backend / parser / quota / entitlement / AI / DB / lesson structure change | **PASS** |
| No Platform Admin public CTA; direct route works | **PASS** |
| No Three.js/WebGL; Canvas 2D only | **PASS** |
| Mesh **landing-only**; no canvas on any auth/activation route | **PASS** |
| Each role/page has a distinct visual treatment (not just hidden mesh) | **PASS** (8 unique bgs) |
| Reduced motion → static mesh | **PASS** |
| Fine-pointer gate; coarse/mobile no forced deformation | **PASS** |
| Logo mark geometry unchanged; readable on dark + light | **PASS** |
| Headline + CurriculumPipeline preserved | **PASS** |
| Signup / login / activation API contracts preserved | **PASS** |
| `npx tsc --noEmit` + `npm run build` green | **PASS** |
| Browser matrix + reduced motion | **PASS 88/88** |
