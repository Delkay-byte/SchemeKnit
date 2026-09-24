/**
 * Hero V3 acceptance — mesh landing-only + distinct auth/activation shells + logo contrast.
 *
 * Usage: node e2e/hero-v3-acceptance.js [baseUrl]
 * Requires: npm run build already completed.
 */
const { chromium } = require('playwright')
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

async function bodyBg(page) {
  return page.evaluate(() => getComputedStyle(document.body).backgroundColor)
}

async function pageBg(page) {
  return page.evaluate(() => {
    const root = document.querySelector('main > div, div.min-h-screen, [class*="min-h-screen"]')
    if (!root) return getComputedStyle(document.body).backgroundColor
    return getComputedStyle(root).backgroundColor
  })
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
  // Canonical navy mark on a light/white capsule — check capsule background luminance.
  return page.evaluate(() => {
    const imgs = Array.from(document.querySelectorAll('header span, main span, a span, div span'))
    for (const el of imgs) {
      const bg = getComputedStyle(el).backgroundColor
      const m = bg.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/)
      if (!m) continue
      const [r, g, b] = [1, 2, 3].map((i) => Number(m[i]))
      const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
      // look for near-white capsule containing an svg
      if (lum > 230 && el.querySelector('svg') && el.offsetWidth >= 24 && el.offsetWidth <= 64) {
        return { ok: true, bg, w: el.offsetWidth }
      }
    }
    return { ok: false, bg: null }
  })
}

const ROUTES = [
  { route: '/login', label: 'teacher-login', titleMust: 'Teacher', bg: 'rgb(247, 245, 240)', distinct: 'warm-teacher' },
  { route: '/login/school-admin', label: 'school-admin-login', titleMust: 'School Administration', bg: 'rgb(11, 31, 58)', distinct: 'school-dark' },
  { route: '/login/platform-admin', label: 'platform-admin-login', titleMust: 'Platform Administration', bg: 'rgb(5, 14, 24)', distinct: 'platform-dark' },
  { route: '/signup', label: 'signup', titleMust: 'Create', bg: 'rgb(255, 255, 255)', distinct: 'register-white' },
  { route: '/activate-school', label: 'activate-school', titleMust: 'Activate', bg: 'rgb(243, 246, 250)', distinct: 'school-activate' },
  { route: '/activate', label: 'activate-teacher', titleMust: 'Welcome', bg: 'rgb(250, 250, 247)', distinct: 'teacher-license' },
  { route: '/reset-password', label: 'reset-password', titleMust: 'Reset', bg: 'rgb(244, 247, 250)', distinct: 'password-reset' },
  { route: '/setup', label: 'setup', titleMust: 'Set Up', bg: 'rgb(248, 247, 252)', distinct: 'first-run' },
]

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
  })
  const page = await context.newPage()

  // ---- Landing: mesh present + logo contrast ----
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

  // Deformation responds to pointer
  const before = await page.evaluate(() => {
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
  await page.mouse.move(400, 300)
  await page.mouse.move(700, 400, { steps: 12 })
  await page.waitForTimeout(350)
  const during = await page.evaluate(() => {
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
  log(before !== null && during !== null && before !== during, 'landing: cursor deformation changes pixels', `before=${before} during=${during}`)

  const landingLogo = await logoReadable(page)
  log(landingLogo.ok, 'landing: light logo capsule', JSON.stringify(landingLogo))

  const ov = await overflow(page)
  log(ov.scrollW <= ov.clientW + 1, 'landing: no horizontal overflow', `${ov.scrollW}/${ov.clientW}`)

  // ---- Auth routes: NO mesh + distinct page backgrounds ----
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
      // AuthShell root: relative.min-h-screen.overflow-hidden (layout also has a white min-h-screen wrapper).
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

  // ---- Reduced motion: static mesh, still visible ----
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
  const rmA = await rmPage.evaluate(async () => {
    const c = document.querySelector('canvas')
    if (!c) return null
    const ctx = c.getContext('2d')
    const d = ctx.getImageData(0, 0, 200, 150).data
    let s = 0
    for (let i = 0; i < d.length; i += 16) s += d[i]
    return s
  })
  await rmPage.waitForTimeout(400)
  const rmB = await rmPage.evaluate(async () => {
    const c = document.querySelector('canvas')
    if (!c) return null
    const ctx = c.getContext('2d')
    const d = ctx.getImageData(0, 0, 200, 150).data
    let s = 0
    for (let i = 0; i < d.length; i += 16) s += d[i]
    return s
  })
  // Under reduce, mesh should be static (same sample); ambient page CSS may still differ slightly
  log(rmA === rmB, 'reduced-motion: mesh static (no animation loop)', `${rmA} vs ${rmB}`)
  await rmContext.close()

  // ---- Responsive matrix on landing ----
  for (const w of [390, 430, 768, 1024, 1280, 1440]) {
    await page.setViewportSize({ width: w, height: 860 })
    await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 45000 })
    await page.waitForTimeout(400)
    await shot(page, `landing-${w}.png`)
    const o = await overflow(page)
    log(o.scrollW <= o.clientW + 1, `landing @${w}: no overflow`, `${o.scrollW}/${o.clientW}`)
    const h1 = await page.locator('h1').first().isVisible()
    log(h1, `landing @${w}: headline visible`)
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

  // ---- Platform admin not linked from public pages ----
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 45000 })
  const hrefs = await page.evaluate(() =>
    Array.from(document.querySelectorAll('a')).map((a) => a.getAttribute('href') || ''),
  )
  const platformPublic = hrefs.filter((h) => h.includes('platform-admin'))
  log(platformPublic.length === 0, 'landing: no public platform-admin CTA', JSON.stringify(platformPublic))

  // Direct route still works
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
    `Hero V3 acceptance — ${new Date().toISOString()}`,
    `BASE=${BASE}`,
    `PASS=${pass} FAIL=${fail}`,
    '',
    ...results,
  ].join('\n')
  fs.writeFileSync(path.join(OUT, 'results.txt'), report, 'utf8')
  console.log(`\nHero V3 acceptance: ${pass} pass, ${fail} fail`)
  if (fail) {
    results.filter((r) => r.startsWith('FAIL')).forEach((r) => console.log(r))
  }
  process.exit(fail ? 1 : 0)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
