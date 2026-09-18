'use client'

import { useEffect } from 'react'
import { PwaInstallPrompt } from './install-prompt'

/**
 * Registers the SchemeKnit service worker and hosts the install prompt.
 *
 * Registration runs in production builds only: the dev server recompiles
 * assets on every change, so caching them would serve stale chunks locally.
 * The browser's installability signal (beforeinstallprompt) is a production
 * concern as well — see docs/PUBLIC_ENTRY_AND_INSTALLATION.md.
 */
export function PwaManager() {
  useEffect(() => {
    if (process.env.NODE_ENV !== 'production') return
    if (typeof window === 'undefined' || !('serviceWorker' in navigator)) return
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // Registration failing never blocks the app.
    })
  }, [])

  return <PwaInstallPrompt />
}
