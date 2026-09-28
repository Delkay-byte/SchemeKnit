"""Build the real-use remediation regression fixture (Defect 9).

Run:  python tests/fixtures/remediation/build_fixture.py

The output ``bs7_mixed_midterm_scheme.docx`` reproduces the EXACT structural
shapes that exposed the post-deployment defects in the teacher's real scheme:

  * ONE subject section (a single-subject document) — never a false
    "multiple subjects detected" (Defect 1).
  * An INDICATOR column that most weeks genuinely populate (Defect 2 success
    case) and one week that genuinely leaves it EMPTY (Defect 2 failure case).
  * Week 8's indicator cell split over several lines — the continuation-cell
    shape that silently lost indicators before the merge hardening.
  * Week 9 holding BOTH a "MID-TERM (05-11-2026 to 06-11-2026)" period row AND
    a real teaching row in the same week cell — the mixed-week shape that used
    to be labelled "Other" and to swallow the midterm label as an indicator
    (Defects 4/5).
  * A pure REVISION week (no teaching content) — the special-period shape that
    must never become a lesson.

Nothing here is simplified to avoid the bug: the table columns, week cells,
date formats, merged-looking continuation rows and label text mirror the real
source documents under ``C:\\Users\\SAVIOUR\\Documents\\DScience\\Lesson Plan``.
"""

from pathlib import Path

from docx import Document

OUT = Path(__file__).resolve().parent / "bs7_mixed_midterm_scheme.docx"
#: The SECOND real shape: a scheme whose INDICATOR column prints the CODE ONLY
#: ("B7.1.1.1.1") with no prose at all — the teacher's BS7 Computing scheme. A
#: parser that requires prose after the code silently drops every one of those
#: weeks, which is exactly what the teacher reported ("only one week captured
#: the indicators"). Week 6 lists TWO codes in one cell; week 9 shares its week
#: cell with a MID-TERM row; weeks 14/15 are REVISION / EXAMINATION.
OUT_CODE_ONLY = Path(__file__).resolve().parent / "bs7_code_only_indicators_scheme.docx"

HEADER = ["WEEK", "WEEK ENDING", "STRAND", "SUB-STRAND", "CONTENT STANDARD",
          "INDICATOR(S)", "RESOURCES"]

# week, week-ending, strand, sub-strand, content standard, indicator, resources
ROWS = [
    ("1", "11-09-2026", "God", "Nature of God", "B7.1.1.1.1",
     "B7.1.1.1.1 Explain the nature of God through His attributes",
     "Bible; Wall charts"),
    ("2", "18-09-2026", "God", "Attributes of God", "B7.1.1.2.1",
     "B7.1.1.2.1 Describe ways of demonstrating the attributes of God",
     "Bible; Flashcards"),
    # Defect 2 failure case: the source genuinely leaves this cell empty.
    ("3", "25-09-2026", "God", "Worship", "B7.2.1.1.1", "", "Bible"),
    ("4", "02-10-2026", "Religious Practices", "Worship", "B7.2.1.2.1",
     "B7.2.1.2.1 Identify the types of worship in the three major religions in Ghana",
     "Wall charts; Bible"),
    ("5", "09-10-2026", "Religious Practices", "Festivals", "B7.2.2.1.1",
     "B7.2.2.1.1 Explain the significance of festivals in Ghana",
     "Pictures; Calendar"),
    ("6", "16-10-2026", "Religious Practices", "Festivals", "B7.2.2.2.1",
     "B7.2.2.2.1 Describe the rituals performed during festivals",
     "Posters; Video clips"),
    ("7", "23-10-2026", "The Family", "Roles", "B7.3.1.1.1",
     "B7.3.1.1.1 Describe the roles of members of the family",
     "Family tree chart"),
    # Defect 2 success case that used to fail: the indicator cell is split
    # across physical lines inside the merged cell.
    ("8", "30-10-2026", "The Family", "Values", "B7.3.1.2.1",
     "B7.3.1.2.1 Explain the values that hold the family together,\n"
     "and describe how each value is practised at home\n"
     "and in the wider community",
     "Charts; Story books"),
    # Defect 4/5 mixed week: a MID-TERM period row and a teaching row share
    # the same WEEK cell. The midterm must never become a lesson; the teaching
    # content must never be discarded.
    ("9", "06-11-2026", "MID-TERM (05-11-2026 to 06-11-2026)", "MID-TERM",
     "", "MID-TERM (05-11-2026 to 06-11-2026)", ""),
    ("9", "07-11-2026", "The Family", "Values", "B7.3.1.2.2",
     "B7.3.1.2.2 Demonstrate the values of honesty and respect in daily life",
     "Role play; Charts"),
    ("10", "13-11-2026", "The Family", "Authority", "B7.3.2.1.1",
     "B7.3.2.1.1 Describe the authority relationships in the family",
     "Charts"),
    ("11", "20-11-2026", "The Family", "Responsibility", "B7.3.2.2.1",
     "B7.3.2.2.1 Explain the responsibilities of parents and children",
     "Story books"),
    ("12", "27-11-2026", "Our Community", "Leadership", "B7.4.1.1.1",
     "B7.4.1.1.1 Describe the qualities of a good leader in the community",
     "Pictures; Biographies"),
    # Pure special period: no teaching content at all → never a lesson.
    ("13", "04-12-2026", "REVISION", "REVISION", "", "REVISION", "Past questions"),
]


# week, week-ending, strand, sub-strand, content standard, INDICATOR(S), resources
CODE_ONLY_ROWS = [
    ("1", "11-09-2026", "Introduction to Computing",
     "Components of Computers and Computer Systems", "B7.1.1.1", "B7.1.1.1.1",
     "Personal Computer, Processor"),
    ("2", "18-09-2026", "Introduction to Computing",
     "Components of Computers and Computer Systems", "B7.1.1.1", "B7.1.1.1.2",
     "Personal Computer, keyboard, mouse"),
    ("3", "25-09-2026", "Introduction to Computing",
     "Components of Computers and Computer Systems", "B7.1.1.1", "B7.1.1.1.4",
     "Pen drive, Hard Disk"),
    ("4", "02-10-2026", "Introduction to Computing",
     "Components of Computers and Computer Systems", "B7.1.1.2", "B7.1.1.2.1",
     "Bootable Flash drive"),
    # TWO distinct codes printed in one cell: two indicators, not one with the
    # second code echoed as its description.
    ("6", "16-10-2026", "Introduction to Computing", "Health and Safety in using ICT tools",
     "B7.1.2.1", "B7.1.2.1.1\nB7.1.2.1.2", "Smart Phone, Pictures"),
    # The MID-TERM row and the teaching row share week 9 — the mixed shape, with
    # a code-only indicator on the teaching row.
    ("9", "06-11-2026", "MID-TERM (05-11-2026 to 06-11-2026)",
     "MID-TERM (05-11-2026 to 06-11-2026)",
     "MID-TERM (05-11-2026 to 06-11-2026)",
     "MID-TERM (05-11-2026 to 06-11-2026)", ""),
    ("9", "06-11-2026", "Introduction to Computing", "Health and Safety in using ICT tools",
     "B7.1.3.1", "B7.1.3.1.1", "Personal Computer, Pictures"),
    ("10", "13-11-2026", "Productivity Software", "Word Processing", "B7.2.1.1",
     "B7.2.1.1.1", "Computer, Keyboard"),
    ("14", "11-12-2026", "REVISION", "REVISION", "", "", "Past questions"),
    ("15", "18-12-2026", "EXAMINATION", "EXAMINATION", "", "", "Question papers"),
]


def _write(path: Path, title: str, rows) -> None:
    doc = Document()
    doc.add_paragraph(title)
    table = doc.add_table(rows=1, cols=len(HEADER))
    for i, cell in enumerate(HEADER):
        table.rows[0].cells[i].text = cell
    for row in rows:
        cells = table.add_row().cells
        for i, value in enumerate(row):
            cells[i].text = value
    doc.save(path)
    print(f"wrote {path}")


def main() -> None:
    _write(
        OUT,
        "FIRST TERM SCHEME OF LEARNING FOR BASIC 7 - RELIGIOUS AND MORAL EDUCATION",
        ROWS,
    )
    _write(
        OUT_CODE_ONLY,
        "FIRST TERM SCHEME OF LEARNING, 2026/2027 ACADEMIC YEAR\nSUBJECT: COMPUTING",
        CODE_ONLY_ROWS,
    )


if __name__ == "__main__":
    main()
