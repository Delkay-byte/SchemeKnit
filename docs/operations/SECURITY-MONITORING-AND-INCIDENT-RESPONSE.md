# Security Monitoring and Incident Response

Date: 2026-10-31  
Status: **Structured logging and optional webhook adapter implemented; central delivery BLOCKED without a configured service**

## Security events

Recorded through `log_security` / `alert_security`:

- login failed / account cooldown,
- MFA failed / enabled / disabled / recovery used,
- rate-limit exceeded,
- password reset events,
- session revocation,
- authorization failures where logged,
- upload validation failures,
- provider failures,
- admin/bootstrap failures.

Events use opaque HMAC account keys or user ids; no passwords, tokens,
reset tokens, TOTP secrets, recovery codes, API keys, database URLs or lesson
content.

## Alert adapter

`SECURITY_ALERT_WEBHOOK_URL` optionally posts JSON events to a configured
webhook. With no URL, `alert_security` records the structured event and returns
`False`; it does not claim delivery.

Tested in `backend/tests/test_security_monitoring.py`:
- no URL → not delivered,
- configured webhook → delivered,
- delivery failure → logged, never raises, returns False.

## Alert thresholds to configure

- 5+ account cooldowns in 10 minutes,
- burst of rate-limit 429s from one or many IPs,
- repeated MFA failures,
- repeated 401/403 on admin routes,
- provider failure burst,
- database connectivity loss,
- webhook signature failures.

## Incident response runbook

1. Detect: inspect security logs/alert payload.
2. Classify severity: account, data, payment, availability.
3. Contain: revoke sessions (`jti`/`pwv`), disable account, rotate credentials.
4. Investigate: preserve logs, timeline, affected accounts; do not log secrets.
5. Notify owner; assess data/payment impact.
6. Recover: restore service, verify controls, monitor.
7. Review: update checklist and tests.

## Remaining

No central monitoring account is configured. No alert delivery has been
verified against a real service. This is **BLOCKED**, not DONE.
