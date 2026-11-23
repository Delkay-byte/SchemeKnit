import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  CORE_COMPETENCY_LABELS,
  applySavedLessonConfig,
  firstLessonConfigProblem,
  indicatorCode,
  lessonConfigPayload,
  mergeIndicatorResources,
  sourceOccurrenceId,
  splitEntries,
  splitSourceIndicators,
  toggleCompetency,
  validateLessonConfig,
  weekOccurrences,
} from '../../src/lib/lesson-config.ts'

const COMPLETE = {
  school_name: 'Kpogede Community School',
  class_size: 35,
  lesson_duration_minutes: 60,
  lessons_per_week: 3,
  teaching_days: [0, 2, 4],
  term_start_date: '2026-09-07',
  term_end_date: '2026-12-18',
  term: 'First Term',
  generation_method: 'standard' as const,
}

test('a complete configuration passes validation', () => {
  assert.deepEqual(validateLessonConfig(COMPLETE), {})
  assert.equal(firstLessonConfigProblem(validateLessonConfig(COMPLETE)), null)
})

test('every missing required field is reported separately', () => {
  const problems = validateLessonConfig({})
  assert.ok(problems.school_name)
  assert.ok(problems.class_size)
  assert.ok(problems.lesson_duration_minutes)
  assert.ok(problems.lessons_per_week)
  assert.ok(problems.teaching_days)
  assert.equal(firstLessonConfigProblem(problems), 'School name is required.')
})

test('invalid numbers and empty teaching days are rejected', () => {
  const problems = validateLessonConfig({
    ...COMPLETE, class_size: 0, lesson_duration_minutes: 10,
    lessons_per_week: 0, teaching_days: [],
  })
  assert.match(problems.class_size || '', /positive/)
  assert.match(problems.lesson_duration_minutes || '', /20 and 240/)
  assert.match(problems.lessons_per_week || '', /positive/)
  assert.match(problems.teaching_days || '', /at least one/)
})

test('term end cannot precede term start', () => {
  const problems = validateLessonConfig({
    ...COMPLETE, term_start_date: '2026-12-18', term_end_date: '2026-09-07',
  })
  assert.match(problems.term_end_date || '', /cannot be before/)
  assert.equal(validateLessonConfig({
    ...COMPLETE, term_start_date: '2026-09-07', term_end_date: '2026-09-07',
  }).term_end_date, undefined)
})

test('Zeli that is confirmed unavailable blocks instead of falling back', () => {
  const unavailable = validateLessonConfig(
    { ...COMPLETE, generation_method: 'zeli' },
    { zeliAvailable: false, zeliReason: 'No AI provider is configured.' },
  )
  assert.equal(unavailable.generation_method, 'No AI provider is configured.')

  const available = validateLessonConfig(
    { ...COMPLETE, generation_method: 'zeli' }, { zeliAvailable: true })
  assert.deepEqual(available, {})

  // Unknown availability does not block the teacher from choosing the method.
  assert.deepEqual(
    validateLessonConfig({ ...COMPLETE, generation_method: 'zeli' }), {})
})

test('per-indicator keys are stable and never position-only', () => {
  const first = sourceOccurrenceId(2, 0, 'B6.1.1.1.1 Demonstrate the skill')
  const second = sourceOccurrenceId(2, 1, 'B6.1.1.1.2 Demonstrate the skill')
  assert.equal(first, 'week2:0:B6.1.1.1.1')
  assert.equal(second, 'week2:1:B6.1.1.1.2')
  assert.notEqual(first, second)
  assert.equal(first, sourceOccurrenceId(2, 0, 'B6.1.1.1.1'))
  assert.equal(indicatorCode('B6.1.1.1.1: use a mouse'), 'B6.1.1.1.1')
  assert.equal(indicatorCode('Demonstrate the skill'), 'Demonstrate the skill')
  assert.equal(sourceOccurrenceId(3, 0, 'Demonstrate the skill'), 'week3:0:Demonstrate_the_skill')
  assert.equal(indicatorCode(''), '')
  assert.equal(sourceOccurrenceId(3, 0, ''), 'week3:0:row')
})

test('indicator resource values split into trimmed lines and drop blanks', () => {
  assert.deepEqual(
    splitEntries('  Computing Textbook p.12 \n\n Integrated Science p.4 \n'),
    ['Computing Textbook p.12', 'Integrated Science p.4'],
  )
  assert.deepEqual(splitEntries(''), [])
})

test('references and additional TLRs stay optional per lesson', () => {
  assert.deepEqual(validateLessonConfig({
    ...COMPLETE,
    indicator_resources: { 'week1:0:B6.1.1.1.1': { references: [], tlrs: [] } },
  }), {})
})

test('merging saved resources keeps other weeks and copies arrays', () => {
  const current = {
    'week1:0:B6.1.1.1.1': { references: ['Week 1 book'], tlrs: ['Chart'] },
  }
  const incoming = {
    'week2:0:B6.1.1.1.2': { references: ['Week 2 book'], tlrs: ['Samples'] },
  }
  const merged = mergeIndicatorResources(current, incoming)
  assert.deepEqual(merged?.['week1:0:B6.1.1.1.1'], {
    references: ['Week 1 book'], tlrs: ['Chart'],
  })
  assert.deepEqual(merged?.['week2:0:B6.1.1.1.2'], {
    references: ['Week 2 book'], tlrs: ['Samples'],
  })
  // Mutating the merged copy must not corrupt the dialog draft.
  ;(merged?.['week2:0:B6.1.1.1.2']?.references || []).push('Extra')
  assert.deepEqual(incoming['week2:0:B6.1.1.1.2'].references, ['Week 2 book'])
})


test('concatenated indicators split into one occurrence each', () => {
  const merged = 'B9.1.1.1.2 Discuss formation of soil. B9.1.1.1.3 Describe soil types.'
  const split = splitSourceIndicators([merged])
  assert.deepEqual(split, [
    'B9.1.1.1.2 Discuss formation of soil.',
    'B9.1.1.1.3 Describe soil types.',
  ])
  const keys = weekOccurrences([merged]).map((text, position) =>
    sourceOccurrenceId(2, position, text))
  assert.deepEqual(keys, ['week2:0:B9.1.1.1.2', 'week2:1:B9.1.1.1.3'])
})

test('a repeated KG code is not turned into a phantom lesson', () => {
  assert.deepEqual(
    splitSourceIndicators(['K2.1.1.1.1 K2.1.1.1.1-3 Name colours']),
    ['K2.1.1.1.1 K2.1.1.1.1-3 Name colours'],
  )
})

test('duplicate source rows are deduped like the allocation engine', () => {
  const rows = ['B6.1.1.1.1 Use a mouse', 'B6.1.1.1.1 Use a mouse']
  assert.equal(weekOccurrences(rows).length, 1)
  assert.equal(weekOccurrences([...rows, 'B6.1.1.1.2 Use a keyboard']).length, 2)
})

test('all six approved core competencies are selectable together', () => {
  assert.equal(CORE_COMPETENCY_LABELS.length, 6)
  assert.deepEqual(CORE_COMPETENCY_LABELS, [
    'Critical Thinking and Problem Solving (CP)',
    'Creativity and Innovation (CI)',
    'Communication and Collaboration (CC)',
    'Cultural Identity and Global Citizenship (CG)',
    'Personal Development and Leadership (PL)',
    'Digital Literacy (DL)',
  ])
  let selected: string[] = []
  for (const label of CORE_COMPETENCY_LABELS.slice(0, 3)) {
    selected = toggleCompetency(selected, label)
  }
  assert.equal(selected.length, 3)
  selected = toggleCompetency(selected, CORE_COMPETENCY_LABELS[1])
  assert.deepEqual(selected, [
    CORE_COMPETENCY_LABELS[0],
    CORE_COMPETENCY_LABELS[2],
  ])
  assert.deepEqual(toggleCompetency(null, CORE_COMPETENCY_LABELS[5]), [
    CORE_COMPETENCY_LABELS[5],
  ])
})

test('save payload carries the whole teacher snapshot, not fallback maps', () => {
  const payload = lessonConfigPayload({
    school_name: ' Kpogede Community School ',
    teacher_name: ' Deladem Amegayie ',
    class_size: 38,
    lesson_duration_minutes: 45,
    lessons_per_week: 4,
    period: '3rd & 4th',
    teaching_days: [1, 3],
    term: 'Second Term',
    term_start_date: '2027-01-05',
    term_end_date: '2027-04-01',
    generation_method: 'zeli',
    ai_mode: 'BASIC',
    template_id: 'tpl-wapef-maths-b4',
    reference: ' GES Basic 4 ',
    indicator_resources: {
      'week2:0:B4.1.1.1.1': { references: ['Page 19'], tlrs: ['Bottle tops'] },
    },
    competency_selections: {
      'week2:0:B4.1.1.1.1': [CORE_COMPETENCY_LABELS[0]],
    },
    indicator_keywords: {
      'week2:0:B4.1.1.1.1': ['regroup', 'place value'],
      'week3:0:B4.1.1.2.1': [],
    },
    indicator_wapef: {
      'week2:0:B4.1.1.1.1': {
        through_lines: ['Order discoverer'], gods_story: 'Creation',
      },
    },
  })
  assert.equal(payload.school_name, 'Kpogede Community School')
  assert.equal(payload.teacher_name, 'Deladem Amegayie')
  assert.equal(payload.class_size, 38)
  assert.equal(payload.lesson_duration_minutes, 45)
  assert.equal(payload.lessons_per_week, 4)
  assert.equal(payload.period, '3rd & 4th')
  assert.deepEqual(payload.teaching_days, [1, 3])
  assert.equal(payload.term, 'Second Term')
  assert.equal(payload.term_start_date, '2027-01-05')
  assert.equal(payload.term_end_date, '2027-04-01')
  assert.equal(payload.generation_method, 'zeli')
  assert.equal(payload.ai_mode, 'BASIC')
  assert.equal(payload.template_id, 'tpl-wapef-maths-b4')
  assert.equal(payload.reference, 'GES Basic 4')
  assert.deepEqual(payload.indicator_keywords?.['week3:0:B4.1.1.2.1'], [])
  assert.deepEqual(payload.indicator_wapef?.['week2:0:B4.1.1.1.1'], {
    through_lines: ['Order discoverer'], gods_story: 'Creation',
  })
})

test('save payload distinguishes an unloaded map from an explicit clear', () => {
  const maps = [
    'indicator_resources', 'competency_selections',
    'indicator_keywords', 'indicator_wapef',
  ]
  const absent = lessonConfigPayload({ school_name: 'Kpogede Community School' })
  for (const key of maps) assert.equal(key in absent, false)

  const cleared = lessonConfigPayload({
    school_name: 'Kpogede Community School',
    indicator_resources: {},
    competency_selections: {},
    indicator_keywords: {},
    indicator_wapef: {},
  })
  for (const key of maps) assert.deepEqual(cleared[key as keyof typeof cleared], {})
})

test('generation config keeps saved AI mode and every per-lesson map', () => {
  const base: Parameters<typeof applySavedLessonConfig>[0] = {
    scheme_of_work_id: 'scheme-42',
    term_start_date: '2026-09-07',
    term_end_date: '2026-12-18',
    lessons_per_week: 3,
    lesson_duration_minutes: 60,
    class_size: 24,
    teaching_days: [0, 2, 4],
    holidays: [],
    ai_mode: 'OFF',
    generation_method: 'standard',
    include_special_weeks: false,
  }
  const next = applySavedLessonConfig(base, {
    class_size: 38,
    lesson_duration_minutes: 45,
    lessons_per_week: 4,
    period: '3rd & 4th',
    term: 'Second Term',
    term_start_date: '2027-01-05',
    term_end_date: '2027-04-01',
    teaching_days: [1, 3],
    generation_method: 'zeli',
    ai_mode: 'BASIC',
    template_id: 'tpl-wapef-maths-b4',
    indicator_resources: {
      'week2:0:B4.1.1.1.1': { references: ['Page 19'], tlrs: ['Bottle tops'] },
    },
    competency_selections: {
      'week2:0:B4.1.1.1.1': [CORE_COMPETENCY_LABELS[0]],
    },
    indicator_keywords: { 'week3:0:B4.1.1.2.1': [] },
    indicator_wapef: {
      'week2:0:B4.1.1.1.1': {
        through_lines: ['Order discoverer'], gods_story: 'Creation',
      },
    },
  })
  assert.equal(next.ai_mode, 'BASIC')
  assert.equal(next.generation_method, 'zeli')
  assert.equal(next.class_size, 38)
  assert.deepEqual(next.teaching_days, [1, 3])
  assert.deepEqual(next.indicator_wapef, {
    'week2:0:B4.1.1.1.1': {
      through_lines: ['Order discoverer'], gods_story: 'Creation',
    },
  })
  assert.deepEqual(next.indicator_keywords, { 'week3:0:B4.1.1.2.1': [] })
})
