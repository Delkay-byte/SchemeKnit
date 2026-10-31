# SEO Audit

Date: 2026-10-31  
Framework: Next.js App Router  
Status: **baseline audit only — technical implementation not applied in this task**

Reason: staging infrastructure is unavailable. SEO changes were not deployed or
validated against a staging origin. No ranking, indexing, traffic or Core Web
Vitals improvement is claimed.

## Public route inventory

| Route | Type | Current indexability | Metadata state |
|---|---|---|---|
| `/` | Public marketing | Indexable candidate | Root metadata only; no page-specific title/description/canonical/OG |
| `/about` | Public | Indexable candidate | No page metadata |
| `/features` | Public | Indexable candidate | No page metadata |
| `/how-it-works` | Public | Indexable candidate | No page metadata |
| `/pricing` | Public | Indexable candidate | No page metadata |
| `/contact` | Public | Indexable candidate | Has page metadata |
| `/help` | Public | Indexable candidate | No page metadata |
| `/privacy-policy` | Public legal | Indexable candidate | Has page metadata |
| `/terms` | Public legal | Indexable candidate | Has page metadata |
| `/refunds-cancellation` | Public legal | Indexable candidate | Has page metadata |
| `/data-retention` | Public legal | Indexable candidate | Has page metadata |
| `/license-subscription` | Public | Indexable candidate | Has page metadata |
| `/login`, `/login/*`, `/signup`, `/reset-password` | Auth | Should be noindex | No explicit robots |
| `/setup`, `/setup/*` | Setup | Should be noindex | No explicit robots |
| `/(app)/*` | Authenticated app | Private | Client-side auth; no explicit noindex |
| `/(platform-admin)/*` | Admin | Private | No explicit noindex |
| `/(school-admin)/*` | Admin | Private | No explicit noindex |
| `/admin` | Admin | Private | No explicit noindex |
| `/activate`, `/activate-school` | Activation | Should be noindex | No explicit robots |
| `/payments`, `/payments/callback` | Payment flow | Should be noindex | No explicit robots |

## Technical findings

| Issue | Impact | Evidence | Fix | Priority |
|---|---|---|---|---|
| No `robots.txt` route | High | No `src/app/robots.ts` or static file | Add `robots.ts` allowing public pages and disallowing private/auth/API/payment paths, with sitemap reference | 1 |
| No XML sitemap | High | No `sitemap.ts` or static sitemap | Add canonical public URLs only | 1 |
| No canonical tags | High | Root layout has no `metadataBase`/`alternates.canonical` | Add centralized `NEXT_PUBLIC_SITE_URL` and self-canonical per public page | 1 |
| Missing page metadata | High | Only 6 public pages export metadata | Add unique title, description, H1, canonical, OG per public page | 1 |
| No Open Graph/Twitter metadata | Medium | No `openGraph` or `twitter` fields | Add factual OG image/title/description | 2 |
| No structured data | Medium | No JSON-LD components | Add Organization, WebSite, SoftwareApplication; no invented ratings | 2 |
| No staging noindex | High | No environment-gated robots metadata/header | Add staging-only `X-Robots-Tag: noindex` and meta robots | 1 |
| Root title contains mojibake | Medium | `src/app/layout.tsx`: `SchemeKnit �?" Lesson Plan Generator` | Replace with clean `SchemeKnit | Lesson Plan Generator` | 1 |
| No `metadataBase` | Medium | Root metadata lacks it | Set from centralized site URL | 2 |
| Private pages not explicitly noindex | High | App/admin routes have no robots directive | Add noindex to private layouts/pages; authentication remains the actual control | 1 |
| Internal linking not audited at scale | Medium | No crawl export | Add descriptive links among public pages | 3 |
| Image alt text not fully audited | Medium | No image inventory | Audit public images and add meaningful alt | 2 |
| Performance not measured | Medium | No PageSpeed/Search Console evidence | Run staging Lighthouse/PageSpeed after domain | 3 |

## Domain policy

The permanent custom domain is not purchased. Do not invent one. Use a single
centralized configuration:

```env
NEXT_PUBLIC_SITE_URL=https://current-approved-origin
```

Every canonical, sitemap, robots sitemap reference and structured-data URL must
derive from it. Transition to the permanent domain later with one configuration
change and a 301 plan.

## Staging indexing policy

- Staging must send `X-Robots-Tag: noindex, nofollow` for HTML responses and
  `noindex` metadata.
- Do not rely on `robots.txt` as access control.
- Private content must remain authentication/authorization protected.
- Staging must never be used as the canonical production origin.

## What is not claimed

- No search ranking, impression, click or traffic improvement.
- No Google Search Console verification.
- No indexing outcome.
- No Core Web Vitals measurement.
- No schema validation against a live staging/production page.

## Required next step

Implement the technical foundation locally, then validate it on an isolated
staging origin before production. The implementation plan is in
`docs/seo/TECHNICAL-SEO-IMPLEMENTATION.md`.
