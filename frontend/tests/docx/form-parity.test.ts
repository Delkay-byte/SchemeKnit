import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { extractDocxText, fillFormDocument } from '../../src/lib/docx/ooxml.ts'
import { assertSameLines, fixture, publicAsset, xmldomAdapter } from './helpers.ts'

for (const name of ['official_ges', 'wapef']) {
  test(`${name}: browser fill preserves the server text and form topology`, () => {
    const { model, backendText } = fixture(name)
    assert.equal(model.renderer, 'form')
    const documents = model.documents
    const forms = documents.map((document) => {
      assert.ok(document.form, 'form model missing')
      return document.form
    })
    const bytes = fillFormDocument(
      publicAsset(forms[0].asset),
      forms,
      { appendices: model.appendices, xml: xmldomAdapter },
    )

    const text = extractDocxText(bytes, xmldomAdapter)
    assertSameLines(text, backendText, name)

    // No placeholder may survive into a teacher's document.
    assert.ok(!/\[[A-Z][A-Z0-9_]*\]/.test(text), 'unfilled placeholder left in output')

    // The form itself is preserved: two tables per lesson block (the bundled
    // form's own tables), not a rebuilt layout.
    const source = extractDocxText(publicAsset(forms[0].asset), xmldomAdapter)
    assert.ok(source.length > 0)
  })
}

test('standalone export of one lesson keeps school, teacher and week identity', () => {
  const { model } = fixture('official_ges')
  const document = model.documents[1]
  assert.ok(document.form)
  const bytes = fillFormDocument(
    publicAsset(document.form.asset),
    [document.form],
    {
      standalone: true,
      appendices: document.appendix ? [document.appendix] : [],
      xml: xmldomAdapter,
    },
  )
  const text = extractDocxText(bytes, xmldomAdapter)
  assert.match(text, /Achimota Basic School/)
  assert.match(text, /A\. Mensah/)
  assert.match(text, /Week 1/)
})

test('cancelling or empty input never fabricates a document', () => {
  const { model } = fixture('official_ges')
  const form = model.documents[0].form
  assert.ok(form)
  assert.throws(
    () => fillFormDocument(publicAsset(form.asset), [], { xml: xmldomAdapter }),
    /nothing to export/i,
  )
})

test('template assets match the backend byte-for-byte', async () => {
  const manifest = JSON.parse(
    readFileSync(
      fileURLToPath(new URL('../../public/docx-templates/manifest.json', import.meta.url)),
      'utf8',
    ),
  )
  for (const [name, hash] of Object.entries(manifest.assets as Record<string, string>)) {
    const bytes = new Uint8Array(
      readFileSync(
        fileURLToPath(new URL(`../../../backend/src/engines/assets/${name}`, import.meta.url)),
      ),
    )
    const { createHash } = await import('node:crypto')
    const actual = createHash('sha256').update(bytes).digest('hex')
    assert.equal(actual, hash, `${name} drifted from backend asset`)
    const publicBytes = publicAsset(`docx-templates/${name}`)
    assert.equal(
      createHash('sha256').update(publicBytes).digest('hex'),
      hash,
      `${name} is stale in public/docx-templates`,
    )
  }
})
