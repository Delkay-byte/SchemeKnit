/**
 * Lesson rubric display helpers.
 *
 * `assessment_rubric.evidence_to_award` is stored as a single paragraph on the
 * backend (`models.py`, `assessment_design.py`) and rendered verbatim by the
 * DOCX/PDF exporters. Older drafts can still hold a string array, so the
 * lesson workspace normalises both shapes before display instead of assuming
 * an array and throwing on `.join`.
 */
export function rubricEvidenceText(value: unknown): string {
  if (Array.isArray(value)) {
    return value
      .map((entry) => String(entry ?? '').trim())
      .filter(Boolean)
      .join('; ')
  }
  return typeof value === 'string' ? value.trim() : ''
}
