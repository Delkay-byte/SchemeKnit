/**
 * KG browser acceptance — the KG-specific journey on the real app.
 *
 * Covers: real KG2 DOCX scheme (whole-level, subject confirmation) and the
 * real KG1 PDF scheme; the play-based generated content on the review rows;
 * WAPEF field persistence; DOCX + PDF export downloads; responsive overflow.
 * Screenshots inspected; zero page errors expected.
 *
 * Usage: node e2e/kg-acceptance.js [baseUrl]
 */
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')
const { execSync } = require('child_process')

const BASE = process.argv[2] || 'http://localhost:3000'
const ROOT = path.join(__dirname, '..', '..')
const KG2 = path.join(ROOT, 'backend', 'tests', 'fixtures', 'wapef', 'WAPEF SCHEME OF LEARNING FOR KG.docx')
const KG1 = path.join(ROOT, 'backend', 'tests', 'fixtures', 'wapef', 'KG 1 Scheme.pdf')
const OUT = path.join(__dirname, 'kg-acceptance')
fs.mkdirSync(OUT, { recursive: true })

const STAMP = Date.now()
const PASSWORD = 'KgAcc#2026'
// One teacher per leg: the Free Tier quota is 5 lesson plans per calendar
// month, and the KG2 indicator-based allocation can legitimately consume all
// five within a short term window (carry-forward fills later weeks). A second
// fresh teacher gives the KG1 leg its own full allowance.
const EMAIL2 = `kg.acc2.${STAMP}@schemeknit.test`
const DEEP_HOPE = 'Learners will recognize and appreciate the beauty, order, and purpose of design in the physical world around them.'
const STORYLINE = 'Shaping our world.'

let pass = 0
let fail = 0
const results = []

function log(ok, label, detail) {
  if (ok) pass++
  else fail++
  results.push(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? ' — ' + detail : ''}`)
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? ' — ' + detail : ''}`)
}

async function shot(page, name) {
  await page.screenshot({ path: path.join(OUT, name), fullPage: false })
}

async function noOverflow(page, label) {
  const o = await page.evaluate(() => ({
    scrollW: document.documentElement.scrollWidth,
    clientW: document.documentElement.clientWidth,
  }))
  log(o.scrollW <= o.clientW + 1,
    `no horizontal overflow @ ${page.viewportSize().width}x${page.viewportSize().height}: ${label}`,
    `${o.scrollW}/${o.clientW}`)
}

async function signup(page, email) {
  await page.goto(BASE + '/signup', { waitUntil: 'domcontentloaded', timeout: 45000 })
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.locator('#signup-name').fill('KG Acceptance Teacher')
  await page.locator('#signup-email').fill(email)
  await page.locator('#signup-password').fill(PASSWORD)
  await page.locator('#signup-confirm').fill(PASSWORD)
  await page.getByRole('button', { name: /create account/i }).click()
  await page.waitForURL((u) => !u.pathname.startsWith('/signup'), { timeout: 30000 })
  await page.waitForLoadState('networkidle').catch(() => {})
}

async function uploadFile(page, filePath) {
  await page.goto(BASE + '/upload', { waitUntil: 'domcontentloaded', timeout: 45000 })
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.locator('input[type="file"]').setInputFiles(filePath)
  await page.getByRole('button', { name: /upload & process/i }).click()
  const success = page.locator('[data-upload-success]')
  const picker = page.locator('[data-multi-subject]')
  await Promise.race([
    success.waitFor({ timeout: 90000 }),
    picker.waitFor({ timeout: 90000 }),
  ])
  return { needsConfirm: !(await success.isVisible().catch(() => false)) }
}

async function confirmSubject(page, subjectLabel) {
  const picker = page.locator('[data-multi-subject]')
  const buttons = picker.getByRole('button')
  if (await buttons.count()) {
    await buttons.first().click()
  } else {
    await page.locator('#confirm-fallback-subject').selectOption({ label: subjectLabel })
  }
  await page.waitForURL(/\/review\//, { timeout: 60000 })
  await page.waitForLoadState('networkidle').catch(() => {})
}

async function approveAndOpenGenerate(page) {
  await page.getByRole('button', { name: /approve & configure/i }).last().click()
  await page.waitForURL(/\/generate\//, { timeout: 30000 })
  await page.waitForLoadState('networkidle').catch(() => {})
}

async function selectWapefTemplate(page) {
  const sel = page.locator('#cfg-template')
  await sel.waitFor({ timeout: 30000 })
  await page.waitForFunction(() => {
    const el = document.querySelector('#cfg-template')
    return el && el.options.length >= 2
  }, { timeout: 30000 }).catch(() => {})
  await sel.selectOption({ label: 'Approved WAPEF Plan' })
}

async function previewAllocation(page, { lessonsPerWeek = '1' } = {}) {
  await page.locator('#cfg-term-start').fill('2026-09-14')
  await page.locator('#cfg-term-end').fill('2026-09-25')
  await page.locator('#cfg-lessons-per-week').fill(lessonsPerWeek)
  await page.getByRole('button', { name: /preview allocation/i }).click()
  await page.locator('[data-lesson-review]').waitFor({ timeout: 60000 })
  await page.locator('select[id^="wapef-deep-hope-"]').first().waitFor({ timeout: 15000 })
}

async function setWapefFields(page) {
  const deepHopes = page.locator('select[id^="wapef-deep-hope-"]')
  const n = await deepHopes.count()
  for (let i = 0; i < n; i++) {
    await deepHopes.nth(i).selectOption({ label: DEEP_HOPE })
    await page.locator('select[id^="wapef-storyline-"]').nth(i).selectOption({ label: STORYLINE })
    await page.locator('select[id^="wapef-gods-story-"]').nth(i).selectOption({ label: 'Creation' })
    const rowScope = deepHopes.nth(i)
      .locator('xpath=ancestor::div[contains(@class,"rounded-md border")]')
    const chips = rowScope.locator('button[type="button"]')
    const chipCount = Math.min(await chips.count(), 2)
    for (let c = 0; c < chipCount; c++) await chips.nth(c).click()
  }
  return n
}

async function generate(page) {
  await page.getByRole('button', { name: /confirm & generate/i }).click()
  await page.waitForTimeout(6000)
  await page.waitForLoadState('networkidle').catch(() => {})
}

;(async () => {
  const browser = await chromium.launch({ headless: true })
  const pageErrors = []
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true })
  const page = await ctx.newPage()
  page.on('pageerror', (e) => pageErrors.push(e.message))

  try {
    await signup(page, `kg.acc.${STAMP}@schemeknit.test`)
    log(true, 'fresh teacher account created (KG2 leg)')

    // ══ A. KG2 DOCX journey: class + play-based content ═════════════════
    const kg2 = await uploadFile(page, KG2)
    log(kg2.needsConfirm, 'KG2 scheme: whole-level subject confirmation shown')
    await shot(page, '01-kg2-confirm.png')

    await confirmSubject(page, 'Numeracy')
    await page.waitForTimeout(1500)
    const reviewClass = await page.evaluate(() => document.body.innerText)
    log(/KG 2/.test(reviewClass), 'review screen shows detected class KG 2')
    log(/Numeracy/.test(reviewClass), 'review screen shows confirmed subject Numeracy')
    await shot(page, '02-kg2-review.png')
    await noOverflow(page, 'kg2 review')

    // The parsed weeks must show source strand/sub-strand and indicator codes
    const reviewText = await page.evaluate(() => document.body.innerText)
    log(/All About Me/.test(reviewText), 'KG2 review shows source strand "All About Me"')
    log(/K2\.1\.1\.1\.1/.test(reviewText), 'KG2 review shows the source indicator code')

    await approveAndOpenGenerate(page)
    await selectWapefTemplate(page)
    await previewAllocation(page)
    const rows = await setWapefFields(page)
    log(rows > 0, 'WAPEF teacher selections set on KG lesson rows', `${rows} row(s)`)
    await shot(page, '03-kg2-wapef-fields.png')
    await noOverflow(page, 'kg2 WAPEF fields')

    // The generated-content seed visible in the review rows must be
    // play-based, not board-worked (deterministic content is built at
    // generate time; here we assert the control flow and then inspect the
    // exported document which carries the generated activities).
    await generate(page)
    await shot(page, '04-kg2-after-generate.png')
    await noOverflow(page, 'kg2 post-generate')

    // DOCX export with verification of KG curriculum + play-based content
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle').catch(() => {})
    await page.waitForTimeout(1500)
    const docxBtn = page.getByRole('button', { name: /docx/i }).first()
    if (await docxBtn.count()) {
      const [dl] = await Promise.all([
        page.waitForEvent('download', { timeout: 90000 }).catch(() => null),
        docxBtn.click(),
      ])
      if (dl) {
        const f = path.join(OUT, 'exported-kg2.docx')
        await dl.saveAs(f)
        log(true, 'KG2 DOCX downloads', dl.suggestedFilename())
        const xml = execSync(
          `python -c "import zipfile;print(zipfile.ZipFile(r'${f}').read('word/document.xml').decode('utf-8'))"`,
          { maxBuffer: 64 * 1024 * 1024 }).toString('utf-8')
        const plain = xml.replace(/<[^>]+>/g, '\n')
        log(/KG 2/.test(plain), 'KG2 DOCX carries class KG 2')
        log(/All About Me/.test(plain), 'KG2 DOCX carries source strand')
        log(/K2\.1\.1\.1\.1/.test(plain), 'KG2 DOCX carries the source indicator')
        log(/K2\.1\.1\.1(?!\.)/.test(plain), 'KG2 DOCX carries the content-standard code')
        log(/Poster\/ cut out/.test(plain), 'KG2 DOCX preserves source resources')
        log(plain.includes(DEEP_HOPE), 'KG2 DOCX carries Deep Hope verbatim')
        log(/song|rhyme|play/i.test(plain), 'KG2 DOCX activities are play-based', 'song/rhyme/play found')
        log(!/on the board/i.test(plain), 'KG2 DOCX has no board-worked exercise content')
        log(/PHASE 1[\s\S]*PHASE 2[\s\S]*PHASE 3/.test(plain), 'KG2 DOCX keeps the three-phase structure')
      } else {
        log(false, 'KG2 DOCX download event fired')
      }
    }

    // PDF export
    const pdfBtn = page.getByRole('button', { name: /pdf/i }).first()
    if (await pdfBtn.count()) {
      const [dl2] = await Promise.all([
        page.waitForEvent('download', { timeout: 120000 }).catch(() => null),
        pdfBtn.click(),
      ])
      if (dl2) {
        const f2 = path.join(OUT, 'exported-kg2.pdf')
        await dl2.saveAs(f2)
        const sig = fs.readFileSync(f2).subarray(0, 5).toString()
        log(sig === '%PDF-', 'KG2 PDF export downloads with a real PDF signature', `${fs.statSync(f2).size} bytes`)
      } else {
        log(false, 'KG2 PDF download event fired')
      }
    }

    // ══ B. KG1 PDF journey: fresh teacher (own quota) + class detection ══
    // Sign out by logging in as the second fresh teacher via signup.
    await page.goto(BASE + '/settings', { waitUntil: 'domcontentloaded' }).catch(() => {})
    await page.evaluate(() => { try { localStorage.clear(); sessionStorage.clear() } catch {} })
    const ctx2 = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true })
    const page2 = await ctx2.newPage()
    page2.on('pageerror', (e) => pageErrors.push(e.message))
    // Replace the active page with the new context's page for the KG1 leg.
    await page2.goto(BASE + '/signup', { waitUntil: 'domcontentloaded', timeout: 45000 })
    await signup(page2, EMAIL2)
    log(true, 'second fresh teacher created (KG1 leg)', EMAIL2)
    const activePage = page2

    const kg1 = await uploadFile(activePage, KG1)
    log(kg1.needsConfirm, 'KG1 PDF scheme: subject confirmation shown')
    await shot(activePage, '05-kg1-confirm.png')
    // Class-level detection itself is asserted on the review screen below
    // (the confirmation card shows the document title, not the class).

    await confirmSubject(activePage, 'Numeracy')
    await activePage.waitForTimeout(1500)
    await shot(activePage, '06-kg1-review.png')
    await noOverflow(activePage, 'kg1 review')
    const kg1Review = await activePage.evaluate(() => document.body.innerText)
    log(/KG 1/.test(kg1Review), 'KG1 review screen shows class KG 1')
    log(/K1\.1\.1\.1\.1/.test(kg1Review), 'KG1 review shows its own indicator codes (merged-header fix)')

    await approveAndOpenGenerate(activePage)
    await selectWapefTemplate(activePage)
    await previewAllocation(activePage)
    const kg1Rows = await setWapefFields(activePage)
    log(kg1Rows > 0, 'KG1 WAPEF teacher selections set', `${kg1Rows} row(s)`)
    await shot(activePage, '07-kg1-wapef-fields.png')
    await generate(activePage)
    await shot(activePage, '08-kg1-after-generate.png')
    await noOverflow(activePage, 'kg1 post-generate')

    // ══ C. Responsive ════════════════════════════════════════════════════
    await activePage.setViewportSize({ width: 1024, height: 768 })
    await activePage.waitForTimeout(500)
    await noOverflow(activePage, 'kg generate (tablet)')
    await shot(activePage, '09-responsive-1024.png')
    await activePage.setViewportSize({ width: 390, height: 844 })
    await activePage.waitForTimeout(500)
    await noOverflow(activePage, 'kg generate (phone)')
    await shot(activePage, '10-responsive-390.png')
    await ctx2.close()

    log(pageErrors.length === 0, 'zero uncaught page errors', pageErrors.slice(0, 3).join(' | '))
  } catch (e) {
    log(false, 'script completed', e.message)
    await shot(page, '99-failure.png').catch(() => {})
  } finally {
    fs.writeFileSync(path.join(OUT, 'results.txt'), results.join('\n') + '\n')
    console.log(`\n${pass} passed, ${fail} failed — screenshots in e2e/kg-acceptance/`)
    await browser.close()
    process.exit(fail === 0 ? 0 : 1)
  }
})()
