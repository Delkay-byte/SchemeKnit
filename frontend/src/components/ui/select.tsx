import * as React from 'react'

import { cn } from '@/lib/utils'

/**
 * Shared native <select> styled to match Input.
 *
 * Deliberately native (not a Radix wrapper): existing acceptance suites drive
 * these controls with Playwright selectOption(), and native semantics keep
 * value/onChange behaviour identical to the markup being replaced.
 */
export interface SelectProps
  extends React.SelectHTMLAttributes<HTMLSelectElement> {}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  function Select({ className, children, ...props }, ref) {
    return (
      <select
        ref={ref}
        className={cn(
          'flex h-11 w-full rounded-lg border border-input bg-white px-3.5 py-2 text-sm text-[#102A43]',
          'shadow-[0_1px_2px_rgba(16,42,67,0.04)] transition-all duration-150',
          'hover:border-[#04A9CE]/45',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE]/45 focus-visible:border-[#04A9CE]/70 focus-visible:shadow-[0_0_0_3px_rgba(4,169,206,0.16)]',
          'disabled:cursor-not-allowed disabled:opacity-60 disabled:bg-muted',
          className,
        )}
        {...props}
      >
        {children}
      </select>
    )
  },
)
