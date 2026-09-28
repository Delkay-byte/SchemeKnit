"""
Real-use remediation tests (post-deployment defect pass).

Covers the ten defects observed after a teacher used the deployed product:

1.  single-subject detection (never "multiple" for one subject)
2.  genuine multi-subject detection
3.  indicator extracted when the source provides it
4.  missing indicator genuinely absent (whole-source, e.g. WAPEF Nursery)
5.  malformed/uncertain indicator classification
6.  Needs-review classification
7.  Needs-review route/navigation data
8.  special-period classification
9.  mixed-week classification (special + teaching in one source row)
10. segmented dates preserved from the source
11. mixed-week allocation (special excluded, teaching allocatable)
12. valid allocation preview (200, well-formed report)
13. Quick Generate allocation path
14. Build-with-me allocation path
15. no AI guessing of missing indicators

The parser-level fixtures mirror the REAL document structures that exposed
the defects (a single-subject BS7 RME scheme; the Week-9 mixed midterm row;
the WAPEF Nursery whole-level scheme) without copying the files themselves.
"""

import asyncio
from datetime import date, timedelta
from pathlib import Path

import pytest

from src.parsers.docx_parser import DOCXParser
from src.models import Week, WeekType, TermConfig
from src.curriculum.spine import (
    build_week_spine,
    classify_week_review,
    scheme_provides_indicators,
    week_special_segments,
    week_teaching_segments,
)
from src.engines.allocation_engine import (
    AllocationEngine,
    reclassify_special_weeks,
    scheme_has_indicators,
    week_is_non_instructional,
)
from src.database import WeekDB

from tests.conftest import make_user
from tests.test_curriculum_spine_and_provenance import make_scheme, add_week


# ── Helpers ──────────────────────────────────────────────────────────────────

def _week_row(n, *, week_type=WeekType.INSTRUCTION, strand=None, sub_strand=None,
              content_standard="", indicators="", resources=""):
    """A parser-level row dict, as _merge_week_rows consumes them."""
    return {
        "week_number": n, "date": None, "week_type": week_type,
        "strand": strand, "sub_strand": sub_strand,
        "content_standard": content_standard,
        "indicators": indicators, "resources": resources,
        "raw_row": [],
    }


def _mk_week(n, *, week_type=WeekType.INSTRUCTION, strand=None, sub_strand=None,
             indicators=None, label="", label_type=""):
    """Week model for classification tests.

    ``strand`` defaults to a populated value (the real WAPEF Nursery rows DO
    carry strand/sub-strand — only the Indicator column is absent), so the
    only review signal left is the missing indicator itself.
    """
    return Week(
        week_number=n, start_date=date(2026, 11, 7), end_date=date(2026, 11, 7),
        week_type=week_type,
        strand=strand if strand is not None else "Numbers",
        sub_strand=sub_strand if sub_strand is not None else "Counting",
        content_standards=[], indicators=indicators or [], resources=[],
        special_period_label=label, special_period_type=label_type,
        scheme_of_work_id="x",
    )


def _calendar_for(week_number, dates):
    from src.models import TeachingCalendar, TeachingDay
    days = [
        TeachingDay(date=d, day_of_week=d.weekday(), is_teaching_day=True,
                    is_holiday=False, week_number=week_number, lesson_slot=i + 1)
        for i, d in enumerate(dates)
    ]
    return TeachingCalendar(term_start=min(dates), term_end=max(dates),
                            teaching_days=list(range(7)), days=days,
                            total_teaching_days=len(dates), total_lessons=len(dates))


VALID_CONFIG = {
    "academic_year": "2026/2027",
    "term": "First Term",
    "class_level": "Basic 7",
    "subject": "Religious and Moral Education",
    "term_start_date": "2026-09-11",
    "term_end_date": "2026-12-18",
    "lessons_per_week": 3,
    "lesson_duration_minutes": 60,
    "class_size": 11,
    "teaching_days": [0, 2, 4],
    "holidays": [],
    "ai_mode": "OFF",
    "template_type": "GES-style",
    "template_id": "",
    "include_special_weeks": False,
    "school_name": "Remediation School",
    "teacher_name": "Remediation Teacher",
    "period": "",
    "keywords": [],
    "teaching_learning_resources": [],
    "core_competencies": [],
    "references": [],
    "selected_indicator_codes": [],
}


def _term_config(scheme_id, **over):
    cfg = {**VALID_CONFIG, "scheme_of_work_id": scheme_id}
    cfg.update(over)
    return TermConfig(**cfg)


# ── Defect 1: subject detection ──────────────────────────────────────────────

class TestSubjectDetection:
    def test_single_subject_document_reports_single(self):
        """A one-subject scheme never classifies as multiple (Defect 1)."""
        parser = DOCXParser()
        # One subject heading + one table of week rows: the structural shape
        # of a single-subject scheme (BS7 RME).
        blocks = [
            ("paragraph", "FIRST TERM SCHEME OF LEARNING FOR BASIC 7 - RELIGIOUS AND MORAL EDUCATION"),
            ("table", [
                ["WEEK", "STRAND", "SUB-STRAND", "CONTENT STANDARD", "INDICATORS", "RESOURCES"],
                ["1", "God", "Nature of God", "B7.1.1.1.1", "B7.1.1.1.1 Explain the nature of God", "Bible"],
                ["2", "God", "Worship", "B7.2.1.1.1", "B7.2.1.1.1 Identify types of worship", "Bible"],
            ]),
        ]
        sections = parser._detect_sections(blocks)
        assert len(sections) == 1
        assert sections[0]["subject"].value == "Religious and Moral Education"

    def test_single_subject_never_flags_metadata_only_multiples(self):
        """Subject-like words in content must not create extra sections."""
        parser = DOCXParser()
        blocks = [
            ("paragraph", "FIRST TERM SCHEME OF LEARNING FOR BASIC 7 - ENGLISH LANGUAGE"),
            ("table", [
                ["WEEK", "STRAND", "SUB-STRAND", "INDICATORS"],
                ["1", "Writing", "Composition", "B7.3.1.1.1 Write about History and Citizenship topics"],
            ]),
        ]
        sections = parser._detect_sections(blocks)
        subjects = [s["subject"] for s in sections if s["subject"] is not None]
        assert subjects == [] or len(subjects) == 1

    def test_genuine_multi_subject_document_reports_multiple(self):
        """Two subject sections with week rows each → two sections (Defect 1)."""
        parser = DOCXParser()
        blocks = [
            ("paragraph", "FIRST TERM SCHEME OF LEARNING FOR BASIC 7 - ENGLISH LANGUAGE"),
            ("table", [
                ["WEEK", "STRAND", "SUB-STRAND", "INDICATORS"],
                ["1", "Writing", "Composition", "B7.3.1.1.1 Write narratives"],
                ["2", "Reading", "Comprehension", "B7.4.1.1.1 Read fluently"],
            ]),
            ("paragraph", "FIRST TERM SCHEME OF LEARNING FOR BASIC 7 - SCIENCE"),
            ("table", [
                ["WEEK", "STRAND", "SUB-STRAND", "INDICATORS"],
                ["1", "Matter", "Elements", "B7.1.1.1.1 Describe materials"],
                ["2", "Matter", "Mixtures", "B7.1.1.2.1 Separate mixtures"],
            ]),
        ]
        sections = parser._detect_sections(blocks)
        subjects = [s["subject"].value for s in sections if s["subject"] is not None]
        assert len(subjects) == 2


# ── Defect 2: indicator extraction states ────────────────────────────────────

class TestIndicatorExtraction:
    def test_indicator_extracted_when_present(self):
        parser = DOCXParser()
        rows = [_week_row(1, strand="God", sub_strand="Nature of God",
                          content_standard="B7.1.1.1.1",
                          indicators="B7.1.1.1.1 Explain the nature of God through His attributes")]
        pw = parser._merge_week_rows(1, rows)
        assert len(pw.indicators) == 1
        assert pw.indicators[0].code == "B7.1.1.1.1"
        assert "nature of God" in pw.indicators[0].description

    def test_multiline_indicator_cell_is_recovered(self):
        """Merged/newline-broken cells keep the full indicator (Defect 2)."""
        parser = DOCXParser()
        rows = [_week_row(6, strand="God", sub_strand="Worship",
                          indicators="B7.2.1.1.1 Identify the types of worship in the three major religions in Ghana")]
        pw = parser._merge_week_rows(6, rows)
        assert pw.indicators[0].code == "B7.2.1.1.1"
        assert "types of worship" in pw.indicators[0].description

    def test_missing_indicator_is_reported_not_fabricated(self):
        """A week with an empty indicator cell yields NO indicator — never a
        copied one from another week (Defect 2/15)."""
        parser = DOCXParser()
        rows = [_week_row(3, strand="Religious practices", sub_strand="Worship",
                          indicators="")]
        pw = parser._merge_week_rows(3, rows)
        assert pw.indicators == []

    def test_genuinely_absent_indicators_whole_scheme(self):
        """WAPEF Nursery shape: NO week carries indicators → the source is the
        authority and the honest state is 'not provided', not 'needs review'
        for every week (Defect 4 of the spec / case B of Defect 7)."""
        weeks = [_mk_week(1), _mk_week(2), _mk_week(3)]
        assert scheme_provides_indicators(weeks) is False

    def test_provided_indicators_detected_whole_scheme(self):
        """Any week with indicators means the source provides the column."""
        weeks = [_mk_week(1, indicators=["B7.1.1.1.1 A"]), _mk_week(2)]
        assert scheme_provides_indicators(weeks) is True


# ── Defect 2/7: review classification ────────────────────────────────────────

class TestReviewClassification:
    def test_week_needs_review_when_source_provides_indicators(self):
        """One week missing indicators among weeks that have them → review."""
        weeks = [_mk_week(1, indicators=["B7.1.1.1.1 A"]), _mk_week(2)]
        status, reasons = classify_week_review(weeks[1], weeks)
        assert status == "needs_review"
        assert any("indicator" in r.lower() for r in reasons)

    def test_nursery_weeks_are_not_flagged_for_missing_indicators(self):
        """A source with no indicator column must not flag every week."""
        weeks = [_mk_week(1), _mk_week(2)]
        status, reasons = classify_week_review(weeks[0], weeks)
        assert status == "ok"
        assert not any("indicator" in r.lower() for r in reasons)

    def test_malformed_indicator_still_counts_as_extracted(self):
        """A mangled-but-present indicator (the production W2 shape) is
        extracted data — the week stays 'ok', never silently 'failed'."""
        weeks = [_mk_week(1, indicators=["1.1.1.1 B7 B7.1.1.1.2 B7.1.1.1.3"])]
        assert classify_week_review(weeks[0])[0] == "ok"
        status, _ = classify_week_review(weeks[0])
        assert status == "ok"

    def test_special_week_classification(self):
        w = _mk_week(13, week_type=WeekType.REVISION, label="REVISION",
                     label_type="revision")
        status, _ = classify_week_review(w)
        assert status == "special"

    def test_mixed_week_classification(self):
        w = _mk_week(9, week_type=WeekType.MIXED, indicators=["B7.2.2.1.1 A"],
                     label="MID-TERM (05-11-2026 to 06-11-2026)",
                     label_type="mid_term")
        status, _ = classify_week_review(w)
        assert status == "mixed"

    def test_review_reasons_are_teacher_facing(self):
        w = _mk_week(3)
        _, reasons = classify_week_review(w)
        joined = " ".join(reasons).lower()
        for jargon in ("confidence", "parser", "fallback", "malformed", "score"):
            assert jargon not in joined


# ── Defect 4/5: mixed weeks + segmented dates ────────────────────────────────

class TestMixedWeeks:
    def test_parser_merges_midterm_and_teaching_rows_as_mixed(self):
        """Week 9 shape: a MID-TERM row and a teaching row share the week."""
        parser = DOCXParser()
        rows = [
            _week_row(9, week_type=WeekType.REVISION,
                      strand="MID-TERM (05-11-2026 to 06-11-2026)",
                      sub_strand="MID-TERM (05-11-2026 to 06-11-2026)",
                      resources="MID-TERM (05-11-2026 to 06-11-2026)"),
            _week_row(9, strand="Materials for production",
                      sub_strand="Resistant materials",
                      content_standard="B7.2.2.1.1",
                      indicators="B7.2.2.1.1 Describe resistant materials.",
                      resources="Charts"),
        ]
        pw = parser._merge_week_rows(9, rows)
        assert pw.week_type == WeekType.MIXED
        assert "MID-TERM" in pw.special_period_label
        assert any(i.code == "B7.2.2.1.1" for i in pw.indicators)
        # The label must never leak into curriculum fields — the TEACHING row's
        # strand/sub-strand are the week's framing (Defect 4/5).
        assert pw.strand == "Materials for production"
        assert pw.sub_strand == "Resistant materials"
        assert "MID-TERM" not in (pw.strand or "")

    def test_midterm_label_never_becomes_indicator(self):
        parser = DOCXParser()
        rows = [_week_row(9, week_type=WeekType.REVISION,
                          strand="MID-TERM (05-11-2026 to 06-11-2026)",
                          sub_strand="MID-TERM (05-11-2026 to 06-11-2026)",
                          resources="MID-TERM (05-11-2026 to 06-11-2026)")]
        pw = parser._merge_week_rows(9, rows)
        assert pw.indicators == []
        assert pw.week_type != WeekType.INSTRUCTION

    def test_reclassify_persisted_label_row_with_teaching(self):
        """A pre-fix persisted week re-classifies to MIXED at allocation time."""
        w = _mk_week(9, indicators=["MID-TERM (05-11-2026 to 06-11-2026)",
                                    "B7.2.2.1.1 Describe resistant materials."],
                     strand="MID-TERM (05-11-2026 to 06-11-2026)")
        reclassify_special_weeks([w])
        assert w.week_type == WeekType.MIXED
        assert w.indicators == ["B7.2.2.1.1 Describe resistant materials."]

    def test_special_segments_preserve_source_dates(self):
        """The MID-TERM span comes from the source label — nothing invented."""
        w = _mk_week(9, week_type=WeekType.MIXED, indicators=["B7.2.2.1.1 A"],
                     label="MID-TERM (05-11-2026 to 06-11-2026)",
                     label_type="mid_term")
        segs = week_special_segments(w)
        assert len(segs) == 1
        assert segs[0]["label"] == "MID-TERM (05-11-2026 to 06-11-2026)"
        assert segs[0]["start"] == "2026-11-05"
        assert segs[0]["end"] == "2026-11-06"
        assert segs[0]["type"] == "mid_term"

    def test_label_without_dates_yields_no_invented_span(self):
        w = _mk_week(13, week_type=WeekType.REVISION, label="REVISION",
                     label_type="revision")
        segs = week_special_segments(w)
        assert segs[0]["start"] is None
        assert segs[0]["end"] is None

    def test_teaching_segments_present(self):
        w = _mk_week(9, week_type=WeekType.MIXED, indicators=["B7.2.2.1.1 A"])
        segs = week_teaching_segments(w)
        assert segs == [{"start": "2026-11-07", "end": "2026-11-07"}]

    def test_week_spine_carries_segments_and_labels(self):
        w = _mk_week(9, week_type=WeekType.MIXED, indicators=["B7.2.2.1.1 A"],
                     label="MID-TERM (05-11-2026 to 06-11-2026)",
                     label_type="mid_term")
        spine = build_week_spine(w)
        assert spine["week_type_label"] == "Mixed week"
        assert spine["special_segments"][0]["start"] == "2026-11-05"
        assert spine["teaching_segments"]


# ── Defect 7/11: mixed week allocation ───────────────────────────────────────

class TestMixedWeekAllocation:
    def test_mixed_week_special_segment_excluded_teaching_allocated(self):
        w = _mk_week(9, week_type=WeekType.MIXED, indicators=["B7.2.2.1.1 Describe resistant materials."],
                     label="MID-TERM (05-11-2026 to 06-11-2026)",
                     label_type="mid_term")
        assert week_is_non_instructional(w) is False
        assert scheme_has_indicators([w]) is True

        cal = _calendar_for(9, [date(2026, 11, 9), date(2026, 11, 11)])
        cfg = TermConfig(scheme_of_work_id="x")
        coverage = AllocationEngine().allocate([w], cal, cfg, False)
        # Exactly ONE lesson: the teaching indicator. The midterm is not one.
        real = [a for a in coverage.allocations if not a.is_special_period]
        assert len(real) == 1
        assert real[0].indicator_code == "B7.2.2.1.1"
        assert not any("MID-TERM" in (a.indicator_description or "") for a in real)

    def test_mixed_week_included_without_special_weeks_flag(self):
        w = _mk_week(9, week_type=WeekType.MIXED, indicators=["B7.2.2.1.1 A"],
                     label="MID-TERM", label_type="mid_term")
        cal = _calendar_for(9, [date(2026, 11, 9)])
        cfg = TermConfig(scheme_of_work_id="x")
        coverage = AllocationEngine().allocate([w], cal, cfg, False)
        real = [a for a in coverage.allocations if not a.is_special_period]
        assert len(real) == 1


# ── Defect 6/7/12/13/14: allocation preview through the endpoint ────────────

class TestAllocationPreviewAPI:
    """Drive the SAME handler the Quick Generate / Build-with-me buttons hit.

    The endpoint is called directly (the project's established pattern for
    router tests) with the exact TermConfig shape the frontend builds — so a
    regression in the preview machinery itself fails here, independent of
    transport.
    """

    def _create_scheme(self, db, user_id, *, weeks_spec=None):
        scheme = make_scheme(db, user_id)
        spec = weeks_spec or [
            (1, "instruction", ["B7.1.1.1.1 Explain the nature of God through His attributes"]),
            (2, "instruction", ["B7.1.1.1.2 Describe ways of demonstrating the attributes"]),
            (3, "instruction", []),
            (9, "mixed", ["B7.2.2.1.1 Describe resistant materials."]),
            (13, "revision", []),
        ]
        for n, wt, inds in spec:
            add_week(db, scheme.id, n, week_type=wt, indicators=inds)
        db.commit()
        return scheme

    def _label(self, db, scheme):
        """Set a special-period label on the mixed/revision week rows."""
        for w in db.query(WeekDB).filter(WeekDB.scheme_id == scheme.id):
            if w.week_type in ("mixed", "revision"):
                w.special_period_label = (
                    "MID-TERM (05-11-2026 to 06-11-2026)"
                    if w.week_type == "mixed" else "REVISION")
                w.special_period_type = (
                    "mid_term" if w.week_type == "mixed" else "revision")
        db.commit()

    @pytest.mark.asyncio
    async def test_valid_preview_succeeds_and_report_is_well_formed(self, db):
        user = make_user(db)
        scheme = self._create_scheme(db, user.id)
        self._label(db, scheme)
        from src.routers import generation
        report = await generation.preview_allocation(
            scheme.id, _term_config(scheme.id), user, db)
        assert "lesson_review" in report
        assert "lesson_quota" in report
        assert report["lesson_review"], "real indicator rows must be present"

    @pytest.mark.asyncio
    async def test_quick_generate_path_preview(self, db):
        """Quick Generate posts the SAME config shape and must succeed."""
        user = make_user(db, email="rem.teacher2@remediation.test")
        scheme = self._create_scheme(db, user.id)
        self._label(db, scheme)
        from src.routers import generation
        report = await generation.preview_allocation(
            scheme.id, _term_config(scheme.id), user, db)
        assert report["total_generated_lessons"] >= 1

    @pytest.mark.asyncio
    async def test_build_with_me_path_preview(self, db):
        """Build with me hits the same endpoint with the same shape."""
        user = make_user(db, email="rem.teacher3@remediation.test")
        scheme = self._create_scheme(db, user.id)
        self._label(db, scheme)
        from src.routers import generation
        report = await generation.preview_allocation(
            scheme.id, _term_config(scheme.id), user, db)
        assert report["coverage_percentage"] >= 0

    def test_empty_date_strings_are_not_a_validation_failure(self):
        """Defect 6 root cause: an emptied date input submits ``""``.

        Pydantic used to reject that with ``body -> term_start_date: Input
        should be a valid date``, which the UI surfaced as "Validation
        failed" on BOTH generate modes. An empty value is "not set" — the
        model accepts it and the term window is derived from the scheme.
        """
        cfg = TermConfig(**{**VALID_CONFIG, "scheme_of_work_id": "x",
                            "term_start_date": "", "term_end_date": ""})
        assert cfg.term_start_date is None
        assert cfg.term_end_date is None

    @pytest.mark.asyncio
    async def test_blank_term_dates_are_derived_from_the_scheme(self, db):
        """Defect 7: a blank term window is filled from the source scheme's
        own curriculum dates — never guessed, never a dead end."""
        user = make_user(db, email="rem.teacher7@remediation.test")
        scheme = self._create_scheme(db, user.id)
        self._label(db, scheme)
        cfg = _term_config(scheme.id)
        cfg.term_start_date = None
        cfg.term_end_date = None
        from src.routers import generation
        report = await generation.preview_allocation(scheme.id, cfg, user, db)
        assert report["lesson_review"], "blank dates must not block allocation"
        starts = [w.start_date for w in db.query(WeekDB)
                  .filter(WeekDB.scheme_id == scheme.id)]
        assert cfg.term_start_date == min(starts)

    @pytest.mark.asyncio
    async def test_empty_date_payload_succeeds_end_to_end(self, db):
        """The literal broken payload the teacher's browser sent now works."""
        user = make_user(db, email="rem.teacher8@remediation.test")
        scheme = self._create_scheme(db, user.id)
        self._label(db, scheme)
        payload = {**VALID_CONFIG, "scheme_of_work_id": scheme.id,
                   "term_start_date": "", "term_end_date": ""}
        cfg = TermConfig(**payload)
        from src.routers import generation
        report = await generation.preview_allocation(scheme.id, cfg, user, db)
        assert report["total_generated_lessons"] >= 1

    @pytest.mark.asyncio
    async def test_needs_review_week_does_not_block_allocation(self, db):
        """Defect 7 case B: weeks with missing indicators must not make the
        whole allocation fail — the payload stays valid."""
        user = make_user(db, email="rem.teacher5@remediation.test")
        scheme = self._create_scheme(db, user.id)  # week 3 has no indicators
        self._label(db, scheme)
        from src.routers import generation
        report = await generation.preview_allocation(
            scheme.id, _term_config(scheme.id), user, db)
        rows = report.get("lesson_review", [])
        review_row = next((r for r in rows if r.get("source_week") == 3), None)
        # Week 3 produced NO lesson row (no indicator to allocate), so nothing
        # blocks; the WEEK-level state is what flags it for review.
        from src.database import WeekDB
        wk = (db.query(WeekDB)
              .filter(WeekDB.scheme_id == scheme.id, WeekDB.week_number == 3)
              .first())
        assert classify_week_review(wk)[0] == "needs_review"

    @pytest.mark.asyncio
    async def test_mixed_week_rows_carry_review_route_data(self, db):
        """Defect 3/7: preview rows expose the source week's review state and
        reasons so the UI can deep-link to the actual problem."""
        user = make_user(db, email="rem.teacher6@remediation.test")
        scheme = self._create_scheme(db, user.id)
        self._label(db, scheme)
        from src.routers import generation
        report = await generation.preview_allocation(
            scheme.id, _term_config(scheme.id), user, db)
        row = report["lesson_review"][0]
        prov = row.get("source_provenance") or {}
        assert "source_review_status" in prov
        assert "source_review_reasons" in prov
        # A mixed source week reports as such on the row's provenance.
        mixed_row = next(
            (r for r in report["lesson_review"]
             if (r.get("source_provenance") or {}).get("source_week") == 9),
            None)
        if mixed_row:
            assert mixed_row["source_provenance"]["source_review_status"] == "mixed"


# ── Defect 9: regression against the real source document structure ─────────

FIXTURE_DOCX = (
    Path(__file__).resolve().parent
    / "fixtures" / "remediation" / "bs7_mixed_midterm_scheme.docx"
)


class TestRealSchemeFixtureRegression:
    """Parse the REAL-shaped single-subject scheme that exposed the defects.

    ``bs7_mixed_midterm_scheme.docx`` (built by ``fixtures/remediation/
    build_fixture.py``) carries the exact structural shapes of the teacher's
    uploaded BS7 RME scheme: one subject section, an Indicator column that most
    weeks populate and Week 3 leaves empty, a multi-line indicator cell, the
    Week-9 MID-TERM row sharing its week with a teaching row, and a pure
    REVISION week. Nothing is simplified away.
    """

    @classmethod
    def setup_class(cls):
        if not FIXTURE_DOCX.exists():
            pytest.skip("remediation fixture not built")
        cls.parser = DOCXParser()
        cls.scheme = asyncio.run(cls.parser.parse(FIXTURE_DOCX))
        cls.weeks = {w.week_number: w for w in cls.scheme.weeks}

    def test_single_subject_detection(self):
        assert len(self.scheme.weeks) == 13
        assert self.scheme.subject.value == "Religious and Moral Education"
        assert self.scheme.class_level.value == "Basic 7"

    def test_successful_indicator_extraction(self):
        """Weeks whose source cell HAS an indicator must keep it."""
        for n in (1, 2, 4, 5, 6, 7, 10, 11, 12):
            assert self.weeks[n].indicators, f"week {n} lost its indicator"
            assert str(self.weeks[n].indicators[0]).startswith("B7.")

    def test_multiline_indicator_cell_recovered(self):
        """Week 8's indicator is split across several physical lines."""
        ind = str(self.weeks[8].indicators[0])
        assert ind.startswith("B7.3.1.2.1")
        assert "practised at home" in ind
        assert "wider community" in ind

    def test_genuinely_empty_indicator_stays_empty(self):
        """Week 3's source cell is empty — nothing is fabricated (Defect 2)."""
        assert self.weeks[3].indicators == []
        assert self.weeks[3].week_type == WeekType.INSTRUCTION

    def test_review_state_distinguishes_parser_uncertainty(self):
        weeks = list(self.scheme.weeks)
        assert scheme_provides_indicators(weeks) is True
        assert classify_week_review(self.weeks[3], weeks)[0] == "needs_review"
        assert classify_week_review(self.weeks[1], weeks)[0] == "ok"

    def test_week_9_is_mixed_not_other(self):
        w9 = self.weeks[9]
        assert w9.week_type == WeekType.MIXED
        spine = build_week_spine(w9, list(self.scheme.weeks))
        assert spine["week_type_label"] == "Mixed week"
        assert spine["review_status"] == "mixed"

    def test_midterm_never_becomes_a_lesson(self):
        w9 = self.weeks[9]
        assert str(w9.indicators[0]).startswith("B7.3.1.2.2")
        assert not any("MID-TERM" in str(i).upper() for i in w9.indicators)
        assert w9.strand == "The Family"

    def test_source_date_segments_preserved(self):
        """MID-TERM 05-11→06-11 and teaching 07-11, exactly as the source."""
        w9 = self.weeks[9]
        special = week_special_segments(w9)
        assert special == [{
            "type": "mid_term",
            "label": "MID-TERM (05-11-2026 to 06-11-2026)",
            "start": "2026-11-05",
            "end": "2026-11-06",
        }]
        teaching = week_teaching_segments(w9)
        assert teaching[0]["start"] == "2026-11-07"

    def test_special_revision_week_has_no_lessons(self):
        w13 = self.weeks[13]
        assert w13.week_type == WeekType.REVISION
        assert w13.indicators == []
        assert week_is_non_instructional(w13) is True

    def test_mixed_week_allocation_excludes_special_segment(self):
        w9 = self.weeks[9]
        assert week_is_non_instructional(w9) is False
        cal = _calendar_for(9, [date(2026, 11, 9), date(2026, 11, 11)])
        cfg = TermConfig(scheme_of_work_id="fixture")
        coverage = AllocationEngine().allocate([w9], cal, cfg, False)
        real = [a for a in coverage.allocations if not a.is_special_period]
        assert len(real) == 1
        assert real[0].indicator_code == "B7.3.1.2.2"

    def test_no_ai_guessing_for_the_empty_week(self):
        """The empty week produces no lesson and no invented indicator.

        Allocated against the WHOLE scheme — the real generation path — so the
        indicatorless week-unit fallback (which only applies to schemes whose
        source has no indicator column at all) can never mask it.
        """
        weeks = list(self.scheme.weeks)
        cal = _calendar_for(3, [date(2026, 9, 21), date(2026, 9, 23)])
        cfg = TermConfig(scheme_of_work_id="fixture")
        coverage = AllocationEngine().allocate(weeks, cal, cfg, False)
        assert [a for a in coverage.allocations if a.week_number == 3] == []


# ── Defect 8/15: curriculum authority ────────────────────────────────────────

class TestCurriculumAuthority:
    def test_no_indicator_fabrication_for_empty_weeks(self):
        """Nothing may invent an indicator where the source has none."""
        parser = DOCXParser()
        rows = [_week_row(4, strand="Religious practices", sub_strand="Worship",
                          indicators="")]
        pw = parser._merge_week_rows(4, rows)
        assert pw.indicators == []
        # And the spine keeps the week honest: with indicators provided
        # elsewhere in the scheme, the empty week is extraction uncertainty.
        weeks = [_mk_week(1, indicators=["B7.1.1.1.1 A"]), _mk_week(4)]
        status, reasons = classify_week_review(weeks[1], weeks)
        assert status == "needs_review"
        assert any("indicator" in r.lower() for r in reasons)
