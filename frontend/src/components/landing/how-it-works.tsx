import Link from 'next/link'

/**
 * Below-the-fold explanation that immediately follows the hero.
 *
 * Reinforces the product's central promise — SchemeKnit works from the
 * teacher's own scheme of learning — and lists the five real steps a teacher
 * takes. Static markup only: no animation, no data, no network calls.
 */

const CHAIN = ['Your scheme', 'Your curriculum', 'Your indicator', 'Your lesson'] as const

const STEPS = [
  {
    title: 'Upload your scheme',
    body: 'Bring the scheme of learning you already teach. SchemeKnit reads its structure.',
  },
  {
    title: 'Review the curriculum',
    body: 'Strands, sub-strands, content standards and indicators are mapped for you to check.',
  },
  {
    title: 'Select indicators',
    body: 'Choose the exact indicator for the teaching period you are planning.',
  },
  {
    title: 'Generate lessons',
    body: 'SchemeKnit builds a lesson around that indicator, bounded by your curriculum.',
  },
  {
    title: 'Export',
    body: 'Review the teacher-ready lesson and export it in the format your school expects.',
  },
] as const

export function HowItWorks() {
  return (
    <section id="how-it-works" className="scroll-mt-20 bg-[#f4f7fa]">
      <div className="container mx-auto px-4 py-14 md:py-20">
        <div className="mx-auto max-w-3xl text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#04a9ce]">
            How it works
          </p>
          <h2 className="mt-3 text-3xl font-bold tracking-tight text-[#102A43] md:text-4xl">
            Your curriculum stays in control.
          </h2>
          <p className="mt-4 text-base leading-relaxed text-slate-600 md:text-lg">
            SchemeKnit is not a generic lesson writer. It starts from the scheme you
            upload, follows the indicator you select, and keeps every lesson inside the
            bounds of that curriculum.
          </p>
        </div>

        {/* The chain that mirrors the hero: scheme → curriculum → indicator → lesson */}
        <ol className="mt-9 flex flex-wrap items-center justify-center gap-x-2 gap-y-3 sm:gap-x-3">
          {CHAIN.map((item, index) => (
            <li key={item} className="flex items-center gap-x-2 sm:gap-x-3">
              <span
                className={[
                  'inline-flex items-center rounded-full border px-3.5 py-1.5 text-xs font-semibold tracking-wide sm:text-sm',
                  index === CHAIN.length - 1
                    ? 'border-[#04a9ce] bg-[#04a9ce] text-white'
                    : 'border-[#102A43]/15 bg-white text-[#102A43]',
                ].join(' ')}
              >
                {item}
              </span>
              {index < CHAIN.length - 1 && (
                <span aria-hidden="true" className="text-[#04a9ce]">
                  &rarr;
                </span>
              )}
            </li>
          ))}
        </ol>

        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {STEPS.map((step, index) => (
            <article
              key={step.title}
              className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <span className="text-sm font-bold text-[#04a9ce]">
                {String(index + 1).padStart(2, '0')}
              </span>
              <h3 className="mt-2 text-base font-semibold text-[#102A43]">{step.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-slate-600">{step.body}</p>
            </article>
          ))}
        </div>

        <p className="mx-auto mt-8 max-w-2xl text-center text-sm text-slate-500">
          Example content shown above is illustrative. SchemeKnit follows whatever scheme
          you upload — your document sets the curriculum.{' '}
          <Link href="/login" className="font-semibold text-[#102A43] underline underline-offset-2">
            Start Planning
          </Link>
        </p>
      </div>
    </section>
  )
}
