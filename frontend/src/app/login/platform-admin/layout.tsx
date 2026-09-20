import type { Metadata } from 'next'

/**
 * Staff-only route. Kept out of search engines and the public journey; the
 * backend still enforces authentication, authorization and rate limiting.
 */
export const metadata: Metadata = {
  title: 'Platform Admin Login',
  robots: { index: false, follow: false, nocache: true },
}

export default function PlatformAdminLoginLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return children
}
