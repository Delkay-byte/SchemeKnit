import Link from 'next/link'
import { PublicPage } from '@/components/public-page'
import { Button } from '@/components/ui/button'

const AUDIENCES = [
  {
    title: 'KG teachers',
    body: 'Work from your own early-years scheme. Review the week, strand and indicators, then generate a plan that fits the classroom routines you already use.',
  },
  {
    title: 'Basic 1–6 class teachers',
    body: 'Upload the scheme for your class and subject. TeachFlow extracts the week, strand, sub-strand, content standard and indicators for you to check and correct.',
  },
  {
    title: 'JHS subject teachers',
    body: 'Keep separate indicator-level plans for each subject and class you teach, even when several indicators sit inside the same scheme week.',
  },
]

export default function FeaturesPage() {
  return (
    <PublicPage
      eyebrow="Features"
      title="Your Scheme of Learning. Your Lesson Plans. Made Easier."
      description="TeachFlow starts with the scheme you upload, not a generic library of pre-written lessons. You stay in control of the curriculum; the application does the repetitive assembly."
    >
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm md:p-8">
        <h2 className="text-2xl font-bold text-[#102A43]">Five steps, one scheme</h2>
        <ol className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {[
            ['Upload', 'Upload a DOCX or PDF scheme of learning.'],
            ['Extract', 'Week, strand, sub-strand, content standard and indicators are extracted.'],
            ['Review', 'Check and correct the extracted information before generating.'],
            ['Generate', 'Choose indicators; each one becomes its own lesson plan.'],
            ['Edit & export', 'Edit, save and export the plans your school expects.'],
          ].map(([title, body], i) => (
            <li key={title} className="rounded-xl border border-slate-200 p-4">
              <span className="text-sm font-bold text-[#04A9CE]">{String(i + 1).padStart(2, '0')}</span>
              <h3 className="mt-2 font-semibold text-[#102A43]">{title}</h3>
              <p className="mt-1 text-sm text-slate-600">{body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="mt-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm md:p-8">
        <h2 className="text-2xl font-bold text-[#102A43]">One week, several indicators, separate plans</h2>
        <p className="mt-3 text-sm leading-relaxed text-slate-600">
          A single scheme week can contain more than one indicator. TeachFlow
          generates a separate, independently teachable plan for each indicator
          you select. A week with three indicators can produce three plans and
          consume three credits.
        </p>
        <div className="mt-5 overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                <th className="py-2 pr-4">Week</th>
                <th className="py-2 pr-4">Strand / sub-strand</th>
                <th className="py-2 pr-4">Indicator</th>
                <th className="py-2">Plan</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              <tr>
                <td className="py-3 pr-4">Week 2</td>
                <td className="py-3 pr-4">Numbers / Counting</td>
                <td className="py-3 pr-4">Count objects up to 20</td>
                <td className="py-3">Lesson plan 1</td>
              </tr>
              <tr>
                <td className="py-3 pr-4">Week 2</td>
                <td className="py-3 pr-4">Numbers / Counting</td>
                <td className="py-3 pr-4">Match numerals to quantities</td>
                <td className="py-3">Lesson plan 2</td>
              </tr>
              <tr>
                <td className="py-3 pr-4">Week 2</td>
                <td className="py-3 pr-4">Numbers / Counting</td>
                <td className="py-3 pr-4">Order numbers 1–20</td>
                <td className="py-3">Lesson plan 3</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-slate-500">
          Illustrative example only. The content comes from the scheme you upload.
        </p>
      </section>

      <section className="mt-8 grid gap-4 md:grid-cols-3">
        {AUDIENCES.map((a) => (
          <article key={a.title} className="rounded-xl border border-slate-200 bg-white p-5">
            <h3 className="font-semibold text-[#102A43]">{a.title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">{a.body}</p>
          </article>
        ))}
      </section>

      <div className="mt-8 rounded-2xl bg-[#102A43] p-6 text-center text-white md:p-8">
        <h2 className="text-2xl font-bold">Start with two free lesson plans every month</h2>
        <p className="mt-2 text-white/75">
          No payment information is needed to create a free account.
        </p>
        <div className="mt-5 flex flex-wrap justify-center gap-3">
          <Button asChild><Link href="/signup">Start Free</Link></Button>
          <Button asChild variant="outline"><Link href="/pricing">View Pricing</Link></Button>
        </div>
      </div>
    </PublicPage>
  )
}
