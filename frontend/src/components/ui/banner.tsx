import * as React from 'react'
import { AlertCircle, AlertTriangle, CheckCircle2, Info } from 'lucide-react'

import { cn } from '@/lib/utils'

export type BannerTone = 'info' | 'success' | 'warning' | 'danger'

const TONE_CLASS: Record<BannerTone, string> = {
  info: 'border-blue-200 bg-blue-50 text-blue-800',
  success: 'border-green-200 bg-green-50 text-green-800',
  warning: 'border-amber-300 bg-amber-50 text-amber-800',
  danger: 'border-red-200 bg-red-50 text-red-800',
}

const TONE_ICON: Record<BannerTone, React.ReactNode> = {
  info: <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />,
  success: <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />,
  warning: <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />,
  danger: <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />,
}

export interface BannerProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'> {
  tone?: BannerTone
  title?: React.ReactNode
  action?: React.ReactNode
}

/**
 * Inline status/feedback banner. Tones map to the status colours already in
 * use across the app — no new semantic colours are introduced here.
 */
export function Banner({
  tone = 'info',
  title,
  action,
  className,
  children,
  ...props
}: BannerProps) {
  return (
    <div
      role={tone === 'danger' ? 'alert' : 'status'}
      className={cn(
        'flex items-start gap-3 rounded-lg border px-4 py-3 text-sm',
        TONE_CLASS[tone],
        className,
      )}
      {...props}
    >
      {TONE_ICON[tone]}
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold">{title}</p>}
        {children != null && (
          <div className={cn('break-words', title && 'mt-0.5')}>{children}</div>
        )}
      </div>
      {action}
    </div>
  )
}
