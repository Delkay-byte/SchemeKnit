# Dependency Remediation Report

Date: 2026-10-31  
Status: **HIGH/CRITICAL FINDINGS RESOLVED LOCALLY**

## Frontend

| Package | Before | After | Reason |
|---|---:|---:|---|
| `next` | 14.2.35 | 16.4.3 | Critical Next.js advisory required a major patched release |
| `eslint` | 8.57 | 9.39.5 | Required by `eslint-config-next@16` |
| `eslint-config-next` | 14.2.35 | 16.4.3 | Matches Next major |
| `@types/*`, `typescript` | dependencies | devDependencies | Reduces production install surface |

Result:

- `npm audit --omit=dev`: **0 critical, 0 high, 0 moderate, 0 total**.
- Full `npm audit`: **16 moderate**, all ESLint/TypeScript lint tooling in `devDependencies`; no production runtime path.
- `npx tsc --noEmit`: passed after Next 16 migration.
- `npm run build`: passed. Route table still emits metadata, robots, sitemap and Proxy/Middleware.

Compatibility changes required by Next 16:

- `RefObject<T | null>` types in `landing-hero`/`logo-particles`.
- `Banner` class-name conditional narrowed to `undefined`.
- Existing middleware continues to work (Next labels it Proxy/Middleware).

No `npm audit fix --force` was used for the final state; the Next upgrade was explicit.

## Backend

| Package | Before | After | Reason |
|---|---:|---:|---|
| `python-multipart` | 0.0.9 | 0.0.31 | Multiple PYSEC advisories |
| `python-dotenv` | 1.0.1 | 1.2.2 | PYSEC-2026-2270 |
| `python-jose` | 3.3.0 | removed | Vulnerable; only HS256 JWT use |
| `ecdsa` | 0.19.2 | removed | Transitive via python-jose; no fixed release |
| `PyJWT` | — | 2.15.1 | Replaces python-jose for HS256 JWT |
| `aiohttp` | 3.10.5 | 3.14.4 | Multiple PYSEC/CVE advisories |
| `requests` | 2.32.3 | 2.33.0 | PYSEC-2026-1872 / 2275 |
| `pytest` | 8.3.3 | 9.1.1 | PYSEC-2026-1845 |
| `pytest-asyncio` | 0.24.0 | 1.4.1 | Compatible with pytest 9 |
| `black` | 24.8.0 | 26.10.1 | PYSEC-2026-2120/2121, CVE-2026-114134 |

`pip-audit -r requirements.txt`: **0 vulnerabilities**.

JWT migration: `src/auth.py` now imports `jwt` / `InvalidTokenError` from PyJWT. HS256 encode/decode signature is unchanged. Existing auth/logout/revocation tests pass.

## Remaining moderate findings

Full frontend audit retains 16 moderate findings in ESLint/TypeScript tooling. They are development-only, not shipped in the Next production runtime, and are scheduled for tooling follow-up. No production dependency finding remains.

## Verification

- Backend full suite: pending final rerun after this report.
- Frontend typecheck/build: passed.
- Provider/auth/payment/parser regression tests: included in suite.
