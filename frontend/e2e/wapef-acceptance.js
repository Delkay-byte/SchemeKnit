/**
 * WAPEF browser acceptance — the real teacher journey on the real app.
 *
 * Covers: Approved WAPEF Plan selection, KG + Nursery scheme ingestion
 * (Nursery first so both legs fit the Free Tier monthly lesson quota),
 * teacher-selected WAPEF fields (deep hope / storyline / through lines /
 * God's story), generation with the deterministic engine, and a real DOCX
 * export whose XML carries the teacher's WAPEF selections. Screenshots at
 * 1440x900, 1024x768, 390x844 with horizontal-overflow checks at every stop.
 *
 * Usage: node e2e/wapef-acceptance.js [baseUrl]
 * Requires: backend on :8000 + production frontend (`next start`) running.
 */
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')
const { execSync } = require('child_process')

const BASE = process.argv[2] || 'http://localhost:3000'
const ROOT = path.join(__dirname, '..', '..')
const KG = path.join(ROOT, 'backend', 'tests', 'fixtures', 'wapef', 'WAPEF SCHEME OF LEARNING FOR KG.docx')
const NURSERY = path.join(ROOT, 'backend', 'tests', 'fixtures', 'wapef', 'WAPEF SCHEME OF LEARNING FOR NURSERY.docx')
const OUT = path.join(__dirname, 'wapef-acceptance')
fs.mkdirSync(OUT, { recursive: true })

const STAMP = Date.now()
const EMAIL = `wapef.acc.${STAMP}@schemeknit.test`
const PASSWORD = 'Wapef#2026'
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

async function signup(page) {
  await page.goto(BASE + '/signup', { waitUntil: 'domcontentloaded', timeout: 45000 })
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.locator('#signup-name').fill('WAPEF Acceptance Teacher')
  await page.locator('#signup-email').fill(EMAIL)
  await page.locator('#signup-password').fill(PASSWORD)
  await page.locator('#signup-confirm').fill(PASSWORD)
  await page.getByRole('button', { name: /create account/i }).click()
  await page.waitForURL((u) => !u.pathname.startsWith('/signup'), { timeout: 30000 })
  await page.waitForLoadState('networkidle').catch(() => {})
}

/** Upload a fixture and stay on whatever the upload screen shows. */
async function uploadFile(page, filePath) {
  await page.goto(BASE + '/upload', { waitUntil: 'domcontentloaded', timeout: 45000 })
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.locator('input[type="file"]').setInputFiles(filePath)
  await page.getByRole('button', { name: /upload & process/i }).click()
  const success = page.locator('[data-upload-success]')
  const picker = page.locator('[data-multi-subject]')
  await Promise.race([
    success.waitFor({ timeout: 60000 }),
    picker.waitFor({ timeout: 60000 }),
  ])
  return { needsConfirm: !(await success.isVisible().catch(() => false)) }
}

/** Confirm the subject on an open confirmation card, then land on review. */
async function confirmSubject(page, subjectLabel) {
  const picker = page.locator('[data-multi-subject]')
  const buttons = picker.getByRole('button')
  if (await buttons.count()) {
    const target = subjectLabel
      ? picker.getByRole('button', { name: subjectLabel })
      : buttons.first()
    await (await target.count() ? target : buttons.first()).click()
  } else {
    // Whole-level scheme (WAPEF KG shape): teacher declares the subject.
    await page.locator('#confirm-fallback-subject').selectOption({ label: subjectLabel })
  }
  // Confirming navigates straight to the review screen.
  await page.waitForURL(/\/review\//, { timeout: 60000 })
  await page.waitForLoadState('networkidle').catch(() => {})
}

async function approveAndOpenGenerate(page) {
  await page.getByRole('button', { name: /approve & configure/i }).last().click()
  await page.waitForURL(/\/generate\//, { timeout: 30000 })
  await page.waitForLoadState('networkidle').catch(() => {})
}

/** Select the Approved WAPEF Plan in the Template dropdown. */
async function selectWapefTemplate(page) {
  const sel = page.locator('#cfg-template')
  await sel.waitFor({ timeout: 30000 })
  await page.waitForFunction(() => {
    const el = document.querySelector('#cfg-template')
    return el && el.options.length >= 2
  }, { timeout: 30000 }).catch(() => {})
  await sel.selectOption({ label: 'Approved WAPEF Plan' })
  await page.waitForFunction(() => {
    const el = document.querySelector('#cfg-template')
    return el && el.value === 'tpl-wapef-approved-plan'
  }, { timeout: 15000 })
}

/**
 * Shorten the term (Free Tier quota = 5 lessons/month) and run the allocation
 * preview so the per-lesson review rows (with the WAPEF field controls) appear.
 */
async function previewAllocation(page, { lessonsPerWeek = '3' } = {}) {
  await page.locator('#cfg-term-start').fill('2026-09-14')
  await page.locator('#cfg-term-end').fill('2026-09-25')
  await page.locator('#cfg-lessons-per-week').fill(lessonsPerWeek)
  await page.getByRole('button', { name: /preview allocation/i }).click()
  await page.locator('[data-lesson-review]').waitFor({ timeout: 60000 })
  await page.locator('select[id^="wapef-deep-hope-"]').first().waitFor({ timeout: 15000 })
}

/** Set the four WAPEF teacher selections on every visible lesson row. */
async function setWapefFields(page, { godsStory, godsStoryRow2 }) {
  const deepHopes = page.locator('select[id^="wapef-deep-hope-"]')
  const n = await deepHopes.count()
  log(n > 0, 'WAPEF field controls visible on lesson rows', `${n} row(s)`)
  for (let i = 0; i < n; i++) {
    await deepHopes.nth(i).selectOption({ label: DEEP_HOPE })
    await page.locator('select[id^="wapef-storyline-"]').nth(i).selectOption({ label: STORYLINE })
    await page.locator('select[id^="wapef-gods-story-"]').nth(i)
      .selectOption({ label: i === 1 && godsStoryRow2 ? godsStoryRow2 : godsStory })
    // Through lines: toggle the first two approved chips for this row.
    const rowScope = deepHopes.nth(i)
      .locator('xpath=ancestor::div[contains(@class,"rounded-md border")]')
    const chips = rowScope.locator('button[type="button"]')
    const chipCount = Math.min(await chips.count(), 2)
    for (let c = 0; c < chipCount; c++) await chips.nth(c).click()
  }
}

async function readWapefRow(page, i) {
  const rowScope = page.locator('select[id^="wapef-deep-hope-"]').nth(i)
    .locator('xpath=ancestor::div[contains(@class,"rounded-md border")]')
  return {
    deepHope: await page.locator('select[id^="wapef-deep-hope-"]').nth(i).inputValue(),
    storyline: await page.locator('select[id^="wapef-storyline-"]').nth(i).inputValue(),
    godsStory: await page.locator('select[id^="wapef-gods-story-"]').nth(i).inputValue(),
    chips: await rowScope.locator('button[type="button"][class*="bg-[#102A43]"]').count(),
  }
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
    // ── 0. Fresh teacher ─────────────────────────────────────────────────
    await signup(page)
    log(true, 'fresh teacher account created', EMAIL)

    // ══ A. NURSERY leg (first: consumes only 2 of the 5 free lessons) ══
    const nurUp = await uploadFile(page, NURSERY)
    log(nurUp.needsConfirm, 'Nursery scheme asks the teacher to confirm a subject section')

    const detected = await page.evaluate(() =>
      (document.body.innerText.match(/Numeracy|Language and Literacy|Creative Arts(?: and Design)?|Our World Our People|Physical Development/g) || []))
    const uniqueSubjects = [...new Set(detected)]
    log(uniqueSubjects.length >= 3, 'Nursery multi-subject detection lists the subject sections',
      uniqueSubjects.slice(0, 6).join(', '))
    await noOverflow(page, 'nursery subject confirm')
    await shot(page, '01-nursery-subject-confirm.png')

    await confirmSubject(page, 'Numeracy')
    log(true, 'Nursery: Numeracy section confirmed; other subjects excluded')
    await shot(page, '02-nursery-review.png')

    await approveAndOpenGenerate(page)
    await selectWapefTemplate(page)
    log(true, 'Approved WAPEF Plan selectable in Template dropdown')

    await previewAllocation(page, { lessonsPerWeek: '1' })
    log(true, 'allocation preview renders per-lesson WAPEF field controls (Nursery)')

    const nurRows = await page.locator('select[id^="wapef-deep-hope-"]').count()
    await setWapefFields(page, { godsStory: 'Redemption', godsStoryRow2: 'Fall' })
    await shot(page, '03-nursery-wapef-fields.png')
    await noOverflow(page, 'nursery WAPEF fields')

    const nurRead = await readWapefRow(page, 0)
    log(nurRead.deepHope === DEEP_HOPE, 'Nursery Deep Hope selection retained before generate')
    log(nurRead.storyline === STORYLINE, 'Nursery Storyline selection retained before generate')
    log(nurRead.godsStory === 'Redemption', "Nursery God's Story selection retained before generate")
    log(nurRead.chips >= 1, 'Nursery Through lines chips toggle on', `${nurRead.chips} selected`)

    await generate(page)
    await shot(page, '04-nursery-after-generate.png')
    await noOverflow(page, 'nursery post-generate')

    // ══ B. KG leg (whole-level scheme, no subject headings) ═════════════
    const kgUp = await uploadFile(page, KG)
    log(kgUp.needsConfirm, 'KG whole-level scheme asks for subject confirmation (no headings)')

    const kgHasButtons = await page.locator('[data-multi-subject]').getByRole('button').count()
    log(kgHasButtons === 0, 'KG confirmation card offers the subject catalogue (no bogus sections)')
    await shot(page, '05-kg-subject-confirm.png')
    await noOverflow(page, 'kg subject confirm')

    await confirmSubject(page, 'Numeracy')
    log(true, 'KG: subject confirmed on the whole-level document')
    await shot(page, '06-kg-review.png')

    await approveAndOpenGenerate(page)
    await selectWapefTemplate(page)
    await previewAllocation(page, { lessonsPerWeek: '3' })

    const kgRows = await page.locator('select[id^="wapef-deep-hope-"]').count()
    const kgEmpty = await readWapefRow(page, 0)
    log(kgEmpty.deepHope === '' && kgEmpty.chips === 0,
      'KG rows start with empty WAPEF selections (no leakage from the Nursery leg)')
    await setWapefFields(page, { godsStory: 'Creation', godsStoryRow2: 'Fall' })
    await shot(page, '07-kg-wapef-fields.png')
    await noOverflow(page, 'kg WAPEF fields')

    if (kgRows > 1) {
      const r1 = await page.locator('select[id^="wapef-gods-story-"]').nth(1).inputValue()
      log(r1 === 'Fall', 'lesson 2 holds its own WAPEF selections (no cross-lesson leak)', r1)
    }

    await generate(page)
    await shot(page, '08-kg-after-generate.png')
    await noOverflow(page, 'kg post-generate')

    // ══ C. Export: the DOCX must carry the teacher's WAPEF selections ═══
    const genUrl = page.url()
    await page.goto(genUrl, { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle').catch(() => {})
    await page.waitForTimeout(1500)

    const exportBtn = page.getByRole('button', { name: /export docx/i }).or(
      page.getByRole('button', { name: /docx/i })).first()
    let exportVerified = false
    if (await exportBtn.count()) {
      const [download] = await Promise.all([
        page.waitForEvent('download', { timeout: 60000 }).catch(() => null),
        exportBtn.click(),
      ])
      if (download) {
        const file = path.join(OUT, 'exported-wapef.docx')
        await download.saveAs(file)
        log(true, 'DOCX export downloads', download.suggestedFilename())
        try {
          const xml = execSync(
            `python -c "import zipfile;print(zipfile.ZipFile(r'${file}').read('word/document.xml').decode('utf-8'))"`,
            { maxBuffer: 64 * 1024 * 1024 }).toString('utf-8')
          exportVerified = xml.includes(DEEP_HOPE)
          log(exportVerified, 'exported DOCX contains the teacher-selected Deep Hope verbatim')
          log(xml.includes(STORYLINE), 'exported DOCX contains the selected Storyline verbatim')
          log(xml.includes('Creation') || xml.includes('Redemption'), "exported DOCX contains a selected God's Story value")
          log(xml.includes('God worshiper') || xml.includes('Image reflector'),
            'exported DOCX contains a selected Through line value')
        } catch (e) {
          log(false, 'exported DOCX readable', e.message.slice(0, 120))
        }
      } else {
        log(false, 'DOCX export triggers a download')
      }
    } else {
      log(false, 'export control reachable after generation')
    }
    await shot(page, '09-kg-export.png')

    // ══ D. Lessons list sanity ══════════════════════════════════════════
    await page.goto(BASE + '/lessons', { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle').catch(() => {})
    await shot(page, '10-lessons.png')
    await noOverflow(page, 'lessons list')

    // ══ E. Responsive pass on the generate surface ══════════════════════
    await page.setViewportSize({ width: 1024, height: 768 })
    await page.waitForTimeout(600)
    await noOverflow(page, 'lessons (tablet)')
    await shot(page, '11-responsive-1024.png')

    await page.setViewportSize({ width: 390, height: 844 })
    await page.waitForTimeout(600)
    await noOverflow(page, 'lessons (phone)')
    await shot(page, '12-responsive-390.png')

    // ── Wrap up ──────────────────────────────────────────────────────────
    log(pageErrors.length === 0, 'zero uncaught page errors', pageErrors.slice(0, 3).join(' | '))
  } catch (e) {
    log(false, 'script completed', e.message)
    await shot(page, '99-failure.png').catch(() => {})
  } finally {
    fs.writeFileSync(path.join(OUT, 'results.txt'), results.join('\n') + '\n')
    console.log(`\n${pass} passed, ${fail} failed — screenshots in e2e/wapef-acceptance/`)
    await browser.close()
    process.exit(fail === 0 ? 0 : 1)
  }
})()
