import * as React from 'react'

import { cn } from '@/lib/utils'

/**
 * Light-surface card with the auth DepthCard's elevation language
 * (brand-tinted shadow + optional gradient accent bar), for app pages.
 */
export interface SurfaceCardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Tailwind gradient classes for the 3px top accent bar, e.g. "bg-gradient-to-r from-emerald-600 to-[#04A9CE]". Omit for no bar. */
  accent?: string
  /** Heavier elevation (auth DepthCard level) for hero/feature cards. */
  elevated?: boolean
}

export function SurfaceCard({
  accent,
  elevated = false,
  className,
  children,
  ...props
}: SurfaceCardProps) {
  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-2xl border border-[#102A43]/8 bg-white text-[#102A43]',
        elevated
          ? 'shadow-[0_24px_55px_rgba(16,42,67,0.12)]'
          : 'shadow-[0_10px_30px_rgba(16,42,67,0.08)]',
        className,
      )}
      {...props}
    >
      {accent && (
        <div
          aria-hidden="true"
          className={cn('absolute inset-x-0 top-0 h-[3px]', accent)}
        />
      )}
      {children}
    </div>
  )
}
