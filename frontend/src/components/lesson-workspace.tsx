'use client'

import { useCallback, useEffect, useState } from 'react'
import { CheckCircle, Loader2, Plus, RefreshCw, Save, Sparkles, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { SurfaceCard } from '@/components/ui/surface-card'
import { Banner } from '@/components/ui/banner'
import { TextArea } from '@/components/ui/field'
import { SourceAlignment, type LessonProvenance } from '@/components/source-alignment'
import { api } from '@/lib/api'
import { aiFailure } from '@/lib/ai-feedback'

/** Canonical Phase 2 activity (never flattened to raw JSON). */
export interface MainActivity {
  phase?: string
  description: string
  duration_minutes: number | null
  resources?: string[]
}

function normalizeActivities(raw: unknown): MainActivity[] {
  if (!Array.isArray(raw)) return []
  const out: MainActivity[] = []
  for (const a of raw) {
    if (a && typeof a === 'object') {
      const description = String((a as any).description || '').trim()
      if (!description) continue
      const rawDur = (a as any).duration_minutes
      const n = typeof rawDur === 'number' ? rawDur : parseInt(String(rawDur ?? ''), 10)
      out.push({
        phase: (a as any).phase,
        description,
        duration_minutes: Number.isFinite(n) && n > 0 ? n : null,
        resources: Array.isArray((a as any).resources) ? (a as any).resources : [],
      })
    } else if (typeof a === 'string' && a.trim()) {
      out.push({ description: a.trim(), duration_minutes: null, resources: [] })
    }
  }
  return out
}

interface LessonData {
  id: string
  scheme_id: string
  week_number: number
  source_week?: number
  teaching_week?: number
  period?: string
  special_period_label?: string
  special_period_type?: string
  class_level: string
  subject: string
  strand: string | null
  sub_strand: string | null
  content_standard: string | null
  indicator_codes?: string[]
  indicators?: string[] | null
  lesson_topic: string | null
  introduction: string | null
  assessment: string | null
  conclusion: string | null
  lesson_date?: string | null
  learning_objectives?: { description: string }[]
  main_activities?: { description: string; duration_minutes?: number; resources?: string[] }[]
  keywords?: string[]
  source_tlrs?: string[]
  other_tlrs?: string[]
  core_competencies?: string[]
  structured_references?: { type: string; title: string; page?: string }[]
  references?: string[]
  wapef_deep_hope?: string
  wapef_storyline?: string
  wapef_through_lines?: string[]
  wapef_gods_story?: string
  status?: string
  teacher_edited?: boolean
  ai_generated?: boolean
  provenance?: LessonProvenance
}

interface Draft {
  topic: string
  introduction: string
  assessment: string
  conclusion: string
  mainActivities: MainActivity[]
}

function draftFrom(l: LessonData): Draft {
  return {
    topic: l.lesson_topic || '',
    introduction: l.introduction || '',
    assessment: l.assessment || '',
    conclusion: l.conclusion || '',
    mainActivities: normalizeActivities(l.main_activities),
  }
}

const DAY_LABELS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

function teachingDayLabel(lesson: LessonData): string {
  if (!lesson.lesson_date) return ''
  const d = new Date(lesson.lesson_date)
  if (isNaN(d.getTime())) return ''
  return DAY_LABELS[d.getDay()] || ''
}

export interface LessonWorkspaceProps {
  jobId: string
  /** Build-with-me mode: reveal one section at a time with accept/skip. */
  guided?: boolean
  onExport: (format: string) => void
  exporting: string | null
  onLessonsLoaded?: (count: number) => void
}

const GUIDED_STEPS = ['objectives', 'starter', 'main', 'assessment', 'reflection'] as const
type GuidedStep = typeof GUIDED_STEPS[number]

/**
 * The curriculum-grounded lesson workspace.
 *
 * Answers four questions at once: what curriculum am I teaching, where this
 * lesson came from, what SchemeKnit generated, and what can I change before I
 * approve it. The real lesson is shown first — never an empty editor.
 */
export function LessonWorkspace({
  jobId,
  guided = false,
  onExport,
  exporting,
  onLessonsLoaded,
}: LessonWorkspaceProps) {
  const [lessons, setLessons] = useState<LessonData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  // Unsaved edits are a real workspace state, not a silent one.
  const [dirty, setDirty] = useState(false)
  const [suggesting, setSuggesting] = useState<string | null>(null)
  const [aiNotice, setAiNotice] = useState<string | null>(null)
  const [guidedStep, setGuidedStep] = useState<GuidedStep>('objectives')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getGeneratedLessons(jobId)
      const list: LessonData[] = data.lesson_plans || []
      setLessons(list)
      onLessonsLoaded?.(list.length)
      const first = list[0]
      if (first) {
        setActiveId(first.id)
        setDraft(draftFrom(first))
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'We could not load the generated lesson.')
    } finally {
      setLoading(false)
    }
  }, [jobId, onLessonsLoaded])

  useEffect(() => { load() }, [load])

  const active = lessons.find((l) => l.id === activeId) || null

  const selectLesson = (l: LessonData) => {
    setActiveId(l.id)
    setDraft(draftFrom(l))
    setSaved(false)
    setDirty(false)
    setAiNotice(null)
    setGuidedStep('objectives')
  }

  const updateDraft = (patch: Partial<Draft>) => {
    setDraft((d) => (d ? { ...d, ...patch } : d))
    setSaved(false)
    setDirty(true)
  }

  const handleSave = async () => {
    if (!active || !draft) return
    setSaving(true)
    setError(null)
    try {
      const updated = await api.updateLesson(active.id, {
        lesson_topic: draft.topic,
        introduction: draft.introduction,
        assessment: draft.assessment,
        conclusion: draft.conclusion,
        main_activities: draft.mainActivities.map((a) => ({
          phase: a.phase || 'main_learning',
          description: a.description,
          duration_minutes: a.duration_minutes || 0,
          resources: a.resources || [],
        })),
      })
      setLessons((ls) => ls.map((l) => (l.id === active.id ? { ...l, ...updated } : l)))
      setSaved(true)
      setDirty(false)
      setTimeout(() => setSaved(false), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'We could not save your changes.')
    } finally {
      setSaving(false)
    }
  }

  // Build with me (Pattern 7): a per-section AI suggestion that NEVER blanks
  // existing content on failure (teacher-safe copy via aiFailure).
  const suggest = async (
    section: 'introduction' | 'main_activities' | 'assessment' | 'conclusion',
  ) => {
    if (!active || !draft) return
    setSuggesting(section)
    setAiNotice(null)
    try {
      let mode = 'BASIC'
      try {
        const savedMode = window.localStorage.getItem('schemeknit.ai_mode')
        if (savedMode && savedMode !== 'OFF') mode = savedMode
      } catch { /* storage unavailable */ }
      const requestId = `${active.id}:${section}:${Date.now()}`
      const res = await api.regenerateSection(active.id, section, mode, '', requestId)
      if (section === 'main_activities') {
        const next = normalizeActivities(res.new_activities)
        if (next.length === 0) {
          setAiNotice(aiFailure({ code: 'AI_NO_SUGGESTION' }).message)
          return
        }
        updateDraft({ mainActivities: next })
      } else {
        const text = res.new_content || ''
        if (section === 'introduction') updateDraft({ introduction: text })
        if (section === 'assessment') updateDraft({ assessment: text })
        if (section === 'conclusion') updateDraft({ conclusion: text })
      }
      setAiNotice(
        `AI suggestion${res.provider ? ` from ${res.provider}` : ''} inserted. ` +
        'Review it and Save to keep it.',
      )
    } catch (err) {
      setAiNotice(aiFailure(err).message)
    } finally {
      setSuggesting(null)
    }
  }

  const updateActivity = (index: number, patch: Partial<MainActivity>) => {
    if (!draft) return
    const next = draft.mainActivities.map((a, i) => (i === index ? { ...a, ...patch } : a))
    updateDraft({ mainActivities: next })
  }

  if (loading) {
    return (
      <SurfaceCard data-lesson-workspace className="px-5 py-10 text-center sm:px-6">
        <Loader2 className="mx-auto mb-3 h-8 w-8 animate-spin text-[#04769B]" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">Loading your generated lesson…</p>
      </SurfaceCard>
    )
  }

  if (error && lessons.length === 0) {
    return (
      <SurfaceCard data-lesson-workspace className="px-5 py-8 text-center sm:px-6">
        <Banner tone="danger" title="We could not load the lesson" className="text-left">
          {error}
        </Banner>
        <Button className="mt-4" onClick={load}>
          <RefreshCw className="mr-2 h-4 w-4" /> Try again
        </Button>
      </SurfaceCard>
    )
  }

  if (!active || !draft) {
    return (
      <SurfaceCard data-lesson-workspace className="px-5 py-8 text-center sm:px-6">
        <p className="text-sm text-muted-foreground">
          No lesson plans were produced for this scheme.
        </p>
      </SurfaceCard>
    )
  }

  const isSpecial = Boolean(active.special_period_label || active.special_period_type)
  const objectives = active.learning_objectives || []
  const resources = [...(active.source_tlrs || []), ...(active.other_tlrs || [])]

  // Guided mode shows one section at a time (accept / suggest / skip).
  const stepVisible = (step: GuidedStep) => !guided || guidedStep === step
  const stepIndex = GUIDED_STEPS.indexOf(guidedStep)
  const advance = () => {
    if (stepIndex < GUIDED_STEPS.length - 1) setGuidedStep(GUIDED_STEPS[stepIndex + 1])
  }

  return (
    <div data-lesson-workspace className="space-y-4">
      {/* Lesson selector — one chip per generated lesson. */}
      {lessons.length > 1 && (
        <div className="flex flex-wrap gap-2" role="tablist" aria-label="Generated lessons">
          {lessons.map((l) => {
            const selected = l.id === active.id
            return (
              <button
                key={l.id}
                role="tab"
                aria-selected={selected}
                onClick={() => selectLesson(l)}
                className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                  selected
                    ? 'border-[#102A43] bg-[#102A43] text-white'
                    : 'border-slate-200 bg-white text-[#102A43] hover:bg-slate-50'
                }`}
              >
                Week {l.teaching_week || l.week_number}
                {l.period ? ` · ${l.period}` : ''}
              </button>
            )
          })}
        </div>
      )}

      <SurfaceCard data-lesson-context className="px-5 py-5 sm:px-6">
        {/* SECTION 1 — CONTEXT */}
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <ContextItem label="Subject" value={active.subject} />
          <ContextItem label="Class" value={active.class_level} />
          <ContextItem label="Week" value={String(active.teaching_week || active.week_number)} />
          {teachingDayLabel(active) && (
            <ContextItem label="Teaching day" value={teachingDayLabel(active)} />
          )}
          {active.period && <ContextItem label="Period" value={active.period} />}
        </div>

        <SourceAlignment
          className="mt-4"
          title="Source & alignment"
          provenance={active.provenance}
        />

        {/* Real workspace states: the source week genuinely needed review, so
            the teacher is told — calmly, and without inventing content. */}
        {active.provenance?.source_review_status === 'needs_review' && (
          <Banner tone="warning" title="This week needs review" className="mt-3">
            SchemeKnit could not fully read this week of your scheme. Generate and
            edit as normal — nothing has been guessed or filled in for you.
          </Banner>
        )}

        {(saved || error || aiNotice) && (
          <div className="mt-4 space-y-2">
            {saved && (
              <Banner tone="success" title="Saved">
                Your edits are stored with this lesson.
              </Banner>
            )}
            {error && lessons.length > 0 && (
              <Banner tone="danger" title="Action failed">{error}</Banner>
            )}
            {aiNotice && <Banner tone="info">{aiNotice}</Banner>}
          </div>
        )}
      </SurfaceCard>

      {/* Special periods are NOT lessons: show the banner, no lesson fields. */}
      {isSpecial ? (
        <SurfaceCard className="px-5 py-5 sm:px-6">
          <Banner tone="info" title={`Special period: ${active.special_period_label || 'Mid-Term'}`}>
            This period does not contain a normal lesson, so there is nothing to edit.
          </Banner>
        </SurfaceCard>
      ) : (
        <SurfaceCard data-lesson-content className="px-5 py-5 sm:px-6">
          {/* SECTION 2 — THE LESSON (shown immediately). */}
          <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Lesson topic
          </label>
          <input
            type="text"
            value={draft.topic}
            onChange={(e) => updateDraft({ topic: e.target.value })}
            className="mt-1 w-full rounded-lg border border-input bg-white px-3 py-2 text-lg font-semibold text-[#102A43] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE]/45"
            aria-label="Lesson topic"
          />

          {guided && (
            <p className="mt-3 text-xs text-muted-foreground">
              Build with me — section {stepIndex + 1} of {GUIDED_STEPS.length}
            </p>
          )}

          {stepVisible('objectives') && (
            <WorkspaceSection title="Objectives">
              {objectives.length > 0 ? (
                <ul className="list-disc space-y-1.5 pl-5 text-sm text-[#102A43]">
                  {objectives.map((o, i) => <li key={i}>{o.description}</li>)}
                </ul>
              ) : (
                <p className="text-sm italic text-muted-foreground">
                  No objectives were recorded for this lesson.
                </p>
              )}
            </WorkspaceSection>
          )}

          {stepVisible('starter') && (
            <WorkspaceSection
              title="Phase 1 · Starter"
              onSuggest={() => suggest('introduction')}
              suggesting={suggesting === 'introduction'}
            >
              <TextArea
                value={draft.introduction}
                onChange={(e) => updateDraft({ introduction: e.target.value })}
                rows={3}
                aria-label="Phase 1 starter"
              />
            </WorkspaceSection>
          )}

          {stepVisible('main') && (
            <WorkspaceSection
              title="Phase 2 · Main Learning"
              onSuggest={() => suggest('main_activities')}
              suggesting={suggesting === 'main_activities'}
            >
              {draft.mainActivities.length > 0 ? (
                <div className="space-y-2">
                  {draft.mainActivities.map((a, i) => (
                    <div key={i} className="flex items-start gap-2">
                      <span className="mt-2.5 text-xs font-semibold text-slate-400">{i + 1}</span>
                      <TextArea
                        value={a.description}
                        onChange={(e) => updateActivity(i, { description: e.target.value })}
                        rows={2}
                        aria-label={`Main learning activity ${i + 1}`}
                        className="flex-1"
                      />
                      <button
                        type="button"
                        aria-label={`Remove activity ${i + 1}`}
                        onClick={() =>
                          updateDraft({
                            mainActivities: draft.mainActivities.filter((_, j) => j !== i),
                          })
                        }
                        className="mt-2 text-slate-400 hover:text-red-600"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm italic text-muted-foreground">
                  No main-learning activities were generated.
                </p>
              )}
              <Button
                size="sm"
                variant="outline"
                className="mt-2"
                onClick={() =>
                  updateDraft({
                    mainActivities: [
                      ...draft.mainActivities,
                      { phase: 'main_learning', description: '', duration_minutes: null, resources: [] },
                    ],
                  })
                }
              >
                <Plus className="mr-1 h-3 w-3" /> Add activity
              </Button>
            </WorkspaceSection>
          )}

          {stepVisible('assessment') && (
            <WorkspaceSection
              title="Assessment"
              onSuggest={() => suggest('assessment')}
              suggesting={suggesting === 'assessment'}
            >
              <TextArea
                value={draft.assessment}
                onChange={(e) => updateDraft({ assessment: e.target.value })}
                rows={3}
                aria-label="Assessment"
              />
            </WorkspaceSection>
          )}

          {stepVisible('reflection') && (
            <WorkspaceSection
              title="Phase 3 · Reflection"
              onSuggest={() => suggest('conclusion')}
              suggesting={suggesting === 'conclusion'}
            >
              <TextArea
                value={draft.conclusion}
                onChange={(e) => updateDraft({ conclusion: e.target.value })}
                rows={3}
                aria-label="Phase 3 reflection"
              />
            </WorkspaceSection>
          )}

          {/* Read-only curriculum context (not AI, not editable here). */}
          <WorkspaceSection title="Resources">
            {resources.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {resources.map((r, i) => (
                  <span key={i} className="rounded bg-[#102A43]/8 px-2 py-1 text-sm text-[#102A43]">
                    {r}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-sm italic text-muted-foreground">No resources recorded.</p>
            )}
          </WorkspaceSection>

          {(active.structured_references?.length || 0) > 0 && (
            <WorkspaceSection title="References">
              <ul className="list-disc space-y-1 pl-5 text-sm text-[#102A43]">
                {active.structured_references!.map((r, i) => (
                  <li key={i}>
                    {r.title}
                    {r.page ? ` — p.${r.page}` : ''}
                    {r.type ? ` (${r.type})` : ''}
                  </li>
                ))}
              </ul>
            </WorkspaceSection>
          )}

          {(active.core_competencies?.length || 0) > 0 && (
            <WorkspaceSection title="Core Competencies">
              <div className="flex flex-wrap gap-2">
                {active.core_competencies!.map((c, i) => (
                  <span key={i} className="rounded border border-[#04A9CE]/40 bg-[#04A9CE]/8 px-2 py-1 text-xs text-[#04769B]">
                    {c}
                  </span>
                ))}
              </div>
            </WorkspaceSection>
          )}

          {(active.keywords?.length || 0) > 0 && (
            <WorkspaceSection title="Keywords">
              <p className="text-sm text-[#102A43]">{active.keywords!.join(', ')}</p>
            </WorkspaceSection>
          )}

          {(active.wapef_deep_hope || active.wapef_storyline || active.wapef_gods_story) && (
            <WorkspaceSection title="WAPEF">
              <dl className="space-y-1 text-sm text-[#102A43]">
                {active.wapef_deep_hope && <div><dt className="inline font-medium">Deep Hope: </dt><dd className="inline">{active.wapef_deep_hope}</dd></div>}
                {active.wapef_storyline && <div><dt className="inline font-medium">Storyline: </dt><dd className="inline">{active.wapef_storyline}</dd></div>}
                {active.wapef_gods_story && <div><dt className="inline font-medium">God&apos;s Story: </dt><dd className="inline">{active.wapef_gods_story}</dd></div>}
              </dl>
            </WorkspaceSection>
          )}

          {/* SECTION 3 — ACTIONS: few, obvious, contextual. */}
          <div className="mt-6 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-4">
            <Button onClick={handleSave} disabled={saving}>
              {saving ? (
                <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Saving…</>
              ) : (
                <><Save className="mr-2 h-4 w-4" /> Save</>
              )}
            </Button>
            {dirty && !saving && (
              <span className="text-xs text-muted-foreground">Unsaved changes</span>
            )}
            {guided && stepIndex < GUIDED_STEPS.length - 1 && (
              <Button variant="outline" onClick={advance}>
                <CheckCircle className="mr-2 h-4 w-4" /> Looks good, next
              </Button>
            )}
            <Button variant="outline" onClick={() => onExport('docx')} disabled={exporting === 'docx'}>
              {exporting === 'docx' ? 'Exporting…' : 'Export DOCX'}
            </Button>
            <Button variant="outline" onClick={() => onExport('pdf')} disabled={exporting === 'pdf'}>
              {exporting === 'pdf' ? 'Exporting…' : 'Export PDF'}
            </Button>
          </div>
        </SurfaceCard>
      )}
    </div>
  )
}

function ContextItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{label}</div>
      <div className="text-sm font-semibold text-[#102A43]">{value}</div>
    </div>
  )
}

function WorkspaceSection({
  title,
  onSuggest,
  suggesting,
  children,
}: {
  title: string
  onSuggest?: () => void
  suggesting?: boolean
  children: React.ReactNode
}) {
  return (
    <section className="mt-5 border-t border-slate-100 pt-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">{title}</h3>
        {onSuggest && (
          <Button
            size="sm"
            variant="ghost"
            className="h-7 px-2 text-xs"
            onClick={onSuggest}
            disabled={suggesting}
          >
            {suggesting ? (
              <><Loader2 className="mr-1 h-3 w-3 animate-spin" /> Suggesting…</>
            ) : (
              <><Sparkles className="mr-1 h-3 w-3" /> Suggest</>
            )}
          </Button>
        )}
      </div>
      {children}
    </section>
  )
}
