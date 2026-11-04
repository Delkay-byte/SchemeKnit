'use client'

import { useEffect, useState } from 'react'
import { Loader2, ShieldCheck } from 'lucide-react'

/**
 * SSO session handoff (platform-admin SSO completion).
 *
 * The backend's OIDC callback 303-redirects here with the native access token
 * in the URL FRAGMENT (`#token=...`) — never a query parameter — so the token
 * is not transmitted to any server, not logged by proxies, and is stripped
 * from the address bar immediately below.
 *
 * Storage matches the normal password login: tab-scoped sessionStorage
 * (`teachflow_token` / `teachflow_user`). A full-page replace back to the
 * console reboots AuthProvider from sessionStorage, exactly like a fresh tab
 * after sign-in.
 */
export default function PlatformAdminSsoCompletePage() {
  const [error, setError] = useState('')

  useEffect(() => {
    const hash = window.location.hash || ''
    const params = new URLSearchParams(
      hash.startsWith('#') ? hash.slice(1) : hash
    )
    const token = params.get('token') || ''

    // Strip the fragment from the address bar immediately (defense in depth:
    // the token must not linger in the URL, history entries or screen sharing).
    window.history.replaceState(null, '', window.location.pathname)

    if (!token) {
      setError(
        'No sign-in token was received. Please start again from the platform sign-in page.'
      )
      return
    }

    let cancelled = false
    ;(async () => {
      try {
        const { getApiBaseUrl } = await import('@/lib/api')
        const res = await fetch(`${getApiBaseUrl()}/api/auth/me`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (!res.ok) {
          if (!cancelled) setError('Sign-in could not be verified. Please try again.')
          return
        }
        const user = await res.json()
        sessionStorage.setItem('teachflow_token', token)
        sessionStorage.setItem('teachflow_user', JSON.stringify(user))
        // Full navigation so AuthProvider boots from sessionStorage, exactly
        // like a fresh tab after a normal password login.
        window.location.replace('/platform-admin')
      } catch {
        if (!cancelled) setError('Network error while completing sign-in. Please try again.')
      }
    })()

    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0f172a] px-4 text-slate-200">
      <div className="max-w-sm text-center">
        {error ? (
          <>
            <h1 className="mb-2 text-lg font-semibold">Sign-in incomplete</h1>
            <p className="text-sm text-slate-400">{error}</p>
            <a
              href="/login/platform-admin"
              className="mt-4 inline-block text-sm text-sky-400 underline"
            >
              Back to platform sign-in
            </a>
          </>
        ) : (
          <>
            <ShieldCheck className="mx-auto mb-3 h-8 w-8 text-sky-400" aria-hidden="true" />
            <p className="flex items-center justify-center gap-2 text-sm text-slate-400">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              Completing sign-in…
            </p>
          </>
        )}
      </div>
    </div>
  )
}
