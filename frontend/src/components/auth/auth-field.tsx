'use client'

import * as React from 'react'

import { cn } from '@/lib/utils'

/**
 * Auth field label + control wrapper.
 * Associates the label with the input via htmlFor/id for accessibility.
 */
export function AuthField({
  id,
  label,
  hint,
  error,
  children,
  className,
}: {
  id: string
  label: string
  hint?: React.ReactNode
  error?: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <div className={cn('space-y-1.5', className)}>
      <label
        htmlFor={id}
        className="block text-sm font-semibold text-[#102A43]"
      >
        {label}
      </label>
      {children}
      {error ? (
        <p
          role="alert"
          className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-md px-2.5 py-1.5"
        >
          {error}
        </p>
      ) : hint ? (
        <p className="text-xs text-muted-foreground leading-relaxed">{hint}</p>
      ) : null}
    </div>
  )
}

/**
 * Small role pill shown on every auth card.
 */
export function RoleBadge({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.12em]',
        className,
      )}
    >
      {children}
    </span>
  )
}

/**
 * Accessible error banner for form-level failures.
 */
export function AuthError({ message }: { message?: string }) {
  if (!message) return null
  return (
    <p
      role="alert"
      className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2.5"
    >
      {message}
    </p>
  )
}
