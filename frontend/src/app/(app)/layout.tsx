'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Header } from '@/components/header'
import { useAuth } from '@/lib/auth-context'

/**
 * Teacher workspace route group — `(app)` (Batch 2, auth gate Batch 4).
 *
 * Route groups are organizational only: URLs, auth behavior, permissions,
 * API calls and redirects are unchanged. This layout renders the canonical
 * application header exactly once for the whole area (pages no longer embed
 * it) over a quiet static blueprint background.
 *
 * The gate matches the school-admin layout: while the stored session is
 * restoring show the standard app loader (never a blank screen), and send
 * logged-out visitors to `/login` instead of letting every page render its
 * own error state. Any authenticated user keeps access to every route here,
 * exactly as before.
 */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const { user, loading } = useAuth()

  useEffect(() => {
    if (!loading && !user) {
      router.push('/login')
    }
  }, [loading, user, router])

  if (loading || !user) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    )
  }

  return (
    <div className="min-h-screen app-blueprint">
      <Header />
      {children}
    </div>
  )
}
