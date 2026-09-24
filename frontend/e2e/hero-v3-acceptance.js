/**
 * Hero V3/V4 acceptance — mesh landing-only + distinct auth/activation shells
 * + logo contrast + mobile touch interaction + hero/white seam.
 *
 * Extends the original V3 suite (all prior tests retained) with V4 checks:
 *  - mobile touch (Playwright touch context, 390×844): down/move/release pixel
 *    signatures, vertical scroll, no overflow
 *  - hero/next-section seam: heroRect.bottom ≈ nextSectionRect.top (≤1px),
 *    canvas fully inside hero box
 *  - reduced-motion: touch produces no deformation (static mesh)
 *
 * Usage: node e2e/hero-v3-acceptance.js [baseUrl]
 * Requires: npm run build already completed.
 */
const { chromium, devices } = require('playwright')
const fs = require('fs')
const path = require('path')

const BASE = process.argv[2] || 'http://localhost:3001'
const OUT = path.join(__dirname, 'hero-v3-acceptance')
fs.mkdirSync(OUT, { recursive: true })

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

async function canvasCount(page) {
  return page.locator('canvas').count()
}

async function hasCanvasMesh(page) {
  return page.evaluate(() => {
    const c = document.querySelector('canvas')
    if (!c) return false
    const ctx = c.getContext('2d')
    if (!ctx || !c.width || !c.height) return true
    const data = ctx.getImageData(0, 0, Math.min(c.width, 200), Math.min(c.height, 150)).data
    let painted = 0
    for (let i = 3; i < data.length; i += 4) if (data[i] > 0) painted++
    return painted > 20
  })
}

async function logoReadable(page) {
  return page.evaluate(() => {
    const imgs = Array.from(document.querySelectorAll('header span, main span, a span, div span'))
    for (const el of imgs) {
      const bg = getComputedStyle(el).backgroundColor
      const m = bg.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/)
      if (!m) continue
      const [r, g, b] = [1, 2, 3].map((i) => Number(m[i]))
      const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
      if (lum > 230 && el.querySelector('svg') && el.offsetWidth >= 24 && el.offsetWidth <= 64) {
        return { ok: true, bg, w: el.offsetWidth }
      }
    }
    return { ok: false, bg: null }
  })
}

/** Coarse pixel signature of the mesh canvas (top-left sample window). */
async function meshSignature(page) {
  return page.evaluate(() => {
    const c = document.querySelector('canvas')
    if (!c) return null
    const ctx = c.getContext('2d')
    if (!ctx) return null
    const w = Math.min(c.width, 240)
    const h = Math.min(c.height, 160)
    const d = ctx.getImageData(0, 0, w, h).data
    let s = 0
    for (let i = 0; i < d.length; i += 32) s += d[i] + d[i + 3]
    return s
  })
}

/** Hero/next-section seam + canvas containment (V4). */
async function seamMetrics(page) {
  return page.evaluate(() => {
    const hero = document.querySelector('section[aria-labelledby="hero-heading"]')
    const next = document.getElementById('how-it-works')
    if (!hero || !next) return null
    const hr = hero.getBoundingClientRect()
    const nr = next.getBoundingClientRect()
    const canvas = hero.querySelector('canvas')
    const cr = canvas ? canvas.getBoundingClientRect() : null
    return {
      heroBottom: hr.bottom,
      nextTop: nr.top,
      gap: nr.top - hr.bottom,
      canvasTop: cr ? cr.top : null,
      canvasBottom: cr ? cr.bottom : null,
      heroTop: hr.top,
      heroH: hr.height,
      overlap: hr.bottom - nr.top,
    }
  })
}

const ROUTES = [
  { route: '/login', label: 'teacher-login', titleMust: 'Teacher', bg: 'rgb(247, 245, 240)' },
  { route: '/login/school-admin', label: 'school-admin-login', titleMust: 'School Administration', bg: 'rgb(11, 31, 58)' },
  { route: '/login/platform-admin', label: 'platform-admin-login', titleMust: 'Platform Administration', bg: 'rgb(5, 14, 24)' },
  { route: '/signup', label: 'signup', titleMust: 'Create', bg: 'rgb(255, 255, 255)' },
  { route: '/activate-school', label: 'activate-school', titleMust: 'Activate', bg: 'rgb(243, 246, 250)' },
  { route: '/activate', label: 'activate-teacher', titleMust: 'Activate', bg: 'rgb(250, 250, 247)' },
  { route: '/reset-password', label: 'reset-password', titleMust: 'Reset', bg: 'rgb(244, 247, 250)' },
  { route: '/setup', label: 'setup', titleMust: 'Initialize', bg: 'rgb(248, 247, 252)' },
]

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
  })
  const page = await context.newPage()

  // ---- Landing: mesh present + logo contrast (V3) ----
  await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 60000 })
  await page.waitForTimeout(900)
  await shot(page, 'landing-desktop.png')

  const landingCanvas = await canvasCount(page)
  log(landingCanvas >= 1, 'landing: mesh canvas present', `count=${landingCanvas}`)

  const meshPainted = await page.evaluate(() => {
    const canvas = document.querySelector('section[aria-labelledby="hero-heading"] canvas') || document.querySelector('canvas')
    if (!canvas) return false
    const ctx = canvas.getContext('2d')
    if (!ctx) return false
    const d = ctx.getImageData(0, 0, Math.min(canvas.width || 1, 300), Math.min(canvas.height || 1, 200)).data
    let n = 0
    for (let i = 3; i < d.length; i += 4) if (d[i] > 0) n++
    return n > 50
  })
  log(meshPainted, 'landing: mesh painted')

  const before = await meshSignature(page)
  await page.mouse.move(400, 300)
  await page.mouse.move(700, 400, { steps: 12 })
  await page.waitForTimeout(350)
  const during = await meshSignature(page)
  log(before !== null && during !== null && before !== during, 'landing: cursor deformation changes pixels', `before=${before} during=${during}`)
  await shot(page, 'landing-desktop-cursor.png')

  const landingLogo = await logoReadable(page)
  log(landingLogo.ok, 'landing: light logo capsule', JSON.stringify(landingLogo))

  const ov = await overflow(page)
  log(ov.scrollW <= ov.clientW + 1, 'landing: no horizontal overflow', `${ov.scrollW}/${ov.clientW}`)

  // ---- V4: hero/white seam (desktop) ----
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.waitForTimeout(200)
  const seam = await seamMetrics(page)
  if (!seam) {
    log(false, 'seam: hero + next section found')
  } else {
    log(Math.abs(seam.gap) <= 1, 'seam: hero.bottom ≈ next.top (≤1px)', `gap=${seam.gap.toFixed(2)}px`)
    log(seam.overlap <= 1, 'seam: no white overlap onto hero', `overlap=${seam.overlap.toFixed(2)}px`)
    log(
      seam.canvasTop !== null && seam.canvasTop >= seam.heroTop - 1,
      'seam: canvas top inside hero',
      `canvasTop=${seam.canvasTop?.toFixed(1)} heroTop=${seam.heroTop.toFixed(1)}`,
    )
    log(
      seam.canvasBottom !== null && seam.canvasBottom <= seam.heroBottom + 1,
      'seam: canvas bottom inside hero',
      `canvasBottom=${seam.canvasBottom?.toFixed(1)} heroBottom=${seam.heroBottom.toFixed(1)}`,
    )
    // Seam screenshot: scroll so the boundary is visible
    await page.evaluate(() => {
      const hero = document.querySelector('section[aria-labelledby="hero-heading"]')
      if (hero) {
        const r = hero.getBoundingClientRect()
        window.scrollTo(0, window.scrollY + r.bottom - window.innerHeight / 2)
      }
    })
    await page.waitForTimeout(250)
    await shot(page, 'seam-desktop.png')
    await page.evaluate(() => window.scrollTo(0, 0))
  }

  // ---- Auth routes: NO mesh + distinct page backgrounds (V3) ----
  const bgSet = new Set()
  for (const r of ROUTES) {
    await page.goto(BASE + r.route, { waitUntil: 'networkidle', timeout: 45000 })
    await page.waitForTimeout(500)
    await shot(page, `${r.label}.png`)

    const title = await page.locator('h1').first().innerText().catch(() => '')
    log(
      title.toLowerCase().includes(r.titleMust.toLowerCase()),
      `${r.label}: title`,
      title.replace(/\s+/g, ' ').trim(),
    )

    const c = await canvasCount(page)
    log(c === 0, `${r.label}: no canvas/mesh`, `count=${c}`)

    const painted = await hasCanvasMesh(page)
    log(!painted, `${r.label}: no painted mesh`)

    const rootEl = await page.evaluate(() => {
      const el =
        document.querySelector('div.relative.min-h-screen.overflow-hidden') ||
        document.querySelector('main > div.min-h-screen') ||
        document.querySelector('div.min-h-screen') ||
        document.body
      return getComputedStyle(el).backgroundColor
    })
    bgSet.add(rootEl)
    log(
      rootEl === r.bg || rootEl.replace(/\s/g, '') === r.bg.replace(/\s/g, ''),
      `${r.label}: distinct bg`,
      `${rootEl} expected ${r.bg}`,
    )

    const logo = await logoReadable(page)
    log(logo.ok, `${r.label}: light logo capsule`)

    const o = await overflow(page)
    log(o.scrollW <= o.clientW + 1, `${r.label}: no overflow`, `${o.scrollW}/${o.clientW}`)
  }

  log(bgSet.size >= 6, 'auth matrix: distinct backgrounds', `unique=${bgSet.size}`)

  // ---- Reduced motion: static mesh, still visible (V3) ----
  const rmContext = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    reducedMotion: 'reduce',
  })
  const rmPage = await rmContext.newPage()
  await rmPage.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 45000 })
  await rmPage.waitForTimeout(700)
  await shot(rmPage, 'landing-reduced-motion.png')
  const rmPainted = await rmPage.evaluate(() => {
    const c = document.querySelector('canvas')
    if (!c) return false
    const ctx = c.getContext('2d')
    if (!ctx) return false
    const d = ctx.getImageData(0, 0, Math.min(c.width, 200), Math.min(c.height, 150)).data
    let n = 0
    for (let i = 3; i < d.length; i += 4) if (d[i] > 0) n++
    return n > 40
  })
  log(rmPainted, 'reduced-motion: static mesh still painted')
  const rmA = await meshSignature(rmPage)
  await rmPage.waitForTimeout(400)
  const rmB = await meshSignature(rmPage)
  log(rmA === rmB, 'reduced-motion: mesh static (no animation loop)', `${rmA} vs ${rmB}`)

  // V4: reduced-motion + touch → no deformation
  const rmTouchBefore = await meshSignature(rmPage)
  await rmPage.touchscreen.tap(200, 300).catch(() => {})
  await rmPage.waitForTimeout(300)
  const rmTouchAfter = await meshSignature(rmPage)
  log(
    rmTouchBefore !== null && rmTouchAfter !== null && rmTouchBefore === rmTouchAfter,
    'reduced-motion: touch does not deform mesh',
    `${rmTouchBefore} vs ${rmTouchAfter}`,
  )
  await rmContext.close()

  // ---- Responsive matrix + seam at each width (V3 + V4) ----
  for (const w of [390, 430, 768, 1024, 1280, 1440]) {
    await page.setViewportSize({ width: w, height: 860 })
    await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 45000 })
    await page.waitForTimeout(400)
    await shot(page, `landing-${w}.png`)
    const o = await overflow(page)
    log(o.scrollW <= o.clientW + 1, `landing @${w}: no overflow`, `${o.scrollW}/${o.clientW}`)
    const h1 = await page.locator('h1').first().isVisible()
    log(h1, `landing @${w}: headline visible`)

    const s = await seamMetrics(page)
    if (s) {
      log(Math.abs(s.gap) <= 1, `seam @${w}: hero/next meet ≤1px`, `gap=${s.gap.toFixed(2)}`)
      log(s.overlap <= 1, `seam @${w}: no overlap`, `overlap=${s.overlap.toFixed(2)}`)
    } else {
      log(false, `seam @${w}: sections found`)
    }
  }

  // Auth overflow on mobile
  await page.setViewportSize({ width: 390, height: 844 })
  for (const r of ROUTES) {
    await page.goto(BASE + r.route, { waitUntil: 'networkidle', timeout: 45000 })
    await page.waitForTimeout(350)
    const o = await overflow(page)
    log(o.scrollW <= o.clientW + 1, `${r.label} @390: no overflow`, `${o.scrollW}/${o.clientW}`)
    const c = await canvasCount(page)
    log(c === 0, `${r.label} @390: no canvas`)
  }

  // ---- V4: mobile touch interaction (iPhone 13, 390×844) ----
  const iPhone = devices['iPhone 13']
  const touchContext = await browser.newContext({
    ...iPhone,
    // ensure touch + hasTouch
    hasTouch: true,
    isMobile: true,
  })
  const tPage = await touchContext.newPage()
  await tPage.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 60000 })
  await tPage.waitForTimeout(900)

  const tCanvas = await canvasCount(tPage)
  log(tCanvas >= 1, 'touch: mesh canvas present', `count=${tCanvas}`)

  const tPainted = await hasCanvasMesh(tPage)
  log(tPainted, 'touch: mesh painted at rest')

  const tRest = await meshSignature(tPage)
  await shot(tPage, 'mobile-rest.png')

  // Touch down → pixel change
  await tPage.touchscreen.tap(195, 420)
  // tap is instantaneous; use dispatchEvent sequence for hold
  const tDown = await (async () => {
    // Fire pointerdown at center of hero via CDP-free path: touchscreen.tap
    // already lifted; instead simulate press using evaluate dispatch.
    return tPage.evaluate(() => {
      const c = document.querySelector('canvas')
      if (!c) return null
      const ctx = c.getContext('2d')
      const w = Math.min(c.width, 240)
      const h = Math.min(c.height, 160)
      const d = ctx.getImageData(0, 0, w, h).data
      let s = 0
      for (let i = 0; i < d.length; i += 32) s += d[i] + d[i + 3]
      return s
    })
  })()
  // Use page.touchscreen for a real touch press-hold-move via CDP if available
  try {
    const client = await touchContext.newCDPSession(tPage)
    // touchStart at (195, 420)
    await client.send('Input.dispatchTouchEvent', {
      type: 'touchStart',
      touchPoints: [{ x: 195, y: 420, id: 1 }],
    })
    await tPage.waitForTimeout(280)
    await shot(tPage, 'mobile-touch-down.png')
    const tHold = await meshSignature(tPage)
    log(
      tRest !== null && tHold !== null && tRest !== tHold,
      'touch: pointer down changes pixels',
      `rest=${tRest} hold=${tHold}`,
    )

    // Move touch → different signature
    await client.send('Input.dispatchTouchEvent', {
      type: 'touchMove',
      touchPoints: [{ x: 240, y: 480, id: 1 }],
    })
    await client.send('Input.dispatchTouchEvent', {
      type: 'touchMove',
      touchPoints: [{ x: 280, y: 540, id: 1 }],
    })
    await tPage.waitForTimeout(220)
    await shot(tPage, 'mobile-touch-drag.png')
    const tDrag = await meshSignature(tPage)
    log(
      tHold !== null && tDrag !== null && tHold !== tDrag,
      'touch: moving touch changes pixel signature',
      `hold=${tHold} drag=${tDrag}`,
    )

    // Release → settling (signature differs from drag, moves toward rest)
    await client.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
    await tPage.waitForTimeout(500)
    await shot(tPage, 'mobile-settled.png')
    const tSettle = await meshSignature(tPage)
    log(
      tDrag !== null && tSettle !== null && tSettle !== tDrag,
      'touch: release allows settling (signature changes)',
      `drag=${tDrag} settle=${tSettle}`,
    )
  } catch (err) {
    log(false, 'touch: CDP touch sequence', String(err && err.message ? err.message : err))
  }

  // No horizontal overflow on mobile
  const tOv = await overflow(tPage)
  log(tOv.scrollW <= tOv.clientW + 1, 'touch: no horizontal overflow', `${tOv.scrollW}/${tOv.clientW}`)

  // Vertical scroll still works
  const scrollBefore = await tPage.evaluate(() => window.scrollY)
  await tPage.evaluate(() => window.scrollBy(0, 500))
  await tPage.waitForTimeout(400)
  const scrollAfter = await tPage.evaluate(() => window.scrollY)
  log(scrollAfter > scrollBefore, 'touch: page can vertically scroll', `${scrollBefore} → ${scrollAfter}`)

  // Seam on mobile touch viewport
  await tPage.evaluate(() => window.scrollTo(0, 0))
  await tPage.waitForTimeout(200)
  const tSeam = await seamMetrics(tPage)
  if (tSeam) {
    log(Math.abs(tSeam.gap) <= 1, 'touch seam: hero/next meet ≤1px', `gap=${tSeam.gap.toFixed(2)}`)
    log(tSeam.overlap <= 1, 'touch seam: no overlap', `overlap=${tSeam.overlap.toFixed(2)}`)
    log(
      tSeam.canvasBottom !== null && tSeam.canvasBottom <= tSeam.heroBottom + 1,
      'touch seam: canvas inside hero',
      `canvasBottom=${tSeam.canvasBottom?.toFixed(1)} heroBottom=${tSeam.heroBottom.toFixed(1)}`,
    )
    await tPage.evaluate(() => {
      const hero = document.querySelector('section[aria-labelledby="hero-heading"]')
      if (hero) {
        const r = hero.getBoundingClientRect()
        window.scrollTo(0, window.scrollY + r.bottom - window.innerHeight / 2)
      }
    })
    await tPage.waitForTimeout(250)
    await shot(tPage, 'mobile-seam.png')
  } else {
    log(false, 'touch seam: sections found')
  }

  await touchContext.close()

  // ---- Platform admin not linked from public pages (V3) ----
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 45000 })
  const hrefs = await page.evaluate(() =>
    Array.from(document.querySelectorAll('a')).map((a) => a.getAttribute('href') || ''),
  )
  const platformPublic = hrefs.filter((h) => h.includes('platform-admin'))
  log(platformPublic.length === 0, 'landing: no public platform-admin CTA', JSON.stringify(platformPublic))

  await page.goto(BASE + '/login/platform-admin', { waitUntil: 'networkidle', timeout: 45000 })
  const paH1 = await page.locator('h1').first().innerText().catch(() => '')
  log(paH1.toLowerCase().includes('platform'), 'direct platform admin route works', paH1)
  const paCanvas = await canvasCount(page)
  log(paCanvas === 0, 'platform admin: no mesh')

  // Footer logo
  await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 45000 })
  const footerLogo = await page.evaluate(() => {
    const footer = document.querySelector('footer')
    if (!footer) return { ok: false, reason: 'no footer' }
    const spans = Array.from(footer.querySelectorAll('span'))
    for (const el of spans) {
      const bg = getComputedStyle(el).backgroundColor
      const m = bg.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/)
      if (!m) continue
      const lum = 0.2126 * Number(m[1]) + 0.7152 * Number(m[2]) + 0.0722 * Number(m[3])
      if (lum > 230 && el.querySelector('svg')) return { ok: true, bg }
    }
    return { ok: false, reason: 'no light capsule' }
  })
  log(footerLogo.ok, 'footer: light logo capsule', JSON.stringify(footerLogo))

  await browser.close()

  const report = [
    `Hero V3/V4 acceptance — ${new Date().toISOString()}`,
    `BASE=${BASE}`,
    `PASS=${pass} FAIL=${fail}`,
    '',
    ...results,
  ].join('\n')
  fs.writeFileSync(path.join(OUT, 'results.txt'), report, 'utf8')
  console.log(`\nHero V3/V4 acceptance: ${pass} pass, ${fail} fail`)
  if (fail) {
    results.filter((r) => r.startsWith('FAIL')).forEach((r) => console.log(r))
  }
  process.exit(fail ? 1 : 0)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
