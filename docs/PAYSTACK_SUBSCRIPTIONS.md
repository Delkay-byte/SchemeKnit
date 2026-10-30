# Prepaid packages: Bank Transfer and Mobile Money

TeachFlow no longer offers card checkout or automatic recurring billing. Every
package is a one-time prepaid purchase. Credits are granted only after Paystack
confirms the payment and the backend verifies it.

## Architecture

```
Browser → /upgrade → POST /api/paystack/bank-transfer/charge (auth)
                   → POST /api/paystack/momo/charge          (auth)
        → Paystack Charge API returns instructions
        → GET /api/paystack/charge/status/{reference} polls
        → Paystack charge.success webhook (HMAC SHA512, raw body)
        → verified reference/amount/currency/customer
        → transaction credited once → credits granted → package active
```

`POST /api/paystack/initialize` is retired and returns **410**. It never calls
Paystack. Historical card transactions, licences and subscriptions remain in the
database and are still shown in purchase history as historical records.

## Approved catalogue

The authoritative values live in `backend/src/catalogue.py`; migration v041
seeds `subscription_plans` from it. The API reads the database.

| Package | Price | Credits | Validity |
|---|---:|---:|---|
| Free | GH₵0 | 2 per calendar month | Monthly reset |
| Flexible Credit Pack | GH₵12 | 20 | Credits do not expire |
| Teacher Monthly | GH₵22 | 40 | 30 days |
| Teacher Term Pass | GH₵50 | 160 | 120 days |
| Academic Year Pass | GH₵120 | 480 | 365 days |

`teacher-annual` and `school-monthly` remain in the database for history but are
inactive for new purchases. Existing customer entitlements are not modified.

## Bank Transfer (Ghana Pay with Transfer)

`POST /api/paystack/bank-transfer/charge` with `{plan_slug}` calls Paystack
`POST /charge` with a `bank_transfer` object and an `account_expires_at` up to
8 hours ahead. Paystack returns `status=pending_bank_transfer`, a temporary
account name/number, bank name and expiry. The response is stored in
`subscription_transactions.payment_details` and returned to the browser.

Nothing is activated when the instructions are displayed. Activation requires a
verified `charge.success` or a successful `GET /verify/{reference}`.

`bank.transfer.rejected` / `transfer.rejected` marks a pending transaction
failed. `GET /api/paystack/charge/status/{reference}` reports `expired` after the
account expiry, and never issues credits for an expired session.

## Mobile Money

`POST /api/paystack/momo/charge` with `{plan_slug, phone, provider}` calls
Paystack `POST /charge` with `mobile_money: {phone, provider}`.

Providers: `mtn` (MTN), `vod` (Telecel), `atl` (AirtelTigo/ATMoney). The phone
must be a valid 10-digit Ghana number matching the selected network's prefixes.
The response is normally `pay_offline` with `display_text`; the package stays
pending while the customer authorises on their phone (180-second provider
window). The frontend polls `GET /api/paystack/charge/status/{reference}`.

No reusable authorisation is created, no card is charged and no automatic
renewal is initiated.

## Webhook

Public URL: `https://<backend-host>/api/paystack/webhook`.

Register it in the Paystack dashboard. The signature is HMAC SHA512 of the raw
body using the secret key. Every delivery is recorded in
`paystack_webhook_events` with a unique event key before processing, so duplicate
deliveries are ignored.

Handled events:

- `charge.success` — verify with Paystack, then activate exactly once.
- `charge.failed`, `bank.transfer.rejected`, `transfer.rejected` — mark failed.
- `refund.processed`, `charge.reversed`, `refund.pending` — mark the transaction
  reversed and reverse unused package/referral credits without going negative.
- Historical subscription events remain handled for old records only.

A processing failure is recorded (`status=failed`, `last_error`) and the event is
retried on the next delivery. A stale `received` event older than five minutes
is also retried. The HTTP response is sent immediately after HMAC validation
and event recording; Paystack verification and entitlement activation run in a
background task, so a slow provider call cannot make Paystack time out. Invalid
signatures are rejected before any event is recorded or processed.

## Exactly-once activation

`activate_paid_transaction` checks the transaction status first and grants the
package credits with the unique key `package:<reference>`. A duplicate webhook,
callback race or replayed verify cannot grant twice. Credits are also tracked in
`credit_balances` and `credit_ledger`.

## Environment

Backend (private production secrets; never in frontend or Git):

| Variable | Purpose |
|---|---|
| `PAYSTACK_ENABLED` | `true` by default. Set `false` to stop all new payment initiation safely. |
| `PAYSTACK_MODE` | `test` in development/tests, `live` in production. Must match the key prefix. |
| `PAYSTACK_SECRET_KEY` | Server-only `sk_test_...` or `sk_live_...`. |
| `PAYSTACK_CURRENCY` | Must be `GHS`. |

Optional frontend variable only if a Paystack client-side SDK is ever used:
`NEXT_PUBLIC_PAYSTACK_PUBLIC_KEY=pk_test_...` / `pk_live_...`. The current
server-side Charge API flow does **not** need a public key. Never put a secret
key in a `NEXT_PUBLIC_*` variable.

The backend refuses a live key unless `PAYSTACK_MODE=live`, and refuses a test
key when `PAYSTACK_MODE=live`. Production startup also fails if a test key is
configured with `DEBUG=false`. The secret key is never returned, logged or
bundled; all API calls use `https://api.paystack.co` with TLS certificate
verification enabled.

## Database

- `v038_paystack_subscriptions` — subscription/transaction/webhook/licence tables.
- `v039_payment_method_modes` — prepaid vs recurring columns.
- `v040_adesua_package_labels` — historical labels.
- `v041_commercial_credits_referrals` — approved catalogue, credit tables and
  referral tables. Additive; `down()` only re-activates the legacy catalogue and
  is not a data deletion.
- `v042_package_price_update` — Teacher Term Pass GH₵50/5,000 pesewas and
  Academic Year Pass GH₵120/12,000 pesewas. Credits/validity unchanged. Rows
  referenced by a subscription, licence or transaction are preserved under a
  `*-legacy` slug and deactivated; new rows serve checkout. Unreferenced rows
  are updated in place. Historical transaction amounts and plan IDs are never
  rewritten.

## Durable webhook recovery

The webhook endpoint persists the verified event payload before acknowledging it.
Processing is idempotent and runs in a background task. A one-shot sweeper
recovers events left in `received`, `failed` or expired `processing` state after
a worker crash.

Run one bounded cycle:

```bash
cd backend
python -m src.webhook_sweeper --batch-size 20 --max-batches 5
```

Properties:

- PostgreSQL `FOR UPDATE SKIP LOCKED` claims rows; SQLite is supported for tests
  only and does not prove PostgreSQL lock behaviour.
- 120-second lease; expired leases are reclaimed.
- Stale `received` events become eligible after 5 minutes.
- Failed events retry with 30s, 60s, 120s … backoff capped at 1 hour.
- Maximum 8 attempts by default; exhausted rows are retained for inspection.
- Unknown/outgoing-transfer events are marked `ignored`, never retried.
- Completed events are never retried.
- Only the existing `handle_webhook` finalizer runs; credits, referrals and
  refunds keep their existing idempotency keys.

Scheduling is deliberately **not** created automatically. Add a Render Cron Job
only after approving its cost, with start command:

```bash
cd backend && python -m src.webhook_sweeper --batch-size 20 --max-batches 5
```

A cron job is not required for the webhook endpoint to work; it is the recovery
safety net for worker crashes.

## Recovery

- Duplicate webhook: unique `event_key` plus unique credit grant key.
- Callback/webhook race: transaction status check plus unique grant key.
- Wrong amount/currency/reference/customer: rejected with 400, no credits.
- Failed processing: event row `failed` with sanitized `last_error`; the sweeper retries after backoff.
- Rollback: remove the Paystack secret key; lesson and credit features continue,
  and no new payment can start.
