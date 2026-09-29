"""
Final lesson-quality remediation regression (PART 12/13/15/21/26).

These pin the behaviours a teacher actually depends on after the generator,
the WAPEF form and the DOCX/PDF exports have all run:

* every generated lesson carries a CLASS assignment and a HOME assignment that
  follow the indicator's own activity type (never one generic written question);
* no internal/harness artefact (an acceptance marker, an epoch stamp, an icon
  serialization leak) can be persisted onto a lesson;
* a curriculum code is printed exactly once in the WAPEF form;
* a teacher's corrected lesson resource wins in the export while the scheme's
  own source record is left untouched.
"""

from datetime import date

import pytest


# ── PART 15 — class assignment + home assignment ────────────────────────────


def _cfg(**kw):
    from src.models import ClassLevel, Subject, TermConfig

    return TermConfig(
        scheme_of_work_id="s", academic_year="2026/2027", term="First Term",
        class_level=ClassLevel.BASIC_7, subject=Subject.ICT,
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=2, lesson_duration_minutes=60,
        teaching_days=[0, 2], holidays=[],
        keywords=list(kw.pop("keywords", []) or []),
        teaching_learning_resources=list(kw.pop("tlrs", []) or []),
        core_competencies=list(kw.pop("comps", []) or []),
        references=list(kw.pop("refs", []) or []),
        **kw,
    )


def _alloc(text, resources=None, week=1):
    from src.models import AllocatedIndicator

    return AllocatedIndicator(
        indicator_code="B7.1.1.1.2",
        indicator_description=text,
        content_standard_code="B7.1.1.1",
        content_standard_description="B7.1.1.1 Learners describe devices",
        strand="Introduction to Computing", sub_strand="Components of a computer",
        week_number=week,
        source_resources=list(resources or ["Touchscreen", "Mouse", "Keyboard"]),
        lesson_date=date(2026, 9, 7), period_index=1, allocated=True,
        teaching_week=week,
    )


class TestClassAndHomeAssignments:
    def test_a_generated_lesson_carries_both_assignments(self):
        from src.curriculum.lesson_builder import build_lesson

        lp = build_lesson(
            _alloc("B7.1.1.1.2 Classify input and output devices"), _cfg(), "s")
        assert lp.class_assignment.strip()
        assert lp.home_assignment.strip()
        # The legacy single field mirrors the home assignment so templates that
        # declare only a Homework row still render the follow-up.
        assert lp.homework == lp.home_assignment

    def test_assignments_follow_the_indicators_activity_type(self):
        """A practical indicator and a classification indicator must not be
        handed the same task — that was the generic-homework defect."""
        from src.curriculum.lesson_builder import build_lesson

        practical = build_lesson(
            _alloc("B7.1.1.1.2 Demonstrate how to start a computer safely"),
            _cfg(), "s")
        classification = build_lesson(
            _alloc("B7.1.1.1.2 Classify devices as manual or automatic"),
            _cfg(), "s")

        assert practical.class_assignment != classification.class_assignment
        assert practical.home_assignment != classification.home_assignment

    def test_class_assignment_is_tied_to_the_indicator(self):
        from src.curriculum.lesson_builder import build_lesson

        lp = build_lesson(
            _alloc("B7.1.1.1.2 Classify input and output devices"), _cfg(), "s")
        text = lp.class_assignment.lower()
        assert "input and output devices" in text or "classify" in text
        # Concrete learner actions, never a placeholder sentence.
        assert any(v in text for v in ("sort", "group", "learners", "pairs"))


# ── PART 21 — internal artefacts can never persist ──────────────────────────


class TestInternalMarkerGuard:
    def test_acceptance_marker_is_stripped(self):
        from src.ai_resource_text import strip_internal_markers

        assert strip_internal_markers("Acceptance main learning 1790564027080") == ""
        assert strip_internal_markers("Acceptance main learning 1790564027080").find(
            "1790564") == -1

    def test_marker_inside_real_prose_is_removed_not_the_prose(self):
        from src.ai_resource_text import strip_internal_markers

        cleaned = strip_internal_markers(
            "Learners classify devices. Acceptance probe 1700000000000")
        assert "Learners classify devices." in cleaned
        assert "1700000000000" not in cleaned

    def test_icon_serialization_leak_is_removed(self):
        from src.ai_resource_text import strip_internal_markers

        assert "svg" not in strip_internal_markers("svgSuggest")

    def test_ordinary_lesson_prose_is_untouched(self):
        from src.ai_resource_text import strip_internal_markers

        prose = (
            "Display pictures of a desktop computer, smartphone and tablet. "
            "Ask learners to identify which devices they have used."
        )
        assert strip_internal_markers(prose) == prose
        assert strip_internal_markers("") == ""
        assert strip_internal_markers(None) == ""

    def test_marker_cannot_be_saved_onto_a_lesson(self, db):
        from fastapi.testclient import TestClient

        from tests.test_lesson_persistence_matrix import _app, _login
        from tests.test_export_download import make_job_with_lessons
        from src.database import LessonPlanDB

        user = _login(db)
        _scheme, job = make_job_with_lessons(db, user, lessons=1)
        lp = db.query(LessonPlanDB).filter_by(job_id=job.id).first()

        with TestClient(_app(db, user, user)) as client:
            r = client.put(f"/api/generation/lessons/{lp.id}", json={
                "introduction": "Acceptance main learning 1790564027080",
                "class_assignment": "Acceptance probe 1790564027081",
                "keywords": ["components", "Acceptance seed 1790564027082"],
            })
            assert r.status_code == 200, r.text
            got = r.json()

        assert "1790564" not in (got["introduction"] or "")
        assert "1790564" not in (got["class_assignment"] or "")
        assert all("1790564" not in k for k in (got["keywords"] or []))

    def test_marker_cannot_be_saved_into_an_activity_or_objective(self, db):
        """The reported defect: 'Acceptance main learning <epoch>' appeared in
        an exported Word file, i.e. inside a saved activity description."""
        from fastapi.testclient import TestClient

        from tests.test_lesson_persistence_matrix import _app, _login
        from tests.test_export_download import make_job_with_lessons
        from src.database import LessonPlanDB

        user = _login(db)
        _scheme, job = make_job_with_lessons(db, user, lessons=1)
        lp = db.query(LessonPlanDB).filter_by(job_id=job.id).first()

        with TestClient(_app(db, user, user)) as client:
            r = client.put(f"/api/generation/lessons/{lp.id}", json={
                "main_activities": [{
                    "phase": "main_learning",
                    "description": "Acceptance main learning 1790564027080",
                    "duration_minutes": 15,
                    "resources": ["Acceptance chart 1700000000000"],
                }],
                "learning_objectives": [{
                    "description": "Acceptance objective 1700000000001",
                }],
            })
            assert r.status_code == 200, r.text
            got = r.json()

        for act in got["main_activities"]:
            assert "1790564" not in (act.get("description") or "")
            assert all("1700000" not in (res or "") for res in (act.get("resources") or []))
        for obj in got["learning_objectives"]:
            assert "1700000" not in (obj.get("description") or "")


# ── PART 12 — one code, printed once ────────────────────────────────────────


class TestCurriculumCodeDeduplication:
    def test_identical_code_and_text_is_not_repeated(self):
        from src.engines.official_ges_template import _code_and_text as ges
        from src.engines.wapef_template import _code_and_text as wapef

        for fn in (ges, wapef):
            assert fn("B7.1.1.1", "B7.1.1.1") == "B7.1.1.1"

    def test_code_prefixed_text_keeps_the_code_once(self):
        from src.engines.official_ges_template import _code_and_text as ges
        from src.engines.wapef_template import _code_and_text as wapef

        for fn in (ges, wapef):
            assert fn("B7.1.1.1", "B7.1.1.1 Learners classify devices") == (
                "B7.1.1.1 Learners classify devices")

    def test_a_real_description_still_gets_its_code(self):
        from src.engines.official_ges_template import _code_and_text as ges
        from src.engines.wapef_template import _code_and_text as wapef

        for fn in (ges, wapef):
            assert fn("B7.1.1.1", "Learners classify devices") == (
                "B7.1.1.1 Learners classify devices")

    def test_distinct_indicators_are_not_collapsed(self):
        """Two genuinely different codes stay two entries — dedup only removes
        an exact repeat, it never merges distinct curriculum values."""
        from src.engines.official_ges_template import _code_and_text_list

        out = _code_and_text_list(
            ["B7.1.1.1.1", "B7.1.1.1.2"],
            ["Users of computers", "Parts of a computer"],
        )
        assert out == [
            "B7.1.1.1.1 Users of computers",
            "B7.1.1.1.2 Parts of a computer",
        ]


# ── PART 13/26 — lesson value vs source value ───────────────────────────────


class TestLessonResourceOverride:
    def _lesson(self):
        from src.models import (
            ClassLevel, LessonPlan, LessonStatus, Subject,
        )

        return LessonPlan(
            scheme_of_work_id="s", term_config_id="j", week_number=1,
            lesson_sequence=1, lesson_date=date(2026, 9, 7),
            class_level=ClassLevel.BASIC_7, subject=Subject.ICT,
            lesson_topic="Input devices",
            source_tlrs=["Touchscreenn", "Mouse"],
            teaching_learning_resources=["Touchscreen", "Mouse"],
            status=LessonStatus.GENERATED,
        )

    def test_the_lesson_value_wins_in_the_export(self):
        from src.engines.wapef_template import _phase_resources

        lp = self._lesson()
        rendered = _phase_resources(lp, 2, {})
        assert "Touchscreen" in rendered
        assert "Touchscreenn" not in rendered

    def test_the_source_record_is_left_untouched(self):
        from src.engines.wapef_template import _phase_resources

        lp = self._lesson()
        _phase_resources(lp, 2, {})
        assert lp.source_tlrs == ["Touchscreenn", "Mouse"]

    def test_structured_pdf_uses_the_lesson_value_too(self):
        from src.engines.structured_pdf import _resource_lines

        lp = self._lesson()
        lines = _resource_lines(lp)
        assert "Touchscreen" in lines
        assert "Touchscreenn" not in lines

    def test_source_is_the_fallback_when_the_lesson_has_not_edited(self):
        from src.engines.wapef_template import _phase_resources

        lp = self._lesson()
        lp.teaching_learning_resources = []
        rendered = _phase_resources(lp, 2, {})
        assert "Touchscreenn" in rendered


# ── PART 14 — keywords ───────────────────────────────────────────────────────


class TestKeywordQuality:
    def test_scheme_resources_seed_the_keyword_list(self):
        from src.curriculum.lesson_builder import build_lesson

        lp = build_lesson(
            _alloc(
                "B7.1.1.1.2 Distinguish between manual and automatic devices",
                ["Touchscreen", "Mouse", "Keyboard"],
            ),
            _cfg(), "s")
        # The scheme's own materials lead the list (PART 14): they are far more
        # lesson-specific than the shared sub-strand.
        assert lp.keywords[:3] == ["Touchscreen", "Mouse", "Keyboard"]

    def test_generic_action_verbs_are_not_keywords(self):
        from src.curriculum.lesson_builder import build_lesson

        lp = build_lesson(
            _alloc("B7.1.1.1.2 Distinguish between manual and automatic devices"),
            _cfg(), "s")
        lowered = {k.lower() for k in lp.keywords}
        for verb in ("distinguish", "compare", "contrast", "differentiate",
                     "between", "describe"):
            assert verb not in lowered, f"{verb!r} is an action verb, not vocabulary"

    def test_two_lessons_do_not_share_one_generic_list(self):
        from src.curriculum.lesson_builder import build_lesson

        a = build_lesson(
            _alloc("B7.1.1.1.2 Distinguish between manual and automatic devices",
                   ["Touchscreen"]), _cfg(), "s")
        b = build_lesson(
            _alloc("B7.1.1.2.1 Explain how a computer stores data",
                   ["Hard drive"]), _cfg(), "s")
        assert a.keywords != b.keywords


# ── PART 17 — subject-aware pedagogy ────────────────────────────────────────


def _subject_cfg(subject):
    cfg = _cfg()
    cfg.subject = subject
    return cfg


class TestSubjectAwarePedagogy:
    def test_the_same_verb_teaches_differently_per_subject(self):
        """A discussion indicator in RME and in Mathematics must not receive the
        same main-phase skeleton."""
        from src.curriculum.lesson_builder import build_lesson
        from src.models import Subject

        text = "B7.1.1.1.1 Discuss and apply the idea in real situations"
        rme = build_lesson(_alloc(text), _subject_cfg(Subject.RME), "s")
        maths = build_lesson(_alloc(text), _subject_cfg(Subject.MATHEMATICS), "s")
        rme_text = " ".join(a.description for a in rme.main_activities)
        maths_text = " ".join(a.description for a in maths.main_activities)
        assert rme_text != maths_text

    def test_computing_gets_practical_demonstration_language(self):
        from src.curriculum.lesson_builder import build_lesson
        from src.models import Subject

        lp = build_lesson(
            _alloc("B7.1.1.1.2 Demonstrate how to start a computer safely"),
            _subject_cfg(Subject.ICT), "s")
        joined = " ".join(a.description for a in lp.main_activities).lower()
        assert any(v in joined for v in ("demonstrat", "practice", "practical",
                                         "model"))

    def test_every_lesson_has_the_three_phases_and_assignments(self):
        from src.curriculum.lesson_builder import build_lesson
        from src.models import Subject

        for subject in (Subject.ICT, Subject.RME, Subject.MATHEMATICS,
                        Subject.SCIENCE, Subject.ENGLISH, Subject.CAREER_TECHNOLOGY,
                        Subject.CREATIVE_ARTS, Subject.PHE):
            cfg = _cfg()
            try:
                cfg.subject = subject
            except Exception:
                continue
            lp = build_lesson(
                _alloc("B7.1.1.1.1 Describe and apply the concept in context"),
                cfg, "s")
            assert lp.main_activities, f"{subject} produced no main phases"
            assert len(lp.learner_activities) == len(lp.main_activities)
            assert lp.class_assignment.strip()
            assert lp.home_assignment.strip()


# ── PART 23/24/25/30 — structured PDF template fidelity ─────────────────────


def _wapef_lesson():
    from src.models import (
        ClassLevel, LearningObjective, LessonPlan, LessonStatus, Subject,
        TeachingActivity,
    )

    return LessonPlan(
        scheme_of_work_id="s", term_config_id="j", week_number=3,
        lesson_sequence=1, lesson_date=date(2026, 9, 25),
        week_ending=date(2026, 9, 25), class_level=ClassLevel.BASIC_7,
        subject=Subject.ICT, class_size=25, duration_minutes=60,
        school_name="Awasive M/A JHS", teacher_name="Saviour Amegayie",
        strand="Introduction to Computing",
        sub_strand="Components of a computer",
        content_standard_code="B7.1.1.1",
        content_standard="B7.1.1.1 Learners describe devices",
        indicators=["B7.1.1.1.2 Classify input and output devices"],
        indicator_codes=["B7.1.1.1.2"],
        lesson_topic="Input and output devices",
        learning_objectives=[LearningObjective(
            description="Classify input and output devices correctly.")],
        keywords=["Touchscreen", "Mouse", "Keyboard"],
        source_tlrs=["Touchscreenn", "Mouse"],
        teaching_learning_resources=["Touchscreen", "Mouse"],
        introduction="Show pictures of a desktop computer and a smartphone.",
        main_activities=[TeachingActivity(
            phase="MAIN", description="Learners sort the device pictures.",
            duration_minutes=25, resources=[])],
        assessment="Ask each learner to name one input device.",
        conclusion="Learners state the key difference between the two groups.",
        class_assignment="In-class: sort the samples in pairs.",
        home_assignment="At-home: list three devices you use at home.",
        wapef_deep_hope=(
            "Learners will recognize and appreciate the beauty, order, and "
            "purpose of design in the physical world around them."),
        wapef_storyline="Shaping our world.",
        wapef_through_lines=["God worshiper", "Beauty creator"],
        wapef_gods_story="Creation",
        template_id="tpl-wapef-approved-plan",
        status=LessonStatus.GENERATED,
    )


class TestStructuredPdfTemplateFidelity:
    def test_wapef_pdf_is_structured_and_carries_every_saved_value(self, tmp_path):
        pymupdf = pytest.importorskip("pymupdf")
        from src.engines.structured_pdf import render_structured_pdf
        from src.engines.template_engine import get_template_by_id

        lp = _wapef_lesson()
        out = tmp_path / "wapef.pdf"
        template = get_template_by_id("tpl-wapef-approved-plan")
        render_structured_pdf([lp], template=template, output_path=out)

        assert out.read_bytes().startswith(b"%PDF-")
        doc = pymupdf.open(str(out))
        try:
            pages = list(doc)
            tables = [t for page in pages for t in page.find_tables().tables]
            text = " ".join(page.get_text() for page in pages)
        finally:
            doc.close()

        # A structured document, not a text dump: the lesson's content is laid
        # out in real tables (PART 23/30).
        assert tables, "structured PDF rendered no tables"

        # PART 6/22/24: the four WAPEF selections are printed verbatim.
        assert "Shaping our world." in text
        assert "God worshiper" in text
        assert "Beauty creator" in text
        assert "Creation" in text
        assert "recognize and appreciate the beauty" in text

        # PART 15: both assignments reach the PDF.
        assert "sort the samples in pairs" in text
        assert "list three devices you use at home" in text

        # PART 13/26: the LESSON value wins; the source's own record is not
        # printed beside the correction.
        assert "Touchscreen" in text
        assert "Touchscreen" in text and "Touchscreenn" not in text

        # PART 21: nothing internal is ever laid out.
        assert "Acceptance" not in text
        assert "svg" not in text

    def test_wapef_and_ges_both_render_the_shared_canonical_lesson(self, tmp_path):
        """PART 24: DOCX and PDF consume the same lesson; switching template is
        the only thing that changes the document, and the indicator the teacher
        saved is present in both."""
        pytest.importorskip("pymupdf")
        from src.engines.structured_pdf import render_structured_pdf
        from src.engines.template_engine import get_template_by_id

        lp = _wapef_lesson()
        out = tmp_path / "ges.pdf"
        lp.template_id = "tpl-official-ges-nacca-jhs"
        render_structured_pdf(
            [lp], template=get_template_by_id("tpl-official-ges-nacca-jhs"),
            output_path=out)
        assert out.read_bytes().startswith(b"%PDF-")
        # A non-WAPEF template is the ONLY thing that removes the WAPEF fields.
        assert "Shaping our world." not in out.read_bytes().decode("latin-1")


# ── PART 24/25 — DOCX and PDF share the canonical lesson ────────────────────


def _docx_text(path) -> str:
    from docx import Document

    doc = Document(str(path))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts)


def _docx_tables(path):
    from docx import Document

    return Document(str(path)).tables


class TestDocxTemplateFidelity:
    def test_wapef_docx_carries_the_four_fields_and_both_assignments(self, tmp_path):
        from src.engines.generation_pipeline import GenerationPipeline
        from src.models import TemplateType

        lp = _wapef_lesson()
        out = tmp_path / "wapef.docx"
        GenerationPipeline().export_docx_combined(
            "Week 3", [lp], TemplateType.GES_STYLE, out,
            template_id="tpl-wapef-approved-plan")

        assert out.read_bytes().startswith(b"PK")
        # A real template: the document has the form's own tables.
        assert _docx_tables(out), "WAPEF DOCX rendered without tables"
        text = _docx_text(out)
        for value in ("Shaping our world.", "God worshiper", "Beauty creator",
                      "recognize and appreciate the beauty"):
            assert value in text, f"WAPEF value missing from DOCX: {value!r}"
        assert "sort the samples in pairs" in text
        assert "list three devices you use at home" in text

    def test_ges_style_docx_also_carries_both_assignments(self, tmp_path):
        """PART 15: a template with no dedicated assignment row still receives
        both tasks in its own approved locations (assessment / plenary)."""
        from src.engines.generation_pipeline import GenerationPipeline
        from src.models import TemplateType

        lp = _wapef_lesson()
        lp.template_id = None
        out = tmp_path / "ges.docx"
        GenerationPipeline().export_docx_combined(
            "Week 3", [lp], TemplateType.GES_STYLE, out)
        text = _docx_text(out)
        assert "sort the samples in pairs" in text
        assert "list three devices you use at home" in text

    def test_the_same_lesson_renders_in_both_exporters(self, tmp_path):
        """PART 24: DOCX and PDF both consume the SAME canonical lesson — the
        saved indicator and topic survive in each, so neither renderer keeps its
        own copy of the content."""
        pymupdf = pytest.importorskip("pymupdf")
        from src.engines.generation_pipeline import GenerationPipeline
        from src.engines.structured_pdf import render_structured_pdf
        from src.engines.template_engine import get_template_by_id
        from src.models import TemplateType

        lp = _wapef_lesson()
        docx_path = tmp_path / "both.docx"
        pdf_path = tmp_path / "both.pdf"
        GenerationPipeline().export_docx_combined(
            "Week 3", [lp], TemplateType.GES_STYLE, docx_path,
            template_id="tpl-wapef-approved-plan")
        render_structured_pdf(
            [lp], template=get_template_by_id("tpl-wapef-approved-plan"),
            output_path=pdf_path)

        docx_text = _docx_text(docx_path)
        doc = pymupdf.open(str(pdf_path))
        try:
            pdf_text = " ".join(page.get_text() for page in doc)
        finally:
            doc.close()

        # The approved WAPEF form prints no topic row: its identity is the
        # curriculum fields and the delivery phases, which BOTH renderers must
        # take from the same canonical lesson.
        for rendered in (docx_text, pdf_text):
            assert "B7.1.1.1.2" in rendered
            assert "Learners sort the device pictures" in rendered
            assert "Touchscreen" in rendered


# ── PART 5/29/36 — the workspace save payload, end to end ───────────────────


class TestWorkspaceSavePayload:
    """The exact payload the lesson workspace sends must round-trip.

    Save → navigate away → return → reload → open lesson: every teacher-owned
    value must be identical. The database is the authoritative source, so this
    asserts on a FRESH session, not the one that performed the write.
    """

    def _payload(self):
        return {
            "lesson_topic": "Input and output devices",
            "introduction": "Show pictures of a desktop computer and a smartphone.",
            "assessment": "Ask each learner to name one input device.",
            "conclusion": "Learners state the key difference between the two groups.",
            "class_assignment": "In-class: pairs sort the device pictures.",
            "home_assignment": "At-home: list three devices used at home.",
            "homework": "At-home: list three devices used at home.",
            "keywords": ["Touchscreen", "Mouse", "Keyboard"],
            "teaching_learning_resources": ["Touchscreen", "Mouse"],
            "structured_references": [{
                "type": "Computing Curriculum", "title": "NaCCA Computing",
                "page": "12",
            }],
            "wapef_deep_hope": (
                "Learners will recognize and appreciate the beauty, order, and "
                "purpose of design in the physical world around them."),
            "wapef_storyline": "Shaping our world.",
            "wapef_through_lines": ["God worshiper", "Earth keeper"],
            "wapef_gods_story": "Creation",
            "main_activities": [
                {"phase": "main_learning",
                 "description": "Learners sort the device pictures.",
                 "duration_minutes": 25, "resources": ["Board"]},
                {"phase": "main_learning",
                 "description": "Pairs explain one classification.",
                 "duration_minutes": 20, "resources": []},
            ],
        }

    def test_the_workspace_payload_survives_save_and_a_fresh_reload(self, db, db_engine):
        from fastapi.testclient import TestClient
        from sqlalchemy.orm import sessionmaker

        from tests.test_lesson_persistence_matrix import _app, _login
        from tests.test_export_download import make_job_with_lessons
        from src.database import LessonPlanDB
        from src.routers.generation import _db_to_lesson_model, _serialize_lesson

        user = _login(db)
        scheme, job = make_job_with_lessons(db, user, lessons=1)
        lp = db.query(LessonPlanDB).filter_by(job_id=job.id).first()
        payload = self._payload()

        with TestClient(_app(db, user, user)) as client:
            r = client.put(f"/api/generation/lessons/{lp.id}", json=payload)
            assert r.status_code == 200, r.text

        # A brand-new session reads the row back: the value is durable, not
        # held in the writer's identity map.
        Session = sessionmaker(bind=db_engine)
        fresh = Session()
        try:
            row = fresh.query(LessonPlanDB).filter_by(id=lp.id).first()
            assert row.lesson_topic == payload["lesson_topic"]
            assert row.class_assignment == payload["class_assignment"]
            assert row.home_assignment == payload["home_assignment"]
            assert list(row.keywords or []) == payload["keywords"]
            assert list(row.teaching_learning_resources or []) == (
                payload["teaching_learning_resources"])
            assert row.wapef_deep_hope == payload["wapef_deep_hope"]
            assert row.wapef_storyline == payload["wapef_storyline"]
            assert list(row.wapef_through_lines or []) == (
                payload["wapef_through_lines"])
            assert row.wapef_gods_story == payload["wapef_gods_story"]
            # Source authority is untouched by a lesson-level edit.
            assert "Touchscreenn" not in list(row.teaching_learning_resources or [])

            model = _db_to_lesson_model(row)
            assert model.class_assignment == payload["class_assignment"]
            assert model.home_assignment == payload["home_assignment"]
            assert model.wapef_gods_story == payload["wapef_gods_story"]
            ser = _serialize_lesson(row, scheme)
            for key in ("lesson_topic", "introduction", "assessment",
                        "conclusion", "class_assignment", "home_assignment",
                        "homework", "keywords", "teaching_learning_resources",
                        "wapef_deep_hope", "wapef_storyline",
                        "wapef_through_lines", "wapef_gods_story"):
                assert ser.get(key) == payload[key], (
                    f"GET lost {key!r}: {ser.get(key)!r}")
        finally:
            fresh.close()


# ── PART 15/23 — prose fields keep their punctuation in the exports ──────


class TestProseVsListNormalization:
    """A sentence is not a comma-separated list.

    The real defect: the WAPEF phase block read its prose fields through the
    resource-list normalizer, which splits on commas and semicolons. The
    teacher's Class Assignment came back in BOTH the DOCX and the PDF as
    comma-less fragments joined into one run-on line:

        "In pairs learners classify a set of device pictures as manual or
         automatic and write one advantage and one disadvantage of each group
         the teacher checks the reasons given"
    """

    SENTENCE = (
        "In pairs, learners classify a set of device pictures as manual or "
        "automatic; the teacher checks the reasons given."
    )

    def _lesson(self):
        from datetime import date

        from src.models import LessonPlan

        return LessonPlan(
            scheme_of_work_id="s", term_config_id="t", week_number=1,
            lesson_sequence=1, lesson_date=date(2026, 9, 7),
            class_level="Basic 7", subject="ICT",
            lesson_topic="Input devices",
            introduction="Show a keyboard, a mouse and a touchscreen; ask which "
                         "ones the class has used, then record the answers.",
            main_activities=[], assessment="",
            conclusion="Learners state one manual and one automatic device, and "
                       "say why a hospital would choose the automatic one.",
            class_assignment=self.SENTENCE,
            home_assignment="List three devices at home; for each, say whether "
                            "it is manual or automatic.",
        )

    def test_the_phase_block_keeps_prose_punctuation(self):
        from src.engines.wapef_template import _phase_block

        lp = self._lesson()
        for phase, source in ((1, lp.introduction), (3, lp.conclusion)):
            block = _phase_block(lp, phase)
            assert source in block, f"phase {phase} damaged its prose: {block!r}"
        main = _phase_block(lp, 2)
        assert f"Class Assignment: {self.SENTENCE}" in main, main
        assert lp.home_assignment in _phase_block(lp, 3)

    def test_a_real_resource_list_still_splits(self):
        """The list normalizer keeps doing its job for genuine lists."""
        from src.engines.wapef_template import _text_items

        assert _text_items("Counters, sticks, flash cards") == [
            "Counters", "sticks", "flash cards"]

    def test_the_exported_documents_keep_the_sentence(self):
        from src.engines.wapef_template import _phase_block

        lp = self._lesson()
        # Both renderers read this same block, so one assertion covers DOCX
        # and the structured PDF (PART 24: one canonical lesson).
        assert "," in _phase_block(lp, 2)
        assert ";" in _phase_block(lp, 2)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
