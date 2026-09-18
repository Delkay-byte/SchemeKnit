"""
SchemeKnit Test Configuration

Sets up in-memory SQLite test database and provides fixtures
for all test modules.
"""

import os
import sys
import pytest
from datetime import datetime, date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure backend src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database import Base, generate_id
from src.auth import hash_password, create_access_token


def _test_database_url():
    """Clean DATABASE_URL override: set TEACHFLOW_TEST_DATABASE_URL to run the
    same suite against PostgreSQL (or any SQLAlchemy URL). Defaults to SQLite."""
    return os.environ.get("TEACHFLOW_TEST_DATABASE_URL") or "sqlite:///:memory:"


@pytest.fixture(scope="function")
def db_engine():
    """Create a fresh database for each test (SQLite memory by default)."""
    url = _test_database_url()
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db(db_engine):
    """Create a fresh database session for each test."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


def make_user(db, role="teacher", school_id=None, is_admin=False, email=None):
    """Helper to create a test user."""
    from src.database import User
    user = User(
        id=generate_id(),
        email=email or f"{role}_{generate_id()[:8]}@test.com",
        full_name=f"Test {role.title()}",
        hashed_password=hash_password("testpass123"),
        school_name="Test School",
        is_active=True,
        is_admin=is_admin,
        role=role,
        school_id=school_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def make_school(db, name="Test School", code=None):
    """Helper to create a test school."""
    from src.database import SchoolDB
    school = SchoolDB(
        id=generate_id(),
        name=name,
        school_code=code or f"SCH-{generate_id()[:8]}",
        contact_name="Test Contact",
        contact_phone="0551234567",
        contact_email="contact@test.com",
        status="active",
    )
    db.add(school)
    db.commit()
    db.refresh(school)
    return school


def make_product_plan(db, name="Test Plan", price=800.0, seat_limit=20, duration_days=365):
    """Helper to create a test product plan."""
    from src.database import ProductPlanDB
    plan = ProductPlanDB(
        id=generate_id(),
        name=name,
        description="Test plan description",
        product_type="school",
        price=price,
        currency="GHS",
        duration_days=duration_days,
        seat_limit=seat_limit,
        features=["multi_teacher", "admin_dashboard"],
        active=True,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def make_license(db, school_id, product_plan_id, seat_limit=20, status="active"):
    """Helper to create a test school license."""
    from src.database import SchoolLicenseDB
    today = date.today()
    lic = SchoolLicenseDB(
        id=generate_id(),
        school_id=school_id,
        product_plan_id=product_plan_id,
        license_code=f"TF-LIC-{generate_id()[:8]}",
        status=status,
        start_date=today,
        expiry_date=today + timedelta(days=365),
        seat_limit=seat_limit,
    )
    db.add(lic)
    db.commit()
    db.refresh(lic)
    return lic


def make_entitled_teacher(db, email=None, license_status="active", role="teacher"):
    """A teacher in a school that holds a license -> commercially AI-entitled.

    AI requires entitlement (an active school license or a paid entitlement
    row), so AI tests must set one up. Returns (user, school, license).
    """
    school = make_school(db)
    plan = make_product_plan(db)
    lic = make_license(db, school.id, plan.id, status=license_status)
    user = make_user(db, role=role, school_id=school.id, email=email)
    return user, school, lic


def make_paid_entitlement(db, user_id, ai_enabled=True, expires_at=None):
    """Grant a paid AI entitlement row directly (no school required)."""
    from src.database import EntitlementDB
    ent = EntitlementDB(
        id=generate_id(),
        user_id=user_id,
        edition="teacher_pro",
        features=["ai_basic"],
        ai_enabled=ai_enabled,
        advanced_ai_enabled=False,
        expires_at=expires_at,
    )
    db.add(ent)
    db.commit()
    db.refresh(ent)
    return ent


def make_activation_code(db, license_id, status="active"):
    """Helper to create a test activation code."""
    from src.database import ActivationCodeDB
    code = ActivationCodeDB(
        id=generate_id(),
        license_id=license_id,
        code=f"TF-SCH-{generate_id()[:4]}-{generate_id()[:4]}-{generate_id()[:4]}",
        status=status,
        expires_at=datetime.utcnow() + timedelta(days=30),
    )
    db.add(code)
    db.commit()
    db.refresh(code)
    return code


def make_payment(db, user_id, amount=800.0, status="pending"):
    """Helper to create a test payment."""
    from src.database import PaymentDB
    payment = PaymentDB(
        id=generate_id(),
        user_id=user_id,
        payment_method="mtn_momo",
        amount=amount,
        currency="GHS",
        product_type="school_license",
        product_id="",
        product_name="Test License",
        reference="REF-123",
        payer_name="Test Payer",
        payer_phone="0551234567",
        status=status,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


def get_token(user):
    """Generate a JWT token for a test user.

    Uses the legacy (no-pwv) format so existing tests are unaffected by the
    session-invalidation check. New auth-lifecycle tests call create_user_token
    directly to exercise the pwv flow.
    """
    from src.auth import create_access_token
    return create_access_token({"sub": user.id, "email": user.email})
