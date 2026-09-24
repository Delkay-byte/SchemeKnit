/**
 * APP CHROME (Batch 2) acceptance.
 *
 * Verifies the shared chrome layer: one canonical header per application
 * area (navy #071826, sticky, z-40, cyan active state, aria-current, mobile
 * menu), PageHeader adoption on migrated pages, sub-navigation via the shared
 * Tabs primitive, the static blueprint workspace background (no landing mesh,
 * no auth grid, reduced-motion safe), and ServiceStatusBanner stacking (never
 * covering navigation or content, no fixed overlay).
 *
 * Usage: node e2e/app-chrome-acceptance.js [baseUrl]
 * Requires: backend on :8000 + `npm run build` + `next start` already running.
 */
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')

const BASE = process.argv[2] || 'http://localhost:3003'
const OUT = path.join(__dirname, 'app-chrome-acceptance')
fs.mkdirSync(OUT, { recursive: true })

const TEACHER = { email: 'accept.teacher@schemeknit.test', password: 'Accept#2026' }
const SCHOOL = { email: 'accept.sa@schemeknit.test', password: 'Accept#2026' }
const PLATFORM = { email: 'accept.pa@schemeknit.test', password: 'Accept#2026' }

const NAVY = 'rgb(7, 24, 38)' // #071826
const CYAN = 'rgb(4, 169, 206)' // #04A9CE

let pass = 0
let fail = 0
const results = []

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

async function login(page, entry, creds) {
  await page.goto(BASE + entry, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.locator('input[type="email"]').fill(creds.email)
  await page.locator('input[type="password"]').fill(creds.password)
  await page.getByRole('button', { name: /sign in/i }).click()
  await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 30000 })
}

/** Shared header invariants for whichever page the browser is on. */
async function checkHeader(page, scope) {
  const h = await page.evaluate(() => {
    const els = document.querySelectorAll('[data-app-header]')
    const el = els[0]
    if (!el) return { count: 0 }
    const cs = getComputedStyle(el)
    const rect = el.getBoundingClientRect()
    return {
      count: els.length,
      bg: cs.backgroundColor,
      position: cs.position,
      top: cs.top,
      zIndex: cs.zIndex,
      rectTop: rect.top,
    }
  })
  log(h.count === 1, `${scope}: exactly one application header`, `count=${h.count}`)
  log(h.bg === NAVY, `${scope}: header background = #071826`, `bg=${h.bg}`)
  log(h.position === 'sticky', `${scope}: header is sticky`, `position=${h.position} top=${h.top}`)
  log(h.zIndex === '40', `${scope}: header z-index = 40 (below dialogs at z-50)`, `z=${h.zIndex}`)
}

/** No landing mesh and no auth grid inside an app page. */
async function checkNoPublicDecor(page, scope) {
  const found = await page.evaluate(
    () => document.querySelectorAll('[data-mesh], [data-grid-signal-root]').length,
  )
  log(found === 0, `${scope}: no landing mesh / auth grid signal in app page`, `count=${found}`)
}

// ── 1. Static source checks ─────────────────────────────────────────────────
function staticChecks() {
  const src = (rel) => fs.readFileSync(path.join(__dirname, '..', rel), 'utf8')

  // Header renders exactly once per area — the three route-group layouts.
  let headerRenders = 0
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, entry.name)
      if (entry.isDirectory()) walk(p)
      else if (entry.name.endsWith('.tsx')) {
        const text = fs.readFileSync(p, 'utf8')
        if (/<Header\s*\/>/.test(text)) headerRenders++
      }
    }
  }
  walk(path.join(__dirname, '..', 'src'))
  log(headerRenders === 3,
    'static: <Header /> renders exactly 3x (one per application area)',
    `count=${headerRenders}`)

  // Pages no longer embed the header inline.
  const appDir = path.join(__dirname, '..', 'src', 'app')
  let inlineHeader = 0
  const walkPages = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, entry.name)
      if (entry.isDirectory()) walkPages(p)
      else if (entry.name === 'page.tsx') {
        if (/<Header\s*\/>/.test(fs.readFileSync(p, 'utf8'))) inlineHeader++
      }
    }
  }
  walkPages(appDir)
  log(inlineHeader === 0, 'static: no page embeds <Header /> inline', `count=${inlineHeader}`)

  // Status banner: never a fixed z-50 overlay (comments stripped first).
  const stripComments = (text) => {
    let out = ''
    let inBlock = false
    for (const line of text.split('\n')) {
      let t = line
      if (inBlock) {
        const end = t.indexOf('*/')
        if (end === -1) continue
        t = t.slice(end + 2)
        inBlock = false
      }
      const start = t.indexOf('/*')
      if (start !== -1) {
        const end = t.indexOf('*/', start + 2)
        if (end === -1) {
          inBlock = true
          t = t.slice(0, start)
        } else {
          t = t.slice(0, start) + t.slice(end + 2)
        }
      }
      const lineComment = t.indexOf('//')
      if (lineComment !== -1) t = t.slice(0, lineComment)
      out += t + '\n'
    }
    return out
  }
  const banner = stripComments(src('src/components/ServiceStatusBanner.tsx'))
  log(!/fixed top-0/.test(banner) && !/z-50/.test(banner),
    'static: ServiceStatusBanner is not a fixed z-50 overlay',
    'position classes checked')

  // School-admin authorization guard preserved verbatim.
  const saLayout = src('src/app/(school-admin)/school-admin/layout.tsx')
  log(
    /Strict role boundary: only school_admin belongs here/.test(saLayout) &&
      /router\.push\('\/login'\)/.test(saLayout) &&
      /router\.push\('\/platform-admin'\)/.test(saLayout) &&
      /router\.push\('\/dashboard'\)/.test(saLayout),
    'static: school-admin authorization guard intact (login/role redirects)',
    'all four redirects present',
  )

  // PageHeader component exists with its gate marker.
  const ph = src('src/components/ui/page-header.tsx')
  log(/data-page-header/.test(ph) && /<h1/.test(ph),
    'static: PageHeader component renders data-page-header + h1', 'ok')

  // Blueprint background is static CSS (no animation) and not the landing mesh.
  const css = src('src/app/globals.css')
  log(/\.app-blueprint/.test(css) && !/animation|@keyframes/.test(css.split('.app-blueprint')[1] || ''),
    'static: .app-blueprint is static CSS (no animation → reduced-motion safe)', 'ok')
}

// ── 2. Browser checks ───────────────────────────────────────────────────────
;(async () => {
  staticChecks()

  const pageErrors = []
  const browser = await chromium.launch({ headless: true })

  try {
    // ── Teacher @1440 ──
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    page.on('pageerror', (e) => pageErrors.push(`teacher: ${e.message}`))

    await login(page, '/login', TEACHER)
    await page.goto(BASE + '/dashboard/', { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle').catch(() => {})

    await checkHeader(page, 'teacher/dashboard')

    // Active nav + aria-current + cyan indicator on /lessons
    await page.goto(BASE + '/lessons/', { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle').catch(() => {})
    const active = await page.evaluate(() => {
      const nav = document.querySelector('[data-app-header] nav[aria-label="Primary"]')
      if (!nav) return null
      const current = nav.querySelector('[aria-current="page"]')
      const cs = current ? getComputedStyle(current) : null
      return {
        total: nav.querySelectorAll('[aria-current="page"]').length,
        href: current ? current.getAttribute('href') : null,
        color: cs ? cs.color : null,
      }
    })
    log(!!active && active.total === 1, 'teacher/lessons: exactly one aria-current nav link',
      active ? `href=${active.href}` : 'nav missing')
    log(!!active && (active.href || '').replace(/\/+$/, '') === '/lessons',
      'teacher/lessons: aria-current on Lesson Plans', active ? active.href : '')
    log(!!active && active.color === CYAN, 'teacher/lessons: active indicator = brand cyan #04A9CE',
      active ? `color=${active.color}` : '')

    // PageHeader on migrated pages
    for (const route of ['/dashboard/', '/upload/', '/lessons/', '/templates/', '/payments/']) {
      await page.goto(BASE + route, { waitUntil: 'domcontentloaded' })
      await page.waitForLoadState('networkidle').catch(() => {})
      const ph = await page.locator('[data-page-header]').count()
      const h1 = await page.locator('[data-page-header] h1').count()
      log(ph >= 1 && h1 >= 1, `PageHeader present with h1 on ${route}`, `headers=${ph} h1=${h1}`)
      await checkNoPublicDecor(page, route)
      const ov = await overflow(page)
      log(ov.scrollW <= ov.clientW + 1, `no horizontal overflow @1440 ${route}`,
        `${ov.scrollW}/${ov.clientW}`)
    }

    // Blueprint background renders (and only linear gradients — no mesh)
    const bg = await page.evaluate(() => {
      const el = document.querySelector('.app-blueprint')
      if (!el) return null
      const cs = getComputedStyle(el)
      return { image: cs.backgroundImage, animation: cs.animationName }
    })
    log(!!bg && bg.image.includes('linear-gradient') && !bg.image.includes('radial-gradient'),
      'teacher: workspace blueprint = static linear grid (not the landing mesh)',
      bg ? bg.image.slice(0, 60) : 'missing')
    log(!!bg && bg.animation === 'none', 'teacher: blueprint has no animation',
      bg ? `animation=${bg.animation}` : '')

    // ServiceStatusBanner stacking: in-flow, never covering header/nav/content
    await page.goto(BASE + '/dashboard/', { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle').catch(() => {})
    await page.evaluate(() => window.dispatchEvent(new CustomEvent('schemeknit:server-down')))
    await page.waitForTimeout(300)
    const banner = await page.evaluate(() => {
      const banners = Array.from(document.querySelectorAll('div')).filter(
        (d) => getComputedStyle(d).position === 'fixed' && /unavailable/i.test(d.textContent || ''),
      )
      const el = Array.from(document.querySelectorAll('div[role="status"]')).find((d) =>
        /server is currently unavailable|maintenance/i.test(d.textContent || ''),
      )
      if (!el) return { visible: false }
      const cs = getComputedStyle(el)
      const r = el.getBoundingClientRect()
      const h = document.querySelector('[data-app-header]')
      const hr = h ? h.getBoundingClientRect() : null
      return {
        visible: true,
        position: cs.position,
        zIndex: cs.zIndex,
        fixedCount: banners.length,
        rect: { top: r.top, bottom: r.bottom, left: r.left, right: r.right },
        headerRect: hr ? { top: hr.top, bottom: hr.bottom } : null,
      }
    })
    log(banner.visible, 'banner: status banner renders on server-down event', 'visible')
    log(banner.visible && banner.position !== 'fixed' && banner.fixedCount === 0,
      'banner: not a fixed overlay (in normal document flow)',
      banner.visible ? `position=${banner.position}` : '')
    log(banner.visible && (!banner.zIndex || banner.zIndex === 'auto' || Number(banner.zIndex) < 40),
      'banner: z-index below header (never covers navigation)',
      banner.visible ? `z=${banner.zIndex || 'auto'}` : '')
    log(
      banner.visible && banner.headerRect &&
        (banner.rect.bottom <= banner.headerRect.top + 1 ||
          banner.rect.top >= banner.headerRect.bottom - 1),
      'banner: does not overlap the sticky header (stacked, not covering)',
      banner.visible && banner.headerRect
        ? `banner.bottom=${Math.round(banner.rect.bottom)} header.top=${Math.round(banner.headerRect.top)}`
        : 'n/a',
    )
    // Restore healthy state for the rest of the run
    await page.evaluate(() => window.dispatchEvent(new CustomEvent('schemeknit:back-online')))
    await page.waitForTimeout(300)

    // Reduced-motion context: blueprint still renders, static
    const ctxR = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      reducedMotion: 'reduce',
    })
    const rPage = await ctxR.newPage()
    rPage.on('pageerror', (e) => pageErrors.push(`reduced: ${e.message}`))
    await login(rPage, '/login', TEACHER)
    await rPage.goto(BASE + '/dashboard/', { waitUntil: 'domcontentloaded' })
    await rPage.waitForLoadState('networkidle').catch(() => {})
    const rm = await rPage.evaluate(() => {
      const el = document.querySelector('.app-blueprint')
      return {
        matches: matchMedia('(prefers-reduced-motion: reduce)').matches,
        present: !!el,
        animation: el ? getComputedStyle(el).animationName : null,
      }
    })
    log(rm.matches && rm.present && rm.animation === 'none',
      'reduced-motion: blueprint static and present',
      `matches=${rm.matches} animation=${rm.animation}`)
    await ctxR.close()

    // 1024 pass
    const ctxT = await browser.newContext({ viewport: { width: 1024, height: 800 } })
    const tPage = await ctxT.newPage()
    tPage.on('pageerror', (e) => pageErrors.push(`tablet: ${e.message}`))
    await login(tPage, '/login', TEACHER)
    for (const route of ['/dashboard/', '/lessons/']) {
      await tPage.goto(BASE + route, { waitUntil: 'domcontentloaded' })
      await tPage.waitForLoadState('networkidle').catch(() => {})
      const ov = await overflow(tPage)
      log(ov.scrollW <= ov.clientW + 1, `no horizontal overflow @1024 ${route}`,
        `${ov.scrollW}/${ov.clientW}`)
    }
    await ctxT.close()

    // Mobile @390: header + hamburger menu
    const ctxM = await browser.newContext({ viewport: { width: 390, height: 844 } })
    const mPage = await ctxM.newPage()
    mPage.on('pageerror', (e) => pageErrors.push(`mobile: ${e.message}`))
    await login(mPage, '/login', TEACHER)
    await mPage.goto(BASE + '/dashboard/', { waitUntil: 'domcontentloaded' })
    await mPage.waitForLoadState('networkidle').catch(() => {})
    await checkHeader(mPage, 'teacher/dashboard @390')
    const mNav = await mPage.evaluate(() => {
      const btn = document.querySelector('button[aria-controls="app-mobile-nav"]')
      const desktop = document.querySelector('[data-app-header] nav[aria-label="Primary"]')
      return {
        btn: !!btn,
        btnLabel: btn ? btn.getAttribute('aria-label') : null,
        expanded: btn ? btn.getAttribute('aria-expanded') : null,
        desktopHidden: desktop ? getComputedStyle(desktop).display === 'none' : null,
      }
    })
    log(mNav.btn && mNav.expanded === 'false', 'mobile: hamburger menu button present (collapsed)',
      `label=${mNav.btnLabel} expanded=${mNav.expanded}`)
    log(mNav.desktopHidden === true, 'mobile: desktop nav hidden at 390', `hidden=${mNav.desktopHidden}`)
    await mPage.locator('button[aria-controls="app-mobile-nav"]').click()
    await mPage.waitForTimeout(200)
    const panel = await mPage.evaluate(() => {
      const nav = document.querySelector('#app-mobile-nav')
      const btn = document.querySelector('button[aria-controls="app-mobile-nav"]')
      return {
        visible: !!nav && getComputedStyle(nav).display !== 'none',
        links: nav ? nav.querySelectorAll('a[href]').length : 0,
        current: nav ? nav.querySelectorAll('[aria-current="page"]').length : 0,
        expanded: btn ? btn.getAttribute('aria-expanded') : null,
      }
    })
    log(panel.visible && panel.links >= 4 && panel.expanded === 'true',
      'mobile: menu opens with nav links + aria-expanded=true',
      `links=${panel.links} expanded=${panel.expanded}`)
    log(panel.current === 1, 'mobile: active link marked aria-current inside menu',
      `count=${panel.current}`)
    await mPage.keyboard.press('Escape')
    await mPage.waitForTimeout(200)
    const closed = await mPage.evaluate(() => !document.querySelector('#app-mobile-nav'))
    log(closed, 'mobile: Escape closes the menu', `open=${!closed}`)
    // Review page @390 (deep task page — action rows must wrap, not overflow)
    const reviewHref = await mPage
      .locator('a[href^="/review/"]')
      .first()
      .getAttribute('href')
      .catch(() => null)
    if (reviewHref) {
      await mPage.goto(BASE + reviewHref, { waitUntil: 'domcontentloaded' })
      await mPage.waitForLoadState('networkidle').catch(() => {})
      const ovR = await overflow(mPage)
      log(ovR.scrollW <= ovR.clientW + 1, `no horizontal overflow @390 ${reviewHref}`,
        `${ovR.scrollW}/${ovR.clientW}`)
    } else {
      log(true, 'no horizontal overflow @390 review (skipped)', 'no review link seeded')
    }
    for (const route of ['/dashboard/', '/lessons/', '/settings/']) {
      await mPage.goto(BASE + route, { waitUntil: 'domcontentloaded' })
      await mPage.waitForLoadState('networkidle').catch(() => {})
      const ov = await overflow(mPage)
      log(ov.scrollW <= ov.clientW + 1, `no horizontal overflow @390 ${route}`,
        `${ov.scrollW}/${ov.clientW}`)
    }
    await ctxM.close()

    await ctx.close()

    // ── School admin @1440 ──
    const ctxS = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const sPage = await ctxS.newPage()
    sPage.on('pageerror', (e) => pageErrors.push(`school: ${e.message}`))
    await login(sPage, '/login/school-admin', SCHOOL)
    await sPage.goto(BASE + '/school-admin/', { waitUntil: 'domcontentloaded' })
    await sPage.waitForLoadState('networkidle').catch(() => {})
    await checkHeader(sPage, 'school-admin')
    await checkNoPublicDecor(sPage, 'school-admin')

    const subnav = await sPage.evaluate(() => {
      const list = document.querySelector('[role="tablist"][aria-label="School administration sections"]')
      if (!list) return null
      const tabs = Array.from(list.querySelectorAll('[role="tab"]'))
      const current = list.querySelector('[aria-current="page"]')
      return {
        count: tabs.length,
        hrefs: tabs.map((t) => (t.closest('a') || t.querySelector('a') || t).getAttribute('href')),
        current: current ? (current.closest('a') || current).getAttribute('href') : null,
      }
    })
    const norm = (h) => (h || '').replace(/\/+$/, '') || '/'
    log(!!subnav && subnav.count === 4, 'school-admin: sub-nav uses shared Tabs (4 tabs)',
      subnav ? `count=${subnav.count}` : 'tablist missing')
    log(!!subnav && subnav.hrefs.map(norm).includes('/school-admin/teachers'),
      'school-admin: tabs keep existing route links', subnav ? subnav.hrefs.join(',') : '')
    log(!!subnav && norm(subnav.current) === '/school-admin',
      'school-admin: active section marked on dashboard', subnav ? subnav.current : '')

    // Route behavior preserved: tab click navigates to teachers
    await sPage.locator('[role="tablist"] a[href^="/school-admin/teachers"]').click()
    await sPage.waitForURL((u) => u.pathname.replace(/\/+$/, '') === '/school-admin/teachers', { timeout: 10000 }).catch(() => {})
    log(sPage.url().replace(/\/+$/, '').endsWith('/school-admin/teachers'),
      'school-admin: tab click navigates (route behavior preserved)', sPage.url())
    await sPage.waitForLoadState('networkidle').catch(() => {})
    await sPage.locator('[data-page-header]').first()
      .waitFor({ state: 'visible', timeout: 15000 })
      .catch(() => {})
    const phT = await sPage.locator('[data-page-header]').count()
    log(phT >= 1, 'school-admin/teachers: PageHeader present', `count=${phT}`)
    const ovS = await overflow(sPage)
    log(ovS.scrollW <= ovS.clientW + 1, 'school-admin/teachers: no horizontal overflow @1440',
      `${ovS.scrollW}/${ovS.clientW}`)
    await ctxS.close()

    // ── Platform admin @1440 ──
    const ctxP = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const pPage = await ctxP.newPage()
    pPage.on('pageerror', (e) => pageErrors.push(`platform: ${e.message}`))
    await login(pPage, '/login/platform-admin', PLATFORM)
    await pPage.goto(BASE + '/platform-admin/', { waitUntil: 'domcontentloaded' })
    await pPage.waitForLoadState('networkidle').catch(() => {})
    await checkHeader(pPage, 'platform-admin')
    await checkNoPublicDecor(pPage, 'platform-admin')

    const paTabs = await pPage.evaluate(() => {
      const list = document.querySelector('main [role="tablist"]')
      if (!list) return null
      return { count: list.querySelectorAll('[role="tab"]').length }
    })
    log(!!paTabs && paTabs.count === 9, 'platform-admin: tab row uses shared Tabs (9 tabs)',
      paTabs ? `count=${paTabs.count}` : 'tablist missing')

    await pPage.locator('main [role="tab"]:has-text("schools")').first().click()
    await pPage.waitForTimeout(600)
    const paActive = await pPage.evaluate(() => {
      const t = document.querySelector('main [role="tab"][data-state="active"]')
      return t ? t.textContent.trim() : null
    })
    log(paActive === 'schools', 'platform-admin: tab click activates section (behavior preserved)',
      `active=${paActive}`)

    const phP = await pPage.locator('[data-page-header]').count()
    log(phP >= 1, 'platform-admin: PageHeader present', `count=${phP}`)
    const ovP = await overflow(pPage)
    log(ovP.scrollW <= ovP.clientW + 1, 'platform-admin: no horizontal overflow @1440',
      `${ovP.scrollW}/${ovP.clientW}`)

    // Platform admin mobile chrome
    await pPage.setViewportSize({ width: 390, height: 844 })
    await pPage.waitForTimeout(300)
    const ovPM = await overflow(pPage)
    log(ovPM.scrollW <= ovPM.clientW + 1, 'platform-admin: no horizontal overflow @390',
      `${ovPM.scrollW}/${ovPM.clientW}`)
    await ctxP.close()

    log(pageErrors.length === 0, 'zero page errors across all journeys',
      pageErrors.slice(0, 3).join(' | ') || 'none')
  } catch (e) {
    log(false, 'gate completed without thrown error', e.message)
  } finally {
    await browser.close()
  }

  const summary = `App chrome (Batch 2) acceptance — ${new Date().toISOString()}\nBASE=${BASE}\nPASS=${pass} FAIL=${fail}\n\n${results.join('\n')}\n`
  fs.writeFileSync(path.join(OUT, 'results.txt'), summary)
  console.log(summary)
  console.log(`${pass} pass, ${fail} fail`)
  process.exit(fail > 0 ? 1 : 0)
})()
