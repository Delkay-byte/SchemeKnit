"""
Real Document Acceptance Tests — Generation V2
Uses actual Basic 7 and Basic 9 PDFs.
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pathlib import Path
from datetime import date

from src.parsers.pdf_parser import PDFParser
from src.models import (
    Week, WeekType, Subject, TermConfig,
    AIMode, TeachingCalendar, TeachingDay, Holiday,
)
from src.engines.allocation_engine import AllocationEngine
from src.engines.calendar_engine import CalendarEngine
from src.engines.generation_pipeline import GenerationPipeline
from src.curriculum import Indicator
from src.curriculum.quality_gate import validate_lesson_quality

REAL_DOCS = Path(__file__).parent.parent / "real_documents"
BASIC7_PDF = REAL_DOCS / "BASIC 7 TERM 1.pdf"
BASIC9_PDF = REAL_DOCS / "BASIC 9 TERM 1.pdf"


def _make_term_config(scheme_id="real-doc-test"):
    return TermConfig(
        scheme_of_work_id=scheme_id,
        term_start_date=date(2026, 9, 7),
        term_end_date=date(2026, 12, 18),
        semester=1,
        lessons_per_week=3,
        lesson_duration_minutes=45,
        teaching_days=[0, 1, 2, 3, 4],
        holidays=[
            Holiday(name="Founder's Day", date=date(2026, 11, 20)),
            Holiday(name="Constitution Day", date=date(2026, 12, 7)),
        ],
        ai_mode=AIMode.OFF,
    )


# ======================================================================
# BASIC 7
# ======================================================================

class TestBasic7RealDocument:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.parser = PDFParser()

    @pytest.mark.skipif(not BASIC7_PDF.exists(), reason="Basic 7 PDF not found")
    def test_01_analyze_detects_science(self):
        result = self.parser.analyze(BASIC7_PDF)
        print(f"\n[BASIC7] Detected: {result['detected_subjects']}")
        print(f"[BASIC7] Status: {result['detection_status']}")
        for s in result['sections']:
            print(f"  {s['subject']}: {s['week_count']} weeks")
        assert result["detection_status"] == "multiple"
        subjects = [s["subject"] for s in result["sections"]]
        assert "Science" in subjects

    @pytest.mark.skipif(not BASIC7_PDF.exists(), reason="Basic 7 PDF not found")
    def test_02_parse_science_section(self):
        scheme = asyncio.run(
            self.parser.parse(BASIC7_PDF, original_filename="BASIC 7 TERM 1.pdf", target_subject="Science")
        )
        print(f"\n[BASIC7-Sci] Subject: {scheme.subject}, Class: {scheme.class_level}")
        print(f"[BASIC7-Sci] Total weeks: {len(scheme.weeks)}")
        for w in scheme.weeks[:8]:
            print(f"  Wk {w.week_number}: {w.week_type.value:12s} | strand={w.strand[:40] if w.strand else '-':40s} | indicators={len(w.indicators)}")
            for ind in w.indicators[:2]:
                print(f"    {ind}")

        assert scheme.subject == Subject.SCIENCE
        instruction = [w for w in scheme.weeks if w.week_type == WeekType.INSTRUCTION]
        assert len(instruction) >= 3
        total_ind = sum(len(w.indicators) for w in instruction)
        assert total_ind >= 5

    @pytest.mark.skipif(not BASIC7_PDF.exists(), reason="Basic 7 PDF not found")
    def test_02b_strand_extraction(self):
        """Verify strand is now extracted from the real PDF (was empty before fix)."""
        scheme = asyncio.run(
            self.parser.parse(BASIC7_PDF, original_filename="BASIC 7 TERM 1.pdf", target_subject="Science")
        )
        strands = {w.strand for w in scheme.weeks if w.strand}
        print(f"\n[BASIC7-Strand] Unique strands: {strands}")
        assert len(strands) >= 2, f"Expected at least 2 unique strands, got {strands}"
        assert "Diversity Of Matter" in strands or "Diversity of Matter" in strands, \
            f"Expected 'Diversity Of/Matter' strand, got {strands}"

    @pytest.mark.skipif(not BASIC7_PDF.exists(), reason="Basic 7 PDF not found")
    def test_03_no_english_leakage(self):
        scheme = asyncio.run(
            self.parser.parse(BASIC7_PDF, original_filename="BASIC 7 TERM 1.pdf", target_subject="Science")
        )
        english_kws = ["grammar", "composition", "essay", "reading comprehension",
                        "punctuation", "letter writing", "writing skills"]
        all_text = " ".join(
            f"{w.strand} {w.sub_strand} {' '.join(w.indicators)}" for w in scheme.weeks
        ).lower()
        for kw in english_kws:
            assert kw not in all_text, f"English keyword '{kw}' leaked into Science"

    @pytest.mark.skipif(not BASIC7_PDF.exists(), reason="Basic 7 PDF not found")
    def test_04_special_weeks_preserved(self):
        scheme = asyncio.run(
            self.parser.parse(BASIC7_PDF, original_filename="BASIC 7 TERM 1.pdf", target_subject="Science")
        )
        special = [w for w in scheme.weeks if w.week_type != WeekType.INSTRUCTION]
        print(f"\n[BASIC7-Special] {len(special)} special weeks:")
        for w in special:
            print(f"  Wk {w.week_number}: {w.week_type.value}")
        for w in special:
            assert w.week_type in [WeekType.REVISION, WeekType.ASSESSMENT, WeekType.SBA, WeekType.OTHER]

    @pytest.mark.skipif(not BASIC7_PDF.exists(), reason="Basic 7 PDF not found")
    def test_05_allocation_engine(self):
        scheme = asyncio.run(
            self.parser.parse(BASIC7_PDF, original_filename="BASIC 7 TERM 1.pdf", target_subject="Science")
        )
        config = _make_term_config()
        calendar = CalendarEngine().build_calendar(config, scheme.weeks)
        engine = AllocationEngine()
        coverage = engine.allocate(scheme.weeks, calendar, config)

        instruction = [w for w in scheme.weeks if w.week_type == WeekType.INSTRUCTION]
        total_indicators_in_weeks = sum(len(w.indicators) for w in instruction)

        print(f"\n[BASIC7-Alloc] parsed_indicators={total_indicators_in_weeks} allocated={coverage.total_generated_lessons} coverage={coverage.coverage_percentage}%")
        print(f"[BASIC7-Alloc] total_indicators field={coverage.total_indicators}")
        for alloc in coverage.allocations[:5]:
            print(f"  {alloc.indicator_code}: wk{alloc.week_number} seq={alloc.lesson_sequence} strand={alloc.strand[:40] if alloc.strand else '-'} sub={alloc.sub_strand}")

        assert coverage.total_generated_lessons >= total_indicators_in_weeks
        assert coverage.coverage_percentage >= 90

    @pytest.mark.skipif(not BASIC7_PDF.exists(), reason="Basic 7 PDF not found")
    def test_06_generate_lessons(self):
        scheme = asyncio.run(
            self.parser.parse(BASIC7_PDF, original_filename="BASIC 7 TERM 1.pdf", target_subject="Science")
        )
        config = _make_term_config()
        pipeline = GenerationPipeline()
        job = pipeline.generate_all(scheme, config)
        lessons = job._lesson_plans

        print(f"\n[BASIC7-Gen] {len(lessons)} lessons generated")
        for i, lp in enumerate(lessons[:5]):
            print(f"\n  L{i+1}: Wk{lp.week_number} Seq{lp.lesson_sequence} | strand={lp.strand or '(empty)'} sub={lp.sub_strand}")
            print(f"    Codes: {lp.indicator_codes}")
            print(f"    Objectives: {[o.description[:60] for o in lp.learning_objectives[:2]]}")
            print(f"    Activities: {len(lp.main_activities)} main, {len(lp.learner_activities)} learner")
            print(f"    Assessment: {(lp.assessment or '')[:80]}")

        assert len(lessons) >= 5
        for lp in lessons:
            assert lp.subject == Subject.SCIENCE
            assert lp.learning_objectives
            assert lp.main_activities

    @pytest.mark.skipif(not BASIC7_PDF.exists(), reason="Basic 7 PDF not found")
    def test_07_quality_gate(self):
        scheme = asyncio.run(
            self.parser.parse(BASIC7_PDF, original_filename="BASIC 7 TERM 1.pdf", target_subject="Science")
        )
        config = _make_term_config()
        pipeline = GenerationPipeline()
        job = pipeline.generate_all(scheme, config)

        passed = 0
        failed_list = []
        for lp in job._lesson_plans:
            ind_code = lp.indicator_codes[0] if lp.indicator_codes else "unknown"
            ind_text = lp.indicators[0] if lp.indicators else ""
            indicator = Indicator(
                code=ind_code,
                exact_text=ind_text,
                description=ind_text,
                source_week=lp.week_number,
                source_subject="Science",
            )
            lesson_dict = {
                "curriculum_match": True,
                "indicator_match": True,
                "indicator_codes": lp.indicator_codes,
                "learning_objectives": [{"text": o.description, "indicator_code": o.indicator_code} for o in lp.learning_objectives],
                "main_activities": [{"phase": a.phase, "description": a.description, "duration_minutes": a.duration_minutes}
                               for a in lp.main_activities],
                "learner_activities": [{"phase": a.phase, "description": a.description, "duration_minutes": a.duration_minutes}
                               for a in lp.learner_activities],
                "assessment": lp.assessment,
                "introduction": getattr(lp, 'introduction', '') or '',
                "starter": getattr(lp, 'starter_activity', '') or '',
                "conclusion": lp.conclusion,
                "subject": "Science",
                "strand": lp.strand,
                "indicator_code": lp.indicator_codes[0] if lp.indicator_codes else "",
                "duration_minutes": config.lesson_duration_minutes,
                "resources": [],
            }
            report = validate_lesson_quality(lesson_dict, indicator)
            if report.overall_status in ("pass", "warn"):
                passed += 1
            else:
                failed_list.append(f"Wk{lp.week_number} Seq{lp.lesson_sequence}: score={report.score} issues={[i.message for i in report.issues[:3]]}")

        print(f"\n[BASIC7-QG] {passed}/{len(job._lesson_plans)} passed")
        if failed_list:
            for f in failed_list:
                print(f"  FAIL: {f}")
        assert len(failed_list) == 0, f"{len(failed_list)} lessons failed quality gate"

    @pytest.mark.skipif(not BASIC7_PDF.exists(), reason="Basic 7 PDF not found")
    def test_08_lesson_variation(self):
        """Verify different indicators produce different lessons."""
        scheme = asyncio.run(
            self.parser.parse(BASIC7_PDF, original_filename="BASIC 7 TERM 1.pdf", target_subject="Science")
        )
        config = _make_term_config()
        pipeline = GenerationPipeline()
        job = pipeline.generate_all(scheme, config)
        lessons = job._lesson_plans

        sub_strands = [lp.sub_strand for lp in lessons]
        objectives = [" ".join(o.description for o in lp.learning_objectives) for lp in lessons]

        unique_sub_strands = len(set(sub_strands))
        print(f"\n[BASIC7-Var] Unique sub-strands: {set(sub_strands)}")
        print(f"[BASIC7-Var] Lesson count: {len(lessons)}")

        assert unique_sub_strands >= 2, f"Only {unique_sub_strands} unique sub-strand(s)"

        for i, obj_text in enumerate(objectives[:3]):
            print(f"  L{i+1} objectives: {obj_text[:100]}")


# ======================================================================
# BASIC 9
# ======================================================================

class TestBasic9RealDocument:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.parser = PDFParser()

    @pytest.mark.skipif(not BASIC9_PDF.exists(), reason="Basic 9 PDF not found")
    def test_01_analyze_multiple_subjects(self):
        result = self.parser.analyze(BASIC9_PDF)
        print(f"\n[BASIC9] Detected: {result['detected_subjects']}")
        print(f"[BASIC9] Status: {result['detection_status']}")
        for s in result['sections']:
            print(f"  {s['subject']}: {s['week_count']} weeks")
        assert result["detection_status"] == "multiple"
        assert len(result["sections"]) >= 2

    @pytest.mark.skipif(not BASIC9_PDF.exists(), reason="Basic 9 PDF not found")
    def test_02_parse_english(self):
        scheme = asyncio.run(
            self.parser.parse(BASIC9_PDF, original_filename="BASIC 9 TERM 1.pdf", target_subject="English Language")
        )
        print(f"\n[BASIC9-Eng] Subject: {scheme.subject}")
        print(f"[BASIC9-Eng] Weeks: {len(scheme.weeks)}")
        for w in scheme.weeks[:3]:
            print(f"  Wk {w.week_number}: {w.strand[:50] if w.strand else '-'} | indicators={len(w.indicators)}")

        assert scheme.subject == Subject.ENGLISH
        instruction = [w for w in scheme.weeks if w.week_type == WeekType.INSTRUCTION]
        assert len(instruction) >= 2

    @pytest.mark.skipif(not BASIC9_PDF.exists(), reason="Basic 9 PDF not found")
    def test_03_parse_science(self):
        scheme = asyncio.run(
            self.parser.parse(BASIC9_PDF, original_filename="BASIC 9 TERM 1.pdf", target_subject="Science")
        )
        print(f"\n[BASIC9-Sci] Subject: {scheme.subject}")
        print(f"[BASIC9-Sci] Weeks: {len(scheme.weeks)}")
        for w in scheme.weeks[:3]:
            print(f"  Wk {w.week_number}: {w.strand[:50] if w.strand else '-'} | indicators={len(w.indicators)}")

        assert scheme.subject == Subject.SCIENCE
        instruction = [w for w in scheme.weeks if w.week_type == WeekType.INSTRUCTION]
        assert len(instruction) >= 2

    @pytest.mark.skipif(not BASIC9_PDF.exists(), reason="Basic 9 PDF not found")
    def test_04_generate_english(self):
        scheme = asyncio.run(
            self.parser.parse(BASIC9_PDF, original_filename="BASIC 9 TERM 1.pdf", target_subject="English Language")
        )
        config = _make_term_config()
        pipeline = GenerationPipeline()
        job = pipeline.generate_all(scheme, config)
        lessons = job._lesson_plans

        print(f"\n[BASIC9-Eng-Gen] {len(lessons)} lessons, parsed subject={scheme.subject}")
        for lp in lessons[:3]:
            print(f"  Wk{lp.week_number} | subj={lp.subject} | strand={lp.strand[:50] if lp.strand else '-'} | codes={lp.indicator_codes}")

        assert len(lessons) >= 2

    @pytest.mark.skipif(not BASIC9_PDF.exists(), reason="Basic 9 PDF not found")
    def test_05_generate_science(self):
        scheme = asyncio.run(
            self.parser.parse(BASIC9_PDF, original_filename="BASIC 9 TERM 1.pdf", target_subject="Science")
        )
        config = _make_term_config()
        pipeline = GenerationPipeline()
        job = pipeline.generate_all(scheme, config)
        lessons = job._lesson_plans

        print(f"\n[BASIC9-Sci-Gen] {len(lessons)} lessons")
        for lp in lessons[:3]:
            print(f"  Wk{lp.week_number} | {lp.strand[:50] if lp.strand else '-'} | codes={lp.indicator_codes}")

        assert len(lessons) >= 2
        for lp in lessons:
            assert lp.subject == Subject.SCIENCE

    @pytest.mark.skipif(not BASIC9_PDF.exists(), reason="Basic 9 PDF not found")
    def test_06_subject_variation(self):
        """English and Science must produce different content."""
        eng = asyncio.run(
            self.parser.parse(BASIC9_PDF, original_filename="BASIC 9 TERM 1.pdf", target_subject="English Language")
        )
        sci = asyncio.run(
            self.parser.parse(BASIC9_PDF, original_filename="BASIC 9 TERM 1.pdf", target_subject="Science")
        )
        eng_strands = {w.strand for w in eng.weeks if w.strand}
        sci_strands = {w.strand for w in sci.weeks if w.strand}
        print(f"\n[BASIC9-Variation] Eng strands: {eng_strands}")
        print(f"[BASIC9-Variation] Sci strands: {sci_strands}")
        assert eng_strands != sci_strands

    @pytest.mark.skipif(not BASIC9_PDF.exists(), reason="Basic 9 PDF not found")
    def test_07_english_quality_gate(self):
        scheme = asyncio.run(
            self.parser.parse(BASIC9_PDF, original_filename="BASIC 9 TERM 1.pdf", target_subject="English Language")
        )
        config = _make_term_config()
        pipeline = GenerationPipeline()
        job = pipeline.generate_all(scheme, config)

        passed = 0
        for lp in job._lesson_plans:
            ind_code = lp.indicator_codes[0] if lp.indicator_codes else "unknown"
            ind_text = lp.indicators[0] if lp.indicators else ""
            indicator = Indicator(
                code=ind_code, exact_text=ind_text, description=ind_text,
                source_week=lp.week_number, source_subject="English",
            )
            lesson_dict = {
                "curriculum_match": True, "indicator_match": True,
                "indicator_codes": lp.indicator_codes,
                "learning_objectives": [{"text": o.description, "indicator_code": o.indicator_code} for o in lp.learning_objectives],
                "main_activities": [{"phase": a.phase, "description": a.description, "duration_minutes": a.duration_minutes}
                               for a in lp.main_activities],
                "learner_activities": [{"phase": a.phase, "description": a.description, "duration_minutes": a.duration_minutes}
                               for a in lp.learner_activities],
                "assessment": lp.assessment, "introduction": getattr(lp, 'introduction', '') or '',
                "starter": getattr(lp, 'starter_activity', '') or '',
                "conclusion": lp.conclusion, "subject": "English",
                "strand": lp.strand,
                "indicator_code": lp.indicator_codes[0] if lp.indicator_codes else "",
                "duration_minutes": config.lesson_duration_minutes, "resources": [],
            }
            report = validate_lesson_quality(lesson_dict, indicator)
            if report.overall_status in ("pass", "warn"):
                passed += 1
            else:
                print(f"  FAIL: Wk{lp.week_number} score={report.score} issues={[i.message for i in report.issues[:3]]}")
        print(f"\n[BASIC9-Eng-QG] {passed}/{len(job._lesson_plans)} passed")
        assert passed == len(job._lesson_plans)

    @pytest.mark.skipif(not BASIC9_PDF.exists(), reason="Basic 9 PDF not found")
    def test_08_science_quality_gate(self):
        scheme = asyncio.run(
            self.parser.parse(BASIC9_PDF, original_filename="BASIC 9 TERM 1.pdf", target_subject="Science")
        )
        config = _make_term_config()
        pipeline = GenerationPipeline()
        job = pipeline.generate_all(scheme, config)

        passed = 0
        for lp in job._lesson_plans:
            ind_code = lp.indicator_codes[0] if lp.indicator_codes else "unknown"
            ind_text = lp.indicators[0] if lp.indicators else ""
            indicator = Indicator(
                code=ind_code, exact_text=ind_text, description=ind_text,
                source_week=lp.week_number, source_subject="Science",
            )
            lesson_dict = {
                "curriculum_match": True, "indicator_match": True,
                "indicator_codes": lp.indicator_codes,
                "learning_objectives": [{"text": o.description, "indicator_code": o.indicator_code} for o in lp.learning_objectives],
                "main_activities": [{"phase": a.phase, "description": a.description, "duration_minutes": a.duration_minutes}
                               for a in lp.main_activities],
                "learner_activities": [{"phase": a.phase, "description": a.description, "duration_minutes": a.duration_minutes}
                               for a in lp.learner_activities],
                "assessment": lp.assessment, "introduction": getattr(lp, 'introduction', '') or '',
                "starter": getattr(lp, 'starter_activity', '') or '',
                "conclusion": lp.conclusion, "subject": "Science",
                "strand": lp.strand,
                "indicator_code": lp.indicator_codes[0] if lp.indicator_codes else "",
                "duration_minutes": config.lesson_duration_minutes, "resources": [],
            }
            report = validate_lesson_quality(lesson_dict, indicator)
            if report.overall_status in ("pass", "warn"):
                passed += 1
            else:
                print(f"  FAIL: Wk{lp.week_number} score={report.score}")
        print(f"\n[BASIC9-Sci-QG] {passed}/{len(job._lesson_plans)} passed")
        assert passed == len(job._lesson_plans)
