import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { DOMParser, XMLSerializer } from '@xmldom/xmldom'
import type { XmlAdapter } from '../../src/lib/docx/ooxml.ts'

const here = (path: string) => fileURLToPath(new URL(path, import.meta.url))

export const xmldomAdapter: XmlAdapter = {
  parse: (xml: string) => new DOMParser().parseFromString(xml, 'application/xml') as unknown as Document,
  serialize: (doc: Document) => new XMLSerializer().serializeToString(doc as unknown as Node),
}

export function fixture(name: string): {
  model: import('../../src/lib/docx/types.ts').ExportModel
  backendText: string
  docx: Uint8Array
} {
  const model = JSON.parse(readFileSync(here(`../fixtures/docx/${name}.model.json`), 'utf8'))
  const backendText = readFileSync(here(`../fixtures/docx/${name}.txt`), 'utf8')
  const bytes = readFileSync(here(`../fixtures/docx/${name}.docx`))
  return { model, backendText, docx: new Uint8Array(bytes) }
}

export function publicAsset(path: string): Uint8Array {
  const bytes = readFileSync(here(`../../public/${path}`))
  return new Uint8Array(bytes)
}

export function sha256(bytes: Uint8Array): string {
  return createHash('sha256').update(bytes).digest('hex')
}

/** Compare line-oriented document text, ignoring blank lines and edge spaces. */
export function normalizedLines(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
}

export function assertSameLines(actual: string, expected: string, label: string): void {
  const got = normalizedLines(actual)
  const want = normalizedLines(expected)
  if (got.join('\n') === want.join('\n')) return
  const limit = Math.max(got.length, want.length)
  const differences: string[] = []
  for (let i = 0; i < limit; i += 1) {
    if (got[i] !== want[i]) {
      differences.push(`line ${i + 1}:\n  browser: ${JSON.stringify(got[i])}\n  server:  ${JSON.stringify(want[i])}`)
    }
    if (differences.length >= 8) break
  }
  assert.fail(`${label}: ${differences.length} text difference(s)\n${differences.join('\n')}`)
}
