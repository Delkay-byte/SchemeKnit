# Admin Password Reset

## Who Can Reset Whom

| Initiator | Target | Mechanism |
|---|---|---|
| Platform Admin | School Admin | Token-based reset (Accounts tab or school detail) |
| Platform Admin | School Teacher | Token-based reset (Accounts tab or school detail) |
| Platform Admin | Individual Teacher | Token-based reset (Accounts tab) |
| Platform Admin | Another Platform Admin | Token-based reset (Accounts tab) |
| School Admin | Own school's teacher | Token-based reset or direct-set (teachers page) |

## Platform Admin UI

### Accounts Tab

The platform admin console has an **Accounts** tab that lists every user on the platform with their role and status. Each row (except the current admin's own) has an **Initiate Password Reset** button.

Clicking it:
1. Shows a confirmation: "You are about to initiate a password reset for [name] ([email])."
2. On confirm, the server generates a one-time reset token.
3. A modal displays the token with a copy button and the expiry time.
4. The admin delivers the token to the user out-of-band.

### School Detail Modal

The Schools tab's school drill-down lists all teachers and administrators in a school. Each active user (except the current admin) has a key icon button that initiates a password reset.

## School Admin UI

The school admin's Teachers page has two reset actions per teacher:

1. **Key icon (direct set):** The admin sets a new password directly (legacy flow, still supported).
2. **KeyRound icon (initiate reset):** Generates a one-time token shown to the admin, who delivers it to the teacher. The teacher completes the reset at `/reset-password`.

## Reset Completion

The user visits `/reset-password`:
1. Enters (or pastes) the reset token and clicks **Verify** — the page shows which account the token is for.
2. Enters a new password and confirms it.
3. On success, all existing sessions are invalidated and the user must sign in fresh.

The token is single-use; a second attempt with the same token returns 410.

## Audit Trail

Every reset is audited in `platform_audit_logs`:
- `password_reset_initiated` — who initiated, target account, timestamp.
- `password_reset_completed` — target completed the reset, method used.

No secrets are ever included in audit entries.

## Known Limitations

- **No email delivery:** tokens are displayed to the admin, not emailed. The admin must deliver them out-of-band (phone, in person). When email delivery is added, it can replace this display with secure email links.
- **Disabled accounts cannot be reset:** the reset endpoint rejects tokens bound to disabled accounts. Reactivate the account first, then initiate the reset.
