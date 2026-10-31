import React from 'react'
import Link from 'next/link'
import { SchemeKnitMark } from '@/components/scheme-knit-mark'
import { WhatsAppIcon } from '@/components/whatsapp-button'
import {
  BUSINESS_NAME, BUSINESS_REGISTRATION_DATE, BUSINESS_REGISTRATION_NUMBER,
  CONTACT_EMAIL, CONTACT_PHONE_LOCAL, CONTACT_PHONE_LOCAL_2,
  contactMailtoUrl, contactTelUrl, contactTelUrl2, whatsappUrl,
} from '@/lib/contact'

/**
 * Public site footer — appears on the landing page and all public legal pages.
 *
 * The registered-business panel is deliberately factual: it contains only the
 * details shown on the supplied Registrar of Companies certificate and the
 * owner-confirmed contact channels. The business TIN, proprietor identity and
 * any invented address are never rendered here.
 */
export function PublicFooter() {
  return (
    <footer className="border-t bg-brand-navy text-white">
      <div className="container mx-auto px-4 py-10 md:py-14">
        <div className="grid grid-cols-1 gap-8 sm:grid-cols-2 md:grid-cols-4">
          {/* Brand */}
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <span
                className="flex h-10 w-10 items-center justify-center rounded-xl border"
                style={{
                  background: '#F4F7FA',
                  borderColor: 'rgba(16,42,67,0.12)',
                  boxShadow: '0 0 0 1px rgba(4,169,206,0.28)',
                }}
              >
                <SchemeKnitMark size={26} />
              </span>
              <span className="text-lg font-bold">
                Scheme<span className="text-[#04A9CE]">Knit</span>
              </span>
            </div>
            <p className="text-sm text-white/70">
              Professional lesson plan generation for Ghanaian teachers and schools.
            </p>
          </div>

          {/* Product */}
          <div>
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-white/90">
              Product
            </h3>
            <ul className="space-y-2 text-sm">
              <li>
                <Link href="/features" className="text-white/70 hover:text-white">
                  Features
                </Link>
              </li>
              <li>
                <Link href="/how-it-works" className="text-white/70 hover:text-white">
                  How It Works
                </Link>
              </li>
              <li>
                <Link href="/pricing" className="text-white/70 hover:text-white">
                  Pricing
                </Link>
              </li>
              <li>
                <Link href="/help" className="text-white/70 hover:text-white">
                  Help &amp; FAQ
                </Link>
              </li>
              <li>
                <Link href="/about" className="text-white/70 hover:text-white">
                  About
                </Link>
              </li>
            </ul>
          </div>

          {/* Support */}
          <div>
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-white/90">
              Support
            </h3>
            <ul className="space-y-2 text-sm">
              <li>
                <Link href="/contact" className="text-white/70 hover:text-white">
                  Contact
                </Link>
              </li>
              <li>
                <a
                  href={contactMailtoUrl('SchemeKnit enquiry')}
                  className="text-white/70 hover:text-white break-all"
                  aria-label={`Email BloomCore Technologies at ${CONTACT_EMAIL}`}
                >
                  Email
                </a>
              </li>
              <li>
                <a
                  href={contactTelUrl()}
                  className="text-white/70 hover:text-white"
                  aria-label={`Call BloomCore Technologies on ${CONTACT_PHONE_LOCAL}`}
                >
                  Call {CONTACT_PHONE_LOCAL}
                </a>
              </li>
              <li>
                <a
                  href={contactTelUrl2()}
                  className="text-white/70 hover:text-white"
                  aria-label={`Call BloomCore Technologies on ${CONTACT_PHONE_LOCAL_2}`}
                >
                  Call {CONTACT_PHONE_LOCAL_2}
                </a>
              </li>
              <li>
                <a
                  href={whatsappUrl()}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 text-white/70 hover:text-white"
                  aria-label={`Chat with BloomCore Technologies on WhatsApp (${CONTACT_PHONE_LOCAL})`}
                >
                  <WhatsAppIcon className="h-4 w-4 text-[#25D366]" />
                  WhatsApp
                </a>
              </li>
            </ul>
          </div>

          {/* Legal */}
          <div>
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-white/90">
              Legal
            </h3>
            <ul className="space-y-2 text-sm">
              <li>
                <Link href="/privacy-policy" className="text-white/70 hover:text-white">
                  Privacy Policy
                </Link>
              </li>
              <li>
                <Link href="/terms" className="text-white/70 hover:text-white">
                  Terms of Service
                </Link>
              </li>
              <li>
                <Link href="/refunds-cancellation" className="text-white/70 hover:text-white">
                  Refund &amp; Cancellation
                </Link>
              </li>
              <li>
                <Link href="/data-retention" className="text-white/70 hover:text-white">
                  Data Retention
                </Link>
              </li>
              <li>
                <Link href="/license-subscription" className="text-white/70 hover:text-white">
                  License &amp; Subscription Terms
                </Link>
              </li>
              <li>
                <Link href="/cookie-policy" className="text-white/70 hover:text-white">
                  Cookie Policy
                </Link>
              </li>
            </ul>
          </div>
        </div>

        {/* Registered business panel */}
        <section
          className="mt-10 rounded-2xl border border-white/15 bg-white/5 p-5 sm:p-6"
          aria-labelledby="registered-business-heading"
          data-registered-business
        >
          <h2
            id="registered-business-heading"
            className="text-xs font-bold uppercase tracking-[0.18em] text-[#7DD3E8]"
          >
            Registered Business
          </h2>
          <p className="mt-2 text-lg font-bold text-white">{BUSINESS_NAME}</p>
          <p className="text-sm text-white/70">
            Ghana-registered business name. Operated as a sole proprietorship.
          </p>

          <dl className="mt-4 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <dt className="text-xs uppercase tracking-wide text-white/50">
                Business Registration No.
              </dt>
              <dd className="font-semibold text-white">{BUSINESS_REGISTRATION_NUMBER}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-white/50">
                Registration Date
              </dt>
              <dd className="font-semibold text-white">{BUSINESS_REGISTRATION_DATE}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-white/50">
                Registered Under
              </dt>
              <dd className="text-white/85">
                Registration of Business Names Act, 1962 (No. 151)
              </dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-xs uppercase tracking-wide text-white/50">
                Issuing Authority
              </dt>
              <dd className="text-white/85">
                Office of the Registrar of Companies, Republic of Ghana
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-white/50">
                Telephone
              </dt>
              <dd className="flex flex-wrap items-center gap-x-2 gap-y-1 text-white/85">
                <a href={contactTelUrl()} className="hover:text-white underline underline-offset-2">
                  {CONTACT_PHONE_LOCAL}
                </a>
                <span aria-hidden="true" className="text-white/40">/</span>
                <a href={contactTelUrl2()} className="hover:text-white underline underline-offset-2">
                  {CONTACT_PHONE_LOCAL_2}
                </a>
                <a
                  href={whatsappUrl()}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-[#7DE3A8] hover:text-white"
                  aria-label={`WhatsApp BloomCore Technologies on ${CONTACT_PHONE_LOCAL}`}
                >
                  <WhatsAppIcon className="h-3.5 w-3.5" />
                  WhatsApp
                </a>
              </dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-xs uppercase tracking-wide text-white/50">Email</dt>
              <dd>
                <a
                  href={contactMailtoUrl('SchemeKnit enquiry')}
                  className="break-all text-white/85 underline underline-offset-2 hover:text-white"
                >
                  {CONTACT_EMAIL}
                </a>
              </dd>
            </div>
          </dl>
        </section>

        <div className="mt-8 border-t border-white/20 pt-6">
          <p className="text-sm text-white/60">
            &copy; {new Date().getFullYear()} SchemeKnit. All rights reserved.
            Operated by {BUSINESS_NAME}, Ghana.
          </p>
        </div>
      </div>
    </footer>
  )
}
