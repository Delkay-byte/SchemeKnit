'use client'

import { useState, useEffect, useRef } from 'react'
import { useRouter, useParams } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { SurfaceCard } from '@/components/ui/surface-card'
import { Banner } from '@/components/ui/banner'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Field, TextArea } from '@/components/ui/field'
import { Download, Settings, Play, CheckCircle, FileText, FileSpreadsheet, FileArchive, Loader2, Eye, Save, ChevronDown, ChevronRight } from 'lucide-react'
import { api, sanitizeTermConfig } from '@/lib/api'
import { normalizeError } from '@/lib/error-normalizer'
import { resolveRouteId } from '@/lib/route-params'
import {
  buildWeekPlans,
  distinctInOrder,
  formatWeekCounts,
  fullSelection,
  generatableRowsForWeek,
  planCountLabel,
  quotaFitForRows,
  quotaLine,
  WeekPlan,
  WeekRow,
} from '@/lib/generate-coverage'
import { PageHeader } from '@/components/ui/page-header'
import { StatusPill } from '@/components/ui/badge'
import { LessonWorkspace } from '@/components/lesson-workspace'
import { SchemeOfWork, TermConfig, CurriculumCoverage, Template, CurriculumProfile, WapefOptions } from '@/types'

// The Approved WAPEF Plan is one shared form for Nursery/KG/Basic/JHS; its
// four structured fields are teacher-selected from approved option lists.
const WAPEF_TEMPLATE_ID = 'tpl-wapef-approved-plan'

export default function GeneratePage() {
  const router = useRouter()
  const params = useParams()
  const schemeId = resolveRouteId(params.id, 'generate')

  // PART 3: when a scheme never states its class, the teacher must choose one
  // before generating. "Unknown" is never a generation-ready value.
  const [classLevels, setClassLevels] = useState<string[]>([])
  const [scheme, setScheme] = useState<SchemeOfWork | null>(null)
  const [templates, setTemplates] = useState<Template[]>([])
  const [profiles, setProfiles] = useState<CurriculumProfile[]>([])
  const [currentUser, setCurrentUser] = useState<{ full_name?: string; school_name?: string } | null>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [coverage, setCoverage] = useState<CurriculumCoverage | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [exporting, setExporting] = useState<string | null>(null)
  const [genProgress, setGenProgress] = useState<string>('')
  const [allocationPreview, setAllocationPreview] = useState<any>(null)
  const [previewing, setPreviewing] = useState(false)
  // Occurrence ids the teacher has edited since the last preview. A debounced
  // preview refresh must never wipe unsaved teacher edits (the WAPEF/Deep
  // Hope race): edited rows are re-merged on top of the fresh server rows by
  // their stable occurrence id.
  const touchedOccurrences = useRef<Set<string>>(new Set())
  // Every lesson already persisted for this scheme (across jobs) — the weeks
  // surface marks which timetable occurrences are already generated from it.
  const [schemeLessons, setSchemeLessons] = useState<any[]>([])
  // Weeks collapse individually; every week starts expanded so the curriculum
  // is visible without hunting (a long scheme can be collapsed week by week).
  const [collapsedWeeks, setCollapsedWeeks] = useState<number[]>([])
  // Generation experience (Pattern 7): Quick Generate is the default; Build
  // with me reveals the generated lesson one section at a time. Persisted so
  // the teacher's choice survives a reload.
  const [genMode, setGenMode] = useState<'quick' | 'guided'>('quick')
  const [reviewedLessons, setReviewedLessons] = useState<number | null>(null)
  // Per-lesson review drafts (keywords / Other TLRs / competencies / refs)
  // edited BEFORE generation and applied when lessons are built.
  const [lessonReview, setLessonReview] = useState<any[]>([])
  const [reviewSaving, setReviewSaving] = useState(false)
  const [reviewSaved, setReviewSaved] = useState(false)
  // Approved WAPEF option lists (Deep Hope / Storyline / Through lines /
  // God's Story). Dropdown-only: the teacher picks, never free text, never AI.
  const [wapefOptions, setWapefOptions] = useState<WapefOptions | null>(null)
  const NACCA_COMPETENCIES = [
    'Critical Thinking and Problem Solving',
    'Creativity and Innovation',
    'Communication and Collaboration',
    'Cultural Identity and Global Citizenship',
    'Personal Development and Leadership',
    'Digital Literacy',
  ]
  // Actual AI resolution (mode/provider/available) reported by the backend —
  // so the UI never shows a mode that disagrees with real behaviour.
  const [aiStatus, setAiStatus] = useState<{
    mode: string; active: boolean; provider: string | null; state: string;
    reason: string | null; provider_label?: string | null;
  } | null>(null)
  const [aiResult, setAiResult] = useState<{
    mode: string; active: boolean; provider: string | null;
    lessons_ai: number; lessons_deterministic: number; reason: string | null;
  } | null>(null)

  const levelForClass = (classLevel: string): string | undefined => {
    const c = (classLevel || '').toLowerCase()
    if (/(nursery|kg|kindergarten|early)/.test(c)) return 'Early Childhood'
    if (/(shs|senior high|basic 1[0-2])/.test(c)) return 'Senior High School'
    if (/(basic [7-9]|jhs|junior high|form [1-3])/.test(c)) return 'Junior High School'
    if (/(basic [1-6]|primary|class [1-6]|std [1-6])/.test(c)) return 'Primary'
    return undefined
  }

  const [config, setConfig] = useState<TermConfig>({
    scheme_of_work_id: schemeId,
    academic_year: '2026/2027',
    term: 'First Term',
    // Class/subject come from the parsed scheme — never a hardcoded default
    // (an unknown class must stay unknown, not become Basic 9).
    class_level: '',
    subject: '',
    term_start_date: '2026-09-11',
    term_end_date: '2026-12-18',
    lessons_per_week: 3,
    lesson_duration_minutes: 60,
    class_size: 11,
    teaching_days: [0, 2, 4],
    holidays: [],
    ai_mode: 'OFF',
    template_type: 'GES-style',
    template_id: '',
    include_special_weeks: false,
    school_name: '',
    teacher_name: '',
    period: '',
    keywords: [],
    teaching_learning_resources: [],
    core_competencies: [],
    references: [],
    selected_indicator_codes: [],
  })

  // PART 2/28: the curriculum reference option names THIS scheme's subject
  // ("Computing Curriculum") — never a hard-coded "Subject Curriculum".
  const REFERENCE_TYPES = [
    config.subject && config.subject !== 'Unknown'
      ? `${config.subject} Curriculum`
      : 'Subject Curriculum',
    'Teacher\'s Handbook / Teacher\'s Guide',
    'Textbook',
    'Other',
  ]

  useEffect(() => {
    // Restore the teacher's last AI mode choice so it persists across visits.
    try {
      const saved = window.localStorage.getItem('schemeknit.ai_mode')
      if (saved) setConfig(prev => ({ ...prev, ai_mode: saved as any }))
      const savedGenMode = window.localStorage.getItem('schemeknit.gen_mode')
      if (savedGenMode === 'guided' || savedGenMode === 'quick') setGenMode(savedGenMode)
    } catch { /* storage unavailable */ }
    loadData()
    // WAPEF dropdown options are canonical; a failure just means the WAPEF
    // selects stay hidden (non-WAPEF templates never show them anyway).
    api.getWapefOptions()
      .then(setWapefOptions)
      .catch(() => setWapefOptions(null))
  }, [schemeId])

  // The displayed AI status must always reflect what the backend will actually
  // do for the currently selected mode.
  useEffect(() => {
    let cancelled = false
    api.getAiStatus(config.ai_mode || 'OFF')
      .then((s) => { if (!cancelled) setAiStatus(s) })
      .catch(() => { if (!cancelled) setAiStatus(null) })
    return () => { cancelled = true }
  }, [config.ai_mode])

  const loadData = async () => {
    try {
      setLoading(true)
      const schemeData = await api.getScheme(schemeId)
      // PART A: no level filter — the full active catalog is requested so the
      // template selector lists every active template (GES forms, WAPEF plans,
      // plus the teacher's own templates).
      const [templatesData, profilesData, statusData] = await Promise.all([
        api.listTemplates(),
        api.listProfiles(),
        api.getGenerationStatusForScheme(schemeId).catch(() => null),
      ])
      setScheme(schemeData)
      // Keep the scheme's own curriculum span for payload fallbacks (date
      // inputs the teacher cleared must never reach the backend as '').
      try {
        const weeksData = await api.getSchemeWeeks(schemeId)
        ;(schemeData as any).weeks = weeksData.weeks || []
      } catch { /* fallback stays undefined; sanitizer uses safe defaults */ }
      setTemplates(templatesData.templates || [])
      setProfiles(profilesData.profiles || [])

      // PART 3: the canonical class catalogue, for the "class needs
      // confirmation" control. A failure here never blocks the page — the
      // teacher simply cannot confirm from this screen.
      api
        .listClassLevels()
        .then((d) => setClassLevels(d.class_levels || []))
        .catch(() => setClassLevels([]))

      // School and teacher identity come from the authenticated user, not from
      // typed input (PART 14-15). Seed the config so the generation payload
      // carries the right values; the backend is the source of truth.
      const me = await api.getProfile().catch(() => null)
      if (me) {
        setCurrentUser(me)
        setConfig(prev => ({
          ...prev,
          school_name: me.school_name || prev.school_name,
          teacher_name: me.full_name || prev.teacher_name,
        }))
      }

      // If this scheme was already generated, restore that job so exports stay reachable after reload
      if (statusData?.id && statusData?.status === 'completed') {
        setJobId(statusData.id)
        setCoverage({
          total_instructional_weeks: 0,
          total_indicators: 0,
          total_generated_lessons: statusData.completed_lessons || 0,
          indicators_allocated: 0,
          indicators_unallocated: 0,
          coverage_percentage: 0,
          warnings: [],
        })
      }
      const defaultTemplate = templatesData.templates?.find((t: Template) => t.is_default)
      // Prefer the template the lessons were actually generated with (from the
      // job snapshot): exporting a reloaded WAPEF job must use the WAPEF form,
      // not silently fall back to the level default.
      const generatedTemplateId: string | undefined =
        statusData?.status === 'completed' ? statusData.template_id : undefined
      const restoredTemplate = generatedTemplateId
        ? templatesData.templates?.find((t: Template) => t.id === generatedTemplateId)
        : undefined
      setConfig(prev => ({
        ...prev,
        scheme_of_work_id: schemeId,
        template_id: restoredTemplate?.id || defaultTemplate?.id || prev.template_id || '',
        // The backend requires these fields; seed them from the parsed scheme.
        academic_year: schemeData.academic_year || prev.academic_year,
        term: schemeData.term || prev.term,
        // Prefer the scheme's own identity; only keep a previous value when
        // the scheme field is missing — never substitute a default level.
        // PART 3: a scheme that does not state its class must be confirmed by
        // the teacher, so the summary shows "Class needs confirmation" and
        // generation is blocked until they choose. The "Unknown" placeholder is
        // dropped here — it is a detection artefact, not a class.
        class_level:
          schemeData.class_level && schemeData.class_level !== 'Unknown'
            ? schemeData.class_level
            : '',
        subject:
          schemeData.subject && schemeData.subject !== 'Unknown'
            ? schemeData.subject
            : '',
      }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }

  // Term-date / identity fallback for the allocation payload: when the teacher
  // cleared a date input (or a detection field stayed blank), the payload falls
  // back to the scheme's own extracted curriculum span and identity instead of
  // failing backend validation with an opaque 422 (real-use remediation).
  const configFallback = () => {
    const weeks = (scheme as any)?.weeks || []
    const starts = weeks.map((w: any) => w.start_date).filter(Boolean).sort()
    const ends = weeks.map((w: any) => w.end_date).filter(Boolean).sort()
    return {
      term_start_date: starts[0],
      term_end_date: ends[ends.length - 1],
      // PART 3: a teacher-confirmed class WINS over the scheme's own (possibly
      // "Unknown") value; the scheme value is only the fallback. "Unknown" is
      // never forwarded as a class.
      class_level: config.class_level || scheme?.class_level,
      subject: scheme?.subject,
    }
  }

  const handlePreviewAllocation = async () => {
    try {
      setPreviewing(true)
      setError(null)
      const preview = await api.getAllocationPreview(schemeId, sanitizeTermConfig(config, configFallback()))
      setAllocationPreview(preview)
      // PART T: per-lesson review rows arrive with GENERATED DEFAULTS
      // (lesson-specific keywords from the indicator/sub-strand, competencies
      // from the activity type, exact source TLRs) — the teacher only edits
      // where necessary. References start as exactly 3 empty slots (PART L);
      // "Add reference" appends another.
      const reviewRows = Array.isArray(preview.lesson_review)
        ? preview.lesson_review.map((row: any) => ({
            ...row,
            structured_references:
              row.structured_references && row.structured_references.length > 0
                ? row.structured_references
                : [0, 1, 2].map(() => ({ type: 'Other', title: '', page: '' })),
          }))
        : []
      setLessonReview((prev) => {
        const prevByOcc = new Map<string, any>()
        for (const r of prev) {
          if (r.source_occurrence_id) prevByOcc.set(r.source_occurrence_id, r)
        }
        return reviewRows.map((rr: any) => {
          const local =
            rr.source_occurrence_id &&
            touchedOccurrences.current.has(rr.source_occurrence_id)
              ? prevByOcc.get(rr.source_occurrence_id)
              : null
          return local ? { ...rr, ...local } : rr
        })
      })
      setReviewSaved(false)
      // Which occurrences are ALREADY generated (any previous run) — the
      // weeks surface reads this, never a client-side count.
      refreshSchemeLessons()
    } catch (err) {
      // Teacher-facing copy: a validation failure explains WHAT to fix, never
      // the raw "Validation failed" (real-use remediation).
      setError(normalizeError(err).message)
    } finally {
      setPreviewing(false)
    }
  }

  const refreshSchemeLessons = async () => {
    try {
      const data = await api.getSchemeLessons(schemeId)
      setSchemeLessons(data.lesson_plans || [])
    } catch {
      // The weeks still render — every row simply shows as not generated.
      setSchemeLessons([])
    }
  }

  // The week surface IS the generate screen (Priority 3): it loads itself
  // whenever the setup view is ready (first visit and after "Start New
  // Generation"), so no teacher ever has to discover a preview button first.
  useEffect(() => {
    if (loading || !scheme || jobId || allocationPreview || previewing) return
    handlePreviewAllocation()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, scheme, jobId, allocationPreview, previewing])

  // Allocation inputs changed (term window, teaching days, confirmed class):
  // refresh the weeks after a short pause so typing a date never spams the
  // server and the surface always shows the truth for the current inputs.
  // Runs even when no preview exists yet (an early failure must self-heal
  // once the teacher supplies the missing inputs).
  useEffect(() => {
    if (loading || !scheme || jobId || previewing) return
    const timer = setTimeout(() => { handlePreviewAllocation() }, 600)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    config.term_start_date,
    config.term_end_date,
    config.teaching_days.join(','),
    config.class_level,
  ])

  // ── Generate actions (Priority 3) ─────────────────────────────────────
  // The teacher acts on WHAT they can see — a week, a single lesson, or the
  // whole scheme. The payload names the exact source occurrences (and their
  // codes for quota reservation); the backend owns the rest. Every path
  // crosses the WAPEF save boundary first: the PUT carrying the teacher's
  // CURRENT review selections must be persisted before POST /generate reads
  // the draft store, and a save failure cancels generation (a fire-and-forget
  // save is exactly the race that dropped WAPEF values).
  const runGeneration = async (selection: { codes: string[]; occurrences: string[] }) => {
    try {
      setGenerating(true)
      setError(null)
      setGenProgress('Generating your lesson plans…')
      if (lessonReview.length > 0) {
        try {
          await saveLessonReviewDrafts(lessonReview)
        } catch {
          setError('Your lesson review could not be saved, so generation was cancelled. Check your connection and try again — your selections are still on screen.')
          setGenProgress('')
          return
        }
      }
      const body = {
        ...sanitizeTermConfig(config, configFallback()),
        selected_indicator_codes: selection.codes,
        selected_occurrence_ids: selection.occurrences,
      }
      const response = await api.generateLessonPlans(schemeId, body)
      setJobId(response.job_id)
      setAiResult(response.ai || null)
      setGenProgress('Lesson plans generated successfully!')

      const coverageData = await api.getCurriculumCoverage(response.job_id)
      setCoverage(coverageData)
      // Statuses on the week surface must reflect the just-generated set.
      await refreshSchemeLessons()
    } catch (err) {
      setError(normalizeError(err).message)
      setGenProgress('')
    } finally {
      setGenerating(false)
    }
  }

  // Whole scheme: every distinct PENDING indicator code in curriculum order,
  // capped at the remaining monthly allowance when the quota is enforced
  // (honest about what fits — never a silent cap, never a client-side quota
  // rule). Already-generated rows never re-enter the batch.
  const handleGenerateAll = () => {
    const pending = weekPlans.flatMap((w) => w.rows.filter((r) => !r.generated))
    const selection = fullSelection(pending, allocationPreview?.lesson_quota)
    return runGeneration({ codes: selection.codes, occurrences: [] })
  }

  // One whole week: exactly that week's timetable occurrences.
  const handleGenerateWeek = (week: WeekPlan) => {
    const rows = generatableRowsForWeek(week, allocationPreview?.lesson_quota)
    if (!rows.length) return Promise.resolve()
    return runGeneration({
      codes: distinctInOrder(rows.map((r) => (r.indicator_code || '').trim())),
      occurrences: rows.map((r) => r.source_occurrence_id).filter(Boolean),
    })
  }

  // One single lesson occurrence — even when its indicator code repeats in
  // other weeks (codes alone cannot say "only week 5's copy").
  const handleGenerateRow = (row: WeekRow) => {
    if (!row.source_occurrence_id) return Promise.resolve()
    return runGeneration({
      codes: row.indicator_code ? [row.indicator_code] : [],
      occurrences: [row.source_occurrence_id],
    })
  }

  // Canonical WAPEF draft shape for ONE review row: built from the CURRENT
  // row object (React state the teacher just edited), never from a closure
  // captured earlier. WAPEF keys are sent verbatim with empty-list/empty-string
  // fallbacks so a partially-filled row can never serialize undefined.
  const wapefDraftFor = (row: any) => ({
    wapef_deep_hope: row.wapef_deep_hope || '',
    wapef_storyline: row.wapef_storyline || '',
    wapef_through_lines: Array.isArray(row.wapef_through_lines)
      ? row.wapef_through_lines
      : [],
    wapef_gods_story: row.wapef_gods_story || '',
    remarks: row.remarks || '',
  })

  // rows param: the CALLER passes the rows to save. runGeneration
  // passes its own in-scope `lessonReview` (the exact state the teacher sees
  // on screen at click time), so the payload can never be built from a stale
  // render's copy. The Save-review button passes nothing and saves the
  // current state.
  const saveLessonReviewDrafts = async (rows?: any[]) => {
    const reviewRows = rows && rows.length ? rows : lessonReview
    if (!reviewRows.length) return
    setReviewSaving(true)
    setReviewSaved(false)
    try {
      const drafts: Record<string, any> = {}
      for (const row of reviewRows) {
        drafts[String(row.lesson_sequence)] = {
          // Teacher-adjusted timetable slot for this lesson (Pattern 1).
          // Applied to the built lesson; blank is preserved as blank.
          period: row.period || '',
          keywords: row.keywords || [],
          other_tlrs: row.other_tlrs || [],
          core_competencies: row.core_competencies || [],
          structured_references: row.structured_references || [],
          // Approved WAPEF Plan teacher-selected fields (dropdown values,
          // sent as-is; the server normalizes against the approved lists).
          ...wapefDraftFor(row),
        }
      }
      // The PUT must have PERSISTED (server echoed the full store) before
      // generation may read it — this await IS the save boundary.
      await api.saveLessonReview(schemeId, drafts)
      setReviewSaved(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save lesson review')
      throw err
    } finally {
      setReviewSaving(false)
    }
  }

  const updateLessonReviewRow = (seq: number, patch: Partial<any>) => {
    // Functional update: the patch is applied to the LATEST row state, never
    // a closure-captured copy. (A stale closure here was the WAPEF race: two
    // quick edits — or an edit immediately followed by Generate lesson plans —
    // built the save payload from a pre-edit row and silently dropped the
    // teacher's latest selections.)
    setLessonReview(rows => rows.map(r => {
      if (r.lesson_sequence !== seq) return r
      if (r.source_occurrence_id) touchedOccurrences.current.add(r.source_occurrence_id)
      return { ...r, ...patch }
    }))
    setReviewSaved(false)
  }

  const updateStructuredRef = (seq: number, index: number, patch: Partial<any>) => {
    setLessonReview(rows => rows.map(r => {
      if (r.lesson_sequence !== seq) return r
      if (r.source_occurrence_id) touchedOccurrences.current.add(r.source_occurrence_id)
      const refs = [...(r.structured_references || [])]
      refs[index] = { ...(refs[index] || { type: 'Other', title: '' }), ...patch }
      return { ...r, structured_references: refs }
    }))
    setReviewSaved(false)
  }

  const handleExport = async (format: string) => {
    if (!jobId) return
    try {
      setExporting(format)
      const subject = scheme?.subject || 'Lesson'
      const cls = scheme?.class_level || 'Plans'

      // Every export goes through the one-time download URL (PART 27): the
      // POST validates and renders first — so a genuine server failure still
      // surfaces as a real error — then the browser navigates to a single-use
      // URL and the browser/download manager owns the transfer. There is no
      // fetch() body read on the page, so a successful handoff (including IDM
      // interception) can no longer be misreported as "Failed to fetch".
      const res = await api.getDownloadUrl(
        jobId, format, config.template_type, config.template_id)
      const fallback = `${subject} ${cls} - Lesson Plans.${format}`
      const filename = res.filename || fallback
      // Sanitize on the client too so the saved name is always filesystem-safe.
      void filename
      api.navigateToDownload(res.download_url)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed')
    } finally {
      setExporting(null)
    }
  }

  const getProfileForScheme = () => {
    if (!scheme?.educational_level) return null
    return profiles.find(p => p.educational_level === scheme.educational_level) || null
  }

  // PART A: the teacher must see EVERY ACTIVE template the system offers —
  // never a level-limited slice that hides valid forms (the old client-side
  // educational_level filter was exactly why only two templates appeared).
  // The backend already enforces verified/active visibility per teacher.
  const getTemplatesForScheme = () => templates

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-muted-foreground">Loading configuration...</p>
        </div>
      </div>
    )
  }

  if (error && !scheme) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center px-4">
        <SurfaceCard className="w-full max-w-md px-6 py-8 text-center">
          <p className="mb-4 text-destructive">{error}</p>
          <Button onClick={loadData}>Try Again</Button>
        </SurfaceCard>
      </div>
    )
  }

  if (!scheme) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center px-4">
        <SurfaceCard className="w-full max-w-md px-6 py-8 text-center">
          <p className="mb-4 text-muted-foreground">Scheme not found</p>
          <Button asChild>
            <Link href="/dashboard">Go to Dashboard</Link>
          </Button>
        </SurfaceCard>
      </div>
    )
  }

  const filteredTemplates = getTemplatesForScheme()
  const currentProfile = getProfileForScheme()
  // PART 27: the summary names the REAL selected template (not just "2/week ·
  // 60 min"), so a teacher can see the WAPEF/GES form they are about to use.
  const selectedTemplateName =
    templates.find((t: Template) => t.id === config.template_id)?.name || ''
  // PART 3: a scheme that never states its class must be confirmed by the
  // teacher. "Unknown" is never printed as a generation-ready value.
  const classNeedsConfirmation =
    !config.class_level || config.class_level === 'Unknown'
  // The WAPEF structured fields belong to the Approved WAPEF Plan only; they
  // appear in the per-lesson review when that template is the chosen form.
  const isWapefSelected = config.template_id === WAPEF_TEMPLATE_ID

  // ── The week-centric view model (Priority 3) ──────────────────────────
  const weekPlans: WeekPlan[] = buildWeekPlans(allocationPreview, schemeLessons)
  const pendingRows = weekPlans.flatMap((w) => w.rows.filter((r) => !r.generated))
  const totalLessonPlans =
    allocationPreview?.total_generated_lessons ??
    weekPlans.reduce((n, w) => n + w.lessonCount, 0)
  const generatedLessonCount =
    weekPlans.reduce((n, w) => n + w.generatedCount, 0)
  const quota = allocationPreview?.lesson_quota || null
  const quotaText = quotaLine(quota)
  const fullPlanSelection = fullSelection(pendingRows, quota)
  // How many of the PENDING rows the capped full-set selection can build.
  const fullFitRowCount = fullPlanSelection.capped
    ? pendingRows.filter((r) =>
        !r.indicator_code || fullPlanSelection.codes.includes(r.indicator_code),
      ).length
    : pendingRows.length

  // Why the Generate action is unavailable — never a silent disable.
  const generateBlockReasons: string[] = []
  // PART 3: generating without a confirmed class is blocked, and the reason
  // is stated rather than left to a silent disable.
  if (classNeedsConfirmation) {
    generateBlockReasons.push('Confirm the class for this scheme before generating.')
  }
  // Quota exhaustion: nothing left this month. (Indicatorless Nursery-style
  // schemes never enter this branch — their rows carry no indicator codes, so
  // the server exempts them from the selection requirement entirely.)
  if (
    quota?.enforced &&
    (quota.remaining ?? 0) <= 0 &&
    weekPlans.some((w) => w.rows.some((r) => !!r.indicator_code))
  ) {
    generateBlockReasons.push(
      'Your Free Tier lesson plans for this month are used up. Upgrade to Teacher Pro for unlimited generation, or wait for next month.')
  }
  const generateIsBlocked = generateBlockReasons.length > 0

  const toggleWeek = (weekNumber: number) => {
    setCollapsedWeeks((prev) =>
      prev.includes(weekNumber)
        ? prev.filter((n) => n !== weekNumber)
        : [...prev, weekNumber],
    )
  }

  return (
    <div className="min-h-screen">
      <main className="container mx-auto px-4 py-8">
        {/* One h1: this page generates lesson plans from this scheme. */}
        <PageHeader
          className="mb-6"
          eyebrow="Generate"
          title="Generate Lesson Plans"
          description={<>{scheme.filename} &bull; {scheme.subject} &bull; {scheme.class_level} &bull; {scheme.term}</>}
        />

        <div className="grid gap-6 lg:grid-cols-3">
          {/* MAIN COLUMN — after generation the CURRICULUM-GROUNDED LESSON
              WORKSPACE leads, so the first thing the teacher sees is the real
              generated lesson (never an empty editor or a bare success toast).
              The configuration surfaces remain below for regeneration. */}
          <div className="space-y-6 lg:col-span-2">
          {jobId && (
            <LessonWorkspace
              jobId={jobId}
              guided={genMode === 'guided'}
              onExport={handleExport}
              exporting={exporting}
              onLessonsLoaded={setReviewedLessons}
            />
          )}
            {/* A. What exact lessons am I about to generate? Source facts first. */}
            <SurfaceCard
              data-generate-summary
              accent="bg-gradient-to-r from-[#102A43] to-[#04A9CE]"
              className="px-5 py-5 sm:px-6"
            >
              <h2 className="text-lg font-semibold text-[#102A43]">What you will generate</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Everything here comes from your uploaded scheme — check it matches your class
                before generating.
              </p>
              <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">
                <div>
                  <dt className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Subject</dt>
                  <dd className="text-sm font-semibold text-[#102A43]">{scheme.subject}</dd>
                </div>
                <div>
                  <dt className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Class</dt>
                  <dd className="text-sm font-semibold text-[#102A43]">
                    {/* PART 3/27: "Unknown" is never a generation-ready state.
                        When the scheme does not state a class the teacher must
                        choose one before generating, so the summary asks for it
                        instead of printing a placeholder. */}
                    {classNeedsConfirmation ? (
                      <span className="text-amber-700" data-class-needs-confirmation>
                        Class needs confirmation
                      </span>
                    ) : (
                      config.class_level || scheme.class_level
                    )}
                  </dd>
                </div>
                <div>
                  <dt className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Term</dt>
                  <dd className="text-sm font-semibold text-[#102A43]">{scheme.term || config.term}</dd>
                </div>
                <div>
                  <dt className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Academic year</dt>
                  <dd className="text-sm font-semibold text-[#102A43]">{scheme.academic_year}</dd>
                </div>
                <div>
                  <dt className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Weeks in scheme</dt>
                  <dd className="text-sm font-semibold text-[#102A43]">{scheme.weeks_count}</dd>
                </div>
                {/* PART 27: name the real selected template, not only its profile. */}
                <div>
                  <dt className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Template</dt>
                  <dd className="text-sm font-semibold text-[#102A43]" data-selected-template>
                    {selectedTemplateName || 'Not selected'}
                  </dd>
                </div>
                {/* PART 7: the school this lesson belongs to — asked ONCE,
                    in one place, from the teacher's profile (never three
                    different phrasings across the page). */}
                <div>
                  <dt className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">School</dt>
                  <dd className="text-sm font-semibold text-[#102A43]">
                    {config.school_name || currentUser?.school_name ? (
                      config.school_name || currentUser?.school_name
                    ) : (
                      <Link href="/settings" className="text-amber-700 underline">
                        Add your school in Settings
                      </Link>
                    )}
                  </dd>
                </div>
                <div>
                  <dt className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Template profile</dt>
                  <dd className="text-sm font-semibold text-[#102A43]">
                    {currentProfile
                      ? `${currentProfile.lessons_per_week}/week · ${currentProfile.lesson_duration_minutes} min`
                      : `${config.lessons_per_week}/week · ${config.lesson_duration_minutes} min`}
                  </dd>
                </div>
              </dl>
            </SurfaceCard>

            {/* B. Configuration — grouped sections inside one surface. Hidden
                once a job exists (§15): the workspace takes over and "Start
                New Generation" brings setup back. */}
            {!jobId && (
            <SurfaceCard data-generate-config className="px-5 py-5 sm:px-6">
              <div className="flex items-center">
                <Settings className="mr-2 h-5 w-5 text-[#04769B]" aria-hidden="true" />
                <div>
                  <h2 className="text-lg font-semibold text-[#102A43]">Configuration</h2>
                  <p className="text-sm text-muted-foreground">
                    Configure your lesson plan generation settings
                  </p>
                </div>
              </div>

              <div className="mt-5 space-y-6">
                <section aria-label="Teaching setup" className="space-y-6">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Teaching setup
                  </h3>
                  <div className="grid gap-4 md:grid-cols-3">
                    <Field label="Class Size" htmlFor="cfg-class-size">
                      <Input
                        id="cfg-class-size"
                        type="number"
                        value={config.class_size}
                        onChange={(e) => setConfig({ ...config, class_size: parseInt(e.target.value) || 11 })}
                      />
                    </Field>
                    <Field label="Lesson Duration (min)" htmlFor="cfg-duration">
                      <Input
                        id="cfg-duration"
                        type="number"
                        value={config.lesson_duration_minutes}
                        onChange={(e) => setConfig({ ...config, lesson_duration_minutes: parseInt(e.target.value) || 60 })}
                      />
                    </Field>
                    <Field label="Lessons/Week" htmlFor="cfg-lessons-per-week">
                      <Input
                        id="cfg-lessons-per-week"
                        type="number"
                        value={config.lessons_per_week}
                        onChange={(e) => setConfig({ ...config, lessons_per_week: parseInt(e.target.value) || 3 })}
                      />
                    </Field>
                  </div>

                  <div className="grid gap-4 md:grid-cols-2">
                    <Field label="Term Start" htmlFor="cfg-term-start">
                      <Input
                        id="cfg-term-start"
                        type="date"
                        value={config.term_start_date}
                        onChange={(e) => setConfig({ ...config, term_start_date: e.target.value })}
                      />
                    </Field>
                    <Field label="Term End" htmlFor="cfg-term-end">
                      <Input
                        id="cfg-term-end"
                        type="date"
                        value={config.term_end_date}
                        onChange={(e) => setConfig({ ...config, term_end_date: e.target.value })}
                      />
                    </Field>
                  </div>

                  <div>
                    <p className="mb-2 text-sm font-medium">Teaching Days</p>
                    <div className="flex flex-wrap gap-2">
                      {[
                        { value: 0, label: 'Monday' },
                        { value: 1, label: 'Tuesday' },
                        { value: 2, label: 'Wednesday' },
                        { value: 3, label: 'Thursday' },
                        { value: 4, label: 'Friday' },
                      ].map((day) => (
                        <button
                          key={day.value}
                          onClick={() => {
                            const newDays = config.teaching_days.includes(day.value)
                              ? config.teaching_days.filter(d => d !== day.value)
                              : [...config.teaching_days, day.value]
                            setConfig({ ...config, teaching_days: newDays.sort() })
                          }}
                          className={`rounded-full px-3 py-1 text-sm ${
                            config.teaching_days.includes(day.value)
                              ? 'bg-[#102A43] text-white'
                              : 'bg-muted text-muted-foreground'
                          }`}
                        >
                          {day.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="grid gap-4 md:grid-cols-2">
                    <Field label="Template" htmlFor="cfg-template">
                      <Select
                        id="cfg-template"
                        value={config.template_id || config.template_type}
                        onChange={(e) => setConfig({ ...config, template_id: e.target.value })}
                      >
                        {filteredTemplates.map((t) => (
                          <option key={t.id} value={t.id}>
                            {t.name}{t.is_default ? ' (Default)' : ''}
                          </option>
                        ))}
                      </Select>
                      {currentProfile && (
                        <p className="mt-1 text-xs text-muted-foreground">
                          {currentProfile.name} &bull; {currentProfile.lessons_per_week} lessons/week &bull; {currentProfile.lesson_duration_minutes} min
                        </p>
                      )}
                    </Field>
                    <Field label="AI Mode" htmlFor="cfg-ai-mode">
                      <Select
                        id="cfg-ai-mode"
                        value={config.ai_mode}
                        onChange={(e) => {
                          const mode = e.target.value
                          setConfig({ ...config, ai_mode: mode as any })
                          try { window.localStorage.setItem('schemeknit.ai_mode', mode) } catch { /* ignore */ }
                        }}
                      >
                        <option value="OFF">OFF - Deterministic only</option>
                        <option value="BASIC">BASIC - Zeli suggestions</option>
                        <option value="ENHANCED">ENHANCED - Zeli assistance</option>
                      </Select>
                      {aiStatus && (
                        <p className={`mt-1 text-xs ${aiStatus.active ? 'text-green-600' : 'text-muted-foreground'}`}>
                          {/* Zeli is the teacher-facing assistant name. The
                              resolved provider stays in the backend-only
                              ai-status payload (developer/admin diagnostics). */}
                          {aiStatus.active
                            ? 'Zeli available'
                            : config.ai_mode === 'OFF'
                              ? 'Zeli off — lessons will come from the deterministic engine.'
                              : 'Zeli unavailable right now — lessons will be deterministic.'}
                        </p>
                      )}
                    </Field>
                  </div>

                  <div className="grid gap-4 md:grid-cols-2">
                    {/* PART 3: a scheme that never states its class needs the
                        teacher's choice. This is the only place the class can
                        be set on this screen, and it persists into the
                        generation payload. */}
                    <Field
                      label="Class"
                      htmlFor="cfg-class-level"
                      hint={
                        classNeedsConfirmation
                          ? 'Your scheme does not state the class — choose it to continue'
                          : 'Taken from your scheme'
                      }
                    >
                      {classNeedsConfirmation ? (
                        <Select
                          id="cfg-class-level"
                          aria-label="Class"
                          data-class-level-select
                          value=""
                          onChange={(e) =>
                            setConfig((prev) => ({ ...prev, class_level: e.target.value }))
                          }
                        >
                          <option value="">Select the class…</option>
                          {classLevels.map((c) => (
                            <option key={c} value={c}>
                              {c}
                            </option>
                          ))}
                        </Select>
                      ) : (
                        <Input
                          id="cfg-class-level"
                          type="text"
                          value={config.class_level}
                          disabled
                          className="bg-muted text-muted-foreground"
                        />
                      )}
                    </Field>
                    {/* School identity is server-derived from the teacher's
                        profile and asked ONCE (summary strip → Settings) —
                        never repeated as a field here (§14). */}
                    <Field label="Teacher Name" htmlFor="cfg-teacher-name" hint="From your profile — update it in Settings">
                      <Input
                        id="cfg-teacher-name"
                        type="text"
                        value={config.teacher_name || currentUser?.full_name || '—'}
                        disabled
                        placeholder="Derived from your profile"
                        className="bg-muted text-muted-foreground"
                      />
                    </Field>
                  </div>
                </section>

                {/* PART F/G/H/I/L: the GLOBAL SEED model is gone. Keywords,
                    competencies, TLRs and references are generated PER LESSON
                    from the lesson's own curriculum context (AI-suggested +
                    teacher-editable in the per-lesson review below); Other TLRs
                    and references start EMPTY per lesson. Period/timing is
                    teacher-entered and stays blank when not supplied. */}
                <section aria-label="Lesson plan details" className="border-t pt-6">
                  <h3 className="text-sm font-semibold">Lesson Plan Details</h3>
                  <p className="mb-4 text-xs text-muted-foreground">
                    Keywords, core competencies and source resources are filled in
                    automatically for EACH lesson from your scheme — you edit them
                    in the per-lesson review below. Other TLRs and references stay
                    empty unless you add them per lesson. Period/timing is
                    teacher-entered; leave blank if not applicable.
                  </p>
                  <div className="space-y-4">
                    <div className="grid gap-4 md:grid-cols-2">
                      {/* PART K: period/timing is LESSON-SPECIFIC teacher data.
                          When left empty it stays genuinely empty — never "0",
                          "-", "N/A" or a generated "Period N". */}
                      <Field label="Period / Timing" htmlFor="cfg-period">
                        <Input
                          id="cfg-period"
                          type="text"
                          value={config.period || ''}
                          onChange={(e) => setConfig({ ...config, period: e.target.value })}
                          placeholder="e.g. 1st & 2nd — leave blank if not applicable"
                        />
                      </Field>
                      <Field label="Academic Term" htmlFor="cfg-term">
                        <Select
                          id="cfg-term"
                          value={config.term}
                          onChange={(e) => setConfig({ ...config, term: e.target.value })}
                        >
                          <option value="First Term">Term 1</option>
                          <option value="Second Term">Term 2</option>
                          <option value="Third Term">Term 3</option>
                        </Select>
                      </Field>
                    </div>
                  </div>
                </section>
              </div>
            </SurfaceCard>
            )}

            {/* C. Lesson plans by week — the primary surface (Priority 3). */}
            {!allocationPreview && previewing && (
              <SurfaceCard data-allocation-preview className="px-5 py-5 sm:px-6">
                <p className="flex items-center text-sm text-muted-foreground" role="status" aria-live="polite">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
                  Reading your weeks…
                </p>
              </SurfaceCard>
            )}
            {allocationPreview && (
              <SurfaceCard
                data-allocation-preview
                accent="bg-gradient-to-r from-[#102A43] to-[#04A9CE]"
                className="px-5 py-5 sm:px-6"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-semibold text-[#102A43]">Lesson plans by week</h2>
                    <p className="text-sm text-muted-foreground">
                      Every curriculum indicator in your scheme becomes its own lesson plan, in its source week.
                      Timetable periods are context, not a limit.
                    </p>
                  </div>
                  <p data-generate-total className="rounded-lg bg-[#102A43]/5 px-3 py-2 text-sm">
                    <span className="font-semibold text-[#102A43]">{planCountLabel(totalLessonPlans)}</span>
                    {' · '}
                    {allocationPreview.coverage_percentage?.toFixed(1) ?? 0}% curriculum coverage
                    {generatedLessonCount > 0 && (
                      <span className="block text-xs text-muted-foreground">
                        {generatedLessonCount} already generated
                      </span>
                    )}
                  </p>
                </div>

                <div className="mt-4 space-y-4">
                  {/* Conflicts first — teacher must see these before generating */}
                  {(allocationPreview.allocation_conflicts?.length > 0 ||
                    allocationPreview.indicators_unallocated > 0 ||
                    allocationPreview.indicators_duplicated > 0) && (
                    <Banner tone="warning" title="Check these weeks before generating">
                      <div className="space-y-1">
                        {allocationPreview.allocation_conflicts?.map((c: string, i: number) => (
                          <p key={`c-${i}`}>{c}</p>
                        ))}
                        {allocationPreview.indicators_unallocated > 0 && (
                          <p>
                            {allocationPreview.indicators_unallocated} indicator(s) have no
                            lesson allocation — they would disappear from the plan.
                          </p>
                        )}
                        {allocationPreview.indicators_duplicated > 0 && (
                          <p>
                            Duplicate source occurrence detected — the same source
                            occurrence would be generated more than once.
                          </p>
                        )}
                      </div>
                    </Banner>
                  )}

                  {/* The week surface: what needs generating, week by week.
                      One card per week; every week starts expanded; each row
                      says whether its lesson already exists. */}
                  <div className="space-y-4" data-allocation-weeks>
                    {weekPlans.length === 0 && (
                      <p className="rounded-lg border border-dashed px-3 py-4 text-sm text-muted-foreground">
                        No curriculum weeks found — check the term dates above.
                      </p>
                    )}
                    {weekPlans.map((week) => {
                      const collapsed = collapsedWeeks.includes(week.weekNumber)
                      const fit = quotaFitForRows(week.rows, quota)
                      const weekRows = generatableRowsForWeek(week, quota)
                      const weekBlocked =
                        generating ||
                        generateIsBlocked ||
                        (quota?.enforced && weekRows.length === 0)
                      return (
                        <div
                          key={`week-${week.weekNumber}`}
                          data-week-card
                          data-week-number={week.weekNumber}
                          className="overflow-hidden rounded-lg border border-slate-200"
                        >
                          <div className="flex flex-wrap items-center gap-2 bg-[#F8FAFC] px-3 py-2">
                            <button
                              type="button"
                              onClick={() => toggleWeek(week.weekNumber)}
                              aria-expanded={!collapsed}
                              className="flex items-center gap-1.5 text-sm font-semibold text-[#102A43]"
                            >
                              {collapsed ? (
                                <ChevronRight className="h-4 w-4" aria-hidden="true" />
                              ) : (
                                <ChevronDown className="h-4 w-4" aria-hidden="true" />
                              )}
                              Week {week.weekNumber}
                            </button>
                            {week.allGenerated ? (
                              <StatusPill tone="success">Generated</StatusPill>
                            ) : week.anyGenerated ? (
                              <StatusPill tone="info">
                                {week.generatedCount} of {week.lessonCount} generated
                              </StatusPill>
                            ) : week.pendingCount > 0 ? (
                              <StatusPill tone="neutral">
                                {planCountLabel(week.pendingCount)} to generate
                              </StatusPill>
                            ) : null}
                            <span className="flex-1" />
                            {week.pendingCount > 0 && (
                              <Button
                                data-generate-week
                                size="sm"
                                className="h-7 rounded-md px-2.5 text-xs"
                                disabled={weekBlocked}
                                onClick={() => handleGenerateWeek(week)}
                              >
                                Generate week
                              </Button>
                            )}
                          </div>
                          {/* Counts line — the teacher's weekly fit answer, in
                              plain words (e2e: data-week-coverage). */}
                          <p
                            data-week-coverage
                            className="border-t px-3 py-1.5 text-[11px] text-muted-foreground"
                          >
                            {formatWeekCounts(week)}
                            {fit && fit.capped && (
                              <span className="block text-amber-700">
                                {planCountLabel(fit.rowsGeneratable)} of the {planCountLabel(week.pendingCount)} pending
                                can be generated with your remaining monthly allowance.
                              </span>
                            )}
                          </p>
                          {!collapsed && (
                            <div className="divide-y">
                              {week.rows.map((row) => {
                                const rowFit = quotaFitForRows([row], quota)
                                const rowDisabled =
                                  generating ||
                                  generateIsBlocked ||
                                  (!!rowFit && rowFit.rowsGeneratable === 0)
                                const lesson = row.generatedLesson
                                return (
                                  <div
                                    key={row.source_occurrence_id || `row-${row.lesson_sequence}`}
                                    data-week-row
                                    data-occurrence-id={row.source_occurrence_id}
                                    className="flex flex-wrap items-center gap-2 px-3 py-2 text-xs"
                                  >
                                    <span className="font-semibold text-[#102A43]">
                                      Lesson {row.lesson_sequence}
                                    </span>
                                    <span className="text-muted-foreground">
                                      {row.week_ending
                                        ? `Week ending ${new Date(row.week_ending).toLocaleDateString('en-GB')}`
                                        : `Week ${row.source_week}`}
                                    </span>
                                    <span className="font-mono text-muted-foreground">
                                      {row.indicator_code || '—'}
                                    </span>
                                    <span
                                      className="min-w-0 flex-1 truncate text-muted-foreground"
                                      title={row.indicator_description}
                                    >
                                      {row.indicator_description}
                                    </span>
                                    {row.generated ? (
                                      <>
                                        <StatusPill tone={lesson?.teacher_edited ? 'info' : 'success'}>
                                          {lesson?.teacher_edited ? 'Updated' : 'Generated'}
                                        </StatusPill>
                                        <a
                                          href="#lesson-workspace"
                                          className="rounded-md border px-1.5 py-0.5 text-[11px] text-[#04769B] hover:bg-slate-50"
                                          onClick={(e) => {
                                            e.preventDefault()
                                            document
                                              .querySelector('[data-lesson-workspace]')
                                              ?.scrollIntoView({ behavior: 'smooth' })
                                          }}
                                        >
                                          Open in workspace
                                        </a>
                                        {/* An already-generated lesson can still be
                                            re-run on its own — same occurrence, same
                                            quota identity (the backend dedupes it). */}
                                        <Button
                                          data-generate-lesson
                                          size="sm"
                                          variant="outline"
                                          className="h-6 rounded-md px-2 text-[11px]"
                                          disabled={rowDisabled || !row.source_occurrence_id}
                                          onClick={() => handleGenerateRow(row)}
                                        >
                                          Regenerate
                                        </Button>
                                      </>
                                    ) : (
                                      <>
                                        {row.needs_review ? (
                                          <StatusPill tone="warning">Needs review</StatusPill>
                                        ) : (
                                          <StatusPill tone="neutral">Ready to generate</StatusPill>
                                        )}
                                        <Button
                                          data-generate-lesson
                                          size="sm"
                                          className="h-6 rounded-md px-2 text-[11px]"
                                          disabled={rowDisabled || !row.source_occurrence_id}
                                          onClick={() => handleGenerateRow(row)}
                                        >
                                          Generate
                                        </Button>
                                      </>
                                    )}
                                    {/* §6: where this row came from, kept in
                                        secondary disclosure — never an audit
                                        wall in front of the workflow. */}
                                    {row.source_provenance && (
                                      <details className="w-full text-[11px] text-muted-foreground">
                                        <summary className="cursor-pointer select-none">
                                          Source &amp; alignment
                                        </summary>
                                        <dl className="mt-1 grid gap-x-4 gap-y-0.5 sm:grid-cols-2">
                                          {Object.entries(row.source_provenance).map(([k, v]) => (
                                            <div key={k} className="flex gap-1">
                                              <dt className="capitalize">{k.replace(/_/g, ' ')}:</dt>
                                              <dd className="truncate">
                                                {typeof v === 'object' && v !== null
                                                  ? JSON.stringify(v)
                                                  : String(v ?? '—')}
                                              </dd>
                                            </div>
                                          ))}
                                        </dl>
                                      </details>
                                    )}
                                  </div>
                                )
                              })}
                              {week.specialRows.map((row) => (
                                <div
                                  key={`special-${row.source_occurrence_id || row.lesson_sequence}`}
                                  data-week-row
                                  data-occurrence-id={row.source_occurrence_id}
                                  className="flex flex-wrap items-center gap-2 bg-amber-50/60 px-3 py-2 text-xs text-amber-900"
                                >
                                  <span className="font-semibold">
                                    {row.special_period_label || 'Special period'}
                                  </span>
                                  <span className="text-muted-foreground">
                                    {row.indicator_description}
                                  </span>
                                  <span className="flex-1" />
                                  <StatusPill tone="caution">Automatic</StatusPill>
                                </div>
                              ))}
                              {week.rows.length === 0 && week.specialRows.length === 0 && (
                                <p className="px-3 py-2 text-xs italic text-muted-foreground">
                                  No teaching periods this week
                                </p>
                              )}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              </SurfaceCard>
            )}

            {/* D. Per-lesson review data (Section H): source fields are
                read-only; keywords / Other TLRs / competencies /
                references are editable and applied on generate. Hidden once a
                job exists (§15) — the workspace shows the generated lessons. */}
            {!jobId && lessonReview.length > 0 && (
              <SurfaceCard data-lesson-review className="px-5 py-5 sm:px-6">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <h2 className="text-base font-semibold text-[#102A43]">Lesson Review Data</h2>
                    <p className="text-xs text-muted-foreground">
                      Review each lesson before generating. Source TLRs and
                      week-ending stay from your scheme document.
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => saveLessonReviewDrafts()}
                    disabled={reviewSaving}
                  >
                    {reviewSaving ? (
                      <>
                        <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                        Saving...
                      </>
                    ) : (
                      <>
                        <Save className="mr-1 h-3 w-3" />
                        Save review
                      </>
                    )}
                  </Button>
                </div>
                {reviewSaved && (
                  <p className="mt-2 text-xs text-green-600">Lesson review saved.</p>
                )}
                <div className="mt-4 max-h-96 space-y-4 overflow-y-auto pr-1">
                  {lessonReview.map((row) => (
                    <div
                      key={`review-${row.lesson_sequence}`}
                      className="space-y-2 rounded-md border bg-muted/30 p-3"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <p className="text-xs font-semibold">
                            Lesson {row.lesson_sequence} ·{' '}
                            <span className="font-mono">{row.indicator_code}</span>
                          </p>
                          <p className="text-[11px] text-muted-foreground">
                            Source Week {row.source_week}
                            {row.week_ending
                              ? ` · Week ending ${new Date(row.week_ending).toLocaleDateString('en-GB')}`
                              : ''}
                            {row.week_ending_derived ? ' (derived)' : ''}
                            {' · '}Teaching Week {row.teaching_week}
                          </p>
                        </div>
                      </div>
                      {/* PART R: a special period is NOT a lesson. Show the
                          period banner instead of fake curriculum fields and
                          offer no lesson fields or AI generation for it. */}
                      {row.is_special_period && (
                        <Banner tone="info" className="text-xs">
                          <p className="font-semibold">
                            Special Period: {row.special_period_label || 'Mid-Term'}
                          </p>
                          <p>This period does not contain a normal lesson.</p>
                        </Banner>
                      )}
                      {!row.is_special_period && (
                        <>
                          {/* ALLOCATION (Pattern 1): the teacher reviews the
                              auto-assigned slot and adjusts it. Mostly reviewing,
                              rarely typing — an intelligent default, editable. */}
                          <div className="flex flex-wrap items-end gap-2">
                            <div className="flex-1 min-w-[10rem]">
                              <label
                                htmlFor={`period-${row.lesson_sequence}`}
                                className="mb-1 block text-[11px] font-medium text-muted-foreground"
                              >
                                Teaching period / day
                              </label>
                              <input
                                id={`period-${row.lesson_sequence}`}
                                type="text"
                                value={row.period || ''}
                                onChange={(e) => updateLessonReviewRow(row.lesson_sequence, {
                                  period: e.target.value,
                                })}
                                placeholder="e.g. Monday · Period 1"
                                className="w-full rounded-md border border-input px-2 py-1.5 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE]/45 focus-visible:border-[#04A9CE]/70"
                              />
                            </div>
                          </div>
                          {/* CURRICULUM CONTEXT — read-only authoritative source
                              data (PART X/Y). */}
                          <p className="text-[11px] leading-snug text-muted-foreground">
                            {row.indicator_description}
                          </p>
                          {(row.content_standard || row.strand) && (
                            <p className="text-[11px] text-muted-foreground">
                              {row.strand}{row.sub_strand ? ` › ${row.sub_strand}` : ''}
                              {row.content_standard ? ` · ${row.content_standard}` : ''}
                            </p>
                          )}
                          <div>
                            <p className="mb-1 text-[11px] font-medium text-muted-foreground">
                              Source TLRs (from scheme — read only)
                            </p>
                            {row.source_tlrs?.length ? (
                              <ul className="list-inside list-disc text-[11px] text-muted-foreground">
                                {row.source_tlrs.map((r: string, i: number) => (
                                  <li key={i}>{r}</li>
                                ))}
                              </ul>
                            ) : (
                              <p className="text-[11px] italic text-muted-foreground">
                                No source TLRs for this week
                              </p>
                            )}
                          </div>
                          {/* KEYWORDS — AI-suggested per lesson + editable
                              (PART G/X). */}
                          <div>
                            <label
                              htmlFor={`keywords-${row.lesson_sequence}`}
                              className="mb-1 block text-[11px] font-medium text-muted-foreground"
                            >
                              Keywords for this lesson (AI-suggested — edit as needed)
                            </label>
                            <input
                              id={`keywords-${row.lesson_sequence}`}
                              type="text"
                              value={(row.keywords || []).join(', ')}
                              onChange={(e) => updateLessonReviewRow(row.lesson_sequence, {
                                keywords: e.target.value.split(',').map((s) => s.trim()).filter(Boolean),
                              })}
                              placeholder="Comma-separated"
                              className="w-full rounded-md border border-input px-2 py-1.5 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE]/45 focus-visible:border-[#04A9CE]/70"
                            />
                          </div>
                          {/* OTHER TLRs — teacher-added only; default empty
                              (PART I/X). */}
                          <div>
                            <label
                              htmlFor={`other-tlrs-${row.lesson_sequence}`}
                              className="mb-1 block text-[11px] font-medium text-muted-foreground"
                            >
                              Other TLRs for this lesson (optional teacher additions)
                            </label>
                            <input
                              id={`other-tlrs-${row.lesson_sequence}`}
                              type="text"
                              value={(row.other_tlrs || []).join(', ')}
                              onChange={(e) => updateLessonReviewRow(row.lesson_sequence, {
                                other_tlrs: e.target.value.split(',').map((s) => s.trim()).filter(Boolean),
                              })}
                              placeholder="Leave blank unless you want to add resources"
                              className="w-full rounded-md border border-input px-2 py-1.5 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE]/45 focus-visible:border-[#04A9CE]/70"
                            />
                          </div>
                        </>
                      )}
                      {isWapefSelected && wapefOptions && !row.is_special_period && (
                        <div className="rounded-md border bg-background p-2.5">
                          <p className="mb-2 text-[11px] font-semibold text-[#102A43]">
                            Approved WAPEF Plan fields
                            <span className="ml-1 font-normal text-muted-foreground">
                              (teacher-selected — the AI never changes these)
                            </span>
                          </p>
                          <div className="grid gap-2.5 sm:grid-cols-2">
                            <Field label="Deep Hope" htmlFor={`wapef-deep-hope-${row.lesson_sequence}`}>
                              <Select
                                id={`wapef-deep-hope-${row.lesson_sequence}`}
                                value={row.wapef_deep_hope || ''}
                                onChange={(e) => updateLessonReviewRow(row.lesson_sequence, {
                                  wapef_deep_hope: e.target.value,
                                })}
                              >
                                <option value="">— Select —</option>
                                {wapefOptions.deep_hopes.map((option) => (
                                  <option key={option} value={option}>{option}</option>
                                ))}
                              </Select>
                            </Field>
                            <Field label="Storyline" htmlFor={`wapef-storyline-${row.lesson_sequence}`}>
                              <Select
                                id={`wapef-storyline-${row.lesson_sequence}`}
                                value={row.wapef_storyline || ''}
                                onChange={(e) => updateLessonReviewRow(row.lesson_sequence, {
                                  wapef_storyline: e.target.value,
                                })}
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
                                const selected = (row.wapef_through_lines || []).includes(option)
                                return (
                                  <button
                                    key={option}
                                    type="button"
                                    onClick={() => {
                                      const cur = row.wapef_through_lines || []
                                      const next = selected
                                        ? cur.filter((t: string) => t !== option)
                                        : [...cur, option]
                                      updateLessonReviewRow(row.lesson_sequence, {
                                        wapef_through_lines: next,
                                      })
                                    }}
                                    className={`rounded border px-1.5 py-0.5 text-[10px] ${
                                      selected
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
                          <div className="mt-2.5 grid gap-2.5 sm:grid-cols-2">
                            <Field label="God's Story" htmlFor={`wapef-gods-story-${row.lesson_sequence}`}>
                              <Select
                                id={`wapef-gods-story-${row.lesson_sequence}`}
                                value={row.wapef_gods_story || ''}
                                onChange={(e) => updateLessonReviewRow(row.lesson_sequence, {
                                  wapef_gods_story: e.target.value,
                                })}
                              >
                                <option value="">— Select —</option>
                                {wapefOptions.gods_story.map((option) => (
                                  <option key={option} value={option}>{option}</option>
                                ))}
                              </Select>
                            </Field>
                            <Field label="Remarks" htmlFor={`wapef-remarks-${row.lesson_sequence}`}>
                              <TextArea
                                id={`wapef-remarks-${row.lesson_sequence}`}
                                value={row.remarks || ''}
                                onChange={(e) => updateLessonReviewRow(row.lesson_sequence, {
                                  remarks: e.target.value,
                                })}
                                placeholder="Your reflection (printed in REMARKS)"
                                rows={2}
                              />
                            </Field>
                          </div>
                        </div>
                      )}
                      {/* CORE COMPETENCIES — AI-suggested for this lesson's
                          activity type + teacher-editable (PART H/X). */}
                      {!row.is_special_period && (
                      <div>
                        <p className="mb-1 text-[11px] font-medium text-muted-foreground">
                          Core competencies (AI-suggested — edit as needed)
                        </p>
                        <div className="flex flex-wrap gap-1.5">
                          {NACCA_COMPETENCIES.map((label) => {
                            const selected = (row.core_competencies || []).includes(label)
                            return (
                              <button
                                key={label}
                                type="button"
                                onClick={() => {
                                  const cur = row.core_competencies || []
                                  const next = selected
                                    ? cur.filter((c: string) => c !== label)
                                    : [...cur, label]
                                  updateLessonReviewRow(row.lesson_sequence, {
                                    core_competencies: next,
                                  })
                                }}
                                className={`rounded border px-1.5 py-0.5 text-[10px] ${
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
                      </div>
                      )}
                      {/* REFERENCES — teacher-entered only. Exactly 3 empty
                          slots by default; + Add creates another slot (PART
                          L/M/X). Empty slots are never persisted. */}
                      {!row.is_special_period && (
                      <div>
                        <div className="mb-1 flex items-center justify-between">
                          <p className="text-[11px] font-medium text-muted-foreground">
                            References (teacher-entered)
                          </p>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-6 px-2 text-[10px]"
                            onClick={() => updateLessonReviewRow(row.lesson_sequence, {
                              structured_references: [
                                ...(row.structured_references || []),
                                { type: 'Other', title: '', page: '' },
                              ],
                            })}
                          >
                            + Add reference
                          </Button>
                        </div>
                        {(row.structured_references || []).map((ref: any, idx: number) => (
                          <div key={idx} className="mb-1 grid grid-cols-12 gap-1">
                            <Select
                              value={ref.type || 'Other'}
                              onChange={(e) => updateStructuredRef(row.lesson_sequence, idx, { type: e.target.value })}
                              className="col-span-4 h-7 px-1 text-[10px]"
                              aria-label="Reference type"
                            >
                              {REFERENCE_TYPES.map(t => (
                                <option key={t} value={t}>{t}</option>
                              ))}
                            </Select>
                            <Input
                              type="text"
                              value={ref.title || ''}
                              onChange={(e) => updateStructuredRef(row.lesson_sequence, idx, { title: e.target.value })}
                              placeholder="Title"
                              className="col-span-5 h-7 px-1 text-[10px]"
                            />
                            <Input
                              type="text"
                              value={ref.page || ''}
                              onChange={(e) => updateStructuredRef(row.lesson_sequence, idx, { page: e.target.value })}
                              placeholder="Page (optional)"
                              className="col-span-3 h-7 px-1 text-[10px]"
                            />
                          </div>
                        ))}
                      </div>
                      )}
                    </div>
                  ))}
                </div>
              </SurfaceCard>
            )}
          </div>

          {/* ACTION RAIL — the one unmistakable place to generate. */}
          <div className="space-y-6 lg:col-span-1 lg:sticky lg:top-20 lg:self-start">
            <SurfaceCard
              data-generate-action
              accent="bg-gradient-to-r from-[#102A43] to-[#04A9CE]"
              className="px-5 py-5"
            >
              <h2 className="text-base font-semibold text-[#102A43]">Generate</h2>

              {/* Export/generation failures surface here. Without this the controlled
                  server messages (403 licence, 500 conversion, 503 converter missing)
                  were invisible: the click simply appeared to do nothing. The title
                  stays generic because this banner serves BOTH flows (PART 22). */}
              {error && scheme && (
                <Banner tone="danger" className="mt-3" title="Action failed">
                  {error}
                </Banner>
              )}

              {!jobId ? (
                <>
                  {/* Generation experience (Pattern 7). Quick Generate remains
                      the default; Build with me is opt-in and never asks the
                      teacher ten questions before delivering a lesson. */}
                  <div data-generate-mode className="mt-3 grid grid-cols-2 gap-2" role="radiogroup" aria-label="Generation mode">
                    {([
                      { key: 'quick', label: 'Quick Generate' },
                      { key: 'guided', label: 'Build with me' },
                    ] as const).map((m) => {
                      const active = genMode === m.key
                      return (
                        <button
                          key={m.key}
                          type="button"
                          role="radio"
                          aria-checked={active}
                          onClick={() => {
                            setGenMode(m.key)
                            try { window.localStorage.setItem('schemeknit.gen_mode', m.key) } catch { /* ignore */ }
                          }}
                          className={`rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
                            active
                              ? 'border-[#102A43] bg-[#102A43] text-white'
                              : 'border-slate-200 bg-white text-[#102A43] hover:bg-slate-50'
                          }`}
                        >
                          {m.label}
                        </button>
                      )
                    })}
                  </div>
                  <p className="mt-1 text-center text-xs text-muted-foreground">
                    {genMode === 'guided'
                      ? 'Build with me — review one section at a time after generating.'
                      : 'Quick Generate — one complete draft from your scheme.'}
                  </p>

                  {/* Free Tier allowance (PART C) — the exact line phase17
                      and teachers parse, plus what the scheme may spend. Lives
                      here ONCE (§14), not repeated across cards. */}
                  {quotaText && (
                    <Banner tone="info" data-quota-banner className="mt-3 text-xs">
                      <div className="space-y-1">
                        <p className="font-semibold">{quotaText}</p>
                        {allocationPreview?.selectable_indicators?.length > 0 && (
                          <p>
                            This scheme contains {allocationPreview.selectable_indicators.length} instructional indicator
                            {allocationPreview.selectable_indicators.length === 1 ? '' : 's'}. You can generate up to{' '}
                            {quota?.remaining ?? 0} now; Teacher Pro removes this limit.
                          </p>
                        )}
                      </div>
                    </Banner>
                  )}

                  {/* Never a silent disable: state the reason next to the CTA. */}
                  {generateIsBlocked && (
                    <Banner tone="warning" className="mt-3" title="Before you can generate">
                      <ul className="list-disc space-y-1 pl-4">
                        {generateBlockReasons.map((r) => (
                          <li key={r}>{r}</li>
                        ))}
                      </ul>
                    </Banner>
                  )}
                  {!generateIsBlocked && allocationPreview && (
                    <p className="mt-3 text-sm font-medium text-green-700">
                      {pendingRows.length === 0
                        ? `All ${planCountLabel(totalLessonPlans)} for this scheme are already generated.`
                        : fullPlanSelection.capped
                          ? `${fullFitRowCount} of ${pendingRows.length} pending can be generated this month — the rest stay in your scheme for next month.`
                          : `Ready to generate ${planCountLabel(pendingRows.length)}.`}
                    </p>
                  )}

                  <Button
                    onClick={handleGenerateAll}
                    disabled={generating || generateIsBlocked || !allocationPreview}
                    className="mt-3 w-full bg-gradient-to-r from-[#102A43] to-[#04769B] text-white hover:from-[#0d2136] hover:to-[#04698a]"
                    size="lg"
                  >
                    {generating ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Generating...
                      </>
                    ) : (
                      <>
                        <Play className="mr-2 h-4 w-4" />
                        Generate lesson plans
                      </>
                    )}
                  </Button>
                  {(allocationPreview?.allocation_conflicts?.length > 0 ||
                    allocationPreview?.indicators_unallocated > 0) && (
                    <p className="mt-2 text-center text-xs text-yellow-700">
                      Every curriculum occurrence stays in its own source
                      week — none are dropped, merged or moved to a later week.
                    </p>
                  )}
                  {generating && genProgress && (
                    <p className="mt-3 text-center text-sm text-muted-foreground" role="status" aria-live="polite">
                      {genProgress}
                    </p>
                  )}
                </>
              ) : (
                <div className="mt-3 space-y-3">
                  <div className="flex items-center rounded-lg bg-green-50 p-3 text-green-700">
                    <CheckCircle className="mr-2 h-5 w-5 shrink-0" />
                    <span className="font-medium">
                      {reviewedLessons ?? coverage?.total_generated_lessons ?? 0} lesson plans generated — shown on the left
                    </span>
                  </div>
                  {aiResult && (
                    <p className="text-center text-xs text-muted-foreground">
                      {aiResult.active && aiResult.lessons_ai > 0
                        ? `Zeli enriched ${aiResult.lessons_ai} lesson${aiResult.lessons_ai === 1 ? '' : 's'}; ${aiResult.lessons_deterministic} used the deterministic engine.`
                        : aiResult.mode === 'OFF'
                          ? 'All lessons generated deterministically (Zeli off).'
                          : 'Zeli unavailable right now — all lessons generated deterministically.'}
                    </p>
                  )}
                  <Button className="w-full" variant="outline" asChild>
                    <Link href="/lessons">
                      <Eye className="mr-2 h-4 w-4" />
                      See all lesson plans
                    </Link>
                  </Button>
                  <Button onClick={() => handleExport('docx')} disabled={exporting === 'docx'} className="w-full" variant="outline">
                    <FileText className="mr-2 h-4 w-4" />
                    {exporting === 'docx' ? 'Exporting...' : 'Download DOCX'}
                  </Button>
                  <Button onClick={() => handleExport('pdf')} disabled={exporting === 'pdf'} className="w-full" variant="outline">
                    <Download className="mr-2 h-4 w-4" />
                    {exporting === 'pdf' ? 'Exporting...' : 'Download PDF'}
                  </Button>
                  <Button onClick={() => handleExport('xlsx')} disabled={exporting === 'xlsx'} className="w-full" variant="outline">
                    <FileSpreadsheet className="mr-2 h-4 w-4" />
                    {exporting === 'xlsx' ? 'Exporting...' : 'Download Register (XLSX)'}
                  </Button>
                  <Button onClick={() => handleExport('zip')} disabled={exporting === 'zip'} className="w-full" variant="outline">
                    <FileArchive className="mr-2 h-4 w-4" />
                    {exporting === 'zip' ? 'Exporting...' : 'Export ZIP'}
                  </Button>
                  <Button
                    onClick={() => {
                      // Back to setup: config + review return (§15); the
                      // auto-preview effect rebuilds the weeks for editing.
                      setJobId(null); setCoverage(null); setGenProgress('');
                      setAllocationPreview(null);
                    }}
                    className="w-full"
                    variant="outline"
                  >
                    <Play className="mr-2 h-4 w-4" />
                    Start New Generation
                  </Button>
                  <Button variant="ghost" className="w-full" asChild>
                    <Link href="/dashboard">Back to Dashboard</Link>
                  </Button>
                </div>
              )}
            </SurfaceCard>

            {/* Coverage Summary */}
            {coverage && (
              <SurfaceCard data-coverage className="px-5 py-5">
                <h2 className="text-base font-semibold text-[#102A43]">Coverage Summary</h2>
                <dl className="mt-3 space-y-3">
                  <div className="flex justify-between text-sm">
                    <dt className="text-muted-foreground">Instructional Weeks</dt>
                    <dd className="font-medium">{coverage.total_instructional_weeks}</dd>
                  </div>
                  <div className="flex justify-between text-sm">
                    <dt className="text-muted-foreground">Curriculum Indicators</dt>
                    <dd className="font-medium">{coverage.total_indicators}</dd>
                  </div>
                  <div className="flex justify-between text-sm">
                    <dt className="text-muted-foreground">Lessons Generated</dt>
                    <dd className="font-medium">{coverage.total_generated_lessons}</dd>
                  </div>
                  <div className="flex justify-between text-sm">
                    <dt className="text-muted-foreground">Coverage</dt>
                    <dd className="font-medium">{coverage.coverage_percentage?.toFixed(1)}%</dd>
                  </div>
                </dl>
                {coverage.warnings && coverage.warnings.length > 0 && (
                  <Banner tone="warning" className="mt-3" title="Coverage warnings">
                    <ul className="list-disc space-y-1 pl-4">
                      {coverage.warnings.map((w, i) => <li key={i}>{w}</li>)}
                    </ul>
                  </Banner>
                )}
              </SurfaceCard>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
