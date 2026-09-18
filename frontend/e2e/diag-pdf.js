/**
 * Diagnostic: PDF export only. Logs response status, blob type/size, and
 * whether an 'a'-click download event fires.
 */
const { chromium } = require('playwright')
const path = require('path')

const CHANNEL = process.argv[2] || 'chrome'
const WEB = process.env.TF_WEB_URL || 'http://localhost:3000'
const SCHEME_ID = process.env.TF_SCHEME_ID
const TEACHER = { email: 'teacher@acceptance.test', password: 'TeacherPass123' }
const OUT = path.resolve(__dirname, '..', '..', 'backend', 'temp', 'ba', 'downloads')

;(async () => {
  const browser = await chromium.launch({ channel: CHANNEL, downloadsPath: OUT })
  const context = await browser.newContext({ acceptDownloads: true })
  const page = await context.newPage()

  page.on('console', (m) => { if (m.type() === 'error') console.log('  [console.error FULL]', m.text()) })
  page.on('download', (d) => console.log('  [download event]', d.suggestedFilename()))

  await page.goto(`${WEB}/login/`, { waitUntil: 'domcontentloaded' })
  await page.fill('input[type="email"]', TEACHER.email)
  await page.fill('input[type="password"]', TEACHER.password)
  await page.click('button[type="submit"]')
  await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 30000 })

  await page.goto(`${WEB}/generate/${SCHEME_ID}/`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('button:has-text("Download PDF")', { timeout: 30000 })

  // Instrument fetch + anchor clicks inside the page
  await page.evaluate(() => {
    window.__diag = { fetches: [], clicks: 0 }
    const origFetch = window.fetch
    window.fetch = async (...args) => {
      const res = await origFetch(...args)
      const url = String(args[0])
      if (url.includes('/export/pdf')) {
        const clone = res.clone()
        const blob = await clone.blob()
        window.__diag.fetches.push({ status: res.status, type: res.headers.get('content-type'), size: blob.size, blobType: blob.type })
      }
      return res
    }
    const origClick = HTMLAnchorElement.prototype.click
    HTMLAnchorElement.prototype.click = function () {
      if (this.download) {
        window.__diag.clicks++
        console.log('  [page] anchor click download=', this.download, 'href type=', this.href.slice(0, 40))
      }
      return origClick.call(this)
    }
  })

  console.log(`\n=== PDF diagnostic (${CHANNEL}) ===`)
  await page.click('button:has-text("Download PDF")')
  await page.waitForTimeout(60000)

  const diag = await page.evaluate(() => window.__diag)
  console.log('fetches:', JSON.stringify(diag.fetches))
  console.log('anchor clicks with download attr:', diag.clicks)

  const body = await page.locator('body').innerText()
  const errLine = body.split('\n').find((l) => /pdf|failed|error/i.test(l))
  console.log('visible pdf-ish line:', errLine ? errLine.slice(0, 160) : '(none)')

  await browser.close().catch(() => {})
})().catch((e) => { console.error('diag failed:', e.message); process.exit(1) })
