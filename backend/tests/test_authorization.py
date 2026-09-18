"""
Tests for authorization enforcement.

Tests that role checks work correctly at the database/model level.
"""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.database import User, Base, generate_id
from src.auth import hash_password, verify_password, create_access_token, decode_token
from tests.conftest import make_user


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


class TestRoleChecks:
    """Test the role check logic that would be used in authorization dependencies."""

    def test_is_platform_admin(self, db):
        user = make_user(db, role="platform_admin")
        assert user.role == "platform_admin"

    def test_is_school_admin(self, db):
        user = make_user(db, role="school_admin")
        assert user.role == "school_admin"

    def test_is_teacher(self, db):
        user = make_user(db, role="teacher")
        assert user.role == "teacher"

    def test_require_platform_admin_check(self, db):
        """Simulate require_platform_admin: user.role == 'platform_admin'"""
        platform_admin = make_user(db, role="platform_admin")
        school_admin = make_user(db, role="school_admin")
        teacher = make_user(db, role="teacher")

        # Platform admin passes
        assert platform_admin.role == "platform_admin"
        # School admin fails
        assert school_admin.role != "platform_admin"
        # Teacher fails
        assert teacher.role != "platform_admin"

    def test_require_school_admin_check(self, db):
        """Simulate require_admin: user.is_admin or user.role == 'school_admin'"""
        platform_admin = make_user(db, role="platform_admin")
        school_admin = make_user(db, role="school_admin", is_admin=True)
        legacy_admin = make_user(db, role="teacher", is_admin=True)
        teacher = make_user(db, role="teacher")

        # School admin passes (via role or is_admin)
        assert school_admin.role == "school_admin" or school_admin.is_admin
        # Legacy admin passes (via is_admin)
        assert legacy_admin.is_admin
        # Platform admin: role is platform_admin, not school_admin
        # In actual code: require_admin checks is_admin or role=="school_admin"
        # platform_admin has is_admin=False, role="platform_admin"
        # So platform_admin does NOT pass require_admin (unless is_admin is also set)
        # This is by design - platform admin uses separate endpoint
        # Teacher fails
        assert not teacher.is_admin
        assert teacher.role != "school_admin"


class TestSchoolMembership:
    def test_user_has_school_id(self, db):
        from tests.conftest import make_school
        school = make_school(db)
        user = make_user(db, role="teacher", school_id=school.id)
        assert user.school_id == school.id

    def test_user_without_school(self, db):
        user = make_user(db, role="platform_admin")
        assert user.school_id is None

    def test_different_users_different_schools(self, db):
        from tests.conftest import make_school
        school_a = make_school(db, code="A")
        school_b = make_school(db, code="B")

        user_a = make_user(db, role="teacher", school_id=school_a.id)
        user_b = make_user(db, role="teacher", school_id=school_b.id)

        assert user_a.school_id != user_b.school_id


class TestJWTTokenContents:
    def test_token_contains_user_id(self, db):
        user = make_user(db, role="teacher")
        token = create_access_token({"sub": user.id, "email": user.email})
        payload = decode_token(token)
        assert payload["sub"] == user.id

    def test_token_contains_email(self, db):
        user = make_user(db, role="teacher")
        token = create_access_token({"sub": user.id, "email": user.email})
        payload = decode_token(token)
        assert payload["email"] == user.email

    def test_token_does_not_contain_role(self, db):
        """Role should be checked from DB, not from token."""
        user = make_user(db, role="platform_admin")
        token = create_access_token({"sub": user.id, "email": user.email})
        payload = decode_token(token)
        assert "role" not in payload  # Role is not in the token


class TestMigration:
    def test_migrate_admin_to_school_admin(self, db):
        """Simulate migration: is_admin=True users get role='school_admin'."""
        # Create legacy admin
        user = User(
            id=generate_id(),
            email="legacy@test.com",
            full_name="Legacy Admin",
            hashed_password=hash_password("pass"),
            is_admin=True,
            role="teacher",  # Default before migration
        )
        db.add(user)
        db.commit()

        # Simulate migration
        db.execute(text("UPDATE users SET role = 'school_admin' WHERE is_admin = 1 AND role = 'teacher'"))
        db.commit()

        db.refresh(user)
        assert user.role == "school_admin"
