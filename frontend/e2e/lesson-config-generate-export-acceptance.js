// Temporary manual browser check for the corrected configuration flow.
// Uses a direct API-created teacher session because the local signup page's
// registration-policy request is not reachable in this harness.
const { chromium } = require('playwright')
const path = require('path')

const WEB = 'http://localhost:3010'
const API = 'http://localhost:8011'
const SCHEME = path.join(__dirname, '..', '..', 'backend', 'uploads',
  '1d3813d1-8fce-47b1-ac81-2ab40c5a8bb8_BASIC 9 SCIENCE SCHEME OF LEARNING.docx')
const STAMP = Date.now()
const EMAIL = `e2e.manual.${STAMP}@schemeknit.test`
const PASS = 'SchemeKnit#2026'

async function main() {
  const reg = await fetch(`${API}/api/auth/register/individual`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: EMAIL, password: PASS, full_name: 'E2E Manual' }),
  })
  if (!reg.ok) throw new Error(`register ${reg.status}: ${await reg.text()}`)
  const session = await reg.json()

  const browser = await chromium.launch()
  const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 } })
  await ctx.addInitScript(({ token, user }) => {
    sessionStorage.setItem('teachflow_token', token)
    sessionStorage.setItem('teachflow_user', JSON.stringify(user))
  }, { token: session.access_token, user: session.user })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))

  await page.goto(`${WEB}/upload`, { waitUntil: 'domcontentloaded' })
  await page.locator('input[type="file"]').waitFor({ state: 'attached', timeout: 30000 })
  await page.waitForTimeout(4000)
  await page.locator('input[type="file"]').setInputFiles(SCHEME)
  await page.waitForTimeout(1500)
  const upload = page.getByRole('button', { name: /upload & process/i })
  if (await upload.isDisabled()) {
    throw new Error(`upload button disabled; body=${(await page.locator('body').innerText()).slice(0, 600)}`)
  }
  await upload.click()
  await page.waitForSelector('[data-upload-success]', { timeout: 240000 })
  const review = page.getByRole('button', { name: /review curriculum/i })
  if (await review.count()) await review.click()
  await page.waitForURL(/\/review\//, { timeout: 90000 })
  const schemeId = page.url().match(/review\/([^/?]+)/)[1]

  await page.locator('[data-configure-lesson-rubrics]').click()
  await page.waitForSelector('[data-lesson-config-modal]', { timeout: 20000 })
  const reference = 'Computing curriculum page 16\nTeacher guide page 4'
  await page.fill('#lcfg-school', 'Awasive M/A JHS')
  await page.fill('#lcfg-teacher', 'Mabel Asamoah')
  await page.fill('#lcfg-class-size', '22')
  await page.fill('#lcfg-duration', '60')
  await page.fill('#lcfg-periods', '2')
  await page.fill('#lcfg-period', '2nd & 4th')
  await page.fill('#lcfg-reference', reference)
  for (const day of ['Tuesday', 'Thursday']) {
    const chip = page.locator(`[data-lesson-config-modal] button:has-text("${day}")`)
    if ((await chip.getAttribute('aria-pressed')) !== 'true') await chip.click()
  }
  const typedReference = await page.inputValue('#lcfg-reference')
  if (typedReference !== reference) throw new Error('reference textarea lost spacing/newline')
  await page.click('[data-save-lesson-config]')
  await page.waitForSelector('[data-lesson-config-modal]', { state: 'detached', timeout: 30000 })

  await page.goto(`${WEB}/generate/${schemeId}`, { waitUntil: 'domcontentloaded' })
  await page.locator('[data-lesson-review]').waitFor({ timeout: 120000 })
  const tlr = page.locator('textarea[id^="other-tlrs-"]').first()
  await tlr.fill('Computer\nUSB mouse\nExercise books')
  const typedTlr = await tlr.inputValue()
  if (typedTlr !== 'Computer\nUSB mouse\nExercise books') throw new Error('TLR textarea lost newlines')

  // Two official competencies, selected on the first lesson.
  const firstRow = page.locator('[data-lesson-review] .space-y-2.rounded-md').first()
  await firstRow.getByRole('button', { name: /Critical Thinking and Problem Solving \(CP\)/ }).click()
  await firstRow.getByRole('button', { name: /Digital Literacy \(DL\)/ }).click()
  await page.getByRole('button', { name: /Save review/i }).click()
  await page.waitForTimeout(1500)

  // Reload: the persisted draft must restore every entry and selection.
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.locator('[data-lesson-review]').waitFor({ timeout: 120000 })
  const savedTlr = await page.locator('textarea[id^="other-tlrs-"]').first().inputValue()
  if (!savedTlr.includes('Computer') || !savedTlr.includes('USB mouse')
      || !savedTlr.includes('Exercise books')) {
    throw new Error(`TLR draft not restored: ${savedTlr}`)
  }
  const savedRefs = await page.evaluate(async (sid) => {
    const token = sessionStorage.getItem('teachflow_token')
    const r = await fetch(`http://localhost:8011/api/generation/${sid}/lesson-config`,
      { headers: { Authorization: `Bearer ${token}` } })
    return r.json()
  }, schemeId)
  if (!savedRefs?.config?.reference?.includes('Computing curriculum page 16')
      || !savedRefs.config.reference.includes('Teacher guide page 4')) {
    throw new Error(`reference not persisted: ${JSON.stringify(savedRefs)}`)
  }
  const reviewState = await page.evaluate(async (sid) => {
    const token = sessionStorage.getItem('teachflow_token')
    const r = await fetch(`http://localhost:8011/api/generation/${sid}/lesson-review`,
      { headers: { Authorization: `Bearer ${token}` } })
    return r.json()
  }, schemeId)
  const draft = Object.values(reviewState.drafts || {})[0] || {}
  if (!(draft.core_competencies || []).includes('Critical Thinking and Problem Solving (CP)')
      || !(draft.core_competencies || []).includes('Digital Literacy (DL)')) {
    throw new Error(`competencies not persisted: ${JSON.stringify(draft)}`)
  }
  if (errors.length) throw new Error(`page errors: ${errors.join(' | ')}`)
  console.log('PASS reference textarea keeps spaces and newlines')
  console.log('PASS TLR textarea keeps spaces and newlines')
  console.log('PASS configuration and multiple competencies persist after reload')

  // ── Generate, verify scheme order, and download both canonical exports ──
  await page.getByRole('button', { name: /Generate lesson plans/i }).click()
  await page.getByRole('button', { name: /Download DOCX/i }).waitFor({ timeout: 360000 })
  console.log('PASS generation completed through the single Generate action')
  const lessons = await page.evaluate(async (sid) => {
    const token = sessionStorage.getItem('teachflow_token')
    const r = await fetch(`http://localhost:8011/api/generation/schemes/${sid}/lessons`,
      { headers: { Authorization: `Bearer ${token}` } })
    return r.json()
  }, schemeId)
  const weeks = (lessons.lesson_plans || []).map((lp) => lp.week_number)
  const sorted = [...weeks].sort((a, b) => a - b)
  if (JSON.stringify(weeks) !== JSON.stringify(sorted)) {
    throw new Error(`lesson order is not scheme order: ${weeks}`)
  }
  console.log(`PASS generated lessons keep scheme order: ${weeks.join(', ')}`)

  const docxDownload = page.waitForEvent('download', { timeout: 180000 })
  await page.getByRole('button', { name: /Download DOCX/i }).click()
  const docx = await docxDownload
  const docxPath = path.join(__dirname, 'lesson-config-generate-export.docx')
  await docx.saveAs(docxPath)

  const pdfDownload = page.waitForEvent('download', { timeout: 240000 })
  await page.getByRole('button', { name: /Download PDF/i }).click()
  const pdf = await pdfDownload
  const pdfPath = path.join(__dirname, 'lesson-config-generate-export.pdf')
  await pdf.saveAs(pdfPath)
  const fs = require('fs')
  if (fs.readFileSync(docxPath).subarray(0, 2).toString() !== 'PK') {
    throw new Error('DOCX is not a package')
  }
  if (fs.readFileSync(pdfPath).subarray(0, 5).toString() !== '%PDF-') {
    throw new Error('PDF has no PDF signature')
  }
  console.log('PASS DOCX and DOCX-derived PDF downloaded')
  console.log(`exports=${docxPath}|${pdfPath}`)
  console.log(`scheme=${schemeId}`)
  await browser.close()
}

main().catch((e) => { console.error('FAIL', e.message); process.exit(1) })
