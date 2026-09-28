'use client'

import { useState, useEffect } from 'react'
import { useRouter, useParams } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { SurfaceCard } from '@/components/ui/surface-card'
import { Banner } from '@/components/ui/banner'
import { StatusPill, type StatusTone } from '@/components/ui/badge'
import { PageHeader } from '@/components/ui/page-header'
import { ArrowLeft, ArrowRight, CheckCircle, AlertCircle, Info } from 'lucide-react'
import { api } from '@/lib/api'
import { resolveRouteId } from '@/lib/route-params'

interface WeekData {
  id: string
  week_number: number
  start_date: string
  end_date: string
  week_type: string
  week_type_label?: string
  strand: string | null
  sub_strand: string | null
  content_standards: string[]
  indicators: string[]
  resources: string[]
  special_period_label?: string
  special_period_type?: string
  // Source-defined segments (real-use remediation, Defect 5): a special period
  // and the teaching content of the same week are shown as separate spans.
  special_segments?: { type: string; label: string; start: string | null; end: string | null }[]
  teaching_segments?: { start: string | null; end: string | null }[]
  // Teacher-facing extraction review state (from the curriculum spine).
  // Never raw parser diagnostics.
  review_status?: 'ok' | 'needs_review' | 'special' | 'mixed'
  review_reasons?: string[]
}

function firstIndicatorCode(text: string): string {
  const m = /[A-Za-z]?\d+\.\d+\.\d+\.\d+(?:\.\d+)?/.exec(text || '')
  return m ? m[0] : ''
}

function firstIndicatorText(text: string): string {
  const code = firstIndicatorCode(text)
  return code ? (text || '').slice((text || '').indexOf(code) + code.length).replace(/^[:.\s]+/, '') : (text || '')
}

interface SchemeData {
  id: string
  filename: string
  subject: string
  class_level: string
  term: string
  academic_year: string
  weeks_count: number
  status: string
  // Multi-subject detection (§4)
  detection_status?: string
  detected_subjects?: string[]
  needs_subject_confirmation?: boolean
}

const WEEK_TYPE_LABELS: Record<string, string> = {
  instruction: 'Instruction',
  revision: 'Revision',
  assessment: 'Assessment',
  sba: 'SBA',
  mixed: 'Mixed week',
  other: 'Other',
}

export default function ReviewPage() {
  const router = useRouter()
  const params = useParams()
  const schemeId = resolveRouteId(params.id, 'review')

  const [scheme, setScheme] = useState<SchemeData | null>(null)
  const [weeks, setWeeks] = useState<WeekData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedWeek, setSelectedWeek] = useState<number>(1)
  // Defect 2: does the SOURCE provide an Indicator column at all? Props that
  // come from the same endpoint as the weeks (never re-parsed here).
  const [sourceProvidesIndicators, setSourceProvidesIndicators] = useState<boolean>(true)
  const [validation, setValidation] = useState<any>(null)
  const [approving, setApproving] = useState(false)
  const [confirmingSubject, setConfirmingSubject] = useState<string | null>(null)

  useEffect(() => {
    loadSchemeData()
  }, [schemeId])

  const loadSchemeData = async () => {
    try {
      setLoading(true)
      const schemeData = await api.getScheme(schemeId)
      setScheme(schemeData)
      const weeksData = await api.getSchemeWeeks(schemeId)
      setWeeks(weeksData.weeks || [])
      // Defect 2: whether the source carries an Indicator column at all — the
      // difference between "parser could not read it" and "the source has none".
      if (typeof weeksData.source_provides_indicators === 'boolean') {
        setSourceProvidesIndicators(weeksData.source_provides_indicators)
      }
      if (weeksData.weeks && weeksData.weeks.length > 0) {
        setSelectedWeek(weeksData.weeks[0].week_number)
      }
      try {
        setValidation(await api.validateScheme(schemeId))
      } catch {
        setValidation(null)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load scheme data')
    } finally {
      setLoading(false)
    }
  }

  const handleApprove = async () => {
    try {
      setApproving(true)
      await api.approveScheme(schemeId)
      router.push(`/generate/${schemeId}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to approve scheme')
    } finally {
      setApproving(false)
    }
  }

  const handleConfirmSubject = async (subject: string) => {
    setConfirmingSubject(subject)
    setError(null)
    try {
      await api.confirmSubjectSection(schemeId, subject)
      await loadSchemeData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not confirm that subject')
    } finally {
      setConfirmingSubject(null)
    }
  }

  const currentWeek = weeks.find(w => w.week_number === selectedWeek)
  const weekTypeTone = (type: string): StatusTone => {
    const tones: Record<string, StatusTone> = {
      instruction: 'info',
      revision: 'warning',
      assessment: 'danger',
      sba: 'accent',
      mixed: 'warning',
      other: 'neutral',
    }
    return tones[type] || tones.other
  }
  const instructionalCount = weeks.filter(w => w.week_type === 'instruction').length
  const specialCount = weeks.length - instructionalCount
  const needsReviewWeeks = weeks.filter(w => w.review_status === 'needs_review')
  const needsReviewNumbers = needsReviewWeeks.map(w => w.week_number)

  const reviewStatusPill = (week: WeekData) => {
    if (week.review_status === 'needs_review') {
      return <StatusPill tone="warning">⚠ Needs review</StatusPill>
    }
    if (week.review_status === 'mixed' || week.week_type === 'mixed') {
      return <StatusPill tone="warning">◐ Mixed week</StatusPill>
    }
    if (week.review_status === 'special' || week.week_type !== 'instruction') {
      return (
        <StatusPill tone={weekTypeTone(week.week_type)}>
          ★ {week.week_type_label || WEEK_TYPE_LABELS[week.week_type] || week.week_type}
        </StatusPill>
      )
    }
    return <StatusPill tone="success">✓ Parsed</StatusPill>
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-muted-foreground">Loading scheme data...</p>
        </div>
      </div>
    )
  }

  if (error && !scheme) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center px-4">
        <SurfaceCard className="w-full max-w-md px-6 py-8 text-center">
          <AlertCircle className="mx-auto mb-4 h-12 w-12 text-destructive" aria-hidden="true" />
          <p className="mb-4 text-destructive">{error}</p>
          <Button onClick={loadSchemeData}>Try Again</Button>
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

  return (
    <div className="min-h-screen">
      <main className="container mx-auto px-4 py-8">
        {/* One h1, one obvious next action: approve what SchemeKnit read. */}
        <PageHeader
          className="mb-6"
          eyebrow="Review"
          title="Review Curriculum"
          description={
            <>
              Check what SchemeKnit extracted from{' '}
              <span className="font-medium text-[#102A43]">{scheme.filename}</span>, then approve
              to continue.
            </>
          }
          actions={
            <>
              <Button variant="outline" asChild>
                <Link href="/dashboard">Back to Dashboard</Link>
              </Button>
              <Button size="lg" onClick={handleApprove} disabled={approving}>
                <CheckCircle className="mr-2 h-4 w-4" />
                {approving ? 'Approving...' : 'Approve & Configure'}
              </Button>
            </>
          }
        />

        {/* Runtime errors (e.g. failed approve) surface inline, never silently. */}
        {error && scheme && (
          <Banner tone="danger" title="Action failed" className="mb-6">
            {error}
          </Banner>
        )}

        {/* Subject-section confirmation (§4). A document with several subjects
            must be confirmed before generation; nothing is generated from an
            unconfirmed section. */}
        {scheme.needs_subject_confirmation && (
          <Banner tone="warning" title="Multiple subjects detected" className="mb-6">
            <p>
              This document contains more than one subject. Choose the subject
              you are teaching — only that section will be used.
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              {(scheme.detected_subjects || []).map((s) => (
                <Button
                  key={s}
                  size="sm"
                  variant="outline"
                  className="whitespace-normal bg-white"
                  disabled={confirmingSubject !== null}
                  onClick={() => handleConfirmSubject(s)}
                >
                  {confirmingSubject === s ? 'Confirming…' : s}
                </Button>
              ))}
            </div>
          </Banner>
        )}

        {/* Extraction summary — SchemeKnit has understood this curriculum. */}
        <SurfaceCard
          data-extraction-summary
          accent="bg-gradient-to-r from-[#102A43] to-[#04A9CE]"
          className="mb-6 px-5 py-5 sm:px-6"
        >
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <CheckCircle className="h-5 w-5 shrink-0 text-green-600" aria-hidden="true" />
                <h2 className="truncate text-lg font-semibold text-[#102A43]">{scheme.filename}</h2>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                {scheme.subject} &bull; {scheme.class_level} &bull; {scheme.term} &bull; {scheme.academic_year}
              </p>
              <p className="mt-1 text-sm font-medium text-[#04769B]">
                {weeks.length} week{weeks.length === 1 ? '' : 's'} of curriculum read from this document
              </p>
            </div>
            <div className="flex gap-6 text-center">
              <div>
                <div className="text-xl font-bold text-[#102A43]">{weeks.length}</div>
                <div className="text-xs text-muted-foreground">Weeks extracted</div>
              </div>
              <div>
                <div className="text-xl font-bold text-[#102A43]">{instructionalCount}</div>
                <div className="text-xs text-muted-foreground">Instruction weeks</div>
              </div>
              <div>
                <div className="text-xl font-bold text-[#102A43]">{specialCount}</div>
                <div className="text-xs text-muted-foreground">Special weeks</div>
              </div>
            </div>
          </div>
          {validation && !validation.is_valid && (
            <Banner tone="warning" title="Check these before approving" className="mt-4">
              <ul className="list-disc space-y-1 pl-4">
                {validation.issues?.map((iss: any, i: number) => (
                  <li key={i}>{iss.message}</li>
                ))}
              </ul>
            </Banner>
          )}
        </SurfaceCard>

        {/* Extraction verification table — the teacher sees exactly what was
            read from their scheme and which weeks need a second look BEFORE
            trusting generation. Clicking a row selects that week. */}
        <SurfaceCard data-extraction-table className="mb-6 overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-5 py-4 sm:px-6">
            <div>
              <h2 className="text-lg font-semibold text-[#102A43]">Extracted curriculum</h2>
              <p className="text-sm text-muted-foreground">
                What SchemeKnit read from your document. Select a week to review it.
              </p>
            </div>
            {needsReviewWeeks.length > 0 && (
              <StatusPill tone="warning">
                {needsReviewWeeks.length} week{needsReviewWeeks.length === 1 ? '' : 's'} need review
              </StatusPill>
            )}
          </div>

          {weeks.length === 0 ? (
            <p className="px-5 py-6 text-sm text-muted-foreground sm:px-6">
              No weeks were extracted from this document.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[36rem] border-collapse text-sm">
                <thead>
                  <tr className="border-b border-slate-100 text-left text-xs uppercase tracking-wide text-slate-500">
                    <th className="px-4 py-2 font-semibold">Week</th>
                    <th className="px-4 py-2 font-semibold">Strand</th>
                    <th className="px-4 py-2 font-semibold">Sub-strand</th>
                    <th className="px-4 py-2 font-semibold">Indicator</th>
                    <th className="px-4 py-2 font-semibold">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {weeks.map((week) => {
                    const selected = week.week_number === selectedWeek
                    return (
                      <tr
                        key={`xt-${week.id}`}
                        onClick={() => setSelectedWeek(week.week_number)}
                        aria-selected={selected}
                        data-week-row={week.week_number}
                        data-needs-review={week.review_status === 'needs_review' ? 'true' : undefined}
                        className={`cursor-pointer border-b border-slate-50 transition-colors ${
                          selected
                            ? 'bg-[#102A43]/5'
                            : week.review_status === 'needs_review'
                              ? 'bg-amber-50/60 hover:bg-amber-50'
                              : 'hover:bg-slate-50'
                        }`}
                      >
                        <td className="whitespace-nowrap px-4 py-2.5 font-medium text-[#102A43]">
                          Week {week.week_number}
                          {week.special_period_label && (
                            <span className="ml-2 text-xs text-muted-foreground">
                              {week.special_period_label}
                            </span>
                          )}
                        </td>
                        <td className="max-w-[10rem] truncate px-4 py-2.5 text-muted-foreground" title={week.strand || ''}>
                          {week.strand || '—'}
                        </td>
                        <td className="max-w-[10rem] truncate px-4 py-2.5 text-muted-foreground" title={week.sub_strand || ''}>
                          {week.sub_strand || '—'}
                        </td>
                        <td className="px-4 py-2.5">
                          {week.indicators.length > 0 ? (
                            <span className="text-[#102A43]" title={week.indicators[0]}>
                              <span className="font-mono text-xs">
                                {firstIndicatorCode(week.indicators[0]) || '—'}
                              </span>
                              <span className="ml-1.5 text-muted-foreground">
                                {firstIndicatorText(week.indicators[0]).slice(0, 48)}
                                {firstIndicatorText(week.indicators[0]).length > 48 ? '…' : ''}
                              </span>
                              {week.indicators.length > 1 && (
                                <span className="ml-1.5 text-xs text-muted-foreground">
                                  +{week.indicators.length - 1} more
                                </span>
                              )}
                            </span>
                          ) : week.week_type === 'instruction' ? (
                            // Defect 2: "the parser could not read one" (the
                            // source DOES have an Indicator column elsewhere)
                            // and "the source has none" are DIFFERENT facts.
                            sourceProvidesIndicators ? (
                              <span className="italic text-amber-700">⚠ Needs review</span>
                            ) : (
                              <span className="italic text-muted-foreground">— Not provided in source</span>
                            )
                          ) : (
                            <span className="italic text-muted-foreground">—</span>
                          )}
                        </td>
                        <td className="whitespace-nowrap px-4 py-2.5">{reviewStatusPill(week)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          {needsReviewWeeks.length > 0 && (
            <div className="px-5 pb-5 sm:px-6">
              <Banner tone="warning" title="Some weeks need your review" className="mt-1">
                <ul className="list-disc space-y-1 pl-4">
                  {needsReviewWeeks.map((w) => (
                    <li key={`nr-${w.id}`}>
                      Week {w.week_number}: {(w.review_reasons || []).join(' ') || 'Check this week.'}
                    </li>
                  ))}
                </ul>
                <p className="mt-1">
                  You can still continue — these weeks stay exactly as read and are
                  never filled in with guessed content.
                </p>
              </Banner>
            </div>
          )}
        </SurfaceCard>

        <div className="grid gap-6 lg:grid-cols-4">
          {/* Sidebar - week navigation (self-start so it can stick beside the
              longer detail pane without changing the grid rhythm). */}
          <div className="lg:col-span-1 lg:sticky lg:top-20 lg:self-start">
            <SurfaceCard data-week-nav className="overflow-hidden">
              <div className="border-b border-slate-100 px-4 py-3">
                <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
                  Curriculum weeks
                </h2>
                <p className="text-sm text-muted-foreground">Select a week to review</p>
              </div>
              <nav
                aria-label="Weeks"
                className="max-h-[60vh] space-y-1 overflow-y-auto p-2"
              >
                {weeks.map((week) => (
                  <button
                    key={week.id}
                    onClick={() => setSelectedWeek(week.week_number)}
                    aria-current={selectedWeek === week.week_number ? 'true' : undefined}
                    data-nav-week={week.week_number}
                    className={`w-full rounded-lg px-3 py-2 text-left transition-colors ${
                      selectedWeek === week.week_number
                        ? 'bg-[#102A43] text-white'
                        : week.review_status === 'needs_review'
                          ? 'bg-amber-50 hover:bg-amber-100'
                          : 'hover:bg-slate-50'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium">Week {week.week_number}</span>
                      {/* The week's REVIEW state is what the teacher needs to see
                          here (Defect 3): an instructional week whose extraction
                          is uncertain must not be labelled "Instruction" as if
                          all were well. */}
                      {reviewStatusPill(week)}
                    </div>
                    <div
                      className={`text-xs ${
                        selectedWeek === week.week_number ? 'text-white/70' : 'text-muted-foreground'
                      }`}
                    >
                      {week.start_date} → {week.end_date}
                    </div>
                  </button>
                ))}
              </nav>
              <div className="flex justify-between border-t border-slate-100 px-4 py-3 text-sm">
                <span className="text-muted-foreground">
                  Total <span className="font-semibold text-[#102A43]">{weeks.length}</span>
                </span>
                <span className="text-muted-foreground">
                  Instruction{' '}
                  <span className="font-semibold text-[#102A43]">{instructionalCount}</span>
                </span>
                <span className="text-muted-foreground">
                  Special <span className="font-semibold text-[#102A43]">{specialCount}</span>
                </span>
              </div>
            </SurfaceCard>
          </div>

          {/* Main content - the selected week, one surface with clear sections. */}
          <div className="lg:col-span-3">
            {weeks.length === 0 ? (
              <SurfaceCard className="px-6 py-12 text-center">
                <Info className="mx-auto mb-4 h-12 w-12 text-muted-foreground" aria-hidden="true" />
                <p className="mb-4 text-muted-foreground">No weeks found in the scheme</p>
                <Button asChild>
                  <Link href="/dashboard">Go to Dashboard</Link>
                </Button>
              </SurfaceCard>
            ) : currentWeek ? (
              <>
                <SurfaceCard
                  data-week-detail
                  accent="bg-gradient-to-r from-[#102A43] to-[#04A9CE]"
                  className="px-5 py-5 sm:px-6"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h2 className="flex items-center gap-2 text-lg font-semibold text-[#102A43]">
                      Week {currentWeek.week_number}
                      <StatusPill tone={weekTypeTone(currentWeek.week_type)}>
                        {WEEK_TYPE_LABELS[currentWeek.week_type] || currentWeek.week_type}
                      </StatusPill>
                    </h2>
                    <p className="text-sm text-muted-foreground">
                      {currentWeek.start_date} → {currentWeek.end_date}
                    </p>
                  </div>

                  {/* Defect 3: clicking a needs-review week opens THIS pane — the
                      problematic field is named, the reason is stated in plain
                      language, and the continue action stays available. */}
                  {currentWeek.review_status === 'needs_review' && (
                    <Banner tone="warning" title="This week needs your review" className="mt-4" data-week-review-context>
                      <ul className="list-disc space-y-1 pl-4">
                        {(currentWeek.review_reasons || []).map((r, i) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                      {(!currentWeek.indicators || currentWeek.indicators.length === 0)
                        && currentWeek.week_type === 'instruction' && (
                        <p className="mt-2 text-sm">
                          <span className="font-medium">Indicator — ⚠ Needs review:</span>{' '}
                          SchemeKnit could not confidently read an indicator for this week.
                          The week stays exactly as read — nothing is guessed. You can still
                          continue; this week simply will not produce a lesson until its
                          indicator is available in the source.
                        </p>
                      )}
                    </Banner>
                  )}

                  {/* Defect 4/5: a mixed week shows its special period and its
                      teaching content as separate, source-defined segments. */}
                  {(currentWeek.week_type === 'mixed'
                    || (currentWeek.special_segments?.length ?? 0) > 0) && (
                    <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3" data-mixed-week-segments>
                      <p className="text-sm font-semibold text-[#102A43]">
                        ◐ Mixed week — special period and teaching content
                      </p>
                      {(currentWeek.special_segments || []).map((seg, i) => (
                        <p key={`sp-${i}`} className="mt-1 text-sm text-amber-800" data-special-segment>
                          <span className="font-medium">Special period: {seg.label}</span>
                          {seg.start && seg.end
                            ? ` · ${seg.start} → ${seg.end}`
                            : (seg.start || seg.end
                                ? ` · ${seg.start || seg.end}`
                                : '')}
                          {' '}(not a lesson)
                        </p>
                      ))}
                      {(currentWeek.teaching_segments || []).map((seg, i) => (
                        <p key={`ts-${i}`} className="mt-1 text-sm text-[#102A43]" data-teaching-segment>
                          <span className="font-medium">Teaching:</span>{' '}
                          {seg.start && seg.end ? `${seg.start} → ${seg.end}` : 'dates as in the source'}
                          {currentWeek.strand ? ` · ${currentWeek.strand}` : ''}
                        </p>
                      ))}
                    </div>
                  )}

                  {currentWeek.strand && (
                    <section className="mt-4" aria-label="Strand">
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                        Strand
                      </h3>
                      <p className="mt-1 text-lg font-semibold text-[#102A43]">
                        {currentWeek.strand}
                      </p>
                      {currentWeek.sub_strand && (
                        <p className="mt-1 text-sm text-muted-foreground">
                          <span className="font-medium">Sub-strand:</span> {currentWeek.sub_strand}
                        </p>
                      )}
                    </section>
                  )}

                  {currentWeek.content_standards.length > 0 && (
                    <section
                      className="mt-4 border-t border-slate-100 pt-4"
                      aria-label="Content standards"
                    >
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                        Content Standards
                      </h3>
                      <ul className="mt-2 space-y-2">
                        {currentWeek.content_standards.map((cs, idx) => (
                          <li key={idx} className="rounded-lg bg-slate-50 px-3 py-2 text-sm">
                            {cs}
                          </li>
                        ))}
                      </ul>
                    </section>
                  )}

                  {currentWeek.indicators.length > 0 && (
                    <section
                      className="mt-4 border-t border-slate-100 pt-4"
                      aria-label="Indicators of adjustment to learning"
                    >
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                        Indicators
                      </h3>
                      <ul className="mt-2 space-y-2">
                        {currentWeek.indicators.map((ind, idx) => (
                          <li key={idx} className="flex items-start gap-2.5 text-sm">
                            <span
                              aria-hidden="true"
                              className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#04A9CE]"
                            />
                            <span>{ind}</span>
                          </li>
                        ))}
                      </ul>
                    </section>
                  )}

                  {/* Defect 2: "the source provides no indicator" is a DIFFERENT
                      fact from "the parser could not read one". A special/
                      mixed week never claims either — it is just not a lesson
                      week. Data stays exactly as read from the source. */}
                  {currentWeek.indicators.length === 0 && currentWeek.week_type !== 'instruction' && (
                    <section className="mt-4 border-t border-slate-100 pt-4" aria-label="Indicators">
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                        Indicators
                      </h3>
                      <p className="mt-2 text-sm italic text-muted-foreground">—</p>
                    </section>
                  )}

                  {currentWeek.resources.length > 0 && (
                    <section className="mt-4 border-t border-slate-100 pt-4" aria-label="Resources">
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                        Teaching &amp; Learning Resources
                      </h3>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {currentWeek.resources.map((res, idx) => (
                          <span
                            key={idx}
                            className="rounded bg-[#102A43]/8 px-2 py-1 text-sm text-[#102A43]"
                          >
                            {res}
                          </span>
                        ))}
                      </div>
                    </section>
                  )}
                </SurfaceCard>

                {/* Navigation + approve (wrapped at every width). */}
                <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex flex-wrap items-center gap-2">
                    {selectedWeek > weeks[0]?.week_number && (
                      <Button variant="outline" onClick={() => setSelectedWeek(selectedWeek - 1)}>
                        <ArrowLeft className="mr-2 h-4 w-4" /> Previous
                      </Button>
                    )}
                    {selectedWeek < weeks[weeks.length - 1]?.week_number && (
                      <Button variant="outline" onClick={() => setSelectedWeek(selectedWeek + 1)}>
                        Next <ArrowRight className="ml-2 h-4 w-4" />
                      </Button>
                    )}
                    <span className="text-sm text-muted-foreground">
                      Week {selectedWeek} of {weeks.length}
                    </span>
                  </div>
                  <Button onClick={handleApprove} disabled={approving} size="lg">
                    <CheckCircle className="mr-2 h-4 w-4" />
                    {approving ? 'Approving...' : 'Approve & Configure'}
                  </Button>
                </div>
              </>
            ) : null}
          </div>
        </div>
      </main>
    </div>
  )
}
