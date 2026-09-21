"""
SchemeKnit Platform Admin Router

Endpoints for BloomCore/SchemeKnit platform administration.
Manages schools, licenses, activations, product plans, and payments.
"""

import secrets
import string
from datetime import datetime, date, timedelta
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import (
    get_db, User, SchoolDB, SchoolMembershipDB, SchoolLicenseDB,
    ActivationCodeDB, IndividualActivationCodeDB, ProductPlanDB, PaymentDB, PlatformAuditLogDB,
    LicenseCacheDB, generate_id,
)
from ..auth import get_current_user, require_platform_admin
from ..config import get_settings
from ..logging_config import get_logger, log_event

router = APIRouter()
logger = get_logger()


# ── Pydantic Models ──────────────────────────────────────────────────────────

class CreateSchoolRequest(BaseModel):
    name: str
    school_code: str
    contact_name: str = ""
    contact_phone: str = ""
    contact_email: str = ""
    address: str = ""


class UpdateSchoolRequest(BaseModel):
    name: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    address: Optional[str] = None
    status: Optional[str] = None


class CreateProductPlanRequest(BaseModel):
    name: str
    description: str = ""
    product_type: str
    price: float
    currency: str = "GHS"
    duration_days: Optional[int] = None
    seat_limit: int = 10
    features: List[str] = []


class CreateLicenseRequest(BaseModel):
    school_id: str
    product_plan_id: str
    seat_limit: Optional[int] = None


class ActivateLicenseRequest(BaseModel):
    activation_code: str


class CreateSchoolAdminRequest(BaseModel):
    email: str
    password: str
    full_name: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generate_activation_code() -> str:
    """Generate a secure activation code: TF-SCH-XXXX-XXXX-XXXX."""
    chars = string.ascii_uppercase + string.digits
    parts = [''.join(secrets.choice(chars) for _ in range(4)) for _ in range(3)]
    return f"TF-SCH-{'-'.join(parts)}"


def _generate_license_code() -> str:
    """Generate a license code: TF-LIC-XXXX-XXXX."""
    chars = string.ascii_uppercase + string.digits
    parts = [''.join(secrets.choice(chars) for _ in range(4)) for _ in range(2)]
    return f"TF-LIC-{'-'.join(parts)}"


def _license_view(db: Session, lic: SchoolLicenseDB) -> dict:
    """Server-derived license view for Platform Admin.

    Everything here is recomputed from stored rows on every request — never
    cached, never taken from a previous response — so the Platform Admin view
    reflects a school's activation as soon as it happens.

    Activation model:
      status          — raw lifecycle column (pending/active/suspended/...)
      effective_status — `status` with elapsed expiry folded in, which is what
                          an operator actually needs to see
      activated_at    — when a school first claimed this license with a code
                          (null = created but not yet claimed)
    """
    today = date.today()
    school = db.query(SchoolDB).filter(SchoolDB.id == lic.school_id).first()
    plan = db.query(ProductPlanDB).filter(ProductPlanDB.id == lic.product_plan_id).first()

    # Real seat usage = every active account provisioned into the school,
    # whatever its role. Counting teachers only hid the school-admin account
    # that activation itself creates.
    seats_used = db.query(func.count(func.distinct(User.id))).filter(
        User.school_id == lic.school_id,
        User.is_active == True,  # noqa: E712 — SQLAlchemy needs the comparison
    ).scalar() or 0

    effective_status = lic.status
    if lic.status == "active" and lic.expiry_date and lic.expiry_date < today:
        effective_status = "expired"

    code = None
    if lic.activation_code_id:
        code = db.query(ActivationCodeDB).filter(
            ActivationCodeDB.id == lic.activation_code_id).first()
    else:
        # Older rows predate activation tracking: fall back to the code that
        # actually redeemed against this license so the operator still sees it.
        code = db.query(ActivationCodeDB).filter(
            ActivationCodeDB.license_id == lic.id,
            ActivationCodeDB.status == "used",
        ).order_by(ActivationCodeDB.used_at.asc()).first()

    return {
        "id": lic.id,
        "license_code": lic.license_code,
        "school_id": lic.school_id,
        "school_name": school.name if school else "Unknown",
        "school_code": school.school_code if school else "",
        "plan_name": plan.name if plan else "Unknown",
        "seat_limit": lic.seat_limit,
        "seats_used": int(seats_used),
        "seats_available": max(0, (lic.seat_limit or 0) - int(seats_used)),
        "status": lic.status,
        "effective_status": effective_status,
        "is_active": effective_status == "active",
        "start_date": lic.start_date.isoformat() if lic.start_date else None,
        "expiry_date": lic.expiry_date.isoformat() if lic.expiry_date else None,
        "activated_at": lic.activated_at.isoformat() if lic.activated_at else None,
        "activation_code": code.code if code else None,
        "activation_code_status": code.status if code else None,
        "claimed_by_school": lic.activated_at is not None or bool(code),
        "created_at": lic.created_at.isoformat() if lic.created_at else None,
    }


def _audit_log(db: Session, actor: User, action: str, target_type: str = "", target_id: str = "", details: dict = None):
    """Write to platform audit log."""
    log = PlatformAuditLogDB(
        id=generate_id(),
        actor_id=actor.id,
        actor_role=actor.role,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details or {},
    )
    db.add(log)


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def platform_dashboard(
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    """Platform admin dashboard with commercial metrics."""
    today = date.today()

    active_schools = db.query(SchoolDB).filter(SchoolDB.status == "active").count()
    total_schools = db.query(SchoolDB).count()

    active_licenses = db.query(SchoolLicenseDB).filter(
        SchoolLicenseDB.status == "active"
    ).count()
    expiring_soon = db.query(SchoolLicenseDB).filter(
        SchoolLicenseDB.status == "active",
        SchoolLicenseDB.expiry_date <= today + timedelta(days=30),
        SchoolLicenseDB.expiry_date > today,
    ).count()
    expired_licenses = db.query(SchoolLicenseDB).filter(
        SchoolLicenseDB.status == "active",
        SchoolLicenseDB.expiry_date < today,
    ).count()

    total_teachers = db.query(User).filter(User.role == "teacher").count()
    seat_limit_sum = db.query(func.sum(SchoolLicenseDB.seat_limit)).filter(
        SchoolLicenseDB.status == "active"
    ).scalar() or 0

    pending_payments = db.query(PaymentDB).filter(PaymentDB.status == "pending").count()
    verified_revenue = db.query(func.sum(PaymentDB.amount)).filter(
        PaymentDB.status == "verified"
    ).scalar() or 0

    return {
        "active_schools": active_schools,
        "total_schools": total_schools,
        "active_licenses": active_licenses,
        "expiring_soon": expiring_soon,
        "expired_licenses": expired_licenses,
        "total_teachers": total_teachers,
        "total_seat_limit": int(seat_limit_sum),
        "seats_available": int(seat_limit_sum) - total_teachers,
        "pending_payments": pending_payments,
        "verified_revenue": float(verified_revenue),
        "currency": "GHS",
    }


# ── Schools ───────────────────────────────────────────────────────────────────

@router.get("/schools")
async def list_schools(
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    schools = db.query(SchoolDB).order_by(SchoolDB.created_at.desc()).all()
    result = []
    for s in schools:
        teacher_count = db.query(User).filter(User.school_id == s.id, User.role == "teacher").count()
        active_license = db.query(SchoolLicenseDB).filter(
            SchoolLicenseDB.school_id == s.id,
            SchoolLicenseDB.status == "active",
        ).first()
        result.append({
            "id": s.id,
            "name": s.name,
            "school_code": s.school_code,
            "contact_name": s.contact_name,
            "contact_phone": s.contact_phone,
            "contact_email": s.contact_email,
            "address": s.address,
            "status": s.status,
            "teacher_count": teacher_count,
            "has_active_license": active_license is not None,
            "license_expiry": active_license.expiry_date.isoformat() if active_license else None,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        })
    return {"schools": result}


@router.post("/schools")
async def create_school(
    req: CreateSchoolRequest,
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    existing = db.query(SchoolDB).filter(SchoolDB.school_code == req.school_code).first()
    if existing:
        raise HTTPException(status_code=409, detail="School code already exists")

    school = SchoolDB(
        id=generate_id(),
        name=req.name,
        school_code=req.school_code,
        contact_name=req.contact_name,
        contact_phone=req.contact_phone,
        contact_email=req.contact_email,
        address=req.address,
        status="active",
    )
    db.add(school)
    _audit_log(db, user, "school_created", "school", school.id, {"name": school.name})
    db.commit()
    db.refresh(school)

    return {
        "id": school.id,
        "name": school.name,
        "school_code": school.school_code,
        "status": school.status,
    }


@router.get("/schools/{school_id}")
async def get_school(
    school_id: str,
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    school = db.query(SchoolDB).filter(SchoolDB.id == school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    teachers = db.query(User).filter(User.school_id == school_id).all()
    # Prefer the license the school actually claimed, then any active license.
    # Reporting only "active" made a pending/unclaimed license look absent.
    license = db.query(SchoolLicenseDB).filter(
        SchoolLicenseDB.school_id == school_id,
        SchoolLicenseDB.activated_at.isnot(None),
    ).order_by(SchoolLicenseDB.activated_at.desc()).first()
    if not license:
        license = db.query(SchoolLicenseDB).filter(
            SchoolLicenseDB.school_id == school_id,
            SchoolLicenseDB.status == "active",
        ).first()
    if not license:
        license = db.query(SchoolLicenseDB).filter(
            SchoolLicenseDB.school_id == school_id,
        ).order_by(SchoolLicenseDB.created_at.desc()).first()

    return {
        "id": school.id,
        "name": school.name,
        "school_code": school.school_code,
        "contact_name": school.contact_name,
        "contact_phone": school.contact_phone,
        "contact_email": school.contact_email,
        "address": school.address,
        "status": school.status,
        "created_at": school.created_at.isoformat() if school.created_at else None,
        "teachers": [{"id": t.id, "email": t.email, "full_name": t.full_name, "role": t.role, "is_active": t.is_active} for t in teachers],
        "license": _license_view(db, license) if license else None,
    }


@router.put("/schools/{school_id}")
async def update_school(
    school_id: str,
    req: UpdateSchoolRequest,
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    school = db.query(SchoolDB).filter(SchoolDB.id == school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    if req.name is not None: school.name = req.name
    if req.contact_name is not None: school.contact_name = req.contact_name
    if req.contact_phone is not None: school.contact_phone = req.contact_phone
    if req.contact_email is not None: school.contact_email = req.contact_email
    if req.address is not None: school.address = req.address
    if req.status is not None: school.status = req.status

    _audit_log(db, user, "school_updated", "school", school.id)
    db.commit()
    return {"message": "School updated"}


# ── Product Plans ─────────────────────────────────────────────────────────────

@router.get("/plans")
async def list_product_plans(
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    plans = db.query(ProductPlanDB).order_by(ProductPlanDB.created_at.desc()).all()
    return {
        "plans": [{
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "product_type": p.product_type,
            "price": p.price,
            "currency": p.currency,
            "duration_days": p.duration_days,
            "seat_limit": p.seat_limit,
            "features": p.features or [],
            "active": p.active,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        } for p in plans]
    }


@router.post("/plans")
async def create_product_plan(
    req: CreateProductPlanRequest,
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    plan = ProductPlanDB(
        id=generate_id(),
        name=req.name,
        description=req.description,
        product_type=req.product_type,
        price=req.price,
        currency=req.currency,
        duration_days=req.duration_days,
        seat_limit=req.seat_limit,
        features=req.features,
    )
    db.add(plan)
    _audit_log(db, user, "plan_created", "plan", plan.id, {"name": plan.name, "price": plan.price})
    db.commit()
    db.refresh(plan)

    return {
        "id": plan.id,
        "name": plan.name,
        "price": plan.price,
        "seat_limit": plan.seat_limit,
    }


# ── Licenses ──────────────────────────────────────────────────────────────────

@router.get("/licenses")
async def list_licenses(
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    licenses = db.query(SchoolLicenseDB).order_by(SchoolLicenseDB.created_at.desc()).all()
    return {"licenses": [_license_view(db, lic) for lic in licenses]}


@router.post("/licenses")
async def create_license(
    req: CreateLicenseRequest,
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    school = db.query(SchoolDB).filter(SchoolDB.id == req.school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    plan = db.query(ProductPlanDB).filter(ProductPlanDB.id == req.product_plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Product plan not found")

    today = date.today()
    expiry = today + timedelta(days=plan.duration_days or 365)

    license = SchoolLicenseDB(
        id=generate_id(),
        school_id=req.school_id,
        product_plan_id=req.product_plan_id,
        license_code=_generate_license_code(),
        status="pending",
        start_date=today,
        expiry_date=expiry,
        seat_limit=req.seat_limit or plan.seat_limit,
    )
    db.add(license)

    # Generate initial activation code
    activation = ActivationCodeDB(
        id=generate_id(),
        license_id=license.id,
        code=_generate_activation_code(),
        status="active",
        expires_at=datetime.utcnow() + timedelta(days=30),
    )
    db.add(activation)

    _audit_log(db, user, "license_created", "license", license.id, {
        "school": school.name, "plan": plan.name, "code": activation.code,
    })
    db.commit()
    db.refresh(license)

    return {
        "id": license.id,
        "license_code": license.license_code,
        "activation_code": activation.code,
        "status": license.status,
        "start_date": license.start_date.isoformat(),
        "expiry_date": license.expiry_date.isoformat(),
        "seat_limit": license.seat_limit,
    }


@router.post("/licenses/{license_id}/activate")
async def activate_license(
    license_id: str,
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    license = db.query(SchoolLicenseDB).filter(SchoolLicenseDB.id == license_id).first()
    if not license:
        raise HTTPException(status_code=404, detail="License not found")

    license.status = "active"
    _audit_log(db, user, "license_activated", "license", license.id)
    db.commit()
    return {"message": "License activated", "status": "active"}


@router.post("/licenses/{license_id}/suspend")
async def suspend_license(
    license_id: str,
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    license = db.query(SchoolLicenseDB).filter(SchoolLicenseDB.id == license_id).first()
    if not license:
        raise HTTPException(status_code=404, detail="License not found")

    license.status = "suspended"
    _audit_log(db, user, "license_suspended", "license", license.id)
    db.commit()
    return {"message": "License suspended"}


@router.post("/licenses/{license_id}/renew")
async def renew_license(
    license_id: str,
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    license = db.query(SchoolLicenseDB).filter(SchoolLicenseDB.id == license_id).first()
    if not license:
        raise HTTPException(status_code=404, detail="License not found")

    plan = db.query(ProductPlanDB).filter(ProductPlanDB.id == license.product_plan_id).first()
    days = plan.duration_days if plan else 365

    new_start = license.expiry_date if license.expiry_date > date.today() else date.today()
    license.start_date = new_start
    license.expiry_date = new_start + timedelta(days=days)
    license.status = "active"

    _audit_log(db, user, "license_renewed", "license", license.id, {
        "new_expiry": license.expiry_date.isoformat(),
    })
    db.commit()
    return {
        "message": "License renewed",
        "start_date": license.start_date.isoformat(),
        "expiry_date": license.expiry_date.isoformat(),
    }


# ── Activation ────────────────────────────────────────────────────────────────

@router.get("/activations")
async def list_activation_codes(
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    codes = db.query(ActivationCodeDB).order_by(ActivationCodeDB.created_at.desc()).all()
    result = []
    for ac in codes:
        lic = db.query(SchoolLicenseDB).filter(SchoolLicenseDB.id == ac.license_id).first()
        school = db.query(SchoolDB).filter(SchoolDB.id == ac.used_by_school_id).first() if ac.used_by_school_id else None
        result.append({
            "id": ac.id,
            "code": ac.code,
            "license_id": ac.license_id,
            "license_code": lic.license_code if lic else "Unknown",
            "status": ac.status,
            "used_by_school": school.name if school else None,
            "used_at": ac.used_at.isoformat() if ac.used_at else None,
            "expires_at": ac.expires_at.isoformat() if ac.expires_at else None,
            "created_at": ac.created_at.isoformat() if ac.created_at else None,
        })
    return {"activations": result}


@router.post("/activations/{code_id}/revoke")
async def revoke_activation_code(
    code_id: str,
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    code = db.query(ActivationCodeDB).filter(ActivationCodeDB.id == code_id).first()
    if not code:
        raise HTTPException(status_code=404, detail="Activation code not found")
    if code.status == "used":
        raise HTTPException(status_code=400, detail="Cannot revoke a used code")

    code.status = "revoked"
    _audit_log(db, user, "activation_revoked", "activation", code.id)
    db.commit()
    return {"message": "Activation code revoked"}


# ── Desktop Activation Endpoint ──────────────────────────────────────────────

@router.post("/activate")
async def activate_desktop(
    req: ActivateLicenseRequest,
    db=Depends(get_db),
):
    """
    Desktop activation endpoint. Validates activation code and returns license info.
    This is a public endpoint (no auth required) - the code itself is the credential.
    """
    code = db.query(ActivationCodeDB).filter(ActivationCodeDB.code == req.activation_code).first()
    if not code:
        raise HTTPException(status_code=404, detail="Invalid activation code")

    if code.status == "revoked":
        raise HTTPException(status_code=403, detail="Activation code has been revoked")

    if code.status == "used":
        raise HTTPException(status_code=403, detail="Activation code already used")

    if code.expires_at and code.expires_at < datetime.utcnow():
        raise HTTPException(status_code=403, detail="Activation code has expired")

    license = db.query(SchoolLicenseDB).filter(SchoolLicenseDB.id == code.license_id).first()
    if not license:
        raise HTTPException(status_code=404, detail="License not found")

    if license.status not in ("active", "pending"):
        raise HTTPException(status_code=403, detail=f"License is {license.status}")

    school = db.query(SchoolDB).filter(SchoolDB.id == license.school_id).first()
    plan = db.query(ProductPlanDB).filter(ProductPlanDB.id == license.product_plan_id).first()

    # Mark code as used
    if code.status == "active":
        code.status = "used"
        code.used_by_school_id = license.school_id
        code.used_at = datetime.utcnow()

    # Activate license if pending
    if license.status == "pending":
        license.status = "active"

    # Record the activation so the Platform Admin license view can show that
    # (and when) the school claimed this license. First claim wins.
    if license.activated_at is None:
        license.activated_at = datetime.utcnow()
        license.activation_code_id = code.id
    license.updated_at = datetime.utcnow()

    # Cache license locally
    cache = LicenseCacheDB(
        id=generate_id(),
        school_id=license.school_id,
        license_code=license.license_code,
        plan_name=plan.name if plan else "",
        seat_limit=license.seat_limit,
        features=plan.features if plan else [],
        expiry_date=license.expiry_date,
    )
    db.add(cache)

    db.commit()

    return {
        "school": {
            "id": school.id,
            "name": school.name,
            "school_code": school.school_code,
        } if school else None,
        "license": {
            "code": license.license_code,
            "plan": plan.name if plan else "Unknown",
            "start_date": license.start_date.isoformat(),
            "expiry_date": license.expiry_date.isoformat(),
            "seat_limit": license.seat_limit,
            "features": plan.features if plan else [],
        },
        "message": "Activation successful",
    }


# ── Payments (Platform Admin) ────────────────────────────────────────────────

@router.get("/payments")
async def list_all_payments(
    status: Optional[str] = None,
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    query = db.query(PaymentDB)
    if status:
        query = query.filter(PaymentDB.status == status)
    payments = query.order_by(PaymentDB.submitted_at.desc()).limit(100).all()

    return {
        "payments": [{
            "id": p.id,
            "user_id": p.user_id,
            "payment_method": p.payment_method,
            "amount": p.amount,
            "currency": p.currency,
            "product_type": p.product_type,
            "product_name": p.product_name,
            "reference": p.reference,
            "payer_name": p.payer_name,
            "payer_phone": p.payer_phone,
            "status": p.status,
            "submitted_at": p.submitted_at.isoformat() if p.submitted_at else None,
        } for p in payments]
    }


@router.post("/payments/{payment_id}/verify")
async def verify_payment(
    payment_id: str,
    notes: str = "",
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    try:
        from ..payment_service import payment_service
        payment = payment_service.verify_payment(db, payment_id, user.id, notes)
        return {"message": "Payment verified"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/payments/{payment_id}/reject")
async def reject_payment(
    payment_id: str,
    reason: str = "",
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    try:
        from ..payment_service import payment_service
        payment = payment_service.reject_payment(db, payment_id, user.id, reason)
        return {"message": "Payment rejected"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Audit Log ─────────────────────────────────────────────────────────────────

@router.get("/audit")
async def list_audit_logs(
    limit: int = 100,
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    logs = db.query(PlatformAuditLogDB).order_by(
        PlatformAuditLogDB.timestamp.desc()
    ).limit(limit).all()

    return {
        "logs": [{
            "id": l.id,
            "actor_id": l.actor_id,
            "actor_role": l.actor_role,
            "action": l.action,
            "target_type": l.target_type,
            "target_id": l.target_id,
            "details": l.details,
            "timestamp": l.timestamp.isoformat() if l.timestamp else None,
        } for l in logs]
    }


# ── Activation Codes (per license) ───────────────────────────────────────────

def _serialize_activation(db, ac) -> dict:
    lic = db.query(SchoolLicenseDB).filter(SchoolLicenseDB.id == ac.license_id).first()
    return {
        "id": ac.id,
        "code": ac.code,
        "license_id": ac.license_id,
        "license_code": lic.license_code if lic else None,
        "status": ac.status,
        "used_by_school": ac.used_by_school_id,
        "used_at": ac.used_at.isoformat() if ac.used_at else None,
        "expires_at": ac.expires_at.isoformat() if ac.expires_at else None,
        "created_at": ac.created_at.isoformat() if ac.created_at else None,
    }


@router.get("/licenses/{license_id}/activation-codes")
async def list_license_activation_codes(
    license_id: str,
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    """List every activation code that belongs to a given license."""
    license = db.query(SchoolLicenseDB).filter(SchoolLicenseDB.id == license_id).first()
    if not license:
        raise HTTPException(status_code=404, detail="License not found")

    codes = db.query(ActivationCodeDB).filter(
        ActivationCodeDB.license_id == license_id
    ).order_by(ActivationCodeDB.created_at.desc()).all()

    return {"activation_codes": [_serialize_activation(db, c) for c in codes]}


@router.post("/licenses/{license_id}/activation-codes")
async def generate_license_activation_code(
    license_id: str,
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    """Generate a new activation code (TF-SCH-XXXX-XXXX-XXXX) for a license."""
    license = db.query(SchoolLicenseDB).filter(SchoolLicenseDB.id == license_id).first()
    if not license:
        raise HTTPException(status_code=404, detail="License not found")

    code = ActivationCodeDB(
        id=generate_id(),
        license_id=license.id,
        code=_generate_activation_code(),
        status="active",
        expires_at=datetime.utcnow() + timedelta(days=30),
    )
    db.add(code)
    _audit_log(db, user, "activation_code_generated", "license", license.id,
               {"code": code.code})
    db.commit()
    db.refresh(code)

    return _serialize_activation(db, code)


# ── Individual Activation Codes ──────────────────────────────────────────────

class CreateIndividualActivationRequest(BaseModel):
    teacher_email: str
    product_plan_id: str

@router.post("/activation-codes")
async def create_individual_activation_code(
    req: CreateIndividualActivationRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """Create an individual teacher activation code. Returns the code for the admin to share."""
    from ..database import IndividualActivationCodeDB

    plan = db.query(ProductPlanDB).filter(ProductPlanDB.id == req.product_plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Product plan not found")

    code_value = f"TF-IND-{''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(12))}"

    activation_code = IndividualActivationCodeDB(
        id=generate_id(),
        product_plan_id=req.product_plan_id,
        code=code_value,
        status="active",
        expires_at=datetime.utcnow() + timedelta(days=30),
    )
    db.add(activation_code)
    _audit_log(db, user, "individual_activation_code_created", "product_plan", req.product_plan_id,
               {"code": code_value, "teacher_email": req.teacher_email})
    db.commit()
    db.refresh(activation_code)

    return {
        "id": activation_code.id,
        "code": activation_code.code,
        "teacher_email": req.teacher_email,
        "product_plan_id": activation_code.product_plan_id,
        "status": activation_code.status,
        "expires_at": activation_code.expires_at.isoformat() if activation_code.expires_at else None,
        "created_at": activation_code.created_at.isoformat() if activation_code.created_at else None,
    }


@router.get("/activation-codes")
async def list_individual_activation_codes(
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """List all individual activation codes."""
    from ..database import IndividualActivationCodeDB

    codes = db.query(IndividualActivationCodeDB).order_by(IndividualActivationCodeDB.created_at.desc()).all()
    result = []
    for c in codes:
        result.append({
            "id": c.id,
            "code": c.code,
            "product_plan_id": c.product_plan_id,
            "status": c.status,
            "used_by_user_id": c.used_by_user_id,
            "used_at": c.used_at.isoformat() if c.used_at else None,
            "expires_at": c.expires_at.isoformat() if c.expires_at else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })
    return {"codes": result, "count": len(result)}


# ── Individual Teacher Management ────────────────────────────────────────────

@router.get("/individual-teachers")
async def list_individual_teachers(
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """List all individual teachers (no school or with subscription_type=individual)."""
    from ..database import EntitlementDB, SubscriptionDB

    teachers = db.query(User).filter(
        User.role == "teacher",
    ).all()

    result = []
    for t in teachers:
        ent = db.query(EntitlementDB).filter(
            EntitlementDB.user_id == t.id
        ).first()
        sub = db.query(SubscriptionDB).filter(
            SubscriptionDB.user_id == t.id,
            SubscriptionDB.status == "active",
        ).first()

        # Determine if this is an individual teacher
        is_individual = (
            getattr(t, "subscription_type", None) == "individual"
            or (t.school_id is None and ent is not None)
        )
        if not is_individual:
            continue

        effective_status = "active"
        if ent and ent.expires_at and ent.expires_at < datetime.utcnow():
            effective_status = "expired"

        result.append({
            "id": t.id,
            "email": t.email,
            "full_name": t.full_name,
            "is_active": t.is_active,
            "subscription_type": "individual",
            "plan_name": "Teacher Pro" if ent and ent.edition == "teacher" else "Free Teacher",
            "edition": ent.edition if ent else "free",
            "status": effective_status,
            "payment_status": sub.status if sub else "none",
            "ai_enabled": bool(ent.ai_enabled) if ent else False,
            "ai_credits": ent.ai_credits if ent else 5,
            "ai_credits_used": ent.ai_credits_used if ent else 0,
            "generation_limit": ent.generation_limit if ent else 3,
            "generations_used": ent.generations_used if ent else 0,
            "expires_at": ent.expires_at.isoformat() if ent and ent.expires_at else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        })

    return {"teachers": result, "count": len(result)}


@router.get("/individual-teachers/{teacher_id}")
async def get_individual_teacher(
    teacher_id: str,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """Get detailed view of an individual teacher."""
    from ..database import EntitlementDB, SubscriptionDB, PaymentDB

    teacher = db.query(User).filter(User.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    ent = db.query(EntitlementDB).filter(
        EntitlementDB.user_id == teacher_id
    ).first()
    sub = db.query(SubscriptionDB).filter(
        SubscriptionDB.user_id == teacher_id,
        SubscriptionDB.status == "active",
    ).first()
    payments = db.query(PaymentDB).filter(
        PaymentDB.user_id == teacher_id
    ).order_by(PaymentDB.created_at.desc()).all()

    return {
        "teacher": {
            "id": teacher.id,
            "email": teacher.email,
            "full_name": teacher.full_name,
            "is_active": teacher.is_active,
            "subscription_type": getattr(teacher, "subscription_type", None),
            "school_id": teacher.school_id,
            "created_at": teacher.created_at.isoformat() if teacher.created_at else None,
        },
        "entitlement": {
            "edition": ent.edition if ent else "free",
            "subscription_type": ent.subscription_type if ent else None,
            "generation_limit": ent.generation_limit if ent else 3,
            "generations_used": ent.generations_used if ent else 0,
            "batch_generation": bool(ent.batch_generation) if ent else False,
            "zip_export": bool(ent.zip_export) if ent else False,
            "pdf_export": bool(ent.pdf_export) if ent else True,
            "custom_template_limit": ent.custom_template_limit if ent else 1,
            "history_limit": ent.history_limit if ent else 10,
            "ai_enabled": bool(ent.ai_enabled) if ent else False,
            "ai_credits": ent.ai_credits if ent else 5,
            "ai_credits_used": ent.ai_credits_used if ent else 0,
            "expires_at": ent.expires_at.isoformat() if ent and ent.expires_at else None,
        } if ent else None,
        "subscription": {
            "status": sub.status if sub else "none",
            "plan_name": sub.plan_name if sub else "",
            "started_at": sub.started_at.isoformat() if sub and sub.started_at else None,
            "expires_at": sub.expires_at.isoformat() if sub and sub.expires_at else None,
        } if sub else None,
        "payments": [{
            "id": p.id,
            "amount": p.amount,
            "currency": p.currency,
            "status": p.status,
            "payment_method": p.payment_method,
            "product_name": p.product_name,
            "submitted_at": p.submitted_at.isoformat() if p.submitted_at else None,
            "reviewed_at": p.reviewed_at.isoformat() if p.reviewed_at else None,
        } for p in payments],
    }


class ActivateIndividualRequest(BaseModel):
    teacher_id: str
    product_plan_id: str
    duration_days: Optional[int] = None


@router.post("/individual-teachers/activate")
async def activate_individual_teacher(
    req: ActivateIndividualRequest,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """Manually activate Teacher Pro for an individual teacher.

    Platform Admin can directly activate without going through the payment flow.
    """
    from ..database import EntitlementDB, SubscriptionDB

    teacher = db.query(User).filter(User.id == req.teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    plan = db.query(ProductPlanDB).filter(ProductPlanDB.id == req.product_plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Product plan not found")

    now = datetime.utcnow()
    duration_days = req.duration_days or plan.duration_days or 30

    # Create or update subscription
    sub = db.query(SubscriptionDB).filter(
        SubscriptionDB.user_id == req.teacher_id,
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
            user_id=req.teacher_id,
            edition="teacher",
            plan_name=plan.name,
            status="active",
            started_at=now,
            expires_at=now + timedelta(days=duration_days),
            payment_provider="admin_activation",
            external_id="",
        )
        db.add(sub)

    # Create or update entitlement
    ent = db.query(EntitlementDB).filter(
        EntitlementDB.user_id == req.teacher_id,
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
            user_id=req.teacher_id,
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
    teacher.subscription_type = "individual"

    _audit_log(db, user, "individual_teacher_activated", "user", req.teacher_id,
               {"plan": plan.name, "duration_days": duration_days})
    db.commit()

    return {
        "teacher_id": req.teacher_id,
        "plan": plan.name,
        "expires_at": (now + timedelta(days=duration_days)).isoformat(),
        "status": "activated",
    }


# ── Demo Data Reset (development only) ───────────────────────────────────────

class ResetDemoRequest(BaseModel):
    confirm: str


@router.post("/reset-demo-data")
async def reset_demo_data(
    req: ResetDemoRequest,
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    """
    RESET DEMO COMMERCIAL DATA.

    Removes demo schools, licenses, activation codes, license caches, school
    memberships, payments and teacher/school-admin accounts. Platform
    configuration (platform admins, product plans, payment config, holidays)
    and platform audit logs are NEVER touched.

    Only available while DEBUG is enabled (development). Returns 403 in production.
    """
    settings = get_settings()
    if not settings.DEBUG:
        raise HTTPException(status_code=403, detail="Demo reset is disabled in production")

    if req.confirm != "RESET DEMO COMMERCIAL DATA":
        raise HTTPException(status_code=400, detail="Confirmation phrase did not match")

    removed = {}

    removed["activation_codes"] = db.query(ActivationCodeDB).delete(synchronize_session=False)
    removed["license_cache"] = db.query(LicenseCacheDB).delete(synchronize_session=False)
    removed["school_memberships"] = db.query(SchoolMembershipDB).delete(synchronize_session=False)
    removed["payments"] = db.query(PaymentDB).delete(synchronize_session=False)
    removed["school_licenses"] = db.query(SchoolLicenseDB).delete(synchronize_session=False)
    removed["schools"] = db.query(SchoolDB).delete(synchronize_session=False)

    # Remove demo staff accounts, never platform admins.
    demo_users = db.query(User).filter(
        User.role.in_(["teacher", "school_admin"])
    ).all()
    removed["users"] = len(demo_users)
    for u in demo_users:
        db.delete(u)

    _audit_log(db, user, "demo_data_reset", "platform", None, removed)
    db.commit()

    logger.info("demo_data_reset", actor=user.email, removed=removed)
    return {"message": "Demo commercial data reset", "removed": removed}


# ── Maintenance Mode Control ────────────────────────────────────────────────

class MaintenanceRequest(BaseModel):
    enabled: bool
    message: str = ""
    estimated_restore: str = ""


@router.post("/maintenance")
async def set_maintenance_mode(
    req: MaintenanceRequest,
    user: User = Depends(require_platform_admin),
):
    """Toggle maintenance mode. Changes take effect immediately."""
    from ..config import get_settings
    settings = get_settings()

    # Update the in-memory settings (this only affects the current process)
    settings.MAINTENANCE_MODE = req.enabled
    if req.message:
        settings.MAINTENANCE_MESSAGE = req.message
    if req.estimated_restore:
        settings.MAINTENANCE_ESTIMATED_RESTORE = req.estimated_restore

    _audit_log(db, user, "maintenance_mode_toggled" if not req.enabled else "maintenance_mode_enabled",
               "platform", None, {
                   "enabled": req.enabled,
                   "message": req.message,
                   "estimated_restore": req.estimated_restore,
               })
    db.commit()

    return {
        "maintenance": {
            "active": req.enabled,
            "message": settings.MAINTENANCE_MESSAGE,
            "estimated_restore": settings.MAINTENANCE_ESTIMATED_RESTORE,
        }
    }


@router.get("/maintenance")
async def get_maintenance_mode(
    user: User = Depends(require_platform_admin),
):
    """Get current maintenance mode status."""
    from ..config import get_settings
    settings = get_settings()

    return {
        "maintenance": {
            "active": settings.MAINTENANCE_MODE,
            "message": settings.MAINTENANCE_MESSAGE,
            "estimated_restore": settings.MAINTENANCE_ESTIMATED_RESTORE,
        }
    }
