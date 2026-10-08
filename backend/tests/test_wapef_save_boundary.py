"""
WAPEF save-boundary regression tests (A–H).

The production defect: WAPEF selections made on the Generate page's review
rows did not reliably reach the stored lesson. The generate flow is a
TWO-request sequence — PUT /lesson-review (save drafts) then POST /generate
(build lessons FROM the saved drafts). Three failure windows existed around
that boundary:

1. FRONTEND STALE STATE — the save payload was built from a component-scope
   array that a just-committed edit had not yet re-rendered (stale closure),
   so the PUT silently dropped the teacher's latest selections.
2. FRONTEND FIRE-AND-FORGET — generation was allowed to proceed after a save
   failure, persisting lessons from the previous (empty) draft store.
3. BACKEND DRAFT-MAP REPLACEMENT — ``save_lesson_review_drafts`` REPLACED the
   whole store, so any payload that omitted lessons (partial hydration,
   paginated review) erased other lessons' saved selections.

Fixes: (a) the Generate page builds the payload from the exact rows on
screen, passes them explicitly, and AWAITS the persisted PUT before issuing
POST /generate (a save failure cancels generation); (b) the backend merges
the incoming draft map into the committed store and re-reads the store at
generate time through a session refresh (never an identity-map snapshot).

Each test below names the window it closes.
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


def _wapef_scheme(db, owner_id, weeks=2):
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


def _distinct_selections(offset: int = 0):
    """Distinctive, non-default approved values for ALL FOUR WAPEF fields."""
    from src.engines.wapef_fields import wapef_options
    opts = wapef_options()
    hopes = opts["deep_hopes"] or [""]
    lines = opts["through_lines"]
    return {
        "wapef_deep_hope": hopes[offset % len(hopes)],
        "wapef_storyline": opts["storylines"][0],
        "wapef_through_lines": [
            lines[(offset + i) % len(lines)] for i in range(min(3, len(lines)))
        ],
        "wapef_gods_story": opts["gods_story"][(offset + 1) % len(opts["gods_story"])],
    }


class TestAWapefSaveBoundary:
    """A. Generate-page payload: selections in → payload contains exactly those."""

    def test_preview_rows_carry_saved_selections_back_to_the_ui(self, db):
        from fastapi.testclient import TestClient

        user = make_user(db)
        scheme = _wapef_scheme(db, user.id)
        sel = _distinct_selections()
        data_service.save_lesson_review_drafts(db, scheme.id, user.id, {
            "1": {**sel, "remarks": "row 1"},
            "2": {**sel, "remarks": "row 2"},
        })

        with TestClient(_app(db, user)) as client:
            preview = client.post(
                f"/api/generation/{scheme.id}/allocation-preview",
                json=_config(scheme.id).model_dump(mode="json"),
            )
            assert preview.status_code == 200, preview.text
        rows = {r["lesson_sequence"]: r for r in preview.json()["lesson_review"]}
        for seq in (1, 2):
            row = rows[seq]
            assert row["wapef_deep_hope"] == sel["wapef_deep_hope"]
            assert row["wapef_storyline"] == sel["wapef_storyline"]
            assert row["wapef_gods_story"] == sel["wapef_gods_story"]
            assert row["wapef_through_lines"] == sel["wapef_through_lines"]
            assert row["remarks"] == f"row {seq}"


class TestBWapefPersistence:
    """B. Selections → stored lesson contains exactly those values."""

    def test_generate_persists_all_four_fields_for_every_lesson(self, db):
        from fastapi.testclient import TestClient

        user = make_user(db)
        scheme = _wapef_scheme(db, user.id, weeks=3)
        config = _config(scheme.id)

        with TestClient(_app(db, user)) as client:
            preview = client.post(
                f"/api/generation/{scheme.id}/allocation-preview",
                json=config.model_dump(mode="json"),
            ).json()
            rows = preview["lesson_review"]
            sel = _distinct_selections()
            drafts = {
                str(r["lesson_sequence"]): {
                    "period": "", "keywords": [], "other_tlrs": [],
                    "core_competencies": [], "structured_references": [],
                    "remarks": f"R{r['lesson_sequence']}", **sel,
                } for r in rows
            }
            assert client.put(
                f"/api/generation/{scheme.id}/lesson-review",
                json={"drafts": drafts},
            ).status_code == 200

            gen = client.post(
                f"/api/generation/{scheme.id}/generate",
                json=config.model_dump(mode="json"),
            )
            assert gen.status_code == 200, gen.text
            job_id = gen.json()["job_id"]

            lessons = client.get(f"/api/generation/{job_id}/lessons").json()["lesson_plans"]
        assert len(lessons) == len(rows)
        for lp in lessons:
            assert lp["wapef_deep_hope"] == sel["wapef_deep_hope"]
            assert lp["wapef_storyline"] == sel["wapef_storyline"]
            assert lp["wapef_gods_story"] == sel["wapef_gods_story"]
            assert lp["wapef_through_lines"] == sel["wapef_through_lines"]
            assert lp["remarks"] == f"R{lp['lesson_sequence']}"


class TestCWapefReload:
    """C. Persisted lesson → API read → frontend model preserves all four."""

    def test_api_read_back_preserves_all_four_fields_verbatim(self, db):
        from fastapi.testclient import TestClient

        user = make_user(db)
        scheme = _wapef_scheme(db, user.id)
        config = _config(scheme.id)
        sel = _distinct_selections()

        with TestClient(_app(db, user)) as client:
            client.post(f"/api/generation/{scheme.id}/allocation-preview",
                        json=config.model_dump(mode="json"))
            client.put(f"/api/generation/{scheme.id}/lesson-review",
                       json={"drafts": {"1": {**sel}, "2": {**sel}}})
            job_id = client.post(
                f"/api/generation/{scheme.id}/generate",
                json=config.model_dump(mode="json"),
            ).json()["job_id"]

            # Single-lesson read (the review page's path) ...
            one = client.get(f"/api/generation/{job_id}/lessons").json()["lesson_plans"][0]
            single = client.get(f"/api/generation/lessons/{one['id']}").json()
            # ... and the job listing (the workspace's path).
            listed = client.get(f"/api/generation/{job_id}/lessons").json()["lesson_plans"]

        for lp in [single, *listed]:
            assert lp["wapef_deep_hope"] == sel["wapef_deep_hope"]
            assert lp["wapef_storyline"] == sel["wapef_storyline"]
            assert lp["wapef_gods_story"] == sel["wapef_gods_story"]
            assert lp["wapef_through_lines"] == sel["wapef_through_lines"]


class TestDZeliPreservationContract:
    """D. Zeli rewrite must never touch the four WAPEF fields.

    The rewrite endpoint never writes WAPEF fields at all (they are not
    rewriteable sections); the pipeline snapshots/restores them around any AI
    content application. Pinned here so a future regression fails loudly.
    """

    def test_regenerate_section_is_rejected_for_wapef_fields(self, db):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.auth import get_current_user
        from src.database import get_db
        from src.routers import ai_regeneration as ai_router
        from tests.test_export_download import make_job_with_lessons
        from src.database import LessonPlanDB

        user = make_user(db)
        _scheme, job = make_job_with_lessons(db, user, lessons=1)
        lp = db.query(LessonPlanDB).filter_by(job_id=job.id).first()

        app = FastAPI()
        app.include_router(ai_router.router, prefix="/api/ai")
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: db
        with TestClient(app) as client:
            r = client.post("/api/ai/regenerate-section", json={
                "lesson_plan_id": lp.id,
                "section": "wapef_deep_hope",
                "ai_mode": "OFF",
            })
        assert r.status_code == 400, "a WAPEF field must never be a rewriteable section"

    def test_apply_lesson_review_draft_never_blanks_a_set_field(self, db):
        from src.routers.generation import _apply_lesson_review_draft

        sel = _distinct_selections()
        lp = type("LP", (), {})()  # bare object; only WAPEF attrs are touched
        for k, v in sel.items():
            setattr(lp, k, v)
        lp.lesson_sequence = 1
        lp.indicator_codes = []
        lp.remarks = "teacher text"
        lp.period = ""
        lp.keywords = []
        lp.other_tlrs = []
        lp.teaching_learning_resources = []
        lp.core_competencies = []
        lp.structured_references = []
        lp.references = []

        # A draft WITHOUT WAPEF keys (e.g. a later keywords-only edit) must
        # leave the four fields byte-identical.
        _apply_lesson_review_draft(lp, {"1": {"keywords": ["added"]}})
        assert lp.wapef_deep_hope == sel["wapef_deep_hope"]
        assert lp.wapef_storyline == sel["wapef_storyline"]
        assert lp.wapef_gods_story == sel["wapef_gods_story"]
        assert lp.wapef_through_lines == sel["wapef_through_lines"]


class TestEWapefDocxExport:
    """E. Stored lesson with all four fields → DOCX → all four present."""

    def test_docx_export_carries_all_four_wapef_fields(self, db, tmp_path):
        from fastapi.testclient import TestClient

        user = make_user(db)
        scheme = _wapef_scheme(db, user.id)
        config = _config(scheme.id)
        sel = _distinct_selections()

        with TestClient(_app(db, user)) as client:
            client.post(f"/api/generation/{scheme.id}/allocation-preview",
                        json=config.model_dump(mode="json"))
            client.put(f"/api/generation/{scheme.id}/lesson-review",
                       json={"drafts": {"1": {**sel}, "2": {**sel}}})
            job_id = client.post(
                f"/api/generation/{scheme.id}/generate",
                json=config.model_dump(mode="json"),
            ).json()["job_id"]

            dl = client.post(f"/api/generation/{job_id}/export/docx?template_id=tpl-wapef-approved-plan")
            assert dl.status_code == 200, dl.text
            assert dl.headers["content-type"].startswith(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            raw = dl.content

        # DOCX integrity: a real PK/ZIP package.
        import io, zipfile
        zf = zipfile.ZipFile(io.BytesIO(raw))
        assert zf.testzip() is None
        from docx import Document
        doc = Document(io.BytesIO(raw))
        text = "\n".join(p.text for p in doc.paragraphs)
        for t in doc.tables:
            for row in t.rows:
                for cell in row.cells:
                    text += "\n" + cell.text
        assert sel["wapef_deep_hope"][:40] in text
        assert sel["wapef_storyline"] in text
        assert sel["wapef_gods_story"] in text
        for line in sel["wapef_through_lines"]:
            assert line in text


class TestFWapefPdfExport:
    """F. Stored lesson with all four fields → PDF → all four present."""

    def test_pdf_export_carries_all_four_wapef_fields(self, db, tmp_path):
        from fastapi.testclient import TestClient

        user = make_user(db)
        scheme = _wapef_scheme(db, user.id)
        config = _config(scheme.id)
        sel = _distinct_selections()

        with TestClient(_app(db, user)) as client:
            client.post(f"/api/generation/{scheme.id}/allocation-preview",
                        json=config.model_dump(mode="json"))
            client.put(f"/api/generation/{scheme.id}/lesson-review",
                       json={"drafts": {"1": {**sel}, "2": {**sel}}})
            job_id = client.post(
                f"/api/generation/{scheme.id}/generate",
                json=config.model_dump(mode="json"),
            ).json()["job_id"]

            dl = client.post(f"/api/generation/{job_id}/export/pdf?template_id=tpl-wapef-approved-plan")
            assert dl.status_code == 200, dl.text
            assert dl.headers["content-type"] == "application/pdf"
            raw = dl.content

        # PDF integrity: real %PDF header.
        assert raw[:5] == b"%PDF-"
        pypdf = pytest.importorskip("pypdf")
        import io
        reader = pypdf.PdfReader(io.BytesIO(raw))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        compact = " ".join(text.split())
        assert sel["wapef_deep_hope"][:40].replace(" ", "") in compact.replace(" ", "")
        assert "Shaping our world." in compact
        assert sel["wapef_gods_story"] in compact
        for line in sel["wapef_through_lines"]:
            assert line in compact


class TestGEmptyStateSemantics:
    """G. No WAPEF selection → valid existing behaviour unchanged."""

    def test_omitted_wapef_fields_stay_empty_and_generation_succeeds(self, db):
        from fastapi.testclient import TestClient

        user = make_user(db)
        scheme = _wapef_scheme(db, user.id)
        config = _config(scheme.id)

        with TestClient(_app(db, user)) as client:
            preview = client.post(
                f"/api/generation/{scheme.id}/allocation-preview",
                json=config.model_dump(mode="json"),
            ).json()
            drafts = {
                str(r["lesson_sequence"]): {
                    "period": "", "keywords": ["kw"], "other_tlrs": [],
                    "core_competencies": [], "structured_references": [],
                    "remarks": "",
                } for r in preview["lesson_review"]
            }
            assert client.put(
                f"/api/generation/{scheme.id}/lesson-review",
                json={"drafts": drafts}).status_code == 200
            job_id = client.post(
                f"/api/generation/{scheme.id}/generate",
                json=config.model_dump(mode="json"),
            ).json()["job_id"]
            lessons = client.get(f"/api/generation/{job_id}/lessons").json()["lesson_plans"]

        assert lessons
        for lp in lessons:
            # No selection → genuinely empty, never an invented default.
            assert lp["wapef_deep_hope"] == ""
            assert lp["wapef_storyline"] == ""
            assert lp["wapef_gods_story"] == ""
            assert lp["wapef_through_lines"] == []
            # The non-WAPEF draft field still applied (drafts still work).
            assert "kw" in lp["keywords"]


class TestHRepeatSaveReload:
    """H. Generate/save → reload → save again → WAPEF unchanged."""

    def test_second_save_after_reload_keeps_selections_byte_identical(self, db):
        from fastapi.testclient import TestClient

        user = make_user(db)
        scheme = _wapef_scheme(db, user.id)
        config = _config(scheme.id)
        sel = _distinct_selections()

        with TestClient(_app(db, user)) as client:
            client.post(f"/api/generation/{scheme.id}/allocation-preview",
                        json=config.model_dump(mode="json"))
            client.put(f"/api/generation/{scheme.id}/lesson-review",
                       json={"drafts": {"1": {**sel}, "2": {**sel}}})
            first = client.post(
                f"/api/generation/{scheme.id}/generate",
                json=config.model_dump(mode="json"),
            ).json()
            job1 = client.get(f"/api/generation/{first['job_id']}/lessons").json()["lesson_plans"]

            # "Reload": a brand-new preview read of the drafts.
            again = client.get(f"/api/generation/{scheme.id}/lesson-review").json()["drafts"]
            assert again["1"]["wapef_deep_hope"] == sel["wapef_deep_hope"]

            # Save again — the same map, re-sent exactly as the page would.
            client.put(f"/api/generation/{scheme.id}/lesson-review",
                       json={"drafts": {"1": {**sel}, "2": {**sel}}})
            second = client.post(
                f"/api/generation/{scheme.id}/generate",
                json=config.model_dump(mode="json"),
            ).json()
            # Priority 3 merge semantics: every run re-homes the scheme's
            # lesson set onto its NEW job (workspace/status/coverage/exports
            # always read the latest job), so the read-back goes through the
            # second run's job id — not the first's.
            job2 = client.get(
                f"/api/generation/{second['job_id']}/lessons"
            ).json()["lesson_plans"]

        def _snap(lps):
            return [(l["lesson_sequence"], l["wapef_deep_hope"], l["wapef_storyline"],
                     l["wapef_gods_story"], tuple(l["wapef_through_lines"])) for l in lps]

        # Regeneration re-applied the same selections — byte-identical.
        assert _snap(job1) == _snap(job2)
        for _, deep, story, gods, lines in _snap(job2):
            assert deep == sel["wapef_deep_hope"]
            assert story == sel["wapef_storyline"]
            assert gods == sel["wapef_gods_story"]
            assert lines == tuple(sel["wapef_through_lines"])

    def test_partial_payload_never_erases_other_lessons_selections(self, db):
        """The replacement-window regression: a partial PUT must MERGE."""
        user = make_user(db)
        scheme = _wapef_scheme(db, user.id)
        sel = _distinct_selections()
        data_service.save_lesson_review_drafts(db, scheme.id, user.id, {
            "1": {**sel}, "2": {**sel},
        })
        # Later partial save (only lesson 1, e.g. a paginated review):
        data_service.save_lesson_review_drafts(db, scheme.id, user.id, {
            "1": {"remarks": "updated only"},
        })
        store = data_service.get_lesson_review_drafts(db, scheme.id, user.id)
        assert "2" in store, "the partial PUT erased lesson 2's saved selections"
        assert store["2"]["wapef_deep_hope"] == sel["wapef_deep_hope"]
        assert store["1"]["remarks"] == "updated only"

    def test_generate_reads_the_committed_store_on_the_same_session(self, db):
        """Read-after-write on ONE session must see the just-PUT drafts."""
        user = make_user(db)
        scheme = _wapef_scheme(db, user.id)
        sel = _distinct_selections()
        data_service.save_lesson_review_drafts(db, scheme.id, user.id, {"1": {**sel}})
        # A second save on the SAME session (the FastAPI request-scoped case):
        data_service.save_lesson_review_draft(db, scheme.id, user.id, "2",
                                              {"wapef_deep_hope": sel["wapef_deep_hope"]})
        store = data_service.get_lesson_review_drafts(db, scheme.id, user.id)
        assert set(store) == {"1", "2"}
        assert store["2"]["wapef_deep_hope"] == sel["wapef_deep_hope"]
        assert store["1"]["wapef_gods_story"] == sel["wapef_gods_story"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
