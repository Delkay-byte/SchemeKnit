'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { LayoutDashboard, Users, Settings, Key } from 'lucide-react'
import { useAuth } from '@/lib/auth-context'
import { Header } from '@/components/header'
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

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <div className="container mx-auto px-4 py-6 max-w-6xl">
        <nav className="flex gap-2 mb-6 flex-wrap">
          {NAV.map((item) => {
            const active = item.exact ? pathname === item.href : pathname.startsWith(item.href)
            const Icon = item.icon
            return (
              <Link key={item.href} href={item.href}>
                <Button variant={active ? 'default' : 'outline'} size="sm">
                  <Icon className="h-4 w-4 mr-1.5" />
                  {item.label}
                </Button>
              </Link>
            )
          })}
        </nav>
        <main>{children}</main>
      </div>
    </div>
  )
}
