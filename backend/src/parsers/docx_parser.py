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
    SUBJECT_KEYWORDS, canonical_subject_from_heading, detect_document_title,
)


HEADER_ALIASES = {
    "week ending": "week_ending",
    "week": "week_ending",
    "week no": "week_ending",
    "week number": "week_ending",
    "strand": "strand",
    "sub-strand": "sub_strand",
    "sub strand": "sub_strand",
    "sub_strand": "sub_strand",
    "content standard": "content_standard",
    "content standards": "content_standard",
    "indicators": "indicators",
    "indicator": "indicators",
    "resources": "resources",
    "resource": "resources",
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

WEEK_NUMBER_PATTERN = re.compile(r'^(\d{1,2})\s*[\|\n\r]+\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})')
WEEK_ONLY_PATTERN = re.compile(r'^(\d{1,2})$')
DATE_SLASH_PATTERN = re.compile(r'(\d{1,2})/(\d{1,2})/(\d{2,4})')
DATE_DASH_PATTERN = re.compile(r'(\d{1,2})-(\d{1,2})-(\d{2,4})')
INDICATOR_CODE_PATTERN = re.compile(r'[Bb]?\d+\.\d+\.\d+\.\d+(\.\d+)?')
CONTENT_STANDARD_CODE_PATTERN = re.compile(r'[Bb]?\d+\.\d+\.\d+\.\d+')


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

        filename_for_detection = original_filename or file_path.name
        parsed_scheme = self._parse_scheme(tables_data, raw_text, file_path.name)

        weeks = self._convert_to_weeks(parsed_scheme)

        scheme = SchemeOfWork(
            filename=filename_for_detection,
            upload_date=datetime.utcnow(),
            subject=forced_subject or self._detect_subject(parsed_scheme, raw_text),
            class_level=self._detect_class_level(parsed_scheme, raw_text, filename_for_detection),
            term=parsed_scheme.term or self._detect_term(raw_text),
            academic_year=parsed_scheme.academic_year or self._detect_academic_year(raw_text),
            weeks=weeks,
            raw_text=raw_text,
            status="extracted"
        )
        return scheme

    # ── Multi-subject document detection (§4) ────────────────────────────

    def analyze(self, file_path: Path) -> Dict[str, Any]:
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

        return {
            "title": title,
            "detected_subjects": [d["subject"] for d in described],
            "sections": described,
            "detection_status": status,
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

    def _detect_sections(self, blocks: List[Tuple[str, Any]]) -> List[Dict[str, Any]]:
        """Split ordered blocks into subject sections at subject headings."""
        sections: List[Dict[str, Any]] = []
        current: Optional[Dict[str, Any]] = None

        for kind, payload in blocks:
            if kind == "paragraph":
                subject = canonical_subject_from_heading(payload)
                if subject is not None:
                    if current and current["tables"]:
                        sections.append(current)
                    current = {"subject": subject, "title": payload, "tables": []}
            else:  # table
                if current is None:
                    current = {"subject": None, "title": "", "tables": []}
                current["tables"].append(payload)

        if current and current["tables"]:
            sections.append(current)

        # Merge consecutive sections that share a subject (repeated headings).
        merged: List[Dict[str, Any]] = []
        for s in sections:
            if merged and merged[-1]["subject"] == s["subject"]:
                merged[-1]["tables"].extend(s["tables"])
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
            date_str = match.group(2)
            parsed_date = self._parse_date(date_str)
            return {
                "week_number": week_num,
                "date": parsed_date
            }

        match = WEEK_ONLY_PATTERN.match(cleaned)
        if match:
            week_num = int(match.group(1))
            return {
                "week_number": week_num,
                "date": None
            }

        # Handle "Week N" format (e.g., "Week 1", "Week 2", "WEEK 1")
        week_text_pattern = re.match(r'^week\s+(\d{1,2})\b', cleaned, re.IGNORECASE)
        if week_text_pattern:
            week_num = int(week_text_pattern.group(1))
            return {
                "week_number": week_num,
                "date": None
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

        if any(kw in cleaned.lower() for kw in SPECIAL_WEEK_KEYWORDS):
            pass

        return None

    def _parse_date(self, date_str: str) -> Optional[date]:
        date_str = date_str.strip()

        for sep in ['/', '-', '.']:
            if sep in date_str:
                parts = date_str.split(sep)
                if len(parts) == 3:
                    try:
                        d = int(parts[0])
                        m = int(parts[1])
                        y = int(parts[2])
                        if y < 100:
                            y += 2000
                        if 1 <= d <= 31 and 1 <= m <= 12 and 2020 <= y <= 2030:
                            return date(y, m, d)
                    except ValueError:
                        continue

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
                if cs_code and not any(c.code == cs_code for c in all_content_standards):
                    all_content_standards.append(ParsedContentStandard(
                        code=cs_code,
                        description=cs_desc
                    ))

            ind_text = row.get("indicators", "")
            if ind_text:
                ind_code = self._extract_code(ind_text, INDICATOR_CODE_PATTERN)
                ind_desc = self._clean_description(ind_text, ind_code)
                if ind_code and not any(i.code == ind_code for i in all_indicators):
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
        return desc if desc else text.strip()

    def _convert_to_weeks(self, parsed_scheme: ParsedScheme) -> List[Week]:
        weeks = []
        for pw in parsed_scheme.weeks:
            week_ending = pw.week_ending or date.today()
            start = week_ending

            content_std_texts = [f"{cs.code} {cs.description}" for cs in pw.content_standards]
            indicator_texts = [f"{ind.code} {ind.description}" for ind in pw.indicators]

            week = Week(
                week_number=pw.week_number,
                start_date=start,
                end_date=week_ending,
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

    def _extract_subject_from_text(self, text: str) -> Optional[str]:
        """Best-effort subject from free text, using the canonical keyword list.

        Specific phrases are tried before generic substrings (Integrated Science
        before Science, Core Mathematics before Mathematics). Detection is only
        a hint — a multi-subject document is confirmed by the teacher, never
        silently classified.
        """
        text_lower = (text or "").lower()
        for keyword, subject in SUBJECT_KEYWORDS:
            if keyword in text_lower:
                return subject.value
        return None

    def _extract_class_level_from_text(self, text: str, filename: str = "") -> Optional[str]:
        # Combine document text and filename for detection
        # Normalize underscores and hyphens in filename to spaces for matching
        import re as _re
        normalized_filename = _re.sub(r"[_\-]+", " ", filename)
        combined = f"{text} {normalized_filename}".lower()
        text_lower = text.lower()
        levels = [
            ("basic 7", "Basic 7"), ("b7", "Basic 7"), ("jhs 1", "Basic 7"),
            ("basic 8", "Basic 8"), ("b8", "Basic 8"), ("jhs 2", "Basic 8"),
            ("basic 9", "Basic 9"), ("b9", "Basic 9"), ("jhs 3", "Basic 9"),
            ("basic 10", "Basic 10"), ("b10", "Basic 10"),
            ("shs 1", "SHS 1"), ("senior high 1", "SHS 1"),
            ("shs 2", "SHS 2"), ("senior high 2", "SHS 2"),
            ("shs 3", "SHS 3"), ("senior high 3", "SHS 3"),
        ]
        # First try document text (higher confidence)
        for keyword, level in levels:
            if keyword in text_lower:
                return level
        # Then try filename as secondary signal
        for keyword, level in levels:
            if keyword in combined:
                return level
        return None

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

    def _detect_subject(self, parsed: Optional[ParsedScheme], raw_text: str) -> Subject:
        subj = (parsed.subject if parsed else None) or self._extract_subject_from_text(raw_text)
        if not subj:
            # Never invent a subject classification — leave the safe default.
            return Subject.MATHEMATICS
        try:
            return Subject(subj)
        except ValueError:
            return Subject.MATHEMATICS

    def _detect_class_level(self, parsed: Optional[ParsedScheme], raw_text: str, filename: str = "") -> ClassLevel:
        level = (parsed.class_level if parsed else None) or self._extract_class_level_from_text(raw_text, filename)
        mapping = {
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
        return mapping.get(level, ClassLevel.BASIC_9)

    def _detect_term(self, raw_text: str) -> str:
        return self._extract_term_from_text(raw_text) or "First Term"

    def _detect_academic_year(self, raw_text: str) -> str:
        return self._extract_academic_year_from_text(raw_text) or "2026/2027"
