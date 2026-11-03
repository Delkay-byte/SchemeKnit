'use client'

/**
 * Guided lesson / generation configuration.
 *
 * ONE dialog is used from the upload-success screen and from the Generate
 * page. It owns teaching setup, generation method, template/AI settings and
 * per-indicator references + additional TLRs. Saved values live on the scheme
 * (persisted by the backend) and are keyed by the canonical source occurrence.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Field } from '@/components/ui/field'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { DraftRecoveryBanner, DraftSaveStatus } from '@/components/ui/draft-recovery'
import { toast } from '@/components/ui/toaster'
import { Loader2, Save, Settings } from 'lucide-react'
import { api } from '@/lib/api'
import { normalizeError } from '@/lib/error-normalizer'
import { useAuth } from '@/lib/auth-context'
import { useFormDraft } from '@/hooks/use-form-draft'
import { prefillLessonConfig } from '@/lib/prefill'
import { readClearedFields, setFieldCleared } from '@/lib/prefill-overrides'
import {
  TERMS, WEEK_DAYS, firstLessonConfigProblem, indicatorCode,
  sourceOccurrenceId, splitEntries, validateLessonConfig, weekOccurrences,
} from '@/lib/lesson-config'
import { LessonRubricConfig } from '@/types'

interface SchemeWeek {
  week_number: number
  strand?: string
  sub_strand?: string
  indicators?: string[]
  resources?: string[]
}

export interface LessonConfigModalProps {
  schemeId: string
  open: boolean
  onOpenChange: (open: boolean) => void
  config: LessonRubricConfig
  onSaved: (config: LessonRubricConfig, missing: string[]) => void
  /** Method chosen on the upload-success screen. */
  initialMethod?: 'standard' | 'zeli'
}

export function LessonConfigModal({
  schemeId, open, onOpenChange, config, onSaved, initialMethod,
}: LessonConfigModalProps) {
  const { user } = useAuth()
  const [draft, setDraft] = useState<LessonRubricConfig>(config)
  const [baseline, setBaseline] = useState<LessonRubricConfig>(config)
  const [saving, setSaving] = useState(false)
  const savingRef = useRef(false)
  const [error, setError] = useState<string | null>(null)
  const [discardArmed, setDiscardArmed] = useState(false)
  const [scheme, setScheme] = useState<{ class_level?: string; subject?: string; term?: string; academic_year?: string; filename?: string } | null>(null)
  const [weeks, setWeeks] = useState<SchemeWeek[]>([])
  const [templates, setTemplates] = useState<{ id: string; name: string }[]>([])
  const [zeliStatus, setZeliStatus] = useState<{ active: boolean; reason?: string | null } | null>(null)

  const [clearedFields, setClearedFields] = useState<string[]>([])
  const prefill = useMemo<LessonRubricConfig>(
    () => prefillLessonConfig(config, user, new Set(clearedFields)),
    [config, user, clearedFields],
  )
  const overrideIdentity = user?.id
    ? { userId: user.id, workflow: 'lesson-config', resourceId: schemeId }
    : null

  const dirty = JSON.stringify(draft) !== JSON.stringify(baseline)
  const draftStore = useFormDraft<LessonRubricConfig>({
    userId: user?.id || null,
    workflow: 'lesson-config',
    resourceId: schemeId,
    value: draft,
    enabled: open && dirty,
  })

  useEffect(() => {
    if (!open) return
    const cleared = overrideIdentity ? readClearedFields(overrideIdentity) : new Set<string>()
    setClearedFields(Array.from(cleared))
    const base = prefillLessonConfig(config, user, cleared)
    const next: LessonRubricConfig = {
      ...base,
      generation_method: initialMethod || base.generation_method || 'standard',
      term: base.term || 'First Term',
      term_start_date: base.term_start_date || '',
      term_end_date: base.term_end_date || '',
      lessons_per_week: base.lessons_per_week ?? base.periods_per_week ?? 3,
      lesson_duration_minutes: base.lesson_duration_minutes ?? 60,
      teaching_days: base.teaching_days?.length ? base.teaching_days : [0, 2, 4],
      indicator_resources: base.indicator_resources || {},
    }
    setDraft(next)
    setBaseline(next)
    setError(null)
    setShowProblems(false)
    setDiscardArmed(false)

    api.getScheme(schemeId).then((data) => {
      setScheme(data)
      setDraft((current) => ({
        ...current,
        term: current.term || data.term || 'First Term',
      }))
    }).catch(() => {})
    api.getSchemeWeeks(schemeId)
      .then((data) => setWeeks(data.weeks || []))
      .catch(() => setWeeks([]))
    api.listTemplates()
      .then((data) => setTemplates(data.templates || []))
      .catch(() => setTemplates([]))
    // Only opening the dialog starts a fresh draft.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  useEffect(() => {
    if (!open) return
    const method = draft.generation_method || 'standard'
    if (method !== 'zeli') {
      setZeliStatus(null)
      return
    }
    api.getAiStatus(draft.ai_mode || 'OFF', 'zeli')
      .then((status) => setZeliStatus({ active: Boolean(status.active), reason: status.reason }))
      .catch(() => setZeliStatus({ active: false, reason: 'Zeli status could not be checked.' }))
  }, [open, draft.generation_method, draft.ai_mode])

  const handleOpenChange = (next: boolean) => {
    if (!next && dirty) {
      if (discardArmed) {
        draftStore.clear()
        setDiscardArmed(false)
        onOpenChange(false)
      } else {
        setDiscardArmed(true)
      }
      return
    }
    setDiscardArmed(false)
    onOpenChange(next)
  }

  const rememberExplicitBlanks = (saved: LessonRubricConfig) => {
    if (!overrideIdentity) return
    for (const field of ['teacher_name', 'school_name'] as const) {
      setFieldCleared(overrideIdentity, field, !(saved[field] || '').trim())
    }
    setClearedFields(Array.from(readClearedFields(overrideIdentity)))
  }

  const indicatorValue = (key: string, field: 'references' | 'tlrs'): string => {
    const entry = draft.indicator_resources?.[key]
    return (entry?.[field] || []).join('\n')
  }

  const setIndicatorValue = (key: string, field: 'references' | 'tlrs', raw: string) => {
    setDraft((current) => {
      const resources = { ...(current.indicator_resources || {}) }
      const entry = resources[key] || { references: [], tlrs: [] }
      resources[key] = { ...entry, [field]: splitEntries(raw) }
      return { ...current, indicator_resources: resources }
    })
  }

  const [showProblems, setShowProblems] = useState(false)
  const problems = validateLessonConfig(draft, {
    zeliAvailable: draft.generation_method === 'zeli' && zeliStatus
      ? zeliStatus.active
      : undefined,
    zeliReason: zeliStatus?.reason,
  })

  const handleSave = async () => {
    if (savingRef.current) return
    setShowProblems(true)
    const problem = firstLessonConfigProblem(problems)
    if (problem) {
      setError(problem)
      return
    }
    savingRef.current = true
    setSaving(true)
    setError(null)
    toast({
      title: 'Saving lesson settings…',
      variant: 'info',
      duration: 4000,
      key: `lesson-config-saving:${schemeId}`,
    })
    try {
      const resp = await api.saveLessonConfig(schemeId, {
        ...draft,
        school_name: (draft.school_name || '').trim() || null,
        teacher_name: (draft.teacher_name || '').trim() || null,
        term: draft.term || null,
        term_start_date: draft.term_start_date || null,
        term_end_date: draft.term_end_date || null,
        periods_per_week: draft.lessons_per_week ?? null,
        lessons_per_week: draft.lessons_per_week ?? null,
        generation_method: draft.generation_method || 'standard',
        ai_mode: draft.ai_mode || 'OFF',
        template_id: draft.template_id || null,
        indicator_resources: draft.indicator_resources || {},
        reference: null,
      })
      const savedConfig = resp.config || draft
      rememberExplicitBlanks(savedConfig)
      draftStore.clear()
      onSaved(savedConfig, resp.missing || [])
      onOpenChange(false)
      toast({
        title: 'Lesson settings saved.',
        variant: 'success',
        key: `lesson-config-saved:${schemeId}`,
      })
    } catch (err) {
      const normalized = normalizeError(err)
      setError(normalized.message)
      toast({
        title: 'Lesson settings were not saved',
        description: normalized.message,
        variant: 'error',
        key: `lesson-config-error:${schemeId}`,
        action: { label: 'Try again', onClick: () => { void handleSave() } },
      })
    } finally {
      savingRef.current = false
      setSaving(false)
    }
  }

  const applyRecovered = () => {
    const recovered = draftStore.accept()
    if (recovered) {
      setDraft({ ...prefill, ...recovered })
      setBaseline(prefill)
    }
  }

  const discardRecovered = () => {
    draftStore.discard()
    setDraft(prefill)
    setBaseline(prefill)
  }

  if (!open) return null

  const className = scheme?.class_level || ''
  const activeMethod = draft.generation_method || 'standard'

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl" data-lesson-config-modal>
        <DialogHeader>
          <DialogTitle>Configure teaching setup &amp; lesson rubrics</DialogTitle>
          <DialogDescription>
            These settings apply to this scheme only. Every curriculum indicator
            keeps its own references and additional TLRs.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-2">
          {draftStore.recovered && (
            <DraftRecoveryBanner
              updatedAt={draftStore.recovered.updatedAt}
              label="Unsaved lesson settings for this scheme"
              onContinue={applyRecovered}
              onDiscard={discardRecovered}
            />
          )}

          <section aria-labelledby="setup-heading" className="space-y-3">
            <h3 id="setup-heading" className="text-sm font-semibold text-[#102A43]">Teaching setup</h3>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="School name" htmlFor="lcfg-school" required
                error={showProblems ? problems.school_name : undefined}>
                <Input id="lcfg-school" autoComplete="organization"
                  value={draft.school_name || ''}
                  onChange={(e) => setDraft({ ...draft, school_name: e.target.value })} />
              </Field>
              <Field label="Class" htmlFor="lcfg-class" hint="Detected from your scheme">
                <Input id="lcfg-class" value={className} disabled className="bg-muted text-muted-foreground" />
              </Field>
              <Field label="Teacher's name" htmlFor="lcfg-teacher" hint="From your profile — update it in Settings">
                <Input id="lcfg-teacher" autoComplete="name" value={draft.teacher_name || ''}
                  onChange={(e) => setDraft({ ...draft, teacher_name: e.target.value })} />
              </Field>
              <Field label="Class size" htmlFor="lcfg-class-size" required
                error={showProblems ? problems.class_size : undefined}>
                <Input id="lcfg-class-size" type="number" min={1} max={500}
                  value={draft.class_size ?? ''}
                  onChange={(e) => {
                    const value = parseInt(e.target.value, 10)
                    setDraft({ ...draft, class_size: Number.isFinite(value) && value > 0 ? value : null })
                  }} />
              </Field>
              <Field label="Lesson duration (min)" htmlFor="lcfg-duration" required
                error={showProblems ? problems.lesson_duration_minutes : undefined}>
                <Input id="lcfg-duration" type="number" min={20} max={240}
                  value={draft.lesson_duration_minutes ?? ''}
                  onChange={(e) => {
                    const value = parseInt(e.target.value, 10)
                    setDraft({ ...draft, lesson_duration_minutes: Number.isFinite(value) ? value : null })
                  }} />
              </Field>
              <Field label="Lessons per week" htmlFor="lcfg-lessons-week" required
                error={showProblems ? problems.lessons_per_week : undefined}>
                <Input id="lcfg-lessons-week" type="number" min={1} max={15}
                  value={draft.lessons_per_week ?? ''}
                  onChange={(e) => {
                    const value = parseInt(e.target.value, 10)
                    setDraft({ ...draft, lessons_per_week: Number.isFinite(value) && value > 0 ? value : null })
                  }} />
              </Field>
              <Field label="Term start" htmlFor="lcfg-term-start">
                <Input id="lcfg-term-start" type="date" value={draft.term_start_date || ''}
                  onChange={(e) => setDraft({ ...draft, term_start_date: e.target.value })} />
              </Field>
              <Field label="Term end" htmlFor="lcfg-term-end"
                error={showProblems ? problems.term_end_date : undefined}>
                <Input id="lcfg-term-end" type="date" value={draft.term_end_date || ''}
                  onChange={(e) => setDraft({ ...draft, term_end_date: e.target.value })} />
              </Field>
              <Field label="Academic term" htmlFor="lcfg-term">
                <select id="lcfg-term" className="h-10 w-full rounded-md border border-input bg-white px-3 text-sm"
                  value={draft.term || 'First Term'}
                  onChange={(e) => setDraft({ ...draft, term: e.target.value })}>
                  {TERMS.map((term) => <option key={term} value={term}>{term}</option>)}
                </select>
              </Field>
              <Field label="Academic year" htmlFor="lcfg-academic-year" hint="From your uploaded scheme">
                <Input id="lcfg-academic-year" value={scheme?.academic_year || ''} disabled
                  className="bg-muted text-muted-foreground" />
              </Field>
              <Field label="Period / timing" htmlFor="lcfg-period" hint="Leave blank if not applicable">
                <Input id="lcfg-period" value={draft.period || ''}
                  placeholder="e.g. 1st & 2nd — leave blank if not applicable"
                  onChange={(e) => setDraft({ ...draft, period: e.target.value })} />
              </Field>
            </div>
            <div>
              <p className="mb-2 text-sm font-medium">Teaching days<span className="ml-0.5 text-destructive">*</span></p>
              <div className="flex flex-wrap gap-2">
                {WEEK_DAYS.map((day) => {
                  const selected = (draft.teaching_days || []).includes(day.value)
                  return (
                    <button key={day.value} type="button" aria-pressed={selected}
                      onClick={() => {
                        const current = draft.teaching_days || []
                        const next = selected ? current.filter((d) => d !== day.value)
                          : [...current, day.value].sort((a, b) => a - b)
                        setDraft({ ...draft, teaching_days: next })
                      }}
                      className={`rounded-full px-3 py-1 text-sm ${selected ? 'bg-[#102A43] text-white' : 'bg-muted text-muted-foreground'}`}>
                      {day.label}
                    </button>
                  )
                })}
              </div>
              {showProblems && problems.teaching_days && (
                <p role="alert" className="mt-1 text-xs font-medium text-destructive">
                  {problems.teaching_days}
                </p>
              )}
            </div>
          </section>

          <section aria-labelledby="method-heading" className="space-y-3 border-t pt-4">
            <h3 id="method-heading" className="text-sm font-semibold text-[#102A43]">Generation method</h3>
            <div className="grid gap-2 sm:grid-cols-2">
              <button type="button" aria-pressed={activeMethod === 'standard'}
                data-generation-method="standard"
                onClick={() => setDraft({ ...draft, generation_method: 'standard' })}
                className={`rounded-xl border p-3 text-left ${activeMethod === 'standard' ? 'border-[#04A9CE] bg-[#04A9CE]/5' : 'border-slate-200'}`}>
                <span className="block font-semibold">Standard</span>
                <span className="text-xs text-muted-foreground">Deterministic lessons, optionally enriched.</span>
              </button>
              <button type="button" aria-pressed={activeMethod === 'zeli'}
                data-generation-method="zeli"
                onClick={() => setDraft({ ...draft, generation_method: 'zeli' })}
                className={`rounded-xl border p-3 text-left ${activeMethod === 'zeli' ? 'border-[#04A9CE] bg-[#04A9CE]/5' : 'border-slate-200'}`}>
                <span className="block font-semibold">Generate with Zeli</span>
                <span className="text-xs text-muted-foreground">Zeli writes each whole lesson plan.</span>
              </button>
            </div>
            {activeMethod === 'zeli' && zeliStatus && (
              <p className={`text-xs ${zeliStatus.active ? 'text-green-700' : 'text-amber-800'}`} role="status">
                {zeliStatus.active ? 'Zeli is ready.' : (zeliStatus.reason || 'Zeli is unavailable. Choose Standard or fix provider settings.')}
              </p>
            )}
            {showProblems && problems.generation_method && (
              <p role="alert" className="text-xs font-medium text-destructive">
                {problems.generation_method}
              </p>
            )}
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Template" htmlFor="lcfg-template">
                <select id="lcfg-template" className="h-10 w-full rounded-md border border-input bg-white px-3 text-sm"
                  value={draft.template_id || ''}
                  onChange={(e) => setDraft({ ...draft, template_id: e.target.value })}>
                  <option value="">Approved GES Plan (Default)</option>
                  {templates.map((template) => (
                    <option key={template.id} value={template.id}>{template.name}</option>
                  ))}
                </select>
              </Field>
              <Field label="AI mode" htmlFor="lcfg-ai-mode"
                hint={activeMethod === 'zeli' ? 'Zeli writes whole lessons; enrichment mode is not used.' : undefined}>
                <select id="lcfg-ai-mode" className="h-10 w-full rounded-md border border-input bg-white px-3 text-sm"
                  value={draft.ai_mode || 'OFF'} disabled={activeMethod === 'zeli'}
                  onChange={(e) => setDraft({ ...draft, ai_mode: e.target.value })}>
                  <option value="OFF">OFF — deterministic</option>
                  <option value="BASIC">BASIC — teacher-facing assistance</option>
                  <option value="ENHANCED">ENHANCED — fuller AI assistance</option>
                </select>
              </Field>
            </div>
            <p id="cfg-ai-mode-note" className="text-xs text-muted-foreground">
              {activeMethod === 'zeli'
                ? 'Zeli writes whole lessons, so enrichment mode is not used.'
                : 'Reading and writing support is controlled by the selected method and your provider configuration.'}{' '}
              Zeli never silently falls back to Standard.
            </p>
          </section>

          <section aria-labelledby="per-lesson-heading" className="space-y-3 border-t pt-4">
            <div>
              <h3 id="per-lesson-heading" className="text-sm font-semibold text-[#102A43]">
                References and additional TLRs by lesson
              </h3>
              <p className="text-xs text-muted-foreground">
                Each indicator becomes its own lesson. Enter one reference/TLR per line
                for that lesson only.
              </p>
            </div>
            {weeks.length === 0 ? (
              <p className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-muted-foreground">
                No curriculum weeks are available yet.
              </p>
            ) : (
              <div className="max-h-80 space-y-4 overflow-y-auto pr-1">
                {weeks.map((week) => (
                  <div key={week.week_number} className="rounded-xl border border-slate-200 p-3">
                    <p className="text-sm font-semibold text-[#102A43]">Week {week.week_number}</p>
                    <p className="text-xs text-muted-foreground">
                      {[week.strand, week.sub_strand].filter(Boolean).join(' · ') || 'Curriculum week'}
                    </p>
                    {(week.resources || []).length > 0 && (
                      <p className="mt-1 text-xs text-muted-foreground">
                        Source TLRs: {(week.resources || []).join(', ')}
                      </p>
                    )}
                    {weekOccurrences(week.indicators || []).length === 0 ? (
                      <p className="mt-2 text-xs text-muted-foreground">No indicators in this week.</p>
                    ) : (
                      weekOccurrences(week.indicators || []).map((indicator, position) => {
                        const key = sourceOccurrenceId(week.week_number, position, indicator)
                        return (
                          <div key={key} className="mt-3 space-y-2 rounded-lg bg-slate-50 p-2.5">
                            <p className="text-xs font-medium text-[#102A43]">
                              {indicatorCode(indicator) ? `${indicatorCode(indicator)} — ` : ''}{indicator}
                            </p>
                            <Field label="References" htmlFor={`ref-${key}`}>
                              <textarea id={`ref-${key}`} rows={2}
                                className="w-full rounded-md border border-input bg-white px-2.5 py-2 text-xs"
                                placeholder="One reference per line"
                                value={indicatorValue(key, 'references')}
                                onChange={(e) => setIndicatorValue(key, 'references', e.target.value)} />
                            </Field>
                            <Field label="Additional TLRs" htmlFor={`tlr-${key}`}>
                              <textarea id={`tlr-${key}`} rows={2}
                                className="w-full rounded-md border border-input bg-white px-2.5 py-2 text-xs"
                                placeholder="One teacher-added resource per line"
                                value={indicatorValue(key, 'tlrs')}
                                onChange={(e) => setIndicatorValue(key, 'tlrs', e.target.value)} />
                            </Field>
                          </div>
                        )
                      })
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          {discardArmed && dirty && (
            <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900" role="alert">
              You have unsaved changes. Click Cancel again to discard them, or Save configuration to keep them.
            </p>
          )}
          {error && (
            <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900" role="alert">
              {error}
            </p>
          )}
        </div>

        <DialogFooter className="sm:items-center sm:justify-between">
          <DraftSaveStatus status={draftStore.status} savedAt={draftStore.savedAt} />
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="ghost" asChild>
              <Link href="/settings"><Settings className="mr-1.5 h-4 w-4" />Settings</Link>
            </Button>
            <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>Cancel</Button>
            <Button type="button" disabled={saving} onClick={handleSave} data-save-lesson-config>
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="mr-2 h-4 w-4" aria-hidden="true" />}
              Save configuration
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
