import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { test } from 'node:test'

const ROOTS = ['src/app', 'src/components', 'src/lib', 'src/types']
const RETIRED = /adesua|ad\s*esua/i

function walk(dir: string): string[] {
  const files: string[] = []
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) files.push(...walk(full))
    else if (/\.(tsx?|jsx?)$/.test(entry)) files.push(full)
  }
  return files
}

test('no customer-facing source file shows the retired Adesua branding', () => {
  const offenders: string[] = []
  for (const root of ROOTS) {
    for (const file of walk(root)) {
      const text = readFileSync(file, 'utf8')
      if (RETIRED.test(text)) offenders.push(file)
    }
  }
  assert.deepEqual(offenders, [])
})

test('the dashboard free-plan card uses neutral wording', () => {
  const page = readFileSync('src/app/(app)/dashboard/page.tsx', 'utf8')
  assert.match(page, /FREE PLAN/)
  assert.match(page, /Free plan/)
  assert.doesNotMatch(page, /Individual plan/)
})
