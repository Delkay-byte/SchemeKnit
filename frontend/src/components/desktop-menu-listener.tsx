'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'

export function DesktopMenuListener() {
  const router = useRouter()
  const { logout } = useAuth()

  useEffect(() => {
    const api = (window as any).electronAPI
    if (!api?.onMenuAction) return

    const offNavigate = api.onMenuAction('menu:navigate', (p: string) => {
      router.push(p)
    })

    const offSave = api.onMenuAction('menu:save', () => {
      window.dispatchEvent(new CustomEvent('schemeknit:save'))
    })

    const offSignOut = api.onMenuAction('menu:sign-out', () => {
      logout()
      router.push('/')
    })

    return () => {
      offNavigate?.()
      offSave?.()
      offSignOut?.()
    }
  }, [router, logout])

  return null
}
