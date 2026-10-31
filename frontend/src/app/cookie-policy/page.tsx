import { LegalPageLayout, LegalSection } from '@/components/legal-page-layout'
import { pageMetadata } from '@/lib/site-url'
import {
  BUSINESS_NAME, BUSINESS_REGISTRATION_NUMBER, CONTACT_EMAIL,
  contactMailtoUrl,
} from '@/lib/contact'

export const metadata = pageMetadata({
  title: 'Cookie Policy',
  description: 'How SchemeKnit uses browser storage and cookies.',
  path: '/cookie-policy',
})

export default function CookiePolicyPage() {
  return (
    <LegalPageLayout
      title="Cookie Policy"
      subtitle="How SchemeKnit uses cookies and browser storage."
      lastUpdated="October 2026"
    >
      <LegalSection title="1. What cookies and browser storage are">
        <p>
          Cookies are small text files a website can ask a browser to store.
          Browsers also provide other storage: <strong>sessionStorage</strong>{' '}
          lasts only for one browser tab, <strong>localStorage</strong> lasts
          until cleared, and a <strong>service-worker cache</strong> stores
          static files for faster loading. These are different mechanisms; this
          policy names each one accurately.
        </p>
      </LegalSection>

      <LegalSection title="2. First-party cookies set by SchemeKnit">
        <p>
          The current SchemeKnit application does not set first-party browser
          cookies through application code. It does not use cookies for
          advertising, analytics, cross-site tracking or marketing.
        </p>
        <p>
          No cookie-consent banner is shown because the application does not
          currently use non-essential cookies or tracking technologies.
        </p>
      </LegalSection>

      <LegalSection title="3. Essential browser storage">
        <p>
          SchemeKnit uses browser storage that is necessary to operate the
          signed-in experience:
        </p>
        <ul className="list-disc space-y-1 pl-6">
          <li>
            <strong>sessionStorage</strong>: the authentication token and the
            signed-in user profile are stored for the current tab only. They
            are removed on sign-out, on session expiry, or when the tab is
            closed. A new tab does not inherit another tab&apos;s session.
          </li>
          <li>
            <strong>localStorage</strong>: the selected AI/generation mode and
            other interface preferences may be remembered on this device. A
            referral code from an invitation link may also be kept until the
            account is created. These values are not authentication tokens.
          </li>
          <li>
            <strong>sessionStorage (one-time flow flag)</strong>: a short-lived
            flag may pass the teacher from upload confirmation to the
            generation screen. It is removed after use.
          </li>
          <li>
            <strong>Service-worker cache</strong>: if the installable app is
            used, same-origin static assets such as scripts, icons and the web
            manifest are cached to speed up loading. API responses,
            authenticated page HTML, generated lessons, documents and exports
            are deliberately excluded.
          </li>
        </ul>
      </LegalSection>

      <LegalSection title="4. Analytics, advertising and tracking">
        <p>
          SchemeKnit does not currently run advertising pixels, marketing
          trackers, third-party analytics scripts or session-replay tools. If
          this changes, this policy and the necessary consent controls will be
          updated before those technologies are enabled.
        </p>
      </LegalSection>

      <LegalSection title="5. External services">
        <p>
          Some actions take you to an external service that has its own cookie
          and privacy practices:
        </p>
        <ul className="list-disc space-y-1 pl-6">
          <li>
            <strong>Paystack</strong>: when a payment is initiated or a
            payment page is opened, Paystack may set cookies or use similar
            storage on its own domain to process and secure the transaction.
          </li>
          <li>
            <strong>WhatsApp</strong>: opening a WhatsApp link takes you to
            WhatsApp or wa.me, which is operated by Meta and has its own
            cookie and privacy terms.
          </li>
          <li>
            <strong>Email</strong>: email links open your email provider, not a
            SchemeKnit-controlled web page.
          </li>
        </ul>
        <p>
          SchemeKnit does not control cookies set by those external services.
          Review the relevant provider&apos;s policy before using it.
        </p>
      </LegalSection>

      <LegalSection title="6. Managing browser storage">
        <p>
          You can clear or restrict cookies and site data in your browser
          settings. Blocking all storage may prevent sign-in or other
          essential parts of SchemeKnit from working. Clearing only
          sessionStorage or closing the tab ends the current tab&apos;s
          session; clearing localStorage removes remembered interface
          preferences.
        </p>
      </LegalSection>

      <LegalSection title="7. Contact">
        <p>
          SchemeKnit is operated by {BUSINESS_NAME}, business registration
          number {BUSINESS_REGISTRATION_NUMBER}. For questions about this
          policy or personal data, email{' '}
          <a href={contactMailtoUrl('SchemeKnit — Cookie and Privacy Enquiry')} className="text-brand-cyan underline break-all">
            {CONTACT_EMAIL}
          </a>
          . See also our{' '}
          <a href="/privacy-policy" className="text-brand-cyan underline">
            Privacy Policy
          </a>{' '}
          and{' '}
          <a href="/data-retention" className="text-brand-cyan underline">
            Data Retention Policy
          </a>
          .
        </p>
        <p className="text-sm text-muted-foreground">
          This policy describes the current implementation. It is not a
          substitute for legal advice.
        </p>
      </LegalSection>
    </LegalPageLayout>
  )
}
