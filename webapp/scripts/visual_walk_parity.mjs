#!/usr/bin/env node
/**
 * Visual walk: ai.conall.ru vs cloudpub.
 * Opens every report, tabs, filters, checkboxes, light/dark — screenshots + pixel-diff.
 *
 * From webapp/:
 *   node scripts/visual_walk_parity.mjs
 *
 * Env:
 *   PROD_BASE  DEV_BASE  PROD_USER  PROD_PASS  DEV_USER  DEV_PASS
 *   SETTLE_MS=2500  NAV_MS=4000  DIFF_THRESHOLD=0.12
 *   MAX_TABS=8  MAX_CHECKS=8  MAX_DROPDOWNS=2
 *   ONLY=working-documentation,bdds   SITE=prod|dev|both
 *   HEADED=1  PARITY_OUT=...
 */
import { chromium } from "playwright";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { PNG } from "pngjs";
import pixelmatch from "pixelmatch";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const PROD_BASE = (process.env.PROD_BASE || "https://ai.conall.ru").replace(/\/$/, "");
const DEV_BASE = (
  process.env.DEV_BASE || "https://insipidly-carefree-husky.cloudpub.ru"
).replace(/\/$/, "");
const PROD_USER = process.env.PROD_USER || "admin";
const PROD_PASS = process.env.PROD_PASS || "adminAIcon!2026X";
const DEV_USER = process.env.DEV_USER || "admin";
const DEV_PASS = process.env.DEV_PASS || process.env.PROD_PASS || "adminAIcon!2026X";
const SETTLE_MS = Number(process.env.SETTLE_MS || 2500);
const NAV_MS = Number(process.env.NAV_MS || 4000);
const DIFF_THRESHOLD = Number(process.env.DIFF_THRESHOLD || 0.12);
const MAX_TABS = Number(process.env.MAX_TABS || 8);
const MAX_CHECKS = Number(process.env.MAX_CHECKS || 8);
const MAX_DROPDOWNS = Number(process.env.MAX_DROPDOWNS || 2);
const SITE = (process.env.SITE || "both").toLowerCase();
const ONLY = new Set(
  (process.env.ONLY || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean),
);
const OUT = path.resolve(
  process.env.PARITY_OUT || path.join(__dirname, "..", "parity_out", `walk_${stamp()}`),
);

const ROUTES = [
  { id: "developer-projects", href: "/developer-projects" },
  { id: "bdds", href: "/finance/bdds" },
  { id: "bdr", href: "/finance/bdr" },
  { id: "approved-budget", href: "/finance/approved-budget" },
  { id: "bdds-plan-fact", href: "/finance/bdds-plan-fact" },
  { id: "control-points", href: "/timeline/control-points" },
  { id: "project-schedule", href: "/timeline/project-schedule" },
  { id: "deviation-reasons", href: "/timeline/deviation-reasons" },
  { id: "baseline-deviation", href: "/timeline/baseline-deviation" },
  { id: "project-documentation", href: "/docs/project-documentation" },
  { id: "working-documentation", href: "/docs/working-documentation" },
  { id: "gdrs-people", href: "/gdrs/people" },
  { id: "gdrs-equipment", href: "/gdrs/equipment" },
  { id: "prescriptions", href: "/prescriptions" },
  { id: "executive-docs", href: "/executive-docs" },
  { id: "debit-credit", href: "/debit-credit" },
  { id: "settings-profile", href: "/settings/profile" },
  { id: "settings-admin", href: "/settings/admin" },
];

const SKIP_RE =
  /выйти|ftp|скачать|спросить|удалить|перезагрузить|скопировать|сбросить всё|пароль|синк|ingest/i;

function stamp() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}`;
}

function slug(s) {
  return String(s || "x")
    .toLowerCase()
    .replace(/ё/g, "е")
    .replace(/[^a-z0-9а-я]+/gi, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 48) || "x";
}

function ensureDir(p) {
  fs.mkdirSync(p, { recursive: true });
}

async function isLoginPage(page) {
  const url = page.url();
  if (/\/login(\?|$)/.test(url)) return true;
  const title = await page.locator("h1, .login-card, button.login-btn-primary").first().innerText().catch(() => "");
  return /войти|имя пользователя|bi analytics/i.test(title) && (await page.locator("input[type='password']").count()) > 0;
}

async function login(page, base, user, pass) {
  await page.goto(`${base}/login`, { waitUntil: "domcontentloaded", timeout: 90000 });
  await page.waitForTimeout(600);
  await page.locator('input[autocomplete="username"], input[name="username"], input[type="text"]').first().fill(user);
  await page
    .locator('input[autocomplete="current-password"], input[name="password"], input[type="password"]')
    .first()
    .fill(pass);
  await page.locator("button.login-btn-primary, button[type='submit']").first().click();
  await page.waitForURL((u) => !String(u.pathname).includes("/login"), { timeout: 60000 });
}

async function ensureLoggedIn(page, base, user, pass) {
  if (await isLoginPage(page)) {
    await login(page, base, user, pass);
  }
}

async function waitReady(page, ms = SETTLE_MS) {
  await page.waitForTimeout(Math.min(ms, 1200));
  for (let i = 0; i < 45; i++) {
    if (await isLoginPage(page)) return false;
    const overlay = await page.locator("text=/Загрузка дашборда/i").count();
    const busy = await page.locator("text=/^Загрузка|^пересчёт|^Loading/i").count();
    const hasTitle = await page.locator("h1").count();
    if (!overlay && hasTitle && busy < 2) {
      await page.waitForTimeout(600);
      return true;
    }
    await page.waitForTimeout(700);
  }
  return !(await isLoginPage(page));
}

async function maskDynamic(page) {
  await page.addStyleTag({
    content: `
      aside section:has(button:has-text("FTP")),
      aside section:has-text("Версия данных"),
      aside section:has-text(" Staging") { visibility: hidden !important; }
    `,
  }).catch(() => {});
}

async function shot(page, dir, name, { full = false } = {}) {
  const file = path.join(dir, `${name}.png`);
  await page.screenshot({ path: file, fullPage: full, animations: "disabled" });
  return file;
}

async function discoverTabs(page) {
  return page.evaluate((skipSrc) => {
    const skip = new RegExp(skipSrc, "i");
    const vis = (el) => {
      const r = el.getBoundingClientRect();
      const st = getComputedStyle(el);
      return r.width > 4 && r.height > 4 && st.visibility !== "hidden" && st.display !== "none";
    };
    const groups = [];
    const seen = new Set();
    for (const btn of document.querySelectorAll("main button")) {
      if (btn.closest(".bi-tabbar, nav.bi-tabbar, aside")) continue;
      const parent = btn.parentElement;
      if (!parent || seen.has(parent)) continue;
      const kids = [...parent.children].filter((el) => el.tagName === "BUTTON" && vis(el));
      if (kids.length < 2 || kids.length > 10) continue;
      const labels = kids.map((k) => (k.innerText || "").trim().replace(/\s+/g, " "));
      const joined = labels.join("|");
      if (skip.test(joined)) continue;
      if (/поиск|тёмн|светл|ширина|плотность|горяч|меню|профиль|вверх/i.test(joined)) continue;
      const cls = `${parent.className || ""} ${parent.parentElement?.className || ""}`;
      const tabby = /border-b|gap-1|gap-4/.test(cls);
      if (!tabby) continue;
      seen.add(parent);
      groups.push(labels);
    }
    return groups[0] || [];
  }, SKIP_RE.source);
}

async function clickTab(page, label) {
  const loc = page
    .locator("main button")
    .filter({ hasText: new RegExp(`^\\s*${escapeRe(label)}\\s*$`) })
    .filter({ visible: true });
  const n = await loc.count();
  if (!n) return false;
  try {
    await loc.first().click({ timeout: 2500 });
    return true;
  } catch {
    return false;
  }
}

function escapeRe(s) {
  return String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

async function openFilters(page) {
  const trigger = page.locator("button[aria-expanded]").filter({ hasText: /фильтр/i }).first();
  if (!(await trigger.count())) return false;
  const expanded = await trigger.getAttribute("aria-expanded");
  if (expanded !== "true") {
    await trigger.click({ timeout: 2000 }).catch(() => {});
    await page.waitForTimeout(400);
  }
  return true;
}

async function listFilterChecks(page) {
  return page.evaluate(() => {
    const out = [];
    document.querySelectorAll(".bi-filters-check input[type='checkbox']:not([disabled])").forEach((el, i) => {
      const label = (el.closest("label")?.innerText || el.getAttribute("name") || `check_${i}`)
        .trim()
        .replace(/\s+/g, " ")
        .slice(0, 60);
      out.push({ i, label, checked: el.checked });
    });
    return out;
  });
}

async function toggleFilterCheck(page, index) {
  const box = page.locator(".bi-filters-check input[type='checkbox']:not([disabled])").nth(index);
  if (!(await box.count())) return false;
  await box.click({ timeout: 2000, force: true });
  return true;
}

async function openFilterDropdowns(page, maxN) {
  const labels = [];
  const fields = page.locator(".bi-filters-field button, .bi-filters-field [role='combobox'], .bi-filters-field-control button");
  const n = Math.min(await fields.count(), maxN);
  for (let i = 0; i < n; i++) {
    const el = fields.nth(i);
    const text = ((await el.innerText().catch(() => "")) || `dd_${i}`).trim().slice(0, 40);
    if (SKIP_RE.test(text)) continue;
    try {
      await el.click({ timeout: 1500 });
      await page.waitForTimeout(300);
      labels.push(text || `dd_${i}`);
    } catch {
      /* ignore */
    }
  }
  await page.keyboard.press("Escape").catch(() => {});
  return labels;
}

async function setTheme(page, dark) {
  await page.evaluate((wantDark) => {
    const root = document.documentElement;
    if (wantDark) root.classList.add("dark");
    else root.classList.remove("dark");
    try {
      localStorage.setItem("bi_showcase_theme_v3", wantDark ? "dark" : "light");
    } catch {
      /* ignore */
    }
  }, dark);
  await page.waitForTimeout(250);
}

async function walkRoute(page, route, shotDir, creds) {
  const shots = [];
  const actions = [];
  if (creds) await ensureLoggedIn(page, creds.base, creds.user, creds.pass);
  const ready = await waitReady(page, NAV_MS);
  if (!ready || (await isLoginPage(page))) {
    actions.push("login_or_loading");
    return { shots, actions, tabs: [] };
  }
  await maskDynamic(page);

  await setTheme(page, false);
  shots.push({ id: `${route.id}__00_default`, file: await shot(page, shotDir, `${route.id}__00_default`) });
  shots.push({
    id: `${route.id}__00_default_full`,
    file: await shot(page, shotDir, `${route.id}__00_default_full`, { full: true }),
  });
  actions.push("default");

  const tabs = (await discoverTabs(page)).slice(0, MAX_TABS);
  actions.push(`tabs:${tabs.join("|") || "-"}`);
  for (let i = 0; i < tabs.length; i++) {
    const label = tabs[i];
    const ok = await clickTab(page, label);
    if (!ok) continue;
    await waitReady(page);
    const id = `${route.id}__10_tab_${String(i).padStart(2, "0")}_${slug(label)}`;
    shots.push({ id, file: await shot(page, shotDir, id) });
  }
  if (tabs.length) {
    await clickTab(page, tabs[0]).catch(() => {});
    await waitReady(page, 800);
  }

  const filtersOpened = await openFilters(page).catch(() => false);
  if (filtersOpened) {
    await page.waitForTimeout(400);
    const id = `${route.id}__20_filters_open`;
    shots.push({ id, file: await shot(page, shotDir, id) });
    actions.push("filters_open");

    const dds = await openFilterDropdowns(page, MAX_DROPDOWNS);
    if (dds.length) {
      const did = `${route.id}__21_filters_dropdown`;
      shots.push({ id: did, file: await shot(page, shotDir, did) });
      actions.push(`dropdowns:${dds.join("|")}`);
      await page.keyboard.press("Escape").catch(() => {});
    }

    const checks = (await listFilterChecks(page)).slice(0, MAX_CHECKS);
    actions.push(`checks:${checks.map((c) => c.label).join("|") || "-"}`);
    for (const c of checks) {
      const ok = await toggleFilterCheck(page, c.i);
      if (!ok) continue;
      await waitReady(page);
      const sid = `${route.id}__30_check_${String(c.i).padStart(2, "0")}_${slug(c.label)}`;
      shots.push({ id: sid, file: await shot(page, shotDir, sid) });
      await toggleFilterCheck(page, c.i);
      await waitReady(page, 600);
    }
  }

  await setTheme(page, true);
  await page.waitForTimeout(300);
  const darkId = `${route.id}__90_dark`;
  shots.push({ id: darkId, file: await shot(page, shotDir, darkId) });
  actions.push("theme_dark");
  await setTheme(page, false);

  return { shots, actions, tabs };
}

async function runSite(browser, label, base, user, pass, shotDir) {
  ensureDir(shotDir);
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    ignoreHTTPSErrors: true,
    locale: "ru-RU",
  });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on("pageerror", (e) => consoleErrors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error") consoleErrors.push(m.text());
  });

  const result = { label, base, login: false, routes: [], consoleErrors: [] };
  try {
    await login(page, base, user, pass);
    result.login = true;
  } catch (e) {
    result.loginError = String(e);
    await context.close();
    return result;
  }

  const routes = ROUTES.filter((r) => !ONLY.size || ONLY.has(r.id));
  const creds = { base, user, pass };
  for (const route of routes) {
    const entry = { id: route.id, href: route.href, ok: true, issues: [], shots: [], actions: [] };
    try {
      await setTheme(page, false);
      await page.goto(`${base}${route.href}`, { waitUntil: "domcontentloaded", timeout: 120000 });
      if (await isLoginPage(page)) {
        await login(page, base, user, pass);
        await page.goto(`${base}${route.href}`, { waitUntil: "domcontentloaded", timeout: 120000 });
      }
      const walked = await walkRoute(page, route, shotDir, creds);
      entry.shots = walked.shots.map((s) => s.id);
      entry.actions = walked.actions;
      if (!entry.shots.length) {
        entry.ok = false;
        entry.issues.push("no screenshots (login or still loading)");
      }
    } catch (e) {
      entry.ok = false;
      entry.issues.push(String(e).slice(0, 400));
    }
    result.routes.push(entry);
    console.log(`[${label}] ${route.id}: ${entry.ok ? "OK" : "FAIL"} shots=${entry.shots.length} ${entry.issues[0] || ""}`);
  }

  result.consoleErrors = consoleErrors.slice(0, 50);
  await context.close();
  return result;
}

function pixelDiff(aPath, bPath, diffPath) {
  const img1 = PNG.sync.read(fs.readFileSync(aPath));
  const img2 = PNG.sync.read(fs.readFileSync(bPath));
  const w = Math.min(img1.width, img2.width);
  const h = Math.min(img1.height, img2.height);
  const diff = new PNG({ width: w, height: h });
  const crop = (img) => {
    if (img.width === w && img.height === h) return img.data;
    const out = Buffer.alloc(w * h * 4);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const si = (y * img.width + x) * 4;
        const di = (y * w + x) * 4;
        out[di] = img.data[si];
        out[di + 1] = img.data[si + 1];
        out[di + 2] = img.data[si + 2];
        out[di + 3] = img.data[si + 3];
      }
    }
    return out;
  };
  const mismatched = pixelmatch(crop(img1), crop(img2), diff.data, w, h, { threshold: 0.18 });
  fs.writeFileSync(diffPath, PNG.sync.write(diff));
  return { mismatched, ratio: mismatched / (w * h), width: w, height: h };
}

function writeHtml(outDir, comparisons) {
  const rows = comparisons
    .map((c) => {
      const cls = c.ok ? "ok" : "bad";
      const pct = c.ratio != null ? `${(c.ratio * 100).toFixed(2)}%` : c.reason || "";
      const prod = c.prodRel ? `<img src="${c.prodRel}" />` : "";
      const dev = c.devRel ? `<img src="${c.devRel}" />` : "";
      const diff = c.diffRel ? `<img src="${c.diffRel}" />` : "";
      return `<tr class="${cls}"><td>${c.id}</td><td>${pct}</td><td>${prod}</td><td>${dev}</td><td>${diff}</td></tr>`;
    })
    .join("\n");
  const html = `<!doctype html><html lang="ru"><head><meta charset="utf-8"/><title>Visual walk prod vs cloudpub</title>
<style>
body{font:14px/1.4 system-ui,sans-serif;margin:16px;background:#111;color:#eee}
table{border-collapse:collapse;width:100%}
th,td{border:1px solid #333;padding:6px;vertical-align:top}
img{max-width:420px;height:auto;background:#222}
tr.bad{background:#3a1515} tr.ok{background:#14301a}
.sticky{position:sticky;top:0;background:#111;padding:8px 0}
</style></head><body>
<div class="sticky"><h1>Visual walk: ai.conall.ru vs cloudpub</h1>
<p>Красные строки — pixel-diff выше порога. Смотри столбец Diff.</p></div>
<table><thead><tr><th>id</th><th>diff</th><th>prod</th><th>cloudpub</th><th>diff</th></tr></thead>
<tbody>${rows}</tbody></table></body></html>`;
  fs.writeFileSync(path.join(outDir, "compare.html"), html);
}

async function main() {
  ensureDir(OUT);
  const prodDir = path.join(OUT, "prod");
  const devDir = path.join(OUT, "dev");
  const diffDir = path.join(OUT, "diff");
  ensureDir(diffDir);
  console.log("OUT", OUT);
  console.log("PROD", PROD_BASE, "DEV", DEV_BASE, "SITE", SITE);

  const browser = await chromium.launch({ headless: process.env.HEADED !== "1" });
  let prod = { login: false, routes: [], label: "prod", base: PROD_BASE };
  let dev = { login: false, routes: [], label: "dev", base: DEV_BASE };

  if (SITE === "prod" || SITE === "both") {
    prod = await runSite(browser, "prod", PROD_BASE, PROD_USER, PROD_PASS, prodDir);
  }
  if (SITE === "dev" || SITE === "both") {
    dev = await runSite(browser, "dev", DEV_BASE, DEV_USER, DEV_PASS, devDir);
    if (!dev.login && DEV_PASS !== "admin") {
      console.log("dev login retry admin/admin");
      dev = await runSite(browser, "dev", DEV_BASE, "admin", "admin", devDir);
    }
  }
  await browser.close();

  const ids = new Set();
  for (const dir of [prodDir, devDir]) {
    if (!fs.existsSync(dir)) continue;
    for (const f of fs.readdirSync(dir)) {
      if (f.endsWith(".png")) ids.add(f.replace(/\.png$/, ""));
    }
  }

  const comparisons = [];
  for (const id of [...ids].sort()) {
    const p = path.join(prodDir, `${id}.png`);
    const d = path.join(devDir, `${id}.png`);
    const row = {
      id,
      ok: false,
      prodRel: fs.existsSync(p) ? `prod/${id}.png` : null,
      devRel: fs.existsSync(d) ? `dev/${id}.png` : null,
    };
    if (!row.prodRel || !row.devRel) {
      row.reason = "missing screenshot";
      comparisons.push(row);
      continue;
    }
    try {
      const diffPath = path.join(diffDir, `${id}.png`);
      const r = pixelDiff(p, d, diffPath);
      row.ratio = Number(r.ratio.toFixed(4));
      row.mismatched = r.mismatched;
      row.ok = r.ratio <= DIFF_THRESHOLD;
      row.diffRel = `diff/${id}.png`;
      console.log(`diff ${id}: ${(r.ratio * 100).toFixed(2)}% ${row.ok ? "OK" : "DIFF"}`);
    } catch (e) {
      row.reason = String(e);
    }
    comparisons.push(row);
  }

  writeHtml(OUT, comparisons);
  const report = {
    generatedAt: new Date().toISOString(),
    prodBase: PROD_BASE,
    devBase: DEV_BASE,
    threshold: DIFF_THRESHOLD,
    prod,
    dev,
    comparisons,
    summary: {
      prodLogin: prod.login,
      devLogin: dev.login,
      shots: comparisons.length,
      visualDiffs: comparisons.filter((c) => !c.ok).map((c) => c.id),
    },
  };
  fs.writeFileSync(path.join(OUT, "report.json"), JSON.stringify(report, null, 2));
  const md = [
    `# Visual walk prod vs cloudpub`,
    `Generated: ${report.generatedAt}`,
    "",
    `- Prod: ${PROD_BASE} login=${prod.login}`,
    `- Dev: ${DEV_BASE} login=${dev.login}`,
    `- Shots compared: ${comparisons.length}`,
    `- Diffs > ${DIFF_THRESHOLD * 100}%: ${report.summary.visualDiffs.length}`,
    "",
    `Open \`compare.html\` for side-by-side.`,
    "",
    `## Diffs`,
    ...(report.summary.visualDiffs.length
      ? report.summary.visualDiffs.map((id) => {
          const c = comparisons.find((x) => x.id === id);
          return `- ${id}: ${c?.ratio != null ? `${(c.ratio * 100).toFixed(2)}%` : c?.reason}`;
        })
      : ["(none)"]),
  ];
  fs.writeFileSync(path.join(OUT, "REPORT.md"), md.join("\n"));
  console.log("\n=== SUMMARY ===");
  console.log(JSON.stringify(report.summary, null, 2));
  console.log("HTML", path.join(OUT, "compare.html"));
}

main().catch((e) => {
  console.error(e);
  process.exit(2);
});
