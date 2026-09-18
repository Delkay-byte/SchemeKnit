"""
SchemeKnit Entitlement Enforcement

Server-side checks for feature access. Supports two commercial models:
  1. School subscription — controlled by SchoolLicenseDB
  2. Individual teacher subscription — controlled by EntitlementDB + SubscriptionDB

Precedence rule:
  - School entitlement controls school-provided capabilities.
  - Individual Pro applies to personal capabilities not already provided by the
    school. When a teacher has both, the MORE permissive value wins for each
    capability (school may grant batch generation while individual Pro grants
    higher AI credits, etc.).
"""

from datetime import date, datetime
from typing import Optional, Tuple, Dict, Any
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from .database import get_db, User, EntitlementDB, SubscriptionDB, SchoolLicenseDB, SchoolDB

#: User-facing, secret-free message for a denied AI request.
AI_ENTITLEMENT_REQUIRED = (
    "AI assistance requires an active school license or a paid AI entitlement."
)


# ── Core lookups ─────────────────────────────────────────────────────────────

def get_user_entitlement(db: Session, user_id: str) -> Optional[EntitlementDB]:
    """Return the user's EntitlementDB row, or None if expired."""
    ent = db.query(EntitlementDB).filter(
        EntitlementDB.user_id == user_id
    ).first()
    if ent and ent.expires_at and ent.expires_at < datetime.utcnow():
        ent = None
    return ent


def get_active_subscription(db: Session, user_id: str) -> Optional[SubscriptionDB]:
    """Return the user's active SubscriptionDB row, auto-expiring if past due."""
    sub = db.query(SubscriptionDB).filter(
        SubscriptionDB.user_id == user_id,
        SubscriptionDB.status == "active",
    ).first()
    if sub and sub.expires_at and sub.expires_at < datetime.utcnow():
        sub.status = "expired"
        db.commit()
        sub = None
    return sub


def get_school_license(db: Session, school_id: str) -> Optional[SchoolLicenseDB]:
    """Return the school's active, non-expired license, or None."""
    if not school_id:
        return None
    lic = db.query(SchoolLicenseDB).filter(
        SchoolLicenseDB.school_id == school_id,
        SchoolLicenseDB.status == "active",
    ).first()
    if lic and lic.expiry_date and lic.expiry_date < date.today():
        return None
    return lic


# ── Individual teacher entitlement resolution ────────────────────────────────

def resolve_entitlement(db: Session, user: User) -> Dict[str, Any]:
    """Resolve the user's effective entitlement from all applicable sources.

    Returns a dict describing the resolved entitlement:
      {
        "source": "individual" | "school" | "individual+school" | "free",
        "edition": "free" | "teacher" | "school",
        "subscription_type": "individual" | "school" | null,
        "plan_name": str,
        "generation_limit": int,       # 0 = unlimited
        "generations_used": int,
        "batch_generation": bool,
        "zip_export": bool,
        "pdf_export": bool,
        "custom_template_limit": int,
        "history_limit": int,
        "ai_enabled": bool,
        "ai_credits": int,             # 0 = unlimited
        "ai_credits_used": int,
        "expires_at": datetime | None,
        "is_active": bool,
        "school_name": str | None,     # set when access comes from a school
      }
    """
    ent = get_user_entitlement(db, user.id)
    school_license = get_school_license(db, getattr(user, "school_id", None))

    has_individual = ent is not None
    has_school = school_license is not None

    # Resolve the school name once for the SCHOOL ACCESS badge (§13).
    school_name = None
    if has_school:
        school_row = db.query(SchoolDB).filter(
            SchoolDB.id == school_license.school_id).first()
        school_name = school_row.name if school_row else None

    # Start with free-tier defaults
    result = {
        "source": "free",
        "edition": "free",
        "subscription_type": None,
        "plan_name": "Free Teacher",
        "generation_limit": 3,
        "generations_used": ent.generations_used if ent else 0,
        "batch_generation": False,
        "zip_export": False,
        "pdf_export": True,
        "custom_template_limit": 1,
        "history_limit": 10,
        "ai_enabled": False,
        "ai_credits": 5,
        "ai_credits_used": ent.ai_credits_used if ent else 0,
        "expires_at": None,
        "is_active": True,
        "school_name": None,
    }

    # Apply individual teacher entitlement
    if has_individual:
        result["source"] = "individual"
        result["edition"] = ent.edition or "teacher"
        result["subscription_type"] = "individual"
        result["plan_name"] = "Teacher Pro" if ent.edition == "teacher" else "Free Teacher"
        result["generation_limit"] = ent.generation_limit or 0
        result["generations_used"] = ent.generations_used or 0
        result["batch_generation"] = bool(ent.batch_generation)
        result["zip_export"] = bool(ent.zip_export)
        result["pdf_export"] = bool(ent.pdf_export)
        result["custom_template_limit"] = ent.custom_template_limit or 10
        result["history_limit"] = ent.history_limit or 100
        result["ai_enabled"] = bool(ent.ai_enabled)
        result["ai_credits"] = ent.ai_credits or 0
        result["ai_credits_used"] = ent.ai_credits_used or 0
        result["expires_at"] = ent.expires_at
        result["is_active"] = True

    # Apply school entitlement (may be more permissive for some capabilities)
    if has_school:
        if has_individual:
            result["source"] = "individual+school"
        else:
            result["source"] = "school"
            result["edition"] = "school"
            result["subscription_type"] = "school"
            result["plan_name"] = "School Subscription"
        result["school_name"] = school_name

        # School grants unlimited generation, batch, ZIP, PDF
        result["batch_generation"] = True
        result["zip_export"] = True
        result["pdf_export"] = True
        result["generation_limit"] = 0  # unlimited under school license
        result["custom_template_limit"] = max(result["custom_template_limit"], 10)
        result["history_limit"] = max(result["history_limit"], 100)

        # School AI entitlement is handled by ai_entitlement() separately

    return result


# ── Feature gates ────────────────────────────────────────────────────────────

def check_feature_access(user_id: str, feature: str, db: Session) -> bool:
    """Check if a user has access to a specific feature."""
    ent = get_user_entitlement(db, user_id)
    if not ent:
        return False
    if feature in (ent.features or []):
        return True
    if feature == "ai_basic" and ent.ai_enabled:
        return True
    if feature == "ai_enhanced" and ent.advanced_ai_enabled:
        return True
    if feature == "cloud_sync" and ent.cloud_sync:
        return True
    if feature == "template_import" and ent.template_import:
        return True
    if feature == "content_library" and ent.content_library:
        return True
    return False


def can_generate_batch(user: User, db: Session) -> Tuple[bool, str]:
    """Check if the user is entitled to batch/full-term generation.

    Returns (allowed, reason).
    """
    resolved = resolve_entitlement(db, user)
    if resolved["batch_generation"]:
        return True, "entitled"
    return False, "Full-term batch generation is available with Teacher Pro."


def can_export_zip(user: User, db: Session) -> Tuple[bool, str]:
    """Check if the user is entitled to ZIP export.

    Returns (allowed, reason).
    """
    resolved = resolve_entitlement(db, user)
    if resolved["zip_export"]:
        return True, "entitled"
    return False, "ZIP export is available with Teacher Pro."


def can_use_ai(user: User, db: Session) -> Tuple[bool, str]:
    """Check if the user is entitled to AI and has credits remaining.

    Returns (allowed, reason).
    """
    resolved = resolve_entitlement(db, user)
    if not resolved["ai_enabled"]:
        return False, "AI assistance is not available on your current plan."
    credits = resolved["ai_credits"]
    used = resolved["ai_credits_used"]
    if credits > 0 and used >= credits:
        return False, "Your AI allowance for this period has been reached."
    return True, "entitled"


def can_create_custom_template(user: User, db: Session) -> Tuple[bool, str]:
    """Check if the user can create another custom template.

    Returns (allowed, reason).
    """
    resolved = resolve_entitlement(db, user)
    limit = resolved["custom_template_limit"]
    if limit <= 0:
        return False, "Custom templates are not available on your current plan."
    from .database import CustomTemplateDB
    count = db.query(CustomTemplateDB).filter(
        CustomTemplateDB.owner_id == user.id,
        CustomTemplateDB.status != "archived",
    ).count()
    if count >= limit:
        return False, f"You have reached the limit of {limit} custom template(s). Upgrade to Teacher Pro for more."
    return True, "entitled"


def increment_generation_count(user: User, db: Session, count: int = 1) -> None:
    """Atomically increment the generation counter for the user's entitlement."""
    ent = get_user_entitlement(db, user.id)
    if ent:
        ent.generations_used = (ent.generations_used or 0) + count
        db.commit()


def increment_ai_credits(user: User, db: Session, count: int = 1) -> None:
    """Atomically increment the AI credit counter for the user's entitlement."""
    ent = get_user_entitlement(db, user.id)
    if ent:
        ent.ai_credits_used = (ent.ai_credits_used or 0) + count
        db.commit()


# ── AI commercial entitlement ────────────────────────────────────────────────

def ai_entitlement(user: User, db: Session) -> Tuple[bool, str]:
    """Server-derived AI commercial entitlement.

    Returns (entitled, reason). Reason is stable and safe to log, not to show:
      paid_entitlement   — an unexpired EntitlementDB row grants AI
      school_license     — the teacher's school holds an active, in-date license
      free_trial         — free teacher has limited AI trial credits
      no_entitlement     — no paid entitlement, no school, no trial
      no_active_license  — school membership but no active license row
      license_expired    — active license row whose expiry date has passed
      credits_exhausted  — AI credits used up
    """
    ent = get_user_entitlement(db, user.id)

    # Individual paid entitlement with AI enabled
    if ent and (ent.ai_enabled or ent.advanced_ai_enabled):
        # Check credits
        credits = ent.ai_credits or 0
        used = ent.ai_credits_used or 0
        if credits > 0 and used >= credits:
            return False, "credits_exhausted"
        return True, "paid_entitlement"

    # Free teacher AI trial
    if ent and ent.ai_enabled and not ent.ai_enabled:
        pass  # fall through to school check

    school_id = getattr(user, "school_id", None)
    if not school_id:
        # Free tier: check for trial AI credits
        if ent and ent.ai_enabled:
            credits = ent.ai_credits or 0
            used = ent.ai_credits_used or 0
            if credits > 0 and used >= credits:
                return False, "credits_exhausted"
            return True, "free_trial"
        return False, "no_entitlement"

    license = db.query(SchoolLicenseDB).filter(
        SchoolLicenseDB.school_id == school_id,
        SchoolLicenseDB.status == "active",
    ).first()
    if not license:
        return False, "no_active_license"
    if license.expiry_date and license.expiry_date < date.today():
        return False, "license_expired"
    return True, "school_license"


def require_ai_entitlement(user: User, db: Session) -> User:
    """Raise 403 unless the caller is commercially entitled to AI.

    Called before any provider is constructed, so an unlicensed teacher cannot
    reach a locally installed provider even when it is available.
    """
    entitled, _reason = ai_entitlement(user, db)
    if not entitled:
        raise HTTPException(status_code=403, detail=AI_ENTITLEMENT_REQUIRED)
    return user


def require_feature(feature: str):
    async def _check(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
        if not check_feature_access(user.id, feature, db):
            raise HTTPException(
                status_code=403,
                detail=f"This feature requires a paid subscription. Feature: {feature}"
            )
        return user
    return _check


from .auth import get_current_user
