# TeachFlow Template Validation Matrix

## Overview

Each template is classified by its source verification status.

## Source Types

- **VERIFIED SOURCE TEMPLATE**: Based on an actual verified GES document
- **TEACHFLOW STANDARD TEMPLATE**: Designed by TeachFlow based on GES guidelines
- **NOT YET VERIFIED**: Template exists but not yet validated against real documents

## Template Validation Matrix

| Template ID | Name | Level | Family | Source Type | Real Document Tested | Status |
|-------------|------|-------|--------|-------------|---------------------|--------|
| tpl-ec-activity | Activity-Based (KG) | Early Childhood | early_childhood | TEACHFLOW STANDARD | No | PARTIAL |
| tpl-primary-standard | Standard (Primary) | Primary | primary | TEACHFLOW STANDARD | No | PARTIAL |
| tpl-jhs-ges | GES-Style (JHS) | JHS | jhs | TEACHFLOW STANDARD | Partial | PARTIAL |
| tpl-jhs-professional | Professional (JHS) | JHS | jhs | TEACHFLOW STANDARD | No | PENDING |
| tpl-shs-ges | GES-Style (SHS) | SHS | shs | TEACHFLOW STANDARD | No | PENDING |

## Status Definitions

- **VERIFIED**: Template has been tested against real documents and produces correct output
- **PARTIAL**: Template works but has not been fully validated against all scenarios
- **PENDING**: Template exists but has not been tested with real documents

## Lower-Level Classification

### Early Childhood (Nursery, KG 1, KG 2)
- Template family: early_childhood
- Source type: TEACHFLOW STANDARD
- Verified against real documents: No
- Note: Based on GES guidelines for early childhood education. Actual format may vary by school.

### Primary (Basic 1-6)
- Template family: primary
- Source type: TEACHFLOW STANDARD
- Verified against real documents: No
- Note: Based on GES primary curriculum structure. Specific school formats not yet validated.

### JHS (Basic 7-9)
- Template family: jhs
- Source type: TEACHFLOW STANDARD
- Verified against real documents: Partial
- Note: Based on GES JHS curriculum structure. Partially validated with Basic 9 Science and Mathematics schemes.

### SHS (SHS 1-3)
- Template family: shs
- Source type: TEACHFLOW STANDARD
- Verified against real documents: No
- Note: Based on GES SHS curriculum structure. Not yet validated with real SHS documents.

## Recommendations

1. **Before claiming any template as "official"**: Obtain and test against actual GES lesson plan samples
2. **For lower-level templates**: Seek validation from experienced Nursery/KG/Primary teachers
3. **Document differences**: Each school may have variations; templates should be flexible
4. **User feedback**: Allow teachers to report format issues for continuous improvement

## Future Work

- Obtain verified GES lesson plan templates for all levels
- Test each template with real documents
- Update validation status based on real-world usage
