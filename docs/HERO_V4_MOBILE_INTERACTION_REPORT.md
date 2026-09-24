# HERO V4 — MOBILE TOUCH MESH + PERFECT HERO/SECTION EDGE

**Project:** SchemeKnit (repo folder: `TeachFlow`)  
**Date:** 2026-09-24  
**Branch:** `main`  
**Remote:** `https://github.com/Delkay-byte/SchemeKnit.git`  
**Scope:** Frontend landing page only — hero mesh interaction + hero/white boundary.  
**Out of scope (untouched):** authentication redesign, role-specific auth, lesson generation, curriculum parser, quota, AI providers, backend, database, migrations, lesson template.

---

## A. APMIX rendered-behavior study

**Method:** live HTML fetch of `https://apmix.ai/`, public CSS chunk inspection, public web search. **No proprietary JS source was extracted, decompiled, or reviewed.** Runtime behavior was not directly observable in this environment (no browser DevTools session against their site).

### OBSERVED FROM LIVE APMIX (public HTML/CSS/meta)

| Item | Observation |
|---|---|
| Stack | Next.js App Router + Turbopack; Tailwind-style utilities; Metryo analytics |
| 3D/anim libs in HTML | **None** — no three.js, GSAP, Framer Motion, p5, Pixi, matter.js, R3F references |
| Hero graphic | `<canvas class="block h-full w-full" role="img" aria-label="Decorative background: a mesh of points that bends around your cursor.">` |
| Wrapper | `pointer-events-none absolute inset-0` + `aria-hidden` + CSS `mask-image` linear fade |
| Second instance | Same canvas component reused in a lower CTA band with a radial mask |
| Reduced motion | CSS disables `animate-rise`/`animate-blink`/`animate-marquee`; no canvas-specific rule found in CSS |
| Public technical docs | **None found** (no awards write-up, blog, or repo documenting the interaction) |

### INFERRED (not confirmed from source or runtime)

| Question | Inference | Confidence |
|---|---|---|
| Graphic type | Canvas-rendered point mesh (2D or raw WebGL — cannot distinguish from static HTML) | High for canvas; medium for 2D-vs-WebGL |
| Pointer behavior | Spatial displacement field — “bends around cursor” implies radial push with falloff | Medium (label-based) |
| Wake / trailing | **Cannot determine** from static assets | Unverified |
| Settle after interaction | Spring-to-rest is the standard pattern; **unconfirmed** for APMIX | Unverified |
| Touch handling | Unknown — wrapper is `pointer-events-none`; nothing in HTML indicates touch support | Unknown |

**Explicit disclaimer:** No access to proprietary APMIX source code is claimed. Everything above is either directly observed from public HTML or clearly labeled as inference.

---

## B. What was directly observed

- APMIX uses a decorative full-bleed `<canvas>` behind hero copy, non-interactive to hit-testing (`pointer-events-none`), masked into the section.
- The site’s own aria-label states the design intent: *“a mesh of points that bends around your cursor.”*
- No large animation/3D framework is referenced in the page HTML.
- No public engineering write-up of the interaction exists.

---

## C. What was inferred

- The interaction is a **displacement/bulge field** around the pointer (not a click-ripple, not color-only).
- A spring/lerp return to a rest grid is the conventional way to achieve “bends around” phrasing — used as the model for SchemeKnit’s own mesh (which already had this in V3).
- Trailing wake and touch behavior could not be observed on APMIX; SchemeKnit’s wake/touch model below is an **independent implementation** inspired only by the spirit of fluid, physical pointer response — not copied from APMIX.

---

## D. Touch interaction model

Unified **Pointer Events** (`pointerdown` / `pointermove` / `pointerup` / `pointercancel` / `pointerleave`) drive the same Canvas 2D mesh simulation for mouse, pen, and touch. No separate touch engine; no WebGL; no Three.js; no animation framework.

| Phase | Behavior |
|---|---|
| **Touch down** | Strong but controlled local bulge at the touch point (`strength` jumps to ≥0.62); nearby nodes deform coherently; local elevation/brightness rises. Not a giant circular shockwave. |
| **Touch move** | Current position tracked; velocity estimated from frame-to-frame delta (clamped ±55); influence center **interpolated** (lerp 0.18/frame) so it never teleports; neighboring nodes follow through spring/cohesion. |
| **Touch hold (still)** | Slow pulsing/settling: gentle sine modulation on strength while velocity ≈ 0. |
| **Touch release** | `active=false`, `releaseFast=true` → strength decays at k=0.1/frame (~250–700ms to near-zero) while spring physics returns nodes to rest. Velocity bleeds off with strength for natural spring-back. No instant reset. |
| **pointercancel / leave / blur / visibility / orientation** | Full release; no stale coordinates remain. |

**Pressure/duration:** Browser force APIs are not used (not guaranteed). Duration + velocity + distance travelled create the press/drag feel.

**Velocity effects:** Slow movement → soft controlled deformation. Fast movement → slightly stronger target strength (clamped ≤1.12) and longer wake. All values clamped — high-speed flicks cannot explode the mesh.

---

## E. Finger movement / wake model

A short-lived **temporal trail** of the last ~9 smoothed pointer samples (`TRAIL_MAX=9`, `TRAIL_LIFE=480ms`) is recorded each frame while active.

On every physics pass, each live trail sample applies a weaker radial push (0.45× main push, radius 0.6× main radius) with quadratic age-based falloff to the **same node network**. The wake deforms existing nodes and connected lines — it is **not** a separate decorative ripple circle drawn on top.

Trail samples are pruned when older than `TRAIL_LIFE`. The interpolated main pointer + trail together produce a smooth elongated wake behind the finger that bends the surrounding network naturally.

---

## F. Spring / settling behavior

Unchanged core physics from V3 (preserved as required):

- Lens falloff (smoothstep + power shaping) for strong central core
- Neighbor membrane cohesion pass (coherent surface, not isolated dots)
- Velocity coupling (finger/cursor imparts momentum → lag/inertia)
- Elevation-driven line brightness/width boost
- Tangential shear for fabric elasticity
- Ambient rest offsets (subtle idle motion)
- Damping 0.86 desktop / **0.89 mobile** (softer on touch)

Release envelope: fast decay (k=0.1) after explicit touch release puts strength in the 250–700ms band; springs finish the settle. Hover-leave on desktop keeps the gentler V3 decay (k=0.055).

---

## G. Mobile scrolling behavior

- All pointer listeners are **`{ passive: true }`** — **never** `preventDefault`.
- Mesh wrapper remains `pointer-events-none` — hit-testing passes through to the page.
- Hero does **not** set `touch-action: none` — default `auto` allows native vertical panning.
- Result: touch hero → interact; swipe vertically → page scrolls normally (browser fires `pointercancel` when it takes over the gesture → mesh releases cleanly).
- Tested: slow vertical swipe, fast vertical swipe, horizontal movement, stationary touch, touch + release, touch while scrolling — page never traps the user.

---

## H. Hero/section boundary root cause

**Root cause:** `.hero::after` in `landing-hero.module.css` was a 72px absolutely-positioned gradient at the hero’s bottom edge:

```css
.hero::after {
  bottom: 0;
  height: 72px;
  background: linear-gradient(to bottom, transparent, #f4f7fa); /* white endpoint */
  z-index: 2; /* above .heroInner (z:1) and mesh (z:0) */
}
```

This painted a **white layer over the bottom 72px of the dark hero**, which read as the white section “bleeding upward.” The hero and `#how-it-works` were already plain sibling blocks in normal flow (no negative margins, no transforms, no z-index collision between sections) — the only offender was this decorative fade.

**Inspected and cleared:** hero `boundingClientRect`, hero height/min-height, hero `overflow:hidden`, mesh canvas rect (already `absolute inset-0`, clipped by hero), landing pipeline wrapper, next-section rect, section margins/padding, negative margins, transforms, absolute positioning, z-index, stacking contexts, pseudo-elements, bottom gradients, border radius, overflow clipping.

---

## I. Boundary fix

**Removed `.hero::after` entirely.** No replacement layer, no added padding, no z-index bump, no tinting of the white section.

The hero is now fully self-contained:
- Its dark background ends exactly at the hero box edge.
- Mesh canvas: `position:absolute; inset:0` inside hero, clipped by `overflow:hidden` — cannot extend beyond.
- Hero content and pipeline stay inside the hero.
- `#how-it-works` participates in normal document flow immediately after the hero.

Conceptual result:

```
┌─────────────────────┐
│        HERO         │
│        MESH         │
└─────────────────────┘
┌─────────────────────┐
│  NEXT WHITE SECTION │
└─────────────────────┘
```

Programmatically verified: `|heroRect.bottom − nextSectionRect.top| ≤ 1px`, `canvasRect.bottom ≤ heroRect.bottom + 1`, `canvasRect.top ≥ heroRect.top − 1` at **390 / 430 / 768 / 1024 / 1280 / 1440**.

---

## J. Desktop regression

Desktop behavior preserved at V3 quality:

- Hover-driven cursor bulge (mouse path unchanged: `pointermove` while inside hero).
- Network deformation, spring return, wake, elevation cues — all intact.
- Desktop mesh density unchanged (`baseSpacing 42`, `minCols 18`, `maxCols 42`, `influenceRadius 200`, `pushStrength 52`, `damping 0.86`).
- Reduced motion still static.
- No horizontal overflow.
- No visual seam (clean edge).
- Acceptance cursor-deformation test passes; `landing-desktop-cursor.png` reviewed.

The only desktop additions are harmless: `pointerdown` slightly boosts strength on click; velocity is now hard-clamped (safety, not a visual change at normal speeds).

---

## K. Reduced motion

With `prefers-reduced-motion: reduce`:

- `interactive = false` → no pointer/touch deformation path runs.
- Static mesh drawn once via `drawStatic()`; no `requestAnimationFrame` loop.
- Touch input produces **no** pixel change (verified in acceptance: `reduced-motion: touch does not deform mesh`).
- Hero copy, pipeline, and CTAs remain fully visible/static (V3 CSS rules retained).

---

## L. Browser acceptance

**Extended (not replaced)** `frontend/e2e/hero-v3-acceptance.js` — all prior V3 tests retained.

**Result: 115 pass / 0 fail** against `next start` `:3003`.

New V4 coverage:

| Area | Checks |
|---|---|
| Seam (desktop + each width) | `hero.bottom ≈ next.top` ≤1px; no overlap; canvas top/bottom inside hero |
| Mobile touch (iPhone 13, 390×844, `hasTouch`) | canvas present + painted; CDP `touchStart` → pixel change; `touchMove` → different signature; `touchEnd` → settling signature change; no horizontal overflow; vertical `scrollBy` works; mobile seam ≤1px |
| Reduced motion + touch | touch does not deform mesh |
| Screenshots | `mobile-rest`, `mobile-touch-down`, `mobile-touch-drag`, `mobile-settled`, `mobile-seam`, `seam-desktop`, `landing-desktop-cursor` |

Two stale title expectations from the auth redesign (`activate-teacher`, `setup`) were corrected to match current page titles — no product code changed for this.

Where automation cannot measure “physical feel,” evidence is canvas pixel signatures + boundingClientRect comparisons + CDP touch-event sequences + screenshots — not a bare DOM existence test.

---

## M. Screenshot review

| Screenshot | Verdict |
|---|---|
| `seam-desktop.png` | Hard edge: dark hero ends, white section begins — no bleed, no gap, no white layer on hero |
| `mobile-seam.png` | Same clean seam at 390 |
| `mobile-rest.png` | Resting mesh grid visible, no deformation |
| `mobile-touch-down.png` | Local nodes displaced around touch point; lines bend |
| `mobile-touch-drag.png` | Elongated deformation along drag path (wake) |
| `mobile-settled.png` | Network relaxing back toward rest |
| `landing-desktop-cursor.png` | Desktop cursor bulge + wake intact (V3 parity) |

---

## N. Performance

- Canvas 2D only; single `requestAnimationFrame` loop; no React re-renders per frame.
- Wake adds ≤9 trail samples × falloff check per node — O(nodes × 9), negligible.
- Velocity hard-clamped (±55); strength targets clamped (≤1.12).
- DPR capped at 2; grid density viewport-capped (`maxCols` 28 mobile / 42 desktop).
- `visibilitychange` pauses the loop when the tab is hidden; `orientationchange` rebuilds the grid and hard-releases the pointer.
- Passive listeners only — no scroll jank from the interaction layer.

---

## O. Files changed

| File | Change |
|---|---|
| `frontend/src/components/mesh-background.tsx` | V4 pointer model: touch press lifecycle, interpolated drag, velocity clamp, temporal wake trail, hold pulse, fast release decay, mobile physics variant, orientation/visibility hard-release |
| `frontend/src/components/landing/landing-hero.module.css` | **Removed `.hero::after`** white bottom fade (seam root cause) |
| `frontend/e2e/hero-v3-acceptance.js` | Extended: seam metrics (6 viewports), mobile touch suite (CDP), reduced-motion touch, screenshots; corrected 2 stale auth title expectations |

---

## P. Commits

| Commit | Message |
|---|---|
| feat | `feat: refine mobile mesh interaction and hero section boundary` |
| docs | `docs: document mobile hero interaction refinement` |

Screenshots, `tsconfig.tsbuildinfo`, temp scripts, and `backend/.env` intentionally **not** committed.

---

## Q. Remaining limitations

- APMIX internal physics (exact spring constants, wake buffer, touch handling) remain **unknown** — no proprietary source was accessed; SchemeKnit’s model is an independent implementation inferred from observed design intent only.
- “Physical feel” (fluidity, weight) cannot be fully proven by pixel signatures alone; screenshots + event evidence are the practical ceiling for headless automation.
- Touch pressure APIs are intentionally unused (unreliable across browsers); duration + velocity + distance stand in.
- On hybrid devices (fine primary pointer), mobile physics tune activates only when `pointer: coarse` **or** width < 768; a narrow desktop window gets the mobile density variant — intentional and visually acceptable.
- `pointercancel` on scroll-gesture takeover ends interaction immediately (desired); the mesh settles while the page scrolls — deformation during the brief pre-cancel move is by design.
- Real-device Safari/Chrome手感 (480ms trail life, 0.1 release decay) is tuned to the stated 250–700ms band but may benefit from minor on-device tuning later.

---

## Constraints checklist

| Constraint | Status |
|---|---|
| No backend / auth / parser / quota / AI / DB changes | **PASS** |
| Canvas 2D only — no WebGL, no Three.js, no anim framework | **PASS** |
| Pointer Events for mouse + pen + touch, same simulation | **PASS** |
| Touch start → controlled bulge (not giant shockwave) | **PASS** |
| Touch move → interpolated follow + velocity wake, no teleport | **PASS** |
| Touch release → 250–700ms decay + spring settle | **PASS** |
| Passive listeners; natural vertical scroll; no preventDefault | **PASS** |
| Lifecycle: down/move/up/cancel/leave + visibility/resize/orientation | **PASS** |
| Mobile tune: lower density, larger radius, stronger push, softer damping | **PASS** |
| Wake deforms the network (not a decorative overlay) | **PASS** |
| Hero ends exactly where white section begins (≤1px, 6 widths) | **PASS** |
| No negative-margin / z-index hacks; layout relationship fixed at source | **PASS** |
| White section stays white | **PASS** |
| Desktop not degraded (V3 parity) | **PASS** |
| Reduced motion → static mesh, no touch deformation | **PASS** |
| Mesh exclusive to landing page | **PASS** |
| Acceptance: all V3 tests retained + V4 tests → **115/0** | **PASS** |
| tsc + build green (35/35) | **PASS** |
