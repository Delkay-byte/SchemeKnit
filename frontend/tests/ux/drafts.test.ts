import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  DRAFT_TTL_MS,
  draftAgeLabel,
  draftStorageKey,
  readDraft,
  removeDraft,
  sanitizeDraftValue,
  saveDraft,
  sweepExpiredDrafts,
  type DraftStorage,
} from '../../src/lib/drafts.ts'

class MemoryStorage implements DraftStorage {
  private map = new Map<string, string>()
  get length() { return this.map.size }
  key(index: number) { return Array.from(this.map.keys())[index] ?? null }
  getItem(key: string) { return this.map.get(key) ?? null }
  setItem(key: string, value: string) { this.map.set(key, value) }
  removeItem(key: string) { this.map.delete(key) }
  keys() { return Array.from(this.map.keys()) }
}

const USER = 'user-a'
const WORKFLOW = 'lesson-config'
const RESOURCE = 'scheme-1'

test('draft saves and restores for the same user and resource', () => {
  const storage = new MemoryStorage()
  const identity = { userId: USER, workflow: WORKFLOW, resourceId: RESOURCE }
  assert.equal(saveDraft(identity, { teacher_name: 'Ama' }, { storage, now: 1000 }).ok, true)
  const restored = readDraft<{ teacher_name: string }>(identity, { storage, now: 2000 })
  assert.equal(restored?.data.teacher_name, 'Ama')
  assert.equal(restored?.schemaVersion, 1)
  assert.equal(restored?.userId, USER)
})

test('drafts are isolated per user, workflow and resource', () => {
  const storage = new MemoryStorage()
  saveDraft({ userId: USER, workflow: WORKFLOW, resourceId: RESOURCE }, { value: 'a' }, { storage })
  assert.equal(readDraft({ userId: 'user-b', workflow: WORKFLOW, resourceId: RESOURCE }, { storage }), null)
  assert.equal(readDraft({ userId: USER, workflow: 'other', resourceId: RESOURCE }, { storage }), null)
  assert.equal(readDraft({ userId: USER, workflow: WORKFLOW, resourceId: 'scheme-2' }, { storage }), null)
})

test('draft keys are deterministic and scoped', () => {
  const key = draftStorageKey({ userId: USER, workflow: WORKFLOW, resourceId: RESOURCE })
  assert.match(key, /^schemeknit:draft:v1:user-a:lesson-config:scheme-1$/)
})

test('expired drafts are deleted when read', () => {
  const storage = new MemoryStorage()
  const identity = { userId: USER, workflow: WORKFLOW, resourceId: RESOURCE }
  saveDraft(identity, { value: 'old' }, { storage, now: 0 })
  assert.equal(readDraft(identity, { storage, now: DRAFT_TTL_MS + 1 }), null)
  assert.equal(storage.getItem(draftStorageKey(identity)), null)
})

test('sweeping removes only expired drafts for one user', () => {
  const storage = new MemoryStorage()
  const now = 10_000
  saveDraft({ userId: USER, workflow: 'a', resourceId: '1' }, { value: 1 }, { storage, now: now - DRAFT_TTL_MS - 1 })
  saveDraft({ userId: USER, workflow: 'b', resourceId: '2' }, { value: 2 }, { storage, now: now })
  saveDraft({ userId: 'user-b', workflow: 'a', resourceId: '1' }, { value: 3 }, { storage, now: now - DRAFT_TTL_MS - 1 })

  const removed = sweepExpiredDrafts(USER, { storage, now })
  assert.equal(removed, 1)
  assert.ok(storage.keys().some((key) => key.includes('user-b')))
  assert.ok(storage.keys().some((key) => key.includes(':b:')))
})

test('sensitive values are stripped before writing', () => {
  const storage = new MemoryStorage()
  const identity = { userId: USER, workflow: 'signup', resourceId: 'form' }
  saveDraft(identity, {
    full_name: 'Ama',
    email: 'ama@example.com',
    password: 'secret',
    turnstile_token: 'token-value',
    invite_code: 'PILOT-CODE',
    mfa_code: '123456',
    nested: { activation_code: 'ABC', note: 'keep' },
    items: [{ api_key: 'k', title: 'keep' }],
  }, { storage })

  const raw = storage.getItem(draftStorageKey(identity)) || ''
  assert.doesNotMatch(raw, /secret|token-value|PILOT-CODE|123456|ABC|"k"/)
  const restored = readDraft<Record<string, unknown>>(identity, { storage })
  assert.equal(restored?.data.full_name, 'Ama')
  assert.deepEqual(restored?.data.nested, { note: 'keep' })
  assert.deepEqual(restored?.data.items, [{ title: 'keep' }])
})

test('sanitizeDraftValue keeps ordinary editable content', () => {
  const value = sanitizeDraftValue({
    topic: 'Photosynthesis',
    duration: 40,
    days: [1, 2],
    assessment: 'Explain the process',
  })
  assert.deepEqual(value, {
    topic: 'Photosynthesis',
    duration: 40,
    days: [1, 2],
    assessment: 'Explain the process',
  })
})

test('explicit removal clears the draft', () => {
  const storage = new MemoryStorage()
  const identity = { userId: USER, workflow: WORKFLOW, resourceId: RESOURCE }
  saveDraft(identity, { value: 'x' }, { storage })
  removeDraft(identity, { storage })
  assert.equal(readDraft(identity, { storage }), null)
})

test('quota failures are reported without throwing', () => {
  const storage = new MemoryStorage()
  storage.setItem = () => { throw new Error('QuotaExceededError') }
  const result = saveDraft({ userId: USER, workflow: WORKFLOW }, { value: 'x' }, { storage })
  assert.deepEqual(result, { ok: false, error: 'quota' })
})

test('draft age labels stay human-readable', () => {
  assert.equal(draftAgeLabel(1_000, 1_000), 'just now')
  assert.equal(draftAgeLabel(1_000, 31_000), '30 seconds ago')
  assert.equal(draftAgeLabel(0, 60_000), '1 minute ago')
  assert.equal(draftAgeLabel(0, 7_200_000), '2 hours ago')
})
