import { LegalPageLayout, LegalSection } from '@/components/legal-page-layout'
import { pageMetadata } from '@/lib/site-url'
import {
  BUSINESS_NAME, CONTACT_EMAIL, CONTACT_PHONE_LOCAL, CONTACT_PHONE_LOCAL_2,
  contactMailtoUrl, contactTelUrl, contactTelUrl2, whatsappUrl,
} from '@/lib/contact'

export const metadata = pageMetadata({
  title: 'Contact SchemeKnit',
  description: 'Contact BloomCore Technologies for SchemeKnit support, billing, privacy and security enquiries.',
  path: '/contact',
})

export default function ContactPage() {
  return (
    <LegalPageLayout
      title="Contact Us"
      subtitle="Contact BloomCore Technologies, the business that operates SchemeKnit."
      lastUpdated="October 2026"
    >
      <LegalSection title="1. General Enquiries">
        <p>
          SchemeKnit is operated by <strong>{BUSINESS_NAME}</strong>. For general
          questions about the product, feature enquiries, school licensing or
          collaboration, email us:
        </p>
        <p>
          <a
            href={contactMailtoUrl('SchemeKnit — General Enquiry')}
            className="font-semibold text-brand-cyan underline break-all"
            data-contact-email
          >
            {CONTACT_EMAIL}
          </a>
        </p>
      </LegalSection>

      <LegalSection title="2. Call or WhatsApp">
        <div className="space-y-4">
          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <p className="text-lg font-bold text-brand-navy">{CONTACT_PHONE_LOCAL}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Call this number, or use WhatsApp.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <a
                href={contactTelUrl()}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-brand-navy hover:border-brand-cyan"
              >
                Call {CONTACT_PHONE_LOCAL}
              </a>
              <a
                href={whatsappUrl()}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-lg border border-[#25D366]/50 bg-[#25D366]/10 px-3 py-2 text-sm font-semibold text-[#128C7E] hover:bg-[#25D366]/20"
                data-whatsapp-link
              >
                WhatsApp {CONTACT_PHONE_LOCAL}
              </a>
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <p className="text-lg font-bold text-brand-navy">{CONTACT_PHONE_LOCAL_2}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Calls only. This number is not registered for WhatsApp.
            </p>
            <div className="mt-3">
              <a
                href={contactTelUrl2()}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-brand-navy hover:border-brand-cyan"
              >
                Call {CONTACT_PHONE_LOCAL_2}
              </a>
            </div>
          </div>
        </div>
      </LegalSection>

      <LegalSection title="3. Billing and Payment Support">
        <p>
          For a pending payment, verification issue, duplicate payment,
          package activation or billing question, email us with your account
          email and payment reference:
        </p>
        <p>
          <a
            href={contactMailtoUrl('SchemeKnit — Billing and Payment Support')}
            className="font-semibold text-brand-cyan underline break-all"
          >
            {CONTACT_EMAIL}
          </a>
        </p>
        <p>
          You may also call{' '}
          <a href={contactTelUrl()} className="text-brand-cyan underline">
            {CONTACT_PHONE_LOCAL}
          </a>{' '}
          or{' '}
          <a href={contactTelUrl2()} className="text-brand-cyan underline">
            {CONTACT_PHONE_LOCAL_2}
          </a>
          . Do not send card numbers, Mobile Money PINs, Paystack secret keys or
          other payment credentials by email.
        </p>
      </LegalSection>

      <LegalSection title="4. Privacy and Personal-Data Enquiries">
        <p>
          For access, correction, objection, deletion or other personal-data
          requests under Ghana&apos;s Data Protection Act, 2012 (Act 843),
          email:
        </p>
        <p>
          <a
            href={contactMailtoUrl('SchemeKnit — Privacy and Data Request')}
            className="font-semibold text-brand-cyan underline break-all"
          >
            {CONTACT_EMAIL}
          </a>
        </p>
        <p>
          See our{' '}
          <a href="/privacy-policy" className="text-brand-cyan underline">
            Privacy Policy
          </a>{' '}
          and{' '}
          <a href="/data-retention" className="text-brand-cyan underline">
            Data Retention Policy
          </a>{' '}
          for how requests are handled.
        </p>
      </LegalSection>

      <LegalSection title="5. Security Reports">
        <p>
          If you believe you have found a security vulnerability, report it
          responsibly:
        </p>
        <p>
          <a
            href={contactMailtoUrl('SchemeKnit — Security Report')}
            className="font-semibold text-brand-cyan underline break-all"
          >
            {CONTACT_EMAIL}
          </a>
        </p>
        <p>
          Include a description, the affected page or endpoint, and steps to
          reproduce. Do not include passwords, authentication tokens, payment
          credentials or other people&apos;s personal data.
        </p>
      </LegalSection>
    </LegalPageLayout>
  )
}
