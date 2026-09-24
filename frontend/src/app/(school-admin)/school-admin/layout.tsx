'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, ReactNode } from 'react'
import { LayoutDashboard, Users, Settings, Key } from 'lucide-react'
import { useAuth } from '@/lib/auth-context'
import { Header } from '@/components/header'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
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
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
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
        <Tabs value={activeSection} activationMode="manual" className="mb-6">
          <TabsList
            aria-label="School administration sections"
            className="h-auto max-w-full flex-wrap justify-start gap-1 bg-transparent p-0"
          >
            {NAV.map((item) => {
              const Icon = item.icon
              return (
                <TabsTrigger
                  key={item.href}
                  value={item.href}
                  asChild
                  className="gap-1.5 border border-border bg-background px-3 py-2 text-muted-foreground data-[state=active]:border-[#04A9CE]/40 data-[state=active]:bg-[#04A9CE]/10 data-[state=active]:text-[#04769B]"
                >
                  <Link
                    href={item.href}
                    aria-current={
                      item.exact
                        ? currentPath === item.href
                          ? 'page'
                          : undefined
                        : currentPath === item.href || currentPath.startsWith(item.href)
                          ? 'page'
                          : undefined
                    }
                  >
                    <Icon className="h-4 w-4" aria-hidden="true" />
                    {item.label}
                  </Link>
                </TabsTrigger>
              )
            })}
          </TabsList>
        </Tabs>
        <main>{children}</main>
      </div>
    </div>
  )
}
