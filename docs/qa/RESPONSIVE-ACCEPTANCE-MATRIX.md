# Responsive Acceptance Matrix

Date: 2026-11-03
Tool: Playwright Chromium, automated in `frontend/e2e/responsive-accessibility.js`
Result: **84 passed, 0 failed**

## 1. Method

Each screen was opened at every width with disposable teacher/admin fixtures.
The assertion was:

- document horizontal overflow ≤ viewport width + 1 px;
- page body has rendered content;
- primary dialogs/banners remain visible and contained.

Overflow was not hidden globally. No CSS `overflow-x: hidden` was added.

## 2. Screens × viewports

✓ = no horizontal overflow and content rendered.

| Screen | 320 | 360 | 390 | 768 | 1024 | 1280 | 1440 |
|---|---|---|---|---|---|---|---|
| Dashboard | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Lesson editor | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Existing weekly-plan editor | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| New weekly plan | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Scheme review | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Settings | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| School overview | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Teacher management | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| School settings | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Licence management | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

Additional checks:

- Lesson configuration modal opens and fits at 1280; modal body scrolls.
- Draft recovery banner at 320: visible, readable and contained.
- Reduced-motion context: skeleton `animation-name: none`.
- Tables keep their own scroll container; the document does not overflow.

## 3. Intentional layout differences

- Weekly plan and lesson tables use `min-w-[…]` inside an overflow container at
  narrow widths; rows scroll horizontally inside the card, not the page.
- The school-admin section navigation wraps instead of collapsing into a
  hamburger (existing product pattern).
- Draft/conflict banners stack their action buttons vertically at mobile widths.

## 4. Screenshots

Screenshots were not committed (large binaries). The automated assertions and
failure messages are the evidence. Re-run:

```bash
cd frontend
npm run e2e:responsive-a11y
```

## 5. Limitations

- Platform administration was not loaded with an authenticated platform-admin
  session (MFA gate); its public/login state was not counted as coverage.
- Long-content stress (very long teacher/school names) was reviewed in code,
  not exhaustively seeded in every table.
- Touch-target and mobile-keyboard ergonomics were reviewed from rendered
  layout, not measured per element.
