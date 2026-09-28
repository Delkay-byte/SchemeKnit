"""
Curriculum Spine, source provenance, and allocation-edit tests.

Covers the curriculum-grounded lesson workspace foundation:

  CURRICULUM
    - extraction review status per week (ok / needs_review / special)
    - teacher-facing review reasons (never raw parser diagnostics)
    - spine persistence shape + content version (source replacement)
    - empty / uncertain weeks are first-class states, never fabricated

  PROVENANCE
    - "why this lesson" record (source week, indicator, generation)
    - serialized lessons carry provenance
    - cross-user denial on the provenance endpoint

  ALLOCATION
    - teacher-editable per-lesson period flows through the review draft
      into the built lesson; source fields stay authoritative
"""

import os
import sys
from datetime import date, timedelta

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import make_user, make_school  # noqa: E402
from src.database import (  # noqa: E402
    SchemeDB, WeekDB, LessonPlanDB, GenerationJobDB, generate_id,
)
from src.routers import documents, curriculum, generation  # noqa: E402
from src.curriculum.spine import (  # noqa: E402
    build_curriculum_spine, classify_week_review, lesson_provenance,
    spine_version, REVIEW_OK, REVIEW_NEEDS_REVIEW, REVIEW_SPECIAL,
)


# ── Fixtures / helpers ──────────────────────────────────────────────────────

def make_scheme(db, owner_id, *, subject="Science", class_level="Basic 9",
                filename="B9 Science Term 1.docx", detection_status="single"):
    scheme = SchemeDB(
        id=generate_id(), owner_id=owner_id,
        filename=filename, subject=subject, class_level=class_level,
        term="First Term", academic_year="2026/2027",
        status="uploaded", detection_status=detection_status,
    )
    db.add(scheme)
    db.flush()
    return scheme


def add_week(db, scheme_id, n, *, week_type="instruction", indicators=None,
             strand="Diversity of Matter", sub_strand="Elements",
             standards=None, resources=None):
    # WeekENDING dates are week N's Monday + 7*(N-1) days — computed with
    # timedelta so week numbers above 5 stay valid (a January day-math bug
    # previously broke helpers using weeks 9/13, the mixed-midterm shape).
    start = date(2026, 1, 5) + timedelta(days=7 * (n - 1))
    w = WeekDB(
        id=generate_id(), scheme_id=scheme_id, week_number=n,
        week_type=week_type, start_date=start, end_date=start,
        strand=strand, sub_strand=sub_strand,
        content_standards=standards if standards is not None else ["B9.1.1.1 Matter"],
        indicators=indicators if indicators is not None else ["B9.1.1.1.1 Describe matter."],
        resources=resources or [],
    )
    db.add(w)
    db.flush()
    return w


# ── CURRICULUM: extraction review status ────────────────────────────────────

class TestExtractionReviewStatus:
    def test_complete_instructional_week_is_ok(self):
        w = WeekDB(week_number=1, week_type="instruction", start_date=date(2026, 1, 5),
                   end_date=date(2026, 1, 11), strand="S", sub_strand="Sub",
                   content_standards=["C"], indicators=["B9.1.1.1.1 Do it."])
        status, reasons = classify_week_review(w)
        assert status == REVIEW_OK
        assert reasons == []

    def test_instructional_week_without_indicators_needs_review(self):
        w = WeekDB(week_number=2, week_type="instruction", start_date=date(2026, 1, 5),
                   end_date=date(2026, 1, 11), strand="S", sub_strand="Sub",
                   content_standards=["C"], indicators=[])
        status, reasons = classify_week_review(w)
        assert status == REVIEW_NEEDS_REVIEW
        assert any("indicator" in r.lower() for r in reasons)

    def test_instructional_week_without_framing_needs_review(self):
        w = WeekDB(week_number=3, week_type="instruction", start_date=date(2026, 1, 5),
                   end_date=date(2026, 1, 11), strand="", sub_strand="",
                   content_standards=[], indicators=["B9.1.1.1.1 Do it."])
        status, reasons = classify_week_review(w)
        assert status == REVIEW_NEEDS_REVIEW
        assert any("strand" in r.lower() for r in reasons)

    def test_revision_week_is_special_not_needs_review(self):
        """A special period is a real curriculum state, not an extraction failure."""
        w = WeekDB(week_number=6, week_type="revision", start_date=date(2026, 1, 5),
                   end_date=date(2026, 1, 11), strand="", sub_strand="",
                   content_standards=[], indicators=[])
        status, reasons = classify_week_review(w)
        assert status == REVIEW_SPECIAL
        assert reasons == []

    def test_review_reasons_are_teacher_facing(self):
        """No parser jargon (confidence scores, fallback paths) in the UI reasons."""
        w = WeekDB(week_number=4, week_type="instruction", start_date=date(2026, 1, 5),
                   end_date=date(2026, 1, 11), strand="", sub_strand="",
                   content_standards=[], indicators=[])
        _, reasons = classify_week_review(w)
        joined = " ".join(reasons).lower()
        for jargon in ("confidence", "parser", "fallback", "malformed", "score"):
            assert jargon not in joined


class TestSpineShape:
    def test_spine_counts_and_labels(self, db):
        user = make_user(db)
        scheme = make_scheme(db, user.id)
        add_week(db, scheme.id, 1, indicators=["B9.1.1.1.1 A", "B9.1.1.1.2 B"])
        add_week(db, scheme.id, 2, week_type="revision", indicators=[])
        add_week(db, scheme.id, 3, indicators=[])  # uncertain
        db.commit()

        spine = build_curriculum_spine(scheme)
        assert spine["subject"] == "Science"
        assert spine["summary"]["total_weeks"] == 3
        assert spine["summary"]["instructional_weeks"] == 2
        assert spine["summary"]["special_weeks"] == 1
        assert spine["summary"]["indicator_count"] == 2
        assert spine["summary"]["needs_review_weeks"] == 1
        assert spine["source"]["filename"] == "B9 Science Term 1.docx"

        week1 = spine["weeks"][0]
        assert week1["week_type_label"] == "Instruction"
        assert week1["indicator_count"] == 2
        assert week1["indicators"][0]["code"] == "B9.1.1.1.1"
        assert week1["review_status"] == REVIEW_OK
        assert spine["weeks"][1]["week_type_label"] == "Revision"
        assert spine["weeks"][1]["review_status"] == REVIEW_SPECIAL
        assert spine["weeks"][2]["review_status"] == REVIEW_NEEDS_REVIEW

    def test_spine_version_stable_for_same_content(self, db):
        user = make_user(db)
        s1 = make_scheme(db, user.id, filename="a.docx")
        add_week(db, s1.id, 1)
        db.commit()
        first = spine_version(s1)
        assert spine_version(s1) == first

    def test_spine_version_changes_on_source_replacement(self, db):
        """Replacing the source curriculum must change the version (no stale cache)."""
        user = make_user(db)
        scheme = make_scheme(db, user.id)
        add_week(db, scheme.id, 1, indicators=["B9.1.1.1.1 Original"])
        db.commit()
        before = spine_version(scheme)

        # The teacher replaces the source: week 1 now carries different content.
        week = db.query(WeekDB).filter(WeekDB.scheme_id == scheme.id).first()
        week.indicators = ["B9.1.1.1.9 Replacement"]
        db.commit()
        db.refresh(scheme)
        assert spine_version(scheme) != before

    def test_spine_version_changes_on_filename_change(self, db):
        user = make_user(db)
        scheme = make_scheme(db, user.id, filename="first.docx")
        add_week(db, scheme.id, 1)
        db.commit()
        before = spine_version(scheme)
        scheme.filename = "second.docx"
        db.commit()
        assert spine_version(scheme) != before


class TestSpineEndpointAuthorization:
    @pytest.mark.asyncio
    async def test_owner_can_read_spine(self, db):
        user = make_user(db)
        scheme = make_scheme(db, user.id)
        add_week(db, scheme.id, 1)
        db.commit()
        spine = await curriculum.get_curriculum_spine(scheme.id, user, db)
        assert spine["scheme_id"] == scheme.id
        assert spine["weeks"][0]["week_number"] == 1

    @pytest.mark.asyncio
    async def test_other_user_denied(self, db):
        a = make_user(db, email="a@spine.test")
        b = make_user(db, email="b@spine.test")
        scheme = make_scheme(db, a.id)
        add_week(db, scheme.id, 1)
        db.commit()
        with pytest.raises(HTTPException) as e:
            await curriculum.get_curriculum_spine(scheme.id, b, db)
        assert e.value.status_code in (403, 404)

    @pytest.mark.asyncio
    async def test_unknown_scheme_404(self, db):
        user = make_user(db)
        with pytest.raises(HTTPException) as e:
            await curriculum.get_curriculum_spine("does-not-exist", user, db)
        assert e.value.status_code == 404


class TestWeeksEndpointCarriesReviewStatus:
    @pytest.mark.asyncio
    async def test_weeks_include_review_status(self, db):
        user = make_user(db)
        scheme = make_scheme(db, user.id)
        add_week(db, scheme.id, 1, indicators=["B9.1.1.1.1 A"])
        add_week(db, scheme.id, 2, indicators=[])  # uncertain
        db.commit()
        payload = await documents.get_scheme_weeks(scheme.id, user, db)
        weeks = {w["week_number"]: w for w in payload["weeks"]}
        assert weeks[1]["review_status"] == REVIEW_OK
        assert weeks[2]["review_status"] == REVIEW_NEEDS_REVIEW
        assert weeks[2]["review_reasons"]
        assert weeks[1]["week_type_label"] == "Instruction"


# ── PROVENANCE ──────────────────────────────────────────────────────────────

def _lesson(scheme_id, **over):
    base = dict(
        id=generate_id(), job_id="job-1", owner_id="owner", scheme_id=scheme_id,
        week_number=5, lesson_sequence=2, class_level="Basic 9", subject="Science",
        strand="Diversity of Matter", sub_strand="Elements",
        content_standard="B9.1.1 Demonstrate understanding",
        content_standard_code="B9.1.1",
        indicators=["B7.2.1.1.2 Discuss the formation of rocks."],
        indicator_codes=["B7.2.1.1.2"], teaching_week=6, period="Wednesday · Period 2",
    )
    base.update(over)
    return LessonPlanDB(**base)


class TestLessonProvenance:
    def test_provenance_records_source_and_indicator(self, db):
        user = make_user(db)
        scheme = make_scheme(db, user.id, filename="My_B7_Maths_Term1.docx")
        lp = _lesson(scheme.id)
        prov = lesson_provenance(lp, scheme)
        assert prov["scheme"] == "My_B7_Maths_Term1.docx"
        assert prov["source_week"] == 5
        assert prov["teaching_week"] == 6
        assert prov["indicator"] == "B7.2.1.1.2"
        assert "rocks" in prov["indicator_text"]
        assert prov["curriculum_source"] == "Teacher scheme"
        assert prov["generation"] == "Curriculum-first (deterministic)"

    def test_provenance_reports_ai_enrichment_honestly(self, db):
        user = make_user(db)
        scheme = make_scheme(db, user.id)
        lp = _lesson(scheme.id, ai_generated=True)
        prov = lesson_provenance(lp, scheme, ai_active=True, ai_provider="Gemini")
        assert prov["generation"] == "Curriculum-first + AI enrichment"
        assert prov["ai_provider"] == "Gemini"

    def test_provenance_without_scheme_is_still_truthful(self):
        """A missing source is stated as empty, never fabricated."""
        lp = _lesson("scheme-x")
        prov = lesson_provenance(lp, None)
        assert prov["scheme"] == ""
        assert prov["source_week"] == 5
        assert prov["indicator"] == "B7.2.1.1.2"
        # With no source we cannot claim the week is fine: "unknown", not "ok".
        assert prov["source_review_status"] is None
        assert prov["source_review_reasons"] == []

    def test_provenance_reports_source_week_review_state(self, db):
        """A lesson built from an uncertain week says so (Pattern 6)."""
        user = make_user(db)
        scheme = make_scheme(db, user.id)
        add_week(db, scheme.id, 1, indicators=["B7.2.1.1.2 Discuss rocks."])
        add_week(db, scheme.id, 2, strand="", sub_strand="", standards=[],
                 indicators=["B7.2.1.1.3 Draw rocks."])  # framing not read
        db.commit()

        ok_prov = lesson_provenance(_lesson(scheme.id, week_number=1), scheme)
        assert ok_prov["source_review_status"] == REVIEW_OK
        assert ok_prov["source_review_reasons"] == []

        prov = lesson_provenance(_lesson(scheme.id, week_number=2), scheme)
        assert prov["source_review_status"] == REVIEW_NEEDS_REVIEW
        assert any("strand" in r.lower() for r in prov["source_review_reasons"])

    def test_provenance_special_week_is_not_a_review_failure(self, db):
        user = make_user(db)
        scheme = make_scheme(db, user.id)
        add_week(db, scheme.id, 3, week_type="revision", indicators=[])
        db.commit()
        prov = lesson_provenance(_lesson(scheme.id, week_number=3), scheme)
        assert prov["source_review_status"] == REVIEW_SPECIAL
        assert prov["source_review_reasons"] == []

    def test_serialized_lesson_carries_provenance(self, db):
        user = make_user(db)
        scheme = make_scheme(db, user.id, filename="src.docx")
        lp = _lesson(scheme.id)
        out = generation._serialize_lesson(lp, scheme)
        assert out["provenance"]["scheme"] == "src.docx"
        assert out["provenance"]["source_week"] == 5

    @pytest.mark.asyncio
    async def test_provenance_endpoint_owner_enforced(self, db):
        a = make_user(db, email="a@prov.test")
        b = make_user(db, email="b@prov.test")
        scheme = make_scheme(db, a.id)
        job = GenerationJobDB(id=generate_id(), owner_id=a.id, scheme_id=scheme.id,
                              status="completed", completed_lessons=1)
        db.add(job)
        db.flush()
        lp = _lesson(scheme.id, job_id=job.id, owner_id=a.id)
        db.add(lp)
        db.commit()

        prov = await generation.get_lesson_provenance(lp.id, a, db)
        assert prov["source_week"] == 5

        with pytest.raises(HTTPException) as e:
            await generation.get_lesson_provenance(lp.id, b, db)
        assert e.value.status_code == 404


# ── ALLOCATION: teacher-editable period, authoritative source ───────────────

class TestAllocationPeriodEditing:
    def test_period_draft_is_persisted_and_applied(self, db):
        from src.service import data_service
        from src.models import LessonPlan
        user = make_user(db)
        scheme = make_scheme(db, user.id)
        add_week(db, scheme.id, 1)
        db.commit()

        store = data_service.save_lesson_review_draft(
            db, scheme.id, user.id, "2",
            {"period": "Wednesday · Period 2", "keywords": ["matter"]},
        )
        assert store["2"]["period"] == "Wednesday · Period 2"

        lp = LessonPlan(
            scheme_of_work_id=scheme.id, term_config_id="t",
            week_number=1, lesson_sequence=2, lesson_date=date(2026, 1, 7),
        )
        generation._apply_lesson_review_draft(lp, store)
        assert lp.period == "Wednesday · Period 2"
        assert lp.keywords == ["matter"]

    def test_source_fields_still_not_writable_through_drafts(self, db):
        from src.service import data_service
        user = make_user(db)
        scheme = make_scheme(db, user.id)
        db.commit()
        store = data_service.save_lesson_review_draft(
            db, scheme.id, user.id, "1",
            {"indicator_code": "HACK", "strand": "HACK", "period": "P1"},
        )
        assert "indicator_code" not in store["1"]
        assert "strand" not in store["1"]
        assert store["1"]["period"] == "P1"

    @pytest.mark.asyncio
    async def test_allocation_preview_carries_provenance_and_period(self, db):
        """The allocation preview is the teacher's allocation + provenance view."""
        from src.models import TermConfig
        from src.routers.generation import preview_allocation
        from src.service import data_service

        user = make_user(db)
        scheme = make_scheme(db, user.id, filename="Maths Term1.docx")
        add_week(db, scheme.id, 1,
                 strand="Number", sub_strand="Fractions",
                 standards=["B7.2.1.1 Compare fractions"],
                 indicators=["B7.2.1.1.1 Compare fractions with unlike denominators."])
        db.commit()
        config = TermConfig(
            scheme_of_work_id=scheme.id,
            term_start_date=date(2026, 1, 5),
            term_end_date=date(2026, 4, 10),
            lessons_per_week=3,
            lesson_duration_minutes=60,
            class_size=24,
            teaching_days=[0, 2, 4],
            holidays=[],
            ai_mode="OFF",
            template_type="GES-style",
            include_special_weeks=False,
            class_level="Basic 7",
            subject="Mathematics",
        )
        report = await preview_allocation(scheme.id, config, user, db)
        rows = report["lesson_review"]
        assert rows, "preview produced no lesson review rows"
        row = rows[0]
        prov = row["source_provenance"]
        assert prov["scheme"] == "Maths Term1.docx"
        assert prov["source_week"] == 1
        assert prov["indicator"] == "B7.2.1.1.1"
        assert prov["curriculum_source"] == "Teacher scheme"

        # A teacher-adjusted period is saved against the real lesson_sequence
        # and round-trips back into the preview (and into the built lesson).
        data_service.save_lesson_review_draft(
            db, scheme.id, user.id, str(row["lesson_sequence"]),
            {"period": "Monday Period 1"})
        report2 = await preview_allocation(scheme.id, config, user, db)
        assert report2["lesson_review"][0]["period"] == "Monday Period 1"

    @pytest.mark.asyncio
    async def test_allocation_preview_exposes_review_state(self, db):
        """Uncertain weeks and unplaced allocations are visible before generating."""
        from src.models import TermConfig
        from src.routers.generation import preview_allocation

        user = make_user(db)
        scheme = make_scheme(db, user.id)
        add_week(db, scheme.id, 1, indicators=["B7.2.1.1.1 Compare fractions."])
        add_week(db, scheme.id, 2, strand="", sub_strand="", standards=[],
                 indicators=["B7.2.1.1.2 Order fractions."])  # framing not read
        db.commit()

        config = TermConfig(
            scheme_of_work_id=scheme.id,
            term_start_date=date(2026, 1, 5),
            term_end_date=date(2026, 4, 10),
            lessons_per_week=3,
            lesson_duration_minutes=60,
            class_size=24,
            teaching_days=[0, 2, 4],
            holidays=[],
            ai_mode="OFF",
            template_type="GES-style",
            include_special_weeks=False,
            class_level="Basic 7",
            subject="Mathematics",
        )
        report = await preview_allocation(scheme.id, config, user, db)
        rows = {r["source_week"]: r for r in report["lesson_review"]}
        assert rows[1]["source_provenance"]["source_review_status"] == REVIEW_OK
        assert rows[1]["needs_review"] is False
        assert rows[2]["source_provenance"]["source_review_status"] == REVIEW_NEEDS_REVIEW
        assert isinstance(rows[2]["needs_review"], bool)
