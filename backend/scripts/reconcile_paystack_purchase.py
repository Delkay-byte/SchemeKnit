"""Safely reconcile one Paystack purchase through the application services.

Read-only by default. It never creates a charge, never changes package prices
and never edits a ledger row directly.

Examples::

    python -m scripts.reconcile_paystack_purchase --reference TFM-...
    python -m scripts.reconcile_paystack_purchase --reference TFM-... \
        --apply --confirm TFM-... \
        --reason "Verified live Paystack success; credits were not activated"

The write path requires the exact reference as confirmation and uses the same
idempotent activation service as the webhook/verify endpoints.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import paystack  # noqa: E402
from src.database import (  # noqa: E402
    SessionLocal, SubscriptionEventDB, SubscriptionPlanDB,
    SubscriptionTransactionDB, User, UserLicenseDB, generate_id,
)


def _mask(email: str) -> str:
    if not email or "@" not in email:
        return "—"
    name, domain = email.split("@", 1)
    return f"{name[:2]}***@{domain}"


def _summary(db, tx) -> dict:
    user = db.query(User).filter(User.id == tx.user_id).first()
    plan = db.query(SubscriptionPlanDB).filter(
        SubscriptionPlanDB.id == tx.plan_id).first()
    lic = db.query(UserLicenseDB).filter(
        UserLicenseDB.user_id == tx.user_id).first()
    payload = paystack.purchase_payload(db, tx)
    return {
        "reference": tx.reference,
        "environment": tx.environment,
        "local_status": tx.status,
        "payment_status": payload["payment_status"],
        "fulfilment_status": payload["fulfilment_status"],
        "package": plan.name if plan else "",
        "package_slug": plan.slug if plan else "",
        "amount_ghs": f"{(tx.amount_pesewas or 0) / 100:.2f}",
        "currency": tx.currency,
        "channel": tx.channel or tx.payment_method,
        "account": _mask(user.email if user else ""),
        "licence": lic.status if lic else "none",
        "credits_granted": payload["credits_granted"],
        "credit_balance": (payload.get("credit_balance") or {}).get("total"),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True)
    parser.add_argument("--reason", default="")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        tx = (db.query(SubscriptionTransactionDB)
              .filter(SubscriptionTransactionDB.reference == args.reference)
              .first())
        if tx is None:
            print("ERROR: purchase not found")
            return 2
        before = _summary(db, tx)
        print("BEFORE", before)
        if not args.apply:
            print("READ-ONLY. Re-run with --apply --confirm <reference> to reconcile.")
            return 0
        if args.confirm != args.reference:
            print("ERROR: --confirm must equal the exact reference")
            return 2
        if len((args.reason or "").strip()) < 5:
            print("ERROR: a reconciliation reason is required")
            return 2
        if tx.status in ("reversed", "refunded"):
            print("ERROR: reversed/refunded payment cannot be activated")
            return 2

        verified = paystack.verify(args.reference)  # server-side, live status
        user = db.query(User).filter(User.id == tx.user_id).first()
        try:
            paystack._validate_verified_payment(tx, verified, user)
        except paystack.PaystackError as exc:
            print("ERROR: Paystack verification refused:", exc.message)
            return 2

        if tx.status in ("failed", "expired"):
            tx.status = "pending"
            tx.charge_status = "success"
            db.commit()
        sub, lic = paystack.activate_paid_transaction(db, tx, verified)
        plan = db.query(SubscriptionPlanDB).filter(
            SubscriptionPlanDB.id == tx.plan_id).first()
        from src.purchase_notifications import notify_purchase
        notify_purchase(db, tx, user, plan, sub, lic)

        history = list((tx.payment_details or {}).get("reconciliation") or [])
        history.append({
            "actor": "operator-cli",
            "reason": args.reason.strip(),
            "at": datetime.utcnow().isoformat(),
            "before": before["fulfilment_status"],
            "after": paystack.fulfilment_state(db, tx),
        })
        details = dict(tx.payment_details or {})
        details["reconciliation"] = history
        tx.payment_details = details
        if sub is not None:
            db.add(SubscriptionEventDB(
                id=generate_id(), subscription_id=sub.id,
                event_type="reconciled",
                metadata_json={"reference": args.reference,
                               "reason": args.reason.strip(),
                               "actor": "operator-cli"},
            ))
        db.commit()
        print("AFTER", _summary(db, tx))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
