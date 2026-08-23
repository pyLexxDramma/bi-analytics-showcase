#!/usr/bin/env node
/**
 * Parity walk: local (правки) vs ref (cloudpub = ai.conall.ru).
 *
 * Env:
 *   LOCAL_BASE  REF_BASE  LOCAL_USER  LOCAL_PASS  REF_USER  REF_PASS
 *   (aliases: PROD_BASE→LOCAL, DEV_BASE→REF, SITE local|ref|both)
 *   VIEWPORTS=desktop,mobile  SIMPLE_SHOTS=1  ONLY=bdds
 */
import { chromium } from "playwright";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { PNG } from "pngjs";
import pixelmatch from "pixelmatch";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const LOCAL_BASE = (
  process.env.LOCAL_BASE ||
  process.env.PROD_BASE ||
  "http://127.0.0.1:3000"
).replace(/\/$/, "");
const REF_BASE = (
  process.env.REF_BASE ||
  process.env.DEV_BASE ||
  "https://insipidly-carefree-husky.cloudpub.ru"
).replace(/\/$/, "");
const LOCAL_USER = process.env.LOCAL_USER || process.env.PROD_USER || "admin";
const LOCAL_PASS = process.env.LOCAL_PASS || process.env.PROD_PASS || "admin";
const REF_USER = process.env.REF_USER || process.env.DEV_USER || "admin";
const REF_PASS = process.env.REF_PASS || process.env.DEV_PASS || "admin";
const SETTLE_MS = Number(process.env.SETTLE_MS || 2500);
const NAV_MS = Number(process.env.NAV_MS || 4000);
const DIFF_THRESHOLD = Number(process.env.DIFF_THRESHOLD || 0.003);
const MAX_TABS = Number(process.env.MAX_TABS || 8);
const MAX_CHECKS = Number(process.env.MAX_CHECKS || 8);
const MAX_DROPDOWNS = Number(process.env.MAX_DROPDOWNS || 2);
const SITE_RAW = (process.env.SITE || "both").toLowerCase();
const SITE =
  SITE_RAW === "prod" ? "local" : SITE_RAW === "dev" ? "ref" : SITE_RAW;
const VIEWPORT_MAP = {
  desktop: { width: 1440, height: 900 },
  mobile: { width: 390, height: 844 },
};
const VIEWPORT_NAMES = (process.env.VIEWPORTS || "desktop,mobile")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);
const ONLY = new Set(
  (process.env.ONLY || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean),
);
const SIMPLE_SHOTS =
  process.env.SIMPLE_SHOTS === "1" ||
  (ONLY.size > 0 && process.env.SIMPLE_SHOTS !== "0");
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
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
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

async function isLoading(page) {
  return page.evaluate(() => {
    const vis = (el) => {
      if (el.closest(".sr-only, [aria-hidden='true']")) return false;
      const r = el.getBoundingClientRect();
      const st = getComputedStyle(el);
      if (st.visibility === "hidden" || st.display === "none" || Number(st.opacity) === 0) {
        return false;
      }
      // sr-only / clipped text must not block the walk
      if (r.width < 8 || r.height < 8) return false;
      return true;
    };
    for (const el of document.querySelectorAll("span, div, p")) {
      const t = (el.textContent || "").replace(/\s+/g, " ").trim();
      if (t === "Загрузка дашборда" && vis(el)) return true;
    }
    return false;
  });
}

async function waitReady(page, ms = SETTLE_MS) {
  await page.waitForTimeout(Math.min(ms, 800));
  const rounds = Math.max(80, Math.ceil(ms / 500) + 20);
  for (let i = 0; i < rounds; i++) {
    if (await isLoginPage(page)) return false;
    const loading = await isLoading(page);
    const hasTitle = (await page.locator("h1").count()) > 0;
    if (!loading && hasTitle) {
      await page.waitForTimeout(900);
      if (!(await isLoading(page))) return true;
    }
    await page.waitForTimeout(500);
  }
  return !(await isLoginPage(page)) && !(await isLoading(page));
}

async function maskDynamic(page) {
  await page.addStyleTag({
    content: `
      aside section:has(button:has-text("FTP")),
      aside section:has-text("Версия данных"),
      aside section:has-text(" Staging"),
      .modebar, .js-plotly-plot .modebar,
      [data-walk-mask] { visibility: hidden !important; }
    `,
  }).catch(() => {});
  await page.evaluate(() => {
    const hide = (el) => {
      if (el) el.style.setProperty("visibility", "hidden", "important");
    };
    for (const el of document.querySelectorAll("span, p, time, small")) {
      const t = (el.textContent || "").replace(/\s+/g, " ").trim();
      if (t.length < 90 && /данные на |снимок #|снимок \d/.test(t)) hide(el);
    }
    document.querySelectorAll(".modebar, .js-plotly-plot .modebar").forEach(hide);
  }).catch(() => {});
}

async function closePopovers(page) {
  await page.keyboard.press("Escape").catch(() => {});
  await page.keyboard.press("Escape").catch(() => {});
  await page.locator("h1").first().click({ timeout: 800 }).catch(() => {});
  await page.waitForTimeout(200);
}

async function shot(page, dir, name, { full = false } = {}) {
  if (!full) await closePopovers(page);
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
  let ready = await waitReady(page, NAV_MS);
  if (!ready || (await isLoginPage(page)) || (await isLoading(page))) {
    // Soft ready: title already rendered (loading overlay / waitReady false-positive).
    await page.waitForTimeout(1500);
    const soft =
      !(await isLoginPage(page)) &&
      (await page.locator("h1").count()) > 0 &&
      !(await isLoading(page));
    if (!soft) {
      actions.push("login_or_loading");
      return { shots, actions, tabs: [] };
    }
    ready = true;
    actions.push("soft_ready");
  }
  await maskDynamic(page);

  await setTheme(page, false);
  shots.push({ id: `${route.id}__00_default`, file: await shot(page, shotDir, `${route.id}__00_default`) });
  shots.push({
    id: `${route.id}__00_default_full`,
    file: await shot(page, shotDir, `${route.id}__00_default_full`, { full: true }),
  });
  actions.push("default");
  if (SIMPLE_SHOTS) {
    return { shots, actions, tabs: [] };
  }

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
      await closePopovers(page);
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

async function runSite(browser, label, base, user, pass, shotDir, viewport) {
  ensureDir(shotDir);
  const context = await browser.newContext({
    viewport,
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

function writeHtml(outDir, comparisons, title) {
  const rows = comparisons
    .map((c) => {
      const cls = c.ok ? "ok" : "bad";
      const pct = c.ratio != null ? `${(c.ratio * 100).toFixed(2)}%` : c.reason || "";
      const local = c.localRel ? `<img src="${c.localRel}" />` : "";
      const ref = c.refRel ? `<img src="${c.refRel}" />` : "";
      const diff = c.diffRel ? `<img src="${c.diffRel}" />` : "";
      return `<tr class="${cls}"><td>${c.id}</td><td>${pct}</td><td>${local}</td><td>${ref}</td><td>${diff}</td></tr>`;
    })
    .join("\n");
  const html = `<!doctype html><html lang="ru"><head><meta charset="utf-8"/><title>${title}</title>
<style>
body{font:14px/1.4 system-ui,sans-serif;margin:16px;background:#111;color:#eee}
table{border-collapse:collapse;width:100%}
th,td{border:1px solid #333;padding:6px;vertical-align:top}
img{max-width:420px;height:auto;background:#222}
tr.bad{background:#3a1515} tr.ok{background:#14301a}
.sticky{position:sticky;top:0;background:#111;padding:8px 0}
</style></head><body>
<div class="sticky"><h1>${title}</h1>
<p>Local = правки. Ref = cloudpub (= ai.conall.ru). Красные строки — pixel-diff выше порога.</p></div>
<table><thead><tr><th>id</th><th>diff</th><th>local</th><th>ref</th><th>diff</th></tr></thead>
<tbody>${rows}</tbody></table></body></html>`;
  fs.writeFileSync(path.join(outDir, "compare.html"), html);
}

async function compareDirs(localDir, refDir, diffDir, prefix = "") {
  const ids = new Set();
  for (const dir of [localDir, refDir]) {
    if (!fs.existsSync(dir)) continue;
    for (const f of fs.readdirSync(dir)) {
      if (f.endsWith(".png")) ids.add(f.replace(/\.png$/, ""));
    }
  }
  const comparisons = [];
  for (const id of [...ids].sort()) {
    const l = path.join(localDir, `${id}.png`);
    const r = path.join(refDir, `${id}.png`);
    const row = {
      id: prefix ? `${prefix}/${id}` : id,
      ok: false,
      localRel: fs.existsSync(l)
        ? `${prefix ? `${prefix}/` : ""}local/${id}.png`
        : null,
      refRel: fs.existsSync(r) ? `${prefix ? `${prefix}/` : ""}ref/${id}.png` : null,
    };
    if (!row.localRel || !row.refRel) {
      row.reason = "missing screenshot";
      comparisons.push(row);
      continue;
    }
    try {
      const diffPath = path.join(diffDir, `${prefix ? `${prefix}_` : ""}${id}.png`);
      const px = pixelDiff(l, r, diffPath);
      row.ratio = Number(px.ratio.toFixed(4));
      row.mismatched = px.mismatched;
      const full = id.endsWith("_full");
      row.ok = full ? true : row.ratio <= DIFF_THRESHOLD;
      row.full = full;
      row.diffRel = `${prefix ? `${prefix}/` : ""}diff/${prefix ? `${prefix}_` : ""}${id}.png`;
      console.log(
        `diff ${row.id}: ${(row.ratio * 100).toFixed(2)}% ${row.ok ? "OK" : "DIFF"}${full ? " (full)" : ""}`,
      );
    } catch (e) {
      row.reason = String(e);
    }
    comparisons.push(row);
  }
  return comparisons;
}

async function main() {
  ensureDir(OUT);
  console.log("OUT", OUT);
  console.log("LOCAL", LOCAL_BASE, "REF", REF_BASE, "SITE", SITE, "SIMPLE", SIMPLE_SHOTS);

  const browser = await chromium.launch({ headless: process.env.HEADED !== "1" });
  const allComparisons = [];
  const runMeta = { local: null, ref: null };

  for (const vpName of VIEWPORT_NAMES) {
    const viewport = VIEWPORT_MAP[vpName] || VIEWPORT_MAP.desktop;
    const vpRoot = path.join(OUT, vpName);
    const localDir = path.join(vpRoot, "local");
    const refDir = path.join(vpRoot, "ref");
    const diffDir = path.join(vpRoot, "diff");
    ensureDir(diffDir);

    let local = { login: false, routes: [], label: "local", base: LOCAL_BASE };
    let ref = { login: false, routes: [], label: "ref", base: REF_BASE };

    if (SITE === "local" || SITE === "both") {
      local = await runSite(browser, "local", LOCAL_BASE, LOCAL_USER, LOCAL_PASS, localDir, viewport);
      runMeta.local = local;
    }
    if (SITE === "ref" || SITE === "both") {
      ref = await runSite(browser, "ref", REF_BASE, REF_USER, REF_PASS, refDir, viewport);
      if (!ref.login && REF_PASS !== "admin") {
        console.log("ref login retry admin/admin");
        ref = await runSite(browser, "ref", REF_BASE, "admin", "admin", refDir, viewport);
      }
      runMeta.ref = ref;
    }

    const vpCmp = await compareDirs(localDir, refDir, diffDir, vpName);
    allComparisons.push(...vpCmp);
    writeHtml(vpRoot, vpCmp, `Parity ${vpName}: local vs ref`);
  }

  await browser.close();

  writeHtml(OUT, allComparisons, "Parity: local vs cloudpub (= ai.conall.ru)");
  const report = {
    generatedAt: new Date().toISOString(),
    localBase: LOCAL_BASE,
    refBase: REF_BASE,
    viewports: VIEWPORT_NAMES,
    simpleShots: SIMPLE_SHOTS,
    threshold: DIFF_THRESHOLD,
    local: runMeta.local,
    ref: runMeta.ref,
    comparisons: allComparisons,
    summary: {
      localLogin: runMeta.local?.login,
      refLogin: runMeta.ref?.login,
      shots: allComparisons.length,
      visualDiffs: allComparisons.filter((c) => !c.ok).map((c) => c.id),
    },
  };
  fs.writeFileSync(path.join(OUT, "report.json"), JSON.stringify(report, null, 2));
  const md = [
    `# Parity local vs ref (cloudpub)`,
    `Generated: ${report.generatedAt}`,
    "",
    `- Local: ${LOCAL_BASE} login=${runMeta.local?.login}`,
    `- Ref: ${REF_BASE} login=${runMeta.ref?.login}`,
    `- Viewports: ${VIEWPORT_NAMES.join(", ")}`,
    `- Shots compared: ${allComparisons.length}`,
    `- Diffs > ${DIFF_THRESHOLD * 100}%: ${report.summary.visualDiffs.length}`,
    "",
    `Open \`compare.html\` or \`desktop/compare.html\` / \`mobile/compare.html\`.`,
    "",
    `## Diffs`,
    ...(report.summary.visualDiffs.length
      ? report.summary.visualDiffs.map((id) => {
          const c = allComparisons.find((x) => x.id === id);
          return `- ${id}: ${c?.ratio != null ? `${(c.ratio * 100).toFixed(2)}%` : c?.reason}`;
        })
      : ["(none)"]),
  ];
  fs.writeFileSync(path.join(OUT, "REPORT.md"), md.join("\n"));
  console.log("\n=== SUMMARY ===");
  console.log(JSON.stringify(report.summary, null, 2));
  console.log("HTML", path.join(OUT, "compare.html"));
  if (process.env.OPEN_COMPARE === "1" && process.platform === "win32") {
    const { execFile } = await import("node:child_process");
    for (const p of [
      path.join(OUT, "compare.html"),
      path.join(OUT, "desktop", "compare.html"),
      path.join(OUT, "mobile", "compare.html"),
    ]) {
      if (fs.existsSync(p)) execFile("cmd", ["/c", "start", "", p]);
    }
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(2);
});
