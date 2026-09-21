"""
SchemeKnit Curriculum Normalization Layer
==========================================

Canonical representation of a parsed term document.

A term PDF contains:
  DOCUMENT
    → METADATA (academic year, term, class, dates)
    → SUBJECT SECTION[]
      → CURRICULUM WEEK[]
        → CURRICULUM ENTRY[]
          → INDICATOR[]

This module defines the intermediate representation that sits between
raw parsing and lesson generation. Every downstream consumer (allocation,
generation, quality gate, export) reads from this normalized form.

The parser writes to this model. The generation engine reads from it.
No consumer should depend on raw parser internals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional


# ── Enums ──────────────────────────────────────────────────────────────────

class CurriculumWeekType(str, Enum):
    """Classification of curriculum weeks within a term."""
    INSTRUCTION = "instruction"
    REVISION = "revision"
    ASSESSMENT = "assessment"
    SBA_VACATION = "sba_vacation"
    OTHER = "other"


class ExtractionMethod(str, Enum):
    """How a week's data was extracted from the document."""
    PRIMARY = "primary"          # header-mapped column extraction
    FALLBACK = "fallback"        # cell-scan fallback
    MANUAL = "manual"            # teacher-entered


class SectionDetectionConfidence(str, Enum):
    """Confidence level for subject section detection."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


# ── Indicator ──────────────────────────────────────────────────────────────

@dataclass
class Indicator:
    """A single curriculum indicator — the atomic unit of lesson generation.

    ONE indicator → ONE teaching period → ONE lesson plan.
    """
    code: str                          # e.g. "B9.1.1.1.2"
    exact_text: str                    # verbatim from source, including code prefix
    description: str                   # text only (code stripped)
    source_week: int                   # curriculum week number
    source_subject: str                # subject name
    source_entry_order: int = 0       # position within the curriculum entry
    indicator_order: int = 0          # position within the week

    # Interpreted fields (populated during indicator interpretation)
    primary_action: Optional[str] = None       # verb/focus
    expected_performance: Optional[str] = None  # what learners must DO
    knowledge_focus: Optional[str] = None       # content domain
    evidence_of_achievement: Optional[str] = None
    prerequisite_knowledge: Optional[str] = None
    misconception_risks: Optional[str] = None
    assessment_mode: Optional[str] = None
    activity_type: Optional[str] = None


# ── Curriculum Entry (one row in the weekly table) ─────────────────────────

@dataclass
class CurriculumEntry:
    """One row within a curriculum week's table."""
    strand: str
    sub_strand: str
    content_standard: str
    content_standard_code: str = ""
    indicators: List[Indicator] = field(default_factory=list)
    resources: List[str] = field(default_factory=list)
    source_location: str = ""  # e.g. "Page 12, Row 3"


# ── Curriculum Week ────────────────────────────────────────────────────────

@dataclass
class CurriculumWeek:
    """A single week within a subject section.

    May contain multiple entries (rows) and multiple indicators.
    """
    week_number: int
    week_type: CurriculumWeekType = CurriculumWeekType.INSTRUCTION
    week_ending: Optional[date] = None
    entries: List[CurriculumEntry] = field(default_factory=list)
    extraction_method: ExtractionMethod = ExtractionMethod.PRIMARY

    @property
    def all_indicators(self) -> List[Indicator]:
        """Flatten all indicators from all entries in this week."""
        result = []
        for entry in self.entries:
            result.extend(entry.indicators)
        return result

    @property
    def indicator_count(self) -> int:
        return len(self.all_indicators)

    @property
    def strand(self) -> str:
        """Primary strand (from first entry)."""
        return self.entries[0].strand if self.entries else ""

    @property
    def sub_strand(self) -> str:
        """Primary sub-strand (from first entry)."""
        return self.entries[0].sub_strand if self.entries else ""

    @property
    def content_standards(self) -> List[str]:
        """All content standards across entries."""
        return [e.content_standard for e in self.entries if e.content_standard]

    @property
    def all_resources(self) -> List[str]:
        """All resources across entries, deduplicated."""
        seen = set()
        result = []
        for entry in self.entries:
            for r in entry.resources:
                if r not in seen:
                    seen.add(r)
                    result.append(r)
        return result


# ── Subject Section ────────────────────────────────────────────────────────

@dataclass
class SubjectSection:
    """A detected subject section within the term document.

    Contains all weeks and entries for ONE subject.
    """
    subject: str
    title: str = ""
    weeks: List[CurriculumWeek] = field(default_factory=list)
    source_start: int = 0   # block index in the document
    source_end: int = 0     # block index in the document
    detection_confidence: SectionDetectionConfidence = SectionDetectionConfidence.HIGH
    extraction_status: str = "primary"  # primary / fallback_only / mixed / failed

    @property
    def all_indicators(self) -> List[Indicator]:
        """All indicators across all weeks in this section."""
        result = []
        for week in self.weeks:
            result.extend(week.all_indicators)
        return result

    @property
    def total_weeks(self) -> int:
        return len(self.weeks)

    @property
    def instructional_weeks(self) -> int:
        return sum(1 for w in self.weeks if w.week_type == CurriculumWeekType.INSTRUCTION)

    @property
    def revision_weeks(self) -> int:
        return sum(1 for w in self.weeks if w.week_type == CurriculumWeekType.REVISION)

    @property
    def assessment_weeks(self) -> int:
        return sum(1 for w in self.weeks if w.week_type == CurriculumWeekType.ASSESSMENT)

    @property
    def sba_weeks(self) -> int:
        return sum(1 for w in self.weeks if w.week_type == CurriculumWeekType.SBA_VACATION)

    @property
    def total_indicator_count(self) -> int:
        return len(self.all_indicators)

    def summary(self) -> Dict[str, Any]:
        """Human-readable summary for the subject confirmation UI."""
        return {
            "subject": self.subject,
            "title": self.title,
            "total_weeks": self.total_weeks,
            "instructional_weeks": self.instructional_weeks,
            "revision_weeks": self.revision_weeks,
            "assessment_weeks": self.assessment_weeks,
            "sba_weeks": self.sba_weeks,
            "indicator_count": self.total_indicator_count,
            "detection_confidence": self.detection_confidence.value,
            "extraction_status": self.extraction_status,
        }


# ── Curriculum Document (top level) ───────────────────────────────────────

@dataclass
class CurriculumDocument:
    """The fully normalized representation of a term document.

    This is the source-of-truth after parsing and normalization.
    Everything downstream reads from here.
    """
    academic_year: str = ""
    term: str = ""
    class_level: str = ""
    reopening_date: Optional[date] = None
    midterm_break: Optional[date] = None
    closing_date: Optional[date] = None
    subjects: List[SubjectSection] = field(default_factory=list)
    source_filename: str = ""
    parsed_at: Optional[datetime] = None

    def get_subject(self, name: str) -> Optional[SubjectSection]:
        """Find a subject section by name (case-insensitive)."""
        name_lower = name.lower().strip()
        for s in self.subjects:
            if s.subject.lower().strip() == name_lower:
                return s
        return None

    def subject_names(self) -> List[str]:
        return [s.subject for s in self.subjects]

    def summary(self) -> Dict[str, Any]:
        return {
            "academic_year": self.academic_year,
            "term": self.term,
            "class_level": self.class_level,
            "subject_count": len(self.subjects),
            "subjects": [s.summary() for s in self.subjects],
        }


# ── Indicator Code Utilities ──────────────────────────────────────────────

# Matches indicator codes like B9.1.1.1.2, B7.4.3.1.2, 9.1.1.1, B8.2.1.1.1
INDICATOR_CODE_RE = re.compile(r'[Bb]?\d+\.\d+\.\d+\.\d+(?:\.\d+)?')


def split_indicator_text(text: str) -> tuple[str, str]:
    """Split an indicator string into (code, description).

    Input:  "B9.1.1.1.2 Discuss the formation of Igneous rocks"
    Output: ("B9.1.1.1.2", "Discuss the formation of Igneous rocks")
    """
    if not text:
        return ("", "")
    m = INDICATOR_CODE_RE.search(text)
    if m:
        code = m.group(0)
        description = text[m.end():].strip()
        # Strip leading punctuation
        description = re.sub(r'^[:.\s]+', '', description)
        return (code, description)
    return ("", text.strip())


def classify_week_type(week_number: int, entries: List[CurriculumEntry],
                       header_text: str = "") -> CurriculumWeekType:
    """Classify a curriculum week based on its content and position.

    Rules:
    - If header/content mentions 'revision' → REVISION
    - If header/content mentions 'assessment', 'exam', 'test' → ASSESSMENT
    - If header/content mentions 'sba', 'vacation', 'activity' → SBA_VACATION
    - If entries have indicators → INSTRUCTION
    - Otherwise → OTHER
    """
    check_text = header_text.lower()
    for entry in entries:
        check_text += " " + entry.strand.lower()
        check_text += " " + entry.sub_strand.lower()
        check_text += " " + entry.content_standard.lower()

    if any(kw in check_text for kw in ["revision", "revise", "review"]):
        return CurriculumWeekType.REVISION
    if any(kw in check_text for kw in ["assessment", "exam", "examination", "test", "terminal"]):
        return CurriculumWeekType.ASSESSMENT
    if any(kw in check_text for kw in ["sba", "vacation", "activity", "activities", "closure"]):
        return CurriculumWeekType.SBA_VACATION

    # If the week has indicators, it's instructional
    has_indicators = any(e.indicators for e in entries)
    if has_indicators:
        return CurriculumWeekType.INSTRUCTION

    return CurriculumWeekType.OTHER
