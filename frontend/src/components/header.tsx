'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { BookOpen, LogOut, LayoutDashboard, Upload, FileText, Settings, Users, Shield, Mail } from 'lucide-react'
import { useAuth } from '@/lib/auth-context'
import { isDesktop } from '@/lib/build-target'
import { SchemeKnitMark } from '@/components/scheme-knit-mark'
import { WhatsAppIcon } from '@/components/whatsapp-button'
import { whatsappUrl, contactMailtoUrl, CONTACT_EMAIL } from '@/lib/contact'

export function Header() {
  const { user, logout } = useAuth()
  const pathname = usePathname()

  const isActive = (path: string) => pathname === path
  const isPlatformAdmin = !isDesktop && user?.role === 'platform_admin'
  const isSchoolAdmin = user?.role === 'school_admin'

  return (
    <header className="border-b bg-background">
      <div className="container mx-auto px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-6">
            <Link
              href={isPlatformAdmin ? '/platform-admin' : isSchoolAdmin ? '/school-admin' : '/dashboard'}
              className="flex items-center space-x-2"
            >
              {/* Master brand mark — the same canonical SVG used by the
                  landing page, footer and legal pages. Never a raster path
                  that may be absent from a given deployment. */}
              <SchemeKnitMark size={28} className="h-7 w-7 rounded-md" />
              <span className="text-xl font-bold">SchemeKnit</span>
            </Link>
            {user && (
              <nav className="hidden md:flex items-center space-x-1">
                {isPlatformAdmin ? (
                  <Link href="/platform-admin">
                    <Button variant={isActive('/platform-admin') ? 'default' : 'ghost'} size="sm">
                      <Shield className="h-4 w-4 mr-1.5" />
                      Platform
                    </Button>
                  </Link>
                ) : isSchoolAdmin ? (
                  <Link href="/school-admin">
                    <Button variant={isActive('/school-admin') ? 'default' : 'ghost'} size="sm">
                      <Users className="h-4 w-4 mr-1.5" />
                      School
                    </Button>
                  </Link>
                ) : (
                  <>
                    <Link href="/dashboard">
                      <Button variant={isActive('/dashboard') ? 'default' : 'ghost'} size="sm">
                        <LayoutDashboard className="h-4 w-4 mr-1.5" />
                        Dashboard
                      </Button>
                    </Link>
                    <Link href="/upload">
                      <Button variant={isActive('/upload') ? 'default' : 'ghost'} size="sm">
                        <Upload className="h-4 w-4 mr-1.5" />
                        Upload
                      </Button>
                    </Link>
                    <Link href="/lessons">
                      <Button variant={isActive('/lessons') ? 'default' : 'ghost'} size="sm">
                        <BookOpen className="h-4 w-4 mr-1.5" />
                        Lesson Plans
                      </Button>
                    </Link>
                    <Link href="/templates">
                      <Button variant={isActive('/templates') ? 'default' : 'ghost'} size="sm">
                        <FileText className="h-4 w-4 mr-1.5" />
                        Templates
                      </Button>
                    </Link>
                    {(user.is_admin || user.role === 'school_admin') && (
                      <Link href="/school-admin">
                        <Button variant={isActive('/school-admin') ? 'default' : 'ghost'} size="sm">
                          <Users className="h-4 w-4 mr-1.5" />
                          Admin
                        </Button>
                      </Link>
                    )}
                  </>
                )}
              </nav>
            )}
          </div>
          <div className="flex items-center space-x-3">
            {/* Contact/help actions — one canonical contact config, kept compact
                in the header so support is reachable from every page without
                crowding the UI. */}
            <a
              href={whatsappUrl()}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Chat with BloomCore Technologies on WhatsApp"
              title="Chat with BloomCore Technologies on WhatsApp"
              className="inline-flex h-9 w-9 items-center justify-center rounded-md text-[#25D366] hover:bg-[#25D366]/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <WhatsAppIcon className="h-5 w-5" />
            </a>
            <a
              href={contactMailtoUrl('SchemeKnit enquiry')}
              aria-label={`Email BloomCore Technologies at ${CONTACT_EMAIL}`}
              title={`Email ${CONTACT_EMAIL}`}
              className="hidden sm:inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Mail className="h-4 w-4" />
            </a>
            {user && (
              <>
                <span className="text-sm text-muted-foreground hidden sm:inline">
                  {user.full_name}
                </span>
                <Link href="/settings">
                  <Button variant={isActive('/settings') ? 'default' : 'ghost'} size="sm">
                    <Settings className="h-4 w-4" />
                  </Button>
                </Link>
                <Button variant="ghost" size="sm" onClick={logout}>
                  <LogOut className="h-4 w-4" />
                </Button>
              </>
            )}
          </div>
        </div>
      </div>
    </header>
  )
}
