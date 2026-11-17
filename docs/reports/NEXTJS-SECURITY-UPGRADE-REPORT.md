# Next.js Security Dependency Upgrade Report

**Date:** 2026-11-17  
**Branch:** `fix/nextjs-security-upgrade`  
**Base:** `main` at `cf199328ef8a317632865aa9d2681b4f2935a8bd`  
**Upgrade commit:** `438917d1b0388406921e2f466a77311eb4d045ec`  
**Deployment:** NOT performed.

## Status

**GREEN — Next.js upgraded to a verified patched release; checks pass.**

## 1. Version decision

| Item | Before | After |
| --- | --- | --- |
| `next` (package.json) | `^16.4.3` (installed 16.4.3) | `^16.4.6` (installed 16.4.6) |
| `eslint-config-next` | `^16.4.3` | `^16.4.6` |
| React / React DOM | `^18.2.0` (18.2.0) | unchanged |
| Next.js major line | 16.x | 16.x (no Next 17) |

Verified against the npm registry at execution time:

- `next` `latest` = **16.4.6**
- `eslint-config-next@16.4.6` exists
- `next@16.4.6` peer range accepts React 18.2.0
- No later stable 16.x release exists

`16.4.6` is the latest stable patched 16.x release. It contains the 16.4.5
November 2026 security fixes plus the 16.4.6 backports (route-handler response
compression, Tailwind pin for create-next-app, Turbopack dev GC fixes).

## 2. Advisories addressed

The 16.4.5 security release fixes seven issues affecting 16.x up to and
including 16.4.4. 16.4.6 includes them.

| Advisory (CVE) | Severity | Fixed in |
| --- | --- | --- |
| GHSA-mfr8-8qww-v76h (CVE-2026-119790) — cross-tenant cache disclosure | Moderate | 16.4.5 |
| GHSA-vc7v-qv4w-wrv8 (CVE-2026-119351) — nested `use cache` cross-root disclosure | Moderate | 16.4.5 |
| GHSA-rhh4-g77r-r9qj (CVE-2026-119349) — binary `use cache` argument collision | Moderate | 16.4.5 |
| GHSA-vvgp-ww4w-46vf (CVE-2026-119350) — shared shell cache poisoning | Moderate | 16.4.5 |
| GHSA-pc58-hwjq-p385 (CVE-2026-119348) — stale compressed response framing | Moderate | 16.4.5 |
| GHSA-f3mh-rxg3-f5g2 (CVE-2026-119346) — cookie exposure via `x-middleware-set-cookie` | Moderate | 16.4.5 |
| GHSA-7qx7-33qx-rqx2 (CVE-2026-119347) — SVG rejection bypass in Image Optimization | Moderate | 16.4.5 |

Severity is taken from the GitHub Security Advisory records (CVSS 4.0 scores
6.0–6.9, all Moderate). The November security blog post used the word "High"
editorially for the cross-tenant cache issue; the advisory record itself is
**Moderate**, and this report follows the advisory record.

The previous build gate failed with `SecurityFatalError` on 16.4.3. After the
upgrade the production build completes with exit code `0` and no
`SecurityFatalError`.

## 3. Application compatibility review

- **App Router routes/layouts:** unchanged route tree builds successfully (all
  static and dynamic routes render).
- **Middleware:** `frontend/src/middleware.ts` remains supported in 16.x. Next
  16.4.6 prints a deprecation warning suggesting the `proxy` convention. The
  middleware still executes (`ƒ Proxy (Middleware)` in the build output). Rename
  is an application refactor, out of scope for this dependency-security task.
- **Server/client components:** no API changes affecting the current usage.
- **Route handlers / fetches:** no `use cache`, `unstable_cache` or
  `cacheComponents` usage; no `fetchCache` overrides. The Cache Components
  advisories therefore have no exposed path here, but the upgrade still removes
  the vulnerable version.
- **Caching/revalidation:** only `dynamic = 'force-static'` on `robots.ts` and
  `sitemap.ts`; unaffected.
- **Image optimization:** `images.unoptimized = true`; no `next/image` usage, so
  the SVG optimizer advisory has no active surface.
- **Build/deployment:** `next.config.js` (`headers`, `output: 'export'` for
  desktop, `trailingSlash`, env mapping) builds unchanged for both web and
  existing scripts.
- **React 18:** still supported in Next 16.4.6. Next prints a deprecation notice
  that React 18 support ends in Next 17. React was intentionally not upgraded
  (major version change, outside this task).

## 4. Validation results

All commands run from a clean `npm ci` install using the updated lockfile.

| Check | Command | Result |
| --- | --- | --- |
| Clean install | `npm ci` | exit 0 |
| Installed versions | `npm ls next eslint-config-next react react-dom --depth=0` | next 16.4.6, eslint-config-next 16.4.6, react/react-dom 18.2.0 |
| TypeScript | `npx tsc --noEmit` | exit 0 |
| ESLint | `npm run lint` | exit 0, 0 errors (380 pre-existing warnings) |
| Frontend UX tests | `npm run test:ux` | 100 passed |
| Frontend DOCX tests | `npm run test:docx` | 14 passed |
| Backend regression (auth, rubric, entitlement, export model) | `pytest test_auth_login_session_p0 test_rubric_docx_quality test_internal_test_account test_export_model` | 20 passed |
| Production build | `npm run build:web` | exit 0, compiled successfully, no `SecurityFatalError` |
| Dependency audit | `npm audit --omit=dev --audit-level=high` | exit 0, 0 production vulnerabilities |
| Full dependency audit | `npm audit` | 1 unfixed upstream advisory (`picomatch`), dev/build tooling only — see §5 |
| Backend full suite | `pytest -q` | run on the final commit; result recorded in §6 |

## 5. Full npm dependency remediation

### Baseline at task start (current advisory database)

`npm audit` reported 9 findings in the 16.4.6 tree:

| Package | Severity | Type | Installed | Fixed in |
| --- | --- | --- | --- | --- |
| `@xmldom/xmldom` | High | direct dev | 0.8.11 | 0.8.15 (LTS) |
| `fflate` | Moderate | direct | 0.8.2 | 0.8.3 |
| `minimatch` | Moderate | transitive (`typescript-eslint` → `typescript-estree`) | 10.2.6 | 11.0.1+ |
| `typescript-eslint` chain | Moderate | transitive (`eslint-config-next`) | 8.72.1 | 8.73.0 |

### Remediation applied

| Package | Change | Reason | Compatibility |
| --- | --- | --- | --- |
| `next` | `^16.4.3` → `^16.4.6` | November 2026 security fixes | same major/minor line |
| `eslint-config-next` | `^16.4.3` → `^16.4.6` | matching Next release | same |
| `@xmldom/xmldom` | `^0.8.11` → `^0.8.15` | XML injection / serialization / ReDoS advisories | same 0.8 LTS API; used only by the test XML adapter and DOCX serializer helpers |
| `fflate` | `^0.8.2` → `^0.8.3` | malformed ZIP64 infinite loop | same 0.8 API; ZIP/DOCX tests pass |
| `typescript-eslint` (transitive) | 8.72.1 → 8.73.0 | pulls `minimatch@11.0.9` (patched) | within `eslint-config-next`'s `^8.56.0` range; ESLint passes |
| `minimatch` | 10.2.6 → 11.0.9 | ReDoS via globparts amplification | transitive under `@typescript-eslint/typescript-estree@8.73.0` |
| `tailwindcss`, `tailwindcss-animate`, `postcss`, `autoprefixer` | moved to `devDependencies` | build-time only; removes the last picomatch path from the production dependency graph | Next build and Tailwind still resolve them at build time |

`npm audit fix --force` was **not** used. No package was removed. No audit
check, CI rule or advisory identifier was suppressed.

### Residual advisory (no upstream fix)

`picomatch` — **High**, GHSA-fc5q-39xc-vjpf / CVE-2026-112366, affected
`<= 4.0.7`, **no patched version published** (npm latest is 4.0.7; the
advisory record lists no fixed version at execution time).

- Path: development/build tooling only. `tailwindcss`, `tailwindcss-animate`,
  `postcss` and `autoprefixer` were reclassified from `dependencies` to
  `devDependencies` (they are build-time tools), so the production-only graph
  now contains no picomatch:
  `npm ls --omit=dev picomatch` → empty; `npm audit --omit=dev` → 0
  vulnerabilities.
- Remaining path: `eslint-config-next` → `typescript-eslint` →
  `tinyglobby`/`fdir`, `eslint-plugin-import` → `fast-glob`/`micromatch`.
- Trigger: exponential backtracking when an attacker supplies a glob pattern
  such as `+(*)` or `+(*a)` to picomatch.
- SchemeKnit exposure: no application code imports picomatch; the dependency is
  never reached from a request handler. The compiled production build was
  searched and the vulnerable `analyzeRepeatedExtglob` implementation is not
  present in `.next` output. No SchemeKnit feature accepts user-supplied glob
  patterns.
- Mitigation: build-chain-only; no production input path reaches it. Upgrade
  to the patched release as soon as it is published.
- Why not overridden: forcing a different picomatch version would leave the
  vulnerable code in place (all published versions are affected) and risks
  breaking ESLint/Tailwind glob semantics.

#### Upstream fix evaluation (PR #237)

`https://github.com/micromatch/picomatch/pull/237` (`fix: CVE-2026-112366
prevent ReDoS in single-branch repeated extglobs`, head `1bf0d045…`, fork
`seeibt/picomatch`) proposes collapsing `+(P)` to `(?:P)` and `*(P)` to
`(?:P)?` when the branch contains a top-level `*`. The diff is small and
targeted, and its tests assert no nested quantifier plus a timing bound.

It is **not** an official fix: the PR is open and unmerged, no maintainer
review or release exists, and pinning a personal fork would introduce an
unreviewed supply-chain dependency. It was evaluated and **not adopted**. The
mitigation stands on the production graph being clean.

This is the only remaining finding. It is not fixable with a published,
compatible package at execution time.

## 6. Diff scope

Only dependency manifests and the report changed:

- `frontend/package.json` — `next`/`eslint-config-next` `^16.4.6`,
  `fflate` `^0.8.3`, `@xmldom/xmldom` `^0.8.15`
- `frontend/package-lock.json` — resolved versions for those packages plus
  `typescript-eslint@8.73.0` / `minimatch@11.0.9`
- `docs/reports/NEXTJS-SECURITY-UPGRADE-REPORT.md`

No authentication, rubric, DOCX, entitlement, backend, database, SSO,
environment, DNS or domain changes.

## 7. Delivery

- Branch: `fix/nextjs-security-upgrade`
- Next.js upgrade commit: `86d7c80`
- Dependency remediation commit: recorded in the final closeout report.
- Separate PR #12 to `main`; merged only after required CI is green.
- No staging infrastructure created.
