import Link from 'next/link'
import { PublicPage } from '@/components/public-page'
import { Button } from '@/components/ui/button'
import { pageMetadata } from '@/lib/site-url'

export const metadata = pageMetadata({
  title: 'About SchemeKnit',
  description:
    'SchemeKnit is a lesson-planning workspace for Ghanaian teachers, built around the Scheme of Learning they already use.',
  path: '/about',
})

export default function AboutPage() {
  return (
    <PublicPage
      eyebrow="About"
      title="Built around the scheme teachers already use"
      description="SchemeKnit is a lesson-planning workspace for Ghanaian teachers. It starts from the teacher's own scheme of learning and turns selected indicators into editable, exportable plans."
    >
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm md:p-8">
        <h2 className="text-xl font-bold text-[#102A43]">Why we built it</h2>
        <p className="mt-3 text-sm leading-relaxed text-slate-600">
          Lesson planning takes time that teachers would rather spend on
          teaching. Much of that time is repetitive: reading the same scheme
          week after week, finding the indicator, and assembling the same
          lesson structure around it. SchemeKnit does the repetitive assembly
          while keeping the teacher's scheme and professional judgement in
          charge.
        </p>
      </section>

      <section className="mt-6 grid gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <h3 className="font-semibold text-[#102A43]">What we do not claim</h3>
          <ul className="mt-3 space-y-2 text-sm text-slate-600">
            <li>• We do not claim official GES approval or endorsement.</li>
            <li>• We do not guarantee perfect extraction or perfect lessons.</li>
            <li>• We do not replace the teacher's review before use.</li>
            <li>• We do not promise unlimited generation.</li>
          </ul>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <h3 className="font-semibold text-[#102A43]">Who it serves</h3>
          <ul className="mt-3 space-y-2 text-sm text-slate-600">
            <li>• KG teachers working from early-years schemes.</li>
            <li>• Basic 1–6 class teachers.</li>
            <li>• JHS subject teachers with several classes or subjects.</li>
            <li>• Schools that manage teacher access separately.</li>
          </ul>
        </div>
      </section>

      <div className="mt-8 flex flex-wrap justify-center gap-3">
        <Button asChild><Link href="/signup">Start Free</Link></Button>
        <Button asChild variant="outline"><Link href="/how-it-works">See How It Works</Link></Button>
      </div>
    </PublicPage>
  )
}
