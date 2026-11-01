# Platform Admin Bootstrap and Recovery

## First Deployment

1. Provision the production environment.
2. Set `PLATFORM_ADMIN_BOOTSTRAP_SECRET` to a strong random value (environment variable or `.env` — never commit it).
3. Start the application.
4. Open `/setup/platform-admin`.
5. Enter the bootstrap secret, full name, email, and password.
6. The new admin lands on the blocking enrollment screen at `/platform-admin`.
   Scan the QR code (or copy the manual setup key) into a TOTP authenticator
   app and enter the current six-digit code. Store the recovery codes shown
   once, offline.
7. Confirm successful login at `/login/platform-admin`.
8. Remove or rotate the bootstrap secret (if your deployment strategy supports it).
9. Verify `/setup/platform-admin` is no longer usable (returns 410).

**Never seed a known production password. Never ship a default admin account.**

## Authenticator Enrollment (TOTP)

Platform administration requires TOTP MFA. Enrollment is mandatory: with
`DEBUG=false`, every platform-admin API request from an unenrolled account is
refused with 403, and the console shows only the enrollment screen.

- `POST /api/auth/mfa/setup` creates a fresh random secret for the signed-in
  admin, stores it with `mfa_enabled = false`, and returns the secret, the
  `otpauth://` URI and an SVG QR code generated locally (`segno`; no external
  QR service). The response is `Cache-Control: no-store, private`.
- The secret stays pending until `POST /api/auth/mfa/verify-setup` accepts a
  current six-digit code (30-second step, ±1 step window). Only then is
  `mfa_enabled` set and eight single-use recovery codes issued.
- Recovery codes are stored as bcrypt hashes and shown once. Regenerating them
  requires the password and a current TOTP or recovery code, and invalidates
  every previous code.
- After enrollment the secret and QR are never returned again; re-enrolling
  (changing authenticator) requires the password plus a current code via
  `POST /api/auth/mfa/disable`, then a fresh enrollment.
- Sign-in without a current TOTP or unused recovery code fails. Codes already
  accepted in a timestep cannot be replayed.

## Bootstrap Security

- The bootstrap endpoint is available **only when zero active platform admins exist**.
- Requires the `PLATFORM_ADMIN_BOOTSTRAP_SECRET` from server configuration.
- The secret is compared in constant time (`secrets.compare_digest`) and never logged.
- Race-safe: the INSERT is conditional (`WHERE NOT EXISTS`), so two simultaneous requests cannot both create a first admin.
- After the first admin is created, the endpoint permanently returns **410 Gone** (backend-enforced, not just hidden in the frontend).
- If the secret is empty (not configured), the endpoint returns **404** and bootstrap is only possible via the CLI tool.

## Multiple Platform Admins

The system supports multiple platform admin accounts. A second platform admin can be created by an existing one via the Accounts tab in the platform admin console (or the CLI tool). Any platform admin can initiate a password reset for another platform admin.

**Last-admin safeguard:** The system prevents deactivating the last active platform administrator, so the platform never loses all recovery paths.

## Operator-only MFA Reset (CLI)

Use only when the Super Admin cannot complete an authenticator challenge and
has no unused recovery code. MFA reset is never exposed over HTTP.

**Before running it, verify the requester's identity out of band** (known
phone number or video call, employee record, photo ID against the account
name). Do not accept an email-only request. Record who approved it and why.

Default is a dry run:

```bash
cd backend
python -m src.tools.reset_platform_admin --reset-mfa \
  --email admin@example.com \
  --operator "operator-name" \
  --reason "Lost phone; identity verified by video call, ticket OPS-123"
```

The command prints the target, current MFA status and active session count. To
apply, add `--apply` and type the target email when prompted:

```bash
python -m src.tools.reset_platform_admin --reset-mfa --apply \
  --email admin@example.com --operator "operator-name" --reason "OPS-123"
```

Effects: clears `mfa_enabled`, `mfa_secret`, recovery-code hashes and the replay
marker; revokes every active session for that account; writes a
`platform_audit_logs` row (`platform_admin_mfa_reset_cli`) containing the target,
operator, reason and timestamp. It never changes the password, role or active
flag. The admin signs in with the existing password and enrolls a new
authenticator at `/platform-admin`.

## Break-Glass Recovery (CLI)

When the only platform admin is locked out and no second admin can initiate a reset:

```bash
cd backend
python -m src.tools.reset_platform_admin --email admin@example.com
```

This server-side operational tool:
- Finds the platform admin by email.
- Issues a **one-time, expiring reset token** (30-minute TTL).
- Prints the token for the operator to deliver out-of-band.
- The admin completes the reset at `/reset-password`.
- Audits the event as `platform_admin_password_reset_cli` with method `cli_break_glass_token`.

Alternative — directly set a new password (prompted, never echoed):

```bash
python -m src.tools.reset_platform_admin --email admin@example.com --set-password
```

This tool is **never exposed through the web UI**. It requires local filesystem access to the database. The password must still satisfy the production policy.

## DB Resolution (CLI tools)

The CLI tools search for the database in this order:
1. `DATABASE_URL` environment variable (PostgreSQL).
2. `TEACHFLOW_DATA_DIR` environment variable.
3. Current working directory (`teachflow.db`).
4. `%APPDATA%/teachflow-desktop/data/teachflow.db` (desktop).
5. `~/teachflow_data/teachflow.db`.

## Known Limitations

- **No email delivery.** Reset tokens are displayed to the initiating admin (or printed by the CLI) and must be delivered out-of-band. When email delivery is added in the future, it can replace the operational reset-code display with secure email reset links.
- **JWT sessions are stateless.** Session invalidation after password change/reset is implemented via a `pwv` (password-version) claim in the token, not a server-side revocation list. Tokens issued before the change are rejected at the next authenticated request.
