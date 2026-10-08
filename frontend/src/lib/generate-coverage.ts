/**
 * Generate workflow — weekly coverage model (Priority 3).
 *
 * PURE helpers: read the allocation preview + the scheme's persisted lessons
 * and derive the week-centric view model the Generate page renders. No
 * fetching, no lesson-generation logic — the frontend only decides WHAT to
 * generate; the backend owns HOW (spec §25).
 *
 * Design rules encoded here:
 *  - Weekly coverage semantics are never re-filtered client-side (spec §24):
 *    the counts come straight from the preview payload.
 *  - "Generated" status is keyed by SOURCE OCCURRENCE identity (one row of
 *    one source week); indicator codes alone cannot disambiguate a code that
 *    repeats across weeks. Legacy rows without an occurrence id fall back to
 *    week + indicator code.
 *  - Quota copy keeps the exact phase17-teacher-journey format:
 *    "<used> of <limit> Free Tier lesson plans used this month · <remaining>
 *    remaining".
 */

export interface PreviewWeekMeta {
  week_number: number
  indicator_count?: number
  lesson_count?: number
  teaching_period_count?: number
  lesson_plans_required?: number
  strand?: string
  sub_strand?: string
}

export interface PreviewRow {
  lesson_sequence: number
  indicator_code: string
  indicator_description: string
  content_standard_code?: string
  content_standard?: string
  strand?: string
  sub_strand?: string
  source_week: number
  teaching_week?: number
  week_ending?: string | null
  week_ending_derived?: boolean
  source_occurrence_id: string
  source_tlrs?: string[]
  needs_review?: boolean
  review_reasons?: string[]
  is_special_period?: boolean
  special_period_label?: string
  special_period_type?: string
  source_provenance?: Record<string, unknown>
}

export interface QuotaStatus {
  enforced?: boolean
  limit?: number
  used?: number
  remaining?: number
}

export interface StoredLesson {
  id: string
  week_number?: number
  source_week?: number
  source_occurrence_id?: string
  indicator_codes?: string[]
  teacher_edited?: boolean
  status?: string
  lesson_sequence?: number
}

export interface WeekRow extends PreviewRow {
  generated: boolean
  generatedLesson?: StoredLesson
}

export interface WeekPlan {
  weekNumber: number
  rows: WeekRow[]
  specialRows: PreviewRow[]
  indicatorCount: number
  lessonCount: number
  teachingPeriodCount: number
  generatedCount: number
  pendingCount: number
  allGenerated: boolean
  anyGenerated: boolean
  needsReview: boolean
}

/** Distinct values, first-seen order preserved (curriculum order for codes). */
export function distinctInOrder(values: string[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const v of values) {
    if (!v || seen.has(v)) continue
    seen.add(v)
    out.push(v)
  }
  return out
}

function lessonKey(lesson: StoredLesson): { occ: string; legacy: string | null } {
  const occ = (lesson.source_occurrence_id || '').trim()
  const week = lesson.week_number ?? lesson.source_week
  const code = (lesson.indicator_codes || [])[0] || ''
  // Legacy key only exists for rows persisted before occurrence ids.
  const legacy = occ ? null : (week != null ? `${week}:${code}` : null)
  return { occ, legacy }
}

function rowKey(row: PreviewRow): { occ: string; legacy: string | null } {
  const occ = (row.source_occurrence_id || '').trim()
  const week = row.source_week
  const code = (row.indicator_code || '').trim()
  const legacy = occ ? null : `${week}:${code}`
  return { occ, legacy }
}

/**
 * Build the week plans the Generate page renders.
 *
 * Weeks come from BOTH the preview's instruction-week meta (counts,
 * timetable periods) and the review rows — special-period weeks and
 * MIXED weeks only exist in the rows, so neither source alone is complete.
 */
export function buildWeekPlans(
  preview: { weeks?: PreviewWeekMeta[]; lesson_review?: PreviewRow[] } | null,
  lessons: StoredLesson[],
): WeekPlan[] {
  if (!preview) return []

  const metaByWeek = new Map<number, PreviewWeekMeta>()
  for (const w of preview.weeks || []) {
    metaByWeek.set(w.week_number, w)
  }

  // Match persisted lessons to preview rows by occurrence identity first.
  const byOcc = new Map<string, StoredLesson>()
  const byLegacy = new Map<string, StoredLesson>()
  for (const lesson of lessons || []) {
    const { occ, legacy } = lessonKey(lesson)
    if (occ) byOcc.set(occ, lesson)
    else if (legacy) {
      // Multiple codeless legacy rows in one week cannot be told apart —
      // first unmatched lesson wins per key (legacy edge only; occurrence
      // ids have existed since Priority 1).
      if (!byLegacy.has(legacy)) byLegacy.set(legacy, lesson)
    }
  }

  const rowsByWeek = new Map<number, { rows: PreviewRow[]; special: PreviewRow[] }>()
  for (const row of preview.lesson_review || []) {
    const bucket = rowsByWeek.get(row.source_week) || { rows: [], special: [] }
    if (row.is_special_period) bucket.special.push(row)
    else bucket.rows.push(row)
    rowsByWeek.set(row.source_week, bucket)
  }

  const weekSet = new Set<number>()
  metaByWeek.forEach((_, weekNumber) => weekSet.add(weekNumber))
  rowsByWeek.forEach((_, weekNumber) => weekSet.add(weekNumber))
  const weekNumbers = Array.from(weekSet).sort((a, b) => a - b)

  const plans: WeekPlan[] = []
  for (const weekNumber of weekNumbers) {
    const meta = metaByWeek.get(weekNumber)
    const bucket = rowsByWeek.get(weekNumber) || { rows: [], special: [] }
    const rows: WeekRow[] = bucket.rows.map((row) => {
      const { occ, legacy } = rowKey(row)
      const lesson = (occ && byOcc.get(occ)) || (legacy && byLegacy.get(legacy)) || undefined
      return { ...row, generated: !!lesson, generatedLesson: lesson || undefined }
    })
    const specialRows = bucket.special
    const generatedCount = rows.filter((r) => r.generated).length
    const lessonCount = meta?.lesson_count ?? rows.length
    plans.push({
      weekNumber,
      rows,
      specialRows,
      indicatorCount:
        meta?.indicator_count ?? rows.filter((r) => !!r.indicator_code).length,
      lessonCount,
      teachingPeriodCount: meta?.teaching_period_count ?? 0,
      generatedCount,
      pendingCount: rows.length - generatedCount,
      allGenerated: rows.length > 0 && generatedCount === rows.length,
      anyGenerated: generatedCount > 0,
      needsReview: rows.some((r) => !!r.needs_review),
    })
  }
  return plans
}

/** The week counts line — one canonical, exact phrasing (e2e contract). */
export function formatWeekCounts(week: WeekPlan): string {
  const indicators =
    week.indicatorCount > 0
      ? `${week.indicatorCount} curriculum indicator${week.indicatorCount === 1 ? '' : 's'}`
      : `${week.lessonCount} curriculum row${week.lessonCount === 1 ? '' : 's'}`
  const periods =
    week.teachingPeriodCount > 0
      ? `${week.teachingPeriodCount} timetable period${week.teachingPeriodCount === 1 ? '' : 's'}`
      : 'teaching periods not specified'
  const required = `${week.lessonCount} lesson plan${week.lessonCount === 1 ? '' : 's'} required for this week`
  return `${indicators} · ${periods} → ${required}`
}

/** One-line plan count for a set of rows ("N lesson plans"). */
export function planCountLabel(count: number): string {
  return `${count} lesson plan${count === 1 ? '' : 's'}`
}

/**
 * The quota banner line, exact legacy format (parsed verbatim by
 * phase17-teacher-journey). Null when the quota is not enforced.
 */
export function quotaLine(quota: QuotaStatus | null | undefined): string | null {
  if (!quota?.enforced) return null
  return `${quota.used ?? 0} of ${quota.limit ?? 0} Free Tier lesson plans used this month · ${
    quota.remaining ?? 0
  } remaining`
}

export interface QuotaFit {
  /** Distinct indicator codes the rows need. */
  needed: number
  /** How many of those codes fit in the remaining monthly allowance. */
  canGenerate: number
  /** Lesson rows generatable now (rows whose code is inside the fit). */
  rowsGeneratable: number
  capped: boolean
}

/**
 * Week-fit math for one week's PENDING rows (spec §10): "Week 5 contains 4
 * lessons. 2 of the 4 can be generated with your remaining monthly
 * allowance." Returns null when the quota is not enforced or nothing is
 * pending.
 */
export function quotaFitForRows(
  rows: WeekRow[] | PreviewRow[],
  quota: QuotaStatus | null | undefined,
): QuotaFit | null {
  if (!quota?.enforced) return null
  const pending = rows.filter((r) => !(r as WeekRow).generated && !r.is_special_period)
  if (pending.length === 0) return null
  const remaining = Math.max(quota.remaining ?? 0, 0)
  const codes: string[] = []
  const allowed = new Set<string>()
  let rowsGeneratable = 0
  for (const row of pending) {
    const code = (row.indicator_code || '').trim()
    if (code) {
      if (!codes.includes(code)) {
        if (codes.length < remaining) allowed.add(code)
        codes.push(code)
      }
      if (allowed.has(code)) rowsGeneratable += 1
    } else {
      // Codeless rows (Nursery-style) are quota-exempt — same as the server.
      rowsGeneratable += 1
    }
  }
  const canGenerate = Math.min(codes.length, remaining)
  return {
    needed: codes.length,
    canGenerate,
    rowsGeneratable,
    capped: canGenerate < codes.length,
  }
}

/**
 * The rows to generate for a whole week, already quota-capped in curriculum
 * order (a code that fits makes its whole week's copy free; codeless rows
 * are exempt). Empty array = nothing fits this month.
 */
export function generatableRowsForWeek(
  week: WeekPlan,
  quota: QuotaStatus | null | undefined,
): WeekRow[] {
  const pending = week.rows.filter((r) => !r.generated)
  if (!quota?.enforced) return pending
  const remaining = Math.max(quota.remaining ?? 0, 0)
  const allowed = new Set<string>()
  const seen: string[] = []
  const out: WeekRow[] = []
  for (const row of pending) {
    const code = (row.indicator_code || '').trim()
    if (!code) {
      out.push(row)
      continue
    }
    if (!seen.includes(code)) {
      if (seen.length < remaining) allowed.add(code)
      seen.push(code)
    }
    if (allowed.has(code)) out.push(row)
  }
  return out
}

/**
 * The full-set selection the rail's "Generate lesson plans" sends: every
 * distinct PENDING indicator code in curriculum order (rows already generated
 * never re-enter the batch), capped at the remaining allowance when the quota
 * is enforced; empty (true full generation) when it is not.
 */
export function fullSelection(
  rows: Array<{ indicator_code?: string; is_special_period?: boolean }>,
  quota: QuotaStatus | null | undefined,
): { codes: string[]; capped: boolean } {
  const codes = distinctInOrder(
    rows
      .filter((r) => !r.is_special_period)
      .map((r) => (r.indicator_code || '').trim()),
  )
  if (!quota?.enforced) return { codes: [], capped: false }
  const remaining = Math.max(quota.remaining ?? 0, 0)
  const capped = codes.length > remaining
  return { codes: codes.slice(0, remaining), capped }
}
