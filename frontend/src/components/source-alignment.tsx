'use client'

import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

import { cn } from '@/lib/utils'

/**
 * The source/alignment record for one lesson ("why this lesson?").
 * Mirrors the backend `curriculum.spine.lesson_provenance` shape.
 */
export interface LessonProvenance {
  scheme?: string
  curriculum_source?: string
  source_week?: number | null
  teaching_week?: number | null
  strand?: string
  sub_strand?: string
  content_standard?: string
  content_standard_code?: string
  indicator?: string
  indicator_text?: string
  period?: string
  carry_forward?: boolean
  generation?: string
  ai_provider?: string | null
  /** Faithful review state of the source week (never a parser score). */
  source_week_type?: string | null
  source_review_status?: 'ok' | 'needs_review' | 'special' | null
  source_review_reasons?: string[]
}

function Row({ label, value }: { label: string; value?: React.ReactNode }) {
  if (value === null || value === undefined || value === '') return null
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:gap-3">
      <dt className="w-40 shrink-0 text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </dt>
      <dd className="min-w-0 break-words text-sm text-[#102A43]">{value}</dd>
    </div>
  )
}

export interface SourceAlignmentProps {
  provenance?: LessonProvenance | null
  defaultOpen?: boolean
  className?: string
  /** Heading text; the review workspace uses "Why this lesson?". */
  title?: string
}

/**
 * Compact, collapsed-by-default provenance panel.
 *
 * Technical detail belongs here, behind a disclosure — never in the main
 * lesson surface. The panel answers "which part of my scheme produced this
 * lesson?" without turning the screen into an audit dashboard.
 */
export function SourceAlignment({
  provenance,
  defaultOpen = false,
  className,
  title = 'Source & alignment',
}: SourceAlignmentProps) {
  const [open, setOpen] = useState(defaultOpen)
  const p = provenance || {}

  const weekLine =
    p.source_week != null && p.teaching_week != null && p.teaching_week !== p.source_week
      ? `Week ${p.source_week} → taught in Week ${p.teaching_week}`
      : p.source_week != null
        ? `Week ${p.source_week}`
        : ''

  const summaryParts = [
    p.indicator ? `Indicator ${p.indicator}` : '',
    p.period ? `Period ${p.period}` : '',
  ].filter(Boolean)

  return (
    <div
      data-source-alignment
      className={cn('rounded-lg border border-slate-200 bg-slate-50/60', className)}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
      >
        {open ? (
          <ChevronDown className="h-4 w-4 shrink-0 text-slate-500" aria-hidden="true" />
        ) : (
          <ChevronRight className="h-4 w-4 shrink-0 text-slate-500" aria-hidden="true" />
        )}
        <span className="text-sm font-semibold text-[#102A43]">{title}</span>
        {summaryParts.length > 0 && (
          <span className="ml-auto hidden truncate text-xs text-muted-foreground sm:block">
            {summaryParts.join(' · ')}
          </span>
        )}
      </button>

      {open && (
        <dl className="space-y-2 border-t border-slate-200 px-3 py-3">
          <Row label="Scheme" value={p.scheme} />
          <Row label="Curriculum source" value={p.curriculum_source} />
          <Row label="Source week" value={weekLine} />
          <Row
            label="Strand"
            value={p.strand ? [p.strand, p.sub_strand].filter(Boolean).join(' › ') : ''}
          />
          <Row label="Content standard" value={p.content_standard} />
          <Row
            label="Indicator"
            value={
              p.indicator ? (
                <span>
                  <span className="font-mono">{p.indicator}</span>
                  {p.indicator_text ? ` — ${p.indicator_text}` : ''}
                </span>
              ) : (
                ''
              )
            }
          />
          <Row label="Teaching period" value={p.period} />
          <Row label="Generation" value={p.generation} />
          {p.source_review_status === 'needs_review' && (
            <Row
              label="Source check"
              value={
                <span className="text-amber-700">
                  ⚠ This source week needs review
                  {p.source_review_reasons?.length ? ` — ${p.source_review_reasons.join(' ')}` : ''}
                </span>
              }
            />
          )}
          {p.source_review_status === 'special' && (
            <Row label="Source check" value="Special period in your scheme" />
          )}
          {p.carry_forward && (
            <Row label="Note" value="Carried forward from an earlier curriculum week." />
          )}
        </dl>
      )}
    </div>
  )
}
