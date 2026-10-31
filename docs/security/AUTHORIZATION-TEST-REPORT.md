# Authorization Test Report

Date: 2026-10-31

## Inventory

- Sensitive route families: auth/MFA, documents, curriculum, generation, templates, weekly plans, settings, AI regeneration, platform admin, payments/Paystack, school admin.
- Automated inventory test: `backend/tests/test_authorization_route_inventory.py`.
- It asserts every non-public handler in the inventoried modules declares an authentication/role dependency.
- It separately asserts every non-public platform-admin handler requires `require_platform_admin`.

Result: both inventory tests pass.

## Existing negative coverage

- Cross-user lesson/scheme access: `test_authorization_idor.py`, `test_school_isolation.py`.
- Lesson and export ownership: `test_export_download.py`.
- School-admin same-school checks: `test_school_admin.py`.
- Role boundaries: `test_public_entry_roles.py`, `test_auth_entry_boundary.py`.
- Admin-only operations: platform-admin tests.
- Unauthenticated access: auth/authorization tests.

## Remaining gaps

- No single test enumerates every handler with User A/User B read/write/property tests.
- Property-level mass-assignment tests are representative, not exhaustive.
- Payment/Paystack callback flows need staging-level negative checks.
- No OWASP ZAP authorization scan yet.

No claim of complete handler-level negative coverage is made.
