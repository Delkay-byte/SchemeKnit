"""
PHASE 12 — internal-string audit across every teacher-visible output path.

An acceptance harness once stamped its own markers onto a lesson, and the
pipeline once stored a serialized list ``["a", "b"]`` as display text, and the
GES template once printed an indicator code twice (once from the code column and
once inside prose). None of those may reach a teacher.

This module audits the four surfaces a teacher actually sees, for a lesson built
from EVERY record of the official NaCCA exemplar corpus:

  1. the ``LessonPlan`` object the planner returns;
  2. the JSON the API serializes for the review/workspace UI;
  3. the exported DOCX (the approved WAPEF form and the GES form);
  4. the exported PDF (both templates).

The banned shapes are deliberately unambiguous: an unfilled ``{{TOKEN}}``, a
Python list/dict repr (``['a'``), the ``svgIcon`` leak, a ``tpl-…`` template id,
an epoch-millisecond stamp, a 12–13 digit acceptance marker, or the same
indicator code printed twice in a row. Ordinary classroom prose is never
matched, so a failure here is always a real leak.
"""

import re

import pytest


# ── Banned shapes ───────────────────────────────────────────────────────────

_BANNED_PATTERNS = [
    (re.compile(r"\{\{[A-Za-z_][A-Za-z_0-9]*\}\}"), "unfilled template token"),
    (re.compile(r"\[['\"]"), "serialized list repr"),
    (re.compile(r"\{['\"]"), "serialized dict repr"),
    (re.compile(r"\bsvg(?=[A-Z][a-z])"), "icon leak (svgIcon)"),
    (re.compile(r"\btpl-[a-z0-9-]+", re.IGNORECASE), "template id leak"),
    (re.compile(r"\b\d{12,13}\b"), "epoch-millisecond stamp"),
    (re.compile(r"<object at 0x[0-9a-f]+", re.IGNORECASE), "python object repr"),
    (re.compile(r"\bNone\b(?!\s+of\b)"), "'None' leak"),
]


def _assert_clean(text: str, where: str) -> None:
    """Assert one teacher-visible string carries no internal artefact."""
    from src.ai_resource_text import looks_internal

    assert not looks_internal(text), f"{where}: internal marker in {text!r}"
    for pattern, label in _BANNED_PATTERNS:
        match = pattern.search(text)
        assert match is None, (
            f"{where}: {label} leaked as {match.group(0)!r} "
            f"(in {text[:200]!r})")


def _assert_no_duplicate_codes(text: str, where: str) -> None:
    """The same indicator code must never be printed twice in a row."""
    from src.curriculum import ANY_CODE_RE

    found = [(m.start(), m.end(), m.group(0)) for m in ANY_CODE_RE.finditer(text)]
    for (_, end, code), (start, _, other) in zip(found, found[1:]):
        if code == other and start - end <= 4:
            raise AssertionError(
                f"{where}: indicator code {code!r} printed twice — "
                f"{text[max(0, end - 40):start + 40]!r}")


# ── Corpus-driven lessons ───────────────────────────────────────────────────

#: Corpus subject -> the ``Subject`` enum member a teacher's scheme would carry.
_SUBJECT_ENUM = {
    "Computing": "ICT",
    "Mathematics": "MATHEMATICS",
    "Science": "SCIENCE",
    "English Language": "ENGLISH",
    "Religious and Moral Education": "RME",
    "Social Studies": "SOCIAL_STUDIES",
    "Career Technology": "CAREER_TECHNOLOGY",
    "Creative Arts and Design": "CREATIVE_ARTS",
    "Physical Education and Health": "PHE",
}


def _content_standard_of(code: str) -> str:
    """``B7/JHS1 1.1.1.1`` -> ``B7/JHS1 1.1.1`` (drop the last segment)."""
    match = re.match(r"^(.*?)[.\s]\d+$", code)
    return match.group(1) if match else code


def _corpus_lessons():
    """One real code-only lesson per corpus record, on the WAPEF template."""
    from datetime import date

    from src.curriculum.exemplars import all_records
    from src.curriculum.lesson_builder import build_lesson
    from src.models import AllocatedIndicator, ClassLevel, Subject, TermConfig

    lessons = []
    for record in all_records():
        enum_name = _SUBJECT_ENUM.get(record.subject)
        assert enum_name, f"no Subject enum mapping for {record.subject!r}"
        subject = getattr(Subject, enum_name)
        config = TermConfig(
            scheme_of_work_id="s", academic_year="2026/2027", term="First Term",
            class_level=ClassLevel.BASIC_7, subject=subject,
            term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
            lessons_per_week=2, lesson_duration_minutes=60,
            teaching_days=[0, 2], holidays=[],
        )
        alloc = AllocatedIndicator(
            indicator_code=record.indicator_code,
            # The published schemes are code-only in the indicator column.
            indicator_description=record.indicator_code,
            content_standard_code=_content_standard_of(record.indicator_code),
            content_standard_description=record.indicator_code,
            strand=record.strand or "Strand 1",
            sub_strand=record.sub_strand or "Sub-strand 1",
            week_number=1, source_resources=[], lesson_date=date(2026, 9, 7),
            period_index=1, allocated=True, teaching_week=1,
        )
        lp = build_lesson(alloc, config, "s")
        # The four WAPEF selections a teacher makes before generating.
        lp.template_id = "tpl-wapef-approved-plan"
        lp.wapef_deep_hope = (
            "Learners will recognize and appreciate the beauty, order, and "
            "purpose of design in the physical world around them.")
        lp.wapef_storyline = "Shaping our world."
        lp.wapef_through_lines = ["God worshiper", "Image bearer"]
        lp.wapef_gods_story = "Creation"
        lessons.append(pytest.param(lp, id=f"{record.subject}-{record.indicator_code}"))
    return lessons


_CORPUS_LESSONS = _corpus_lessons()


#: Keys that legitimately carry machine identifiers, not teacher prose.
_ID_KEYS = {
    "id", "scheme_id", "job_id", "template_id", "source_url", "corpus_version",
    "source_version", "created_at", "updated_at", "status",
}


def _walk_strings(value, where="lesson"):
    """Yield ``(path, text)`` for every teacher-visible string in ``value``."""
    if isinstance(value, str):
        if value.strip():
            yield where, value
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _ID_KEYS:
                continue
            yield from _walk_strings(item, f"{where}.{key}")
        return
    if isinstance(value, (list, tuple, set)):
        for index, item in enumerate(value):
            yield from _walk_strings(item, f"{where}[{index}]")
        return
    if hasattr(value, "model_fields"):  # a pydantic model
        for name in value.__class__.model_fields:
            if name in _ID_KEYS:
                continue
            yield from _walk_strings(getattr(value, name, None), f"{where}.{name}")


def _serialized_prose(payload: dict):
    def walk(value, path):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in _ID_KEYS:
                    continue
                yield from walk(item, f"{path}.{key}")
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                yield from walk(item, f"{path}[{index}]")
        elif isinstance(value, str) and value.strip():
            yield path, value

    yield from walk(payload, "api")


def _docx_text(path) -> str:
    from docx import Document

    doc = Document(str(path))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts)


def _pdf_text(path) -> str:
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open(str(path))
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def _export_docx(lp, out, template_id):
    from src.engines.generation_pipeline import GenerationPipeline
    from src.models import TemplateType

    GenerationPipeline().export_docx_combined(
        "Week 1", [lp], TemplateType.GES_STYLE, out, template_id=template_id)
    return out


def _export_pdf(lp, out, template_id):
    from src.engines.structured_pdf import render_structured_pdf
    from src.engines.template_engine import get_template_by_id

    template = get_template_by_id(template_id) if template_id else None
    render_structured_pdf([lp], template=template, output_path=out)
    return out


class TestUuidIdsAreNeverInternalArtefacts:
    """A uuid4 id is never an epoch stamp.

    The real defect: ``_EPOCH_STAMP_RE`` matched any bare 12–13 digit integer,
    and a uuid4's 12-hex-character segment is all-decimal often enough
    (~1 in 1300) that ``looks_internal`` flagged a legitimate ``LessonPlan.id``
    — intermittently failing the audit and, worse, letting
    ``strip_internal_markers`` DELETE the id wherever a uuid reached prose.
    """

    def test_a_uuid_id_is_never_judged_internal(self):
        import uuid

        from src.ai_resource_text import looks_internal

        # The exact shapes that flaked before the fix.
        for u in ("b818a2f9-22d9-48ae-96cb-673169063170",
                  "58b0c881-b818-4e95-b2e3-542740533973",
                  "c06b46c9-c56b-4678-bbbb-583272136008"):
            assert not looks_internal(u), u
        for _ in range(20_000):
            assert not looks_internal(str(uuid.uuid4()))

    def test_real_epoch_stamps_are_still_caught(self):
        from src.ai_resource_text import looks_internal, strip_internal_markers

        assert looks_internal("Acceptance main learning 1790564027080")
        assert looks_internal("Learners classify devices. Acceptance probe 1700000000000")
        cleaned = strip_internal_markers(
            "Learners classify devices. Acceptance probe 1700000000000")
        assert "Learners classify devices." in cleaned
        assert "1700000000000" not in cleaned


# ── 1. The lesson object ────────────────────────────────────────────────────


class TestLessonObjectIsClean:
    @pytest.mark.parametrize("lp", _CORPUS_LESSONS)
    def test_every_corpus_lesson_object_is_free_of_internal_strings(self, lp):
        for path, text in _walk_strings(lp):
            _assert_clean(text, path)

    @pytest.mark.parametrize("lp", _CORPUS_LESSONS)
    def test_no_objective_or_assignment_starts_with_a_bare_code(self, lp):
        """The defect: "Learners can B7/JHS1 1.1.1.1" reached the classroom."""
        from src.curriculum import CODE_PREFIX_RE

        fields = {
            "objective": lp.learning_objectives[0].description,
            "starter": lp.starter_activity or "",
            "assessment": lp.assessment or "",
            "class_assignment": lp.class_assignment or "",
            "home_assignment": lp.home_assignment or "",
            "introduction": lp.introduction or "",
            "conclusion": lp.conclusion or "",
        }
        for path, text in fields.items():
            assert not CODE_PREFIX_RE.match(text.strip()), (path, text)


# ── 2. The API JSON ─────────────────────────────────────────────────────────


#: Prose fields the review/workspace UI renders and the API must serialize.
_TEACHER_TEXT_FIELDS = (
    "lesson_topic", "introduction", "assessment", "conclusion",
    "class_assignment", "home_assignment", "homework", "starter_activity",
    "content_standard", "strand", "sub_strand",
)

#: Array-typed fields that must arrive as arrays, never as ``["a", "b"]``.
_TEACHER_LIST_FIELDS = (
    "indicators", "keywords", "teaching_learning_resources",
    "core_competencies", "references", "source_tlrs", "other_tlrs",
    "wapef_through_lines", "indicator_codes", "essential_questions",
)


def _persist(db, lp):
    """Write the built lesson through the real persistence boundary."""
    from src.database import GenerationJobDB
    from src.service import DataService
    from tests.conftest import make_user

    user = make_user(db)
    job = GenerationJobDB(
        id="job-audit", owner_id=user.id, scheme_id="s-audit",
        status="completed", total_lessons=1,
    )
    db.add(job)
    db.commit()
    row = DataService().create_lesson_plan(db, user.id, "job-audit",
                                           "s-audit", lp)
    db.refresh(row)
    return row


class TestApiPayloadIsClean:
    @pytest.mark.parametrize("lp", _CORPUS_LESSONS)
    def test_the_serialized_lesson_carries_no_internal_strings(self, lp, db):
        from src.routers.generation import _serialize_lesson

        row = _persist(db, lp)
        for path, text in _serialized_prose(_serialize_lesson(row)):
            _assert_clean(text, path)

    @pytest.mark.parametrize("lp", _CORPUS_LESSONS)
    def test_the_loaded_lesson_model_carries_no_internal_strings(self, lp, db):
        """The load path (DB row -> LessonPlan) feeds review AND exports."""
        from src.routers.generation import _db_to_lesson_model

        row = _persist(db, lp)
        for path, text in _walk_strings(_db_to_lesson_model(row)):
            _assert_clean(text, path)

    @pytest.mark.parametrize("lp", _CORPUS_LESSONS)
    def test_no_teacher_field_is_a_serialized_list(self, lp, db):
        """A stored list must arrive as an array, never as ``["a", "b"]``."""
        from src.routers.generation import _serialize_lesson

        payload = _serialize_lesson(_persist(db, lp))
        for field in _TEACHER_LIST_FIELDS:
            value = payload.get(field)
            assert isinstance(value, list), (field, type(value))
            for item in value:
                assert not (str(item).startswith("[") and str(item).endswith("]")), (
                    field, item)

    @pytest.mark.parametrize("lp", _CORPUS_LESSONS)
    def test_no_teacher_field_is_a_serialized_repr(self, lp, db):
        from src.routers.generation import _serialize_lesson

        payload = _serialize_lesson(_persist(db, lp))
        for field in _TEACHER_TEXT_FIELDS:
            value = payload.get(field)
            assert isinstance(value, str), (field, type(value))
            assert "[" not in value or "http" in value, (field, value)


# ── 3. The DOCX export ──────────────────────────────────────────────────────


class TestDocxExportIsClean:
    @pytest.mark.parametrize("template_id", [
        "tpl-wapef-approved-plan", "tpl-official-ges-nacca-jhs", None])
    @pytest.mark.parametrize("lp", _CORPUS_LESSONS)
    def test_the_exported_docx_carries_no_internal_strings(
            self, lp, template_id, tmp_path):
        out = _export_docx(lp, tmp_path / "lesson.docx", template_id)
        text = _docx_text(out)
        _assert_clean(text, f"docx[{template_id}]")
        _assert_no_duplicate_codes(text, f"docx[{template_id}]")

    @pytest.mark.parametrize("lp", _CORPUS_LESSONS)
    def test_the_exported_docx_renders_a_real_form(self, lp, tmp_path):
        out = _export_docx(lp, tmp_path / "lesson.docx", "tpl-wapef-approved-plan")
        from docx import Document

        assert Document(str(out)).tables, "DOCX rendered no template tables"
        assert "PHASE 1" in _docx_text(out)


# ── 4. The PDF export ───────────────────────────────────────────────────────


class TestPdfExportIsClean:
    @pytest.mark.parametrize("template_id", [
        "tpl-wapef-approved-plan", "tpl-official-ges-nacca-jhs"])
    @pytest.mark.parametrize("lp", _CORPUS_LESSONS)
    def test_the_exported_pdf_carries_no_internal_strings(
            self, lp, template_id, tmp_path):
        pytest.importorskip("pymupdf")
        out = _export_pdf(lp, tmp_path / "lesson.pdf", template_id)
        assert out.read_bytes().startswith(b"%PDF-")
        text = _pdf_text(out)
        _assert_clean(text, f"pdf[{template_id}]")
        _assert_no_duplicate_codes(text, f"pdf[{template_id}]")

    @pytest.mark.parametrize("lp", _CORPUS_LESSONS)
    def test_the_exported_pdf_is_structured(self, lp, tmp_path):
        pymupdf = pytest.importorskip("pymupdf")
        out = _export_pdf(lp, tmp_path / "lesson.pdf", "tpl-wapef-approved-plan")
        doc = pymupdf.open(str(out))
        try:
            tables = [t for page in doc for t in page.find_tables().tables]
        finally:
            doc.close()
        assert tables, "PDF rendered no tables (a text dump, not a form)"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
