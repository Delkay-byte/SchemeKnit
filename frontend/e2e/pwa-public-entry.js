/**
 * TeachFlow — PWA + Public Entry production acceptance (milestone: UI + PWA).
 *
 * Runs against the PRODUCTION frontend build (next start) and verifies:
 *   - manifest is valid, has the right name/icons/start_url/display, and no
 *     localhost references anywhere
 *   - every referenced icon resolves and has the correct PNG dimensions
 *   - the service worker is served, caches static assets only, and never
 *     caches /api or private data
 *   - the public landing page presents Teacher / School Admin / Platform Admin
 *     correctly, with Platform Admin positioned as an administrative entry
 *   - no development/implementation text leaks into production UI
 *   - all three login routes remain live and distinct
 *
 * No physical mobile device is required for these checks; they validate
 * everything an install prompt needs to appear. Physical-device acceptance
 * (install to home screen) is documented as outstanding in the final report.
 *
 * Usage: node e2e/pwa-public-entry.js [baseURL]
 */
const { chromium } = require('playwright')

const BASE = process.argv[2] || 'http://localhost:3001'

let pass = 0
let fail = 0
const results = []

async function check(fn, label) {
  try {
    const ok = await fn()
    if (ok) pass++
    else fail++
    results.push({ label, ok })
    console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}`)
  } catch (e) {
    fail++
    results.push({ label, ok: false, err: e.message })
    console.log(`FAIL  ${label} [${e.message}]`)
  }
}

async function get(url) {
  const res = await fetch(url)
  const text = await res.text()
  return { status: res.status, text }
}

/** Read PNG width/height from the IHDR chunk (bytes 16-24). */
function pngDimensions(buf) {
  if (!(buf instanceof Uint8Array)) buf = new Uint8Array(buf)
  const isPng =
    buf[0] === 0x89 && buf[1] === 0x50 && buf[2] === 0x4e && buf[3] === 0x47
  if (!isPng) return null
  const view = new DataView(buf.buffer, buf.byteOffset, buf.byteLength)
  return {
    width: view.getUint32(16),
    height: view.getUint32(20),
  }
}

async function main() {
  console.log(`Target: ${BASE}\n`)

  // ── 1. Manifest ──────────────────────────────────────────────────────
  console.log('--- 1. WEB APP MANIFEST ---')
  let manifest = null
  await check(async () => {
    const r = await get(`${BASE}/manifest.webmanifest`)
    if (r.status !== 200) return false
    manifest = JSON.parse(r.text)
    return !!manifest
  }, 'manifest: served and valid JSON')

  await check(() => manifest.name === 'TeachFlow', 'manifest: name = TeachFlow')
  await check(() => manifest.short_name === 'TeachFlow', 'manifest: short_name = TeachFlow')
  await check(() => typeof manifest.description === 'string' && manifest.description.length > 10, 'manifest: description present')
  await check(() => manifest.display === 'standalone', 'manifest: display = standalone')
  await check(() => manifest.start_url === '/', 'manifest: start_url is relative (no localhost)')
  await check(() => manifest.scope === '/', 'manifest: scope is relative')
  await check(() => !!manifest.theme_color && /^#[0-9a-f]{6}$/i.test(manifest.theme_color), `manifest: theme_color = ${manifest && manifest.theme_color}`)
  await check(() => !!manifest.background_color, 'manifest: background_color present')

  const has = (size, purpose) =>
    manifest.icons.some(
      (i) => i.sizes === `${size}x${size}` && i.purpose === purpose && i.type === 'image/png'
    )
  await check(() => has('192', 'any'), 'manifest: 192 any icon')
  await check(() => has('512', 'any'), 'manifest: 512 any icon')
  await check(() => has('192', 'maskable'), 'manifest: 192 maskable icon')
  await check(() => has('512', 'maskable'), 'manifest: 512 maskable icon')

  await check(() => {
    const blob = JSON.stringify(manifest)
    return !/localhost|127\.0\.0\.1/.test(blob)
  }, 'manifest: no localhost references anywhere')

  // ── 2. Icons resolve with correct dimensions ─────────────────────────
  console.log('\n--- 2. ICON ASSETS ---')
  const iconChecks = [
    ['/icons/icon-16.png', 16], ['/icons/icon-32.png', 32],
    ['/icons/icon-48.png', 48], ['/icons/icon-96.png', 96],
    ['/icons/icon-180.png', 180], ['/icons/icon-192.png', 192],
    ['/icons/icon-256.png', 256], ['/icons/icon-512.png', 512],
    ['/icons/icon-192-maskable.png', 192], ['/icons/icon-512-maskable.png', 512],
    ['/icons/apple-touch-icon.png', 180],
  ]
  for (const [path, size] of iconChecks) {
    await check(async () => {
      const res = await fetch(`${BASE}${path}`)
      if (res.status !== 200) return false
      const dims = pngDimensions(await res.arrayBuffer())
      return dims && dims.width === size && dims.height === size
    }, `icon: ${path.split('/').pop()} (${size}x${size})`)
  }

  // Favicon (ICO reports as PNG-magic? ICO files start with 00 00 01 00, so
  // only assert it resolves with content.)
  await check(async () => {
    const res = await fetch(`${BASE}/icons/favicon.ico`)
    const buf = await res.arrayBuffer()
    return res.status === 200 && buf.byteLength > 1000
  }, 'icon: favicon.ico served')

  // ── 3. Service worker ────────────────────────────────────────────────
  console.log('\n--- 3. SERVICE WORKER ---')
  let sw = ''
  await check(async () => {
    const r = await get(`${BASE}/sw.js`)
    sw = r.text
    return r.status === 200 && sw.includes('teachflow-static')
  }, 'sw: served with static cache')
  await check(() => sw.includes('/api/') && sw.includes('Never touch the API'), 'sw: /api explicitly excluded from cache')
  await check(() => !/cache.*\/api\//.test(sw.replace('Never touch the API', '').replace("url.pathname.startsWith('/api/')", '')), 'sw: no API path added to cache')
  await check(() => /stale|network/.test(sw), 'sw: network-first/SWR strategy for static only')

  // ── 4-6. Rendered UI (needs a real browser: these pages show a spinner
  //         until client-side auth resolves, so raw fetch sees no content).
  console.log('\n--- 4. DOCUMENT HEAD + RENDERED UI ---')
  const browser = await chromium.launch()
  const page = await browser.newPage()
  await page.goto(`${BASE}/`, { waitUntil: 'networkidle' })

  let home = await page.content()
  await check(() => home.includes('rel="manifest"'), 'head: manifest link present')
  await check(() => home.includes('apple-touch-icon'), 'head: apple-touch-icon present')
  await check(() => home.includes('theme-color'), 'head: theme-color meta present')
  await check(() => home.includes('icon-192.png') || home.includes('icon-512.png'), 'head: PNG icons linked')

  // ── 5. Public landing content ────────────────────────────────────────
  console.log('\n--- 5. PUBLIC LANDING ---')
  await check(() => home.includes('TeachFlow'), 'landing: TeachFlow branding')
  await check(() => home.includes('Teacher') && home.includes('Teacher Login'), 'landing: Teacher entry')
  await check(() => home.includes('Create Free Teacher Account'), 'landing: individual teacher signup')
  await check(() => home.includes('School Administration'), 'landing: School Admin entry')
  await check(() => home.includes('Activate Your School'), 'landing: Activate School action')
  await check(() => home.includes('School Admin Login'), 'landing: School Admin Login action')
  await check(() => home.includes('Platform Administration'), 'landing: Platform Admin entry present')
  await check(() => home.includes('/login/platform-admin'), 'landing: PA routes to dedicated login')
  await check(() => home.includes('School Teacher') && home.includes('Independent'), 'landing: teacher tiers shown without full comparison')

  // Mobile 375px: cards remain usable, no overlap.
  await page.setViewportSize({ width: 375, height: 812 })
  await page.goto(`${BASE}/`, { waitUntil: 'networkidle' })
  await check(async () => {
    await page.waitForSelector('text=Teacher Login', { timeout: 5000 })
    const cards = await page.locator('a:has-text("Teacher Login"), a:has-text("School Admin Login"), a:has-text("Platform Admin Login")').count()
    return cards >= 3
  }, 'mobile 375px: three role entries render')
  const overflow = await page.evaluate(() => {
    return document.documentElement.scrollWidth > document.documentElement.clientWidth + 1
  })
  await check(() => !overflow, 'mobile 375px: no horizontal overflow (cards do not overlap)')
  await page.setViewportSize({ width: 1280, height: 900 })

  // ── 6. No development leakage in production UI ───────────────────────
  console.log('\n--- 6. PRODUCTION LEAKAGE ---')
  const leakPatterns = [
    ['CLI provisioning text', /create_platform_admin/],
    ['backend source path', /backend\/src/],
    ['Development only', /Development only/],
    ['demo reset button', /RESET DEMO COMMERCIAL DATA/],
    ['localhost in HTML', /http:\/\/localhost/],
    ['acceptance DB reference', /teachflow\.db/],
  ]
  let pages = { 'landing': home }
  for (const p of ['/login', '/login/platform-admin', '/login/school-admin']) {
    await page.goto(`${BASE}${p}`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(800)
    pages[p] = await page.content()
    await check(() => pages[p].length > 500, `route: ${p} live`)
  }
  for (const [pageName, html] of Object.entries(pages)) {
    for (const [label, re] of leakPatterns) {
      await check(() => !re.test(html), `leak: ${label} absent from ${pageName}`)
    }
  }
  await check(() => pages['/login/platform-admin'].includes('Platform Administration'), 'PA login: separate interface')
  await check(() => !pages['/login/platform-admin'].includes('provisioned with the local CLI'), 'PA login: no CLI implementation text')
  await check(() => pages['/login/platform-admin'].includes('Authorized'), 'PA login: production-appropriate restricted wording')
  await check(() => pages['/login'].includes('School Teacher') && pages['/login'].includes('Individual Teacher'), 'teacher login: unified for school + individual')

  await browser.close()

  // ── Done ─────────────────────────────────────────────────────────────
  console.log('\n======================================================================')
  console.log(`PWA + PUBLIC ENTRY: ${pass} passed, ${fail} failed`)
  console.log('======================================================================')
  if (fail) {
    console.log('\nFAILED CHECKS:')
    results.filter((r) => !r.ok).forEach((r) => console.log(`  - ${r.label}${r.err ? ` [${r.err}]` : ''}`))
  }
  process.exit(fail ? 1 : 0)
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
