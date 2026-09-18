import { LegalPageLayout, LegalSection } from '@/components/legal-page-layout'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Data Retention Policy',
  description: 'How long SchemeKnit keeps different types of data.',
}

export default function DataRetentionPage() {
  return (
    <LegalPageLayout
      title="Data Retention Policy"
      subtitle="How long SchemeKnit keeps different types of data."
      lastUpdated="September 2026"
    >
      <LegalSection title="1. Purpose">
        <p>
          This policy describes how long different types of data are retained
          and what happens when retention periods end. The goal is to keep
          data only as long as it serves a legitimate purpose.
        </p>
      </LegalSection>

      <LegalSection title="2. Retention Periods">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b text-left">
              <th className="py-2 pr-4 font-semibold">Data type</th>
              <th className="py-2 pr-4 font-semibold">Retention</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            <tr>
              <td className="py-2 pr-4">Account information</td>
              <td className="py-2 pr-4">Until account deletion is requested</td>
            </tr>
            <tr>
              <td className="py-2 pr-4">Uploaded schemes of work</td>
              <td className="py-2 pr-4">Until deleted by the owner or account deletion</td>
            </tr>
            <tr>
              <td className="py-2 pr-4">Generated lesson plans</td>
              <td className="py-2 pr-4">Until deleted by the owner or account deletion</td>
            </tr>
            <tr>
              <td className="py-2 pr-4">Exported files (DOCX/PDF/XLSX/ZIP)</td>
              <td className="py-2 pr-4">Deleted after 30 days or on download, whichever is first</td>
            </tr>
            <tr>
              <td className="py-2 pr-4">Payment and verification records</td>
              <td className="py-2 pr-4">7 years (financial record-keeping)</td>
            </tr>
            <tr>
              <td className="py-2 pr-4">Audit logs (security events)</td>
              <td className="py-2 pr-4">2 years</td>
            </tr>
            <tr>
              <td className="py-2 pr-4">Password reset tokens</td>
              <td className="py-2 pr-4">30 minutes (single-use, then destroyed)</td>
            </tr>
            <tr>
              <td className="py-2 pr-4">AI enrichment caches</td>
              <td className="py-2 pr-4">Deleted when the associated lesson is deleted</td>
            </tr>
          </tbody>
        </table>
      </LegalSection>

      <LegalSection title="3. Account Deletion">
        <p>
          When you request account deletion, we remove your account
          information, uploaded schemes, generated lessons, and associated
          files. Payment and verification records are retained for the
          financial record-keeping period listed above, with personal
          identifiers removed where practical.
        </p>
        <p>
          To request account deletion, please{' '}
          <a href="/contact" className="text-brand-cyan underline">contact us</a>.
        </p>
      </LegalSection>

      <LegalSection title="4. School Closure or Deactivation">
        <p>
          When a school deactivates SchemeKnit, the school's teachers retain
          access to their individually generated lesson plans for export.
          School-level data (license records, memberships) is retained for
          the financial record-keeping period.
        </p>
      </LegalSection>

      <LegalSection title="5. Backups">
        <p>
          Database backups are maintained for disaster recovery. Data deleted
          from the live system is removed from backups within 30 days of the
          deletion.
        </p>
      </LegalSection>
    </LegalPageLayout>
  )
}
