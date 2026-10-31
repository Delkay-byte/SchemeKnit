/**
 * Public pages, contact channels and footer responsiveness acceptance.
 * Usage: node e2e/public-pages-responsive.js [baseUrl]
 */
const { chromium } = require('playwright')

const BASE = process.argv[2] || 'http://localhost:3000'
const PAGES = ['/', '/contact', '/cookie-policy', '/privacy-policy', '/terms', '/refunds-cancellation', '/data-retention', '/license-subscription']
let pass = 0
let fail = 0
function log(ok, label, detail = '') {
  if (ok) pass++
  else fail++
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? ' — ' + detail : ''}`)
}

;(async () => {
  const browser = await chromium.launch({ headless: true })
  try {
    for (const [label, viewport] of [
      ['mobile', { width: 390, height: 844 }],
      ['tablet', { width: 768, height: 1024 }],
      ['desktop', { width: 1440, height: 900 }],
    ]) {
      const context = await browser.newContext({ viewport })
      const page = await context.newPage()
      for (const path of PAGES) {
        const res = await page.goto(BASE + path, { waitUntil: 'domcontentloaded', timeout: 30000 })
        log(res && res.status() < 400, `${label}: ${path} responds`)
        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth - window.innerWidth,
        )
        log(overflow <= 1, `${label}: ${path} no horizontal overflow`, String(overflow))
      }

      await page.goto(BASE + '/contact', { waitUntil: 'domcontentloaded' })
      const email = await page.locator('[data-contact-email]').first().getAttribute('href')
      log(email === 'mailto:bloomcoretechnologies@gmail.com?subject=SchemeKnit%20%E2%80%94%20General%20Enquiry' || email?.startsWith('mailto:bloomcoretechnologies@gmail.com'), `${label}: email link`)
      const tels = await page.locator('a[href^="tel:"]').evaluateAll((els) => els.map((e) => e.getAttribute('href')))
      log(tels.includes('tel:+233240064668') && tels.includes('tel:+233553976334'), `${label}: both call links`, tels.join(','))
      const whatsapps = await page.locator('a[href*="wa.me"]').evaluateAll((els) => els.map((e) => e.getAttribute('href')))
      log(whatsapps.length > 0 && whatsapps.every((href) => href.includes('233240064668')), `${label}: WhatsApp only on 024`, whatsapps.join(','))
      log(whatsapps.every((href) => !href.includes('0553976334')), `${label}: no WhatsApp for 055`)
      const contactText = await page.locator('body').innerText()
      log(contactText.includes('L7 Olive St., Akast Road, Akatsi, Volta Region, Ghana.'), `${label}: contact address`)
      log(!contactText.includes('P.O. Box') && !contactText.includes('PO Box'), `${label}: no P.O. Box placeholder`)

      await page.goto(BASE + '/privacy-policy', { waitUntil: 'domcontentloaded' })
      const privacyText = await page.locator('body').innerText()
      log(privacyText.includes('L7 Olive St., Akast Road, Akatsi, Volta Region, Ghana.'), `${label}: privacy address`)
      log(privacyText.includes('makes no claim that BloomCore is'), `${label}: no false DPC claim`)
      const dpc = await page.goto(BASE + '/dpc-registration', { waitUntil: 'domcontentloaded' })
      log(dpc && dpc.status() === 404, `${label}: no DPC certificate page`)

      await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' })
      const footer = page.locator('[data-registered-business]').first()
      log(await footer.isVisible(), `${label}: registered business panel visible`)
      const footerText = await footer.innerText()
      log(footerText.includes('BloomCore Technologies'), `${label}: business name`)
      log(footerText.includes('BN428031125'), `${label}: registration number`)
      log(footerText.includes('7 November 2025'), `${label}: registration date`)
      log(footerText.includes('L7 Olive St., Akast Road, Akatsi, Volta Region, Ghana.'), `${label}: footer address`)
      log(!footerText.includes('P0066415551'), `${label}: TIN absent`)
      await context.close()
    }
  } catch (err) {
    log(false, 'public pages flow', err.message)
  } finally {
    await browser.close()
  }
  console.log(`\n${pass} passed, ${fail} failed`)
  process.exit(fail ? 1 : 0)
})()
