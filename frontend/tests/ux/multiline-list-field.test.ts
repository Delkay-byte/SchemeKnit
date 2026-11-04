import assert from 'node:assert/strict'
import test from 'node:test'

import {
  formatMultilineEntries,
  parseMultilineEntries,
} from '../../src/lib/multiline.ts'

test('spaces inside a reference are preserved', () => {
  const typed = 'Computing curriculum page 16'
  assert.deepEqual(parseMultilineEntries(typed), [typed])
})

test('a trailing space survives typing until parsing', () => {
  // The editor keeps raw text; parsing is the deliberate boundary.
  assert.deepEqual(parseMultilineEntries('Computing curriculum '), [
    'Computing curriculum',
  ])
})

test('Enter creates a separate entry and never merges lines', () => {
  const typed = 'Computing curriculum page 16\nTeacher guide page 4'
  assert.deepEqual(parseMultilineEntries(typed), [
    'Computing curriculum page 16',
    'Teacher guide page 4',
  ])
})

test('pasted newline-separated TLRs become three entries', () => {
  const pasted = 'Computer\nUSB mouse\nExercise books'
  assert.deepEqual(parseMultilineEntries(pasted), [
    'Computer',
    'USB mouse',
    'Exercise books',
  ])
})

test('blank lines are ignored and per-entry whitespace trimmed', () => {
  assert.deepEqual(parseMultilineEntries('  Charts  \n\n  Ruler\n'), [
    'Charts',
    'Ruler',
  ])
})

test('commas inside one entry are not treated as separators', () => {
  assert.deepEqual(
    parseMultilineEntries('Charts, pictures and realia'),
    ['Charts, pictures and realia'],
  )
})

test('round-trip formatting keeps every entry on its own line', () => {
  const entries = ['Computing curriculum page 16', 'Teacher guide page 4']
  assert.deepEqual(parseMultilineEntries(formatMultilineEntries(entries)), entries)
})
