# SchemeKnit Access and Super Admin MFA — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let public teachers register when the backend is `open`, make Super Admin TOTP enrollment real and mandatory, and render one logo on the admin login page.

**Architecture:** Backend stays the source of truth. A public policy endpoint drives the signup field; the invite gate and Turnstile are untouched. `/mfa/setup` gains a server-rendered QR and no-store headers; the console blocks itself until TOTP verifies; `require_platform_admin` blocks unenrolled admins. An operator CLI resets MFA only.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, segno (SVG QR), Next.js 16 (App Router, client components), Tailwind, lucide-react.

**Spec:** `docs/superpowers/specs/2026-11-01-schemeknit-access-and-super-admin-mfa-design.md`

## Global Constraints

- Do not deploy, change production env vars, reset production data or reset the production Super Admin.
- `REGISTRATION_MODE` remains `open` | `invite_only` | `closed`; defaults unchanged.
- `PILOT_INVITE_CODE` never logged, never committed, never returned by API.
- Turnstile server verification stays enabled; never disable it for tests.
- TOTP secret: 20 random bytes, base32; SHA1/6 digits/30 seconds; window ±1 step.
- Secrets never logged, never returned after enrollment, never in URLs.
- `/mfa/setup` response headers: `Cache-Control: no-store, private`, `Pragma: no-cache`.
- QR generation is local (segno). No external QR service.
- Recovery codes: 8, single use, bcrypt-hashed, shown once, regeneration invalidates all.
- MFA reset is CLI-only, dry-run by default, `--apply` required, audited, sessions revoked, MFA-only.
- Frontend has no JS test runner: pin frontend behaviour with backend pytest source-contract tests.
- Keep changes inside the SchemeKnit repo.

## Review Focus

- A signup page that renders while the policy call is pending must not allow submit.
- Direct `POST /api/auth/register/individual` with a valid Turnstile token but no invite code must be rejected when the mode is `invite_only`.
- Direct platform-admin API calls without MFA must be rejected when `DEBUG=false`, including GET.
- An enrolled admin calling `/mfa/setup` again must not receive a secret or QR.
- An operator reset must leave password, role and active flag unchanged while forcing re-enrollment.
- The Platform Administration login page must render exactly one logo at 390 px and 1440 px.

---

### Task 1: Registration policy endpoint

**Files:**
- Modify: `backend/src/routers/auth.py` (near `setup_status`)
- Test: `backend/tests/test_pilot_registration_gate.py`
- Modify: `backend/tests/test_authorization_route_inventory.py:17-45`

**Interfaces:**
- Produces: `GET /api/auth/registration-policy` → `{registration_mode: str, self_registration: bool, invite_code_required: bool}`.

- [ ] **Step 1: Write the failing tests**

```python
def test_registration_policy_reports_open(db, monkeypatch):
    monkeypatch.setenv("REGISTRATION_MODE", "open")
    get_settings.cache_clear()
    with TestClient(_app(db)) as client:
        body = client.get("/api/auth/registration-policy")
    assert body.status_code == 200
    assert body.json() == {
        "registration_mode": "open",
        "self_registration": True,
        "invite_code_required": False,
    }


def test_registration_policy_reports_invite_only(db, monkeypatch):
    monkeypatch.setenv("REGISTRATION_MODE", "invite_only")
    monkeypatch.setenv("PILOT_INVITE_CODE", "pilot-123")
    get_settings.cache_clear()
    with TestClient(_app(db)) as client:
        body = client.get("/api/auth/registration-policy")
    assert body.json()["invite_code_required"] is True


def test_registration_policy_reports_closed(db, monkeypatch):
    monkeypatch.setenv("REGISTRATION_MODE", "closed")
    get_settings.cache_clear()
    with TestClient(_app(db)) as client:
        body = client.get("/api/auth/registration-policy")
    assert body.json()["self_registration"] is False
    assert body.json()["invite_code_required"] is False
```

Plus HTTP registration tests: `open` + verified Turnstile + no invite code → 200; `invite_only` + verified Turnstile + no/invalid code → 403; `invite_only` + matching code → 200. Reuse `tests/test_turnstile.py` helpers by copying the local `_enable`/`_fake_siteverify` pattern into the pilot test module (test-local monkeypatch, no shared mutable state).

- [ ] **Step 2: Run tests, expect failure**

`cd backend && python -m pytest tests/test_pilot_registration_gate.py -v` → 404 on the policy route.

- [ ] **Step 3: Implement**

```python
@router.get("/registration-policy")
async def registration_policy(response: Response):
    settings = get_settings()
    mode = (settings.REGISTRATION_MODE or "open").strip().lower()
    response.headers["Cache-Control"] = "no-store"
    return {
        "registration_mode": mode,
        "self_registration": mode != "closed",
        "invite_code_required": mode == "invite_only",
    }
```

Add `Response` to the `fastapi` import. Add `("auth", "/registration-policy", "GET")` to `PUBLIC` in the inventory test.

- [ ] **Step 4: Run tests** → all pass.

- [ ] **Step 5: Commit** — `feat(auth): publish registration policy for the signup UI`

---

### Task 2: Signup reads the policy at runtime

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/app/signup/page.tsx`
- Test: `backend/tests/test_pilot_registration_gate.py`

**Interfaces:**
- Consumes: `GET /api/auth/registration-policy` (Task 1).
- Produces: `api.getRegistrationPolicy(): Promise<{registration_mode: string; self_registration: boolean; invite_code_required: boolean}>`.

- [ ] **Step 1: Failing source-contract test**

Assert `signup/page.tsx` contains `getRegistrationPolicy`, `policyError`, and a retry control, and that the env flag appears only as an initial fallback.

- [ ] **Step 2: Run it** → fails.

- [ ] **Step 3: Implement**

`api.ts`:

```ts
async getRegistrationPolicy(): Promise<{
  registration_mode: string
  self_registration: boolean
  invite_code_required: boolean
}> {
  return this.request('/api/auth/registration-policy')
}
```

`signup/page.tsx`: `policy: {invite_code_required: boolean; self_registration: boolean} | null`, `policyError: boolean`. `loadPolicy()` calls the API; on success set policy and `setInviteRequired(res.invite_code_required)`; on failure set `policyError` and `inviteRequired` stays at the env fallback. Submit is disabled while `!policy` or `policyError`, with a visible retry button. Render a closed-registration notice instead of the form when `policy.self_registration === false`.

- [ ] **Step 4: Run the source test** → passes.

- [ ] **Step 5: Commit** — `feat(signup): drive invite field from backend registration policy`

---

### Task 3: Server QR for TOTP enrollment

**Files:**
- Create: `backend/src/mfa_qr.py`
- Modify: `backend/src/routers/auth.py:mfa_setup`
- Modify: `backend/requirements.txt`
- Test: `backend/tests/test_mfa.py`

**Interfaces:**
- Produces: `mfa_qr.provisioning_qr_data_uri(otpauth_uri: str) -> str` (returns `data:image/svg+xml;base64,...`).
- Produces: `POST /api/auth/mfa/setup` response adds `qr_data_uri`.

- [ ] **Step 1: Failing tests**

```python
def test_setup_returns_local_qr_and_no_store_headers(db):
    admin = make_user(db, role="platform_admin", is_admin=True, email="qr-admin@test.com")
    with TestClient(_app(db, admin)) as client:
        res = client.post("/api/auth/mfa/setup")
    assert res.status_code == 200
    assert res.json()["qr_data_uri"].startswith("data:image/svg+xml;base64,")
    assert "no-store" in res.headers["cache-control"]
    assert "private" in res.headers["cache-control"]
    assert res.headers["pragma"] == "no-cache"


def test_enrolled_admin_cannot_read_secret_again(db):
    # setup -> verify-setup -> second setup returns 400 with no secret field
```

Also: a teacher token on `/mfa/setup` → 403.

- [ ] **Step 2: Run** → fails (`qr_data_uri` missing).

- [ ] **Step 3: Implement**

`mfa_qr.py`:

```python
import base64
import segno

def provisioning_qr_data_uri(otpauth_uri: str) -> str:
    qr = segno.make(otpauth_uri, error="m")
    svg = qr.svg_inline(scale=4, border=2)
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"
```

`auth.py`: `async def mfa_setup(response: Response, user=..., db=...)`; add `qr_data_uri` to the payload; set `response.headers["Cache-Control"] = "no-store, private"` and `response.headers["Pragma"] = "no-cache"`.

`requirements.txt`: add `segno==1.6.6` under Document processing (or a new QR section).

- [ ] **Step 4: Install and run** — `python -m pip install segno==1.6.6` in the project venv, then the tests.

- [ ] **Step 5: Commit** — `feat(mfa): return locally generated QR for enrollment`

---

### Task 4: Backend enrollment enforcement

**Files:**
- Modify: `backend/src/auth.py:271-293`
- Test: `backend/tests/test_mfa.py`

**Interfaces:**
- Consumes: existing `require_platform_admin`.
- Produces: 403 for every method from an unenrolled platform admin when `DEBUG=false`.

- [ ] **Step 1: Failing test**

Use a test app with a real platform-admin route (or a stub route) guarded by `require_platform_admin`, patch `src.auth.settings.DEBUG` false, call GET → 403; then set `mfa_enabled=True` → 200. `/api/auth/mfa/setup` still 200 for the unenrolled admin.

- [ ] **Step 2: Run** → GET passes today (bug).

- [ ] **Step 3: Implement** — drop the method check:

```python
if not settings.DEBUG and not user.mfa_enabled:
    raise HTTPException(status_code=403, detail="MFA enrollment is required before platform administration.")
```

Update the docstring: reads are no longer available pre-enrollment; `/mfa/*` uses `require_platform_admin_unenrolled`.

- [ ] **Step 4: Run the MFA and platform-admin suites** → pass.

- [ ] **Step 5: Commit** — `fix(auth): block all platform admin API calls until MFA enrollment`

---

### Task 5: Frontend enrollment panel, gate and one-time codes

**Files:**
- Create: `frontend/src/components/mfa-enroll-panel.tsx`
- Modify: `frontend/src/components/mfa-settings-card.tsx`
- Modify: `frontend/src/lib/auth-context.tsx`
- Modify: `frontend/src/app/(platform-admin)/platform-admin/page.tsx`
- Modify: `frontend/src/components/role-login.tsx`
- Modify: `frontend/src/lib/api.ts`
- Test: `backend/tests/test_mfa_frontend_source.py`

**Interfaces:**
- Consumes: `api.beginMfaSetup()` now returns `{secret, otpauth_uri, qr_data_uri, digits, period_seconds}`; `api.verifyMfaSetup(code)`.
- Produces: `MfaEnrollPanel({ onComplete?: (codes: string[]) => void })`; `useAuth().refreshUser(): Promise<void>`.

- [ ] **Step 1: Failing source tests**

Assert the panel contains `qr_data_uri`, `secret` copy control, `recovery_codes`, acknowledgement checkbox; `/platform-admin` renders the gate when `!user.mfa_enabled`; `auth-context` has `refreshUser`; role-login contains first-sign-in guidance.

- [ ] **Step 2: Run** → fails.

- [ ] **Step 3: Implement**

- `MfaEnrollPanel`: `useEffect` → `beginMfaSetup`; render `<img src={setup.qr_data_uri} alt="Authenticator QR code" />`, manual key `<code>` + Copy, instructions, 6-digit `Input`, verify; on success show recovery codes once, copy button, acknowledgement checkbox, then `onComplete?.(codes)`.
- `MfaSettingsCard`: when disabled, keep the "Enable MFA" button and render `MfaEnrollPanel` after it starts; when enabled, never render `setup.secret`/QR; keep regenerate/disable.
- `auth-context`: `refreshUser` → `api.getProfile()`, update state/sessionStorage; add to context type.
- `/platform-admin`: before the console, `if (user.role === 'platform_admin' && !user.mfa_enabled)` return a focused gate card with `MfaEnrollPanel` and `onComplete={refreshUser}`. Keep the existing spinner/redirect logic.
- `role-login`: add a hint under the code field: "First sign-in? Leave this blank. You will set up your authenticator after signing in."
- `api.beginMfaSetup` return type adds `qr_data_uri: string`.

- [ ] **Step 4: Run source tests + `npx tsc --noEmit`** → pass.

- [ ] **Step 5: Commit** — `feat(admin): add blocking TOTP enrollment with QR and recovery codes`

---

### Task 6: Single logo on Platform Administration login

**Files:**
- Modify: `frontend/src/components/auth/auth-shell.tsx:715-746`
- Test: `backend/tests/test_final_web_ux.py` or a new source test in `test_mfa_frontend_source.py`

**Interfaces:** none.

- [ ] **Step 1: Failing test** — assert `auth-shell.tsx` contains exactly one `<BrandCapsule`.

- [ ] **Step 2: Run** → fails (2 occurrences).

- [ ] **Step 3: Implement** — delete the aside capsule line; keep the main header capsule. Ensure the main header wrapper still renders the badge for centered layouts.

- [ ] **Step 4: Run source tests + `npx tsc --noEmit`** → pass.

- [ ] **Step 5: Commit** — `fix(ui): render one logo on platform admin login`

---

### Task 7: Operator MFA reset

**Files:**
- Modify: `backend/src/tools/reset_platform_admin.py`
- Test: `backend/tests/test_platform_admin_mfa_reset.py`
- Modify: `docs/PLATFORM_ADMIN_BOOTSTRAP_AND_RECOVERY.md`

**Interfaces:**
- Produces: `reset_platform_admin_mfa(db: Session, email: str, operator: str, reason: str, apply: bool = False) -> dict` returning `{found, email, mfa_enabled, sessions_revoked, applied}`.
- CLI: `--reset-mfa --email <email> --operator <name> --reason <text> [--apply]`.

- [ ] **Step 1: Failing tests**

- dry-run: admin still `mfa_enabled=True` with secret; result `applied=False`.
- apply: `mfa_enabled is False`, `mfa_secret is None`, recovery codes empty, `mfa_last_step is None`, password hash unchanged, role unchanged, active sessions revoked (`UserSessionDB.revoked_at` not null), audit row action `platform_admin_mfa_reset_cli` with details containing operator and reason.
- unknown email → `found=False`, no exception.

- [ ] **Step 2: Run** → fails (function missing).

- [ ] **Step 3: Implement** — find user by normalized email and role; dry-run returns counts only; apply updates the four MFA columns, calls `revoke_user_sessions(db, user.id)`, inserts `PlatformAuditLogDB(actor_id=user.id, actor_role="platform_admin", action="platform_admin_mfa_reset_cli", target_type="user", target_id=user.id, details={"method": "cli_operator_mfa_reset", "operator": operator, "reason": reason})`. CLI: argparse flags, refuse `--set-password` together with `--reset-mfa`, print plan, require typing the email when `--apply`, never print secrets.

- [ ] **Step 4: Run tests** → pass.

- [ ] **Step 5: Docs** — add enrollment section and operator reset procedure with identity verification steps.

- [ ] **Step 6: Commit** — `feat(cli): add audited operator MFA reset`

---

### Task 8: Documentation and full verification

**Files:**
- Modify: `docs/release/FRIENDS-AND-FAMILY-PILOT-PLAN.md`
- Modify: `docs/infrastructure/ZERO-COST-INFRASTRUCTURE-ASSESSMENT.md`
- Modify: `docs/roadmap/SCHEMEKNIT-SECURITY-SEO-RELEASE-CHECKLIST.md`
- Test: full suite

- [ ] **Step 1: Document** that public registration needs `REGISTRATION_MODE=open` and `NEXT_PUBLIC_PILOT_INVITE_REQUIRED=false`, and that the frontend now reads the backend policy.
- [ ] **Step 2: Run** `cd backend && python -m pytest -q` (allow live-marked skips), `cd frontend && npx tsc --noEmit && npm run lint && npm run build`.
- [ ] **Step 3: Inspect diff** for subscription, credits, payments, referrals: none of those files should change.
- [ ] **Step 4: Commit** — `docs: record public registration and admin MFA procedures`
