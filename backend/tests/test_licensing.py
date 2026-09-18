"""
Tests for licensing system.

Tests database models directly without FastAPI app import.
"""

import pytest
from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import (
    SchoolDB, SchoolLicenseDB, ProductPlanDB, ActivationCodeDB,
    User, Base, generate_id
)
from tests.conftest import make_user, make_school, make_product_plan, make_license, make_activation_code


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


class TestLicenseCreation:
    def test_create_license(self, db):
        school = make_school(db)
        plan = make_product_plan(db)
        lic = make_license(db, school.id, plan.id)

        assert lic.school_id == school.id
        assert lic.product_plan_id == plan.id
        assert lic.status == "active"
        assert lic.seat_limit == 20

    def test_license_has_unique_code(self, db):
        school = make_school(db)
        plan = make_product_plan(db)
        lic1 = make_license(db, school.id, plan.id)
        lic2 = make_license(db, school.id, plan.id)

        assert lic1.license_code != lic2.license_code

    def test_license_dates(self, db):
        school = make_school(db)
        plan = make_product_plan(db, duration_days=365)
        lic = make_license(db, school.id, plan.id)

        assert lic.start_date == date.today()
        assert lic.expiry_date == date.today() + timedelta(days=365)


class TestLicenseStates:
    def test_pending_license(self, db):
        school = make_school(db)
        plan = make_product_plan(db)
        lic = make_license(db, school.id, plan.id, status="pending")
        assert lic.status == "pending"

    def test_active_license(self, db):
        school = make_school(db)
        plan = make_product_plan(db)
        lic = make_license(db, school.id, plan.id, status="active")
        assert lic.status == "active"

    def test_suspended_license(self, db):
        school = make_school(db)
        plan = make_product_plan(db)
        lic = make_license(db, school.id, plan.id, status="suspended")
        assert lic.status == "suspended"

    def test_expired_license(self, db):
        school = make_school(db)
        plan = make_product_plan(db)
        lic = make_license(db, school.id, plan.id, status="expired")
        assert lic.status == "expired"

    def test_cancelled_license(self, db):
        school = make_school(db)
        plan = make_product_plan(db)
        lic = make_license(db, school.id, plan.id, status="cancelled")
        assert lic.status == "cancelled"


class TestSeatLimits:
    def test_seat_limit_on_license(self, db):
        school = make_school(db)
        plan = make_product_plan(db, seat_limit=5)
        lic = make_license(db, school.id, plan.id, seat_limit=5)
        assert lic.seat_limit == 5

    def test_seat_limit_on_plan(self, db):
        plan = make_product_plan(db, seat_limit=50)
        assert plan.seat_limit == 50

    def test_count_active_teachers(self, db):
        school = make_school(db)
        make_user(db, role="teacher", school_id=school.id)
        make_user(db, role="teacher", school_id=school.id)
        make_user(db, role="teacher", school_id=school.id)

        teacher_count = db.query(User).filter(
            User.school_id == school.id,
            User.role == "teacher"
        ).count()
        assert teacher_count == 3

    def test_seat_enforcement_query(self, db):
        school = make_school(db)
        plan = make_product_plan(db, seat_limit=2)
        lic = make_license(db, school.id, plan.id, seat_limit=2)

        # Add 2 teachers
        make_user(db, role="teacher", school_id=school.id)
        make_user(db, role="teacher", school_id=school.id)

        # Check if at limit
        current_count = db.query(User).filter(
            User.school_id == school.id,
            User.role == "teacher",
            User.is_active == True,
        ).count()

        assert current_count == lic.seat_limit  # At limit


class TestProductPlans:
    def test_create_plan(self, db):
        plan = make_product_plan(db, name="School Annual", price=800.0, seat_limit=20)
        assert plan.name == "School Annual"
        assert plan.price == 800.0
        assert plan.seat_limit == 20
        assert plan.currency == "GHS"

    def test_plan_features(self, db):
        plan = make_product_plan(db)
        # Features set by conftest helper
        assert "multi_teacher" in plan.features
        assert "admin_dashboard" in plan.features

    def test_plan_duration(self, db):
        plan = make_product_plan(db, duration_days=365)
        assert plan.duration_days == 365


class TestLicenseRenewal:
    def test_renewal_extends_expiry(self, db):
        school = make_school(db)
        plan = make_product_plan(db, duration_days=365)
        lic = make_license(db, school.id, plan.id, status="active")

        old_expiry = lic.expiry_date
        # Simulate renewal
        lic.expiry_date = lic.expiry_date + timedelta(days=365)
        db.commit()

        assert lic.expiry_date == old_expiry + timedelta(days=365)


class TestSeatLimitEnforcement:
    def test_count_active_teachers(self, db):
        from tests.conftest import make_school
        from sqlalchemy import func
        school = make_school(db)
        for i in range(3):
            make_user(db, role="teacher", school_id=school.id)

        count = db.query(func.count(User.id)).filter(
            User.school_id == school.id,
            User.role == "teacher",
            User.is_active == True,
        ).scalar()
        assert count == 3

    def test_seat_limit_blocks_creation(self, db):
        from tests.conftest import make_school
        from sqlalchemy import func
        school = make_school(db)
        plan = make_product_plan(db, duration_days=365, seat_limit=2)
        lic = make_license(db, school.id, plan.id, seat_limit=2, status="active")

        for i in range(2):
            make_user(db, role="teacher", school_id=school.id)

        count = db.query(func.count(User.id)).filter(
            User.school_id == school.id,
            User.role == "teacher",
            User.is_active == True,
        ).scalar()

        assert count >= lic.seat_limit

    def test_no_license_allows_creation(self, db):
        from tests.conftest import make_school
        from sqlalchemy import func
        school = make_school(db)

        for i in range(5):
            make_user(db, role="teacher", school_id=school.id)

        license = db.query(SchoolLicenseDB).filter(
            SchoolLicenseDB.school_id == school.id,
            SchoolLicenseDB.status == "active",
        ).first()

        assert license is None

        count = db.query(func.count(User.id)).filter(
            User.school_id == school.id,
            User.role == "teacher",
            User.is_active == True,
        ).scalar()
        assert count == 5


class TestLicenseActivationState:
    """Activation must leave observable, server-derived evidence.

    Regression for: "when a school begins using its activation key, the
    Platform Admin license page does not visibly change the license to ACTIVE /
    show the expected active state and school usage".
    """

    @pytest.mark.asyncio
    async def test_redeem_records_activation_on_the_license(self, db):
        from src.routers.auth import setup_school_admin, SetupSchoolAdminRequest
        school = make_school(db)
        plan = make_product_plan(db)
        lic = make_license(db, school.id, plan.id, status="pending")
        code = make_activation_code(db, lic.id)
        assert lic.activated_at is None

        await setup_school_admin(SetupSchoolAdminRequest(
            email="sa@claim.test", password="Admin123!", full_name="SA",
            activation_code=code.code), db)

        db.refresh(lic)
        assert lic.status == "active"
        assert lic.activated_at is not None
        assert lic.activation_code_id == code.id

    @pytest.mark.asyncio
    async def test_first_claim_wins_on_replacement_code(self, db):
        from src.routers.auth import setup_school_admin, SetupSchoolAdminRequest
        school = make_school(db)
        plan = make_product_plan(db)
        lic = make_license(db, school.id, plan.id, status="pending")
        first = make_activation_code(db, lic.id)
        second = make_activation_code(db, lic.id)

        await setup_school_admin(SetupSchoolAdminRequest(
            email="sa1@claim.test", password="Admin123!", full_name="SA1",
            activation_code=first.code), db)
        db.refresh(lic)
        claimed_at = lic.activated_at
        assert claimed_at is not None

        await setup_school_admin(SetupSchoolAdminRequest(
            email="sa2@claim.test", password="Admin123!", full_name="SA2",
            activation_code=second.code), db)
        db.refresh(lic)
        # A replacement code must not rewrite the school's activation point.
        assert lic.activated_at == claimed_at
        assert lic.activation_code_id == first.id

    @pytest.mark.asyncio
    async def test_platform_view_shows_activation_and_usage(self, db):
        from src.routers.auth import setup_school_admin, SetupSchoolAdminRequest
        from src.routers import platform_admin as pa
        school = make_school(db)
        plan = make_product_plan(db, seat_limit=20)
        lic = make_license(db, school.id, plan.id, status="pending", seat_limit=20)
        code = make_activation_code(db, lic.id)
        admin = make_user(db, role="platform_admin", is_admin=True)

        before = (await pa.list_licenses(admin, db))["licenses"][0]
        assert before["status"] == "pending"
        assert before["effective_status"] == "pending"
        assert before["is_active"] is False
        assert before["claimed_by_school"] is False
        assert before["activated_at"] is None

        await setup_school_admin(SetupSchoolAdminRequest(
            email="sa@view.test", password="Admin123!", full_name="SA",
            activation_code=code.code), db)

        after = (await pa.list_licenses(admin, db))["licenses"][0]
        assert after["status"] == "active"
        assert after["effective_status"] == "active"
        assert after["is_active"] is True
        assert after["claimed_by_school"] is True
        assert after["activated_at"] is not None
        assert after["activation_code"] == code.code
        assert after["activation_code_status"] == "used"
        assert after["plan_name"] == plan.name
        assert after["school_name"] == school.name
        assert after["seat_limit"] == 20
        assert after["expiry_date"] is not None
        # Real school usage: the school-admin account activation itself created.
        assert after["seats_used"] == 1
        assert after["seats_available"] == 19

    @pytest.mark.asyncio
    async def test_seats_used_counts_every_provisioned_role(self, db):
        from src.routers import platform_admin as pa
        school = make_school(db)
        plan = make_product_plan(db, seat_limit=10)
        lic = make_license(db, school.id, plan.id, seat_limit=10)
        make_user(db, role="school_admin", school_id=school.id, is_admin=True)
        make_user(db, role="teacher", school_id=school.id)
        make_user(db, role="teacher", school_id=school.id)
        disabled = make_user(db, role="teacher", school_id=school.id)
        disabled.is_active = False
        db.commit()
        admin = make_user(db, role="platform_admin", is_admin=True)

        view = (await pa.list_licenses(admin, db))["licenses"][0]
        assert view["seats_used"] == 3        # inactive teacher excluded
        assert view["seats_available"] == 7

    @pytest.mark.asyncio
    async def test_expired_active_license_is_reported_expired(self, db):
        from src.routers import platform_admin as pa
        school = make_school(db)
        plan = make_product_plan(db)
        lic = make_license(db, school.id, plan.id, status="active")
        lic.expiry_date = date.today() - timedelta(days=1)
        db.commit()
        admin = make_user(db, role="platform_admin", is_admin=True)

        view = (await pa.list_licenses(admin, db))["licenses"][0]
        assert view["status"] == "active"           # raw column untouched
        assert view["effective_status"] == "expired"
        assert view["is_active"] is False

    @pytest.mark.asyncio
    async def test_suspend_and_reactivate_are_reflected(self, db):
        from src.routers import platform_admin as pa
        school = make_school(db)
        plan = make_product_plan(db)
        lic = make_license(db, school.id, plan.id, status="active")
        admin = make_user(db, role="platform_admin", is_admin=True)

        await pa.suspend_license(lic.id, admin, db)
        view = (await pa.list_licenses(admin, db))["licenses"][0]
        assert view["effective_status"] == "suspended" and view["is_active"] is False

        await pa.activate_license(lic.id, admin, db)
        view = (await pa.list_licenses(admin, db))["licenses"][0]
        assert view["effective_status"] == "active" and view["is_active"] is True

    @pytest.mark.asyncio
    async def test_school_detail_exposes_activation(self, db):
        from src.routers.auth import setup_school_admin, SetupSchoolAdminRequest
        from src.routers import platform_admin as pa
        school = make_school(db)
        plan = make_product_plan(db)
        lic = make_license(db, school.id, plan.id, status="pending")
        code = make_activation_code(db, lic.id)
        admin = make_user(db, role="platform_admin", is_admin=True)

        await setup_school_admin(SetupSchoolAdminRequest(
            email="sa@detail.test", password="Admin123!", full_name="SA",
            activation_code=code.code), db)

        detail = await pa.get_school(school.id, admin, db)
        assert detail["license"]["effective_status"] == "active"
        assert detail["license"]["claimed_by_school"] is True
        assert detail["license"]["activated_at"] is not None
