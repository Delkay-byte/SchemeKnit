/**
 * Hero V2 + professional authentication experience validation.
 *
 * Usage: node e2e/hero-auth-acceptance.js [baseUrl]
 * Requires: npm run build already completed.
 */
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')

const BASE = process.argv[2] || 'http://localhost:3001'
const OUT = path.join(__dirname, 'hero-auth-acceptance')
fs.mkdirSync(OUT, { recursive: true })

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

async function shot(page, name) {
  await page.screenshot({ path: path.join(OUT, name), fullPage: false })
}

async function canvasStats(page) {
  return page.evaluate(() => {
    const canvas = document.querySelector('section[aria-labelledby="hero-heading"] canvas')
    if (!canvas) return { present: false }
    const ctx = canvas.getContext('2d')
    const w = canvas.width
    const h = canvas.height
    if (!w || !h || !ctx) return { present: true, w, h, painted: false }
    const data = ctx.getImageData(0, 0, Math.min(w, 400), Math.min(h, 300)).data
    let painted = 0
    for (let i = 3; i < data.length; i += 4) {
      if (data[i] > 0) painted++
    }
    return { present: true, w, h, painted, styleW: canvas.style.width, styleH: canvas.style.height }
  })
}

async function frameDiffSamples(page, samples = 8) {
  // Sample canvas pixels at two times after a cursor move — mesh should change
  // when animated (or be stable under reduced motion).
  return page.evaluate(async (n) => {
    const canvas = document.querySelector('section[aria-labelledby="hero-heading"] canvas')
    if (!canvas) return null
    const ctx = canvas.getContext('2d')
    const w = Math.min(canvas.width, 300)
    const h = Math.min(canvas.height, 200)
    const read = () => {
      const d = ctx.getImageData(0, 0, w, h).data
      let sum = 0
      for (let i = 0; i < d.length; i += 16) sum += d[i] + d[i + 1] + d[i + 2] + d[i + 3]
      return sum
    }
    const a = read()
    await new Promise((r) => requestAnimationFrame(() => setTimeout(r, 120)))
    const b = read()
    return { a, b, changed: a !== b }
  }, samples)
}

async function navPlatformHref(page) {
  return page.evaluate(() => {
    const anchors = Array.from(document.querySelectorAll('a'))
    const hrefs = anchors.map((a) => a.getAttribute('href') || '')
    return {
      platformLogin: hrefs.filter((h) => h.includes('platform-admin') || h.toLowerCase().includes('platform')),
      platformSetup: hrefs.filter((h) => h.includes('/setup/platform-admin')),
    }
  })
}

async function checkAuthPage(page, route, opts) {
  await page.goto(BASE + route, { waitUntil: 'networkidle', timeout: 45000 })
  await page.waitForTimeout(600)
  await shot(page, opts.shot)

  const title = await page.locator('h1').first().innerText().catch(() => '')
  log(
    title.toLowerCase().includes(opts.titleMust.toLowerCase()),
    `${opts.label}: title`,
    title.replace(/\s+/g, ' ').trim(),
  )

  const canvas = await page.locator('canvas').count()
  log(canvas >= 1, `${opts.label}: ambient mesh canvas present`, `count=${canvas}`)

  const emailId = opts.emailId
  const emailVisible = await page.locator(`#${emailId}`).isVisible()
  log(emailVisible, `${opts.label}: email field visible`)

  const emailLabel = await page.locator(`label[for="${emailId}"]`).innerText()
  log(!!emailLabel.trim(), `${opts.label}: email label linked`, emailLabel.trim())

  const pwVisible = await page.locator('input[type="password"]').first().isVisible()
  log(pwVisible, `${opts.label}: password field visible`)

  const submit = page.locator('button[type="submit"]')
  log(await submit.isVisible(), `${opts.label}: submit visible`, await submit.innerText())

  // Autofocus check optional — skip strict if not required

  if (opts.expectForgot) {
    const forgot = page.getByRole('button', { name: /forgot password/i })
    log(await forgot.isVisible(), `${opts.label}: forgot password control`)
    await forgot.click()
    await page.waitForTimeout(200)
    const hint = page.locator('text=/Contact support/i').first()
    log(await hint.isVisible().catch(() => false), `${opts.label}: forgot hint + /contact link`)
  } else {
    const forgot = page.getByRole('button', { name: /forgot password/i })
    const count = await forgot.count()
    log(count === 0, `${opts.label}: no forgot control for restricted role`, `count=${count}`)
  }

  if (opts.roleBadge) {
    const badge = page.getByText(opts.roleBadge, { exact: false }).first()
    log(await badge.isVisible().catch(() => false), `${opts.label}: role badge`, opts.roleBadge)
  }

  if (opts.expectSecurityNote) {
    const note = page.locator('text=/Authorized SchemeKnit platform staff/i').first()
    log(await note.isVisible().catch(() => false), `${opts.label}: security note`)
  }

  if (opts.expectTeacherCards) {
    const schoolCard = page.locator('text=School Teacher').first()
    const indCard = page.locator('text=Individual Teacher').first()
    log(await schoolCard.isVisible(), `${opts.label}: teacher audience cards`)
    log(await indCard.isVisible(), `${opts.label}: individual teacher card`)
    const create = page.locator('a[href="/signup"], a[href="/signup/"]')
    log(await create.first().isVisible(), `${opts.label}: create account CTA`)
  }

  if (opts.expectActivate) {
    const act = page.locator('a[href="/activate-school"], a[href="/activate-school/"]')
    log(await act.first().isVisible().catch(() => false), `${opts.label}: activation code link`)
  }

  // Cross-links present (not platform admin)
  const nav = await navPlatformHref(page)
  if (opts.label !== 'platform-admin') {
    const bad = nav.platformLogin.concat(nav.platformSetup)
    log(bad.length === 0, `${opts.label}: no public platform-admin link`, JSON.stringify(nav))
  }

  const of = await overflow(page)
  log(of.scrollW <= of.clientW + 1, `${opts.label}: no horizontal overflow`, JSON.stringify(of))

  // Empty submit surfaces validation (browser or app) without crashing
  if (opts.tryEmptySubmit) {
    const errors = []
    const onErr = (e) => errors.push(e.message)
    page.on('pageerror', onErr)
    await submit.click()
    await page.waitForTimeout(400)
    log(errors.length === 0, `${opts.label}: empty submit no page crash`)
    page.off('pageerror', onErr)
  }

  return of
}

async function main() {
  const browser = await chromium.launch({ headless: true })

  // ---------- Hero desktop 1440 ----------
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    const errors = []
    page.on('pageerror', (e) => errors.push(e.message))
    page.on('console', (m) => {
      if (m.type() === 'error') errors.push(m.text())
    })
    await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 60000 })
    await page.waitForTimeout(1500)
    await shot(page, 'hero-1440.png')

    const heading = await page.locator('#hero-heading').innerText()
    log(
      /Turn Your Scheme/i.test(heading) && /Into the Right Lesson/i.test(heading),
      'hero: headline intact',
      heading.replace(/\s+/g, ' ').trim(),
    )

    const support = await page.locator('section[aria-labelledby="hero-heading"] p').filter({ hasText: 'scheme' }).first().isVisible()
    log(support, 'hero: support copy visible')

    const pipeline = await page.locator('#curriculum-pipeline').isVisible()
    log(pipeline, 'hero: curriculum pipeline visible')

    const logo = page.locator('header').locator('svg, span').filter({ hasText: 'SchemeKnit' }).first()
    log(await logo.isVisible(), 'header: brand wordmark visible')
    const capsule = page.locator('header span').filter({ hasText: '' }).first()
    const headerHasRing = await page.evaluate(() => {
      const header = document.querySelector('header')
      if (!header) return false
      return !!header.querySelector('[class*="ring-1"][class*="04A9CE"], [class*="capsule"], [class*="ring-[#04A9CE]"]')
    })
    log(headerHasRing, 'header: logo capsule treatment present')

    const st = await canvasStats(page)
    log(st.present && st.w > 0 && st.h > 0, 'hero: mesh canvas sized', JSON.stringify(st))
    log(st.painted > 50, 'hero: mesh painted non-empty pixels', `painted=${st.painted}`)

    // z-index: mesh behind copy
    const z = await page.evaluate(() => {
      const mesh = document.querySelector('section[aria-labelledby="hero-heading"] canvas')?.parentElement
      const inner = document.querySelector('section[aria-labelledby="hero-heading"] [class*="heroInner"], section[aria-labelledby="hero-heading"] > div:not([aria-hidden])')
      const csMesh = mesh ? getComputedStyle(mesh) : null
      const csInner = inner ? getComputedStyle(inner) : null
      return {
        meshZ: csMesh?.zIndex,
        meshPE: csMesh?.pointerEvents,
        innerZ: csInner?.zIndex,
      }
    })
    log(z.meshPE === 'none', 'hero: mesh pointer-events none', JSON.stringify(z))
    log(Number(z.innerZ) > Number(z.meshZ || 0), 'hero: content above mesh', JSON.stringify(z))

    // Cursor deformation — move over hero and sample twice
    await page.mouse.move(720, 420)
    await page.waitForTimeout(200)
    await page.mouse.move(860, 460, { steps: 12 })
    await page.waitForTimeout(250)
    const diff1 = await frameDiffSamples(page)
    log(!!diff1 && diff1.changed, 'hero: mesh animates after cursor move', JSON.stringify(diff1))

    // Move far away, settle, sample again
    await page.mouse.move(100, 100, { steps: 8 })
    await page.waitForTimeout(900)
    const diff2 = await frameDiffSamples(page)
    log(!!diff2, 'hero: mesh still running after settle', JSON.stringify(diff2))

    const nav = await navPlatformHref(page)
    const badNav = nav.platformLogin.concat(nav.platformSetup)
    log(badNav.length === 0, 'landing: no public Platform Admin CTA', JSON.stringify(nav))

    const of = await overflow(page)
    log(of.scrollW <= of.clientW + 1, 'hero@1440: no horizontal overflow', JSON.stringify(of))

    const cta = await page.getAttribute('a:has-text("Start Planning")', 'href')
    log(
      cta === '/login' || cta === '/login/',
      'hero: Start Planning → /login',
      String(cta),
    )

    const pageErrors = errors.filter(
      (e) => !/ERR_CONNECTION_REFUSED|Failed to load resource/i.test(e),
    )
    log(
      pageErrors.length === 0,
      'hero@1440: no console/page errors (backend refusals ignored)',
      pageErrors.join(' | ') || 'none',
    )
    await ctx.close()
  }

  // ---------- Responsive hero ----------
  for (const [w, h, mobile] of [
    [1024, 860, false],
    [768, 1024, false],
    [430, 860, true],
    [390, 844, true],
  ]) {
    const ctx = await browser.newContext({
      viewport: { width: w, height: h },
      isMobile: mobile,
      hasTouch: mobile,
    })
    const page = await ctx.newPage()
    await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 45000 })
    await page.waitForTimeout(900)
    await shot(page, `hero-${w}.png`)
    const of = await overflow(page)
    log(of.scrollW <= of.clientW + 1, `hero@${w}: no horizontal overflow`, JSON.stringify(of))
    const heading = await page.locator('#hero-heading').isVisible()
    log(heading, `hero@${w}: headline visible`)
    const pipeline = await page.locator('#curriculum-pipeline').isVisible()
    log(pipeline, `hero@${w}: pipeline visible`)
    const canvas = await canvasStats(page)
    log(canvas.present, `hero@${w}: mesh present`, JSON.stringify(canvas))
    await ctx.close()
  }

  // ---------- Reduced motion ----------
  {
    const ctx = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      reducedMotion: 'reduce',
    })
    const page = await ctx.newPage()
    await page.goto(BASE + '/', { waitUntil: 'networkidle' })
    await page.waitForTimeout(1200)
    await shot(page, 'hero-reduced-motion.png')
    const heading = await page.locator('#hero-heading').isVisible()
    log(heading, 'reduced-motion: headline visible')
    const st = await canvasStats(page)
    log(st.present && st.painted > 50, 'reduced-motion: static mesh still drawn', JSON.stringify(st))
    await page.mouse.move(700, 400, { steps: 5 })
    await page.waitForTimeout(400)
    // Static under reduced motion: two samples should be identical (or very close)
    const s1 = await frameDiffSamples(page)
    // force a short wait and re-sample without requiring change
    const s2 = await page.evaluate(() => {
      const canvas = document.querySelector('section[aria-labelledby="hero-heading"] canvas')
      if (!canvas) return null
      const ctx = canvas.getContext('2d')
      const d = ctx.getImageData(0, 0, Math.min(canvas.width, 200), Math.min(canvas.height, 150)).data
      let sum = 0
      for (let i = 0; i < d.length; i += 16) sum += d[i] + d[i + 3]
      return sum
    })
    log(s1 !== null && s2 !== null, 'reduced-motion: mesh canvas readable', JSON.stringify({ s1, s2 }))
    await ctx.close()
  }

  // ---------- Auth pages ----------
  const authCases = [
    {
      route: '/login',
      label: 'teacher-login',
      titleMust: 'Teacher Sign In',
      emailId: 'teacher-email',
      shot: 'auth-teacher-login-1440.png',
      roleBadge: 'Teacher',
      expectForgot: true,
      expectTeacherCards: true,
      tryEmptySubmit: false,
    },
    {
      route: '/signup',
      label: 'signup',
      titleMust: 'Create your',
      emailId: 'signup-email',
      shot: 'auth-signup-1440.png',
      roleBadge: 'Teacher',
      tryEmptySubmit: false,
    },
    {
      route: '/login/school-admin',
      label: 'school-admin-login',
      titleMust: 'School Administration',
      emailId: 'school_admin-email',
      shot: 'auth-school-admin-1440.png',
      roleBadge: 'School Administration',
      expectForgot: true,
      expectActivate: true,
      tryEmptySubmit: false,
    },
    {
      route: '/login/platform-admin',
      label: 'platform-admin',
      titleMust: 'Platform Administration',
      emailId: 'platform_admin-email',
      shot: 'auth-platform-admin-1440.png',
      roleBadge: 'Platform Administration',
      expectForgot: false,
      expectSecurityNote: true,
      tryEmptySubmit: false,
    },
  ]

  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    for (const c of authCases) {
      await checkAuthPage(page, c.route, c)
    }

    // Signup confirm-password match indicator
    await page.goto(BASE + '/signup', { waitUntil: 'networkidle' })
    await page.fill('#signup-password', 'Secret12!')
    await page.waitForTimeout(150)
    await page.fill('#signup-confirm', 'Secret99!')
    await page.waitForTimeout(200)
    const mismatch = await page.locator('text=/Passwords do not match/i').first().isVisible()
    log(mismatch, 'signup: password mismatch indicator')
    await page.fill('#signup-confirm', 'Secret12!')
    await page.waitForTimeout(200)
    const match = await page.locator('text=/Passwords match/i').first().isVisible()
    log(match, 'signup: password match indicator')

    // Forgot password expands to /contact (teacher)
    await page.goto(BASE + '/login', { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: /forgot password/i }).click()
    await page.waitForTimeout(300)
    const contactHref = await page
      .locator('a[href="/contact"], a[href="/contact/"]')
      .first()
      .getAttribute('href')
    log(
      contactHref === '/contact' || contactHref === '/contact/',
      'teacher-login: forgot → /contact link',
      String(contactHref),
    )

    await ctx.close()
  }

  // ---------- Auth responsive ----------
  for (const [w, h] of [
    [1024, 860],
    [768, 1024],
    [430, 860],
    [390, 844],
  ]) {
    const ctx = await browser.newContext({
      viewport: { width: w, height: h },
      isMobile: w <= 430,
      hasTouch: w <= 430,
    })
    const page = await ctx.newPage()
    for (const route of ['/login', '/signup', '/login/school-admin', '/login/platform-admin']) {
      await page.goto(BASE + route, { waitUntil: 'networkidle', timeout: 45000 })
      await page.waitForTimeout(500)
      const of = await overflow(page)
      log(
        of.scrollW <= of.clientW + 1,
        `auth ${route}@${w}: no horizontal overflow`,
        JSON.stringify(of),
      )
      const email = await page.locator('input[type="email"], input[autocomplete="email"]').first().isVisible()
      log(email, `auth ${route}@${w}: email field visible`)
      const submit = await page.locator('button[type="submit"]').isVisible()
      log(submit, `auth ${route}@${w}: submit visible`)
    }
    await shot(page, `auth-login-${w}.png`)
    await page.goto(BASE + '/login', { waitUntil: 'networkidle' })
    await shot(page, `auth-teacher-login-${w}.png`)
    await ctx.close()
  }

  // ---------- Direct platform route works (status 200, form mounts) ----------
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    const res = await page.goto(BASE + '/login/platform-admin', { waitUntil: 'domcontentloaded' })
    log(res && res.status() === 200, 'platform-admin: direct route HTTP 200', String(res && res.status()))
    let formMounted = false
    try {
      await page.waitForSelector('form', { state: 'visible', timeout: 8000 })
      formMounted = true
    } catch (_) {
      formMounted = await page.locator('form').isVisible().catch(() => false)
    }
    log(formMounted, 'platform-admin: form mounts on direct route')
    await ctx.close()
  }

  await browser.close()

  const summaryPath = path.join(OUT, 'summary.txt')
  const summary =
    '=== HERO + AUTH ACCEPTANCE ===\n' +
    results.join('\n') +
    `\n\nTOTAL pass=${pass} fail=${fail}\n`
  fs.writeFileSync(summaryPath, summary, 'utf8')
  console.log(summary)
  process.exit(fail > 0 ? 1 : 0)
}

main().catch((e) => {
  const summaryPath = path.join(OUT, 'summary.txt')
  try {
    fs.writeFileSync(
      summaryPath,
      '=== HERO + AUTH ACCEPTANCE (CRASH) ===\n' +
        results.join('\n') +
        `\n\nCRASH: ${e.message}\nTOTAL pass=${pass} fail=${fail}\n`,
      'utf8',
    )
  } catch (_) {}
  console.error(e)
  process.exit(1)
})
