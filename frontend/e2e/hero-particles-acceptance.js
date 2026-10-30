// Browser acceptance for the SchemeKnit cinematic logo hero.
//
// Covers the real landing page at desktop/mobile: initial crisp logo, the
// scroll-scrubbed particle state, reversal, the next section, reduced motion,
// no-JavaScript rendering and the static fallback when the mark image fails.
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')

const BASE = (process.env.TF_WEB_URL || 'http://localhost:3100').replace(/\/$/, '')
const OUT = path.join(__dirname, '..', '..', 'backend', 'temp', 'hero-particles-acceptance')
fs.mkdirSync(OUT, { recursive: true })

let pass = 0
let fail = 0
function log(ok, label, detail) {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? ` — ${detail}` : ''}`)
  if (ok) pass += 1
  else fail += 1
}

async function shot(page, name) {
  await page.screenshot({ path: path.join(OUT, name), fullPage: false })
}

async function waitForHero(page) {
  await page.waitForFunction(() => {
    const track = document.querySelector('[data-hero-track]')
    return track && (track.dataset.ready === 'true' || track.dataset.fallback === 'true')
  }, null, { timeout: 20000 })
}

async function state(page) {
  return page.evaluate(() => {
    const track = document.querySelector('[data-hero-track]')
    const stage = document.querySelector('[data-hero-stage]')
    const logo = document.querySelector('[data-hero-logo]')
    const copy = document.querySelector('[data-hero-copy]')
    const canvas = document.querySelector('[data-particle-canvas]')
    const intro = document.querySelector('[data-hero-intro]')
    const header = document.querySelector('[data-landing-header]')
    const heading = document.querySelector('#hero-heading')
    const cta = document.querySelector('a[href^="/login"]')
    const rect = (el) => {
      if (!el) return null
      const r = el.getBoundingClientRect()
      return { top: Math.round(r.top), bottom: Math.round(r.bottom), w: Math.round(r.width), h: Math.round(r.height) }
    }
    let painted = 0
    if (canvas) {
      const ctx = canvas.getContext('2d')
      if (ctx && canvas.width && canvas.height) {
        const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data
        for (let i = 3; i < data.length; i += 16) if (data[i] > 0) painted += 1
      }
    }
    return {
      y: Math.round(scrollY),
      phase: stage?.dataset.phase || null,
      pointer: stage?.dataset.pointer || null,
      logoOpacity: logo ? Number(getComputedStyle(logo).opacity) : null,
      logoVisibility: logo ? getComputedStyle(logo).visibility : null,
      copyOpacity: copy ? Number(getComputedStyle(copy).opacity) : null,
      canvasOpacity: canvas ? Number(getComputedStyle(canvas).opacity) : null,
      canvasDisplay: canvas ? getComputedStyle(canvas).display : null,
      canvasPointer: canvas?.parentElement ? getComputedStyle(canvas.parentElement).pointerEvents : null,
      canvasAriaHidden: canvas?.getAttribute('aria-hidden'),
      particles: Number(canvas?.dataset.particles || 0),
      painted,
      introTop: rect(intro)?.top ?? null,
      introText: intro?.textContent?.replace(/\s+/g, ' ').trim() || null,
      cardCount: document.querySelectorAll('#curriculum-pipeline, #curriculum-pipeline-section').length,
      headerVisibility: header ? getComputedStyle(header).visibility : null,
      headerOpacity: header ? Number(getComputedStyle(header).opacity) : null,
      canvasHeight: canvas ? Math.round(canvas.getBoundingClientRect().height) : null,
      heading: heading?.textContent?.replace(/\s+/g, ' ').trim() || null,
      ctaHref: cta?.getAttribute('href') || null,
      ready: track?.dataset.ready || null,
      fallback: track?.dataset.fallback || null,
      bodyH: document.body.scrollHeight,
      overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
    }
  })
}

;(async () => {
  const browser = await chromium.launch({ headless: true })

  // ── Desktop: initial, scrub, reversal, next section ──────────────────────
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    const errors = []
    page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`))
    page.on('console', (m) => { if (m.type() === 'error') errors.push(`console: ${m.text()}`) })
    await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 60000 })
    await waitForHero(page)
    await page.waitForTimeout(500)
    await shot(page, 'desktop-initial.png')

    const initial = await state(page)
    log(initial.heading?.includes('Turn Your Scheme') && initial.heading?.includes('Into the Right Lesson'), 'desktop: hero headline intact', initial.heading)
    log(initial.logoOpacity === 1 && initial.logoVisibility === 'visible', 'desktop: crisp logo is the first paint', `opacity=${initial.logoOpacity}`)
    log(initial.canvasOpacity === 0 && initial.phase === 'logo', 'desktop: particle layer starts hidden', `phase=${initial.phase} opacity=${initial.canvasOpacity}`)
    log(initial.particles >= 400, 'desktop: particle field sampled from the real mark', `particles=${initial.particles}`)
    log(initial.canvasAriaHidden === 'true' && initial.canvasPointer === 'none', 'desktop: decorative canvas is aria-hidden and non-interactive', `aria=${initial.canvasAriaHidden} pe=${initial.canvasPointer}`)
    log(initial.ctaHref?.startsWith('/login'), 'desktop: Start Planning still links to /login', String(initial.ctaHref))
    log(!initial.overflow, 'desktop: no horizontal overflow')
    log(initial.headerVisibility === 'hidden' && initial.headerOpacity === 0, 'desktop: header is absent over the intact logo', `visibility=${initial.headerVisibility}`)
    log(/One scheme\. One indicator\. One lesson\./i.test(initial.introText || ''), 'desktop: “Inside the lesson” copy is preserved', (initial.introText || '').slice(0, 80))
    log(initial.cardCount === 0, 'desktop: the old workflow card is removed', `cards=${initial.cardCount}`)
    log(initial.introTop >= 900, 'desktop: lesson intro begins below the first viewport', `top=${initial.introTop}`)
    log(initial.canvasHeight > 900, 'desktop: particle stage covers the lesson intro', `canvas=${initial.canvasHeight}`)

    await page.evaluate(() => window.scrollTo(0, 140))
    await page.waitForTimeout(400)
    await shot(page, 'desktop-scrub-140.png')
    const early = await state(page)
    log(early.headerVisibility === 'visible' && early.headerOpacity > 0.5, 'desktop: header appears after a small scroll', `opacity=${early.headerOpacity}`)
    log(early.phase === 'dispersion', 'desktop: scrolling begins the disintegration', `phase=${early.phase}`)
    log(early.logoOpacity === 0, 'desktop: DOM logo hands over to particles', `opacity=${early.logoOpacity}`)
    log(early.canvasOpacity > 0.5 && early.painted > 100, 'desktop: particle field is visible and painted', `opacity=${early.canvasOpacity} painted=${early.painted}`)
    log(early.introTop < 900, 'desktop: lesson intro is visible during the transition', `top=${early.introTop}`)

    await page.evaluate(() => window.scrollTo(0, 340))
    await page.waitForTimeout(400)
    await shot(page, 'desktop-scrub-340.png')
    const movingA = await page.evaluate(() => {
      const c = document.querySelector('[data-particle-canvas]')
      const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data
      let s = 0
      for (let i = 0; i < d.length; i += 64) s += d[i] + d[i + 1] + d[i + 2] + d[i + 3]
      return s
    })
    await page.waitForTimeout(650)
    const movingB = await page.evaluate(() => {
      const c = document.querySelector('[data-particle-canvas]')
      const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data
      let s = 0
      for (let i = 0; i < d.length; i += 64) s += d[i] + d[i + 1] + d[i + 2] + d[i + 3]
      return s
    })
    log(movingA !== movingB, 'desktop: particle cloud keeps moving without scrolling', `${movingA} → ${movingB}`)
    const mid = await state(page)
    log(['dispersion', 'dissipation'].includes(mid.phase), 'desktop: mid-scroll is a coherent particle expansion', `phase=${mid.phase}`)
    log(mid.copyOpacity >= 0.9, 'desktop: copy remains readable while particles expand', `copy=${mid.copyOpacity}`)
    log(mid.introTop < 700, 'desktop: lesson intro rises with the hero', `top=${mid.introTop}`)

    await page.evaluate(() => window.scrollTo(0, 600))
    await page.waitForTimeout(450)
    const fading = await state(page)
    log(fading.copyOpacity < 1 && fading.copyOpacity > 0, 'desktop: copy fades as the hero leaves', `copy=${fading.copyOpacity}`)
    log(fading.introTop < 400, 'desktop: lesson intro is in view while particles remain', `top=${fading.introTop}`)
    log(fading.canvasOpacity > 0.5, 'desktop: particles still cover the intro', `opacity=${fading.canvasOpacity}`)

    // Cursor response over the particle field (including the intro area).
    await page.mouse.move(720, 360)
    await page.mouse.move(880, 430, { steps: 12 })
    await page.waitForTimeout(500)
    const pointerState = await state(page)
    log(
      pointerState.pointer === 'active',
      'desktop: cursor activates the particle lens',
      `pointer=${pointerState.pointer}`,
    )
    await shot(page, 'desktop-pointer.png')
    await page.mouse.move(80, 80)
    await page.waitForTimeout(350)

    await page.evaluate(() => window.scrollTo(0, 950))
    await page.waitForTimeout(500)
    await shot(page, 'desktop-scrub-950.png')
    const late = await state(page)
    log(['dissipation', 'complete'].includes(late.phase), 'desktop: particles dissipate before completion', `phase=${late.phase}`)
    log(late.canvasOpacity < 0.6, 'desktop: particle density falls away', `opacity=${late.canvasOpacity}`)

    await page.evaluate(() => window.scrollTo(0, 0))
    await page.waitForTimeout(500)
    await shot(page, 'desktop-restored.png')
    const restored = await state(page)
    log(restored.phase === 'logo' && restored.logoOpacity === 1, 'desktop: scrolling back restores the logo', `phase=${restored.phase} opacity=${restored.logoOpacity}`)
    log(restored.canvasOpacity === 0 && restored.copyOpacity === 1, 'desktop: scrolling back restores copy and hides particles', `canvas=${restored.canvasOpacity} copy=${restored.copyOpacity}`)
    log(restored.headerVisibility === 'hidden', 'desktop: header hides again at the top', `visibility=${restored.headerVisibility}`)

    // The secondary CTA must still reach the next content section.
    await page.getByRole('link', { name: 'See How It Works' }).click()
    await page.waitForFunction(() => {
      const target = document.getElementById('how-it-works')
      if (!target) return false
      const r = target.getBoundingClientRect()
      return r.top < window.innerHeight && r.bottom > 0
    }, null, { timeout: 12000 })
    log(true, 'desktop: See How It Works reaches the workflow section')
    log(errors.length === 0, 'desktop: no page or console errors', errors.slice(0, 2).join(' | ') || 'none')
    await ctx.close()
  }

  // ── Mobile ───────────────────────────────────────────────────────────────
  for (const [w, h, label] of [[390, 844, '390'], [375, 667, '375x667']]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: true, hasTouch: true })
    const page = await ctx.newPage()
    await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 60000 })
    await waitForHero(page)
    await page.waitForTimeout(400)
    await shot(page, `mobile-${label}-initial.png`)
    const initial = await state(page)
    log(initial.logoOpacity === 1 && initial.heading?.includes('Turn Your Scheme'), `mobile ${label}: logo and heading visible`, `logo=${initial.logoOpacity}`)
    log(!initial.overflow, `mobile ${label}: no horizontal overflow`)
    log(initial.particles >= 300, `mobile ${label}: particle field built`, `particles=${initial.particles}`)
    const ctaVisible = await page.locator('[data-hero-copy]').getByRole('link', { name: 'Start Planning' }).isVisible()
    log(ctaVisible, `mobile ${label}: primary CTA visible`)

    await page.evaluate(() => window.scrollTo(0, Math.round(window.innerHeight * 0.28)))
    await page.waitForTimeout(400)
    await shot(page, `mobile-${label}-scrub.png`)
    const scrub = await state(page)
    log(scrub.phase === 'dispersion' || scrub.phase === 'dissipation', `mobile ${label}: scroll drives the particle transition`, `phase=${scrub.phase}`)
    log(scrub.canvasOpacity > 0.4 && scrub.painted > 80, `mobile ${label}: particles are visible on screen`, `opacity=${scrub.canvasOpacity} painted=${scrub.painted}`)
    log(scrub.introTop < h, `mobile ${label}: lesson intro is visible during the transition`, `top=${scrub.introTop}`)
    await ctx.close()
  }

  // ── Reduced motion ───────────────────────────────────────────────────────
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' })
    const page = await ctx.newPage()
    await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 60000 })
    await waitForHero(page)
    await page.waitForTimeout(500)
    await shot(page, 'reduced-motion.png')
    const reduced = await state(page)
    const stagePosition = await page.locator('[data-hero-stage]').evaluate((el) => getComputedStyle(el).position)
    log(stagePosition === 'relative', 'reduced-motion: no pinned hero stage', `position=${stagePosition}`)
    log(reduced.canvasDisplay === 'none', 'reduced-motion: particle canvas is not rendered', String(reduced.canvasDisplay))
    log(reduced.logoOpacity === 1 && reduced.copyOpacity === 1, 'reduced-motion: logo and copy stay complete', `logo=${reduced.logoOpacity} copy=${reduced.copyOpacity}`)
    await page.evaluate(() => window.scrollTo(0, 300))
    await page.waitForTimeout(300)
    const afterScroll = await state(page)
    log(afterScroll.logoOpacity === 1, 'reduced-motion: scrolling does not animate the logo away', `opacity=${afterScroll.logoOpacity}`)
    log(!afterScroll.overflow, 'reduced-motion: no horizontal overflow')
    await ctx.close()
  }

  // ── No JavaScript ────────────────────────────────────────────────────────
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, javaScriptEnabled: false })
    const page = await ctx.newPage()
    await page.goto(BASE + '/', { waitUntil: 'load', timeout: 60000 })
    const heading = await page.locator('#hero-heading').innerText().catch(() => '')
    const logoVisible = await page.locator('[data-hero-logo]').isVisible().catch(() => false)
    log(/Turn Your Scheme/i.test(heading), 'no-JS: server-rendered hero heading is present', heading.replace(/\s+/g, ' ').trim())
    log(logoVisible, 'no-JS: static logo is present')
    log(await page.locator('[data-hero-copy]').getByRole('link', { name: 'Start Planning' }).isVisible(), 'no-JS: primary CTA remains usable')
    await shot(page, 'no-js.png')
    await ctx.close()
  }

  // ── Image failure fallback ───────────────────────────────────────────────
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    await page.route('**/icons/icon-512.png', (route) => route.abort())
    await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 60000 })
    await page.waitForFunction(() => document.querySelector('[data-hero-track]')?.dataset.fallback === 'true', null, { timeout: 15000 })
    const fallback = await state(page)
    log(fallback.fallback === 'true', 'fallback: mark image failure is detected')
    log(fallback.canvasDisplay === 'none' && fallback.logoOpacity === 1, 'fallback: static logo remains and canvas is hidden', `display=${fallback.canvasDisplay} logo=${fallback.logoOpacity}`)
    log(!fallback.overflow, 'fallback: no horizontal overflow')
    await shot(page, 'fallback.png')
    await ctx.close()
  }

  // ── Canvas context failure fallback ──────────────────────────────────────
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    await ctx.addInitScript(() => {
      HTMLCanvasElement.prototype.getContext = () => null
    })
    const page = await ctx.newPage()
    await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 60000 })
    const fallback = await state(page)
    log(fallback.fallback === 'true', 'fallback: canvas context failure is detected')
    log(fallback.logoOpacity === 1 && fallback.copyOpacity === 1, 'fallback: content remains visible without canvas', `logo=${fallback.logoOpacity} copy=${fallback.copyOpacity}`)
    await ctx.close()
  }

  // ── Resize / orientation ─────────────────────────────────────────────────
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()
    await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 60000 })
    await waitForHero(page)
    await page.setViewportSize({ width: 390, height: 844 })
    await page.waitForTimeout(600)
    const resized = await state(page)
    const canvasSize = await page.locator('[data-particle-canvas]').evaluate((el) => ({ w: el.width, h: el.height, cssW: el.getBoundingClientRect().width }))
    log(!resized.overflow, 'resize: no horizontal overflow after desktop → mobile')
    log(Math.abs(canvasSize.cssW - 390) < 2, 'resize: canvas re-fits the mobile stage', JSON.stringify(canvasSize))
    await page.evaluate(() => window.scrollTo(0, 180))
    await page.waitForTimeout(350)
    const resizedScroll = await state(page)
    log(resizedScroll.phase !== 'logo' && resizedScroll.canvasOpacity > 0.3, 'resize: scroll transition still works after resize', `phase=${resizedScroll.phase} opacity=${resizedScroll.canvasOpacity}`)
    await ctx.close()
  }

  await browser.close()
  console.log(`\n${pass} passed, ${fail} failed — artefacts in ${OUT}`)
  process.exit(fail ? 1 : 0)
})().catch((error) => {
  console.error('ERROR', error)
  process.exit(2)
})
