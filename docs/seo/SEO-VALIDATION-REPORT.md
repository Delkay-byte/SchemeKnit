# SEO Validation Report

Date: 2026-10-31  
Status: **Local technical validation passed; staging/production indexing not verified**

## Implemented

- Centralized `frontend/src/lib/site-url.ts` using `NEXT_PUBLIC_SITE_URL`.
- Clean homepage title: `SchemeKnit — Lesson Plan Generator for Ghanaian Teachers`.
- Root `metadataBase`, canonical, Open Graph and Twitter metadata.
- `pageMetadata()` helper for unique title/description/canonical/OG/Twitter.
- Metadata on public pages: about, features, how-it-works, help, pricing,
  contact, legal pages.
- `sitemap.ts` with only public canonical routes.
- `robots.ts` with private/auth/payment/API exclusions and sitemap reference.
- `middleware.ts` sets `X-Robots-Tag: noindex, nofollow` on private routes and
  on staging.
- Organization, WebSite and SoftwareApplication JSON-LD.
- Staging returns no sitemap and disallows all crawling.
- Public-facing “TeachFlow” references replaced with “SchemeKnit”.

## Validation performed locally

| Check | Result |
|---|---|
| `npx tsc --noEmit` | passed |
| `npm run build` | passed; `/robots.txt`, `/sitemap.xml`, middleware emitted |
| Homepage HTML title | `SchemeKnit - Lesson Plan Generator for Ghanaian Teachers` |
| Homepage canonical | present |
| Homepage Open Graph title | present |
| Homepage JSON-LD | present |
| Pricing page title | `Pricing and Lesson-Plan Credits | SchemeKnit` |
| Pricing canonical/OG | present |
| `robots.txt` | 200, disallows private paths, sitemap URL correct |
| `sitemap.xml` | 200, public URLs only |
| `/login` | 200 after redirect, `X-Robots-Tag: noindex, nofollow` |
| `/dashboard` | 200 after redirect, `X-Robots-Tag: noindex, nofollow` |
| Static SEO tests | `tests/test_seo_foundation.py` 6 passed |

## Not verified

- Search Console verification.
- Google indexing, ranking, impressions, clicks or traffic.
- Rich Results Test against staging/production.
- Staging noindex over the real staging host.
- Core Web Vitals / PageSpeed.
- Permanent domain (`schemeknit.com`) canonical behavior.

The current environment variable remains the verified Render frontend origin.
No future domain is hardcoded.

## Future domain

See `docs/seo/FUTURE-DOMAIN-MIGRATION.md`.
