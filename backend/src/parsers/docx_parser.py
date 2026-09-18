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

    async def parse(self, file_path: Path, original_filename: str = None) -> SchemeOfWork:
        """Parse a scheme document.

        `original_filename` is the name the teacher's file had on their machine.
        It is what the UI must display; the on-disk storage name (UUID-based) is
        never shown to users.
        """
        doc = Document(file_path)
        raw_text = self._extract_raw_text(doc)
        tables_data = self._extract_tables(doc)
        parsed_scheme = self._parse_scheme(tables_data, raw_text, file_path.name)

        weeks = self._convert_to_weeks(parsed_scheme)

        scheme = SchemeOfWork(
            filename=original_filename or file_path.name,
            upload_date=datetime.utcnow(),
            subject=self._detect_subject(parsed_scheme, raw_text),
            class_level=self._detect_class_level(parsed_scheme, raw_text),
            term=parsed_scheme.term or self._detect_term(raw_text),
            academic_year=parsed_scheme.academic_year or self._detect_academic_year(raw_text),
            weeks=weeks,
            raw_text=raw_text,
            status="extracted"
        )
        return scheme

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
        scheme.class_level = self._extract_class_level_from_text(raw_text)
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

        for t_idx, r_idx, row in all_rows:
            if t_idx not in seen_headers_in_table:
                detected = self._detect_header(row)
                if detected:
                    header_map = detected
                    seen_headers_in_table[t_idx] = True
                    continue
                else:
                    seen_headers_in_table[t_idx] = False

            if seen_headers_in_table.get(t_idx) is True and r_idx == 0:
                continue

            normalized = self._normalize_row(row, header_map)

            week_text = normalized.get("week_ending", "")
            week_info = self._extract_week_info(week_text)

            if week_info:
                current_week = week_info["week_number"]
                current_date = week_info["date"]
                current_strand = None
                current_sub_strand = None
                current_resources = []

                if current_week not in week_rows:
                    week_rows[current_week] = []

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
        text_lower = text.lower()
        if 'mathematics' in text_lower or 'maths' in text_lower or 'math' in text_lower:
            return "Mathematics"
        elif 'science' in text_lower:
            return "Science"
        elif 'english' in text_lower:
            return "English Language"
        elif 'social studies' in text_lower:
            return "Social Studies"
        elif 'ict' in text_lower or 'computing' in text_lower:
            return "ICT"
        return None

    def _extract_class_level_from_text(self, text: str) -> Optional[str]:
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
        for keyword, level in levels:
            if keyword in text_lower:
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

    def _detect_subject(self, parsed: ParsedScheme, raw_text: str) -> Subject:
        subj = parsed.subject or self._extract_subject_from_text(raw_text)
        mapping = {
            "Mathematics": Subject.MATHEMATICS,
            "Science": Subject.SCIENCE,
            "English Language": Subject.ENGLISH,
            "Social Studies": Subject.SOCIAL_STUDIES,
            "ICT": Subject.ICT,
        }
        return mapping.get(subj, Subject.MATHEMATICS)

    def _detect_class_level(self, parsed: ParsedScheme, raw_text: str) -> ClassLevel:
        level = parsed.class_level or self._extract_class_level_from_text(raw_text)
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
