# Authorization Matrix

Date: 2026-10-31  
Scope: release candidate `4f15111` + local hardening branch

This is a route-family authorization inventory. It is not a claim that every
individual handler was manually exercised. Representative tests are named.

| Route family | Examples | Access rule | Cross-user protection | Test evidence |
|---|---|---|---|---|
| `/api/auth/*` | register, login, logout, change-password, reset | Public for login/register/reset; authenticated for profile/logout/change | Own account only; admin reset restricted to same school | `test_auth_lifecycle.py`, `test_auth_entry_boundary.py`, `test_logout_revocation.py` |
| `/api/auth/mfa/*` | setup, verify-setup, disable | Platform admin only | Own account only | `test_mfa.py` |
| `/api/documents/*` | upload, list, delete, weeks | Teacher workflow required | Scheme lookup by owner; `_resolve_scheme_or_raise` returns 403 for another owner | `test_authorization_idor.py`, upload tests |
| `/api/curriculum/*` | spine, coverage | Authenticated owner | Owner-scoped scheme lookup | `test_curriculum_spine_and_provenance.py` |
| `/api/generation/*` | preview, generate, resume, status, lessons, exports | Teacher workflow / authenticated owner | Job/lesson owner checks; export ownership tests | `test_generation_workflow_regression.py`, `test_export_download.py` |
| `/api/templates/*` | list, upload, analyze, delete | Authenticated; custom template limits | Owner-scoped templates | `test_custom_templates.py` |
| `/api/weekly-plans/*` | create, list, get, export | Teacher workflow | Owner-scoped plans | `test_weekly_coverage_semantics.py` |
| `/api/settings/*` | profile, preferences, AI status | Authenticated | Own settings only | settings tests |
| `/api/ai/regenerate-section` | section rewrite | Authenticated owner | Lesson owner check | `test_ai_rewrite_wiring.py` |
| `/api/payments/*` | plans, initiate, history | Authenticated; payment disabled | Own payment references | `test_payment.py` |
| `/api/paystack/*` | checkout, verify, webhook | Public webhook with HMAC; authenticated checkout | Paystack signature/idempotency | `test_prepaid_payments.py`, `test_paystack_subscriptions.py` |
| `/api/platform-admin/*` | licenses, users, plans, audit | `require_platform_admin` | Platform scope | `test_public_entry_roles.py`, platform admin tests |
| `/api/school-admin/*` | teachers, license, settings | `require_admin` + same-school checks | `_require_same_school` | `test_school_admin.py`, `test_school_isolation.py` |

## Verified isolation rules

- Lesson reads/edits/exports are owner-scoped through `data_service.get_lesson_plan`.
- Scheme reads/deletes are owner-scoped through `data_service.get_scheme`.
- School admins can only manage users in their own school.
- Platform admins cannot use the teacher workflow where the route requires it.
- Frontend hiding is never treated as authorization; backend dependencies enforce.

## Remaining gaps

- No single automated test enumerates every handler and asserts an access rule.
- Property-level authorization (e.g. which fields a role may edit) is not fully
  matrixed.
- Add a route-inventory test and per-route negative tests before production.
