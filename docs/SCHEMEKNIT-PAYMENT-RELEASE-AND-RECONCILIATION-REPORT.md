# SchemeKnit Payment Release and Live Purchase Reconciliation Report

Date: 2026-11-06
Repository: `Delkay-byte/SchemeKnit`
Production: `https://schemeknit-frontend.onrender.com` / `https://schemeknit-api.onrender.com`

## 1. Repository and SHAs

| Item | Value |
|---|---|
| Starting `main` base | `ad7ca5392473ce7f543a890df47d8652fe9cc811` |
| Starting feature head (reported) | `116cd79b81a5669f27f2f8597f98163684e807cd` |
| Final feature head | `78ed1a1c84d747bf3f5cd118f9e6de25a36900f3` |
| PR #10 merge commit (`main`) | `9824a6d95f33c5447fc24e10e4c25ca34ac3ea9d` |

The feature branch was 20 commits ahead of `main` and had no divergence. No reset,
rebase, force-push, clean or history rewrite was used. No newer work from another
agent was overwritten.

## 2. PR #10

- URL: https://github.com/Delkay-byte/SchemeKnit/pull/10
- Marked ready for review and merged with a merge commit after all required checks
  passed on `78ed1a1`.
- Merge commit: `9824a6d95f33c5447fc24e10e4c25ca34ac3ea9d`.
- Resulting `main` SHA deployed to production: `9824a6d95f33c5447fc24e10e4c25ca34ac3ea9d`.

## 3. Files changed in the release commit

```
.github/workflows/ci.yml
backend/scripts/reconcile_paystack_purchase.py
backend/src/credits.py
backend/src/database.py
backend/src/main.py
backend/src/migrations/v054_purchase_entitlements.py
backend/src/paystack.py
backend/src/purchase_notifications.py
backend/src/routers/auth.py
backend/src/routers/platform_admin.py
backend/tests/test_prepaid_payments.py
backend/tests/test_purchase_entitlements.py
backend/tests/test_purchase_notification_recovery.py
frontend/e2e/purchase-confirmation-ui.js
frontend/package.json
frontend/src/app/(app)/dashboard/page.tsx
frontend/src/app/(app)/payments/callback/page.tsx
frontend/src/app/(app)/subscription/page.tsx
frontend/src/types/index.ts
```

## 4. Entitlement-separation design

Two commercial products now have independent lifecycles.

**A. Flexible credit-pack entitlement**

- New `purchase_entitlements` row keyed by the immutable payment reference.
- `kind = 'flexible'`, `expires_at = NULL`.
- Credits remain in the existing `credit_balances` bucket with source `purchased`.
- Never expired by `expire_overdue()`.
- Auditable through the row, the credit bucket and the append-only `credit_ledger`.

**B. Time-limited package entitlement**

- `kind = 'timed'`, own `starts_at` / `expires_at`.
- Expiry is handled only by its own lifecycle in `expire_overdue()`.
- Expiring it never touches flexible rows, credit balances, unrelated licences or
  unrelated purchases.

`UserLicenseDB` remains the single-per-account internal licence mirror for
compatibility and administration. Fulfilment and dashboard decisions are now
scoped to the transaction reference in `purchase_entitlements`, not to one shared
licence status.

`expire_overdue()`:

1. expires timed `purchase_entitlements` rows only;
2. expires overdue legacy subscription rows;
3. keeps the shared licence/entitlement mirror active when a live flexible pack
   exists;
4. never deletes or reduces a credit balance.

Dashboard behaviour:

- `GET /api/auth/my-plan` selects a live purchased entitlement first, so an
  expired timed package cannot hide a valid flexible pack.
- The dashboard shows package name, type, amount, payment method, purchase date,
  credits granted, credits used and credits remaining.
- Expiry is shown only for timed packages. Flexible packs explicitly show no
  expiry.

## 5. Migration and compatibility evidence

Migration: `v054_purchase_entitlements` (`Independent purchased-entitlement lifecycle`).

- Additive only: creates `purchase_entitlements`, a unique reference index and a
  `(user_id, status)` index.
- No column is dropped or rewritten. No credit, licence, transaction or
  subscription row is modified.
- Existing successful transactions are backfilled with deterministic IDs
  (`pe:<reference>`) and their historical package kind/period.
- Legacy records that predate the table still resolve through the compatibility
  path in `fulfilment_state()`.
- Rollback/forward recovery: the migration is forward-only. Recovery is to
  disable the deploying revision or restore the pre-deployment logical backup;
  dropping the new table does not affect existing purchase, licence or credit data.

Production evidence:

- Log: `migration_applied v054_purchase_entitlements ... status=applied` at
  `2026-11-06T10:28:30.937199Z`.
- Production database after deployment: `successful_transactions=1`,
  `purchase_entitlements=1`, `missing_entitlements=[]`.
- Pre-deployment logical backup of affected tables was created at
  `2026-11-06T10:06:57Z` (users, plans, transactions, licences, subscriptions,
  credit balances/ledger, entitlements, subscription events, payments).

## 6. Admin 502 error handling

`POST /api/platform-admin/paystack-purchases/{reference}/reconcile` now wraps
`paystack.verify()` in the provider exception handler.

- Provider outage/timeout/credential rejection: controlled **502** with the
  transaction reference and an explicit statement that no entitlement changed.
- Unknown local purchase: **404**.
- Invalid reference, amount mismatch, currency mismatch, channel/account/package
  mismatch: controlled **400**.
- Reversed/refunded payment: **409**.
- Verified success: fulfilment path; incomplete fulfilment is reported as
  `needs_attention`.
- No provider secret, header or internal exception detail is returned.
- Safe server-side log event: `paystack_reconcile_verification_unavailable`
  with reference, provider status and error type only.
- The CLI reconciliation command handles provider unavailability without changing
  local state.

Tests cover 502, 404, amount mismatch and successful idempotent repair.

## 7. Notification recovery beyond 20 records

`retry_pending()` no longer limits recovery to the latest 20 successful rows.

- Stable keyset pagination on the transaction primary key (`id`), bounded batches.
- Processes all eligible successful purchases across repeated batches without
  loading a full table into memory.
- Per-channel idempotency: delivered notifications are never resent.
- Exponential backoff and an 8-attempt automatic limit.
- Failed records remain stored with attempts, timestamps and provider responses
  for authorised recovery.
- Restart-safe: the next worker pass starts from the beginning of the keyset and
  recovers older gaps.
- Notification failure never rolls back a payment, licence, entitlement or credit
  grant.

Tests include 25 successful transactions where the oldest failed notification is
outside the latest 20, plus backoff, retry-limit, failure-retention and repeated
worker-run idempotency.

## 8. CI integration for `purchase-confirmation-ui.js`

`frontend/e2e/purchase-confirmation-ui.js` is executed by the `UX browser and
accessibility` job in `.github/workflows/ci.yml`:

```text
node e2e/payment-checkout.js
node e2e/purchase-confirmation-ui.js
```

The script is also available as `npm run e2e:purchase-confirmation`.

CI run `42200518635` log confirms the command ran and the full journey passed:

```text
node e2e/purchase-confirmation-ui.js
PASS activated confirmation shows package/credits and no key entry
PASS full flexible-pack purchase journey activates automatically
```

## 9. Browser test evidence

The browser test uses only synthetic fixtures; no live charge is created.

Journey covered:

1. Open the package catalogue.
2. Select the Flexible Credit Pack.
3. Assert package name and GH₵12.00 price.
4. Start Mobile Money checkout.
5. Receive processing feedback (`Check your phone`, reference state).
6. Receive verified payment and activation feedback.
7. See automatic package activation.
8. See 20 credits granted.
9. See current balance 20.
10. See the package name on the dashboard.
11. See the purchase in purchase history.
12. Refresh and retain the entitlement.
13. Confirm no licence-key input or key exposure.
14. Confirm `needs_attention` tells the teacher not to pay again.
15. Confirm delayed/pending and failed states do not claim success.

Local run result: 5 PASS scenarios. CI run: same test passed inside the browser job.

## 10. Full test results

CI run `42200518635` on final head `78ed1a1`:

| Job | Result |
|---|---|
| Backend tests and compile | **3282 passed, 62 skipped, 5 deselected, 0 failed** |
| PostgreSQL migration harness | pass |
| Frontend lint, UX unit tests, `tsc --noEmit`, build | pass |
| Secret scan | pass |
| UX browser and accessibility | pass |
| Live Gemini/Groq providers (manual) | skipped |

Local full backend run (`-m "not live_provider"`) on the same code:

```text
3316 passed, 27 skipped, 5 deselected in 1336.64s
```

The local run has fewer skips because this workstation has additional converters
and local-only test prerequisites. `tests/security` was included. No assertions
were weakened or removed.

## 11. Exact Paystack verification result

Production server-side verification (live key, live mode) for
`TFM-312e7b80-475e34f2211c0682fa9a`:

```json
{
  "status": "success",
  "reference": "TFM-312e7b80-475e34f2211c0682fa9a",
  "id": 6730146887,
  "receipt_number": "0000015151983695",
  "amount": 1200,
  "currency": "GHS",
  "channel": "mobile_money",
  "paid_at": "2026-11-04T17:32:36.000Z",
  "metadata": {
    "user_id": "312e7b80-198a-456b-921c-95eb7cf0558b",
    "plan_id": "55da58a1-e176-4d67-ad62-10f13fa1fce3",
    "plan_slug": "flexible-credit-pack",
    "environment": "live",
    "provider": "vod"
  }
}
```

## 12. Original purchase snapshot

The original transaction predates package-snapshot capture, so its stored
`package_snapshot` is `null`. The purchase is nonetheless conclusively identified
by three independent production facts, not by the amount alone:

- local transaction `plan_id = 55da58a1-e176-4d67-ad62-10f13fa1fce3`, which is
  `flexible-credit-pack` / Flexible Credit Pack / `package_kind=flexible`;
- Paystack metadata `plan_id` and `plan_slug=flexible-credit-pack`;
- the immutable credit grant key `package:TFM-312e7b80-475e34f2211c0682fa9a`
  with 20 credits.

Production purchase record:

| Field | Value |
|---|---|
| Reference | `TFM-312e7b80-475e34f2211c0682fa9a` |
| Provider transaction | `6730146887` |
| Receipt | `0000015151983695` |
| Amount | GHS 12.00 (1200 pesewas) |
| Currency | GHS |
| Channel/provider | Mobile Money / Telecel (`vod`) |
| Paid at | 2026-11-04 17:32:36 UTC |
| Package | Flexible Credit Pack (`flexible-credit-pack`) |
| Environment | live |
| Local status | success |
| Fulfilment | activated |

## 13. Teacher entitlement before and after reconciliation

Account verified through the production API: id
`312e7b80-198a-456b-921c-95eb7cf0558b`, email `de***@gmail.com`, role `teacher`,
subscription type `individual`.

Before the reconciliation command:

| Field | Value |
|---|---|
| Transaction | success / activated |
| Licence | active, no expiry |
| Credit bucket | 20 granted, 20 remaining, no expiry |
| Dashboard package | Flexible Credit Pack, flexible |
| Purchase entitlement row | absent before v054; created by the migration |

After the official reconciliation command
(`python -m scripts.reconcile_paystack_purchase --reference ... --apply --confirm ... --reason ...`):

| Field | Value |
|---|---|
| Transaction | success / activated (unchanged) |
| Purchase entitlement | `kind=flexible`, `status=active`, `expires_at=null` |
| Licence | active, no expiry |
| Credits | 20 granted, 0 used, 20 remaining |
| Plan | PRO, source `paystack`, no expiry |
| Purchase history | present with GHS 12.00, Mobile Money, 20 credits, activated |
| Reconciliation audit entry | written with before/after `activated` |

No second charge was created. No credits were granted twice: the grant ledger has
exactly one `grant:package:TFM-...` entry.

## 14. Notification outcomes

| Channel | Status | Evidence |
|---|---|---|
| Owner | **sent** | attempts=1, provider_id `01a1b067-2bc9-7b97-b21e-2aa1c5aa913d` |
| Teacher | **failed / accurately pending** | attempts=5, no provider_id |

The teacher email is pending because the production Resend account is still in
testing mode. Resend returned HTTP 403:

```text
You can only send testing emails to your own email address
(amegayiesaviour@gmail.com). To send emails to other recipients, please verify
a domain at resend.com/domains, and change the `from` address to an email using
that domain.
```

This is an email-provider configuration limitation, not a payment or entitlement
failure. The teacher's in-app package, credits, licence, dashboard and purchase
history are all correct. Delivering the email requires verifying a sending domain
with Resend and updating the production `EMAIL_FROM`; that infrastructure change
was outside this release's authorised scope and was not performed.

## 15. Merge commit

`9824a6d95f33c5447fc24e10e4c25ca34ac3ea9d`
(`Merge pull request #10 from Delkay-byte/feat/oidc-platform-admin-sso`)

## 16. Production deployment

Both services were deployed from the exact merge SHA with the Render API.

| Service | Service ID | Deploy ID | Commit | Status | Finished |
|---|---|---|---|---|---|
| schemeknit-api | `srv-damsbb1ntn7c73d7eg10` | `dep-dbmqmje417fc739ieqe0` | `9824a6d` | live | 2026-11-06T10:28:33Z |
| schemeknit-frontend | `srv-damt6sjm8hqs7398lfl0` | `dep-dbmqmjrbc2fs73amqhjg` | `9824a6d` | live | 2026-11-06T10:28:48Z |

No unreviewed feature-branch SHA was deployed.

## 17. Production health results

| Check | Result |
|---|---|
| `GET /api/health` | 200 `{"status":"healthy",...}` |
| `GET /api/ready` | 200, database reachable, storage reachable, email configured |
| `GET /api/paystack/config-status` | configured=true, environment=live, mode=live, enabled=true, currency=GHS |
| `POST /api/paystack/webhook` without signature | 401 (endpoint present, signature enforced) |
| `GET /api/auth/oidc/status` | `{"enabled":false}` |
| `GET /api/paystack/plans` | Flexible Credit Pack, GHS 12.00, 20 credits, flexible (pricing unchanged) |
| `/`, `/upgrade/`, `/payments/callback/`, `/subscription/`, `/dashboard/` | HTTP 200 |
| Migration log | v052, v053, v054 applied |
| Purchase entitlement coverage | 1/1 successful transactions backfilled |

`PLATFORM_OIDC_ENABLED` remains disabled. Production Paystack secrets, payment
mode, pricing and unrelated product settings were not changed.

## 18. Remaining limitations

1. **Teacher purchase email is pending.** The Resend account is in testing mode
   and only sends to the owner address. Fix requires verifying a sending domain
   and changing `EMAIL_FROM` in production. The transaction, entitlement and
   in-app surfaces are correct; the failure is recorded accurately.
2. **Legacy transaction has no package snapshot.** Identification is conclusive
   from `plan_id`, Paystack metadata and the credit grant key, but the original
   snapshot object is absent in historical data. New purchases capture it.
3. **Migration is forward-only.** Recovery relies on the pre-deployment logical
   backup or redeploying the previous revision. The migration is additive and
   does not modify existing rows.
4. **This report is committed after the production deployment.** It is a
   documentation-only change; production runs the reviewed merge SHA
   `9824a6d95f33c5447fc24e10e4c25ca34ac3ea9d`.

## Status summary

| Dimension | Status |
|---|---|
| Code fixed and verified | Yes |
| CI green on final head | Yes |
| PR #10 merged | Yes |
| Exact `main` SHA deployed | Yes (`9824a6d`) |
| Production health verified | Yes |
| Live payment verified with Paystack | Yes (`6730146887`, GHS 12.00, success) |
| Purchase fulfilled | Yes (20 flexible credits, licence active, no expiry) |
| Teacher account verified in production | Yes |
| Teacher email delivered | No — accurately pending (Resend test-mode restriction) |
| Owner email delivered | Yes |
| Second payment created | No |
