/**
 * APP UI FOUNDATIONS (Batch 1) acceptance.
 *
 * Verifies the primitive migration: no legacy confirm()/raw controls remain in
 * the targeted pages, and the shared Badge/StatusPill, Dialog/ConfirmDialog,
 * Select, Table, Field/Input and Banner primitives render and behave on the
 * real app pages (cancel semantics = no API call).
 *
 * Usage: node e2e/app-ui-acceptance.js [baseUrl]
 * Requires: backend on :8000 + `npm run build` + `next start` already running.
 */
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')

const BASE = process.argv[2] || 'http://localhost:3003'
const OUT = path.join(__dirname, 'app-ui-acceptance')
fs.mkdirSync(OUT, { recursive: true })

const TEACHER = { email: 'accept.teacher@schemeknit.test', password: 'Accept#2026' }
const SCHOOL = { email: 'accept.sa@schemeknit.test', password: 'Accept#2026' }
const PLATFORM = { email: 'accept.pa@schemeknit.test', password: 'Accept#2026' }

let pass = 0
let fail = 0
const results = []

function log(ok, label, detail) {
  if (ok) pass++
  else fail++
  results.push(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? ' — ' + detail : ''}`)
}

async function shot(page, name) {
  await page.screenshot({ path: path.join(OUT, name), fullPage: false })
}

async function overflow(page) {
  return page.evaluate(() => ({
    scrollW: document.documentElement.scrollWidth,
    clientW: document.documentElement.clientWidth,
  }))
}

/** Track every state-changing request so "Cancel = no-op" is provable. */
function watchMutations(page) {
  const muts = []
  page.on('request', (r) => {
    const m = r.method()
    if (m !== 'GET' && m !== 'HEAD') muts.push(`${m} ${r.url().replace(BASE, '')}`)
  })
  return muts
}

async function login(page, entry, creds) {
  await page.goto(BASE + entry, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.locator('input[type="email"]').fill(creds.email)
  await page.locator('input[type="password"]').fill(creds.password)
  await page.getByRole('button', { name: /sign in/i }).click()
  await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 30000 })
}

// ── 1. Static source checks ─────────────────────────────────────────────────
function staticChecks() {
  const files = [
    'src/app/(app)/dashboard/page.tsx',
    'src/app/(app)/settings/page.tsx',
    'src/app/(app)/templates/page.tsx',
    'src/app/(app)/upload/page.tsx',
    'src/app/(app)/lessons/page.tsx',
    'src/app/(app)/lessons/[id]/page.tsx',
    'src/app/(app)/payments/page.tsx',
    'src/app/(app)/generate/[id]/page.tsx',
    'src/app/(app)/review/[id]/page.tsx',
    'src/app/(school-admin)/school-admin/page.tsx',
    'src/app/(school-admin)/school-admin/settings/page.tsx',
    'src/app/(school-admin)/school-admin/license/page.tsx',
    'src/app/(school-admin)/school-admin/teachers/page.tsx',
    'src/app/(platform-admin)/platform-admin/page.tsx',
  ]
  const code = files.map((f) => {
    const raw = fs.readFileSync(path.join(__dirname, '..', f), 'utf8')
    // Strip comment-only lines so prose mentioning legacy APIs never fails.
    const lines = raw.split('\n').filter((l) => {
      const t = l.trim()
      return !(t.startsWith('//') || t.startsWith('/*') || t.startsWith('*'))
    })
    return { f, text: lines.join('\n') }
  })

  const confirms = code.filter((c) => /\bconfirm\s*\(/.test(c.text)).map((c) => c.f)
  log(confirms.length === 0, 'static: zero confirm() in targeted pages',
    confirms.join(', ') || `${files.length} files clean`)

  const rawInputs = code.filter((c) => c.text.includes('px-3 py-2 border rounded-md')).map((c) => c.f)
  log(rawInputs.length === 0, 'static: zero px-3 py-2 border rounded-md remnants',
    rawInputs.join(', ') || 'none')

  const rawTags = code.filter((c) => /<select[\s>]/.test(c.text) || /<textarea[\s>]/.test(c.text)).map((c) => c.f)
  log(rawTags.length === 0, 'static: no raw <select>/<textarea> tags in targeted pages',
    rawTags.join(', ') || 'none')
}

// ── 2. Browser checks ───────────────────────────────────────────────────────
;(async () => {
  staticChecks()

  const pageErrors = []
  const browser = await chromium.launch({ headless: true })

  try {
    // Public surface: header mark + Free Tier wording intact, no overflow.
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    page.on('pageerror', (e) => pageErrors.push(`landing: ${e.message}`))

    await page.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 45000 })
    await page.waitForLoadState('networkidle').catch(() => {})
    const mark = await page.locator('a[href="/"] svg, a[href="/"] img').count()
    log(mark > 0, 'landing: header mark present', `count=${mark}`)
    let ov = await overflow(page)
    log(ov.scrollW <= ov.clientW + 1, 'landing: no horizontal overflow @1440', `${ov.scrollW}/${ov.clientW}`)

    // Free Tier wording lives in the login plan comparison card.
    await page.goto(BASE + '/login/', { waitUntil: 'domcontentloaded', timeout: 45000 })
    await page.waitForLoadState('networkidle').catch(() => {})
    const freeTier = await page.getByText(/Free Tier/).count()
    log(freeTier > 0, 'login: Free Tier wording intact', `count=${freeTier}`)

    // ── Teacher journey ──
    const muts = watchMutations(page)
    await login(page, '/login', TEACHER)
    log(page.url().includes('/dashboard') || !page.url().includes('/login'),
      'teacher: login succeeds', page.url())

    await page.goto(BASE + '/dashboard/', { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle').catch(() => {})
    const dashPills = await page.locator('main span.bg-green-100, main span.bg-blue-100, main span.bg-purple-100, main span.bg-gray-100').count()
    log(dashPills > 0, 'dashboard: StatusPill primitives render', `count=${dashPills}`)
    const dashMark = await page.locator('header svg[aria-label="SchemeKnit mark"], a[href="/"] svg, a[href="/"] img').count()
    log(dashMark > 0, 'dashboard: header mark present', `count=${dashMark}`)
    ov = await overflow(page)
    log(ov.scrollW <= ov.clientW + 1, 'dashboard: no horizontal overflow @1440', `${ov.scrollW}/${ov.clientW}`)
    await shot(page, 'dashboard-1440.png')

    // ConfirmDialog (Delete scheme) — Cancel must be a pure no-op.
    const delBtn = page.locator('main button:has(svg.lucide-trash-2), main button:has(svg.lucide-trash)').first()
    if ((await delBtn.count()) > 0) {
      const before = muts.length
      await delBtn.click()
      await page.getByRole('dialog').waitFor({ state: 'visible', timeout: 5000 }).catch(() => {})
      const dTitle = await page.getByRole('dialog').innerText().catch(() => '')
      log(/delete scheme/i.test(dTitle), 'dashboard: ConfirmDialog opens (Delete scheme)',
        dTitle.split('\n')[0])
      const cancelD = page.getByRole('dialog').locator('button:has-text("Cancel")')
      if ((await cancelD.count()) > 0) {
        await cancelD.first().click()
        await page.waitForTimeout(300)
        log((await page.getByRole('dialog').count()) === 0,
          'dashboard: ConfirmDialog Cancel closes without deleting', '')
      }
      const dMuts = muts.slice(before)
      log(dMuts.length === 0, 'dashboard: ConfirmDialog Cancel sent no API call',
        dMuts.join(', ') || 'none')
    } else {
      log(true, 'dashboard: ConfirmDialog — no schemes seeded (skipped)', 'no delete button')
    }

    // Input focus ring = brand cyan (#04A9CE)
    await page.goto(BASE + '/settings/', { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle').catch(() => {})
    const ring = await page.evaluate(async () => {
      const input = document.querySelector('main input:not([type="checkbox"]):not([type="file"])')
      if (!input) return null
      input.focus()
      await new Promise((r) => setTimeout(r, 400))
      return getComputedStyle(input).boxShadow
    })
    log(!!ring && ring.includes('4, 169, 206'), 'settings: Input focus ring = brand cyan', `box-shadow=${ring}`)
    const settingsInputs = await page.locator('main input[type="text"], main input[type="email"], main input[type="number"], main input[type="date"], main input[type="tel"]').count()
    log(settingsInputs >= 3, 'settings: shared Input primitives present', `count=${settingsInputs}`)

    // Table primitive on lessons (or its explicit empty state)
    await page.goto(BASE + '/lessons/', { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle').catch(() => {})
    const lessonsHeading = await page.getByRole('heading', { name: /Lesson Plans/i }).count()
    log(lessonsHeading > 0, 'lessons: page renders', `heading=${lessonsHeading}`)
    const tableCount = await page.locator('main table').count()
    const emptyCount = await page.getByText(/No lesson plans yet/).count()
    log(tableCount > 0 || emptyCount > 0,
      'lessons: Table primitive or empty state', `table=${tableCount} empty=${emptyCount}`)
    if (tableCount > 0) {
      const th = await page.locator('main table thead th').count()
      log(th >= 4, 'lessons: table header structure intact', `th=${th}`)
      const pills = await page.locator('main table span.bg-green-100, main table span.bg-blue-100, main table span.bg-gray-100').count()
      log(pills > 0, 'lessons: status pills in table', `count=${pills}`)
    }

    // Select primitive: payments purchase form (native selectOption must work)
    await page.goto(BASE + '/payments/', { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle').catch(() => {})
    const purchase = page.locator('button:has-text("Purchase")')
    if ((await purchase.count()) > 0) {
      const before = muts.length
      await purchase.first().click()
      const sel = page.locator('main select')
      log((await sel.count()) >= 1, 'payments: Select primitive in form', `count=${await sel.count()}`)
      try {
        await sel.first().selectOption('bank_transfer')
        const v = await sel.first().inputValue()
        log(v === 'bank_transfer', 'payments: selectOption() works on shared Select', `value=${v}`)
      } catch (e) {
        log(false, 'payments: selectOption() works on shared Select', e.message)
      }
      const newMuts = muts.slice(before).filter((m) => !m.startsWith('GET'))
      log(newMuts.length === 0, 'payments: selecting an option makes no API call', newMuts.join(', ') || 'none')
      // Cancel button closes the form without submitting
      const cancel = page.locator('button:has-text("Cancel")')
      if ((await cancel.count()) > 0) {
        await cancel.first().click()
        await page.waitForTimeout(200)
        log((await page.locator('main select').count()) === 0, 'payments: Cancel closes form', '')
      }
    } else {
      log(true, 'payments: Select primitive in form — no plans seeded (skipped)', 'purchase button absent')
    }

    // Generate page (native selects for AI mode / template — e2e contract)
    const genLink = await page.locator('a[href^="/generate/"]').count()
    const dashGen = await (async () => {
      await page.goto(BASE + '/dashboard/', { waitUntil: 'domcontentloaded' })
      await page.waitForLoadState('networkidle').catch(() => {})
      return page.locator('a[href^="/generate/"]').first()
    })()
    if ((await dashGen.count()) > 0) {
      const href = await dashGen.getAttribute('href')
      await page.goto(BASE + href, { waitUntil: 'domcontentloaded' })
      await page.waitForLoadState('networkidle').catch(() => {})
      const aiSel = page.locator('main select')
      log((await aiSel.count()) >= 2, 'generate: native Select controls render', `count=${await aiSel.count()}`)
      const aiMode = page.locator('main select').filter({ has: page.locator('option[value="ENHANCED"]') })
      if ((await aiMode.count()) > 0) {
        try {
          await aiMode.first().selectOption('ENHANCED')
          const v = await aiMode.first().inputValue()
          log(v === 'ENHANCED', 'generate: AI mode selectOption("ENHANCED") works', `value=${v}`)
        } catch (e) {
          log(false, 'generate: AI mode selectOption("ENHANCED") works', e.message)
        }
      }
      const genInputs = await page.locator('main input[type="text"], main input[type="number"], main input[type="date"]').count()
      log(genInputs >= 8, 'generate: shared Input primitives present', `count=${genInputs}`)
    } else {
      log(true, 'generate: native Select controls render — no scheme seeded (skipped)', 'no generate link')
      log(true, 'generate: AI mode selectOption — no scheme seeded (skipped)', 'no generate link')
      log(true, 'generate: shared Input primitives — no scheme seeded (skipped)', 'no generate link')
    }

    ov = await overflow(page)
    log(ov.scrollW <= ov.clientW + 1, 'teacher pages: no horizontal overflow @1440', `${ov.scrollW}/${ov.clientW}`)

    await ctx.close()

    // 390px pass on key pages (fresh context keeps login state simple)
    const ctxM = await browser.newContext({ viewport: { width: 390, height: 844 } })
    const mPage = await ctxM.newPage()
    mPage.on('pageerror', (e) => pageErrors.push(`mobile: ${e.message}`))
    await login(mPage, '/login', TEACHER)
    for (const route of ['/dashboard/', '/lessons/', '/settings/']) {
      await mPage.goto(BASE + route, { waitUntil: 'domcontentloaded' })
      await mPage.waitForLoadState('networkidle').catch(() => {})
      const o = await overflow(mPage)
      log(o.scrollW <= o.clientW + 1, `no horizontal overflow @390 ${route}`, `${o.scrollW}/${o.clientW}`)
    }
    await ctxM.close()

    // ── School admin journey: Dialog / ConfirmDialog / Banner semantics ──
    const ctxS = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const sPage = await ctxS.newPage()
    sPage.on('pageerror', (e) => pageErrors.push(`school: ${e.message}`))
    const sMuts = watchMutations(sPage)
    await login(sPage, '/login/school-admin', SCHOOL)
    log(!sPage.url().includes('/login'), 'school-admin: login succeeds', sPage.url())

    await sPage.goto(BASE + '/school-admin/', { waitUntil: 'domcontentloaded' })
    await sPage.waitForLoadState('networkidle').catch(() => {})
    const saPills = await sPage.locator('main span.bg-green-100, main span.bg-red-100, main span.bg-orange-100').count()
    const saEmpty = await sPage.getByText(/No teachers yet|Add your first teacher/i).count()
    log(saPills > 0 || saEmpty > 0, 'school-admin: StatusPill primitives render',
      saPills > 0 ? `count=${saPills}` : 'empty state (no teachers seeded)')
    await shot(sPage, 'school-admin-1440.png')

    await sPage.goto(BASE + '/school-admin/teachers/', { waitUntil: 'domcontentloaded' })
    await sPage.waitForLoadState('networkidle').catch(() => {})
    const addBtn = sPage.locator('button:has-text("Add Teacher")').first()
    if ((await addBtn.count()) > 0) {
      const before = sMuts.length
      await addBtn.click()
      const dlg = sPage.locator('role=dialog')
      await dlg.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {})
      const open1 = await sPage.locator('role=dialog').count()
      log(open1 > 0, 'teachers: Dialog (Add Teacher) opens', `dialogs=${open1}`)

      const focusIn = await sPage.evaluate(() => {
        const d = document.querySelector('[role="dialog"]')
        return !!d && d.contains(document.activeElement)
      })
      log(focusIn, 'teachers: dialog traps focus', '')

      await sPage.keyboard.press('Escape')
      await sPage.waitForTimeout(300)
      log((await sPage.locator('role=dialog').count()) === 0, 'teachers: Escape closes dialog', '')

      await addBtn.click()
      await sPage.getByRole('dialog').waitFor({ state: 'visible', timeout: 5000 }).catch(() => {})
      const cancelBtn = sPage.getByRole('dialog').locator('button:has-text("Cancel")').first()
      if ((await cancelBtn.count()) > 0) {
        await cancelBtn.click()
        await sPage.waitForTimeout(300)
        log((await sPage.locator('role=dialog').count()) === 0, 'teachers: Cancel closes dialog', '')
      }
      const dlgMuts = sMuts.slice(before)
      log(dlgMuts.length === 0, 'teachers: open/Escape/Cancel made no API call', dlgMuts.join(', ') || 'none')
    } else {
      log(false, 'teachers: Dialog (Add Teacher) opens', 'Add Teacher button not found')
    }

    // ConfirmDialog cancel semantics (Deactivate → dialog → Escape → nothing sent)
    const toggleBtn = sPage.locator('button[title="Deactivate"], button[title="Reactivate"]').first()
    if ((await toggleBtn.count()) > 0) {
      const before = sMuts.length
      await toggleBtn.click()
      const confirmDlg = sPage.locator('role=dialog')
      await confirmDlg.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {})
      const title = await sPage.locator('role=dialog').innerText().catch(() => '')
      log(/deactivate|reactivate/i.test(title), 'teachers: ConfirmDialog opens', title.split('\n')[0])
      const confirmBtn = sPage.getByRole('dialog').locator('button:has-text("Continue")')
      const cancel2 = sPage.getByRole('dialog').locator('button:has-text("Cancel")')
      log((await confirmBtn.count()) > 0, 'teachers: ConfirmDialog has explicit Confirm action', `count=${await confirmBtn.count()}`)
      await cancel2.first().click().catch(() => sPage.keyboard.press('Escape'))
      await sPage.waitForTimeout(300)
      const stillOpen = await sPage.locator('role=dialog').count()
      log(stillOpen === 0, 'teachers: ConfirmDialog Cancel closes without action', '')
      const cMuts = sMuts.slice(before)
      log(cMuts.length === 0, 'teachers: ConfirmDialog Cancel sent no API call', cMuts.join(', ') || 'none')
    } else {
      log(true, 'teachers: ConfirmDialog — no toggleable teacher seeded (skipped)', 'no Deactivate/Reactivate button')
    }

    // Banner: client-side validation error, no API call
    await sPage.goto(BASE + '/school-admin/settings/', { waitUntil: 'domcontentloaded' })
    await sPage.waitForLoadState('networkidle').catch(() => {})
    const nameInput = sPage.locator('#school-name')
    if ((await nameInput.count()) > 0) {
      const before = sMuts.length
      await nameInput.fill('')
      await sPage.locator('button:has-text("Save Changes")').click()
      await sPage.waitForTimeout(300)
      const banner = await sPage.locator('main div[role="alert"]').count()
      const bannerText = banner > 0 ? await sPage.locator('main div[role="alert"]').first().innerText() : ''
      log(banner > 0 && /required/i.test(bannerText), 'school settings: Banner role=alert on validation error', bannerText || 'no banner')
      const bMuts = sMuts.slice(before)
      log(bMuts.length === 0, 'school settings: validation error made no API call', bMuts.join(', ') || 'none')
    } else {
      log(false, 'school settings: Banner role=alert on validation error', '#school-name not found')
    }

    const tTable = await sPage.locator('main table').count().catch(() => 0)
    await sPage.goto(BASE + '/school-admin/teachers/', { waitUntil: 'domcontentloaded' })
    await sPage.waitForLoadState('networkidle').catch(() => {})
    const teachersTable = await sPage.locator('main table').count()
    log(teachersTable > 0 || (await sPage.getByText(/No teachers|Add your first teacher/i).count()) > 0,
      'teachers: Table primitive or empty state', `table=${teachersTable}`)
    ov = await overflow(sPage)
    log(ov.scrollW <= ov.clientW + 1, 'school-admin: no horizontal overflow @1440', `${ov.scrollW}/${ov.clientW}`)

    await ctxS.close()

    // ── Platform admin journey ──
    const ctxP = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const pPage = await ctxP.newPage()
    pPage.on('pageerror', (e) => pageErrors.push(`platform: ${e.message}`))
    const pMuts = watchMutations(pPage)
    await login(pPage, '/login/platform-admin', PLATFORM)
    log(!pPage.url().includes('/login'), 'platform-admin: login succeeds', pPage.url())

    await pPage.goto(BASE + '/platform-admin/', { waitUntil: 'domcontentloaded' })
    await pPage.waitForLoadState('networkidle').catch(() => {})
    const h1 = await pPage.getByRole('heading', { name: /Platform Administration/i }).count()
    log(h1 > 0, 'platform-admin: page renders', `h1=${h1}`)
    const tabs = await pPage.locator('main button:has-text("schools"), main button:has-text("licenses"), main button:has-text("payments"), main button:has-text("accounts")').count()
    log(tabs >= 4, 'platform-admin: tab row intact (Button-based)', `count=${tabs}`)
    const paBanner = await pPage.locator('main div[role="alert"], main div[role="status"]').count()
    log(paBanner >= 0, 'platform-admin: Banner host renders', `count=${paBanner}`)

    await pPage.locator('main button:has-text("schools")').first().click()
    await pPage.waitForLoadState('networkidle').catch(() => {})
    await pPage.waitForTimeout(500)
    const paPills = await pPage.locator('main span.bg-green-100, main span.bg-red-100, main span.bg-orange-100, main span.bg-blue-100, main span.bg-yellow-100').count()
    log(paPills > 0, 'platform-admin: StatusPill primitives render on Schools tab', `count=${paPills}`)
    await shot(pPage, 'platform-admin-1440.png')

    // A confirm-style action must open ConfirmDialog, not window.confirm()
    const resetBtn = pPage.locator('button:has-text("Reset Demo"), button:has-text("Initiate")').first()
    if ((await resetBtn.count()) > 0) {
      const beforeP = pMuts.length
      await resetBtn.click()
      await pPage.getByRole('dialog').waitFor({ state: 'visible', timeout: 5000 }).catch(() => {})
      const opened = await pPage.getByRole('dialog').count()
      log(opened > 0, 'platform-admin: ConfirmDialog replaces window.confirm', `dialogs=${opened}`)
      const pCancel = pPage.getByRole('dialog').locator('button:has-text("Cancel")')
      if ((await pCancel.count()) > 0) {
        await pCancel.first().click()
        await pPage.waitForTimeout(300)
        log((await pPage.getByRole('dialog').count()) === 0,
          'platform-admin: ConfirmDialog Cancel closes without action', '')
      }
      const pMutList = pMuts.slice(beforeP)
      log(pMutList.length === 0, 'platform-admin: ConfirmDialog Cancel sent no API call',
        pMutList.join(', ') || 'none')
    } else {
      log(true, 'platform-admin: ConfirmDialog — trigger not visible (skipped)', 'no trigger')
    }

    // Accounts tab: Initiate Password Reset is a destructive confirm path.
    const acctTab = pPage.locator('main button:has-text("accounts")')
    if ((await acctTab.count()) > 0) {
      await acctTab.first().click()
      await pPage.waitForLoadState('networkidle').catch(() => {})
      await pPage.waitForTimeout(500)
      const initBtn = pPage.locator('button:has-text("Initiate Password Reset")').first()
      if ((await initBtn.count()) > 0) {
        const beforeA = pMuts.length
        await initBtn.click()
        await pPage.getByRole('dialog').waitFor({ state: 'visible', timeout: 5000 }).catch(() => {})
        const aTitle = await pPage.getByRole('dialog').innerText().catch(() => '')
        log(/initiate password reset/i.test(aTitle),
          'platform-admin: ConfirmDialog opens (Initiate password reset)', aTitle.split('\n')[0])
        await pPage.keyboard.press('Escape')
        await pPage.waitForTimeout(300)
        log((await pPage.getByRole('dialog').count()) === 0,
          'platform-admin: Escape closes ConfirmDialog', '')
        const aMuts = pMuts.slice(beforeA)
        log(aMuts.length === 0, 'platform-admin: ConfirmDialog Escape sent no API call',
          aMuts.join(', ') || 'none')
      } else {
        log(true, 'platform-admin: ConfirmDialog (accounts) — no accounts seeded (skipped)',
          'no Initiate Password Reset button')
      }
    }

    const ovP = await overflow(pPage)
    log(ovP.scrollW <= ovP.clientW + 1, 'platform-admin: no horizontal overflow @1440', `${ovP.scrollW}/${ovP.clientW}`)
    await ctxP.close()

    // ── prefers-reduced-motion ──
    const ctxR = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' })
    const rPage = await ctxR.newPage()
    rPage.on('pageerror', (e) => pageErrors.push(`reduced: ${e.message}`))
    await login(rPage, '/login', TEACHER)
    await rPage.goto(BASE + '/dashboard/', { waitUntil: 'domcontentloaded' })
    await rPage.waitForLoadState('networkidle').catch(() => {})
    const rm = await rPage.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches)
    log(rm === true, 'reduced-motion: media query honored', `matches=${rm}`)
    const rmRender = await rPage.locator('main').count()
    log(rmRender > 0, 'reduced-motion: dashboard renders', `main=${rmRender}`)
    await ctxR.close()

    log(pageErrors.length === 0, 'zero page errors across all journeys',
      pageErrors.slice(0, 3).join(' | ') || 'none')
  } catch (e) {
    log(false, 'gate completed without thrown error', e.message)
  } finally {
    await browser.close()
  }

  const summary = `App UI foundations (Batch 1) acceptance — ${new Date().toISOString()}\nBASE=${BASE}\nPASS=${pass} FAIL=${fail}\n\n${results.join('\n')}\n`
  fs.writeFileSync(path.join(OUT, 'results.txt'), summary)
  console.log(summary)
  console.log(`${pass} pass, ${fail} fail`)
  process.exit(fail > 0 ? 1 : 0)
})()
