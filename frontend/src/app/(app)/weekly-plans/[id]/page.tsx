'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { FileDown, FileText, Save } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SurfaceCard } from '@/components/ui/surface-card'
import { Banner } from '@/components/ui/banner'
import { Field, TextArea } from '@/components/ui/field'
import { Select } from '@/components/ui/select'
import { PageHeader } from '@/components/ui/page-header'
import { DetailPageSkeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { DraftConflictBanner, DraftRecoveryBanner, DraftSaveStatus } from '@/components/ui/draft-recovery'
import { toast } from '@/components/ui/toaster'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { useFormDraft } from '@/hooks/use-form-draft'
import { normalizeError } from '@/lib/error-normalizer'
import { isStaleDraftBaseline } from '@/lib/drafts'
import { resolveRouteId } from '@/lib/route-params'
import type { WapefOptions, WeeklyClassPlan } from '@/types'

/** Local edits: WAPEF metadata per subject index + starter/reflection per day. */
interface MetadataPatch {
  wapef_deep_hope?: string
  wapef_storyline?: string
  wapef_through_lines?: string[]
  wapef_gods_story?: string
}

/**
 * Review, edit and export one saved Basic 1-3 weekly class plan.
 *
 * The review hierarchy mirrors the document: subject section -> metadata
 * (curriculum + the four approved WAPEF fields) -> one card per teaching day
 * (starter / main / reflection). Edits are keyed by subject index and day
 * index and sent at that granularity, so changing one subject's day never
 * touches another subject or another day (the server enforces the same
 * isolation on PUT).
 */
export default function WeeklyPlanDetailPage() {
  const params = useParams()
  const planId = resolveRouteId(params?.id as string | string[] | undefined, 'weekly-plans')

  const [plan, setPlan] = useState<WeeklyClassPlan | null>(null)
  const [serverVersion, setServerVersion] = useState<string | null>(null)
  const [serverConflict, setServerConflict] = useState(false)
  const [wapefOptions, setWapefOptions] = useState<WapefOptions | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const savingRef = useRef(false)
  const [exporting, setExporting] = useState<'docx' | 'pdf' | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)

  const [metaEdits, setMetaEdits] = useState<Record<number, MetadataPatch>>({})
  const [dayEdits, setDayEdits] = useState<Record<string, { starter?: string; reflection?: string }>>({})

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [planResponse, options] = await Promise.all([
          api.getWeeklyPlan(planId),
          api.getWapefOptions().catch(() => null),
        ])
        if (cancelled) return
        setPlan(planResponse.plan)
        setServerVersion(planResponse.version || planResponse.plan.updated_date || null)
        setServerConflict(false)
        setWapefOptions(options)
      } catch (err) {
        if (!cancelled) {
          setError(normalizeError(err).message)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [planId])

  const dirty = Object.keys(metaEdits).length > 0 || Object.keys(dayEdits).length > 0
  const { user } = useAuth()

  const planDraft = useFormDraft<{
    metaEdits: Record<number, MetadataPatch>
    dayEdits: Record<string, { starter?: string; reflection?: string }>
  }>({
    userId: user?.id || null,
    workflow: 'weekly-plan-edit',
    resourceId: planId,
    value: { metaEdits, dayEdits },
    enabled: dirty,
    baseline: serverVersion,
  })

  const draftBaselineChanged = Boolean(
    planDraft.recovered
      && isStaleDraftBaseline(planDraft.recovered.baseline, serverVersion),
  )

  const continuePlanDraft = () => {
    const recovered = planDraft.accept()
    if (!recovered) return
    if (draftBaselineChanged) setServerConflict(true)
    setMetaEdits(recovered.metaEdits || {})
    setDayEdits(recovered.dayEdits || {})
  }

  const reloadLatestPlan = async () => {
    planDraft.discard()
    setLoading(true)
    try {
      const [latest, options] = await Promise.all([
        api.getWeeklyPlan(planId),
        api.getWapefOptions().catch(() => null),
      ])
      setPlan(latest.plan)
      setServerVersion(latest.version || latest.plan.updated_date || null)
      setServerConflict(false)
      setMetaEdits({})
      setDayEdits({})
      setWapefOptions(options)
      setError(null)
    } catch (err) {
      setError(normalizeError(err).message)
    } finally {
      setLoading(false)
    }
  }

  const dayEditKey = (subjectIndex: number, dayIndex: number) =>
    `${subjectIndex}:${dayIndex}`

  const patchMetadata = (subjectIndex: number, patch: MetadataPatch) => {
    setMetaEdits((prev) => ({
      ...prev,
      [subjectIndex]: { ...prev[subjectIndex], ...patch },
    }))
  }

  const patchDay = (subjectIndex: number, dayIndex: number,
                    patch: { starter?: string; reflection?: string }) => {
    const key = dayEditKey(subjectIndex, dayIndex)
    setDayEdits((prev) => ({ ...prev, [key]: { ...prev[key], ...patch } }))
  }

  const handleSave = async (forceOverwrite = false) => {
    if (!plan || savingRef.current) return
    savingRef.current = true
    setSaving(true)
    setError(null)
    toast({
      title: 'Saving weekly plan changes…',
      variant: 'info',
      duration: 3000,
      key: `weekly-plan-edit-saving:${planId}`,
    })
    try {
      const latest = await api.getWeeklyPlan(planId)
      const latestVersion = latest.version || latest.plan.updated_date || null
      if (!forceOverwrite && latestVersion !== serverVersion) {
        setServerConflict(true)
        setError(
          'This weekly plan changed on the server since you opened it. ' +
          'Load the latest version, or confirm an overwrite of the latest version.',
        )
        return
      }
      const writeVersion = forceOverwrite ? latestVersion : serverVersion
      const subjectIndexes = new Set<number>([
        ...Object.keys(metaEdits).map(Number),
        ...Object.keys(dayEdits).map((key) => Number(key.split(':')[0])),
      ])
      const subjects = Array.from(subjectIndexes).sort((a, b) => a - b).map((index) => {
        const dayKeys = Object.keys(dayEdits)
          .filter((key) => key.startsWith(`${index}:`))
          .sort((a, b) => Number(a.split(':')[1]) - Number(b.split(':')[1]))
        return {
          index,
          ...(metaEdits[index] ? { metadata: metaEdits[index] } : {}),
          day_plans: dayKeys.map((key) => ({
            index: Number(key.split(':')[1]),
            ...(dayEdits[key].starter !== undefined ? { starter: dayEdits[key].starter } : {}),
            ...(dayEdits[key].reflection !== undefined ? { reflection: dayEdits[key].reflection } : {}),
          })),
        }
      })
      const response = await api.updateWeeklyPlan(
        planId, { subjects }, writeVersion || undefined)
      setPlan(response.plan)
      setServerVersion(response.version || response.plan.updated_date || null)
      setServerConflict(false)
      setMetaEdits({})
      setDayEdits({})
      planDraft.clear()
      toast({ title: 'Changes saved', description: 'Only the edited subject/day changed.' })
    } catch (err) {
      const normalized = normalizeError(err)
      setError(normalized.message)
      if (normalized.category === 'conflict') {
        setServerConflict(true)
        return
      }
      savingRef.current = false
      setSaving(false)
      toast({
        title: 'Weekly plan was not saved',
        description: normalized.message,
        variant: 'error',
        key: `weekly-plan-edit-error:${planId}`,
        action: { label: 'Try again', onClick: () => { void handleSave() } },
      })
    } finally {
      savingRef.current = false
      setSaving(false)
    }
  }

  const handleExport = async (format: 'docx' | 'pdf') => {
    setExporting(format)
    setExportError(null)
    try {
      const payload = format === 'docx'
        ? await api.exportWeeklyDocx(planId)
        : await api.exportWeeklyPdf(planId)
      await api.downloadFile(payload.blob, payload.filename || `Weekly_Plan.${format}`)
      toast({ title: `Exported ${format.toUpperCase()}`, description: 'One weekly document with every subject section.' })
    } catch (err) {
      setExportError(normalizeError(err).message)
    } finally {
      setExporting(null)
    }
  }

  const displayDays = (subjectIndex: number, dayIndex: number, field: 'starter' | 'reflection') => {
    const edit = dayEdits[dayEditKey(subjectIndex, dayIndex)]
    if (edit && edit[field] !== undefined) return edit[field]!
    const day = plan?.subjects[subjectIndex]?.day_plans[dayIndex]
    return field === 'starter' ? (day?.starter ?? '') : (day?.reflection ?? '')
  }

  const wapefValue = (subjectIndex: number, field: keyof MetadataPatch) =>
    metaEdits[subjectIndex]?.[field] ?? plan?.subjects[subjectIndex]?.metadata[field] ?? ''

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8" data-weekly-loading>
        <DetailPageSkeleton label="Loading weekly plan" />
      </div>
    )
  }

  if (!plan) {
    return (
      <div className="space-y-6">
        <PageHeader eyebrow="Weekly Plan" title="Weekly plan not found" />
        <SurfaceCard className="p-8 text-center" data-empty>
          <p className="text-sm text-muted-foreground">
            {error || 'This weekly plan does not exist or is not yours.'}
          </p>
          <Button asChild className="mt-4">
            <Link href="/weekly-plans">Back to weekly plans</Link>
          </Button>
        </SurfaceCard>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Weekly Plan"
        title={`${plan.class_level} · Week ${plan.week_number} · ${plan.term}`}
        description={[
          plan.school_name,
          plan.teacher_name,
          plan.academic_year,
        ].filter(Boolean).join(' · ')}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" asChild>
              <Link href="/weekly-plans">All weekly plans</Link>
            </Button>
            <Button
              variant="outline"
              onClick={() => handleExport('docx')}
              disabled={exporting !== null}
              data-weekly-export-docx
            >
              <FileDown className="h-4 w-4" aria-hidden="true" />
              {exporting === 'docx' ? 'Exporting…' : 'Export DOCX'}
            </Button>
            <Button
              variant="outline"
              onClick={() => handleExport('pdf')}
              disabled={exporting !== null}
              data-weekly-export-pdf
            >
              <FileText className="h-4 w-4" aria-hidden="true" />
              {exporting === 'pdf' ? 'Exporting…' : 'Export PDF'}
            </Button>
          </div>
        }
      />

      {planDraft.recovered && (
        draftBaselineChanged ? (
          <DraftConflictBanner
            updatedAt={planDraft.recovered.updatedAt}
            onLoadLatest={() => { void reloadLatestPlan() }}
            onKeepDraft={continuePlanDraft}
            onReview={() => setError(
              'Your edits were based on an older weekly-plan version. Keeping ' +
              'them will replace the latest saved version only after you press Save.',
            )}
          />
        ) : (
          <DraftRecoveryBanner
            updatedAt={planDraft.recovered.updatedAt}
            label="Unsaved edits to this weekly plan"
            onContinue={continuePlanDraft}
            onDiscard={planDraft.discard}
          />
        )
      )}

      {serverConflict && !planDraft.recovered && (
        <Banner
          tone="danger"
          title="This weekly plan changed on the server"
          action={
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={() => { void reloadLatestPlan() }}>
                Load latest version
              </Button>
              <Button size="sm" onClick={() => { void handleSave(true) }}>
                Overwrite latest with my draft
              </Button>
            </div>
          }
        >
          Your edits are still here. Load the latest version, or explicitly
          overwrite it. A second server update will still be rejected.
        </Banner>
      )}

      {error && <Banner tone="danger" title="Could not save">{error}</Banner>}
      {exportError && (
        <Banner tone="danger" title="Export failed" data-weekly-export-error>
          {exportError}
        </Banner>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {plan.subjects.map((subject, subjectIndex) => {
            const meta = subject.metadata
            const metadataRows: { label: string; value: string; always?: boolean }[] = [
              { label: 'Class', value: meta.class_level, always: true },
              { label: 'Week Ending', value: meta.week_ending ? String(meta.week_ending).slice(0, 10) : '', always: true },
              { label: 'Reference', value: meta.reference },
              { label: 'Strand', value: meta.strand },
              { label: 'Sub strand', value: meta.sub_strand },
              { label: 'Content Standard', value: (meta.content_standards || []).join(' ') },
              { label: 'Learning Indicator(s)', value: (meta.indicators || []).join(' ') },
              { label: 'Performance Indicator', value: (meta.performance_indicators || []).join(' ') },
              { label: 'Teaching/ Learning Resources', value: (meta.teaching_learning_resources || []).join(', ') },
              { label: 'Core Competencies', value: (meta.core_competencies || []).join(', ') },
              { label: 'Key words', value: (meta.keywords || []).join(', ') },
            ]
            return (
              <SurfaceCard
                key={subject.scheme_of_work_id}
                className="p-6"
                data-weekly-subject={subjectIndex}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className="text-lg font-semibold text-[#102A43]">{subject.subject}</h2>
                  <div className="flex flex-wrap gap-1">
                    {subject.teaching_day_groups.map((group) => (
                      <Badge key={group.join('&')} variant="secondary">{group.join(' & ')}</Badge>
                    ))}
                  </div>
                </div>

                <dl className="mt-4 grid gap-x-4 gap-y-2 sm:grid-cols-2" data-weekly-metadata>
                  {metadataRows
                    .filter((row) => row.always || row.value)
                    .map((row) => (
                      <div key={row.label} className="min-w-0">
                        <dt className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                          {row.label}
                        </dt>
                        <dd className="truncate text-sm" title={row.value}>{row.value || '—'}</dd>
                      </div>
                    ))}
                </dl>

                {wapefOptions && (
                  <div className="mt-4 rounded-md border bg-background p-3" data-weekly-wapef>
                    <p className="mb-2 text-[11px] font-semibold text-[#102A43]">
                      Approved WAPEF fields
                      <span className="ml-1 font-normal text-muted-foreground">
                        (teacher-selected — leave blank if the plan has none)
                      </span>
                    </p>
                    <div className="grid gap-2.5 sm:grid-cols-2">
                      <Field label="Deep Hope" htmlFor={`weekly-deep-hope-${subjectIndex}`}>
                        <Select
                          id={`weekly-deep-hope-${subjectIndex}`}
                          value={String(wapefValue(subjectIndex, 'wapef_deep_hope') ?? '')}
                          onChange={(e) => patchMetadata(subjectIndex, { wapef_deep_hope: e.target.value })}
                        >
                          <option value="">— Select —</option>
                          {wapefOptions.deep_hopes.map((option) => (
                            <option key={option} value={option}>{option}</option>
                          ))}
                        </Select>
                      </Field>
                      <Field label="Storyline" htmlFor={`weekly-storyline-${subjectIndex}`}>
                        <Select
                          id={`weekly-storyline-${subjectIndex}`}
                          value={String(wapefValue(subjectIndex, 'wapef_storyline') ?? '')}
                          onChange={(e) => patchMetadata(subjectIndex, { wapef_storyline: e.target.value })}
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
                          const current = (wapefValue(subjectIndex, 'wapef_through_lines') as string[]) || []
                          const active = current.includes(option)
                          return (
                            <button
                              key={option}
                              type="button"
                              onClick={() => {
                                const next = active
                                  ? current.filter((t) => t !== option)
                                  : [...current, option]
                                patchMetadata(subjectIndex, { wapef_through_lines: next })
                              }}
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
                      <Field label="God's Story" htmlFor={`weekly-gods-story-${subjectIndex}`}>
                        <Select
                          id={`weekly-gods-story-${subjectIndex}`}
                          value={String(wapefValue(subjectIndex, 'wapef_gods_story') ?? '')}
                          onChange={(e) => patchMetadata(subjectIndex, { wapef_gods_story: e.target.value })}
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

                <div className="mt-4 space-y-3">
                  <h3 className="text-sm font-semibold text-[#102A43]">Teaching days</h3>
                  {subject.day_plans.map((day, dayIndex) => (
                    <div
                      key={`${day.day_label}-${dayIndex}`}
                      className="rounded-md border p-3"
                      data-weekly-day={dayIndex}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-sm font-semibold">{day.day_label}</p>
                        {(day.focus_indicators || []).length > 0 && (
                          <p className="text-xs text-muted-foreground">
                            Focus: {day.focus_indicators.join('; ')}
                          </p>
                        )}
                      </div>
                      <div className="mt-2 grid gap-3">
                        <Field
                          label="Phase 1: Starter"
                          htmlFor={`weekly-starter-${subjectIndex}-${dayIndex}`}
                        >
                          <TextArea
                            id={`weekly-starter-${subjectIndex}-${dayIndex}`}
                            rows={2}
                            value={displayDays(subjectIndex, dayIndex, 'starter')}
                            onChange={(e) => patchDay(subjectIndex, dayIndex, { starter: e.target.value })}
                          />
                        </Field>
                        <div>
                          <p className="mb-1 text-sm font-medium">Phase 2: Main</p>
                          <ol className="list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
                            {(day.main_activities || []).map((activity, activityIndex) => (
                              <li key={activityIndex}>{activity.description || ''}</li>
                            ))}
                          </ol>
                        </div>
                        <Field
                          label="Phase 3: Reflection"
                          htmlFor={`weekly-reflection-${subjectIndex}-${dayIndex}`}
                        >
                          <TextArea
                            id={`weekly-reflection-${subjectIndex}-${dayIndex}`}
                            rows={2}
                            value={displayDays(subjectIndex, dayIndex, 'reflection')}
                            onChange={(e) => patchDay(subjectIndex, dayIndex, { reflection: e.target.value })}
                          />
                        </Field>
                      </div>
                    </div>
                  ))}
                </div>
              </SurfaceCard>
            )
          })}
        </div>

        <div className="lg:col-span-1 lg:sticky lg:top-20 lg:self-start">
          <SurfaceCard data-weekly-action className="p-6 space-y-4">
            <div>
              <h2 className="text-base font-semibold text-[#102A43]">Review and export</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {plan.subjects.length} subject section(s){' '}
                {dirty ? '· unsaved changes' : '· all changes saved'}
              </p>
            </div>
            <Button
              className="w-full"
              onClick={() => { void handleSave() }}
              disabled={!dirty || saving}
              data-weekly-save
            >
              <Save className="h-4 w-4" aria-hidden="true" />
              {saving ? 'Saving…' : 'Save changes'}
            </Button>
            <DraftSaveStatus status={planDraft.status} savedAt={planDraft.savedAt} />
            <Button
              className="w-full"
              variant="outline"
              onClick={() => handleExport('docx')}
              disabled={exporting !== null}
              data-weekly-export-docx
            >
              <FileDown className="h-4 w-4" aria-hidden="true" />
              {exporting === 'docx' ? 'Exporting…' : 'Export DOCX'}
            </Button>
            <Button
              className="w-full"
              variant="outline"
              onClick={() => handleExport('pdf')}
              disabled={exporting !== null}
              data-weekly-export-pdf
            >
              <FileText className="h-4 w-4" aria-hidden="true" />
              {exporting === 'pdf' ? 'Exporting…' : 'Export PDF'}
            </Button>
            <p className="text-xs text-muted-foreground">
              DOCX and PDF come from the same canonical weekly document — one
              file holding every subject section.
            </p>
          </SurfaceCard>
        </div>
      </div>
    </div>
  )
}
