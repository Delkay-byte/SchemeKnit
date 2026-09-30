"""
REPRODUCTION SCRIPT (pre-fix evidence).

Drives the REAL generate-page data path over the HTTP boundary, exactly as
the browser does it:

  1. POST /allocation-preview  (renders the per-lesson review rows)
  2. PUT  /lesson-review       (what saveLessonReviewDrafts() sends)
  3. POST /{scheme_id}/generate
  4. GET  /{job_id}/lessons    (the persisted lessons)

The generate page's review rows key WAPEF selections by ``lesson_sequence``,
which comes from the ALLOCATION PREVIEW. If the generate endpoint cannot find
those keys in the saved draft store, the selections never reach the lesson.
"""

from __future__ import annotations

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.database import SchemeDB, WeekDB, generate_id  # noqa: E402
from src.models import TermConfig  # noqa: E402
from src.service import data_service  # noqa: E402
from tests.conftest import make_user  # noqa: E402


APPROVED_DEEP_HOPE = (
    "Learners will recognize and appreciate the beauty, order, and purpose "
    "of design in the physical world around them."
)
STORYLINE = "Shaping our world."


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


def _wapef_scheme(db, owner_id, weeks=2):
    """A WAPEF-shaped scheme (subject stated, WAPEF template generated)."""
    scheme = SchemeDB(
        id=generate_id(), owner_id=owner_id, filename="B7 Computing.docx",
        subject="ICT", class_level="Basic 7", term="First Term",
        academic_year="2026/2027", status="uploaded", detection_status="single",
    )
    db.add(scheme)
    db.flush()
    for n in range(1, weeks + 1):
        db.add(WeekDB(
            id=generate_id(), scheme_id=scheme.id, week_number=n,
            start_date=date(2026, 9, 7), end_date=date(2026, 9, 11),
            week_type="instruction", strand="Introduction to Computing",
            sub_strand="Components of Computers and Computer Systems",
            content_standards=[f"B7.1.1.{n}"],
            indicators=[f"B7.1.1.{n}.1 Identify the parts of a computer"],
            resources=["Keyboard"],
        ))
    db.commit()
    return scheme


def _config(scheme_id):
    return TermConfig(
        scheme_of_work_id=scheme_id,
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=2, lesson_duration_minutes=60, class_size=30,
        teaching_days=[0, 2], holidays=[], ai_mode="OFF",
        template_type="GES-style", template_id="tpl-wapef-approved-plan",
        include_special_weeks=False,
        class_level="Basic 7", subject="ICT",
    )


def _wapef_selections():
    from src.engines.wapef_fields import wapef_options
    opts = wapef_options()
    return {
        "wapef_deep_hope": opts["deep_hopes"][0],
        "wapef_storyline": opts["storylines"][0],
        "wapef_through_lines": opts["through_lines"][:2],
        "wapef_gods_story": opts["gods_story"][0],
    }


class TestGeneratePageWapefRace:
    def test_single_row_wapef_reaches_the_stored_lesson(self, db):
        from fastapi.testclient import TestClient

        user = make_user(db)
        scheme = _wapef_scheme(db, user.id)
        config = _config(scheme.id)

        with TestClient(_app(db, user)) as client:
            # 1. Allocation preview — the rows the teacher sees and edits.
            preview = client.post(
                f"/api/generation/{scheme.id}/allocation-preview",
                json=config.model_dump(mode="json"),
            )
            assert preview.status_code == 200, preview.text
            rows = preview.json()["lesson_review"]
            assert rows, "preview returned no review rows"

            # 2. The teacher fills the WAPEF selects on EVERY row and clicks
            #    Confirm & Generate — which first PUTs the drafts exactly as
            #    the Generate page does.
            sel = _wapef_selections()
            drafts = {}
            for row in rows:
                drafts[str(row["lesson_sequence"])] = {
                    "period": row.get("period") or "",
                    "keywords": ["distinctive-keyword"],
                    "other_tlrs": [],
                    "core_competencies": [],
                    "structured_references": [],
                    "remarks": f"Remarks for lesson {row['lesson_sequence']}",
                    **sel,
                }
            put = client.put(
                f"/api/generation/{scheme.id}/lesson-review",
                json={"drafts": drafts},
            )
            assert put.status_code == 200, put.text

            # What the store holds right after the PUT:
            saved = put.json()["drafts"]
            print("\nSTORE AFTER PUT:", {k: sorted(v.keys()) for k, v in saved.items()})

            # 3. Generate.
            gen = client.post(
                f"/api/generation/{scheme.id}/generate",
                json=config.model_dump(mode="json"),
            )
            assert gen.status_code == 200, gen.text
            job_id = gen.json()["job_id"]

            # 4. Read back the persisted lessons.
            got = client.get(f"/api/generation/{job_id}/lessons")
            assert got.status_code == 200, got.text
            lessons = got.json()["lesson_plans"]
            assert len(lessons) == len(rows)

        for lp in lessons:
            print(
                f"lesson {lp['lesson_sequence']}: "
                f"deep_hope={bool(lp['wapef_deep_hope'])} "
                f"storyline={lp['wapef_storyline']!r} "
                f"through={lp['wapef_through_lines']} "
                f"gods={lp['wapef_gods_story']!r} "
                f"remarks={lp['remarks']!r}"
            )
            assert lp["wapef_deep_hope"] == sel["wapef_deep_hope"], (
                f"lesson {lp['lesson_sequence']} lost its Deep Hope"
            )
            assert lp["wapef_storyline"] == sel["wapef_storyline"]
            assert lp["wapef_through_lines"] == sel["wapef_through_lines"]
            assert lp["wapef_gods_story"] == sel["wapef_gods_story"]
            assert lp["remarks"] == f"Remarks for lesson {lp['lesson_sequence']}"
            assert "distinctive-keyword" in lp["keywords"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q", "-s"]))
