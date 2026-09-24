'use client'

import { Header } from '@/components/header'

/**
 * Teacher workspace route group — `(app)` (Batch 2).
 *
 * Route groups are organizational only: URLs, auth behavior, permissions,
 * API calls and redirects are unchanged. This layout renders the canonical
 * application header exactly once for the whole area (pages no longer embed
 * it) over a quiet static blueprint background.
 */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen app-blueprint">
      <Header />
      {children}
    </div>
  )
}
