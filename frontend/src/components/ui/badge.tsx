import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/lib/utils'
import { formatStatus, getStatusColor } from '@/lib/utils-display'

const badgeVariants = cva(
  'inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium transition-colors',
  {
    variants: {
      variant: {
        default: 'border-transparent bg-primary text-primary-foreground',
        secondary: 'border-transparent bg-secondary text-secondary-foreground',
        outline: 'border-border text-foreground',
        success: 'bg-green-100 text-green-800',
        info: 'bg-blue-100 text-blue-800',
        warning: 'bg-yellow-100 text-yellow-800',
        danger: 'bg-red-100 text-red-800',
        neutral: 'bg-gray-100 text-gray-800',
      },
    },
    defaultVariants: { variant: 'default' },
  },
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />
}

export type StatusTone =
  | 'success'
  | 'info'
  | 'warning'
  | 'caution'
  | 'accent'
  | 'danger'
  | 'neutral'

const STATUS_TONE_CLASS: Record<StatusTone, string> = {
  success: 'bg-green-100 text-green-800',
  info: 'bg-blue-100 text-blue-800',
  warning: 'bg-yellow-100 text-yellow-800',
  caution: 'bg-orange-100 text-orange-800',
  accent: 'bg-purple-100 text-purple-800',
  danger: 'bg-red-100 text-red-800',
  neutral: 'bg-gray-100 text-gray-800',
}

/**
 * Status pill for existing business statuses only — tone colors are fixed here
 * so every surface renders the same status the same way. Do not invent tones
 * for new states without a product decision.
 */
export interface StatusPillProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: StatusTone
}

export function StatusPill({
  tone = 'neutral',
  className,
  ...props
}: StatusPillProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded px-2 py-0.5 text-xs font-medium',
        STATUS_TONE_CLASS[tone],
        className,
      )}
      {...props}
    />
  )
}

/**
 * Status pill driven by the shared scheme-status colour map in
 * lib/utils-display.ts — colours and labels come from the existing
 * helpers, so business semantics cannot drift.
 */
export interface StatusFromKeyProps
  extends React.HTMLAttributes<HTMLSpanElement> {
  status: string
}

export function StatusFromKey({
  status,
  className,
  ...props
}: StatusFromKeyProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded px-2 py-0.5 text-xs font-medium',
        getStatusColor(status),
        className,
      )}
      {...props}
    >
      {formatStatus(status)}
    </span>
  )
}
