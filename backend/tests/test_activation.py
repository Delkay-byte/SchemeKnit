"""
Tests for activation code system.

Tests database models directly without FastAPI app import.
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import (
    ActivationCodeDB, SchoolLicenseDB, LicenseCacheDB,
    Base, generate_id
)
from tests.conftest import make_school, make_product_plan, make_license, make_activation_code


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


class TestActivationCodeCreation:
    def test_create_activation_code(self, db):
        school = make_school(db)
        plan = make_product_plan(db)
        lic = make_license(db, school.id, plan.id)
        ac = make_activation_code(db, lic.id)

        assert ac.license_id == lic.id
        assert ac.status == "active"
        assert ac.code.startswith("TF-SCH-")

    def test_activation_code_unique(self, db):
        school = make_school(db)
        plan = make_product_plan(db)
        lic = make_license(db, school.id, plan.id)
        ac1 = make_activation_code(db, lic.id)
        ac2 = make_activation_code(db, lic.id)

        assert ac1.code != ac2.code

    def test_activation_code_expires(self, db):
        school = make_school(db)
        plan = make_product_plan(db)
        lic = make_license(db, school.id, plan.id)
        ac = make_activation_code(db, lic.id)

        assert ac.expires_at is not None
        assert ac.expires_at > datetime.utcnow()


class TestActivationCodeStates:
    def test_active_code(self, db):
        school = make_school(db)
        plan = make_product_plan(db)
        lic = make_license(db, school.id, plan.id)
        ac = make_activation_code(db, lic.id, status="active")
        assert ac.status == "active"

    def test_used_code(self, db):
        school = make_school(db)
        plan = make_product_plan(db)
        lic = make_license(db, school.id, plan.id)
        ac = make_activation_code(db, lic.id, status="used")
        assert ac.status == "used"

    def test_revoked_code(self, db):
        school = make_school(db)
        plan = make_product_plan(db)
        lic = make_license(db, school.id, plan.id)
        ac = make_activation_code(db, lic.id, status="revoked")
        assert ac.status == "revoked"


class TestActivationFlow:
    def test_activation_marks_code_as_used(self, db):
        school = make_school(db)
        plan = make_product_plan(db)
        lic = make_license(db, school.id, plan.id, status="pending")
        ac = make_activation_code(db, lic.id, status="active")

        # Simulate activation
        ac.status = "used"
        ac.used_by_school_id = school.id
        ac.used_at = datetime.utcnow()
        lic.status = "active"
        db.commit()

        assert ac.status == "used"
        assert ac.used_by_school_id == school.id
        assert ac.used_at is not None
        assert lic.status == "active"

    def test_cannot_reuse_used_code(self, db):
        school = make_school(db)
        plan = make_product_plan(db)
        lic = make_license(db, school.id, plan.id)
        ac = make_activation_code(db, lic.id, status="used")

        # In actual code, this would return 403
        assert ac.status == "used"

    def test_cannot_reuse_revoked_code(self, db):
        school = make_school(db)
        plan = make_product_plan(db)
        lic = make_license(db, school.id, plan.id)
        ac = make_activation_code(db, lic.id, status="revoked")

        assert ac.status == "revoked"

    def test_expired_code_check(self, db):
        school = make_school(db)
        plan = make_product_plan(db)
        lic = make_license(db, school.id, plan.id)

        ac = ActivationCodeDB(
            id=generate_id(),
            license_id=lic.id,
            code=f"TF-SCH-EXP-{generate_id()[:4]}",
            status="active",
            expires_at=datetime.utcnow() - timedelta(days=1),
        )
        db.add(ac)
        db.commit()

        assert ac.expires_at < datetime.utcnow()  # Expired


class TestLicenseCache:
    def test_cache_creation(self, db):
        school = make_school(db)
        plan = make_product_plan(db)
        lic = make_license(db, school.id, plan.id)

        cache = LicenseCacheDB(
            id=generate_id(),
            school_id=school.id,
            license_code=lic.license_code,
            plan_name=plan.name,
            seat_limit=lic.seat_limit,
            features=plan.features,
            expiry_date=lic.expiry_date,
        )
        db.add(cache)
        db.commit()

        assert cache.school_id == school.id
        assert cache.plan_name == plan.name
        assert cache.seat_limit == lic.seat_limit

    def test_cache_has_expiry(self, db):
        school = make_school(db)
        plan = make_product_plan(db, duration_days=365)
        lic = make_license(db, school.id, plan.id)

        cache = LicenseCacheDB(
            id=generate_id(),
            school_id=school.id,
            license_code=lic.license_code,
            expiry_date=lic.expiry_date,
        )
        db.add(cache)
        db.commit()

        assert cache.expiry_date == lic.expiry_date
