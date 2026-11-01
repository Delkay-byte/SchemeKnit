# SchemeKnit Access and Super Admin Setup — Design

Date: 2026-11-01
Status: Approved by owner in session (approach + security requirements)

## Intent

Two production complaints:

1. Ordinary teachers see a pilot invite-code field on `/signup` even though the
   product should allow public teacher registration.
2. The first Super Admin is sent to an authenticator-code prompt with no QR
   code and no setup key.

A third, cosmetic defect: the Platform Administration login page renders two
logos.

## Goals

- Public teacher registration works when the backend registration mode is
  explicitly `open`; the frontend must read the backend policy at runtime so a
  stale build flag cannot demand a code the backend does not enforce.
- Turnstile, password policy, rate limiting and all existing account controls
  stay enforced server-side.
- Super Admin TOTP enrollment is discoverable, mandatory and verifiable, with
  QR code plus manual setup key, one-time recovery codes and an operator-only
  reset path.
- Exactly one logo on the Platform Administration login page.
- Automated tests cover every changed behaviour.

## Non-goals

- No deployment, no production environment change, no production data change.
- No invite-code removal from restriction mode itself; `invite_only` and
  `closed` keep working exactly as before.
- No password reset, role change or privilege change in the MFA reset tool.
- No email-verification system is introduced; none exists today and none is
  required by this change.

## Constraints found in the codebase

- Registration mode is environment-only: `REGISTRATION_MODE`
  (`open` | `invite_only` | `closed`) in `backend/src/config.py`, enforced by
  `_registration_allowed` in `backend/src/routers/auth.py`. Default is `open`.
- The frontend only hides/shows the invite field using the build-time
  `NEXT_PUBLIC_PILOT_INVITE_REQUIRED` flag. It can therefore disagree with the
  backend in both directions.
- TOTP endpoints already exist and are sound: `generate_secret`,
  `provisioning_uri`, `verify_totp`, hashed single-use recovery codes,
  replay protection via `mfa_last_step`.
- `/mfa/setup` returns the secret and `otpauth_uri`; nothing renders a QR.
- The platform admin console already blocks privileged mutations when MFA is
  not enrolled (`require_platform_admin`, non-DEBUG only), but the login page
  always shows an authenticator field and the bootstrap flow goes straight to
  the console.
- `AuthShell` renders `BrandCapsule` in both the aside and the main header for
  split layouts; Platform Administration uses the split layout.
- The frontend has no JS test runner. Frontend behaviour is pinned by backend
  pytest source-contract tests, plus Playwright e2e scripts that need a live
  server. New frontend tests follow the existing source-contract pattern.

## Approaches

### B1 — registration policy

A. Configuration-only: set `REGISTRATION_MODE=open`, clear
   `PILOT_INVITE_CODE`, set `NEXT_PUBLIC_PILOT_INVITE_REQUIRED=false`, rebuild.
   No code change. Downsides: a forgotten frontend flag still blocks signup, and
   a missed flag in the other direction silently hides a required field.

B. Server-authoritative policy endpoint (chosen): add public
   `GET /api/auth/registration-policy` returning
   `{registration_mode, self_registration, invite_code_required}`. The signup
   page reads it at runtime, keeps the env flag only as a fallback, and refuses
   to submit while the policy is unknown. Backend invite enforcement is
   untouched.

C. Remove the invite field entirely. Rejected: breaks `invite_only`
   deployments and their UX.

### B2 — Super Admin enrollment

A. Blocking enrollment panel on `/platform-admin` (chosen). Reuse one shared
   enrollment component for the console gate and the Settings card. QR is
   rendered server-side from the existing `otpauth_uri` using `segno`, returned
   as an SVG data URI, so the provisioning URL never leaves the server as an
   image request.

B. Dedicated `/setup/platform-admin/enroll` route. More routing and redirect
   states for no security gain.

C. Keep enrollment only in Settings. Rejected: this is the reported defect.

### B3 — logo duplication

Remove the aside `BrandCapsule`; keep the main header capsule. The main header
already appears on every auth shell, including mobile, at 44 px with 28 px mark.

## Design

### Registration policy endpoint

`GET /api/auth/registration-policy` (public, `Cache-Control: no-store`):

```json
{ "registration_mode": "open", "self_registration": true, "invite_code_required": false }
```

Derived from `REGISTRATION_MODE` only. No secret, no account data. `closed`
returns `self_registration: false`.

Frontend: on mount, `api.getRegistrationPolicy()`. While loading, submit is
disabled. On success, `invite_code_required` controls the field and the
client-side check. On failure, registration is treated as unavailable (message
plus retry); the env flag is never used to assume open. The backend still
validates the code on every request, so direct API calls cannot bypass it.

### QR enrollment

- `backend/src/mfa_qr.py`: `provisioning_qr_data_uri(otpauth_uri)` uses
  `segno` to build an SVG QR and returns `data:image/svg+xml;base64,...`.
  No third-party network call.
- `/mfa/setup` adds `qr_data_uri` and `Cache-Control: no-store, private`,
  `Pragma: no-cache`. It still requires `require_platform_admin_unenrolled`,
  so only the authenticated admin can obtain their own pending secret. Secret
  and URI stay out of logs.
- Secret is persisted in `mfa_pending_secret` with
  `mfa_pending_expires_at` (30 minutes, `MFA_PENDING_TTL_MINUTES`). It is
  copied to the active `mfa_secret` only when `/mfa/verify-setup` accepts a
  current code, and only then is `mfa_enabled` set and recovery codes issued.
- Setup is idempotent: inside the pending window, refreshes, multiple tabs and
  concurrent requests return the same secret and QR. A single conditional
  UPDATE installs the pending secret, so competing requests converge.
- Expired pending secrets are discarded; their codes are rejected and a later
  setup call starts a fresh enrollment.
- After enrollment, `/mfa/setup` returns 400, so the secret and QR are never
  shown again. Changing an authenticator requires the existing
  disable flow (password + current TOTP/recovery code) and then a fresh
  enrollment.

### Backend enrollment enforcement

`require_platform_admin` rejects every request from a platform admin without
`mfa_enabled` when `DEBUG` is false, including reads. Reads were previously
allowed; the console now blocks itself with the enrollment panel, so nothing
legitimate needs them before enrollment. `/api/auth/mfa/*` continues to use
`require_platform_admin_unenrolled`, which is the only pre-enrollment surface.

### Frontend enrollment

- `MfaEnrollPanel`: auto-calls `beginMfaSetup`, renders QR `<img>`, manual key
  with copy, 6-digit input, verify, then recovery codes shown once with an
  acknowledgement checkbox.
- `MfaSettingsCard`: uses the panel while not enrolled; after enrollment it
  shows status and the disable/regenerate controls only.
- `/platform-admin`: if the signed-in user is a platform admin without MFA,
  render the blocking enrollment card and nothing else. On success,
  `refreshUser()` re-reads `/api/auth/me` and the console appears.
- `/login/platform-admin`: keep the code field for already-enrolled admins, add
  first-sign-in guidance that an authenticator is set up after signing in.

### Operator MFA reset

Extend `python -m src.tools.reset_platform_admin` with `--reset-mfa`:

- Requires `--email`, `--operator`, `--reason`.
- Dry-run by default; `--apply` performs the change, and the operator must type
  the target email to confirm.
- Clears only `mfa_enabled`, `mfa_secret`, `mfa_recovery_codes`,
  `mfa_last_step`; never touches the password, role or active flag.
- Revokes every active session for the account.
- Inserts a `platform_audit_logs` row: action `platform_admin_mfa_reset_cli`,
  target user, operator, reason, timestamp.
- Documented in `docs/PLATFORM_ADMIN_BOOTSTRAP_AND_RECOVERY.md` with the
  identity-verification steps to complete before running it.

### Logo

Remove the aside `BrandCapsule`. The main header capsule becomes the single
logo for every role and viewport. The school-admin aside already had no brand,
so it is unaffected.

## Testing

Backend pytest:

- registration-policy responses for `open`, `invite_only`, `closed`.
- public registration without invite code under `open`; `invite_only` rejects
  missing/invalid code even with a valid Turnstile token; Turnstile missing,
  invalid and unavailable still reject; password policy still rejects weak
  passwords.
- `/mfa/setup` returns a local SVG data-URI QR and no-store headers; an
  enrolled admin cannot re-read the secret; a non-admin cannot call setup.
- enrollment from bootstrap state through verify; invalid code; expired code
  (outside the ±1 step window); replay; recovery single use; regeneration
  invalidates old codes.
- blocking: unenrolled admin gets 403 on console endpoints when `DEBUG=false`;
  `/mfa/setup` stays reachable.
- operator reset: dry-run changes nothing; apply clears MFA, revokes sessions,
  writes audit with operator and reason, and leaves password/role intact.
- source contracts: signup reads the policy endpoint; auth shell renders
  exactly one brand capsule; enrollment panel renders QR, manual key, recovery
  codes.

Project gates: `pytest`, frontend `tsc --noEmit`, `next lint`, `next build`.

## Rollout

Code changes only. Owner must, separately and with approval:

1. Backend: `REGISTRATION_MODE=open` (remove/blank `PILOT_INVITE_CODE` if
   present).
2. Frontend: `NEXT_PUBLIC_PILOT_INVITE_REQUIRED=false`, rebuild and redeploy.
3. Backend deploy must install the new `segno` requirement.
4. The existing Super Admin signs in and completes enrollment on first entry to
   `/platform-admin`; no database reset.
