/**
 * Upload privacy notice — browser acceptance.
 *
 * Pins the owner's exact notice on the Scheme of Learning upload page before
 * any file is selected, at desktop and mobile widths, and confirms the
 * existing file-selection interaction still works.
 *
 * Usage: node e2e/upload-privacy-notice.js [baseUrl]
 * Requires: backend on :8000 + `npm run build` + `next start` already running.
 */
const { chromium } = require('playwright')
const path = require('path')

const BASE = process.argv[2] || 'http://localhost:3000'
const TEACHER = { email: 'accept.teacher@schemeknit.test', password: 'Accept#2026' }
const SAMPLE = path.resolve(
  __dirname,
  '../../backend/real_documents/BASIC 9 SCIENCE SCHEME OF LEARNING.docx',
)

const EXACT_NOTICE =
  "Upload curriculum and teaching documents only. Please do not include pupils' names, personal information, grades or other identifiable student records. SchemeKnit is a teacher lesson-planning tool, not a student records management system."

let pass = 0
let fail = 0

function log(ok, label, detail = '') {
  if (ok) pass++
  else fail++
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? ' — ' + detail : ''}`)
}

async function login(page) {
  await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.locator('input[type="email"]').fill(TEACHER.email)
  await page.locator('input[type="password"]').fill(TEACHER.password)
  await page.getByRole('button', { name: /sign in/i }).click()
  await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 30000 })
}

;(async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
    await login(page)
    await page.goto(BASE + '/upload', { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle').catch(() => {})

    const notice = page.locator('[data-upload-privacy-notice]')
    log((await notice.count()) === 1, 'exactly one notice is rendered')
    log(await notice.isVisible(), 'notice is visible before file selection')
    log((await notice.innerText()).includes(EXACT_NOTICE), 'notice contains exact owner wording')

    const noteByRole = page.getByRole('note', { name: 'Before you upload' })
    log((await noteByRole.count()) === 1, 'notice exposes role=note with an accessible name')

    const dropzone = page.locator('[data-dropzone]')
    const noticeBox = await notice.boundingBox()
    const dropzoneBox = await dropzone.boundingBox()
    log(
      Boolean(noticeBox && dropzoneBox && noticeBox.y < dropzoneBox.y),
      'notice appears above the dropzone',
      `notice y=${noticeBox && Math.round(noticeBox.y)} dropzone y=${dropzoneBox && Math.round(dropzoneBox.y)}`,
    )

    const overflowDesktop = await page.evaluate(() => ({
      scrollW: document.documentElement.scrollWidth,
      clientW: document.documentElement.clientWidth,
    }))
    log(
      overflowDesktop.scrollW <= overflowDesktop.clientW + 1,
      'no horizontal overflow at 1440',
      `${overflowDesktop.scrollW}/${overflowDesktop.clientW}`,
    )

    await page.setViewportSize({ width: 390, height: 844 })
    await page.waitForTimeout(300)
    log(await notice.isVisible(), 'notice remains available at 390 width')
    const mobileBox = await notice.boundingBox()
    log(
      Boolean(mobileBox && mobileBox.x >= 0 && mobileBox.x + mobileBox.width <= 390 + 1),
      'notice fits the mobile viewport',
      mobileBox ? `x=${Math.round(mobileBox.x)} w=${Math.round(mobileBox.width)}` : 'no box',
    )
    const overflowMobile = await page.evaluate(() => ({
      scrollW: document.documentElement.scrollWidth,
      clientW: document.documentElement.clientWidth,
    }))
    log(
      overflowMobile.scrollW <= overflowMobile.clientW + 1,
      'no horizontal overflow at 390',
      `${overflowMobile.scrollW}/${overflowMobile.clientW}`,
    )

    await page.setViewportSize({ width: 1440, height: 900 })
    const input = page.locator('main input[type="file"]')
    log((await input.count()) === 1, 'scheme file input still present')
    log((await input.getAttribute('accept')) === '.docx,.pdf',
      'upload still accepts .docx and .pdf only')
    await input.setInputFiles(SAMPLE)
    await page.getByText(path.basename(SAMPLE), { exact: false }).first().waitFor({ timeout: 5000 })
    log(true, 'existing file selection still works after the notice')
    log(
      (await page.getByRole('button', { name: /choose different file/i }).count()) === 1,
      'teacher can still replace the selected file',
    )
  } catch (error) {
    log(false, 'browser run completed', error && error.message)
  } finally {
    await browser.close()
  }

  console.log(`\n${pass} passed, ${fail} failed`)
  process.exit(fail === 0 ? 0 : 1)
})()
