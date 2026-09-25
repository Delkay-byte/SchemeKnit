/**
 * Basic 1-3 weekly class-plan browser acceptance — the class-teacher
 * weekly-plan journey on the real app.
 *
 * Covers (phase brief §9, §13, §15, §19-§23, §26-§27, §35, items A-R):
 *  * nav: "Weekly Plan" header entry -> list page (one row per week)
 *  * builder: Basic 1 routing = class-teacher model; day pills; per-subject
 *    teaching days; shared "MONDAY & TUESDAY..." entry; optional WAPEF fields
 *  * boundary: Basic 4+ switches to the subject-teacher model — banner shown,
 *    preview/save disabled (the old Approved WAPEF Plan flow stays untouched)
 *  * preview: one weekly document, subject sections, day rows per subject,
 *    clean validation; shared entry collapses to one grouped day row
 *  * save -> review page: metadata + WAPEF + per-day starter/main/reflection
 *  * edit: Monday starter change persists after reload and never touches
 *    Tuesday (same subject) or the other subject (isolation)
 *  * export: DOCX downloads and carries the edit + WAPEF values + both
 *    subjects; PDF fails gracefully with an environment banner (no crash)
 *  * responsive overflow at 1440/1024/390; zero uncaught page errors
 *
 * Usage: node e2e/basic13-acceptance.js [baseUrl]
 */
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')
const { execSync } = require('child_process')

const BASE = process.argv[2] || 'http://localhost:3003'
const OUT = path.join(__dirname, 'basic13-acceptance')
fs.mkdirSync(OUT, { recursive: true })

const EMAIL = 'accept.teacher@schemeknit.test'
const PASSWORD = 'Accept#2026'
// Two known Basic 7 schemes of the acceptance teacher (the builder lists
// every uploaded scheme and badges class mismatches — asserted below).
const SCHEME_A = 'b28921de-1a7b-40af-879c-ebb358a598e2' // 5 weeks
const SCHEME_B = '3afea283-2820-4141-a1f3-4720270718cf' // 2 weeks
const EDITED_STARTER = 'E2E EDITED STARTER A MONDAY'

let pass = 0
let fail = 0
const results = []
const pageErrors = []

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
    `no horizontal overflow @ ${page.viewportSize().width}px: ${label}`,
    `${o.scrollW}/${o.clientW}`)
}

async function readDocxText(file) {
  const xml = execSync(
    `python -c "import zipfile,html;print(html.unescape(zipfile.ZipFile(r'${file}').read('word/document.xml').decode('utf-8')))"`,
    { maxBuffer: 64 * 1024 * 1024 }).toString('utf-8')
  return xml.replace(/<[^>]+>/g, '\n')
}

;(async () => {
  const browser = await chromium.launch({ headless: true })
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true })
  const page = await ctx.newPage()
  page.on('pageerror', (e) => pageErrors.push(e.message))

  try {
    // ══ Login ═════════════════════════════════════════════════════════════
    await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded', timeout: 45000 })
    await page.waitForLoadState('networkidle').catch(() => {})
    await page.getByText('Welcome back, teacher.').waitFor({ timeout: 15000 })
    await page.locator('input[type="email"]').fill(EMAIL)
    await page.locator('input[type="password"]').fill(PASSWORD)
    await page.getByRole('button', { name: 'Sign In' }).click()
    await page.waitForURL(/\/dashboard/, { timeout: 30000 })
    await page.waitForLoadState('networkidle').catch(() => {})
    log(true, 'teacher logged in')

    // ══ Nav entry ════════════════════════════════════════════════════════
    const navLink = page.locator('nav a[href="/weekly-plans/"]')
    await navLink.first().waitFor({ timeout: 30000 })
    log(await navLink.count() > 0, 'header nav shows "Weekly Plan"')
    await navLink.first().click()
    await page.waitForURL(/\/weekly-plans/, { timeout: 20000 })
    await page.waitForLoadState('networkidle').catch(() => {})
    log(/Weekly Class Plans/.test(await page.evaluate(() => document.body.innerText)),
      'list page renders "Weekly Class Plans"')
    await page.locator('[data-weekly-list], [data-empty]').first().waitFor({ timeout: 30000 })
    const listVisible = await page.locator('[data-weekly-list]').isVisible()
      || await page.locator('[data-empty]').isVisible()
    log(listVisible, 'list page shows table or empty state')
    await shot(page, '01-list-1440.png')
    await noOverflow(page, 'weekly plans list')

    // ══ Builder ══════════════════════════════════════════════════════════
    await page.getByRole('link', { name: /new weekly plan/i }).first().click()
    await page.waitForURL(/\/weekly-plans\/new/, { timeout: 20000 })
    await page.waitForLoadState('networkidle').catch(() => {})
    await page.locator('[data-weekly-schemes]').waitFor({ timeout: 20000 })
    await page.waitForFunction(() => {
      const el = document.querySelector('[data-weekly-model]')
      return !!el && /Class-teacher model|Subject-teacher model/.test(el.textContent || '')
    }, { timeout: 30000 })
    log((await page.locator('[data-weekly-model]').innerText()).includes('Class-teacher model'),
      'Basic 1 routes to the class-teacher model')

    // Boundary: Basic 4+ is the subject-teacher model — banner + disabled.
    await page.locator('#weekly-class-level').selectOption('Basic 4')
    await page.locator('[data-weekly-boundary]').waitFor({ timeout: 20000 })
    const boundaryText = await page.locator('[data-weekly-boundary]').innerText()
    log(/subject-teacher|Approved WAPEF Plan/i.test(boundaryText),
      'Basic 4 shows the subject-teacher boundary banner', boundaryText.split('\n')[0])
    log(await page.locator('[data-weekly-model]').innerText().then(t => t.includes('Subject-teacher')),
      'Basic 4 model text = subject-teacher (weekly plan not available)')
    log(await page.locator('[data-weekly-preview-button]').isDisabled(),
      'preview disabled for Basic 4')
    await shot(page, '02-boundary-basic4.png')
    await page.locator('#weekly-class-level').selectOption('Basic 1')
    await page.locator('[data-weekly-boundary]').waitFor({ state: 'hidden', timeout: 20000 })
    await page.waitForFunction(() => {
      const el = document.querySelector('[data-weekly-model]')
      return !!el && /Class-teacher model/.test(el.textContent || '')
    }, { timeout: 30000 })
    log((await page.locator('[data-weekly-model]').innerText()).includes('Class-teacher'),
      'back to Basic 1 -> class-teacher model again')

    // Select two schemes (class mismatch badged, never hidden).
    await page.locator(`li[data-weekly-scheme="${SCHEME_A}"] input[type="checkbox"]`).check()
    await page.locator(`li[data-weekly-scheme="${SCHEME_B}"] input[type="checkbox"]`).check()
    log(await page.locator('[data-weekly-subject-days]').count() === 2,
      'both schemes open their teaching-day panels')
    const schemeCardText = await page.locator(`li[data-weekly-scheme="${SCHEME_A}"]`).innerText()
    log(/Different class \(Basic 7\)/.test(schemeCardText),
      'class mismatch is badged (Basic 7 scheme under Basic 1)')

    // Subject A: drop Wednesday (4 days), WAPEF selections, shared entry ON.
    const pillWedsA = page.locator(`li[data-weekly-scheme="${SCHEME_A}"] button[aria-pressed]`, { hasText: 'Wednesday' })
    await pillWedsA.click()
    log((await pillWedsA.getAttribute('aria-pressed')) === 'false', 'Wednesday deselected for subject A')

    await page.locator(`#weekly-deep-hope-${SCHEME_A}`).selectOption({ index: 1 })
    await page.locator(`#weekly-storyline-${SCHEME_A}`).selectOption({ index: 1 })
    await page.locator(`#weekly-gods-story-${SCHEME_A}`).selectOption({ index: 1 })
    const chipsA = page.locator(`li[data-weekly-scheme="${SCHEME_A}"] [data-weekly-subject-days] button:not([aria-pressed])`)
    const chipCount = Math.min(await chipsA.count(), 2)
    for (let c = 0; c < chipCount; c++) await chipsA.nth(c).click()
    const deepHopeLabel = await page.locator(`#weekly-deep-hope-${SCHEME_A} option:checked`).innerText()
    log(!!deepHopeLabel && deepHopeLabel !== '— Select —', 'WAPEF Deep Hope selected', deepHopeLabel.slice(0, 40))

    await page.locator(`li[data-weekly-scheme="${SCHEME_A}"] label:has-text("One shared entry") input`).check()
    log(true, 'shared-entry toggle ON for subject A')

    // Preview with the shared entry: A = one grouped day row, B = five rows.
    await page.locator('[data-weekly-preview-button]').click()
    await page.locator('[data-weekly-preview]').waitFor({ timeout: 90000 })
    const previewA = page.locator('[data-weekly-preview-subject]').nth(0)
    const previewB = page.locator('[data-weekly-preview-subject]').nth(1)
    const aText = await previewA.innerText()
    log(/MONDAY & TUESDAY & THURSDAY & FRIDAY/.test(aText),
      'shared entry renders one grouped day label', aText.split('\n')[1] || '')
    log(await previewA.locator('li').count() === 1, 'shared entry = 1 day row for subject A')
    log(await previewB.locator('li').count() === 5, 'subject B keeps 5 individual day rows')
    await shot(page, '03-preview-shared.png')

    // Turn shared OFF again: A = 4 day rows (no Wednesday), B = 5.
    await page.locator(`li[data-weekly-scheme="${SCHEME_A}"] label:has-text("One shared entry") input`).uncheck()
    await page.locator('[data-weekly-preview]').waitFor({ state: 'hidden', timeout: 20000 })
    await page.locator('[data-weekly-preview-button]').click()
    await page.locator('[data-weekly-preview]').waitFor({ timeout: 90000 })
    log(await previewA.locator('li').count() === 4, 'per-day mode: subject A = 4 day rows (no Wednesday)')
    const aText2 = await previewA.innerText()
    log(!/WEDNESDAY/i.test(aText2), 'subject A preview has no Wednesday row')
    log(await previewB.locator('li').count() === 5, 'subject B unaffected: still 5 day rows')
    const issues = await page.locator('[data-weekly-preview-summary]').innerText()
    log(/Ready to save/.test(issues), 'preview validates clean', issues.split('\n')[0])
    await shot(page, '04-preview-perday.png')
    await noOverflow(page, 'builder preview')

    // ══ Save -> review ════════════════════════════════════════════════════
    await page.locator('[data-weekly-save]').click()
    await page.waitForURL(/\/weekly-plans\/[0-9a-f-]{36}/, { timeout: 90000 })
    const planUrl = page.url()
    const planId = planUrl.split('/weekly-plans/')[1]
    await page.waitForLoadState('networkidle').catch(() => {})
    await page.locator('[data-weekly-subject]').first().waitFor({ timeout: 30000 })
    log(/Basic 1 · Week 1/.test(await page.evaluate(() => document.body.innerText)),
      'review header shows Basic 1 · Week 1 (request class)')
    log(await page.locator('[data-weekly-subject]').count() === 2, 'review shows both subject sections')

    const subjA = page.locator('[data-weekly-subject]').nth(0)
    const subjB = page.locator('[data-weekly-subject]').nth(1)
    log(await subjA.locator('[data-weekly-day]').count() === 4, 'subject A review = 4 day cards')
    log(await subjB.locator('[data-weekly-day]').count() === 5, 'subject B review = 5 day cards')
    log(!/WEDNESDAY/i.test(await subjA.innerText()), 'subject A review has no Wednesday card')
    log(await subjB.innerText().then(t => /WEDNESDAY/.test(t)), 'subject B review keeps Wednesday card')
    log(await page.locator('[data-weekly-wapef]').first().isVisible(), 'WAPEF fields visible on review')
    await shot(page, '05-review-1440.png')
    await noOverflow(page, 'review page')

    // ══ Edit Monday starter + isolation ═══════════════════════════════════
    const starterB0 = await page.locator(`#weekly-starter-1-0`).inputValue()
    const starterA1 = await page.locator(`#weekly-starter-0-1`).inputValue()
    await page.locator('#weekly-starter-0-0').fill(EDITED_STARTER)
    log(await page.locator('[data-weekly-save]:not([disabled])').count() === 1,
      'save enables when a day starter changes')
    await page.locator('[data-weekly-save]').click()
    await page.getByText('Changes saved', { exact: true }).waitFor({ timeout: 30000 })
    log(true, 'edit saved (toast "Changes saved")')
    log((await page.locator('#weekly-starter-0-1').inputValue()) === starterA1,
      'isolation: Tuesday starter of subject A unchanged')
    log((await page.locator('#weekly-starter-1-0').inputValue()) === starterB0,
      'isolation: Monday starter of subject B unchanged')

    // Reload -> persistence.
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle').catch(() => {})
    await page.locator('#weekly-starter-0-0').waitFor({ timeout: 30000 })
    log((await page.locator('#weekly-starter-0-0').inputValue()) === EDITED_STARTER,
      'edited starter persists after reload')
    await shot(page, '06-review-edited.png')

    // ══ DOCX export ═══════════════════════════════════════════════════════
    const [dl] = await Promise.all([
      page.waitForEvent('download', { timeout: 120000 }).catch(() => null),
      page.locator('[data-weekly-export-docx]').first().click(),
    ])
    if (dl) {
      const f = path.join(OUT, 'exported-weekly.docx')
      await dl.saveAs(f)
      log(true, 'DOCX downloads', dl.suggestedFilename())
      const plain = await readDocxText(f)
      log(plain.includes(EDITED_STARTER), 'DOCX carries the edited Monday starter')
      log(plain.includes(starterA1), 'DOCX carries the untouched Tuesday starter')
      log(plain.includes(starterB0), 'DOCX carries subject B Monday starter (cross-subject)')
      log(plain.includes(deepHopeLabel), 'DOCX carries the WAPEF Deep Hope selection')
      log(/DAYS/.test(plain) && /PHASE 1[\s\S]*PHASE 2[\s\S]*PHASE 3/.test(plain),
        'DOCX keeps DAYS + PHASE 1/2/3 structure')
      log((plain.match(/Science/g) || []).length >= 2, 'DOCX holds both subject sections')
      log(!/\{\{[A-Z_0-9]+\}\}/.test(plain) && !/\[object Object\]/.test(plain),
        'DOCX has no leftover template tokens')
    } else {
      log(false, 'DOCX download event fired')
    }

    // ══ PDF export (environment limitation -> graceful banner) ════════════
    const dlWatcher = page.waitForEvent('download', { timeout: 15000 }).catch(() => null)
    await page.locator('[data-weekly-export-pdf]').first().click()
    await page.locator('[data-weekly-export-error]').waitFor({ timeout: 60000 })
    const pdfErr = await page.locator('[data-weekly-export-error]').innerText()
    const pdfDl = await dlWatcher
    log(!pdfDl, 'PDF export: no download event (LibreOffice missing here)')
    log(/LibreOffice|unavailable/i.test(pdfErr), 'PDF export fails with an explanatory banner', pdfErr.split('\n').pop())
    await shot(page, '07-pdf-graceful-error.png')

    // ══ Back to list: the saved week shows as one row ═════════════════════
    await page.getByRole('link', { name: /all weekly plans/i }).click()
    await page.waitForURL(/\/weekly-plans\/?$/, { timeout: 20000 })
    await page.waitForLoadState('networkidle').catch(() => {})
    const rows = page.locator('[data-weekly-list] tbody tr')
    await rows.first().waitFor({ timeout: 20000 })
    const rowCount = await rows.count()
    log(rowCount >= 2, 'list now shows the saved week as a row', `${rowCount} row(s)`)
    const firstRow = await rows.first().innerText()
    log(/Basic 1/.test(firstRow) && /Science/.test(firstRow),
      'list row shows class + subjects', firstRow.replace(/\n/g, ' | ').slice(0, 80))
    await shot(page, '08-list-with-plan.png')

    // ══ Responsive ════════════════════════════════════════════════════════
    for (const [w, h, name] of [[1024, 768, '1024'], [390, 844, '390']]) {
      await page.setViewportSize({ width: w, height: h })
      await page.waitForTimeout(500)
      await noOverflow(page, 'list')
      await shot(page, `09-list-${name}.png`)

      await page.goto(planUrl, { waitUntil: 'domcontentloaded' })
      await page.waitForLoadState('networkidle').catch(() => {})
      await page.locator('[data-weekly-subject]').first().waitFor({ timeout: 30000 })
      await page.waitForTimeout(400)
      await noOverflow(page, `review @ ${name}`)
      await shot(page, `10-review-${name}.png`)

      await page.goto(BASE + '/weekly-plans/new/', { waitUntil: 'domcontentloaded' })
      await page.waitForLoadState('networkidle').catch(() => {})
      await page.locator('[data-weekly-schemes]').waitFor({ timeout: 30000 })
      await page.waitForTimeout(400)
      await noOverflow(page, `builder @ ${name}`)
      await shot(page, `11-builder-${name}.png`)
    }

    log(pageErrors.length === 0, 'zero uncaught page errors', pageErrors.slice(0, 3).join(' | '))
  } catch (e) {
    log(false, 'script completed', e.message)
    await shot(page, '99-failure.png').catch(() => {})
  } finally {
    fs.writeFileSync(path.join(OUT, 'results.txt'), results.join('\n') + '\n')
    console.log(`\n${pass} passed, ${fail} failed — screenshots in e2e/basic13-acceptance/`)
    await browser.close()
    process.exit(fail === 0 ? 0 : 1)
  }
})()
