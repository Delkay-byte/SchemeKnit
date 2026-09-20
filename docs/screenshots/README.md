# Screenshots

Product screenshots for the SchemeKnit GitHub repository.

## Captured screenshots

| File | Description | Viewport | Captured from |
|------|-------------|----------|---------------|
| `01-landing.png` | Public landing page with SchemeKnit wordmark, hero text, and the two public role cards (Teacher, School Administration). **Platform Admin is deliberately NOT shown.** | 1440x900 | Local production build (2026-09-20) |
| `02-login.png` | Teacher login page with email/password fields and role descriptions | 1440x900 | Live preview |
| `03-scheme-upload.png` | Scheme upload interface — accepts Word (.docx) **and PDF**, drag-and-drop, workflow steps | 1440x900 | Local production build (2026-09-20) |
| `04-allocation.png` | Generate Lesson Plans page — allocation preview grouped by **actual teaching week**, with `Scheduled` / `Carried forward from Week N` / `Needs review` statuses | 1440x900 | Local production build (2026-09-20) |
| `05-lesson-plan.png` | Generated lesson plan detail — curriculum context, editable topic/introduction/assessment, AI assist | 1440x900 | Local production build (2026-09-20) |
| `06-export.png` | Export sidebar — Download DOCX, PDF, Register (XLSX), Export ZIP, plus lesson plan detail fields | 1440x900 | Local production build (2026-09-20) |
| `07-dashboard.png` | Authenticated teacher dashboard — brand mark in the header, **Free Tier** plan label, lifetime AI generations remaining | 1440x900 | Local production build (2026-09-20) |
| `08-school-admin.png` | School Admin / Headteacher dashboard — canonical brand mark in the header, teacher management overview | 1440x900 | Local production build (2026-09-20) |
| `09-platform-admin.png` | Platform Admin console — canonical brand mark, schools/licenses overview. Reached only through the direct `/login/platform-admin` route (never linked publicly) | 1440x900 | Local production build (2026-09-20) |
| `10-multi-subject-detect.png` | Multi-subject document detection — a single "Basic 7 Scheme of Learning" containing English, Mathematics and Science; the teacher must confirm which subject section to use | 1440x900 | Local production build (2026-09-20) |
| `11-multi-subject-generated.png` | Subject-specific review after confirming **Science** — only the confirmed subject section is extracted for review | 1440x900 | Local production build (2026-09-20) |

## Capture details

- **Date**: 2026-09-20 (01, 03, 04, 05, 06, 07, 08, 09, 10, 11); 02 predates this change set
- **Viewport**: 1440x900, device scale factor 1
- **Browser**: Chromium (Playwright 1.49.1, headless)
- **Demo data**: Basic 9 Science scheme, 15 instructional weeks, generated lesson plans
- **Demo account**: an individual teacher account (Free Tier) on a local instance

## What changed in this capture pass

- The landing page no longer shows a Platform Admin card, link or footer entry.
  Platform Admin still works through its secure direct route
  `/login/platform-admin` (and `/setup/platform-admin`), verified separately.
- Every authenticated dashboard (teacher, school admin, platform admin) renders
  the same canonical SchemeKnit SVG mark in its header — the previous raster
  path (`/icons/icon-32.png`) did not exist in the build and rendered broken.
- The allocation preview is grouped by actual teaching week and shows
  carry-forward plainly.
- The header exposes a compact WhatsApp + email contact action on every page.
- Screenshots 08–11 add the school-admin and platform-admin dashboards (both
  rendering the fixed branding) and the multi-subject detection → confirmation
  → subject-specific review flow.

## Usage in README

Screenshots are referenced in README.md under the "Product preview" section using relative paths:

```markdown
![SchemeKnit landing page](docs/screenshots/01-landing.png)
```

## Existing brand assets

- Social preview: `frontend/public/icons/social-preview.png` (1200x630)
- OG image: `frontend/public/icons/og-image.png` (1200x630)
- Wordmark: `assets/brand/schemeknit-wordmark.svg`
- Mark: `assets/brand/schemeknit-mark.svg`
