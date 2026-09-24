import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

export interface PageHeaderProps {
  /** Optional small label above the title (e.g. UPLOAD, PLATFORM). */
  eyebrow?: ReactNode
  /** Page title — the single h1 of the page. */
  title: ReactNode
  /** Muted supporting line. */
  description?: ReactNode
  /** Primary actions, right-aligned on wide screens. */
  actions?: ReactNode
  className?: string
}

/**
 * Shared page header (Batch 2) — a hierarchy system, not a rigid card.
 *
 * Eyebrow and actions are optional so pages keep their own voice: some show
 * only a title, others pair a description or a right-hand action cluster.
 * Always renders semantic heading structure (one h1 per page) and the
 * `data-page-header` marker used by the app-chrome acceptance gate.
 */
export function PageHeader({ eyebrow, title, description, actions, className }: PageHeaderProps) {
  return (
    <div
      data-page-header
      className={cn('flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between', className)}
    >
      <div className="min-w-0 space-y-1">
        {eyebrow && (
          <p className="text-xs font-semibold uppercase tracking-wider text-[#04769B]">
            {eyebrow}
          </p>
        )}
        <h1 className="text-2xl font-bold tracking-tight text-[#102A43]">{title}</h1>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}
