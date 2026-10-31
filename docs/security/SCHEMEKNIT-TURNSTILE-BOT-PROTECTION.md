# SchemeKnit Turnstile Bot Protection

Status: **IMPLEMENTED AND LOCALLY VERIFIED; PRODUCTION ACTIVATION REQUIRED**.
No Cloudflare widget was created and no production key is present in this
repository. Production bot protection is not active until the owner completes
the activation steps in section 6.

## 1. Design

Cloudflare Turnstile (Free, Managed widget) is independent of Cloudflare's
CDN/proxy. SchemeKnit keeps its Render hosting and DNS. The browser widget only
obtains a short-lived token; the backend is the authority and calls:

`POST https://challenges.cloudflare.com/turnstile/v0/siteverify`

The secret key is backend-only. The site key is public and ships in the
frontend bundle.

## 2. Protected actions

| Action | Entry point | When a challenge is required |
|---|---|---|
| `register` | `POST /api/auth/register/individual` | Always when `TURNSTILE_ENABLED=true`, including invite-only mode |
| `login` | `POST /api/auth/login` | Only after `LOGIN_TURNSTILE_AFTER_FAILURES` recent failures for the account (default 3) |
| `password_reset` | `POST /api/auth/confirm-password-reset` | Always when enabled |

Normal uploads, lesson generation and exports never require a CAPTCHA.
Normal first-time logins stay frictionless. The progressive account lockout and
all rate limits remain in place; Turnstile is an additional layer.

There is no anonymous "request a password reset" endpoint in SchemeKnit:
reset tokens are issued by an authenticated school/platform administrator. The
public completion form is protected instead, and the reset token itself remains
single-use and expiring.

## 3. Server-side rules

`backend/src/turnstile.py` enforces:

- token presence, maximum length and a single configured action;
- Siteverify `success: true`;
- exact action match (`register` ≠ `login` ≠ `password_reset`);
- exact hostname match against `TURNSTILE_ALLOWED_HOSTNAMES`;
- a SHA-256 digest of every accepted token stored in `turnstile_tokens` with a
  unique constraint, so the same token cannot authorise a second action even if
  Siteverify were replayed;
- a bounded Siteverify timeout (`TURNSTILE_TIMEOUT_SECONDS`, default 5 s) and
  one retry with a stable idempotency key;
- fail-closed 503 `turnstile_unavailable` when Siteverify cannot be reached;
- no provider response internals, secret or raw diagnostic in the HTTP body.

Cloudflare enforces the five-minute token lifetime. SchemeKnit additionally
rejects its own digest rows after one hour and cleans expired rows
opportunistically.

A successful-looking browser callback is never accepted without Siteverify.

## 4. Frontend

`frontend/src/components/turnstile-widget.tsx`:

- loads `https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit`
  once;
- renders a Managed widget with the public site key and the action name;
- exposes loading, success, expired and error states with `aria-live`;
- provides a keyboard-operable "Retry verification" action;
- resets after every failed submit, because a Turnstile token is single-use;
- prevents duplicate submission while no valid token is present;
- is responsive and uses Cloudflare's accessible widget;
- renders nothing when no public site key is configured (local development).

`NEXT_PUBLIC_TURNSTILE_SITE_KEY` is the only browser-visible value.

CSP additions (frontend `next.config.js`), nothing broader:

```text
script-src 'self' 'unsafe-inline' https://challenges.cloudflare.com
connect-src ... https://challenges.cloudflare.com
frame-src ... https://challenges.cloudflare.com
```

`unsafe-eval` is not added.

## 5. Privacy

The privacy policy now discloses that Cloudflare Turnstile processes browser
signals, IP address and challenge results to distinguish people from bots, acts
as a service provider, and may process data outside the user's country. It does
not claim that Cloudflare performs no processing and does not describe the data
as advertising/profile data.

## 6. Owner activation steps (Cloudflare + Render)

1. In the Cloudflare dashboard open **Turnstile → Add widget**.
2. Name: `SchemeKnit Production`.
3. Widget mode: **Managed**.
4. Hostnames: add only `schemeknit-frontend.onrender.com` (the existing Render
   frontend host). Do not add wildcards or unrelated domains. Add a future
   custom domain explicitly, one exact hostname at a time.
5. Copy the **site key** and **secret key**.
6. Render backend environment:
   - `TURNSTILE_ENABLED=true`
   - `TURNSTILE_SECRET_KEY=<secret>` (backend only, never in Git or the bundle)
   - `TURNSTILE_SITE_KEY=<site key>`
   - `TURNSTILE_ALLOWED_HOSTNAMES=schemeknit-frontend.onrender.com`
   - optional: `TURNSTILE_TIMEOUT_SECONDS=5`,
     `LOGIN_TURNSTILE_AFTER_FAILURES=3`
7. Render frontend environment:
   - `NEXT_PUBLIC_TURNSTILE_SITE_KEY=<site key>`
8. Redeploy frontend and backend. The backend refuses to start in a
   non-debug profile when `TURNSTILE_ENABLED=true` and either key or the
   allowed-hostname list is missing.
9. Register a real test account, complete the visible challenge, and confirm a
   second replay of the same token is rejected.
10. Trigger three failed logins on a test account, then confirm the login page
    shows the challenge and a correct password succeeds after verification.

The Cloudflare API token available to the project was not shown to have
Turnstile widget-management permission, so no widget was created
automatically. No broader account permission was requested.

## 7. Testing keys

- Site keys (public):
  - `1x00000000000000000000AA` — visible, always passes
  - `2x00000000000000000000AB` — visible, always blocks
  - `1x00000000000000000000BB` — invisible, always passes
  - `3x00000000000000000000FF` — forces an interactive challenge
- Secrets (test only):
  - `1x0000000000000000000000000000000AA` — always passes
  - `2x0000000000000000000000000000000AA` — always fails
  - `3x0000000000000000000000000000000AA` — token already spent

These are Cloudflare's documented public test values and appear only in test
configuration. Production secrets are never used in tests or committed.

The public test site key returns the same dummy token for every widget and does
not report a consistent action/hostname. SchemeKnit therefore skips replay
storage and action/hostname matching **only** when the configured secret is one
of the documented test secrets. A production secret always enforces all rules;
this exception cannot be reached by a production deployment.

## 8. Tests and evidence

`backend/tests/test_turnstile.py` (15 tests) proves:

- a valid test token permits the intended action;
- missing, invalid and expired tokens are rejected;
- a replayed token is rejected;
- a token issued for a different action is rejected;
- a token issued for a different hostname is rejected;
- registration cannot bypass verification by calling the API directly;
- a verified registration succeeds;
- a normal login needs no challenge;
- the login challenge appears after repeated failures;
- registration tokens cannot be reused for login;
- Siteverify timeout fails closed with 503;
- disabled Turnstile keeps local flows working;
- CSP permits Turnstile without `unsafe-eval`.

Browser acceptance for the registration and challenge-triggered login flows is
implemented in `frontend/e2e/turnstile-auth.js`. Against a local backend with
the documented test keys and a frontend built with the test site key, the run
passed:

```text
PASS  desktop: registration passed with a Turnstile token
PASS  desktop: login challenge appeared and verified
PASS  mobile: registration passed with a Turnstile token
PASS  mobile: login challenge appeared and verified
4 passed, 0 failed
```

This proves the widget, form submission and risk-triggered login UI work at
1440 px and 390 px. It does not prove production activation: a real widget token
must still be validated after the owner configures the production site key and
secret.

## 9. Residual limitations

- Production activation depends on the Cloudflare widget and Render secrets.
- The in-repo Siteverify test mocks the Cloudflare response; a real token from
  the production widget has not been validated yet.
- A Cloudflare outage pauses protected forms (fail closed) rather than silently
  disabling bot protection.
