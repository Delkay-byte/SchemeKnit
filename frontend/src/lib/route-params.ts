'use client'

/**
 * Resolve a dynamic route id with desktop static-export compatibility.
 *
 * The packaged desktop app serves a statically exported frontend: every
 * /<segment>/<id> URL is served the prerendered placeholder page, so Next's
 * useParams() returns the build-time id ('placeholder') instead of the live id.
 * In that case (and only then) fall back to the live browser URL.
 *
 * On the web build useParams() is always correct, so this is a no-op there.
 */
export function resolveRouteId(paramId: string | string[] | undefined, segment: string): string {
  const raw = Array.isArray(paramId) ? paramId[0] : paramId
  if (raw && raw !== 'placeholder') {
    return raw
  }
  if (typeof window !== 'undefined') {
    const m = window.location.pathname.match(new RegExp(`/${segment}/([^/]+)`))
    if (m && m[1] && m[1] !== 'placeholder') {
      return decodeURIComponent(m[1])
    }
  }
  return raw || ''
}
