import { LegalPageLayout, LegalSection } from '@/components/legal-page-layout'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Privacy Policy',
  description: 'How SchemeKnit collects, uses, and protects your information.',
}

export default function PrivacyPolicyPage() {
  return (
    <LegalPageLayout
      title="Privacy Policy"
      subtitle="How SchemeKnit collects, uses, and protects your information."
      lastUpdated="September 2026"
    >
      <LegalSection title="1. Who We Are">
        <p>
          SchemeKnit is a lesson-plan generation platform serving Ghanaian
          teachers and schools. This policy describes what information we
          collect and how we use it.
        </p>
      </LegalSection>

      <LegalSection title="2. Information We Collect">
        <p>We collect information that is necessary to provide the service:</p>
        <ul className="list-disc space-y-1 pl-6">
          <li>
            <strong>Account information:</strong> name, email address, and
            role (teacher, school administrator, or platform administrator).
          </li>
          <li>
            <strong>School information:</strong> school name and details
            provided when a school activates SchemeKnit.
          </li>
          <li>
            <strong>Uploaded documents:</strong> schemes of work and curriculum
            documents you upload for lesson-plan generation.
          </li>
          <li>
            <strong>Generated content:</strong> lesson plans and export files
            produced from your uploaded schemes.
          </li>
          <li>
            <strong>Payment records:</strong> payment evidence and verification
            details for subscriptions. Payments are verified manually — we do
            not process card or mobile-money transactions automatically.
          </li>
          <li>
            <strong>Usage data:</strong> generation counts, feature usage, and
            audit logs used for entitlement management and security.
          </li>
        </ul>
      </LegalSection>

      <LegalSection title="3. How We Use Your Information">
        <ul className="list-disc space-y-1 pl-6">
          <li>To generate lesson plans from your uploaded schemes of work.</li>
          <li>To manage your subscription and entitlements (Free or Pro).</li>
          <li>To verify payments and activate school licenses.</li>
          <li>To provide password reset and account recovery.</li>
          <li>To maintain audit trails for security and compliance.</li>
        </ul>
        <p>
          We do not sell your information to third parties. We do not use
          your uploaded curriculum documents to train public models.
        </p>
      </LegalSection>

      <LegalSection title="4. AI Assistance">
        <p>
          When AI assistance is enabled, lesson content is generated using the
          indicator, strand, and context of the specific lesson being enriched.
          AI providers receive only the lesson-level context needed to produce
          the enrichment — not your entire scheme of work. AI usage is
          quota-limited according to your plan.
        </p>
      </LegalSection>

      <LegalSection title="5. Data Storage and Security">
        <p>
          Your data is stored in a managed PostgreSQL database and, for
          uploaded and generated files, in access-controlled object storage.
          Passwords are hashed using industry-standard algorithms and are
          never stored in plain text. Access to your data is restricted to
          authorised platform administrators.
        </p>
      </LegalSection>

      <LegalSection title="6. Your Rights">
        <ul className="list-disc space-y-1 pl-6">
          <li>You may access and export your generated lesson plans at any time.</li>
          <li>You may delete your uploaded schemes and generated lessons.</li>
          <li>You may request account deletion.</li>
          <li>You may contact us regarding any privacy concern.</li>
        </ul>
      </LegalSection>

      <LegalSection title="7. Data Retention">
        <p>
          Please see our <a href="/data-retention" className="text-brand-cyan underline">Data Retention Policy</a> for
          how long different types of data are kept.
        </p>
      </LegalSection>

      <LegalSection title="8. Contact">
        <p>
          For privacy questions, please contact us through our{' '}
          <a href="/contact" className="text-brand-cyan underline">Contact page</a>.
        </p>
      </LegalSection>
    </LegalPageLayout>
  )
}
