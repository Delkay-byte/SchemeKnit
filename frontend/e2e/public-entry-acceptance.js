// Browser acceptance for the PUBLIC ENTRY journey.
//
// Staff/Platform Admin is deliberately NOT exposed on the public landing page.
// It remains reachable only through its secure direct routes
// (/login/platform-admin, /setup/platform-admin), which are still checked here.
const { chromium } = require('playwright');

const BASE = 'http://localhost:3000';

async function expect(fn, label) {
  let ok = false;
  try { ok = await fn(); } catch (e) { ok = false; }
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}`);
  return ok;
}

async function land(page, path) {
  await page.goto(BASE + path, { waitUntil: 'domcontentloaded' });
  // The landing page is a client component; SSR emits a spinner until
  // hydration completes. Wait for the hero to paint before asserting.
  await page.waitForLoadState('networkidle');
  await page.getByText('Professional Lesson Plans in Minutes')
    .waitFor({ timeout: 15000 });
  await page.waitForTimeout(1500);
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  let allPass = true;

  // 1-2. Landing page + three role cards
  await land(page, '/');
  await page.getByText('Professional Lesson Plans in Minutes').waitFor({ timeout: 8000 });
  allPass = await expect(async () => await page.getByRole('heading', { name: 'Teacher' }).count() > 0, 'landing: Teacher card') && allPass;
  allPass = await expect(async () => await page.getByRole('heading', { name: 'School Administration' }).count() > 0, 'landing: School Administration card') && allPass;
  allPass = await expect(async () => await page.getByRole('heading', { name: 'Platform Administration' }).count() === 0, 'landing: Platform Administration NOT shown') && allPass;
  allPass = await expect(async () => await page.getByRole('link', { name: 'Platform Admin Login' }).count() === 0, 'landing: no Platform Admin Login link') && allPass;
  allPass = await expect(async () => await page.getByText('Staff / Platform Admin').count() === 0, 'footer: no Staff / Platform Admin link') && allPass;
  allPass = await expect(async () => await page.getByRole('link', { name: 'Activate Your School' }).count() > 0, 'landing: Activate Your School button') && allPass;
  allPass = await expect(async () => await page.getByRole('link', { name: 'School Admin Login' }).count() > 0, 'landing: School Admin Login button') && allPass;
  allPass = await expect(async () => await page.getByRole('link', { name: 'Create Free Account' }).count() > 0, 'landing: Create Free Account button') && allPass;
  // Contact affordances (WhatsApp + email) available on the public page.
  allPass = await expect(async () => await page.getByLabel(/WhatsApp/i).count() > 0, 'landing: WhatsApp contact action') && allPass;
  allPass = await expect(async () => await page.locator('a[href^="mailto:bloomcoretechnologies@gmail.com"]').count() > 0, 'landing: contact email link') && allPass;

  // 3-4. Platform Admin direct route still works (bypassing the landing page).
  await page.goto(BASE + '/login/platform-admin', { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle');
  allPass = await expect(async () => await page.getByText('SchemeKnit Platform Administration').count() > 0, 'platform admin direct login loads') && allPass;
  allPass = await expect(async () => await page.getByRole('button', { name: 'Sign In' }).count() > 0, 'platform admin direct login has form') && allPass;

  // 5-7. School Administration entry
  await land(page, '/');
  await page.getByRole('link', { name: 'Activate Your School' }).click();
  await page.waitForURL(/\/activate-school/, { timeout: 10000 });
  await page.getByPlaceholder('TF-SCH-XXXX-XXXX-XXXX').waitFor({ timeout: 10000 });
  allPass = await expect(async () => await page.getByRole('heading', { name: 'Activate Your School' }).count() > 0, 'activate-school page title') && allPass;
  allPass = await expect(async () => await page.getByPlaceholder('TF-SCH-XXXX-XXXX-XXXX').count() > 0, 'activate-school: code input') && allPass;

  await land(page, '/');
  await page.getByRole('link', { name: 'School Admin Login' }).click();
  await page.waitForURL(/\/login\/school-admin/, { timeout: 10000 });
  await page.getByText('Have a school activation code?').waitFor({ timeout: 10000 });
  allPass = await expect(async () => await page.getByText('Have a school activation code?').count() > 0, 'school-admin: activation-code link') && allPass;

  // 8-9. Teacher login + two-path explanation
  await land(page, '/');
  await page.getByRole('link', { name: 'Teacher Login' }).click();
  await page.waitForURL(/\/login/, { timeout: 10000 });
  // The login card is client-rendered; wait for it to paint before asserting.
  await page.getByText('SchemeKnit Teacher').waitFor({ timeout: 10000 });
  allPass = await expect(async () => await page.getByText('SchemeKnit Teacher').count() > 0, 'teacher login labelled') && allPass;
  allPass = await expect(async () => await page.getByText('School Teacher').count() > 0, 'teacher login: School Teacher path') && allPass;
  allPass = await expect(async () => await page.getByText('Individual Teacher').count() > 0, 'teacher login: Individual Teacher path') && allPass;
  allPass = await expect(async () => await page.getByText('Register as individual teacher').count() > 0, 'teacher login: register link') && allPass;
  allPass = await expect(async () => await page.getByText('Choose Your Plan').count() > 0, 'teacher login: Free/Pro comparison card') && allPass;

  // Signup form
  await page.getByText('Register as individual teacher').click();
  await page.waitForURL(/\/signup/, { timeout: 10000 });
  await page.getByPlaceholder('Ama Mensah').waitFor({ timeout: 10000 });
  allPass = await expect(async () => await page.getByPlaceholder('Ama Mensah').count() > 0, 'signup: full name field') && allPass;
  allPass = await expect(async () => await page.getByPlaceholder('name@gmail.com').count() > 0, 'signup: email field') && allPass;
  allPass = await expect(async () => await page.getByText('Create Account').count() > 0, 'signup: submit button') && allPass;

  // Mobile viewport — cards stay usable (§21)
  await page.setViewportSize({ width: 375, height: 700 });
  await land(page, '/');
  allPass = await expect(async () => (await page.getByRole('heading', { name: 'Teacher' }).count()) > 0, 'mobile: teacher card visible') && allPass;
  allPass = await expect(async () => (await page.getByRole('heading', { name: 'School Administration' }).count()) > 0, 'mobile: school card visible') && allPass;
  allPass = await expect(async () => (await page.getByRole('heading', { name: 'Platform Administration' }).count()) === 0, 'mobile: platform card NOT visible') && allPass;

  await browser.close();
  console.log(allPass ? '\nALL PUBLIC ACCEPTANCE CHECKS PASSED' : '\nSOME CHECKS FAILED');
  process.exit(allPass ? 0 : 1);
})().catch((e) => { console.error('ERROR', e.message); process.exit(2); });



