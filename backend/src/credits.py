"""Credit accounting for TeachFlow's approved commercial model.

A credit is one successfully generated, independently teachable, indicator-level
lesson plan. Free credits are a calendar-month allowance (Africa/Accra) held in
the existing ``usage_periods`` ledger and never roll over. Purchased, package
and referral credits live in ``credit_balances`` with their own expiry and an
append-only ``credit_ledger``.

Spending order (documented and deterministic):

1. Free monthly credits — they expire at the end of the month.
2. Package credits — the balance expiring soonest is used first.
3. Referral bonus credits — non-expiring, kept distinct from purchased credits.
4. Flexible purchased credits — non-expiring and never consumed by a package
   expiry.

Reservations are idempotent by key and refund exactly the source that paid when
a generation fails or produces fewer plans than requested. The browser never
decides affordability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .catalogue import FREE, PACKAGE_KIND_FLEXIBLE, PACKAGE_KIND_TIMED
from .database import (
    CreditBalanceDB, CreditLedgerDB, CreditReservationDB, SubscriptionPlanDB,
    generate_id,
)
from .usage_quota import (
    PERIOD_TYPE_CALENDAR_MONTH,
    charged_indicator_codes,
    current_period_key,
    get_units_used,
    release_lesson_units,
    reserve_lesson_units,
)

SOURCE_PURCHASED = "purchased"
SOURCE_PACKAGE = "package"
SOURCE_REFERRAL = "referral"

#: Free allowance from the approved catalogue.
FREE_CREDITS = FREE.credits


def free_limit() -> int:
    """Current free monthly allowance (catalogue default, test-overridable)."""
    try:
        from .entitlements import FREE_TIER_LESSON_PLANS_PER_MONTH
        return int(FREE_TIER_LESSON_PLANS_PER_MONTH)
    except Exception:
        return FREE_CREDITS


def _now() -> datetime:
    return datetime.utcnow()


def _active_balances(db: Session, user_id: str, now: Optional[datetime] = None):
    now = now or _now()
    rows = (
        db.query(CreditBalanceDB)
        .filter(
            CreditBalanceDB.user_id == user_id,
            CreditBalanceDB.credits_remaining > 0,
            CreditBalanceDB.status == "active",
        )
        .all()
    )
    live = [b for b in rows if b.expires_at is None or b.expires_at > now]
    # Expiring package credits first (soonest expiry), then referral, then
    # non-expiring purchased credits. Stable slug/id tie-break for determinism.
    source_rank = {SOURCE_PACKAGE: 0, SOURCE_REFERRAL: 1, SOURCE_PURCHASED: 2}
    live.sort(key=lambda b: (
        source_rank.get(b.source, 9),
        b.expires_at or datetime.max,
        b.granted_at or datetime.min,
        b.id,
    ))
    return live


def status(db: Session, user_id: str) -> Dict[str, Any]:
    """Server-derived credit snapshot used by the API and generation route."""
    period_key = current_period_key()
    free_used = get_units_used(db, user_id, period_key)
    limit = free_limit()
    free_remaining = max(limit - free_used, 0)
    now = _now()
    balances = _active_balances(db, user_id, now)

    by_source = {SOURCE_PURCHASED: 0, SOURCE_PACKAGE: 0, SOURCE_REFERRAL: 0}
    packages: List[dict] = []
    for b in balances:
        by_source[b.source] = by_source.get(b.source, 0) + int(b.credits_remaining)
        if b.source == SOURCE_PACKAGE:
            packages.append({
                "slug": b.package_slug,
                "label": b.label,
                "remaining": int(b.credits_remaining),
                "expires_at": b.expires_at.isoformat() if b.expires_at else None,
                "granted": int(b.credits_granted),
            })

    # Include recently expired package balances in the display so the teacher
    # can see what ended (but they grant nothing).
    expired = (
        db.query(CreditBalanceDB)
        .filter(
            CreditBalanceDB.user_id == user_id,
            CreditBalanceDB.source == SOURCE_PACKAGE,
            CreditBalanceDB.credits_remaining > 0,
            CreditBalanceDB.expires_at.isnot(None),
            CreditBalanceDB.expires_at <= now,
        )
        .order_by(CreditBalanceDB.expires_at.desc())
        .limit(10)
        .all()
    )
    expired_packages = [{
        "slug": b.package_slug,
        "label": b.label,
        "unused": int(b.credits_remaining),
        "expired_at": b.expires_at.isoformat() if b.expires_at else None,
    } for b in expired]

    total_paid = sum(by_source.values())
    return {
        "free": {
            "limit": limit,
            "used": free_used,
            "remaining": free_remaining,
            "period_key": period_key,
            "period_type": PERIOD_TYPE_CALENDAR_MONTH,
            "resets": "1st of each month (Africa/Accra)",
            "rollover": False,
        },
        "purchased": by_source[SOURCE_PURCHASED],
        "package": by_source[SOURCE_PACKAGE],
        "referral": by_source[SOURCE_REFERRAL],
        "packages": packages,
        "expired_packages": expired_packages,
        "total": free_remaining + total_paid,
        "spending_order": ["free", "package", "referral", "purchased"],
        "unit": "indicator_level_lesson_plan",
    }


def available(db: Session, user_id: str) -> int:
    return int(status(db, user_id)["total"])


def _ledger(
    db: Session, user_id: str, balance_id: Optional[str], entry_type: str,
    source: str, credits: int, reason: str, reference: str, key: str,
) -> None:
    """Append one movement; duplicate keys are ignored (idempotent)."""
    exists = db.query(CreditLedgerDB.id).filter(
        CreditLedgerDB.idempotency_key == key).first()
    if exists:
        return
    db.add(CreditLedgerDB(
        id=generate_id(), user_id=user_id, balance_id=balance_id,
        entry_type=entry_type, source=source, credits=credits,
        reason=reason, reference=reference, idempotency_key=key,
    ))


def grant(
    db: Session,
    user_id: str,
    *,
    source: str,
    credits: int,
    grant_key: str,
    package_slug: str = "",
    label: str = "",
    expires_at: Optional[datetime] = None,
    reference: str = "",
    commit: bool = True,
) -> Optional[CreditBalanceDB]:
    """Grant a credit bucket exactly once for ``grant_key``."""
    if credits <= 0:
        return None
    existing = db.query(CreditBalanceDB).filter(
        CreditBalanceDB.grant_key == grant_key).first()
    if existing:
        return existing
    balance = CreditBalanceDB(
        id=generate_id(), user_id=user_id, source=source,
        package_slug=package_slug, label=label,
        credits_granted=int(credits), credits_remaining=int(credits),
        granted_at=_now(), expires_at=expires_at, grant_key=grant_key,
        reference=reference, status="active",
    )
    db.add(balance)
    _ledger(
        db, user_id, balance.id, "grant", source, int(credits),
        label or source, reference, f"grant:{grant_key}",
    )
    try:
        if commit:
            db.commit()
        else:
            db.flush()
    except IntegrityError:
        db.rollback()
        return db.query(CreditBalanceDB).filter(
            CreditBalanceDB.grant_key == grant_key).first()
    return balance


def grant_package(
    db: Session,
    user_id: str,
    plan: SubscriptionPlanDB,
    reference: str,
    activated_at: Optional[datetime] = None,
    commit: bool = True,
) -> Optional[CreditBalanceDB]:
    """Grant the plan's credits once, starting the validity at activation."""
    entitlement = dict(plan.entitlements or {})
    credits = int(
        getattr(plan, "credit_allowance", 0)
        or entitlement.get("credit_allowance", 0)
        or 0
    )
    if credits <= 0:
        return None
    kind = getattr(plan, "package_kind", "") or entitlement.get("package_kind", "")
    days = getattr(plan, "credit_validity_days", None)
    if days is None:
        days = entitlement.get("credit_validity_days")
    if days is None and kind == PACKAGE_KIND_TIMED:
        days = getattr(plan, "duration_days", 0) or None
    start = activated_at or _now()
    expires_at = None
    if kind == PACKAGE_KIND_TIMED and days:
        expires_at = start + timedelta(days=int(days))
    source = SOURCE_PURCHASED if kind == PACKAGE_KIND_FLEXIBLE else SOURCE_PACKAGE
    return grant(
        db, user_id,
        source=source,
        credits=credits,
        grant_key=f"package:{reference}",
        package_slug=plan.slug,
        label=plan.name,
        expires_at=expires_at,
        reference=reference,
        commit=commit,
    )


@dataclass
class Reservation:
    allowed: bool
    available: int
    units_requested: int = 0
    free_units: int = 0
    paid_units: int = 0
    charged: int = 0
    reservation_id: str = ""
    allocations: List[dict] = field(default_factory=list)
    reason: str = ""
    already: bool = False

    @property
    def free_keys(self) -> List[str]:
        return [a["unit_key"] for a in self.allocations if a["source"] == "free"]

    @property
    def consumed(self) -> int:
        return self.charged

    @property
    def reserved_keys(self) -> List[str]:
        return [a["unit_key"] for a in self.allocations if a.get("unit_key")]

    @property
    def period_key(self) -> str:
        return current_period_key()

    def as_quota(self) -> dict:
        return {
            "enforced": True,
            "limit": self.available + self.charged,
            "used": 0,
            "remaining": self.available,
            "unlimited": False,
            "period_type": PERIOD_TYPE_CALENDAR_MONTH,
            "period_key": self.period_key,
        }


def _reserve_paid(db: Session, user_id: str, need: int, idempotency_key: str,
                  codes: List[str], nonce: str = "") -> tuple[List[dict], int]:
    """Atomically take paid credits, returning allocations and units taken."""
    allocations: List[dict] = []
    taken = 0
    idx = 0
    nonce = nonce or generate_id()[:8]
    for balance in _active_balances(db, user_id):
        if taken >= need:
            break
        take = min(int(balance.credits_remaining), need - taken)
        if take <= 0:
            continue
        upd = db.execute(
            text(
                "UPDATE credit_balances SET credits_remaining = credits_remaining - :n, "
                "updated_at = :now WHERE id = :id AND credits_remaining >= :n"
            ),
            {"n": take, "now": _now(), "id": balance.id},
        )
        if (upd.rowcount or 0) != 1:
            continue  # lost a concurrent race; try the next bucket
        for _ in range(take):
            code = codes[idx] if idx < len(codes) else f"unit-{idx}"
            allocations.append({
                "source": balance.source,
                "balance_id": balance.id,
                "code": code,
                "credits": 1,
            })
            idx += 1
        _ledger(
            db, user_id, balance.id, "consume", balance.source, -take,
            f"generation {idempotency_key}", idempotency_key,
            f"consume:{idempotency_key}:{balance.id}:{nonce}",
        )
        taken += take
    db.flush()
    return allocations, taken


def _refund_allocations(db: Session, user_id: str, reservation_id: str,
                        allocations: Iterable[dict]) -> int:
    refunded = 0
    by_balance: Dict[str, int] = {}
    for a in allocations:
        if a.get("source") == "free":
            continue
        by_balance[a["balance_id"]] = by_balance.get(a["balance_id"], 0) + int(a.get("credits", 1))
    nonce = generate_id()[:8]
    for balance_id, amount in by_balance.items():
        db.execute(
            text(
                "UPDATE credit_balances SET credits_remaining = credits_remaining + :n, "
                "status = 'active', updated_at = :now WHERE id = :id"
            ),
            {"n": amount, "now": _now(), "id": balance_id},
        )
        bal = db.query(CreditBalanceDB).filter(CreditBalanceDB.id == balance_id).first()
        _ledger(
            db, user_id, balance_id, "release", bal.source if bal else "",
            amount, "generation released unused credits", reservation_id,
            f"release:{reservation_id}:{balance_id}:{amount}:{nonce}",
        )
        refunded += amount
    return refunded


def reserve(
    db: Session,
    user_id: str,
    units: int,
    idempotency_key: str,
    scheme_id: str = "",
    codes: Optional[List[str]] = None,
    period_key: Optional[str] = None,
) -> Reservation:
    """Reserve ``units`` credits for one generation request.

    Free monthly credits are claimed first, then paid buckets in the documented
    order. A duplicate ``idempotency_key`` returns the existing hold and charges
    nothing more.
    """
    units = max(int(units or 0), 0)
    codes = list(codes or [])
    while len(codes) < units:
        codes.append(f"unit-{len(codes)}")

    existing = db.query(CreditReservationDB).filter(
        CreditReservationDB.idempotency_key == idempotency_key).first()
    if existing is not None and existing.status == "released":
        # A failed run refunded its hold; the same request id may try again.
        db.delete(existing)
        db.commit()
        existing = None
    if existing is not None:
        if existing.status == "released":
            return Reservation(
                allowed=False, available=_available(db, user_id),
                units_requested=existing.units, reason="reservation_released",
                reservation_id=existing.id, already=True,
            )
        return Reservation(
            allowed=True, available=_available(db, user_id),
            units_requested=existing.units,
            free_units=sum(1 for a in (existing.allocations or [])
                           if a.get("source") == "free"),
            paid_units=sum(1 for a in (existing.allocations or [])
                           if a.get("source") != "free"),
            charged=0, reservation_id=existing.id,
            allocations=list(existing.allocations or []), already=True,
        )

    period_key = period_key or current_period_key()
    used = get_units_used(db, user_id, period_key)
    free_remaining = max(free_limit() - used, 0)
    if units == 0:
        row = CreditReservationDB(
            id=generate_id(), user_id=user_id,
            idempotency_key=idempotency_key, scheme_id=scheme_id,
            units=0, status="committed", allocations=[],
        )
        db.add(row)
        db.commit()
        return Reservation(allowed=True, available=_available(db, user_id),
                           reservation_id=row.id)

    # Free credits are claimed for codes not already counted this month.
    already_free = charged_indicator_codes(db, user_id, scheme_id, period_key)
    unpaid_codes = [c for c in codes if c not in already_free]
    free_take = min(len(unpaid_codes), free_remaining, units)
    free_codes = unpaid_codes[:free_take]
    free_res = None
    if free_take > 0:
        free_res = reserve_lesson_units(
            db, user_id, scheme_id, free_codes, free_limit(), period_key)
        if not free_res.allowed:
            free_take = 0
            free_codes = []
        else:
            free_take = len(free_res.reserved_keys)

    paid_need = units - free_take
    allocations: List[dict] = [
        {"source": "free", "balance_id": None, "code": c,
         "unit_key": f"{scheme_id}:{c}", "credits": 1}
        for c in free_codes[:free_take]
    ]
    paid_codes = codes[free_take:free_take + paid_need]
    paid_allocs, paid_taken = _reserve_paid(
        db, user_id, paid_need, idempotency_key, paid_codes)
    allocations.extend(paid_allocs)

    if free_take + paid_taken < units:
        # Not enough: undo every movement from this attempt.
        if paid_allocs:
            _refund_allocations(db, user_id, f"abort:{idempotency_key}", paid_allocs)
        if free_codes[:free_take]:
            release_lesson_units(
                db, user_id,
                [f"{scheme_id}:{c}" for c in free_codes[:free_take]], period_key)
        db.commit()
        return Reservation(
            allowed=False, available=_available(db, user_id),
            units_requested=units, reason="insufficient_credits",
        )

    row = CreditReservationDB(
        id=generate_id(), user_id=user_id, idempotency_key=idempotency_key,
        scheme_id=scheme_id, units=units, status="held",
        allocations=allocations,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(CreditReservationDB).filter(
            CreditReservationDB.idempotency_key == idempotency_key).first()
        if existing:
            return Reservation(
                allowed=True, available=_available(db, user_id),
                units_requested=existing.units, charged=0,
                reservation_id=existing.id,
                allocations=list(existing.allocations or []), already=True,
            )
        raise
    return Reservation(
        allowed=True, available=_available(db, user_id),
        units_requested=units, free_units=free_take, paid_units=paid_taken,
        charged=units, reservation_id=row.id, allocations=allocations,
    )


def _available(db: Session, user_id: str) -> int:
    return int(status(db, user_id)["total"])


def _reservation(db: Session, reservation) -> Optional[CreditReservationDB]:
    if isinstance(reservation, CreditReservationDB):
        return reservation
    row_id = (reservation if isinstance(reservation, str)
              else getattr(reservation, "reservation_id", "")
              or getattr(reservation, "id", ""))
    if not row_id:
        return None
    return db.query(CreditReservationDB).filter(
        CreditReservationDB.id == row_id).first()


def release(db: Session, reservation, codes: Optional[Iterable[str]] = None,
            commit: bool = True) -> int:
    """Refund held credits for the named codes (or everything held)."""
    row = _reservation(db, reservation)
    if row is None or row.status != "held":
        return 0
    wanted = set(codes or [])
    allocations = list(row.allocations or [])
    if wanted:
        target = [a for a in allocations if a.get("code") in wanted]
    else:
        target = list(allocations)
    if not target:
        if commit:
            db.commit()
        return 0

    free_keys = [a["unit_key"] for a in target if a.get("source") == "free"]
    if free_keys:
        release_lesson_units(db, row.user_id, free_keys, commit=False)
    _refund_allocations(db, row.user_id, row.id, target)

    remaining = [a for a in allocations if a not in target]
    row.allocations = remaining
    if not remaining:
        row.status = "released"
    if commit:
        db.commit()
    else:
        db.flush()
    return len(target)


def commit(db: Session, reservation, produced_codes: Iterable[str],
           commit: bool = True) -> int:
    """Keep credits for produced plans and release the rest atomically."""
    produced = set(produced_codes or [])
    row = _reservation(db, reservation)
    if row is None or row.status != "held":
        return 0
    unused = [a.get("code") for a in (row.allocations or [])
              if a.get("code") not in produced]
    released = 0
    if unused:
        released = release(db, row, unused, commit=False)
    row = _reservation(db, row.id)
    if row is not None:
        row.status = "committed" if row.allocations else "released"
    if commit:
        db.commit()
    else:
        db.flush()
    return released


def reverse_balance(db: Session, balance: CreditBalanceDB, reason: str,
                    commit: bool = True) -> int:
    """Reverse up to the unused remainder of one balance, never below zero."""
    remaining = int(balance.credits_remaining or 0)
    if remaining <= 0:
        if commit:
            db.commit()
        return 0
    db.execute(
        text("UPDATE credit_balances SET credits_remaining = 0, status = 'reversed', "
             "updated_at = :now WHERE id = :id AND credits_remaining >= :n"),
        {"now": _now(), "id": balance.id, "n": remaining},
    )
    _ledger(
        db, balance.user_id, balance.id, "reverse", balance.source, -remaining,
        reason, balance.reference or balance.grant_key,
        f"reverse:{balance.grant_key}",
    )
    if commit:
        db.commit()
    else:
        db.flush()
    return remaining
