"""Paystack subscription, webhook and automatic licence tests (mocked API)."""
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.database import (  # noqa: E402
    Base, EntitlementDB, SubscriptionPlanDB, SubscriptionTransactionDB,
    UserLicenseDB, UserSubscriptionDB, get_db,
)
from src.routers import paystack as router_module  # noqa: E402
from src.auth import get_current_user  # noqa: E402
from src import paystack  # noqa: E402
from tests.conftest import make_user  # noqa: E402

SECRET = "sk_test_unit_secret"
PUBLIC = "pk_test_unit_public"


class _Resp:
    def __init__(self, data, ok=True, status=200):
        self._data = data
        self.ok = ok
        self.status_code = status
        self.content = b"x"

    def json(self):
        return {"status": self.ok, "data": self._data}


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    for slug, name, price, interval, days, credits, kind in (
        ("flexible-credit-pack", "Flexible Credit Pack", 1200, "one_time", 0, 20, "flexible"),
        ("teacher-monthly", "Teacher Monthly", 2200, "one_time", 30, 40, "timed"),
    ):
        session.add(SubscriptionPlanDB(
            slug=slug, name=name, price_pesewas=price, currency="GHS",
            interval=interval, duration_days=days,
            features=["Lesson-plan credits"],
            entitlements={"generation_limit": 0, "ai_enabled": True,
                          "credit_allowance": credits},
            active=True, paystack_test_plan_code=f"PLN_{slug}",
            package_kind=kind, credit_allowance=credits,
            credit_validity_days=days or None,
        ))
    session.commit()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("PAYSTACK_SECRET_KEY", SECRET)
    monkeypatch.setenv("NEXT_PUBLIC_PAYSTACK_PUBLIC_KEY", PUBLIC)
    monkeypatch.setenv("PAYSTACK_CURRENCY", "GHS")
    return monkeypatch


def _client(db, user=None):
    app = FastAPI()
    app.include_router(router_module.router, prefix="/api/paystack")
    app.dependency_overrides[get_db] = lambda: db
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _webhook(client, event, data):
    raw = json.dumps({"event": event, "data": data}).encode()
    sig = hmac.new(SECRET.encode(), raw, hashlib.sha512).hexdigest()
    return client.post("/api/paystack/webhook", content=raw,
                       headers={"x-paystack-signature": sig,
                                "content-type": "application/json"})


def test_config_status_rejects_missing_and_mixed_keys(db, monkeypatch):
    monkeypatch.delenv("PAYSTACK_SECRET_KEY", raising=False)
    monkeypatch.delenv("NEXT_PUBLIC_PAYSTACK_PUBLIC_KEY", raising=False)
    assert _client(db).get("/api/paystack/config-status").json()["configured"] is False

    monkeypatch.setenv("PAYSTACK_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("NEXT_PUBLIC_PAYSTACK_PUBLIC_KEY", "pk_live_x")
    assert _client(db).get("/api/paystack/config-status").json()["configured"] is False


def test_plans_are_listed_server_side(db, env):
    body = _client(db).get("/api/paystack/plans").json()
    assert [p["slug"] for p in body["plans"]] == [
        "flexible-credit-pack", "teacher-monthly"]
    assert body["plans"][1]["price_pesewas"] == 2200
    assert body["plans"][1]["credits"] == 40
    assert body["plans"][1]["credit_validity_days"] == 30


def test_catalogue_includes_free_and_excludes_legacy(db, env):
    body = _client(db).get("/api/paystack/catalogue").json()
    slugs = [p["slug"] for p in body["plans"]]
    assert slugs[0] == "free"
    assert "teacher-annual" not in slugs
    assert body["plans"][0]["credits"] == 2
    assert body["payment_methods"] == ["bank_transfer", "mobile_money"]


def test_initialize_requires_auth(db, env):
    r = _client(db).post("/api/paystack/initialize",
                         json={"plan_slug": "teacher-monthly"})
    assert r.status_code in (401, 403)


def test_initialize_rejects_unknown_plan(db, env):
    user = make_user(db)
    r = _client(db, user).post("/api/paystack/bank-transfer/charge",
                               json={"plan_slug": "does-not-exist"})
    assert r.status_code == 404


def test_card_checkout_is_disabled(db, env, monkeypatch):
    user = make_user(db)
    called = {"n": 0}

    def fake_request(*a, **k):
        called["n"] += 1
        return _Resp({})

    monkeypatch.setattr("requests.request", fake_request)
    r = _client(db, user).post("/api/paystack/initialize",
                               json={"plan_slug": "teacher-monthly", "amount": 1})
    assert r.status_code == 410
    assert "Card checkout" in r.json()["detail"]
    assert called["n"] == 0
    assert db.query(SubscriptionTransactionDB).count() == 0


def test_bank_transfer_fails_safely_without_configuration(db, monkeypatch):
    monkeypatch.delenv("PAYSTACK_SECRET_KEY", raising=False)
    user = make_user(db)
    r = _client(db, user).post("/api/paystack/bank-transfer/charge",
                               json={"plan_slug": "teacher-monthly"})
    assert r.status_code == 503
    assert "No payment was taken" in r.json()["detail"]
    assert db.query(SubscriptionTransactionDB).count() == 0


def _started_tx(db, user, slug="teacher-monthly", amount=2200):
    plan = db.query(SubscriptionPlanDB).filter_by(slug=slug).one()
    tx = SubscriptionTransactionDB(
        reference="TF-ref-1", user_id=user.id, plan_id=plan.id,
        environment="test", amount_pesewas=amount, currency="GHS",
        status="pending")
    db.add(tx)
    db.commit()
    return tx


def test_verify_success_issues_licence_once(db, env, monkeypatch):
    user = make_user(db)
    tx = _started_tx(db, user)
    payload = {"status": "success", "amount": 2200, "currency": "GHS",
               "reference": tx.reference, "id": 12345,
               "customer": {"customer_code": "CUS_1"}, "channel": "card"}
    monkeypatch.setattr(paystack, "verify", lambda ref: payload)

    body = _client(db, user).get(f"/api/paystack/verify/{tx.reference}").json()
    assert body["status"] == "success"
    assert body["licence"]["key"].startswith("TF-")
    first_expiry = body["licence"]["expires_at"]

    lic_count = db.query(UserLicenseDB).count()
    ent = db.query(EntitlementDB).filter_by(user_id=user.id).one()
    assert ent.status == "active" and ent.source == "paystack"
    assert ent.expires_at is not None

    # Repeat verification must not extend or duplicate.
    body2 = _client(db, user).get(f"/api/paystack/verify/{tx.reference}").json()
    assert body2["licence"]["expires_at"] == first_expiry
    assert db.query(UserLicenseDB).count() == lic_count


def test_late_card_reconciliation_keeps_prepaid_momo_mode(db, env):
    """A card payment verified after a newer MoMo payment earns its period
    without relabelling the active prepaid licence as recurring card.

    Paystack returns ``plan`` as a string on some charge payloads, so this
    also guards the activation path against treating it as a dict.
    """
    user = make_user(db)
    plan = db.query(SubscriptionPlanDB).filter_by(slug="teacher-monthly").one()
    now = datetime.utcnow()

    momo = SubscriptionTransactionDB(
        reference="TF-momo-1", user_id=user.id, plan_id=plan.id,
        environment="test", amount_pesewas=2200, currency="GHS",
        status="pending", payment_method="mobile_money")
    db.add(momo)
    db.commit()
    paystack.activate_paid_transaction(db, momo, {
        "status": "success", "amount": 2200, "currency": "GHS",
        "reference": "TF-momo-1",
        "id": 1, "channel": "mobile_money", "plan": "PLN_momo",
        "paid_at": now.isoformat(), "customer": {"customer_code": "CUS_2"}})
    sub = db.query(UserSubscriptionDB).filter_by(user_id=user.id).one()
    assert sub.billing_mode == "prepaid"
    first_paid_through = sub.paid_through

    card = SubscriptionTransactionDB(
        reference="TF-card-1", user_id=user.id, plan_id=plan.id,
        environment="test", amount_pesewas=2200, currency="GHS",
        status="pending", payment_method="card_recurring")
    db.add(card)
    db.commit()
    paystack.activate_paid_transaction(db, card, {
        "status": "success", "amount": 2200, "currency": "GHS",
        "reference": "TF-card-1",
        "id": 2, "channel": "card", "plan": "PLN_card",
        "paid_at": (now - timedelta(days=1)).isoformat(),
        "customer": {"customer_code": "CUS_2"}})

    db.refresh(sub)
    assert card.status == "success"
    assert sub.billing_mode == "prepaid"
    assert sub.payment_method == "mobile_money"
    assert sub.current_period_start is not None
    assert sub.paid_through == first_paid_through + timedelta(
        days=plan.duration_days)
    assert db.query(UserLicenseDB).count() == 1


def test_verify_rejects_amount_and_pending(db, env, monkeypatch):
    user = make_user(db)
    tx = _started_tx(db, user)
    monkeypatch.setattr(paystack, "verify", lambda ref: {
        "status": "success", "amount": 100, "currency": "GHS",
        "reference": ref, "id": 1})
    r = _client(db, user).get(f"/api/paystack/verify/{tx.reference}")
    assert r.status_code == 400
    assert db.query(UserLicenseDB).count() == 0

    monkeypatch.setattr(paystack, "verify", lambda ref: {
        "status": "failed", "amount": 2200, "currency": "GHS",
        "reference": ref, "id": 2})
    r = _client(db, user).get(f"/api/paystack/verify/{tx.reference}")
    assert r.status_code == 402


def test_webhook_rejects_invalid_signature(db, env):
    r = _client(db).post("/api/paystack/webhook", content=b"{}",
                         headers={"x-paystack-signature": "bad"})
    assert r.status_code == 401


def test_webhook_charge_success_is_idempotent(db, env, monkeypatch):
    user = make_user(db)
    tx = _started_tx(db, user)
    payload = {"status": "success", "amount": 2200, "currency": "GHS",
               "reference": tx.reference, "id": 99,
               "customer": {"customer_code": "CUS_2"}, "channel": "card"}
    monkeypatch.setattr(paystack, "verify", lambda ref: payload)
    data = {"reference": tx.reference, "id": 777, "status": "success",
            "amount": 2200, "currency": "GHS",
            "customer": {"customer_code": "CUS_2", "email": user.email}}

    client = _client(db)
    assert _webhook(client, "charge.success", data).status_code == 200
    db.expire_all()
    assert db.query(UserLicenseDB).count() == 1
    expiry = db.query(UserLicenseDB).one().expires_at

    dup = _webhook(client, "charge.success", data)
    assert dup.status_code == 200 and dup.json().get("duplicate") is True
    db.expire_all()
    assert db.query(UserLicenseDB).one().expires_at == expiry


def test_failed_invoice_marks_past_due_without_removing_access(db, env, monkeypatch):
    user = make_user(db)
    tx = _started_tx(db, user)
    payload = {"status": "success", "amount": 2200, "currency": "GHS",
               "reference": tx.reference, "id": 5,
               "customer": {"customer_code": "CUS_3"}, "channel": "card"}
    monkeypatch.setattr(paystack, "verify", lambda ref: payload)
    client = _client(db)
    _webhook(client, "charge.success", {
        "reference": tx.reference, "id": 5, "amount": 2200, "currency": "GHS",
        "customer": {"email": user.email}})
    sub = db.query(UserSubscriptionDB).filter_by(user_id=user.id).one()
    sub.provider_subscription_code = "SUB_1"
    db.commit()

    r = _webhook(client, "invoice.payment_failed", {
        "subscription_code": "SUB_1", "id": 11, "status": "failed",
        "customer": {"email": user.email}})
    assert r.status_code == 200
    db.expire_all()
    sub = db.query(UserSubscriptionDB).filter_by(user_id=user.id).one()
    assert sub.status == "past_due"
    assert sub.grace_until is not None
    assert db.query(UserLicenseDB).one().status == "active"


def test_prepaid_package_has_no_cancel_and_keeps_access(db, env, monkeypatch):
    user = make_user(db)
    tx = _started_tx(db, user)
    payload = {"status": "success", "amount": 2200, "currency": "GHS",
               "reference": tx.reference, "id": 6,
               "customer": {"customer_code": "CUS_4"}, "channel": "card"}
    monkeypatch.setattr(paystack, "verify", lambda ref: payload)
    client = _client(db, user)
    client.get(f"/api/paystack/verify/{tx.reference}")
    sub = db.query(UserSubscriptionDB).filter_by(user_id=user.id).one()
    paid_through = sub.paid_through

    r = client.post("/api/paystack/cancel")
    assert r.status_code == 400
    assert "renew automatically" in r.json()["detail"]
    db.expire_all()
    sub = db.query(UserSubscriptionDB).filter_by(user_id=user.id).one()
    assert sub.paid_through == paid_through


def test_expiry_removes_paid_entitlement_but_keeps_history(db, env):
    user = make_user(db)
    tx = _started_tx(db, user)
    sub = UserSubscriptionDB(user_id=user.id, plan_id=tx.plan_id,
                             status="active", environment="test",
                             paid_through=datetime.utcnow() - timedelta(days=4))
    db.add(sub)
    db.add(UserLicenseDB(user_id=user.id, plan_id=tx.plan_id,
                         licence_key="TF-TEST", key_hash="hash",
                         status="active", expires_at=sub.paid_through))
    db.add(EntitlementDB(user_id=user.id, edition="pro", status="active",
                         source="paystack", expires_at=sub.paid_through))
    db.commit()
    paystack.expire_overdue(db)
    db.expire_all()
    assert db.query(UserSubscriptionDB).one().status == "expired"
    assert db.query(UserLicenseDB).one().status == "expired"
    # Payment history is never deleted.
    assert db.query(SubscriptionTransactionDB).count() == 1


# ── Mobile Money (prepaid, no recurring authorisation) ─────────────────────

def test_customer_facing_card_route_is_absent(db, env, monkeypatch):
    """No new card/recurring charge can be started from the public API."""
    user = make_user(db)
    called = {"n": 0}
    monkeypatch.setattr("requests.request",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    r = _client(db, user).post("/api/paystack/initialize",
                               json={"plan_slug": "teacher-monthly"})
    assert r.status_code == 410
    assert called["n"] == 0


def test_momo_charge_pay_offline_and_instructions(db, env, monkeypatch):
    user = make_user(db)
    seen = {}

    def fake_request(method, url, **kwargs):
        seen.update(kwargs.get("json") or {})
        return _Resp({"reference": "x", "status": "pay_offline",
                      "display_text": "Please approve on your phone"})

    monkeypatch.setattr("requests.request", fake_request)
    r = _client(db, user).post("/api/paystack/momo/charge", json={
        "plan_slug": "teacher-monthly", "phone": "0551234987",
        "provider": "mtn"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["charge_status"] == "pay_offline"
    assert "approve" in body["display_text"]
    assert seen["mobile_money"] == {"phone": "0551234987", "provider": "mtn"}
    assert seen["currency"] == "GHS" and seen["amount"] == 2200
    assert "plan" not in seen  # one-time charge, never a recurring plan
    tx = db.query(SubscriptionTransactionDB).one()
    assert tx.payment_method == "mobile_money" and tx.status == "pending"
    assert db.query(UserLicenseDB).count() == 0


def test_momo_rejects_wrong_provider_or_phone(db, env):
    user = make_user(db)
    client = _client(db, user)
    r = client.post("/api/paystack/momo/charge", json={
        "plan_slug": "teacher-monthly", "phone": "0551234987",
        "provider": "card"})
    assert r.status_code == 400
    r = client.post("/api/paystack/momo/charge", json={
        "plan_slug": "teacher-monthly", "phone": "0551234987",
        "provider": "telecel"})  # 055 is MTN, not Telecel
    assert r.status_code == 400
    r = client.post("/api/paystack/momo/charge", json={
        "plan_slug": "teacher-monthly", "phone": "123",
        "provider": "mtn"})
    assert r.status_code == 400
    assert db.query(SubscriptionTransactionDB).count() == 0


def test_momo_delayed_success_issues_prepaid_licence_once(db, env, monkeypatch):
    user = make_user(db)
    monkeypatch.setattr("requests.request", lambda *a, **k: _Resp({
        "reference": "r", "status": "pay_offline",
        "display_text": "Approve on your phone"}))
    client = _client(db, user)
    r = client.post("/api/paystack/momo/charge", json={
        "plan_slug": "teacher-monthly", "phone": "0551234987",
        "provider": "mtn"})
    ref = r.json()["reference"]
    payload = {"status": "success", "amount": 2200, "currency": "GHS",
               "reference": ref, "id": 501, "channel": "mobile_money",
               "customer": {"customer_code": "CUS_M"}}
    monkeypatch.setattr(paystack, "check_charge", lambda ref: payload)
    monkeypatch.setattr(paystack, "verify", lambda ref: payload)

    first = client.get(f"/api/paystack/momo/status/{ref}").json()
    assert first["status"] == "success"
    assert first["licence"]["key"].startswith("TF-")
    assert first["subscription"]["billing_mode"] == "prepaid"
    assert first["subscription"]["payment_method"] == "mobile_money"
    expiry = first["licence"]["expires_at"]

    second = client.get(f"/api/paystack/momo/status/{ref}").json()
    assert second["licence"]["expires_at"] == expiry
    assert db.query(UserLicenseDB).count() == 1


def test_momo_failed_charge_marks_failed_without_licence(db, env, monkeypatch):
    user = make_user(db)
    monkeypatch.setattr("requests.request", lambda *a, **k: _Resp({
        "reference": "r", "status": "pay_offline",
        "display_text": "Approve on your phone"}))
    client = _client(db, user)
    ref = client.post("/api/paystack/momo/charge", json={
        "plan_slug": "teacher-monthly", "phone": "0551234987",
        "provider": "mtn"}).json()["reference"]
    monkeypatch.setattr(paystack, "check_charge",
                        lambda ref: {"status": "failed", "reference": ref})
    body = client.get(f"/api/paystack/momo/status/{ref}").json()
    assert body["status"] == "failed"
    assert db.query(UserLicenseDB).count() == 0


def test_momo_webhook_wrong_amount_never_issues_licence(db, env, monkeypatch):
    user = make_user(db)
    monkeypatch.setattr("requests.request", lambda *a, **k: _Resp({
        "reference": "r", "status": "pay_offline",
        "display_text": "Approve"}))
    client = _client(db)
    ref = _client(db, user).post("/api/paystack/momo/charge", json={
        "plan_slug": "teacher-monthly", "phone": "0551234987",
        "provider": "mtn"}).json()["reference"]
    monkeypatch.setattr(paystack, "verify", lambda ref: {
        "status": "success", "amount": 1, "currency": "GHS",
        "reference": ref, "id": 9})
    r = _webhook(client, "charge.success", {
        "reference": ref, "status": "success", "amount": 1,
        "currency": "GHS", "id": 9, "channel": "mobile_money",
        "customer": {"email": user.email}})
    assert r.status_code == 200
    assert db.query(UserLicenseDB).count() == 0


def test_momo_does_not_auto_renew_and_cancel_is_rejected(db, env, monkeypatch):
    user = make_user(db)
    monkeypatch.setattr("requests.request", lambda *a, **k: _Resp({
        "reference": "r", "status": "pay_offline", "display_text": "Approve"}))
    client = _client(db, user)
    ref = client.post("/api/paystack/momo/charge", json={
        "plan_slug": "teacher-monthly", "phone": "0551234987",
        "provider": "mtn"}).json()["reference"]
    payload = {"status": "success", "amount": 2200, "currency": "GHS",
               "reference": ref, "id": 10, "channel": "mobile_money"}
    monkeypatch.setattr(paystack, "check_charge", lambda ref: payload)
    monkeypatch.setattr(paystack, "verify", lambda ref: payload)
    client.get(f"/api/paystack/momo/status/{ref}")
    r = client.post("/api/paystack/cancel")
    assert r.status_code == 400
    assert "prepaid" in r.json()["detail"].lower()
