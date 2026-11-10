import assert from 'node:assert/strict'
import { test } from 'node:test'
import { unzipSync } from 'fflate'
import { safeDocxFilename, safeZipFilename, uniqueNames } from '../../src/lib/docx/filename.ts'
import { generateZip } from '../../src/lib/docx/generate.ts'
import { modelWithTwoPlans } from './model-factory.ts'

test('filename sanitizer keeps the extension and drops unsafe characters', () => {
  assert.equal(safeDocxFilename('Science/Basic 7: Week 1?.docx'), 'Science_Basic 7_ Week 1_.docx')
  assert.equal(safeDocxFilename('   .docx'), 'lesson_plan.docx')
  assert.equal(safeZipFilename('Lesson Plans: Term 1'), 'Lesson Plans_ Term 1.zip')
})

test('duplicate lesson names receive a suffix instead of overwriting', () => {
  const names = uniqueNames([
    'SCIENCE_B7_W01_L01_2026-02-03.docx',
    'SCIENCE_B7_W01_L01_2026-02-03.docx',
    'SCIENCE_B7_W01_L02_2026-02-03.docx',
  ])
  assert.equal(new Set(names.map((name) => name.toLowerCase())).size, 3)
  assert.equal(names[0], 'SCIENCE_B7_W01_L01_2026-02-03.docx')
  assert.match(names[1], /_2\.docx$/)
  assert.equal(names[2], 'SCIENCE_B7_W01_L02_2026-02-03.docx')
})

test('ZIP contains every plan, no duplicates, with DOCX MIME members', async () => {
  const model = modelWithTwoPlans()
  const progress: string[] = []
  const file = await generateZip(model, {
    onProgress: (event) => progress.push(event.phase),
  })
  assert.equal(file.blob.type, 'application/zip')
  const archive = unzipSync(new Uint8Array(await file.blob.arrayBuffer()))
  const names = Object.keys(archive)
  assert.equal(names.length, 2)
  assert.equal(new Set(names).size, 2)
  for (const name of names) {
    assert.match(name, /\.docx$/)
    const inner = unzipSync(archive[name])
    assert.ok(inner['word/document.xml'], `${name} is not a Word package`)
    assert.ok(inner['[Content_Types].xml'], `${name} has no content types`)
  }
  assert.ok(progress.includes('rendering'))
  assert.ok(progress.includes('zipping'))
  assert.ok(progress.includes('complete'))
})

test('aborting stops before any file is produced', async () => {
  const controller = new AbortController()
  controller.abort()
  await assert.rejects(
    () => generateZip(modelWithTwoPlans(), { signal: controller.signal }),
    /cancelled/i,
  )
})
