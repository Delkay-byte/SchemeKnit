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
import { Field, TextArea } from '@/components/ui/field'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { DraftRecoveryBanner, DraftSaveStatus } from '@/components/ui/draft-recovery'
import { MultilineListField } from '@/components/ui/multiline-list-field'
import { toast } from '@/components/ui/toaster'
import { Loader2, Save, Settings } from 'lucide-react'
import { api } from '@/lib/api'
import { normalizeError } from '@/lib/error-normalizer'
import { useAuth } from '@/lib/auth-context'
import { useFormDraft } from '@/hooks/use-form-draft'
import { prefillLessonConfig } from '@/lib/prefill'
import { readClearedFields, setFieldCleared } from '@/lib/prefill-overrides'
import {
  CORE_COMPETENCY_LABELS, TERMS, WEEK_DAYS, firstLessonConfigProblem, indicatorCode,
  sourceOccurrenceId, toggleCompetency, validateLessonConfig, weekOccurrences,
} from '@/lib/lesson-config'
import { LessonRubricConfig, WapefAnnualProfile, WapefOptions } from '@/types'

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
  const [annual, setAnnual] = useState<WapefAnnualProfile | null>(null)
  const [annualOptions, setAnnualOptions] = useState<WapefOptions | null>(null)
  const [wapefOptions, setWapefOptions] = useState<WapefOptions | null>(null)
  const [annualDirty, setAnnualDirty] = useState(false)
  const [annualEditing, setAnnualEditing] = useState(false)
  const [autoStatus, setAutoStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [autoSavedAt, setAutoSavedAt] = useState<Date | null>(null)
  const autoSeq = useRef(0)

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
    // WAPEF annual values (Deep Hope + Storyline) are keyed by the scheme's
    // academic year on the server. Loading them here means reopening the
    // dialog or switching to GES and back never loses the year's choices.
    api.getWapefAnnual(schemeId)
      .then((profile) => {
        setAnnual(profile)
        setAnnualDirty(false)
        setAnnualEditing(false)
        if (profile.options) {
          setAnnualOptions({
            deep_hopes: profile.options.deep_hopes || [],
            storylines: profile.options.storylines || [],
            through_lines: [],
            gods_story: [],
          })
        }
      })
      .catch(() => setAnnual(null))
    api.getWapefOptions()
      .then((options) => setWapefOptions(options))
      .catch(() => setWapefOptions(null))
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

  const restoreProfileDefault = (field: 'teacher_name' | 'school_name') => {
    const value = field === 'teacher_name'
      ? (user?.full_name || '').trim()
      : (user?.school_name || '').trim()
    if (!value) return
    if (overrideIdentity) setFieldCleared(overrideIdentity, field, false)
    setClearedFields((current) => current.filter((item) => item !== field))
    setDraft((current) => ({ ...current, [field]: value }))
  }

  const rememberExplicitBlanks = (saved: LessonRubricConfig) => {
    if (!overrideIdentity) return
    for (const field of ['teacher_name', 'school_name'] as const) {
      setFieldCleared(overrideIdentity, field, !(saved[field] || '').trim())
    }
    setClearedFields(Array.from(readClearedFields(overrideIdentity)))
  }

  const indicatorWapefValue = (key: string) => draft.indicator_wapef?.[key] || {}

  const setIndicatorWapef = (
    key: string,
    patch: { through_lines?: string[]; gods_story?: string },
  ) => {
    setDraft((current) => ({
      ...current,
      indicator_wapef: {
        ...(current.indicator_wapef || {}),
        [key]: { ...(current.indicator_wapef?.[key] || {}), ...patch },
      },
    }))
  }

  const setIndicatorValue = (key: string, field: 'references' | 'tlrs', entries: string[]) => {    setDraft((current) => {
      const resources = { ...(current.indicator_resources || {}) }
      const entry = resources[key] || { references: [], tlrs: [] }
      resources[key] = { ...entry, [field]: entries }
      return { ...current, indicator_resources: resources }
    })
  }

  const setIndicatorKeywords = (key: string, entries: string[]) => {
    setDraft((current) => ({
      ...current,
      indicator_keywords: {
        ...(current.indicator_keywords || {}),
        [key]: entries,
      },
    }))
  }

  const competencyValue = (key: string): string[] => (
    draft.competency_selections?.[key] || []
  )

  const setCompetencyValue = (key: string, label: string) => {
    setDraft((current) => {
      const selections = { ...(current.competency_selections || {}) }
      selections[key] = toggleCompetency(selections[key], label)
      return { ...current, competency_selections: selections }
    })
  }

  const [showProblems, setShowProblems] = useState(false)
  const problems = validateLessonConfig(draft, {
    zeliAvailable: draft.generation_method === 'zeli' && zeliStatus
      ? zeliStatus.active
      : undefined,
    zeliReason: zeliStatus?.reason,
  })

  // The approved WAPEF plan is the only template that owns the annual fields.
  const isWapefTemplate = (draft.template_id || '').startsWith('tpl-wapef')
  const annualReady = Boolean(annual?.deep_hope && annual?.storyline)

  const configPayload = () => ({
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
    competency_selections: draft.competency_selections || {},
    reference: (draft.reference || '').trim() || null,
  })

  const setAnnualField = (field: 'deep_hope' | 'storyline', value: string) => {
    setAnnual((current) => current ? { ...current, [field]: value } : current)
    setAnnualDirty(true)
    setAutoStatus('idle')
  }

  const saveAnnualValues = async () => {
    if (!annual) return
    const hope = (annual.deep_hope || '').trim()
    const story = (annual.storyline || '').trim()
    if (!hope || !story) {
      setError('Enter both Deep Hope and Storyline before saving them.')
      return
    }
    try {
      const saved = await api.saveWapefAnnual(schemeId, {
        deep_hope: hope,
        storyline: story,
      })
      setAnnual(saved)
      setAnnualDirty(false)
      setAnnualEditing(false)
      setError(null)
    } catch (err) {
      const normalized = normalizeError(err)
      setError(normalized.message)
    }
  }

  const persistSchoolName = async () => {
    const value = (draft.school_name || '').trim()
    if (!value || value === (user?.school_name || '').trim()) return
    try {
      await api.updateProfile({ school_name: value })
    } catch {
      // The plan config still carries the school name; the profile sync is a
      // convenience and must never block saving the configuration.
    }
  }

  // Option list fallback: if the annual-profile request failed, still load the
  // approved lists so the teacher is never shown an empty WAPEF selector.
  useEffect(() => {
    if (!open || !isWapefTemplate || annualOptions) return
    api.getWapefOptions()
      .then((options) => setAnnualOptions(options))
      .catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isWapefTemplate, annualOptions])

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
    if (isWapefTemplate && !annualReady) {
      savingRef.current = false
      setSaving(false)
      setError(
        `Select Deep Hope and Storyline for ${annual?.academic_year || 'this academic year'} before saving the WAPEF plan.`,
      )
      setShowProblems(true)
      return
    }
    try {
      if (isWapefTemplate && annual) {
        await api.saveWapefAnnual(schemeId, {
          deep_hope: annual.deep_hope || '',
          storyline: annual.storyline || '',
        })
        setAnnualDirty(false)
      }
      const resp = await api.saveLessonConfig(schemeId, configPayload())
      await persistSchoolName()
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
    } finally {
      savingRef.current = false
      setSaving(false)
    }
  }

  // ── Autosave (debounced) ─────────────────────────────────────────────
  // Every teacher input persists through the same endpoints as "Save", so a
  // refresh or navigation never loses work. The explicit Save stays for
  // validation and for the "I am done" moment; autosave keeps the draft.
  useEffect(() => {
    if (!open) return
    const wapef = (draft.template_id || '').startsWith('tpl-wapef')
    const annualChanged = wapef && annualDirty && !annualEditing && Boolean(
      annual?.deep_hope && annual?.storyline)
    if (!dirty && !annualChanged) return
    const seq = ++autoSeq.current
    const timer = setTimeout(async () => {
      setAutoStatus('saving')
      try {
        if (annualChanged && annual) {
          await api.saveWapefAnnual(schemeId, {
            deep_hope: annual.deep_hope || '',
            storyline: annual.storyline || '',
          })
          if (seq === autoSeq.current) setAnnualDirty(false)
        }
        await api.saveLessonConfig(schemeId, configPayload())
        await persistSchoolName()
        if (seq !== autoSeq.current) return
        setAutoStatus('saved')
        setAutoSavedAt(new Date())
        setBaseline(draft)
      } catch {
        if (seq !== autoSeq.current) return
        setAutoStatus('error')
      }
    }, 1200)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, baseline, annualDirty, annual?.deep_hope, annual?.storyline, open, schemeId, annualEditing])

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
                {Boolean(user?.school_name) && (draft.school_name || '') !== user?.school_name && (
                  <button type="button"
                    className="text-xs font-medium text-[#035f7c] underline"
                    onClick={() => restoreProfileDefault('school_name')}>
                    Use my school from profile
                  </button>
                )}
              </Field>
              <Field label="Class" htmlFor="lcfg-class" hint="Detected from your scheme">
                <Input id="lcfg-class" value={className} disabled className="bg-muted text-muted-foreground" />
              </Field>
              <Field label="Teacher's name" htmlFor="lcfg-teacher" hint="From your profile — update it in Settings">
                <Input id="lcfg-teacher" autoComplete="name" value={draft.teacher_name || ''}
                  onChange={(e) => setDraft({ ...draft, teacher_name: e.target.value })} />
                {Boolean(user?.full_name) && (draft.teacher_name || '') !== user?.full_name && (
                  <button type="button"
                    className="text-xs font-medium text-[#035f7c] underline"
                    onClick={() => restoreProfileDefault('teacher_name')}>
                    Use my name from profile
                  </button>
                )}
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
              <Field label="Reference (plan header)" htmlFor="lcfg-reference"
                hint="Optional. Leave blank if the scheme states none">
                <Input id="lcfg-reference" value={draft.reference || ''}
                  placeholder="e.g. Computing Curriculum, p. 12"
                  onChange={(e) => setDraft({ ...draft, reference: e.target.value })} />
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
                onClick={() => setDraft({ ...draft, generation_method: 'standard', ai_mode: 'OFF' })}
                className={`rounded-xl border p-3 text-left ${activeMethod === 'standard' ? 'border-[#04A9CE] bg-[#04A9CE]/5' : 'border-slate-200'}`}>
                <span className="block font-semibold">Generate with Deterministic Engine</span>
                <span className="text-xs text-muted-foreground">
                  Builds complete plans from your scheme without AI. Fast,
                  predictable, and uses no AI credit.
                </span>
              </button>
              <button type="button" aria-pressed={activeMethod === 'zeli'}
                data-generation-method="zeli"
                onClick={() => setDraft({ ...draft, generation_method: 'zeli', ai_mode: 'OFF' })}
                className={`rounded-xl border p-3 text-left ${activeMethod === 'zeli' ? 'border-[#04A9CE] bg-[#04A9CE]/5' : 'border-slate-200'}`}>
                <span className="block font-semibold">Generate with Zeli AI</span>
                <span className="text-xs text-muted-foreground">
                  Zeli writes each whole lesson plan from your scheme. Richer
                  wording, slower, and uses an AI credit.
                </span>
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
                  onChange={(e) => {
                    const templateId = e.target.value
                    setDraft({ ...draft, template_id: templateId })
                    if (!templateId.startsWith('tpl-wapef')) setAnnualEditing(false)
                    if (templateId.startsWith('tpl-wapef') && !annual) {
                      setAnnual({
                        academic_year: scheme?.academic_year || '',
                        deep_hope: '',
                        storyline: '',
                        configured: false,
                        missing: ['Deep Hope', 'Storyline'],
                      })
                    }
                  }}>
                  <option value="">Approved GES Plan (Default)</option>
                  {templates.map((template) => (
                    <option key={template.id} value={template.id}>{template.name}</option>
                  ))}
                </select>
              </Field>
            </div>

            {isWapefTemplate && (
              <div className="space-y-3 rounded-xl border border-[#04A9CE]/30 bg-[#04A9CE]/5 p-3" data-wapef-annual>
                <div>
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <h4 className="text-sm font-semibold text-[#102A43]">WAPEF — this academic year</h4>
                    {!annualEditing ? (
                      <Button type="button" size="sm" variant="outline"
                        data-edit-wapef-annual
                        onClick={() => setAnnualEditing(true)}>
                        Edit
                      </Button>
                    ) : (
                      <span className="text-xs font-medium text-[#035f7c]" role="status">
                        Editing — save to lock for the year
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Deep Hope and Storyline apply to every WAPEF lesson in{' '}
                    {annual?.academic_year || scheme?.academic_year || 'this academic year'}.
                    They stay locked for the year unless you click Edit again. A
                    new academic year starts empty and never inherits these values.
                  </p>
                </div>
                {!annualEditing ? (
                  <dl className="grid gap-3 text-sm sm:grid-cols-2" data-wapef-annual-read>
                    <div className="rounded-lg border border-slate-200 bg-white p-2.5">
                      <dt className="text-xs font-medium text-muted-foreground">Deep Hope</dt>
                      <dd className="mt-0.5 text-[#102A43]">
                        {annual?.deep_hope || 'Not set yet — click Edit.'}
                      </dd>
                    </div>
                    <div className="rounded-lg border border-slate-200 bg-white p-2.5">
                      <dt className="text-xs font-medium text-muted-foreground">Storyline</dt>
                      <dd className="mt-0.5 text-[#102A43]">
                        {annual?.storyline || 'Not set yet — click Edit.'}
                      </dd>
                    </div>
                  </dl>
                ) : (
                  <>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <Field label="Deep Hope" htmlFor="lcfg-deep-hope" required
                        error={showProblems && !annual?.deep_hope ? 'Enter the Deep Hope for this academic year.' : undefined}>
                        <TextArea id="lcfg-deep-hope" rows={3}
                          value={annual?.deep_hope || ''}
                          placeholder="Write the enduring hope for this year's learners"
                          onChange={(e) => setAnnualField('deep_hope', e.target.value)} />
                        {(annualOptions?.deep_hopes || []).map((option) => (
                          <button key={option} type="button"
                            className="mt-1 text-left text-xs font-medium text-[#035f7c] underline"
                            onClick={() => setAnnualField('deep_hope', option)}>
                            Use approved wording
                          </button>
                        ))}
                      </Field>
                      <Field label="Storyline" htmlFor="lcfg-storyline" required
                        error={showProblems && !annual?.storyline ? 'Enter the Storyline for this academic year.' : undefined}>
                        <TextArea id="lcfg-storyline" rows={3}
                          value={annual?.storyline || ''}
                          placeholder="Write the storyline that frames this year"
                          onChange={(e) => setAnnualField('storyline', e.target.value)} />
                        {(annualOptions?.storylines || []).map((option) => (
                          <button key={option} type="button"
                            className="mt-1 text-left text-xs font-medium text-[#035f7c] underline"
                            onClick={() => setAnnualField('storyline', option)}>
                            Use approved wording
                          </button>
                        ))}
                      </Field>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button type="button" size="sm" onClick={() => { void saveAnnualValues() }}
                        data-save-wapef-annual>
                        Save &amp; lock for the year
                      </Button>
                      <Button type="button" size="sm" variant="outline"
                        onClick={() => {
                          setAnnualEditing(false)
                          setAnnualDirty(false)
                          // Reload the stored values so Cancel never leaves a
                          // half-typed edit on screen.
                          api.getWapefAnnual(schemeId).then(setAnnual).catch(() => {})
                        }}>
                        Cancel
                      </Button>
                    </div>
                  </>
                )}
                <p className="text-xs text-muted-foreground">
                  Throughline and God&apos;s Story are topic-level: choose them
                  for each lesson during review. AI may suggest those two, but
                  you keep the final choice.
                </p>
              </div>
            )}
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
                              <MultilineListField
                                id={`ref-${key}`}
                                rows={2}
                                placeholder="One reference per line"
                                value={draft.indicator_resources?.[key]?.references || []}
                                onChange={(entries) => setIndicatorValue(key, 'references', entries)}
                              />
                            </Field>
                            <Field label="Additional TLRs" htmlFor={`tlr-${key}`}>
                              <MultilineListField
                                id={`tlr-${key}`}
                                rows={2}
                                placeholder="One teacher-added resource per line"
                                value={draft.indicator_resources?.[key]?.tlrs || []}
                                onChange={(entries) => setIndicatorValue(key, 'tlrs', entries)}
                              />
                            </Field>
                            <fieldset className="space-y-1.5">
                              <legend className="text-xs font-medium text-[#102A43]">
                                Core competencies
                              </legend>
                              <p className="text-[11px] text-muted-foreground">
                                Select every approved competency this lesson genuinely develops.
                              </p>
                              <div className="flex flex-wrap gap-1.5">
                                {CORE_COMPETENCY_LABELS.map((label) => {
                                  const selected = competencyValue(key).includes(label)
                                  return (
                                    <button
                                      key={label}
                                      type="button"
                                      aria-pressed={selected}
                                      data-competency={label}
                                      onClick={() => setCompetencyValue(key, label)}
                                      className={`rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${
                                        selected
                                          ? 'border-[#102A43] bg-[#102A43] text-white'
                                          : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                                      }`}
                                    >
                                      {label}
                                    </button>
                                  )
                                })}
                              </div>
                            </fieldset>
                            {isWapefTemplate && wapefOptions && (
                              <div className="space-y-2 rounded-lg border border-[#04A9CE]/30 bg-[#04A9CE]/5 p-2.5">
                                <p className="text-xs font-semibold text-[#102A43]">
                                  WAPEF topic connection
                                </p>
                                <p className="text-[11px] text-muted-foreground">
                                  Deep Hope and Storyline come from the academic
                                  year above. Choose this lesson&apos;s Through
                                  lines and God&apos;s Story here.
                                </p>
                                <Field
                                  label="God's Story"
                                  htmlFor={`wapef-gods-story-${key}`}
                                  hint="A truthful Biblical connection for this indicator."
                                >
                                  <select
                                    id={`wapef-gods-story-${key}`}
                                    className="h-9 w-full rounded-md border border-input bg-white px-2 text-sm"
                                    value={indicatorWapefValue(key).gods_story || ''}
                                    onChange={(e) => setIndicatorWapef(key, { gods_story: e.target.value })}
                                  >
                                    <option value="">Not selected</option>
                                    {wapefOptions.gods_story.map((option) => (
                                      <option key={option} value={option}>{option}</option>
                                    ))}
                                  </select>
                                </Field>
                                <div>
                                  <p className="mb-1 text-xs font-medium text-[#102A43]">
                                    Through lines
                                  </p>
                                  <div className="flex flex-wrap gap-1.5">
                                    {wapefOptions.through_lines.map((option) => {
                                      const selected = (indicatorWapefValue(key).through_lines || []).includes(option)
                                      return (
                                        <button
                                          key={option}
                                          type="button"
                                          aria-pressed={selected}
                                          data-wapef-throughline={option}
                                          onClick={() => {
                                            const current = indicatorWapefValue(key).through_lines || []
                                            setIndicatorWapef(key, {
                                              through_lines: selected
                                                ? current.filter((item) => item !== option)
                                                : [...current, option],
                                            })
                                          }}
                                          className={`rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${
                                            selected
                                              ? 'border-[#102A43] bg-[#102A43] text-white'
                                              : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                                          }`}
                                        >
                                          {option}
                                        </button>
                                      )
                                    })}
                                  </div>
                                </div>
                              </div>
                            )}
                            <Field
                              label="Key words / New vocabulary"
                              htmlFor={`keywords-${key}`}
                              hint="Optional. Leave blank to use the lesson-specific suggestions."
                            >
                              <MultilineListField
                                id={`keywords-${key}`}
                                rows={2}
                                placeholder="One word or phrase per line (e.g. place value)"
                                value={draft.indicator_keywords?.[key] || []}
                                onChange={(entries) => setIndicatorKeywords(key, entries)}
                              />
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
          <div className="flex flex-col gap-1">
            <DraftSaveStatus status={draftStore.status} savedAt={draftStore.savedAt} />
            <span className="text-[11px] text-muted-foreground" role="status" aria-live="polite">
              {autoStatus === 'saving' && 'Saving your changes…'}
              {autoStatus === 'saved' && autoSavedAt
                && `All changes saved ${autoSavedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}.`}
              {autoStatus === 'error' && 'Autosave failed — changes are still on this screen.'}
              {autoStatus === 'idle' && dirty && 'Unsaved changes — autosave starts shortly.'}
            </span>
          </div>
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
