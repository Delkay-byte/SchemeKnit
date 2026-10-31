/**
 * Safe purchase-return destinations.
 *
 * A browser-supplied `next` value is never trusted. Only the internal upgrade
 * route with an approved paid package slug is accepted. The upgrade page
 * re-checks the slug against the live server catalogue before any payment can
 * start, so the catalogue remains authoritative.
 */

export const APPROVED_PAID_PACKAGE_SLUGS = [
  'flexible-credit-pack',
  'teacher-monthly',
  'teacher-term-pass',
  'academic-year-pass',
] as const

export type PaidPackageSlug = (typeof APPROVED_PAID_PACKAGE_SLUGS)[number]

export function isApprovedPaidPackageSlug(value: string): value is PaidPackageSlug {
  return (APPROVED_PAID_PACKAGE_SLUGS as readonly string[]).includes(value)
}

/** Canonical upgrade path for a selected package, or null when invalid. */
export function upgradePath(slug: string): string | null {
  if (!isApprovedPaidPackageSlug(slug)) return null
  return `/upgrade?package=${encodeURIComponent(slug)}`
}

/**
 * Validate a return destination. Returns the canonical internal path, or null.
 *
 * Rejected: absolute URLs, protocol-relative URLs, backslashes, other routes,
 * unknown packages, duplicate query keys and extra destinations.
 */
export function safeNextPath(raw: string | null | undefined): string | null {
  if (!raw) return null
  const value = raw.trim()
  if (!value.startsWith('/') || value.startsWith('//')) return null
  if (value.includes('\\') || value.includes('://')) return null
  try {
    const parsed = new URL(value, 'https://schemeknit.invalid')
    if (parsed.origin !== 'https://schemeknit.invalid') return null
    const pathname = parsed.pathname.replace(/\/+$/, '') || '/'
    if (pathname !== '/upgrade') return null
    const slugs = parsed.searchParams.getAll('package')
    if (slugs.length !== 1) return null
    if ([...parsed.searchParams.keys()].some((key) => key !== 'package')) {
      return null
    }
    return upgradePath(slugs[0])
  } catch {
    return null
  }
}

/** Append a validated next destination to an authentication page. */
export function authHref(
  base: '/login' | '/signup',
  next: string | null | undefined,
): string {
  const safe = safeNextPath(next)
  return safe ? `${base}?next=${encodeURIComponent(safe)}` : base
}

/** Read and validate the `next` query parameter in the browser. */
export function currentNextPath(): string | null {
  if (typeof window === 'undefined') return null
  try {
    return safeNextPath(new URLSearchParams(window.location.search).get('next'))
  } catch {
    return null
  }
}
