import * as React from 'react'

import { cn } from '@/lib/utils'

/**
 * Light-surface field wrapper: label + control + hint/error.
 * Same contract as AuthField (error announced via role="alert"), for app pages.
 */
export interface FieldProps {
  label?: React.ReactNode
  htmlFor?: string
  hint?: React.ReactNode
  error?: React.ReactNode
  required?: boolean
  className?: string
  children: React.ReactNode
}

export function Field({
  label,
  htmlFor,
  hint,
  error,
  required,
  className,
  children,
}: FieldProps) {
  return (
    <div className={cn('space-y-1.5', className)}>
      {label != null && (
        <label
          htmlFor={htmlFor}
          className="text-sm font-semibold leading-none text-[#102A43]"
        >
          {label}
          {required && <span className="ml-0.5 text-destructive">*</span>}
        </label>
      )}
      {children}
      {error ? (
        <p role="alert" className="text-xs font-medium text-destructive">
          {error}
        </p>
      ) : hint ? (
        <p className="text-xs text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  )
}

export interface TextAreaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {}

export const TextArea = React.forwardRef<HTMLTextAreaElement, TextAreaProps>(
  function TextArea({ className, ...props }, ref) {
    return (
      <textarea
        ref={ref}
        className={cn(
          'flex min-h-[80px] w-full rounded-lg border border-input bg-white px-3.5 py-2 text-sm text-[#102A43]',
          'shadow-[0_1px_2px_rgba(16,42,67,0.04)] transition-all duration-150',
          'placeholder:text-muted-foreground',
          'hover:border-[#04A9CE]/45',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE]/45 focus-visible:border-[#04A9CE]/70 focus-visible:shadow-[0_0_0_3px_rgba(4,169,206,0.16)]',
          'disabled:cursor-not-allowed disabled:opacity-60 disabled:bg-muted',
          'aria-[invalid=true]:border-destructive aria-[invalid=true]:ring-2 aria-[invalid=true]:ring-destructive/25',
          className,
        )}
        {...props}
      />
    )
  },
)
