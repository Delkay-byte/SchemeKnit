# SchemeKnit — Staging Acceptance and Security Release Report

**Date:** 2026-11-17  
**Release merge on `main`:** `3f6875f68d1062b8f4ca713a0050dc9cb435cc40` (PR #12)  
**Final `main` tip:** this report commit (parent `3f6875f`)
**Production frontend:** `schemeknit-frontend` at `3f6875f`, live  
**Production API:** `schemeknit-api` at `5a88a35`, live  
**Public application:** `https://schemeknit.bloomcoretech.com/`

## Status

**BLOCKED** — staging acceptance passed, the security release is merged and
autodeployed, and production is healthy. Two owner-only checks remain: the
production Super Admin sign-in must be completed with the owner's authenticator
or recovery code, and the production internal test account has not been
provisioned.

The production platform-admin account itself is healthy:

- email `bloomcoretechnologies@gmail.com`
- role `platform_admin`
- active, `is_admin = true`
- `mfa_enabled = true`
- bcrypt hash present (`$2b$12$`, length 60)
- no account-level lockout table rows

The generic `Invalid email or password` response is also the response for a
missing/invalid MFA code. The account state therefore points to the MFA gate (or
using the teacher entry page), not a missing account or a wrong role.

## 1. Pull requests and main

| PR | Merge commit | Scope |
| --- | --- | --- |
| #13 | `85ffc1c` | CI restore: DB server default for `is_internal_test_account`; no-auto-generation source contracts |
| #15 | `d60a94f` | npm remediation: xmldom 0.8.15, fflate 0.8.3, typescript-eslint 8.73.0 / minimatch 11.0.9, build tools to devDependencies |
| #14 | `4e29616` | Rubric language fix and reference de-duplication |
| #16 | `5a88a35` | Citation normalizer: keep internal commas, then de-duplicate |
| #12 | `3f6875f` | Next.js 16.4.6 and full advisory report |

Functional authentication, rubric, DOCX and internal-account changes were
already on `main` from the earlier release (`cf19932`).

## 2. Next.js and dependency audit

- `next`: `16.4.3` → `16.4.6` (latest stable 16.x, verified on npm)
- `eslint-config-next`: `16.4.6`
- React / React DOM: `18.2.0` (unchanged, compatible)
- Lockfile consistent; `npm ci` clean

### Before

At task start `npm audit` reported 9 findings: `@xmldom/xmldom` (High),
`fflate` (Moderate), `minimatch` (Moderate), and the `typescript-eslint` chain
(Moderate).

### After

- `npm audit --omit=dev --audit-level=high` → **0 vulnerabilities**
- Full `npm audit` → 1 advisory only: `picomatch` GHSA-fc5q-39xc-vjpf /
  CVE-2026-112366, affected `<= 4.0.7`, **no published fix**
- `next` has no advisory
- No audit check or CI rule was suppressed

### Picomatch advisory decision (owner-approved conditional mitigation)

The owner approved a conditional mitigation after the checks below.

1. `npm ls --omit=dev picomatch` → empty. The package is absent from the
   effective production dependency graph.
2. `npm audit --omit=dev` → 0 findings.
3. No SchemeKnit API, route, upload, setting or public input accepts a glob
   pattern. The word `picomatch` is not imported by application code.
4. ESLint/Tailwind integrations use repository-controlled configuration.
5. The vulnerable `analyzeRepeatedExtglob` implementation is not present in the
   compiled `.next` output.
6. Render builds install developer dependencies for `next build`, but production
   runtime does not execute glob matching against customer data.

Recorded risk: **High severity — temporarily mitigated, not fixed.** Upgrade to
the first patched release when published.

### Upstream PR #237 assessment

`micromatch/picomatch` PR #237 (head `1bf0d045…`, fork `seeibt/picomatch`)
proposes collapsing `+(P)` to `(?:P)` and `*(P)` to `(?:P)?` for a single branch
containing a top-level `*`, with ReDoS timing tests. The diff is small and
targeted, but the PR is open and unmerged, has no maintainer review or release,
and pinning a personal fork would add an unreviewed supply-chain dependency. It
was evaluated and **not adopted**.

## 3. Staging environment used

No new service was created. Existing services:

| Service | Render ID | Branch tracked | Live commit |
| --- | --- | --- | --- |
| Staging frontend | `srv-dbl5ors9v7es73caicpg` | `feature/upload-zeli-config-payments` | `5a88a35` |
| Staging API | `srv-dbl5ore7bikc73f2stvg` | `feature/upload-zeli-config-payments` | `5a88a35` |

- Staging API origin: `https://schemeknit-staging-api.onrender.com`
- Staging DB: Neon `schemeknit_staging` (database `schemeknit_staging`)
- Production DB: Neon `neondb` (database `neondb`)
- The staging frontend env sets `NEXT_PUBLIC_API_URL` to the staging API. The two
  databases are different databases on the same Neon project, not the same
  database.

Both staging services had `autoDeploy = no`; the candidate commit was deployed
through the existing Render deploy API to each existing service. Migration
`v055_internal_test_account` applied automatically on the staging API boot.

## 4. Authentication results

Verified on staging with dedicated staging-only accounts (credentials never
printed and not stored in the repository):

| Check | Result |
| --- | --- |
| Super Admin (platform_admin) login | PASS |
| MFA enrollment (TOTP) | PASS |
| Login with TOTP code | PASS |
| Login with recovery code | PASS |
| Platform console renders | PASS |
| Refresh keeps session | PASS |
| Protected navigation keeps role | PASS |
| Logout enforced | PASS |
| Teacher login | PASS |
| Teacher refresh keeps session | PASS |
| Invalid credentials | 401, truthful credential error, no false session-expiry, no session |
| Wrong entry page | 401 (generic; role boundary intact) |
| Production account state | active `platform_admin`, MFA enabled, bcrypt hash valid shape |

Production Super Admin sign-in was **not executed** because the owner's password,
authenticator and recovery codes are owner-only. The owner must sign in at
`https://schemeknit.bloomcoretech.com/login/platform-admin/` with
`bloomcoretechnologies@gmail.com` and a current authenticator code (or an unused
recovery code). If both are unavailable, a controlled MFA reset is required; no
reset or role change was performed.

## 5. Internal test account

- Staging: exactly one normal teacher account with
  `is_internal_test_account = true`.
- Staging quota response: `plan_name = Internal test account`,
  `unlimited = true`, `internal_test_account = true`,
  `plan_source = internal_test_account`.
- Staging AI entitlement: unlimited (`ai_quota_unlimited = true`).
- A second staging teacher stays on the Free plan (`limit = 2`, enforced).
- Staging teachers are not platform administrators.
- Production: migration `v055` applied, `is_internal_test_account` present,
  **0 internal accounts**. Provisioning is the owner action in §10.

## 6. Rubric and DOCX acceptance (staging)

A Basic 7 Religious and Moral Education scheme was uploaded through the staging
API and a lesson generated with the internal test account.

- Configuration saved before generation; no automatic generation occurred.
- Standard generation: PASS.
- Zeli generation: PASS.
- Generated lesson carries a real criteria × levels rubric matrix.
- DOCX REFERENCE and PERIOD populated from saved configuration.
- Citation `RME Curriculum, p. 12` appears exactly once after the §1 fix.
- Rubric task reads "The learner's work for the lesson task on the nature of
  God"; no "explain work" wording.
- No "demonstrates discuss" or spliced "in Frame the task" remediation text.
- DOCX opens with python-docx; header/table structure intact; rubric table has
  five columns and four descriptor rows.
- Every page was inspected through the extracted page/table dump; no empty
  generated page or malformed repeated sentence was found in the generated
  lesson.

Limitation: no interactive Microsoft Word GUI is available in this environment;
the DOCX was validated as a valid OOXML package and rendered text/table
structure, not by opening Word visually.

## 7. Production deployment

- Merge `3f6875f` triggered the existing Render autodeploy for
  `schemeknit-frontend` (`trigger=new_commit`).
- `schemeknit-frontend` deployed `3f6875f` and reached `live` at
  `2026-11-17T19:44:51Z`.
- `schemeknit-api` was already live on `5a88a35` from the PR #16 merge; no
  backend code differs after the docs-only PR #12.
- No manual deployment, no new Render service, no DNS/domain change.

## 8. Production verification

| Check | Result |
| --- | --- |
| `https://schemeknit.bloomcoretech.com/` | HTTP 200 |
| `/login/` | HTTP 200 |
| `/login/platform-admin/` | HTTP 200 |
| Static assets | Loaded (application renders) |
| `/api/health` | `healthy`, version `1.0.5` |
| `/api/ready` | `ready: true`, database/storage/email reachable |
| Invalid credentials | 401 |
| Console/runtime errors | None on public pages; only the expected 401 from the deliberate invalid-login probe |

## 9. Remaining limitations

- Production Super Admin password verification is fixed; the final browser MFA
  sign-in awaits the owner's authenticator/recovery code.
- Production internal test account is provisioned for one normal teacher.
- `picomatch` remains a High-severity **dev/build-only** advisory until upstream
  publishes a patched release.
- Interactive Word GUI inspection and authenticated production generation were
  not possible without owner credentials.

## 10. Owner actions

## 11. Production owner checks (2026-11-17, post-release)

### Environment identity (read-only)

| Item | Evidence |
| --- | --- |
| Repository `main` | `1a97a28406e7b0cba35da7c0cef17855c3e85907` |
| Production frontend | `schemeknit-frontend`, live `3f6875f` |
| Production API | `schemeknit-api`, live `5a88a35` (docs-only difference from `1a97a28`) |
| Production database | Neon database `neondb` |
| Staging database | Neon database `schemeknit_staging` |
| Separation | Different databases; staging frontend env points at `https://schemeknit-staging-api.onrender.com` |
| Provisioning script | Present on `main` and in the live backend image |
| Migration v055 | Present on `main`; applied in production |
| Entitlement implementation | Present in `src/entitlements.py` |

### Super Admin login — BLOCKED (password verification)

Recent production backend logs show:

```
event=login_failed reason=bad_credentials
POST /api/auth/login 401 Unauthorized
```

The account-key hashes map the attempts:

- `00040604…` = `bloomcoretechnologies@gmail.com` — three failed password checks
  at 19:56:45, 19:57:06 and 19:57:21 UTC.
- `38970480…` = `amegayiesaviour@gmail.com` — one failed check at 20:02:32 UTC.
  This account does not exist yet, so any password fails.

The account row is healthy: `bloomcoretechnologies@gmail.com`, role
`platform_admin`, active, `is_admin = true`, MFA enabled, valid bcrypt hash
shape, no lockout. Because the failure is `bad_credentials`, the password did
not verify; MFA was never reached. The app returns the same generic 401 for a
wrong password and for a wrong MFA code, so logs are the distinguishing
evidence.

Turnstile: login pages intentionally do **not** show the widget on first load.
The backend only requires it after repeated failures
(`LOGIN_TURNSTILE_AFTER_FAILURES`, default 3) and returns a machine code that
renders the widget. Registration (`/signup`) always shows Turnstile. A quiet
login page is expected behaviour, not a missing widget.

Owner authorised and a controlled password reset was completed against the
verified production database. The new hash verifies with the owner-provided
password, `password_changed_at` was bumped (existing JWTs invalidated), and a
subsequent login attempt reached the MFA gate:

```
event=mfa_failed
```

That proves password verification now succeeds; MFA is the only remaining gate.
No password, hash or secret was printed. MFA settings were not changed. The
owner must complete the sign-in in the browser with their existing authenticator
or an unused recovery code.

### Internal teacher test account — PROVISIONED

The dedicated account `amegayiesaviour@gmail.com` did not exist, so it was
created with the owner-approved name and password as a normal individual teacher
with the standard Free entitlement. The owner then authorised the existing
provisioning script, which was run against the verified production database:

```bash
python scripts/provision_internal_test_account.py \
  --email amegayiesaviour@gmail.com \
  --actor bloomcoretechnologies@gmail.com \
  --apply
```

Result: `OK: grant applied ... changed=1`.

Read-only verification:

- exactly one `is_internal_test_account = true` row
- email `amegayiesaviour@gmail.com`
- role remains `teacher`, account active, not an administrator
- quota: `unlimited = true`, `plan_name = Internal test account`
- AI: `ai_enabled = true`, `ai_quota_unlimited = true`
- other teachers remain on their existing plans: `saviour.amegayie.ds@gmail.com`
  and `sheilamawusi@gmail.com` keep `generation_limit = 2`; the existing paid
  teacher keeps their paid entitlement
- no second internal account exists

### Status

Overall remains **BLOCKED** only until the owner completes the browser
Super Admin sign-in with their existing authenticator/recovery code and
confirms it succeeded. Password verification and the internal entitlement are
complete.

