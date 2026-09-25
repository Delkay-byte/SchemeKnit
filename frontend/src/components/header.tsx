'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { BookOpen, LogOut, LayoutDashboard, Upload, FileText, Settings, Users, Shield, Mail, Menu, X, CalendarDays } from 'lucide-react'
import { useAuth } from '@/lib/auth-context'
import { isDesktop } from '@/lib/build-target'
import { SchemeKnitMark } from '@/components/scheme-knit-mark'
import { WhatsAppIcon } from '@/components/whatsapp-button'
import { whatsappUrl, contactMailtoUrl, CONTACT_EMAIL } from '@/lib/contact'
import { cn } from '@/lib/utils'

interface NavItem {
  href: string
  label: string
  icon: LucideIcon
  exact: boolean
}

/**
 * Canonical application header (Batch 2).
 *
 * Rendered once per application area from the area's route-group layout —
 * never inline in individual pages. Dark navy chrome (#071826) with a brand
 * cyan active state (#04A9CE), sticky at the top of the workspace, correct
 * z-index (below dialogs/toasts at z-50), aria-current on the active link and
 * a keyboard-accessible mobile menu. The visual language is intentionally
 * quiet and structured — no landing mesh, no hero treatment.
 */
export function Header() {
  const { user, logout } = useAuth()
  const pathname = usePathname()
  const [menuOpen, setMenuOpen] = useState(false)

  // Close the mobile menu whenever the route changes or Escape is pressed.
  useEffect(() => {
    setMenuOpen(false)
  }, [pathname])
  useEffect(() => {
    if (!menuOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [menuOpen])

  const isActive = (path: string, exact = true) => {
    // Canonicalize so trailing-slash URLs (e.g. /dashboard/) still match.
    const current = pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname
    return exact ? current === path : current === path || current.startsWith(path + '/')
  }

  const isPlatformAdmin = !isDesktop && user?.role === 'platform_admin'
  const isSchoolAdmin = user?.role === 'school_admin'

  const navItems: NavItem[] = !user
    ? []
    : isPlatformAdmin
      ? [{ href: '/platform-admin', label: 'Platform', icon: Shield, exact: false }]
      : isSchoolAdmin
        ? [{ href: '/school-admin', label: 'School', icon: Users, exact: false }]
        : [
            { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, exact: true },
            { href: '/upload', label: 'Upload', icon: Upload, exact: true },
            { href: '/lessons', label: 'Lesson Plans', icon: BookOpen, exact: false },
            { href: '/weekly-plans', label: 'Weekly Plan', icon: CalendarDays, exact: true },
            { href: '/templates', label: 'Templates', icon: FileText, exact: true },
            ...((user.is_admin || user.role === 'school_admin')
              ? [{ href: '/school-admin', label: 'Admin', icon: Users, exact: false }]
              : []),
          ]

  const homeHref = isPlatformAdmin ? '/platform-admin' : isSchoolAdmin ? '/school-admin' : '/dashboard'

  const linkClass = (active: boolean) =>
    cn(
      'inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm font-medium transition-colors',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE] focus-visible:ring-offset-2 focus-visible:ring-offset-[#071826]',
      active
        ? 'bg-[#04A9CE]/15 text-[#04A9CE]'
        : 'text-white/70 hover:bg-white/5 hover:text-white',
    )

  return (
    <header className="sticky top-0 z-40 border-b border-white/10 bg-[#071826]" data-app-header>
      <div className="container mx-auto px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-6 min-w-0">
            <Link href={homeHref} className="flex items-center gap-2.5 shrink-0">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-white/10 bg-[#F4F7FA] ring-1 ring-[#04A9CE]/25">
                <SchemeKnitMark size={24} />
              </span>
              <span className="text-xl font-bold tracking-tight text-white">
                Scheme<span className="text-[#04A9CE]">Knit</span>
              </span>
            </Link>
            {navItems.length > 0 && (
              <nav aria-label="Primary" className="hidden md:flex items-center gap-1">
                {navItems.map((item) => {
                  const active = isActive(item.href, item.exact)
                  const Icon = item.icon
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      aria-current={active ? 'page' : undefined}
                      className={linkClass(active)}
                    >
                      <Icon className="h-4 w-4" aria-hidden="true" />
                      {item.label}
                    </Link>
                  )
                })}
              </nav>
            )}
          </div>

          <div className="flex items-center gap-1 sm:gap-2">
            <a
              href={whatsappUrl()}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Chat with BloomCore Technologies on WhatsApp"
              title="Chat with BloomCore Technologies on WhatsApp"
              className="inline-flex h-9 w-9 items-center justify-center rounded-md text-[#25D366] hover:bg-[#25D366]/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE]"
            >
              <WhatsAppIcon className="h-5 w-5" />
            </a>
            <a
              href={contactMailtoUrl('SchemeKnit enquiry')}
              aria-label={`Email BloomCore Technologies at ${CONTACT_EMAIL}`}
              title={`Email ${CONTACT_EMAIL}`}
              className="hidden sm:inline-flex h-9 w-9 items-center justify-center rounded-md text-white/70 hover:bg-white/5 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE]"
            >
              <Mail className="h-4 w-4" />
            </a>
            {user && (
              <>
                <span className="text-sm text-white/70 hidden lg:inline truncate max-w-[10rem]">
                  {user.full_name}
                </span>
                <Link
                  href="/settings"
                  aria-current={isActive('/settings') ? 'page' : undefined}
                  className="hidden md:inline-flex"
                >
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label="Settings"
                    className={cn(
                      'text-white/70 hover:bg-white/5 hover:text-white',
                      isActive('/settings') && 'bg-[#04A9CE]/15 text-[#04A9CE] hover:bg-[#04A9CE]/15 hover:text-[#04A9CE]',
                    )}
                  >
                    <Settings className="h-4 w-4" />
                  </Button>
                </Link>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label="Log out"
                  onClick={logout}
                  className="hidden md:inline-flex text-white/70 hover:bg-white/5 hover:text-white"
                >
                  <LogOut className="h-4 w-4" />
                </Button>
              </>
            )}
            {navItems.length > 0 && (
              <button
                type="button"
                aria-label={menuOpen ? 'Close menu' : 'Open menu'}
                aria-expanded={menuOpen}
                aria-controls="app-mobile-nav"
                onClick={() => setMenuOpen((o) => !o)}
                className="md:hidden inline-flex h-9 w-9 items-center justify-center rounded-md text-white/80 hover:bg-white/5 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE]"
              >
                {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
              </button>
            )}
          </div>
        </div>

        {menuOpen && navItems.length > 0 && (
          <nav
            id="app-mobile-nav"
            aria-label="Mobile navigation"
            className="md:hidden mt-3 flex flex-col gap-1 border-t border-white/10 pt-3"
          >
            {navItems.map((item) => {
              const active = isActive(item.href, item.exact)
              const Icon = item.icon
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? 'page' : undefined}
                  className={cn(linkClass(active), 'px-3 py-2.5')}
                >
                  <Icon className="h-4 w-4" aria-hidden="true" />
                  {item.label}
                </Link>
              )
            })}
            {user && (
              <div className="mt-1 flex items-center justify-between gap-2 border-t border-white/10 pt-3">
                <span className="text-sm text-white/70 truncate">{user.full_name}</span>
                <div className="flex items-center gap-1 shrink-0">
                  <Link
                    href="/settings"
                    aria-current={isActive('/settings') ? 'page' : undefined}
                    className={cn(linkClass(isActive('/settings')), 'px-3 py-2')}
                  >
                    <Settings className="h-4 w-4" aria-hidden="true" />
                    Settings
                  </Link>
                  <button
                    type="button"
                    onClick={logout}
                    aria-label="Log out"
                    className="inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium text-white/70 hover:bg-white/5 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#04A9CE]"
                  >
                    <LogOut className="h-4 w-4" aria-hidden="true" />
                    Log out
                  </button>
                </div>
              </div>
            )}
          </nav>
        )}
      </div>
    </header>
  )
}
