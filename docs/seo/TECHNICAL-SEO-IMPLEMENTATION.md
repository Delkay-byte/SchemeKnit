# Technical SEO Implementation Plan

Date: 2026-10-31  
Status: **Not implemented in this task**  
Reason: staging infrastructure unavailable; no staging validation possible.

## Planned changes

### 1. Central site URL

Add:

```env
NEXT_PUBLIC_SITE_URL=https://<approved-origin>
```

Use it only through a small helper (`src/lib/site-url.ts`) for metadata,
canonical URLs, sitemap and JSON-LD. Do not hard-code a future domain.

### 2. Root metadata

Update `frontend/src/app/layout.tsx`:

- clean the mojibake title,
- set `metadataBase`,
- add factual Open Graph/Twitter defaults,
- keep the title template,
- add robots default `index, follow` (production) and staging override.

### 3. Public page metadata

Add page-specific `export const metadata` or `generateMetadata` to:

- `/` — Ghana lesson plan generator / Scheme of Learning
- `/about`
- `/features`
- `/how-it-works`
- `/pricing`
- `/help`

Each needs:

- unique title,
- meaningful description,
- one H1,
- self-canonical,
- Open Graph title/description/image,
- descriptive internal links.

Existing metadata pages must be checked for uniqueness and canonical URLs.

### 4. Private-page noindex

Add `robots: { index: false, follow: false }` to:

- auth routes,
- setup routes,
- app routes,
- admin routes,
- payment routes,
- activation routes.

This is defense in depth. Authentication/authorization remains the real access
control.

### 5. robots.ts

Allow public pages; disallow:

- `/api/`,
- `/(app)` routes,
- `/(platform-admin)`,
- `/(school-admin)`,
- `/login`, `/signup`, `/reset-password`, `/setup`,
- `/payments`, `/payments/callback`,
- `/activate`, `/activate-school`,
- `/admin`.

Reference `/sitemap.xml`.

### 6. sitemap.ts

Include only canonical, public, indexable URLs:

- `/`, `/about`, `/features`, `/how-it-works`, `/pricing`, `/contact`,
  `/help`, `/privacy-policy`, `/terms`, `/refunds-cancellation`,
  `/data-retention`, `/license-subscription`.

Use real last-modified values where available; otherwise omit them. Never
include authenticated, export, API, payment or admin routes.

### 7. Structured data

Add JSON-LD components:

- `Organization` — SchemeKnit name, URL, logo, contact.
- `WebSite` — site name, URL.
- `SoftwareApplication` — name, application category, operating system,
  factual description, current public price only if sourced from the catalogue.

Do not include ratings, reviews, awards or endorsements.

### 8. Staging noindex

Gate on an explicit staging flag or non-production site URL:

- HTML `robots: noindex, nofollow`,
- `X-Robots-Tag: noindex, nofollow` header for HTML,
- never index staging.

### 9. Validation

Automated checks:

- every public page has unique title/description/canonical,
- sitemap contains only public pages,
- robots excludes private routes,
- private pages emit noindex,
- JSON-LD parses and has required fields,
- no staging URL in production sitemap.

Manual/staging-only:

- rich results validation,
- Search Console verification,
- PageSpeed/Lighthouse,
- mobile layout and Core Web Vitals.

## Out of scope

- invented domain,
- fake reviews/ratings,
- doorway/thin keyword pages,
- claims of rankings or traffic.
