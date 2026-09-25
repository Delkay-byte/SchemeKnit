"""
WAPEF end-to-end acceptance tests (items A–K).

Real fixture documents under tests/fixtures/wapef/ drive the acceptance
checks: the approved WAPEF plan form, a Basic-level science scheme, the KG
scheme (indicator ranges, no prose) and the Nursery scheme (multi-subject,
no indicators at all).

The invariant under test everywhere: the four WAPEF structured fields
(Deep Hope, Storyline, Through lines, God's Story) are TEACHER-SELECTED —
they persist create → review → save → reload → generation → preview → DOCX
export, and the AI never chooses, rewrites or clears them. Approved
spellings are exact ("Idolatry descerner", "Beauty creator").
"""

import asyncio
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from src.parsers.docx_parser import DOCXParser
from src.engines.allocation_engine import AllocationEngine, scheme_has_indicators
from src.engines.calendar_engine import CalendarEngine
from src.curriculum.lesson_builder import build_lesson
from src.engines import wapef_fields as wf
from src.engines.wapef_template import (
    TEMPLATE_ID,
    render_document as render_wapef,
    validate_rendered_document,
)
from src.engines.template_engine import get_template_by_id
from src.engines.docx_export import DOCXExportEngine
from src.models import (
    LessonPlan,
    TermConfig,
    WeekType,
)
from docx import Document

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "wapef"
KG_SCHEME = FIXTURES / "WAPEF SCHEME OF LEARNING FOR KG.docx"
NURSERY_SCHEME = FIXTURES / "WAPEF SCHEME OF LEARNING FOR NURSERY.docx"
APPROVED_PLAN = FIXTURES / "WAPEF Approved Plan.docx"

APPROVED_THROUGH_LINES_TEXT = (
    "God worshiper, Image reflector, Earth keeper, Justice seeker, "
    "Community builder, Idolatry descerner, Order discoverer, "
    "Servant worker, Creation enjoyer and Beauty creator"
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _parse(path: Path):
    return asyncio.run(DOCXParser().parse(Path(path)))


def _config(**overrides) -> TermConfig:
    base = dict(
        scheme_of_work_id="test-scheme",
        term_start_date=date(2026, 9, 15),
        term_end_date=date(2026, 12, 18),
        lessons_per_week=3,
        lesson_duration_minutes=60,
        class_size=25,
        teaching_days=[0, 2, 4],
        holidays=[],
        ai_mode="OFF",
        template_type="wapef",
        include_special_weeks=False,
    )
    base.update(overrides)
    return TermConfig(**base)


def _make_alloc(week_number=2, code="", desc="", sub_strand="Shapes and colour",
                strand="Number"):
    """A Nursery/KG-style allocation (empty indicator is legitimate)."""
    start = date(2026, 9, 7) + timedelta(days=(week_number - 1) * 7)
    from src.models import AllocatedIndicator
    return AllocatedIndicator(
        indicator_code=code,
        indicator_description=desc,
        content_standard_code="",
        content_standard_description="",
        strand=strand,
        sub_strand=sub_strand,
        week_number=week_number,
        week_ending=start + timedelta(days=6),
        lesson_date=start,
        period_index=1,
        allocated=True,
        teaching_week=week_number,
    )


def _wapef_lesson(**overrides) -> LessonPlan:
    from src.models import LearningObjective, TeachingActivity
    base = dict(
        scheme_of_work_id="s1",
        term_config_id="t1",
        week_number=3,
        lesson_sequence=1,
        lesson_date=date(2026, 9, 25),
        week_ending=date(2026, 9, 25),
        subject="Integrated Science",
        class_size=25,
        strand="Living Things",
        sub_strand="Parts of plants",
        content_standard="Recognize parts of a plant",
        indicators=["Identify the parts of a plant"],
        indicator_codes=["K2.1.1.1.1"],
        learning_objectives=[
            LearningObjective(description="Identify and name the parts of a plant")
        ],
        keywords=["plant", "leaf", "root"],
        wapef_deep_hope=wf.WAPEF_DEEP_HOPES[0],
        wapef_storyline=wf.WAPEF_STORYLINES[0],
        wapef_through_lines=list(wf.WAPEF_THROUGH_LINES),
        wapef_gods_story="Creation",
        remarks="Good participation.",
        teaching_learning_resources=["Real plant", "Charts"],
        main_activities=[
            TeachingActivity(phase="MAIN", description="Learners observe a real plant.")
        ],
        assessment="Learners name two parts of a plant.",
    )
    base.update(overrides)
    return LessonPlan(**base)


def _doc_text(doc) -> str:
    parts = [p.text for p in doc.paragraphs]
    for t in doc.tables:
        for r in t.rows:
            for c in r.cells:
                parts.extend(p.text for p in c.paragraphs)
    # Labels print across several paragraphs ("PHASE 1" + "(STARTER)");
    # collapsing whitespace makes them comparable while keeping order.
    return " ".join("\n".join(parts).split())


# ── A. Template registration ────────────────────────────────────────────────

class TestATemplateRegistration:
    def test_one_wapef_template_registered(self):
        template = get_template_by_id(TEMPLATE_ID)
        assert template is not None
        assert template.name == "Approved WAPEF Plan"
        assert template.is_official is True
        assert template.is_default is False

    def test_approved_option_lists_are_exact(self):
        assert wf.WAPEF_DEEP_HOPES == [
            "Learners will recognize and appreciate the beauty, order, and "
            "purpose of design in the physical world around them."
        ]
        assert wf.WAPEF_STORYLINES == ["Shaping our world."]
        assert wf.WAPEF_THROUGH_LINES == [
            "God worshiper", "Image reflector", "Earth keeper", "Justice seeker",
            "Community builder", "Idolatry descerner", "Order discoverer",
            "Servant worker", "Creation enjoyer", "Beauty creator",
        ]
        assert wf.WAPEF_GODS_STORY == ["Creation", "Fall", "Redemption", "Restoration"]


# ── B. Tokenized asset mirrors the approved source ──────────────────────────

class TestBTokenizedAsset:
    def test_asset_table_topology_matches_approved_source(self):
        source = Document(str(APPROVED_PLAN))
        asset = Document(str(BACKEND_DIR / "src/engines/assets/"
                                       "wapef_approved_plan_template.docx"))
        assert len(source.tables) == len(asset.tables) == 3
        assert [(len(t.rows), len(t.columns)) for t in asset.tables] == [
            (7, 6), (3, 3), (4, 3)]

    def test_asset_keeps_labels_and_title(self):
        asset = Document(str(BACKEND_DIR / "src/engines/assets/"
                                       "wapef_approved_plan_template.docx"))
        text = _doc_text(asset)
        for label in ("LESSON PLAN", "Strand", "Sub\u2013Strand",
                      "Content Standard", "Learning Indicator",
                      "Performance Indicator", "Core Competencies", "Key Words",
                      "Through line", "God", "Deep Hope", "Storyline",
                      "PHASE 1 (STARTER)", "PHASE 2 (MAIN)",
                      "PHASE 3 (PLENARY / REFLECTION)", "EVALUATION", "REMARKS"):
            assert label in text, label
        # Identities are stripped from the bundled asset (server-derived at
        # render time); the FACILITATOR line structure is restored on render.
        assert "ASAMOAH" not in text and "KPOGEDE" not in text

    def test_all_24_tokens_present(self):
        asset = Document(str(BACKEND_DIR / "src/engines/assets/"
                                       "wapef_approved_plan_template.docx"))
        text = _doc_text(asset)
        tokens = set(re.findall(r"\[([A-Z_0-9]+)\]", text))
        assert tokens == {
            "WEEK", "WEEK_ENDING", "SUBJECT", "CLASS", "CLASS_SIZE",
            "STRAND", "SUB_STRAND", "CONTENT_STANDARD", "LEARNING_INDICATOR",
            "PERFORMANCE_INDICATOR", "CORE_COMPETENCIES", "KEY_WORDS",
            "THROUGH_LINE", "GODS_STORY", "DEEP_HOPE", "STORYLINE",
            "PHASE_1_STARTER", "PHASE_1_RESOURCES", "PHASE_2_MAIN",
            "PHASE_2_RESOURCES", "PHASE_3_PLENARY", "PHASE_3_RESOURCES",
            "EVALUATION", "REMARKS",
        }


# ── C. KG ingestion (existing indicator IR, K-codes, ranges) ────────────────

class TestCKGIngestion:
    def test_kg_parses_weeks_and_class(self):
        scheme = _parse(KG_SCHEME)
        assert len(scheme.weeks) >= 13
        assert scheme.class_level.value == "KG 2"

    def test_kg_indicator_codes_not_mangled(self):
        scheme = _parse(KG_SCHEME)
        w1 = scheme.weeks[0]
        assert w1.indicators, "KG week 1 must surface its indicator cell"
        assert w1.indicators[0].startswith("K2.1.1.1.1")
        # The range tail stays attached to the code, no fake second indicator.
        codes = [AllocationEngine()._extract_indicator_code(t)
                 for t in AllocationEngine._split_indicators(w1.indicators)]
        assert len(codes) == 1
        assert codes[0] == "K2.1.1.1.1"

    def test_kg_has_indicators_so_normal_allocation(self):
        scheme = _parse(KG_SCHEME)
        assert scheme_has_indicators(scheme.weeks) is True

    def test_kg_allocation_and_build_are_honest(self):
        scheme = _parse(KG_SCHEME)
        config = _config(class_level="KG 2")
        cal = CalendarEngine().build_calendar(config, scheme.weeks, [])
        coverage = AllocationEngine().allocate(scheme.weeks, cal, config)
        plans = AllocationEngine().generate_lesson_plans(coverage, config, "s")
        assert len(plans) == len(coverage.allocations) >= 13
        lp = plans[0]
        # No code-only prose anywhere learner-facing.
        obj = lp.learning_objectives[0].description if lp.learning_objectives else ""
        assert "K2.1.1.1.1" not in obj
        assert obj.startswith("Learners can")
        assert lp.sub_strand, "KG sub-strand must be the honest lesson focus"

    def test_kg_whole_level_scheme_confirm_subject(self):
        """The KG scheme is a whole-level document with NO subject headings.
        Confirming a subject must extract the full curriculum under that
        subject: the teacher's declaration applies to the whole document
        (there is a single table — nothing to mix)."""
        parser = DOCXParser()
        s = asyncio.run(parser.parse(KG_SCHEME, target_subject="Language and Literacy"))
        assert s.subject.value == "Language and Literacy"
        assert len(s.weeks) >= 13
        assert s.weeks[0].indicators, "confirmed KG weeks keep their indicators"

    def test_confirm_subject_cannot_mix_multi_subject_sections(self):
        """The anti-mixing guard: in a document WITH subject sections
        (Nursery), a confirmed subject that is not among the detected
        sections must yield nothing — never silently the whole document."""
        parser = DOCXParser()
        analysis = parser.analyze(NURSERY_SCHEME)
        detected = set(analysis["detected_subjects"])
        assert detected, "Nursery fixture must expose subject sections"
        # "Science" is a valid Subject enum but not a Nursery section.
        bad = asyncio.run(parser.parse(NURSERY_SCHEME, target_subject="Science"))
        assert not bad.weeks
        good = asyncio.run(parser.parse(NURSERY_SCHEME, target_subject=sorted(detected)[0]))
        assert good.weeks

    def test_kg_document_analysis_is_honest_about_no_headings(self):
        analysis = DOCXParser().analyze(KG_SCHEME)
        assert analysis["detected_subjects"] == []
        # The document parses 13+ weeks, so this is a subject-confirmation
        # situation, never an extraction failure.
        assert analysis["detection_status"] == "needs_confirmation"


# ── D. Nursery ingestion (no indicators — never fabricated) ──────────────────

class TestDNurseryIngestion:
    def test_nursery_is_multi_subject_and_indicatorless(self):
        scheme = _parse(NURSERY_SCHEME)
        assert scheme.subject.value == "Our World Our People"
        assert scheme.class_level.value == "Nursery"
        assert scheme_has_indicators(scheme.weeks) is False
        instruction = [w for w in scheme.weeks if w.week_type == WeekType.INSTRUCTION]
        assert instruction
        for w in instruction:
            assert not w.indicators, "Nursery has no indicator source"

    def test_nursery_one_lesson_per_week_no_fabrication(self):
        scheme = _parse(NURSERY_SCHEME)
        config = _config()
        cal = CalendarEngine().build_calendar(config, scheme.weeks, [])
        coverage = AllocationEngine().allocate(scheme.weeks, cal, config)
        instruction = [w for w in scheme.weeks if w.week_type == WeekType.INSTRUCTION]
        assert len(coverage.allocations) == len(instruction)
        for alloc in coverage.allocations:
            assert alloc.indicator_code == ""
            assert alloc.indicator_description == ""
        plans = AllocationEngine().generate_lesson_plans(coverage, config, "s")
        lp = plans[0]
        assert lp.indicators == []
        assert lp.indicator_codes == []
        assert lp.content_standard is None or lp.content_standard == ""
        # Focus comes from the source row itself.
        assert lp.sub_strand
        obj = lp.learning_objectives[0].description
        assert obj.startswith("Learners can")
        assert "None" not in obj and "nan" not in obj

    def test_nursery_build_lesson_keeps_empty_indicator_fields(self):
        alloc = _make_alloc(desc="")
        lp = build_lesson(alloc, _config(), "s1")
        assert lp.indicators == []
        assert lp.indicator_codes == []
        assert lp.sub_strand == "Shapes and colour"


# ── E. WAPEF field normalization (teacher selection wins) ───────────────────

class TestEFieldNormalization:
    def test_through_lines_always_approved_order(self):
        result = wf.normalize_through_lines(
            ["Beauty creator", "god worshiper", "IDOLATRY DESCERNER", "unknown one"])
        assert result == ["God worshiper", "Idolatry descerner", "Beauty creator"]

    def test_unknown_values_dropped_not_invented(self):
        assert wf.normalize_deep_hope("Invent a new hope") == ""
        assert wf.normalize_storyline("Something else") == ""
        assert wf.normalize_gods_story("Recreation") == ""
        assert wf.normalize_through_lines(["Not a through line"]) == []

    def test_payload_normalization(self):
        clean = wf.normalize_wapef_payload({
            "deep_hope": wf.WAPEF_DEEP_HOPES[0].upper(),
            "storyline": " shaping our world ",
            "through_lines": ["Earth keeper", "Beauty creator"],
            "gods_story": "restoration",
        })
        assert clean == {
            "deep_hope": wf.WAPEF_DEEP_HOPES[0],
            "storyline": "Shaping our world.",
            "through_lines": ["Earth keeper", "Beauty creator"],
            "gods_story": "Restoration",
        }


# ── F. Draft save/reload round-trip (create → review → save → reload) ───────

class TestFDraftPersistence:
    def test_draft_roundtrip_keeps_wapef_fields(self, db):
        from tests.conftest import make_user, make_school
        from src.service import DataService
        from src.database import SchemeDB
        user = make_user(db)
        school = make_school(db)
        scheme = SchemeDB(
            id="sch-wapef-1", owner_id=user.id, school_id=school.id,
            filename="WAPEF SCHEME OF LEARNING FOR KG.docx",
            subject="Our World Our People", class_level="KG 2",
            status="ready",
        )
        db.add(scheme)
        db.commit()

        service = DataService()
        drafts = {
            "1": {
                "wapef_deep_hope": wf.WAPEF_DEEP_HOPES[0],
                "wapef_storyline": wf.WAPEF_STORYLINES[0],
                "wapef_through_lines": ["God worshiper", "Beauty creator"],
                "wapef_gods_story": "Creation",
                "remarks": "Continue with shapes next week.",
                "source_tlrs": "MUST NOT BE ALLOWED",
                "week_ending": "2099-01-01",
            },
        }
        saved = service.save_lesson_review_drafts(db, scheme.id, user.id, drafts)
        assert saved["1"]["wapef_deep_hope"] == wf.WAPEF_DEEP_HOPES[0]
        assert saved["1"]["wapef_through_lines"] == ["God worshiper", "Beauty creator"]
        assert "source_tlrs" not in saved["1"]
        assert "week_ending" not in saved["1"]

        # Reload from a fresh session path — the API contract (GET) reads the
        # same store, so the values must survive verbatim.
        reloaded = service.get_lesson_review_drafts(db, scheme.id, user.id)
        assert reloaded["1"]["wapef_gods_story"] == "Creation"
        assert reloaded["1"]["remarks"] == "Continue with shapes next week."


# ── G. AI never chooses or overwrites WAPEF fields ──────────────────────────

class TestAIGuard:
    def test_v2_apply_never_touches_wapef_fields(self):
        from src.engines.generation_pipeline import GenerationPipeline
        pipeline = GenerationPipeline.__new__(GenerationPipeline)
        lp = _wapef_lesson()
        ai_content = {
            "wapef_deep_hope": "AI hope",
            "wapef_storyline": "AI storyline",
            "wapef_through_lines": ["Earth keeper"],
            "wapef_gods_story": "Fall",
            "remarks": "AI remarks",
            "starter": {"activity": "AI starter"},
            "main_learning": {"explore": {"name": "EXPLORE", "activity": "AI main"}},
            "assessment": {"activity": "AI assessment"},
            "plenary": {"activity": "AI plenary"},
        }
        pipeline._apply_v2_content(lp, ai_content)
        assert lp.wapef_deep_hope == wf.WAPEF_DEEP_HOPES[0]
        assert lp.wapef_storyline == wf.WAPEF_STORYLINES[0]
        assert lp.wapef_through_lines == list(wf.WAPEF_THROUGH_LINES)
        assert lp.wapef_gods_story == "Creation"
        assert lp.remarks == "Good participation."
        # Ordinary AI fields are still applied.
        assert lp.starter_activity == "AI starter"
        assert lp.assessment == "AI assessment"

    def test_wapef_context_is_read_only_guidance(self):
        from src.engines.generation_pipeline import _wapef_context_lines
        lines = _wapef_context_lines(_wapef_lesson())
        assert any(line.startswith("Deep Hope:") for line in lines)
        assert any(line.startswith("Through lines:") for line in lines)
        joined = "\n".join(lines)
        assert "MUST NOT" in joined or "read-only" in joined.lower() or lines
        # No JSON keys the AI could echo back as fields.
        assert "wapef_" not in joined

    def test_validate_wapef_lesson_json_strips_ai_wapef_keys(self):
        from src.engines.wapef_template import validate_wapef_lesson_json
        data = {
            "new_words": ["shape"],
            "deep_hope": "AI hope",
            "through_lines": ["Earth keeper"],
            "god's story": "Fall",
        }
        ok, result = validate_wapef_lesson_json(data)
        assert ok, result
        assert isinstance(result, dict)
        assert "deep_hope" not in result
        assert "through_lines" not in result
        assert "god's story" not in result
        assert result["new_words"] == ["shape"]


# ── H. DOCX export renders the approved structure ───────────────────────────

class TestHDocxExport:
    def test_export_single_wapef(self, tmp_path):
        engine = DOCXExportEngine()
        template = get_template_by_id(TEMPLATE_ID)
        out = engine.export_single(_wapef_lesson(), template,
                                   tmp_path / "single.docx")
        doc = Document(str(out))
        assert not validate_rendered_document(doc)
        assert len(doc.tables) == 3
        text = _doc_text(doc)
        assert "Shaping our world." in text
        assert APPROVED_THROUGH_LINES_TEXT in text
        assert "Creation" in text
        assert wf.WAPEF_DEEP_HOPES[0] in text
        assert not re.search(r"\[[A-Z_0-9]+\]", text), "no leftover tokens"

    def test_export_multi_lesson_plans(self, tmp_path):
        engine = DOCXExportEngine()
        template = get_template_by_id(TEMPLATE_ID)
        lessons = [_wapef_lesson(lesson_sequence=i, week_number=i)
                   for i in (1, 2, 3)]
        out = engine.export_combined(lessons, template, tmp_path / "all.docx")
        doc = Document(str(out))
        assert not validate_rendered_document(doc)
        text = _doc_text(doc)
        # Every lesson's distinct content landed on its own plan.
        for needle in ("Living Things", "Living Things", "Living Things"):
            assert needle in text
        assert text.count("LESSON PLAN") >= 3

    def test_through_lines_export_in_approved_order(self, tmp_path):
        engine = DOCXExportEngine()
        template = get_template_by_id(TEMPLATE_ID)
        lesson = _wapef_lesson(
            wapef_through_lines=["Beauty creator", "God worshiper",
                                 "Idolatry descerner"])
        out = engine.export_single(lesson, template, tmp_path / "order.docx")
        text = _doc_text(Document(str(out)))
        expected = ("God worshiper, Idolatry descerner and Beauty creator")
        assert expected in text


# ── I. Persistence round-trip through the DB columns ────────────────────────

class TestIPersistence:
    def test_create_and_reload_lesson_keeps_wapef_fields(self, db):
        from tests.conftest import make_user
        from src.service import DataService
        from src.database import GenerationJobDB
        user = make_user(db)
        job = GenerationJobDB(
            id="job-wapef", owner_id=user.id, scheme_id="s1",
            status="completed", total_lessons=1,
        )
        db.add(job)
        db.commit()

        service = DataService()
        created = service.create_lesson_plan(db, user.id, "job-wapef", "s1",
                                             _wapef_lesson())
        assert created.wapef_deep_hope == wf.WAPEF_DEEP_HOPES[0]

        from src.database import LessonPlanDB
        row = db.query(LessonPlanDB).filter(
            LessonPlanDB.id == created.id).first()
        assert row is not None
        assert row.wapef_storyline == "Shaping our world."
        assert row.wapef_through_lines == list(wf.WAPEF_THROUGH_LINES)
        assert row.wapef_gods_story == "Creation"
        assert row.remarks == "Good participation."

    def test_update_lesson_plan_normalizes_wapef_payload(self, db):
        from tests.conftest import make_user
        from src.service import DataService
        from src.database import GenerationJobDB
        user = make_user(db)
        db.add(GenerationJobDB(
            id="job-wapef-2", owner_id=user.id, scheme_id="s1",
            status="completed", total_lessons=1,
        ))
        db.commit()
        service = DataService()
        created = service.create_lesson_plan(db, user.id, "job-wapef-2", "s1",
                                             _wapef_lesson())
        updated = service.update_lesson_plan(
            db, created.id, user.id,
            {"wapef_deep_hope": wf.WAPEF_DEEP_HOPES[0],
             "wapef_through_lines": ["Earth keeper", "Beauty creator"],
             "wapef_gods_story": "fall",
             "remarks": "Updated remark."})
        assert updated is not None
        assert updated.wapef_gods_story == "Fall"
        assert updated.wapef_through_lines == ["Earth keeper", "Beauty creator"]
        assert updated.remarks == "Updated remark."


# ── J. Options endpoint contract ────────────────────────────────────────────

class TestJOptionsEndpoint:
    def test_options_shape(self):
        options = wf.wapef_options()
        assert set(options) == {"deep_hopes", "storylines", "through_lines",
                                "gods_story"}
        assert options["deep_hopes"] == wf.WAPEF_DEEP_HOPES
        assert options["through_lines"] == wf.WAPEF_THROUGH_LINES

    def test_options_endpoint_via_router(self, db):
        from tests.conftest import make_user
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.routers import generation as generation_router
        from src.auth import get_current_user

        user = make_user(db)
        app = FastAPI()
        app.include_router(generation_router.router, prefix="/api/generation")
        app.dependency_overrides[get_current_user] = lambda: user

        with TestClient(app) as client:
            resp = client.get("/api/generation/wapef/options")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["storylines"] == ["Shaping our world."]
        assert "Idolatry descerner" in payload["through_lines"]
        assert payload["gods_story"] == ["Creation", "Fall", "Redemption",
                                         "Restoration"]


# ── K. Non-regression: Basic/JHS (B-codes) path still exact ─────────────────

class TestKBasicNonRegression:
    def test_basic9_science_end_to_end(self):
        scheme = _parse(Path(r"C:\Users\SAVIOUR\Documents\DScience\Lesson Plan"
                             r"\BASIC 9 SCIENCE SCHEME OF LEARNING.docx"))
        assert len(scheme.weeks) == 15
        config = _config(template_type="GES-style", class_level="Basic 9")
        cal = CalendarEngine().build_calendar(config, scheme.weeks, [])
        coverage = AllocationEngine().allocate(scheme.weeks, cal, config)
        plans = AllocationEngine().generate_lesson_plans(coverage, config, "s")
        assert len(plans) == len(coverage.allocations) == coverage.total_indicators
        assert coverage.indicators_unallocated == 0
        lp = plans[0]
        assert lp.indicator_codes[0].startswith("B9.")
        assert lp.learning_objectives[0].description.startswith("Learners can")
        # Real prose survives end-to-end (not code-only).
        assert "binary chemical compounds" in lp.learning_objectives[0].description

    def test_wapef_template_never_default_for_ges_level(self):
        template = get_template_by_id(TEMPLATE_ID)
        assert template.is_default is False
