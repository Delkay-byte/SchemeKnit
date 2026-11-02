'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react'

export type ToastVariant =
  | 'default'
  | 'destructive'
  | 'success'
  | 'info'
  | 'warning'
  | 'error'

export interface ToastAction {
  label: string
  onClick: () => void
}

export interface ToastOptions {
  title: string
  description?: string
  variant?: ToastVariant
  /** Milliseconds before auto-dismiss. `null` keeps it until dismissed. */
  duration?: number | null
  action?: ToastAction
  /** Stable key used to suppress duplicate notifications. */
  key?: string
}

interface ToastRecord extends ToastOptions {
  id: string
  dedupeKey: string
}

let toastId = 0

export function toast(options: ToastOptions): string {
  const id = String(++toastId)
  if (typeof window === 'undefined') return id
  window.dispatchEvent(new CustomEvent('toast', { detail: { ...options, id } }))
  return id
}

function defaultDuration(variant: ToastVariant | undefined): number | null {
  if (variant === 'error' || variant === 'destructive') return null
  if (variant === 'warning') return 8000
  return 5000
}

function iconFor(variant: ToastVariant) {
  if (variant === 'success') return <CheckCircle2 className="h-5 w-5 text-emerald-600" aria-hidden="true" />
  if (variant === 'warning') return <AlertTriangle className="h-5 w-5 text-amber-600" aria-hidden="true" />
  if (variant === 'error' || variant === 'destructive') return <XCircle className="h-5 w-5 text-red-600" aria-hidden="true" />
  if (variant === 'info') return <Info className="h-5 w-5 text-[#04769B]" aria-hidden="true" />
  return <Info className="h-5 w-5 text-slate-500" aria-hidden="true" />
}

export function Toaster() {
  const [toasts, setToasts] = useState<ToastRecord[]>([])
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>())
  const activeKeys = useRef(new Set<string>())

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => {
      const target = prev.find((item) => item.id === id)
      if (target) activeKeys.current.delete(target.dedupeKey)
      return prev.filter((item) => item.id !== id)
    })
    const timer = timers.current.get(id)
    if (timer) clearTimeout(timer)
    timers.current.delete(id)
  }, [])

  useEffect(() => {
    const handleToast = (event: Event) => {
      const detail = (event as CustomEvent<ToastOptions & { id: string }>).detail
      if (!detail?.title) return
      const variant = detail.variant || 'default'
      const dedupeKey = detail.key || `${variant}|${detail.title}|${detail.description || ''}`
      if (activeKeys.current.has(dedupeKey)) return

      const record: ToastRecord = {
        ...detail,
        variant,
        duration: detail.duration === undefined ? defaultDuration(variant) : detail.duration,
        dedupeKey,
      }
      activeKeys.current.add(dedupeKey)
      setToasts((prev) => [...prev.slice(-3), record])

      if (record.duration !== null) {
        const timer = setTimeout(() => dismiss(record.id), record.duration)
        timers.current.set(record.id, timer)
      }
    }

    window.addEventListener('toast', handleToast)
    return () => window.removeEventListener('toast', handleToast)
  }, [dismiss])

  useEffect(() => {
    return () => {
      timers.current.forEach((timer) => clearTimeout(timer))
      timers.current.clear()
    }
  }, [])

  if (toasts.length === 0) return null

  return (
    <div
      className="pointer-events-none fixed inset-x-3 bottom-3 z-50 flex flex-col gap-2 sm:left-auto sm:right-4 sm:w-full sm:max-w-sm"
      aria-live="polite"
      aria-relevant="additions"
      data-toaster
    >
      {toasts.map((item) => {
        const variant = item.variant || 'default'
        const destructive = variant === 'error' || variant === 'destructive'
        return (
          <div
            key={item.id}
            role={destructive ? 'alert' : 'status'}
            data-toast-variant={variant}
            className={`pointer-events-auto rounded-xl border p-4 shadow-[0_16px_40px_rgba(16,42,67,0.18)] ${
              destructive
                ? 'border-red-200 bg-red-50 text-red-950'
                : variant === 'success'
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-950'
                  : variant === 'warning'
                    ? 'border-amber-200 bg-amber-50 text-amber-950'
                    : 'border-slate-200 bg-white text-[#102A43]'
            }`}
          >
            <div className="flex items-start gap-3">
              <span className="mt-0.5 shrink-0">{iconFor(variant)}</span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold">{item.title}</p>
                {item.description && (
                  <p className="mt-0.5 text-sm opacity-90">{item.description}</p>
                )}
                {item.action && (
                  <button
                    type="button"
                    className="mt-3 rounded-md border border-black/20 px-2.5 py-1 text-xs font-semibold hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE]/50"
                    onClick={() => {
                      dismiss(item.id)
                      item.action?.onClick()
                    }}
                  >
                    {item.action.label}
                  </button>
                )}
              </div>
              <button
                type="button"
                aria-label="Dismiss notification"
                className="shrink-0 rounded p-1 opacity-70 hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE]/50"
                onClick={() => dismiss(item.id)}
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
