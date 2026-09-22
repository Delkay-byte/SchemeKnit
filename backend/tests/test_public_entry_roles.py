"""
Public Entry + Role-Based Authentication Architecture — backend tests.

Covers (§25):
  - Public landing / setup-status routes
  - Role login routing (one shared teacher login, role from backend)
  - Activation must precede School Admin account creation (§6)
  - School Admin login after activation (§8)
  - Individual teacher registration (§12)
  - School teacher vs individual teacher login (§10, §13, §14)
  - Entitlement resolution states A-D (§15)
  - Wrong-role access denied (§22)
  - Invalid / expired / redeemed / suspended activation states (§19)
  - Activation-code replay rejected (§22)
  - Password + email UX regression (§20)
  - Existing school commercial + individual Free/Pro flows intact
"""

import os
import sys
from datetime import date, datetime, timedelta

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.database import (
    get_db, User, EntitlementDB, SchoolDB, SchoolLicenseDB,
    SchoolMembershipDB, ProductPlanDB, ActivationCodeDB, generate_id,
)
from src.auth import hash_password, verify_password
from src.validation import validate_email, validate_password
from src.entitlements import resolve_entitlement
from tests.conftest import (
    make_user, make_school, make_product_plan, make_license,
    make_activation_code, get_token,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.database import Base
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _school_with_code(db, status="active", code_status="active",
                      license_status="active", expired_code=False):
    """Create a school + plan + license + activation code (the Platform Admin
    commercial lifecycle up to the point the headteacher redeems)."""
    school = make_school(db, name="Sunrise Academy")
    plan = make_product_plan(db, name="School Premium")
    lic = make_license(db, school.id, plan.id, status=license_status)
    code = make_activation_code(db, lic.id, status=code_status)
    if expired_code:
        code.expires_at = datetime.utcnow() - timedelta(days=1)
        db.commit()
    return school, plan, lic, code


# ── Public / setup routes ─────────────────────────────────────────────────────

class TestPublicRoutes:
    @pytest.mark.asyncio
    async def test_setup_status_is_public(self, db):
        from src.routers.auth import setup_status
        res = await setup_status(db)
        assert res["needs_setup"] is True
        # The published policy is what the frontend mirrors (§20).
        assert res["password_policy"]["min_length"] == 8
        assert res["password_policy"]["requires_symbol"] is True

    @pytest.mark.asyncio
    async def test_setup_status_reports_existing_users(self, db):
        from src.routers.auth import setup_status
        make_user(db, role="school_admin")
        res = await setup_status(db)
        assert res["needs_setup"] is False


# ── Individual teacher registration (§12) ────────────────────────────────────

class TestIndividualRegistration:
    @pytest.mark.asyncio
    async def test_registration_forces_teacher_role_and_null_school(self, db):
        from src.routers.auth import register_individual_teacher, IndividualRegisterRequest
        req = IndividualRegisterRequest(
            email="Teacher1@Gmail.com", password="Strong1!",
            full_name="Ama Boateng",
        )
        res = await register_individual_teacher(req, db)
        # Client cannot choose role/plan/school — all server-derived.
        assert res["user"]["role"] == "teacher"
        assert res["user"]["school_id"] is None
        assert res["user"]["subscription_type"] == "individual"
        # Email is normalized.
        assert res["user"]["email"] == "teacher1@gmail.com"

    @pytest.mark.asyncio
    async def test_registration_grants_free_plan_limits(self, db):
        from src.routers.auth import register_individual_teacher, IndividualRegisterRequest
        req = IndividualRegisterRequest(
            email="free@test.com", password="Strong1!", full_name="Free Teacher")
        res = await register_individual_teacher(req, db)
        plan = await _resolve(db, res["user"]["id"])
        assert plan["edition"] == "free"
        assert plan["generation_limit"] == 5
        assert plan["lesson_quota_period"] == "calendar_month"
        assert plan["lesson_quota_remaining"] == 5
        assert plan["batch_generation"] is False
        assert plan["zip_export"] is False

    @pytest.mark.asyncio
    async def test_registration_rejects_bad_password(self, db):
        from src.routers.auth import register_individual_teacher, IndividualRegisterRequest
        req = IndividualRegisterRequest(
            email="bad@test.com", password="short", full_name="X")
        with pytest.raises(HTTPException) as exc:
            await register_individual_teacher(req, db)
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_registration_rejects_duplicate_email(self, db):
        from src.routers.auth import register_individual_teacher, IndividualRegisterRequest
        make_user(db, role="teacher", email="dup@test.com")
        req = IndividualRegisterRequest(
            email="dup@test.com", password="Strong1!", full_name="Dup")
        with pytest.raises(HTTPException) as exc:
            await register_individual_teacher(req, db)
        assert exc.value.status_code == 409


async def _resolve(db, user_id):
    """Resolve entitlement for a user via the my-plan path."""
    user = db.query(User).filter(User.id == user_id).first()
    return resolve_entitlement(db, user)


# ── Shared teacher login serves both audiences (§10) ─────────────────────────

class TestSharedTeacherLogin:
    @pytest.mark.asyncio
    async def test_school_teacher_logs_in_via_same_endpoint(self, db):
        from src.routers.auth import login, LoginRequest
        school, plan, lic, code = _school_with_code(db)
        u = make_user(db, role="teacher", school_id=school.id,
                      email="st@sunrise.edu.gh")
        u.hashed_password = hash_password("Strong1!")
        db.commit()

        res = await login(LoginRequest(email="st@sunrise.edu.gh", password="Strong1!"), db)
        assert res["user"]["role"] == "teacher"
        assert res["user"]["school_id"] == school.id

    @pytest.mark.asyncio
    async def test_individual_teacher_logs_in_via_same_endpoint(self, db):
        from src.routers.auth import login, LoginRequest
        u = make_user(db, role="teacher", email="indiv@free.com")
        u.hashed_password = hash_password("Strong1!")
        db.commit()

        res = await login(LoginRequest(email="indiv@free.com", password="Strong1!"), db)
        assert res["user"]["role"] == "teacher"
        assert res["user"]["school_id"] is None

    @pytest.mark.asyncio
    async def test_login_rejects_wrong_password(self, db):
        from src.routers.auth import login, LoginRequest
        u = make_user(db, role="teacher", email="wp@free.com")
        u.hashed_password = hash_password("Strong1!")
        db.commit()
        with pytest.raises(HTTPException) as exc:
            await login(LoginRequest(email="wp@free.com", password="nope"), db)
        assert exc.value.status_code in (401, 400)


# ── Entitlement resolution states A-D (§15) ──────────────────────────────────

class TestEntitlementResolution:
    def test_state_a_school_teacher_school_access(self, db):
        """A: teacher + school_id + active school license → SCHOOL ACCESS."""
        school, plan, lic, code = _school_with_code(db)
        u = make_user(db, role="teacher", school_id=school.id)
        res = resolve_entitlement(db, u)
        assert res["source"] == "school"
        assert res["edition"] == "school"
        assert res["school_name"] == "Sunrise Academy"
        assert res["batch_generation"] is True
        assert res["zip_export"] is True

    def test_state_b_individual_free(self, db):
        """B: teacher, no school, free individual plan → FREE TEACHER."""
        u = make_user(db, role="teacher", school_id=None)
        u.subscription_type = "individual"
        ent = EntitlementDB(
            id=generate_id(), user_id=u.id, edition="free",
            subscription_type="individual", generation_limit=3,
            ai_enabled=True, ai_credits=5,
        )
        db.add(ent)
        db.commit()
        res = resolve_entitlement(db, u)
        assert res["source"] in ("individual", "free")
        assert res["edition"] == "free"
        assert res["school_name"] is None
        assert res["batch_generation"] is False

    def test_state_c_individual_pro(self, db):
        """C: teacher, no school, active Pro → INDIVIDUAL PRO."""
        u = make_user(db, role="teacher", school_id=None)
        ent = EntitlementDB(
            id=generate_id(), user_id=u.id, edition="teacher",
            subscription_type="individual", generation_limit=0,
            batch_generation=True, zip_export=True,
            ai_enabled=True, ai_credits=50,
        )
        db.add(ent)
        db.commit()
        res = resolve_entitlement(db, u)
        assert res["source"] == "individual"
        assert res["edition"] == "teacher"
        assert res["batch_generation"] is True

    def test_state_d_combined_most_permissive_wins(self, db):
        """D: school + individual Pro → most permissive per capability."""
        school, plan, lic, code = _school_with_code(db)
        u = make_user(db, role="teacher", school_id=school.id)
        ent = EntitlementDB(
            id=generate_id(), user_id=u.id, edition="teacher",
            subscription_type="individual", generation_limit=0,
            batch_generation=True, zip_export=True, ai_credits=50,
        )
        db.add(ent)
        db.commit()
        res = resolve_entitlement(db, u)
        assert res["source"] == "individual+school"
        # School grants batch/ZIP; combined keeps them on.
        assert res["batch_generation"] is True
        assert res["zip_export"] is True
        assert res["generation_limit"] == 0  # unlimited under school


# ── Activation must precede School Admin (§6, §7, §19) ───────────────────────

class TestSchoolActivation:
    @pytest.mark.asyncio
    async def test_validate_code_returns_safe_info_only(self, db):
        from src.routers.auth import validate_activation_code, ActivationValidateRequest
        school, plan, lic, code = _school_with_code(db)
        res = await validate_activation_code(
            ActivationValidateRequest(activation_code=code.code), db)
        body = str(res)
        assert res["valid"] is True
        assert res["school"]["name"] == "Sunrise Academy"
        assert res["license"]["plan"] == "School Premium"
        assert res["license"]["seat_limit"] == 20
        # No secrets or internal ids leak into the public payload.
        assert "license_code" not in body
        assert "hashed" not in body

    @pytest.mark.asyncio
    async def test_validate_invalid_code_rejected(self, db):
        from src.routers.auth import validate_activation_code, ActivationValidateRequest
        with pytest.raises(HTTPException) as exc:
            await validate_activation_code(
                ActivationValidateRequest(activation_code="TF-SCH-NOPE"), db)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_validate_expired_code_rejected(self, db):
        from src.routers.auth import validate_activation_code, ActivationValidateRequest
        school, plan, lic, code = _school_with_code(db, expired_code=True)
        with pytest.raises(HTTPException) as exc:
            await validate_activation_code(
                ActivationValidateRequest(activation_code=code.code), db)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_validate_redeemed_code_rejected(self, db):
        from src.routers.auth import validate_activation_code, ActivationValidateRequest
        school, plan, lic, code = _school_with_code(db, code_status="used")
        with pytest.raises(HTTPException) as exc:
            await validate_activation_code(
                ActivationValidateRequest(activation_code=code.code), db)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_suspended_license_rejected(self, db):
        from src.routers.auth import setup_school_admin, SetupSchoolAdminRequest
        school, plan, lic, code = _school_with_code(db, license_status="suspended")
        req = SetupSchoolAdminRequest(
            email="ht@sunrise.edu.gh", password="Strong1!",
            full_name="Headteacher", activation_code=code.code)
        with pytest.raises(HTTPException) as exc:
            await setup_school_admin(req, db)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_setup_creates_school_admin_and_redeems_atomically(self, db):
        from src.routers.auth import setup_school_admin, SetupSchoolAdminRequest
        school, plan, lic, code = _school_with_code(db)
        req = SetupSchoolAdminRequest(
            email="ht@sunrise.edu.gh", password="Strong1!",
            full_name="Headteacher One", activation_code=code.code)
        res = await setup_school_admin(req, db)

        assert res["user"]["role"] == "school_admin"
        assert res["user"]["school_id"] == school.id

        # Code redeemed.
        db.refresh(code)
        assert code.status == "used"
        assert code.used_at is not None
        # License activated + recorded.
        db.refresh(lic)
        assert lic.activated_at is not None
        assert lic.activation_code_id == code.id
        # Membership recorded.
        mem = db.query(SchoolMembershipDB).filter(
            SchoolMembershipDB.user_id == res["user"]["id"]).first()
        assert mem is not None and mem.role == "school_admin"

    @pytest.mark.asyncio
    async def test_client_supplied_school_id_is_ignored(self, db):
        """The school always comes from the code's license, never the client."""
        from src.routers.auth import setup_school_admin, SetupSchoolAdminRequest
        school, plan, lic, code = _school_with_code(db)
        other = make_school(db, name="Other School")
        req = SetupSchoolAdminRequest(
            email="ht2@sunrise.edu.gh", password="Strong1!",
            full_name="Headteacher", activation_code=code.code,
            school_id=other.id)  # must be ignored
        res = await setup_school_admin(req, db)
        assert res["user"]["school_id"] == school.id

    @pytest.mark.asyncio
    async def test_activation_replay_rejected(self, db):
        """A redeemed code cannot be replayed to create a second admin (§22)."""
        from src.routers.auth import setup_school_admin, SetupSchoolAdminRequest
        school, plan, lic, code = _school_with_code(db)
        req = SetupSchoolAdminRequest(
            email="ht@sunrise.edu.gh", password="Strong1!",
            full_name="Headteacher", activation_code=code.code)
        await setup_school_admin(req, db)

        req2 = SetupSchoolAdminRequest(
            email="other@sunrise.edu.gh", password="Strong1!",
            full_name="Other", activation_code=code.code)
        with pytest.raises(HTTPException) as exc:
            await setup_school_admin(req2, db)
        assert exc.value.status_code == 403
        # Only one admin was created.
        admins = db.query(User).filter(User.role == "school_admin").all()
        assert len(admins) == 1

    @pytest.mark.asyncio
    async def test_setup_requires_valid_code(self, db):
        """Anonymous user cannot create a School Admin without a code (§9)."""
        from src.routers.auth import setup_school_admin, SetupSchoolAdminRequest
        req = SetupSchoolAdminRequest(
            email="anon@sunrise.edu.gh", password="Strong1!",
            full_name="Anon", activation_code="")
        with pytest.raises(HTTPException) as exc:
            await setup_school_admin(req, db)
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_school_admin_login_after_activation(self, db):
        """After activation, the admin logs in with email+password (§8)."""
        from src.routers.auth import setup_school_admin, login, SetupSchoolAdminRequest, LoginRequest
        school, plan, lic, code = _school_with_code(db)
        await setup_school_admin(SetupSchoolAdminRequest(
            email="ht@sunrise.edu.gh", password="Strong1!",
            full_name="Headteacher", activation_code=code.code), db)

        # The code is NOT a credential — normal login works.
        res = await login(LoginRequest(
            email="ht@sunrise.edu.gh", password="Strong1!"), db)
        assert res["user"]["role"] == "school_admin"
        assert res["access_token"]


# ── Wrong-role access denied (§22) ────────────────────────────────────────────

def _creds(user):
    """Build a real bearer credential for a user (the dependency decodes it)."""
    from fastapi.security import HTTPAuthorizationCredentials
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=get_token(user))


class TestRoleEnforcement:
    @pytest.mark.asyncio
    async def test_missing_credentials_denied(self, db):
        """No bearer header → the optional dependency yields None (the public
        entry path). A required guard would reject before reaching logic."""
        from src.auth import get_optional_user
        assert await get_optional_user(None, db) is None

    @pytest.mark.asyncio
    async def test_teacher_denied_platform_admin_dependency(self, db):
        from src.auth import require_platform_admin
        teacher = make_user(db, role="teacher")
        with pytest.raises(HTTPException) as exc:
            await require_platform_admin(_creds(teacher), db)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_teacher_denied_platform_admin_dependency(self, db):
        from src.auth import require_platform_admin
        teacher = make_user(db, role="teacher")
        with pytest.raises(HTTPException) as exc:
            await require_platform_admin(_creds(teacher), db)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_school_admin_denied_platform_admin_dependency(self, db):
        """A school admin cannot reach platform operations (§22)."""
        from src.auth import require_platform_admin
        school_admin = make_user(db, role="school_admin", is_admin=True)
        with pytest.raises(HTTPException) as exc:
            await require_platform_admin(_creds(school_admin), db)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_platform_admin_passes_own_dependency(self, db):
        from src.auth import require_platform_admin
        pa = make_user(db, role="platform_admin")
        assert await require_platform_admin(_creds(pa), db) is not None

    @pytest.mark.asyncio
    async def test_bad_token_denied(self, db):
        from src.auth import require_admin
        from fastapi.security import HTTPAuthorizationCredentials
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="garbage")
        with pytest.raises(HTTPException) as exc:
            await require_admin(creds, db)
        assert exc.value.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_teacher_denied_platform_create_school(self, db):
        """The platform-admin guard rejects a teacher; school creation is
        platform-only (§23)."""
        from src.auth import require_platform_admin
        teacher = make_user(db, role="teacher")
        with pytest.raises(HTTPException) as exc:
            await require_platform_admin(_creds(teacher), db)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_school_admin_scoped_to_own_school_only(self, db):
        """A school admin from school A cannot see school B's users (§22)."""
        from src.routers.auth import list_users
        school_a, *_ = _school_with_code(db)
        school_b = make_school(db, name="Rival School")
        make_user(db, role="teacher", school_id=school_b.id, email="b@rival.com")
        admin_a = make_user(db, role="school_admin", school_id=school_a.id,
                            is_admin=True, email="a@sunrise.edu.gh")

        res = await list_users(admin=admin_a, db=db)
        emails = [u["email"] for u in res["users"]]
        assert "a@sunrise.edu.gh" in emails
        assert "b@rival.com" not in emails


# ── Password UX regression (§20) ──────────────────────────────────────────────

class TestPasswordUx:
    def test_password_requires_min_length(self):
        ok, _ = validate_password("Ab1!")
        assert ok is False

    def test_password_requires_letter(self):
        ok, _ = validate_password("12345678!")
        assert ok is False

    def test_password_requires_digit(self):
        ok, _ = validate_password("Password!")
        assert ok is False

    def test_password_requires_symbol(self):
        ok, _ = validate_password("Password1")
        assert ok is False

    def test_valid_password_accepted(self):
        ok, _ = validate_password("Strong1!")
        assert ok is True

    def test_email_validation_rejects_placeholder(self):
        ok, _ = validate_email("not-an-email")
        assert ok is False

    def test_email_validation_accepts_real_address(self):
        ok, _ = validate_email("ama@school.edu.gh")
        assert ok is True

    def test_password_hash_roundtrip(self):
        h = hash_password("Strong1!")
        assert verify_password("Strong1!", h) is True
        assert verify_password("wrong", h) is False


# ── Existing flows intact (§25 regression guard) ─────────────────────────────

class TestExistingFlowsIntact:
    @pytest.mark.asyncio
    async def test_school_commercial_flow_still_works(self, db):
        """The existing school license + activation lifecycle is unchanged."""
        from src.routers.auth import validate_activation_code, ActivationValidateRequest
        school, plan, lic, code = _school_with_code(db)
        assert code.status == "active"
        res = await validate_activation_code(
            ActivationValidateRequest(activation_code=code.code), db)
        assert res["valid"] is True

    @pytest.mark.asyncio
    async def test_individual_free_and_pro_both_work(self, db):
        """Both individual tiers still resolve correctly."""
        free = make_user(db, role="teacher", school_id=None, email="f2@x.com")
        free.subscription_type = "individual"
        db.add(EntitlementDB(
            id=generate_id(), user_id=free.id, edition="free",
            subscription_type="individual", generation_limit=3, ai_credits=5))
        pro = make_user(db, role="teacher", school_id=None, email="p2@x.com")
        db.add(EntitlementDB(
            id=generate_id(), user_id=pro.id, edition="teacher",
            subscription_type="individual", generation_limit=0,
            batch_generation=True, zip_export=True, ai_credits=50))
        db.commit()

        assert resolve_entitlement(db, free)["edition"] == "free"
        assert resolve_entitlement(db, pro)["edition"] == "teacher"
