'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { CalendarDays, ChevronRight, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SurfaceCard } from '@/components/ui/surface-card'
import { Banner } from '@/components/ui/banner'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { PageHeader } from '@/components/ui/page-header'
import { Badge } from '@/components/ui/badge'
import { toast } from '@/components/ui/toaster'
import { api } from '@/lib/api'
import {
  CLASS_LEVELS,
  type SchemeOfWork,
  type WapefOptions,
  type WeeklyPreviewResponse,
  type WeeklyPlanRequest,
  type WeeklyRouting,
} from '@/types'

const WEEKDAY_DAYS = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY'] as const
const DAY_LABELS: Record<string, string> = {
  MONDAY: 'Monday', TUESDAY: 'Tuesday', WEDNESDAY: 'Wednesday',
  THURSDAY: 'Thursday', FRIDAY: 'Friday',
}
const TERMS = ['First Term', 'Second Term', 'Third Term']

/** One subject's teacher selections for this week. */
interface SubjectDraft {
  days: string[]
  shared: boolean
  wapef_deep_hope: string
  wapef_storyline: string
  wapef_through_lines: string[]
  wapef_gods_story: string
}

function freshDraft(): SubjectDraft {
  return {
    days: [...WEEKDAY_DAYS],
    shared: false,
    wapef_deep_hope: '',
    wapef_storyline: '',
    wapef_through_lines: [],
    wapef_gods_story: '',
  }
}

function orderedDays(days: string[]): string[] {
  return WEEKDAY_DAYS.filter((d) => days.includes(d))
}

/**
 * Build a Basic 1-3 weekly class plan (Approved WAPEF Basic 1-3 Plan).
 *
 * The class-teacher model: the teacher picks the subject schemes they teach
 * this week, assigns each subject its teaching days (single days, or one
 * shared "MONDAY & THURSDAY" entry), optionally sets the four approved WAPEF
 * fields, previews the generated week, and saves it. The class band decides
 * the planning model through the shared routing rule — Basic 4 and above
 * report the subject-teacher model here and never generate a weekly plan.
 */
export default function NewWeeklyPlanPage() {
  const router = useRouter()

  const [classLevel, setClassLevel] = useState('Basic 1')
  const [routing, setRouting] = useState<WeeklyRouting | null>(null)
  const [weekNumber, setWeekNumber] = useState(1)
  const [term, setTerm] = useState('First Term')
  const [academicYear, setAcademicYear] = useState('2026/2027')
  const [termStart, setTermStart] = useState('2026-09-11')
  const [termEnd, setTermEnd] = useState('2026-12-18')

  const [schemes, setSchemes] = useState<SchemeOfWork[]>([])
  const [drafts, setDrafts] = useState<Record<string, SubjectDraft>>({})
  const [wapefOptions, setWapefOptions] = useState<WapefOptions | null>(null)

  const [preview, setPreview] = useState<WeeklyPreviewResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [previewing, setPreviewing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isClassTeacher = routing?.planning_model === 'class_teacher'
  const selectedIds = Object.keys(drafts)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [schemeResponse, options] = await Promise.all([
          api.listSchemes(),
          api.getWapefOptions().catch(() => null),
        ])
        if (cancelled) return
        setSchemes(schemeResponse.schemes || [])
        setWapefOptions(options)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load schemes')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [])

  // The class band decides the planning model (shared routing rule, never
  // ad hoc client logic): Basic 1-3 -> class_teacher, Basic 4+ -> subject_teacher.
  useEffect(() => {
    let cancelled = false
    setRouting(null)
    setPreview(null)
    api.getWeeklyRouting(classLevel)
      .then((result) => { if (!cancelled) setRouting(result) })
      .catch(() => { if (!cancelled) setRouting(null) })
    return () => { cancelled = true }
  }, [classLevel])

  const toggleScheme = (schemeId: string) => {
    setPreview(null)
    setError(null)
    setDrafts((prev) => {
      const next = { ...prev }
      if (next[schemeId]) delete next[schemeId]
      else next[schemeId] = freshDraft()
      return next
    })
  }

  const patchDraft = (schemeId: string, patch: Partial<SubjectDraft>) => {
    setPreview(null)
    setDrafts((prev) => ({ ...prev, [schemeId]: { ...prev[schemeId], ...patch } }))
  }

  const toggleDay = (schemeId: string, day: string) => {
    const draft = drafts[schemeId]
    if (!draft) return
    const days = draft.days.includes(day)
      ? draft.days.filter((d) => d !== day)
      : orderedDays([...draft.days, day])
    patchDraft(schemeId, { days })
  }

  const toggleThroughLine = (schemeId: string, option: string) => {
    const draft = drafts[schemeId]
    if (!draft) return
    const current = draft.wapef_through_lines
    const next = current.includes(option)
      ? current.filter((t) => t !== option)
      : [...current, option]
    patchDraft(schemeId, { wapef_through_lines: next })
  }

  const buildRequest = (): WeeklyPlanRequest => ({
    class_level: classLevel,
    week_number: Number(weekNumber) || 1,
    term_start_date: termStart,
    term_end_date: termEnd,
    term,
    academic_year: academicYear,
    subjects: selectedIds.map((schemeId) => {
      const draft = drafts[schemeId]
      const days = orderedDays(draft.days)
      // One shared entry ("MONDAY & THURSDAY") when the teacher says the same
      // lesson covers all selected days; otherwise one entry per day.
      const teaching_day_groups = draft.shared && days.length > 1
        ? [days]
        : days.map((day) => [day])
      return {
        scheme_id: schemeId,
        teaching_day_groups,
        wapef_deep_hope: draft.wapef_deep_hope,
        wapef_storyline: draft.wapef_storyline,
        wapef_through_lines: draft.wapef_through_lines,
        wapef_gods_story: draft.wapef_gods_story,
      }
    }),
  })

  const handlePreview = async () => {
    setError(null)
    setPreview(null)
    if (!isClassTeacher) return
    if (selectedIds.length === 0) {
      setError('Select at least one subject scheme.')
      return
    }
    const emptyDays = selectedIds.filter((id) => drafts[id].days.length === 0)
    if (emptyDays.length > 0) {
      setError('Assign at least one teaching day to every selected subject.')
      return
    }
    setPreviewing(true)
    try {
      const response = await api.previewWeeklyPlan(buildRequest())
      setPreview(response)
      if (response.validation_issues.length > 0) {
        setError(response.validation_issues.join(' '))
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to preview the week')
    } finally {
      setPreviewing(false)
    }
  }

  const handleSave = async () => {
    if (!preview || preview.validation_issues.length > 0) return
    setSaving(true)
    setError(null)
    try {
      const created = await api.createWeeklyPlan(buildRequest())
      toast({ title: 'Weekly plan saved', description: `${classLevel} · Week ${weekNumber}` })
      router.push(`/weekly-plans/${created.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save the weekly plan')
      setSaving(false)
    }
  }

  const selectedSchemes = useMemo(
    () => schemes.filter((s) => selectedIds.includes(s.id)),
    [schemes, selectedIds],
  )

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Weekly Plan"
        title="New Weekly Class Plan"
        description="Basic 1-3 class-teacher model: one teacher, several subjects, different teaching days, one weekly document."
        actions={
          <Button variant="outline" asChild>
            <Link href="/weekly-plans">Back to weekly plans</Link>
          </Button>
        }
      />

      {!isClassTeacher && routing && (
        <Banner tone="warning" title="Not a class-teacher plan" data-weekly-boundary>
          {routing.class_level || classLevel} uses the {routing.template_name}{' '}
          (subject-teacher model). The weekly class plan is for Basic 1-3 only —
          generate this class from the lesson-plan flow instead.
          <div className="mt-2">
            <Button variant="outline" size="sm" asChild>
              <Link href="/dashboard">Go to lesson plans</Link>
            </Button>
          </div>
        </Banner>
      )}

      {error && <Banner tone="danger" title="Needs attention">{error}</Banner>}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {/* ── Plan details ─────────────────────────────────────────── */}
          <SurfaceCard data-weekly-config className="p-6">
            <h2 className="text-base font-semibold text-[#102A43]">Plan details</h2>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <Field label="Class level" htmlFor="weekly-class-level">
                <Select
                  id="weekly-class-level"
                  value={classLevel}
                  onChange={(e) => setClassLevel(e.target.value)}
                >
                  {CLASS_LEVELS.map((level) => (
                    <option key={level.value} value={level.value}>{level.label}</option>
                  ))}
                </Select>
                <p className="mt-1 text-xs text-muted-foreground" data-weekly-model>
                  {routing
                    ? routing.planning_model === 'class_teacher'
                      ? 'Class-teacher model (weekly plan available)'
                      : 'Subject-teacher model (weekly plan not available)'
                    : 'Checking planning model…'}
                </p>
              </Field>
              <Field label="Week number" htmlFor="weekly-week-number">
                <Input
                  id="weekly-week-number"
                  type="number"
                  min={1}
                  value={weekNumber}
                  onChange={(e) => setWeekNumber(Number(e.target.value))}
                />
              </Field>
              <Field label="Term" htmlFor="weekly-term">
                <Select id="weekly-term" value={term} onChange={(e) => setTerm(e.target.value)}>
                  {TERMS.map((t) => <option key={t} value={t}>{t}</option>)}
                </Select>
              </Field>
              <Field label="Academic year" htmlFor="weekly-academic-year">
                <Input
                  id="weekly-academic-year"
                  value={academicYear}
                  onChange={(e) => setAcademicYear(e.target.value)}
                />
              </Field>
              <Field label="Term starts" htmlFor="weekly-term-start">
                <Input
                  id="weekly-term-start"
                  type="date"
                  value={termStart}
                  onChange={(e) => setTermStart(e.target.value)}
                />
              </Field>
              <Field label="Term ends" htmlFor="weekly-term-end">
                <Input
                  id="weekly-term-end"
                  type="date"
                  value={termEnd}
                  onChange={(e) => setTermEnd(e.target.value)}
                />
              </Field>
            </div>
          </SurfaceCard>

          {/* ── Subjects + teaching days + WAPEF fields ───────────────── */}
          <SurfaceCard data-weekly-schemes className="p-6">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-base font-semibold text-[#102A43]">Subjects and teaching days</h2>
              <span className="text-xs text-muted-foreground">
                {selectedIds.length} selected
              </span>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              Pick the schemes you teach this week, then assign the days each subject is taught.
            </p>

            {loading ? (
              <div className="flex items-center justify-center py-10" data-weekly-loading>
                <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
              </div>
            ) : schemes.length === 0 ? (
              <div className="mt-4 rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground" data-empty>
                No schemes uploaded yet. Upload a scheme of work first, then build the weekly plan.
                <div className="mt-3">
                  <Button variant="outline" size="sm" asChild>
                    <Link href="/upload">Upload a scheme</Link>
                  </Button>
                </div>
              </div>
            ) : (
              <ul className="mt-4 space-y-3">
                {schemes.map((scheme) => {
                  const selected = !!drafts[scheme.id]
                  const draft = drafts[scheme.id]
                  const mismatch = scheme.class_level && scheme.class_level !== classLevel
                  return (
                    <li key={scheme.id} className="rounded-md border" data-weekly-scheme={scheme.id}>
                      <label className="flex cursor-pointer items-start gap-3 p-3">
                        <input
                          type="checkbox"
                          className="mt-1 h-4 w-4 accent-[#04A9CE]"
                          checked={selected}
                          onChange={() => toggleScheme(scheme.id)}
                          aria-label={`Select ${scheme.subject} scheme`}
                        />
                        <span className="min-w-0 flex-1">
                          <span className="flex flex-wrap items-center gap-2">
                            <span className="font-medium">{scheme.subject || 'Unknown subject'}</span>
                            <Badge variant="outline">{scheme.class_level}</Badge>
                            {mismatch && (
                              <Badge variant="warning">
                                Different class ({scheme.class_level})
                              </Badge>
                            )}
                          </span>
                          <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                            {scheme.filename} &middot; {scheme.weeks_count} weeks
                          </span>
                        </span>
                      </label>

                      {selected && draft && (
                        <div className="border-t bg-background/60 p-3" data-weekly-subject-days={scheme.id}>
                          <p className="mb-2 text-sm font-medium">
                            {scheme.subject} teaching days
                          </p>
                          <div className="flex flex-wrap gap-2">
                            {WEEKDAY_DAYS.map((day) => (
                              <button
                                key={day}
                                type="button"
                                onClick={() => toggleDay(scheme.id, day)}
                                aria-pressed={draft.days.includes(day)}
                                className={`rounded-full px-3 py-1 text-sm ${
                                  draft.days.includes(day)
                                    ? 'bg-[#102A43] text-white'
                                    : 'bg-muted text-muted-foreground'
                                }`}
                              >
                                {DAY_LABELS[day]}
                              </button>
                            ))}
                          </div>
                          <label className="mt-2.5 flex items-center gap-2 text-xs text-muted-foreground">
                            <input
                              type="checkbox"
                              className="h-3.5 w-3.5 accent-[#04A9CE]"
                              checked={draft.shared}
                              onChange={(e) => patchDraft(scheme.id, { shared: e.target.checked })}
                            />
                            One shared entry for all selected days (renders as
                            &ldquo;{orderedDays(draft.days).join(' & ') || 'DAY'}&rdquo;)
                          </label>

                          {wapefOptions && (
                            <div className="mt-3 rounded-md border bg-background p-2.5">
                              <p className="mb-2 text-[11px] font-semibold text-[#102A43]">
                                Approved WAPEF fields
                                <span className="ml-1 font-normal text-muted-foreground">
                                  (teacher-selected — optional, never invented)
                                </span>
                              </p>
                              <div className="grid gap-2.5 sm:grid-cols-2">
                                <Field label="Deep Hope" htmlFor={`weekly-deep-hope-${scheme.id}`}>
                                  <Select
                                    id={`weekly-deep-hope-${scheme.id}`}
                                    value={draft.wapef_deep_hope}
                                    onChange={(e) => patchDraft(scheme.id, { wapef_deep_hope: e.target.value })}
                                  >
                                    <option value="">— Select —</option>
                                    {wapefOptions.deep_hopes.map((option) => (
                                      <option key={option} value={option}>{option}</option>
                                    ))}
                                  </Select>
                                </Field>
                                <Field label="Storyline" htmlFor={`weekly-storyline-${scheme.id}`}>
                                  <Select
                                    id={`weekly-storyline-${scheme.id}`}
                                    value={draft.wapef_storyline}
                                    onChange={(e) => patchDraft(scheme.id, { wapef_storyline: e.target.value })}
                                  >
                                    <option value="">— Select —</option>
                                    {wapefOptions.storylines.map((option) => (
                                      <option key={option} value={option}>{option}</option>
                                    ))}
                                  </Select>
                                </Field>
                              </div>
                              <div className="mt-2.5">
                                <p className="mb-1 text-[11px] font-medium text-muted-foreground">
                                  Through lines (select all that apply)
                                </p>
                                <div className="flex flex-wrap gap-1.5">
                                  {wapefOptions.through_lines.map((option) => {
                                    const active = draft.wapef_through_lines.includes(option)
                                    return (
                                      <button
                                        key={option}
                                        type="button"
                                        onClick={() => toggleThroughLine(scheme.id, option)}
                                        className={`rounded border px-1.5 py-0.5 text-[10px] ${
                                          active
                                            ? 'border-[#102A43] bg-[#102A43] text-white'
                                            : 'bg-background text-muted-foreground'
                                        }`}
                                      >
                                        {option}
                                      </button>
                                    )
                                  })}
                                </div>
                              </div>
                              <div className="mt-2.5">
                                <Field label="God's Story" htmlFor={`weekly-gods-story-${scheme.id}`}>
                                  <Select
                                    id={`weekly-gods-story-${scheme.id}`}
                                    value={draft.wapef_gods_story}
                                    onChange={(e) => patchDraft(scheme.id, { wapef_gods_story: e.target.value })}
                                  >
                                    <option value="">— Select —</option>
                                    {wapefOptions.gods_story.map((option) => (
                                      <option key={option} value={option}>{option}</option>
                                    ))}
                                  </Select>
                                </Field>
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </li>
                  )
                })}
              </ul>
            )}
          </SurfaceCard>

          {/* ── Preview ────────────────────────────────────────────────── */}
          {preview && (
            <SurfaceCard data-weekly-preview className="p-6">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-[#04769B]" aria-hidden="true" />
                <h2 className="text-base font-semibold text-[#102A43]">
                  Preview — {preview.plan.class_level}, Week {preview.plan.week_number}
                </h2>
              </div>
              {preview.validation_issues.length === 0 && (
                <p className="mt-1 text-sm text-muted-foreground">
                  One weekly document with {preview.plan.subjects.length} subject section(s).
                  Review each subject and its day rows, then save.
                </p>
              )}
              <div className="mt-4 space-y-4">
                {preview.plan.subjects.map((subject) => (
                  <div key={subject.scheme_of_work_id} className="rounded-md border" data-weekly-preview-subject>
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-background/60 px-3 py-2">
                      <span className="font-medium">{subject.subject}</span>
                      <span className="flex flex-wrap gap-1">
                        {subject.teaching_day_groups.map((group) => (
                          <Badge key={group.join('&')} variant="secondary">
                            {group.join(' & ')}
                          </Badge>
                        ))}
                      </span>
                    </div>
                    <ul className="divide-y">
                      {subject.day_plans.map((day, index) => (
                        <li key={`${day.day_label}-${index}`} className="px-3 py-2 text-sm">
                          <p className="font-medium text-[#102A43]">{day.day_label}</p>
                          <p className="mt-0.5 text-muted-foreground">{day.starter}</p>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </SurfaceCard>
          )}
        </div>

        {/* ── Action rail ───────────────────────────────────────────── */}
        <div className="lg:col-span-1 lg:sticky lg:top-20 lg:self-start">
          <SurfaceCard data-weekly-action className="p-6 space-y-4">
            <div>
              <h2 className="text-base font-semibold text-[#102A43]">Generate this week</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {selectedIds.length === 0
                  ? 'Select at least one subject scheme.'
                  : `${selectedIds.length} subject(s) · ${classLevel} · Week ${weekNumber}`}
              </p>
            </div>

            {preview && (
              <div className="rounded-md border bg-background p-3 text-sm" data-weekly-preview-summary>
                {preview.validation_issues.length === 0 ? (
                  <p className="text-green-700">
                    Ready to save: {preview.plan.subjects.length} subject section(s),{' '}
                    {preview.plan.subjects.reduce((n, s) => n + s.day_plans.length, 0)} day row(s).
                  </p>
                ) : (
                  <p className="text-destructive">
                    {preview.validation_issues.length} issue(s) must be resolved before saving.
                  </p>
                )}
              </div>
            )}

            <Button
              className="w-full"
              onClick={handlePreview}
              disabled={previewing || saving || !isClassTeacher || loading}
              data-weekly-preview-button
            >
              {previewing ? 'Generating…' : 'Preview week'}
              {!previewing && <ChevronRight className="ml-1 h-4 w-4" aria-hidden="true" />}
            </Button>
            <Button
              className="w-full"
              onClick={handleSave}
              disabled={!preview || preview.validation_issues.length > 0 || saving}
              data-weekly-save
            >
              {saving ? 'Saving…' : 'Save weekly plan'}
            </Button>
            <p className="text-xs text-muted-foreground">
              <CalendarDays className="mr-1 inline h-3.5 w-3.5" aria-hidden="true" />
              Saved plans reopen for review, editing and DOCX/PDF export.
            </p>
          </SurfaceCard>
        </div>
      </div>
    </div>
  )
}
