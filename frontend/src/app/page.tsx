'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Building2, GraduationCap, ArrowRight, KeyRound, LogIn, UserPlus } from 'lucide-react'
import { useAuth } from '@/lib/auth-context'
import { SchemeKnitMark } from '@/components/scheme-knit-mark'
import { PublicFooter } from '@/components/public-footer'
import { WhatsAppButton } from '@/components/whatsapp-button'
import { LandingHero, scrollToSection } from '@/components/landing/landing-hero'
import { HowItWorks } from '@/components/landing/how-it-works'

/**
 * Public landing page (§2, §3).
 *
 * This is the single public entry point. It leads with the SchemeKnit hero —
 * the scheme → curriculum → indicator → lesson story — then explains the
 * workflow, then presents the two public audiences (Teachers and School
 * Administration) as distinct cards so a visitor immediately knows which door
 * is theirs. It is deliberately NOT an internal dashboard.
 *
 * Staff/Platform Admin access is intentionally NOT advertised here. It stays in
 * the same deployment behind its secure direct routes (/login/platform-admin,
 * /setup/platform-admin) and is not part of the normal public journey.
 *
 * Role routing after login is decided by the backend role, never here.
 */
export default function Home() {
  const { user, loading } = useAuth()
  const router = useRouter()

  // A live session skips the marketing page and lands on the role's console.
  useEffect(() => {
    if (!loading && user) {
      router.push('/dashboard')
    }
  }, [user, loading, router])

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#f4f7fa]">
      <header className="bg-[#071826] text-white">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between gap-4">
            <Link href="/" className="flex items-center space-x-2.5">
              {/* Master brand mark — same symbol as the favicon, PWA icon and
                  future EXE (see docs/PUBLIC_ENTRY_AND_INSTALLATION.md). */}
              <SchemeKnitMark size={32} className="h-8 w-8 rounded-md" />
              <span className="text-2xl font-bold">SchemeKnit</span>
            </Link>
            <nav className="flex items-center gap-3 sm:gap-5">
              <button
                type="button"
                onClick={() => scrollToSection('how-it-works')}
                className="hidden text-sm font-medium text-white/75 transition-colors hover:text-white sm:inline"
              >
                How it works
              </button>
              <Link
                href="/login"
                className="inline-flex items-center rounded-full border border-white/25 px-4 py-1.5 text-sm font-semibold text-white transition-colors hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7edcf0] focus-visible:ring-offset-2 focus-visible:ring-offset-[#071826]"
              >
                Sign in
              </Link>
            </nav>
          </div>
        </div>
      </header>

      {/* Hero — scheme → curriculum → indicator → lesson */}
      <LandingHero />

      {/* Below-the-fold: reinforce that the curriculum stays in control */}
      <HowItWorks />

      {/* Role cards — the two public audiences only. Staff/Platform Admin is
          deliberately not shown: it is operations, not a public option. */}
      <section className="container mx-auto px-4 pb-12 md:pb-16">
        <div className="mx-auto mb-8 max-w-2xl text-center">
          <h2 className="text-2xl font-bold tracking-tight text-[#102A43] md:text-3xl">
            Choose how you use SchemeKnit
          </h2>
          <p className="mt-3 text-muted-foreground">
            Teachers plan and export lessons. Schools activate and manage their staff.
          </p>
        </div>

        <div className="mx-auto grid max-w-4xl gap-6 md:grid-cols-2">
          {/* Teacher — blue, the classroom audience */}
          <Card className="flex flex-col border-blue-300 hover:border-blue-400 transition-colors md:order-1">
            <CardHeader>
              <div className="p-3 rounded-full bg-blue-100 text-blue-700 w-fit mb-4">
                <GraduationCap className="h-7 w-7" />
              </div>
              <span className="inline-block text-[11px] font-semibold uppercase tracking-wider text-blue-600 mb-1">
                For Teachers
              </span>
              <CardTitle className="text-xl">Teacher</CardTitle>
              <CardDescription>
                Create, manage and export lesson plans. Use SchemeKnit through
                your school or independently.
              </CardDescription>
            </CardHeader>
            <CardContent className="mt-auto space-y-3">
              <div className="flex flex-wrap gap-2">
                <span className="inline-flex items-center rounded-full border border-blue-200 bg-blue-50 px-2.5 py-0.5 text-xs font-medium text-blue-700">
                  School Teacher
                </span>
                <span className="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-700">
                  Independent — Free / Pro
                </span>
              </div>
              <Link
                href="/login"
                className="inline-flex items-center justify-center w-full px-4 py-2.5 rounded-md bg-blue-600 text-white font-medium hover:bg-blue-700 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                <LogIn className="h-4 w-4 mr-2" aria-hidden="true" />
                Teacher Login
                <ArrowRight className="h-4 w-4 ml-2" aria-hidden="true" />
              </Link>
              <Link
                href="/signup"
                className="inline-flex items-center justify-center w-full px-4 py-2.5 rounded-md border border-blue-300 text-blue-700 font-medium hover:bg-blue-50 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                <UserPlus className="h-4 w-4 mr-2" aria-hidden="true" />
                Create Free Account
              </Link>
            </CardContent>
          </Card>

          {/* School Admin — emerald, commercial onboarding */}
          <Card className="flex flex-col border-emerald-300 hover:border-emerald-400 transition-colors md:order-2">
            <CardHeader>
              <div className="p-3 rounded-full bg-emerald-100 text-emerald-700 w-fit mb-4">
                <Building2 className="h-7 w-7" />
              </div>
              <span className="inline-block text-[11px] font-semibold uppercase tracking-wider text-emerald-600 mb-1">
                For Schools
              </span>
              <CardTitle className="text-xl">School Administration</CardTitle>
              <CardDescription>
                Activate your school, manage teachers, seats and school
                settings.
              </CardDescription>
            </CardHeader>
            <CardContent className="mt-auto space-y-3">
              <Link
                href="/activate-school"
                className="inline-flex items-center justify-center w-full px-4 py-2.5 rounded-md bg-emerald-600 text-white font-medium hover:bg-emerald-700 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                <KeyRound className="h-4 w-4 mr-2" aria-hidden="true" />
                Activate Your School
                <ArrowRight className="h-4 w-4 ml-2" aria-hidden="true" />
              </Link>
              <Link
                href="/login/school-admin"
                className="inline-flex items-center justify-center w-full px-4 py-2.5 rounded-md border border-emerald-300 text-emerald-700 font-medium hover:bg-emerald-50 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                <LogIn className="h-4 w-4 mr-2" aria-hidden="true" />
                School Admin Login
              </Link>
            </CardContent>
          </Card>
        </div>
      </section>

      <PublicFooter />
      {/* Contact affordance on the public entry point (desktop + mobile). */}
      <WhatsAppButton />
    </div>
  )
}
