# Template Provenance

Every TeachFlow lesson-plan template carries a provenance record so that
generation, export, and validation all resolve to the correct source document.

## Verified templates

| Template ID | Source document | Renderer |
|-------------|----------------|----------|
| `tpl-ges-jhs` | `ges_jhs_lesson_plan_template.docx` | `official_ges_template.py` (legacy 6-column) |
| `tpl-approved-org-headteacher` | `ges_jhs_lesson_plan_template.docx` | `approved_template.py` (4-table in-place) |

Both templates share the same DOCX source. They differ only in renderer
complexity: the legacy renderer inserts into the six-column table; the
approved renderer performs in-place replacement in the four-table layout.

## Provenance fields

Each entry in `src/engines/template_provenance.py` records:

- `template_id` — canonical identifier
- `label` — human-readable description
- `source_docx` — filename of the DOCX source
- `renderer` — Python module that performs the render
- `evidence` — chain-of-custody string linking template_id to source

## Regeneration

Run `src/tools/regenerate_golden_master.py` to regenerate the golden-master
JSON from the real DOCX. The structural fingerprint can be verified with
`src/tools/docx_structure.py`.
