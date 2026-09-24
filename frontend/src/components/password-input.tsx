'use client'

import { useState, forwardRef } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * Password input with a show/hide eye control (PART 3).
 *
 * Every password field in the application uses this component so the behaviour
 * is defined once: the eye toggles visibility, preserves typed content, keeps
 * keyboard focus, never submits the form, and is labelled for screen readers.
 *
 * Accessibility notes:
 * - The toggle is a real <button type="button">, so it is focusable and
 *   activatable from the keyboard, and `type="button"` stops it submitting the
 *   enclosing form.
 * -Focus stays on the input: the button toggles state only and does not steal
 *   focus. Tabbing reaches the button as a normal control.
 * -The input's own label comes from the parent (aria-label / label element);
 *   the eye has its own aria-label describing what it does.
 */
export interface PasswordInputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {
  /** Accessible label for the eye toggle (e.g. "Show password"). */
  toggleLabel?: string
}

export const PasswordInput = forwardRef<HTMLInputElement, PasswordInputProps>(
  function PasswordInput(
    { toggleLabel = 'Show password', className = '', ...props },
    ref,
  ) {
    const [visible, setVisible] = useState(false)

    return (
      <div className="relative">
        <input
          {...props}
          ref={ref}
          type={visible ? 'text' : 'password'}
          className={cn(
            'flex h-11 w-full rounded-lg border border-input bg-white px-3.5 py-2 pr-10 text-sm text-[#102A43]',
            'shadow-[0_1px_2px_rgba(16,42,67,0.04)] transition-all duration-150',
            'placeholder:text-muted-foreground',
            'hover:border-[#04A9CE]/45',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE]/45 focus-visible:border-[#04A9CE]/70 focus-visible:shadow-[0_0_0_3px_rgba(4,169,206,0.16)]',
            'disabled:cursor-not-allowed disabled:opacity-60 disabled:bg-muted',
            'aria-[invalid=true]:border-destructive aria-[invalid=true]:ring-2 aria-[invalid=true]:ring-destructive/25',
            className,
          )}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? 'Hide password' : toggleLabel}
          aria-pressed={visible}
          // Keeps the input's typed content untouched and focus where it was.
          tabIndex={0}
          className="absolute inset-y-0 right-0 flex items-center px-3 text-muted-foreground hover:text-foreground focus:outline-none focus:ring-2 focus:ring-ring rounded-r-lg"
          title={visible ? 'Hide password' : 'Show password'}
        >
          {visible ? (
            <EyeOff className="h-4 w-4" aria-hidden="true" />
          ) : (
            <Eye className="h-4 w-4" aria-hidden="true" />
          )}
        </button>
      </div>
    )
  },
)

/**
 * Live password-match indicator (PART 5).
 *
 * Renders nothing while the confirmation field is empty (never a false "match"
 * on a blank field), shows an immediate mismatch/match as the user types, and
 * exposes whether the pair matches so the form can block submission.
 */
export function passwordMatchStatus(
  password: string,
  confirm: string,
): { matched: boolean; show: boolean } {
  const show = confirm.length > 0
  return { matched: show && password === confirm, show }
}

export interface PasswordMatchIndicatorProps {
  password: string
  confirm: string
}

export function PasswordMatchIndicator({
  password,
  confirm,
}: PasswordMatchIndicatorProps) {
  const { matched, show } = passwordMatchStatus(password, confirm)
  if (!show) return null
  return (
    <p
      role="status"
      aria-live="polite"
      className={`text-sm p-2 rounded ${
        matched
          ? 'text-green-700 bg-green-50'
          : 'text-destructive bg-destructive/10'
      }`}
    >
      {matched ? '✓ Passwords match' : '✕ Passwords do not match'}
    </p>
  )
}
