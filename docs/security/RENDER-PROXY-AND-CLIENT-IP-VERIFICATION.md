# Render Proxy and Client-IP Verification

Date: 2026-10-31  
Scope: SchemeKnit FastAPI backend on Render, rate-limit client identity, and
forwarded-header trust. Read-only infrastructure investigation; no production
environment change, deployment or rate-limit exhaustion was performed.

## Decision

**Production forwarded-header trust remains DISABLED. Live topology is BLOCKED.**

`TRUST_PROXY_HEADERS=false` remains the default, and the Render services are not
configured to trust forwarded headers. The code now fails closed and has a
right-to-left trusted-chain parser ready for a future verified proxy range, but
Render does not publish the inbound proxy CIDRs or forwarded-header behaviour
needed to enable it safely.

## 1. What Render documents

| Claim | Official evidence | Verdict |
|---|---|---|
| Public HTTPS terminates at Render's managed load balancer; the app receives HTTP on its bound port | [Render Web Services](https://render.com/docs/web-services): "Render's load balancer terminates SSL for inbound HTTPS requests, then forwards those requests to your web service over HTTP." The app port "is not directly reachable via the public internet." | Documented |
| Render publishes outbound IP ranges | [Outbound IP Addresses](https://render.com/docs/outbound-ip-addresses) | Documented, but **outbound only** |
| Outbound ranges can be reused as inbound proxy ranges | The same page describes ranges used by services *sending* traffic; it does not describe the load balancer's inbound source addresses | **No** |
| Render publishes stable inbound proxy CIDRs | No inbound proxy CIDR list found in the Web Services or Outbound IP pages | **Not published** |
| Render documents whether it sets/overwrites/appends `X-Forwarded-For` | No statement found in the reviewed Web Services, Outbound IP or Inbound IP pages | **Not published** |
| Render inbound IP rules are a proxy allowlist | [Inbound IP Rules](https://render.com/docs/inbound-ip-rules) are an allowlist of *client* ranges on Scale/Enterprise, not the source ranges of Render's proxy | **Different feature** |
| A trusted proxy count is documented | No official hop-count contract found | **Not proven** |
| Render's FastAPI guidance recommends restricting `--forwarded-allow-ips` to proxy IPs/CIDRs | [Render FastAPI production article](https://render.com/articles/fastapi-production-best-practices), 2026-09-29 | General guidance only; no SchemeKnit-specific ranges |

Sources accessed: 2026-10-31.

## 2. Topology findings

Confirmed from documentation:

```
Client
  │ HTTPS
  ▼
Render managed load balancer (TLS termination)
  │ HTTP
  ▼
SchemeKnit FastAPI on 0.0.0.0:$PORT
```

Confirmed from the Render API for `schemeknit-api`:

- Service type: `web_service`
- Runtime: `python`
- Plan: `free`
- Region: `oregon`
- Public URL: `https://schemeknit-api.onrender.com`
- Start command: `cd backend && python -m uvicorn src.main:app --host 0.0.0.0 --port $PORT`
- No persistent disk; no private service; no alternative public port exposed.

Not confirmed:

- The actual value FastAPI receives as `request.client.host`.
- Whether that value is a Render proxy, a per-instance sidecar, or another
  address.
- Whether Render supplies `X-Forwarded-For`.
- Whether Render overwrites or appends to a client-supplied
  `X-Forwarded-For`.
- Whether a forged header reaches the application unchanged.
- Whether the direct peer is stable enough for a CIDR allowlist.
- Whether a fixed proxy-hop count is safe.

A DNS lookup of `schemeknit-api.onrender.com` only proves the public edge
address. It does not prove the source address of the HTTP connection FastAPI
sees, and it is not used as proxy evidence here.

## 3. Risk of the current default

With trust disabled, `client_ip()` returns the direct socket peer. If Render's
load balancer is the direct peer for all requests, all teachers share one
rate-limit bucket. That is **fail-closed but not client-distinguishing**: a
single abusive client can consume the shared bucket and cause collateral 429s
for others.

This is preferable to trusting a forged header. It is why account-scoped
lockout and per-user budgets remain essential.

## 4. Code behaviour after hardening

`backend/src/security.py`:

- `TRUST_PROXY_HEADERS=false` remains the default.
- Startup validation (`backend/src/config.py`) rejects:
  - `TRUST_PROXY_HEADERS=true` with an empty `TRUSTED_PROXY_CIDRS`;
  - malformed CIDRs;
  - `0.0.0.0/0` and `::/0`;
  - empty entries in the CIDR list.
- `_trusted_proxy()` trusts only the direct peer when it is inside an explicitly
  configured CIDR.
- `_normalize_ip()` handles IPv4, IPv6, bracketed IPv6 with a port, IPv4 with a
  port, and IPv4-mapped IPv6 (`::ffff:192.0.2.1` -> `192.0.2.1`).
- `_forwarded_chain()`:
  - reads every `X-Forwarded-For` field;
  - limits fields to 8, total characters to 2,048, hops to 32, and each value
    to 128 characters;
  - rejects malformed/oversized chains and falls back to the direct peer;
  - does not use the RFC 7239 `Forwarded` header, because Render's maintenance
    of it is undocumented.
- `client_ip()` walks the chain **right-to-left** and returns the first hop that
  is not a verified trusted proxy. It never blindly returns the leftmost value.
- A direct peer that is not a valid IP (test clients, embedded servers) is kept
  as an opaque value for one shared bucket; it is never treated as trusted.
- `client_key()` HMACs the address before it is used in the shared counter table
  or security logs.
- Loopback rate-limit exemptions apply only when `DEBUG=true`; production does
  not exempt `127.0.0.1` or `::1`.
- `enforce_authenticated_budget()` adds per-account budgets independent of IP:
  - upload: 10 / 15 minutes
  - generate: 20 / 10 minutes
  - resume: 10 / 10 minutes
  - export: 30 / 10 minutes
  - shared-store failure returns 503 for these expensive operations.

## 5. Spoofing and parser tests

`backend/tests/test_client_ip_proxy.py` — 34 tests, all passing.

Covered:

- Direct request with no forwarded headers.
- Untrusted peer with one forged XFF value.
- Untrusted peer with multiple XFF values.
- Untrusted peer with multiple XFF header fields.
- Untrusted peer with a forged RFC 7239 `Forwarded` header.
- Trust disabled with valid-looking headers.
- Trusted peer, single client.
- Trusted multi-proxy chain.
- Trusted chain with untrusted intermediate (returns the intermediate).
- IPv6 client.
- IPv4-mapped IPv6.
- Empty, malformed and overlong headers.
- Excessive hops.
- Trusted peer outside the configured allowlist.
- Trust enabled with empty/invalid/wildcard CIDRs.
- Config changes not broadening trust.
- HMAC client keys and independent account keys.
- Distinct verified clients with separate buckets.
- Forged headers not creating new identities.
- Per-account budget independent of source IP.
- Shared-store failure returns 503 on high-risk routes and leaves low-risk
  routes working.
- Loopback exemption only in debug mode.

Related existing tests:

- `tests/test_login_lockout.py` — 7 passed, including forged-header rejection.
- `tests/test_security_hardening.py` — 42 passed, including 429/CORS and
  limiter-store fail-closed behaviour.
- Full backend suite — run after this change (see §8).

## 6. Account and endpoint abuse protection

Retained:

- Per-account progressive login lockout (`login_security.py`), independent of IP.
- Shared database-backed IP counters (`DbRateLimiter`).
- High-risk middleware fail-closed 503 when the shared limiter store errors.
- Per-user budgets for upload/generate/resume/export, independent of IP.
- AI quotas, credits and bounded provider retries.
- Upload size/container validation and generation locks.

This means an attacker cannot bypass all throttling merely by changing
`X-Forwarded-For`, rotating IPs, or switching between anonymous and
authenticated routes. They still hit account lockout, per-user budgets and
business quotas.

## 7. Runtime verification status

**BLOCKED.** No isolated staging service exists yet, and production diagnostics
were deliberately not deployed.

Required staging procedure:

1. Create an isolated staging FastAPI service on Render with the same runtime
   and start command. Do not use production.
2. Add a staging-only, owner-protected diagnostic that returns
   `request.client.host` and whether `X-Forwarded-For` was present (never log
   full production headers or secrets).
3. Send requests from two independent client networks.
4. Send the same requests with forged `X-Forwarded-For` values and duplicate
   header fields.
5. Record the direct peer for each request and compare it with the public edge.
6. Confirm whether Render overwrites, appends or ignores XFF.
7. If the direct peer is stable and documented, configure the narrowest
   verified CIDR and re-run the spoofing matrix.
8. Verify two clients get distinct limiter buckets and a forged header cannot
   change the bucket.
9. Verify account lockout still works independently.

If Render cannot provide a stable, documented ingress range or refuses to
confirm the behaviour, keep `TRUST_PROXY_HEADERS=false`. Do not infer CIDRs from
one observed address, DNS, outbound ranges, or Cloudflare ranges.

## 8. Test evidence

| Check | Result |
|---|---|
| New proxy/client-IP tests | 34 passed |
| Login lockout + hardening + proxy tests | 83 passed |
| Upload/IDOR targeted suite | 99 passed |
| Generation/export/upload targeted suite | 95 passed |
| Full backend suite | **2999 passed, 21 skipped, 0 failed** |

## 9. Privacy and logging

- Rate-limit counters and security logs use `client_key()` HMAC, not raw IPs.
- The middleware no longer logs the raw `client` value.
- `SECURITY_HMAC_KEY` is preferred; `SECRET_KEY` is the development fallback.
  Rotating the key resets HMAC-derived counter identities.
- No raw IP is added to user-facing responses.

## 10. Residual risks

1. **Production client distinctness is unverified.** If all requests share the
   load-balancer peer, IP buckets are shared. Account and per-user limits reduce
   impact but do not restore per-client IP fairness.
2. **No stable inbound CIDR or hop count is proven.** Trust must stay off.
3. **RFC 7239 `Forwarded` is intentionally ignored.** If Render later adopts it,
   a separate verified change is required.
4. **The per-user budgets are new policy values.** They should be reviewed
   against real pilot usage before launch.
5. **No staging browser/load test exists yet.** Runtime verification remains
   BLOCKED.

## 11. Files and references

- `backend/src/security.py`
- `backend/src/config.py`
- `backend/src/routers/documents.py`
- `backend/src/routers/generation.py`
- `backend/.env.example`
- `backend/tests/test_client_ip_proxy.py`
- `backend/tests/test_security_hardening.py`
- `backend/tests/test_login_lockout.py`
- `docs/security/SCHEMEKNIT-ASVS-5-AND-API-TOP10-GAP-ASSESSMENT.md`
- `docs/roadmap/SCHEMEKNIT-SECURITY-SEO-RELEASE-CHECKLIST.md`
