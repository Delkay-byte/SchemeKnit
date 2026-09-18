"""
SchemeKnit Curriculum Coverage Validation
==========================================

Validates that every instruction indicator is allocated to exactly one
lesson. The core invariant of the indicator→period allocation model:

    ONE INDICATOR → EXACTLY ONE PRIMARY LESSON

No indicator may disappear (missing allocation).
No indicator may appear as the primary indicator of multiple lessons
(duplicate allocation).
"""

from typing import List, Dict, Tuple
from collections import Counter, defaultdict

from ..models import (
    Week, WeekType, CurriculumCoverage, AllocatedIndicator,
    ValidationIssue, ValidationSeverity
)
from .allocation_engine import AllocationEngine


class CoverageValidator:
    """Validates curriculum coverage and allocation completeness."""

    def validate(
        self,
        weeks: List[Week],
        coverage: CurriculumCoverage,
    ) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []

        instruction_weeks = [w for w in weeks if w.week_type == WeekType.INSTRUCTION]
        total_expected = sum(
            len(AllocationEngine._split_indicators(w.indicators))
            for w in instruction_weeks
        )

        # ── 1. Indicator count integrity ─────────────────────────────
        if coverage.total_indicators != total_expected:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                message=(
                    f"Indicator count mismatch: expected {total_expected}, "
                    f"got {coverage.total_indicators}"
                ),
            ))

        # ── 2. Unallocated indicators ────────────────────────────────
        if coverage.indicators_unallocated > 0:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                message=f"{coverage.indicators_unallocated} indicators are unallocated",
            ))

        # ── 3. Duplicate primary allocations ─────────────────────────
        # An indicator must be the primary focus of EXACTLY ONE lesson.
        code_counter: Counter = Counter()
        for alloc in coverage.allocations:
            code_counter[alloc.indicator_code] += 1

        duplicated = {code: count for code, count in code_counter.items() if count > 1}
        if duplicated:
            for code, count in sorted(duplicated.items()):
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    field="indicator",
                    message=f"Indicator {code} is the primary indicator of {count} lessons (expected exactly 1)",
                ))

        # ── 4. Missing indicators ────────────────────────────────────
        # Every indicator in every instruction week must have an allocation.
        # Split concatenated strings the same way the allocation engine does
        # so a merged "B9.x.1 ... B9.x.2 ..." string counts as two indicators.
        expected_codes: Dict[int, set] = defaultdict(set)
        for w in instruction_weeks:
            for ind_text in AllocationEngine._split_indicators(w.indicators):
                # Extract the code the same way the allocation engine does
                import re
                m = re.search(r'[Bb]?\d+\.\d+\.\d+\.\d+(\.\d+)?', ind_text)
                code = m.group(0) if m else ind_text[:30]
                expected_codes[w.week_number].add(code)

        allocated_codes = set(a.indicator_code for a in coverage.allocations)
        all_expected = set()
        for codes in expected_codes.values():
            all_expected.update(codes)

        missing = all_expected - allocated_codes
        if missing:
            for code in sorted(missing):
                # Find which week it belongs to
                wn = next((w for w, codes in expected_codes.items() if code in codes), "?")
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    field="indicator",
                    message=f"Indicator {code} (Week {wn}) has no lesson allocation — it would disappear from the plan",
                ))

        # ── 5. Per-week lesson count vs indicator count ──────────────
        # Each instruction week must produce exactly one lesson per indicator.
        lessons_per_week: Dict[int, int] = defaultdict(int)
        for alloc in coverage.allocations:
            lessons_per_week[alloc.week_number] += 1

        for w in instruction_weeks:
            n_ind = len(AllocationEngine._split_indicators(w.indicators))
            if n_ind == 0:
                continue
            actual = lessons_per_week.get(w.week_number, 0)
            if actual != n_ind:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    field="week",
                    message=(
                        f"Week {w.week_number}: {n_ind} indicators but "
                        f"{actual} lessons allocated (expected {n_ind})"
                    ),
                ))

        # ── 6. Empty strand info ─────────────────────────────────────
        empty_strands = [
            a for a in coverage.allocations
            if not a.strand and not a.sub_strand
        ]
        if empty_strands:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.INFO,
                message=f"{len(empty_strands)} allocations have no strand/sub-strand info",
            ))

        # ── 7. Coverage percentage ───────────────────────────────────
        if coverage.coverage_percentage < 100 and coverage.total_indicators > 0:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                message=f"Curriculum coverage is {coverage.coverage_percentage:.1f}% (expected 100%)",
            ))

        # ── 8. Surface allocation conflicts ──────────────────────────
        for conflict in coverage.allocation_conflicts:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                field="allocation",
                message=conflict,
            ))

        return issues

    def generate_report(
        self,
        weeks: List[Week],
        coverage: CurriculumCoverage,
    ) -> Dict:
        instruction_weeks = [w for w in weeks if w.week_type == WeekType.INSTRUCTION]
        total_indicators = sum(
            len(AllocationEngine._split_indicators(w.indicators))
            for w in instruction_weeks
        )

        # Per-week allocation summary for the review UI
        week_summaries = []
        lessons_per_week: Dict[int, int] = defaultdict(int)
        for alloc in coverage.allocations:
            lessons_per_week[alloc.week_number] += 1

        for w in sorted(instruction_weeks, key=lambda x: x.week_number):
            n_indicators = len(AllocationEngine._split_indicators(w.indicators))
            n_lessons = lessons_per_week.get(w.week_number, 0)
            cs = w.content_standards[0] if w.content_standards else ""
            week_summaries.append({
                "week_number": w.week_number,
                "week_type": w.week_type.value if hasattr(w.week_type, 'value') else str(w.week_type),
                "strand": w.strand or "",
                "sub_strand": w.sub_strand or "",
                "content_standard": cs,
                "indicator_count": n_indicators,
                "lesson_count": n_lessons,
                "periods": [
                    {
                        "period_index": a.period_index,
                        "indicator_code": a.indicator_code,
                        "indicator_description": a.indicator_description,
                        "lesson_date": a.lesson_date.isoformat() if a.lesson_date else None,
                    }
                    for a in sorted(
                        [x for x in coverage.allocations if x.week_number == w.week_number],
                        key=lambda x: x.period_index,
                    )
                ],
            })

        return {
            "total_instructional_weeks": len(instruction_weeks),
            "total_curriculum_indicators": total_indicators,
            "total_generated_lessons": coverage.total_generated_lessons,
            "total_periods_allocated": coverage.total_periods_allocated,
            "indicators_allocated": coverage.indicators_allocated,
            "indicators_unallocated": coverage.indicators_unallocated,
            "indicators_duplicated": coverage.indicators_duplicated,
            "coverage_percentage": coverage.coverage_percentage,
            "warnings": coverage.warnings,
            "allocation_conflicts": coverage.allocation_conflicts,
            "weeks": week_summaries,
        }
