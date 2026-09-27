'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { SurfaceCard } from '@/components/ui/surface-card'
import { Input } from '@/components/ui/input'
import { Field, TextArea } from '@/components/ui/field'
import { Select } from '@/components/ui/select'
import { Banner } from '@/components/ui/banner'
import { ArrowLeft, CheckCircle, AlertCircle, Save, Loader2, Plus, Trash2, ChevronUp, ChevronDown } from 'lucide-react'
import { api } from '@/lib/api'
import { aiFailure } from '@/lib/ai-feedback'
import { resolveRouteId } from '@/lib/route-params'
import { PageHeader } from '@/components/ui/page-header'
import { SourceAlignment, type LessonProvenance } from '@/components/source-alignment'

/** Canonical main-learning activity (PART X): never flattened to raw JSON. */
interface MainActivity {
  phase?: string
  description: string
  duration_minutes: number | null
  resources?: string[]
}

/**
 * Normalize any stored/provider activities to the editable shape. Drops
 * entries without a usable description so the UI never shows blank/`null`
 * activities (PART Y).
 */
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
  job_id: string
  scheme_id: string
  week_number: number
  week_ending?: string | null
  week_ending_derived?: boolean
  teaching_week?: number
  lesson_sequence?: number
  lesson_number: number
  lesson_date: string | null
  class_level: string
  subject: string
  strand: string | null
  sub_strand: string | null
  content_standard: string | null
  indicators: string[] | null
  indicator_codes?: string[]
  lesson_topic: string | null
  introduction: string | null
  assessment: string | null
  conclusion: string | null
  learning_objectives?: { description: string; indicator_code?: string }[]
  main_activities?: { description: string; duration_minutes?: number; resources?: string[] }[]
  keywords?: string[]
  source_tlrs?: string[]
  other_tlrs?: string[]
  core_competencies?: string[]
  structured_references?: { type: string; title: string; author_publisher?: string; page?: string; notes?: string }[]
  references?: string[]
  status: string
  teacher_edited: boolean
  /** "Why this lesson?" — source/alignment record from the curriculum spine. */
  provenance?: LessonProvenance
}

export default function LessonDetailPage() {
  const params = useParams()
  const lessonId = resolveRouteId(params.id, 'lessons')

  const [lesson, setLesson] = useState<LessonData | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Editable fields
  const [topic, setTopic] = useState('')
  const [introduction, setIntroduction] = useState('')
  const [assessment, setAssessment] = useState('')
  const [conclusion, setConclusion] = useState('')
  // Per-lesson review fields (Section I)
  const [keywords, setKeywords] = useState<string[]>([])
  const [otherTlrs, setOtherTlrs] = useState<string[]>([])
  const [coreCompetencies, setCoreCompetencies] = useState<string[]>([])
  const [structuredRefs, setStructuredRefs] = useState<
    { type: string; title: string; author_publisher?: string; page?: string; notes?: string }[]
  >([])
  const NACCA_COMPETENCIES = [
    'Critical Thinking and Problem Solving',
    'Creativity and Innovation',
    'Communication and Collaboration',
    'Cultural Identity and Global Citizenship',
    'Personal Development and Leadership',
    'Digital Literacy',
  ]
  const REFERENCE_TYPES = [
    'Subject Curriculum',
    "Teacher's Handbook / Teacher's Guide",
    'Textbook',
    'Other',
  ]
  // Phase 2 · Main Learning — independently editable activities (PART A/B).
  const [mainActivities, setMainActivities] = useState<MainActivity[]>([])
  // Optional AI section regeneration (existing /api/ai/regenerate-section)
  const [regenBusy, setRegenBusy] = useState<string | null>(null)
  const [regenNote, setRegenNote] = useState<string | null>(null)
  // PART I: calm, teacher-safe AI failure notice (never raw provider detail).
  const [aiWarning, setAiWarning] = useState<string | null>(null)
  // What AI would actually do for this teacher's selected mode.
  const [aiStatus, setAiStatus] = useState<{
    active: boolean; provider: string | null; mode: string; reason: string | null;
  } | null>(null)

  useEffect(() => {
    load()
    let mode = 'BASIC'
    try {
      const saved = window.localStorage.getItem('schemeknit.ai_mode')
      if (saved && saved !== 'OFF') mode = saved
    } catch { /* storage unavailable */ }
    api.getAiStatus(mode).then(setAiStatus).catch(() => setAiStatus(null))
  }, [lessonId])

  const load = async () => {
    try {
      setLoading(true)
      const data = await api.getLesson(lessonId)
      setLesson(data)
      setTopic(data.lesson_topic || '')
      setIntroduction(data.introduction || '')
      setAssessment(data.assessment || '')
      setConclusion(data.conclusion || '')
      setKeywords(data.keywords || [])
      setOtherTlrs(data.other_tlrs || [])
      setMainActivities(normalizeActivities(data.main_activities))
      setCoreCompetencies(data.core_competencies || [])
      setStructuredRefs(
        (data.structured_references && data.structured_references.length > 0
          ? data.structured_references
          : []
        ).map((r: any) => ({
          type: r.type || 'Other',
          title: r.title || '',
          author_publisher: r.author_publisher || '',
          page: r.page || '',
          notes: r.notes || '',
        }))
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load lesson')
    } finally {
      setLoading(false)
    }
  }

  const handleRegenerate = async (
    section: 'introduction' | 'assessment' | 'conclusion' | 'main_activities',
  ) => {
    if (!lesson) return
    try {
      setRegenBusy(section)
      setRegenNote(null)
      setAiWarning(null)
      setError(null)
      // Stable idempotency key for this user action so a retried submission
      // cannot consume a second monthly AI generation.
      const requestId = `${lesson.id}:${section}:${Date.now()}`
      // Use the teacher's last chosen AI mode. This is NOT hard-coded to a
      // single provider: OFF (or unset) resolves to BASIC, which lets the
      // backend auto-select whichever real provider is configured, and report
      // an accurate diagnostic when none is.
      let mode = 'BASIC'
      try {
        const saved = window.localStorage.getItem('schemeknit.ai_mode')
        if (saved && saved !== 'OFF') mode = saved
      } catch { /* storage unavailable */ }
      const res = await api.regenerateSection(lesson.id, section, mode, '', requestId)
      if (section === 'main_activities') {
        // PART F/G: render the backend-normalized structured activities, then
        // let the teacher review — saving is an explicit, separate action.
        const next = normalizeActivities(res.new_activities)
        if (next.length === 0) {
          // A 200 with no usable activities is still a failed suggestion.
          // Never blank the teacher's existing activities.
          setAiWarning(aiFailure({ code: 'AI_NO_SUGGESTION' }).message)
          return
        }
        setMainActivities(next)
        setRegenNote(
          `AI suggestion inserted by ${res.provider || 'provider'}. ` +
          'Review and Save to keep it.'
        )
        return
      }
      const text = res.new_content || ''
      if (section === 'introduction') setIntroduction(text)
      if (section === 'assessment') setAssessment(text)
      if (section === 'conclusion') setConclusion(text)
      setRegenNote(
        `AI suggestion inserted by ${res.provider || 'provider'} (mode: ${res.mode || mode}). ` +
        'Review and Save to keep it.'
      )
    } catch (err) {
      // PART H/I/J/AD: the teacher sees ONLY calm, non-technical copy; the raw
      // provider diagnostic stays server-side.
      setAiWarning(aiFailure(err).message)
    } finally {
      setRegenBusy(null)
    }
  }

  const addActivity = () =>
    setMainActivities(prev => [
      ...prev,
      { description: '', duration_minutes: null, resources: [] },
    ])

  const updateActivity = (idx: number, patch: Partial<MainActivity>) =>
    setMainActivities(prev => prev.map((a, i) => (i === idx ? { ...a, ...patch } : a)))

  const removeActivity = (idx: number) =>
    setMainActivities(prev => prev.filter((_, i) => i !== idx))

  const moveActivity = (idx: number, delta: number) =>
    setMainActivities(prev => {
      const next = [...prev]
      const target = idx + delta
      if (target < 0 || target >= next.length) return prev
      ;[next[idx], next[target]] = [next[target], next[idx]]
      return next
    })

  const handleSave = async () => {
    try {
      setSaving(true)
      setSaved(false)
      // PART L/M: only non-empty references are persisted — empty slots on
      // screen never become stored empty objects.
      const savedRefs = structuredRefs.filter(r => (r.title || '').trim())
      // Only non-empty activities persist; ordering is preserved as displayed.
      const activities = mainActivities
        .map(a => ({
          phase: a.phase,
          description: (a.description || '').trim(),
          duration_minutes: a.duration_minutes,
          resources: a.resources || [],
        }))
        .filter(a => a.description)
      const updated = await api.updateLesson(lessonId, {
        lesson_topic: topic,
        introduction,
        main_activities: activities,
        assessment,
        conclusion,
        keywords,
        other_tlrs: otherTlrs,
        core_competencies: coreCompetencies,
        structured_references: savedRefs,
        references: savedRefs.map(r => r.title || r.type).filter(Boolean),
      })
      setLesson(updated)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save lesson')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-muted-foreground">Loading lesson...</p>
        </div>
      </div>
    )
  }

  if (error && !lesson) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center px-4">
        <SurfaceCard className="w-full max-w-md px-6 py-8 text-center">
          <AlertCircle className="mx-auto mb-4 h-12 w-12 text-destructive" aria-hidden="true" />
          <p className="mb-4 text-destructive">{error}</p>
          <Button onClick={load}>Try Again</Button>
        </SurfaceCard>
      </div>
    )
  }

  if (!lesson) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center px-4">
        <SurfaceCard className="w-full max-w-md px-6 py-8 text-center">
          <p className="mb-4 text-muted-foreground">Lesson not found</p>
          <Button asChild>
            <Link href="/lessons">Back to Lesson Plans</Link>
          </Button>
        </SurfaceCard>
      </div>
    )
  }

  const objectives = lesson.learning_objectives || []

  const suggestButton = (section: 'introduction' | 'assessment' | 'conclusion') => (
    <Button
      size="sm"
      variant="outline"
      disabled={regenBusy !== null}
      onClick={() => handleRegenerate(section)}
    >
      {regenBusy === section ? 'Generating...' : `Suggest ${section}`}
    </Button>
  )

  const sectionHeading = 'text-xs font-semibold uppercase tracking-wider text-slate-500'

  return (
    <div className="min-h-screen">
      <main className="container mx-auto max-w-4xl px-4 py-8">
        {/* One h1: which lesson this is, at a glance. */}
        <PageHeader
          className="mb-6"
          eyebrow="Lesson"
          title={`Week ${lesson.teaching_week || lesson.week_number} • Lesson ${lesson.lesson_number}`}
          description={
            <>
              {lesson.subject} &bull; {lesson.class_level}
              {lesson.lesson_date ? ` &bull; ${lesson.lesson_date}` : ''}
              {lesson.teacher_edited ? ' &bull; Edited' : ''}
            </>
          }
          actions={
            <Button variant="outline" asChild>
              <Link href="/lessons">
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back to Lesson Plans
              </Link>
            </Button>
          }
        />

        {/* Lesson context (read-only) */}
        <SurfaceCard
          data-lesson-context
          accent="bg-gradient-to-r from-[#102A43] to-[#04A9CE]"
          className="mb-6 px-5 py-5 sm:px-6"
        >
          <h2 className="text-base font-semibold text-[#102A43]">Lesson context</h2>
          <div className="mt-3 space-y-2 text-sm">
            {lesson.strand && (
              <p><span className="text-muted-foreground">Strand:</span> {lesson.strand}</p>
            )}
            {lesson.sub_strand && (
              <p><span className="text-muted-foreground">Sub-strand:</span> {lesson.sub_strand}</p>
            )}
            {lesson.content_standard && (
              <p><span className="text-muted-foreground">Content Standard:</span> {lesson.content_standard}</p>
            )}
            {lesson.indicators && lesson.indicators.length > 0 && (
              <div>
                <p className="mb-1 text-muted-foreground">Indicators:</p>
                <ul className="space-y-1">
                  {lesson.indicators.map((ind, i) => (
                    <li key={i} className="flex items-start gap-2.5">
                      <span
                        aria-hidden="true"
                        className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#04A9CE]"
                      />
                      <span>{ind}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {lesson.week_ending && (
              <p>
                <span className="text-muted-foreground">Source week ending:</span>{' '}
                {lesson.week_ending}
                {lesson.week_ending_derived ? ' (derived)' : ''}
              </p>
            )}
          </div>

          {/* Why this lesson? Which part of the teacher's scheme produced it.
              Collapsed by default so technical detail never crowds the lesson. */}
          <SourceAlignment className="mt-4" title="Source & alignment" provenance={lesson.provenance} />
          {lesson.provenance?.source_review_status === 'needs_review' && (
            <Banner tone="warning" title="This week needs review" className="mt-3">
              SchemeKnit could not fully read this week of your scheme. Your lesson is
              still editable — nothing has been guessed or filled in for you.
            </Banner>
          )}
        </SurfaceCard>

        {/* The lesson document — phased hierarchy, editable in place. */}
        <SurfaceCard data-lesson-plan className="px-5 py-5 sm:px-6">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <h2 className="text-base font-semibold text-[#102A43]">Lesson plan</h2>
              <p className="text-sm text-muted-foreground">
                Edit the sections below and save your changes
              </p>
            </div>
            <span className="text-xs text-muted-foreground">
              {aiStatus
                ? aiStatus.active
                  ? `AI active · provider: ${(aiStatus as any).provider_label || aiStatus.provider}`
                  : `AI unavailable${aiStatus.provider ? ` · ${aiStatus.provider}` : ''} — suggestions are disabled until one is available.`
                : ''}
            </span>
          </div>
          {regenNote && <Banner tone="success" className="mt-3">{regenNote}</Banner>}
          {aiWarning && <Banner tone="warning" className="mt-3">{aiWarning}</Banner>}

          {/* Objectives — read-only from the generator. */}
          {objectives.length > 0 && (
            <section className="mt-5" aria-label="Objectives">
              <h3 className={sectionHeading}>Objectives</h3>
              <ul className="mt-2 space-y-1.5">
                {objectives.map((obj, i) => (
                  <li key={i} className="flex items-start gap-2.5 text-sm">
                    <span
                      aria-hidden="true"
                      className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#102A43]"
                    />
                    <span>
                      {obj.description}
                      {obj.indicator_code && (
                        <span className="ml-2 font-mono text-xs text-[#04769B]">
                          {obj.indicator_code}
                        </span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <div className="mt-5">
            <Field label="Lesson Topic" htmlFor="lesson-topic">
              <Input
                id="lesson-topic"
                type="text"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
              />
            </Field>
          </div>

          {/* Phase 1 · Starter */}
          <section className="mt-5 border-t border-slate-100 pt-5" aria-label="Phase 1 Starter">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-[#102A43]">Phase 1 · Starter</h3>
              {suggestButton('introduction')}
            </div>
            <TextArea
              id="lesson-introduction"
              aria-label="Introduction / Starter"
              value={introduction}
              onChange={(e) => setIntroduction(e.target.value)}
              rows={4}
            />
          </section>

          {/* Phase 2 · Main Learning — fully editable, AI-suggestible (PART A/B). */}
          <section
            className="mt-5 border-t border-slate-100 pt-5"
            aria-label="Phase 2 Main Learning"
          >
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-[#102A43]">Phase 2 · Main Learning</h3>
              <Button
                size="sm"
                variant="outline"
                type="button"
                disabled={regenBusy !== null}
                onClick={() => handleRegenerate('main_activities')}
              >
                {regenBusy === 'main_activities' ? 'Generating...' : 'Suggest Main Learning'}
              </Button>
            </div>

            {mainActivities.length === 0 && (
              <p className="mb-2 text-sm text-muted-foreground">
                No main learning activities yet.
              </p>
            )}

            <div className="space-y-3">
              {mainActivities.map((act, i) => (
                <div key={i} className="rounded-lg border border-slate-200 bg-slate-50/60 p-3">
                  <div className="mb-1.5 flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                      Activity {i + 1}
                    </span>
                    <div className="flex items-center gap-1">
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        aria-label={`Move activity ${i + 1} up`}
                        disabled={i === 0}
                        onClick={() => moveActivity(i, -1)}
                      >
                        <ChevronUp className="h-4 w-4" />
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        aria-label={`Move activity ${i + 1} down`}
                        disabled={i === mainActivities.length - 1}
                        onClick={() => moveActivity(i, 1)}
                      >
                        <ChevronDown className="h-4 w-4" />
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        aria-label={`Remove activity ${i + 1}`}
                        onClick={() => removeActivity(i)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                  <TextArea
                    aria-label={`Activity ${i + 1} description`}
                    value={act.description}
                    onChange={(e) => updateActivity(i, { description: e.target.value })}
                    rows={2}
                  />
                  <div className="mt-2 flex items-center gap-2">
                    <label
                      htmlFor={`activity-duration-${i}`}
                      className="text-xs text-muted-foreground"
                    >
                      Duration
                    </label>
                    <Input
                      id={`activity-duration-${i}`}
                      type="number"
                      min={1}
                      value={act.duration_minutes ?? ''}
                      onChange={(e) => {
                        const n = parseInt(e.target.value, 10)
                        updateActivity(i, { duration_minutes: Number.isFinite(n) && n > 0 ? n : null })
                      }}
                      className="h-9 w-24"
                    />
                    <span className="text-xs text-muted-foreground">min</span>
                  </div>
                </div>
              ))}
            </div>

            <Button
              type="button"
              size="sm"
              variant="outline"
              className="mt-3"
              onClick={addActivity}
            >
              <Plus className="mr-1.5 h-4 w-4" />
              Add activity
            </Button>
          </section>

          {/* Assessment */}
          <section className="mt-5 border-t border-slate-100 pt-5" aria-label="Assessment">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-[#102A43]">Assessment</h3>
              {suggestButton('assessment')}
            </div>
            <TextArea
              id="lesson-assessment"
              aria-label="Assessment"
              value={assessment}
              onChange={(e) => setAssessment(e.target.value)}
              rows={3}
            />
          </section>

          {/* Phase 3 · Plenary */}
          <section className="mt-5 border-t border-slate-100 pt-5" aria-label="Phase 3 Plenary">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-[#102A43]">Phase 3 · Plenary</h3>
              {suggestButton('conclusion')}
            </div>
            <TextArea
              id="lesson-conclusion"
              aria-label="Conclusion / Reflection"
              value={conclusion}
              onChange={(e) => setConclusion(e.target.value)}
              rows={3}
            />
          </section>

          {/* Keywords */}
          <section className="mt-5 border-t border-slate-100 pt-5" aria-label="Keywords">
            <h3 className="mb-2 text-sm font-semibold text-[#102A43]">Keywords</h3>
            <Field label="Keywords / Vocabulary" htmlFor="lesson-keywords">
              <Input
                id="lesson-keywords"
                type="text"
                value={keywords.join(', ')}
                onChange={(e) => setKeywords(e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                placeholder="Comma-separated"
              />
            </Field>
          </section>

          {/* TLRs — from the scheme of learning, read-only. */}
          {!!(lesson.source_tlrs?.length) && (
            <section className="mt-5 border-t border-slate-100 pt-5" aria-label="Teaching and Learning Resources">
              <h3 className="text-sm font-semibold text-[#102A43]">Teaching &amp; Learning Resources</h3>
              <p className="mt-1 text-xs text-muted-foreground">From your scheme of learning</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {lesson.source_tlrs!.map((r, i) => (
                  <span key={i} className="rounded bg-[#102A43]/8 px-2 py-1 text-sm text-[#102A43]">
                    {r}
                  </span>
                ))}
              </div>
            </section>
          )}

          {/* Other TLRs — teacher additions. */}
          <section className="mt-5 border-t border-slate-100 pt-5" aria-label="Other TLRs">
            <h3 className="mb-2 text-sm font-semibold text-[#102A43]">Other TLRs</h3>
            <Field
              label="Other Teaching & Learning Resources"
              htmlFor="lesson-other-tlrs"
              hint="Teacher additions — not from the scheme"
            >
              <Input
                id="lesson-other-tlrs"
                type="text"
                value={otherTlrs.join(', ')}
                onChange={(e) => setOtherTlrs(e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                placeholder="Comma-separated teacher additions"
              />
            </Field>
          </section>

          {/* Core Competencies */}
          <section className="mt-5 border-t border-slate-100 pt-5" aria-label="Core Competencies">
            <h3 className="mb-2 text-sm font-semibold text-[#102A43]">Core Competencies</h3>
            <div className="flex flex-wrap gap-1.5">
              {NACCA_COMPETENCIES.map(label => {
                const selected = coreCompetencies.includes(label)
                return (
                  <button
                    key={label}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => setCoreCompetencies(prev =>
                      selected ? prev.filter(c => c !== label) : [...prev, label]
                    )}
                    className={`rounded border px-2 py-1 text-xs ${
                      selected
                        ? 'border-[#102A43] bg-[#102A43] text-white'
                        : 'bg-background text-muted-foreground'
                    }`}
                  >
                    {label}
                  </button>
                )
              })}
            </div>
          </section>

          {/* References */}
          <section className="mt-5 border-t border-slate-100 pt-5" aria-label="References">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-[#102A43]">References</h3>
              <Button
                size="sm"
                variant="outline"
                type="button"
                onClick={() => setStructuredRefs(prev => [
                  ...prev,
                  { type: 'Other', title: '', author_publisher: '', page: '', notes: '' },
                ])}
              >
                + Add reference
              </Button>
            </div>
            {/* PART L/M: 3 empty entry slots by default; + Add reference
                appends another. Empty slots are not persisted on save. */}
            {structuredRefs.length === 0 && (
              <p className="mb-2 text-xs text-muted-foreground">
                No references yet — fill a slot below or add one.
              </p>
            )}
            {structuredRefs.map((ref, idx) => (
              <div key={idx} className="mb-2 grid grid-cols-12 gap-2">
                <Select
                  value={ref.type}
                  onChange={(e) => setStructuredRefs(prev => prev.map((r, i) =>
                    i === idx ? { ...r, type: e.target.value } : r
                  ))}
                  className="col-span-4 h-9 px-2 text-sm"
                  aria-label="Reference type"
                >
                  {REFERENCE_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                </Select>
                <Input
                  type="text"
                  value={ref.title}
                  onChange={(e) => setStructuredRefs(prev => prev.map((r, i) =>
                    i === idx ? { ...r, title: e.target.value } : r
                  ))}
                  placeholder="Title"
                  className="col-span-5 h-9 px-2 text-sm"
                />
                <Input
                  type="text"
                  value={ref.page || ''}
                  onChange={(e) => setStructuredRefs(prev => prev.map((r, i) =>
                    i === idx ? { ...r, page: e.target.value } : r
                  ))}
                  placeholder="Page (optional)"
                  className="col-span-3 h-9 px-2 text-sm"
                />
              </div>
            ))}
          </section>

          {/* Save */}
          <div className="mt-6 flex flex-wrap items-center gap-3 border-t border-slate-100 pt-4">
            <Button onClick={handleSave} disabled={saving}>
              {saving ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <Save className="mr-2 h-4 w-4" />
                  Save Changes
                </>
              )}
            </Button>
            {saved && (
              <span className="flex items-center text-sm text-green-600">
                <CheckCircle className="mr-1 h-4 w-4" />
                Saved
              </span>
            )}
          </div>
          {error && <Banner tone="danger" className="mt-4">{error}</Banner>}
        </SurfaceCard>
      </main>
    </div>
  )
}
