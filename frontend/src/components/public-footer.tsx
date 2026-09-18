import React from 'react'
import Link from 'next/link'
import { SchemeKnitMark } from '@/components/scheme-knit-mark'
import { isDesktop } from '@/lib/build-target'

/**
 * Public site footer — appears on the landing page and all public legal pages.
 *
 * Links are grouped: Product, Support, Legal, Platform.
 * Must remain usable on mobile (single column stack).
 */
export function PublicFooter() {
  return (
    <footer className="border-t bg-brand-navy text-white">
      <div className="container mx-auto px-4 py-10 md:py-14">
        <div className="grid grid-cols-1 gap-8 sm:grid-cols-2 md:grid-cols-4">
          {/* Brand */}
          <div className="space-y-3">
            <div className="flex items-center space-x-2.5">
              <SchemeKnitMark size={28} className="h-7 w-7" />
              <span className="text-lg font-bold">SchemeKnit</span>
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

        {/* Platform — web only */}
        {!isDesktop && (
          <div className="mt-8 border-t border-white/20 pt-6">
            <div className="flex flex-col items-start gap-2 text-sm sm:flex-row sm:items-center sm:justify-between">
              <p className="text-white/60">
                &copy; {new Date().getFullYear()} SchemeKnit. All rights reserved.
              </p>
              <div className="flex items-center gap-4">
                <Link
                  href="/login/platform-admin"
                  className="text-white/60 hover:text-white"
                >
                  Staff / Platform Admin
                </Link>
              </div>
            </div>
          </div>
        )}
        {isDesktop && (
          <div className="mt-8 border-t border-white/20 pt-6">
            <p className="text-white/60 text-sm">
              &copy; {new Date().getFullYear()} SchemeKnit. All rights reserved.
            </p>
          </div>
        )}
      </div>
    </footer>
  )
}
