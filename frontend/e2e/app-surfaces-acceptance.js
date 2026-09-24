/**
 * BATCH 3 — APP SURFACES acceptance.
 *
 * Verifies the redesigned application surfaces: dashboard command center,
 * upload flow strip, review extraction summary, generate workspace (summary /
 * config / allocation / lesson review + action rail), lessons list & detail,
 * templates (my templates + approved groups), settings sections, upgrade and
 * payments, plus the school-admin and platform-admin consoles. Behavior and
 * API calls are covered by the older gates — this gate pins the new visual
 * structure, responsive overflow, and form interactivity of Batch 3.
 *
 * Usage: node e2e/app-surfaces-acceptance.js [baseUrl]
 * Requires: backend on :8000 + `npm run build` + `next start` already running.
 */
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')

const BASE = process.argv[2] || 'http://localhost:3003'
const OUT = path.join(__dirname, 'app-surfaces-acceptance')
fs.mkdirSync(OUT, { recursive: true })

const TEACHER = { email: 'accept.teacher@schemeknit.test', password: 'Accept#2026' }
const SCHOOL = { email: 'accept.sa@schemeknit.test', password: 'Accept#2026' }
const PLATFORM = { email: 'accept.pa@schemeknit.test', password: 'Accept#2026' }

let pass = 0
let fail = 0
const results = []
const pageErrors = []

function log(ok, label, detail) {
  if (ok) pass++
  else fail++
  results.push(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? ' — ' + detail : ''}`)
}

async function overflow(page) {
  return page.evaluate(() => ({
    scrollW: document.documentElement.scrollWidth,
    clientW: document.documentElement.clientWidth,
  }))
}

async function checkOverflow(page, scope) {
  await page.waitForLoadState('networkidle').catch(() => {})
  const a = await overflow(page)
  log(a.scrollW <= a.clientW + 1, `${scope}: no horizontal overflow @1440`, `${a.scrollW}/${a.clientW}`)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.waitForTimeout(350)
  const b = await overflow(page)
  log(b.scrollW <= b.clientW + 1, `${scope}: no horizontal overflow @390`, `${b.scrollW}/${b.clientW}`)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.waitForTimeout(250)
}

/** Wait for a marker rendered after data fetch, then report its count. */
async function waitCount(page, sel, timeout = 20000) {
  await page.locator(sel).first().waitFor({ state: 'attached', timeout }).catch(() => {})
  return page.locator(sel).count()
}

async function login(page, entry, creds) {
  await page.goto(BASE + entry, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.locator('input[type="email"]').fill(creds.email)
  await page.locator('input[type="password"]').fill(creds.password)
  await page.getByRole('button', { name: /sign in/i }).click()
  await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 30000 })
}

const count = (page, sel) => page.locator(sel).count()

// ── 1. Static source checks ─────────────────────────────────────────────────
function staticChecks() {
  const files = [
    'src/app/(app)/dashboard/page.tsx',
    'src/app/(app)/upload/page.tsx',
    'src/app/(app)/review/[id]/page.tsx',
    'src/app/(app)/generate/[id]/page.tsx',
    'src/app/(app)/lessons/page.tsx',
    'src/app/(app)/lessons/[id]/page.tsx',
    'src/app/(app)/templates/page.tsx',
    'src/app/(app)/settings/page.tsx',
    'src/app/(app)/upgrade/page.tsx',
    'src/app/(app)/payments/page.tsx',
    'src/app/(school-admin)/school-admin/page.tsx',
    'src/app/(school-admin)/school-admin/teachers/page.tsx',
    'src/app/(school-admin)/school-admin/license/page.tsx',
    'src/app/(school-admin)/school-admin/settings/page.tsx',
    'src/app/(platform-admin)/platform-admin/page.tsx',
  ]
  const strip = (raw) =>
    raw
      .split('\n')
      .filter((l) => {
        const t = l.trim()
        return !(
          t.startsWith('//') ||
          t.startsWith('/*') ||
          t.startsWith('*') ||
          t.startsWith('{/*')
        )
      })
      .join('\n')
  const read = (rel) => strip(fs.readFileSync(path.join(__dirname, '..', rel), 'utf8'))

  const confirms = files.filter((f) => /\bconfirm\s*\(/.test(read(f)))
  log(confirms.length === 0, 'static: zero confirm() across Batch 3 pages',
    confirms.join(', ') || `${files.length} files clean`)

  const legacy = files.filter((f) => read(f).includes('px-3 py-2 border rounded-md'))
  log(legacy.length === 0, 'static: zero legacy raw-input class remnants', legacy.join(', ') || 'none')

  const rawTags = files.filter((f) => /<select[\s>]/.test(read(f)) || /<textarea[\s>]/.test(read(f)))
  log(rawTags.length === 0, 'static: no raw <select>/<textarea> tags', rawTags.join(', ') || 'none')

  const templates = read('src/app/(app)/templates/page.tsx')
  log(!/\bprompt\s*\(/.test(templates), 'static: templates uses dialogs, no window.prompt()',
    'no prompt()')

  const upgrade = read('src/app/(app)/upgrade/page.tsx')
  log(!/emerald/.test(upgrade), 'static: upgrade uses brand palette (no emerald)', 'no emerald classes')

  const src = (rel) => fs.readFileSync(path.join(__dirname, '..', rel), 'utf8')
  const lessonsSrc = src('src/app/(app)/lessons/page.tsx')
  log(!/updated_at|"Updated"/.test(lessonsSrc),
    'static: lessons has no invented Updated column', 'absent')
}

// ── 2. Browser checks ───────────────────────────────────────────────────────
;(async () => {
  staticChecks()

  const browser = await chromium.launch({ headless: true })

  try {
    // ═══ Teacher surfaces ═══
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    page.on('pageerror', (e) => pageErrors.push(`teacher: ${e.message}`))

    await login(page, '/login', TEACHER)
    log(!page.url().includes('/login'), 'teacher: login succeeds', page.url())

    // ── Dashboard ──
    await page.goto(BASE + '/dashboard/', { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle').catch(() => {})
    log((await count(page, '[data-page-header]')) >= 1, 'dashboard: PageHeader present', '')
    log((await count(page, '[data-workflow]')) >= 1, 'dashboard: numbered workflow present', '')
    const wfHrefs = await page.evaluate(() =>
      Array.from(document.querySelectorAll('[data-workflow] a')).map((a) => a.getAttribute('href')),
    )
    log(wfHrefs.some((h) => (h || '').startsWith('/upload/')),
      'dashboard: workflow links to /upload/', wfHrefs.join(','))
    const wfText = await page.locator('[data-workflow]').innerText()
    for (const step of ['Upload Scheme', 'Review Curriculum', 'Select Indicators', 'Generate Lessons']) {
      log(wfText.includes(step), `dashboard: workflow step "${step}" renders`, '')
    }
    log((await count(page, '[data-stat]')) >= 3, 'dashboard: stat cards render',
      `count=${await count(page, '[data-stat]')}`)
    log((await count(page, 'main span.bg-green-100, main span.bg-blue-100, main span.bg-gray-100, main span.bg-purple-100')) > 0,
      'dashboard: StatusPill primitives render', '')
    await checkOverflow(page, 'dashboard')

    // ── Upload ──
    await page.goto(BASE + '/upload/', { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle').catch(() => {})
    log((await page.getByRole('heading', { name: /Upload/i }).count()) >= 1, 'upload: page heading renders', '')
    log((await count(page, '[data-upload-flow]')) >= 1, 'upload: UPLOAD→DETECT→REVIEW flow strip present', '')
    log((await count(page, '[data-dropzone]')) >= 1, 'upload: dropzone present', '')
    log((await count(page, 'main input[type="file"]')) >= 1, 'upload: file input present', '')
    await checkOverflow(page, 'upload')

    // ── Review (follow a review link when a scheme needs it) ──
    await page.goto(BASE + '/dashboard/', { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle').catch(() => {})
    const reviewLink = page.locator('main a[href^="/review/"]').first()
    if ((await reviewLink.count()) > 0) {
      await reviewLink.click()
      await page.waitForURL(/\/review\//, { timeout: 15000 }).catch(() => {})
      await page.waitForLoadState('networkidle').catch(() => {})
      log((await waitCount(page, '[data-page-header]')) >= 1, 'review: PageHeader present', '')
      log((await waitCount(page, '[data-extraction-summary]')) >= 1, 'review: extraction summary present', '')
      log((await waitCount(page, '[data-week-nav]')) >= 1, 'review: week navigation present', '')
      log((await waitCount(page, '[data-week-detail]')) >= 1, 'review: week detail surface present', '')
      await checkOverflow(page, 'review')
    } else {
      log(true, 'review: no scheme awaiting review (skipped)', 'no review link on dashboard')
    }

    // ── Generate (follow a generate link) ──
    await page.goto(BASE + '/dashboard/', { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle').catch(() => {})
    const genLink = page.locator('main a[href^="/generate/"]').first()
    if ((await genLink.count()) > 0) {
      await genLink.click()
      await page.waitForURL(/\/generate\//, { timeout: 15000 }).catch(() => {})
      await page.waitForLoadState('networkidle').catch(() => {})
      log((await waitCount(page, '[data-generate-summary]')) >= 1, 'generate: summary surface present', '')
      log((await waitCount(page, '[data-generate-config]')) >= 1, 'generate: config surface present', '')
      log((await waitCount(page, '[data-generate-action]')) >= 1, 'generate: action rail with primary CTA present', '')
      const selCount = await waitCount(page, 'main select')
      log(selCount >= 2, 'generate: at least 2 shared Select controls', `count=${selCount}`)
      const inputCount = await page.locator(
        'main input[type="text"], main input[type="number"], main input[type="date"]').count()
      log(inputCount >= 8, 'generate: configuration inputs present', `count=${inputCount}`)
      const enh = page.locator('main select:has(option[value="ENHANCED"])').first()
      if ((await enh.count()) > 0) {
        try {
          await enh.selectOption('ENHANCED')
          const v = await enh.inputValue()
          log(v === 'ENHANCED', 'generate: ENHANCED option selectable (native selectOption)', `value=${v}`)
        } catch (e) {
          log(false, 'generate: ENHANCED option selectable (native selectOption)', e.message)
        }
      } else {
        log(false, 'generate: ENHANCED option present', 'no select offers ENHANCED')
      }
      // Allocation surfaces render after Preview Allocation (fetch-driven).
      // A previously generated scheme shows the export rail instead.
      const previewBtn = page.locator('main button:has-text("Preview Allocation")').first()
      const exportBtn = page.locator('[data-generate-action] button:has-text("Download DOCX")').first()
      if ((await previewBtn.count()) > 0) {
        await previewBtn.click({ timeout: 8000 }).catch((e) => results.push(`INFO  preview click: ${e.message}`))
        log((await waitCount(page, '[data-allocation-preview]')) >= 1,
          'generate: allocation preview renders after Preview Allocation', '')
        log((await waitCount(page, '[data-lesson-review]')) >= 1,
          'generate: lesson review surface renders', '')
        log((await waitCount(page, '[data-coverage]')) >= 1,
          'generate: coverage summary renders', '')
      } else if ((await exportBtn.count()) > 0) {
        log(true, 'generate: scheme already generated — export rail present (preview not applicable)', '')
        log((await waitCount(page, '[data-coverage]')) >= 1,
          'generate: coverage summary renders', '')
      } else {
        log(false, 'generate: Preview Allocation button present', 'not found and no export rail')
      }
      await checkOverflow(page, 'generate')
      // Reload to discard local selection state.
      await page.goto(BASE + '/dashboard/', { waitUntil: 'domcontentloaded' })
    } else {
      log(true, 'generate: no scheme ready to generate (skipped)', 'no generate link on dashboard')
    }

    // ── Lessons list ──
    await page.goto(BASE + '/lessons/', { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle').catch(() => {})
    log((await page.getByRole('heading', { name: /Lesson Plans/i }).count()) >= 1,
      'lessons: page heading renders', '')
    const lessonsTable = await count(page, 'main table')
    const lessonsEmpty = await count(page, '[data-empty]')
    log(lessonsTable > 0 || lessonsEmpty > 0, 'lessons: table or empty state',
      `table=${lessonsTable} empty=${lessonsEmpty}`)
    if (lessonsTable > 0) {
      const headers = await page.evaluate(() =>
        Array.from(document.querySelectorAll('main table thead th')).map((th) => th.textContent.trim()),
      )
      for (const col of ['Subject', 'Week', 'Status', 'Actions']) {
        log(headers.some((h) => h.includes(col)), `lessons: column "${col}" present`, headers.join(','))
      }
      log((await count(page, 'main table span.bg-green-100, main table span.bg-blue-100, main table span.bg-gray-100')) > 0,
        'lessons: status pills in table', '')
    }
    await checkOverflow(page, 'lessons')

    // ── Lesson detail ──
    const lessonLink = page.locator('main a[href^="/lessons/"]').first()
    if ((await lessonLink.count()) > 0) {
      await lessonLink.click()
      await page.waitForURL((u) => /\/lessons\/.+/.test(u.pathname), { timeout: 15000 }).catch(() => {})
      await page.waitForLoadState('networkidle').catch(() => {})
      log((await waitCount(page, '[data-page-header]')) >= 1, 'lesson detail: PageHeader present', '')
      log((await waitCount(page, '[data-lesson-context]')) >= 1, 'lesson detail: context card present', '')
      log((await waitCount(page, '[data-lesson-plan]')) >= 1, 'lesson detail: lesson plan card present', '')
      const body = await page.locator('main').innerText().catch(() => '')
      log(/Objectives/i.test(body) && /Assessment/i.test(body),
        'lesson detail: objectives + assessment sections render', '')
      log((await page.locator('main button:has-text("Save")').count()) >= 1,
        'lesson detail: Save action present', '')
      await checkOverflow(page, 'lesson detail')
    } else {
      log(true, 'lesson detail: no lessons seeded (skipped)', 'no lesson link')
    }

    // ── Templates ──
    await page.goto(BASE + '/templates/', { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle').catch(() => {})
    log((await count(page, '[data-page-header]')) >= 1, 'templates: PageHeader present', '')
    const myTpl = await count(page, '[data-my-templates]')
    const tplEmpty = await count(page, '[data-empty]')
    log(myTpl >= 1 || tplEmpty >= 1, 'templates: my-templates surface or empty state',
      `mine=${myTpl} empty=${tplEmpty}`)
    log((await count(page, '[data-approved-group]')) >= 1, 'templates: approved template groups render', '')
    await checkOverflow(page, 'templates')

    // ── Settings ──
    await page.goto(BASE + '/settings/', { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle').catch(() => {})
    log((await count(page, '[data-page-header]')) >= 1, 'settings: PageHeader present', '')
    for (const sel of ['[data-settings-profile]', '[data-settings-holidays]', '[data-settings-subjects]', '[data-settings-about]']) {
      log((await count(page, sel)) >= 1, `settings: ${sel} section present`, '')
    }
    const sInputs = await count(page,
      'main input[type="text"], main input[type="email"], main input[type="date"]')
    log(sInputs >= 3, 'settings: shared Input primitives present', `count=${sInputs}`)
    await checkOverflow(page, 'settings')

    // ── Upgrade ──
    await page.goto(BASE + '/upgrade/', { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle').catch(() => {})
    log((await count(page, '[data-page-header]')) >= 1, 'upgrade: PageHeader present', '')
    const proShown = await count(page, '[data-pro-features]')
    const alreadyPro = await count(page, '[data-already-pro]')
    log(proShown >= 1 || alreadyPro >= 1, 'upgrade: features or already-pro surface',
      `features=${proShown} already=${alreadyPro}`)
    log((await count(page, 'main a[href^="/dashboard"]')) >= 1, 'upgrade: route back to dashboard', '')
    await checkOverflow(page, 'upgrade')

    // ── Payments ──
    await page.goto(BASE + '/payments/', { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle').catch(() => {})
    log((await count(page, '[data-page-header]')) >= 1, 'payments: PageHeader present', '')
    const purchase = page.locator('button:has-text("Purchase")').first()
    const purchaseCount = await purchase.count()
    const planCards = await count(page, '[data-plan-card]')
    log(planCards >= 1 || purchaseCount === 0, 'payments: plan cards render (or none seeded)',
      `cards=${planCards} purchase=${purchaseCount}`)
    if (purchaseCount > 0) {
      await purchase.click()
      await page.waitForTimeout(300)
      log((await count(page, '[data-submit-payment]')) >= 1, 'payments: submit form opens on Purchase', '')
      const paySel = page.locator('main select').first()
      log((await paySel.count()) >= 1, 'payments: shared Select in submit form', '')
      if ((await paySel.count()) > 0) {
        try {
          await paySel.selectOption('bank_transfer')
          const v = await paySel.inputValue()
          log(v === 'bank_transfer', 'payments: selectOption works on shared Select', `value=${v}`)
        } catch (e) {
          log(false, 'payments: selectOption works on shared Select', e.message)
        }
      }
      log((await count(page, '#payer-name')) >= 1, 'payments: form fields wired', '')
      const cancel = page.locator('[data-submit-payment] button:has-text("Cancel")')
      if ((await cancel.count()) > 0) {
        await cancel.click()
        await page.waitForTimeout(300)
        log((await count(page, 'main select')) === 0, 'payments: Cancel closes the form', '')
      }
    } else {
      log(true, 'payments: no plans seeded (skipped)', 'no Purchase button')
    }
    const histTable = await count(page, 'main table')
    const histEmpty = await page.getByText(/No payment history yet/i).count()
    log(histTable > 0 || histEmpty > 0, 'payments: history table or empty state',
      `table=${histTable} empty=${histEmpty}`)
    await checkOverflow(page, 'payments')

    await ctx.close()

    // ═══ School admin console ═══
    const ctxS = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const sPage = await ctxS.newPage()
    sPage.on('pageerror', (e) => pageErrors.push(`school: ${e.message}`))

    await login(sPage, '/login/school-admin', SCHOOL)
    log(!sPage.url().includes('/login'), 'school-admin: login succeeds', sPage.url())

    await sPage.goto(BASE + '/school-admin/', { waitUntil: 'domcontentloaded' })
    await sPage.waitForLoadState('networkidle').catch(() => {})
    log((await count(sPage, '[data-page-header]')) >= 1, 'school-admin: PageHeader present', '')
    log((await count(sPage, '[data-recent-teachers]')) >= 1, 'school-admin: recent teachers surface present', '')
    log((await count(sPage, 'main a[href^="/school-admin/teachers"]')) >= 1,
      'school-admin: routes to teachers section', '')
    await checkOverflow(sPage, 'school-admin dashboard')

    await sPage.goto(BASE + '/school-admin/teachers/', { waitUntil: 'domcontentloaded' })
    await sPage.waitForLoadState('networkidle').catch(() => {})
    log((await count(sPage, '[data-page-header]')) >= 1, 'school-admin/teachers: PageHeader present', '')
    const saTable = await count(sPage, 'main table')
    const saEmpty = await sPage.getByText(/No teachers yet/i).count()
    log(saTable > 0 || saEmpty > 0, 'school-admin/teachers: table or empty state',
      `table=${saTable} empty=${saEmpty}`)
    await checkOverflow(sPage, 'school-admin/teachers')

    await sPage.goto(BASE + '/school-admin/license/', { waitUntil: 'domcontentloaded' })
    await sPage.waitForLoadState('networkidle').catch(() => {})
    log((await count(sPage, '[data-page-header]')) >= 1, 'school-admin/license: PageHeader present', '')
    const licCard = await count(sPage, '[data-license-card]')
    const licEmpty = await sPage.getByText(/No license found/i).count()
    log(licCard >= 1 || licEmpty >= 1, 'school-admin/license: license card or empty state',
      `card=${licCard} empty=${licEmpty}`)

    await sPage.goto(BASE + '/school-admin/settings/', { waitUntil: 'domcontentloaded' })
    await sPage.waitForLoadState('networkidle').catch(() => {})
    log((await count(sPage, '[data-page-header]')) >= 1, 'school-admin/settings: PageHeader present', '')
    log((await count(sPage, '#school-name')) >= 1, 'school-admin/settings: school profile form wired', '')

    await ctxS.close()

    // ═══ Platform admin console ═══
    const ctxP = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const pPage = await ctxP.newPage()
    pPage.on('pageerror', (e) => pageErrors.push(`platform: ${e.message}`))

    await login(pPage, '/login/platform-admin', PLATFORM)
    log(!pPage.url().includes('/login'), 'platform-admin: login succeeds', pPage.url())

    await pPage.goto(BASE + '/platform-admin/', { waitUntil: 'domcontentloaded' })
    await pPage.waitForLoadState('networkidle').catch(() => {})
    log((await count(pPage, '[data-page-header]')) >= 1, 'platform-admin: PageHeader present', '')
    const paTabs = await pPage.evaluate(() => {
      const list = document.querySelector('main [role="tablist"]')
      return list ? list.querySelectorAll('[role="tab"]').length : 0
    })
    log(paTabs === 9, 'platform-admin: 9 console tabs render', `count=${paTabs}`)

    const schoolsTab = pPage.locator('main [role="tab"]:has-text("schools")').first()
    if ((await schoolsTab.count()) > 0) {
      await schoolsTab.click()
      await pPage.waitForTimeout(700)
      log((await count(pPage, 'main table')) >= 1, 'platform-admin/schools: table-first list renders', '')
      log((await count(pPage, 'main span.bg-green-100, main span.bg-red-100, main span.bg-orange-100')) > 0,
        'platform-admin/schools: StatusPill primitives render', '')
      await checkOverflow(pPage, 'platform-admin/schools')
    } else {
      log(false, 'platform-admin/schools: tab present', 'tab not found')
    }

    const paymentsTab = pPage.locator('main [role="tab"]:has-text("payments")').first()
    if ((await paymentsTab.count()) > 0) {
      await paymentsTab.click()
      await pPage.waitForTimeout(700)
      const heading = await pPage.getByRole('heading', { name: /Payments \(/i }).count()
      log(heading >= 1 || (await count(pPage, 'main table')) >= 1 || (await pPage.getByText(/No payments yet/i).count()) >= 1,
        'platform-admin/payments: section renders', `heading=${heading}`)
    }

    const settingsTab = pPage.locator('main [role="tab"]:has-text("settings")').first()
    if ((await settingsTab.count()) > 0) {
      await settingsTab.click()
      await pPage.waitForTimeout(500)
      log((await pPage.getByText(/Platform Settings/i).count()) >= 1,
        'platform-admin/settings: section renders', '')
      log((await count(pPage, '[data-maintenance]')) >= 1,
        'platform-admin/settings: maintenance control present', '')
    }

    await ctxP.close()

    log(pageErrors.length === 0, 'zero page errors across all journeys',
      pageErrors.slice(0, 3).join(' | ') || 'none')
  } catch (e) {
    log(false, 'gate completed without thrown error', e.message)
  } finally {
    await browser.close()
  }

  const summary = `App surfaces (Batch 3) acceptance — ${new Date().toISOString()}\nBASE=${BASE}\nPASS=${pass} FAIL=${fail}\n\n${results.join('\n')}\n`
  fs.writeFileSync(path.join(OUT, 'results.txt'), summary)
  console.log(summary)
  console.log(`${pass} pass, ${fail} fail`)
  process.exit(fail > 0 ? 1 : 0)
})()
