# AUTHENTICATION UI REMEDIATION V2 — ROLE-SPECIFIC DESIGN REPORT

**Project:** SchemeKnit (repo folder: `TeachFlow`)  
**Date:** 2026-09-24  
**Branch:** `main`  
**Remote:** `https://github.com/Delkay-byte/SchemeKnit.git`  
**Benchmark:** School Administration login (`/login/school-admin`) — not redesigned.  
**Scope:** Frontend design only. Backend generation, curriculum parser, quota, entitlements, AI providers, database, migrations, lesson template, authentication API contracts, and Platform Admin security/authorization are **unchanged**.

---

## A. Pages redesigned

| # | Page | Route | Concept |
|---|---|---|---|
| 1 | Teacher Login | `/login` | Teacher workspace / lesson planning |
| 2 | Teacher Registration | `/signup` | Onboarding progression |
| 3 | Platform Administration Login | `/login/platform-admin` | Secure platform operations |
| 4 | School Activation | `/activate-school` | Institutional setup / activation |
| 5 | Teacher License Activation | `/activate` | Personal entitlement / license unlock |
| 6 | Password Reset | `/reset-password` | Secure recovery |
| 7 | First-Run Setup | `/setup` | System initialization |
| 8 | Platform Admin Setup | `/setup/platform-admin` | Controlled administrative bootstrap |

School Administration login (`/login/school-admin`) was **not** redesigned (benchmark).

---

## B. Visual concept for each page

### Teacher Login — “Teacher’s workspace”
- Warm ivory foundation (`#F7F5F0`) + subtle notebook grid paper.
- 3D-tilted “Scheme of Learning” card stack (right) suggesting scheme → lesson → teaching.
- Left notebook tabs (Scheme / Lesson / Teach).
- Messaging: “Welcome back, teacher.” / “Pick up where your lesson planning left off.”
- Audience cards (School Teacher / Individual Teacher) retained.

### Teacher Registration — “Starting your workspace”
- Bright white/cyan aurora + step rail (Your details → Secure password → Ready).
- Floating curriculum chips (Upload scheme → Map indicators → Generate lesson) as a 3D stack.
- Soft workspace-ready paper card (bottom-left on xl).
- Distinct from Teacher Login: white vs ivory, horizontal pipeline metaphor vs workspace cards.

### Platform Administration Login — “Secure platform operations”
- Near-black ops surface (`#050E18`) + vertical grid + horizon scan line.
- 3D shield/lock control geometry; status ticks (ENCRYPTED / RESTRICTED / AUDITED).
- Split layout with restricted-operations aside (same pattern as School Admin benchmark, distinct copy/geometry).
- Supporting message: “SECURE ADMIN ACCESS — Authorized SchemeKnit platform staff only.”
- **Not** linked from public landing or public auth navigation; direct route works.

### School Activation — “School setup / activation”
- Cool slate (`#F3F6FA`) + architectural blueprint grid.
- Isometric building glyph (left on xl); right-edge step rail (Code → License → Admin → Live).
- Wide composition: header + prominent institutional activation-code field outside a generic form stack.
- Messaging: “Activate your school” / “Connect your school to SchemeKnit…”

### Teacher License Activation — “Unlock your teaching tools”
- Warm ivory (`#FAFAF7`) + soft topography lines.
- 3D-tilted license card (right): Teacher Pro, Status/Tier/Seats, Free → Pro progress.
- Amber entitlement banner: “PERSONAL ENTITLEMENT / Free Tier → activated plan.”
- Distinct from school activation: amber/personal vs cool/institutional.

### Password Reset — “Securely restore access”
- Cool ice (`#F4F7FA`) + concentric security rings with lock glyph (left).
- Recovery path rail (Token → Verify → New password) on the right.
- Minimal but intentional: no mesh, clear token + new password flow.
- Recovery behavior/API unchanged; `/contact` helper text path preserved where applicable.

### First-Run Setup — “System initialization”
- Violet-tinted neutral (`#F8F7FC`) + hex topology pattern.
- 3D “SYSTEM INIT” console panel (environment/database/checklist motif).
- Step rail: Admin details → School (optional) → Ready.
- Distinct from Platform Admin login: light technical init vs dark secure access.

### Platform Admin Setup — “Controlled administrative bootstrap”
- Same dark ops language as platform login but **bootstrap checklist** geometry (not shield).
- Status ticks: BOOTSTRAP / ONE-TIME / PROTECTED.
- Security note: one-time bootstrap secret from `PLATFORM_ADMIN_BOOTSTRAP_SECRET`.
- Success / already-complete states use dark grid surfaces with light BrandCapsule.
- All bootstrap security logic preserved (backend 410 after first admin).

---

## C. Logo treatment

- Canonical SVG geometry unchanged (`assets/brand/schemeknit-mark.svg`).
- **Light BrandCapsule** on every route: white/`#F4F7FA` surface, subtle border, cyan ring, padding, rounded corners.
- Wordmark shown on dark split asides and brand rows; navy S never sits directly on navy/black.
- Verified luminance > 200 on all 8 routes (desktop + 390) via acceptance.

---

## D–K. Per-page outcomes

| Page | Composition | Bg | Mesh | Logo |
|---|---|---|---|---|
| Teacher Login | Centered card + workspace decor | `#F7F5F0` | No | Light capsule |
| Signup | Centered card + step rail + chips | `#FFFFFF` | No | Light capsule |
| Platform Login | Dark split + ops decor | `#050E18` | No | Light capsule |
| School Activation | Wide header + code card + rails | `#F3F6FA` | No | Light capsule |
| Teacher License | Wide header + license card | `#FAFAF7` | No | Light capsule |
| Password Reset | Centered card + lock rings | `#F4F7FA` | No | Light capsule |
| First-Run Setup | Centered card + init console | `#F8F7FC` | No | Light capsule |
| Platform Setup | Dark bootstrap (decorOverride) | `#050E18` | No | Light capsule |

**8 unique backgrounds** confirmed by acceptance (`unique=8 of 8`).

---

## L. Accessibility

- Shared `AuthField` labels + `htmlFor`/`id`.
- Password fields: visibility toggle + `aria-label`/`toggleLabel`.
- Errors: `role="alert"` + `aria-invalid` on inputs.
- Keyboard focus verified (Tab → INPUT on teacher login).
- Loading states: spinner + disabled submit on every form.
- Reduced motion: decorative transforms are static (no rAF loops on auth).

---

## M. Responsive testing

| Viewport | Result |
|---|---|
| 390 | No horizontal overflow on all 8 routes; logo present; no mesh |
| 430 / 768 / 1024 / 1440 | Covered by prior Hero V3 matrix + this run at 390 + 1440 |
| Decor | Side rails / 3D cards `hidden` below `lg`/`xl` as appropriate |

---

## N. Browser acceptance

**Script:** `frontend/e2e/auth-role-design-acceptance.js`  
**Result:** **89 pass / 0 fail** against `next start` `:3003`.

Verified per route: title/h1, distinct bg, no mesh, light logo capsule, no overflow, form + CTA visible.  
Matrix: 8 unique bgs; teacher ≠ signup; school activation ≠ teacher license; platform setup state distinct; password reset context; keyboard focus; error state; mobile 390; landing mesh only; no public platform-admin CTA.

Screenshots under `frontend/e2e/auth-role-design-acceptance/` (not committed).

---

## O. Build / typecheck

| Gate | Result |
|---|---|
| `npx tsc --noEmit` | **exit 0** |
| `npm run build` | **exit 0** · 35/35 static pages |
| Acceptance | **89/89** |

---

## P. Remaining limitations

- Platform Admin Setup “already complete” / success screens show the closed state when bootstrap is not required (backend fail-closed); the full bootstrap form is only reachable while zero platform admins exist.
- Password reset still depends on out-of-band tokens (admin/CLI); no self-service email flow invented.
- 3D effects are CSS perspective/transform (no WebGL), consistent with technical rules.
- Decorative side panels hide below `lg`/`xl` to protect mobile composition.
- Screenshots and `tsbuildinfo` intentionally uncommitted.

---

## Constraints checklist

| Constraint | Status |
|---|---|
| Do not redesign School Admin login | **PASS** |
| Each page unique composition (not repeated left-decor + white card) | **PASS** |
| No mesh outside landing | **PASS** |
| Light logo capsule, S never lost on dark | **PASS** |
| No public Platform Admin CTA; direct route works | **PASS** |
| Auth/API/entitlement/security logic unchanged | **PASS** |
| Shared design system, not shared generic layout | **PASS** |
| 390–1440 no overflow | **PASS** |
| `tsc` + `build` + browser acceptance | **PASS 89/89** |
