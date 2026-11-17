import assert from 'node:assert/strict'
import { test } from 'node:test'
import { isCredential401 } from '../../src/lib/auth-401.ts'

test('sign-in 401 is a credential failure, not session expiry', () => {
  assert.equal(isCredential401('/api/auth/login'), true)
})

test('in-session credential actions keep the session alive', () => {
  assert.equal(isCredential401('/api/auth/change-password'), true)
  assert.equal(isCredential401('/api/auth/mfa/disable'), true)
  assert.equal(isCredential401('/api/auth/mfa/recovery/regenerate'), true)
})

test('session-check 401 still ends the stale session', () => {
  assert.equal(isCredential401('/api/auth/me'), false)
  assert.equal(isCredential401('/api/documents/'), false)
  assert.equal(isCredential401('/api/platform-admin/dashboard'), false)
})

test('an explicit backend code wins over the endpoint allowlist', () => {
  assert.equal(isCredential401('/api/auth/login', 'invalid_credentials'), true)
  assert.equal(isCredential401('/api/auth/me', 'invalid_credentials'), true)
})

test('query strings and nested paths still match their endpoint', () => {
  assert.equal(isCredential401('/api/auth/reset-token/validate?token=abc'), true)
  assert.equal(isCredential401('/api/auth/mfa/disable/extra'), true)
})
