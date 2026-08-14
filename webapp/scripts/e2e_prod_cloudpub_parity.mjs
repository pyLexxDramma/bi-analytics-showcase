#!/usr/bin/env node
/**
 * E2E parity: ai.conall.ru (prod) vs cloudpub (dev).
 *
 * Usage (from webapp/):
 *   node scripts/e2e_prod_cloudpub_parity.mjs
 *
 * Env:
 *   PROD_BASE / DEV_BASE / PROD_USER / PROD_PASS / DEV_USER / DEV_PASS
 *   SETTLE_MS=4500  DIFF_THRESHOLD=0.14
 */
import { chromium } from "playwright";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { PNG } from "pngjs";
import pixelmatch from "pixelmatch";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PROD_BASE = (process.env.PROD_BASE || "https://ai.conall.ru").replace(/\/$/, "");
const DEV_BASE = (
  process.env.DEV_BASE || "https://insipidly-carefree-husky.cloudpub.ru"
).replace(/\/$/, "");
const PROD_USER = process.env.PROD_USER || "admin";
const PROD_PASS = process.env.PROD_PASS || "adminAIcon!2026X";
const DEV_USER = process.env.DEV_USER || "admin";
const DEV_PASS = process.env.DEV_PASS || process.env.PROD_PASS || "adminAIcon!2026X";
const SETTLE_MS = Number(process.env.SETTLE_MS || 4500);
const DIFF_THRESHOLD = Number(process.env.DIFF_THRESHOLD || 0.14);
const OUT = path.resolve(
  process.env.PARITY_OUT || path.join(__dirname, "..", "parity_out", `run_${Date.now()}`),
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

const ERROR_PATTERNS = [
  /API\s*500/i,
  /API\s*50\d/i,
  /has no attribute/i,
  /KeyError/i,
  /Нет MSP/i,
  /нет MSP/i,
  /Traceback/i,
  /Internal Server Error/i,
  /float' object/i,
  /Bearer token required/i,
];

/** Routes where KPI totals must be non-zero (rub). */
const FINANCE_MUST_HAVE_DATA = new Set([
  "bdds",
  "bdr",
  "approved-budget",
  "bdds-plan-fact",
]);

function ensureDir(p) {
  fs.mkdirSync(p, { recursive: true });
}

async function login(page, base, user, pass) {
  await page.goto(`${base}/login`, { waitUntil: "domcontentloaded", timeout: 90000 });
  await page.waitForTimeout(800);
  const userSel = 'input[autocomplete="username"], input[name="username"], input[type="text"]';
  const passSel =
    'input[autocomplete="current-password"], input[name="password"], input[type="password"]';
  await page.locator(userSel).first().fill(user);
  await page.locator(passSel).first().fill(pass);
  const btn = page.locator("button.login-btn-primary, button[type='submit']").first();
  await btn.click();
  await page.waitForURL((u) => !String(u.pathname).includes("/login"), { timeout: 60000 });
}

async function collectPageIssues(page) {
  const bodyText = (await page.locator("body").innerText().catch(() => "")) || "";
  const hits = [];
  for (const re of ERROR_PATTERNS) {
    if (re.test(bodyText)) hits.push(re.source);
  }
  const snippet = bodyText
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => ERROR_PATTERNS.some((re) => re.test(l)))
    .slice(0, 8);
  return { hits, snippet, bodyLen: bodyText.length };
}

function pixelDiff(prodPngPath, devPngPath, diffPath) {
  const img1 = PNG.sync.read(fs.readFileSync(prodPngPath));
  const img2 = PNG.sync.read(fs.readFileSync(devPngPath));
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
  const mismatched = pixelmatch(crop(img1), crop(img2), diff.data, w, h, { threshold: 0.2 });
  fs.writeFileSync(diffPath, PNG.sync.write(diff));
  return { mismatched, ratio: mismatched / (w * h), width: w, height: h };
}

async function fetchHealth(base, requestContext) {
  try {
    if (requestContext) {
      const r = await requestContext.get(`${base}/api/health`, { timeout: 45000 });
      const j = await r.json().catch(() => ({}));
      return { ok: r.ok(), status: r.status(), body: j };
    }
    const r = await fetch(`${base}/api/health`, { signal: AbortSignal.timeout(45000) });
    const j = await r.json();
    return { ok: r.ok, status: r.status, body: j };
  } catch (e) {
    return { ok: false, status: 0, error: String(e) };
  }
}

async function dataFingerprint(page) {
  const text = (await page.locator("main, [role='main'], body").first().innerText().catch(() => "")) || "";
  const nums = (text.match(/-?\d[\d\s]*([.,]\d+)?/g) || [])
    .map((s) => s.replace(/\s/g, "").replace(",", "."))
    .filter((s) => s.length >= 2)
    .slice(0, 80);
  const titles = (await page.locator("h1, h2, .kpi-label, [data-kpi]").allTextContents().catch(() => []))
    .map((t) => t.trim())
    .filter(Boolean)
    .slice(0, 20);
  return { titles, numsSample: nums.slice(0, 40), numsCount: nums.length };
}

async function exerciseFilters(page) {
  const clicks = [];
  const candidates = page.locator(
    "button:has-text('Фильтр'), button:has-text('Фильтры'), [role='checkbox'], label:has(input[type='checkbox'])",
  );
  const n = Math.min(await candidates.count(), 4);
  for (let i = 0; i < n; i++) {
    try {
      await candidates.nth(i).click({ timeout: 1500 });
      clicks.push(i);
      await page.waitForTimeout(300);
    } catch {
      /* ignore */
    }
  }
  return clicks;
}

function checkDeployWiring() {
  const root = path.resolve(__dirname, "..", "..");
  const webappYml = fs.readFileSync(path.join(root, ".github", "workflows", "webapp.yml"), "utf8");
  const prodYml = fs.readFileSync(
    path.join(root, ".github", "workflows", "deploy-ai-conall-prod.yml"),
    "utf8",
  );
  const issues = [];
  if (!webappYml.includes("push:") || !webappYml.includes("main")) {
    issues.push("webapp.yml: expected auto-deploy on push to main (cloudpub/dev)");
  }
  if (!webappYml.includes("server_deploy.sh")) {
    issues.push("webapp.yml: expected server_deploy.sh (cloudpub :3080)");
  }
  if (prodYml.includes("push:")) {
    issues.push("deploy-ai-conall-prod.yml: must NOT auto-deploy on push");
  }
  if (!prodYml.includes("workflow_dispatch:")) {
    issues.push("deploy-ai-conall-prod.yml: expected workflow_dispatch only");
  }
  if (!prodYml.includes("server_deploy_prod.sh")) {
    issues.push("deploy-ai-conall-prod.yml: expected server_deploy_prod.sh");
  }
  return { ok: issues.length === 0, issues };
}

async function runSite(browser, label, base, user, pass, shotDir) {
  ensureDir(shotDir);
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    ignoreHTTPSErrors: true,
  });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on("pageerror", (e) => consoleErrors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error") consoleErrors.push(m.text());
  });

  const result = {
    label,
    base,
    login: false,
    routes: [],
    consoleErrors: [],
    health: await fetchHealth(base, context.request),
  };
  try {
    await login(page, base, user, pass);
    result.login = true;
  } catch (e) {
    result.loginError = String(e);
    await context.close();
    return result;
  }

  for (const route of ROUTES) {
    const entry = { id: route.id, href: route.href, ok: true, issues: [] };
    const apiTotals = [];
    const onResp = async (r) => {
      const u = r.url();
      if (!/\/api\/(bdds|bdr|approved-budget|bdds-plan-fact)(\?|$)/.test(u)) return;
      try {
        const j = await r.json();
        apiTotals.push({ url: u, status: r.status(), totals: j.totals || null, error: j.meta?.error || null });
      } catch {
        /* ignore */
      }
    };
    page.on("response", onResp);
    try {
      await page.goto(`${base}${route.href}`, {
        waitUntil: "domcontentloaded",
        timeout: 120000,
      });
      await page.waitForTimeout(SETTLE_MS);
      for (let i = 0; i < 20; i++) {
        const busy = await page.locator("text=/Загрузка|пересчёт|Loading/i").count();
        if (!busy) break;
        await page.waitForTimeout(400);
      }
      // Optional: do not randomly toggle filters — that emptied both UIs in prior runs.
      if (process.env.EXERCISE_FILTERS === "1") {
        entry.filterClicks = await exerciseFilters(page);
        await page.waitForTimeout(600);
      }
      const issues = await collectPageIssues(page);
      if (issues.hits.length) {
        entry.ok = false;
        entry.issues = issues.snippet.length ? issues.snippet : issues.hits;
      }
      entry.apiTotals = apiTotals;
      if (FINANCE_MUST_HAVE_DATA.has(route.id)) {
        const t = apiTotals.find((x) => x.totals)?.totals;
        const sum =
          Math.abs(Number(t?.plan || 0)) +
          Math.abs(Number(t?.fact || 0)) +
          Math.abs(Number(t?.forecast || 0));
        if (!t || sum < 1) {
          entry.ok = false;
          entry.issues.push(`finance totals empty: ${JSON.stringify(t)}`);
        }
      }
      entry.fingerprint = await dataFingerprint(page);
      const shot = path.join(shotDir, `${route.id}.png`);
      await page.screenshot({ path: shot, fullPage: false });
      // Also full-page for finance screens
      if (FINANCE_MUST_HAVE_DATA.has(route.id)) {
        await page.screenshot({
          path: path.join(shotDir, `${route.id}__full.png`),
          fullPage: true,
        });
      }
      entry.screenshot = shot;
    } catch (e) {
      entry.ok = false;
      entry.issues.push(String(e).slice(0, 400));
    } finally {
      page.off("response", onResp);
    }
    result.routes.push(entry);
    console.log(`[${label}] ${route.id}: ${entry.ok ? "OK" : "FAIL"} ${entry.issues[0] || ""}`);
  }

  result.consoleErrors = consoleErrors.slice(0, 40);
  await context.close();
  return result;
}

async function main() {
  ensureDir(OUT);
  console.log("OUT", OUT);
  console.log("PROD", PROD_BASE, "DEV", DEV_BASE);

  const deploy = checkDeployWiring();
  console.log("deploy wiring", deploy);

  const browser = await chromium.launch({ headless: true });
  const prodDir = path.join(OUT, "prod");
  const devDir = path.join(OUT, "dev");
  const diffDir = path.join(OUT, "diff");
  ensureDir(diffDir);

  const prod = await runSite(browser, "prod", PROD_BASE, PROD_USER, PROD_PASS, prodDir);
  let dev = await runSite(browser, "dev", DEV_BASE, DEV_USER, DEV_PASS, devDir);
  if (!dev.login && DEV_PASS !== "admin") {
    console.log("dev login failed with PROD pass, retry admin/admin");
    dev = await runSite(browser, "dev", DEV_BASE, "admin", "admin", devDir);
  }
  await browser.close();

  const healthProd = prod.health || { ok: false };
  const healthDev = dev.health || { ok: false };
  console.log(
    "health prod",
    healthProd.status,
    healthProd.body?.data_mode,
    healthProd.body?.active_version_id,
  );
  console.log(
    "health dev",
    healthDev.status,
    healthDev.body?.data_mode,
    healthDev.body?.active_version_id,
  );

  const comparisons = [];
  const dataMismatches = [];
  for (const route of ROUTES) {
    const p = path.join(prodDir, `${route.id}.png`);
    const d = path.join(devDir, `${route.id}.png`);
    const prodRoute = prod.routes.find((r) => r.id === route.id);
    const devRoute = dev.routes.find((r) => r.id === route.id);
    if (prodRoute?.fingerprint && devRoute?.fingerprint) {
      const a = prodRoute.fingerprint.numsSample || [];
      const b = devRoute.fingerprint.numsSample || [];
      const overlap = a.filter((x) => b.includes(x)).length;
      const union = new Set([...a, ...b]).size || 1;
      const jaccard = overlap / union;
      if (jaccard < 0.35 && a.length > 5 && b.length > 5) {
        dataMismatches.push({
          id: route.id,
          jaccard: Number(jaccard.toFixed(3)),
          prodNums: a.slice(0, 8),
          devNums: b.slice(0, 8),
        });
      }
    }
    if (!fs.existsSync(p) || !fs.existsSync(d)) {
      comparisons.push({ id: route.id, ok: false, reason: "missing screenshot" });
      continue;
    }
    try {
      const diffPath = path.join(diffDir, `${route.id}.png`);
      const r = pixelDiff(p, d, diffPath);
      const ok = r.ratio <= DIFF_THRESHOLD;
      comparisons.push({
        id: route.id,
        ok,
        ratio: Number(r.ratio.toFixed(4)),
        mismatched: r.mismatched,
        diff: diffPath,
      });
      console.log(`diff ${route.id}: ${(r.ratio * 100).toFixed(2)}% ${ok ? "OK" : "DIFF"}`);
    } catch (e) {
      comparisons.push({ id: route.id, ok: false, reason: String(e) });
    }
  }

  const report = {
    generatedAt: new Date().toISOString(),
    prodBase: PROD_BASE,
    devBase: DEV_BASE,
    deploy,
    health: { prod: healthProd, dev: healthDev },
    prod,
    dev,
    comparisons,
    dataMismatches,
    summary: {
      prodLogin: prod.login,
      devLogin: dev.login,
      prodRouteFails: prod.routes.filter((r) => !r.ok).map((r) => r.id),
      devRouteFails: dev.routes.filter((r) => !r.ok).map((r) => r.id),
      visualDiffs: comparisons.filter((c) => !c.ok).map((c) => c.id),
      dataMismatches: dataMismatches.map((d) => d.id),
      ftpProd: healthProd.body?.data_mode === "ftp" && healthProd.body?.ftp_configured === true,
      ftpDev: healthDev.body?.data_mode === "ftp" && healthDev.body?.ftp_configured === true,
      deployOk: deploy.ok,
      prodVersion: healthProd.body?.active_version_id ?? null,
      devVersion: healthDev.body?.active_version_id ?? null,
    },
  };

  const reportPath = path.join(OUT, "report.json");
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));

  const md = [];
  md.push(`# Parity report prod vs cloudpub`);
  md.push(`Generated: ${report.generatedAt}`);
  md.push("");
  md.push(`- Prod: ${PROD_BASE} login=${prod.login}`);
  md.push(`- Dev: ${DEV_BASE} login=${dev.login}`);
  md.push(
    `- FTP prod: ${report.summary.ftpProd} (mode=${healthProd.body?.data_mode}, ver=${healthProd.body?.active_version_id})`,
  );
  md.push(
    `- FTP dev: ${report.summary.ftpDev} (mode=${healthDev.body?.data_mode}, ver=${healthDev.body?.active_version_id})`,
  );
  md.push(`- Deploy wiring OK: ${deploy.ok}`);
  if (deploy.issues.length) md.push(`  - ${deploy.issues.join("; ")}`);
  md.push("");
  md.push(`## Prod route failures`);
  md.push(report.summary.prodRouteFails.length ? report.summary.prodRouteFails.join(", ") : "(none)");
  md.push("");
  md.push(`## Dev route failures`);
  md.push(report.summary.devRouteFails.length ? report.summary.devRouteFails.join(", ") : "(none)");
  md.push("");
  md.push(`## Visual diffs (> ${DIFF_THRESHOLD * 100}%)`);
  for (const c of comparisons.filter((x) => !x.ok)) {
    md.push(`- ${c.id}: ${c.ratio != null ? (c.ratio * 100).toFixed(2) + "%" : c.reason}`);
  }
  if (!report.summary.visualDiffs.length) md.push("(none under threshold)");
  md.push("");
  md.push(`## Data number mismatches (Jaccard < 0.35)`);
  if (!dataMismatches.length) md.push("(none)");
  for (const d of dataMismatches) {
    md.push(`- ${d.id}: j=${d.jaccard} prod=${d.prodNums.join(",")} dev=${d.devNums.join(",")}`);
  }
  md.push("");
  md.push(`Artifacts: \`${OUT}\``);
  fs.writeFileSync(path.join(OUT, "REPORT.md"), md.join("\n"));

  console.log("\n=== SUMMARY ===");
  console.log(JSON.stringify(report.summary, null, 2));
  console.log("Wrote", reportPath);

  const hardFail =
    !prod.login ||
    !report.summary.ftpProd ||
    !deploy.ok ||
    report.summary.prodRouteFails.length > 0;
  process.exit(hardFail ? 1 : 0);
}

main().catch((e) => {
  console.error(e);
  process.exit(2);
});
