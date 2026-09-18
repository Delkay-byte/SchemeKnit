# TeachFlow Template Architecture

## Overview

TeachFlow's template system separates **educational content** from **presentation**. The same LessonPlan data can be rendered through multiple templates without regeneration.

## Template Hierarchy

```
TemplateFamily (early_childhood, primary, jhs, shs)
  └── Template (specific variant)
        └── TemplateSection (logical grouping)
              └── TemplateField (individual field)
```

## Template Families

### Family A: Early Childhood (Nursery, KG)
- Activity-based format
- Observation-focused assessment
- Play-based learning structure
- Simplified fields

### Family B: Primary (Basic 1–6)
- Strand/sub-strand structure
- Standard curriculum mapping
- Age-appropriate activities

### Family C: JHS (Basic 7–9)
- Full GES curriculum mapping
- Strand → Sub-strand → Content Standard → Indicator
- Core competencies
- Detailed activities and assessment

### Family D: SHS (SHS 1–3)
- Extended JHS structure
- Essential questions
- Differentiation
- Homework/follow-up
- Reflection

## Template Definition

Each template defines:

| Property | Description |
|----------|-------------|
| `id` | Unique identifier |
| `name` | Display name |
| `family` | Template family |
| `educational_level` | Target level |
| `description` | Human-readable description |
| `features` | List of template features |
| `sections` | Ordered list of sections |
| `layout` | Page layout configuration |
| `is_default` | Whether this is the default for its family |
| `is_official` | Whether this is an official government format |
| `version` | Semantic version |
| `author` | Template author |

## Section Definition

Each section defines:

| Property | Description |
|----------|-------------|
| `name` | Internal identifier |
| `label` | Display label |
| `visible` | Whether section is shown |
| `required` | Whether section must have content |
| `order` | Display order |
| `fields` | List of fields in this section |

## Field Definition

Each field defines:

| Property | Description |
|----------|-------------|
| `name` | Internal identifier |
| `label` | Display label |
| `field_type` | text, textarea, date, number, select, table, rich_text |
| `required` | Whether field must have content |
| `visible` | Whether field is shown |
| `order` | Display order within section |
| `placeholder` | Placeholder text |
| `default_value` | Default value |
| `options` | Options for select fields |
| `source` | Where content comes from (scheme, deterministic, ai, teacher) |

## Layout Configuration

```python
TemplateLayout(
    page_size="A4",
    orientation="portrait",
    margins_top=2.54,      # cm
    margins_bottom=2.54,
    margins_left=2.54,
    margins_right=2.54,
    font_family="Arial",
    font_size=11,
    heading_font_size=14,
    line_spacing=1.15,
    table_border_width=0.5,
    table_header_bg="003366",
    table_header_fg="FFFFFF",
    page_break_between_lessons=True,
)
```

## Default Templates

| Template | Family | Level | Official | Default |
|----------|--------|-------|----------|---------|
| Official GES / NaCCA Lesson Plan (JHS) | JHS | JHS | Yes | Yes |
| Official GES / NaCCA Lesson Plan (KG) | Early Childhood | EC | Yes | Yes |
| Official GES / NaCCA Lesson Plan (Lower Primary) | Primary | Primary | Yes | Basic 1-3 |
| Official GES / NaCCA Lesson Plan (SHS) | SHS | SHS | Yes | Yes |
| GES-Style (JHS) | JHS | JHS | No | No |
| Professional (JHS) | JHS | JHS | No | No |
| Standard (Primary) | Primary | Primary | No | Basic 4-6 |
| Activity-Based (KG) | Early Childhood | EC | No | No |
| GES-Style (SHS) | SHS | SHS | No | No |
| Approved Organizational (Headteacher Source) | JHS | JHS | No | No |

The JHS official form is the head of `DEFAULT_TEMPLATES`, so it is what
exports that name no template and carry no class-level context fall back to.
Every level-aware caller resolves its own form instead
(`docx_export.default_template_for_lessons`, `get_default_template_for_class_level`).
See [OFFICIAL_GES_TEMPLATE.md](OFFICIAL_GES_TEMPLATE.md).

## Custom Templates

Teachers can create custom templates by:
1. Uploading a sample DOCX
2. TeachFlow analyzes the table structure
3. Detects sections and fields
4. Suggests mappings
5. Teacher confirms
6. Template is saved for reuse

## Rendering

The DOCX export engine:
1. Reads the template definition
2. Iterates through visible sections in order
3. For each section, renders its fields
4. Applies layout configuration (fonts, margins, spacing)
5. Handles page breaks between lessons
6. Produces a professional DOCX document

Two templates do not go through the section renderers, because their source
files are documents to fill rather than layouts to imitate:

- `tpl-official-ges-nacca-{kg,primary,jhs,shs}` — bracketed placeholders filled
  in place from the bundled official forms, per level
  (`engines/official_ges_template.py`, contracts in
  `engines/official_ges_levels.py`)
- `tpl-approved-org-headteacher` — table IR replayed from the sampled grid
  (`render_custom_template` in `engines/docx_export.py`)
