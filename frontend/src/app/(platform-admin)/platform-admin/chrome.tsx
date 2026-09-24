'use client'

import { Header } from '@/components/header'

/**
 * Platform console chrome (Batch 2) — client shell for the staff console.
 *
 * The parent layout stays a server component (it exports route metadata);
 * this wrapper renders the canonical header once for the area over the
 * workspace blueprint background. No authorization behavior lives here.
 */
export function PlatformChrome({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen app-blueprint">
      <Header />
      {children}
    </div>
  )
}
