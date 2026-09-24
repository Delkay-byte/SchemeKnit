# HERO V2 + PROFESSIONAL AUTHENTICATION EXPERIENCE

**Project:** SchemeKnit (repo folder: `TeachFlow`)  
**Date:** 2026-09-23  
**Branch:** `main` @ `9118be16e580029ca96f4f67d64322bec5d8eed2` (base HEAD — this report describes the changes committed on top)  
**Remote:** `https://github.com/Delkay-byte/SchemeKnit.git`  
**Scope:** Frontend design + interaction only. Backend generation, curriculum parser, quota, entitlements, AI providers, database, migrations, lesson-plan structure, Platform Admin authorization, and auth/role behavior are **unchanged**.

---

## 1. Interactive mesh background (Hero V2)

**Component:** `frontend/src/components/mesh-background.tsx`

- Canvas 2D curriculum mesh: spring-damped node grid with H/V/diagonal neighbour links.
- Modes: `hero` (dense, cursor-reactive) and `ambient` (auth pages, low-amplitude drift, no pointer force).
- Slight rest-position jitter for a woven, non-mechanical look.
- Accent nodes pulse softly; faint curriculum labels (SCHEME / SUBJECT / WEEK / INDICATOR / PERIOD / LESSON) stay atmospheric — not a diagram.
- Soft radial cyan lens + line brightening near the cursor.
- Runs entirely outside React render cycles (`requestAnimationFrame`); DPR-capped at 2; `ResizeObserver` rebuilds the grid.

**Hero integration:** `landing-hero.tsx` renders `<MeshBackground mode="hero" className={styles.meshLayer} opacity={0.95} />` behind `heroInner`.  
**Layering (measured):** mesh `z-index: 0` + `pointer-events: none`; content `z-index: 1`.

---

## 2. Cursor deformation behaviour

- Fine-pointer gate: `(hover: hover) and (pointer: fine)`.
- Window-level `pointermove` (wrapper is `pointer-events: none` so hero copy stays clickable); coordinates mapped into hero space; outside → deactivate.
- **Smoothstep falloff** radial push + slight tangential swirl; spring + damping settle to rest when the pointer stops; full restore on leave/blur.
- Pixel samples before/after cursor moves: mesh **changed** (deformation active); still animating after settle (ambient + residual motion).
- Not a particle system, starfield, or uniform ripple — local soft bulge only.

---

## 3. Performance

- Single canvas per surface; no WebGL / Three.js / animation libraries.
- `pointer-events: none` overlay — zero cost to CTA / pipeline interaction.
- `visibilitychange` pauses the rAF loop when the tab is hidden.
- Ambient mode uses coarser spacing on narrow viewports.
- No layout thrash; physics + draw only touch canvas pixels.

---

## 4. Reduced motion

- `prefers-reduced-motion: reduce` → **static refined mesh** (`drawStatic()`), no deformation loop, no CSS drift (existing `.hero::before` animation already disabled in the module).
- Acceptance: headline visible; mesh still painted; two samples identical under reduce (`changed: false`).
- Pipeline CSS animations already force `animation: none` under reduce (unchanged).

---

## 5. Logo / brand mark visibility

Raised capsule treatment (mark SVG itself unchanged — `SchemeKnitMark`):

| Surface | Treatment |
|---|---|
| Landing header (`app/page.tsx`) | Navy capsule `#0d2740/95`, border, soft black shadow, cyan ring `#04A9CE/25`, wordmark `Scheme`+`Knit` split |
| Dashboard `header.tsx` | Light capsule `#F4F7FA` + cyan ring on app chrome |
| Footer (`public-footer.tsx`) | Dark capsule + cyan ring |
| Auth shell + mobile brand | Navy capsule + cyan ring |

Acceptance: header brand visible; capsule ring present at 1440px.

---

## 6–9. Four auth experiences (one coherent product)

Shared shell: `components/auth/auth-shell.tsx` — desktop left brand/value panel + right white form card; mobile stacked brand above card; ambient mesh; role accent (badge, top bar, note). Role styling is **cosmetic only**.

| # | Experience | Route | Title | Distinctives |
|---|---|---|---|---|
| 6 | **Teacher registration** | `/signup` | Create your SchemeKnit account | Full name + email + password + **confirm password** + live `PasswordMatchIndicator`; Free Tier blurb; `api.registerIndividual` unchanged (frontend-only confirm) |
| 7 | **Teacher login** | `/login` | Teacher Sign In | Cyan Teacher badge; School vs Individual audience cards; Create account CTA; Forgot → helper with `/contact` link |
| 8 | **School administration** | `/login/school-admin` | School Administration Sign In | Emerald badge/top bar; activation-code link `/activate-school`; teacher cross-link |
| 9 | **Platform administration** | `/login/platform-admin` | Platform Administration Sign In | Slate badge; “Restricted access” indicator; security note; **no** forgot-password self-service (support/admin reset copy only) |

Common: linked labels (`AuthField`), premium `Input`, `PasswordInput` eye toggle, `AuthError` (`role=alert`), loading spinner on submit, cross-role footer links.

---

## 10. Routes & API behavior preserved

- Thin wrappers unchanged: `login/page.tsx`, `login/school-admin/page.tsx`, `login/platform-admin/page.tsx`.
- Same backend login endpoint for all roles; redirect by **account role** (`school_admin` → `/school-admin`, desktop platform → `/platform-admin`, else `/dashboard`); setup-status check retained.
- Signup still calls `POST /api/auth/register/individual` with `{email, password, full_name}`.
- **No Platform Admin link** on landing header, footer, role cards, or public auth footers (acceptance: `platformLogin: []`).
- Direct `/login/platform-admin` → HTTP **200**, form mounts (acceptance PASS).

---

## 11. Accessibility

- Every auth control has a real `<label htmlFor>`; errors use `role="alert"`; match indicator `role="status"` + `aria-live="polite"`.
- Mesh wrapper `aria-hidden="true"`; decorative gradients hidden.
- Focus rings on primary buttons, links, and inputs; keyboard-reachable forgot toggle (`type="button"`).
- Hero hierarchy preserved: headline > support > CTAs > pipeline > mesh.

---

## 12. Browser validation

**Harness:** `frontend/e2e/hero-auth-acceptance.js` against production `next start` on `http://localhost:3002`.  
**Result: TOTAL pass=133 fail=0.**

Covered:

- Hero @ 1440 / 1024 / 768 / 430 / 390 — headline, support, pipeline, mesh paint, no horizontal overflow.
- Cursor deformation + settle (pixel delta).
- Reduced-motion static mesh.
- All four auth routes @ 1440 — titles, badges, fields, labels, submit, forgot/security rules, platform CTA absence, overflow.
- Auth routes @ 1024 / 768 / 430 / 390 — email + submit visible, no overflow.
- Password match / mismatch live indicator.
- Forgot password → `/contact/` link.
- Platform admin direct route 200 + form mount.
- Screenshots written under `frontend/e2e/hero-auth-acceptance/` (not committed).

---

## 13. Type-check

```text
npx tsc --noEmit   → exit 0 (clean)
```

---

## 14. Production build

```text
npm run build      → exit 0
✓ Compiled successfully · 35/35 static pages
```

---

## 15. Files changed

**New**

- `frontend/src/components/mesh-background.tsx`
- `frontend/src/components/auth/auth-shell.tsx`
- `frontend/src/components/auth/auth-field.tsx`
- `frontend/src/components/ui/input.tsx`
- `frontend/e2e/hero-auth-acceptance.js`

**Modified**

- `frontend/src/components/role-login.tsx` — AuthShell redesign; routes/API/redirects preserved
- `frontend/src/app/signup/page.tsx` — AuthShell + confirm password + match indicator
- `frontend/src/components/landing/landing-hero.tsx` + `landing-hero.module.css` — mesh layer + z-index
- `frontend/src/app/page.tsx` — premium logo capsule
- `frontend/src/components/header.tsx` — capsule treatment
- `frontend/src/components/public-footer.tsx` — capsule treatment

**Unchanged (intentionally):** backend/**, auth logic, role permissions, API payloads, lesson template, `SchemeKnitMark` geometry, public Platform Admin hiding (already correct).

---

## 16. Commits

| Commit | Message |
|---|---|
| *(implementation)* | `feat: Hero V2 curriculum mesh + unified SchemeKnit auth redesign` |
| *(report)* | `docs: add Hero V2 + auth redesign report` |

Base: `9118be1` (Postgres migration fix report). Both target `origin/main`.

---

## Constraints checklist

| Constraint | Status |
|---|---|
| No backend / parser / quota / entitlement / AI / DB / lesson structure change | **PASS** |
| No Platform Admin public CTA; direct route works; UI hiding ≠ security | **PASS** |
| No Three.js/WebGL; Canvas 2D preferred | **PASS** |
| Reduced motion → static mesh, text/CTAs visible | **PASS** |
| Mobile/coarse pointer → no pointer deformation, ambient only | **PASS** |
| Headline + CurriculumPipeline preserved | **PASS** |
| Signup API contract preserved | **PASS** |
| Forgot password → no invented API; `/contact` helper only | **PASS** |
| `npx tsc --noEmit` + `npm run build` green | **PASS** |
| Browser matrix 390–1440 + reduced motion | **PASS 133/133** |
