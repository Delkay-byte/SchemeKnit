/**
 * 401 classification for the API client.
 *
 * A 401 does not always mean "the session died". The sign-in endpoint and the
 * in-session credential actions (password change, MFA disable/regenerate,
 * reset-token checks) answer 401 when the *submitted* credential is wrong.
 * Mutating the stored session for those responses signs a perfectly valid user
 * out in the middle of a security action, and on the sign-in form it produced
 * the production P0 message "Your session has expired. Please sign in again."
 * for a simple rejected password.
 *
 * Kept in its own DOM-free module so the rule is unit-testable; `api.ts` is
 * bound to `window`/`fetch` at call time.
 */
export const CREDENTIAL_401_ENDPOINTS = [
  '/api/auth/login',
  '/api/auth/setup',
  '/api/auth/change-password',
  '/api/auth/mfa/disable',
  '/api/auth/mfa/recovery/regenerate',
  '/api/auth/reset-token/validate',
  '/api/auth/confirm-password-reset',
] as const

/**
 * True when a 401 came from a credential check rather than a session check.
 *
 * `failureCode` wins when the backend supplies one, so a future endpoint that
 * reports `invalid_credentials` is classified correctly without a code change
 * here. The endpoint allowlist covers the deployed backend, which returns a
 * plain human `detail` for these responses.
 */
export function isCredential401(endpoint: string, failureCode = ''): boolean {
  if (failureCode === 'invalid_credentials') return true
  return CREDENTIAL_401_ENDPOINTS.some((prefix) => endpoint.startsWith(prefix))
}
