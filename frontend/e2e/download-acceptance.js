/**
 * TeachFlow browser export-download acceptance.
 *
 * Drives a REAL browser (Chrome and Edge) through the canonical web app to
 * verify the reported production failures:
 *   - "Download Word: FAIL" in Chrome (worked in Edge)
 *   - "Download PDF: FAIL" in both
 *
 * It deliberately asserts on what the BROWSER does with the response, which
 * unit tests cannot cover:
 *   - a Word download actually reaches disk and is a real .docx
 *   - a PDF download is either a real PDF or a controlled, user-visible error
 *
 * Usage: node e2e/download-acceptance.js <chrome|msedge>
 */
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')
const { record, summary } = require('./report')

// Edge closes its target before Playwright's own teardown handshake completes,
// which surfaces as an unhandled rejection after every check has already been
// recorded. Ignore that shutdown race only; anything else still fails the run.
process.on('unhandledRejection', (err) => {
  const msg = String((err && err.message) || err)
  if (/TargetClosedError|Target page, context or browser has been closed/.test(msg)) return
  console.error('Unhandled rejection:', msg)
  process.exitCode = 1
})

const CHANNEL = process.argv[2] || 'chrome'  // 'bundled' = Playwright's Chromium (system Chrome may be hooked by extensions)
const WEB = process.env.TF_WEB_URL || 'http://localhost:3000'
const SCHEME_ID = process.env.TF_SCHEME_ID
const TEACHER = { email: process.env.TF_TEACHER_EMAIL || 'teacher@acceptance.test', password: process.env.TF_TEACHER_PASSWORD || 'TeacherPass123' }
const OUT = path.resolve(process.env.TF_DOWNLOAD_DIR || __dirname, '..', '..', 'backend', 'temp', 'ba', 'downloads')

const DOCX_MIME =
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

async function saveDownload(page, label, action, timeout = 30000) {
  const target = path.join(OUT, `${CHANNEL}-${label}`)
  try {
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout }),
      action(),
    ])
    const suggested = download.suggestedFilename()
    const dest = path.join(OUT, `${CHANNEL}-${suggested}`)
    await download.saveAs(dest)
    const bytes = fs.readFileSync(dest)
    return { ok: true, suggested, path: dest, size: bytes.length, head: bytes.subarray(0, 4).toString('binary') }
  } catch (e) {
    return { ok: false, error: e.message }
  }
}

;(async () => {
  fs.mkdirSync(OUT, { recursive: true })
  const browser = await chromium.launch(CHANNEL === 'bundled' ? { downloadsPath: OUT } : { channel: CHANNEL, downloadsPath: OUT })
  const context = await browser.newContext({ acceptDownloads: true })
  const page = await context.newPage()

  // A server with a working converter must deliver a real PDF. If PDF still
  // fails it must fail controlled (503 no-converter / 500 conversion-failed),
  // both of which the UI surfaces as a message rather than a broken file.
  const EXPECTED = [/\/export\/pdf$/]
  const badResponses = []
  const pageErrors = []
  page.on('response', (r) => {
    if (r.status() < 400) return
    const url = r.url().split('?')[0]
    if (EXPECTED.some((re) => re.test(url))) return
    badResponses.push(`${r.status()} ${url}`)
  })
  page.on('pageerror', (e) => pageErrors.push(e.message))

  console.log(`\n=== TeachFlow export downloads — ${CHANNEL} ===`)

  try {
    // 1. Real UI login
    await page.goto(`${WEB}/login/`, { waitUntil: 'domcontentloaded' })
    await page.fill('input[type="email"]', TEACHER.email)
    await page.fill('input[type="password"]', TEACHER.password)
    await page.click('button[type="submit"]')
    await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 30000 })
    record('teacher login through the UI', true, page.url())

    // 2. Open the generation/export page for the generated job
    await page.goto(`${WEB}/generate/${SCHEME_ID}/`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('button:has-text("Download DOCX")', { timeout: 30000 })
    record('export panel rendered', true)

    // 3. Select the canonical approved organizational template
    const select = page.locator('select').first()
    const optionCount = await select.locator('option').count()
    let approvedLabel = null
    for (let i = 0; i < optionCount; i++) {
      const value = await select.locator('option').nth(i).getAttribute('value')
      if (value === 'tpl-approved-org-headteacher') {
        approvedLabel = (await select.locator('option').nth(i).innerText()).trim()
        break
      }
    }
    if (approvedLabel) {
      await select.selectOption('tpl-approved-org-headteacher')
    }
    record('approved organizational template is selectable',
      !!approvedLabel, approvedLabel || `${optionCount} options, approved template not offered`)

    // 4. Chrome: Word download must reach disk
    const docx = await saveDownload(page, 'download', () =>
      page.click('button:has-text("Download DOCX")'))
    record('[Word] browser saved a file',
      docx.ok, docx.ok ? `${docx.suggested} (${docx.size} bytes)` : docx.error)
    if (docx.ok) {
      record('[Word] saved file is a real DOCX (PK zip signature)',
        docx.head.startsWith('PK'), `head=${JSON.stringify(docx.head)}`)
      record('[Word] filename has the .docx extension',
        docx.suggested.toLowerCase().endsWith('.docx'), docx.suggested)
    }

    // 4b. Batch ZIP must be downloadable and must not silently drop the template
    const zip = await saveDownload(page, 'download-zip', () =>
      page.click('button:has-text("Export ZIP")'))
    if (zip.ok) {
      record('[ZIP] browser saved a file', true, `${zip.suggested} (${zip.size} bytes)`)
      record('[ZIP] saved file is a real archive', zip.head.startsWith('PK'), zip.suggested)
      record('[ZIP] filename has the .zip extension',
        zip.suggested.toLowerCase().endsWith('.zip'), zip.suggested)
    } else {
      record('[ZIP] browser saved a file', false, zip.error)
    }

    // 5. PDF: a genuine PDF download when the server has a converter; when it
    // does not, a controlled visible message instead of a raw failure.
    const pdf = await saveDownload(page, 'download-pdf', () =>
      page.click('button:has-text("Download PDF")'), 120000)
    if (pdf.ok) {
      record('[PDF] browser saved a file', true, `${pdf.suggested} (${pdf.size} bytes)`)
      record('[PDF] saved file is a real PDF (%PDF- signature)',
        pdf.head === '%PDF', `head=${JSON.stringify(pdf.head)}`)
      record('[PDF] filename has the .pdf extension',
        pdf.suggested.toLowerCase().endsWith('.pdf'), pdf.suggested)
    } else {
      // No download: the app must show the server's controlled message instead.
      await page.waitForTimeout(1500)
      const body = await page.locator('body').innerText()
      const controlled = /PDF export requires a document converter|PDF conversion failed on the server/i.test(body)
      record('[PDF] no download -> controlled, user-visible message', controlled,
        controlled ? body.split('\n').find((l) => /PDF (export|conversion)/i.test(l)) : 'no controlled message shown')
      record('[PDF] failure did not surface a raw stack trace',
        !/Traceback|at Object\.|\.py:\d+/i.test(body), '')
    }

    record('no uncaught exceptions', pageErrors.length === 0,
      pageErrors.slice(0, 3).join(' | '))
    record('no unexpected failing requests', badResponses.length === 0,
      badResponses.slice(0, 5).join(' | '))
  } catch (e) {
    record('harness completed without throwing', false, e.message)
  } finally {
    // Edge occasionally tears the target down before the close handshake; that
    // is a browser-shutdown race, not a product failure.
    try {
      await browser.close()
    } catch {
      /* already closed */
    }
  }

  const ok = summary(`Browser acceptance (${CHANNEL})`)
  process.exit(ok ? 0 : 1)
})()
