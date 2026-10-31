import { ShieldCheck } from 'lucide-react'

import { cn } from '@/lib/utils'

/**
 * Exact wording required by the owner. Do not rewrite or shorten it: the
 * notice tells teachers what may be uploaded and what SchemeKnit is not for.
 * Tests assert this string verbatim.
 */
export const UPLOAD_PRIVACY_NOTICE =
  "Upload curriculum and teaching documents only. Please do not include pupils' names, personal information, grades or other identifiable student records. SchemeKnit is a teacher lesson-planning tool, not a student records management system."

/**
 * Upload-stage privacy notice. Shown before the teacher selects or drops a
 * file, on every screen that accepts a Scheme of Learning.
 *
 * It is intentionally an informational note (not a warning banner): the goal
 * is a clear instruction, not alarm. `role="note"` keeps it available to
 * assistive technology without interrupting the upload flow.
 */
export function UploadPrivacyNotice({ className }: { className?: string }) {
  return (
    <section
      data-upload-privacy-notice
      role="note"
      aria-labelledby="upload-privacy-notice-title"
      className={cn(
        'mb-4 rounded-2xl border border-[#04A9CE]/30 bg-[#F1FAFC] px-4 py-4 text-[#102A43] shadow-[0_6px_18px_rgba(16,42,67,0.06)] sm:px-5',
        className,
      )}
    >
      <div className="flex items-start gap-3">
        <ShieldCheck
          className="mt-0.5 h-5 w-5 shrink-0 text-[#04769B]"
          aria-hidden="true"
        />
        <div className="min-w-0">
          <h2
            id="upload-privacy-notice-title"
            className="text-sm font-semibold"
          >
            Before you upload
          </h2>
          <p className="mt-1 break-words text-sm leading-relaxed">
            {UPLOAD_PRIVACY_NOTICE}
          </p>
          <p className="mt-2 break-words text-xs leading-relaxed text-[#486581]">
            Tip: remove or anonymise pupil names, grades and other personal
            details from the document before you upload it.
          </p>
        </div>
      </div>
    </section>
  )
}
