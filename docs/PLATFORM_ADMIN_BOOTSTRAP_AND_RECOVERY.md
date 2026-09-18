# Platform Admin Bootstrap and Recovery

## First Deployment

1. Provision the production environment.
2. Set `PLATFORM_ADMIN_BOOTSTRAP_SECRET` to a strong random value (environment variable or `.env` — never commit it).
3. Start the application.
4. Open `/setup/platform-admin`.
5. Enter the bootstrap secret, full name, email, and password.
6. Confirm successful login at `/login/platform-admin`.
7. Remove or rotate the bootstrap secret (if your deployment strategy supports it).
8. Verify `/setup/platform-admin` is no longer usable (returns 410).

**Never seed a known production password. Never ship a default admin account.**

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
