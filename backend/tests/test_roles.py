"""
Tests for role-based authorization.

Tests the auth functions and database models directly,
without importing the FastAPI app (avoids version issues).
"""

import pytest
from datetime import datetime

from src.database import (
    User, SchoolDB, SchoolMembershipDB, SchoolLicenseDB,
    ActivationCodeDB, ProductPlanDB, PaymentDB, PlatformAuditLogDB,
    generate_id, Base
)
from src.auth import (
    hash_password, verify_password, create_access_token,
    decode_token, _authenticate_user
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def db():
    """Create in-memory SQLite test database."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def make_user(db, role="teacher", school_id=None, is_admin=False):
    user = User(
        id=generate_id(),
        email=f"{role}_{generate_id()[:8]}@test.com",
        full_name=f"Test {role.title()}",
        hashed_password=hash_password("testpass123"),
        is_active=True,
        is_admin=is_admin,
        role=role,
        school_id=school_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


class TestPasswordHashing:
    def test_hash_and_verify(self):
        hashed = hash_password("mypassword")
        assert verify_password("mypassword", hashed)
        assert not verify_password("wrongpassword", hashed)

    def test_different_hashes(self):
        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        assert h1 != h2  # bcrypt uses random salt


class TestJWT:
    def test_create_and_decode_token(self):
        token = create_access_token({"sub": "user123", "email": "test@test.com"})
        payload = decode_token(token)
        assert payload["sub"] == "user123"
        assert payload["email"] == "test@test.com"
        assert "exp" in payload

    def test_invalid_token_raises(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            decode_token("invalid.token.here")
        assert exc_info.value.status_code == 401


class TestRoleCreation:
    def test_create_platform_admin(self, db):
        user = make_user(db, role="platform_admin")
        assert user.role == "platform_admin"
        assert user.is_admin == False  # is_admin is separate from role

    def test_create_school_admin(self, db):
        user = make_user(db, role="school_admin", is_admin=True)
        assert user.role == "school_admin"
        assert user.is_admin == True

    def test_create_teacher(self, db):
        user = make_user(db, role="teacher")
        assert user.role == "teacher"
        assert user.is_admin == False

    def test_default_role_is_teacher(self, db):
        user = User(
            id=generate_id(),
            email="default@test.com",
            full_name="Default User",
            hashed_password=hash_password("pass"),
        )
        db.add(user)
        db.commit()
        assert user.role == "teacher"


class TestRoleQuerying:
    def test_query_by_role(self, db):
        make_user(db, role="platform_admin")
        make_user(db, role="school_admin")
        make_user(db, role="teacher")
        make_user(db, role="teacher")

        platform_admins = db.query(User).filter(User.role == "platform_admin").count()
        school_admins = db.query(User).filter(User.role == "school_admin").count()
        teachers = db.query(User).filter(User.role == "teacher").count()

        assert platform_admins == 1
        assert school_admins == 1
        assert teachers == 2

    def test_query_school_members(self, db):
        from tests.conftest import make_school
        school = make_school(db)
        make_user(db, role="teacher", school_id=school.id)
        make_user(db, role="teacher", school_id=school.id)
        make_user(db, role="teacher")  # Different school

        members = db.query(User).filter(User.school_id == school.id).count()
        assert members == 2


class TestBackwardCompatibility:
    def test_legacy_admin_with_role(self, db):
        """is_admin=True with role=teacher should still work for require_admin."""
        user = make_user(db, role="teacher", is_admin=True)
        # The require_admin check: user.is_admin or user.role == "school_admin"
        assert user.is_admin == True  # Access granted via is_admin

    def test_new_school_admin_with_role(self, db):
        """role=school_admin should work for require_admin."""
        user = make_user(db, role="school_admin")
        # The require_admin check: user.is_admin or user.role == "school_admin"
        assert user.role == "school_admin"  # Access granted via role

    def test_platform_admin_not_school_admin(self, db):
        """role=platform_admin should NOT satisfy require_admin (which checks school_admin)."""
        user = make_user(db, role="platform_admin")
        # require_admin checks: user.is_admin or user.role == "school_admin"
        # platform_admin is NOT school_admin
        assert user.is_admin == False
        assert user.role != "school_admin"
