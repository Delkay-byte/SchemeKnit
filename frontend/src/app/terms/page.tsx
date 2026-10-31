import { LegalPageLayout, LegalSection } from '@/components/legal-page-layout'
import { pageMetadata } from '@/lib/site-url'
import { SITE_URL } from '@/lib/site-url'
import {
  BUSINESS_ADDRESS, BUSINESS_NAME, BUSINESS_REGISTRATION_DATE,
  BUSINESS_REGISTRATION_NUMBER, CONTACT_EMAIL, CONTACT_PHONE_LOCAL,
  CONTACT_PHONE_LOCAL_2, contactMailtoUrl, contactTelUrl, contactTelUrl2,
} from '@/lib/contact'

export const metadata = pageMetadata({
  title: 'Terms of Service',
  description: 'The terms and conditions for using SchemeKnit.',
  path: '/terms',
})

export default function TermsPage() {
  return (
    <LegalPageLayout
      title="Terms of Service"
      subtitle="The terms and conditions for using SchemeKnit."
      lastUpdated="October 2026"
    >
      <LegalSection title="1. Acceptance of these Terms">
        <p>
          These Terms are between you and {BUSINESS_NAME}, the business that
          operates SchemeKnit. By creating an account, signing in or using the
          service, you agree to these Terms and to our Privacy Policy, Cookie
          Policy, Refund &amp; Cancellation Policy, Data Retention Policy and
          License &amp; Subscription Terms.
        </p>
      </LegalSection>

      <LegalSection title="2. What SchemeKnit is">
        <p>
          SchemeKnit is a teacher lesson-planning platform. It extracts
          curriculum structure from an uploaded scheme of learning, helps the
          teacher review it, and generates indicator-level lesson plans. It
          also saves and exports plans.
        </p>
        <p>
          SchemeKnit is not a student records management system, a student
          performance database or a general-purpose learning management
          system.
        </p>
      </LegalSection>

      <LegalSection title="3. Individual teacher accounts">
        <p>
          An individual teacher may use the Free plan or buy a prepaid credit
          package. The account holder is responsible for the accuracy of the
          account details and for activity performed through the account.
        </p>
      </LegalSection>

      <LegalSection title="4. School-managed accounts">
        <p>
          A school may hold a licence and manage teacher accounts within its
          seat limit. School administrators control membership and school-level
          access. Platform administrators manage the service, schools and
          licences. Role boundaries are enforced by the service.
        </p>
      </LegalSection>

      <LegalSection title="5. Account security">
        <p>
          Keep your password and authentication factors confidential. Do not
          share a session, password or MFA code. Tell us promptly if you
          believe your account has been compromised. We may revoke sessions or
          require a password reset where necessary to protect the account or
          the service.
        </p>
      </LegalSection>

      <LegalSection title="6. Uploaded documents and ownership">
        <p>
          You keep ownership of the documents you upload and the lesson plans
          you generate from them, subject to any rights held by the original
          curriculum owner. You grant us the limited right to store, process,
          extract and display that content solely to provide the service to
          you.
        </p>
        <p>
          Upload only documents you have the right to use. Do not upload
          confidential third-party material without permission.
        </p>
      </LegalSection>

      <LegalSection title="7. No pupil records">
        <p className="font-semibold text-brand-navy">
          Do not upload pupils&apos; names, personal information, grades or
          other identifiable student records. SchemeKnit is not designed or
          authorised for that purpose.
        </p>
      </LegalSection>

      <LegalSection title="8. Curriculum extraction and review">
        <p>
          Extracted curriculum data may contain errors from the source
          document or from automated detection. You must review the extracted
          subject, class, weeks and indicators before generating lessons. Where
          the system asks you to confirm a subject or class, that confirmation
          is your responsibility.
        </p>
      </LegalSection>

      <LegalSection title="9. Indicator-level lesson generation">
        <p>
          SchemeKnit generates lesson plans focused on individual curriculum
          indicators. One selected indicator produces one independently
          teachable lesson plan. Several indicators in one scheme week may
          produce several separate plans.
        </p>
      </LegalSection>

      <LegalSection title="10. Credits">
        <p>
          One credit is consumed for each independently generated lesson unit,
          consistently with the credit implementation. Cached or replayed
          output, failed generation and deterministic fallback do not consume
          a credit. Free credits reset according to the calendar-month policy.
          Purchased credits follow the validity of the package purchased.
        </p>
      </LegalSection>

      <LegalSection title="11. Saving and editing">
        <p>
          Generated plans can be saved, reviewed, edited and reloaded according
          to the features available on your plan. You are responsible for
          reviewing and adapting generated content before classroom use.
        </p>
      </LegalSection>

      <LegalSection title="12. Exports">
        <p>
          SchemeKnit supports DOCX and PDF export, and XLSX or ZIP export where
          the relevant feature is available to your account. Download links are
          short-lived and single-use. Export files are generated from your
          persisted lesson data.
        </p>
      </LegalSection>

      <LegalSection title="13. Optional AI-assisted content">
        <p>
          AI enrichment is optional and may be unavailable during provider
          outages. When used, it produces advisory content that you must review
          for accuracy, curriculum alignment, cultural appropriateness and
          classroom suitability. Deterministic generation remains available
          without AI.
        </p>
      </LegalSection>

      <LegalSection title="14. Payments and verification">
        <p>
          Individual paid packages are prepaid by Bank Transfer or Mobile Money
          through Paystack. SchemeKnit does not store full payment credentials.
          A package activates only after Paystack confirms the payment and
          SchemeKnit verifies the reference, amount, currency and account.
          Pending, failed or expired payments do not activate credits.
        </p>
      </LegalSection>

      <LegalSection title="15. Prepaid packages">
        <p>
          All individual teacher paid packages are one-time purchases. Teacher
          Monthly, Teacher Term Pass and Academic Year Pass provide
          time-limited credits for their stated validity periods. They do not
          renew automatically and there is no recurring card charge. See the{' '}
          <a href="/license-subscription" className="text-brand-cyan underline">
            License &amp; Subscription Terms
          </a>
          .
        </p>
      </LegalSection>

      <LegalSection title="16. Unacceptable use">
        <ul className="list-disc space-y-1 pl-6">
          <li>Uploading unlawful content or other people&apos;s private records.</li>
          <li>Attempting to bypass credits, quotas, rate limits or authentication.</li>
          <li>Sharing account credentials or reselling access without permission.</li>
          <li>Attacking, probing or disrupting the service or its providers.</li>
          <li>Using the service to harm, deceive or discriminate against others.</li>
        </ul>
      </LegalSection>

      <LegalSection title="17. Service availability">
        <p>
          We aim to keep SchemeKnit available but do not guarantee uninterrupted
          service. Maintenance, provider outages, network failures and events
          beyond our control may interrupt access. We do not guarantee that
          every generated lesson is error-free or suitable for every classroom.
        </p>
      </LegalSection>

      <LegalSection title="18. Suspension">
        <p>
          We may suspend or restrict an account for serious or repeated
          violations of these Terms, abuse of the service, fraud, security
          risk or non-payment. Where appropriate, we will explain the reason
          and the route to appeal. Suspension does not remove statutory rights
          that cannot be excluded.
        </p>
      </LegalSection>

      <LegalSection title="19. Intellectual property">
        <p>
          SchemeKnit, its software, branding and interface are owned by or
          licensed to {BUSINESS_NAME}. You receive a limited, non-exclusive,
          non-transferable right to use the service for your own teaching or
          school work. You may not copy, resell or reverse-engineer the service
          except as permitted by law.
        </p>
      </LegalSection>

      <LegalSection title="20. Liability">
        <p>
          To the maximum extent permitted by applicable law, we are not liable
          for indirect, incidental or consequential loss, or for loss of
          profits, data or goodwill arising from use of the service. Nothing in
          these Terms excludes or limits liability that cannot lawfully be
          excluded, including applicable consumer rights under Ghanaian law.
        </p>
      </LegalSection>

      <LegalSection title="21. Supplier information and electronic-commerce disclosures">
        <p>
          This section provides the supplier information required for electronic
          transactions under section 47 of the Electronic Transactions Act,
          2008 (Act 772).
        </p>
        <ul className="list-disc space-y-1 pl-6">
          <li>
            <strong>Supplier:</strong> {BUSINESS_NAME}, a Ghana-registered
            business name operating as a sole proprietorship. Business
            Registration No. {BUSINESS_REGISTRATION_NUMBER}, registered{' '}
            {BUSINESS_REGISTRATION_DATE} under the Registration of Business
            Names Act, 1962 (No. 151).
          </li>
          <li><strong>Physical address:</strong> {BUSINESS_ADDRESS}</li>
          <li>
            <strong>Telephone:</strong>{' '}
            <a href={contactTelUrl()} className="text-brand-cyan underline">{CONTACT_PHONE_LOCAL}</a>
            {' '}(calls and WhatsApp) or{' '}
            <a href={contactTelUrl2()} className="text-brand-cyan underline">{CONTACT_PHONE_LOCAL_2}</a>
            {' '}(calls only).
          </li>
          <li>
            <strong>Email:</strong>{' '}
            <a href={contactMailtoUrl('SchemeKnit — Supplier Enquiry')} className="text-brand-cyan underline break-all">{CONTACT_EMAIL}</a>
          </li>
          <li>
            <strong>Website:</strong>{' '}
            <a href={SITE_URL} className="text-brand-cyan underline break-all">{SITE_URL}</a>
          </li>
          <li>
            <strong>Self-regulatory or related-body membership:</strong> no
            membership is claimed on this website. No code of conduct is
            currently published or claimed. If either applies in future, this
            section will be updated before publication.
          </li>
          <li>
            <strong>Service characteristics and prices:</strong> teacher
            lesson-plan generation, review, saving and export. Current packages,
            full prices, credits and validity are on the{' '}
            <a href="/pricing" className="text-brand-cyan underline">Pricing page</a>{' '}
            and in the{' '}
            <a href="/license-subscription" className="text-brand-cyan underline">License &amp; Subscription Terms</a>.
          </li>
          <li>
            <strong>Payment methods:</strong> prepaid Bank Transfer or Mobile
            Money through Paystack. Packages do not renew automatically. A
            package activates only after verified payment.
          </li>
          <li>
            <strong>Performance and transaction records:</strong> access is
            provided after verified activation. The signed-in teacher can view
            credit balance, package state and payment history where available.
          </li>
          <li>
            <strong>Refunds and cancellation:</strong> see the{' '}
            <a href="/refunds-cancellation" className="text-brand-cyan underline">Refund &amp; Cancellation Policy</a>.
          </li>
          <li>
            <strong>Payment security and privacy:</strong> payment credentials
            are handled by Paystack; SchemeKnit does not store full card details
            or Mobile Money PINs. See the{' '}
            <a href="/privacy-policy" className="text-brand-cyan underline">Privacy Policy</a>{' '}
            and <a href="/cookie-policy" className="text-brand-cyan underline">Cookie Policy</a>.
          </li>
          <li>
            <strong>Minimum duration:</strong> there is no recurring or
            open-ended commitment. Individual paid packages are one-time
            purchases; time-limited credits expire at the stated validity.
          </li>
          <li>
            <strong>Consumer rights:</strong> nothing in these Terms excludes a
            right under the Electronic Transactions Act, 2008 (Act 772), the
            Data Protection Act, 2012 (Act 843) or other mandatory Ghanaian law.
          </li>
        </ul>
      </LegalSection>

      <LegalSection title="22. Contact and disputes">
        <p>
          Contact {BUSINESS_NAME} at{' '}
          <a href={contactMailtoUrl('SchemeKnit — Terms Enquiry')} className="text-brand-cyan underline break-all">
            {CONTACT_EMAIL}
          </a>{' '}
          or through the <a href="/contact" className="text-brand-cyan underline">Contact page</a>.
          Raise a concern with us first so we can try to resolve it. These Terms
          are governed by the laws of the Republic of Ghana, without limiting
          mandatory consumer protections.
        </p>
        <p className="text-sm text-muted-foreground">
          These Terms describe the current service and are not a substitute for
          advice from a Ghanaian legal practitioner.
        </p>
      </LegalSection>
    </LegalPageLayout>
  )
}
