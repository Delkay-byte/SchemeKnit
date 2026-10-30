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
    Base, CreditBalanceDB, EntitlementDB, ReferralDB, SubscriptionPlanDB,
    SubscriptionTransactionDB, UserLicenseDB, get_db,
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
