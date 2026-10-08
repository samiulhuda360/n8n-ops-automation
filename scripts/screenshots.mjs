// Takes the README screenshots from a running demo (python -m opsflow demo --port 5690).
//
//   PLAYWRIGHT_CORE=<path to playwright-core/index.mjs> CHROME=<chrome.exe> node scripts/screenshots.mjs [slug ...]
//
// For each workflow it opens the n8n editor, clicks "Try with sample data", waits for the run to finish, and saves
// the canvas (green ticks and item counts) and one node's output table. It also captures the ops console tabs.
import { mkdirSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = join(ROOT, 'docs', 'screenshots');
const N8N = process.env.N8N_URL || 'http://localhost:5690';
const MOCK = process.env.MOCK_URL || 'http://127.0.0.1:8790';
const core = process.env.PLAYWRIGHT_CORE || 'playwright-core';
const { chromium } = await import(core.includes(':') || core.startsWith('/') ? pathToFileURL(core).href : core);
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const OWNER = { email: 'ops.lead@example.com', firstName: 'Alex', lastName: 'Morgan', password: 'Demo-Pass-2026' };

// slug -> the node whose output table is captured
const WORKFLOWS = {
  'lead-intake': 'Apply lead rules',
  'supplier-invoice': 'Validate invoice',
  'support-triage': 'Apply support rules',
  'kpi-digest': 'Check every number',
  'purchase-approval': 'Apply spending policy',
  'content-repurpose': 'Check posts',
};
const only = process.argv.slice(2);
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const context = await browser.newContext({ viewport: { width: 1920, height: 1000 }, deviceScaleFactor: 1.25 });
const page = await context.newPage();

async function dismissPopups() {
  for (let i = 0; i < 3; i++) {
    await page.keyboard.press('Escape').catch(() => {});
    await page.waitForTimeout(200);
  }
  for (const text of ['Skip', 'Get started', 'Close', 'Dismiss']) {
    const b = page.getByRole('button', { name: text, exact: true });
    if (await b.count()) await b.first().click().catch(() => {});
  }
}

async function signIn() {
  await page.goto(`${N8N}/`);
  await page.waitForTimeout(4000);
  if (page.url().includes('/setup')) {
    for (const [name, value] of Object.entries(OWNER)) await page.fill(`input[name="${name}"]`, value);
    await page.getByRole('button', { name: 'Next' }).click();
    await page.waitForTimeout(4000);
  }
  if (page.url().includes('/signin')) {
    await page.fill('input[name="emailOrLdapLoginId"], input[name="email"]', OWNER.email);
    await page.fill('input[name="password"]', OWNER.password);
    await page.getByRole('button', { name: /sign in/i }).click();
    await page.waitForTimeout(4000);
  }
  await dismissPopups();
}

async function fitView() {
  const fit = page.locator('[data-test-id="zoom-to-fit"]');
  if (await fit.count()) await fit.first().click();
  else await page.keyboard.press('1');
  await page.waitForTimeout(800);
}

async function runWorkflow(slug, node) {
  const wf = JSON.parse(readFileSync(join(ROOT, 'workflows', `${slug}.json`), 'utf8'));
  await page.goto(`${N8N}/workflow/${wf.id}`);
  await page.waitForSelector('[data-test-id="canvas-node"]', { timeout: 60000 });
  await page.waitForTimeout(1500);
  await dismissPopups();
  await fitView();
  const trigger = page.locator('[data-test-id="canvas-node"][data-node-name="Try with sample data"]');
  if (await trigger.count()) await trigger.first().hover();
  await page.waitForTimeout(400);
  await page.click('[data-test-id="execute-workflow-button-Try with sample data"]', { force: true });
  // wait until the run stops: the stop button disappears, or the approval run reaches its form (waiting)
  const deadline = Date.now() + 240000;
  await page.waitForTimeout(3000);
  while (Date.now() < deadline) {
    const running = await page.locator('[data-test-id="stop-execution-button"]').count();
    const waiting = await page.getByText(/waiting/i).count();
    if (!running || (slug === 'purchase-approval' && waiting)) break;
    await page.waitForTimeout(1000);
  }
  await page.waitForTimeout(2000);
  await dismissPopups();
  await fitView();
  await page.screenshot({ path: join(OUT, `${slug}-canvas.png`) });

  const target = page.locator(`[data-test-id="canvas-node"][data-node-name="${node}"]`);
  if (await target.count()) {
    await target.first().dblclick();
    await page.waitForSelector('[data-test-id="output-panel"]', { timeout: 15000 });
    await page.waitForTimeout(1200);
    const table = page.locator('[data-test-id="output-panel"] [data-test-id="radio-button-table"], [data-test-id="output-panel"] :text-is("Table")');
    if (await table.count()) await table.first().click().catch(() => {});
    await page.waitForTimeout(800);
    // widen the output panel by dragging the centre handle to the left
    const handle = page.locator('[data-test-id="panel-drag-button"]');
    if (await handle.count()) {
      const box = await handle.first().boundingBox();
      console.log('  drag handle at', box && Math.round(box.x), box && Math.round(box.y));
      if (box) {
        const y = box.y + box.height / 2;
        await page.mouse.move(box.x + box.width / 2, y, { steps: 5 });
        await page.waitForTimeout(300);
        await page.mouse.down();
        await page.waitForTimeout(300);
        for (let x = box.x + box.width / 2; x > 150; x -= 15) {
          await page.mouse.move(x, y);
          await page.waitForTimeout(15);
        }
        await page.mouse.up();
        const after = await handle.first().boundingBox();
        console.log('  drag handle now at', after && Math.round(after.x));
      }
    }
    await page.waitForTimeout(800);
    await page.locator('[data-test-id="output-panel"]').first().screenshot({ path: join(OUT, `${slug}-output.png`) });
    await page.keyboard.press('Escape');
  }
}

async function approvalForm() {
  // The approver's form: opened from the link the workflow posted to #approvals, filled in and submitted.
  const state = await (await fetch(`${MOCK}/admin/state`)).json();
  const pending = state.approvals.filter((a) => a.status === 'pending');
  if (!pending.length) return;
  const req = pending[pending.length - 1];
  const form = await context.newPage();
  await form.goto(req.form_url);
  await form.waitForTimeout(2500);
  await form.getByLabel('Your name').fill(req.approver);
  await form.locator('select').first().selectOption('Approve');
  await form.getByLabel('Comment').fill('Fine for the store opening. Use the usual printer.');
  await form.locator('body').click({ position: { x: 5, y: 5 } }); // no focus ring in the picture
  await form.waitForTimeout(300);
  await form.screenshot({ path: join(OUT, 'approval-form.png'), fullPage: true });
  await form.getByRole('button', { name: /submit/i }).click();
  await form.waitForTimeout(3000);
  await form.close();
  await page.waitForTimeout(3000);
  await fitView();
  await page.screenshot({ path: join(OUT, 'purchase-approval-after-decision.png') });
}

await fetch(`${MOCK}/admin/reset`, { method: 'POST' }); // start the mock systems from their seed data
await signIn();
for (const [slug, node] of Object.entries(WORKFLOWS)) {
  if (only.length && !only.includes(slug)) continue;
  console.log('workflow', slug);
  await runWorkflow(slug, node);
  if (slug === 'purchase-approval') await approvalForm();
}

if (!only.length || only.includes('console')) {
  for (const tab of ['overview', 'leads', 'invoices', 'support', 'approvals', 'content', 'chat']) {
    await page.goto(`${MOCK}/?tab=${tab}`);
    await page.waitForTimeout(500);
    await page.screenshot({ path: join(OUT, `console-${tab}.png`), fullPage: false });
  }
}
await browser.close();
console.log('saved to', OUT);
