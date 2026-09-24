import * as React from 'react'

import { cn } from '@/lib/utils'

/**
 * Premium auth form input — shared by login, registration and related forms.
 * Focus ring, hover and disabled states are defined once so every auth page
 * feels identical.
 */
export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  function Input({ className, type, ...props }, ref) {
    return (
      <input
        type={type}
        ref={ref}
        className={cn(
          'flex h-11 w-full rounded-lg border border-input bg-white px-3.5 py-2 text-sm text-[#102A43]',
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
