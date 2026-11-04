"""Local end-to-end driver for the platform-admin OIDC SSO flow.

Drives a REAL login against the local stack, with no browser:

  1. Ensures an Authentik test user (``sk-sso-test``) exists and sets its
     password via the Authentik API.
  2. Enrolls a TOTP device for that user by driving the Authentik
     device-enrollment flow through the flow executor API (so the IdP
     attests a second factor in ``amr``).
  3. Logs in to the BloomCore Control Center (OIDC drive of the CC's own
     login) as the bootstrap owner and declares a PENDING product-admin
     association for the test user's email.
  4. Runs the SchemeKnit SSO flow against a locally running backend:
     /api/auth/oidc/start -> Authentik (identification, password, TOTP) ->
     /api/auth/oidc/callback -> (pending) -> POST /api/auth/oidc/confirm with
     the LOCAL platform-admin password -> native session minted.
  5. Verifies the minted token with /api/auth/me and re-checks the CC
     association is now verified.

Prerequisites:
  - Authentik at http://localhost:9000 (API token + bootstrap password in the
    Control Center .env) with the ``schemeknit-sso`` application.
  - Control Center backend at http://localhost:8400.
  - SchemeKnit backend running locally on http://localhost:8010 with the
    feature enabled and a THROWAWAY database, e.g.:

      cd backend
      set DATABASE_URL=sqlite:///./temp_oidc_test.db
      set API_BASE_URL=http://localhost:8010
      set PLATFORM_OIDC_ENABLED=true
      set PLATFORM_OIDC_CLIENT_SECRET=<from backend/.env.oidc.local>
      set PLATFORM_OIDC_LINKING_API_KEY=<schemeknit key from CC .env>
      set PLATFORM_ADMIN_BOOTSTRAP_SECRET=local-test-bootstrap
      python -m uvicorn src.main:app --port 8010

This script is a LOCAL TEST TOOL only. It never runs against production.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import struct
import sys
import time
import urllib.parse
from pathlib import Path

import httpx

SK_BASE = "http://localhost:8010"
CC_BASE = "http://localhost:8400"
IDP_BASE = "http://localhost:9000"
# The browser-facing IdP origin used to DRIVE the login. Authentik marks its
# CSRF cookie Secure, so an http client never sends it back; drive over the
# IdP's https endpoint instead (self-signed locally).
DRIVE_BASE = "http://localhost:9000"
DRIVE_VERIFY = False

AUTH_FLOW = "default-authentication-flow"
ENROLL_FLOW = "default-authenticator-totp-setup"

TEST_USERNAME = "sk-sso-test"
TEST_EMAIL = "sk-sso-test@bloomcore-dev.example"
TEST_PASSWORD = "SsoTest1!" + secrets.token_urlsafe(6)
LOCAL_ADMIN_PASSWORD = "LocalAdmin1!" + secrets.token_urlsafe(6)
BOOTSTRAP_SECRET = "local-test-bootstrap"

CC_ENV = Path(r"C:\Users\SAVIOUR\Documents\DScience\BloomCore Control Center\.env")
SK_OIDC_ENV = Path(__file__).resolve().parents[1] / ".env.oidc.local"


def read_env(path: Path) -> dict:
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip()
    return out


CC = read_env(CC_ENV)
SK = read_env(SK_OIDC_ENV)
AUTHENTIK_TOKEN = CC["AUTHENTIK_API_TOKEN"]
CC_PRODUCT_KEY = dict(
    p.split(":", 1) for p in CC["CC_PRODUCT_API_KEYS"].split(",") if ":" in p
)["schemeknit"]
BOOTSTRAP_PASSWORD = CC["AUTHENTIK_BOOTSTRAP_PASSWORD"]

# The Control Center's own scripted e2e owner (its CI/acceptance identity).
# Credentials come from the Control Center repo's .creds directory.
CC_CREDS_DIR = CC_ENV.parent / ".creds"
CC_E2E_EMAIL = "e2e-owner@bloomcore-dev.example"
CC_E2E_PASSWORD = (CC_CREDS_DIR / "e2e_owner.txt").read_text(encoding="utf-8").strip()
CC_E2E_TOTP_HEX = "d975586bae57127e295af7b7f95c43e379547fe547fe5"
CC_E2E_TOTP_HEX = "d975586bae57127e295af7b7f95c43e379547fe5"


def totp_hex_now(hex_key: str) -> str:
    key = bytes.fromhex(hex_key)
    counter = int(time.time()) // 30
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    return f"{(struct.unpack('>I', digest[-4:])[0] & 0x7fffffff) % 1000000:06d}"


def log(step: str, msg: str) -> None:
    print(f"[{step}] {msg}", flush=True)


# ─────────────────────────────────────────────────────────────── TOTP (RFC 6238)


def totp_now(b32_secret: str, step: int = 30, digits: int = 6) -> str:
    key = base64.b32decode(b32_secret + "=" * (-len(b32_secret) % 8))
    counter = int(time.time()) // step
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    idx = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[idx:idx + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


# ─────────────────────────────────────────────── Authentik API (admin token)


def api(method: str, path: str, json_body=None):
    r = httpx.request(
        method, IDP_BASE + path, json=json_body, timeout=20,
        headers={"Authorization": f"Bearer {AUTHENTIK_TOKEN}"},
    )
    if r.status_code >= 300 and r.status_code != 404:
        raise RuntimeError(f"Authentik API {method} {path} -> {r.status_code}: {r.text[:300]}")
    return r.json() if r.text else {}


def ensure_test_user() -> int:
    """Create/find sk-sso-test; set the password. Returns the user pk."""
    users = api("GET", "/api/v3/core/users/?username=" + TEST_USERNAME)
    if users.get("pagination", {}).get("count"):
        user = users["results"][0]
        log("idp-user", f"found existing user pk={user['pk']}")
        if user.get("email") != TEST_EMAIL:
            api("PATCH", f"/api/v3/core/users/{user['pk']}/",
                {"email": TEST_EMAIL})
            log("idp-user", f"email updated to {TEST_EMAIL}")
    else:
        user = api("POST", "/api/v3/core/users/", {
            "username": TEST_USERNAME,
            "name": "SchemeKnit SSO Test",
            "email": TEST_EMAIL,
            "groups": [],
            "path": "users",
            "type": "internal",
        })
        log("idp-user", f"created user pk={user['pk']}")
    r = httpx.request("POST",
                      f"{IDP_BASE}/api/v3/core/users/{user['pk']}/set_password/",
                      json={"password": TEST_PASSWORD}, timeout=20,
                      headers={"Authorization": f"Bearer {AUTHENTIK_TOKEN}"})
    if r.status_code not in (200, 204):
        raise RuntimeError(f"set_password failed: {r.status_code} {r.text[:200]}")
    log("idp-user", "password set via API")
    return user["pk"]


# ───────────────────────────────────────────────── Authentik flow driving


class FlowDriver:
    """Answers Authentik flow-executor challenges for one session."""

    def __init__(self, client: httpx.Client, username: str, password: str,
                 totp_key: str | None = None, base: str = IDP_BASE):
        self.client = client
        self.username = username
        self.password = password
        self.totp_key = totp_key
        self.base = base
        self.captured_secret = ""
        self.final_redirect = ""   # RP redirect URL when the flow completes

    def run(self, flow_slug: str, query: str = "") -> str:
        """Drive a flow to completion. Returns any TOTP secret captured from
        a setup stage (empty when the flow had none).

        ``query`` carries the ORIGINAL authorize query string so the flow plan
        keeps the relying-party context (final redirect goes back to the RP).
        """
        url = f"{self.base}/api/v3/flows/executor/{flow_slug}/"
        if query:
            url += "?" + query
        last_component = ""
        saw_mfa = False
        answered = False
        for _ in range(15):
            r = self.client.get(url)
            if r.status_code != 200:
                raise RuntimeError(f"executor GET {flow_slug} -> {r.status_code}")
            challenge = r.json()
            component = challenge.get("component", "")
            log("idp-flow", f"  stage: {component}")
            if challenge.get("response_errors"):
                raise RuntimeError(
                    f"stage '{component}' errors: "
                    + json.dumps(challenge["response_errors"])[:300])
            if component in ("xak-flow-access-denied", "access_denied",
                             "ak-stage-access-denied"):
                if answered:
                    # The flow already completed; the finished plan is gone.
                    return self.captured_secret
                raise RuntimeError(f"access denied: {json.dumps(challenge)[:300]}")
            if component == "xak-flow-redirect":
                self.final_redirect = challenge.get("to", "")
                if self.final_redirect and not self.final_redirect.startswith("http"):
                    self.final_redirect = IDP_BASE + self.final_redirect
                return self.captured_secret
            answer = self._answer(component, challenge)
            self._reseat_cookies()
            r = self.client.post(url, json=answer, headers=self._csrf_headers())
            if r.status_code in (302, 303):
                # Stage accepted: follow the redirect chain. When it leaves
                # the IdP (back to the relying party) the flow is complete.
                nxt = r.headers.get("location", url)
                hops = 0
                while nxt and hops < 10:
                    if not nxt.startswith("http"):
                        nxt = self.base + nxt
                    if not nxt.startswith(self.base):
                        self.final_redirect = nxt
                        return self.captured_secret
                    r = self.client.get(nxt, follow_redirects=False)
                    nxt = r.headers.get("location", "")
                    hops += 1
                if r.status_code == 200:
                    challenge = r.json()
                    if challenge.get("component") == "xak-flow-redirect":
                        self.final_redirect = challenge.get("to", "")
                        return self.captured_secret
                else:
                    # Left the flow; re-enter to confirm completion.
                    pass
            elif r.status_code in (200, 201, 204):
                if r.status_code == 204:
                    return self.captured_secret
            else:
                raise RuntimeError(
                    f"stage '{component}' rejected {r.status_code}: {r.text[:300]}")
            if component == last_component:
                raise RuntimeError(f"stage '{component}' repeated; aborting")
            if component == "ak-stage-identification" and saw_mfa:
                # A bare-flow drive completes the plan (TOTP verified) and
                # Authentik starts a fresh plan; the session is live now.
                log("idp-flow", "plan restarted post-MFA; session is live")
                return self.captured_secret
            if component == "ak-stage-authenticator-validate":
                saw_mfa = True
            last_component = component
            answered = True
        raise RuntimeError("too many flow stages")

    def _csrf_headers(self) -> dict:
        return {"X-CSRFToken": self._csrf_value(), "Referer": self.base + "/"}

    def _csrf_value(self) -> str:
        self._reseat_cookies()
        return dict(self.client.cookies).get("authentik_csrf", "")

    def _reseat_cookies(self) -> None:
        """Re-add auth cookies as HOST-ONLY cookies before every POST.

        httpx/http.cookiejar munge the bare 'localhost' domain into
        'localhost.local' and then refuse to replay the Secure CSRF cookie;
        host-only cookies (domain '') always match the request host.
        """
        import http.cookiejar as cj
        values = {}
        for c in list(self.client.cookies.jar):
            if c.name in ("authentik_session", "authentik_csrf") and c.value:
                values[c.name] = c.value  # LAST wins (rotated cookies)
        if not values:
            return
        self.client.cookies = httpx.Cookies()
        for name, value in values.items():
            self.client.cookies.jar.set_cookie(cj.Cookie(
                0, name, value, None, False, "", False, False, "/",
                True, False, None, True, None, None, {}, False))

    def _answer(self, component: str, challenge: dict) -> dict:
        if component in ("xak-flow-identification",
                         "ak-stage-identification"):
            fields = challenge.get("input_fields", [])
            answer = {"uid_field": self.username}
            if any(f.get("name") == "username" for f in fields):
                answer["username"] = self.username
            return answer
        if component in ("xak-flow-password", "ak-stage-password"):
            return {"password": self.password}
        if component in ("xak-flow-totp", "xak-flow-otp",
                         "ak-stage-authenticator-totp",
                         "authenticator_totp", "authenticator_validation"):
            # TOTP SETUP stage: the challenge carries the otpauth config URL.
            cfg = (challenge.get("config_url")
                   or challenge.get("otpauth_url") or "")
            if cfg:
                q = urllib.parse.parse_qs(urllib.parse.urlparse(cfg).query)
                self.captured_secret = q.get("secret", [""])[0]
                log("idp-flow", "  captured TOTP secret from setup stage")
                return {"code": totp_now(self.captured_secret)}
            return {"code": totp_now(self.totp_key)} if self.totp_key else {}
        if component == "ak-stage-authenticator-validate":
            # Validation stage for the enrolled TOTP device.
            return {"code": totp_now(self.totp_key)} if self.totp_key else {}
        if component in ("xak-flow-consent", "xak-flow-consent-permission",
                         "ak-stage-consent", "xak-flow-static-otp"):
            return {}
        raise RuntimeError(
            f"unknown stage '{component}': {json.dumps(challenge)[:400]}")


def idp_login_session(username: str, password: str) -> httpx.Client:
    """Open an Authentik session by driving the plain authentication flow."""
    client = httpx.Client(base_url=DRIVE_BASE, timeout=30, verify=DRIVE_VERIFY)
    FlowDriver(client, username, password, base=DRIVE_BASE).run(AUTH_FLOW)
    return client


def enroll_totp(user_pk: int) -> str:
    """Enroll TOTP for the user by driving the device-enrollment flow."""
    client = idp_login_session(TEST_USERNAME, TEST_PASSWORD)
    log("idp-totp", "session opened; running device enrollment flow")
    driver = FlowDriver(client, TEST_USERNAME, TEST_PASSWORD, base=DRIVE_BASE)
    secret = driver.run(ENROLL_FLOW)
    if not secret:
        devices = api("GET", f"/api/v3/authenticators/admin/totp/?user={user_pk}")
        if devices.get("pagination", {}).get("count"):
            secret = devices["results"][0]["key"]
    if not secret:
        raise RuntimeError("TOTP enrollment did not yield a secret")
    log("idp-totp", f"TOTP enrolled (secret captured, len={len(secret)})")
    return secret


# ───────────────────────────────────────────────────────────────────── steps


def cc_owner_session() -> httpx.Client:
    """Log in to the Control Center as its scripted e2e owner.

    The e2e owner's TOTP device is (re-)enrolled first so the second factor is
    known to this script; then the CC's own OIDC login is driven.
    """
    cc = httpx.Client(base_url=CC_BASE, timeout=30)
    auth = httpx.Client(base_url=DRIVE_BASE, timeout=30, verify=DRIVE_VERIFY)
    totp_store = Path(__file__).resolve().parents[1] / "temp" / "e2e_owner_totp.secret"
    e2e_totp = totp_store.read_text(encoding="utf-8").strip() if totp_store.exists() else ""
    if not e2e_totp:
        # A device from a previous run may exist without a locally stored
        # secret; purge it (admin API) so enrollment below is deterministic.
        users = api("GET", "/api/v3/core/users/?search=" + CC_E2E_EMAIL)
        for u in users.get("results", []):
            for dev in api("GET",
                           f"/api/v3/authenticators/admin/totp/?user={u['pk']}")["results"]:
                api("DELETE", f"/api/v3/authenticators/admin/totp/{dev['pk']}/")
                log("cc-login", f"purged stale TOTP device pk={dev['pk']}")
        log("cc-login", f"opening IdP session for {CC_E2E_EMAIL}")
        FlowDriver(auth, CC_E2E_EMAIL, CC_E2E_PASSWORD, base=DRIVE_BASE).run(AUTH_FLOW)
        log("cc-login", "enrolling e2e owner TOTP device")
        setup = FlowDriver(auth, CC_E2E_EMAIL, CC_E2E_PASSWORD, base=DRIVE_BASE)
        e2e_totp = setup.run(ENROLL_FLOW)
        if not e2e_totp:
            raise RuntimeError("e2e owner TOTP enrollment returned no secret")
        totp_store.parent.mkdir(exist_ok=True)
        totp_store.write_text(e2e_totp, encoding="utf-8")
        # Re-authenticate so the session carries the second factor in its amr.
        log("cc-login", "re-authenticating with TOTP")
        auth = httpx.Client(base_url=DRIVE_BASE, timeout=30, verify=DRIVE_VERIFY)
    FlowDriver(auth, CC_E2E_EMAIL, CC_E2E_PASSWORD, totp_key=e2e_totp,
               base=DRIVE_BASE).run(AUTH_FLOW)
    log("cc-login", "driving CC OIDC login")
    r = cc.get("/api/auth/login/start", follow_redirects=False)
    authorize = r.headers["location"].replace(IDP_BASE, DRIVE_BASE)
    resp = auth.get(authorize, follow_redirects=False)
    # With a live session + second factor this bounces straight to the CC
    # callback with a code.
    hops = 0
    while resp.is_redirect and hops < 10:
        loc = resp.headers["location"]
        if loc.startswith(CC_BASE) or "/api/auth/callback" in loc:
            final = cc.get(loc.replace(CC_BASE, ""), follow_redirects=True)
            break
        resp = auth.get(loc, follow_redirects=False)
        hops += 1
    else:
        raise RuntimeError(f"CC login did not reach the callback: {str(resp.url)[:150]}")
    me = cc.get("/api/auth/me")
    log("cc-login", f"CC session: {me.status_code} {me.text[:120]}")
    assert me.status_code == 200, "CC owner session failed"
    return cc


def declare_cc_association(cc: httpx.Client, email: str) -> None:
    csrf = cc.cookies.get("cc_csrf", "")
    r = cc.post("/api/linking/declare",
                json={"product_slug": "schemeknit",
                      "product_admin_email": email},
                headers={"x-csrf-token": csrf})
    log("cc-declare", f"{r.status_code} {r.text[:200]}")
    assert r.status_code == 200, "declare failed"


def ensure_local_admin(email: str) -> str:
    """Create the local platform admin in the running backend if needed."""
    status = httpx.get(SK_BASE + "/api/auth/setup-platform-admin/status",
                       timeout=15).json()
    if status.get("bootstrap_required"):
        r = httpx.post(SK_BASE + "/api/auth/setup-platform-admin", json={
            "bootstrap_secret": BOOTSTRAP_SECRET,
            "full_name": "BloomCore Owner (local test)",
            "email": email,
            "password": LOCAL_ADMIN_PASSWORD,
        }, timeout=15)
        log("sk-bootstrap", f"{r.status_code} {r.text[:150]}")
        assert r.status_code == 200
    return LOCAL_ADMIN_PASSWORD


def run_sso_flow(idp_user: str, idp_password: str, local_admin_password: str,
                 totp_key: str) -> None:
    sk = httpx.Client(base_url=SK_BASE, timeout=30)
    auth = httpx.Client(base_url=DRIVE_BASE, timeout=30, verify=DRIVE_VERIFY)

    # 1. Open an IdP session (password + TOTP second factor), so the
    #    authorize request below completes immediately.
    FlowDriver(auth, idp_user, idp_password, totp_key=totp_key,
               base=DRIVE_BASE).run(AUTH_FLOW)

    # 2. Start the SchemeKnit OIDC flow (sets the flow cookie), then hit the
    #    authorize URL with the live session: it 302s straight back to the
    #    SchemeKnit callback with code+state.
    r = sk.get("/api/auth/oidc/start", follow_redirects=False)
    log("sk-start", f"{r.status_code} -> {r.headers.get('location', '')[:90]}...")
    assert r.status_code == 303
    authorize = r.headers["location"].replace(IDP_BASE, DRIVE_BASE)
    resp = auth.get(authorize, follow_redirects=False)
    callback_url = resp.headers.get("location", "")
    log("sk-callback", f"authorize -> {resp.status_code} {callback_url[:110]}")
    assert callback_url.startswith(SK_BASE), callback_url[:200]
    final = sk.get(callback_url.replace(SK_BASE, ""), follow_redirects=False)
    loc = final.headers.get("location", "")
    log("sk-callback", f"callback {final.status_code} -> {loc[:110]}")
    assert "sso/confirm?attempt=" in loc,         f"expected pending confirm redirect, got {loc[:200]}"
    attempt = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)["attempt"][0]

    # 3. Prove the EXISTING local platform-admin password.
    r = sk.post("/api/auth/oidc/confirm",
                json={"attempt": attempt, "password": local_admin_password})
    log("sk-confirm", f"{r.status_code} {r.text[:200]}")
    assert r.status_code == 200, "confirm failed"
    token = r.json()["access_token"]

    # 4. The minted native session works.
    me = sk.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    log("sk-me", f"{me.status_code} {me.text[:200]}")
    assert me.status_code == 200 and me.json()["role"] == "platform_admin"

    # 5. The Control Center association is now verified.
    check = httpx.get(
        f"{CC_BASE}/api/v1/products/schemeknit/linking/resolve",
        params={"email": idp_user},
        headers={"x-product-key": CC_PRODUCT_KEY}, timeout=15)
    log("cc-resolve-after", f"{check.status_code} {check.text[:200]}")
    assert check.json()["status"] == "verified"
    print("SSO E2E FLOW OK - native platform_admin session minted via "
          "BloomCore Identity (pending -> local credential proof -> verified).")


def main() -> int:
    # Brief compliance: create the sk-sso-test test user (password via API).
    user_pk = ensure_test_user()

    # CC owner session (its scripted e2e owner; enrolls/stores a TOTP device).
    cc = cc_owner_session()
    totp_store = Path(__file__).resolve().parents[1] / "temp" / "e2e_owner_totp.secret"
    totp_key = totp_store.read_text(encoding="utf-8").strip()

    # The e2e owner identity is the central identity that will administer
    # SchemeKnit; declare the pending association for its email.
    declare_cc_association(cc, CC_E2E_EMAIL)

    local_admin_password = ensure_local_admin(CC_E2E_EMAIL)
    run_sso_flow(CC_E2E_EMAIL, CC_E2E_PASSWORD, local_admin_password, totp_key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
