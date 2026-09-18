"""
Production architecture lock tests (SchemeKnit role separation).

Locks the browser-verified architecture:
- Platform Admin: business/platform only, MUST NOT use teacher workflow.
- School Admin: manages school users/seats, blocked from platform administration.
- Teacher: lesson-planning workflow, blocked from school admin and platform admin.

These tests exercise the real FastAPI dependency chain (no route-level mocks),
so they fail if anyone re-opens the role boundaries.
"""

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base, get_db
from src.auth import (
    require_teacher_workflow,
    require_valid_license,
    require_admin,
    require_platform_admin,
)
from src.routers import documents, generation, curriculum
from tests.conftest import make_user, make_school, make_product_plan, make_license


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


class TestTeacherWorkflowBlocksPlatformAdmin:
    """Platform admin must not perform teacher workflow actions (upload/review/generate/export)."""

    def _make_teacher_env(self, db):
        school = make_school(db)
        plan = make_product_plan(db)
        make_license(db, school.id, plan.id)
        return school

    def test_platform_admin_blocked_by_dependency(self, db):
        """A resolved platform-admin user must be rejected by the workflow dependency."""
        import asyncio
        from src.auth import create_access_token

        school = self._make_teacher_env(db)
        pa = make_user(db, role="platform_admin")
        token = create_access_token({"sub": pa.id, "email": pa.email})

        class C:
            credentials = token

        async def _call():
            return await require_teacher_workflow(credentials=C(), db=db)

        with pytest.raises(HTTPException) as e:
            asyncio.run(_call())
        assert e.value.status_code == 403
        assert "do not use the teacher" in str(e.value.detail).lower()

    def test_teacher_passes_workflow_dependency(self, db):
        """Licensed teachers keep full workflow access."""
        import asyncio
        from src.auth import create_access_token

        school = self._make_teacher_env(db)
        teacher = make_user(db, role="teacher", school_id=school.id)
        token = create_access_token({"sub": teacher.id, "email": teacher.email})

        class C:
            credentials = token

        async def _call():
            return await require_teacher_workflow(credentials=C(), db=db)

        user = asyncio.run(_call())
        assert user.role == "teacher"

    def test_workflow_routers_declare_teacher_dependency(self):
        """Upload, generate, approve, and lesson-edit endpoints must use require_teacher_workflow."""
        import inspect
        from fastapi import params

        def deps_of(endpoint):
            sig = inspect.signature(endpoint)
            out = []
            for p in sig.parameters.values():
                if p.default is not inspect.Parameter.empty and hasattr(p.default, "dependency"):
                    out.append(p.default.dependency)
            return out

        for endpoint in (
            documents.upload_scheme,
            generation.generate_lesson_plans,
            generation.update_lesson_plan,
            curriculum.approve_scheme,
        ):
            assert require_teacher_workflow in deps_of(endpoint), (
                f"{endpoint.__name__} must enforce require_teacher_workflow"
            )
            assert require_valid_license not in deps_of(endpoint), (
                f"{endpoint.__name__} must not allow the platform-admin bypass"
            )

    def test_read_endpoints_stay_inspectable(self):
        """Metadata/read endpoints keep get_current_user so PA can inspect without impersonating."""
        import inspect

        def deps_of(endpoint):
            sig = inspect.signature(endpoint)
            return [
                p.default.dependency
                for p in sig.parameters.values()
                if p.default is not inspect.Parameter.empty and hasattr(p.default, "dependency")
            ]

        for endpoint in (
            documents.list_schemes,
            documents.get_scheme,
            generation.list_all_lessons,
            generation.get_generation_status,
        ):
            deps = deps_of(endpoint)
            assert require_teacher_workflow not in deps
            assert any(d is not require_teacher_workflow for d in deps), endpoint.__name__


class TestPlatformAdminExcludedFromSchoolAdmin:
    def test_require_admin_rejects_platform_admin(self, db):
        import asyncio
        from src.auth import create_access_token

        pa = make_user(db, role="platform_admin", is_admin=False)
        token = create_access_token({"sub": pa.id, "email": pa.email})

        async def _call():
            return await require_admin(
                credentials=type("C", (), {"credentials": token})(),
                db=db,
            )

        with pytest.raises(HTTPException) as e:
            asyncio.run(_call())
        assert e.value.status_code == 403
        assert "Admin access required" in str(e.value.detail)

    def test_require_platform_admin_rejects_school_roles(self, db):
        import asyncio

        school = make_school(db)
        sa = make_user(db, role="school_admin", school_id=school.id, is_admin=True)
        teacher = make_user(db, role="teacher", school_id=school.id)

        for user in (sa, teacher):
            token = __import__("src.auth", fromlist=["create_access_token"]).create_access_token(
                {"sub": user.id, "email": user.email}
            )

            async def _call():
                return await require_platform_admin(
                    credentials=type("C", (), {"credentials": token})(),
                    db=db,
                )

            with pytest.raises(HTTPException) as e:
                asyncio.run(_call())
            assert e.value.status_code == 403
            assert "Platform administrator" in str(e.value.detail)


class TestTeacherCannotReachAdmin:
    def test_require_admin_rejects_teacher(self, db):
        import asyncio
        from src.auth import create_access_token

        school = make_school(db)
        teacher = make_user(db, role="teacher", school_id=school.id)
        token = create_access_token({"sub": teacher.id, "email": teacher.email})

        async def _call():
            return await require_admin(
                credentials=type("C", (), {"credentials": token})(),
                db=db,
            )

        with pytest.raises(HTTPException) as e:
            asyncio.run(_call())
        assert e.value.status_code == 403
        assert "Admin access required" in str(e.value.detail)
