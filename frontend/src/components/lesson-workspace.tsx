'use client'

import { useCallback, useEffect, useState } from 'react'
import { CheckCircle, Loader2, Plus, RefreshCw, Save, Sparkles, Trash2, Wrench } from 'lucide-react'

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
  teaching_learning_resources?: string[]
  core_competencies?: string[]
  structured_references?: { type: string; title: string; page?: string }[]
  references?: string[]
  wapef_deep_hope?: string
  wapef_storyline?: string
  wapef_through_lines?: string[]
  wapef_gods_story?: string
  homework?: string
  class_assignment?: string
  home_assignment?: string
  school_name?: string | null
  template_id?: string | null
  status?: string
  teacher_edited?: boolean
  ai_generated?: boolean
  provenance?: LessonProvenance
}

/** The Approved WAPEF Plan carries four teacher-selected structured fields. */
const WAPEF_TEMPLATE_ID = 'tpl-wapef-approved-plan'

const NACCA_COMPETENCIES = [
  'Critical Thinking and Problem Solving',
  'Creativity and Innovation',
  'Communication and Collaboration',
  'Cultural Identity and Global Citizenship',
  'Personal Development and Leadership',
  'Digital Literacy',
]

interface ReferenceDraft {
  type: string
  title: string
  page?: string
}

/**
 * Everything the teacher owns on this lesson (PART 5/36 persistence matrix).
 * Source fields (source_tlrs, the indicator, the content standard) are NOT in
 * the draft: they stay the scheme's authoritative record and are read-only.
 */
interface Draft {
  topic: string
  introduction: string
  assessment: string
  conclusion: string
  mainActivities: MainActivity[]
  //: Class work completed IN the lesson (PART 15).
  classAssignment: string
  //: Follow-up completed AT HOME. Seeded from home_assignment, falling back to
  //: the legacy homework field so an AI-enriched home task is never hidden.
  homeAssignment: string
  //: Lesson-specific vocabulary (PART 14) — editable, never re-forced.
  keywords: string[]
  //: The LESSON's resource list (PART 13/26). Editing it corrects the lesson
  //: without ever mutating the scheme's own source_tlrs record.
  lessonResources: string[]
  references: ReferenceDraft[]
  wapefDeepHope: string
  wapefStoryline: string
  wapefThroughLines: string[]
  wapefGodsStory: string
}

function draftFrom(l: LessonData): Draft {
  return {
    topic: l.lesson_topic || '',
    introduction: l.introduction || '',
    assessment: l.assessment || '',
    conclusion: l.conclusion || '',
    mainActivities: normalizeActivities(l.main_activities),
    classAssignment: l.class_assignment || '',
    homeAssignment: l.home_assignment || l.homework || '',
    keywords: Array.isArray(l.keywords) ? l.keywords : [],
    // The lesson value: teacher-corrected list when present, otherwise the
    // generated union of source + teacher resources.
    lessonResources: Array.isArray(l.teaching_learning_resources)
      ? l.teaching_learning_resources
      : [...(l.source_tlrs || []), ...(l.other_tlrs || [])],
    references: (l.structured_references || []).map((r) => ({
      type: r.type || 'Other', title: r.title || '', page: r.page || '',
    })),
    wapefDeepHope: l.wapef_deep_hope || '',
    wapefStoryline: l.wapef_storyline || '',
    wapefThroughLines: Array.isArray(l.wapef_through_lines) ? l.wapef_through_lines : [],
    wapefGodsStory: l.wapef_gods_story || '',
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
  // Approved WAPEF option lists. Loaded once; a failure only means the WAPEF
  // selects are unavailable, never that the workspace breaks (the four fields
  // still show their stored values as read-only text).
  const [wapefOptions, setWapefOptions] = useState<{
    deep_hopes: string[]
    storylines: string[]
    through_lines: string[]
    gods_story: string[]
  } | null>(null)

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

  useEffect(() => {
    api.getWapefOptions()
      .then(setWapefOptions)
      .catch(() => setWapefOptions(null))
  }, [])

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
      // PART 5/36: EVERY teacher-owned field is sent in one payload so a save
      // is complete. The server is authoritative and echoes the stored lesson
      // back, which then replaces local state — the UI can never drift from the
      // database after a save.
      const updated = await api.updateLesson(active.id, {
        lesson_topic: draft.topic,
        introduction: draft.introduction,
        assessment: draft.assessment,
        conclusion: draft.conclusion,
        class_assignment: draft.classAssignment,
        home_assignment: draft.homeAssignment,
        // Keep the legacy single field in step so templates that declare only a
        // Homework row still render the home follow-up.
        homework: draft.homeAssignment,
        keywords: draft.keywords.map((k) => k.trim()).filter(Boolean),
        // The lesson's resource list (PART 13/26): correcting a source spelling
        // changes the lesson only — source_tlrs is untouched server-side.
        teaching_learning_resources: draft.lessonResources
          .map((r) => r.trim())
          .filter(Boolean),
        structured_references: draft.references
          .filter((r) => (r.title || '').trim())
          .map((r) => ({ type: r.type || 'Other', title: r.title.trim(), page: r.page || '' })),
        wapef_deep_hope: draft.wapefDeepHope,
        wapef_storyline: draft.wapefStoryline,
        wapef_through_lines: draft.wapefThroughLines,
        wapef_gods_story: draft.wapefGodsStory,
        main_activities: draft.mainActivities.map((a) => ({
          phase: a.phase || 'main_learning',
          description: a.description,
          duration_minutes: a.duration_minutes || 0,
          resources: a.resources || [],
        })),
      })
      const merged = { ...active, ...updated } as LessonData
      setLessons((ls) => ls.map((l) => (l.id === active.id ? merged : l)))
      // Re-seed from the SERVER's echo, so what the teacher sees after Save is
      // exactly what the database holds (never a local-only value).
      setDraft(draftFrom(merged))
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
  //
  // AI is OFF by default and only ever runs here — one section at a time, on
  // the teacher's explicit request. The two affordances map to the backend's
  // rewrite modes; internal pattern names/scores/corpus ids never surface.
  const suggest = async (
    section: 'introduction' | 'main_activities' | 'assessment' | 'conclusion',
    rewriteMode: 'suggest_another_version' | 'make_more_practical' = 'suggest_another_version',
  ) => {
    if (!active || !draft) return
    setSuggesting(`${section}·${rewriteMode}`)
    setAiNotice(null)
    try {
      let mode = 'BASIC'
      try {
        const savedMode = window.localStorage.getItem('schemeknit.ai_mode')
        if (savedMode && savedMode !== 'OFF') mode = savedMode
      } catch { /* storage unavailable */ }
      const requestId = `${active.id}:${section}:${Date.now()}`
      const res = await api.regenerateSection(active.id, section, mode, '', requestId, rewriteMode)
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
  // PART 6/22: the four WAPEF fields are first-class only for the Approved
  // WAPEF Plan. Any other template intentionally hides them.
  const isWapefTemplate = active.template_id === WAPEF_TEMPLATE_ID
  // PART 2/28: the curriculum reference names THIS lesson's subject
  // ("Computing Curriculum") — never a hard-coded "Subject Curriculum".
  const subjectCurriculumLabel =
    active.subject && active.subject !== 'Unknown'
      ? `${active.subject} Curriculum`
      : 'Subject Curriculum'
  const REFERENCE_TYPES = [
    subjectCurriculumLabel,
    "Teacher's Handbook / Teacher's Guide",
    'Textbook',
    'Other',
  ]

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
          {/* PART 3: "Unknown" is never shown as a generation-ready class. */}
          <ContextItem
            label="Class"
            value={
              active.class_level && active.class_level !== 'Unknown'
                ? active.class_level
                : 'Needs confirmation'
            }
          />
          {/* PART 7: the school this lesson belongs to, server-derived. */}
          <ContextItem
            label="School"
            value={active.school_name || 'Not set in Settings'}
          />
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
          {/* Product-cop: the teacher is told this is a generated lesson, built
              from their own scheme plus the curriculum evidence layer. AI is
              never mentioned as the author and no internal pattern name, score
              or corpus id is ever shown. */}
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center rounded-full bg-[#04769B]/10 px-2.5 py-0.5 text-xs font-semibold text-[#04769B]">
              Generated lesson
            </span>
            {!active.provenance?.ai_provider && (
              <span className="text-xs text-muted-foreground">
                Built from your scheme and curriculum evidence.
              </span>
            )}
          </div>
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
              sectionKey="introduction"
              busyKey={suggesting}
              onSuggest={() => suggest('introduction')}
              onSuggestPractical={() => suggest('introduction', 'make_more_practical')}
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
              sectionKey="main_activities"
              busyKey={suggesting}
              onSuggest={() => suggest('main_activities')}
              onSuggestPractical={() => suggest('main_activities', 'make_more_practical')}
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
              sectionKey="assessment"
              busyKey={suggesting}
              onSuggest={() => suggest('assessment')}
              onSuggestPractical={() => suggest('assessment', 'make_more_practical')}
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
              sectionKey="conclusion"
              busyKey={suggesting}
              onSuggest={() => suggest('conclusion')}
              onSuggestPractical={() => suggest('conclusion', 'make_more_practical')}
            >
              <TextArea
                value={draft.conclusion}
                onChange={(e) => updateDraft({ conclusion: e.target.value })}
                rows={3}
                aria-label="Phase 3 reflection"
              />
            </WorkspaceSection>
          )}

          {/* ASSESSMENT FOLLOW-UP (PART 15): class work and home work are
              two distinct, teacher-editable tasks inside the lesson structure —
              not a huge configuration form. */}
          <WorkspaceSection title="Class Assignment">
            <TextArea
              value={draft.classAssignment}
              onChange={(e) => updateDraft({ classAssignment: e.target.value })}
              rows={3}
              aria-label="Class assignment"
              placeholder="What the class completes during the lesson"
            />
          </WorkspaceSection>

          <WorkspaceSection title="Home Assignment">
            <TextArea
              value={draft.homeAssignment}
              onChange={(e) => updateDraft({ homeAssignment: e.target.value })}
              rows={3}
              aria-label="Home assignment"
              placeholder="What learners complete at home after the lesson"
            />
          </WorkspaceSection>

          {/* RESOURCES — SOURCE vs LESSON (PART 13/26). The scheme's own list is
              shown verbatim and read-only; the lesson list is editable so a
              source spelling error can be corrected without rewriting the
              uploaded scheme. */}
          <WorkspaceSection title="Resources">
            {(active.source_tlrs?.length || 0) > 0 && (
              <div className="mb-3">
                <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                  From your scheme (source — read only)
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {active.source_tlrs!.map((r, i) => (
                    <span
                      key={i}
                      className="rounded bg-[#102A43]/8 px-2 py-1 text-xs text-[#102A43]"
                    >
                      {r}
                    </span>
                  ))}
                </div>
              </div>
            )}
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              This lesson&apos;s resources
            </p>
            {draft.lessonResources.map((r, i) => (
              <div key={i} className="mb-1 flex items-center gap-1.5">
                <input
                  type="text"
                  value={r}
                  aria-label={`Lesson resource ${i + 1}`}
                  onChange={(e) =>
                    updateDraft({
                      lessonResources: draft.lessonResources.map((x, j) =>
                        j === i ? e.target.value : x),
                    })
                  }
                  className="flex-1 rounded-lg border border-input bg-white px-2.5 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE]/45"
                />
                <button
                  type="button"
                  aria-label={`Remove lesson resource ${i + 1}`}
                  onClick={() =>
                    updateDraft({
                      lessonResources: draft.lessonResources.filter((_, j) => j !== i),
                    })
                  }
                  className="text-slate-400 hover:text-red-600"
                >
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
            ))}
            <Button
              size="sm"
              variant="outline"
              className="mt-1"
              onClick={() =>
                updateDraft({ lessonResources: [...draft.lessonResources, ''] })
              }
            >
              <Plus className="mr-1 h-3 w-3" aria-hidden="true" /> Add resource
            </Button>
          </WorkspaceSection>

          {/* KEYWORDS — lesson-specific vocabulary, editable (PART 14). */}
          <WorkspaceSection title="Keywords">
            {draft.keywords.map((k, i) => (
              <div key={i} className="mb-1 flex items-center gap-1.5">
                <input
                  type="text"
                  value={k}
                  aria-label={`Keyword ${i + 1}`}
                  onChange={(e) =>
                    updateDraft({
                      keywords: draft.keywords.map((x, j) =>
                        j === i ? e.target.value : x),
                    })
                  }
                  className="flex-1 rounded-lg border border-input bg-white px-2.5 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE]/45"
                />
                <button
                  type="button"
                  aria-label={`Remove keyword ${i + 1}`}
                  onClick={() =>
                    updateDraft({ keywords: draft.keywords.filter((_, j) => j !== i) })
                  }
                  className="text-slate-400 hover:text-red-600"
                >
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
            ))}
            <Button
              size="sm"
              variant="outline"
              className="mt-1"
              onClick={() => updateDraft({ keywords: [...draft.keywords, ''] })}
            >
              <Plus className="mr-1 h-3 w-3" aria-hidden="true" /> Add keyword
            </Button>
          </WorkspaceSection>

          {/* REFERENCES — teacher-editable; the curriculum option names THIS
              lesson's subject (PART 2/28). */}
          <WorkspaceSection title="References">
            {draft.references.map((ref, i) => (
              <div key={i} className="mb-1 flex items-center gap-1.5">
                <select
                  value={ref.type || 'Other'}
                  aria-label={`Reference ${i + 1} type`}
                  onChange={(e) =>
                    updateDraft({
                      references: draft.references.map((x, j) =>
                        j === i ? { ...x, type: e.target.value } : x),
                    })
                  }
                  className="w-40 rounded-lg border border-input bg-white px-2 py-1.5 text-xs"
                >
                  {REFERENCE_TYPES.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
                <input
                  type="text"
                  value={ref.title || ''}
                  aria-label={`Reference ${i + 1} title`}
                  placeholder="Title"
                  onChange={(e) =>
                    updateDraft({
                      references: draft.references.map((x, j) =>
                        j === i ? { ...x, title: e.target.value } : x),
                    })
                  }
                  className="flex-1 rounded-lg border border-input bg-white px-2.5 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE]/45"
                />
                <input
                  type="text"
                  value={ref.page || ''}
                  aria-label={`Reference ${i + 1} page`}
                  placeholder="Page"
                  onChange={(e) =>
                    updateDraft({
                      references: draft.references.map((x, j) =>
                        j === i ? { ...x, page: e.target.value } : x),
                    })
                  }
                  className="w-20 rounded-lg border border-input bg-white px-2 py-1.5 text-sm"
                />
                <button
                  type="button"
                  aria-label={`Remove reference ${i + 1}`}
                  onClick={() =>
                    updateDraft({
                      references: draft.references.filter((_, j) => j !== i),
                    })
                  }
                  className="text-slate-400 hover:text-red-600"
                >
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
            ))}
            <Button
              size="sm"
              variant="outline"
              className="mt-1"
              onClick={() =>
                updateDraft({
                  references: [
                    ...draft.references,
                    { type: subjectCurriculumLabel, title: '', page: '' },
                  ],
                })
              }
            >
              <Plus className="mr-1 h-3 w-3" aria-hidden="true" /> Add reference
            </Button>
          </WorkspaceSection>

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

          {/* WAPEF four fields (PART 6/22): first-class when the WAPEF plan is
              the selected template — editable here and persisted verbatim.
              They disappear only when a non-WAPEF template is in use. */}
          {isWapefTemplate && (
            <WorkspaceSection title="WAPEF fields">
              <p className="mb-2 text-xs text-muted-foreground">
                Teacher-selected values. The AI never chooses or rewrites these;
                the export prints exactly what is saved here.
              </p>
              {wapefOptions ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="text-xs font-semibold text-[#102A43]">
                    Deep Hope
                    <select
                      value={draft.wapefDeepHope}
                      aria-label="Deep Hope"
                      onChange={(e) => updateDraft({ wapefDeepHope: e.target.value })}
                      className="mt-1 w-full rounded-lg border border-input bg-white px-2.5 py-1.5 text-sm"
                    >
                      <option value="">— Select —</option>
                      {wapefOptions.deep_hopes.map((o) => (
                        <option key={o} value={o}>{o}</option>
                      ))}
                    </select>
                  </label>
                  <label className="text-xs font-semibold text-[#102A43]">
                    Storyline
                    <select
                      value={draft.wapefStoryline}
                      aria-label="Storyline"
                      onChange={(e) => updateDraft({ wapefStoryline: e.target.value })}
                      className="mt-1 w-full rounded-lg border border-input bg-white px-2.5 py-1.5 text-sm"
                    >
                      <option value="">— Select —</option>
                      {wapefOptions.storylines.map((o) => (
                        <option key={o} value={o}>{o}</option>
                      ))}
                    </select>
                  </label>
                  <label className="text-xs font-semibold text-[#102A43]">
                    God&apos;s Story
                    <select
                      value={draft.wapefGodsStory}
                      aria-label="God's Story"
                      onChange={(e) => updateDraft({ wapefGodsStory: e.target.value })}
                      className="mt-1 w-full rounded-lg border border-input bg-white px-2.5 py-1.5 text-sm"
                    >
                      <option value="">— Select —</option>
                      {wapefOptions.gods_story.map((o) => (
                        <option key={o} value={o}>{o}</option>
                      ))}
                    </select>
                  </label>
                </div>
              ) : null}
              <p className="mt-3 mb-1 text-xs font-semibold text-[#102A43]">
                Through lines (select all that apply)
              </p>
              {wapefOptions ? (
                <div className="flex flex-wrap gap-1.5">
                  {wapefOptions.through_lines.map((o) => {
                    const selected = draft.wapefThroughLines.includes(o)
                    return (
                      <button
                        key={o}
                        type="button"
                        aria-pressed={selected}
                        onClick={() =>
                          updateDraft({
                            wapefThroughLines: selected
                              ? draft.wapefThroughLines.filter((t) => t !== o)
                              : [...draft.wapefThroughLines, o],
                          })
                        }
                        className={`rounded border px-2 py-0.5 text-xs ${
                          selected
                            ? 'border-[#102A43] bg-[#102A43] text-white'
                            : 'bg-background text-muted-foreground'
                        }`}
                      >
                        {o}
                      </button>
                    )
                  })}
                </div>
              ) : (
                <p className="text-sm text-[#102A43]">
                  {draft.wapefThroughLines.length
                    ? draft.wapefThroughLines.join(', ')
                    : 'No Through lines selected.'}
                </p>
              )}
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
  sectionKey,
  busyKey,
  onSuggest,
  onSuggestPractical,
  children,
}: {
  title: string
  /** Internal key used to match the spinning affordance. */
  sectionKey?: string
  /** `${section}·${rewriteMode}` for the suggestion currently in flight. */
  busyKey?: string | null
  onSuggest?: () => void
  onSuggestPractical?: () => void
  children: React.ReactNode
}) {
  const suggestSpinning = busyKey === `${sectionKey}·suggest_another_version`
  const practicalSpinning = busyKey === `${sectionKey}·make_more_practical`
  const anySpinning = Boolean(sectionKey && busyKey && busyKey.startsWith(`${sectionKey}·`))
  return (
    <section className="mt-5 border-t border-slate-100 pt-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">{title}</h3>
        {onSuggest && (
          <div className="flex items-center gap-1.5">
            {onSuggestPractical && (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 px-2 text-xs"
                onClick={onSuggestPractical}
                disabled={anySpinning}
              >
                {practicalSpinning ? (
                  <><Loader2 className="mr-1 h-3 w-3 animate-spin" aria-hidden="true" /> Reworking…</>
                ) : (
                  <><Wrench className="mr-1 h-3 w-3" aria-hidden="true" /> Make this more practical</>
                )}
              </Button>
            )}
            <Button
              size="sm"
              variant="ghost"
              className="h-7 px-2 text-xs"
              onClick={onSuggest}
              disabled={anySpinning}
            >
              {suggestSpinning ? (
                <><Loader2 className="mr-1 h-3 w-3 animate-spin" aria-hidden="true" /> Suggesting…</>
              ) : (
                <><Sparkles className="mr-1 h-3 w-3" aria-hidden="true" /> Suggest another version</>
              )}
            </Button>
          </div>
        )}
      </div>
      {children}
    </section>
  )
}
