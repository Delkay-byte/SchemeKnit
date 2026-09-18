"""
SchemeKnit Curriculum Validator
"""

from typing import List, Tuple, Dict, Any
from ..models import (
    SchemeOfWork, Week, Strand, SubStrand, ContentStandard, Indicator,
    GenerationConfig, CurriculumAllocation, Holiday
)
from datetime import date, timedelta


class CurriculumValidator:
    """Validates extracted curriculum data."""
    
    def validate_scheme(self, scheme: SchemeOfWork) -> Dict[str, Any]:
        """Validate the entire scheme of work."""
        issues = []
        warnings = []
        
        # Validate basic fields
        if not scheme.subject:
            issues.append("Subject not detected")
        if not scheme.class_level:
            issues.append("Class level not detected")
        if not scheme.term:
            issues.append("Term not detected")
        
        # Validate weeks
        if not scheme.weeks:
            issues.append("No weeks found in the scheme")
        else:
            for week in scheme.weeks:
                week_issues = self._validate_week(week)
                issues.extend(week_issues)
        
        return {
            "is_valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings
        }
    
    def _validate_week(self, week: Week) -> List[str]:
        """Validate a single week."""
        issues = []
        
        if week.week_number <= 0:
            issues.append(f"Week {week.id}: Invalid week number")
        
        if not week.strands:
            issues.append(f"Week {week.week_number}: No strands found")
        
        for strand in week.strands:
            strand_issues = self._validate_strand(strand, week.week_number)
            issues.extend(strand_issues)
        
        return issues
    
    def _validate_strand(self, strand: Strand, week_number: int) -> List[str]:
        """Validate a strand."""
        issues = []
        
        if not strand.name:
            issues.append(f"Week {week_number}: Strand has no name")
        
        if not strand.sub_strands:
            issues.append(f"Week {week_number}, Strand '{strand.name}': No sub-strands found")
        
        for sub_strand in strand.sub_strands:
            sub_issues = self._validate_sub_strand(sub_strand, week_number, strand.name)
            issues.extend(sub_issues)
        
        return issues
    
    def _validate_sub_strand(self, sub_strand: SubStrand, week_number: int, strand_name: str) -> List[str]:
        """Validate a sub-strand."""
        issues = []
        
        if not sub_strand.name:
            issues.append(f"Week {week_number}, Strand '{strand_name}': Sub-strand has no name")
        
        if not sub_strand.content_standards:
            issues.append(f"Week {week_number}, Strand '{strand_name}', Sub-strand '{sub_strand.name}': No content standards found")
        
        for cs in sub_strand.content_standards:
            cs_issues = self._validate_content_standard(cs, week_number, strand_name, sub_strand.name)
            issues.extend(cs_issues)
        
        return issues
    
    def _validate_content_standard(self, cs: ContentStandard, week_number: int, strand_name: str, sub_strand_name: str) -> List[str]:
        """Validate a content standard."""
        issues = []
        
        if not cs.code:
            issues.append(f"Week {week_number}, Strand '{strand_name}', Sub-strand '{sub_strand_name}': Content standard has no code")
        
        if not cs.description:
            issues.append(f"Week {week_number}, Strand '{strand_name}', Sub-strand '{sub_strand_name}': Content standard has no description")
        
        if not cs.indicators:
            issues.append(f"Week {week_number}, Strand '{strand_name}', Sub-strand '{sub_strand_name}': Content standard has no indicators")
        
        return issues


class CurriculumAllocator:
    """Allocates curriculum content into lessons based on configuration."""
    
    def calculate_allocation(
        self, 
        scheme: SchemeOfWork, 
        config: GenerationConfig
    ) -> CurriculumAllocation:
        """Calculate curriculum allocation based on configuration."""
        
        # Calculate available teaching days
        available_days = self._calculate_available_days(config)
        
        # Calculate total available lessons
        total_available_lessons = available_days * config.lessons_per_week
        
        # Count required lessons (based on curriculum content)
        required_lessons = self._count_required_lessons(scheme)
        
        # Calculate coverage
        coverage_percentage = (required_lessons / total_available_lessons * 100) if total_available_lessons > 0 else 0
        
        # Find unallocated indicators
        unallocated_indicators = self._find_unallocated_indicators(scheme, total_available_lessons)
        
        # Generate warnings and suggestions
        warnings = self._generate_warnings(total_available_lessons, required_lessons)
        suggestions = self._generate_suggestions(total_available_lessons, required_lessons)
        
        return CurriculumAllocation(
            total_available_lessons=total_available_lessons,
            required_lessons=required_lessons,
            allocated_lessons=min(required_lessons, total_available_lessons),
            unallocated_indicators=unallocated_indicators,
            coverage_percentage=coverage_percentage,
            warnings=warnings,
            suggestions=suggestions
        )
    
    def _calculate_available_days(self, config: GenerationConfig) -> int:
        """Calculate available teaching days in the term."""
        total_days = (config.term_end_date - config.term_start_date).days + 1
        
        # Count teaching days (excluding weekends and holidays)
        teaching_days = 0
        current_date = config.term_start_date
        
        while current_date <= config.term_end_date:
            # Check if it's a teaching day (0=Monday, 6=Sunday)
            if current_date.weekday() in config.teaching_days:
                # Check if it's not a holiday
                is_holiday = False
                for holiday in config.holidays:
                    if holiday.date == current_date:
                        is_holiday = True
                        break
                
                if not is_holiday:
                    teaching_days += 1
            
            current_date += timedelta(days=1)
        
        return teaching_days
    
    def _count_required_lessons(self, scheme: SchemeOfWork) -> int:
        """Count the number of lessons required by the curriculum."""
        total_indicators = 0
        
        for week in scheme.weeks:
            for strand in week.strands:
                for sub_strand in strand.sub_strands:
                    for cs in sub_strand.content_standards:
                        total_indicators += len(cs.indicators)
        
        # Each indicator typically requires one lesson
        return total_indicators
    
    def _find_unallocated_indicators(
        self, 
        scheme: SchemeOfWork, 
        total_lessons: int
    ) -> List[Indicator]:
        """Find indicators that cannot be allocated to lessons."""
        all_indicators = []
        
        for week in scheme.weeks:
            for strand in week.strands:
                for sub_strand in strand.sub_strands:
                    for cs in sub_strand.content_standards:
                        all_indicators.extend(cs.indicators)
        
        # If we have more indicators than lessons, some won't be allocated
        if len(all_indicators) > total_lessons:
            return all_indicators[total_lessons:]
        
        return []
    
    def _generate_warnings(self, available: int, required: int) -> List[str]:
        """Generate warnings based on allocation."""
        warnings = []
        
        if required > available:
            difference = required - available
            warnings.append(
                f"WARNING — {difference} additional lesson period{'s' if difference > 1 else ''} are required."
            )
        elif required < available:
            difference = available - required
            warnings.append(
                f"NOTE — {difference} additional lesson period{'s' if difference > 1 else ''} available for revision or enrichment."
            )
        
        return warnings
    
    def _generate_suggestions(self, available: int, required: int) -> List[str]:
        """Generate suggestions for improving allocation."""
        suggestions = []
        
        if required > available:
            suggestions.append("Consider combining related indicators into single lessons")
            suggestions.append("Move some content to homework or self-study")
            suggestions.append("Extend the term if possible")
        elif required < available:
            suggestions.append("Use extra periods for revision and assessment")
            suggestions.append("Add enrichment activities for advanced learners")
            suggestions.append("Include practical sessions or field trips")
        
        return suggestions