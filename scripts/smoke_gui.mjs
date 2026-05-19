#!/usr/bin/env node
/**
 * GUI smoke for Phase 31/34 verification.
 * Requires Playwright once: npm install --no-save playwright@1.49.0
 * Usage: node scripts/smoke_gui.mjs
 * Env: SMOKE_BASE_URL (default http://localhost:8080), SMOKE_USER, SMOKE_PASS
 */
import { chromium } from "playwright";

const BASE = process.env.SMOKE_BASE_URL || "http://localhost:8080";
const USER = process.env.SMOKE_USER || "admin";
const PASS = process.env.SMOKE_PASS || "admin123";

const results = [];

function pass(name, detail = "") {
  results.push({ name, ok: true, detail });
  console.log(`PASS  ${name}${detail ? `: ${detail}` : ""}`);
}

function fail(name, detail = "") {
  results.push({ name, ok: false, detail });
  console.error(`FAIL  ${name}${detail ? `: ${detail}` : ""}`);
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    await page.goto(`${BASE}/auth/login`, { waitUntil: "networkidle" });
    await page.fill('input[name="username"], input[type="text"]', USER);
    await page.fill('input[name="password"], input[type="password"]', PASS);
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/(overview|runs)/, { timeout: 15000 });
    await page.waitForSelector("button.theme-toggle", { timeout: 10000 });
    pass("login", page.url());

    // Dark mode toggle (if present in app shell)
    const themeToggle = page.locator("button.theme-toggle").first();
    if (await themeToggle.count()) {
      const before = await page.locator("html").getAttribute("data-theme");
      await themeToggle.click();
      await page.waitForTimeout(300);
      const after = await page.locator("html").getAttribute("data-theme");
      if (before !== after) pass("dark-mode-toggle", `${before || "none"} -> ${after || "none"}`);
      else fail("dark-mode-toggle", "data-theme unchanged after click");
    } else {
      pass("dark-mode-toggle", "skipped (no toggle found)");
    }

    // Config tabs
    await page.goto(`${BASE}/config`, { waitUntil: "networkidle" });
    const plansTab = page.locator("#config-tab-plans");
    const emailTab = page.locator("#config-tab-email");
    const integrationTab = page.locator("#config-tab-integration");
    if ((await plansTab.count()) && (await emailTab.count()) && (await integrationTab.count())) {
      pass("config-tabs-present");
      await emailTab.click();
      await page.waitForTimeout(200);
      const emailPanelHidden = await page.locator("#config-panel-email").getAttribute("hidden");
      if (emailPanelHidden === null) pass("config-email-tab");
      else fail("config-email-tab", "email panel still hidden");
      await integrationTab.click();
      await page.waitForTimeout(200);
      const integrationPanelHidden = await page.locator("#config-panel-integration").getAttribute("hidden");
      if (integrationPanelHidden === null) pass("config-integration-tab");
      else fail("config-integration-tab", "integration panel still hidden");
      await plansTab.click();
    } else {
      fail("config-tabs-present", "missing tab buttons");
    }

    // Load sim-actors plan
    const loadButtons = page.locator('button:has-text("Load")');
    if (await loadButtons.count()) {
      await loadButtons.first().click();
      await page.waitForTimeout(500);
      const editor = page.locator("textarea").first();
      const value = await editor.inputValue();
      if (value.includes("users") || value.includes("stores")) pass("config-load-plan", "editor populated");
      else fail("config-load-plan", "editor empty or unexpected");
    } else {
      fail("config-load-plan", "no Load button");
    }

    // New clones loaded content
    const newBtn = page.locator('button:has-text("New")').first();
    if (await newBtn.count()) {
      const beforeNew = await page.locator("textarea").first().inputValue();
      await newBtn.click();
      await page.waitForTimeout(300);
      const afterNew = await page.locator("textarea").first().inputValue();
      if (afterNew && afterNew === beforeNew) pass("config-new-clones-loaded");
      else if (afterNew && afterNew.length > 10) pass("config-new-clones-loaded", "draft created");
      else fail("config-new-clones-loaded", "unexpected editor state");
    }

    // Runs — load flow launcher
    await page.goto(`${BASE}/runs`, { waitUntil: "networkidle" });
    const flowSelect = page.locator('#launch-settings select').first();
    if (await flowSelect.count()) {
      await flowSelect.selectOption("load");
      await page.waitForTimeout(400);
      const loadPace = page.locator('text=Load Pace');
      const modeOverride = page.locator('text=Mode Override');
      if (await loadPace.count()) pass("runs-load-pace-visible");
      else fail("runs-load-pace-visible");
      if ((await modeOverride.count()) === 0) pass("runs-trace-controls-hidden");
      else fail("runs-trace-controls-hidden", "Mode Override still visible in load mode");
    } else {
      fail("runs-flow-select");
    }

    // Schedules page loads
    await page.goto(`${BASE}/schedules`, { waitUntil: "networkidle" });
    if (page.url().includes("/schedules")) pass("schedules-page");
    else fail("schedules-page", page.url());

    const editBtn = page.locator('button:has-text("Edit")').first();
    if (await editBtn.count()) {
      await editBtn.click();
      await page.waitForTimeout(400);
      pass("schedules-edit-click");
    } else {
      pass("schedules-edit-click", "skipped (no schedules to edit)");
    }

    // Archives + retention
    for (const path of ["/archives", "/retention"]) {
      await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
      if (page.url().includes(path)) pass(`${path.slice(1)}-page`);
      else fail(`${path.slice(1)}-page`, page.url());
    }
  } catch (err) {
    fail("unexpected-error", String(err));
  } finally {
    await browser.close();
  }

  const failed = results.filter((r) => !r.ok);
  console.log(`\nSummary: ${results.length - failed.length}/${results.length} passed`);
  process.exit(failed.length ? 1 : 0);
}

main();
