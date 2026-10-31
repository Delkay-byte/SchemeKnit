import Link from 'next/link'
import { PublicPage } from '@/components/public-page'
import { Button } from '@/components/ui/button'
import { pageMetadata } from '@/lib/site-url'

export const metadata = pageMetadata({
  title: 'How SchemeKnit Works',
  description:
    'Upload a Scheme of Learning, review extracted curriculum fields, generate lesson plans and export them.',
  path: '/how-it-works',
})

const STEPS = [
  {
    title: 'Upload a DOCX or PDF scheme',
    body: 'Bring the scheme of learning you already teach. SchemeKnit reads its table structure instead of replacing it with generic content.',
  },
  {
    title: 'Extract the curriculum fields',
    body: 'The week, strand, sub-strand, content standard and indicators are extracted and shown to you for review.',
  },
  {
    title: 'Review and correct',
    body: 'Fix any extraction mistake before you generate. Your corrected scheme is what the lesson plans follow.',
  },
  {
    title: 'Generate indicator-level plans',
    body: 'Select individual indicators. Each selected indicator becomes its own plan; several indicators in one week produce several plans.',
  },
  {
    title: 'Edit, save and export',
    body: 'Review the generated plan, make your own edits, and export it. Editing, viewing, downloading and exporting never consume a credit.',
  },
]

export default function HowItWorksPage() {
  return (
    <PublicPage
      eyebrow="How it works"
      title="From your scheme to a teachable plan"
      description="SchemeKnit follows your document. It does not claim to know your curriculum better than you do, and it does not silently replace your scheme with a generic topic library."
    >
      <ol className="space-y-4">
        {STEPS.map((step, i) => (
          <li key={step.title} className="flex gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#04A9CE]/10 font-bold text-[#04769B]">
              {i + 1}
            </span>
            <div>
              <h2 className="font-semibold text-[#102A43]">{step.title}</h2>
              <p className="mt-1 text-sm leading-relaxed text-slate-600">{step.body}</p>
            </div>
          </li>
        ))}
      </ol>

      <section className="mt-8 rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="text-xl font-bold text-[#102A43]">What a credit pays for</h2>
        <p className="mt-2 text-sm leading-relaxed text-slate-600">
          One credit = one successfully generated, independently teachable,
          indicator-level lesson plan. A failed technical generation does not
          consume a credit. Editing an existing plan, viewing it, downloading it
          or exporting saved work does not consume a credit.
        </p>
        <p className="mt-3 text-sm leading-relaxed text-slate-600">
          Free accounts receive two credits each calendar month. Paid packages
          add a separate balance: Flexible Credit Pack credits never expire,
          while Monthly, Term and Academic Year credits run for 30, 120 or 365
          days from activation.
        </p>
      </section>

      <div className="mt-8 flex flex-wrap justify-center gap-3">
        <Button asChild><Link href="/signup">Start Free</Link></Button>
        <Button asChild variant="outline"><Link href="/pricing">View Pricing</Link></Button>
      </div>
    </PublicPage>
  )
}
