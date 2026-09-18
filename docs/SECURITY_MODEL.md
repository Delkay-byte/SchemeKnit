# TeachFlow Security Model

## Roles
- **Platform Admin** (`platform_admin`, no school): all schools, licenses, codes, plans,
  payments, audit. Never teacher workflows (403), never school-teacher ops via workflow.
- **School Admin** (`school_admin`, exactly one `school_id`): own dashboard/teachers/
  settings/license. No platform APIs, no other schools, no teacher lesson planning UI.
- **Teacher** (`teacher`, one `school_id`): lesson workflow + own templates only.
  No user management, no admin areas.

## Tenant boundary
`school_id` is always server-derived (registration, setup claim, creation). Client-supplied
`school_id`/role/ownership is ignored or rejected. Cross-tenant reads/writes return
403 (exists, unowned) or 404 (missing). Resource lists are owner/school-scoped.

## Authorization model
Dependencies: `get_current_user` (401) → `require_admin` (school or platform admin) →
`require_platform_admin` (platform only) → `_require_same_school` (user management) →
license gates (`require_valid_license`, `require_teacher_workflow`). Frontend guards mirror
but never substitute these checks (verified by IDOR suite + live probes).

## License/entitlement boundary
License states: pending/active/suspended/expired/cancelled. Only active, non-expired
licenses unlock teacher workflow and teacher creation. Suspended/expired preserves all
data while restricting commercial access. Platform Admin is the sole license authority.
Seat rule: only ACTIVE teachers consume seats; deactivation frees; reactivation re-checks.

## Activation lifecycle
`active → used` (single atomic redeem + admin claim + audit) or `→ revoked`/`expired`.
Codes never reusable; license auto-activates from pending on first valid redeem.
Validation endpoint is display-only. No secrets in any activation response.

## Export access control
Every export resolves its job/lessons by `(id, owner_id)`; cross-owner access denied.
Export events (`export_events`) record completed builds per scheme/owner for workflow state.

## Template ownership
Private by default (owner-only CRUD/preview/render); archived hidden but preserved;
versions explicit (X.Y). Unknown custom ids fall back to built-in rendering — never to
another owner's template.

## Transport/session posture
Stateless JWT Bearer (24h) in memory+localStorage (no cookies → CSRF N/A). 401 clears
the session client-side and returns to login. Rate limits on sensitive routes; localhost
exempt for dev/test; reverse-proxy limiting required for multi-worker production.
Security headers on API responses; CORS allowlist is environment-configured.
