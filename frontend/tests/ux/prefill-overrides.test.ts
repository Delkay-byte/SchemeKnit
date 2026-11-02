import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  clearPrefillOverrides,
  prefillOverrideKey,
  readClearedFields,
  setFieldCleared,
  type OverrideStorage,
} from '../../src/lib/prefill-overrides.ts'

class MemoryStorage implements OverrideStorage {
  private map = new Map<string, string>()
  getItem(key: string) { return this.map.get(key) ?? null }
  setItem(key: string, value: string) { this.map.set(key, value) }
  removeItem(key: string) { this.map.delete(key) }
}

const identity = { userId: 'teacher-a', workflow: 'lesson-config', resourceId: 'scheme-1' }

test('a cleared field is remembered for the same user and scheme', () => {
  const storage = new MemoryStorage()
  setFieldCleared(identity, 'teacher_name', true, { storage })
  assert.deepEqual([...readClearedFields(identity, { storage })], ['teacher_name'])
})

test('cleared fields are isolated by user and resource', () => {
  const storage = new MemoryStorage()
  setFieldCleared(identity, 'teacher_name', true, { storage })
  assert.equal(readClearedFields({ ...identity, userId: 'teacher-b' }, { storage }).size, 0)
  assert.equal(readClearedFields({ ...identity, resourceId: 'scheme-2' }, { storage }).size, 0)
})

test('restoring a default removes the override', () => {
  const storage = new MemoryStorage()
  setFieldCleared(identity, 'teacher_name', true, { storage })
  setFieldCleared(identity, 'teacher_name', false, { storage })
  assert.equal(readClearedFields(identity, { storage }).size, 0)
  assert.equal(storage.getItem(prefillOverrideKey(identity)), null)
})

test('clearing every override removes the record entirely', () => {
  const storage = new MemoryStorage()
  setFieldCleared(identity, 'teacher_name', true, { storage })
  setFieldCleared(identity, 'school_name', true, { storage })
  clearPrefillOverrides(identity, { storage })
  assert.equal(readClearedFields(identity, { storage }).size, 0)
})

test('a malformed or future-version record is ignored safely', () => {
  const storage = new MemoryStorage()
  storage.setItem(prefillOverrideKey(identity), '{not json')
  assert.equal(readClearedFields(identity, { storage }).size, 0)
  storage.setItem(prefillOverrideKey(identity), JSON.stringify({ version: 99, cleared: ['teacher_name'] }))
  assert.equal(readClearedFields(identity, { storage }).size, 0)
})

test('a storage failure never breaks the form', () => {
  const storage = new MemoryStorage()
  storage.setItem = () => { throw new Error('quota') }
  assert.doesNotThrow(() => setFieldCleared(identity, 'teacher_name', true, { storage }))
  assert.equal(readClearedFields(identity, { storage }).size, 0)
})
