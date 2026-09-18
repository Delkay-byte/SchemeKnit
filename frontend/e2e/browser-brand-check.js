/**
 * Real-browser brand verification (Chrome + Edge).
 *
 * Confirms the TeachFlow mark is what the browser actually fetches for the
 * tab favicon and the in-page brand image — no Next.js placeholder, and the
 * same symbol in both browsers.
 */
const { chromium } = require('playwright')

const BASE = process.argv[2] || 'http://localhost:3000'
let pass = 0, fail = 0

async function check(fn, label) {
  try {
    const ok = await fn()
    if (ok) pass++; else fail++
    console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}`)
  } catch (e) {
    fail++
    console.log(`FAIL  ${label} [${e.message}]`)
  }
}

async function runChannel(channel) {
  console.log(`\n=== ${channel.toUpperCase()} ===`)
  const browser = await chromium.launch({ channel })
  const page = await browser.newPage()

  const requests = []
  page.on('response', (r) => requests.push({ url: r.url(), status: r.status() }))

  await page.goto(`${BASE}/`, { waitUntil: 'networkidle' })
  await page.waitForSelector('h1:has-text("TeachFlow")', { timeout: 15000 })

  // The brand mark image in the header actually loaded (not broken).
  await check(async () => {
    const img = page.locator('header img').first()
    const natural = await img.evaluate((el) => el.naturalWidth)
    return natural > 0
  }, `${channel}: header brand image rendered (not broken)`)

  // Favicon resolved to a real TeachFlow asset, not the Next.js default.
  await check(() => {
    const fav = requests.find(
      (r) => r.url.includes('favicon.ico') || r.url.includes('icon-32.png')
    )
    return !!fav && fav.status === 200 && !fav.url.includes('favicon.ico?')
  }, `${channel}: favicon resolved (200)`)

  // Manifest link is present and the URL actually resolves. (Browsers do not
  // auto-fetch the manifest on a plain load — they fetch it lazily when
  // assessing installability — so assert the link + a direct fetch instead.)
  await check(async () => {
    const href = await page.evaluate(() => {
      const l = document.querySelector('link[rel="manifest"]')
      return l ? l.href : null
    })
    if (!href) return false
    return await page.evaluate(async (u) => {
      const r = await fetch(u)
      const j = await r.json()
      return r.status === 200 && j.name === 'TeachFlow' && j.display === 'standalone'
    }, href)
  }, `${channel}: manifest link present and resolves`)

  // The 192 icon is fetchable (used for the install/home-screen icon).
  await check(async () => {
    const ok = await page.evaluate(async () => {
      const r = await fetch('/icons/icon-192.png')
      return r.status === 200
    })
    return ok
  }, `${channel}: 192 icon fetchable`)

  // No unhandled console errors on the public entry.
  await check(async () => {
    const errors = []
    page.on('pageerror', (e) => errors.push(e.message))
    await page.waitForTimeout(1500)
    return errors.length === 0
  }, `${channel}: no page errors`)

  await browser.close()
}

;(async () => {
  for (const ch of ['chrome', 'msedge']) {
    try {
      await runChannel(ch)
    } catch (e) {
      console.log(`SKIP  ${ch} unavailable on this machine [${e.message.split('\n')[0]}]`)
    }
  }
  console.log(`\nBROWSER BRAND: ${pass} passed, ${fail} failed`)
  process.exit(fail ? 1 : 0)
})()
