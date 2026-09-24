/**
 * APMIX interaction study — observes live rendered behavior only.
 * Does NOT extract or copy proprietary source code.
 * Usage: node e2e/apmix-study.js
 */
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')

const URL = process.env.APMIX_URL || 'https://apmix.ai/'
const OUT = path.join(__dirname, 'apmix-study')
fs.mkdirSync(OUT, { recursive: true })

async function probe(page) {
  return page.evaluate(() => {
    const canvases = Array.from(document.querySelectorAll('canvas'))
    const svgs = document.querySelectorAll('svg')
    const videos = document.querySelectorAll('video')
    const glInfo = canvases.map((c) => {
      let type = null
      try {
        // If a context already exists, getContext returns it; try webgl2 first.
        const gl = c.getContext('webgl2') || c.getContext('webgl') || c.getContext('experimental-webgl')
        type = gl ? 'webgl' : '2d-or-other'
        if (gl) {
          const dbg = gl.getExtension('WEBGL_debug_renderer_info')
          return {
            w: c.width,
            h: c.height,
            cssW: c.style.width || getComputedStyle(c).width,
            cssH: c.style.height || getComputedStyle(c).height,
            context: type,
            renderer: dbg ? String(gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL)) : 'n/a',
          }
        }
      } catch (_) {}
      // Canvas 2D: getContext('2d') after webgl fails returns null if locked to webgl
      let is2d = false
      try {
        is2d = !!c.getContext('2d')
      } catch (_) {}
      return {
        w: c.width,
        h: c.height,
        cssW: c.style.width || getComputedStyle(c).width,
        cssH: c.style.height || getComputedStyle(c).height,
        context: is2d ? '2d' : type || 'unknown',
        renderer: null,
      }
    })

    // Sample pixel colors around center of first large canvas for later diff
    function sampleCanvas(canvas, grid = 12) {
      try {
        const ctx = canvas.getContext('2d')
        if (!ctx) return null
        const w = Math.min(canvas.width, 400)
        const h = Math.min(canvas.height, 300)
        const d = ctx.getImageData(0, 0, w, h).data
        let sum = 0
        let bright = 0
        for (let i = 0; i < d.length; i += 16) {
          const a = d[i + 3]
          sum += d[i] + d[i + 1] + d[i + 2] + a
          if (a > 10) bright++
        }
        return { sum, bright, samples: Math.floor(d.length / 16) }
      } catch (e) {
        return { error: String(e) }
      }
    }

    const heroCandidates = Array.from(
      document.querySelectorAll('section, [class*="hero"], [class*="Hero"], main > div, body > div'),
    ).slice(0, 8).map((el) => {
      const r = el.getBoundingClientRect()
      const cs = getComputedStyle(el)
      return {
        tag: el.tagName,
        cls: String(el.className || '').slice(0, 80),
        w: Math.round(r.width),
        h: Math.round(r.height),
        overflow: cs.overflow,
        position: cs.position,
      }
    })

    return {
      title: document.title,
      url: location.href,
      canvasCount: canvases.length,
      canvases: glInfo,
      svgCount: svgs.length,
      videoCount: videos.length,
      bodyBg: getComputedStyle(document.body).backgroundColor,
      hasWebGLContextType: canvases.some((c) => {
        try {
          return !!(c.getContext('webgl2') || c.getContext('webgl'))
        } catch (_) {
          return false
        }
      }),
      // Text content that might describe the product (no source scraping)
      h1: document.querySelector('h1')?.innerText?.slice(0, 120) || '',
      heroCandidates,
      canvasSample: canvases[0] ? sampleCanvas(canvases[0]) : null,
      dpr: window.devicePixelRatio,
      viewport: { w: window.innerWidth, h: window.innerHeight },
      // Count DOM nodes as a complexity proxy (not source)
      domNodeCount: document.querySelectorAll('*').length,
    }
  })
}

async function sampleHeroPixels(page) {
  return page.evaluate(() => {
    const canvas = Array.from(document.querySelectorAll('canvas'))
      .map((c) => ({ c, r: c.getBoundingClientRect() }))
      .filter((x) => x.r.width > 200 && x.r.height > 150)
      .sort((a, b) => b.r.width * b.r.height - a.r.width * a.r.height)[0]
    if (!canvas) return null
    const c = canvas.c
    const rect = canvas.r
    // Prefer 2d path
    let ctx = null
    try {
      ctx = c.getContext('2d')
    } catch (_) {}
    if (!ctx) {
      // WebGL — sample via readPixels if possible
      try {
        const gl = c.getContext('webgl') || c.getContext('webgl2')
        if (!gl) return { mode: 'none', rect }
        const w = Math.min(gl.drawingBufferWidth, 320)
        const h = Math.min(gl.drawingBufferHeight, 240)
        const pixels = new Uint8Array(w * h * 4)
        gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, pixels)
        let sum = 0
        let nonZero = 0
        for (let i = 0; i < pixels.length; i += 4) {
          sum += pixels[i] + pixels[i + 1] + pixels[i + 2] + pixels[i + 3]
          if (pixels[i + 3] > 0) nonZero++
        }
        return {
          mode: 'webgl-readPixels',
          rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
          buffer: { w: gl.drawingBufferWidth, h: gl.drawingBufferHeight },
          sum,
          nonZero,
        }
      } catch (e) {
        return { mode: 'webgl-error', error: String(e) }
      }
    }
    const w = Math.min(c.width, 360)
    const h = Math.min(c.height, 260)
    const d = ctx.getImageData(0, 0, w, h).data
    let sum = 0
    let alpha = 0
    for (let i = 0; i < d.length; i += 16) {
      sum += d[i] + d[i + 1] + d[i + 2]
      alpha += d[i + 3]
    }
    return {
      mode: '2d',
      rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
      buffer: { w: c.width, h: c.height },
      sum,
      alpha,
    }
  })
}

async function measurePointerResponse(page) {
  const before = await sampleHeroPixels(page)
  const vp = page.viewportSize()
  const cx = Math.round(vp.width * 0.62)
  const cy = Math.round(vp.height * 0.42)
  // Move in steps to generate continuous interaction
  for (let i = 0; i < 18; i++) {
    await page.mouse.move(cx - 80 + i * 8, cy - 40 + i * 4)
    await page.waitForTimeout(30)
  }
  await page.waitForTimeout(80)
  const during = await sampleHeroPixels(page)
  // Stop and wait for settle
  await page.waitForTimeout(900)
  const settled = await sampleHeroPixels(page)
  // Leave
  await page.mouse.move(20, vp.height - 20)
  await page.waitForTimeout(1100)
  const left = await sampleHeroPixels(page)
  return { before, during, settled, left }
}

;(async () => {
  const browser = await chromium.launch({ headless: true })
  const results = []

  for (const [w, h, label] of [
    [1440, 900, 'desktop'],
    [768, 1024, 'tablet'],
    [390, 844, 'mobile'],
  ]) {
    const ctx = await browser.newContext({
      viewport: { width: w, height: h },
      isMobile: w <= 430,
      hasTouch: w <= 430,
      userAgent: w <= 430
        ? undefined
        : 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    })
    const page = await ctx.newPage()
    const consoleErr = []
    page.on('pageerror', (e) => consoleErr.push(e.message))
    const scripts = []
    page.on('response', (r) => {
      const u = r.url()
      if (/\.(js|mjs)(\?|$)/.test(u) || u.includes('chunk') || u.includes('webpack')) {
        scripts.push({ url: u.split('/').slice(-2).join('/'), status: r.status(), len: 0 })
      }
    })

    try {
      await page.goto(URL, { waitUntil: 'networkidle', timeout: 60000 })
    } catch (e) {
      await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {})
    }
    await page.waitForTimeout(2500)
    await page.screenshot({ path: path.join(OUT, `${label}-initial.png`), fullPage: false })

    const info = await probe(page)
    results.push({ label, ...info, consoleErr: consoleErr.slice(0, 5), scriptCount: scripts.length })

    if (w >= 1024) {
      const pointer = await measurePointerResponse(page)
      results[results.length - 1].pointer = pointer
      await page.screenshot({ path: path.join(OUT, `${label}-after-pointer.png`) })
    }

    // Reduced motion
    if (w === 1440) {
      await ctx.close()
      const rm = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' })
      const p2 = await rm.newPage()
      try {
        await p2.goto(URL, { waitUntil: 'networkidle', timeout: 60000 })
      } catch (_) {
        await p2.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {})
      }
      await p2.waitForTimeout(2000)
      const rmInfo = await probe(p2)
      results.push({ label: 'reduced-motion', ...rmInfo })
      await p2.screenshot({ path: path.join(OUT, 'reduced-motion.png') })
      await rm.close()
      continue
    }
    await ctx.close()
  }

  // Try to observe DOM structure depth without dumping full source
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()
  try {
    await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 })
    await page.waitForTimeout(2000)
    const structure = await page.evaluate(() => {
      // Class name frequency only (behavioral fingerprint, not full source)
      const counts = {}
      document.querySelectorAll('[class]').forEach((el) => {
        String(el.className)
          .split(/\s+/)
          .filter(Boolean)
          .forEach((c) => {
            counts[c] = (counts[c] || 0) + 1
          })
      })
      const top = Object.entries(counts)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 40)
        .map(([c, n]) => `${c}:${n}`)
      // Stylesheets count
      return {
        topClasses: top,
        styleSheets: document.styleSheets.length,
        // Detect common libs by global markers without reading code
        globals: {
          THREE: typeof window.THREE !== 'undefined',
          gsap: typeof window.gsap !== 'undefined',
          jQuery: typeof window.jQuery !== 'undefined',
          PIXI: typeof window.PIXI !== 'undefined',
          p5: typeof window.p5 !== 'undefined',
          matter: typeof window.Matter !== 'undefined',
          fabric: typeof window.fabric !== 'undefined',
          FramerMotion: typeof window.__FRAMER_MOTION__ !== 'undefined',
          next: typeof window.__NEXT_DATA__ !== 'undefined' || !!document.querySelector('#__next'),
          nuxt: !!document.querySelector('#__nuxt'),
          gatsby: !!document.querySelector('#___gatsby'),
        },
        // Meta generator
        generator: document.querySelector('meta[name="generator"]')?.content || null,
        // canvas z / pointer-events
        canvasStyles: Array.from(document.querySelectorAll('canvas')).map((c) => {
          const cs = getComputedStyle(c)
          const r = c.getBoundingClientRect()
          return {
            position: cs.position,
            zIndex: cs.zIndex,
            pe: cs.pointerEvents,
            opacity: cs.opacity,
            mixBlend: cs.mixBlendMode,
            w: Math.round(r.width),
            h: Math.round(r.height),
            transform: cs.transform,
          }
        }),
        // Does pointer-events pass through full page?
        htmlPE: getComputedStyle(document.documentElement).pointerEvents,
        bodyPE: getComputedStyle(document.body).pointerEvents,
      }
    })
    results.push({ label: 'structure', ...structure })
  } catch (e) {
    results.push({ label: 'structure-error', error: String(e) })
  }
  await ctx.close()

  await browser.close()
  const outPath = path.join(OUT, 'study.json')
  fs.writeFileSync(outPath, JSON.stringify(results, null, 2), 'utf8')
  console.log(JSON.stringify(results, null, 2))
  console.log('Wrote', outPath)
})().catch((e) => {
  console.error(e)
  process.exit(1)
})
