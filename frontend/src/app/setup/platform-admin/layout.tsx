import type { Metadata } from 'next'

/**
 * One-time staff bootstrap route. Never indexed; protection is server-side
 * (one-time bootstrap secret + backend gate).
 */
export const metadata: Metadata = {
  title: 'Platform Admin Setup',
  robots: { index: false, follow: false, nocache: true },
}

export default function PlatformAdminSetupLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return children
}
