"""Provision Paystack subscription plans for the configured environment.

Usage (from backend/):
    python scripts/paystack_plans.py            # create missing plan codes
    python scripts/paystack_plans.py --dry-run  # show what would be created

Reads PAYSTACK_SECRET_KEY from the environment only. Never prints the key.
Test and live plan codes are stored in separate columns; a plan code is created
once per environment and reused afterwards.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests
from sqlalchemy.orm import sessionmaker

from src.database import SubscriptionPlanDB, engine
from src import paystack


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    env = paystack.environment()
    print(f"Paystack environment: {env}")
    Session = sessionmaker(bind=engine)
    db = Session()
    created = 0
    try:
        for plan in db.query(SubscriptionPlanDB).filter(
                SubscriptionPlanDB.active.is_(True)).all():
            field = ("paystack_test_plan_code" if env == "test"
                     else "paystack_live_plan_code")
            if getattr(plan, field):
                print(f"{plan.slug}: already provisioned")
                continue
            if args.dry_run:
                print(f"{plan.slug}: would create "
                      f"{plan.name} GHS {plan.price_pesewas / 100:.2f} "
                      f"{plan.interval}")
                continue
            payload = {
                "name": f"{plan.name} ({env})",
                "interval": "annually" if plan.interval == "annual" else "monthly",
                "amount": int(plan.price_pesewas),
                "currency": "GHS",
                "description": plan.description,
            }
            resp = requests.post(
                f"{paystack.API_BASE}/plan", json=payload,
                headers={"Authorization": f"Bearer {os.environ['PAYSTACK_SECRET_KEY']}"},
                timeout=paystack.TIMEOUT,
            )
            body = resp.json() if resp.content else {}
            if not resp.ok or not body.get("status"):
                print(f"{plan.slug}: FAILED (HTTP {resp.status_code})")
                continue
            data = body.get("data") or {}
            setattr(plan, field, data.get("plan_code", ""))
            db.commit()
            created += 1
            print(f"{plan.slug}: provisioned")
        print(f"created {created} plan(s)")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
