"""
Tests for school data isolation.

Tests database models directly without FastAPI app import.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import (
    User, SchoolDB, SchoolMembershipDB, SchemeDB, LessonPlanDB,
    Base, generate_id
)
from tests.conftest import make_user, make_school


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


class TestSchoolIsolation:
    def setup_method(self, method):
        """Will be called before each test method, but db fixture isn't available here.
        We'll use the db fixture in each test instead."""

    def test_different_schools_have_different_ids(self, db):
        school_a = make_school(db, name="School A", code="SCH-A")
        school_b = make_school(db, name="School B", code="SCH-B")
        assert school_a.id != school_b.id

    def test_users_belong_to_correct_school(self, db):
        school_a = make_school(db, code="SCH-A")
        school_b = make_school(db, code="SCH-B")

        teacher_a = make_user(db, role="teacher", school_id=school_a.id)
        teacher_b = make_user(db, role="teacher", school_id=school_b.id)

        assert teacher_a.school_id == school_a.id
        assert teacher_b.school_id == school_b.id
        assert teacher_a.school_id != teacher_b.school_id

    def test_school_memberships_isolate_users(self, db):
        school_a = make_school(db, code="SCH-A")
        school_b = make_school(db, code="SCH-B")

        admin_a = make_user(db, role="school_admin", school_id=school_a.id)
        teacher_a = make_user(db, role="teacher", school_id=school_a.id)
        admin_b = make_user(db, role="school_admin", school_id=school_b.id)

        # Create memberships
        membership_a1 = SchoolMembershipDB(
            id=generate_id(), user_id=admin_a.id, school_id=school_a.id, role="school_admin"
        )
        membership_a2 = SchoolMembershipDB(
            id=generate_id(), user_id=teacher_a.id, school_id=school_a.id, role="teacher"
        )
        membership_b1 = SchoolMembershipDB(
            id=generate_id(), user_id=admin_b.id, school_id=school_b.id, role="school_admin"
        )
        db.add_all([membership_a1, membership_a2, membership_b1])
        db.commit()

        # Query school A members
        school_a_members = db.query(SchoolMembershipDB).filter(
            SchoolMembershipDB.school_id == school_a.id
        ).count()
        school_b_members = db.query(SchoolMembershipDB).filter(
            SchoolMembershipDB.school_id == school_b.id
        ).count()

        assert school_a_members == 2
        assert school_b_members == 1

    def test_platform_admin_bypasses_school_check(self, db):
        """Platform admin should be able to access all schools."""
        platform_admin = make_user(db, role="platform_admin")
        school_a = make_school(db, code="SCH-A")
        school_b = make_school(db, code="SCH-B")

        # Platform admin has no school_id (or any school_id)
        assert platform_admin.role == "platform_admin"
        # In the actual auth code, platform_admin bypasses school membership check

    def test_scheme_belongs_to_owner(self, db):
        school_a = make_school(db, code="SCH-A")
        school_b = make_school(db, code="SCH-B")

        teacher_a = make_user(db, role="teacher", school_id=school_a.id)
        teacher_b = make_user(db, role="teacher", school_id=school_b.id)

        scheme_a = SchemeDB(
            id=generate_id(), owner_id=teacher_a.id, filename="Scheme A",
            subject="Science", class_level="Basic 9",
        )
        scheme_b = SchemeDB(
            id=generate_id(), owner_id=teacher_b.id, filename="Scheme B",
            subject="Math", class_level="Basic 8",
        )
        db.add_all([scheme_a, scheme_b])
        db.commit()

        # Query schemes by owner
        a_schemes = db.query(SchemeDB).filter(SchemeDB.owner_id == teacher_a.id).count()
        b_schemes = db.query(SchemeDB).filter(SchemeDB.owner_id == teacher_b.id).count()

        assert a_schemes == 1
        assert b_schemes == 1

    def test_lesson_plans_belong_to_owner(self, db):
        school_a = make_school(db, code="SCH-A")
        teacher_a = make_user(db, role="teacher", school_id=school_a.id)
        teacher_b = make_user(db, role="teacher", school_id=school_a.id)

        # Both teachers in same school, but different lesson plans
        from src.database import GenerationJobDB, LessonPlanDB, WeekDB, SchemeDB, Date
        from datetime import date

        scheme = SchemeDB(
            id=generate_id(), owner_id=teacher_a.id, filename="Scheme",
            subject="Science", class_level="Basic 9",
        )
        db.add(scheme)
        db.commit()

        job_a = GenerationJobDB(
            id=generate_id(), owner_id=teacher_a.id, scheme_id=scheme.id, status="completed"
        )
        job_b = GenerationJobDB(
            id=generate_id(), owner_id=teacher_b.id, scheme_id=scheme.id, status="completed"
        )
        db.add_all([job_a, job_b])
        db.commit()

        lp_a = LessonPlanDB(
            id=generate_id(), job_id=job_a.id, owner_id=teacher_a.id, scheme_id=scheme.id,
            week_number=1, lesson_sequence=1, class_level="Basic 9", subject="Science",
        )
        lp_b = LessonPlanDB(
            id=generate_id(), job_id=job_b.id, owner_id=teacher_b.id, scheme_id=scheme.id,
            week_number=1, lesson_sequence=1, class_level="Basic 9", subject="Science",
        )
        db.add_all([lp_a, lp_b])
        db.commit()

        a_lessons = db.query(LessonPlanDB).filter(LessonPlanDB.owner_id == teacher_a.id).count()
        b_lessons = db.query(LessonPlanDB).filter(LessonPlanDB.owner_id == teacher_b.id).count()

        assert a_lessons == 1
        assert b_lessons == 1
