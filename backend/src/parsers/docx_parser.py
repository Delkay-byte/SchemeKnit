"""
SchemeKnit Document Parser - DOCX Scheme of Work Processing

Production-quality parser for Ghanaian school scheme of work DOCX files.
Handles real-world document structures including:
- Multiple tables spanning pages
- Repeated headers across tables
- Continuation rows (empty week cells inheriting from previous row)
- Merged cells
- Various date formats
- Special weeks (revision, assessment, SBA)
- Unknown/unrecognized rows preserved for teacher review
"""

import re
import uuid
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, date
from pathlib import Path

from docx import Document
from docx.table import Table

from ..models import (
    Week, WeekType, SchemeOfWork, Subject, ClassLevel,
    ParsedScheme, ParsedWeek, ParsedContentStandard, ParsedIndicator,
    ValidationIssue, ValidationSeverity
)
from .subject_keywords import (
    SUBJECT_KEYWORDS, MAX_HEADING_LENGTH, canonical_subject_from_heading,
    detect_document_title,
)


#: Controlled aliases for equivalent curriculum concepts (PART G). Matching is
#: done on a deterministic normalisation of the header cell, never on exact
#: spelling alone, so a different school's wording still maps to the same
#: concept. Unknown headers are preserved (never discarded) — see
#: ``ParsedScheme.unknown_columns``.
HEADER_ALIASES = {
    # ── week concept ────────────────────────────────────────────────────
    "week": "week_ending",
    "week no": "week_ending",
    "week no.": "week_ending",
    "week number": "week_ending",
    "week ending": "week_ending",
    "week ending date": "week_ending",
    "week date": "week_ending",
    "wk": "week_ending",
    "wk no": "week_ending",
    "wks": "week_ending",
    "week/date": "week_ending",
    # ── strand / theme ──────────────────────────────────────────────────
    "strand": "strand",
    "strands": "strand",
    "strand/theme": "strand",
    "theme": "strand",
    # ── sub-strand / context ────────────────────────────────────────────
    "sub-strand": "sub_strand",
    "sub strand": "sub_strand",
    "sub strands": "sub_strand",
    "sub-strands": "sub_strand",
    "substrand": "sub_strand",
    "substrands": "sub_strand",
    "sub_strand": "sub_strand",
    "sub-strand/topic": "sub_strand",
    "sub strand/topic": "sub_strand",
    "sub theme": "sub_strand",
    "subtheme": "sub_strand",
    "sub-theme": "sub_strand",
    "topic": "sub_strand",
    # ── content standard ────────────────────────────────────────────────
    "content standard": "content_standard",
    "content standards": "content_standard",
    "standard": "content_standard",
    "standards": "content_standard",
    "content standard/codes": "content_standard",
    # ── indicator concept ───────────────────────────────────────────────
    "indicators": "indicators",
    "indicator": "indicators",
    "learning indicator": "indicators",
    "learning indicators": "indicators",
    "performance indicator": "indicators",
    "performance indicators": "indicators",
    "specific indicator": "indicators",
    "specific indicators": "indicators",
    "indicator/indicators": "indicators",
    "learning indicator/codes": "indicators",
    # ── resources ───────────────────────────────────────────────────────
    "resources": "resources",
    "resource": "resources",
    "teaching learning resources": "resources",
    "teaching and learning resources": "resources",
    "tlrs": "resources",
    "tlr": "resources",
    "materials": "resources",
    "instructional materials": "resources",
}

SPECIAL_WEEK_KEYWORDS = [
    "revision",
    "end of term assessment",
    "end of term exam",
    "end of term",
    "sba activities and vacation",
    "sba activities",
    "sba",
    "vacation",
    "examination",
    "exam",
]

WEEK_NUMBER_PATTERN = re.compile(
    r'^(\d{1,2})\s*[\|\n\r]+\s*(.+)$', re.DOTALL
)
WEEK_ONLY_PATTERN = re.compile(r'^(\d{1,2})$')
DATE_SLASH_PATTERN = re.compile(r'(\d{1,2})/(\d{1,2})/(\d{2,4})')
DATE_DASH_PATTERN = re.compile(r'(\d{1,2})-(\d{1,2})-(\d{2,4})')
INDICATOR_CODE_PATTERN = re.compile(r'[BbKk]?\d+\.\d+\.\d+\.\d+(\.\d+)?')
CONTENT_STANDARD_CODE_PATTERN = re.compile(r'[BbKk]?\d+\.\d+\.\d+\.\d+')

#: Month name → number (full and common abbreviations), lowercased keys.
_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7,
    "jul": 7, "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12,
    "dec": 12,
}

#: "11 September 2026" / "11 Sep 2026" / "11 September, 2026"
_TEXT_DATE_RE = re.compile(
    r'\b(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})\b'
)
#: "September 11, 2026" / "Sep 11 2026"
_TEXT_DATE_RE_US = re.compile(
    r'\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b'
)



class DOCXParser:
    """Production parser for DOCX scheme of work documents."""

    def __init__(self):
        self.validation_issues: List[ValidationIssue] = []

    async def parse(
        self,
        file_path: Path,
        original_filename: str = None,
        target_subject: str = None,
    ) -> SchemeOfWork:
        """Parse a scheme document.

        `original_filename` is the name the teacher's file had on their machine.
        It is what the UI must display; the on-disk storage name (UUID-based) is
        never shown to users.

        `target_subject` restricts parsing to the detected subject section of the
        requested subject name. This is how a multi-subject document is reduced to
        the one subject the teacher confirmed — the other subject sections are
        ignored, never silently mixed in.
        """
        doc = Document(file_path)
        raw_text = self._extract_raw_text(doc)
        blocks = self._iter_blocks(doc)

        # Include table cell text in raw_text so class-level, subject,
        # and term detection can read metadata embedded in table headers.
        tables_data = [payload for kind, payload in blocks if kind == "table"]
        table_text_parts = []
        for table in tables_data:
            for row in table:
                for cell in row:
                    cell_text = (cell or "").strip()
                    if cell_text:
                        table_text_parts.append(cell_text)
        if table_text_parts:
            raw_text = raw_text + "\n" + "\n".join(table_text_parts)

        forced_subject: Optional[Subject] = None
        if target_subject:
            sections = self._detect_sections(blocks)
            selected = [
                s for s in sections
                if s["subject"] is not None
                and s["subject"].value == target_subject
            ]
            if selected:
                tables_data = [t for s in selected for t in s["tables"]]
                forced_subject = selected[0]["subject"]
            elif any(s["subject"] is not None for s in sections):
                # The requested section does not exist. Never fall back to
                # parsing every subject table — that would silently mix
                # Week N from French with Week N from ICT.
                tables_data = []
            else:
                # Whole-level scheme with NO subject headings anywhere (the
                # WAPEF KG shape: one table for the whole level, no per-subject
                # sections). The teacher's confirmed subject therefore applies
                # to the entire document — there is nothing to mix. An unknown
                # subject name still yields no tables (handled below).
                try:
                    forced_subject = Subject(target_subject)
                except ValueError:
                    tables_data = []

        filename_for_detection = original_filename or file_path.name
        parsed_scheme = self._parse_scheme(tables_data, raw_text, filename_for_detection)

        weeks = self._convert_to_weeks(parsed_scheme)

        # ── Classification: detect, or be honest about not knowing (PART E) ──
        # Never fabricate a class or subject. Unknown → Subject.UNKNOWN /
        # ClassLevel.UNKNOWN plus an explicit "needs confirmation" warning.
        detected_subject = forced_subject or self._detect_subject(parsed_scheme, raw_text)
        detected_class = self._detect_class_level(
            parsed_scheme, raw_text, filename_for_detection)

        scheme = SchemeOfWork(
            filename=filename_for_detection,
            upload_date=datetime.utcnow(),
            subject=detected_subject or Subject.UNKNOWN,
            class_level=detected_class or ClassLevel.UNKNOWN,
            term=parsed_scheme.term or self._detect_term(raw_text),
            academic_year=parsed_scheme.academic_year or self._detect_academic_year(raw_text),
            weeks=weeks,
            raw_text=raw_text,
            # A document that yielded no weeks is an extraction FAILURE, not a
            # usable empty curriculum (PART J).
            status="extracted" if weeks else "extraction_failed",
        )
        if detected_subject is None:
            scheme.validation_issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                field="subject",
                message=("Subject could not be detected from this document — "
                         "needs confirmation before generating."),
            ))
        if detected_class is None:
            scheme.validation_issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                field="class_level",
                message=("Class level could not be detected from this document — "
                         "needs confirmation before generating."),
            ))
        if not weeks:
            scheme.validation_issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                field="weeks",
                message=("Scheme could not be reliably extracted. Review the "
                         "detected structure or upload a clearer copy."),
            ))
        return scheme

    # ── Multi-subject document detection (§4) ────────────────────────────

    def analyze(self, file_path: Path, original_filename: str = None) -> Dict[str, Any]:
        """Inspect a document WITHOUT generating anything.

        Returns the document title, the subject sections detected, and a
        detection status:
          "multiple"       — more than one subject section found (teacher must
                              confirm which one to use)
          "single"         — exactly one subject section found
          "low_confidence" — no subject section could be identified
        Never invents a classification.
        """
        doc = Document(file_path)
        raw_text = self._extract_raw_text(doc)
        blocks = self._iter_blocks(doc)

        # Include table cell text in raw_text for metadata detection
        tables_data = [payload for kind, payload in blocks if kind == "table"]
        table_text_parts = []
        for table in tables_data:
            for row in table:
                for cell in row:
                    cell_text = (cell or "").strip()
                    if cell_text:
                        table_text_parts.append(cell_text)
        if table_text_parts:
            raw_text = raw_text + "\n" + "\n".join(table_text_parts)

        title = detect_document_title(
            [payload for kind, payload in blocks if kind == "paragraph"]
        )
        sections = self._detect_sections(blocks)

        described = []
        for s in sections:
            if s["subject"] is None:
                continue
            parsed = self._parse_scheme(s["tables"], raw_text, file_path.name)
            
            # Determine extraction confidence
            total_weeks = len(parsed.weeks)
            primary_count = len(getattr(parsed, "_extraction_primary", set()))
            fallback_count = len(getattr(parsed, "_extraction_fallback", set()))
            
            if total_weeks == 0:
                extraction_status = "failed"
            elif fallback_count == 0:
                extraction_status = "primary"
            elif primary_count == 0:
                extraction_status = "fallback_only"
            else:
                extraction_status = "mixed"

            described.append({
                "subject": s["subject"].value,
                "title": s["title"],
                "week_count": total_weeks,
                "extraction_status": extraction_status,
                "primary_weeks": primary_count,
                "fallback_weeks": fallback_count,
            })

        # De-duplicate by subject (a document may repeat a subject heading).
        seen: Dict[str, Dict[str, Any]] = {}
        for d in described:
            if d["subject"] not in seen or d["week_count"] > seen[d["subject"]]["week_count"]:
                seen[d["subject"]] = d
        described = list(seen.values())

        non_empty = [d for d in described if d["week_count"] > 0]
        if len(non_empty) > 1:
            status = "multiple"
        elif len(non_empty) == 1:
            status = "single"
        else:
            status = "low_confidence"

        # ── Metadata reconciliation (PART H) ────────────────────────────────
        # Class/subject are detected from multiple independent signals and
        # conflicts are reported rather than silently resolved. The filename is
        # secondary evidence only.
        detection_filename = original_filename or file_path.name
        class_signals = self.class_level_signals(raw_text, detection_filename)
        subject_signals = self.subject_signals(raw_text, detection_filename)
        metadata = {
            "subject": subject_signals["resolved"],
            "class_level": class_signals["resolved"],
            "subject_signals": subject_signals,
            "class_signals": class_signals,
        }
        needs_confirmation = bool(
            class_signals["conflict"] or subject_signals["conflict"]
            or class_signals["resolved"] is None
            or subject_signals["resolved"] is None
        )

        if status in ("single", "low_confidence") and needs_confirmation:
            # Could not confirm subject/class from the document itself.
            status = "needs_confirmation"

        if not non_empty:
            # Distinguish a genuine extraction failure from a low-confidence
            # subject-section detection: try the raw tables directly.
            raw_parsed = self._parse_scheme(tables_data, raw_text, detection_filename)
            if not raw_parsed.weeks:
                status = "extraction_failed"
            elif status == "low_confidence":
                # Content exists but no subject heading was recognised.
                status = "needs_confirmation"

        return {
            "title": title,
            "detected_subjects": [d["subject"] for d in described],
            "sections": described,
            "detection_status": status,
            "needs_confirmation": needs_confirmation,
            "metadata": metadata,
        }

    def _iter_blocks(self, doc: Document) -> List[Tuple[str, Any]]:
        """Yield document blocks IN ORDER as ("paragraph"|"table", payload).

        python-docx exposes paragraphs and tables as separate collections, which
        loses their document order. Section detection needs the true order so a
        subject heading is associated with the table that follows it.
        """
        from docx.oxml.table import CT_Tbl
        from docx.oxml.text.paragraph import CT_P

        blocks: List[Tuple[str, Any]] = []
        for child in doc.element.body.iterchildren():
            if isinstance(child, CT_P):
                from docx.text.paragraph import Paragraph
                text = Paragraph(child, doc).text.strip()
                if text:
                    blocks.append(("paragraph", text))
            elif isinstance(child, CT_Tbl):
                from docx.table import Table
                table = Table(child, doc)
                rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
                blocks.append(("table", rows))
        return blocks

    #: Data rows must never open a subject section (week no, dates, indicator codes).
    _DATA_ROW_PATTERN = re.compile(
        r"(?<!\w)week\s*\d|"
        r"\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}\b|"
        r"\b[a-z]\d+\.\d+\.\d+",
        re.IGNORECASE,
    )

    @classmethod
    def _heading_row_subject(cls, row: List[str]) -> Optional[Subject]:
        """Subject named by a table row that acts as an in-table section heading.

        Real district packs sometimes put the subject title in a cell instead
        of a paragraph. Only short, non-data rows qualify — ordinary curriculum
        cells such as "Earth Science" or "Introduction to Computing" inside a
        week row must not open a new section.
        """
        texts = [(c or "").strip() for c in row]
        non_empty = [t for t in texts if t]
        if not non_empty:
            return None
        joined = " | ".join(non_empty)
        if len(joined) > 200:
            return None
        if cls._DATA_ROW_PATTERN.search(joined):
            return None
        # Long cells are curriculum prose (indicators, content standards).
        if any(len(t) > MAX_HEADING_LENGTH for t in non_empty):
            return None
        for t in non_empty:
            subject = canonical_subject_from_heading(t)
            if subject is None:
                continue
            low = t.lower()
            if (
                len(non_empty) == 1
                or "scheme" in low
                or "learning" in low
                or t is non_empty[0]
            ):
                return subject
        return None

    @staticmethod
    def _row_title(row: List[str]) -> str:
        for c in row:
            text = (c or "").strip()
            if text and canonical_subject_from_heading(text) is not None:
                return text
        return ""

    def _detect_sections(self, blocks: List[Tuple[str, Any]]) -> List[Dict[str, Any]]:
        """Split ordered blocks into subject sections at subject headings.

        Headings may be paragraph text or a short non-data table row; both
        preserve document order. Consecutive sections that share a subject
        (repeated headings) are merged.
        """
        sections: List[Dict[str, Any]] = []
        current: Optional[Dict[str, Any]] = None

        def _flush():
            nonlocal current
            if current and current["tables"]:
                sections.append(current)
            current = None

        for kind, payload in blocks:
            if kind == "paragraph":
                subject = canonical_subject_from_heading(payload)
                if subject is not None:
                    _flush()
                    current = {"subject": subject, "title": payload, "tables": []}
                continue

            # table — look for an in-table heading row that splits this table
            split_at = None
            heading_subject = None
            for ri, row in enumerate(payload):
                subject = self._heading_row_subject(row)
                if subject is not None:
                    split_at = ri
                    heading_subject = subject
                    break

            if split_at is None:
                if current is None:
                    current = {"subject": None, "title": "", "tables": []}
                current["tables"].append(payload)
            else:
                before = payload[:split_at]
                after = payload[split_at:]
                if before:
                    if current is None:
                        current = {"subject": None, "title": "", "tables": []}
                    current["tables"].append(before)
                _flush()
                current = {
                    "subject": heading_subject,
                    "title": self._row_title(after[0]) if after else "",
                    "tables": [after] if after else [],
                }

        _flush()

        # Merge consecutive sections that share a subject (repeated headings).
        merged: List[Dict[str, Any]] = []
        for s in sections:
            if merged and merged[-1]["subject"] == s["subject"]:
                merged[-1]["tables"].extend(s["tables"])
                if not merged[-1]["title"] and s["title"]:
                    merged[-1]["title"] = s["title"]
            else:
                merged.append(s)
        return merged

    def _extract_raw_text(self, doc: Document) -> str:
        parts = []
        for para in doc.paragraphs:
            if para.text.strip():
                parts.append(para.text.strip())
        for table in doc.tables:
            for row in table.rows:
                row_text = []
                for cell in row.cells:
                    text = cell.text.strip()
                    if text:
                        row_text.append(text)
                if row_text:
                    parts.append(' | '.join(row_text))
        return '\n'.join(parts)

    def _extract_tables(self, doc: Document) -> List[List[List[str]]]:
        tables_data = []
        for table in doc.tables:
            table_data = []
            for row in table.rows:
                row_data = []
                for cell in row.cells:
                    cell_text = cell.text.strip()
                    row_data.append(cell_text)
                table_data.append(row_data)
            tables_data.append(table_data)
        return tables_data

    def _parse_scheme(
        self,
        tables_data: List[List[List[str]]],
        raw_text: str,
        filename: str
    ) -> ParsedScheme:
        self.validation_issues = []
        scheme = ParsedScheme(
            filename=filename,
            raw_tables=tables_data
        )

        if not tables_data:
            self.validation_issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                message="No tables found in the document"
            ))
            return scheme

        scheme.subject = self._extract_subject_from_text(raw_text)
        scheme.class_level = self._extract_class_level_from_text(raw_text, filename)
        scheme.term = self._extract_term_from_text(raw_text)
        scheme.academic_year = self._extract_academic_year_from_text(raw_text)

        all_rows = []
        for t_idx, table in enumerate(tables_data):
            for r_idx, row in enumerate(table):
                all_rows.append((t_idx, r_idx, row))

        header_map = {}
        current_week: Optional[int] = None
        current_date: Optional[date] = None
        current_week_type: WeekType = WeekType.INSTRUCTION
        current_strand: Optional[str] = None
        current_sub_strand: Optional[str] = None
        current_resources: List[str] = []

        week_rows: Dict[int, List[Dict[str, Any]]] = {}
        seen_headers_in_table: Dict[int, bool] = {}
        header_buffer: Dict[int, List[List[str]]] = {}
        
        # Track extraction method for confidence reporting
        primary_weeks = set()
        fallback_weeks = set()

        for t_idx, r_idx, row in all_rows:
            if not seen_headers_in_table.get(t_idx, False):
                # Single-row detection always takes priority
                detected = self._detect_header(row)
                if detected:
                    # If we have buffered rows, check if merged version is better
                    if t_idx in header_buffer and header_buffer[t_idx]:
                        test_rows = header_buffer[t_idx] + [row]
                        merged = self._detect_header_with_merge(test_rows, 0)
                        if merged and len(merged) > len(detected):
                            header_map = merged
                        else:
                            header_map = detected
                    else:
                        header_map = detected
                    seen_headers_in_table[t_idx] = True
                    header_buffer.pop(t_idx, None)
                    continue

                # Single-row failed — buffer for potential multi-row merge
                if t_idx not in header_buffer:
                    header_buffer[t_idx] = []
                header_buffer[t_idx].append(row)

                # After buffering 3 rows, attempt merged detection
                if len(header_buffer[t_idx]) >= 3:
                    merged = self._detect_header_with_merge(header_buffer[t_idx], 0)
                    if merged:
                        header_map = merged
                        seen_headers_in_table[t_idx] = True
                        header_buffer.pop(t_idx, None)
                        continue
                    # Merge also failed — these aren't header rows
                    seen_headers_in_table[t_idx] = True
                    header_buffer.pop(t_idx, None)

                seen_headers_in_table[t_idx] = False

            normalized = self._normalize_row(row, header_map)

            # Primary: try to extract week from the header-mapped week_ending column
            week_text = normalized.get("week_ending", "")
            week_info = self._extract_week_info(week_text)
            extraction_method = "primary"
            # The WEEK ENDING column may hold only the date ("11 September 2026")
            # while the WEEK column holds "Week 1" — keep both signals.
            date_from_week_col = self._date_anywhere_in(week_text)

            # Fallback: if header-based extraction failed, scan ALL cells in the row
            # for week-like content. This handles cases where:
            # - header detection failed or week column wasn't mapped
            # - week cell uses "Week N" format instead of bare number/date
            # - week column has a non-standard header name
            if not week_info:
                for cell_text in row:
                    fallback_info = self._extract_week_info(cell_text)
                    if fallback_info:
                        week_info = fallback_info
                        extraction_method = "fallback"
                        break

            if week_info and week_info.get("date") is None:
                # Week number known but date not in that cell — take the
                # authoritative source date from the WEEK ENDING column or
                # any other cell in the row (never invent one later).
                row_date = date_from_week_col or self._date_anywhere_in(*row)
                if row_date:
                    week_info = {
                        "week_number": week_info["week_number"],
                        "date": row_date,
                    }

            if week_info:
                current_week = week_info["week_number"]
                current_date = week_info["date"]
                current_strand = None
                current_sub_strand = None
                current_resources = []

                if current_week not in week_rows:
                    week_rows[current_week] = []
                
                # Track extraction method per week
                if extraction_method == "fallback":
                    fallback_weeks.add(current_week)
                else:
                    primary_weeks.add(current_week)

            strand_text = normalized.get("strand", "").strip()
            if strand_text:
                if self._is_special_week_text(strand_text):
                    current_week_type = self._classify_special_week(strand_text)
                else:
                    current_week_type = WeekType.INSTRUCTION
                    current_strand = strand_text
            elif current_week is not None and current_week_type == WeekType.INSTRUCTION:
                pass

            sub_strand_text = normalized.get("sub_strand", "").strip()
            if sub_strand_text:
                current_sub_strand = sub_strand_text

            resources_text = normalized.get("resources", "").strip()
            if resources_text:
                current_resources.append(resources_text)

            if current_week is not None:
                row_data = {
                    "week_number": current_week,
                    "date": current_date,
                    "week_type": current_week_type,
                    "strand": current_strand,
                    "sub_strand": current_sub_strand,
                    "content_standard": normalized.get("content_standard", "").strip(),
                    "indicators": normalized.get("indicators", "").strip(),
                    "resources": current_resources[-1] if current_resources else "",
                    "raw_row": row,
                }
                week_rows[current_week].append(row_data)

        for week_num in sorted(week_rows.keys()):
            rows = week_rows[week_num]
            parsed_week = self._merge_week_rows(week_num, rows)
            scheme.weeks.append(parsed_week)

        # Attach extraction method info for confidence reporting
        scheme._extraction_primary = primary_weeks
        scheme._extraction_fallback = fallback_weeks

        self._run_validation(scheme)
        scheme.validation_issues = self.validation_issues

        return scheme

    def _detect_header(self, row: List[str]) -> Optional[Dict[str, int]]:
        """Detect header row and return mapping of field_name -> column_index."""
        header_map: Dict[str, int] = {}
        matched = 0
        for c_idx, cell in enumerate(row):
            normalized = self._normalize_header_text(cell)
            if normalized in HEADER_ALIASES:
                header_map[HEADER_ALIASES[normalized]] = c_idx
                matched += 1
        if matched >= 3:
            return header_map
        return None

    def _detect_header_with_merge(self, rows: List[List[str]], start_idx: int) -> Optional[Dict[str, int]]:
        """Detect header by merging up to 3 consecutive rows.

        PDFs with vertically-merged cells often split a single logical header
        across multiple rows.  Row 0 may have "STRAND" while Row 1 has
        "SUB-STRAND", "CONTENT STANDARD", etc.  Neither row alone passes the
        match threshold, but merged they do.

        Returns the merged header_map and the number of rows consumed.
        """
        if start_idx >= len(rows):
            return None

        merged: Dict[str, int] = {}
        consumed = 0

        for offset in range(min(3, len(rows) - start_idx)):
            row = rows[start_idx + offset]
            row_map: Dict[str, int] = {}
            row_matched = 0
            for c_idx, cell in enumerate(row):
                normalized = self._normalize_header_text(cell)
                if normalized in HEADER_ALIASES:
                    field = HEADER_ALIASES[normalized]
                    if field not in merged:
                        row_map[field] = c_idx
                        row_matched += 1
            merged.update(row_map)
            consumed += 1
            if len(merged) >= 3:
                return merged

        if len(merged) >= 3:
            return merged
        return None

    def _normalize_header_text(self, text: str) -> str:
        return text.strip().lower().replace('-', ' ').replace('_', ' ').strip()

    def _normalize_row(self, row: List[str], header_map: Dict[str, int]) -> Dict[str, str]:
        """Map cells to canonical field names using header_map: field_name -> column_index."""
        result: Dict[str, str] = {}
        if header_map:
            for field_name, col_index in header_map.items():
                if col_index < len(row):
                    result[field_name] = row[col_index].strip()
                else:
                    result[field_name] = ""
            return result
        for i, cell in enumerate(row):
            result[f"col_{i}"] = cell.strip()
        return result

    def _extract_week_info(self, text: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None

        cleaned = text.strip()

        match = WEEK_NUMBER_PATTERN.search(cleaned)
        if match:
            week_num = int(match.group(1))
            rest = " ".join(match.group(2).split())
            return {
                "week_number": week_num,
                "date": self._parse_date(rest),
            }

        match = WEEK_ONLY_PATTERN.match(cleaned)
        if match:
            week_num = int(match.group(1))
            return {
                "week_number": week_num,
                "date": None
            }

        # Handle "Week N" format (e.g., "Week 1", "Week 2", "WEEK 1") and
        # "Week 1 11 September 2026" / "Week 1\n11 September 2026".
        week_text_pattern = re.match(
            r'^week\s+(\d{1,2})\b(.*)$', cleaned, re.IGNORECASE | re.DOTALL
        )
        if week_text_pattern:
            week_num = int(week_text_pattern.group(1))
            rest = " ".join(week_text_pattern.group(2).split())
            return {
                "week_number": week_num,
                "date": self._parse_date(rest) if rest else None,
            }

        # PDF (and some Word) cells separate the week number and date with a
        # plain space rather than a pipe/newline. Same week cell, different
        # rendering — accept it so PDF extraction is not silently blind.
        match = re.match(
            r'^(\d{1,2})\s+(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})\s*$',
            cleaned,
        )
        if match:
            return {
                "week_number": int(match.group(1)),
                "date": self._parse_date(match.group(2)),
            }

        # "1 11 September 2026" — week number + textual date in one cell.
        match = re.match(
            r'^(\d{1,2})\s+(\d{1,2}\s+[A-Za-z]{3,9}\.?,?\s+\d{4})\s*$',
            cleaned,
        )
        if match:
            return {
                "week_number": int(match.group(1)),
                "date": self._parse_date(match.group(2)),
            }

        if any(kw in cleaned.lower() for kw in SPECIAL_WEEK_KEYWORDS):
            pass

        return None

    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse a source date. Numeric dates are day-first (DD/MM/YYYY).

        Supports: ``11/09/2026``, ``11-09-2026``, ``11.09.2026``,
        ``11 September 2026``, ``11 Sep 2026``, ``September 11, 2026``.
        Returns None when no date can be read — never invents one.
        """
        if not date_str:
            return None
        text = " ".join(str(date_str).split())
        if not text:
            return None

        # Day-first numeric with / - or . separators
        for sep in ['/', '-', '.']:
            if sep in text:
                parts = text.split(sep)
                # Allow trailing junk after the year (e.g. "11/09/2026 (Fri)")
                if len(parts) >= 3:
                    try:
                        d = int(re.sub(r'\D.*$', '', parts[0]) or '0')
                        m = int(re.sub(r'\D.*$', '', parts[1]) or '0')
                        y_raw = re.sub(r'\D.*$', '', parts[2]) or ''
                        y = int(y_raw) if y_raw else 0
                        if y < 100:
                            y += 2000
                        if 1 <= d <= 31 and 1 <= m <= 12 and 2020 <= y <= 2030:
                            return date(y, m, d)
                    except ValueError:
                        continue

        # Textual: "11 September 2026"
        m = _TEXT_DATE_RE.search(text)
        if m:
            day = int(m.group(1))
            month = _MONTHS.get(m.group(2).lower().rstrip('.'))
            year = int(m.group(3))
            if month and 1 <= day <= 31 and 2020 <= year <= 2030:
                try:
                    return date(year, month, day)
                except ValueError:
                    pass

        # Textual: "September 11, 2026"
        m = _TEXT_DATE_RE_US.search(text)
        if m:
            month = _MONTHS.get(m.group(1).lower().rstrip('.'))
            day = int(m.group(2))
            year = int(m.group(3))
            if month and 1 <= day <= 31 and 2020 <= year <= 2030:
                try:
                    return date(year, month, day)
                except ValueError:
                    pass

        return None

    def _date_anywhere_in(self, *chunks: str) -> Optional[date]:
        """First parseable date among the given text chunks."""
        for chunk in chunks:
            if not chunk:
                continue
            d = self._parse_date(chunk)
            if d:
                return d
        return None

    def _is_special_week_text(self, text: str) -> bool:
        text_lower = text.strip().lower()
        return any(kw in text_lower for kw in SPECIAL_WEEK_KEYWORDS)

    def _classify_special_week(self, text: str) -> WeekType:
        text_lower = text.strip().lower()
        if "revision" in text_lower:
            return WeekType.REVISION
        elif "assessment" in text_lower or "exam" in text_lower:
            return WeekType.ASSESSMENT
        elif "sba" in text_lower or "vacation" in text_lower:
            return WeekType.SBA
        return WeekType.OTHER

    def _merge_week_rows(self, week_num: int, rows: List[Dict[str, Any]]) -> ParsedWeek:
        if not rows:
            return ParsedWeek(week_number=week_num)

        first = rows[0]
        week_type = first.get("week_type", WeekType.INSTRUCTION)
        week_date = first.get("date")
        strand = first.get("strand")
        sub_strand = first.get("sub_strand")

        all_content_standards: List[ParsedContentStandard] = []
        all_indicators: List[ParsedIndicator] = []
        all_resources: set = set()

        for row in rows:
            cs_text = row.get("content_standard", "")
            if cs_text:
                cs_code = self._extract_code(cs_text, CONTENT_STANDARD_CODE_PATTERN)
                cs_desc = self._clean_description(cs_text, cs_code)
                if cs_code and cs_desc and not any(c.code == cs_code for c in all_content_standards):
                    all_content_standards.append(ParsedContentStandard(
                        code=cs_code,
                        description=cs_desc
                    ))

            ind_text = row.get("indicators", "")
            if ind_text:
                ind_code = self._extract_code(ind_text, INDICATOR_CODE_PATTERN)
                ind_desc = self._clean_description(ind_text, ind_code)
                if ind_code and ind_desc and not any(i.code == ind_code for i in all_indicators):
                    all_indicators.append(ParsedIndicator(
                        code=ind_code,
                        description=ind_desc
                    ))

            res = row.get("resources", "")
            if res and res.lower() not in ("", "resources", "resource"):
                all_resources.add(res)

        return ParsedWeek(
            week_number=week_num,
            week_ending=week_date,
            week_type=week_type,
            strand=strand,
            sub_strand=sub_strand,
            content_standards=all_content_standards,
            indicators=all_indicators,
            resources=list(all_resources)
        )

    def _extract_code(self, text: str, pattern: re.Pattern) -> str:
        match = pattern.search(text)
        if match:
            return match.group(0)
        return text.split()[0] if text.split() else ""

    def _clean_description(self, text: str, code: str) -> str:
        if code and code in text:
            desc = text.replace(code, "").strip()
        else:
            desc = text.strip()
        desc = re.sub(r'\s+', ' ', desc).strip()
        if not desc:
            # The cell was ONLY the code (common in KG schemes: "k2.1.1.1").
            # Return empty rather than echoing the code as its own description.
            return ""
        # Indicator ranges print as "K2.1.1.1.1-3": rejoin the code and the
        # range tail without the space the code split introduced.
        if desc.startswith("-") and code:
            return f"{code}{desc}"
        return desc

    def _convert_to_weeks(self, parsed_scheme: ParsedScheme) -> List[Week]:
        """Build Week rows. Source week-ending dates are AUTHORITATIVE.

        When the source omits a date the value is derived (previous week + 7
        days, else today) and flagged ``week_ending_derived=True`` so every
        downstream consumer can show DERIVED instead of a silent assumption.
        """
        from datetime import timedelta

        weeks = []
        prev_end: Optional[date] = None
        for pw in parsed_scheme.weeks:
            if pw.week_ending is not None:
                week_ending = pw.week_ending
                derived = False
            else:
                derived = True
                week_ending = (
                    prev_end + timedelta(days=7) if prev_end else date.today()
                )
            start = week_ending
            prev_end = week_ending

            content_std_texts = [f"{cs.code} {cs.description}" for cs in pw.content_standards]
            indicator_texts = [f"{ind.code} {ind.description}" for ind in pw.indicators]

            week = Week(
                week_number=pw.week_number,
                start_date=start,
                end_date=week_ending,
                week_ending_derived=derived,
                week_type=pw.week_type,
                strand=pw.strand,
                sub_strand=pw.sub_strand,
                content_standards=content_std_texts,
                indicators=indicator_texts,
                resources=pw.resources,
                scheme_of_work_id=""
            )
            weeks.append(week)

        weeks.sort(key=lambda w: w.week_number)
        return weeks

    def _run_validation(self, scheme: ParsedScheme):
        if not scheme.weeks:
            self.validation_issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                message="No weeks extracted from the document"
            ))
            return

        for pw in scheme.weeks:
            if pw.week_ending is None:
                self.validation_issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    field="week_ending",
                    message=f"Week {pw.week_number}: No week-ending date found"
                ))

            if pw.week_type == WeekType.INSTRUCTION:
                if not pw.strand:
                    self.validation_issues.append(ValidationIssue(
                        severity=ValidationSeverity.WARNING,
                        field="strand",
                        row_index=pw.week_number,
                        message=f"Week {pw.week_number}: Missing strand"
                    ))
                if not pw.sub_strand:
                    self.validation_issues.append(ValidationIssue(
                        severity=ValidationSeverity.WARNING,
                        field="sub_strand",
                        row_index=pw.week_number,
                        message=f"Week {pw.week_number}: Missing sub-strand"
                    ))
                if not pw.content_standards:
                    self.validation_issues.append(ValidationIssue(
                        severity=ValidationSeverity.WARNING,
                        field="content_standard",
                        row_index=pw.week_number,
                        message=f"Week {pw.week_number}: Missing content standard"
                    ))
                if not pw.indicators:
                    self.validation_issues.append(ValidationIssue(
                        severity=ValidationSeverity.WARNING,
                        field="indicators",
                        row_index=pw.week_number,
                        message=f"Week {pw.week_number}: Missing indicators"
                    ))

            if pw.week_type != WeekType.INSTRUCTION:
                self.validation_issues.append(ValidationIssue(
                    severity=ValidationSeverity.INFO,
                    message=f"Week {pw.week_number}: Special week detected ({pw.week_type.value})"
                ))

    #: Subject keywords that appear inside ordinary early-years curriculum
    #: prose and must not classify a whole document on their own when the
    #: document itself declares an early-years level ("KG TWO", "NURSERY").
    #: e.g. the WAPEF KG scheme's "my family history" cell is curriculum
    #: content, not a History scheme.
    _EARLY_YEARS_LEVEL_RE = re.compile(
        r"\b(?:kg|k\.g|kindergarten|nursery|kg1|kg2)\b", re.IGNORECASE
    )

    def _extract_subject_from_text(self, text: str) -> Optional[str]:
        """Best-effort subject from free text, using the canonical keyword list.

        Specific phrases are tried before generic substrings (Integrated Science
        before Science, Core Mathematics before Mathematics). Detection is only
        a hint — a multi-subject document is confirmed by the teacher, never
        silently classified.

        Early-years documents (KG/Nursery) teach topics that mention secondary
        subjects in prose ("family history", "creative arts"). When the
        document explicitly declares an early-years level, generic single-word
        keyword hits inside that prose are suppressed — an explicit level mark
        beats a coincidental subject word, and the level itself keeps the
        teacher confirmation flow honest instead of a wrong guess.
        """
        text_lower = (text or "").lower()
        early_years = bool(self._EARLY_YEARS_LEVEL_RE.search(text_lower))
        for keyword, subject in SUBJECT_KEYWORDS:
            if keyword not in text_lower:
                continue
            if early_years and " " not in keyword and len(keyword) > 2:
                # Short generic words (ict, history, english, french, …) inside
                # KG/Nursery prose are not subject classifications.
                continue
            if " " not in keyword and len(keyword) <= 3:
                # Short keywords must match as whole words even outside the
                # early-years guard: "ict" inside "depicting" is prose, not a
                # subject. Multi-word phrases keep substring matching.
                if not re.search(
                        r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])",
                        text_lower):
                    continue
            return subject.value
        return None

    def _extract_class_level_from_text(self, text: str, filename: str = "") -> Optional[str]:
        """Class level from the document body (primary), then the filename.

        Uses the code-aware ``_first_signal`` matcher so indicator-code prefixes
        (B7/B8/B9) are never mistaken for a class. The document body is always
        tried before the filename (secondary evidence).
        """
        doc_level = self._first_signal(text)
        if doc_level:
            return doc_level
        normalized_filename = re.sub(r"[_\-]+", " ", filename)
        return self._first_signal(normalized_filename)

    def _extract_term_from_text(self, text: str) -> Optional[str]:
        text_lower = text.lower()
        if 'first term' in text_lower or 'term 1' in text_lower:
            return "First Term"
        elif 'second term' in text_lower or 'term 2' in text_lower:
            return "Second Term"
        elif 'third term' in text_lower or 'term 3' in text_lower:
            return "Third Term"
        return None

    def _extract_academic_year_from_text(self, text: str) -> Optional[str]:
        year_match = re.search(r'(\d{4})\s*[/\-]\s*(\d{4})', text)
        if year_match:
            return f"{year_match.group(1)}/{year_match.group(2)}"
        return None

    def _detect_subject(self, parsed: Optional[ParsedScheme], raw_text: str) -> Optional[Subject]:
        """Detect the subject, or return None when it genuinely cannot be known.

        NEVER defaults to Mathematics (PART E): uncertainty is represented as
        None and surfaced to the teacher as "needs confirmation".
        """
        subj = (parsed.subject if parsed else None) or self._extract_subject_from_text(raw_text)
        if not subj:
            return None
        try:
            detected = Subject(subj)
        except ValueError:
            return None
        return None if detected is Subject.UNKNOWN else detected

    _CLASS_LEVEL_MAPPING = {
        "Nursery": ClassLevel.NURSERY,
        "KG 1": ClassLevel.KG1,
        "KG 2": ClassLevel.KG2,
        "Basic 1": ClassLevel.BASIC_1,
        "Basic 2": ClassLevel.BASIC_2,
        "Basic 3": ClassLevel.BASIC_3,
        "Basic 4": ClassLevel.BASIC_4,
        "Basic 5": ClassLevel.BASIC_5,
        "Basic 6": ClassLevel.BASIC_6,
        "Basic 7": ClassLevel.BASIC_7,
        "Basic 8": ClassLevel.BASIC_8,
        "Basic 9": ClassLevel.BASIC_9,
        "SHS 1": ClassLevel.SHS_1,
        "SHS 2": ClassLevel.SHS_2,
        "SHS 3": ClassLevel.SHS_3,
    }

    #: (keyword, canonical level name) — specific first.
    _LEVEL_SIGNALS = [
        ("basic 7", "Basic 7"), ("b7", "Basic 7"), ("jhs 1", "Basic 7"),
        ("basic 8", "Basic 8"), ("b8", "Basic 8"), ("jhs 2", "Basic 8"),
        ("basic 9", "Basic 9"), ("b9", "Basic 9"), ("jhs 3", "Basic 9"),
        ("basic 10", "Basic 10"), ("b10", "Basic 10"),
        ("shs 1", "SHS 1"), ("senior high 1", "SHS 1"),
        ("shs 2", "SHS 2"), ("senior high 2", "SHS 2"),
        ("shs 3", "SHS 3"), ("senior high 3", "SHS 3"),
        ("basic 1", "Basic 1"), ("basic 2", "Basic 2"),
        ("basic 3", "Basic 3"), ("basic 4", "Basic 4"),
        ("basic 5", "Basic 5"), ("basic 6", "Basic 6"),
        # Kindergarten: digit and word-number spellings ("KG 2", "KG TWO",
        # "K.G. TWO" — real KG scheme titles use both).
        ("kg 1", "KG 1"), ("kg one", "KG 1"), ("kg i", "KG 1"),
        ("kg 2", "KG 2"), ("kg two", "KG 2"), ("kg ii", "KG 2"),
        ("kindergarten 1", "KG 1"), ("kindergarten 2", "KG 2"),
        ("kindergarten two", "KG 2"),
        ("nursery", "Nursery"),
    ]

    @staticmethod
    def _level_hits(text: str) -> List[Tuple[int, str]]:
        """All class-level hits in ``text`` as (position, canonical level).

        Indicator-code prefixes (``B7.1.1.1``) are ignored — see `_first_signal`.
        """
        lower = (text or "").lower()
        hits: List[Tuple[int, str]] = []
        for keyword, level in DOCXParser._LEVEL_SIGNALS:
            pattern = r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![0-9a-z.])"
            for m in re.finditer(pattern, lower):
                hits.append((m.start(), level))
        hits.sort(key=lambda h: h[0])
        return hits

    @staticmethod
    def _first_signal(text: str) -> Optional[str]:
        """Class-level signal from document text, ranked by evidence position.

        Evidence order (not `_LEVEL_SIGNALS` list order):
          1. Earliest hit inside the title zone (first 500 chars — document
             titles carry the true class: "… FOR BASIC 6 - FRENCH").
          2. Otherwise the most frequent level across the body (repeated
             metadata beats a single stray mention).
          3. Otherwise the earliest body hit.

        Never invents a level: no hits → None (Unknown / needs confirmation).
        Curriculum codes such as ``B7.1.1.1.1`` are not level tokens — the
        negative lookahead rejects a token immediately followed by a digit or
        a dot.
        """
        hits = DOCXParser._level_hits(text)
        if not hits:
            return None
        title_hits = [lvl for pos, lvl in hits if pos < 500]
        if title_hits:
            return title_hits[0]
        counts: Dict[str, int] = {}
        for _, lvl in hits:
            counts[lvl] = counts.get(lvl, 0) + 1
        top = max(counts.values())
        winners = [lvl for lvl, n in counts.items() if n == top]
        if len(winners) == 1:
            return winners[0]
        # Tie → earliest occurrence in the body.
        for _, lvl in hits:
            if lvl in winners:
                return lvl
        return None

    def subject_signals(self, raw_text: str, filename: str = "") -> dict:
        """Independent subject signals (document body vs filename) + conflict.

        The document body is authoritative; the filename is secondary evidence
        only (PART H). A mismatch is reported for teacher confirmation.
        """
        doc = self._extract_subject_from_text(raw_text)
        normalized_filename = re.sub(r"[_\-]+", " ", filename or "")
        fn = self._extract_subject_from_text(normalized_filename)
        conflict = bool(doc and fn and doc != fn)
        resolved = None if conflict else (doc or fn)
        return {
            "document": doc,
            "filename": fn,
            "resolved": resolved,
            "conflict": conflict,
        }

    def class_level_signals(self, raw_text: str, filename: str = "") -> dict:
        """Independent class-level signals + reconciliation (PART H).

        The document body is the primary signal; the filename is secondary
        evidence only. They are reconciled, never blindly trusted. A mismatch
        between the two is reported so the teacher can confirm.
        """
        normalized_filename = re.sub(r"[_\-]+", " ", filename or "")
        doc_level = self._first_signal(raw_text)
        fn_level = self._first_signal(normalized_filename)
        conflict = bool(doc_level and fn_level and doc_level != fn_level)
        resolved = None if conflict else (doc_level or fn_level)
        return {
            "document": doc_level,
            "filename": fn_level,
            "resolved": resolved,
            "conflict": conflict,
        }

    def _detect_class_level(
        self, parsed: Optional[ParsedScheme], raw_text: str, filename: str = ""
    ) -> Optional[ClassLevel]:
        """Detect the class level, or return None (never a fabricated Basic 9).

        Reconciliation rule: an explicit value parsed from the table wins; then
        the document body; then the filename (secondary). A body/filename
        mismatch resolves to None → teacher confirmation.
        """
        # Reconciliation ALWAYS runs first: a document-body/filename mismatch
        # must surface as "needs confirmation", not be resolved by whichever
        # value happened to be parsed from the table.
        signals = self.class_level_signals(raw_text, filename)
        if signals["conflict"]:
            return None
        if parsed and parsed.class_level:
            return self._CLASS_LEVEL_MAPPING.get(parsed.class_level)
        return self._CLASS_LEVEL_MAPPING.get(signals["resolved"]) if signals["resolved"] else None

    def _detect_term(self, raw_text: str) -> str:
        return self._extract_term_from_text(raw_text) or "First Term"

    def _detect_academic_year(self, raw_text: str) -> str:
        return self._extract_academic_year_from_text(raw_text) or "2026/2027"
