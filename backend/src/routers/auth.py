"""
SchemeKnit Auth Router

Registration, login, profile management, first-run setup,
platform-admin bootstrap, password change and token-based password reset.
"""

from datetime import datetime, timedelta
import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from ..database import (
    get_db, User, generate_id, SchoolLicenseDB, SchoolMembershipDB,
    ActivationCodeDB, SchoolDB, ProductPlanDB, PlatformAuditLogDB,
    PasswordResetTokenDB,
)
from ..auth import (
    hash_password, verify_password, create_user_token,
    get_current_user, require_admin, require_platform_admin,
)
from ..service import data_service
from ..config import get_settings
from ..logging_config import log_security
from ..validation import (
    validate_password, validate_email, normalize_email, password_policy_hint,
)

router = APIRouter()

MIN_SETUP_PASSWORD_LEN = 8


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
    (school name, plan, seats, period) — no secrets, no redemption."""
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
    The school always comes from the code's license — never from the client.
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


@router.post("/login")
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    # The email is the login identifier and is compared normalized, so casing
    # at the keyboard never changes which account is matched.
    lookup = normalize_email(req.email) or req.email
    user = db.query(User).filter(User.email == lookup).first()
    if not user or not verify_password(req.password, user.hashed_password):
        # Security audit: identifier + result only. Never passwords, hashes, tokens.
        # Same message whether the email exists or not (no enumeration oracle).
        log_security("login_failed", email=req.email, reason="bad_credentials")
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        log_security("login_failed", email=req.email, reason="disabled")
        raise HTTPException(status_code=403, detail="Account disabled")

    token = create_user_token(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user_response(user),
    }


class IndividualRegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str


@router.post("/register/individual")
async def register_individual_teacher(
    req: IndividualRegisterRequest,
    db: Session = Depends(get_db),
):
    """Self-registration for individual teachers (no school required).

    Creates a teacher account on the Free Teacher plan. School selection is
    deliberately omitted — individual teachers start with school_id = NULL.
    """
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

    # Create Free Tier entitlement. Lesson plans are 5 per CALENDAR MONTH
    # (enforced server-side via the usage ledger); AI is a separate lifetime
    # allowance of 5.
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
    full_name: str = None,
    school_name: str = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if full_name is not None:
        user.full_name = full_name
    if school_name is not None:
        user.school_name = school_name
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
    return resolve_entitlement(db, user)


@router.get("/users")
async def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """List users. School admins see only users in their own school (§2 isolation)."""
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
    School-scoped overview for the SCHOOL ADMIN dashboard (§13):
    school name, license status, seats used/available, teacher roster.
    Returns only this admin's school — never platform-wide data.
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
    return {"message": "Password reset successfully"}


# ══════════════════════════════════════════════════════════════════════════════
# PLATFORM ADMIN BOOTSTRAP
# ══════════════════════════════════════════════════════════════════════════════


def _platform_admin_exists(db: Session) -> bool:
    """True if at least one active platform admin exists."""
    return db.query(User).filter(
        User.role == "platform_admin",
        User.is_active == True,  # noqa: E712
    ).first() is not None


@router.get("/setup-platform-admin/status")
async def platform_admin_setup_status(db: Session = Depends(get_db)):
    """Public check: is the one-time platform-admin bootstrap still open?

    Reveals only a boolean — no secrets, no account data.
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
                               password_changed_at, created_at, updated_at)
            SELECT :id, :email, :name, :password,
                   TRUE, TRUE, 'platform_admin', NULL,
                   :now, :now, :now
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


# ══════════════════════════════════════════════════════════════════════════════
# SELF-SERVICE PASSWORD CHANGE (all roles)
# ══════════════════════════════════════════════════════════════════════════════


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

    # Issue a fresh token stamped with the new password version so the
    # current session remains valid; every OTHER token is now stale.
    token = create_user_token(user)
    return {
        "message": "Password changed successfully",
        "access_token": token,
        "token_type": "bearer",
    }


# ══════════════════════════════════════════════════════════════════════════════
# TOKEN-BASED PASSWORD RESET (admin-initiated)
# ══════════════════════════════════════════════════════════════════════════════

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

    # Nobody resets themselves here — use the self-service change-password.
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


@router.post("/confirm-password-reset")
async def confirm_password_reset(
    req: ConfirmPasswordResetRequest,
    db: Session = Depends(get_db),
):
    """Complete a password reset with a one-time token + new password.

    Public (the user has no session when recovering). The token is consumed
    (single-use), the password is set, and ALL existing sessions for the
    target user are invalidated via the password-version bump.
    """
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

    log_security("password_reset_completed", user_id=target.id)
    # No token returned: the user must sign in fresh.
    return {"message": "Password has been reset successfully. Please sign in."}
