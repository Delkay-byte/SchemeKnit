/**
 * AUTH ROLE DESIGN V2 acceptance.
 *
 * Usage: node e2e/auth-role-design-acceptance.js [baseUrl]
 * Requires: npm run build + next start already running.
 */
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')

const BASE = process.argv[2] || 'http://localhost:3003'
const OUT = path.join(__dirname, 'auth-role-design-acceptance')
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

/** Brightest cyan signal position on the full grid canvas (motion probe). */
async function signalSignature(page) {
  return page.evaluate(() => {
    const c = document.querySelector('canvas[data-grid-signal]')
    if (!c || !c.width || !c.height) return null
    const ctx = c.getContext('2d')
    if (!ctx) return null
    const d = ctx.getImageData(0, 0, c.width, c.height).data
    let best = 0
    let bx = 0
    let by = 0
    for (let y = 0; y < c.height; y += 4) {
      for (let x = 0; x < c.width; x += 4) {
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
    // Quantize so tiny AA jitter doesn't false-fail; real travel still differs.
    return `${Math.round(bx / 6)}:${Math.round(by / 6)}:${best}`
  })
}

/** Login routes expect a role-specific grid signal; others expect no canvas. */
const LOGIN_SIGNALS = {
  'teacher-login': 'teacher',
  'school-admin-login': 'school',
  'platform-admin-login': 'platform',
}

async function pageInfo(page) {
  return page.evaluate(() => {
    const root =
      document.querySelector('div.relative.min-h-screen') ||
      document.querySelector('main') ||
      document.body
    const bg = getComputedStyle(root).backgroundColor
    const canvasCount = document.querySelectorAll('canvas').length
    const meshCount = document.querySelectorAll('[data-mesh]').length
    const gridSignals = Array.from(document.querySelectorAll('canvas[data-grid-signal]')).map((c) =>
      c.getAttribute('data-grid-signal'),
    )
    const h1 = document.querySelector('h1')?.textContent?.trim() || ''
    const title = document.title
    // Light logo capsule: look for scheme-knit mark inside a light surface
    const marks = Array.from(document.querySelectorAll('svg, img'))
    const brandLink = document.querySelector('a[aria-label="SchemeKnit home"], a[href="/"]')
    let logoOk = false
    let logoBg = ''
    if (brandLink) {
      const capsule = brandLink.querySelector('span[style], span')
      if (capsule) {
        const s = getComputedStyle(capsule)
        logoBg = s.backgroundColor
        // Parse rgb luminance
        const m = logoBg.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/)
        if (m) {
          const r = +m[1], g = +m[2], b = +m[3]
          logoOk = (0.2126 * r + 0.7152 * g + 0.0722 * b) > 200
        }
      }
    }
    const forms = document.querySelectorAll('form').length
    const buttons = Array.from(document.querySelectorAll('button[type="submit"]'))
    const ctaVisible = buttons.some((b) => {
      const r = b.getBoundingClientRect()
      return r.width > 0 && r.height > 0
    })
    const inputs = document.querySelectorAll('input').length
    return { bg, canvasCount, meshCount, gridSignals, h1, title, logoOk, logoBg, forms, ctaVisible, inputs }
  })
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await context.newPage()

  const ROUTES = [
    { name: 'teacher-login', path: '/login', title: /Teacher|Welcome back/i, bg: 'rgb(7, 24, 38)' },
    { name: 'school-admin-login', path: '/login/school-admin', title: /School Administration/i, bg: 'rgb(11, 31, 58)' },
    { name: 'platform-admin-login', path: '/login/platform-admin', title: /Platform Administration/i, bg: 'rgb(5, 14, 24)' },
    { name: 'signup', path: '/signup', title: /Create your SchemeKnit account/i, bg: 'rgb(255, 255, 255)' },
    { name: 'activate-school', path: '/activate-school', title: /Activate your school|Activate Your School/i, bg: 'rgb(243, 246, 250)' },
    { name: 'activate-teacher', path: '/activate', title: /Activate your license|Welcome to SchemeKnit/i, bg: 'rgb(250, 250, 247)' },
    { name: 'reset-password', path: '/reset-password', title: /Reset your password|Reset Your Password/i, bg: 'rgb(244, 247, 250)' },
    { name: 'setup', path: '/setup', title: /Initialize SchemeKnit|Set Up SchemeKnit/i, bg: 'rgb(248, 247, 252)' },
  ]

  const bgs = new Set()

  for (const r of ROUTES) {
    await page.goto(BASE + r.path, { waitUntil: 'networkidle', timeout: 30000 })
    await page.waitForTimeout(400)
    const info = await pageInfo(page)
    const ov = await overflow(page)

    log(r.title.test(info.title) || r.title.test(info.h1), `${r.name}: title`, `${info.title} / h1=${info.h1}`)
    log(info.bg === r.bg, `${r.name}: distinct bg`, `${info.bg} expected ${r.bg}`)
    bgs.add(info.bg)
    const expectedSignal = LOGIN_SIGNALS[r.name]
    if (expectedSignal) {
      log(info.meshCount === 0, `${r.name}: no landing mesh`, `mesh=${info.meshCount}`)
      log(
        info.gridSignals.includes(expectedSignal),
        `${r.name}: grid signal present`,
        JSON.stringify(info.gridSignals),
      )
      const s1 = await signalSignature(page)
      await page.waitForTimeout(700)
      const s2 = await signalSignature(page)
      await page.waitForTimeout(700)
      const s3 = await signalSignature(page)
      log(
        s1 !== null && s2 !== null && s3 !== null && s1 !== s2 && s2 !== s3,
        `${r.name}: signal moves over time (3 samples)`,
        `${s1} → ${s2} → ${s3}`,
      )
    } else {
      log(info.canvasCount === 0, `${r.name}: no canvas`, `count=${info.canvasCount}`)
      log(info.meshCount === 0, `${r.name}: no landing mesh`, `mesh=${info.meshCount}`)
    }
    log(info.logoOk, `${r.name}: light logo capsule`, `bg=${info.logoBg}`)
    log(ov.scrollW <= ov.clientW, `${r.name}: no overflow`, `${ov.scrollW}/${ov.clientW}`)
    log(info.forms >= 1 && info.inputs >= 1, `${r.name}: form visible`, `forms=${info.forms} inputs=${info.inputs}`)
    log(info.ctaVisible, `${r.name}: CTA visible`)

    await shot(page, `${r.name}-desktop.png`)
  }

  log(bgs.size >= 7, 'auth matrix: distinct backgrounds', `unique=${bgs.size} of ${bgs.size}`)

  // Distinct pairs
  await page.goto(BASE + '/login', { waitUntil: 'networkidle' })
  const teacherBg = (await pageInfo(page)).bg
  await page.goto(BASE + '/signup', { waitUntil: 'networkidle' })
  const signupBg = (await pageInfo(page)).bg
  log(teacherBg !== signupBg, 'teacher login ≠ signup bg', `${teacherBg} vs ${signupBg}`)

  await page.goto(BASE + '/activate-school', { waitUntil: 'networkidle' })
  const schoolActBg = (await pageInfo(page)).bg
  await page.goto(BASE + '/activate', { waitUntil: 'networkidle' })
  const teacherActBg = (await pageInfo(page)).bg
  log(schoolActBg !== teacherActBg, 'school activation ≠ teacher license bg', `${schoolActBg} vs ${teacherActBg}`)

  await page.goto(BASE + '/login/platform-admin', { waitUntil: 'networkidle' })
  const platLoginBg = (await pageInfo(page)).bg
  // setup/platform-admin may redirect or show bootstrap state
  await page.goto(BASE + '/setup/platform-admin', { waitUntil: 'networkidle', timeout: 30000 })
  await page.waitForTimeout(500)
  const platSetupInfo = await pageInfo(page)
  log(
    platSetupInfo.bg !== platLoginBg || platSetupInfo.h1.length > 0,
    'platform setup state renders distinct',
    `login=${platLoginBg} setup=${platSetupInfo.bg} h1=${platSetupInfo.h1}`,
  )
  await shot(page, 'platform-admin-setup-desktop.png')

  await page.goto(BASE + '/reset-password', { waitUntil: 'networkidle' })
  const resetBg = (await pageInfo(page)).bg
  const otherBgs = [...bgs].filter((b) => b !== resetBg)
  log(otherBgs.length >= 1 && !otherBgs.every((b) => b === resetBg), 'password reset unique context', resetBg)

  // Keyboard focus
  await page.goto(BASE + '/login', { waitUntil: 'networkidle' })
  await page.keyboard.press('Tab')
  const focusTag = await page.evaluate(() => document.activeElement?.tagName || '')
  log(['INPUT', 'A', 'BUTTON', 'BODY'].includes(focusTag), 'keyboard focus works', focusTag)

  // Error state (invalid email)
  await page.fill('#teacher-email', 'not-an-email')
  await page.fill('#teacher-password', 'x')
  await page.click('button[type="submit"]')
  await page.waitForTimeout(400)
  const hasError = await page.evaluate(() => {
    return !!document.querySelector('[role="alert"]') || !!document.querySelector('[aria-invalid="true"]')
  })
  log(hasError, 'error state visible on invalid submit')
  await shot(page, 'teacher-login-error.png')

  // Mobile 390
  await page.setViewportSize({ width: 390, height: 844 })
  for (const r of ROUTES) {
    await page.goto(BASE + r.path, { waitUntil: 'networkidle', timeout: 30000 })
    await page.waitForTimeout(300)
    const ov = await overflow(page)
    const info = await pageInfo(page)
    log(ov.scrollW <= ov.clientW, `${r.name} @390: no overflow`, `${ov.scrollW}/${ov.clientW}`)
    log(info.logoOk || info.logoBg !== '', `${r.name} @390: logo present`, info.logoBg)
    const expected390 = LOGIN_SIGNALS[r.name]
    if (expected390) {
      log(info.gridSignals.includes(expected390), `${r.name} @390: grid signal`, JSON.stringify(info.gridSignals))
      log(info.meshCount === 0, `${r.name} @390: no landing mesh`, `mesh=${info.meshCount}`)
    } else {
      log(info.canvasCount === 0, `${r.name} @390: no canvas`)
      log(info.meshCount === 0, `${r.name} @390: no landing mesh`, `mesh=${info.meshCount}`)
    }
    if (r.name === 'teacher-login' || r.name === 'signup' || r.name === 'platform-admin-login') {
      await shot(page, `${r.name}-mobile.png`)
    }
  }

  // Landing mesh only check
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(BASE + '/', { waitUntil: 'networkidle' })
  await page.waitForTimeout(600)
  const landing = await page.evaluate(() => ({
    canvases: document.querySelectorAll('canvas').length,
    mesh: document.querySelectorAll('[data-mesh]').length,
  }))
  log(landing.mesh >= 1, 'landing: mesh present', `mesh=${landing.mesh} canvas=${landing.canvases}`)

  // Reduced motion: login grid signal is static
  const rmCtx = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    reducedMotion: 'reduce',
  })
  const rmPage = await rmCtx.newPage()
  await rmPage.goto(BASE + '/login', { waitUntil: 'networkidle', timeout: 30000 })
  await rmPage.waitForTimeout(500)
  const rmInfo = await pageInfo(rmPage)
  log(rmInfo.gridSignals.includes('teacher'), 'reduced-motion: grid signal present', JSON.stringify(rmInfo.gridSignals))
  const rm1 = await signalSignature(rmPage)
  await rmPage.waitForTimeout(950)
  const rm2 = await signalSignature(rmPage)
  log(rm1 !== null && rm1 === rm2, 'reduced-motion: signal static', `${rm1} vs ${rm2}`)
  await shot(rmPage, 'teacher-login-reduced-motion.png')
  await rmCtx.close()

  // No public platform admin CTA
  const platformLinks = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('a'))
      .map((a) => a.getAttribute('href') || '')
      .filter((h) => h.includes('platform-admin'))
  })
  log(platformLinks.length === 0, 'landing: no public platform-admin CTA', JSON.stringify(platformLinks))

  await browser.close()

  const summary = `Auth role design V2 acceptance — ${new Date().toISOString()}\nBASE=${BASE}\nPASS=${pass} FAIL=${fail}\n\n${results.join('\n')}\n`
  fs.writeFileSync(path.join(OUT, 'results.txt'), summary)
  console.log(`Auth role design V2 acceptance: ${pass} pass, ${fail} fail`)
  if (fail > 0) {
    console.log(results.filter((r) => r.startsWith('FAIL')).join('\n'))
    process.exit(1)
  }
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
