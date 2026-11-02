# SchemeKnit Turnstile Bot Protection

Status: **ACTIVE IN PRODUCTION**. The Cloudflare widget `Schemeknit Production`
is configured, Render has the matching keys, and the backend validates every
token with Siteverify before the protected action continues.

This document separates three things:

- **Production configuration** — what is deployed today.
- **Development-only settings** — the public Cloudflare test keys used by local
  builds and automated tests.
- **Future operational recommendations** — optional improvements, not current
  requirements.

No secret value, invite code, token or credential belongs in this document or in
Git history.

## 1. Design

Cloudflare Turnstile (Free, Managed widget) is independent of Cloudflare's
CDN/proxy. SchemeKnit keeps its Render hosting and DNS. The browser widget only
obtains a short-lived token; the backend is the authority and calls:

`POST https://challenges.cloudflare.com/turnstile/v0/siteverify`

The Siteverify call is server-to-server. The secret key never reaches the
browser. The site key is public and ships in the frontend bundle.

Production values:

| Item | Value |
|---|---|
| Cloudflare widget | `Schemeknit Production` |
| Mode | Managed |
| Approved hostname | `schemeknit-frontend.onrender.com` |
| Siteverify endpoint | `https://challenges.cloudflare.com/turnstile/v0/siteverify` |
| Backend secret variable | `TURNSTILE_SECRET_KEY` |
| Backend public config | `TURNSTILE_SITE_KEY`, `TURNSTILE_ALLOWED_HOSTNAMES`, `TURNSTILE_ENABLED` |
| Frontend public variable | `NEXT_PUBLIC_TURNSTILE_SITE_KEY` |

`TURNSTILE_SECRET_KEY` is backend-only and must remain a Render secret. It must
never be placed in a `NEXT_PUBLIC_*` variable, a source file, a log line or a
test fixture.

## 2. Protected actions

| Action | Entry point | When a challenge is required |
|---|---|---|
| `register` | `POST /api/auth/register/individual` | Always when `TURNSTILE_ENABLED=true`, including invite-only mode |
| `login` | `POST /api/auth/login` | Only after `LOGIN_TURNSTILE_AFTER_FAILURES` recent failures for the account (default 3) |
| `password_reset` | `POST /api/auth/confirm-password-reset` | Always when enabled |

Normal uploads, lesson generation and exports never require a CAPTCHA.
First-time logins stay frictionless. Progressive account lockout and all rate
limits remain in place; Turnstile is an additional layer, not a replacement.

There is no anonymous "request a password reset" endpoint. Reset tokens are
issued by an authenticated school/platform administrator. The public completion
form is protected, and the reset token itself remains single-use and expiring.

Invite-only registration (`REGISTRATION_MODE=invite_only`) requires **both** a
valid Turnstile token and the correct `PILOT_INVITE_CODE`. A valid token never
substitutes for the invite code, and a correct invite code never substitutes for
a valid token.

## 3. Server-side rules

`backend/src/turnstile.py` is the single verification service. Route handlers do
not duplicate Siteverify logic. It enforces:

- token must be a string, non-empty after trimming, and at most **2048
  characters** (Cloudflare's documented maximum);
- a token longer than 2048 characters is rejected before any HTTP request is
  made; it is never truncated or submitted;
- Siteverify must return an explicit JSON `success: true`;
- action must equal the expected action exactly (`register`, `login` or
  `password_reset`);
- hostname must equal an entry in `TURNSTILE_ALLOWED_HOSTNAMES` exactly;
- a SHA-256 digest of every accepted production token is stored in
  `turnstile_tokens` with a unique constraint, so a replay cannot authorise a
  second action;
- the request uses `application/x-www-form-urlencoded` with `secret`, `response`
  and an `idempotency_key`; `remoteip` is included only when a trusted client
  address is available;
- one bounded retry reuses the same `idempotency_key` for the same verification
  attempt;
- the default Siteverify timeout is **10 seconds**
  (`TURNSTILE_TIMEOUT_SECONDS`, allowed range 1–15 seconds);
- network errors, timeouts, HTTP 5xx responses, malformed JSON and missing
  secrets all fail closed with a safe `503 turnstile_unavailable` (or
  `500 turnstile_misconfigured` for an invalid action);
- a non-5xx HTTP error response is still parsed, but only an explicit
  `success: true` can pass; otherwise the result is `400 turnstile_invalid`;
- no provider response body, secret or raw token appears in an HTTP response or
  a log line. Logs record only failure categories and Cloudflare error codes.

Cloudflare enforces the five-minute token lifetime. SchemeKnit keeps its own
digest rows for one hour and removes expired rows opportunistically.

A successful-looking browser callback is never accepted without Siteverify.

### Client IP handling

`remoteip` is optional. SchemeKnit uses `client_ip()` in `backend/src/security.py`,
which reads forwarded headers only when the direct socket peer is in the explicit
`TRUSTED_PROXY_CIDRS` allowlist. Otherwise it uses the direct peer address.
Arbitrary client-supplied `X-Forwarded-For` values are never trusted.

## 4. Frontend

`frontend/src/components/turnstile-widget.tsx`:

- loads `https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit`
  once;
- renders a Managed widget with the public site key and the action name;
- exposes loading, success, expired and error states with `aria-live`;
- provides a keyboard-operable "Retry verification" action;
- removes and re-renders the widget after every failed or completed submit,
  because a Turnstile token is single-use;
- prevents duplicate submission while no valid token is present;
- renders nothing when no public site key is configured (local development).

`NEXT_PUBLIC_TURNSTILE_SITE_KEY` is the only browser-visible Turnstile value.

CSP additions (frontend `next.config.js`), nothing broader:

```text
script-src 'self' 'unsafe-inline' https://challenges.cloudflare.com
connect-src ... https://challenges.cloudflare.com
frame-src ... https://challenges.cloudflare.com
```

`unsafe-eval` is not added.

## 5. Privacy

The privacy policy discloses that Cloudflare Turnstile processes browser
signals, IP address and challenge results to distinguish people from bots, acts
as a service provider, and may process data outside the user's country. It does
not describe the data as advertising or profile data.

## 6. Production configuration (already deployed)

The following Render backend variables are set for `schemeknit-api`:

- `TURNSTILE_ENABLED=true`
- `TURNSTILE_SECRET_KEY` — secret, backend only
- `TURNSTILE_SITE_KEY` — public site key
- `TURNSTILE_ALLOWED_HOSTNAMES=schemeknit-frontend.onrender.com`
- optional: `TURNSTILE_TIMEOUT_SECONDS` (default 10),
  `LOGIN_TURNSTILE_AFTER_FAILURES` (default 3)

The frontend service `schemeknit-frontend` sets:

- `NEXT_PUBLIC_TURNSTILE_SITE_KEY` — public site key

The backend refuses to start in a non-debug profile when
`TURNSTILE_ENABLED=true` and the secret, site key or allowed-hostname list is
missing. Do not rotate, replace or recreate the widget or its keys as part of a
code change. Do not add hostnames casually: add one exact hostname at a time in
Cloudflare and in `TURNSTILE_ALLOWED_HOSTNAMES`.

## 7. Development and test settings

Local and automated tests use Cloudflare's documented public test keys. They are
not production keys and carry no authority.

- Site keys (public):
  - `1x00000000000000000000AA` — visible, always passes
  - `2x00000000000000000000AB` — visible, always blocks
  - `1x00000000000000000000BB` — invisible, always passes
  - `3x00000000000000000000FF` — forces an interactive challenge
- Secrets (test only):
  - `1x0000000000000000000000000000000AA` — always passes
  - `2x0000000000000000000000000000000AA` — always fails
  - `3x0000000000000000000000000000000AA` — token already spent

The public test site key returns the same dummy token for every widget and does
not report a consistent action/hostname. SchemeKnit therefore skips replay
storage and action/hostname matching **only** when the configured secret is one
of the documented test secrets. A production secret always enforces all rules;
this exception cannot be reached by a production deployment.

Local development may run with `TURNSTILE_ENABLED=false`, which keeps forms
usable without a widget. `localhost` and `127.0.0.1` are never added to the
production hostname allowlist.

## 8. Troubleshooting

Check the backend log category first. Logs intentionally contain no token,
secret or provider response body.

| Symptom | Meaning | Action |
|---|---|---|
| `turnstile_required` (428) | No token reached the backend | Confirm the frontend read `cf-turnstile-response` and included `turnstile_token` in the JSON payload |
| `turnstile_invalid` (400) | Cloudflare rejected the token, or the token exceeded 2048 characters | Complete the widget again; do not reuse an old or truncated token |
| `turnstile_hostname_mismatch` (400) | Widget hostname is not in `TURNSTILE_ALLOWED_HOSTNAMES` | Add the exact frontend hostname in Cloudflare and Render |
| `turnstile_action_mismatch` (400) | Widget action differs from the endpoint's expected action | Align `action` in the widget with `register`, `login` or `password_reset` |
| `turnstile_replay` (400) | The same token was submitted twice | Expected single-use behaviour; reset the widget |
| `turnstile_unavailable` (503) | Secret missing, Siteverify timed out, network failed, HTTP error or malformed JSON | Check Render secrets and network; the request fails closed, never open |
| `turnstile_misconfigured` (500) | A route requested an unknown action | Fix the route; never add an action casually |

Timeouts and network failures are retryable. Tell the user to retry after a
moment. Do not add a fallback that accepts the request when Cloudflare is
unreachable.

## 9. Analytics

Turnstile Analytics in the Cloudflare dashboard reports challenges issued and
solved, browser source, and token validation outcomes. Treat these as separate
signals:

- **Challenges issued** are not Siteverify requests.
- **Challenges solved** are not necessarily successfully validated tokens.
- **Token validation** separately distinguishes requests, valid tokens and
  invalid tokens.
- Browser labels such as Electron, HeadlessChrome and Chrome Mobile are source
  categories, not proof of malicious traffic. Do not block a browser category or
  change challenge mode solely to improve a displayed solve rate.

To review production behaviour, open Cloudflare Dashboard → Turnstile →
`Schemeknit Production` → Analytics, then compare the challenge counts with the
token-validation panel for the same period. Backend logs record the safe failure
category (`turnstile_siteverify_rejected`, `turnstile_action_mismatch`,
`turnstile_hostname_mismatch`, `turnstile_token_replay`,
`turnstile_siteverify_unavailable`, `turnstile_secret_missing`) without token or
secret values.

## 10. Tests and evidence

`backend/tests/test_turnstile.py` covers:

- acceptance of a valid token;
- missing, empty, whitespace, non-string, oversized (2049) and invalid tokens;
- the exact 2048-character boundary;
- expired tokens and replayed tokens;
- hostname and action mismatch;
- Siteverify timeout, connection error, HTTP server error, HTTP client error,
  malformed JSON and non-object JSON;
- a missing backend secret failing closed without any HTTP request;
- the 10-second default and an explicitly configured timeout;
- rejection of out-of-range timeout configuration;
- registration, risk-triggered login and password-reset enforcement;
- invite-only interaction (a valid token does not replace the invite code, and
  the invite code does not replace a valid token);
- disabled Turnstile in local builds;
- CSP permitting Turnstile without `unsafe-eval`.

All Siteverify calls in automated tests are mocked. Tests never send traffic to
live Cloudflare.

Production verification has been performed separately with a real widget token:
a genuine token passed Siteverify and was then rejected by the invite-only gate
(no account created), and a replay of the same token returned
`turnstile_replay`. A dummy token returned `turnstile_invalid`, proving the
backend called Cloudflare rather than only checking token presence.

## 11. Residual limitations and future recommendations

- Dashboard Siteverify counters are only visible in Cloudflare Analytics; they
  are not exposed by the application.
- A Cloudflare outage pauses protected forms (fail closed) rather than silently
  disabling bot protection.
- Future: add alerting on sustained `turnstile_unavailable` rates.
- Future: review Analytics monthly for challenge solve rate and validation
  failures; do not tune challenge mode from a single day's sample.
- Future: if a custom domain replaces the Render hostname, add it explicitly in
  both Cloudflare and `TURNSTILE_ALLOWED_HOSTNAMES`.
