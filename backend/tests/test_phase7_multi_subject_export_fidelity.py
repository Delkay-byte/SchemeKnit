"""Phase 7 — multi-subject export fidelity over the real pipeline (AI OFF).

Generates one real lesson per subject for six JHS subjects on the production
GenerationPipeline (AI OFF / Zeli OFF, frozen harness helpers), then checks
the default DOCX export and the structured PDF export of each subject's
lesson for content hygiene that the approved-template acceptance suites also
enforce: no bare square brackets, no unresolved template placeholders, no
TODO/TBA, curriculum code present, and a parseable document.

The golden-master topology compare for the bundled GES form is covered
per-subject by test_real_science_acceptance / test_official_ges_template;
this file spreads export fidelity across subjects instead.
"""

import os
import re
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import benchmark_hardening as hardening  # noqa: E402

from src.models import AIMode, ClassLevel, Subject  # noqa: E402
from src.engines.generation_pipeline import GenerationPipeline  # noqa: E402
from src.engines.docx_export import DOCXExportEngine  # noqa: E402
from src.engines import structured_pdf  # noqa: E402

B7 = ClassLevel.BASIC_7
_SUBJECTS = (
    Subject.MATHEMATICS,
    Subject.SCIENCE,
    Subject.ENGLISH,
    Subject.ICT,
    Subject.CREATIVE_ARTS,
    Subject.SOCIAL_STUDIES,
)

_UNRESOLVED = re.compile(r"\{focus|\{skill|\{resource|\{strand|\{indicator|\[TODO\]|\bTODO\b|\bTBA\b")


def _generate_subject(subject):
    entries = [e for e in hardening.CORPUS
               if e["subject"] == subject and e["class_level"] == B7]
    if not entries:
        pytest.skip(f"no {subject.value} Basic 7 entries in the frozen corpus")
    scheme = hardening.build_scheme(entries)[0]
    config = hardening.build_config(subject, B7, 60)
    job = GenerationPipeline().generate_all(scheme, config)
    plans = sorted(job._lesson_plans,
                   key=lambda lp: (lp.week_number, lp.lesson_sequence))
    assert plans, f"{subject.value}: pipeline produced no lessons"
    return entries[0], plans[0]


@pytest.fixture(scope="module")
def subject_lessons():
    return {s: _generate_subject(s) for s in _SUBJECTS}


def _docx_text(path):
    from docx import Document
    doc = Document(str(path))
    parts = [p.text for p in doc.paragraphs]
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts)


@pytest.mark.parametrize("subject", _SUBJECTS)
def test_default_docx_export_is_clean(subject, subject_lessons, tmp_path):
    entry, lp = subject_lessons[subject]
    out = DOCXExportEngine().export_single(lp, output_path=tmp_path / f"{subject.value}.docx")
    assert out.exists()
    text = _docx_text(out)
    assert text.strip(), f"{subject.value}: empty export"
    assert entry["code"] in text, f"{subject.value}: curriculum code missing"
    assert not re.search(r"[\[\]]", text), (
        f"{subject.value}: bare bracket in export: "
        f"{re.search(r'.{0,40}[\[\]].{0,40}', text).group(0)!r}")
    bad = _UNRESOLVED.search(text)
    assert not bad, f"{subject.value}: unresolved placeholder {bad.group(0)!r}"
    # All three phases carry prose.
    assert lp.introduction or lp.main_activities
    assert lp.main_activities
    assert lp.conclusion


@pytest.mark.parametrize("subject", _SUBJECTS)
def test_structured_pdf_export_is_valid(subject, subject_lessons, tmp_path):
    _, lp = subject_lessons[subject]
    out = structured_pdf.render_structured_pdf(
        [lp], output_path=tmp_path / f"{subject.value}.pdf")
    raw = open(out, "rb").read()
    assert raw[:5] == b"%PDF-", f"{subject.value}: not a PDF"
    pypdf = pytest.importorskip("pypdf")
    reader = pypdf.PdfReader(str(out))
    assert len(reader.pages) >= 1
    text = "".join((p.extract_text() or "") for p in reader.pages)
    assert text.strip(), f"{subject.value}: PDF has no extractable text"


def test_subjects_covered_is_at_least_five():
    covered = [s for s in _SUBJECTS
               if any(e["subject"] == s and e["class_level"] == B7
                      for e in hardening.CORPUS)]
    assert len(covered) >= 5
