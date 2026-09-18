import { LegalPageLayout, LegalSection } from '@/components/legal-page-layout'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Contact SchemeKnit',
  description: 'Get in touch with SchemeKnit support.',
}

export default function ContactPage() {
  return (
    <LegalPageLayout
      title="Contact Us"
      subtitle="Get in touch with SchemeKnit support."
      lastUpdated="September 2026"
    >
      <LegalSection title="1. General Enquiries">
        <p>
          For general questions about SchemeKnit, including feature enquiries,
          integration support, or collaboration opportunities, please email:
        </p>
        <p className="font-mono text-brand-cyan">support@schemeknit.com</p>
      </LegalSection>

      <LegalSection title="2. Privacy Concerns">
        <p>
          For questions about your personal data, privacy rights, or data
          deletion requests, please email:
        </p>
        <p className="font-mono text-brand-cyan">privacy@schemeknit.com</p>
      </LegalSection>

      <LegalSection title="3. Billing and Payments">
        <p>
          For payment issues, refund requests, or subscription questions,
          please email:
        </p>
        <p className="font-mono text-brand-cyan">billing@schemeknit.com</p>
      </LegalSection>

      <LegalSection title="4. Response Time">
        <p>
          We aim to respond to all enquiries within 2 business days.
          Response times may vary on weekends and public holidays.
        </p>
      </LegalSection>

      <LegalSection title="5. Security Vulnerabilities">
        <p>
          If you discover a security vulnerability in SchemeKnit, please report
          it responsibly by emailing:
        </p>
        <p className="font-mono text-brand-cyan">security@schemeknit.com</p>
        <p>
          Please include a description of the vulnerability and steps to
          reproduce. We will acknowledge receipt within 48 hours and aim to
          resolve confirmed vulnerabilities within 14 days.
        </p>
      </LegalSection>
    </LegalPageLayout>
  )
}
