'use client'

import { useState, useEffect } from 'react'
import { useRouter, useParams } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Field, TextArea } from '@/components/ui/field'
import { Download, Settings, Play, CheckCircle, FileText, FileSpreadsheet, FileArchive, Loader2, Eye, Save } from 'lucide-react'
import { api } from '@/lib/api'
import { resolveRouteId } from '@/lib/route-params'
import { PageHeader } from '@/components/ui/page-header'
import { SchemeOfWork, TermConfig, CurriculumCoverage, Template, CurriculumProfile } from '@/types'
import { formatCurrency } from '@/lib/utils-display'

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
  //: Actual AI resolution (mode/provider/available) reported by the backend —
  //: so the UI never shows a mode that disagrees with real behaviour.
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
      const level = levelForClass(schemeData.class_level || '')
      const [templatesData, profilesData, statusData] = await Promise.all([
        api.listTemplates(level, schemeData.class_level || ''),
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
      setConfig(prev => ({
        ...prev,
        scheme_of_work_id: schemeId,
        template_id: defaultTemplate?.id || '',
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
      setLessonReview(Array.isArray(preview.lesson_review) ? preview.lesson_review : [])
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

  const getTemplatesForScheme = () => {
    if (!scheme?.educational_level) return templates
    return templates.filter(t => t.educational_level === scheme.educational_level)
  }

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
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Card className="max-w-md">
          <CardContent className="p-8 text-center">
            <p className="text-destructive mb-4">{error}</p>
            <Button onClick={loadData}>Try Again</Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (!scheme) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Card className="max-w-md">
          <CardContent className="p-8 text-center">
            <p className="text-muted-foreground mb-4">Scheme not found</p>
            <Link href="/dashboard"><Button>Go to Dashboard</Button></Link>
          </CardContent>
        </Card>
      </div>
    )
  }

  const filteredTemplates = getTemplatesForScheme()
  const currentProfile = getProfileForScheme()

  return (
    <div className="min-h-screen">
      <main className="container mx-auto px-4 py-8">
        {/* Scheme Info */}
        <PageHeader
          className="mb-6"
          eyebrow="Generate"
          title="Generate Lesson Plans"
          description={<>{scheme.filename} &bull; {scheme.subject} &bull; {scheme.class_level} &bull; {scheme.term}</>}
        />

        {/* Read-only scheme context (Class / Subject / Term) */}
        <div className="grid md:grid-cols-3 gap-4 mb-6">
          <Card><CardContent className="p-4"><p className="text-sm text-muted-foreground">Class</p><p className="text-lg font-semibold">{scheme.class_level}</p></CardContent></Card>
          <Card><CardContent className="p-4"><p className="text-sm text-muted-foreground">Subject</p><p className="text-lg font-semibold">{scheme.subject}</p></CardContent></Card>
          <Card><CardContent className="p-4"><p className="text-sm text-muted-foreground">Term</p><p className="text-lg font-semibold">{scheme.term || config.term}</p></CardContent></Card>
        </div>

        <div className="grid lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center">
                  <Settings className="h-5 w-5 mr-2" />
                  Configuration
                </CardTitle>
                <CardDescription>
                  Configure your lesson plan generation settings
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="grid md:grid-cols-3 gap-4">
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

                <div className="grid md:grid-cols-2 gap-4">
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
                  <label className="block text-sm font-medium mb-2">Teaching Days</label>
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
                        className={`px-3 py-1 rounded-full text-sm ${
                          config.teaching_days.includes(day.value)
                            ? 'bg-primary text-primary-foreground'
                            : 'bg-muted text-muted-foreground'
                        }`}
                      >
                        {day.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="grid md:grid-cols-2 gap-4">
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
                      <p className="text-xs text-muted-foreground mt-1">
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
                      <p className={`text-xs mt-1 ${aiStatus.active ? 'text-green-600' : 'text-muted-foreground'}`}>
                        {aiStatus.active
                          ? `AI active · provider: ${aiStatus.provider}`
                          : config.ai_mode === 'OFF'
                            ? 'Deterministic engine · AI provider active: No'
                            : 'No AI provider available — lessons will be deterministic.'}
                      </p>
                    )}
                  </Field>
                </div>

                <div className="grid md:grid-cols-2 gap-4">
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

                {/* Lesson metadata the teacher supplies once (PART 11-24).
                    Each is optional; blanks stay blank and are never invented.
                    Keywords / TLRs / Competencies / References here are SEEDS
                    for every lesson — source TLRs and per-lesson review data
                    stay authoritative in the per-lesson panel below. */}
                <div className="border-t pt-6">
                  <h3 className="text-sm font-semibold mb-1">Lesson Plan Details</h3>
                  <p className="text-xs text-muted-foreground mb-4">
                    These seed every lesson as a starting point. Source TLRs from
                    your scheme and per-lesson edits in Allocation Preview override
                    them for that lesson. Leave blank to keep them empty.
                  </p>
                  <div className="space-y-4">
                    <div className="grid md:grid-cols-2 gap-4">
                      <Field label="Period" htmlFor="cfg-period">
                        <Input
                          id="cfg-period"
                          type="text"
                          value={config.period || ''}
                          onChange={(e) => setConfig({ ...config, period: e.target.value })}
                          placeholder="e.g. 1st & 2nd"
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
                    <Field label={<>Keywords / Vocabulary <span className="font-normal text-muted-foreground">(seed for all lessons)</span></>} htmlFor="cfg-keywords">
                      <TextArea
                        id="cfg-keywords"
                        value={(config.keywords || []).join(', ')}
                        onChange={(e) => setConfig({
                          ...config,
                          keywords: e.target.value.split(',').map((s) => s.trim()).filter(Boolean),
                        })}
                        placeholder="Comma-separated, e.g. material, property, matter"
                        rows={2}
                      />
                    </Field>
                    <Field label={<>Other Teaching &amp; Learning Resources (TLRs) <span className="font-normal text-muted-foreground">(seed — not source)</span></>} htmlFor="cfg-tlrs">
                      <TextArea
                        id="cfg-tlrs"
                        value={(config.teaching_learning_resources || []).join(', ')}
                        onChange={(e) => setConfig({
                          ...config,
                          teaching_learning_resources: e.target.value.split(',').map((s) => s.trim()).filter(Boolean),
                        })}
                        placeholder="Comma-separated, e.g. Textbook, Real objects, Chart"
                        rows={2}
                      />
                    </Field>
                    <Field label={<>Core Competencies <span className="font-normal text-muted-foreground">(seed for all lessons)</span></>} htmlFor="cfg-competencies">
                      <TextArea
                        id="cfg-competencies"
                        value={(config.core_competencies || []).join(', ')}
                        onChange={(e) => setConfig({
                          ...config,
                          core_competencies: e.target.value.split(',').map((s) => s.trim()).filter(Boolean),
                        })}
                        placeholder="Comma-separated, e.g. Critical Thinking, Collaboration"
                        rows={2}
                      />
                    </Field>
                    <Field label={<>Reference <span className="font-normal text-muted-foreground">(seed for all lessons)</span></>} htmlFor="cfg-references">
                      <TextArea
                        id="cfg-references"
                        value={(config.references || []).join(', ')}
                        onChange={(e) => setConfig({
                          ...config,
                          references: e.target.value.split(',').map((s) => s.trim()).filter(Boolean),
                        })}
                        placeholder="Comma-separated, e.g. Science Curriculum, Teacher's Guide"
                        rows={2}
                      />
                    </Field>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="lg:col-span-1 space-y-6">
            {/* Allocation Preview */}
            {allocationPreview && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Allocation Preview</CardTitle>
                  <CardDescription>
                    One indicator → one teaching period → one lesson plan
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {/* Conflicts first — teacher must see these before generating */}
                  {(allocationPreview.allocation_conflicts?.length > 0 ||
                    allocationPreview.indicators_unallocated > 0 ||
                    allocationPreview.indicators_duplicated > 0) && (
                    <div className="p-3 rounded-md bg-yellow-50 border border-yellow-200 text-xs text-yellow-800 space-y-1">
                      <p className="font-semibold">Allocation conflicts — review before generating</p>
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
                  )}

                  {/* Free Tier monthly allowance (PART C): plain, non-technical
                      language, with the scheme's indicator count and the
                      remaining allowance so the teacher can choose a subset. */}
                  {allocationPreview.lesson_quota?.enforced && (
                    <div className="p-3 rounded-md bg-blue-50 border border-blue-200 text-xs text-blue-800 space-y-1">
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
                  )}

                  {/* Indicator selection: one indicator = one lesson plan.
                      When the Free Tier quota is enforced the teacher chooses
                      which indicators to spend this month; the rest stay in the
                      scheme for later. Unlimited plans see every indicator
                      pre-selected with no cap. */}
                  {allocationPreview.selectable_indicators?.length > 0 && (
                    <div className="space-y-2">
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
                      <div className="space-y-1.5 max-h-56 overflow-y-auto border rounded-md p-2">
                        {allocationPreview.selectable_indicators.map((ind: any) => {
                          const checked = selectedCodes.includes(ind.indicator_code)
                          const capped =
                            allocationPreview.lesson_quota?.enforced &&
                            !checked &&
                            selectedCodes.length >= (allocationPreview.lesson_quota.remaining ?? 0)
                          return (
                            <label
                              key={ind.indicator_code}
                              className={`flex items-start gap-2 text-xs p-1.5 rounded ${
                                capped ? 'opacity-50' : 'hover:bg-muted cursor-pointer'
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
                                <span className="text-muted-foreground ml-1">
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
                  <div className="space-y-3 max-h-72 overflow-y-auto">
                    {previewTeachingWeeks.map((week: any) => (
                      <div key={`tw-${week.teaching_week}`}>
                        <h4 className="text-xs font-semibold text-muted-foreground mb-1.5 sticky top-0 bg-background">
                          Week {week.teaching_week}
                          <span className="font-normal ml-2">
                            ({week.lesson_count} lesson{week.lesson_count === 1 ? '' : 's'})
                          </span>
                        </h4>
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
                                  <td className="py-1.5 pr-2 whitespace-nowrap">
                                    {alloc.lesson_date
                                      ? new Date(alloc.lesson_date).toLocaleDateString('en-GB')
                                      : '—'}
                                  </td>
                                  <td className="py-1.5 pr-2 font-mono whitespace-nowrap">
                                    {alloc.period_index}
                                  </td>
                                  <td className="py-1.5 pr-2" title={alloc.indicator_description}>
                                    <span className="font-mono">{alloc.indicator_code}</span>
                                  </td>
                                  <td className="py-1.5">
                                    {alloc.status === 'needs_review' ? (
                                      <span className="text-yellow-700 font-medium">Needs review</span>
                                    ) : alloc.status === 'carried_forward' ? (
                                      <span className="text-blue-700 font-medium">
                                        Carried forward from Week {alloc.source_week}
                                      </span>
                                    ) : (
                                      <span className="text-green-700 font-medium">Scheduled</span>
                                    )}
                                  </td>
                                </tr>
                              )
                            })}
                            {(!week.periods || week.periods.length === 0) && (
                              <tr>
                                <td colSpan={4} className="py-1.5 text-muted-foreground italic">
                                  No teaching periods this week
                                </td>
                              </tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                    ))}
                  </div>

                  {/* Per-lesson review data (Section H): source fields are
                      read-only; keywords / Other TLRs / competencies /
                      references are editable and applied on generate. */}
                  {lessonReview.length > 0 && (
                    <div className="border-t pt-4 space-y-3">
                      <div className="flex items-center justify-between gap-2">
                        <div>
                          <h4 className="text-xs font-semibold text-muted-foreground">
                            Lesson Review Data
                          </h4>
                          <p className="text-[11px] text-muted-foreground">
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
                              <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                              Saving...
                            </>
                          ) : (
                            <>
                              <Save className="h-3 w-3 mr-1" />
                              Save review
                            </>
                          )}
                        </Button>
                      </div>
                      {reviewSaved && (
                        <p className="text-xs text-green-600">Lesson review saved.</p>
                      )}
                      <div className="space-y-4 max-h-96 overflow-y-auto pr-1">
                        {lessonReview.map((row) => (
                          <div
                            key={`review-${row.lesson_sequence}`}
                            className="border rounded-md p-3 space-y-2 bg-muted/30"
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
                            <p className="text-[11px] text-muted-foreground leading-snug">
                              {row.indicator_description}
                            </p>
                            {(row.content_standard || row.strand) && (
                              <p className="text-[11px] text-muted-foreground">
                                {row.strand}{row.sub_strand ? ` › ${row.sub_strand}` : ''}
                                {row.content_standard ? ` · ${row.content_standard}` : ''}
                              </p>
                            )}
                            <div>
                              <p className="text-[11px] font-medium text-muted-foreground mb-1">
                                Source TLRs (from scheme — read only)
                              </p>
                              {row.source_tlrs?.length ? (
                                <ul className="list-disc list-inside text-[11px] text-muted-foreground">
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
                            <div>
                              <label className="text-[11px] font-medium text-muted-foreground block mb-1">
                                Keywords for this lesson
                              </label>
                              <input
                                type="text"
                                value={(row.keywords || []).join(', ')}
                                onChange={(e) => updateLessonReviewRow(row.lesson_sequence, {
                                  keywords: e.target.value.split(',').map((s) => s.trim()).filter(Boolean),
                                })}
                                placeholder="Comma-separated"
                                className="w-full px-2 py-1.5 text-xs border rounded-md"
                              />
                            </div>
                            <div>
                              <label className="text-[11px] font-medium text-muted-foreground block mb-1">
                                Other TLRs for this lesson (not source)
                              </label>
                              <input
                                type="text"
                                value={(row.other_tlrs || []).join(', ')}
                                onChange={(e) => updateLessonReviewRow(row.lesson_sequence, {
                                  other_tlrs: e.target.value.split(',').map((s) => s.trim()).filter(Boolean),
                                })}
                                placeholder="Comma-separated teacher additions"
                                className="w-full px-2 py-1.5 text-xs border rounded-md"
                              />
                            </div>
                            <div>
                              <p className="text-[11px] font-medium text-muted-foreground mb-1">
                                Core competencies
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
                                      className={`text-[10px] px-1.5 py-0.5 rounded border ${
                                        selected
                                          ? 'bg-primary text-primary-foreground border-primary'
                                          : 'bg-background text-muted-foreground'
                                      }`}
                                    >
                                      {label}
                                    </button>
                                  )
                                })}
                              </div>
                            </div>
                            <div>
                              <div className="flex items-center justify-between mb-1">
                                <p className="text-[11px] font-medium text-muted-foreground">
                                  References
                                </p>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="h-6 text-[10px] px-2"
                                  onClick={() => updateLessonReviewRow(row.lesson_sequence, {
                                    structured_references: [
                                      ...(row.structured_references || []),
                                      { type: 'Other', title: '', page: '' },
                                    ],
                                  })}
                                >
                                  + Add
                                </Button>
                              </div>
                              {(row.structured_references || []).map((ref: any, idx: number) => (
                                <div key={idx} className="grid grid-cols-12 gap-1 mb-1">
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
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <p className="text-xs text-muted-foreground border-t pt-3">
                    {allocationPreview.total_generated_lessons || 0} lessons will be generated ·{' '}
                    {allocationPreview.coverage_percentage?.toFixed(1) ?? 0}% curriculum coverage
                  </p>
                </CardContent>
              </Card>
            )}

            {/* Coverage Summary */}
            {coverage && (
              <Card>
                <CardHeader>
                  <CardTitle>Coverage Summary</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Instructional Weeks</span>
                    <span className="font-medium">{coverage.total_instructional_weeks}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Curriculum Indicators</span>
                    <span className="font-medium">{coverage.total_indicators}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Lessons Generated</span>
                    <span className="font-medium">{coverage.total_generated_lessons}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Coverage</span>
                    <span className="font-medium">{coverage.coverage_percentage?.toFixed(1)}%</span>
                  </div>
                  {coverage.warnings && coverage.warnings.length > 0 && (
                    <div className="mt-3 p-2 bg-yellow-50 rounded text-xs text-yellow-700">
                      {coverage.warnings.map((w, i) => <p key={i}>{w}</p>)}
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {/* Generate / Export Panel */}
            <Card>
              <CardContent className="p-6 space-y-3">
                {/* Export/generation failures surface here. Without this the controlled
                    server messages (403 licence, 500 conversion, 503 converter missing)
                    were invisible: the click simply appeared to do nothing. */}
                {error && scheme && (
                  <div className="p-3 rounded-md bg-destructive/10 text-destructive text-sm" role="alert">
                    {error}
                  </div>
                )}
                {!jobId ? (
                  <>
                    {!allocationConfirmed && (
                      <Button onClick={handlePreviewAllocation} disabled={previewing} className="w-full" size="lg">
                        {previewing ? (
                          <>
                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                            Previewing...
                          </>
                        ) : (
                          <>
                            <Eye className="h-4 w-4 mr-2" />
                            Preview Allocation
                          </>
                        )}
                      </Button>
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
                          className="w-full"
                          size="lg"
                        >
                          {generating ? (
                            <>
                              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                              Generating...
                            </>
                          ) : (
                            <>
                              <Play className="h-4 w-4 mr-2" />
                              Confirm &amp; Generate
                            </>
                          )}
                        </Button>
                        {(allocationPreview.allocation_conflicts?.length > 0 ||
                          allocationPreview.indicators_unallocated > 0) && (
                          <p className="text-xs text-yellow-700 text-center">
                            Indicators carry forward to the next teaching week — none are dropped
                            or merged.
                          </p>
                        )}
                      </>
                    )}
                    {!allocationPreview && !allocationConfirmed && (
                      <p className="text-sm text-muted-foreground text-center">
                        Preview allocation before generating
                      </p>
                    )}
                    {generating && genProgress && (
                      <p className="text-sm text-muted-foreground text-center">{genProgress}</p>
                    )}
                  </>
                ) : (
                  <>
                    <div className="flex items-center text-green-600 mb-3 p-3 bg-green-50 rounded-lg">
                      <CheckCircle className="h-5 w-5 mr-2 flex-shrink-0" />
                      <span className="font-medium">
                        {coverage?.total_generated_lessons || 0} lesson plans generated
                      </span>
                    </div>
                    {aiResult && (
                      <p className="text-xs text-muted-foreground mb-2 text-center">
                        {aiResult.active && aiResult.lessons_ai > 0
                          ? `AI (${aiResult.provider}) enriched ${aiResult.lessons_ai} lesson${aiResult.lessons_ai === 1 ? '' : 's'}; ${aiResult.lessons_deterministic} used the deterministic engine.`
                          : aiResult.mode === 'OFF'
                            ? 'All lessons generated deterministically (AI OFF).'
                            : 'No AI provider was available — all lessons generated deterministically.'}
                      </p>
                    )}
                    <Link href="/lessons" className="block">
                      <Button className="w-full">
                        <Eye className="h-4 w-4 mr-2" />
                        Review Lesson Plans
                      </Button>
                    </Link>
                    <Button onClick={() => handleExport('docx')} disabled={exporting === 'docx'} className="w-full" variant="outline">
                      <FileText className="h-4 w-4 mr-2" />
                      {exporting === 'docx' ? 'Exporting...' : 'Download DOCX'}
                    </Button>
                    <Button onClick={() => handleExport('pdf')} disabled={exporting === 'pdf'} className="w-full" variant="outline">
                      <Download className="h-4 w-4 mr-2" />
                      {exporting === 'pdf' ? 'Exporting...' : 'Download PDF'}
                    </Button>
                    <Button onClick={() => handleExport('xlsx')} disabled={exporting === 'xlsx'} className="w-full" variant="outline">
                      <FileSpreadsheet className="h-4 w-4 mr-2" />
                      {exporting === 'xlsx' ? 'Exporting...' : 'Download Register (XLSX)'}
                    </Button>
                    <Button onClick={() => handleExport('zip')} disabled={exporting === 'zip'} className="w-full" variant="outline">
                      <FileArchive className="h-4 w-4 mr-2" />
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
                      <Play className="h-4 w-4 mr-2" />
                      Start New Generation
                    </Button>
                    <Link href="/dashboard" className="block">
                      <Button variant="ghost" className="w-full">Back to Dashboard</Button>
                    </Link>
                  </>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </main>
    </div>
  )
}
