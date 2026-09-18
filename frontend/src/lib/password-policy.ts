/**
 * Frontend mirror of the backend password policy (PART 4).
 *
 * The backend is authoritative; this duplicates the rule only to give the
 * teacher immediate feedback beside the field. The exact rule is also published
 * by GET /api/auth/setup/status under `password_policy`, so the UI can stay in
 * sync with the server rather than hard-coding a divergent copy.
 *
 * Minimum 8 characters, including at least one letter, one number and one
 * symbol.
 */

export const PASSWORD_POLICY = {
  min_length: 8,
  requires_letter: true,
  requires_digit: true,
  requires_symbol: true,
  description: 'At least 8 characters, including a letter, a number and a symbol.',
} as const

export const EMAIL_RULE_TEXT = 'Use your email address, e.g. name@school.edu.gh.'

/**
 * Validate a password against the production policy. Mirrors
 * `src/validation.py:validate_password` — keep both in lockstep.
 */
export function validatePassword(password: string): { ok: boolean; message: string } {
  if (!password) return { ok: false, message: 'Password is required.' }
  if (password.length < PASSWORD_POLICY.min_length) {
    return { ok: false, message: PASSWORD_POLICY.description }
  }
  if (!/[A-Za-z]/.test(password)) {
    return { ok: false, message: PASSWORD_POLICY.description }
  }
  if (!/\d/.test(password)) {
    return { ok: false, message: PASSWORD_POLICY.description }
  }
  if (!/[^A-Za-z\d\s]/.test(password)) {
    return { ok: false, message: PASSWORD_POLICY.description }
  }
  return { ok: true, message: '' }
}

/**
 * Validate an email address is a real address, not a placeholder or username.
 * Mirrors `src/validation.py:validate_email`.
 */
export function validateEmail(email: string): { ok: boolean; message: string } {
  if (!email) return { ok: false, message: 'A valid email address is required.' }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email.trim())) {
    return { ok: false, message: 'Enter a valid email address, e.g. name@school.edu.gh.' }
  }
  return { ok: true, message: '' }
}

/** Normalize an email for comparison: trimmed and lower-cased. */
export function normalizeEmail(email: string): string {
  return (email || '').trim().toLowerCase()
}
