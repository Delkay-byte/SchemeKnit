"""Prepaid Bank Transfer / Mobile Money payment tests (mocked Paystack)."""
from __future__ import annotations

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

from src import catalogue, credits, paystack  # noqa: E402
from src.auth import get_current_user  # noqa: E402
from src.database import (  # noqa: E402
    Base, CreditBalanceDB, CreditLedgerDB, EntitlementDB, ReferralDB,
    SubscriptionPlanDB, SubscriptionTransactionDB, UserLicenseDB,
    PaystackWebhookEventDB, get_db,
)
from src.routers import paystack as router_module  # noqa: E402
from tests.conftest import make_user  # noqa: E402

SECRET = "sk_test_prepaid_secret"
PUBLIC = "pk_test_prepaid_public"


class _Resp:
    def __init__(self, data, ok=True):
        self._data = data
        self.ok = ok
        self.status_code = 200

    def json(self):
        return {"status": self.ok, "data": self._data}


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    for package in (catalogue.FLEXIBLE_CREDIT_PACK, catalogue.TEACHER_MONTHLY):
        session.add(SubscriptionPlanDB(
            slug=package.slug, name=package.name,
            price_pesewas=package.price_pesewas, currency="GHS",
            interval="one_time", duration_days=package.validity_days or 0,
            features=list(package.features),
            entitlements=package.entitlements(), active=True,
            package_kind=package.kind, credit_allowance=package.credits,
            credit_validity_days=package.validity_days,
        ))
    session.commit()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("PAYSTACK_SECRET_KEY", SECRET)
    monkeypatch.setenv("NEXT_PUBLIC_PAYSTACK_PUBLIC_KEY", PUBLIC)
    monkeypatch.setenv("PAYSTACK_CURRENCY", "GHS")


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


def _bank_response():
    return {
        "reference": "ignored-by-server",
        "status": "pending_bank_transfer",
        "display_text": "Please make a transfer to the account specified",
        "account_name": "TEST-MANAGED-ACCOUNT",
        "account_number": "1260257501",
        "bank": {"slug": "test-bank", "name": "Test Bank"},
        "account_expires_at": (datetime.utcnow() + timedelta(hours=8)).isoformat(),
    }


def _momo_response():
    return {
        "reference": "ignored-by-server",
        "status": "pay_offline",
        "display_text": "Please approve on your phone",
    }


class TestBankTransfer:
    def test_initialization_uses_server_package_amount(self, db, monkeypatch):
        user = make_user(db)
        seen = {}

        def fake_request(method, url, **kwargs):
            seen.update(kwargs.get("json") or {})
            return _Resp(_bank_response())

        monkeypatch.setattr("requests.request", fake_request)
        r = _client(db, user).post("/api/paystack/bank-transfer/charge",
                                   json={"plan_slug": "teacher-monthly",
                                         "amount": 1, "credits": 999})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "pending"
        assert body["payment_details"]["account_number"] == "1260257501"
        assert seen["amount"] == 2200
        assert seen["currency"] == "GHS"
        assert "plan" not in seen  # no recurring plan code
        assert "channels" not in seen  # no card channel
        assert seen["metadata"]["billing_mode"] == "prepaid"
        assert seen["metadata"]["payment_method"] == "bank_transfer"
        assert "bank_transfer" in seen
        tx = db.query(SubscriptionTransactionDB).one()
        assert tx.status == "pending" and tx.payment_method == "bank_transfer"
        assert db.query(UserLicenseDB).count() == 0
        assert credits.status(db, user.id)["purchased"] == 0

    def test_webhook_success_activates_package_and_credits_once(self, db, monkeypatch):
        user = make_user(db)
        monkeypatch.setattr("requests.request", lambda *a, **k: _Resp(_bank_response()))
        client = _client(db, user)
        ref = client.post("/api/paystack/bank-transfer/charge",
                          json={"plan_slug": "teacher-monthly"}).json()["reference"]
        payload = {
            "status": "success", "amount": 2200, "currency": "GHS",
            "reference": ref, "id": 9001, "channel": "bank_transfer",
            "paid_at": datetime.utcnow().isoformat(),
            "customer": {"email": user.email, "customer_code": "CUS_B"},
            "metadata": {"user_id": user.id},
        }
        monkeypatch.setattr(paystack, "verify", lambda reference: dict(payload))
        hook = {
            "reference": ref, "id": 9001, "status": "success", "amount": 2200,
            "currency": "GHS", "channel": "bank_transfer",
            "customer": {"email": user.email},
        }
        assert _webhook(_client(db), "charge.success", hook).status_code == 200
        db.expire_all()
        assert db.query(UserLicenseDB).count() == 1
        balances = db.query(CreditBalanceDB).all()
        assert len(balances) == 1
        assert balances[0].source == "package"
        assert balances[0].credits_remaining == 40
        assert balances[0].expires_at is not None
        ent = db.query(EntitlementDB).filter_by(user_id=user.id).one()
        assert ent.status == "active" and ent.source == "paystack"
        tx = db.query(SubscriptionTransactionDB).filter_by(reference=ref).one()
        assert tx.status == "success"

        # Duplicate delivery is recorded but pays nothing more.
        dup = _webhook(_client(db), "charge.success", hook)
        assert dup.status_code == 200 and dup.json().get("duplicate") is True
        db.expire_all()
        assert db.query(CreditBalanceDB).count() == 1
        assert credits.status(db, user.id)["package"] == 40

    def test_failed_transfer_marks_failed_without_licence(self, db, monkeypatch):
        user = make_user(db)
        monkeypatch.setattr("requests.request", lambda *a, **k: _Resp(_bank_response()))
        client = _client(db, user)
        ref = client.post("/api/paystack/bank-transfer/charge",
                          json={"plan_slug": "teacher-monthly"}).json()["reference"]
        _webhook(_client(db), "bank.transfer.rejected",
                 {"reference": ref, "status": "failed", "id": 77,
                  "customer": {"email": user.email}})
        db.expire_all()
        tx = db.query(SubscriptionTransactionDB).filter_by(reference=ref).one()
        assert tx.status == "failed"
        assert db.query(UserLicenseDB).count() == 0
        assert credits.status(db, user.id)["package"] == 0

    def test_expired_account_is_reported_expired(self, db, monkeypatch):
        user = make_user(db)
        past = (datetime.utcnow() - timedelta(minutes=1)).isoformat()
        data = _bank_response()
        data["account_expires_at"] = past
        monkeypatch.setattr("requests.request", lambda *a, **k: _Resp(data))
        monkeypatch.setattr(paystack, "check_charge", lambda ref: data)
        client = _client(db, user)
        ref = client.post("/api/paystack/bank-transfer/charge",
                          json={"plan_slug": "teacher-monthly"}).json()["reference"]
        body = client.get(f"/api/paystack/charge/status/{ref}").json()
        assert body["status"] == "expired"
        assert db.query(UserLicenseDB).count() == 0

    def test_wrong_currency_customer_or_amount_never_activates(self, db, monkeypatch):
        user = make_user(db)
        monkeypatch.setattr("requests.request", lambda *a, **k: _Resp(_bank_response()))
        client = _client(db, user)
        ref = client.post("/api/paystack/bank-transfer/charge",
                          json={"plan_slug": "teacher-monthly"}).json()["reference"]

        for bad in (
            {"status": "success", "amount": 1, "currency": "GHS",
             "reference": ref, "id": 1, "customer": {"email": user.email}},
            {"status": "success", "amount": 2200, "currency": "NGN",
             "reference": ref, "id": 1, "customer": {"email": user.email}},
            {"status": "success", "amount": 2200, "currency": "GHS",
             "reference": ref, "id": 1, "customer": {"email": "other@test.com"}},
            {"status": "success", "amount": 2200, "currency": "GHS",
             "reference": ref, "id": 1, "customer": {"email": user.email},
             "metadata": {"user_id": "someone-else"}},
        ):
            monkeypatch.setattr(paystack, "verify", lambda reference, b=bad: dict(b))
            _webhook(_client(db), "charge.success", {
                "reference": ref, "id": b"x" if False else 1,
                "status": "success", "amount": 2200, "currency": "GHS",
                "customer": {"email": user.email}})
            db.expire_all()
            assert db.query(UserLicenseDB).count() == 0

    def test_verify_endpoint_activates_delayed_payment(self, db, monkeypatch):
        user = make_user(db)
        monkeypatch.setattr("requests.request", lambda *a, **k: _Resp(_bank_response()))
        client = _client(db, user)
        ref = client.post("/api/paystack/bank-transfer/charge",
                          json={"plan_slug": "teacher-monthly"}).json()["reference"]
        payload = {"status": "success", "amount": 2200, "currency": "GHS",
                   "reference": ref, "id": 5, "channel": "bank_transfer",
                   "customer": {"email": user.email}}
        monkeypatch.setattr(paystack, "verify", lambda reference: dict(payload))
        body = client.get(f"/api/paystack/verify/{ref}").json()
        assert body["status"] == "success"
        assert body["credits"]["package"] == 40
        assert db.query(UserLicenseDB).count() == 1


class TestMobileMoney:
    def test_pay_offline_is_pending_with_instructions(self, db, monkeypatch):
        user = make_user(db)
        seen = {}

        def fake_request(method, url, **kwargs):
            seen.update(kwargs.get("json") or {})
            return _Resp(_momo_response())

        monkeypatch.setattr("requests.request", fake_request)
        body = _client(db, user).post("/api/paystack/momo/charge", json={
            "plan_slug": "teacher-monthly", "phone": "0551234987",
            "provider": "mtn"}).json()
        assert body["status"] == "pending"
        assert body["charge_status"] == "pay_offline"
        assert body["awaiting_authorisation"] is True
        assert "approve" in body["display_text"].lower()
        assert seen["amount"] == 2200
        assert seen["mobile_money"] == {"phone": "0551234987", "provider": "mtn"}
        assert "plan" not in seen
        assert "authorization_code" not in seen  # no reusable authorisation

    @pytest.mark.parametrize("provider,phone,ok", [
        ("mtn", "0241234567", True),
        ("telecel", "0201234567", True),
        ("airteltigo", "0261234567", True),
        ("mtn", "0201234567", False),
        ("telecel", "0241234567", False),
        ("card", "0241234567", False),
        ("mtn", "123", False),
    ])
    def test_provider_and_phone_validation(self, db, monkeypatch, provider, phone, ok):
        user = make_user(db)
        monkeypatch.setattr("requests.request", lambda *a, **k: _Resp(_momo_response()))
        r = _client(db, user).post("/api/paystack/momo/charge", json={
            "plan_slug": "teacher-monthly", "phone": phone,
            "provider": provider})
        assert (r.status_code == 200) is ok


class TestPackageCredits:
    def test_flexible_pack_credits_have_no_expiry(self, db, monkeypatch):
        user = make_user(db)
        monkeypatch.setattr("requests.request", lambda *a, **k: _Resp(_momo_response()))
        client = _client(db, user)
        ref = client.post("/api/paystack/momo/charge", json={
            "plan_slug": "flexible-credit-pack", "phone": "0551234987",
            "provider": "mtn"}).json()["reference"]
        payload = {"status": "success", "amount": 1200, "currency": "GHS",
                   "reference": ref, "id": 11, "channel": "mobile_money",
                   "customer": {"email": user.email}}
        monkeypatch.setattr(paystack, "check_charge", lambda r: payload)
        monkeypatch.setattr(paystack, "verify", lambda r: dict(payload))
        body = client.get(f"/api/paystack/charge/status/{ref}").json()
        assert body["status"] == "success"
        bal = db.query(CreditBalanceDB).one()
        assert bal.source == "purchased"
        assert bal.credits_remaining == 20
        assert bal.expires_at is None
        assert body["credits"]["purchased"] == 20


class TestReversal:
    def test_refund_reverses_unused_credits_and_blocks_late_success(self, db, monkeypatch):
        user = make_user(db)
        monkeypatch.setattr("requests.request", lambda *a, **k: _Resp(_bank_response()))
        client = _client(db, user)
        ref = client.post("/api/paystack/bank-transfer/charge",
                          json={"plan_slug": "teacher-monthly"}).json()["reference"]
        payload = {"status": "success", "amount": 2200, "currency": "GHS",
                   "reference": ref, "id": 8001, "channel": "bank_transfer",
                   "customer": {"email": user.email}}
        monkeypatch.setattr(paystack, "verify", lambda r: dict(payload))
        assert _webhook(_client(db), "charge.success", {
            "reference": ref, "id": 8001, "status": "success", "amount": 2200,
            "currency": "GHS", "customer": {"email": user.email}}).status_code == 200
        assert credits.status(db, user.id)["package"] == 40

        assert _webhook(_client(db), "refund.processed", {
            "reference": ref, "id": 8002, "status": "processed",
            "customer": {"email": user.email}}).status_code == 200
        db.expire_all()
        tx = db.query(SubscriptionTransactionDB).filter_by(reference=ref).one()
        assert tx.status == "reversed"
        assert credits.status(db, user.id)["package"] == 0
        assert db.query(CreditBalanceDB).one().credits_remaining == 0

        # A late duplicate success delivery cannot reactivate the package.
        _webhook(_client(db), "charge.success", {
            "reference": ref, "id": 8001, "status": "success", "amount": 2200,
            "currency": "GHS", "customer": {"email": user.email}})
        db.expire_all()
        tx = db.query(SubscriptionTransactionDB).filter_by(reference=ref).one()
        assert tx.status == "reversed"
        assert credits.status(db, user.id)["package"] == 0


def test_momo_pending_session_expires_after_provider_window(db, monkeypatch):
    user = make_user(db)
    monkeypatch.setattr("requests.request", lambda *a, **k: _Resp(_momo_response()))
    monkeypatch.setattr(paystack, "check_charge", lambda ref: _momo_response())
    client = _client(db, user)
    ref = client.post("/api/paystack/momo/charge", json={
        "plan_slug": "teacher-monthly", "phone": "0551234987",
        "provider": "mtn"}).json()["reference"]
    tx = db.query(SubscriptionTransactionDB).filter_by(reference=ref).one()
    tx.created_at = datetime.utcnow() - timedelta(minutes=10)
    db.commit()
    body = client.get(f"/api/paystack/charge/status/{ref}").json()
    assert body["status"] == "expired"
    assert db.query(UserLicenseDB).count() == 0


class TestPaymentSecurity:
    def test_unknown_reference_webhook_grants_nothing(self, db):
        user = make_user(db)
        r = _webhook(_client(db), "charge.success", {
            "reference": "TF-UNKNOWN", "id": 4242, "status": "success",
            "amount": 5000, "currency": "GHS",
            "customer": {"email": user.email}})
        assert r.status_code == 200
        db.expire_all()
        assert db.query(UserLicenseDB).count() == 0
        assert db.query(CreditBalanceDB).count() == 0

    def test_unknown_reference_verify_is_404(self, db):
        user = make_user(db)
        r = _client(db, user).get("/api/paystack/verify/TF-NOPE")
        assert r.status_code == 404

    def test_another_users_transaction_is_not_readable(self, db, monkeypatch):
        owner = make_user(db)
        other = make_user(db)
        monkeypatch.setattr("requests.request", lambda *a, **k: _Resp(_bank_response()))
        ref = _client(db, owner).post(
            "/api/paystack/bank-transfer/charge",
            json={"plan_slug": "teacher-monthly"}).json()["reference"]
        assert _client(db, other).get(
            f"/api/paystack/verify/{ref}").status_code == 404
        assert _client(db, other).get(
            f"/api/paystack/charge/status/{ref}").status_code == 404

    def test_channel_mismatch_is_rejected(self, db, monkeypatch):
        user = make_user(db)
        monkeypatch.setattr("requests.request", lambda *a, **k: _Resp(_bank_response()))
        ref = _client(db, user).post(
            "/api/paystack/bank-transfer/charge",
            json={"plan_slug": "teacher-monthly"}).json()["reference"]
        monkeypatch.setattr(paystack, "verify", lambda r: {
            "status": "success", "amount": 5000, "currency": "GHS",
            "reference": ref, "id": 31, "channel": "card",
            "customer": {"email": user.email}})
        _webhook(_client(db), "charge.success", {
            "reference": ref, "id": 31, "status": "success", "amount": 5000,
            "currency": "GHS", "customer": {"email": user.email}})
        db.expire_all()
        assert db.query(UserLicenseDB).count() == 0
        assert db.query(CreditBalanceDB).count() == 0

    def test_metadata_package_tampering_is_rejected(self, db, monkeypatch):
        user = make_user(db)
        monkeypatch.setattr("requests.request", lambda *a, **k: _Resp(_bank_response()))
        ref = _client(db, user).post(
            "/api/paystack/bank-transfer/charge",
            json={"plan_slug": "teacher-monthly"}).json()["reference"]
        monkeypatch.setattr(paystack, "verify", lambda r: {
            "status": "success", "amount": 5000, "currency": "GHS",
            "reference": ref, "id": 32, "channel": "bank_transfer",
            "customer": {"email": user.email},
            "metadata": {"user_id": user.id, "plan_id": "other-plan"}})
        _webhook(_client(db), "charge.success", {
            "reference": ref, "id": 32, "status": "success", "amount": 5000,
            "currency": "GHS", "customer": {"email": user.email}})
        db.expire_all()
        assert db.query(UserLicenseDB).count() == 0
        assert db.query(CreditBalanceDB).count() == 0

    def test_duplicate_verify_grants_exactly_once(self, db, monkeypatch):
        user = make_user(db)
        monkeypatch.setattr("requests.request", lambda *a, **k: _Resp(_bank_response()))
        ref = _client(db, user).post(
            "/api/paystack/bank-transfer/charge",
            json={"plan_slug": "teacher-monthly"}).json()["reference"]
        payload = {"status": "success", "amount": 2200, "currency": "GHS",
                   "reference": ref, "id": 33, "channel": "bank_transfer",
                   "customer": {"email": user.email}}
        monkeypatch.setattr(paystack, "verify", lambda r: dict(payload))
        client = _client(db, user)
        assert client.get(f"/api/paystack/verify/{ref}").status_code == 200
        assert client.get(f"/api/paystack/verify/{ref}").status_code == 200
        db.expire_all()
        assert db.query(CreditBalanceDB).count() == 1
        assert db.query(CreditBalanceDB).one().credits_remaining == 40
        assert db.query(UserLicenseDB).count() == 1


class TestProviderCodes:
    @pytest.mark.parametrize("provider,phone,code", [
        ("mtn", "0241234567", "mtn"),
        ("telecel", "0201234567", "vod"),
        ("airteltigo", "0261234567", "atl"),
    ])
    def test_provider_code_is_sent_and_stored(self, db, monkeypatch, provider, phone, code):
        user = make_user(db)
        seen = {}

        def fake_request(method, url, **kwargs):
            seen.update(kwargs.get("json") or {})
            return _Resp(_momo_response())

        monkeypatch.setattr("requests.request", fake_request)
        body = _client(db, user).post("/api/paystack/momo/charge", json={
            "plan_slug": "teacher-monthly", "phone": phone,
            "provider": provider}).json()
        assert body["provider"] == code
        assert seen["mobile_money"]["provider"] == code
        tx = db.query(SubscriptionTransactionDB).one()
        assert tx.provider == code

    def test_international_phone_is_normalized(self, db, monkeypatch):
        user = make_user(db)
        seen = {}

        def fake_request(method, url, **kwargs):
            seen.update(kwargs.get("json") or {})
            return _Resp(_momo_response())

        monkeypatch.setattr("requests.request", fake_request)
        _client(db, user).post("/api/paystack/momo/charge", json={
            "plan_slug": "teacher-monthly", "phone": "+233551234987",
            "provider": "mtn"})
        assert seen["mobile_money"]["phone"] == "0551234987"

    def test_amount_is_new_term_price(self, db, monkeypatch):
        user = make_user(db)
        plan = SubscriptionPlanDB(
            slug="teacher-term-pass", name="Teacher Term Pass",
            price_pesewas=5000, currency="GHS", interval="one_time",
            duration_days=120, active=True, package_kind="timed",
            credit_allowance=160, credit_validity_days=120,
            entitlements={"generation_limit": 0, "credit_allowance": 160},
        )
        db.add(plan)
        db.commit()
        seen = {}

        def fake_request(method, url, **kwargs):
            seen.update(kwargs.get("json") or {})
            return _Resp(_momo_response())

        monkeypatch.setattr("requests.request", fake_request)
        _client(db, user).post("/api/paystack/momo/charge", json={
            "plan_slug": "teacher-term-pass", "phone": "0241234567",
            "provider": "mtn"})
        assert seen["amount"] == 5000
        assert seen["currency"] == "GHS"


def test_concurrent_success_processing_grants_once(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    path = tmp_path / "concurrent.db"
    engine = create_engine(f"sqlite:///{path}",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    setup = Session()
    try:
        user = make_user(setup)
        plan = SubscriptionPlanDB(
            slug="teacher-monthly", name="Teacher Monthly",
            price_pesewas=2200, currency="GHS", interval="one_time",
            duration_days=30, active=True, package_kind="timed",
            credit_allowance=40, credit_validity_days=30,
            entitlements={"generation_limit": 0, "credit_allowance": 40},
        )
        setup.add(plan)
        setup.commit()
        tx = SubscriptionTransactionDB(
            reference="TF-CONCURRENT", user_id=user.id, plan_id=plan.id,
            amount_pesewas=2200, currency="GHS", status="pending",
            environment="test", payment_method="bank_transfer")
        setup.add(tx)
        setup.commit()
        user_id, tx_id = user.id, tx.id
    finally:
        setup.close()

    payload = {"status": "success", "amount": 2200, "currency": "GHS",
               "reference": "TF-CONCURRENT", "id": 55,
               "channel": "bank_transfer",
               "customer": {"email": user.email}}
    barrier = threading.Barrier(2)

    def run():
        session = Session()
        try:
            row = session.query(SubscriptionTransactionDB).filter_by(id=tx_id).one()
            barrier.wait(timeout=10)
            try:
                paystack.activate_paid_transaction(session, row, dict(payload))
            except Exception:
                session.rollback()
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: run(), range(2)))

    check = Session()
    try:
        balances = check.query(CreditBalanceDB).all()
        assert len(balances) == 1
        assert balances[0].credits_remaining == 40
        assert check.query(UserLicenseDB).count() == 1
        row = check.query(SubscriptionTransactionDB).filter_by(id=tx_id).one()
        assert row.status == "success"
    finally:
        check.close()
        engine.dispose()


class TestRefundLifecycle:
    def _purchase(self, db, monkeypatch):
        user = make_user(db)
        monkeypatch.setattr("requests.request", lambda *a, **k: _Resp(_bank_response()))
        client = _client(db, user)
        ref = client.post("/api/paystack/bank-transfer/charge",
                          json={"plan_slug": "teacher-monthly"}).json()["reference"]
        payload = {"status": "success", "amount": 2200, "currency": "GHS",
                   "reference": ref, "id": 7001, "channel": "bank_transfer",
                   "customer": {"email": user.email}}
        monkeypatch.setattr(paystack, "verify", lambda r: dict(payload))
        _webhook(_client(db), "charge.success", {
            "reference": ref, "id": 7001, "status": "success", "amount": 2200,
            "currency": "GHS", "customer": {"email": user.email}})
        db.expire_all()
        assert credits.status(db, user.id)["package"] == 40
        return user, ref

    @pytest.mark.parametrize("event,status", [
        ("refund.pending", "pending"),
        ("refund.processing", "processing"),
        ("refund.needs-attention", "needs-attention"),
        ("refund.failed", "failed"),
    ])
    def test_non_processed_refund_states_do_not_revoke(self, db, monkeypatch, event, status):
        user, ref = self._purchase(db, monkeypatch)
        r = _webhook(_client(db), event, {
            "id": 9000 + len(status), "status": status,
            "transaction_reference": ref, "refund_reference": "RFD-1",
            "amount": 2200, "currency": "GHS",
            "customer": {"email": user.email}})
        assert r.status_code == 200
        db.expire_all()
        tx = db.query(SubscriptionTransactionDB).filter_by(reference=ref).one()
        assert tx.status == "success"
        assert tx.payment_details["refund_status"] == status
        assert credits.status(db, user.id)["package"] == 40

    def test_processed_refund_reverses_once_and_is_auditable(self, db, monkeypatch):
        user, ref = self._purchase(db, monkeypatch)
        event = {
            "id": 9100, "status": "processed",
            "transaction_reference": ref, "refund_reference": "RFD-2",
            "amount": 2200, "currency": "GHS",
            "customer": {"email": user.email}}
        assert _webhook(_client(db), "refund.processed", event).status_code == 200
        db.expire_all()
        tx = db.query(SubscriptionTransactionDB).filter_by(reference=ref).one()
        assert tx.status == "reversed"
        assert tx.payment_details["refund_status"] == "processed"
        assert credits.status(db, user.id)["package"] == 0
        # A duplicate processed delivery cannot deduct again (balances never
        # go negative) and the event ledger marks it as duplicate.
        dup = _webhook(_client(db), "refund.processed", event)
        assert dup.status_code == 200 and dup.json().get("duplicate") is True
        db.expire_all()
        assert credits.status(db, user.id)["package"] == 0

    @pytest.mark.parametrize("event", [
        "charge.failed", "charge.reversed", "transfer.rejected",
        "transfer.success", "transfer.failed", "transfer.reversed",
    ])
    def test_unsupported_or_outgoing_transfer_events_are_ignored(self, db, monkeypatch, event):
        user, ref = self._purchase(db, monkeypatch)
        r = _webhook(_client(db), event, {
            "id": 9200 + len(event), "status": "failed",
            "reference": ref, "transaction_reference": ref,
            "customer": {"email": user.email}})
        assert r.status_code == 200
        db.expire_all()
        tx = db.query(SubscriptionTransactionDB).filter_by(reference=ref).one()
        assert tx.status == "success"
        assert credits.status(db, user.id)["package"] == 40

    def test_refund_lifecycle_events_have_distinct_idempotency_keys(self):
        pending = paystack.event_key("refund.pending", {
            "transaction_reference": "REF-1", "status": "pending"})
        processing = paystack.event_key("refund.processing", {
            "transaction_reference": "REF-1", "status": "processing"})
        processed = paystack.event_key("refund.processed", {
            "transaction_reference": "REF-1", "status": "processed"})
        assert len({pending, processing, processed}) == 3


class TestFulfilmentRecovery:
    """A successful payment must never stay half-activated."""

    def _successful_flexible(self, db, monkeypatch):
        user = make_user(db)
        # Flexible GHS12 pack is already seeded in the db fixture.
        client = _client(db, user)
        monkeypatch.setattr("requests.request",
                            lambda *a, **k: _Resp(_bank_response()))
        ref = client.post("/api/paystack/bank-transfer/charge",
                          json={"plan_slug": "flexible-credit-pack"}).json()["reference"]
        payload = {
            "status": "success", "amount": 1200, "currency": "GHS",
            "reference": ref, "id": 9301, "channel": "bank_transfer",
            "paid_at": datetime.utcnow().isoformat(),
            "customer": {"email": user.email, "customer_code": "CUS_F"},
            "metadata": {"user_id": user.id},
        }
        monkeypatch.setattr(paystack, "verify", lambda reference: dict(payload))
        hook = {
            "reference": ref, "id": 9301, "status": "success", "amount": 1200,
            "currency": "GHS", "channel": "bank_transfer",
            "customer": {"email": user.email},
        }
        assert _webhook(_client(db), "charge.success", hook).status_code == 200
        db.expire_all()
        return user, ref

    def test_success_with_missing_credit_is_repaired_once(self, db, monkeypatch):
        user, ref = self._successful_flexible(db, monkeypatch)
        db.query(CreditBalanceDB).delete()
        db.query(CreditLedgerDB).delete()
        db.commit()
        tx = db.query(SubscriptionTransactionDB).filter_by(reference=ref).one()
        assert paystack.fulfilment_state(db, tx) == "needs_attention"

        paystack.activate_paid_transaction(db, tx, {})
        db.expire_all()
        assert credits.status(db, user.id)["purchased"] == 20
        assert db.query(CreditBalanceDB).count() == 1

        # Repeat: still exactly one grant.
        tx = db.query(SubscriptionTransactionDB).filter_by(reference=ref).one()
        paystack.activate_paid_transaction(db, tx, {})
        db.expire_all()
        assert db.query(CreditBalanceDB).count() == 1
        assert credits.status(db, user.id)["purchased"] == 20

    def test_success_with_missing_licence_is_repaired_once(self, db, monkeypatch):
        user, ref = self._successful_flexible(db, monkeypatch)
        old = db.query(UserLicenseDB).filter_by(user_id=user.id).one()
        db.delete(old)
        db.commit()
        tx = db.query(SubscriptionTransactionDB).filter_by(reference=ref).one()
        assert paystack.fulfilment_state(db, tx) == "needs_attention"

        _sub, lic = paystack.activate_paid_transaction(db, tx, {})
        db.expire_all()
        licences = db.query(UserLicenseDB).filter_by(user_id=user.id).all()
        assert len(licences) == 1
        assert licences[0].status == "active"
        assert credits.status(db, user.id)["purchased"] == 20

    def test_package_snapshot_is_authoritative_after_catalogue_change(self, db, monkeypatch):
        user = make_user(db)
        client = _client(db, user)
        monkeypatch.setattr("requests.request",
                            lambda *a, **k: _Resp(_bank_response()))
        ref = client.post("/api/paystack/bank-transfer/charge",
                          json={"plan_slug": "flexible-credit-pack"}).json()["reference"]
        tx = db.query(SubscriptionTransactionDB).filter_by(reference=ref).one()
        assert tx.payment_details["package_snapshot"]["credits"] == 20

        plan = db.query(SubscriptionPlanDB).filter_by(
            slug="flexible-credit-pack").one()
        plan.credit_allowance = 999
        db.commit()
        payload = {
            "status": "success", "amount": 1200, "currency": "GHS",
            "reference": ref, "id": 9402, "channel": "bank_transfer",
            "paid_at": datetime.utcnow().isoformat(),
            "customer": {"email": user.email, "customer_code": "CUS_S"},
            "metadata": {"user_id": user.id},
        }
        monkeypatch.setattr(paystack, "verify", lambda reference: dict(payload))
        paystack.activate_paid_transaction(db, tx, payload)
        db.expire_all()
        assert credits.status(db, user.id)["purchased"] == 20
        assert db.query(CreditBalanceDB).one().package_slug == "flexible-credit-pack"

    def test_unknown_reference_webhook_stays_retryable(self, db):
        user = make_user(db)
        r = _webhook(_client(db), "charge.success", {
            "reference": "TFM-UNKNOWN-1", "id": 9401, "status": "success",
            "amount": 1200, "currency": "GHS",
            "customer": {"email": user.email}})
        assert r.status_code == 200
        db.expire_all()
        row = db.query(PaystackWebhookEventDB).filter_by(
            reference="TFM-UNKNOWN-1").one()
        assert row.status in ("failed", "processing", "received")
        assert row.status != "processed"
        assert db.query(UserLicenseDB).count() == 0
        assert db.query(CreditBalanceDB).count() == 0

    def test_purchase_payload_reports_payment_and_activation_separately(self, db, monkeypatch):
        user, ref = self._successful_flexible(db, monkeypatch)
        tx = db.query(SubscriptionTransactionDB).filter_by(reference=ref).one()
        payload = paystack.purchase_payload(db, tx)
        assert payload["payment_status"] == "success"
        assert payload["fulfilment_status"] == "activated"
        assert payload["package"]["name"] == "Flexible Credit Pack"
        assert payload["package"]["credits"] == 20
        assert payload["credits_granted"] == 20
        assert payload["credit_balance"]["total"] >= 20
        assert payload["licence"]["status"] == "active"

    def test_notifications_are_idempotent_and_recorded(self, db, monkeypatch):
        from src import email_service
        from src.config import get_settings
        monkeypatch.setenv("OWNER_ALERT_EMAIL", "owner@t.test")
        get_settings.cache_clear()

        sent = []

        class FakeEmail:
            def send_subscription_notification(self, **kwargs):
                sent.append(("customer", kwargs))
                return email_service.EmailResult(success=True, provider_id="cus-1")

            def send_owner_purchase(self, **kwargs):
                sent.append(("owner", kwargs))
                return email_service.EmailResult(success=True, provider_id="own-1")

        monkeypatch.setattr(email_service, "get_email", lambda: FakeEmail())
        user, ref = self._successful_flexible(db, monkeypatch)
        tx = db.query(SubscriptionTransactionDB).filter_by(reference=ref).one()
        notes = tx.payment_details["notifications"]
        assert notes["customer"]["status"] == "sent"
        assert notes["owner"]["status"] == "sent"
        assert [kind for kind, _ in sent] == ["owner", "customer"]

        # Re-running activation must not send again.
        paystack.activate_paid_transaction(db, tx, {})
        assert [kind for kind, _ in sent] == ["owner", "customer"]

    def test_notification_failure_does_not_undo_purchase(self, db, monkeypatch):
        from src import email_service
        from src.config import get_settings
        monkeypatch.setenv("OWNER_ALERT_EMAIL", "owner@t.test")
        get_settings.cache_clear()

        class FailingEmail:
            def send_subscription_notification(self, **kwargs):
                return email_service.EmailResult(success=False, message="provider down")

            def send_owner_purchase(self, **kwargs):
                return email_service.EmailResult(success=False, message="provider down")

        monkeypatch.setattr(email_service, "get_email", lambda: FailingEmail())
        user, ref = self._successful_flexible(db, monkeypatch)
        tx = db.query(SubscriptionTransactionDB).filter_by(reference=ref).one()
        assert tx.status == "success"
        assert credits.status(db, user.id)["purchased"] == 20
        notes = tx.payment_details["notifications"]
        assert notes["customer"]["status"] == "failed"
        assert notes["owner"]["status"] == "failed"


class TestAdminPurchaseVisibility:
    def test_admin_list_shows_fulfilment_and_notifications(self, db, monkeypatch):
        import asyncio
        from src.routers import platform_admin as admin_router

        user, ref = TestFulfilmentRecovery()._successful_flexible(db, monkeypatch)
        admin = make_user(db, role="platform_admin")
        result = asyncio.run(admin_router.list_paystack_purchases(
            status=None, fulfilment=None, user=admin, db=db))
        row = next(p for p in result["purchases"] if p["reference"] == ref)
        assert row["payment_status"] == "success"
        assert row["fulfilment_status"] == "activated"
        assert row["licence_issued"] is True
        assert row["credits_granted"] == 20
        assert "customer" in row["notifications"]

    def test_admin_reconcile_repairs_once_and_is_auditable(self, db, monkeypatch):
        import asyncio
        from src.routers import platform_admin as admin_router
        from src.database import PlatformAuditLogDB

        user, ref = TestFulfilmentRecovery()._successful_flexible(db, monkeypatch)
        db.query(CreditBalanceDB).delete()
        db.query(CreditLedgerDB).delete()
        db.commit()
        admin = make_user(db, role="platform_admin")
        result = asyncio.run(admin_router.reconcile_paystack_purchase(
            ref, admin_router.ReconcilePurchaseRequest(
                reason="Verified live Paystack success; credits missing"),
            user=admin, db=db))
        assert result["before"]["fulfilment_status"] == "needs_attention"
        assert result["purchase"]["fulfilment_status"] == "activated"
        assert credits.status(db, user.id)["purchased"] == 20
        db.expire_all()
        logs = db.query(PlatformAuditLogDB).filter_by(
            action="paystack_purchase_reconciled").all()
        assert logs
        # Repeat is safe: no second credit bucket.
        asyncio.run(admin_router.reconcile_paystack_purchase(
            ref, admin_router.ReconcilePurchaseRequest(
                reason="Repeat reconciliation should be idempotent"),
            user=admin, db=db))
        db.expire_all()
        assert db.query(CreditBalanceDB).count() == 1
        assert credits.status(db, user.id)["purchased"] == 20


class TestLicenceRedemption:
    def _licence(self, db, user):
        return db.query(UserLicenseDB).filter_by(user_id=user.id).one()

    def test_same_account_key_is_idempotent(self, db, monkeypatch):
        user, ref = TestFulfilmentRecovery()._successful_flexible(db, monkeypatch)
        lic = self._licence(db, user)
        r = _client(db, user).post("/api/paystack/licence/redeem",
                                   json={"key": lic.licence_key})
        assert r.status_code == 200
        assert r.json()["already_active"] is True
        assert r.json()["licence"]["key"] == lic.licence_key

    def test_another_account_key_is_refused(self, db, monkeypatch):
        user, ref = TestFulfilmentRecovery()._successful_flexible(db, monkeypatch)
        other = make_user(db, email="licence-other@t.test")
        lic = self._licence(db, user)
        r = _client(db, other).post("/api/paystack/licence/redeem",
                                    json={"key": lic.licence_key})
        assert r.status_code == 409
        assert "another account" in r.json()["detail"]
        db.expire_all()
        assert self._licence(db, user).user_id == user.id

    def test_invalid_and_expired_keys_are_clear(self, db):
        user = make_user(db)
        client = _client(db, user)
        assert client.post("/api/paystack/licence/redeem",
                           json={"key": "TF-NOT-A-KEY"}).status_code == 404

        plan = db.query(SubscriptionPlanDB).filter_by(
            slug="flexible-credit-pack").one()
        lic = UserLicenseDB(
            id="lic-expired", user_id=user.id, plan_id=plan.id,
            licence_key="TF-EXPIRED-KEY", key_hash=paystack._hash_key("TF-EXPIRED-KEY"),
            status="expired")
        db.add(lic)
        db.commit()
        r = client.post("/api/paystack/licence/redeem",
                        json={"key": "TF-EXPIRED-KEY"})
        assert r.status_code == 409
        assert "expired" in r.json()["detail"]

