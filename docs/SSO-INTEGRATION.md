# SchemeKnit SSO Integration — Platform-Admin OIDC (BloomCore Identity)

Status: Phase 1, web-only, **feature-flagged OFF by default**.

This document describes the OIDC single-sign-on adapter that lets the
BloomCore owner sign in to the SchemeKnit platform admin console through the
central identity provider ("BloomCore Identity", Authentik) managed by the
BloomCore Control Center.

---

## 1. Design summary

- **Protocol**: OpenID Connect Authorization Code flow with PKCE (S256).
  The product is a confidential client (client_id + client_secret).
- **Token validation** (`backend/src/oidc_client.py`): the ID token's RS256
  signature is verified against the IdP JWKS (`PyJWKClient`), with an exact
  issuer match, `aud == client_id`, `exp`/`iat` with 30 s leeway, mandatory
  `sub`/`email` claims and a **single-use `nonce`** bound to the flow cookie.
- **Flow state** (state, nonce, PKCE verifier, expiry ≤ 10 min) lives in a
  short-lived `HttpOnly`, `SameSite=Lax` cookie (`Secure` in production),
  URL-encoded JSON, path-scoped to `/api/auth/oidc`. It is **cleared on the
  callback regardless of outcome**; the authorization code itself is single
  use at the IdP.
- **Native sessions**: nothing changes about what a SchemeKnit session is.
  After SSO the backend mints the *same* first-party JWT + server-side
  `user_sessions` row it mints after a password login (`create_user_token` /
  `create_session_record`). The frontend stores it in sessionStorage exactly
  like a normal login.
- **Linking**: SchemeKnit never guesses which central identity may administer
  it. The authoritative mapping lives in the Control Center
  (`ProductAdminAssociation`). The product asks the Control Center at login
  time via server-to-server calls authenticated with the per-product API key
  (`x-product-key` header); the key never leaves the backend.

### Account linking flow

```
Browser                SchemeKnit backend             Control Center (CC)
  │  GET /api/auth/oidc/start
  │─────────▶ set sk_oidc_flow cookie, 303 ──▶ BloomCore Identity (/authorize)
  │  IdP authenticates the owner, 302 ──▶ /api/auth/oidc/callback?code&state
  │─────────▶ validate state/nonce/ID token (JWKS), require 2nd factor amr
  │           GET  /api/v1/products/schemeknit/linking/resolve?email=…
  │───────────────────────────────────────────────────▶
  │           ◀── { status: none | pending | verified, identity_sub, email }
  │
  │  status = verified AND local link row exists
  │            ──▶ mint native session, 303 /login/platform-admin/sso/complete#token=…
  │
  │  status = pending (or verified-but-no-local-row: self-healing)
  │            ──▶ 303 /login/platform-admin/sso/confirm?attempt=<one-time token>
  │  POST /api/auth/oidc/confirm { attempt, password }
  │            ──▶ verify EXISTING local platform-admin password (bcrypt)
  │               insert platform_admin_oidc_links row
  │               POST /api/v1/products/schemeknit/linking/confirm
  │                  payload = JSON{product, identity_sub, email,
  │                                  product_admin_email, ts}   (sorted keys)
  │                  signature = HMAC-SHA256(payload, product API key)
  │───────────────────────────────────────────────────▶
  │            ──▶ mint native session, return standard login response
  │
  │  status = none ──▶ 403 "This identity is not authorised for SchemeKnit
  │                      administration." + audit event, NO session.
```

### MFA reconciliation (fail closed)

The IdP attests the authentication methods used in the `amr` claim (e.g.
`["pwd","otp"]`, `["pwd","webauthn"]`, `["mfa"]`). SchemeKnit stores `amr` on
the minted JWT (only the OIDC callback sets it — the claim is never
client-suppliable).

`require_platform_admin` (`backend/src/auth.py`) accepts the gate when
either:

1. the user has a **local TOTP enrollment** (`mfa_enabled`, unchanged
   behavior), or
2. the **current token** carries an IdP-attested second factor
   (`amr ∈ {mfa, otp, totp, webauthn, fido2, u2f, passkey, sms, hwk, pop,
   duo, push}`).

A password-only amr (`["pwd"]`), an absent amr, or a locally-minted token
without amr fails closed, exactly as before. Local TOTP users are unaffected.

### What is audited / rate limited

- Structured security logs (`log_security`) on every step: flow start,
  callback failures, MFA-not-attested, identity-not-authorised, link
  confirmation start/success/failure, login success/denied.
- Platform audit rows (`platform_audit_logs`) for user-attributed events:
  `platform_admin_oidc_login`, `platform_admin_oidc_link_created`,
  `platform_admin_oidc_link_denied`. Pre-auth denials (unknown/unlinked
  identity) are logged via `log_security` only — there is no user row to
  attribute.
- `/start` and `/callback` reuse the `login_security` progressive-cooldown
  primitives keyed by source IP; `/confirm` keys failures on the resolved
  account exactly like the regular login (same lockout steps and
  `Retry-After` semantics).

### Logout

On logout of an SSO-created session (token carries `amr`), the backend
triggers a **best-effort, non-blocking** revocation at the IdP revocation
endpoint. Phase 1 never stores IdP refresh tokens, so the hook is currently a
safeguarded no-op; it becomes active automatically when refresh-token storage
is added. Local logout semantics (jti revocation, session end) are unchanged.

---

## 2. Configuration (env vars)

All settings live in `backend/src/config.py` under the `PLATFORM_OIDC_`
prefix. **Everything defaults to OFF/empty** — with no configuration, the
adapter is inert and every endpoint under `/api/auth/oidc` returns 404.

| Variable | Default | Meaning |
|---|---|---|
| `PLATFORM_OIDC_ENABLED` | `false` | Master feature flag. |
| `PLATFORM_OIDC_ISSUER` | `http://localhost:9000/application/o/schemeknit/` | IdP issuer; must match the token `iss` exactly (trailing slash included). |
| `PLATFORM_OIDC_CLIENT_ID` | `schemeknit-sso` | OAuth2 client id registered on the IdP. |
| `PLATFORM_OIDC_CLIENT_SECRET` | *(empty)* | OAuth2 client secret. Never commit; set via environment. |
| `PLATFORM_OIDC_SCOPES` | `openid email profile` | Requested scopes. |
| `PLATFORM_OIDC_LINKING_API_KEY` | *(empty)* | The Control Center's per-product key for `schemeknit` (from CC `CC_PRODUCT_API_KEYS`). |
| `PLATFORM_OIDC_LINKING_BASE_URL` | `http://localhost:8400` | Control Center backend base URL. |
| `PLATFORM_OIDC_FLOW_TTL_SECONDS` | `600` | Flow cookie / attempt-token lifetime; hard-capped at 600 s. |

Local development values live in `backend/.env.oidc.local` (git-ignored);
copy them into your shell or `.env` to run the feature locally.

### Production validation

When `PLATFORM_OIDC_ENABLED=true` in a non-debug, non-desktop deployment,
`validate_production()` refuses to boot unless the issuer is `https://` and
both the client secret and the linking API key are set. Desktop mode
(`DESKTOP_MODE=1`) keeps booting with the feature OFF (default) and never
runs these checks.

---

## 3. Backend surface

Mounted at `/api/auth/oidc` (`backend/src/routers/auth_oidc.py`):

| Endpoint | Auth | Behavior |
|---|---|---|
| `GET /status` | none | `{ "enabled": bool }` probe for the login page. |
| `GET /start` | none | 404 when disabled. Creates PKCE flow + cookie, 303 → IdP. |
| `GET /callback` | none | Validates flow cookie, code, ID token, amr; resolves linking; outcomes above. Always clears the flow cookie. |
| `POST /confirm` | none (attempt token + confirm cookie) | Completes the pending link with the existing local password. Returns the standard login response `{access_token, token_type, user, mfa_enrollment_required}`. |

Migration `v052_platform_admin_oidc_links` (runner auto-discovers
`src/migrations/v052_*.py` after v051) adds:

```
platform_admin_oidc_links(
  id PK, user_id FK→users(id), issuer, idp_sub UNIQUE,
  linked_at, linked_via ('local_credential_proof'), created_by)
```

No existing table or column is modified. Local password + TOTP login paths
are untouched; with the flag off, nothing in the request path changes.

---

## 4. Frontend surface (minimal)

- `/login/platform-admin` — shows a **"Sign in with BloomCore Identity"**
  button only when `GET /api/auth/oidc/status` reports `enabled`
  (`frontend/src/components/role-login.tsx`). The button is a full-page
  navigation to `/api/auth/oidc/start`.
- `/login/platform-admin/sso/confirm` — password form for the link
  confirmation step (posts `attempt` + password to `POST /api/auth/oidc/confirm`,
  `credentials: 'include'` so the backend-origin confirm cookie rides along).
- `/login/platform-admin/sso/complete` — reads the native access token from
  the **URL fragment** (`#token=…`), immediately strips the hash via
  `history.replaceState`, fetches `/api/auth/me`, stores
  `teachflow_token`/`teachflow_user` in sessionStorage (identical to a
  password login) and navigates to the console. The fragment (never a query
  parameter) is used so the token is not transmitted to any server or logged
  by proxies.

---

## 5. Local end-to-end verification (Authentik)

Prereqs: Authentik at `http://localhost:9000` with the `schemeknit-sso`
OAuth2 provider (redirect URI `http://localhost:8000/api/auth/oidc/callback`,
strict), Control Center backend at `http://localhost:8400` with a *pending*
or *verified* association for the owner identity.

1. Start the backend with the feature on:

   ```
   cd backend
   set PLATFORM_OIDC_ENABLED=true
   set PLATFORM_OIDC_LINKING_API_KEY=<schemeknit key from CC .env>
   python -m uvicorn src.main:app --port 8000
   ```

2. Drive the flow with a script (requests/httpx): GET `/api/auth/oidc/start`
   → follow to the IdP authorize URL → authenticate as the Authentik test
   user → capture the `code`/`state` redirect → call `/callback` → exchange
   the fragment token for `/api/auth/me`.

   A worked script lives in `backend/scripts/oidc_local_flow.py` (see that
   file for the exact steps, the Authentik/Control Center test identities it
   uses, and its output). When port 8000 is taken by another dev server, boot
   the backend on another port (e.g. 8010), set `API_BASE_URL` accordingly and
   register `http://localhost:<port>/api/auth/oidc/callback` as an additional
   STRICT redirect URI on the IdP provider.

3. Expected result: a 200 from `/api/auth/me` with `role: "platform_admin"`,
   a `user_sessions` row server-side, and audit/security log entries
   `oidc_login_success`.

## 6. Known limitations

- **Web-only.** The desktop (Electron) build and any non-browser client are
  out of scope for Phase 1; desktop mode never enables the flag.
- **Turnstile is bypassed by design on the OIDC path.** The IdP already
  performs bot/account security at the central sign-in; adding Turnstile to
  `/start`/`/callback` would double-challenge the owner. Progressive
  cooldown / lockout still applies to these endpoints.
- **Phase 1 stores no IdP refresh token**, so IdP-side revocation at logout
  is a safeguarded no-op (see Logout above).
- **`mfa_enrollment_required` surfaces** (school-admin dependency paths)
  still require local TOTP for platform admins; only
  `require_platform_admin` reconciles IdP `amr` evidence.
- The OIDC path never creates users: an identity is authorised only if the
  Control Center has a declared association AND the local platform-admin
  account exists (and, for the pending path, its password is proven).

## 7. Rollback

Set `PLATFORM_OIDC_ENABLED=false` (or unset it) and restart. Every
`/api/auth/oidc` endpoint returns 404, the login page button disappears, and
the platform admin falls back to the unchanged local password + TOTP login.
The `platform_admin_oidc_links` table is dormant data; no code path reads it
while the flag is off. No migration rollback is required (and by convention
`down()` is a no-op).
