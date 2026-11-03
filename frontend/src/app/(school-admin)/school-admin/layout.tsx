'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, ReactNode } from 'react'
import { LayoutDashboard, Users, Settings, Key } from 'lucide-react'
import { useAuth } from '@/lib/auth-context'
import { Header } from '@/components/header'
import { AppShellSkeleton } from '@/components/ui/skeleton'
import { isDesktop } from '@/lib/build-target'

const NAV = [
  { href: '/school-admin', label: 'School Dashboard', icon: LayoutDashboard, exact: true },
  { href: '/school-admin/teachers', label: 'Teachers', icon: Users, exact: false },
  { href: '/school-admin/settings', label: 'Settings', icon: Settings, exact: false },
  { href: '/school-admin/license', label: 'License', icon: Key, exact: false },
]

export default function SchoolAdminLayout({ children }: { children: ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const { user, loading } = useAuth()

  useEffect(() => {
    if (loading) return
    if (!user) {
      router.push('/login')
      return
    }
    // Strict role boundary: only school_admin belongs here.
    if (!isDesktop && user.role === 'platform_admin') {
      router.push('/platform-admin')
      return
    }
    if (user.role !== 'school_admin') {
      router.push('/dashboard')
    }
  }, [user, loading, router])

  if (loading || !user || user.role !== 'school_admin') {
    return (
      <div className="min-h-screen bg-background">
        <main className="container mx-auto px-4 py-8">
          <AppShellSkeleton />
        </main>
      </div>
    )
  }

  const currentPath = pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname
  const activeSection =
    NAV.find((item) =>
      item.exact ? currentPath === item.href : currentPath.startsWith(item.href),
    )?.href ?? ''

  return (
    <div className="min-h-screen app-blueprint">
      <Header />
      <div className="container mx-auto px-4 py-6 max-w-6xl">
        <nav aria-label="School administration sections" className="mb-6">
          <div className="flex h-auto max-w-full flex-wrap items-center justify-start gap-1">
            {NAV.map((item) => {
              const Icon = item.icon
              const active = item.exact
                ? currentPath === item.href
                : currentPath === item.href || currentPath.startsWith(item.href)
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? 'page' : undefined}
                  className={`inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md border px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ${
                    active
                      ? 'border-[#04A9CE]/40 bg-[#04A9CE]/10 text-[#035f7c]'
                      : 'border-border bg-background text-muted-foreground hover:bg-accent'
                  }`}
                >
                  <Icon className="h-4 w-4" aria-hidden="true" />
                  {item.label}
                </Link>
              )
            })}
          </div>
        </nav>
        <main>{children}</main>
      </div>
    </div>
  )
}
