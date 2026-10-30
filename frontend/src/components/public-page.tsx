import Link from 'next/link'
import { SchemeKnitMark } from '@/components/scheme-knit-mark'
import { PublicFooter } from '@/components/public-footer'

/** Shared shell for public marketing/help pages. */
export function PublicPage({
  children,
  eyebrow,
  title,
  description,
}: {
  children: React.ReactNode
  eyebrow?: string
  title: string
  description?: string
}) {
  return (
    <div className="min-h-screen bg-[#f4f7fa]">
      <header className="border-b border-white/10 bg-[#071826] text-white">
        <div className="container mx-auto flex items-center justify-between gap-4 px-4 py-4">
          <Link href="/" className="flex items-center gap-3">
            <span
              className="flex h-10 w-10 items-center justify-center rounded-xl border"
              style={{
                background: '#F4F7FA',
                borderColor: 'rgba(16,42,67,0.12)',
                boxShadow: '0 0 0 1px rgba(4,169,206,0.3)',
              }}
            >
              <SchemeKnitMark size={26} />
            </span>
            <span className="text-xl font-bold tracking-tight">
              Scheme<span className="text-[#04A9CE]">Knit</span>
            </span>
          </Link>
          <nav className="flex items-center gap-4 text-sm" aria-label="Public">
            <Link href="/features" className="hidden text-white/75 hover:text-white sm:inline">Features</Link>
            <Link href="/how-it-works" className="hidden text-white/75 hover:text-white sm:inline">How it works</Link>
            <Link href="/pricing" className="text-white/75 hover:text-white">Pricing</Link>
            <Link href="/signup" className="rounded-full bg-[#04A9CE] px-4 py-1.5 font-semibold text-[#071826] hover:bg-[#7edcf0]">
              Start Free
            </Link>
          </nav>
        </div>
      </header>

      <main className="container mx-auto max-w-5xl px-4 py-12 md:py-16">
        <div className="mx-auto max-w-3xl text-center">
          {eyebrow && (
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#04769B]">
              {eyebrow}
            </p>
          )}
          <h1 className="mt-3 text-3xl font-bold tracking-tight text-[#102A43] md:text-4xl">
            {title}
          </h1>
          {description && (
            <p className="mt-4 text-base leading-relaxed text-slate-600 md:text-lg">
              {description}
            </p>
          )}
        </div>
        <div className="mt-10">{children}</div>
      </main>

      <PublicFooter />
    </div>
  )
}
