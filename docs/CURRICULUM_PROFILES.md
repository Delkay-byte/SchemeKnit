# TeachFlow Curriculum Profiles

## Overview

TeachFlow uses **Curriculum Profiles** to adapt its behavior for different educational levels. Each profile defines how the system interprets curriculum data and generates lesson plans for a specific level of Ghanaian education.

## Educational Levels

| Level | Class Levels | Profile |
|-------|-------------|---------|
| Early Childhood | Nursery, KG 1, KG 2 | Early Childhood Profile |
| Primary | Basic 1–6 | Primary Profile |
| Junior High School | Basic 7–9 (JHS 1–3) | JHS Profile |
| Senior High School | SHS 1–3 | SHS Profile |

## What a Profile Defines

Each curriculum profile specifies:

- **Supported class levels** — which classes the profile applies to
- **Lesson plan fields** — which fields appear in generated lessons
- **Standard terminology** — level-appropriate labels
- **Assessment expectations** — what kind of assessment is appropriate
- **Template family** — which template family to use
- **Generation rules** — default lessons per week, duration, etc.
- **Validation rules** — level-specific validation requirements
- **AI behavior** — how AI enrichment should adapt to the level

## Profile Details

### Early Childhood Profile
- Activity-based lesson format
- Play-based learning emphasis
- Observation-focused assessment
- Shorter lesson duration (30 min)
- 5 lessons per week typical

### Primary Profile
- Strand/sub-strand structure
- Simplified curriculum mapping
- Standard primary lesson plan
- 35-minute lessons typical
- 3 lessons per week

### JHS Profile
- Full GES curriculum mapping
- Strand → Sub-strand → Content Standard → Indicator
- Core competencies included
- 60-minute lessons
- 3 lessons per week

### SHS Profile
- Extended JHS structure with additional fields
- Essential questions
- Differentiation strategies
- Homework/follow-up
- 80-minute lessons typical
- 3 lessons per week

## Architecture

```
Uploaded Document
  → Parser (deterministic)
  → Normalized Scheme
  → Curriculum Profile (selected by class level)
  → Lesson Allocation
  → LessonPlan (profile-aware fields)
  → Template (renders to DOCX/PDF)
```

The parser is **separate** from the curriculum profile. The same parser handles all document formats. The profile determines how the allocated data maps to lesson plan fields.

## Usage

When a teacher uploads a scheme of work, TeachFlow:
1. Detects the class level from the document
2. Selects the appropriate curriculum profile
3. Uses the profile's fields and rules for generation
4. Selects a template from the matching template family
