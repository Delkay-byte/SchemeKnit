import type { Metadata } from 'next'
import { PlatformChrome } from './chrome'

/** Staff console — never indexed. */
export const metadata: Metadata = {
  title: 'Platform Administration',
  robots: { index: false, follow: false, nocache: true },
}

export default function PlatformAdminLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <PlatformChrome>{children}</PlatformChrome>
}
