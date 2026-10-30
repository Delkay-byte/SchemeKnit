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

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Field } from '@/components/ui/field'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Loader2, Save } from 'lucide-react'
import { api } from '@/lib/api'
import { normalizeError } from '@/lib/error-normalizer'
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
  const [draft, setDraft] = useState<LessonRubricConfig>(config)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [discardArmed, setDiscardArmed] = useState(false)

  // Re-draft from the saved values each time the modal opens.
  useEffect(() => {
    if (open) {
      setDraft({ ...config })
      setError(null)
      setDiscardArmed(false)
    }
  }, [open, config])

  const dirty = JSON.stringify(draft) !== JSON.stringify(config)

  const handleOpenChange = (next: boolean) => {
    if (!next && dirty) {
      if (discardArmed) {
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

  const handleSave = async () => {
    setSaving(true)
    setError(null)
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
      onSaved(resp.config || draft, resp.missing || [])
      onOpenChange(false)
    } catch (err) {
      setError(normalizeError(err).message)
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
          <Field label="School name" htmlFor="lcfg-school" hint="Shown at the top of the first week">
            <Input
              id="lcfg-school"
              type="text"
              value={draft.school_name || ''}
              onChange={(e) => setDraft({ ...draft, school_name: e.target.value })}
            />
          </Field>
          <Field label="Teacher's name" htmlFor="lcfg-teacher" hint="Shown under the school name">
            <Input
              id="lcfg-teacher"
              type="text"
              value={draft.teacher_name || ''}
              onChange={(e) => setDraft({ ...draft, teacher_name: e.target.value })}
            />
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

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" disabled={saving} onClick={handleSave} data-save-lesson-config>
            {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="mr-2 h-4 w-4" aria-hidden="true" />}
            Save &amp; apply
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
