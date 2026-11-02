import assert from 'node:assert/strict'
import { test } from 'node:test'
import { restoreAt, runOptimistic } from '../../src/lib/optimistic.ts'

test('optimistic change applies before the request resolves', async () => {
  const order: string[] = []
  let release: (value: string) => void = () => {}
  const request = new Promise<string>((resolve) => { release = resolve })

  const run = runOptimistic({
    apply: () => order.push('apply'),
    rollback: () => order.push('rollback'),
    request: () => {
      order.push('request')
      return request
    },
    onSuccess: (value) => order.push(`success:${value}`),
  })

  assert.deepEqual(order, ['apply', 'request'])
  release('ok')
  await run
  assert.deepEqual(order, ['apply', 'request', 'success:ok'])
})

test('failed mutation rolls back and rethrows', async () => {
  const order: string[] = []
  await assert.rejects(
    runOptimistic({
      apply: () => order.push('apply'),
      rollback: () => order.push('rollback'),
      request: async () => { throw new Error('boom') },
      onError: (error) => order.push(`error:${(error as Error).message}`),
    }),
    /boom/,
  )
  assert.deepEqual(order, ['apply', 'rollback', 'error:boom'])
})

test('restoreAt puts a removed item back at its original position', () => {
  const remaining = ['a', 'c']
  assert.deepEqual(restoreAt(remaining, 'b', 1), ['a', 'b', 'c'])
  assert.deepEqual(remaining, ['a', 'c'])
})

test('restoreAt clamps an out-of-range index', () => {
  assert.deepEqual(restoreAt(['a'], 'b', 99), ['a', 'b'])
  assert.deepEqual(restoreAt(['a'], 'b', -3), ['b', 'a'])
})
