'use client'

import { useState, useEffect } from 'react'
import { useRouter, useParams } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { SurfaceCard } from '@/components/ui/surface-card'
import { Banner } from '@/components/ui/banner'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Field, TextArea } from '@/components/ui/field'
import { Download, Settings, Play, CheckCircle, FileText, FileSpreadsheet, FileArchive, Loader2, Eye, Save } from 'lucide-react'
import { api } from '@/lib/api'
import { resolveRouteId } from '@/lib/route-params'
import { PageHeader } from '@/components/ui/page-header'
import { StatusPill } from '@/components/ui/badge'
import { SchemeOfWork, TermConfig, CurriculumCoverage, Template, CurriculumProfile, WapefOptions } from '@/types'

// The Approved WAPEF Plan is one shared form for Nursery/KG/Basic/JHS; its
// four structured fields are teacher-selected from approved option lists.
const WAPEF_TEMPLATE_ID = 'tpl-wapef-approved-plan'

export default function GeneratePage() {
  const router = useRouter()
  const params = useParams()
  const schemeId = resolveRouteId(params.id, 'generate')

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
  const [allocationConfirmed, setAllocationConfirmed] = useState(false)
  const [selectedCodes, setSelectedCodes] = useState<string[]>([])
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
  const REFERENCE_TYPES = [
    'Subject Curriculum',
    'Teacher\'s Handbook / Teacher\'s Guide',
    'Textbook',
    'Other',
  ]
  // Actual AI resolution (mode/provider/available) reported by the backend —
  // so the UI never shows a mode that disagrees with real behaviour.
  const [aiStatus, setAiStatus] = useState<{
    mode: string; active: boolean; provider: string | null; state: string; reason: string | null;
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

  useEffect(() => {
    // Restore the teacher's last AI mode choice so it persists across visits.
    try {
      const saved = window.localStorage.getItem('schemeknit.ai_mode')
      if (saved) setConfig(prev => ({ ...prev, ai_mode: saved as any }))
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
      setTemplates(templatesData.templates || [])
      setProfiles(profilesData.profiles || [])

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

  const handlePreviewAllocation = async () => {
    try {
      setPreviewing(true)
      setError(null)
      setAllocationConfirmed(false)
      const preview = await api.getAllocationPreview(schemeId, config)
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
      setLessonReview(reviewRows)
      setReviewSaved(false)
      // Seed the indicator selection: when the Free Tier quota is enforced,
      // pre-select up to the remaining allowance so the teacher can generate
      // immediately, while every other indicator stays visible and selectable.
      const selectable: string[] = (preview.selectable_indicators || [])
        .map((s: any) => s.indicator_code)
        .filter(Boolean)
      const remaining: number | null = preview.lesson_quota?.enforced
        ? (preview.lesson_quota.remaining ?? 0)
        : null
      if (remaining !== null && selectable.length > 0) {
        setSelectedCodes(selectable.slice(0, Math.max(remaining, 0)))
        setConfig(prev => ({
          ...prev,
          selected_indicator_codes: selectable.slice(0, Math.max(remaining, 0)),
        }))
      } else {
        setSelectedCodes([])
        setConfig(prev => ({ ...prev, selected_indicator_codes: [] }))
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to preview allocation')
    } finally {
      setPreviewing(false)
    }
  }

  const toggleIndicator = (code: string) => {
    const quotaEnforced = !!allocationPreview?.lesson_quota?.enforced
    const remaining: number = allocationPreview?.lesson_quota?.remaining ?? 0
    const selectable: string[] = (allocationPreview?.selectable_indicators || [])
      .map((s: any) => s.indicator_code)
      .filter(Boolean)
    let next: string[]
    if (selectedCodes.includes(code)) {
      next = selectedCodes.filter(c => c !== code)
    } else {
      if (quotaEnforced && selectedCodes.length >= remaining) {
        // Hard cap: cannot spend more than this month's remaining allowance.
        return
      }
      next = [...selectedCodes, code]
    }
    // Preserve curriculum order regardless of click order.
    next = selectable.filter(c => next.includes(c))
    setSelectedCodes(next)
    setConfig(prev => ({ ...prev, selected_indicator_codes: next }))
  }

  const handleConfirmAndGenerate = async () => {
    setAllocationConfirmed(true)
    // Persist any unsaved per-lesson review edits before generation so the
    // backend applies them when building each LessonPlan (Section H).
    if (lessonReview.length > 0) {
      try {
        await saveLessonReviewDrafts()
      } catch {
        // Non-fatal: generation still uses last saved drafts / builder defaults.
      }
    }
    await handleGenerate()
  }

  const saveLessonReviewDrafts = async () => {
    if (!lessonReview.length) return
    setReviewSaving(true)
    setReviewSaved(false)
    try {
      const drafts: Record<string, any> = {}
      for (const row of lessonReview) {
        drafts[String(row.lesson_sequence)] = {
          keywords: row.keywords || [],
          other_tlrs: row.other_tlrs || [],
          core_competencies: row.core_competencies || [],
          structured_references: row.structured_references || [],
          // Approved WAPEF Plan teacher-selected fields (dropdown values,
          // sent as-is; the server normalizes against the approved lists).
          wapef_deep_hope: row.wapef_deep_hope || '',
          wapef_storyline: row.wapef_storyline || '',
          wapef_through_lines: row.wapef_through_lines || [],
          wapef_gods_story: row.wapef_gods_story || '',
          remarks: row.remarks || '',
        }
      }
      await api.saveLessonReview(schemeId, drafts)
      setReviewSaved(true)
      setTimeout(() => setReviewSaved(false), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save lesson review')
    } finally {
      setReviewSaving(false)
    }
  }

  const updateLessonReviewRow = (seq: number, patch: Partial<any>) => {
    setLessonReview(rows => rows.map(r => (r.lesson_sequence === seq ? { ...r, ...patch } : r)))
    setReviewSaved(false)
  }

  const updateStructuredRef = (seq: number, index: number, patch: Partial<any>) => {
    setLessonReview(rows => rows.map(r => {
      if (r.lesson_sequence !== seq) return r
      const refs = [...(r.structured_references || [])]
      refs[index] = { ...(refs[index] || { type: 'Other', title: '' }), ...patch }
      return { ...r, structured_references: refs }
    }))
    setReviewSaved(false)
  }

  // Allocation preview grouped by ACTUAL teaching week, with carried-forward
  // lessons marked in simple language (§10). Falls back to curriculum-week
  // grouping when the API response predates teaching-week grouping.
  const previewTeachingWeeks: any[] = (() => {
    if (!allocationPreview) return []
    if (allocationPreview.teaching_weeks?.length) {
      return allocationPreview.teaching_weeks.map((tw: any) => ({
        teaching_week: tw.teaching_week,
        lesson_count: tw.lessons?.length || 0,
        periods: (tw.lessons || []).map((l: any) => ({
          period_index: l.period_index,
          lesson_sequence: l.lesson_sequence,
          lesson_date: l.lesson_date,
          indicator_code: l.indicator_code,
          indicator_description: l.indicator_description,
          status: l.status || 'scheduled',
          source_week: l.source_week,
          week_ending: l.week_ending,
          source_tlrs: l.source_tlrs,
        })),
      }))
    }
    return (allocationPreview.weeks || []).map((w: any) => ({
      teaching_week: w.week_number,
      lesson_count: w.lesson_count,
      periods: (w.periods || []).map((p: any) => ({
        ...p,
        status: p.needs_review
          ? 'needs_review'
          : p.carry_forward
            ? 'carried_forward'
            : 'scheduled',
      })),
    }))
  })()

  const handleGenerate = async () => {
    try {
      setGenerating(true)
      setError(null)
      setGenProgress('Preparing curriculum allocation...')

      const response = await api.generateLessonPlans(schemeId, config)
      setJobId(response.job_id)
      setAiResult(response.ai || null)
      setGenProgress('Lesson plans generated successfully!')

      const coverageData = await api.getCurriculumCoverage(response.job_id)
      setCoverage(coverageData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Generation failed')
    } finally {
      setGenerating(false)
    }
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
  // The WAPEF structured fields belong to the Approved WAPEF Plan only; they
  // appear in the per-lesson review when that template is the chosen form.
  const isWapefSelected = config.template_id === WAPEF_TEMPLATE_ID

  // Why the Generate action is unavailable — never a silent disable.
  const generateBlockReasons: string[] = []
  if (
    allocationPreview &&
    allocationPreview.lesson_quota?.enforced &&
    (allocationPreview.selectable_indicators?.length || 0) > 0 &&
    selectedCodes.length === 0
  ) {
    generateBlockReasons.push('Select at least one indicator to generate.')
  }
  // Quota exhaustion with nothing left to select: state it explicitly.
  // (Indicatorless Nursery-style schemes never enter this branch: the preview
  // advertises no selectable indicators for them and the server exempts them
  // from the selection requirement.)
  if (
    allocationPreview &&
    allocationPreview.lesson_quota?.enforced &&
    (allocationPreview.lesson_quota.remaining ?? 0) <= 0 &&
    (allocationPreview.selectable_indicators?.length || 0) === 0 &&
    selectedCodes.length === 0
  ) {
    generateBlockReasons.push(
      'Your Free Tier lesson plans for this month are used up. Upgrade to Teacher Pro for unlimited generation, or wait for next month.')
  }
  const generateIsBlocked = generateBlockReasons.length > 0

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
          {/* MAIN COLUMN — source facts, configuration, allocation, review. */}
          <div className="space-y-6 lg:col-span-2">
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
                  <dd className="text-sm font-semibold text-[#102A43]">{scheme.class_level}</dd>
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
                <div>
                  <dt className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Template profile</dt>
                  <dd className="text-sm font-semibold text-[#102A43]">
                    {currentProfile
                      ? `${currentProfile.lessons_per_week}/week · ${currentProfile.lesson_duration_minutes} min`
                      : `${config.lessons_per_week}/week · ${config.lesson_duration_minutes} min`}
                  </dd>
                </div>
              </dl>
              {allocationPreview && (
                <div className="mt-4 rounded-lg bg-[#102A43]/5 px-4 py-3 text-sm">
                  <span className="font-semibold text-[#102A43]">
                    {allocationPreview.total_generated_lessons || 0} lesson plan
                    {(allocationPreview.total_generated_lessons || 0) === 1 ? '' : 's'}
                  </span>{' '}
                  will be generated from{' '}
                  <span className="font-semibold text-[#102A43]">
                    {selectedCodes.length} indicator{selectedCodes.length === 1 ? '' : 's'}
                  </span>{' '}
                  selected &bull;{' '}
                  {allocationPreview.coverage_percentage?.toFixed(1) ?? 0}% curriculum coverage
                </div>
              )}
            </SurfaceCard>

            {/* B. Configuration — grouped sections inside one surface. */}
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
                        <option value="BASIC">BASIC - AI suggestions</option>
                        <option value="ENHANCED">ENHANCED - Full AI</option>
                      </Select>
                      {aiStatus && (
                        <p className={`mt-1 text-xs ${aiStatus.active ? 'text-green-600' : 'text-muted-foreground'}`}>
                          {/* PART E: this label reports the backend-RESOLVED
                              provider for the current generation context — the
                              same resolution the generate request itself uses. */}
                          {aiStatus.active
                            ? `AI active · provider: ${aiStatus.provider}`
                            : config.ai_mode === 'OFF'
                              ? 'Deterministic engine · AI provider active: No'
                              : `No usable AI provider for mode '${aiStatus.mode}' — lessons will be deterministic.`}
                        </p>
                      )}
                    </Field>
                  </div>

                  <div className="grid gap-4 md:grid-cols-2">
                    {/* School and teacher identity are server-derived from the
                        authenticated user's school relationship and profile, so
                        they are shown read-only here (PART 13-15): the teacher
                        never types a school name, and the client value is not
                        trusted. */}
                    <Field label="School Name" htmlFor="cfg-school-name" hint="Derived from your school membership">
                      <Input
                        id="cfg-school-name"
                        type="text"
                        value={config.school_name || currentUser?.school_name || '—'}
                        disabled
                        placeholder="Derived from your school"
                        className="bg-muted text-muted-foreground"
                      />
                    </Field>
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

            {/* C. Allocation Preview — quotas, indicators, week-by-week periods. */}
            {allocationPreview && (
              <SurfaceCard
                data-allocation-preview
                accent="bg-gradient-to-r from-[#102A43] to-[#04A9CE]"
                className="px-5 py-5 sm:px-6"
              >
                <h2 className="text-lg font-semibold text-[#102A43]">Allocation Preview</h2>
                <p className="text-sm text-muted-foreground">
                  One indicator → one teaching period → one lesson plan
                </p>

                <div className="mt-4 space-y-4">
                  {/* Conflicts first — teacher must see these before generating */}
                  {(allocationPreview.allocation_conflicts?.length > 0 ||
                    allocationPreview.indicators_unallocated > 0 ||
                    allocationPreview.indicators_duplicated > 0) && (
                    <Banner tone="warning" title="Allocation conflicts — review before generating">
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
                            Duplicate indicator allocation detected — an indicator is the
                            primary focus of more than one lesson.
                          </p>
                        )}
                      </div>
                    </Banner>
                  )}

                  {/* Free Tier monthly allowance (PART C): plain, non-technical
                      language, with the scheme's indicator count and the
                      remaining allowance so the teacher can choose a subset. */}
                  {allocationPreview.lesson_quota?.enforced && (
                    <Banner tone="info" data-quota-banner className="text-xs">
                      <div className="space-y-1">
                        <p className="font-semibold">
                          {allocationPreview.lesson_quota.used} of {allocationPreview.lesson_quota.limit} Free Tier lesson plans used this month ·{' '}
                          {allocationPreview.lesson_quota.remaining} remaining
                        </p>
                        {allocationPreview.selectable_indicators?.length > 0 && (
                          <p>
                            This scheme contains {allocationPreview.selectable_indicators.length} instructional indicator
                            {allocationPreview.selectable_indicators.length === 1 ? '' : 's'}. You can generate up to{' '}
                            {allocationPreview.lesson_quota.remaining} now; Teacher Pro removes this limit.
                          </p>
                        )}
                      </div>
                    </Banner>
                  )}

                  {/* Indicator selection: one indicator = one lesson plan.
                      When the Free Tier quota is enforced the teacher chooses
                      which indicators to spend this month; the rest stay in the
                      scheme for later. Unlimited plans see every indicator
                      pre-selected with no cap. */}
                  {allocationPreview.selectable_indicators?.length > 0 && (
                    <div data-indicator-select className="space-y-2">
                      <div className="flex items-center justify-between">
                        <p className="text-xs font-semibold text-muted-foreground">
                          Choose indicators to generate
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {selectedCodes.length}
                          {allocationPreview.lesson_quota?.enforced
                            ? ` of ${allocationPreview.lesson_quota.remaining} remaining`
                            : ` selected`}
                        </p>
                      </div>
                      <div className="max-h-56 space-y-1.5 overflow-y-auto rounded-md border p-2">
                        {allocationPreview.selectable_indicators.map((ind: any) => {
                          const checked = selectedCodes.includes(ind.indicator_code)
                          const capped =
                            allocationPreview.lesson_quota?.enforced &&
                            !checked &&
                            selectedCodes.length >= (allocationPreview.lesson_quota.remaining ?? 0)
                          return (
                            <label
                              key={ind.indicator_code}
                              className={`flex cursor-pointer items-start gap-2 rounded p-1.5 text-xs ${
                                capped ? 'opacity-50' : 'hover:bg-muted'
                              }`}
                            >
                              <input
                                type="checkbox"
                                checked={checked}
                                disabled={capped}
                                onChange={() => toggleIndicator(ind.indicator_code)}
                                className="mt-0.5"
                              />
                              <span>
                                <span className="font-mono">{ind.indicator_code}</span>
                                {' — '}
                                {ind.indicator_description}
                                <span className="ml-1 text-muted-foreground">
                                  (Week {ind.source_week})
                                </span>
                              </span>
                            </label>
                          )
                        })}
                      </div>
                      {allocationPreview.lesson_quota?.enforced &&
                        selectedCodes.length === 0 && (
                          <p className="text-xs text-yellow-700">
                            Select at least one indicator to generate.
                          </p>
                        )}
                      {allocationPreview.lesson_quota?.enforced &&
                        selectedCodes.length < (allocationPreview.selectable_indicators?.length ?? 0) && (
                          <p className="text-xs text-muted-foreground">
                            Unselected indicators stay in your scheme and can be
                            generated next month.
                          </p>
                        )}
                    </div>
                  )}

                  {/* Allocation preview, grouped by ACTUAL teaching week. A lesson
                      carried forward from an earlier curriculum week says so in
                      plain language. */}
                  <div className="max-h-72 space-y-3 overflow-y-auto" data-allocation-weeks>
                    {previewTeachingWeeks.map((week: any) => (
                      <div key={`tw-${week.teaching_week}`}>
                        <h3 className="mb-1.5 sticky top-0 bg-white text-xs font-semibold text-muted-foreground">
                          Week {week.teaching_week}
                          <span className="ml-2 font-normal">
                            ({week.lesson_count} lesson{week.lesson_count === 1 ? '' : 's'})
                          </span>
                        </h3>
                        <div className="overflow-x-auto">
                          <table className="w-full border-collapse text-xs">
                            <thead>
                              <tr className="border-b text-left text-muted-foreground">
                                <th className="py-1 pr-2 font-medium">Date</th>
                                <th className="py-1 pr-2 font-medium">Period</th>
                                <th className="py-1 pr-2 font-medium">Indicator</th>
                                <th className="py-1 font-medium">Status</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y">
                              {week.periods?.map((alloc: any) => {
                                return (
                                  <tr key={`${week.teaching_week}-${alloc.period_index}`}>
                                    <td className="whitespace-nowrap py-1.5 pr-2">
                                      {alloc.lesson_date
                                        ? new Date(alloc.lesson_date).toLocaleDateString('en-GB')
                                        : '—'}
                                    </td>
                                    <td className="whitespace-nowrap py-1.5 pr-2 font-mono">
                                      {alloc.period_index}
                                    </td>
                                    <td className="py-1.5 pr-2" title={alloc.indicator_description}>
                                      <span className="font-mono">{alloc.indicator_code}</span>
                                    </td>
                                    <td className="py-1.5">
                                      {alloc.status === 'needs_review' ? (
                                        <StatusPill tone="warning">Needs review</StatusPill>
                                      ) : alloc.status === 'carried_forward' ? (
                                        <StatusPill tone="info">
                                          Carried forward from Week {alloc.source_week}
                                        </StatusPill>
                                      ) : (
                                        <StatusPill tone="success">Scheduled</StatusPill>
                                      )}
                                    </td>
                                  </tr>
                                )
                              })}
                              {(!week.periods || week.periods.length === 0) && (
                                <tr>
                                  <td colSpan={4} className="py-1.5 italic text-muted-foreground">
                                    No teaching periods this week
                                  </td>
                                </tr>
                              )}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    ))}
                  </div>

                  <p className="border-t pt-3 text-xs text-muted-foreground">
                    {allocationPreview.total_generated_lessons || 0} lessons will be generated ·{' '}
                    {allocationPreview.coverage_percentage?.toFixed(1) ?? 0}% curriculum coverage
                  </p>
                </div>
              </SurfaceCard>
            )}

            {/* D. Per-lesson review data (Section H): source fields are
                read-only; keywords / Other TLRs / competencies /
                references are editable and applied on generate. */}
            {lessonReview.length > 0 && (
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
                    onClick={saveLessonReviewDrafts}
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
                            Lesson {row.lesson_sequence + 1} ·{' '}
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

          {/* ACTION RAIL — the one unmistakable place to preview and generate. */}
          <div className="space-y-6 lg:col-span-1 lg:sticky lg:top-20 lg:self-start">
            <SurfaceCard
              data-generate-action
              accent="bg-gradient-to-r from-[#102A43] to-[#04A9CE]"
              className="px-5 py-5"
            >
              <h2 className="text-base font-semibold text-[#102A43]">Generate</h2>

              {/* Export/generation failures surface here. Without this the controlled
                  server messages (403 licence, 500 conversion, 503 converter missing)
                  were invisible: the click simply appeared to do nothing. */}
              {error && scheme && (
                <Banner tone="danger" className="mt-3" title="Generation problem">
                  {error}
                </Banner>
              )}

              {!jobId ? (
                <>
                  {!allocationPreview && !allocationConfirmed && (
                    <Banner tone="info" className="mt-3" title="Step 1: preview the allocation">
                      Preview shows exactly which lessons will be generated — dates, periods and
                      indicators — before anything is created.
                    </Banner>
                  )}

                  {!allocationConfirmed && (
                    <Button onClick={handlePreviewAllocation} disabled={previewing} className="mt-3 w-full" size="lg">
                      {previewing ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          Previewing...
                        </>
                      ) : (
                        <>
                          <Eye className="mr-2 h-4 w-4" />
                          Preview Allocation
                        </>
                      )}
                    </Button>
                  )}

                  {/* Never a silent disable: state the reason next to the CTA. */}
                  {allocationPreview && !allocationConfirmed && generateIsBlocked && (
                    <Banner tone="warning" className="mt-3" title="Before you can generate">
                      <ul className="list-disc space-y-1 pl-4">
                        {generateBlockReasons.map((r) => (
                          <li key={r}>{r}</li>
                        ))}
                      </ul>
                    </Banner>
                  )}
                  {allocationPreview && !allocationConfirmed && !generateIsBlocked && (
                    <p className="mt-3 text-sm font-medium text-green-700">
                      Ready to generate {allocationPreview.total_generated_lessons || 0} lesson
                      plan{(allocationPreview.total_generated_lessons || 0) === 1 ? '' : 's'}.
                    </p>
                  )}

                  {allocationPreview && !allocationConfirmed && (
                    <>
                      <Button
                        onClick={handleConfirmAndGenerate}
                        disabled={
                          generating ||
                          (allocationPreview.lesson_quota?.enforced &&
                            (allocationPreview.selectable_indicators?.length || 0) > 0 &&
                            selectedCodes.length === 0)
                        }
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
                            Confirm &amp; Generate
                          </>
                        )}
                      </Button>
                      {(allocationPreview.allocation_conflicts?.length > 0 ||
                        allocationPreview.indicators_unallocated > 0) && (
                        <p className="mt-2 text-center text-xs text-yellow-700">
                          Indicators carry forward to the next teaching week — none are dropped
                          or merged.
                        </p>
                      )}
                    </>
                  )}
                  {!allocationPreview && !allocationConfirmed && (
                    <p className="mt-3 text-center text-sm text-muted-foreground">
                      Preview allocation before generating
                    </p>
                  )}
                  {generating && genProgress && (
                    <p className="mt-3 text-center text-sm text-muted-foreground">{genProgress}</p>
                  )}
                </>
              ) : (
                <div className="mt-3 space-y-3">
                  <div className="flex items-center rounded-lg bg-green-50 p-3 text-green-700">
                    <CheckCircle className="mr-2 h-5 w-5 shrink-0" />
                    <span className="font-medium">
                      {coverage?.total_generated_lessons || 0} lesson plans generated
                    </span>
                  </div>
                  {aiResult && (
                    <p className="text-center text-xs text-muted-foreground">
                      {aiResult.active && aiResult.lessons_ai > 0
                        ? `AI (${aiResult.provider}) enriched ${aiResult.lessons_ai} lesson${aiResult.lessons_ai === 1 ? '' : 's'}; ${aiResult.lessons_deterministic} used the deterministic engine.`
                        : aiResult.mode === 'OFF'
                          ? 'All lessons generated deterministically (AI OFF).'
                          : 'No AI provider was available — all lessons generated deterministically.'}
                    </p>
                  )}
                  <Button className="w-full" asChild>
                    <Link href="/lessons">
                      <Eye className="mr-2 h-4 w-4" />
                      Review Lesson Plans
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
                      setJobId(null); setCoverage(null); setGenProgress('');
                      setAllocationPreview(null); setAllocationConfirmed(false);
                      setSelectedCodes([]);
                      setConfig(prev => ({ ...prev, selected_indicator_codes: [] }))
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
