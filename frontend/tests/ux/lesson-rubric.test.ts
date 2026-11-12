import assert from 'node:assert/strict'
import { test } from 'node:test'
import { rubricEvidenceText } from '../../src/lib/lesson-rubric.ts'

test('string evidence is returned verbatim, not joined', () => {
  const evidence =
    "Award each criterion's points only for evidence visible in the learner's work, performance or recorded answer - the evidence stated in the lesson's Assessment row."
  assert.equal(rubricEvidenceText(evidence), evidence)
})

test('string evidence does not throw when rendered (production P4 regression)', () => {
  // The lesson workspace previously called .join on this value, which threw
  // "evidence_to_award.join is not a function" and killed the whole page.
  const stored = 'Award points only for visible evidence.'
  assert.doesNotThrow(() => rubricEvidenceText(stored))
  assert.equal(rubricEvidenceText(stored).length > 0, true)
})

test('array evidence from older drafts is joined with semicolons', () => {
  assert.equal(rubricEvidenceText(['Work shown', 'Answer correct']), 'Work shown; Answer correct')
  assert.equal(rubricEvidenceText(['  Work shown  ', '', null]), 'Work shown')
})

test('empty and unexpected values render nothing', () => {
  assert.equal(rubricEvidenceText(''), '')
  assert.equal(rubricEvidenceText('   '), '')
  assert.equal(rubricEvidenceText(undefined), '')
  assert.equal(rubricEvidenceText(null), '')
  assert.equal(rubricEvidenceText(42), '')
  assert.equal(rubricEvidenceText([]), '')
})
