import assert from 'node:assert/strict'
import { test } from 'node:test'
import { packBlocksDocument } from '../../src/lib/docx/blocks.ts'
import { extractDocxText } from '../../src/lib/docx/ooxml.ts'
import { assertSameLines, fixture, xmldomAdapter } from './helpers.ts'

for (const name of ['sections', 'custom_structure']) {
  test(`${name}: browser blocks preserve the server text`, async () => {
    const { model, backendText } = fixture(name)
    assert.equal(model.renderer, 'blocks')
    const blob = await packBlocksDocument(model.documents, model.structure)
    const bytes = new Uint8Array(await blob.arrayBuffer())
    const text = extractDocxText(bytes, xmldomAdapter)
    assertSameLines(text, backendText, name)
  })
}

test('custom structure keeps merged cells and table dimensions', async () => {
  const { model } = fixture('custom_structure')
  const document = model.documents[0]
  const table = document.blocks?.find((block) => block.kind === 'customTable')
  assert.ok(table && table.kind === 'customTable')
  assert.equal(table.rows, 3)
  assert.equal(table.cols, 3)
  const spanning = table.cells.find((cell) => (cell.colspan || 1) > 1)
  assert.ok(spanning, 'expected a horizontally merged cell')
})

test('export does not mutate the persisted lesson model', async () => {
  const { model } = fixture('sections')
  const before = JSON.stringify(model)
  await packBlocksDocument(model.documents, model.structure)
  assert.equal(JSON.stringify(model), before)
})

test('one lesson produces one document, not a duplicate of its neighbour', async () => {
  const { model } = fixture('sections')
  const blob = await packBlocksDocument([model.documents[0]], model.structure)
  const bytes = new Uint8Array(await blob.arrayBuffer())
  const text = extractDocxText(bytes, xmldomAdapter)
  assert.match(text, /LESSON PLAN/)
  assert.ok(text.split('\n').filter((line) => line.trim()).length > 10)
})
