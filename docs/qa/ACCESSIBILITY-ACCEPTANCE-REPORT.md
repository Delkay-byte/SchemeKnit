# Accessibility Acceptance Report

Date: 2026-11-03
Goal: WCAG 2.2 AA engineering acceptance. This is **not** a certification.

## 1. Tools

| Tool | Version | Use |
|---|---|---|
| axe-core | 4.14.0 | automated WCAG 2.0/2.1/2.2 A+AA rules |
| Playwright Chromium | bundled with `playwright` 1.49 | rendered screens, keyboard, reduced motion |

Commands:

```bash
cd frontend
npm run e2e:responsive-a11y   # 84 passed, 0 failed
npm run e2e:keyboard          # 5 passed, 0 failed
```

## 2. Automated axe results

Screens checked at 1280 px: dashboard, lesson editor, weekly-plan editor, new
weekly plan, scheme review, settings, school overview, teacher management,
school settings, licence management, and the lesson-configuration dialog.

Final result: **no critical or serious violations** on any checked screen.
Moderate/minor findings were reviewed where axe reported them.

### Findings fixed

1. **Colour contrast (`color-contrast`)**
   - muted text on `bg-slate-100` was 4.34:1 — darkened
     `--muted-foreground` from `215.4 16.3% 46.9%` to `215 20% 40%`.
   - brand text `#04769B` on tinted backgrounds was 4.27–4.48:1 — text uses
     were darkened to `#035f7c`.
   - destructive text `#ef4444` on white was 3.76:1 — light `--destructive`
     changed to `0 72% 42%`.
2. **`aria-valid-attr-value` on school-admin navigation**
   - Radix Tabs triggers emitted `aria-controls` for tab panels that do not
     exist. The navigation is now a semantic `<nav>` with links and
     `aria-current="page"`; no invalid ARIA references.

## 3. Keyboard and focus checks

| Check | Result |
|---|---|
| Lesson-config trigger opens with Enter | pass |
| Focus moves inside the dialog | pass |
| Tab stays contained in the dialog | pass |
| Escape closes the dialog | pass |
| Focus returns to the trigger | pass |
| Not-found page first Tab target is “Go to dashboard” | pass |
| Focus indicator visible on that link | pass |

Toast actions and conflict choices are buttons with visible focus rings; the
existing `focus-visible` styles were retained.

## 4. Semantics and announcements

- Skeleton wrappers use `role="status"`, `aria-busy="true"` and a screen-reader
  label; decorative blocks are `aria-hidden`.
- Error toasts use `role="alert"`; the toast region uses `aria-live`.
- Draft recovery/conflict banners use `role="status"`/`role="alert"` and
  `aria-live="polite"`.
- Form fields tested have associated labels (`htmlFor`/`id`) and error `role`.
- Icon-only admin controls have `title` and accessible names.
- Tables retain header cells and captions/region headings.

## 5. Reduced motion

With `prefers-reduced-motion: reduce`, skeleton animation resolves to
`animation-name: none`.

## 6. Outstanding exceptions / limitations

| Item | Impact | Status |
|---|---|---|
| Platform-admin console not exercised with an authenticated MFA-enrolled session | That screen has no automated axe run | Documented; MFA gate preserved |
| No real screen-reader (NVDA/JAWS/VoiceOver) walkthrough | Semantic review only | Environment limitation |
| No automated test for toast action keyboard activation | Manual/source review | Minor |
| Long-content stress not seeded for every screen | Possible wrapping edge cases | Reviewed in code |
| Contrast of dynamic status colours not exhaustively measured | Possible minor findings outside tested screens | Not a blocker |

**Recommendation:** acceptable for this release. No critical or serious automated
findings remain on the tested screens.
