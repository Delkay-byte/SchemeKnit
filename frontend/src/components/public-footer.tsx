import React from 'react'
import Link from 'next/link'
import { SchemeKnitMark } from '@/components/scheme-knit-mark'
import { WhatsAppIcon } from '@/components/whatsapp-button'
import { whatsappUrl, contactMailtoUrl, CONTACT_EMAIL } from '@/lib/contact'

/**
 * Public site footer — appears on the landing page and all public legal pages.
 *
 * Links are grouped: Product, Support, Legal.
 * Must remain usable on mobile (single column stack).
 *
 * Staff/Platform Admin is deliberately NOT linked here: it stays reachable only
 * through its secure direct route, outside the normal public journey.
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
                <Link href="/#teachers" className="text-white/70 hover:text-white">
                  Teachers
                </Link>
              </li>
              <li>
                <Link href="/#schools" className="text-white/70 hover:text-white">
                  Schools
                </Link>
              </li>
              <li>
                <Link href="/#individual" className="text-white/70 hover:text-white">
                  Individual Teacher
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
                  Contact Support
                </Link>
              </li>
              <li>
                <a
                  href={contactMailtoUrl('SchemeKnit enquiry')}
                  className="text-white/70 hover:text-white break-all"
                  aria-label={`Email BloomCore Technologies at ${CONTACT_EMAIL}`}
                >
                  {CONTACT_EMAIL}
                </a>
              </li>
              <li>
                <a
                  href={whatsappUrl()}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 text-white/70 hover:text-white"
                  aria-label="Chat with BloomCore Technologies on WhatsApp"
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
            </ul>
          </div>
        </div>

        <div className="mt-8 border-t border-white/20 pt-6">
          <p className="text-white/60 text-sm">
            &copy; {new Date().getFullYear()} SchemeKnit. All rights reserved.
            {' '}A product of BloomCore Technologies.
          </p>
        </div>
      </div>
    </footer>
  )
}
