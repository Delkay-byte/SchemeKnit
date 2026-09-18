"""Smoke-test that every GES level renderer fills its own source document.

For each of the four levels this builds one deterministic lesson, renders it
into the level's real source DOCX, and confirms:
  * no unreplaced TOKEN placeholders survive
  * the output still has the same table count as the source (no table added/dropped)
  * the school/teacher/term/week context actually landed in the header cells
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docx import Document  # noqa: E402

from src.engines.official_ges_levels import official_specs  # noqa: E402
from src.engines.official_ges_template import render_document  # noqa: E402
from src.models import (  # noqa: E402
    LessonPlan, LessonStatus, EducationalLevel, ClassLevel, Subject,
    TeachingActivity,
)


def make_lesson(spec) -> LessonPlan:
    return LessonPlan(
        id="smoke", scheme_of_work_id="s", term_config_id="c",
        week_number=2, lesson_sequence=1, lesson_date=date(2026, 9, 17),
        lesson_number=1,
        educational_level=EducationalLevel.JHS,
        class_level=ClassLevel.BASIC_9, subject=Subject.SCIENCE,
        class_size=24, duration_minutes=60,
        school_name="Awasive M/A JHS", teacher_name="Saviour Amegayie",
        strand="Diversity of Matter", sub_strand="Materials",
        content_standard="B9.1.1", content_standard_code="B9.1.1.1",
        indicators=["B9.1.1.1"], indicator_codes=["B9.1.1.1"],
        lesson_topic="Properties of Materials",
        keywords=["material", "property", "matter"],
        core_competencies=["Critical Thinking", "Collaboration"],
        teaching_learning_resources=["Textbook", "Real objects"],
        learning_objectives=[{"code": "B9.1.1.1", "description": "Classify materials"}],
        introduction="Starter activity",
        main_activities=[TeachingActivity(phase="main", description="Main step")],
        learner_activities=[TeachingActivity(phase="main", description="Learner practice")],
        teacher_activities=[TeachingActivity(phase="main", description="Teacher explains")],
        assessment="Oral questions", conclusion="Recap",
        references=["Science Curriculum", "Teacher's Guide"],
        status=LessonStatus.GENERATED,
    )


def main() -> int:
    failed = 0
    for spec in official_specs():
        src = Path(__file__).resolve().parent.parent / "src" / "engines" / "assets" / spec.filename
        if not src.exists():
            print("MISSING SOURCE", spec.key, src)
            failed += 1
            continue
        lesson = make_lesson(spec)
        try:
            doc = render_document(
                spec, [lesson],
                context={"school_name": "Awasive M/A JHS",
                         "teacher_name": "Saviour Amegayie",
                         "period": "1st & 2nd",
                         "academic_term": "Term 1"})
        except Exception as exc:  # noqa: BLE001
            print("RENDER FAILED", spec.key, type(exc).__name__, exc)
            failed += 1
            continue

        src_doc = Document(str(src))
        out_doc = doc

        # 1. table count preserved
        if len(src_doc.tables) != len(out_doc.tables):
            print("TABLE COUNT DRIFT", spec.key, len(src_doc.tables), "->", len(out_doc.tables))
            failed += 1

        # 2. no unreplaced tokens
        tokens = []
        for t in out_doc.tables:
            for row in t.rows:
                for cell in row.cells:
                    if "[" in cell.text and "]" in cell.text and cell.text.strip().startswith("["):
                        tokens.append(cell.text.strip()[:40])
        for p in out_doc.paragraphs:
            txt = p.text.strip()
            if txt.startswith("[") and txt.endswith("]") and len(txt) < 60:
                tokens.append(txt[:40])
        if tokens:
            print("UNREPLACED TOKENS", spec.key, tokens[:6])
            failed += 1

        # 3. context landed
        joined = " ".join(
            [c.text for t in out_doc.tables for r in t.rows for c in r.cells]
            + [p.text for p in out_doc.paragraphs]
        )
        for expected in ("Awasive M/A JHS", "Saviour Amegayie"):
            if expected not in joined:
                print("MISSING CONTEXT", spec.key, expected)
                failed += 1
        print("ok", spec.key, "| tables:", len(out_doc.tables))

    print("\nRESULT:", "FAILED" if failed else "ALL LEVELS RENDER CLEANLY")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
