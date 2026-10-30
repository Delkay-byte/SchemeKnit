"""Referral attribution, rewards and reversal.

Rewards are only issued after a referred account's first *verified* paid
package purchase. Registration alone, an abandoned checkout and a pending
transfer earn nothing. Both rewards use unique credit-ledger grant keys, so a
duplicate Paystack webhook can never pay twice. If the qualifying payment is
later reversed, unused reward credits are removed (never below zero) and the
referral is marked reversed with an auditable reason.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import credits
from .database import (
    CreditBalanceDB, ReferralCodeDB, ReferralDB, ReferralSettingDB,
    ReferralVisitDB, SubscriptionTransactionDB, User, generate_id,
)

DEFAULT_REFERRER_REWARD = 5
DEFAULT_REFERRED_REWARD = 3
DEFAULT_TERM_LIMIT = 5

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _now() -> datetime:
    return datetime.utcnow()


def settings(db: Session) -> ReferralSettingDB:
    row = db.query(ReferralSettingDB).first()
    if row is None:
        row = ReferralSettingDB(
            id=generate_id(),
            reward_referrer=DEFAULT_REFERRER_REWARD,
            reward_referred=DEFAULT_REFERRED_REWARD,
            term_limit=DEFAULT_TERM_LIMIT,
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            row = db.query(ReferralSettingDB).first()
    return row


def _term_start(now: Optional[datetime] = None) -> datetime:
    """Start of the current Ghana academic term (Sep/Apr/Aug boundaries).

    An operator may pin the start explicitly with REFERRAL_TERM_START.
    """
    override = (os.environ.get("REFERRAL_TERM_START") or "").strip()
    if override:
        try:
            return datetime.fromisoformat(override)
        except ValueError:
            pass
    now = now or _now()
    if now.month >= 9:
        return datetime(now.year, 9, 1)
    if now.month >= 5:
        return datetime(now.year, 5, 1)
    return datetime(now.year, 1, 1)


def ensure_code(db: Session, user: User) -> ReferralCodeDB:
    row = db.query(ReferralCodeDB).filter(
        ReferralCodeDB.user_id == user.id).first()
    if row is not None:
        return row
    for _ in range(8):
        code = "TF" + "".join(secrets.choice(_ALPHABET) for _ in range(7))
        if db.query(ReferralCodeDB.id).filter(
                ReferralCodeDB.code == code).first():
            continue
        row = ReferralCodeDB(id=generate_id(), user_id=user.id, code=code)
        db.add(row)
        try:
            db.commit()
            return row
        except IntegrityError:
            db.rollback()
            row = db.query(ReferralCodeDB).filter(
                ReferralCodeDB.user_id == user.id).first()
            if row is not None:
                return row
    raise RuntimeError("Could not allocate a unique referral code.")


def attribute(db: Session, user: User, code: str) -> Optional[ReferralDB]:
    """Attribute a newly registered account to one referrer, once."""
    code = (code or "").strip().upper()
    if not code:
        return None
    existing = db.query(ReferralDB).filter(
        ReferralDB.referred_id == user.id).first()
    if existing is not None:
        return existing
    owner = db.query(ReferralCodeDB).filter(
        ReferralCodeDB.code == code,
        ReferralCodeDB.active.is_(True),
    ).first()
    if owner is None:
        return None
    if owner.user_id == user.id:
        return None  # self-referral
    referrer = db.query(User).filter(User.id == owner.user_id).first()
    if referrer is None:
        return None
    if (referrer.email or "").strip().lower() == (user.email or "").strip().lower():
        return None  # same person, different row
    row = ReferralDB(
        id=generate_id(), referrer_id=owner.user_id, referred_id=user.id,
        code=code, attributed_at=_now(), status="registered",
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return db.query(ReferralDB).filter(
            ReferralDB.referred_id == user.id).first()
    return row


def track_visit(db: Session, code: str) -> bool:
    code = (code or "").strip().upper()
    if not code:
        return False
    if db.query(ReferralCodeDB.id).filter(
            ReferralCodeDB.code == code,
            ReferralCodeDB.active.is_(True)).first() is None:
        return False
    db.add(ReferralVisitDB(id=generate_id(), code=code))
    db.commit()
    return True


def _first_successful_purchase(db: Session, tx: SubscriptionTransactionDB) -> bool:
    earlier = (
        db.query(SubscriptionTransactionDB.id)
        .filter(
            SubscriptionTransactionDB.user_id == tx.user_id,
            SubscriptionTransactionDB.status == "success",
            SubscriptionTransactionDB.reference != tx.reference,
        )
        .first()
    )
    return earlier is None


def qualify(db: Session, user: User, tx: SubscriptionTransactionDB) -> Optional[ReferralDB]:
    """Issue 5/3 rewards once, after a verified first package purchase."""
    referral = db.query(ReferralDB).filter(
        ReferralDB.referred_id == user.id).first()
    if referral is None or referral.status in ("rewarded", "reversed"):
        return referral
    if tx.status != "success" or tx.user_id != user.id:
        return referral
    if not _first_successful_purchase(db, tx):
        referral.status = "ineligible"
        db.commit()
        return referral

    cfg = settings(db)
    term_rows = (
        db.query(ReferralDB)
        .filter(
            ReferralDB.referrer_id == referral.referrer_id,
            ReferralDB.status == "rewarded",
            ReferralDB.rewarded_at >= _term_start(),
        )
        .count()
    )
    if term_rows >= int(cfg.term_limit or DEFAULT_TERM_LIMIT):
        referral.status = "limit_reached"
        db.commit()
        return referral

    referrer_reward = int(cfg.reward_referrer or DEFAULT_REFERRER_REWARD)
    referred_reward = int(cfg.reward_referred or DEFAULT_REFERRED_REWARD)
    credits.grant(
        db, referral.referrer_id, source=credits.SOURCE_REFERRAL,
        credits=referrer_reward, grant_key=f"referral:referrer:{referral.id}",
        label="Referral bonus", reference=tx.reference,
        commit=False,
    )
    credits.grant(
        db, user.id, source=credits.SOURCE_REFERRAL,
        credits=referred_reward, grant_key=f"referral:referred:{referral.id}",
        label="Referral welcome bonus", reference=tx.reference,
        commit=False,
    )
    referral.status = "rewarded"
    referral.qualifying_reference = tx.reference
    referral.referrer_credits = referrer_reward
    referral.referred_credits = referred_reward
    referral.rewarded_at = _now()
    db.commit()
    return referral


def reverse_for_transaction(
    db: Session, tx: SubscriptionTransactionDB, reason: str = "payment reversed",
) -> bool:
    """Reverse unused package and referral credits for a refunded payment."""
    changed = False
    pkg = db.query(CreditBalanceDB).filter(
        CreditBalanceDB.grant_key == f"package:{tx.reference}").first()
    if pkg is not None:
        credits.reverse_balance(db, pkg, reason, commit=False)
        changed = True
    referral = db.query(ReferralDB).filter(
        ReferralDB.qualifying_reference == tx.reference,
        ReferralDB.status == "rewarded",
    ).first()
    if referral is not None:
        for key in (
            f"referral:referrer:{referral.id}",
            f"referral:referred:{referral.id}",
        ):
            bal = db.query(CreditBalanceDB).filter(
                CreditBalanceDB.grant_key == key).first()
            if bal is not None:
                credits.reverse_balance(db, bal, reason, commit=False)
        referral.status = "reversed"
        referral.reversed_at = _now()
        referral.reversal_reason = reason
        changed = True
    if changed:
        db.commit()
    return changed


def stats(db: Session, user: User) -> Dict[str, Any]:
    cfg = settings(db)
    code = ensure_code(db, user)
    visits = db.query(ReferralVisitDB).filter(
        ReferralVisitDB.code == code.code).count()
    rows = (
        db.query(ReferralDB)
        .filter(ReferralDB.referrer_id == user.id)
        .order_by(ReferralDB.attributed_at.desc())
        .all()
    )
    rewarded = [r for r in rows if r.status == "rewarded"]
    earned = sum(int(r.referrer_credits or 0) for r in rewarded)
    balance = credits.status(db, user.id)["referral"]
    history = []
    for r in rows:
        referred = db.query(User).filter(User.id == r.referred_id).first()
        history.append({
            "id": r.id,
            "referred": (referred.full_name if referred else "Teacher"),
            "status": r.status,
            "attributed_at": r.attributed_at.isoformat() if r.attributed_at else None,
            "rewarded_at": r.rewarded_at.isoformat() if r.rewarded_at else None,
            "credits": int(r.referrer_credits or 0),
            "qualifying_reference": r.qualifying_reference or "",
            "reversal_reason": r.reversal_reason or "",
        })
    term_used = sum(
        1 for r in rewarded
        if r.rewarded_at and r.rewarded_at >= _term_start()
    )
    return {
        "code": code.code,
        "link_path": f"/signup?ref={code.code}",
        "invited": visits,
        "registered": len(rows),
        "qualifying": len(rewarded),
        "credits_earned": earned,
        "credits_balance": balance,
        "term_limit": int(cfg.term_limit or DEFAULT_TERM_LIMIT),
        "term_rewarded": term_used,
        "reward": {
            "referrer": int(cfg.reward_referrer or DEFAULT_REFERRER_REWARD),
            "referred": int(cfg.reward_referred or DEFAULT_REFERRED_REWARD),
        },
        "history": history,
        "language": (
            f"Invite a teacher. When they make their first successful purchase, "
            f"you receive {int(cfg.reward_referrer or DEFAULT_REFERRER_REWARD)} "
            f"bonus credits and they receive "
            f"{int(cfg.reward_referred or DEFAULT_REFERRED_REWARD)}."
        ),
    }
