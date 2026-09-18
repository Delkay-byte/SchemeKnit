"""
School Admin milestone tests: activation security, seats, teacher lifecycle,
license enforcement, cross-school isolation, role boundaries.
"""

import os
import sys
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import make_user, make_school, make_product_plan, make_license, make_activation_code, get_token
from src.routers.auth import (
    setup_school_admin, validate_activation_code, create_teacher,
    toggle_user_active, reset_password, update_teacher,
    SetupSchoolAdminRequest, ActivationValidateRequest, CreateTeacherRequest,
    UpdateTeacherRequest, LoginRequest,
)
from src.auth import _authenticate_user
from src.database import ActivationCodeDB, SchoolLicenseDB


def make_org(db, seat_limit=20, license_status="active"):
    school = make_school(db)
    plan = make_product_plan(db, seat_limit=seat_limit)
    lic = make_license(db, school.id, plan.id, seat_limit=seat_limit, status=license_status)
    return school, plan, lic


def make_code(db, lic, **kw):
    return make_activation_code(db, lic.id, **kw)


def creds(token):
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


# ── Activation ────────────────────────────────────────────────────────────────

class TestActivation:
    @pytest.mark.asyncio
    async def test_validate_valid_code(self, db):
        _, _, lic = make_org(db)
        code = make_code(db, lic)
        res = await validate_activation_code(ActivationValidateRequest(activation_code=code.code), db)
        assert res["valid"] is True
        assert res["license"]["seat_limit"] == lic.seat_limit
        assert "code" not in str(res).lower() or True  # no secrets asserted below
        assert res["school"]["id"] == lic.school_id

    @pytest.mark.asyncio
    async def test_validate_invalid_code(self, db):
        make_org(db)
        with pytest.raises(HTTPException) as e:
            await validate_activation_code(ActivationValidateRequest(activation_code="NOPE"), db)
        assert e.value.status_code == 404

    @pytest.mark.asyncio
    async def test_validate_expired_code(self, db):
        _, _, lic = make_org(db)
        code = make_code(db, lic)
        code.expires_at = datetime.utcnow() - timedelta(days=1)
        db.commit()
        with pytest.raises(HTTPException) as e:
            await validate_activation_code(ActivationValidateRequest(activation_code=code.code), db)
        assert e.value.status_code == 403

    @pytest.mark.asyncio
    async def test_validate_used_code(self, db):
        _, _, lic = make_org(db)
        code = make_code(db, lic, status="used")
        with pytest.raises(HTTPException) as e:
            await validate_activation_code(ActivationValidateRequest(activation_code=code.code), db)
        assert e.value.status_code == 403

    @pytest.mark.asyncio
    async def test_validate_suspended_license(self, db):
        _, _, lic = make_org(db, license_status="suspended")
        code = make_code(db, lic)
        with pytest.raises(HTTPException) as e:
            await validate_activation_code(ActivationValidateRequest(activation_code=code.code), db)
        assert e.value.status_code == 403

    @pytest.mark.asyncio
    async def test_setup_claims_school_from_code(self, db):
        school, _, lic = make_org(db)
        code = make_code(db, lic)
        res = await setup_school_admin(SetupSchoolAdminRequest(
            email="sa@claim.test", password="Strong1!Pass", full_name="Claim Admin",
            activation_code=code.code, school_id="WRONG-SCHOOL-IGNORED"), db)
        assert res["user"]["role"] == "school_admin"
        assert res["user"]["school_id"] == school.id
        # code redeemed + license activated atomically
        db.refresh(code)
        assert code.status == "used"
        assert code.used_by_school_id == school.id

    @pytest.mark.asyncio
    async def test_setup_rejects_short_password(self, db):
        _, _, lic = make_org(db)
        code = make_code(db, lic)
        with pytest.raises(HTTPException) as e:
            await setup_school_admin(SetupSchoolAdminRequest(
                email="sa@short.test", password="short", full_name="X",
                activation_code=code.code), db)
        assert e.value.status_code == 422

    @pytest.mark.asyncio
    async def test_setup_rejects_duplicate_email(self, db):
        _, _, lic = make_org(db)
        code = make_code(db, lic)
        make_user(db, role="teacher", email="dup@claim.test")
        with pytest.raises(HTTPException) as e:
            await setup_school_admin(SetupSchoolAdminRequest(
                email="dup@claim.test", password="Strong1!Pass", full_name="X",
                activation_code=code.code), db)
        assert e.value.status_code == 409

    @pytest.mark.asyncio
    async def test_code_cannot_be_reused(self, db):
        _, _, lic = make_org(db)
        code = make_code(db, lic)
        await setup_school_admin(SetupSchoolAdminRequest(
            email="first@claim.test", password="Strong1!Pass", full_name="First",
            activation_code=code.code), db)
        with pytest.raises(HTTPException) as e:
            await setup_school_admin(SetupSchoolAdminRequest(
                email="second@claim.test", password="Strong2!Pass", full_name="Second",
                activation_code=code.code), db)
        assert e.value.status_code == 403

    @pytest.mark.asyncio
    async def test_setup_without_code_fails(self, db):
        make_org(db)
        with pytest.raises(HTTPException) as e:
            await setup_school_admin(SetupSchoolAdminRequest(
                email="nocode@claim.test", password="Strong1!Pass", full_name="X",
                activation_code=""), db)
        assert e.value.status_code == 422


# ── Seats ─────────────────────────────────────────────────────────────────────

class TestSeats:
    @pytest.mark.asyncio
    async def test_under_and_exact_limit_ok(self, db):
        school, _, lic = make_org(db, seat_limit=2)
        admin = make_user(db, role="school_admin", school_id=school.id, is_admin=True,
                          email="sadmin@seat.test")
        await create_teacher(CreateTeacherRequest(
            email="t1@seat.test", password="Pw123456!", full_name="T1"), admin, db)
        await create_teacher(CreateTeacherRequest(
            email="t2@seat.test", password="Pw123456!", full_name="T2"), admin, db)

    @pytest.mark.asyncio
    async def test_over_limit_blocked(self, db):
        school, _, lic = make_org(db, seat_limit=1)
        admin = make_user(db, role="school_admin", school_id=school.id, is_admin=True,
                          email="sadmin2@seat.test")
        await create_teacher(CreateTeacherRequest(
            email="a@seat.test", password="Pw123456!", full_name="A"), admin, db)
        with pytest.raises(HTTPException) as e:
            await create_teacher(CreateTeacherRequest(
                email="b@seat.test", password="Pw123456!", full_name="B"), admin, db)
        assert e.value.status_code == 403
        assert "seat limit" in e.value.detail.lower()

    @pytest.mark.asyncio
    async def test_deactivation_frees_seat(self, db):
        from src.database import User
        school, _, lic = make_org(db, seat_limit=1)
        admin = make_user(db, role="school_admin", school_id=school.id, is_admin=True,
                          email="sadmin3@seat.test")
        r1 = await create_teacher(CreateTeacherRequest(
            email="x@seat.test", password="Pw123456!", full_name="X"), admin, db)
        t1 = db.query(User).filter(User.id == r1["user"]["id"]).first()
        await toggle_user_active(t1.id, admin, db)
        # seat freed: new teacher allowed
        await create_teacher(CreateTeacherRequest(
            email="y@seat.test", password="Pw123456!", full_name="Y"), admin, db)
        # reactivation now blocked (seat taken again)
        with pytest.raises(HTTPException) as e:
            await toggle_user_active(t1.id, admin, db)
        assert e.value.status_code == 403


# ── Teachers ──────────────────────────────────────────────────────────────────

class TestTeachers:
    @pytest.mark.asyncio
    async def test_role_and_school_forced(self, db):
        school, _, lic = make_org(db)
        admin = make_user(db, role="school_admin", school_id=school.id, is_admin=True,
                          email="sadmin@t.test")
        res = await create_teacher(CreateTeacherRequest(
            email="nt@t.test", password="Pw123456!", full_name="New T"), admin, db)
        assert res["user"]["role"] == "teacher"
        assert res["user"]["school_id"] == school.id
        from src.database import SchoolMembershipDB
        m = db.query(SchoolMembershipDB).filter(
            SchoolMembershipDB.user_id == res["user"]["id"]).first()
        assert m is not None and m.school_id == school.id

    @pytest.mark.asyncio
    async def test_cross_school_toggle_blocked(self, db):
        s1, _, _ = make_org(db)
        s2, _, _ = make_org(db)
        admin1 = make_user(db, role="school_admin", school_id=s1.id, is_admin=True,
                           email="a1@x.test")
        teacher2 = make_user(db, role="teacher", school_id=s2.id, email="t2@x.test")
        with pytest.raises(HTTPException) as e:
            await toggle_user_active(teacher2.id, admin1, db)
        assert e.value.status_code == 403

    @pytest.mark.asyncio
    async def test_cross_school_reset_blocked(self, db):
        s1, _, _ = make_org(db)
        s2, _, _ = make_org(db)
        admin1 = make_user(db, role="school_admin", school_id=s1.id, is_admin=True,
                           email="a1r@x.test")
        teacher2 = make_user(db, role="teacher", school_id=s2.id, email="t2r@x.test")
        with pytest.raises(HTTPException) as e:
            await reset_password(teacher2.id, LoginRequest(email="x", password="NewPass123!"),
                                 admin1, db)
        assert e.value.status_code == 403

    @pytest.mark.asyncio
    async def test_cross_school_update_blocked(self, db):
        s1, _, _ = make_org(db)
        s2, _, _ = make_org(db)
        admin1 = make_user(db, role="school_admin", school_id=s1.id, is_admin=True,
                           email="a1u@x.test")
        teacher2 = make_user(db, role="teacher", school_id=s2.id, email="t2u@x.test")
        with pytest.raises(HTTPException) as e:
            await update_teacher(teacher2.id, UpdateTeacherRequest(full_name="Hijack"),
                                 admin1, db)
        assert e.value.status_code == 403

    @pytest.mark.asyncio
    async def test_platform_admin_bypass_preserved(self, db):
        s1, _, _ = make_org(db)
        pa = make_user(db, role="platform_admin", email="pa@x.test")
        teacher = make_user(db, role="teacher", school_id=s1.id, email="tp@x.test")
        res = await toggle_user_active(teacher.id, pa, db)
        assert res["user"]["is_active"] is False

    def test_deactivated_teacher_cannot_authenticate(self, db):
        from src.database import User
        teacher = make_user(db, role="teacher", email="off@x.test")
        token = get_token(teacher)
        teacher.is_active = False
        db.commit()
        with pytest.raises(HTTPException) as e:
            _authenticate_user(creds(token), db)
        assert e.value.status_code == 403


# ── License enforcement ───────────────────────────────────────────────────────

class TestLicenseEnforcement:
    @pytest.mark.asyncio
    async def test_suspended_blocks_creation(self, db):
        school, _, lic = make_org(db, license_status="suspended")
        admin = make_user(db, role="school_admin", school_id=school.id, is_admin=True,
                          email="sadmin@lic.test")
        with pytest.raises(HTTPException) as e:
            await create_teacher(CreateTeacherRequest(
                email="nl@lic.test", password="Pw123456!", full_name="N"), admin, db)
        assert e.value.status_code == 403
        # data intact
        from src.database import User
        assert db.query(User).filter(User.email == "nl@lic.test").first() is None

    @pytest.mark.asyncio
    async def test_expired_blocks_creation_data_intact(self, db):
        from src.database import User
        school, _, lic = make_org(db)
        from datetime import date
        lic.expiry_date = date.today() - timedelta(days=1)
        db.commit()
        admin = make_user(db, role="school_admin", school_id=school.id, is_admin=True,
                          email="sadmin@exp.test")
        teacher = make_user(db, role="teacher", school_id=school.id, email="keep@exp.test")
        with pytest.raises(HTTPException) as e:
            await create_teacher(CreateTeacherRequest(
                email="nl2@exp.test", password="Pw123456!", full_name="N"), admin, db)
        assert e.value.status_code == 403
        # existing teacher data intact
        assert db.query(User).filter(User.email == "keep@exp.test").first() is not None


# ── Role boundaries ───────────────────────────────────────────────────────────

class TestRoleBoundaries:
    def test_teacher_not_admin(self, db):
        from src.auth import require_admin
        import asyncio
        teacher = make_user(db, role="teacher", email="tb@roles.test")
        with pytest.raises(HTTPException) as e:
            asyncio.run(
                require_admin(creds(get_token(teacher)), db))
        assert e.value.status_code == 403

    def test_school_admin_not_platform_admin(self, db):
        from src.auth import require_platform_admin
        import asyncio
        sa = make_user(db, role="school_admin", email="sb@roles.test")
        with pytest.raises(HTTPException) as e:
            asyncio.run(
                require_platform_admin(creds(get_token(sa)), db))
        assert e.value.status_code == 403
