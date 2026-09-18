'use client'

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Download, X } from 'lucide-react'

const DISMISS_KEY = 'SchemeKnit:install-dismissed'
const DISMISS_TTL_MS = 1000 * 60 * 60 * 24 * 30 // 30 days

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

/**
 * Subtle PWA install affordance.
 *
 * Only appears when the browser itself signals installability
 * (beforeinstallprompt) AND the user has not dismissed it recently. Browsers
 * that expose their own install UI (iOS Safari) never trigger the event, so
 * nothing is shown there. Never force-installs and never blocks content.
 */
export function PwaInstallPrompt() {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const dismissed = (() => {
      try {
        const raw = localStorage.getItem(DISMISS_KEY)
        if (!raw) return false
        const { at } = JSON.parse(raw)
        return Date.now() - at < DISMISS_TTL_MS
      } catch {
        return false
      }
    })()

    const onBeforeInstall = (e: Event) => {
      e.preventDefault()
      if (dismissed) return
      setDeferred(e as BeforeInstallPromptEvent)
      setVisible(true)
    }
    const onInstalled = () => {
      setVisible(false)
      setDeferred(null)
    }

    window.addEventListener('beforeinstallprompt', onBeforeInstall)
    window.addEventListener('appinstalled', onInstalled)
    return () => {
      window.removeEventListener('beforeinstallprompt', onBeforeInstall)
      window.removeEventListener('appinstalled', onInstalled)
    }
  }, [])

  const dismiss = () => {
    try {
      localStorage.setItem(DISMISS_KEY, JSON.stringify({ at: Date.now() }))
    } catch {
      // storage unavailable (private mode) — dismiss for this session only
    }
    setVisible(false)
  }

  const install = async () => {
    if (!deferred) return
    await deferred.prompt()
    const choice = await deferred.userChoice
    if (choice.outcome === 'accepted' || choice.outcome === 'dismissed') {
      setVisible(false)
      setDeferred(null)
    }
  }

  if (!visible) return null

  return (
    <div
      role="region"
      aria-label="Install SchemeKnit application"
      className="fixed bottom-4 left-1/2 z-40 w-[calc(100%-2rem)] max-w-sm -translate-x-1/2 sm:left-auto sm:right-4 sm:translate-x-0 rounded-lg border bg-card p-3 shadow-lg"
    >
      <div className="flex items-start gap-3">
        <Download className="h-5 w-5 mt-0.5 text-primary shrink-0" aria-hidden="true" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium">Install SchemeKnit</p>
          <p className="text-xs text-muted-foreground">
            Add it to your home screen for quick access.
          </p>
        </div>
        <button
          type="button"
          onClick={dismiss}
          aria-label="Dismiss install prompt"
          className="text-muted-foreground hover:text-foreground rounded p-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
      <div className="mt-2 flex justify-end gap-2">
        <Button type="button" size="sm" variant="ghost" onClick={dismiss}>
          Not now
        </Button>
        <Button type="button" size="sm" onClick={install}>
          Install
        </Button>
      </div>
    </div>
  )
}
