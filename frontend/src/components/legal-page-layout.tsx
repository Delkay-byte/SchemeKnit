import React from 'react'
import Link from 'next/link'
import { SchemeKnitMark } from '@/components/scheme-knit-mark'
import { PublicFooter } from '@/components/public-footer'

/**
 * Shared layout for public legal/information pages.
 *
 * Renders a minimal header (mark + back-to-home) and the public footer
 * so every legal page looks cohesive without app chrome (no sidebar,
 * no dashboard navigation).
 */
export function LegalPageLayout({
  title,
  subtitle,
  lastUpdated,
  children,
}: {
  title: string
  subtitle?: string
  lastUpdated?: string
  children: React.ReactNode
}) {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      {/* Minimal header */}
      <header className="border-b bg-background/95 backdrop-blur">
        <div className="container mx-auto px-4 py-4">
          <Link
            href="/"
            className="inline-flex items-center space-x-2.5 text-foreground hover:opacity-80"
          >
            <SchemeKnitMark size={28} className="h-7 w-7" />
            <span className="text-lg font-bold">SchemeKnit</span>
          </Link>
        </div>
      </header>

      {/* Content */}
      <main className="container mx-auto flex-1 px-4 py-10 md:py-14">
        <div className="mx-auto max-w-3xl">
          <h1 className="mb-2 text-3xl font-bold text-brand-navy md:text-4xl">
            {title}
          </h1>
          {subtitle && (
            <p className="mb-4 text-lg text-muted-foreground">{subtitle}</p>
          )}
          {lastUpdated && (
            <p className="mb-8 text-sm text-muted-foreground">
              Last updated: {lastUpdated}
            </p>
          )}
          <div className="prose prose-slate max-w-none space-y-6 text-foreground/90">
            {children}
          </div>
        </div>
      </main>

      <PublicFooter />
    </div>
  )
}

/**
 * Reusable section heading inside a legal page.
 */
export function LegalSection({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <section className="space-y-3">
      <h2 className="text-xl font-semibold text-brand-navy">{title}</h2>
      <div className="space-y-3 leading-relaxed">{children}</div>
    </section>
  )
}
