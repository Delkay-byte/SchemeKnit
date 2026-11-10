"""
WAPEF DOCX visual language, adopted from the GES reference document.

The reference (`Lesson_Plans_Basic_6_Computing_Deterministic.docx`) uses:

* label cells: fill ``F2F4F8``, bold label text ``2D3748``;
* delivery-grid header: fill ``1A365D`` with white bold centred text;
* phase labels: fill ``F8FAFC``;
* thin black ``Table Grid`` borders, 100/140 twip vertical padding and
  150 twip horizontal padding;
* 11 pt theme body text with 40 twip paragraph spacing.

WAPEF keeps its own fields and table topology. Only these visual tokens and
pagination rules are applied: fixed balanced column widths, a deliberate
two-line "PHASE / DURATION" heading, repeating delivery-table headers, no
fixed content-row heights, and no split short rows.
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor, Twips

__all__ = ["style_wapef_document", "WAPEF_COLORS"]

WAPEF_COLORS = {
    "label_fill": "F2F4F8",
    "header_fill": "1A365D",
    "phase_fill": "F8FAFC",
    "label_text": "2D3748",
    "header_text": "FFFFFF",
    "border": "000000",
}

BODY_FONT = "Calibri"
BODY_SIZE = Pt(10.5)
METADATA_SIZE = Pt(10)
HEADER_SIZE = Pt(10.5)

#: Usable width in twips for A4/Letter with the margins below (7.2 inches).
_USABLE_TWIPS = 10368
_METADATA_WIDTHS = (1440, 1584, 1008, 3024, 1296, 2016)
_PHASE_WIDTHS = (1872, 5904, 2592)


def _set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    for shd in tc_pr.findall(qn("w:shd")):
        tc_pr.remove(shd)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def _set_cell_margins(cell, top=100, bottom=100, left=150, right=150) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    for margin in tc_pr.findall(qn("w:tcMar")):
        tc_pr.remove(margin)
    mar = OxmlElement("w:tcMar")
    for name, value in (("top", top), ("left", left), ("bottom", bottom),
                        ("right", right)):
        node = OxmlElement(f"w:{name}")
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")
        mar.append(node)
    tc_pr.append(mar)


def _set_table_layout(table) -> None:
    tbl_pr = table._tbl.tblPr
    for layout in tbl_pr.findall(qn("w:tblLayout")):
        tbl_pr.remove(layout)
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tbl_pr.append(layout)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER


def _set_grid(table, widths: Iterable[int]) -> None:
    widths = list(widths)
    for column, width in zip(table.columns, widths):
        column.width = Twips(width)
    # Merged cells span several grid columns: a merged cell's width must be the
    # SUM of its span, never the width of the first column. Setting the first
    # width on every visual cell distorted merged metadata rows (the English
    # plan's label column rendered off the page edge).
    for row in table.rows:
        grid_index = 0
        for cell in _unique_cells(row):
            span = cell.grid_span or 1
            total = sum(widths[grid_index:grid_index + span]) or widths[-1]
            cell.width = Twips(total)
            grid_index += span


def _set_row_auto_height(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    for height in tr_pr.findall(qn("w:trHeight")):
        tr_pr.remove(height)
    row.height = None
    row.height_rule = None


def _repeat_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    if tr_pr.find(qn("w:tblHeader")) is None:
        tr_pr.append(OxmlElement("w:tblHeader"))
    for cell in _unique_cells(row):
        for paragraph in cell.paragraphs:
            paragraph.paragraph_format.keep_with_next = True


def _cant_split(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    if tr_pr.find(qn("w:cantSplit")) is None:
        tr_pr.append(OxmlElement("w:cantSplit"))


def _allow_split(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    for node in tr_pr.findall(qn("w:cantSplit")):
        tr_pr.remove(node)


def _unique_cells(row) -> List:
    seen = set()
    out = []
    for cell in row.cells:
        if id(cell._tc) in seen:
            continue
        seen.add(id(cell._tc))
        out.append(cell)
    return out


def _trim_empty_paragraphs(cell) -> None:
    """Drop the template's blank spacer paragraphs inside a filled cell."""
    paragraphs = list(cell.paragraphs)
    if len(paragraphs) <= 1:
        return
    for paragraph in paragraphs:
        if (paragraph.text or "").strip():
            continue
        if len(list(cell.paragraphs)) <= 1:
            break
        # A blank spacer adds nothing but page height and continuation rows.
        paragraph._element.getparent().remove(paragraph._element)


def _style_runs(cell, *, bold: Optional[bool] = None,
                color: Optional[str] = None, size=BODY_SIZE,
                centered: bool = False) -> None:
    for paragraph in cell.paragraphs:
        if centered:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in paragraph.runs:
            run.font.name = BODY_FONT
            run.font.size = size
            if bold is not None:
                run.bold = bold
            if color:
                run.font.color.rgb = RGBColor.from_string(color)


def _style_metadata_table(table) -> None:
    table.style = "Table Grid"
    _set_table_layout(table)
    _set_grid(table, _METADATA_WIDTHS)
    for row in table.rows:
        _set_row_auto_height(row)
        _cant_split(row)
        for cell in _unique_cells(row):
            _trim_empty_paragraphs(cell)
            _set_cell_shading(cell, WAPEF_COLORS["label_fill"])
            _set_cell_margins(cell, top=60, bottom=60)
            _style_runs(cell, color=WAPEF_COLORS["label_text"], size=METADATA_SIZE)
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_after = Twips(10)
                paragraph.paragraph_format.space_before = Twips(10)
                paragraph.paragraph_format.line_spacing = 1.0


def _style_phase_table(table) -> None:
    table.style = "Table Grid"
    _set_table_layout(table)
    _set_grid(table, _PHASE_WIDTHS)
    if not table.rows:
        return
    for index, row in enumerate(table.rows):
        _set_row_auto_height(row)
        text_length = sum(len(cell.text or "") for cell in _unique_cells(row))
        # Keep a normal Phase row whole (an orphaned single line at the top of
        # the next page is worse than moving the row). Only a genuinely huge
        # row (>2000 characters) is allowed to continue; it then relies on the
        # repeated header for context.
        if index == 0 or text_length < 2000:
            _cant_split(row)
        else:
            _allow_split(row)
        if index == 0:
            _repeat_header(row)
            for cell in _unique_cells(row):
                _set_cell_shading(cell, WAPEF_COLORS["header_fill"])
                _set_cell_margins(cell, top=140, bottom=140)
                _style_runs(cell, bold=True,
                            color=WAPEF_COLORS["header_text"],
                            size=HEADER_SIZE, centered=True)
            continue
        cells = _unique_cells(row)
        for cell_index, cell in enumerate(cells):
            _trim_empty_paragraphs(cell)
            if cell_index == 0:
                _set_cell_shading(cell, WAPEF_COLORS["phase_fill"])
                _style_runs(cell, bold=True)
            else:
                _set_cell_shading(cell, "FFFFFF")
                _style_runs(cell)
            _set_cell_margins(cell)
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_after = Twips(40)
                paragraph.paragraph_format.space_before = Twips(40)


def _style_footer(document) -> None:
    """A quiet page number; no school-specific vision is hard-coded.

    The bundled source printed one school's vision in the footer, which would
    put that school's wording on every other school's plans. Vision text must
    come from configuration when it exists; until then the footer carries only
    the page number.
    """
    for section in document.sections:
        footer = section.footer
        footer.is_linked_to_previous = False
        paragraphs = list(footer.paragraphs)
        if not paragraphs:
            paragraphs = [footer.add_paragraph()]
        paragraph = paragraphs[0]
        for extra in paragraphs[1:]:
            extra._element.getparent().remove(extra._element)
        # Remove the supplied footer's own runs AND field codes (the source
        # carried a stale PAGE field beside its vision line).
        for child in list(paragraph._p):
            if child.tag != qn("w:pPr"):
                paragraph._p.remove(child)
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run("Page ")
        run.font.name = BODY_FONT
        run.font.size = Pt(9)
        fld = OxmlElement("w:fldSimple")
        fld.set(qn("w:instr"), " PAGE ")
        inner_run = OxmlElement("w:r")
        props = OxmlElement("w:rPr")
        size = OxmlElement("w:sz")
        size.set(qn("w:val"), "18")
        props.append(size)
        inner_run.append(props)
        text = OxmlElement("w:t")
        text.text = "1"
        inner_run.append(text)
        fld.append(inner_run)
        paragraph._p.append(fld)


def _style_body_paragraphs(document) -> None:
    """Use the same typeface for the header/title as the tables."""
    for paragraph in document.paragraphs:
        for run in paragraph.runs:
            run.font.name = BODY_FONT


def _style_sections(document) -> None:
    for section in document.sections:
        section.top_margin = Inches(0.5)
        section.bottom_margin = Inches(0.55)
        section.left_margin = Inches(0.65)
        section.right_margin = Inches(0.65)
        section.footer_distance = Inches(0.25)


def style_wapef_document(document) -> None:
    """Apply the GES-inspired visual language to a WAPEF form (idempotent)."""
    _style_sections(document)
    _style_body_paragraphs(document)
    tables = list(document.tables)
    # One approved form = metadata table + two delivery tables. A multi-lesson
    # document repeats that group; styling every table after the first as a
    # delivery grid painted the SECOND lesson's metadata navy and gave it the
    # phase column widths (which pushed it off the page).
    if tables and len(tables) % 3 == 0:
        for start in range(0, len(tables), 3):
            _style_metadata_table(tables[start])
            _style_phase_table(tables[start + 1])
            _style_phase_table(tables[start + 2])
    elif tables:
        _style_metadata_table(tables[0])
        for table in tables[1:]:
            _style_phase_table(table)
    # The title stays the form's own typography; only the body tables and
    # footer are restyled.
    _style_footer(document)
