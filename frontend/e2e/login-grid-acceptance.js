/**
 * LOGIN GRID SYSTEM acceptance — dark grid + moving signal on 3 login routes.
 *
 * Usage: node e2e/login-grid-acceptance.js [baseUrl]
 * Requires: npm run build + next start already running.
 *
 * Checks per login × viewport: load, dark field, logo/S, card readable,
 * no landing mesh, grid signal present, signal position moves across 3
 * samples, no overflow. Plus reduced-motion freeze + landing mesh intact.
 */
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')

const BASE = process.argv[2] || 'http://localhost:3003'
const OUT = path.join(__dirname, 'login-grid-acceptance')
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

/** Brightest cyan signal position on the grid canvas (CSS px). */
async function signalPosition(page) {
  return page.evaluate(() => {
    const c = document.querySelector('canvas[data-grid-signal]')
    if (!c || !c.width || !c.height) return null
    const ctx = c.getContext('2d')
    if (!ctx) return null
    const dpr = c.width / (c.clientWidth || c.width)
    const d = ctx.getImageData(0, 0, c.width, c.height).data
    let best = 0
    let bx = 0
    let by = 0
    for (let y = 0; y < c.height; y += 3) {
      for (let x = 0; x < c.width; x += 3) {
        const i = (y * c.width + x) * 4
        const a = d[i + 3]
        if (a < 50) continue
        const r = d[i]
        const g = d[i + 1]
        const b = d[i + 2]
        const s = (g + b - r) * a
        if (s > best) {
          best = s
          bx = x
          by = y
        }
      }
    }
    if (best < 8000) return null
    return { x: Math.round(bx / dpr), y: Math.round(by / dpr), score: best }
  })
}

async function pageInfo(page) {
  return page.evaluate(() => {
    const root =
      document.querySelector('div.relative.min-h-screen') ||
      document.querySelector('main') ||
      document.body
    const bg = getComputedStyle(root).backgroundColor
    const meshCount = document.querySelectorAll('[data-mesh]').length
    const signal = document.querySelector('canvas[data-grid-signal]')
    const signalVariant = signal ? signal.getAttribute('data-grid-signal') : null
    const h1 = document.querySelector('h1')?.textContent?.trim() || ''
    const title = document.title
    const brandLink = document.querySelector('a[aria-label="SchemeKnit home"], a[href="/"]')
    let logoOk = false
    let logoBg = ''
    let markSvg = false
    if (brandLink) {
      markSvg = !!brandLink.querySelector('svg')
      const capsule = brandLink.querySelector('span[style], span')
      if (capsule) {
        const s = getComputedStyle(capsule)
        logoBg = s.backgroundColor
        const m = logoBg.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/)
        if (m) {
          const r = +m[1]
          const g = +m[2]
          const b = +m[3]
          logoOk = 0.2126 * r + 0.7152 * g + 0.0722 * b > 200
        }
      }
    }
    const card = document.querySelector('form')?.closest('div.rounded-2xl') || null
    let cardReadable = false
    if (card) {
      const cs = getComputedStyle(card)
      const m = cs.backgroundColor.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/)
      if (m) {
        const lum = 0.2126 * +m[1] + 0.7152 * +m[2] + 0.0722 * +m[3]
        cardReadable = lum > 200
      }
    }
    const forms = document.querySelectorAll('form').length
    const inputs = document.querySelectorAll('input').length
    const darkish =
      /^rgb\(/.test(bg) &&
      (() => {
        const m = bg.match(/rgb\((\d+),\s*(\d+),\s*(\d+)/)
        if (!m) return false
        const lum = 0.2126 * +m[1] + 0.7152 * +m[2] + 0.0722 * +m[3]
        return lum < 60
      })()
    return {
      bg,
      meshCount,
      signalVariant,
      h1,
      title,
      logoOk,
      logoBg,
      markSvg,
      cardReadable,
      forms,
      inputs,
      darkish,
    }
  })
}

/** How many non-transparent grid pixels (grid visibility). */
async function gridPainted(page) {
  return page.evaluate(() => {
    const c = document.querySelector('canvas[data-grid-signal]')
    if (!c || !c.width || !c.height) return 0
    const ctx = c.getContext('2d')
    if (!ctx) return 0
    const w = Math.min(c.width, 400)
    const h = Math.min(c.height, 300)
    const d = ctx.getImageData(0, 0, w, h).data
    let n = 0
    for (let i = 3; i < d.length; i += 4) if (d[i] > 8) n++
    return n
  })
}

async function dist(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

/** Hops shorter than one edge should stay nearly axis-aligned (grid path). */
function axisHopOk(a, b) {
  const dx = Math.abs(b.x - a.x)
  const dy = Math.abs(b.y - a.y)
  const d = Math.hypot(dx, dy)
  if (d < 5) return true
  const minor = Math.min(dx, dy)
  return minor <= Math.max(8, d * 0.32)
}

const LOGINS = [
  { name: 'teacher', path: '/login', signal: 'teacher', title: /Teacher|Welcome back/i, bg: 'rgb(7, 24, 38)' },
  { name: 'school', path: '/login/school-admin', signal: 'school', title: /School Administration/i, bg: 'rgb(11, 31, 58)' },
  { name: 'platform', path: '/login/platform-admin', signal: 'platform', title: /Platform Administration/i, bg: 'rgb(5, 14, 24)' },
]

const WIDTHS = [390, 430, 768, 1024, 1280, 1440]

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
  })
  const page = await context.newPage()

  // Motion probe at desktop for each login (3 timed position samples)
  for (const r of LOGINS) {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto(BASE + r.path, { waitUntil: 'networkidle', timeout: 45000 })
    await page.waitForTimeout(600)

    const info = await pageInfo(page)
    log(r.title.test(info.title) || r.title.test(info.h1), `${r.name}: title`, info.h1 || info.title)
    log(info.darkish, `${r.name}: dark field`, info.bg)
    log(info.bg === r.bg || info.bg.replace(/\s/g, '') === r.bg.replace(/\s/g, ''), `${r.name}: bg color`, `${info.bg} expected ${r.bg}`)
    log(info.meshCount === 0, `${r.name}: no landing mesh`, `mesh=${info.meshCount}`)
    log(info.signalVariant === r.signal, `${r.name}: grid signal variant`, String(info.signalVariant))
    log(info.logoOk && info.markSvg, `${r.name}: light logo capsule + S`, `bg=${info.logoBg} svg=${info.markSvg}`)
    log(info.cardReadable, `${r.name}: login card readable`)
    log(info.forms >= 1 && info.inputs >= 1, `${r.name}: form present`, `forms=${info.forms}`)

    const painted = await gridPainted(page)
    log(painted > 400, `${r.name}: dark grid visible`, `painted=${painted}`)

    await shot(page, `${r.name}-resting.png`)

    const p1 = await signalPosition(page)
    await page.waitForTimeout(800)
    await shot(page, `${r.name}-state-a.png`)
    const p2 = await signalPosition(page)
    await page.waitForTimeout(800)
    await shot(page, `${r.name}-state-b.png`)
    const p3 = await signalPosition(page)

    log(p1 !== null && p2 !== null && p3 !== null, `${r.name}: signal position found`, JSON.stringify([p1, p2, p3]))
    if (p1 && p2 && p3) {
      const d12 = await dist(p1, p2)
      const d23 = await dist(p2, p3)
      log(d12 >= 10, `${r.name}: signal moved A→B`, `d=${d12.toFixed(1)}px`)
      log(d23 >= 10, `${r.name}: signal moved B→C`, `d=${d23.toFixed(1)}px`)
      // Dense short hops → path stays on grid edges (connected network).
      const h0 = await signalPosition(page)
      await page.waitForTimeout(280)
      const h1 = await signalPosition(page)
      await page.waitForTimeout(280)
      const h2 = await signalPosition(page)
      const hopsOk =
        h0 && h1 && h2 && axisHopOk(h0, h1) && axisHopOk(h1, h2)
      log(!!hopsOk, `${r.name}: motion follows grid edges (short hops)`, JSON.stringify([h0, h1, h2]))
    }

    const ov = await overflow(page)
    log(ov.scrollW <= ov.clientW + 1, `${r.name}: no overflow @1440`, `${ov.scrollW}/${ov.clientW}`)
  }

  // Responsive matrix
  for (const r of LOGINS) {
    for (const w of WIDTHS) {
      const h = w < 500 ? 844 : 900
      await page.setViewportSize({ width: w, height: h })
      await page.goto(BASE + r.path, { waitUntil: 'networkidle', timeout: 45000 })
      await page.waitForTimeout(450)
      const info = await pageInfo(page)
      const ov = await overflow(page)
      log(ov.scrollW <= ov.clientW + 1, `${r.name} @${w}: no overflow`, `${ov.scrollW}/${ov.clientW}`)
      log(info.darkish, `${r.name} @${w}: dark field`, info.bg)
      log(info.signalVariant === r.signal, `${r.name} @${w}: signal present`, String(info.signalVariant))
      log(info.logoOk, `${r.name} @${w}: logo visible`)
      const painted = await gridPainted(page)
      log(painted > 150, `${r.name} @${w}: grid visible`, `painted=${painted}`)
      if (w === 390 || w === 430 || w === 1440) {
        const a = await signalPosition(page)
        await page.waitForTimeout(850)
        const b = await signalPosition(page)
        if (a && b) {
          const d = await dist(a, b)
          log(d >= 8, `${r.name} @${w}: signal moves`, `d=${d.toFixed(1)}px`)
        } else {
          log(false, `${r.name} @${w}: signal position found`, `${a} / ${b}`)
        }
        await shot(page, `${r.name}-${w}.png`)
      }
    }
  }

  // Reduced motion: static grid + frozen signal
  const rmCtx = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    reducedMotion: 'reduce',
  })
  const rmPage = await rmCtx.newPage()
  for (const r of LOGINS) {
    await rmPage.goto(BASE + r.path, { waitUntil: 'networkidle', timeout: 45000 })
    await rmPage.waitForTimeout(500)
    const painted = await gridPainted(rmPage)
    log(painted > 400, `reduced-motion ${r.name}: static grid painted`, `painted=${painted}`)
    const a = await signalPosition(rmPage)
    await rmPage.waitForTimeout(800)
    const b = await signalPosition(rmPage)
    log(a !== null && b !== null && a.x === b.x && a.y === b.y, `reduced-motion ${r.name}: signal frozen`, `${JSON.stringify(a)} vs ${JSON.stringify(b)}`)
    await shot(rmPage, `${r.name}-reduced-motion.png`)
  }
  await rmCtx.close()

  // Landing mesh still exclusive to landing
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 45000 })
  await page.waitForTimeout(600)
  const landing = await page.evaluate(() => ({
    mesh: document.querySelectorAll('[data-mesh]').length,
    signal: document.querySelectorAll('canvas[data-grid-signal]').length,
  }))
  log(landing.mesh >= 1, 'landing: mesh present', JSON.stringify(landing))
  log(landing.signal === 0, 'landing: no login grid signal', JSON.stringify(landing))

  await browser.close()

  const summary = `Login grid acceptance — ${new Date().toISOString()}\nBASE=${BASE}\nPASS=${pass} FAIL=${fail}\n\n${results.join('\n')}\n`
  fs.writeFileSync(path.join(OUT, 'results.txt'), summary)
  console.log(`Login grid acceptance: ${pass} pass, ${fail} fail`)
  if (fail > 0) {
    console.log(results.filter((r) => r.startsWith('FAIL')).join('\n'))
    process.exit(1)
  }
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
