# SchemeKnit Production Monitoring and Incident Runbook

Date: 2026-10-31  
Scope: launch-level monitoring using Render logs, `/api/health`, `/api/ready`, Resend owner alerts and the existing optional security webhook.

## 1. What is monitored

| Signal | Source | Alert |
|---|---|---|
| Backend process alive | `GET /api/health` | Render health check / owner check |
| DB and storage ready | `GET /api/ready` | Render health check / owner check |
| Repeated app/server errors | structured logs `unhandled_exception` | owner email/webhook via `alert_security` |
| Rate-limit store failure | `rate_limit_store_unavailable` | structured log; high-risk routes return 503 |
| Login lockout / suspicious auth | `login_locked`, `account_cooldown`, `mfa_failed` | owner email/webhook |
| Paystack webhook failure | `paystack_webhook_*`, sweeper counts | owner check + structured logs |
| Payment-credit reconciliation | transaction/credit tests + logs | owner check |
| Upload/storage failure | `scheme_upload_failed` | owner check |

## 2. Alert delivery

`alert_security(event, severity, **kwargs)`:

1. Always writes a structured security log.
2. Throttles the same event to one delivery per 15 minutes.
3. Tries `SECURITY_ALERT_WEBHOOK_URL` if configured.
4. Falls back to `OWNER_ALERT_EMAIL` through the existing Resend service.
5. Never includes passwords, tokens, API keys, full payment payloads or raw IPs.

Owner email is optional. If `OWNER_ALERT_EMAIL` is empty or the Resend sender cannot reach it, delivery returns false and logs `owner_alert_delivery_failed`; logs and health endpoints remain the fallback.

## 3. First-response checks

```bash
curl -fsS https://schemeknit-api.onrender.com/api/health
curl -fsS https://schemeknit-api.onrender.com/api/ready
```

Then:

1. Render backend logs: filter `error`, `security`, `paystack`, `rate_limit_store_unavailable`.
2. Render frontend availability.
3. Neon console: connections, compute, storage.
4. Paystack LIVE dashboard: transaction and webhook delivery.
5. Check `/api/health` version and deployed commit.
6. If `/api/ready` is 503, check DB and R2 reachability first.

## 4. Incident classes

### Backend down or cold-start timeout

- Render free services sleep after 15 minutes; first request can take 1–2 minutes.
- If it does not recover, inspect the latest deploy and logs.
- Roll back to the last known-good Render deploy only with owner approval.

### Database failure

- Do not run destructive SQL.
- Check Neon status/compute and connection limits.
- Restore only from a verified backup into a disposable database first.

### Payment webhook failure

- Do not manually mark a payment successful.
- Keep the failed event row and reference.
- Verify signature, amount, currency, customer and metadata.
- Use `python -m src.webhook_sweeper --max-batches 1` only against the verified production DB, or the prepared manual GitHub workflow.
- Never issue credits twice.

### Security event

- Preserve logs and timestamps.
- Revoke sessions for the affected account (logout-all / admin reset).
- Rotate the exposed credential at the provider if applicable.
- Do not delete evidence.

### Upload/storage failure

- Check R2 bucket/credentials and `/api/ready`.
- Do not report upload success until the object is stored.
- Re-upload is required if the original is missing.

## 5. Owner alert test

Run one harmless test after configuration:

```bash
python -c "from src.logging_config import alert_security; print(alert_security('owner_alert_test', severity='info', service='schemeknit-api'))"
```

Expected: one structured log and one owner email/webhook. If false, check `OWNER_ALERT_EMAIL`, Resend sender/domain and `SECURITY_ALERT_WEBHOOK_URL`.

## 6. Retention and limits

- Render Hobby logs: 7 days.
- Neon Free metrics: 1 day.
- No paid monitoring service is introduced.
- Alerts are aggregate/throttled; this is launch monitoring, not full observability.

## 7. Known limitations

- No 24/7 on-call.
- No central SIEM.
- Render free services can sleep/restart.
- Email alerting depends on a verified sender and authorized recipient.
- Webhook alerting depends on an existing configured endpoint.
