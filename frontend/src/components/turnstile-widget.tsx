'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Accessible Cloudflare Turnstile widget (Managed mode).
 *
 * The component only obtains a short-lived token. The backend is the authority
 * and verifies it with Siteverify; a successful-looking browser callback is
 * never treated as proof on its own.
 *
 * When `siteKey` is absent (local development without a widget) the component
 * renders nothing and the form behaves as before.
 */

declare global {
  interface Window {
    turnstile?: {
      render: (el: HTMLElement, options: Record<string, unknown>) => string
      reset: (widgetId?: string) => void
      remove: (widgetId?: string) => void
    }
  }
}

let scriptPromise: Promise<void> | null = null

function loadTurnstileScript(): Promise<void> {
  if (typeof window === 'undefined') return Promise.resolve()
  if (window.turnstile) return Promise.resolve()
  if (scriptPromise) return scriptPromise
  scriptPromise = new Promise<void>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(
      'script[data-schemeknit-turnstile="true"]',
    )
    if (existing) {
      existing.addEventListener('load', () => resolve(), { once: true })
      existing.addEventListener('error', () => reject(new Error('load')), { once: true })
      return
    }
    const script = document.createElement('script')
    script.src =
      'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
    script.async = true
    script.defer = true
    script.dataset.schemeknitTurnstile = 'true'
    script.onload = () => resolve()
    script.onerror = () => {
      scriptPromise = null
      reject(new Error('load'))
    }
    document.head.appendChild(script)
  })
  return scriptPromise
}

type Status = 'loading' | 'ready' | 'success' | 'expired' | 'error'

export interface TurnstileWidgetProps {
  siteKey?: string
  action: 'register' | 'login' | 'password_reset'
  onToken: (token: string) => void
  onExpire?: () => void
  onError?: () => void
  /** Increment to reset the widget (for example after a failed submit). */
  resetKey?: number
  className?: string
}

export function TurnstileWidget({
  siteKey,
  action,
  onToken,
  onExpire,
  onError,
  resetKey = 0,
  className = '',
}: TurnstileWidgetProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const widgetIdRef = useRef<string | null>(null)
  const renderedKeyRef = useRef<string>('')
  const [status, setStatus] = useState<Status>('loading')

  const reset = useCallback(() => {
    onToken('')
    setStatus('loading')
    if (widgetIdRef.current && window.turnstile) {
      try {
        window.turnstile.reset(widgetIdRef.current)
      } catch {
        setStatus('error')
      }
    }
  }, [onToken])

  useEffect(() => {
    if (!siteKey || !containerRef.current) return
    let cancelled = false

    const boot = async () => {
      try {
        await loadTurnstileScript()
        if (cancelled || !containerRef.current || !window.turnstile) return
        // A resetKey change re-renders a fresh widget so a consumed token can
        // never be reused and an expired challenge has a clear retry path.
        const renderKey = `${siteKey}:${action}:${resetKey}`
        if (renderedKeyRef.current === renderKey) return
        if (widgetIdRef.current && window.turnstile) {
          try {
            window.turnstile.remove(widgetIdRef.current)
          } catch {
            /* widget already gone */
          }
        }
        renderedKeyRef.current = renderKey
        widgetIdRef.current = window.turnstile.render(containerRef.current, {
          sitekey: siteKey,
          action,
          theme: 'auto',
          size: 'flexible',
          retry: 'auto',
          callback: (token: string) => {
            if (cancelled) return
            setStatus('success')
            onToken(token)
          },
          'expired-callback': () => {
            if (cancelled) return
            setStatus('expired')
            onToken('')
            onExpire?.()
          },
          'timeout-callback': () => {
            if (cancelled) return
            setStatus('expired')
            onToken('')
            onExpire?.()
          },
          'error-callback': () => {
            if (cancelled) return
            setStatus('error')
            onToken('')
            onError?.()
            return true
          },
        })
        setStatus('ready')
      } catch {
        if (!cancelled) {
          setStatus('error')
          onError?.()
        }
      }
    }

    void boot()
    return () => {
      cancelled = true
    }
    // onToken/onError are intentionally not dependencies: the parent passes
    // stable inline callbacks and a re-render must not discard a valid token.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteKey, action, resetKey])

  if (!siteKey) return null

  const message =
    status === 'success'
      ? 'Verification complete.'
      : status === 'expired'
        ? 'Verification expired. Please complete the challenge again.'
        : status === 'error'
          ? 'Verification could not load. Check your connection and retry.'
          : 'Complete the verification challenge to continue.'

  return (
    <div className={`space-y-2 ${className}`} role="group" aria-label="Bot verification">
      <div ref={containerRef} />
      <div className="flex items-center justify-between gap-3">
        <p
          className={`text-xs ${
            status === 'error' || status === 'expired'
              ? 'text-amber-700'
              : 'text-muted-foreground'
          }`}
          aria-live="polite"
        >
          {message}
        </p>
        {(status === 'expired' || status === 'error') && (
          <button
            type="button"
            onClick={reset}
            className="shrink-0 rounded-md border border-border bg-white px-2.5 py-1 text-xs font-semibold text-[#102A43] hover:border-[#04A9CE]/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE]/50"
          >
            Retry verification
          </button>
        )}
      </div>
    </div>
  )
}

/** Public site key from the build environment (safe to ship in the bundle). */
export const TURNSTILE_SITE_KEY =
  process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY || ''
