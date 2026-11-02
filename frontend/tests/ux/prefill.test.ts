import assert from 'node:assert/strict'
import { test } from 'node:test'
import { prefillLessonConfig } from '../../src/lib/prefill.ts'

const profile = { full_name: 'Ama Mensah', school_name: 'Aburi Presby Primary' }

test('server-saved values always win over profile defaults', () => {
  const config = prefillLessonConfig(
    { teacher_name: 'Saved Teacher', school_name: 'Saved School' },
    profile,
  )
  assert.equal(config.teacher_name, 'Saved Teacher')
  assert.equal(config.school_name, 'Saved School')
})

test('blank fields are filled from the signed-in profile', () => {
  const config = prefillLessonConfig(
    { teacher_name: '', school_name: null },
    profile,
  )
  assert.equal(config.teacher_name, 'Ama Mensah')
  assert.equal(config.school_name, 'Aburi Presby Primary')
})

test('fields stay empty when no reliable profile value exists', () => {
  const config = prefillLessonConfig({ teacher_name: '', school_name: '' }, null)
  assert.equal(config.teacher_name, null)
  assert.equal(config.school_name, null)
})

test('whitespace-only values count as blank', () => {
  const config = prefillLessonConfig(
    { teacher_name: '   ', school_name: '\t' },
    profile,
  )
  assert.equal(config.teacher_name, 'Ama Mensah')
  assert.equal(config.school_name, 'Aburi Presby Primary')
})

test('one teacher profile cannot leak into another config', () => {
  const other = prefillLessonConfig<{ teacher_name?: string | null; school_name?: string | null }>(
    {},
    { full_name: 'Kofi Boateng', school_name: 'Other School' },
  )
  assert.equal(other.teacher_name, 'Kofi Boateng')
  assert.notEqual(other.teacher_name, profile.full_name)
})

test('the original config object is not mutated', () => {
  const original = { teacher_name: '', school_name: '' }
  prefillLessonConfig(original, profile)
  assert.deepEqual(original, { teacher_name: '', school_name: '' })
})
