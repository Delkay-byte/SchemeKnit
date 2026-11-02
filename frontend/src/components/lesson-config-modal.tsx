'use client'

/**
 * Guided lesson configuration modal (Phases 2/3).
 *
 * ONE entry point into the seven plan-wide lesson fields — school name,
 * teacher's name, class size, reference, lesson duration, periods and the
 * days the subject is taught. Used by the review page (before generation is
 * even available) and the generate page (one "Configure lesson rubrics"
 * button opens it; the review page never duplicates the form).
 *
 * Save/Apply persists to the scheme (per-plan scope, never global settings);
 * Cancel keeps the last saved configuration. Unsaved changes are not
 * silently dismissed — the first Cancel arms the discard, a second confirms.
 */

import { useEffect, useMemo, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Field } from '@/components/ui/field'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { DraftRecoveryBanner, DraftSaveStatus } from '@/components/ui/draft-recovery'
import { toast } from '@/components/ui/toaster'
import { Loader2, Save } from 'lucide-react'
import { api } from '@/lib/api'
import { normalizeError } from '@/lib/error-normalizer'
import { useAuth } from '@/lib/auth-context'
import { useFormDraft } from '@/hooks/use-form-draft'
import { prefillLessonConfig } from '@/lib/prefill'
import {
  readClearedFields,
  setFieldCleared,
} from '@/lib/prefill-overrides'
import { LessonRubricConfig } from '@/types'

const WEEK_DAYS = [
  { value: 0, label: 'Monday' },
  { value: 1, label: 'Tuesday' },
  { value: 2, label: 'Wednesday' },
  { value: 3, label: 'Thursday' },
  { value: 4, label: 'Friday' },
]

export interface LessonConfigModalProps {
  schemeId: string
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Last saved configuration; the modal drafts from a copy of it. */
  config: LessonRubricConfig
  /** Called after a successful save with the server-normalized values. */
  onSaved: (config: LessonRubricConfig, missing: string[]) => void
}

export function LessonConfigModal({
  schemeId, open, onOpenChange, config, onSaved,
}: LessonConfigModalProps) {
  const { user } = useAuth()
  const [draft, setDraft] = useState<LessonRubricConfig>(config)
  const [baseline, setBaseline] = useState<LessonRubricConfig>(config)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [discardArmed, setDiscardArmed] = useState(false)

  // Authoritative defaults from the signed-in profile. They only fill fields
  // that are still blank; server-saved per-scheme values always win.
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

  // Re-draft from the saved values each time the modal opens. Recovery is
  // offered separately so an old local copy never silently replaces saved data.
  useEffect(() => {
    if (open) {
      const cleared = overrideIdentity
        ? readClearedFields(overrideIdentity)
        : new Set<string>()
      setClearedFields(Array.from(cleared))
      const next = prefillLessonConfig(config, user, cleared)
      setDraft(next)
      setBaseline(next)
      setError(null)
      setDiscardArmed(false)
    }
    // Only opening a modal starts a fresh draft; parent re-renders must not
    // discard what the teacher is typing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

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
      const value = (saved[field] || '').trim()
      setFieldCleared(overrideIdentity, field, !value)
    }
    setClearedFields(Array.from(readClearedFields(overrideIdentity)))
  }

  const handleSave = async () => {
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
        school_name: draft.school_name?.trim() || null,
        teacher_name: draft.teacher_name?.trim() || null,
        class_size: draft.class_size ?? null,
        reference: draft.reference?.trim() || null,
        lesson_duration_minutes: draft.lesson_duration_minutes ?? null,
        periods_per_week: draft.periods_per_week ?? null,
        period: draft.period?.trim() || null,
        teaching_days: (draft.teaching_days || []).length
          ? [...(draft.teaching_days || [])].sort((a, b) => a - b)
          : null,
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
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg" data-lesson-config-modal>
        <DialogHeader>
          <DialogTitle>Configure lesson rubrics</DialogTitle>
          <DialogDescription>
            These details appear on every lesson plan for this scheme — school,
            teacher, class, duration and the days you teach. They are saved for
            this plan only.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          {draftStore.recovered && (
            <DraftRecoveryBanner
              updatedAt={draftStore.recovered.updatedAt}
              label={`Unsaved lesson settings for this scheme`}
              onContinue={applyRecovered}
              onDiscard={discardRecovered}
            />
          )}
          <Field label="School name" htmlFor="lcfg-school" hint="Shown at the top of the first week">
            <Input
              id="lcfg-school"
              type="text"
              autoComplete="organization"
              value={draft.school_name || ''}
              onChange={(e) => setDraft({ ...draft, school_name: e.target.value })}
            />
            {!draft.school_name && clearedFields.includes('school_name') && (user?.school_name || '').trim() && (
              <button
                type="button"
                onClick={() => restoreProfileDefault('school_name')}
                className="text-xs font-semibold text-[#04769B] hover:underline"
              >
                Use my school from profile
              </button>
            )}
          </Field>
          <Field label="Teacher's name" htmlFor="lcfg-teacher" hint="Shown under the school name">
            <Input
              id="lcfg-teacher"
              type="text"
              autoComplete="name"
              value={draft.teacher_name || ''}
              onChange={(e) => setDraft({ ...draft, teacher_name: e.target.value })}
            />
            {!draft.teacher_name && clearedFields.includes('teacher_name') && (user?.full_name || '').trim() && (
              <button
                type="button"
                onClick={() => restoreProfileDefault('teacher_name')}
                className="text-xs font-semibold text-[#04769B] hover:underline"
              >
                Use my name from profile
              </button>
            )}
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Class size" htmlFor="lcfg-class-size">
              <Input
                id="lcfg-class-size"
                type="number"
                min={1}
                max={500}
                value={draft.class_size ?? ''}
                onChange={(e) => {
                  const v = parseInt(e.target.value, 10)
                  setDraft({ ...draft, class_size: Number.isFinite(v) && v > 0 ? v : null })
                }}
              />
            </Field>
            <Field label="Lesson duration (minutes)" htmlFor="lcfg-duration">
              <Input
                id="lcfg-duration"
                type="number"
                min={20}
                max={240}
                value={draft.lesson_duration_minutes ?? ''}
                onChange={(e) => {
                  const v = parseInt(e.target.value, 10)
                  setDraft({ ...draft, lesson_duration_minutes: Number.isFinite(v) && v >= 20 ? v : null })
                }}
              />
            </Field>
          </div>
          <Field label="Reference" htmlFor="lcfg-reference" hint="Textbook, curriculum document or teacher's guide (optional)">
            <Input
              id="lcfg-reference"
              type="text"
              value={draft.reference || ''}
              onChange={(e) => setDraft({ ...draft, reference: e.target.value })}
            />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Periods per week" htmlFor="lcfg-periods" hint="How many periods this subject gets each week">
              <Input
                id="lcfg-periods"
                type="number"
                min={1}
                max={15}
                value={draft.periods_per_week ?? ''}
                onChange={(e) => {
                  const v = parseInt(e.target.value, 10)
                  setDraft({ ...draft, periods_per_week: Number.isFinite(v) && v > 0 ? v : null })
                }}
              />
            </Field>
            <Field label="Period / timing" htmlFor="lcfg-period" hint='e.g. "1st & 2nd" (optional)'>
              <Input
                id="lcfg-period"
                type="text"
                value={draft.period || ''}
                onChange={(e) => setDraft({ ...draft, period: e.target.value })}
              />
            </Field>
          </div>
          <div>
            <p className="mb-2 text-sm font-medium">Days the subject is taught</p>
            <div className="flex flex-wrap gap-2">
              {WEEK_DAYS.map((day) => {
                const selected = (draft.teaching_days || []).includes(day.value)
                return (
                  <button
                    key={day.value}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => {
                      const current = draft.teaching_days || []
                      const next = selected
                        ? current.filter((d) => d !== day.value)
                        : [...current, day.value].sort((a, b) => a - b)
                      setDraft({ ...draft, teaching_days: next })
                    }}
                    className={`rounded-full px-3 py-1 text-sm ${
                      selected ? 'bg-[#102A43] text-white' : 'bg-muted text-muted-foreground'
                    }`}
                  >
                    {day.label}
                  </button>
                )
              })}
            </div>
          </div>
          {discardArmed && dirty && (
            <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900" role="alert">
              You have unsaved changes. Click Cancel again to discard them, or Save &amp; apply to keep them.
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
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
              Cancel
            </Button>
            <Button type="button" disabled={saving} onClick={handleSave} data-save-lesson-config>
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="mr-2 h-4 w-4" aria-hidden="true" />}
              Save &amp; apply
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
