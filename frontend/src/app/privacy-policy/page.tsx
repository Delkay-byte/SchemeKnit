import { LegalPageLayout, LegalSection } from '@/components/legal-page-layout'
import { pageMetadata } from '@/lib/site-url'
import {
  BUSINESS_NAME, BUSINESS_REGISTRATION_DATE, BUSINESS_REGISTRATION_NUMBER,
  CONTACT_EMAIL, contactMailtoUrl,
} from '@/lib/contact'

export const metadata = pageMetadata({
  title: 'Privacy Policy',
  description: 'How BloomCore Technologies collects, uses and protects SchemeKnit data.',
  path: '/privacy-policy',
})

export default function PrivacyPolicyPage() {
  return (
    <LegalPageLayout
      title="Privacy Policy"
      subtitle="How BloomCore Technologies collects, uses and protects SchemeKnit data."
      lastUpdated="October 2026"
    >
      <LegalSection title="1. Who is responsible for your data">
        <p>
          SchemeKnit is a teacher lesson-planning platform operated by{' '}
          <strong>{BUSINESS_NAME}</strong>, a Ghana-registered business
          (Business Name Registration No. {BUSINESS_REGISTRATION_NUMBER},
          registered {BUSINESS_REGISTRATION_DATE}). BloomCore Technologies is
          the data controller for the personal data described in this policy.
        </p>
        <p>
          The business-name certificate supplied to SchemeKnit does not show a
          physical or registered business address. Where an address is
          required for a legal or privacy disclosure, that detail is
          outstanding with the owner and will be published when confirmed. We
          do not publish an invented address.
        </p>
        <p>
          BloomCore Technologies has not claimed registration with Ghana&apos;s
          Data Protection Commission in this policy. Business-name
          registration and Data Protection Commission registration are
          separate matters. If registration is completed, this policy will be
          updated with the verified details.
        </p>
      </LegalSection>

      <LegalSection title="2. Information we collect">
        <p>
          We collect only the information needed to provide SchemeKnit:
        </p>
        <ul className="list-disc space-y-1 pl-6">
          <li>
            <strong>Account information:</strong> teacher name, email address,
            role, account status, password hash, authentication and session
            records. School name and school relationship where a teacher is
            managed by a school.
          </li>
          <li>
            <strong>Curriculum and uploaded content:</strong> uploaded schemes
            of learning and curriculum documents, extracted curriculum text,
            strands, sub-strands, indicators, teacher configuration, lesson
            details, generated lesson plans, and exported or downloadable
            files.
          </li>
          <li>
            <strong>Financial and entitlement information:</strong> selected
            package, credits and quota balances, payment reference, amount,
            currency, payment status, payment method, and a Mobile Money phone
            number supplied to initiate a payment where applicable. Referral
            records and reward credits where a referral programme applies.
          </li>
          <li>
            <strong>Security information:</strong> session details,
            login/security events, audit records, password-reset records, MFA
            information where enabled, and security/rate-limit events.
          </li>
          <li>
            <strong>Support communications:</strong> emails and messages sent
            to BloomCore Technologies, including billing and technical support
            requests.
          </li>
        </ul>
        <p>
          SchemeKnit does not receive or store complete bank-card details or
          Mobile Money PINs. Payment credentials are handled by Paystack.
        </p>
      </LegalSection>

      <LegalSection title="3. Student and pupil information">
        <p className="font-semibold text-brand-navy">
          SchemeKnit is a teacher lesson-planning tool, not a student records
          management system. Teachers must not upload pupils&apos; names,
          personal information, grades or other identifiable student records.
        </p>
        <p>
          The upload screen displays this notice before a file is selected. If
          such information is uploaded accidentally, contact us so it can be
          removed.
        </p>
      </LegalSection>

      <LegalSection title="4. Why we use your information">
        <ul className="list-disc space-y-1 pl-6">
          <li>Creating, authenticating and managing teacher and school accounts.</li>
          <li>Uploading documents and extracting curriculum structure.</li>
          <li>Generating, saving, editing, reloading and exporting lesson plans.</li>
          <li>Managing credits, package entitlements and referral rewards.</li>
          <li>Verifying payments and activating packages or school licences.</li>
          <li>Preventing fraud, abuse and unauthorised access.</li>
          <li>Maintaining security, audit and rate-limit records.</li>
          <li>Providing customer, billing and technical support.</li>
          <li>Meeting genuine legal, tax and financial record-keeping obligations.</li>
        </ul>
      </LegalSection>

      <LegalSection title="5. AI-assisted content">
        <p>
          AI-assisted enrichment is an optional product control. When a teacher
          requests AI content, lesson-level context — such as subject, class
          level, strand, indicator, duration and the specific section being
          rewritten — may be sent to the selected AI provider. The provider
          does not routinely receive the teacher&apos;s entire uploaded scheme
          through this path. SchemeKnit does not use uploaded curriculum
          documents to train public AI models.
        </p>
      </LegalSection>

      <LegalSection title="6. Service providers">
        <p>
          SchemeKnit uses service providers that process data on its behalf or
          as independent providers:
        </p>
        <ul className="list-disc space-y-1 pl-6">
          <li><strong>Render</strong> — application hosting.</li>
          <li><strong>Neon</strong> — managed PostgreSQL database hosting.</li>
          <li><strong>Cloudflare R2</strong> — private object storage for uploaded originals.</li>
          <li><strong>Paystack</strong> — payment processing, including Bank Transfer and Mobile Money.</li>
          <li><strong>Resend</strong> — transactional email delivery.</li>
          <li><strong>DeepSeek and Groq</strong> — AI providers used when AI-assisted generation is requested.</li>
        </ul>
        <p>
          These providers may process or store data outside Ghana. We do not
          sell personal data.
        </p>
      </LegalSection>

      <LegalSection title="7. Storage and security">
        <p>
          Account and curriculum data is stored in a managed PostgreSQL
          database. Uploaded originals are stored in access-controlled private
          object storage. Passwords are hashed and are not stored in plain
          text. Access is restricted to authorised platform administrators.
          No system is completely secure; contact us promptly if you believe
          an account or document has been compromised.
        </p>
      </LegalSection>

      <LegalSection title="8. Your rights under Ghana's Data Protection Act, 2012 (Act 843)">
        <p>
          Subject to the Act and applicable exceptions, you may:
        </p>
        <ul className="list-disc space-y-1 pl-6">
          <li>ask whether we hold personal data about you and request access to it;</li>
          <li>request correction of inaccurate or incomplete personal data;</li>
          <li>object to processing, or ask us to restrict it, where the law allows;</li>
          <li>request deletion of personal data that we are not required to keep;</li>
          <li>withdraw consent where processing relies on consent; and</li>
          <li>complain to BloomCore Technologies or the Ghana Data Protection Commission.</li>
        </ul>
        <p>
          Send requests to{' '}
          <a href={contactMailtoUrl('SchemeKnit — Privacy and Data Request')} className="text-brand-cyan underline break-all">
            {CONTACT_EMAIL}
          </a>
          . We may need to verify your identity before acting. Deletion is not
          always immediate or total: financial, tax, security and legal records
          may be retained for the periods described in our{' '}
          <a href="/data-retention" className="text-brand-cyan underline">
            Data Retention Policy
          </a>
          , and backup copies may take time to expire.
        </p>
      </LegalSection>

      <LegalSection title="9. Contact">
        <p>
          Privacy questions and complaints: {BUSINESS_NAME},{' '}
          <a href={contactMailtoUrl('SchemeKnit — Privacy and Data Request')} className="text-brand-cyan underline break-all">
            {CONTACT_EMAIL}
          </a>
          . You may also use our{' '}
          <a href="/contact" className="text-brand-cyan underline">Contact page</a>.
        </p>
        <p className="text-sm text-muted-foreground">
          This policy describes the current implementation. It is not a
          substitute for advice from a Ghanaian legal practitioner.
        </p>
      </LegalSection>
    </LegalPageLayout>
  )
}
