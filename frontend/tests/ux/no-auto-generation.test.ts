/**
 * Generation is always an explicit teacher action.
 *
 * The upload → review → configure journey must never leave a flag that makes the
 * generate page start a run by itself, and the generate page must not call
 * runGeneration from a mount effect. These are source-level guards because the
 * defect was a hidden hand-off, not a pure function.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const root = new URL('../../src/', import.meta.url)

function source(path: string): string {
  return readFileSync(new URL(path, root), 'utf8')
}

test('no upload/review path records an auto-generation intent', () => {
  const upload = source('app/(app)/upload/page.tsx')
  assert.doesNotMatch(upload, /autopilot_intent/)
})

test('generate page does not auto-fire a run from an effect', () => {
  const page = source('app/(app)/generate/[id]/page.tsx')
  assert.doesNotMatch(page, /autopilot_intent/)
  assert.doesNotMatch(page, /autopilotIntent/)
  // The autopilot effect may display the plan, never start generation.
  const effect = page.slice(page.indexOf('Autopilot plan'), page.indexOf('Generate actions'))
  assert.doesNotMatch(effect, /runGeneration\(/)
})

test('lesson configuration persists the reference field', () => {
  const modal = source('components/lesson-config-modal.tsx')
  assert.match(modal, /reference: \(draft\.reference \|\| ''\)\.trim\(\) \|\| null/)
  assert.doesNotMatch(modal, /reference: null/)
  assert.match(modal, /id="lcfg-reference"/)
})
