'use client'

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { draftAgeLabel } from '@/lib/drafts'
import type { DraftSaveStatus } from '@/hooks/use-form-draft'

export function DraftRecoveryBanner({
  updatedAt,
  label,
  onContinue,
  onDiscard,
}: {
  updatedAt: number
  label?: string
  onContinue: () => void
  onDiscard: () => void
}) {
  const time = new Date(updatedAt).toLocaleTimeString([], {
    hour: 'numeric',
    minute: '2-digit',
  })
  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-xl border border-[#04A9CE]/30 bg-[#04A9CE]/5 px-4 py-3"
      data-draft-recovery
    >
      <p className="text-sm font-medium text-[#102A43]">
        We found your unsaved work from {time}.
      </p>
      {label && <p className="mt-0.5 text-xs text-muted-foreground">{label}</p>}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button type="button" size="sm" onClick={onContinue}>
          Continue draft
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={onDiscard}>
          Discard draft
        </Button>
      </div>
    </div>
  )
}

export function DraftSaveStatus({ status, savedAt }: { status: DraftSaveStatus; savedAt: number | null }) {
  const [, setTick] = useState(0)

  useEffect(() => {
    if (status !== 'saved' || !savedAt) return
    const timer = setInterval(() => setTick((value) => value + 1), 30_000)
    return () => clearInterval(timer)
  }, [status, savedAt])

  if (status === 'idle' || (!savedAt && status !== 'saving' && status !== 'error')) {
    return null
  }

  const message =
    status === 'saving'
      ? 'Saving draft…'
      : status === 'error'
        ? 'Unable to save draft. Your work is still here.'
        : `Saved ${draftAgeLabel(savedAt || Date.now())}`

  return (
    <p
      className={`text-xs ${status === 'error' ? 'text-amber-700' : 'text-muted-foreground'}`}
      aria-live="polite"
      data-draft-status
    >
      {message}
    </p>
  )
}
