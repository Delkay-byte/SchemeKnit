/**
 * TeachFlow Teacher Workflow - real browser acceptance run.
 * Performs: login -> dashboard -> upload -> review -> approve -> configure ->
 *           generate -> lessons -> open/edit lesson -> exports.
 *
 * Usage: node teacher_workflow.acceptance.js <scheme-docx> <subject-label>
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = process.env.BASE_URL || 'http://localhost:3000';
const API = process.env.API_URL || 'http://127.0.0.1:8000';
const TEACHER = {
  email: process.env.TEACHER_EMAIL || 'teacher.science@awasive.edu.gh',
  password: process.env.TEACHER_PASSWORD || 'Teacher123!',
};
const SCHEME_PATH = process.argv[2] || 'C:/Users/SAVIOUR/Documents/DScience/Lesson Plan/BASIC 9 SCIENCE SCHEME OF LEARNING.docx';
const SUBJECT_LABEL = process.argv[3] || 'Science';
const SHOT_DIR = 'C:/Users/SAVIOUR/AppData/Local/Temp/tf_shots';
const results = [];
const consoleErrors = [];

function ok(name, pass, detail = '') {
  results.push({ name, status: pass ? 'PASS' : 'FAIL', detail });
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${name}${detail ? '  -- ' + detail : ''}`);
}

// Next.js App Router uses soft navigations (pushState) that page.waitForURL
// often misses; poll the pathname instead.
async function waitForPath(page, prefix, timeout = 90000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    const p = new URL(page.url()).pathname.replace(/\/$/, '');
    if (p === prefix || p.startsWith(prefix + '/')) return true;
    await page.waitForTimeout(300);
  }
  throw new Error(`timed out waiting for path ${prefix} (still at ${page.url()})`);
}

async function apiLogin(email, password) {
  const res = await fetch(`${API}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error(`login failed: ${res.status}`);
  const data = await res.json();
  return data.access_token || data.token;
}

(async () => {
  fs.mkdirSync(SHOT_DIR, { recursive: true });
  const tag = SUBJECT_LABEL.toLowerCase().replace(/\s+/g, '-');
  const shot = (n) => path.join(SHOT_DIR, `${tag}-${String(n).padStart(2, '0')}.png`);

  // ---------- Product-flow bootstrap: activate -> school admin -> teacher ----------
  // Uses only real product endpoints (the same network calls the UI makes). No SQL, no DB edits.
  const schoolAdmin = { email: 'sadmin.acc@awasive.edu.gh', password: 'SchoolAdmin123!', name: 'School Administrator' };
  const teacher = { email: 'teacher.acc@awasive.edu.gh', password: 'Teacher123!', name: 'Test Teacher' };
  const j = async (res) => { const t = await res.text(); try { return JSON.parse(t); } catch { throw new Error(`non-JSON (${res.status}): ${t.slice(0, 160)}`); } };

  try {
    // 1. Get an unused activation code (platform admin does this through the UI in the real flow)
    const paToken = (await j(await fetch(`${API}/api/auth/login`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'admin@bloomcore.com', password: process.env.PA_PASSWORD || 'Admin123' }),
    }))).access_token;

    const licRes = await j(await fetch(`${API}/api/platform-admin/licenses`, {
      headers: { Authorization: `Bearer ${paToken}` },
    }));
    const licenses = licRes.licenses || licRes || [];
    const lic = Array.isArray(licenses) ? licenses[0] : licenses.items?.[0];
    if (!lic) throw new Error('no license found in platform');

    let activation = null;
    const codesRes = await j(await fetch(`${API}/api/platform-admin/licenses/${lic.id}/activation-codes`, {
      headers: { Authorization: `Bearer ${paToken}` },
    }));
    const codes = codesRes.codes || codesRes || [];
    const fresh = Array.isArray(codes) ? codes.find(c => c.status === 'active') : null;
    if (fresh) {
      activation = await j(await fetch(`${API}/api/platform-admin/activate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ activation_code: fresh.code }),
      }));
      console.log('activation code used:', fresh.code);
    } else {
      // consume path already done in a prior run; recover school id from license list
      activation = { school: { id: lic.school_id } };
      console.log('no fresh code; reusing activated school', lic.school_id);
    }
    const schoolId = activation.school?.id;

    // 2. Create School Administrator (the desktop "Create School Administrator" step)
    const saRes = await fetch(`${API}/api/auth/setup-school-admin`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: schoolAdmin.email, password: schoolAdmin.password, full_name: schoolAdmin.name, school_id: schoolId }),
    });
    console.log(saRes.ok ? 'school admin ready' : `school admin bootstrap: ${saRes.status}`);

    // 3. School Admin creates Teacher (the school admin's Users -> Create Teacher step)
    const saToken = (await j(await fetch(`${API}/api/auth/login`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: schoolAdmin.email, password: schoolAdmin.password }),
    }))).access_token;
    const tRes = await fetch(`${API}/api/auth/users`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${saToken}` },
      body: JSON.stringify({ full_name: teacher.name, email: teacher.email, password: teacher.password, role: 'teacher' }),
    });
    console.log(tRes.ok ? 'teacher account ready' : `teacher bootstrap: ${tRes.status} (may already exist)`);
  } catch (e) {
    console.log('bootstrap warning:', e.message);
  }

  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: 1366, height: 900 },
    acceptDownloads: true,
  });
  const page = await ctx.newPage();
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
  page.on('pageerror', (e) => consoleErrors.push('pageerror: ' + e.message));

  try {
    // ---- 1. LOGIN via the UI ----
    await page.goto(BASE + '/login/', { waitUntil: 'networkidle' });
    await page.fill('input[type=email]', teacher.email);
    await page.fill('input[type=password]', teacher.password);
    await page.click('button[type=submit]');
    await waitForPath(page, '/dashboard', 120000);
    ok('1 login as teacher via UI', true, page.url());

    // ---- 2. DASHBOARD ----
    await page.waitForSelector('text=Welcome back', { timeout: 60000 });
    const dashText = await page.textContent('body');
    ok('2 dashboard renders', dashText.includes('Welcome back'), '');
    await page.screenshot({ path: shot(1), fullPage: true });

    // ---- 3. UPLOAD via real file chooser ----
    await page.click('text=Upload Scheme');
    await waitForPath(page, '/upload', 90000);
    const fname = path.basename(SCHEME_PATH);
    await page.setInputFiles('input[type=file]', SCHEME_PATH);
    await page.screenshot({ path: shot(2) });
    // The submit button is "Upload & Process" (the header nav also says "Upload" — do not click that)
    await page.click('button:has-text("Upload & Process")');
    await page.waitForSelector('text=Upload successful', { timeout: 180000 });
    const successText = await page.textContent('body');
    ok('3 upload success shown', true, '');
    ok('4 success shows original filename', successText.includes(fname), fname);
    const weeksMatch = successText.match(/Weeks detected:\s*(\d+)/);
    ok('5 success shows weeks detected', !!weeksMatch, weeksMatch ? weeksMatch[1] + ' weeks' : '');
    await page.screenshot({ path: shot(3) });

    // ---- 6. REVIEW via the primary CTA ----
    await page.click('text=Review Curriculum');
    await waitForPath(page, '/review', 90000);
    const reviewUrl = page.url();
    const schemeId = decodeURIComponent(reviewUrl.split('/review/')[1] || '').replace(/\/$/, '');
    ok('6 review URL contains persisted scheme id', /^[0-9a-f-]{36}$/i.test(schemeId), schemeId);

    // ---- 7. REVIEW survives refresh ----
    await page.reload({ waitUntil: 'load', timeout: 90000 });
    // Wait for data-driven content (filename renders only after fetch completes)
    await page.waitForSelector(`text=${fname}`, { timeout: 90000 });
    await page.waitForSelector('text=Approve & Configure', { timeout: 90000 }).catch(() => {});
    await page.waitForTimeout(1000);
    const reviewText = await page.textContent('body');
    ok('7 review survives refresh with original filename', reviewText.includes(fname), '');
    ok('8 review shows weeks list', /Weeks?\s*\(?\d{1,2}\)?/i.test(reviewText), '');
    ok('9 review shows curriculum columns', /strand/i.test(reviewText) && /indicator/i.test(reviewText), '');
    await page.screenshot({ path: shot(4), fullPage: true });

    // ---- 10. APPROVE & CONFIGURE ----
    await page.click('text=Approve & Configure');
    await waitForPath(page, '/generate', 90000);
    ok('10 approve navigates to configuration', true, page.url());
    await page.waitForSelector('text=Configuration', { timeout: 15000 });
    const genText = await page.textContent('body');
    ok('11 configuration shows class/subject/term', /class/i.test(genText) && /subject/i.test(genText) && /term/i.test(genText), '');
    await page.screenshot({ path: shot(5) });

    // ---- 12. GENERATE ----
    await page.click('button:has-text("Generate Lesson Plans")');
    await page.waitForSelector('text=/lesson plans generated/i', { timeout: 180000 });
    const genDone = await page.textContent('body');
    const m = genDone.match(/(\d+) lesson plans generated/i);
    ok('12 generation success message', !!m && parseInt(m[1], 10) > 0, m ? m[1] + ' plans' : genDone.slice(0, 120));
    await page.screenshot({ path: shot(6) });

    // ---- 13. LESSONS page ----
    await page.click('text=Review Lesson Plans');
    await waitForPath(page, '/lessons', 90000);
    await page.waitForSelector('table', { timeout: 15000 });
    const lessonsText = await page.textContent('body');
    ok('13 lessons page lists generated plans', lessonsText.includes(fname), '');

    // ---- 14-16. OPEN a lesson, EDIT, SAVE, verify persistence ----
    await page.locator('a:has-text("Open")').first().click();
    await page.waitForSelector('text=Curriculum Context', { timeout: 15000 });
    ok('14 lesson detail opens', true, page.url());
    await page.locator('textarea').first().fill('Browser-acceptance edited introduction ' + Date.now());
    await page.screenshot({ path: shot(7) });
    await page.click('button:has-text("Save Changes")');
    await page.waitForSelector('text=Saved', { timeout: 15000 });
    ok('15 lesson edit saved', true, '');

    // return to lessons and re-open to confirm persistence
    await page.click('text=Back to Lesson Plans');
    await page.waitForSelector('table', { timeout: 15000 });
    await page.locator('a:has-text("Open")').first().click();
    await page.waitForSelector('text=Curriculum Context', { timeout: 15000 });
    const lessonText = await page.textContent('body');
    ok('16 edit persists after returning', lessonText.includes('Browser-acceptance edited introduction'), '');
    await page.screenshot({ path: shot(8) });

    // ---- 17-20. EXPORTS from the generate page (state restored via scheme-status) ----
    await page.goto(BASE + `/generate/${schemeId}`, { waitUntil: 'networkidle' });
    await page.waitForSelector('text=/lesson plans generated/i', { timeout: 20000 });
    const exportSpecs = [
      { fmt: 'docx', label: 'Download DOCX', file: 'Download DOCX' },
      { fmt: 'xlsx', label: 'Download Register (XLSX)', file: 'xlsx' },
      { fmt: 'zip', label: 'Export ZIP', file: 'zip' },
    ];
    for (const [i, spec] of exportSpecs.entries()) {
      try {
        const [dl] = await Promise.all([
          page.waitForEvent('download', { timeout: 90000 }),
          page.click(`button:has-text("${spec.label}")`),
        ]);
        const fp = path.join(SHOT_DIR, `${tag}-export-${spec.fmt}`);
        await dl.saveAs(fp);
        const size = fs.statSync(fp).size;
        ok(`17.${i + 1} export ${spec.fmt} downloads real file`, size > 1000, `${size} bytes`);
      } catch (e) {
        ok(`17.${i + 1} export ${spec.fmt} downloads real file`, false, e.message.slice(0, 120));
      }
    }
    await page.screenshot({ path: shot(9), fullPage: true });

    // ---- console errors ----
    const critical = consoleErrors.filter((e) => !/favicon|Download the React DevTools|hydrat/i.test(e));
    ok('18 no critical console errors', critical.length === 0, critical.slice(0, 3).join(' | ').slice(0, 300));
  } catch (e) {
    ok('RUNTIME', false, e.message.slice(0, 300));
    try { await page.screenshot({ path: shot(99), fullPage: true }); } catch {}
  } finally {
    await browser.close();
  }

  fs.writeFileSync(path.join(SHOT_DIR, `${tag}-results.json`), JSON.stringify(results, null, 2));
  const passed = results.filter(r => r.status === 'PASS').length;
  console.log(`\n===== ${SUBJECT_LABEL}: ${passed}/${results.length} steps passed =====`);
  process.exit(passed === results.length ? 0 : 1);
})();
