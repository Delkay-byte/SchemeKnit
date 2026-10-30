import Link from 'next/link'
import { PublicPage } from '@/components/public-page'

const FAQ = [
  {
    q: 'Do I need to pay before I can use TeachFlow?',
    a: 'No. Create a free account and you receive two lesson-plan generations every calendar month. You can upload schemes, review extracted content, generate within the allowance, edit saved plans and export existing work.',
  },
  {
    q: 'What counts as one credit?',
    a: 'One successfully generated, independently teachable, indicator-level lesson plan. Three indicators selected in the same scheme week produce three plans and consume three credits. Editing, viewing, downloading or exporting saved work does not consume a credit.',
  },
  {
    q: 'What happens when my free credits run out?',
    a: 'Generation stops for the rest of the calendar month. Your account and all saved plans stay accessible. You can buy a package or wait for the next monthly allowance on the 1st (Africa/Accra). Free credits do not roll over.',
  },
  {
    q: 'Do purchased credits expire?',
    a: 'Flexible Credit Pack credits never expire. Teacher Monthly credits last 30 days, Teacher Term Pass credits 120 days, and Academic Year Pass credits 365 days from the confirmed activation time. A package ending never removes flexible purchased credits.',
  },
  {
    q: 'How do I pay?',
    a: 'Bank Transfer or Mobile Money (MTN, Telecel or AirtelTigo). Both are one-time prepaid payments. There is no automatic renewal and no card checkout. A package activates only after Paystack confirms the payment.',
  },
  {
    q: 'What if my transfer is still pending?',
    a: 'The payment page shows the status and lets you refresh. Nothing is activated until the payment is verified. A pending, failed or expired payment does not issue credits.',
  },
  {
    q: 'How does the referral programme work?',
    a: 'Invite a teacher with your referral link. When they make their first successful paid package purchase, you receive 5 bonus credits and they receive 3. Registration alone does not earn a reward, and a pending or failed payment does not qualify.',
  },
  {
    q: 'Is TeachFlow officially approved by GES?',
    a: 'TeachFlow does not claim GES approval or endorsement. It is a lesson-planning tool that follows the scheme you upload. Review every generated plan before you teach or submit it.',
  },
  {
    q: 'Can I still access plans after a package expires?',
    a: 'Yes. Expiry affects new generation from that package balance, not your saved work. Previously generated plans remain available to view, edit and export.',
  },
]

export default function HelpPage() {
  return (
    <PublicPage
      eyebrow="Help"
      title="Questions teachers ask"
      description="Credit accounting, payments, referrals and saved work."
    >
      <div className="space-y-3">
        {FAQ.map((item) => (
          <details key={item.q} className="group rounded-xl border border-slate-200 bg-white p-5">
            <summary className="cursor-pointer list-none font-semibold text-[#102A43]">
              {item.q}
            </summary>
            <p className="mt-3 text-sm leading-relaxed text-slate-600">{item.a}</p>
          </details>
        ))}
      </div>
      <p className="mt-8 text-center text-sm text-slate-600">
        Still stuck? <Link href="/contact" className="font-semibold text-[#04769B] underline">Contact support</Link>.
      </p>
    </PublicPage>
  )
}
