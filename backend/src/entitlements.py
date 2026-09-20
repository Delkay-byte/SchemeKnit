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

from .database import (
    get_db, User, EntitlementDB, SubscriptionDB, SchoolLicenseDB, SchoolDB,
    AIUsageEventDB,
)

#: User-facing, secret-free message for a denied AI request.
AI_ENTITLEMENT_REQUIRED = (
    "AI assistance requires an active school license or a paid AI entitlement."
)

#: The Free Tier receives this many SUCCESSFUL AI generations for the LIFETIME
#: of the account. There is NO daily, weekly or monthly reset and no automatic
#: renewal — once used, the allowance stays at zero.
FREE_TIER_AI_GENERATIONS = 5

#: Visible plan label for the free individual-teacher tier (§14). The internal
#: edition identifier stays "free"; only this user-facing wording changes.
FREE_TIER_PLAN_NAME = "Free Tier"


def free_tier_ai_exhausted_message(limit: int = FREE_TIER_AI_GENERATIONS) -> str:
    """The exact user-facing message after the lifetime allowance is used up."""
    return (
        f"You've used all {limit} free AI generations included with the Free Tier. "
        "This is a one-time lifetime allowance — it does not reset. "
        "Upgrade to Teacher Pro for ongoing AI assistance."
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
        "plan_name": FREE_TIER_PLAN_NAME,
        #: Free Tier AI is a LIFETIME allowance (never reset).
        "ai_lifetime": True,
        "generation_limit": 3,
        "generations_used": ent.generations_used if ent else 0,
        "batch_generation": False,
        "zip_export": False,
        "pdf_export": True,
        "custom_template_limit": 1,
        "history_limit": 10,
        "ai_enabled": False,
        "ai_credits": FREE_TIER_AI_GENERATIONS,
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
        result["plan_name"] = "Teacher Pro" if ent.edition == "teacher" else FREE_TIER_PLAN_NAME
        #: Only the free edition is a lifetime allowance; paid plans keep their
        #: own (configurable) allowance and are never lifetime-capped here.
        result["ai_lifetime"] = (ent.edition or "free") == "free"
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
        # A school license provides unlimited AI — not the lifetime free tier.
        result["ai_lifetime"] = False
        result["ai_credits"] = 0
        result["ai_credits_used"] = 0
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

def _entitlement_ai_decision(db: Session, ent) -> Tuple[bool, str]:
    """AI decision for an individual EntitlementDB row.

    A finite ``ai_credits`` (the Free Tier lifetime allowance) is enforced as a
    LIFETIME cap. ``ai_credits == 0`` means unlimited and is never decremented.
    """
    if not ent or not (ent.ai_enabled or ent.advanced_ai_enabled):
        return False, "no_entitlement"
    credits = ent.ai_credits or 0
    used = ent.ai_credits_used or 0
    if credits > 0 and used >= credits:
        return False, "credits_exhausted"
    if (ent.edition or "free") == "free":
        return True, "free_trial"
    return True, "paid_entitlement"


def ai_entitlement(user: User, db: Session) -> Tuple[bool, str]:
    """Server-derived AI commercial entitlement.

    Returns (entitled, reason). Reason is stable and safe to log, not to show:
      school_license     — the teacher's school holds an active, in-date license
      paid_entitlement   — an unexpired paid EntitlementDB row grants AI
      free_trial         — Free Tier has lifetime AI generations remaining
      no_entitlement     — no paid entitlement, no school, no trial
      no_active_license  — school membership but no active license row
      license_expired    — active license row whose expiry date has passed
      credits_exhausted  — the lifetime allowance is used up

    Precedence: an active school license grants unlimited AI and is NEVER
    lifetime-limited. Otherwise the individual entitlement decides.
    """
    school_id = getattr(user, "school_id", None)
    if school_id:
        license = db.query(SchoolLicenseDB).filter(
            SchoolLicenseDB.school_id == school_id,
            SchoolLicenseDB.status == "active",
        ).first()
        if license:
            if license.expiry_date and license.expiry_date < date.today():
                return False, "license_expired"
            return True, "school_license"
        # School member without an active license: an individual entitlement
        # may still apply (independent Pro teacher who joined a school).
        ent = get_user_entitlement(db, user.id)
        if ent and (ent.ai_enabled or ent.advanced_ai_enabled):
            return _entitlement_ai_decision(db, ent)
        return False, "no_active_license"

    ent = get_user_entitlement(db, user.id)
    entitled, reason = _entitlement_ai_decision(db, ent)
    return entitled, reason


def require_ai_entitlement(user: User, db: Session) -> User:
    """Raise 403 unless the caller is commercially entitled to AI.

    Called before any provider is constructed, so an unlicensed teacher cannot
    reach a locally installed provider (e.g. Ollama) even when it is available.
    Ollama is a model runtime, never permission to bypass the commercial limit.
    """
    entitled, reason = ai_entitlement(user, db)
    if not entitled:
        if reason == "credits_exhausted":
            ent = get_user_entitlement(db, user.id)
            limit = (ent.ai_credits if ent and ent.ai_credits else FREE_TIER_AI_GENERATIONS)
            raise HTTPException(
                status_code=403,
                detail=free_tier_ai_exhausted_message(limit),
            )
        raise HTTPException(status_code=403, detail=AI_ENTITLEMENT_REQUIRED)
    return user


def consume_ai_generation(user: User, db: Session, request_id: Optional[str] = None) -> int:
    """Record ONE successfully completed AI generation against the user.

    Only a FINITE allowance is consumed (the Free Tier lifetime allowance).
    Unlimited entitlements — a school license or a paid plan with
    ``ai_credits == 0`` — are never decremented and return -1.

    Returns the remaining count (or -1 when unlimited). Idempotent for a given
    ``request_id`` so a duplicate frontend submission cannot double-consume the
    allowance for the same successful generation request.
    """
    # School license → unlimited; nothing to consume.
    school_id = getattr(user, "school_id", None)
    if school_id:
        license = db.query(SchoolLicenseDB).filter(
            SchoolLicenseDB.school_id == school_id,
            SchoolLicenseDB.status == "active",
        ).first()
        if license and not (license.expiry_date and license.expiry_date < date.today()):
            return -1

    ent = db.query(EntitlementDB).filter(EntitlementDB.user_id == user.id).first()
    if not ent:
        return -1
    credits = ent.ai_credits or 0
    if credits <= 0:
        return -1  # unlimited

    used = ent.ai_credits_used or 0

    # Idempotency: the same successful request must never consume twice.
    if request_id:
        already = db.query(AIUsageEventDB).filter(
            AIUsageEventDB.user_id == user.id,
            AIUsageEventDB.request_id == request_id,
        ).first()
        if already:
            return max(credits - used, 0)

    if used >= credits:
        # Defensive: never exceed the lifetime cap.
        return 0

    ent.ai_credits_used = used + 1
    if request_id:
        db.add(AIUsageEventDB(
            user_id=user.id,
            request_id=request_id,
            consumed=True,
        ))
    db.commit()
    return max(credits - (used + 1), 0)


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
