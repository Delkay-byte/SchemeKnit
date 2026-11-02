'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { readDraft, removeDraft, saveDraft } from '@/lib/drafts'

export type DraftSaveStatus = 'idle' | 'saving' | 'saved' | 'error'

export interface RecoveredDraft<T> {
  data: T
  updatedAt: number
}

export interface UseFormDraftOptions<T> {
  /** Authenticated user id. Drafts are disabled when this is null. */
  userId?: string | null
  workflow: string
  resourceId?: string
  /** Current form value. Persisted after the debounce interval. */
  value: T
  /** Set false until the form is ready to save (for example while loading). */
  enabled?: boolean
  debounceMs?: number
}

export interface UseFormDraftResult<T> {
  /** True once the stored draft has been checked. */
  checked: boolean
  recovered: RecoveredDraft<T> | null
  status: DraftSaveStatus
  savedAt: number | null
  /** Apply the recovered draft to the form and resume saving. */
  accept: () => T | null
  /** Delete the recovered draft and resume saving the current value. */
  discard: () => void
  /** Delete the stored draft (after successful completion). */
  clear: () => void
  /** Persist immediately instead of waiting for the debounce. */
  flush: () => void
}

/**
 * Debounced form-draft persistence with explicit recovery.
 *
 * The hook never applies a draft by itself: the caller decides whether the
 * unsaved local copy should replace current form state. This prevents an old
 * draft from silently overwriting newer server data.
 */
export function useFormDraft<T>({
  userId,
  workflow,
  resourceId,
  value,
  enabled = true,
  debounceMs = 700,
}: UseFormDraftOptions<T>): UseFormDraftResult<T> {
  const identity = useMemo(
    () => (userId ? { userId, workflow, resourceId } : null),
    [userId, workflow, resourceId],
  )
  const [checked, setChecked] = useState(false)
  const [recovered, setRecovered] = useState<RecoveredDraft<T> | null>(null)
  const [status, setStatus] = useState<DraftSaveStatus>('idle')
  const [savedAt, setSavedAt] = useState<number | null>(null)

  const valueRef = useRef(value)
  valueRef.current = value
  const identityRef = useRef(identity)
  identityRef.current = identity

  // Load the stored draft whenever the identity changes.
  useEffect(() => {
    setChecked(false)
    setRecovered(null)
    setStatus('idle')
    setSavedAt(null)
    if (!identity) {
      setChecked(true)
      return
    }
    const stored = readDraft<T>(identity)
    if (stored) {
      setRecovered({ data: stored.data, updatedAt: stored.updatedAt })
      setSavedAt(stored.updatedAt)
    }
    setChecked(true)
  }, [identity])

  const active = Boolean(identity && enabled && checked && !recovered)
  const serialized = JSON.stringify(value)

  // Debounced persistence. A pending timer is flushed on unmount.
  useEffect(() => {
    if (!active || !identityRef.current) return
    setStatus('saving')
    const timer = setTimeout(() => {
      const current = identityRef.current
      if (!current) return
      const result = saveDraft(current, valueRef.current)
      if (result.ok) {
        const now = Date.now()
        setStatus('saved')
        setSavedAt(now)
      } else {
        setStatus('error')
      }
    }, debounceMs)
    return () => clearTimeout(timer)
    // serialized is the change signal; value itself is recreated each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serialized, active, debounceMs])

  const flush = useCallback(() => {
    const current = identityRef.current
    if (!current) return
    const result = saveDraft(current, valueRef.current)
    if (result.ok) {
      setStatus('saved')
      setSavedAt(Date.now())
    } else {
      setStatus('error')
    }
  }, [])

  // Best-effort flush on tab hide/unmount. beforeunload alone is unreliable.
  useEffect(() => {
    if (!active) return
    const onHide = () => {
      if (document.visibilityState === 'hidden') flush()
    }
    document.addEventListener('visibilitychange', onHide)
    return () => {
      document.removeEventListener('visibilitychange', onHide)
      flush()
    }
  }, [active, flush])

  const accept = useCallback((): T | null => {
    if (!recovered) return null
    if (identityRef.current) removeDraft(identityRef.current)
    const data = recovered.data
    setRecovered(null)
    setStatus('saved')
    setSavedAt(recovered.updatedAt)
    return data
  }, [recovered])

  const discard = useCallback(() => {
    if (identityRef.current) removeDraft(identityRef.current)
    setRecovered(null)
    setStatus('idle')
    setSavedAt(null)
  }, [])

  const clear = useCallback(() => {
    if (identityRef.current) removeDraft(identityRef.current)
    setRecovered(null)
    setStatus('idle')
    setSavedAt(null)
  }, [])

  return { checked, recovered, status, savedAt, accept, discard, clear, flush }
}
