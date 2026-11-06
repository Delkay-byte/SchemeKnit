/**
 * Lesson-configuration validation and identity helpers.
 *
 * Shared by the configuration dialog and unit tests so the rules the teacher
 * sees are the rules the tests exercise. Keys are the canonical source
 * occurrence ids produced by the curriculum spine (`week<W>:<pos>:<code>`).
 */

import type { LessonRubricConfig } from '@/types'

export const WEEK_DAYS = [
  { value: 0, label: 'Monday' },
  { value: 1, label: 'Tuesday' },
  { value: 2, label: 'Wednesday' },
  { value: 3, label: 'Thursday' },
  { value: 4, label: 'Friday' },
] as const

export const TERMS = ['First Term', 'Second Term', 'Third Term'] as const

/**
 * The six approved NaCCA core competencies, with their official codes.
 * Teachers select from this fixed list; the interface never accepts free text.
 */
export const CORE_COMPETENCIES = [
  { name: 'Critical Thinking and Problem Solving', code: 'CP' },
  { name: 'Creativity and Innovation', code: 'CI' },
  { name: 'Communication and Collaboration', code: 'CC' },
  { name: 'Cultural Identity and Global Citizenship', code: 'CG' },
  { name: 'Personal Development and Leadership', code: 'PL' },
  { name: 'Digital Literacy', code: 'DL' },
] as const

export const CORE_COMPETENCY_LABELS = CORE_COMPETENCIES.map(
  (competency) => `${competency.name} (${competency.code})`,
)

/** Toggle one approved competency without mutating the current selection. */
export function toggleCompetency(selected: string[] | null | undefined, label: string): string[] {
  const current = Array.isArray(selected) ? selected : []
  return current.includes(label)
    ? current.filter((item) => item !== label)
    : [...current, label]
}

export type LessonConfigField =
  | 'school_name'
  | 'class_size'
  | 'lesson_duration_minutes'
  | 'lessons_per_week'
  | 'teaching_days'
  | 'term_end_date'
  | 'generation_method'

export type LessonConfigProblems = Partial<Record<LessonConfigField, string>>

export interface LessonConfigValidationOptions {
  /** False only when the chosen method is Zeli and availability is known to be off. */
  zeliAvailable?: boolean
  zeliReason?: string | null
}

const CODE_RE = /[BbKk]?\d+\.\d+\.\d+\.\d+(?:\.\d+)?/g

/**
 * Indicator code exactly as the backend allocation engine extracts it: the
 * first code in the cell, or the cell's first 30 characters when it has none.
 */
export function indicatorCode(text: string): string {
  const match = (text || '').trim().match(CODE_RE)
  return match ? match[0] : (text || '').trim().slice(0, 30)
}

/**
 * Split concatenated indicator cells the same way the allocation engine does.
 * Multiple codes in one parsed cell become multiple lessons, never one.
 */
export function splitSourceIndicators(indicators: string[]): string[] {
  const result: string[] = []
  for (const raw of indicators || []) {
    const text = (raw || '').trim()
    if (!text) continue
    const positions: number[] = []
    let previousCode: string | null = null
    let previousEnd = 0
    for (const match of text.matchAll(CODE_RE)) {
      const code = match[0]
      const start = match.index ?? 0
      // A repeated code separated only by whitespace is the SAME indicator
      // (KG ranges come back as "K2.1.1.1.1 K2.1.1.1.1-3").
      if (previousCode !== null && code === previousCode
          && !text.slice(previousEnd, start).trim()) {
        continue
      }
      positions.push(start)
      previousCode = code
      previousEnd = start + code.length
    }
    if (positions.length >= 2) {
      positions.forEach((position, index) => {
        const end = index + 1 < positions.length ? positions[index + 1] : text.length
        const chunk = text.slice(position, end).trim()
        if (chunk) result.push(chunk)
      })
    } else {
      result.push(text)
    }
  }
  return result
}

/**
 * Deduplicated source occurrences for one week, mirroring the engine's
 * first-occurrence-wins rule so positions and keys line up.
 */
export function weekOccurrences(indicators: string[]): string[] {
  const seen = new Set<string>()
  const unique: string[] = []
  for (const text of splitSourceIndicators(indicators)) {
    const key = `${indicatorCode(text)}\u0000${text}`
    if (seen.has(key)) continue
    seen.add(key)
    unique.push(text)
  }
  return unique
}

/**
 * Canonical key for one indicator occurrence. Never position-only: the code
 * makes the key survive re-parsing, and the position separates repeats.
 */
export function sourceOccurrenceId(
  week: number,
  position: number,
  indicator: string,
): string {
  const safe = indicatorCode(indicator)
    .replace(/[^A-Za-z0-9.]+/g, '_')
    .replace(/^_+|_+$/g, '')
  return `week${week}:${position}:${safe || 'row'}`
}

/** One entry per line; blank lines and surrounding whitespace are dropped. */
export function splitEntries(value: string): string[] {
  return (value || '')
    .split(/\r?\n/)
    .map((entry) => entry.trim())
    .filter(Boolean)
}

/**
 * Field-level validation for the shared configuration dialog.
 *
 * Only truly required values block saving. References and additional TLRs
 * stay optional per lesson. A confirmed-unavailable Zeli method blocks
 * generation instead of silently falling back to Standard.
 */
export function validateLessonConfig(
  draft: LessonRubricConfig,
  options: LessonConfigValidationOptions = {},
): LessonConfigProblems {
  const problems: LessonConfigProblems = {}

  if (!(draft.school_name || '').trim()) {
    problems.school_name = 'School name is required.'
  }

  const classSize = draft.class_size
  if (!Number.isInteger(classSize) || (classSize ?? 0) < 1) {
    problems.class_size = 'Class size must be a positive whole number.'
  }

  const duration = draft.lesson_duration_minutes
  if (typeof duration !== 'number' || !Number.isFinite(duration)
      || duration < 20 || duration > 240) {
    problems.lesson_duration_minutes = 'Lesson duration must be between 20 and 240 minutes.'
  }

  const lessons = draft.lessons_per_week ?? draft.periods_per_week
  if (!Number.isInteger(lessons) || (lessons ?? 0) < 1) {
    problems.lessons_per_week = 'Lessons per week must be a positive whole number.'
  }

  if (!(draft.teaching_days || []).length) {
    problems.teaching_days = 'Select at least one teaching day.'
  }

  if (draft.term_start_date && draft.term_end_date
      && draft.term_end_date < draft.term_start_date) {
    problems.term_end_date = 'Term end date cannot be before the term start date.'
  }

  if (draft.generation_method === 'zeli' && options.zeliAvailable === false) {
    problems.generation_method = options.zeliReason
      || 'Zeli is unavailable right now. Choose Standard generation.'
  }

  return problems
}

/** First message in a stable display order, or null when the form is valid. */
export function firstLessonConfigProblem(
  problems: LessonConfigProblems,
): string | null {
  for (const field of [
    'school_name', 'class_size', 'lesson_duration_minutes',
    'lessons_per_week', 'teaching_days', 'term_end_date', 'generation_method',
  ] as const) {
    if (problems[field]) return problems[field] as string
  }
  return null
}

/**
 * Merge server-returned per-indicator resources without touching weeks the
 * teacher did not edit. Keys are canonical occurrence ids.
 */
export function mergeIndicatorResources(
  current: LessonRubricConfig['indicator_resources'],
  incoming: LessonRubricConfig['indicator_resources'],
): LessonRubricConfig['indicator_resources'] {
  const merged: Record<string, { references: string[]; tlrs: string[] }> = {
    ...(current || {}),
  }
  for (const [key, entry] of Object.entries(incoming || {})) {
    merged[key] = {
      references: [...(entry?.references || [])],
      tlrs: [...(entry?.tlrs || [])],
    }
  }
  return merged
}
