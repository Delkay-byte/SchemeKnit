"""
SchemeKnit Auth Router

Registration, login, profile management, first-run setup,
platform-admin bootstrap, password change and token-based password reset.
"""

from datetime import datetime, timedelta
import hashlib
import secrets

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from ..database import (
    get_db, User, generate_id, SchoolLicenseDB, SchoolMembershipDB,
    ActivationCodeDB, SchoolDB, ProductPlanDB, PlatformAuditLogDB,
    PasswordResetTokenDB, RevokedTokenDB, UserSessionDB,
)
from ..auth import (
    hash_password, verify_password, create_user_token,
    create_session_record, revoke_user_sessions,
    get_current_user, require_admin, require_platform_admin,
    require_platform_admin_unenrolled, decode_token, security,
)
from ..service import data_service
from ..config import get_settings
from ..security import client_ip
from ..login_security import (
    account_key, check_lockout, clear_failures, recent_failure_count,
    record_failure,
)
from ..turnstile import require_turnstile
from ..mfa import (
    generate_recovery_codes, generate_secret, hash_recovery_codes,
    provisioning_uri, verify_recovery_code, verify_totp,
)
from ..mfa_qr import provisioning_qr_data_uri
from ..logging_config import log_security, alert_security
from ..validation import (
    validate_password, validate_email, normalize_email, password_policy_hint,
)

router = APIRouter()

MIN_SETUP_PASSWORD_LEN = 8

#: Login entry points. Each entry is validated against the user's database
#: role after the password check; a mismatch returns the same generic 401 as
#: bad credentials (no account-role oracle).
VALID_LOGIN_ENTRIES = frozenset({"teacher", "school_admin", "platform_admin"})


def _entry_matches_role(user: User, entry: str) -> bool:
    """True when ``entry`` is the correct entry point for this DB identity.

    The role is read from the database row â€” never from the request body or a
    token claim. ``is_admin`` keeps legacy school administrators working.
    """
    role = (getattr(user, "role", "") or "").strip().lower()
    if entry == "teacher":
        return role == "teacher"
    if entry == "school_admin":
        return role == "school_admin" or bool(getattr(user, "is_admin", False))
    if entry == "platform_admin":
        return role == "platform_admin"
    return False


def _school_audit(db: Session, actor_id: str, actor_role: str, action: str,
                  target_type: str = "", target_id: str = "", details: dict = None):
    """School-side audit event (platform log table; never exposed to school roles)."""
    db.add(PlatformAuditLogDB(
        id=generate_id(),
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details or {},
    ))


def _load_code_for_redeem(db: Session, code_str: str):
    """Load an activation code row locked for update (atomic redeem on PostgreSQL;
    SQLite serializes writers, giving the same single-winner guarantee)."""
    code = db.query(ActivationCodeDB).filter(
        ActivationCodeDB.code == code_str.strip(),
    ).with_for_update().first()
    if not code:
        raise HTTPException(status_code=404, detail="Invalid activation code")
    return code


def _validate_code_state(db: Session, code) -> tuple:
    """Enforce code + license eligibility. Returns (license, school, plan).

    Error taxonomy mirrors the desktop activate endpoint; messages carry no
    secrets, hashes, or internal license data.
    """
    if code.status == "revoked":
        raise HTTPException(status_code=403, detail="Activation code has been revoked")
    if code.status == "used":
        raise HTTPException(status_code=403, detail="Activation code already used")
    from datetime import datetime
    if code.expires_at and code.expires_at < datetime.utcnow():
        raise HTTPException(status_code=403, detail="Activation code has expired")
    if code.status != "active":
        raise HTTPException(status_code=403, detail="Activation code is not active")

    license = db.query(SchoolLicenseDB).filter(
        SchoolLicenseDB.id == code.license_id).first()
    if not license:
        raise HTTPException(status_code=404, detail="License not found")
    if license.status in ("suspended", "cancelled"):
        raise HTTPException(
            status_code=403, detail=f"License is {license.status}")
    if license.status == "expired":
        raise HTTPException(status_code=403, detail="License has expired")
    from datetime import date
    if license.expiry_date and license.expiry_date < date.today():
        raise HTTPException(status_code=403, detail="License has expired")

    school = db.query(SchoolDB).filter(SchoolDB.id == license.school_id).first()
    if not school or school.status not in ("active",):
        raise HTTPException(status_code=403, detail="School is not active")
    plan = db.query(ProductPlanDB).filter(
        ProductPlanDB.id == license.product_plan_id).first()
    return license, school, plan


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    school_name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str
    mfa_code: Optional[str] = None
    recovery_code: Optional[str] = None
    #: Turnstile token, sent only when the backend has requested a challenge
    #: (after repeated failures). Empty on a normal first login.
    turnstile_token: str = ""
    #: The login entry point the client is using. The backend validates it
    #: against the user's authoritative database role, so a platform admin
    #: cannot obtain a session through the teacher entry (and vice versa).
    entry: Optional[str] = None


class MfaCodeRequest(BaseModel):
    code: str


class MfaDisableRequest(BaseModel):
    password: str
    code: str


class MfaRegenerateRequest(BaseModel):
    password: str
    code: str


class SetupRequest(BaseModel):
    name: str
    email: str
    password: str
    school_name: str = ""


class CreateTeacherRequest(BaseModel):
    email: str
    password: str
    full_name: str
    school_name: str = ""


class ProfileUpdateRequest(BaseModel):
    """The teacher's own profile edits (PART 7).

    The client PUTs a JSON body; the field must be declared here or the write
    is silently discarded (a JSON body is NOT bound to bare function
    parameters â€” that is how the school silently failed to persist).
    """

    full_name: Optional[str] = None
    school_name: Optional[str] = None


def user_response(user: User):
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "school_name": user.school_name,
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "role": user.role,
        "school_id": user.school_id,
        "subscription_type": getattr(user, "subscription_type", None),
        "mfa_enabled": bool(getattr(user, "mfa_enabled", False)),
    }


@router.get("/setup/status")
async def setup_status(db: Session = Depends(get_db)):
    user_count = db.query(User).count()
    return {
        "needs_setup": user_count == 0,
        "user_count": user_count,
        # The authoritative password rule, published so the frontend mirrors the
        # backend exactly instead of re-implementing (and drifting from) it.
        "password_policy": {
            "min_length": 8,
            "requires_letter": True,
            "requires_digit": True,
            "requires_symbol": True,
            "description": password_policy_hint(),
        },
    }


@router.get("/registration-policy")
async def registration_policy(response: Response):
    """Publish the authoritative self-registration rule.

    The signup page reads this instead of trusting a build-time flag, so the
    field can never demand a code the backend does not enforce (or hide one it
    does). No secret or account data is returned.
    """
    settings = get_settings()
    mode = (settings.REGISTRATION_MODE or "open").strip().lower()
    response.headers["Cache-Control"] = "no-store"
    return {
        "registration_mode": mode,
        "self_registration": mode != "closed",
        "invite_code_required": mode == "invite_only",
    }


@router.post("/setup")
async def first_run_setup(req: SetupRequest, db: Session = Depends(get_db)):
    user_count = db.query(User).count()
    if user_count > 0:
        raise HTTPException(status_code=400, detail="Setup already completed")

    ok, msg = validate_email(req.email)
    if not ok:
        raise HTTPException(status_code=422, detail=msg)
    ok, msg = validate_password(req.password)
    if not ok:
        raise HTTPException(status_code=422, detail=msg)

    user = User(
        id=generate_id(),
        email=normalize_email(req.email),
        full_name=req.name,
        hashed_password=hash_password(req.password),
        school_name=req.school_name,
        is_admin=True,
        is_active=True,
        role="school_admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_user_token(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user_response(user),
    }


class ActivationValidateRequest(BaseModel):
    activation_code: str


class SetupSchoolAdminRequest(BaseModel):
    email: str
    password: str
    full_name: str
    activation_code: str
    # Accepted for backward compatibility but NEVER trusted: the school is
    # always derived server-side from the activation code's license.
    school_id: str = None


class IndividualActivateRequest(BaseModel):
    activation_code: str


@router.post("/activation/validate")
async def validate_activation_code(req: ActivationValidateRequest, db: Session = Depends(get_db)):
    """Public code check for the onboarding UX. Reveals display info only
    (school name, plan, seats, period) â€” no secrets, no redemption."""
    code = db.query(ActivationCodeDB).filter(
        ActivationCodeDB.code == req.activation_code.strip()).first()
    if not code:
        raise HTTPException(status_code=404, detail="Invalid activation code")
    license, school, plan = _validate_code_state(db, code)
    return {
        "valid": True,
        "school": {"id": school.id, "name": school.name, "school_code": school.school_code},
        "license": {
            "status": license.status,
            "plan": plan.name if plan else "Unknown",
            "start_date": license.start_date.isoformat(),
            "expiry_date": license.expiry_date.isoformat(),
            "seat_limit": license.seat_limit,
        },
    }


@router.post("/activate-individual")
async def activate_individual_license(
    req: IndividualActivateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Activate an individual teacher license using an activation code.

    The teacher must be logged in and on the Free Tier. The activation code
    is validated and redeemed atomically, granting the teacher the paid
    individual entitlement associated with the code's product plan.
    """
    if not req.activation_code or not req.activation_code.strip():
        raise HTTPException(status_code=422, detail="Activation code is required")

    # Load the individual activation code with row lock
    code = db.query(IndividualActivationCodeDB).filter(
        IndividualActivationCodeDB.code == req.activation_code.strip(),
    ).with_for_update().first()
    if not code:
        raise HTTPException(status_code=404, detail="Invalid activation code")

    # Validate code state
    if code.status == "revoked":
        raise HTTPException(status_code=403, detail="Activation code has been revoked")
    if code.status == "used":
        raise HTTPException(status_code=403, detail="Activation code already used")
    if code.expires_at and code.expires_at < datetime.utcnow():
        raise HTTPException(status_code=403, detail="Activation code has expired")
    if code.status != "active":
        raise HTTPException(status_code=403, detail="Activation code is not active")

    # Get the product plan
    plan = db.query(ProductPlanDB).filter(
        ProductPlanDB.id == code.product_plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Product plan not found")
    if plan.customer_type != "individual_teacher":
        raise HTTPException(status_code=403, detail="Activation code is not for individual teacher license")

    # Check if user is on Free Tier (not already on a paid plan)
    from ..entitlements import resolve_entitlement
    entitlement = resolve_entitlement(db, user)
    if entitlement["edition"] != "free":
        raise HTTPException(status_code=403, detail="Your account already has a paid plan")

    # Redeem the code
    code.status = "used"
    code.used_by_user_id = user.id
    redeemed_at = datetime.utcnow()
    code.used_at = redeemed_at

    # Create or update subscription
    from ..database import EntitlementDB, SubscriptionDB
    now = datetime.utcnow()
    duration_days = plan.duration_days or 365

    sub = db.query(SubscriptionDB).filter(
        SubscriptionDB.user_id == user.id,
        SubscriptionDB.status == "active",
    ).first()

    if sub:
        if sub.expires_at and sub.expires_at > now:
            sub.expires_at = sub.expires_at + timedelta(days=duration_days)
        else:
            sub.expires_at = now + timedelta(days=duration_days)
        sub.status = "active"
        sub.plan_name = plan.name
    else:
        sub = SubscriptionDB(
            id=generate_id(),
            user_id=user.id,
            edition="teacher",
            plan_name=plan.name,
            status="active",
            started_at=now,
            expires_at=now + timedelta(days=duration_days),
            payment_provider="activation_code",
            external_id=code.id,
        )
        db.add(sub)

    # Create or update entitlement
    ent = db.query(EntitlementDB).filter(
        EntitlementDB.user_id == user.id,
    ).first()

    if ent:
        ent.edition = "teacher"
        ent.subscription_type = "individual"
        ent.ai_enabled = getattr(plan, 'ai_enabled', True)
        ent.batch_generation = getattr(plan, 'batch_generation', True)
        ent.zip_export = getattr(plan, 'zip_export', True)
        ent.pdf_export = getattr(plan, 'pdf_export', True)
        ent.custom_template_limit = getattr(plan, 'custom_template_limit', 10)
        ent.history_limit = getattr(plan, 'history_limit', 100)
        ent.ai_credits = getattr(plan, 'ai_credits', 50)
        ent.generation_limit = getattr(plan, 'generation_limit', 0)
        ent.expires_at = now + timedelta(days=duration_days)
        ent.updated_at = now
    else:
        ent = EntitlementDB(
            id=generate_id(),
            user_id=user.id,
            edition="teacher",
            subscription_type="individual",
            features=["ai_basic", "cloud_sync", "template_import", "content_library"],
            ai_enabled=getattr(plan, 'ai_enabled', True),
            batch_generation=getattr(plan, 'batch_generation', True),
            zip_export=getattr(plan, 'zip_export', True),
            pdf_export=getattr(plan, 'pdf_export', True),
            custom_template_limit=getattr(plan, 'custom_template_limit', 10),
            history_limit=getattr(plan, 'history_limit', 100),
            ai_credits=getattr(plan, 'ai_credits', 50),
            ai_credits_used=0,
            generation_limit=getattr(plan, 'generation_limit', 0),
            generations_used=0,
            cloud_sync=True,
            template_import=True,
            content_library=True,
            expires_at=now + timedelta(days=duration_days),
            created_at=now,
            updated_at=now,
        )
        db.add(ent)

    # Update user subscription_type
    user.subscription_type = "individual"

    log_security("individual_license_activated", user_id=user.id,
                 plan=plan.name, activation_code_id=code.id)
    db.commit()

    return {
        "message": "License activated successfully",
        "plan": plan.name,
        "expires_at": (now + timedelta(days=duration_days)).isoformat(),
    }


@router.post("/setup-school-admin")
async def setup_school_admin(req: SetupSchoolAdminRequest, db: Session = Depends(get_db)):
    """Claim a school-admin account with a valid activation code.

    The code is validated AND redeemed atomically in one transaction together
    with admin creation: single-winner redeem, no replay, full audit trail.
    The school always comes from the code's license â€” never from the client.
    """
    if not req.activation_code or not req.activation_code.strip():
        raise HTTPException(status_code=422, detail="Activation code is required")
    ok, msg = validate_email(req.email)
    if not ok:
        raise HTTPException(status_code=422, detail=msg)
    ok, msg = validate_password(req.password)
    if not ok:
        raise HTTPException(status_code=422, detail=msg)

    existing = db.query(User).filter(User.email == normalize_email(req.email)).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    try:
        code = _load_code_for_redeem(db, req.activation_code)
        license, school, plan = _validate_code_state(db, code)

        # Redeem (single transaction with everything below)
        code.status = "used"
        code.used_by_school_id = school.id
        from datetime import datetime
        redeemed_at = datetime.utcnow()
        code.used_at = redeemed_at
        if license.status == "pending":
            license.status = "active"
        # Record the activation on the license itself so Platform Admin can see
        # which license a school actually claimed, and when. First redeem wins:
        # a later replacement code must not rewrite the school's start point.
        if license.activated_at is None:
            license.activated_at = redeemed_at
            license.activation_code_id = code.id
        license.updated_at = redeemed_at

        user = User(
            id=generate_id(),
            email=normalize_email(req.email),
            full_name=req.full_name,
            hashed_password=hash_password(req.password),
            is_admin=True,
            is_active=True,
            role="school_admin",
            school_id=school.id,
        )
        db.add(user)
        db.flush()
        db.add(SchoolMembershipDB(
            id=generate_id(),
            user_id=user.id,
            school_id=school.id,
            role="school_admin",
            status="active",
        ))
        _school_audit(db, user.id, "school_admin", "school_admin_claimed",
                      "school", school.id,
                      {"license_id": license.id,
                       "activation_code_id": code.id})
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Activation failed")
    db.refresh(user)

    token = create_user_token(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user_response(user),
    }


@router.post("/register")
async def register(req: RegisterRequest, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    ok, msg = validate_email(req.email)
    if not ok:
        raise HTTPException(status_code=422, detail=msg)
    ok, msg = validate_password(req.password)
    if not ok:
        raise HTTPException(status_code=422, detail=msg)

    existing = db.query(User).filter(User.email == normalize_email(req.email)).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    new_user = User(
        id=generate_id(),
        email=normalize_email(req.email),
        full_name=req.full_name,
        hashed_password=hash_password(req.password),
        school_name=req.school_name,
        is_admin=False,
        is_active=True,
        role="teacher",
        school_id=user.school_id,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "user": user_response(new_user),
    }


_DUMMY_PASSWORD_HASH = None


def _dummy_password_check(password: str) -> None:
    """Perform a bcrypt verification for an unknown identifier.

    Keeps timing closer to a real account check and avoids a trivial
    account-existence oracle. The result is deliberately ignored.
    """
    global _DUMMY_PASSWORD_HASH
    if _DUMMY_PASSWORD_HASH is None:
        _DUMMY_PASSWORD_HASH = hash_password("schemeKnit-dummy-password-check")
    try:
        verify_password(password, _DUMMY_PASSWORD_HASH)
    except Exception:
        pass


@router.post("/login")
async def login(req: LoginRequest, db: Session = Depends(get_db),
                request: Request = None):
    # The email is the login identifier and is compared normalized, so casing
    # at the keyboard never changes which account is matched.
    lookup = normalize_email(req.email) or req.email

    # Account-level cooldown is checked before password verification. The
    # counter is keyed opaquely and applies across all source IPs. Unknown
    # identifiers are tracked too, so the response never reveals existence.
    retry_after = check_lockout(db, lookup)
    if retry_after:
        log_security("login_locked", account=account_key(lookup),
                     retry_after=retry_after)
        raise HTTPException(
            status_code=429,
            detail=(
                "Too many sign-in attempts. Please wait before trying again."
            ),
            headers={"Retry-After": str(retry_after)},
        )

    # Risk-based bot challenge: normal logins stay frictionless; only an
    # account with recent failures must complete Turnstile. The token is
    # action-bound and single-use, so a registration token cannot be replayed
    # here.
    settings = get_settings()
    threshold = int(getattr(
        settings, "LOGIN_TURNSTILE_AFTER_FAILURES", 3) or 3)
    if recent_failure_count(db, lookup) >= threshold:
        require_turnstile(
            db, req.turnstile_token, action="login",
            remote_ip=client_ip(request) if request is not None else None,
        )

    user = db.query(User).filter(User.email == lookup).first()
    password_ok = bool(user) and verify_password(
        req.password, user.hashed_password)
    if not user:
        # Equalise timing for unknown identifiers; never disclose existence.
        _dummy_password_check(req.password)
    if not password_ok:
        cooldown = record_failure(db, lookup)
        if cooldown:
            alert_security("account_cooldown", account=account_key(lookup),
                         cooldown_seconds=cooldown)
            raise HTTPException(
                status_code=429,
                detail=(
                    "Too many sign-in attempts. Please wait before trying again."
                ),
                headers={"Retry-After": str(cooldown)},
            )
        log_security("login_failed", account=account_key(lookup),
                     reason="bad_credentials")
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        log_security("login_failed", account=account_key(lookup),
                     reason="disabled")
        raise HTTPException(status_code=403, detail="Account disabled")

    # Entry-point boundary: the client says WHICH login it is using; the
    # database says WHO the account is. Both must agree. A mismatch is
    # indistinguishable from bad credentials in the response.
    entry = (req.entry or "").strip().lower()
    if entry not in VALID_LOGIN_ENTRIES or not _entry_matches_role(user, entry):
        cooldown = record_failure(db, lookup)
        if cooldown:
            alert_security("account_cooldown", account=account_key(lookup),
                         cooldown_seconds=cooldown)
            raise HTTPException(
                status_code=429,
                detail=(
                    "Too many sign-in attempts. Please wait before trying again."
                ),
                headers={"Retry-After": str(cooldown)},
            )
        log_security("login_failed", account=account_key(lookup),
                     reason="entry_mismatch")
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if user.mfa_enabled:
        matched_step = None
        recovery_index = None
        if req.recovery_code:
            recovery_index = verify_recovery_code(
                req.recovery_code, user.mfa_recovery_codes or [])
        elif req.mfa_code:
            matched_step = verify_totp(user.mfa_secret or "", req.mfa_code)
            if matched_step is not None and user.mfa_last_step is not None \
                    and matched_step <= user.mfa_last_step:
                matched_step = None  # replay of an already-used code
        if recovery_index is None and matched_step is None:
            cooldown = record_failure(db, lookup)
            log_security("mfa_failed", account=account_key(lookup))
            if cooldown:
                raise HTTPException(
                    status_code=429,
                    detail="Too many sign-in attempts. Please wait before trying again.",
                    headers={"Retry-After": str(cooldown)},
                )
            raise HTTPException(status_code=401, detail="Invalid email or password")
        if recovery_index is not None:
            codes = list(user.mfa_recovery_codes or [])
            codes.pop(recovery_index)
            user.mfa_recovery_codes = codes
            log_security("mfa_recovery_used", user_id=user.id)
        else:
            user.mfa_last_step = matched_step
            log_security("mfa_verified", user_id=user.id)
        db.commit()

    clear_failures(db, lookup)
    jti = secrets.token_hex(16)
    token = create_user_token(user, jti=jti)
    create_session_record(db, user.id, jti)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user_response(user),
        "mfa_enrollment_required": bool(
            user.role == "platform_admin" and not user.mfa_enabled
        ),
    }


@router.post("/mfa/setup")
async def mfa_setup(
    response: Response,
    user: User = Depends(require_platform_admin_unenrolled),
    db: Session = Depends(get_db),
):
    """Start TOTP enrollment.

    The secret stays pending until ``/mfa/verify-setup`` accepts a current
    code. Operational deployments require enrollment before any platform-admin
    request; local DEBUG keeps fixtures simple.
    """
    if user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA is already enabled")
    secret = generate_secret()
    user.mfa_secret = secret
    user.mfa_enabled = False
    db.commit()
    log_security("mfa_setup_started", user_id=user.id)
    uri = provisioning_uri(secret, user.email)
    # The pending secret must never be cached by a proxy, browser or CDN.
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    return {
        "secret": secret,
        "otpauth_uri": uri,
        "qr_data_uri": provisioning_qr_data_uri(uri),
        "digits": 6,
        "period_seconds": 30,
    }


@router.post("/mfa/verify-setup")
async def mfa_verify_setup(
    req: MfaCodeRequest,
    user: User = Depends(require_platform_admin_unenrolled),
    db: Session = Depends(get_db),
):
    if user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA is already enabled")
    if not user.mfa_secret:
        raise HTTPException(status_code=400, detail="Start MFA setup first")
    step = verify_totp(user.mfa_secret, req.code)
    if step is None:
        log_security("mfa_setup_failed", user_id=user.id)
        raise HTTPException(status_code=400, detail="Invalid verification code")
    codes = generate_recovery_codes()
    user.mfa_recovery_codes = hash_recovery_codes(codes)
    user.mfa_last_step = step
    user.mfa_enabled = True
    db.commit()
    log_security("mfa_enabled", user_id=user.id)
    return {"enabled": True, "recovery_codes": codes}


@router.post("/mfa/disable")
async def mfa_disable(
    req: MfaDisableRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    if not user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA is not enabled")
    if not verify_password(req.password, user.hashed_password):
        log_security("mfa_disable_failed", user_id=user.id, reason="password")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    step = verify_totp(user.mfa_secret or "", req.code)
    recovery = verify_recovery_code(
        req.code, user.mfa_recovery_codes or [])
    if step is None and recovery is None:
        log_security("mfa_disable_failed", user_id=user.id, reason="code")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_recovery_codes = []
    user.mfa_last_step = None
    db.commit()
    log_security("mfa_disabled", user_id=user.id)
    return {"enabled": False}


@router.get("/mfa/status")
async def mfa_status(
    user: User = Depends(require_platform_admin_unenrolled),
):
    return {
        "enabled": bool(user.mfa_enabled),
        "recovery_codes_remaining": len(user.mfa_recovery_codes or []),
    }


@router.post("/mfa/recovery/regenerate")
async def mfa_regenerate_recovery(
    req: MfaRegenerateRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    if not user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA is not enabled")
    if not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    step = verify_totp(user.mfa_secret or "", req.code)
    recovery = verify_recovery_code(req.code, user.mfa_recovery_codes or [])
    if step is None and recovery is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    codes = generate_recovery_codes()
    user.mfa_recovery_codes = hash_recovery_codes(codes)
    db.commit()
    log_security("mfa_recovery_regenerated", user_id=user.id)
    return {"recovery_codes": codes}


@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sign out this session server-side.

    The access token is stateless, so logout records its unique ``jti`` until
    the token's natural expiry. Other devices keep their independent sessions;
    the password-version check is unchanged. Only the token id is stored.
    """
    payload = decode_token(credentials.credentials)
    jti = payload.get("jti")
    if jti:
        expires_at = datetime.utcnow() + timedelta(days=1)
        exp = payload.get("exp")
        if isinstance(exp, (int, float)):
            expires_at = datetime.utcfromtimestamp(exp)
        existing = (
            db.query(RevokedTokenDB)
            .filter(RevokedTokenDB.jti == jti)
            .first()
        )
        if existing is None:
            try:
                db.add(RevokedTokenDB(
                    jti=jti, user_id=user.id, expires_at=expires_at))
                db.commit()
            except Exception:
                # A concurrent logout of the same token already recorded it.
                db.rollback()
        session = db.query(UserSessionDB).filter(UserSessionDB.jti == jti).first()
        if session is not None and session.revoked_at is None:
            session.revoked_at = datetime.utcnow()
            db.commit()
    # Bounded cleanup: expired rows can never match a live token.
    try:
        db.query(RevokedTokenDB).filter(
            RevokedTokenDB.expires_at < datetime.utcnow()
        ).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
    return {"ok": True}


@router.post("/logout-all")
async def logout_all(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke every active server-side session for this account."""
    count = revoke_user_sessions(db, user.id)
    log_security("sessions_revoked_all", user_id=user.id, count=count)
    return {"ok": True, "revoked_sessions": count}


def _registration_allowed(mode: str, expected_code: str, supplied_code: str) -> bool:
    """Apply the configured self-registration gate.

    ``open`` preserves the historical behaviour. ``invite_only`` requires a
    non-empty configured code and a constant-time match. ``closed`` rejects
    every self-registration attempt; the owner creates accounts instead.
    """
    mode = (mode or "open").strip().lower()
    if mode == "open":
        return True
    if mode == "closed":
        return False
    expected = (expected_code or "").strip()
    supplied = (supplied_code or "").strip()
    if not expected or not supplied:
        return False
    return secrets.compare_digest(expected, supplied)


class IndividualRegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    #: Captured from a referral link and submitted with the new account. May
    #: be blank. Attribution happens exactly once, at registration.
    referral_code: str = ""
    #: Required only when the deployment is in invite-only pilot mode.
    invite_code: str = ""
    #: Cloudflare Turnstile token. Required when TURNSTILE_ENABLED=true,
    #: including invite-only deployments.
    turnstile_token: str = ""
@router.post("/register/individual")
async def register_individual_teacher(
    req: IndividualRegisterRequest,
    db: Session = Depends(get_db),
    request: Request = None,
):
    """Self-registration for individual teachers (no school required).

    Creates a teacher account on the Free Teacher plan. School selection is
    deliberately omitted — individual teachers start with school_id = NULL.
    """
    require_turnstile(
        db, req.turnstile_token, action="register",
        remote_ip=client_ip(request) if request is not None else None,
    )
    settings = get_settings()
    if not _registration_allowed(
        settings.REGISTRATION_MODE,
        settings.PILOT_INVITE_CODE,
        req.invite_code,
    ):
        raise HTTPException(
            status_code=403,
            detail="A valid pilot invite code is required to create an account",
        )

    ok, msg = validate_email(req.email)
    if not ok:
        raise HTTPException(status_code=422, detail=msg)
    ok, msg = validate_password(req.password)
    if not ok:
        raise HTTPException(status_code=422, detail=msg)

    normalized = normalize_email(req.email)
    existing = db.query(User).filter(User.email == normalized).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    from ..entitlements import get_user_entitlement, FREE_TIER_LESSON_PLANS_PER_MONTH
    from ..database import EntitlementDB

    new_user = User(
        id=generate_id(),
        email=normalized,
        full_name=req.full_name,
        hashed_password=hash_password(req.password),
        school_name="",
        is_admin=False,
        is_active=True,
        role="teacher",
        school_id=None,
        subscription_type="individual",
    )
    db.add(new_user)
    db.flush()

    # Create Free Tier entitlement. Lesson plans are 5 per CALENDAR MONTH and
    # AI is 5 per CALENDAR MONTH (both enforced server-side via the usage
    # ledgers, PART 16-18) â€” never a lifetime cap.
    free_ent = EntitlementDB(
        id=generate_id(),
        user_id=new_user.id,
        edition="free",
        subscription_type="individual",
        generation_limit=FREE_TIER_LESSON_PLANS_PER_MONTH,
        generations_used=0,
        batch_generation=False,
        zip_export=False,
        pdf_export=True,
        custom_template_limit=1,
        history_limit=10,
        ai_enabled=True,
        ai_credits=5,
        ai_credits_used=0,
    )
    db.add(free_ent)
    db.commit()
    db.refresh(new_user)

    # Referral attribution: only for this newly created account, only once.
    # Registration alone never grants credits â€” the reward waits for the
    # first verified paid package purchase.
    try:
        from .. import referrals
        referrals.attribute(db, new_user, req.referral_code)
    except Exception:
        db.rollback()

    token = create_user_token(new_user)
    log_security("individual_teacher_registered", user_id=new_user.id, email=new_user.email)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user_response(new_user),
    }


@router.get("/me")
async def get_profile(user: User = Depends(get_current_user)):
    return user_response(user)


@router.put("/me")
async def update_profile(
    payload: Optional[ProfileUpdateRequest] = Body(None),
    full_name: Optional[str] = None,
    school_name: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the teacher's profile.

    Accepts the JSON body the app sends (``{"full_name": ..., "school_name":
    ...}``) and the query-parameter form for compatibility. A missing field
    leaves the stored value alone; an explicit null/empty is honoured.
    """
    if payload is not None:
        if payload.full_name is not None:
            full_name = payload.full_name
        if payload.school_name is not None:
            school_name = payload.school_name
    if full_name is not None:
        user.full_name = full_name
    if school_name is not None:
        # PART 7 permission model: a teacher attached to a real school has a
        # server-authoritative school name and may not overwrite it with a
        # free-text value. An INDEPENDENT teacher (no membership) declares the
        # institution they teach at once, here, on their own profile.
        if getattr(user, "school_id", None):
            school = db.query(SchoolDB).filter(SchoolDB.id == user.school_id).first()
            if school and school.name:
                user.school_name = school.name
            else:
                user.school_name = ""
        else:
            cleaned = (school_name or "").strip()
            user.school_name = cleaned[:200]
    db.commit()
    return user_response(user)


@router.get("/my-plan")
async def get_my_plan(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the user's resolved entitlement from all applicable sources.

    For teachers with no school: returns individual Free or Pro entitlement.
    For school teachers: returns school entitlement.
    For teachers with both: returns the combined/resolved entitlement.
    """
    from ..entitlements import resolve_entitlement
    from .. import credits
    resolved = resolve_entitlement(db, user)
    resolved["credits"] = credits.status(db, user.id)
    return resolved


@router.get("/users")
async def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """List users. School admins see only users in their own school (Â§2 isolation)."""
    if admin.school_id:
        users = db.query(User).filter(User.school_id == admin.school_id).all()
    else:
        users = db.query(User).all()
    return {"users": [user_response(u) for u in users]}


@router.get("/my-school")
async def get_my_school(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    School-scoped overview for the SCHOOL ADMIN dashboard (Â§13):
    school name, license status, seats used/available, teacher roster.
    Returns only this admin's school â€” never platform-wide data.
    """
    from ..database import SchoolDB, SchoolLicenseDB, ProductPlanDB
    from sqlalchemy import func

    if not admin.school_id:
        return {"school": None, "license": None, "teachers": [], "seats": {"used": 0, "limit": 0}}

    school = db.query(SchoolDB).filter(SchoolDB.id == admin.school_id).first()
    license = db.query(SchoolLicenseDB).filter(
        SchoolLicenseDB.school_id == admin.school_id
    ).order_by(SchoolLicenseDB.expiry_date.desc()).first()
    plan = (
        db.query(ProductPlanDB).filter(ProductPlanDB.id == license.product_plan_id).first()
        if license else None
    )

    teachers = db.query(User).filter(
        User.school_id == admin.school_id,
        User.role == "teacher",
    ).all()
    seats_used = db.query(func.count(User.id)).filter(
        User.school_id == admin.school_id,
        User.role == "teacher",
        User.is_active == True,
    ).scalar() or 0

    return {
        "school": {
            "id": school.id,
            "name": school.name,
            "school_code": school.school_code,
            "contact_name": school.contact_name,
            "contact_phone": school.contact_phone,
            "contact_email": school.contact_email,
            "address": school.address,
            "status": school.status,
        } if school else None,
        "license": {
            "status": license.status,
            "plan": plan.name if plan else None,
            "start_date": license.start_date.isoformat() if license else None,
            "expiry_date": license.expiry_date.isoformat() if license else None,
            "seat_limit": license.seat_limit if license else 0,
        } if license else None,
        "teachers": [user_response(t) for t in teachers],
        "seats": {
            "used": int(seats_used),
            "limit": license.seat_limit if license else 0,
        },
    }


class UpdateSchoolRequest(BaseModel):
    name: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    address: Optional[str] = None


@router.put("/my-school")
async def update_my_school(
    req: UpdateSchoolRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """School admin can update their own school's profile."""
    from ..database import SchoolDB
    if not admin.school_id:
        raise HTTPException(status_code=400, detail="No school associated with this account")

    school = db.query(SchoolDB).filter(SchoolDB.id == admin.school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    for field in ["name", "contact_name", "contact_phone", "contact_email", "address"]:
        val = getattr(req, field, None)
        if val is not None:
            setattr(school, field, val)

    _school_audit(db, admin.id, admin.role, "school_settings_changed",
                  "school", school.id, {})
    db.commit()
    return {"message": "School profile updated"}


def _usable_license(db: Session, school_id: str):
    """Active, non-expired license for teacher creation. None-safe."""
    from datetime import date
    license = db.query(SchoolLicenseDB).filter(
        SchoolLicenseDB.school_id == school_id,
        SchoolLicenseDB.status == "active",
    ).first()
    if not license:
        return None
    if license.expiry_date and license.expiry_date < date.today():
        return None
    return license


def _require_same_school(admin: User, target: User):
    """Cross-school isolation for user management.

    Platform admins (no school) retain platform-wide control; school admins
    are confined to their own school. Unknown/missing target school never matches.
    """
    if admin.school_id is None and admin.role == "platform_admin":
        return
    if not target.school_id or target.school_id != admin.school_id:
        raise HTTPException(status_code=403, detail="Not authorized for this school's users")


@router.post("/users")
async def create_teacher(req: CreateTeacherRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    ok, msg = validate_email(req.email)
    if not ok:
        raise HTTPException(status_code=422, detail=msg)
    ok, msg = validate_password(req.password)
    if not ok:
        raise HTTPException(status_code=422, detail=msg)

    existing = db.query(User).filter(User.email == normalize_email(req.email)).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    # Seat rule: only ACTIVE teachers consume seats. Creation requires a usable
    # (active, non-expired) license; unlicensed/suspended/expired schools cannot grow.
    if admin.school_id:
        from sqlalchemy import func
        license = _usable_license(db, admin.school_id)
        if not license:
            raise HTTPException(
                status_code=403,
                detail="School has no usable license. Activate or renew the school license "
                       "before adding teachers.",
            )
        active_teacher_count = db.query(func.count(User.id)).filter(
            User.school_id == admin.school_id,
            User.role == "teacher",
            User.is_active == True,
        ).scalar()
        if active_teacher_count >= license.seat_limit:
            raise HTTPException(
                status_code=403,
                detail=f"School has reached the seat limit ({license.seat_limit}). "
                       "Please upgrade your license to add more teachers.",
            )

    user = User(
        id=generate_id(),
        email=normalize_email(req.email),
        full_name=req.full_name,
        hashed_password=hash_password(req.password),
        school_name=req.school_name,
        is_admin=False,
        is_active=True,
        role="teacher",
        school_id=admin.school_id,
    )
    db.add(user)

    if admin.school_id:
        membership = SchoolMembershipDB(
            id=generate_id(),
            user_id=user.id,
            school_id=admin.school_id,
            role="teacher",
            status="active",
        )
        db.add(membership)
        _school_audit(db, admin.id, admin.role, "teacher_created",
                      "user", user.id, {"school_id": admin.school_id})

    db.commit()
    db.refresh(user)
    return {"user": user_response(user)}


class UpdateTeacherRequest(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None


@router.put("/users/{user_id}")
async def update_teacher(user_id: str, req: UpdateTeacherRequest,
                         admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Edit a teacher's basic info. School-scoped; role/school never client-settable."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _require_same_school(admin, user)
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Use profile settings for your own account")
    if req.email and req.email != user.email:
        if db.query(User).filter(User.email == req.email).first():
            raise HTTPException(status_code=409, detail="Email already registered")
        user.email = req.email
    if req.full_name is not None:
        user.full_name = req.full_name
    _school_audit(db, admin.id, admin.role, "teacher_updated", "user", user.id, {})
    db.commit()
    db.refresh(user)
    return {"user": user_response(user)}


@router.put("/users/{user_id}/toggle-active")
async def toggle_user_active(user_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    from sqlalchemy import func
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _require_same_school(admin, user)
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    if not user.is_active and user.role == "teacher" and user.school_id:
        # Reactivation re-checks the seat rule: a freed seat may be gone.
        license = _usable_license(db, user.school_id)
        if not license:
            raise HTTPException(
                status_code=403,
                detail="School has no usable license. Activate or renew before reactivating teachers.",
            )
        active_teacher_count = db.query(func.count(User.id)).filter(
            User.school_id == user.school_id,
            User.role == "teacher",
            User.is_active == True,  # noqa: E712
        ).scalar()
        if active_teacher_count >= license.seat_limit:
            raise HTTPException(
                status_code=403,
                detail=f"School has reached the seat limit ({license.seat_limit}).",
            )
    # Guard: never deactivate the last active platform admin (removes the
    # only recovery path for the whole platform).
    if user.is_active and user.role == "platform_admin":
        active_admins = db.query(func.count(User.id)).filter(
            User.role == "platform_admin",
            User.is_active == True,  # noqa: E712
        ).scalar()
        if active_admins <= 1:
            raise HTTPException(
                status_code=403,
                detail="Cannot deactivate the last active platform administrator.",
            )
    user.is_active = not user.is_active
    _school_audit(db, admin.id, admin.role,
                  "teacher_reactivated" if user.is_active else "teacher_deactivated",
                  "user", user.id, {})
    db.commit()
    return {"user": user_response(user)}


@router.post("/users/{user_id}/reset-password")
async def reset_password(user_id: str, req: LoginRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _require_same_school(admin, user)
    ok, msg = validate_password(req.password)
    if not ok:
        raise HTTPException(status_code=422, detail=msg)
    user.hashed_password = hash_password(req.password)
    user.password_changed_at = datetime.utcnow()
    _school_audit(db, admin.id, admin.role, "teacher_password_reset", "user", user.id, {})
    db.commit()
    clear_failures(db, user.email)
    revoke_user_sessions(db, user.id)
    return {"message": "Password reset successfully"}


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# PLATFORM ADMIN BOOTSTRAP
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


def _platform_admin_exists(db: Session) -> bool:
    """True if at least one active platform admin exists."""
    return db.query(User).filter(
        User.role == "platform_admin",
        User.is_active == True,  # noqa: E712
    ).first() is not None


@router.get("/setup-platform-admin/status")
async def platform_admin_setup_status(db: Session = Depends(get_db)):
    """Public check: is the one-time platform-admin bootstrap still open?

    Reveals only a boolean â€” no secrets, no account data.
    """
    return {"bootstrap_required": not _platform_admin_exists(db)}


class PlatformAdminBootstrapRequest(BaseModel):
    bootstrap_secret: str
    full_name: str
    email: str
    password: str


@router.post("/setup-platform-admin")
async def setup_platform_admin(req: PlatformAdminBootstrapRequest, db: Session = Depends(get_db)):
    """Create the FIRST platform admin. One-time, secret-guarded, race-safe.

    Security properties:
    - Available only while zero active platform admins exist.
    - Requires PLATFORM_ADMIN_BOOTSTRAP_SECRET from server configuration.
    - Race-safe: the INSERT is conditional (WHERE NOT EXISTS), so two
      simultaneous requests cannot both create a first admin.
    - The secret is compared in constant time and never logged.
    - After success the endpoint permanently returns 410.
    """
    # 1. Close bootstrap if an admin already exists (backend-enforced).
    if _platform_admin_exists(db):
        raise HTTPException(
            status_code=410,
            detail="Platform administrator setup has already been completed.",
        )

    # 2. The bootstrap secret must be configured and match.
    expected = get_settings().PLATFORM_ADMIN_BOOTSTRAP_SECRET
    if not expected:
        log_security("platform_admin_bootstrap_disabled",
                     reason="secret_not_configured")
        raise HTTPException(
            status_code=404,
            detail="Platform administrator setup is not available.",
        )
    if not secrets.compare_digest(expected, req.bootstrap_secret):
        log_security("platform_admin_bootstrap_failed",
                     reason="bad_secret")
        raise HTTPException(
            status_code=403,
            detail="Invalid bootstrap secret.",
        )

    # 3. Validate email + password against the production policy.
    ok, msg = validate_email(req.email)
    if not ok:
        raise HTTPException(status_code=422, detail=msg)
    ok, msg = validate_password(req.password)
    if not ok:
        raise HTTPException(status_code=422, detail=msg)

    normalized = normalize_email(req.email)
    existing = db.query(User).filter(User.email == normalized).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    # 4. Race-safe insert: only succeed if no platform_admin was created
    #    concurrently. works on both SQLite and PostgreSQL.
    from sqlalchemy import text
    user_id = generate_id()
    now = datetime.utcnow()
    try:
        result = db.execute(text("""
            INSERT INTO users (id, email, full_name, hashed_password,
                               is_admin, is_active, role, school_id,
                               password_changed_at, mfa_enabled, mfa_secret,
                               mfa_recovery_codes, mfa_last_step,
                               created_at, updated_at)
            SELECT :id, :email, :name, :password,
                   TRUE, TRUE, 'platform_admin', NULL,
                   :now, FALSE, NULL, NULL, NULL,
                   :now, :now
            WHERE NOT EXISTS (
                SELECT 1 FROM users
                WHERE role = 'platform_admin' AND is_active = TRUE
            )
        """), {
            "id": user_id,
            "email": normalized,
            "name": req.full_name,
            "password": hash_password(req.password),
            "now": now,
        })
        if result.rowcount == 0:
            # Someone else won the race; bootstrap is closed.
            db.rollback()
            raise HTTPException(
                status_code=410,
                detail="Platform administrator setup has already been completed.",
            )
        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        log_security("platform_admin_bootstrap_failed", reason="server_error")
        raise HTTPException(status_code=500, detail="Setup failed")

    user = db.query(User).filter(User.id == user_id).first()

    # Audit: actor is the new admin itself; no secret is ever logged.
    _school_audit(
        db, user.id, "platform_admin", "platform_admin_created",
        "user", user.id,
        {"email": user.email, "method": "web_bootstrap"},
    )
    db.commit()

    log_security("platform_admin_bootstrap_success", user_id=user.id)
    token = create_user_token(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user_response(user),
    }


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# SELF-SERVICE PASSWORD CHANGE (all roles)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Authenticated self-service password change.

    The user must prove knowledge of their CURRENT password. The new password
    must satisfy the production policy. On success the password version is
    bumped (invalidating all other sessions) and a fresh token is issued so
    the current session stays usable.
    """
    if not verify_password(req.current_password, user.hashed_password):
        log_security("password_change_failed", user_id=user.id,
                     reason="bad_current_password")
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    if req.current_password == req.new_password:
        raise HTTPException(
            status_code=422,
            detail="New password must be different from your current password.",
        )

    ok, msg = validate_password(req.new_password)
    if not ok:
        raise HTTPException(status_code=422, detail=msg)

    user.hashed_password = hash_password(req.new_password)
    user.password_changed_at = datetime.utcnow()

    _school_audit(db, user.id, user.role, "password_changed", "user", user.id, {})
    db.commit()
    clear_failures(db, user.email)
    revoke_user_sessions(db, user.id)

    # Issue a fresh token/session stamped with the new password version so the
    # current device stays usable; every OTHER token is now stale.
    jti = secrets.token_hex(16)
    token = create_user_token(user, jti=jti)
    create_session_record(db, user.id, jti)
    return {
        "message": "Password changed successfully",
        "access_token": token,
        "token_type": "bearer",
    }


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# TOKEN-BASED PASSWORD RESET (admin-initiated)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

RESET_TOKEN_TTL = timedelta(minutes=get_settings().PASSWORD_RESET_TOKEN_TTL_MINUTES)


def _hash_token(raw_token: str) -> str:
    """SHA-256 digest of a raw reset token. Only the digest is persisted."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _create_reset_token(db: Session, target: User, initiated_by: User,
                        method: str = "web_admin") -> str:
    """Issue a one-time, expiring reset token bound to ``target``.

    Returns the RAW token (shown once to the initiating admin). Only its
    SHA-256 digest is stored in the database.
    """
    raw = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    db.add(PasswordResetTokenDB(
        id=generate_id(),
        user_id=target.id,
        token_hash=_hash_token(raw),
        expires_at=now + RESET_TOKEN_TTL,
        used_at=None,
        initiated_by=initiated_by.id,
        initiated_at=now,
        method=method,
    ))
    db.commit()
    return raw


def _consume_reset_token(db: Session, raw_token: str) -> PasswordResetTokenDB:
    """Validate a raw reset token and mark it used (single-use).

    Returns the token row on success. Raises HTTPException on any failure.
    """
    if not raw_token or not raw_token.strip():
        raise HTTPException(status_code=422, detail="Reset token is required")

    record = db.query(PasswordResetTokenDB).filter(
        PasswordResetTokenDB.token_hash == _hash_token(raw_token.strip()),
    ).first()

    if record is None:
        log_security("password_reset_token_invalid", reason="not_found")
        raise HTTPException(status_code=404, detail="Invalid reset token")

    if record.used_at is not None:
        log_security("password_reset_token_invalid", reason="already_used",
                     user_id=record.user_id)
        raise HTTPException(status_code=410, detail="This reset token has already been used")

    if record.expires_at < datetime.utcnow():
        log_security("password_reset_token_invalid", reason="expired",
                     user_id=record.user_id)
        raise HTTPException(status_code=410, detail="This reset token has expired")

    # Bind: the token must belong to a real, active user.
    target = db.query(User).filter(User.id == record.user_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="Invalid reset token")
    if not target.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    # Single-use: consume BEFORE setting the password so a concurrent
    # attempt with the same token finds it already used.
    record.used_at = datetime.utcnow()
    db.commit()
    return record


@router.post("/users/{user_id}/initiate-reset")
async def initiate_password_reset(
    user_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin-initiated, token-based password reset.

    School admins may reset teachers in their own school only.
    Platform admins may reset any account (school admin, teacher,
    individual teacher, or another platform admin).

    The response contains a one-time reset code that the admin must deliver
    to the user out-of-band (the platform has no email delivery yet). The
    code is single-use, expires in 30 minutes, and is bound to the target.
    """
    target = db.query(User).filter(User.id == user_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Cross-school isolation (platform admins bypass).
    _require_same_school(admin, target)

    # Nobody resets themselves here â€” use the self-service change-password.
    if target.id == admin.id:
        raise HTTPException(
            status_code=400,
            detail="Use the password change form to change your own password.",
        )

    # School admins may only reset teachers; platform admins may reset anyone.
    if admin.role != "platform_admin" and target.role != "teacher":
        raise HTTPException(
            status_code=403,
            detail="Only platform administrators can reset non-teacher accounts.",
        )

    raw_token = _create_reset_token(db, target, admin, method="web_admin")

    _school_audit(
        db, admin.id, admin.role, "password_reset_initiated",
        "user", target.id,
        {"target_role": target.role, "target_email": target.email},
    )
    db.commit()

    # The raw token is returned ONCE to the initiating admin. It is never
    # persisted in plaintext, never logged, and never returned again.
    return {
        "message": "Password reset initiated.",
        "reset_token": raw_token,
        "expires_in_minutes": get_settings().PASSWORD_RESET_TOKEN_TTL_MINUTES,
        "target_email": target.email,
    }


@router.get("/reset-token/validate")
async def validate_reset_token(
    token: str,
    db: Session = Depends(get_db),
):
    """Public validation of a reset token.

    Returns the target email so the user can confirm which account they are
    about to reset. Does NOT consume the token.
    """
    if not token or not token.strip():
        raise HTTPException(status_code=422, detail="Reset token is required")

    record = db.query(PasswordResetTokenDB).filter(
        PasswordResetTokenDB.token_hash == _hash_token(token.strip()),
    ).first()

    if record is None:
        raise HTTPException(status_code=404, detail="Invalid reset token")
    if record.used_at is not None:
        raise HTTPException(status_code=410, detail="This reset token has already been used")
    if record.expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="This reset token has expired")

    target = db.query(User).filter(User.id == record.user_id).first()
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="Invalid reset token")

    return {"email": target.email, "full_name": target.full_name}


class ConfirmPasswordResetRequest(BaseModel):
    reset_token: str
    new_password: str
    #: Cloudflare Turnstile token. Required when TURNSTILE_ENABLED=true.
    turnstile_token: str = ""


@router.post("/confirm-password-reset")
async def confirm_password_reset(
    req: ConfirmPasswordResetRequest,
    db: Session = Depends(get_db),
    request: Request = None,
):
    """Complete a password reset with a one-time token + new password.

    Public (the user has no session when recovering). The token is consumed
    (single-use), the password is set, and ALL existing sessions for the
    target user are invalidated via the password-version bump.
    """
    require_turnstile(
        db, req.turnstile_token, action="password_reset",
        remote_ip=client_ip(request) if request is not None else None,
    )
    record = _consume_reset_token(db, req.reset_token)

    target = db.query(User).filter(User.id == record.user_id).first()

    ok, msg = validate_password(req.new_password)
    if not ok:
        raise HTTPException(status_code=422, detail=msg)

    target.hashed_password = hash_password(req.new_password)
    target.password_changed_at = datetime.utcnow()

    _school_audit(
        db, target.id, target.role, "password_reset_completed",
        "user", target.id,
        {"method": record.method},
    )
    db.commit()
    clear_failures(db, target.email)
    revoke_user_sessions(db, target.id)

    log_security("password_reset_completed", user_id=target.id)
    # No token returned: the user must sign in fresh.
    return {"message": "Password has been reset successfully. Please sign in."}
