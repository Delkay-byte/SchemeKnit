/**
 * Verify the new brand renders correctly in the browser.
 * Screenshots the landing page and checks pixel colors for navy + cyan.
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PREVIEW = path.join(__dirname, '_brand_preview');
fs.mkdirSync(PREVIEW, { recursive: true });

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.setViewportSize({ width: 1280, height: 800 });

  // Landing page
  await page.goto('http://localhost:3000', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: path.join(PREVIEW, 'final-landing.png'), fullPage: false });

  // Check the mark SVG is rendered (look for the svg element)
  const markCount = await page.evaluate(() => {
    const svgs = document.querySelectorAll('svg[aria-label="SchemeKnit mark"]');
    return svgs.length;
  });
  console.log(`SchemeKnit mark SVGs on landing page: ${markCount}`);

  // Check the mark has the right fills
  const markFills = await page.evaluate(() => {
    const svg = document.querySelector('svg[aria-label="SchemeKnit mark"]');
    if (!svg) return [];
    return Array.from(svg.querySelectorAll('path')).map(p => p.getAttribute('fill'));
  });
  console.log(`Mark path fills: ${JSON.stringify(markFills)}`);

  const hasNavy = markFills.includes('#102A43');
  const hasCyan = markFills.includes('#04A9CE');
  const noOldGradient = !markFills.some(f => f && f.startsWith('url(#'));
  console.log(`Navy #102A43: ${hasNavy ? 'PASS' : 'FAIL'}`);
  console.log(`Cyan #04A9CE: ${hasCyan ? 'PASS' : 'FAIL'}`);
  console.log(`No old gradient: ${noOldGradient ? 'PASS' : 'FAIL'}`);

  // Screenshot a mark at large size for visual check
  await page.setContent(`
    <html><body style="margin:0;padding:0;background:white;">
      <div style="width:256px;height:256px;margin:20px;">
        ${fs.readFileSync(path.join(__dirname, '..', 'assets', 'brand', 'schemeknit-mark.svg'), 'utf-8')}
      </div>
    </body></html>
  `, { waitUntil: 'load' });
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(PREVIEW, 'final-mark-256.png') });

  // Platform admin login page
  await page.goto('http://localhost:3000/login/platform-admin', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(PREVIEW, 'final-platform-login.png') });

  const allOk = hasNavy && hasCyan && noOldGradient && markCount > 0;
  console.log(`\n${allOk ? 'ALL PASS' : 'FAILURES PRESENT'}`);
  await browser.close();
  process.exit(allOk ? 0 : 1);
})();
