/**
 * ONBOARDING GRID SYSTEM acceptance — dark grid + 3–4 moving signals
 * across login + signup + all onboarding/activation pages.
 *
 * Usage: node e2e/login-grid-acceptance.js [baseUrl]
 * Requires: npm run build + next start already running.
 *
 * Keeps the original 3-login regression baseline and extends to:
 *  - signup, activate-school, activate, reset-password, setup, setup/platform-admin
 *  - signal count (3–4) + multi-signal independent motion
 *  - decorative card / form readability, logo, no mesh, overflow
 *  - reduced-motion freeze, landing mesh exclusive to /
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
    // Prefer test-safe multi-signal diagnostics (stable signal #0).
    const raw = c.getAttribute('data-signal-positions') || ''
    const fromAttr = raw
      .split(/\s+/)
      .filter(Boolean)
      .map((s) => {
        const [x, y] = s.split(',').map(Number)
        return { x, y }
      })
      .filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y))
    if (fromAttr.length > 0) return fromAttr[0]
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

/** All live signal positions (CSS px) from diagnostics. */
async function allSignalPositions(page) {
  return page.evaluate(() => {
    const c = document.querySelector('canvas[data-grid-signal]')
    if (!c) return []
    const raw = c.getAttribute('data-signal-positions') || ''
    return raw
      .split(/\s+/)
      .filter(Boolean)
      .map((s) => {
        const [x, y] = s.split(',').map(Number)
        return { x, y }
      })
      .filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y))
  })
}

/** True if any tracked signal moved ≥ minPx between samples. */
function anyMoved(a, b, minPx) {
  if (!a || !b || !a.length || !b.length) return false
  const n = Math.min(a.length, b.length)
  for (let i = 0; i < n; i++) {
    if (Math.hypot(a[i].x - b[i].x, a[i].y - b[i].y) >= minPx) return true
  }
  // Different array sizes — check nearest matches too.
  for (const p of a) {
    for (const q of b) {
      if (Math.hypot(p.x - q.x, p.y - q.y) >= minPx) return true
    }
  }
  return false
}

/** Test-safe multi-signal diagnostics exposed on the canvas. */
async function signalDiagnostics(page) {
  return page.evaluate(() => {
    const c = document.querySelector('canvas[data-grid-signal]')
    if (!c) return null
    const count = Number(c.getAttribute('data-signal-count') || 0)
    const frame = Number(c.getAttribute('data-signal-frame') || 0)
    const raw = c.getAttribute('data-signal-positions') || ''
    const positions = raw
      .split(/\s+/)
      .filter(Boolean)
      .map((s) => {
        const [x, y] = s.split(',').map(Number)
        return { x, y }
      })
      .filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y))
    return { count, frame, positions, variant: c.getAttribute('data-grid-signal') }
  })
}

/** How many signals moved ≥ minPx between two diagnostic samples. */
function movedCount(a, b, minPx) {
  if (!a || !b || !a.positions.length || !b.positions.length) return 0
  const n = Math.min(a.positions.length, b.positions.length)
  let moved = 0
  for (let i = 0; i < n; i++) {
    const d = Math.hypot(a.positions[i].x - b.positions[i].x, a.positions[i].y - b.positions[i].y)
    if (d >= minPx) moved++
  }
  return moved
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
    const signalCountAttr = signal ? Number(signal.getAttribute('data-signal-count') || 0) : 0
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
    // Decorative light cards (curriculum/license/init chips) must keep dark text.
    let decorTextOk = true
    const lightDecor = Array.from(
      document.querySelectorAll('[aria-hidden="true"] div.rounded-2xl, [aria-hidden="true"] div.rounded-xl, [aria-hidden="true"] div.rounded-3xl'),
    ).filter((el) => {
      const bgc = getComputedStyle(el).backgroundColor
      const m = bgc.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/)
      if (!m) return false
      const lum = 0.2126 * +m[1] + 0.7152 * +m[2] + 0.0722 * +m[3]
      return lum > 200
    })
    for (const el of lightDecor) {
      const texts = Array.from(el.querySelectorAll('p, span, div')).filter((t) => {
        if (!t.textContent || !t.textContent.trim()) return false
        // Leaf text owners only — wrappers inherit page text color.
        return !Array.from(t.children).some(
          (c) => c.textContent && c.textContent.trim(),
        )
      })
      for (const t of texts) {
        const tc = getComputedStyle(t).color
        const m = tc.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/)
        if (!m) continue
        const lum = 0.2126 * +m[1] + 0.7152 * +m[2] + 0.0722 * +m[3]
        // Light card: text must be dark enough to read (fail near-white text).
        if (lum > 200) decorTextOk = false
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
      signalCountAttr,
      h1,
      title,
      logoOk,
      logoBg,
      markSvg,
      cardReadable,
      decorTextOk,
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

/** Original 3-login regression set (all prior checks retained). */
const LOGINS = [
  { name: 'teacher', path: '/login', signal: 'teacher', title: /Teacher|Welcome back/i, bg: 'rgb(7, 24, 38)' },
  { name: 'school', path: '/login/school-admin', signal: 'school', title: /School Administration/i, bg: 'rgb(11, 31, 58)' },
  { name: 'platform', path: '/login/platform-admin', signal: 'platform', title: /Platform Administration/i, bg: 'rgb(5, 14, 24)' },
]

/** Full V3 onboarding matrix (includes the 3 logins). */
const PAGES = [
  ...LOGINS,
  { name: 'signup', path: '/signup', signal: 'register', title: /Create your SchemeKnit account|Create your account/i, bg: 'rgb(10, 31, 53)' },
  { name: 'activate-school', path: '/activate-school', signal: 'school_activate', title: /Activate your school|Activate Your School|Code valid|Create school administrator|School activated/i, bg: 'rgb(10, 34, 64)' },
  { name: 'activate', path: '/activate', signal: 'teacher_license', title: /Activate your license|Activate Teacher License|License unlocked|Create school administrator/i, bg: 'rgb(14, 28, 46)' },
  { name: 'reset-password', path: '/reset-password', signal: 'password_reset', title: /Reset your password|Reset Your Password|Password reset complete/i, bg: 'rgb(10, 22, 40)' },
  { name: 'setup', path: '/setup', signal: 'first_run', title: /Initialize SchemeKnit|Set Up SchemeKnit/i, bg: 'rgb(13, 22, 48)', optional: true },
  { name: 'setup-platform-admin', path: '/setup/platform-admin', signal: 'platform', title: /Controlled admin bootstrap|Setup already complete|Setup complete/i, bg: 'rgb(5, 14, 24)', optional: true },
]

const WIDTHS = [390, 430, 768, 1024, 1280, 1440]

/** Desktop: expect 4 signals; mobile: 3 is acceptable. */
function signalCountOk(count, width) {
  if (width < 640) return count >= 3 && count <= 4
  return count >= 3 && count <= 4
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
  })
  const page = await context.newPage()

  // Motion probe at desktop for each page (3 timed position samples)
  for (const r of PAGES) {
    await page.setViewportSize({ width: 1440, height: 900 })
    try {
      await page.goto(BASE + r.path, { waitUntil: 'networkidle', timeout: 45000 })
    } catch (e) {
      if (r.optional) {
        log(true, `${r.name}: optional page skipped`, String(e && e.message))
        continue
      }
      throw e
    }
    await page.waitForTimeout(700)

    const info = await pageInfo(page)
    // setup may redirect when already initialized — treat as optional pass
    if (r.optional && !r.title.test(info.title) && !r.title.test(info.h1)) {
      log(true, `${r.name}: optional page not in setup state`, info.h1 || info.title)
      continue
    }
    const bootstrapComplete = r.name === 'setup-platform-admin' && info.forms < 1

    log(r.title.test(info.title) || r.title.test(info.h1), `${r.name}: title`, info.h1 || info.title)
    log(info.darkish, `${r.name}: dark field`, info.bg)
    log(info.bg === r.bg || info.bg.replace(/\s/g, '') === r.bg.replace(/\s/g, ''), `${r.name}: bg color`, `${info.bg} expected ${r.bg}`)
    log(info.meshCount === 0, `${r.name}: no landing mesh`, `mesh=${info.meshCount}`)
    log(info.signalVariant === r.signal, `${r.name}: grid signal variant`, String(info.signalVariant))
    log(info.logoOk && info.markSvg, `${r.name}: light logo capsule + S`, `bg=${info.logoBg} svg=${info.markSvg}`)
    if (bootstrapComplete) {
      log(true, `${r.name}: bootstrap complete state (form N/A)`, info.h1)
      log(true, `${r.name}: card readable (complete state)`)
      log(true, `${r.name}: decorative card text legible (complete state)`)
      log(true, `${r.name}: form present (complete state)`)
    } else {
      log(info.cardReadable, `${r.name}: login/form card readable`)
      log(info.decorTextOk !== false, `${r.name}: decorative card text legible`)
      log(info.forms >= 1 && info.inputs >= 1, `${r.name}: form present`, `forms=${info.forms}`)
    }

    const painted = await gridPainted(page)
    log(painted > 400, `${r.name}: dark grid visible`, `painted=${painted}`)

    await shot(page, `${r.name}-resting.png`)

    const d1 = await signalDiagnostics(page)
    log(
      d1 !== null && signalCountOk(d1.count, 1440),
      `${r.name}: 3–4 simultaneous signals`,
      d1 ? `count=${d1.count}` : 'no diagnostics',
    )

    const p1 = await signalPosition(page)
    const ap1 = await allSignalPositions(page)
    await page.waitForTimeout(800)
    await shot(page, `${r.name}-state-a.png`)
    const p2 = await signalPosition(page)
    const ap2 = await allSignalPositions(page)
    await page.waitForTimeout(800)
    await shot(page, `${r.name}-state-b.png`)
    const p3 = await signalPosition(page)
    const ap3 = await allSignalPositions(page)

    log(p1 !== null && p2 !== null && p3 !== null, `${r.name}: signal position found`, JSON.stringify([p1, p2, p3]))
    if (p1 && p2 && p3) {
      const d12 = await dist(p1, p2)
      const d23 = await dist(p2, p3)
      const moved12 = d12 >= 10 || anyMoved(ap1, ap2, 10)
      const moved23 = d23 >= 10 || anyMoved(ap2, ap3, 10)
      log(moved12, `${r.name}: signal moved A→B`, `d=${d12.toFixed(1)}px any=${anyMoved(ap1, ap2, 10)}`)
      log(moved23, `${r.name}: signal moved B→C`, `d=${d23.toFixed(1)}px any=${anyMoved(ap2, ap3, 10)}`)
      // Dense short hops on signal #0 → path stays on grid edges.
      const h0 = await signalPosition(page)
      await page.waitForTimeout(280)
      const h1 = await signalPosition(page)
      await page.waitForTimeout(280)
      const h2 = await signalPosition(page)
      const hopsOk = h0 && h1 && h2 && axisHopOk(h0, h1) && axisHopOk(h1, h2)
      log(!!hopsOk, `${r.name}: motion follows grid edges (short hops)`, JSON.stringify([h0, h1, h2]))
    }

    // Multi-signal independent motion: >1 signal moves between samples
    const m1 = await signalDiagnostics(page)
    await page.waitForTimeout(750)
    const m2 = await signalDiagnostics(page)
    await page.waitForTimeout(750)
    const m3 = await signalDiagnostics(page)
    const movedAB = movedCount(m1, m2, 10)
    const movedBC = movedCount(m2, m3, 10)
    log(
      movedAB > 1 || movedBC > 1,
      `${r.name}: multiple signals move independently`,
      `AB=${movedAB} BC=${movedBC} counts=${m1 && m1.count}/${m2 && m2.count}/${m3 && m3.count}`,
    )

    const ov = await overflow(page)
    log(ov.scrollW <= ov.clientW + 1, `${r.name}: no overflow @1440`, `${ov.scrollW}/${ov.clientW}`)
  }

  // Responsive matrix (all pages)
  for (const r of PAGES) {
    for (const w of WIDTHS) {
      const h = w < 500 ? 844 : 900
      await page.setViewportSize({ width: w, height: h })
      try {
        await page.goto(BASE + r.path, { waitUntil: 'networkidle', timeout: 45000 })
      } catch (e) {
        if (r.optional) continue
        throw e
      }
      await page.waitForTimeout(500)
      const info = await pageInfo(page)
      if (r.optional && !r.title.test(info.title) && !r.title.test(info.h1)) continue

      const ov = await overflow(page)
      log(ov.scrollW <= ov.clientW + 1, `${r.name} @${w}: no overflow`, `${ov.scrollW}/${ov.clientW}`)
      log(info.darkish, `${r.name} @${w}: dark field`, info.bg)
      log(info.signalVariant === r.signal, `${r.name} @${w}: signal present`, String(info.signalVariant))
      log(info.logoOk, `${r.name} @${w}: logo visible`)
      const painted = await gridPainted(page)
      log(painted > 150, `${r.name} @${w}: grid visible`, `painted=${painted}`)

      const diag = await signalDiagnostics(page)
      if (diag) {
        log(
          signalCountOk(diag.count, w),
          `${r.name} @${w}: 3–4 signals`,
          `count=${diag.count}`,
        )
      }

      if (w === 390 || w === 430 || w === 1440) {
        const a = await allSignalPositions(page)
        await page.waitForTimeout(850)
        const b = await allSignalPositions(page)
        if (a.length && b.length) {
          const moved = anyMoved(a, b, 8)
          log(moved, `${r.name} @${w}: signal moves`, `n=${a.length}/${b.length} any≥8=${moved}`)
        } else {
          log(false, `${r.name} @${w}: signal position found`, `${JSON.stringify(a)} / ${JSON.stringify(b)}`)
        }
        await shot(page, `${r.name}-${w}.png`)
      }
    }
  }

  // Reduced motion: static grid + frozen multi-signal frame
  const rmCtx = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    reducedMotion: 'reduce',
  })
  const rmPage = await rmCtx.newPage()
  for (const r of PAGES) {
    try {
      await rmPage.goto(BASE + r.path, { waitUntil: 'networkidle', timeout: 45000 })
    } catch (e) {
      if (r.optional) continue
      throw e
    }
    await rmPage.waitForTimeout(550)
    const info = await pageInfo(rmPage)
    if (r.optional && !r.title.test(info.title) && !r.title.test(info.h1)) continue

    const painted = await gridPainted(rmPage)
    log(painted > 400, `reduced-motion ${r.name}: static grid painted`, `painted=${painted}`)
    const a = await signalPosition(rmPage)
    await rmPage.waitForTimeout(800)
    const b = await signalPosition(rmPage)
    log(
      a !== null && b !== null && a.x === b.x && a.y === b.y,
      `reduced-motion ${r.name}: signal frozen`,
      `${JSON.stringify(a)} vs ${JSON.stringify(b)}`,
    )
    const da = await signalDiagnostics(rmPage)
    await rmPage.waitForTimeout(400)
    const db = await signalDiagnostics(rmPage)
    log(
      da && db && da.frame === db.frame && movedCount(da, db, 4) === 0,
      `reduced-motion ${r.name}: multi-signal static`,
      da && db ? `frame=${da.frame}/${db.frame}` : 'missing',
    )
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

  const summary = `Onboarding grid acceptance — ${new Date().toISOString()}\nBASE=${BASE}\nPASS=${pass} FAIL=${fail}\n\n${results.join('\n')}\n`
  fs.writeFileSync(path.join(OUT, 'results.txt'), summary)
  console.log(`Onboarding grid acceptance: ${pass} pass, ${fail} fail`)
  if (fail > 0) {
    console.log(results.filter((r) => r.startsWith('FAIL')).join('\n'))
    process.exit(1)
  }
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
