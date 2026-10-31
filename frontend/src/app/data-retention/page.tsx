import { LegalPageLayout, LegalSection } from '@/components/legal-page-layout'
import { pageMetadata } from '@/lib/site-url'
import { BUSINESS_NAME, CONTACT_EMAIL, contactMailtoUrl } from '@/lib/contact'

export const metadata = pageMetadata({
  title: 'Data Retention Policy',
  description: 'What SchemeKnit stores, why, and how deletion works.',
  path: '/data-retention',
})

export default function DataRetentionPage() {
  return (
    <LegalPageLayout
      title="Data Retention Policy"
      subtitle="What SchemeKnit stores, why, and how deletion works."
      lastUpdated="October 2026"
    >
      <LegalSection title="1. Purpose and approach">
        <p>
          This policy describes the data categories SchemeKnit actually stores,
          why they are kept, whether the user can delete them, and whether
          deletion is immediate. Some records are retained for security,
          financial or legal reasons. This policy does not promise immediate
          destruction of every copy.
        </p>
      </LegalSection>

      <LegalSection title="2. Retention summary">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[42rem] border-collapse text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="py-2 pr-4 font-semibold">Data</th>
                <th className="py-2 pr-4 font-semibold">Why stored</th>
                <th className="py-2 pr-4 font-semibold">User deletion</th>
                <th className="py-2 pr-4 font-semibold">Retention</th>
              </tr>
            </thead>
            <tbody className="divide-y align-top">
              <tr>
                <td className="py-2 pr-4">Account and profile</td>
                <td className="py-2 pr-4">Sign-in, role and service delivery</td>
                <td className="py-2 pr-4">Request account deletion</td>
                <td className="py-2 pr-4">Until the request is processed; limited records may be retained</td>
              </tr>
              <tr>
                <td className="py-2 pr-4">Uploaded schemes of work</td>
                <td className="py-2 pr-4">Extraction and lesson generation</td>
                <td className="py-2 pr-4">Yes — delete the scheme</td>
                <td className="py-2 pr-4">Deleted with the scheme; the private stored original is removed when no other scheme references it</td>
              </tr>
              <tr>
                <td className="py-2 pr-4">Generated lesson plans</td>
                <td className="py-2 pr-4">Review, editing and export</td>
                <td className="py-2 pr-4">Yes — delete the scheme/lesson where offered</td>
                <td className="py-2 pr-4">Until deleted or account deletion is processed; no scheduled automatic purge</td>
              </tr>
              <tr>
                <td className="py-2 pr-4">Export files (DOCX/PDF/XLSX/ZIP)</td>
                <td className="py-2 pr-4">Download and regeneration</td>
                <td className="py-2 pr-4">Request removal</td>
                <td className="py-2 pr-4">No scheduled automatic 30-day purge is implemented. Download links expire after 10 minutes and are single-use; stored export files may remain until operational cleanup or a deletion request</td>
              </tr>
              <tr>
                <td className="py-2 pr-4">Payment and verification records</td>
                <td className="py-2 pr-4">Payment verification, accounting and fraud prevention</td>
                <td className="py-2 pr-4">Normally retained</td>
                <td className="py-2 pr-4">No automatic expiry; retained as required for financial, tax and audit obligations</td>
              </tr>
              <tr>
                <td className="py-2 pr-4">Paystack webhook events</td>
                <td className="py-2 pr-4">Idempotency, recovery and payment integrity</td>
                <td className="py-2 pr-4">Normally retained</td>
                <td className="py-2 pr-4">No automatic expiry; retained for payment reconciliation and security</td>
              </tr>
              <tr>
                <td className="py-2 pr-4">Security, login and audit records</td>
                <td className="py-2 pr-4">Security, abuse prevention and accountability</td>
                <td className="py-2 pr-4">Normally retained</td>
                <td className="py-2 pr-4">No automatic expiry currently configured; retained only while needed for security and legal purposes</td>
              </tr>
              <tr>
                <td className="py-2 pr-4">Password-reset tokens</td>
                <td className="py-2 pr-4">One-time account recovery</td>
                <td className="py-2 pr-4">Not applicable</td>
                <td className="py-2 pr-4">Expire after 30 minutes and are single-use; the database row may remain as a used marker</td>
              </tr>
              <tr>
                <td className="py-2 pr-4">MFA and recovery information</td>
                <td className="py-2 pr-4">Privileged-account security</td>
                <td className="py-2 pr-4">Disable MFA or request account deletion</td>
                <td className="py-2 pr-4">Until disabled, regenerated or account deletion is processed</td>
              </tr>
              <tr>
                <td className="py-2 pr-4">AI enrichment and generation caches</td>
                <td className="py-2 pr-4">Reuse identical output and avoid repeated provider cost</td>
                <td className="py-2 pr-4">Limited; removed with associated data/cleanup where implemented</td>
                <td className="py-2 pr-4">No scheduled automatic expiry; the whole-lesson cache is not tied to a lesson row</td>
              </tr>
              <tr>
                <td className="py-2 pr-4">Database backups</td>
                <td className="py-2 pr-4">Disaster recovery at the infrastructure provider</td>
                <td className="py-2 pr-4">Indirect; request support</td>
                <td className="py-2 pr-4">Controlled by the hosting/database provider. Deleted live data may persist in backups until the provider&apos;s backup cycle expires; immediate removal cannot be guaranteed</td>
              </tr>
            </tbody>
          </table>
        </div>
      </LegalSection>

      <LegalSection title="3. Account deletion and privacy requests">
        <p>
          To request account deletion or another privacy request, email{' '}
          <a href={contactMailtoUrl('SchemeKnit — Account Deletion Request')} className="text-brand-cyan underline break-all">
            {CONTACT_EMAIL}
          </a>
          . We may need to verify your identity. We will delete or anonymise
          data that we are not required to keep. Payment, tax, fraud-prevention
          and security records may be retained for as long as a genuine legal
          or operational obligation applies.
        </p>
        <p>
          Deleting an uploaded scheme removes its stored original when no other
          scheme references the same object. Generated exports are not
          guaranteed to be removed by that action; ask us to remove residual
          export files if needed.
        </p>
      </LegalSection>

      <LegalSection title="4. School closure or deactivation">
        <p>
          When a school deactivates SchemeKnit, teachers normally keep access
          to their individually generated lesson plans for export according to
          the account status. School licence, membership and payment records
          are retained for legitimate financial and audit purposes.
        </p>
      </LegalSection>

      <LegalSection title="5. Contact">
        <p>
          {BUSINESS_NAME} —{' '}
          <a href={contactMailtoUrl('SchemeKnit — Data Retention Enquiry')} className="text-brand-cyan underline break-all">
            {CONTACT_EMAIL}
          </a>
          . See also our{' '}
          <a href="/privacy-policy" className="text-brand-cyan underline">Privacy Policy</a>{' '}
          and{' '}
          <a href="/cookie-policy" className="text-brand-cyan underline">Cookie Policy</a>.
        </p>
      </LegalSection>
    </LegalPageLayout>
  )
}
