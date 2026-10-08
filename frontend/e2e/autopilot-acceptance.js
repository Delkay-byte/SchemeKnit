// Priority 3.1 — §23 ZERO-DECISION / AUTOPILOT browser acceptance.
//
// Scenarios (the §23 set, driven through the real screens):
//  1. Single-subject upload → ONE explicit action ("Generate my lesson
//     plans") → lesson plans generated, capped to the real allowance.
//  2. Fresh teacher signup shares the same one-action path (zero decisions:
//     no date/class/subject/weeks/units inputs before the click).
//  3. Capped allowance: the counts line and the button label match the
//     SERVER plan exactly (the browser never counts the allowance itself).
//  4. Unlimited account: nothing waits for next month; label stays plain.
//  5. Genuine interruptions only: class confirmation and the WAPEF prompt
//     render as focused blockers (needs-review rows are API-matrix covered).
//  6. Choose manually / Change settings keep the week-centric flow intact.
//  7. A plain visit or a reload NEVER auto-generates; after the run the job
//     restores on reload and an exhausted quota renders a real blocker.
//  + mobile 375px fit.
//
// Env: TF_WEB_URL (default http://localhost:3000), TF_API_URL,
//      TF_PRO_EMAIL / TF_PRO_PASS (primed unlimited account, scenario 4).
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const WEB = (process.env.TF_WEB_URL || 'http://localhost:3000').replace(/\/$/, '');
const API = (process.env.TF_API_URL || 'http://localhost:8000').replace(/\/$/, '');
const ROOT = path.join(__dirname, '..', '..');
const SCIENCE = path.join(ROOT, 'backend', 'uploads',
  '1d3813d1-8fce-47b1-ac81-2ab40c5a8bb8_BASIC 9 SCIENCE SCHEME OF LEARNING.docx');
const CODELESS = path.join(ROOT, 'backend', 'tests', 'fixtures', 'remediation',
  'bs7_code_only_indicators_scheme.docx');
const OUT = path.join(__dirname, 'autopilot-acceptance');
fs.mkdirSync(OUT, { recursive: true });

const STAMP = Date.now();
const PASS_W = 'Auto#2026';
const EMAIL_A = `autopilot.one.${STAMP}@schemeknit.test`;   // scenario 1/2/7 + WAPEF/class flow
const EMAIL_B = `autopilot.manual.${STAMP}@schemeknit.test`; // scenario 3/5/6 (never fires)
const PRO_EMAIL = process.env.TF_PRO_EMAIL || '';
const PRO_PASS = process.env.TF_PRO_PASS || '';

let pass = 0, fail = 0;
const results = [];
function log(ok, label, detail) {
  results.push(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? `  — ${detail}` : ''}`);
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? `  — ${detail}` : ''}`);
  if (ok) pass++; else fail++;
}

async function check(fn, label, detail) {
  try {
    const v = await fn();
    log(v === true || v, label, typeof detail === 'string' ? detail : undefined);
    return v;
  } catch (e) {
    log(false, label, e.message.split('\n')[0].slice(0, 180));
    return false;
  }
}

// Atomic capture: the counts line exists only while the plan is up (checking
// state shows a placeholder; after the run the card hides). One poll that
// returns the real text — never a detached-node read.
async function waitCounts(page, needles, timeout = 45000) {
  const h = await page.waitForFunction((need) => {
    const el = document.querySelector('[data-autopilot-counts]');
    const t = el ? String(el.innerText || '') : '';
    if (!t || t.includes('Checking')) return false;
    return need.every((n) => t.includes(n)) ? t.replace(/\s+/g, ' ').trim() : false;
  }, needles, { timeout });
  return h.jsonValue();
}

async function waitProgress(page, timeout = 45000) {
  const h = await page.waitForFunction(() => {
    const lis = document.querySelectorAll('[data-autopilot-progress] li');
    if (!lis.length) return false;
    return { n: lis.length, first: String(lis[0].innerText || '').replace(/\s+/g, ' ').trim() };
  }, null, { timeout });
  return h.jsonValue();
}

async function shot(page, name) {
  await page.screenshot({ path: path.join(OUT, name), fullPage: false }).catch(() => {});
}

async function signup(page, email) {
  await page.goto(WEB + '/signup', { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.locator('#signup-name').fill('Autopilot Teacher');
  await page.locator('#signup-email').fill(email);
  await page.locator('#signup-password').fill(PASS_W);
  await page.locator('#signup-confirm').fill(PASS_W);
  await page.getByRole('button', { name: /create account/i }).click();
  await page.waitForURL((u) => !u.pathname.startsWith('/signup'), { timeout: 30000 });
  await page.waitForLoadState('networkidle').catch(() => {});
}

async function login(page, email, pass) {
  await page.goto(WEB + '/login', { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.getByText('Welcome back, teacher.').waitFor({ timeout: 15000 });
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(pass);
  await page.getByRole('button', { name: 'Sign In' }).click();
  await page.waitForURL(/\/dashboard/, { timeout: 20000 });
  await page.waitForLoadState('networkidle').catch(() => {});
}

async function upload(page, file) {
  await page.goto(WEB + '/upload', { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.locator('input[type="file"]').setInputFiles(file);
  await page.getByRole('button', { name: /upload & process/i }).click();
  const ok = await page.locator('[data-upload-success]')
    .waitFor({ timeout: 30000 }).then(() => true).catch(() => false);
  if (ok) return 'success';
  // Confirm-the-subject screen (scheme without a stated class/subject).
  await page.locator('[data-multi-subject]').waitFor({ timeout: 30000 });
  return 'confirm';
}

// Confirm screen: the doc states no class, so the teacher picks it FIRST —
// that unlocks the subject chip. Both choices are the §17 genuine interrupts.
async function confirmSubject(page) {
  await page.locator('[data-confirm-class]').waitFor({ timeout: 30000 });
  await page.waitForFunction(() => {
    const s = document.querySelector('#confirm-class-level');
    return s && s.options && s.options.length > 1;
  }, null, { timeout: 20000 });
  const classPrompt = await page.locator('[data-confirm-class]').innerText();
  const prompted = classPrompt.includes('does not state the class level');
  await page.locator('#confirm-class-level').selectOption('Basic 7');
  await page.waitForFunction(() => {
    const b = document.querySelector('[data-multi-subject] button');
    return b && !b.disabled;
  }, null, { timeout: 20000 });
  page.__classPromptOk = prompted;
  await page.locator('[data-multi-subject] button').first().click();
  await page.waitForURL(/\/review\//, { timeout: 30000 });
  return page.url().split('/review/')[1].split(/[?#]/)[0];
}

// Review Curriculum (never sets the autopilot intent) → scheme id.
async function schemeViaReview(page) {
  await page.getByRole('button', { name: /review curriculum/i }).first().click();
  await page.waitForURL(/\/review\//, { timeout: 30000 });
  return page.url().split('/review/')[1].split(/[?#]/)[0];
}

async function gotoGenerate(page, schemeId) {
  await page.goto(`${WEB}/generate/${schemeId}`, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.waitForLoadState('networkidle').catch(() => {});
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  const pageErrors = [];
  page.on('pageerror', (e) => pageErrors.push(String(e)));

  // Requests the autopilot would make WITHOUT a teacher click — every one is
  // a spec violation (§17: quota never spent without the explicit action).
  let autoSelectionPosts = 0, autoGeneratePosts = 0;
  page.on('request', (r) => {
    if (r.method() !== 'POST') return;
    if (r.url().includes('/autopilot-selection')) autoSelectionPosts++;
    if (/\/api\/generation\/[^/]+\/generate$/.test(r.url())) autoGeneratePosts++;
  });

  try {
    // ══ Scenario 1+2: fresh signup, single subject, ONE action ═════════
    await signup(page, EMAIL_A);
    log(true, 'scenario 2: fresh teacher signup lands in the product', EMAIL_A);
    const upMode = await upload(page, SCIENCE);
    log(upMode === 'success', 'scenario 1: single-subject scheme → instant success card', upMode);
    const upVisible = await page.locator('[data-autopilot-upload]').isVisible();
    log(upVisible, 'scenario 1: success card offers the ONE action', 'data-autopilot-upload');
    const primaryText = await page.locator('[data-autopilot-upload]').innerText();
    log(primaryText.includes('Generate my lesson plans'),
      'scenario 1: primary action is "Generate my lesson plans"', primaryText.trim());
    const reviewStillThere = await page.getByRole('button', { name: /review curriculum/i }).count();
    log(reviewStillThere > 0, 'scenario 1: Review Curriculum stays available (§19)');

    await shot(page, '01-upload-one-action.png');
    const beforeClick = autoSelectionPosts;
    await page.locator('[data-autopilot-upload]').click();
    await page.waitForURL(/\/generate\//, { timeout: 30000 });
    await page.waitForLoadState('networkidle').catch(() => {});

    // The plan line comes from the server (§20): 22 pending on this fixture,
    // 5 selected for Free Tier, 17 waiting for next month.
    const counts = await waitCounts(page,
      ['22 lesson plans found', '5 can be generated this month', '17 wait for next month']);
    log(Boolean(counts),
      'scenario 1: server plan counts (22 found · 5 this month · 17 wait)',
      String(counts).slice(0, 120));

    const intentCleared = await page.evaluate(() =>
      window.sessionStorage.getItem('schemeknit.autopilot_intent'));
    log(intentCleared === null, 'scenario 1: upload intent consumed exactly once');

    // Auto-fire: NO further click — the ordered work list runs itself.
    const prog = await waitProgress(page);
    log(prog && prog.n === 5 && /1 of 5 · Week 1/.test(prog.first),
      'scenario 1: honest ordered work list renders during the run',
      prog ? `${prog.n} rows, first: ${prog.first.slice(0, 60)}` : 'no rows');
    await shot(page, '02-autopilot-in-flight.png');

    await page.locator('[data-autopilot-results]').waitFor({ timeout: 120000 });
    const resText = await page.locator('[data-autopilot-results]').innerText();
    log(resText.includes('5 lesson plans ready'),
      'scenario 1: results view says "5 lesson plans ready" (§18)');
    const openLinks = await page.locator('[data-autopilot-results] a[href^="/lessons/"]').count();
    log(openLinks === 5, 'scenario 1: every result row offers Open lesson', `${openLinks} links`);
    const rowText = await page.locator('[data-autopilot-results] li').first().innerText();
    log(/Week 1/.test(rowText) && rowText.includes('Generated'),
      'scenario 1: result rows carry week · topic · status', rowText.replace(/\s+/g, ' ').slice(0, 90));
    await check(async () => await page.locator('[data-lesson-workspace]').first().isVisible(),
      'scenario 1: the generated lesson workspace opens');
    log((await page.locator('[data-generate-config]').count()) === 0,
      'scenario 1: configuration hides behind the workspace once a job exists (§15)');
    await shot(page, '03-autopilot-results.png');

    const quota = await page.evaluate(async () => {
      const t = window.sessionStorage.getItem('teachflow_token');
      const r = await fetch('http://localhost:8000/api/generation/quota',
        { headers: { Authorization: 'Bearer ' + t } });
      return r.ok ? r.json() : null;
    });
    log(quota && quota.used === 5 && quota.remaining === 0,
      'scenario 1: the server consumed exactly the 5-plan monthly allowance',
      quota ? `used=${quota.used} remaining=${quota.remaining}` : 'no quota payload');

    // ══ Scenario 7: reload restores the job, NEVER re-generates ════════
    autoSelectionPosts = 0; autoGeneratePosts = 0;
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle').catch(() => {});
    await page.waitForTimeout(2500);
    log((await page.locator('[data-lesson-workspace]').count()) > 0,
      'scenario 7: reload restores the generated job (workspace back)');
    log((await page.locator('[data-autopilot-progress]').count()) === 0 &&
        autoSelectionPosts === 0 && autoGeneratePosts === 0,
      'scenario 7: plain reload fires no autopilot selection and no generation',
      `selection=${autoSelectionPosts} generate=${autoGeneratePosts}`);
    await shot(page, '04-reload-restores-job.png');

    // ══ Scenario 7b: Start New → exhausted quota renders a real blocker ═
    await page.getByRole('button', { name: /start new generation/i }).click();
    await page.locator('[data-autopilot]').waitFor({ timeout: 30000 });
    await page.locator('[data-autopilot-blocker][data-blocker-code="quota_exhausted"]')
      .waitFor({ timeout: 30000 });
    log(true, 'scenario 7b: exhausted allowance renders the quota blocker',
      'data-blocker-code=quota_exhausted');
    const blockedLabel = await page.locator('[data-autopilot-action]').innerText();
    const blockedDisabled = await page.locator('[data-autopilot-action]').isDisabled();
    log(blockedDisabled && blockedLabel.includes('Generate my lesson plans'),
      'scenario 7b: blocked action stays plain-worded and disabled', blockedLabel.trim());
    await shot(page, '05-quota-blocker.png');

    // ══ Scenario 5: WAPEF is the ONLY interruption it adds ═════════════
    const wapefValue = await page.$eval('#cfg-template', (el) => {
      const opt = Array.from(el.options).find((o) => /WAPEF/i.test(o.text));
      return opt ? opt.value : null;
    });
    if (wapefValue) {
      await page.locator('#cfg-template').first().selectOption(wapefValue);
      await page.locator('[data-autopilot-blocker][data-blocker-code="wapef_required"]')
        .waitFor({ timeout: 30000 });
      log(true, 'scenario 5: selecting WAPEF surfaces exactly the one-time WAPEF prompt');
      const wapefBtn = page.getByRole('button', { name: /add missing wapef fields/i });
      log(await wapefBtn.isVisible(), 'scenario 5: focused interrupt offers "Add missing WAPEF fields"');
      await wapefBtn.click();
      await page.locator('[data-lesson-review]').waitFor({ timeout: 30000 });
      const deepHope = await page.getByText('Deep Hope').first().isVisible().catch(() => false);
      log(deepHope, 'scenario 5: the prompt takes the teacher to the WAPEF inputs (Deep Hope)');
      await shot(page, '06-wapef-interrupt.png');
      // Removing the WAPEF template re-plans the card (no stale plan).
      const gesValue = await page.$eval('#cfg-template', (el) => {
        const opt = Array.from(el.options).find((o) => /WAPEF/i.test(o.text) && o.selected === false);
        return opt ? el.options[0].value : null;
      });
      await page.locator('#cfg-template').first().selectOption(gesValue || { index: 0 });
      await page.locator('[data-autopilot-blocker][data-blocker-code="wapef_required"]')
        .waitFor({ state: 'detached', timeout: 30000 });
      log(true, 'scenario 5: changing settings re-plans the card (stale plan impossible)');
    } else {
      log(false, 'scenario 5: WAPEF template present in the template list');
    }

    // ══ Scenario 3: capped label + counts on a PLAIN visit (no intent) ═
    const ctxB = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const pb = await ctxB.newPage();
    pb.on('pageerror', (e) => pageErrors.push(String(e)));
    let bSelectionPosts = 0, bGeneratePosts = 0;
    pb.on('request', (r) => {
      if (r.method() !== 'POST') return;
      if (r.url().includes('/autopilot-selection')) bSelectionPosts++;
      if (/\/api\/generation\/[^/]+\/generate$/.test(r.url())) bGeneratePosts++;
    });
    await signup(pb, EMAIL_B);
    const bMode = await upload(pb, SCIENCE);
    log(bMode === 'success', 'scenario 3: science scheme uploads without interruption', bMode);
    const schemeScience = await schemeViaReview(pb);   // no intent recorded
    await gotoGenerate(pb, schemeScience);
    const bCounts = await waitCounts(pb,
      ['5 can be generated this month', '17 wait for next month']);
    log(Boolean(bCounts),
      'scenario 3: capped plan shows on a plain visit', String(bCounts).slice(0, 120));
    const bLabel = await pb.locator('[data-autopilot-action]').innerText();
    log(bLabel.includes('Generate 5 lesson plans'),
      'scenario 3: capped button names the exact server count', bLabel.trim());
    await pb.waitForTimeout(4000);
    log(bGeneratePosts === 0 && (await pb.locator('[data-autopilot-results]').count()) === 0,
      'scenario 3: a plain visit NEVER auto-generates (§17)',
      `generate=${bGeneratePosts}`);
    await shot(pb, '07-capped-plain-visit.png');

    // ══ Scenario 5b: class confirmation (genuine interruption) ═════════
    const cMode = await upload(pb, CODELESS);
    log(cMode === 'confirm', 'scenario 5b: a scheme that states no class interrupts at upload', cMode);
    const schemeClass = cMode === 'confirm'
      ? await confirmSubject(pb)      // class prompt → class choice → subject chip → /review
      : await schemeViaReview(pb);
    log(pb.__classPromptOk !== false,
      'scenario 5b: the class prompt is the focused interrupt (§17)',
      'does not state the class level');
    await gotoGenerate(pb, schemeClass);
    const noClassBlock = (await pb.locator('[data-autopilot-blocker][data-blocker-code="class_confirmation"]').count()) === 0;
    log(noClassBlock,
      'scenario 5b: confirmed class flows through — no repeated question on generate');
    const classCounts = await waitCounts(pb, ['8 lesson plans found'], 60000);
    log(Boolean(classCounts),
      'scenario 5b: plan now covers the whole scheme (8 pending)',
      String(classCounts).slice(0, 120));
    await shot(pb, '08-class-confirmed.png');

    // Change settings scrolls back to the config surface (§19: advanced
    // settings never leave the screen behind the card).
    await pb.getByRole('button', { name: /change settings/i }).click();
    await pb.waitForTimeout(800);
    const cfgInViewport = await pb.evaluate(() => {
      const el = document.querySelector('[data-generate-config]');
      if (!el) return false;
      const r = el.getBoundingClientRect();
      return r.top < window.innerHeight && r.bottom > 0;
    });
    log(cfgInViewport, 'scenario 6: Change settings brings the configuration into view');

    // ══ Scenario 6: Choose manually keeps the week-centric flow ════════
    await pb.getByRole('button', { name: /choose manually/i }).click();
    await pb.locator('[data-allocation-weeks]').waitFor({ timeout: 30000 });
    const weeks = await pb.locator('[data-week-card]').count();
    log(weeks > 0, 'scenario 6: Choose manually lands on the week surface',
      `${weeks} week cards`);
    const weekHeading = await pb.getByRole('heading', { name: /lesson plans by week/i }).count();
    log(weekHeading > 0, 'scenario 6: week-centric heading untouched (§19)');
    await shot(pb, '09-manual-week-surface.png');

    // ══ Scenario 4: unlimited account — nothing waits for next month ═══
    if (PRO_EMAIL && PRO_PASS) {
      const ctxU = await browser.newContext({ viewport: { width: 1280, height: 900 } });
      const pu = await ctxU.newPage();
      pu.on('pageerror', (e) => pageErrors.push(String(e)));
      await login(pu, PRO_EMAIL, PRO_PASS);
      const uMode = await upload(pu, SCIENCE);
      log(uMode === 'success', 'scenario 4: unlimited account uploads the science scheme', uMode);
      const schemeU = await schemeViaReview(pu);   // this account's own scheme
      await gotoGenerate(pu, schemeU);
      const uCounts = await waitCounts(pu,
        ['22 can be generated this month'], 60000)
        .catch(() => '');
      const uStable = Boolean(uCounts) && !String(uCounts).includes('wait for next month');
      log(uStable,
        'scenario 4: unlimited plan fits everything this month',
        String(uCounts).slice(0, 120) || 'no counts');
      const uLabel = await pu.locator('[data-autopilot-action]').innerText();
      const uDisabled = await pu.locator('[data-autopilot-action]').isDisabled();
      log(!uDisabled && uLabel.includes('Generate my lesson plans'),
        'scenario 4: unlimited label stays plain and enabled', uLabel.trim());
      await shot(pu, '10-unlimited-plan.png');
      await ctxU.close();
    } else {
      log(false, 'scenario 4: unlimited account primed (set TF_PRO_EMAIL/TF_PRO_PASS)');
    }

    // ══ Mobile 375px: the card and its action fit ══════════════════════
    const ctxM = await browser.newContext({ viewport: { width: 375, height: 812 } });
    const pm = await ctxM.newPage();
    pm.on('pageerror', (e) => pageErrors.push(String(e)));
    await login(pm, EMAIL_B, PASS_W);
    await gotoGenerate(pm, schemeScience);
    await pm.locator('[data-autopilot]').waitFor({ timeout: 30000 });
    const cardBox = await pm.locator('[data-autopilot]').boundingBox();
    log(cardBox && cardBox.x >= -1 && cardBox.x + cardBox.width <= 376,
      'mobile 375px: autopilot card fits the viewport',
      cardBox ? `x=${Math.round(cardBox.x)} w=${Math.round(cardBox.width)}` : 'no box');
    const actionBox = await pm.locator('[data-autopilot-action]').boundingBox();
    log(actionBox && actionBox.x >= -1 && actionBox.x + actionBox.width <= 376,
      'mobile 375px: the ONE action fits the viewport',
      actionBox ? `x=${Math.round(actionBox.x)} w=${Math.round(actionBox.width)}` : 'no box');
    await shot(pm, '11-mobile-375.png');
    await ctxM.close();

    // ── Wrap up ─────────────────────────────────────────────────────────
    log(pageErrors.length === 0, 'zero uncaught page errors',
      pageErrors.slice(0, 3).join(' | ').slice(0, 200));
    await ctxB.close();
  } catch (e) {
    log(false, 'script completed', e.message.split('\n')[0].slice(0, 200));
    await shot(page, '99-failure.png').catch(() => {});
  } finally {
    fs.writeFileSync(path.join(OUT, 'results.txt'), results.join('\n') + '\n');
    console.log(`\n${pass} passed, ${fail} failed — screenshots in e2e/autopilot-acceptance/`);
    await browser.close();
    process.exit(fail === 0 ? 0 : 1);
  }
})();
