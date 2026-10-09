"""Quota enforcement through the REAL endpoints — production incident suite.

Regression suite for the production quota-accounting incident (Oct 2026):
the ledger accepted 6 distinct lessons against the Free Tier limit of 5 while
every quota read returned ``used=0``. Root cause: ``_insert_ignore`` relied on
``rowcount == 1`` for ``INSERT ... ON CONFLICT DO NOTHING``, but PostgreSQL +
psycopg3 reports ``rowcount == -1`` for that statement, so every insert was
misread as an already-counted conflict, the guarded UPDATE never ran, and the
aggregate counter never incremented.

These tests pin the incident invariants END TO END (the browser's API):

  A/E. Five distinct generations succeed; the sixth is rejected 403 BEFORE
       any job, any lesson row, or any counter movement.
  H.   Read-after-write: the generate response, ``GET /quota`` and the
       persisted ledger agree on every run.
  F.   After exhaustion the Autopilot plan reports ``quota_exhausted`` — one
       authority, no silent extra selection.
  C/D. Repeated codes stay distinct-code idempotent (one unit) while
       source occurrences stay distinct lessons.
  Scope. Quota is keyed by user + server month; another user is unaffected.
"""

from __future__ import annotations

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.database import SchemeDB, WeekDB, generate_id  # noqa: E402
from src.models import TermConfig  # noqa: E402
from tests.conftest import make_user  # noqa: E402

WEEKS = 6


def _scheme(db, owner_id, weeks=WEEKS, code_for=None):
    code_for = code_for or (lambda n: f"B7.1.{n}.1.1")
    scheme = SchemeDB(
        id=generate_id(), owner_id=owner_id, filename="Quota Journey.docx",
        subject="ICT", class_level="Basic 7", term="First Term",
        academic_year="2026/2027", status="extracted", detection_status="single",
    )
    db.add(scheme)
    db.flush()
    for n in range(1, weeks + 1):
        code = code_for(n)
        db.add(WeekDB(
            id=generate_id(), scheme_id=scheme.id, week_number=n,
            start_date=date(2026, 9, 7), end_date=date(2026, 9, 11),
            week_type="instruction", strand="Introduction to Computing",
            sub_strand="Components of Computers",
            content_standards=[f"B7.1.1.{n}"],
            indicators=[f"{code} Identify the parts of a computer"],
            resources=["Keyboard"],
        ))
    db.commit()
    return scheme


def _config(scheme_id, **over):
    data = dict(
        scheme_of_work_id=scheme_id,
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=3, lesson_duration_minutes=60, class_size=30,
        teaching_days=[0, 2, 4], holidays=[], ai_mode="OFF",
        include_special_weeks=False, class_level="Basic 7", subject="ICT",
    )
    data.update(over)
    return TermConfig(**data)


def _app(db, user):
    from fastapi import FastAPI
    from src.auth import get_current_user, require_teacher_workflow
    from src.database import get_db
    from src.routers import generation as gen_router

    app = FastAPI()
    app.include_router(gen_router.router, prefix="/api/generation")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_teacher_workflow] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    return app


def _preview(client, scheme, config):
    resp = client.post(
        f"/api/generation/{scheme.id}/allocation-preview",
        json=config.model_dump(mode="json"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["lesson_review"]


def _quota(client):
    resp = client.get("/api/generation/quota")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _lessons(client, scheme):
    resp = client.get(f"/api/generation/schemes/{scheme.id}/lessons")
    assert resp.status_code == 200, resp.text
    return resp.json()["lesson_plans"]


def _job_status(client, scheme):
    return client.get(f"/api/generation/scheme/{scheme.id}/status").json()


def _generate_one(client, scheme, config, row):
    resp = client.post(
        f"/api/generation/{scheme.id}/generate",
        json={
            **config.model_dump(mode="json"),
            "selected_occurrence_ids": [row["source_occurrence_id"]],
            "selected_indicator_codes": [row["indicator_code"]],
        },
    )
    return resp


class TestSixthGenerationRejectedBeforeAnySideEffect:
    def test_five_accepted_sixth_403_no_job_no_lesson_no_counter_move(self, db):
        """Invariants A, E, H: allowance of 5 is exact, end to end."""
        from fastapi.testclient import TestClient

        user = make_user(db)
        scheme = _scheme(db, user.id)
        config = _config(scheme.id)

        with TestClient(_app(db, user)) as client:
            rows = _preview(client, scheme, config)
            assert len(rows) == WEEKS

            for i, row in enumerate(rows[:5], start=1):
                resp = _generate_one(client, scheme, config, row)
                assert resp.status_code == 200, resp.text
                body = resp.json()
                assert body["quota"]["used"] == i, "read-after-write in body"
                assert body["quota"]["remaining"] == 5 - i
                # The endpoint agrees with the response (invariant H).
                q = _quota(client)
                assert q["used"] == i and q["remaining"] == 5 - i

                if i == 3:
                    # Invariant C while allowance remains: regenerating an
                    # already-counted code is free and replaces in place.
                    regen = _generate_one(client, scheme, config, rows[0])
                    assert regen.status_code == 200, regen.text
                    assert regen.json()["quota"]["used"] == 3
                    assert len(_lessons(client, scheme)) == 3

            assert len(_lessons(client, scheme)) == 5
            assert _quota(client)["used"] == 5

            # Sixth distinct code: rejected BEFORE any job or persistence.
            before = _job_status(client, scheme)
            resp = _generate_one(client, scheme, config, rows[5])
            assert resp.status_code == 403, resp.text
            assert "Free Tier" in resp.json()["detail"]
            assert _job_status(client, scheme) == before, "no job created"

            lessons = _lessons(client, scheme)
            assert len(lessons) == 5, "rejected run persisted nothing"
            assert rows[5]["source_occurrence_id"] not in {
                l.get("source_occurrence_id") for l in lessons
            }
            assert _quota(client)["used"] == 5, "rejected run moved nothing"

            # At exhaustion the pre-check refuses ANY further generate call
            # (conservative policy that predates the incident): no charge,
            # no job, no persistence — and never a silent over-allowance.
            resp = _generate_one(client, scheme, config, rows[0])
            assert resp.status_code == 403, resp.text
            assert _quota(client)["used"] == 5
            assert len(_lessons(client, scheme)) == 5
            assert _job_status(client, scheme) == before


class TestAutopilotConsistencyAfterSingles:
    def test_autopilot_reports_quota_exhausted_after_single_generations(self, db):
        """Invariant F: single and Autopilot share one authority."""
        from fastapi.testclient import TestClient

        user = make_user(db)
        scheme = _scheme(db, user.id)
        config = _config(scheme.id)

        with TestClient(_app(db, user)) as client:
            rows = _preview(client, scheme, config)
            for row in rows[:5]:
                assert _generate_one(client, scheme, config, row).status_code == 200
            assert _quota(client)["used"] == 5

            plan = client.post(
                f"/api/generation/{scheme.id}/autopilot-selection",
                json=config.model_dump(mode="json"),
            )
            assert plan.status_code == 200, plan.text
            body = plan.json()
            assert body["ready"] is False
            assert [b["code"] for b in body["blockers"]] == ["quota_exhausted"]
            assert body["counts"]["selected_count"] == 0
            assert body["quota"]["remaining"] == 0


class TestIdentityAndPeriodScope:
    def test_quota_is_scoped_to_the_user_not_the_scheme(self, db):
        """Invariant (scope): user B's allowance is untouched by user A."""
        from fastapi.testclient import TestClient
        from src.auth import get_current_user, require_teacher_workflow

        user_a = make_user(db, email="quota_scope_a@test.com")
        user_b = make_user(db, email="quota_scope_b@test.com")
        scheme = _scheme(db, user_a.id, weeks=2)
        config = _config(scheme.id)

        app = _app(db, user_a)
        with TestClient(app) as client:
            rows = _preview(client, scheme, config)
            assert _generate_one(client, scheme, config, rows[0]).status_code == 200
            assert _quota(client)["used"] == 1

            # Same server month, different user: fresh allowance.
            app.dependency_overrides[get_current_user] = lambda: user_b
            app.dependency_overrides[require_teacher_workflow] = lambda: user_b
            q = _quota(client)
            assert q["used"] == 0 and q["remaining"] == 5

            app.dependency_overrides[get_current_user] = lambda: user_a
            app.dependency_overrides[require_teacher_workflow] = lambda: user_a
            assert _quota(client)["used"] == 1, "A's counter survived the switch"


class TestRepeatedCodeAcrossWeeks:
    def test_two_occurrences_of_one_code_charge_one_unit(self, db):
        """Invariants C + D: distinct lessons, one distinct-code unit."""
        from fastapi.testclient import TestClient

        user = make_user(db)
        scheme = _scheme(db, user.id, weeks=2, code_for=lambda n: "B7.5.1.1.1")
        config = _config(scheme.id)

        with TestClient(_app(db, user)) as client:
            rows = _preview(client, scheme, config)
            assert len(rows) == 2
            assert rows[0]["source_occurrence_id"] != rows[1]["source_occurrence_id"]

            first = _generate_one(client, scheme, config, rows[0])
            assert first.status_code == 200, first.text
            assert first.json()["quota"]["used"] == 1

            second = _generate_one(client, scheme, config, rows[1])
            assert second.status_code == 200, second.text
            assert second.json()["quota"]["used"] == 1, (
                "same code in another week is still one unit"
            )
            lessons = _lessons(client, scheme)
            assert len(lessons) == 2, "both source occurrences persisted"
            assert {l["source_occurrence_id"] for l in lessons} == {
                r["source_occurrence_id"] for r in rows
            }
