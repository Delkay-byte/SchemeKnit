"""
SchemeKnit PDF Scheme Parser

PDFs are extremely common for schemes of learning. This parser turns a PDF into
the same ordered "block" stream the DOCX parser produces (paragraph-like text
lines and table rows), then reuses the shared week/strand/indicator grammar and
multi-subject section detection. PDF support must never regress DOCX support —
both feed the identical downstream pipeline.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..models import SchemeOfWork, Subject, ClassLevel
from .docx_parser import DOCXParser
from .subject_keywords import canonical_subject_from_heading, detect_document_title


class PDFParser:
    """Production parser for PDF scheme of work documents."""

    def __init__(self):
        # The week/strand/indicator grammar lives in the DOCX parser; reuse it
        # rather than maintaining a second, drifting implementation.
        self._grammar = DOCXParser()

    # ── Block extraction ────────────────────────────────────────────────

    def _clamp(self, v, lo, hi):
        return max(lo, min(hi, v))

    def _blocks(self, file_path: Path) -> List[Tuple[str, Any]]:
        """Extract ordered blocks: ("paragraph", line) | ("table", rows)."""
        import fitz

        blocks: List[Tuple[str, Any]] = []
        # Diagnostic scan stats: distinguish an image-only (scanned) PDF from a
        # text PDF with no extractable table, so failures give an honest reason.
        scan = {"pages": 0, "text_chars": 0, "blank_pages": 0}
        pdf = fitz.open(file_path)
        try:
            for page in pdf:
                items: List[Tuple[float, str, Any]] = []
                page_chars = 0
                table_boxes: List[Tuple[float, float, float, float]] = []

                try:
                    finder = page.find_tables()
                    for t in getattr(finder, "tables", []) or []:
                        table_boxes.append(tuple(t.bbox[:4]))
                        rows = [
                            [(cell or "").strip() for cell in row]
                            for row in t.extract()
                        ]
                        rows = [r for r in rows if any(c for c in r)]
                        if rows:
                            page_chars += sum(len(c) for row in rows for c in row)
                            items.append((t.bbox[1], "table", rows))
                except Exception:
                    pass

                for b in page.get_text("blocks"):
                    x0, y0, x1, y1 = b[0], b[1], b[2], b[3]
                    text = (b[4] or "").strip()
                    if not text:
                        continue
                    page_chars += len(text)
                    # Skip text already captured by a detected table.
                    inside = False
                    for (bx0, by0, bx1, by1) in table_boxes:
                        if not (x1 < bx0 or x0 > bx1 or y1 < by0 or y0 > by1):
                            inside = True
                            break
                    if inside:
                        continue
                    items.append((y0, "text", text))

                items.sort(key=lambda it: it[0])
                for _, kind, payload in items:
                    if kind == "table":
                        blocks.append(("table", payload))
                    else:
                        for line in payload.splitlines():
                            line = line.strip()
                            if line:
                                blocks.append(("paragraph", line))

                scan["pages"] += 1
                scan["text_chars"] += page_chars
                if page_chars == 0:
                    scan["blank_pages"] += 1
        finally:
            pdf.close()
        self._last_scan = scan
        return blocks

    def _rows_from_text(self, lines: List[str]) -> List[List[str]]:
        """Best-effort table rows when the PDF has no detectable tables.

        Splits on runs of two or more spaces (the usual way a PDF renders
        column gaps without ruled lines). Lines that do not split become
        single-cell rows. This is a fallback only — a genuinely tabular PDF is
        read through the table extractor above.
        """
        rows: List[List[str]] = []
        for line in lines:
            if "|" in line:
                cells = [c.strip() for c in line.split("|")]
            else:
                cells = [c.strip() for c in re.split(r"\s{2,}", line)]
            cells = [c for c in cells if c != ""]
            if cells:
                rows.append(cells)
        return rows

    # ── Public surface (mirrors DOCXParser) ─────────────────────────────

    def _has_real_tables(self, blocks: List[Tuple[str, Any]]) -> bool:
        return any(k == "table" for k, _ in blocks)

    def _scan_stats(self) -> Dict[str, Any]:
        """Machine-readable extraction diagnostic for the last scanned document."""
        scan = getattr(self, "_last_scan", None) or {}
        if not scan.get("pages"):
            return {"reason": "not_scanned", "pages": 0, "text_chars": 0, "blank_pages": 0}
        no_text = (scan.get("text_chars") or 0) == 0
        return {
            "reason": "no_text_layer" if no_text else None,
            "pages": scan["pages"],
            "text_chars": scan["text_chars"],
            "blank_pages": scan["blank_pages"],
        }

    def _text_sections(self, lines: List[str]) -> List[Dict[str, Any]]:
        """Split a text-only PDF into subject sections at heading lines.

        Used when the PDF has no extractable tables (no ruled lines). Each
        section keeps the raw lines that follow its heading so the shared row
        grammar can parse them.
        """
        sections: List[Dict[str, Any]] = []
        current: Optional[Dict[str, Any]] = None
        for line in lines:
            subject = canonical_subject_from_heading(line)
            if subject is not None:
                if current and current["lines"]:
                    sections.append(current)
                current = {"subject": subject, "title": line, "lines": []}
            else:
                if current is None:
                    current = {"subject": None, "title": "", "lines": []}
                current["lines"].append(line)
        if current and current["lines"]:
            sections.append(current)

        merged: List[Dict[str, Any]] = []
        for s in sections:
            if merged and merged[-1]["subject"] == s["subject"]:
                merged[-1]["lines"].extend(s["lines"])
            else:
                merged.append(s)
        return merged

    def _resolve_sections(
        self, blocks: List[Tuple[str, Any]], text_sections: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Normalise section candidates to {subject, title, tables}."""
        if self._has_real_tables(blocks):
            out = []
            for s in self._grammar._detect_sections(blocks):
                if s["subject"] is None:
                    continue
                out.append({
                    "subject": s["subject"],
                    "title": s["title"],
                    "tables": s["tables"],
                })
            return out
        out = []
        for s in text_sections:
            if s["subject"] is None:
                continue
            out.append({
                "subject": s["subject"],
                "title": s["title"],
                "tables": [self._rows_from_text(s["lines"])],
            })
        return out

    async def parse(
        self,
        file_path: Path,
        original_filename: str = None,
        target_subject: str = None,
    ) -> SchemeOfWork:
        blocks = self._blocks(file_path)
        paragraph_lines = [p for k, p in blocks if k == "paragraph"]
        raw_text = "\n".join(paragraph_lines)
        text_sections = self._text_sections(paragraph_lines)

        # Include table cell text in raw_text so that class-level, subject,
        # and term detection can read metadata embedded in table headers
        # (common in Ghanaian scheme PDFs).
        table_text_parts = []
        for k, p in blocks:
            if k == "table":
                for row in p:
                    for cell in row:
                        cell_text = (cell or "").strip()
                        if cell_text:
                            table_text_parts.append(cell_text)
        if table_text_parts:
            raw_text = raw_text + "\n" + "\n".join(table_text_parts)

        tables = [p for k, p in blocks if k == "table"]
        forced_subject = None
        section_miss = False

        if target_subject:
            sections = self._resolve_sections(blocks, text_sections)
            selected = [
                s for s in sections
                if s["subject"] is not None and s["subject"].value == target_subject
            ]
            if selected:
                tables = [t for s in selected for t in s["tables"]]
                forced_subject = selected[0]["subject"]
            elif any(s["subject"] is not None for s in sections):
                # Missing section → empty parse, never a cross-subject mix
                # and never a text fallback that re-reads every heading.
                tables = []
                section_miss = True
            else:
                # Whole-level scheme with NO subject headings anywhere (the
                # KG scheme shape). The teacher's confirmed subject applies to
                # the entire document — there is nothing to mix. An unknown
                # subject name still yields nothing.
                from ..models import Subject as _Subject
                try:
                    forced_subject = _Subject(target_subject)
                except ValueError:
                    tables = []
                    section_miss = True

        if not tables and not section_miss:
            non_heading = [
                p for k, p in blocks
                if k == "paragraph" and canonical_subject_from_heading(p) is None
            ]
            # Wrap the synthesized rows as a single table so downstream code
            # sees the same `[table][row][cell]` shape as a ruled PDF/DOCX.
            rows = self._rows_from_text(non_heading)
            tables = [rows] if rows else []
        if not tables:
            # No usable structure — return an empty scheme; the caller reports
            # the extraction failure rather than inventing content.
            fname = original_filename or file_path.name
            # No usable structure → honest extraction failure, never an empty
            # "successful" curriculum and never a fabricated class/subject.
            from ..models import ValidationIssue, ValidationSeverity

            issue_message = (
                "The PDF could not be extracted. This document appears to be "
                "a scanned or image-only copy with no machine-readable text. "
                "Provide a text-based PDF (Export/Print as PDF) or run it "
                "through a text-layer OCR tool such as Adobe Scan."
                if self._scan_stats()["reason"] == "no_text_layer"
                else ("Scheme could not be reliably extracted. Review the "
                      "document or upload a clearer copy.")
            )
            return SchemeOfWork(
                filename=fname,
                upload_date=datetime.utcnow(),
                subject=self._grammar._detect_subject(None, raw_text) or Subject.UNKNOWN,
                class_level=self._grammar._detect_class_level(None, raw_text, fname) or ClassLevel.UNKNOWN,
                term=self._grammar._detect_term(raw_text),
                academic_year=self._grammar._detect_academic_year(raw_text),
                weeks=[],
                raw_text=raw_text,
                status="extraction_failed",
                validation_issues=[ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    field="weeks",
                    message=issue_message,
                )],
            )

        fname = original_filename or file_path.name
        parsed = self._grammar._parse_scheme(tables, raw_text, fname)
        weeks = self._grammar._convert_to_weeks(parsed)

        return SchemeOfWork(
            filename=fname,
            upload_date=datetime.utcnow(),
            subject=forced_subject or self._grammar._detect_subject(parsed, raw_text) or Subject.UNKNOWN,
            class_level=self._grammar._detect_class_level(parsed, raw_text, fname) or ClassLevel.UNKNOWN,
            term=parsed.term or self._grammar._detect_term(raw_text),
            academic_year=parsed.academic_year or self._grammar._detect_academic_year(raw_text),
            weeks=weeks,
            raw_text=raw_text,
            status="extracted" if weeks else "extraction_failed",
        )

    def analyze(self, file_path: Path, original_filename: str = None) -> Dict[str, Any]:
        """Same contract as DOCXParser.analyze (§4), for PDFs."""
        blocks = self._blocks(file_path)
        lines = [p for k, p in blocks if k == "paragraph"]
        title = detect_document_title(lines)
        raw_text = "\n".join(lines)
        sections = self._resolve_sections(blocks, self._text_sections(lines))

        described: List[Dict[str, Any]] = []
        for s in sections:
            if s["subject"] is None:
                continue
            parsed = self._grammar._parse_scheme(s["tables"], raw_text, file_path.name)
            described.append({
                "subject": s["subject"].value,
                "title": s["title"],
                "week_count": len(parsed.weeks),
            })

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

        # Metadata reconciliation + honest extraction state (PART E/H/J).
        detection_filename = original_filename or file_path.name
        class_signals = self._grammar.class_level_signals(raw_text, detection_filename)
        subject_signals = self._grammar.subject_signals(raw_text, detection_filename)
        needs_confirmation = bool(
            class_signals["conflict"] or subject_signals["conflict"]
            or class_signals["resolved"] is None
            or subject_signals["resolved"] is None
        )
        if status in ("single", "low_confidence") and needs_confirmation:
            status = "needs_confirmation"
        if not non_empty:
            tables = [p for k, p in blocks if k == "table"]
            raw_parsed = self._grammar._parse_scheme(tables, raw_text, file_path.name)
            if not raw_parsed.weeks:
                status = "extraction_failed"
            elif status == "low_confidence":
                status = "needs_confirmation"

        # Machine-readable extraction diagnostic: image-only scans vs. text
        # documents with no table structure are two distinct failure reasons.
        extraction = self._scan_stats()
        if extraction["reason"] is None and not ([p for k, p in blocks if k == "table"] or
                                                 self._rows_from_text([
                                                     p for k, p in blocks
                                                     if k == "paragraph" and canonical_subject_from_heading(p) is None
                                                 ])):
            extraction["reason"] = "no_curriculum_table"

        return {
            "title": title,
            "detected_subjects": [d["subject"] for d in described],
            "sections": described,
            "detection_status": status,
            "needs_confirmation": needs_confirmation,
            "extraction": extraction,
            "metadata": {
                "subject": subject_signals["resolved"],
                "class_level": class_signals["resolved"],
                "subject_signals": subject_signals,
                "class_signals": class_signals,
            },
        }


def get_document_parser(file_path: Path):
    """Return the parser for a document's extension, or None if unsupported."""
    suffix = Path(file_path).suffix.lower()
    if suffix == ".docx":
        return DOCXParser()
    if suffix == ".pdf":
        return PDFParser()
    return None
