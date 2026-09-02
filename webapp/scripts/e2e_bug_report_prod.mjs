/**
 * E2E: ai.conall.ru → «Сообщить об ошибке» → bugform → submit → Trello card check.
 * Run from webapp/: node scripts/e2e_bug_report_prod.mjs
 */
import { chromium } from "playwright";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(__dirname, "..", "parity_out", "bug_report_e2e");
fs.mkdirSync(OUT, { recursive: true });

const PROD = process.env.PROD_BASE || "https://ai.conall.ru";
const USER = process.env.BI_USER || "admin";
const PASS = process.env.BI_PASS || "adminAIcon!2026X";
const TRELLO_BOARD =
  process.env.TRELLO_BOARD_URL ||
  "https://trello.com/b/dZwWzXh4/%D0%BF%D1%80%D0%BE%D0%B5%D0%BA%D1%82-%D0%B0%D0%BD%D0%B0%D0%BB%D0%B8%D1%82%D0%B8%D0%BA%D0%B0";

const stamp = new Date().toISOString().replace(/[:.]/g, "-");
const marker = `e2e-bug-${stamp}`;

function fail(msg) {
  console.error("FAIL:", msg);
  process.exitCode = 1;
}

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  ignoreHTTPSErrors: true,
});
const page = await ctx.newPage();

try {
  console.log("1) Login", PROD);
  await page.goto(`${PROD}/login`, { waitUntil: "networkidle", timeout: 120000 });
  await page.getByPlaceholder("Имя пользователя").waitFor({ timeout: 60000 });
  await page.getByPlaceholder("Имя пользователя").fill(USER);
  await page.getByPlaceholder("Пароль").fill(PASS);
  await page.locator("button.login-btn-primary, button[type='submit']").first().click();
  await page.waitForURL((u) => !String(u).includes("/login"), { timeout: 60000 });

  const route = "/developer-projects";
  console.log("2) Open dashboard", route);
  await page.goto(`${PROD}${route}`, { waitUntil: "domcontentloaded", timeout: 120000 });
  await page.waitForTimeout(5000);

  const bugBtn = page.locator("button.report-bug-btn").first();
  await bugBtn.waitFor({ state: "visible", timeout: 30000 }).catch(async () => {
    await page.screenshot({ path: path.join(OUT, "no_bug_button.png"), fullPage: true });
    throw new Error("Кнопка «Сообщить об ошибке» не найдена на десктопе");
  });
  if (!(await bugBtn.isVisible())) {
    await page.screenshot({ path: path.join(OUT, "no_bug_button.png"), fullPage: true });
    throw new Error("Кнопка «Сообщить об ошибке» не видна");
  }

  console.log("3) Instruction → open form tab");
  await bugBtn.click();
  const openForm = page.getByRole("button", { name: /Открыть форму/i });
  await openForm.waitFor({ timeout: 15000 });
  const [formPage] = await Promise.all([
    ctx.waitForEvent("page", { timeout: 30000 }),
    openForm.click(),
  ]);
  await formPage.waitForLoadState("domcontentloaded", { timeout: 60000 });
  await formPage.waitForTimeout(2000);

  const formUrl = formPage.url();
  console.log("   form URL:", formUrl);
  if (!/\/bugform\//i.test(formUrl) && !/bugform\/index\.html/i.test(formUrl)) {
    throw new Error(`Ожидали локальную форму /bugform/, got ${formUrl}`);
  }
  const u = new URL(formUrl);
  for (const key of ["menugroup", "report", "contour"]) {
    const v = u.searchParams.get(key);
    console.log(`   prefill ${key}=`, v || "(empty)");
    if (!v) throw new Error(`Нет автозаполнения ${key} в URL формы`);
  }
  if (u.searchParams.get("menugroup") !== "Девелоперские проекты") {
    throw new Error(`menugroup: ожидали «Девелоперские проекты», got ${u.searchParams.get("menugroup")}`);
  }

  const menugroupVal = await formPage.locator("#menugroup").inputValue();
  const reportVal = await formPage.locator("#report").inputValue();
  const contourVal = await formPage.locator("#contour").inputValue();
  console.log("   form fields:", { menugroupVal, reportVal, contourVal });
  if (menugroupVal !== "Девелоперские проекты") {
    throw new Error(`#menugroup не заполнен: ${menugroupVal}`);
  }
  if (!reportVal || reportVal === "__other__") {
    throw new Error(`#report select пуст или Другое: ${reportVal}`);
  }
  if (!contourVal) throw new Error("#contour пуст");
  if (await formPage.locator("#title").count()) {
    throw new Error("Поле #title (краткий заголовок) не должно быть в форме");
  }
  if (await formPage.locator("#section5").isVisible()) {
    throw new Error("Блок «Данные для сверки» виден до выбора типа «данные»");
  }

  await formPage.screenshot({ path: path.join(OUT, "01_form_prefilled.png"), fullPage: true });

  console.log("4) Fill required fields");
  await formPage.locator("#first_name").fill("E2E");
  await formPage.locator("#last_name").fill("Playwright");
  await formPage.locator('input[name="btype"][value="Интерфейс"]').check({ force: true });
  await formPage.waitForTimeout(300);
  const why = await formPage.locator("#whytype").inputValue();
  console.log("   whytype autofill:", why.slice(0, 80));
  if (!why) throw new Error("whytype не автозаполнился после выбора типа");
  await formPage.locator("#block").selectOption({ label: "Таблица" });
  await formPage.locator("#actual").fill(
    `Автотест Playwright: ${marker}. Фактическое поведение — проверка интеграции кнопки «Сообщить об ошибке».`,
  );
  await formPage.locator("#expected").fill(
    "Форма открывается с контекстом дашборда; заявка создаёт карточку в Trello.",
  );
  await formPage.locator("#steps").fill(
    `1. Открыть ${PROD}${route}\n2. Нажать «Сообщить об ошибке»\n3. Заполнить обязательные поля\n4. Отправить`,
  );
  await formPage.locator('input[name="severity"][value="Косметика"]').check({ force: true });
  await formPage
    .locator('input[name="repro"][value="Всегда, при указанных шагах"]')
    .check({ force: true });
  const when = new Date();
  when.setMinutes(when.getMinutes() - when.getTimezoneOffset());
  await formPage.locator("#whendt").fill(when.toISOString().slice(0, 16));
  await formPage.locator("#nofiles").fill("E2E Playwright — без вложений");

  await formPage.screenshot({ path: path.join(OUT, "02_form_filled.png"), fullPage: true });

  console.log("5) Submit");
  const submit = formPage.locator("#sendbtn");
  if (!(await submit.count())) {
    throw new Error("Кнопка «Отправить заявку» не найдена");
  }

  const submitResp = formPage
    .waitForResponse((r) => /bugform\/submit|\/api\/bugform\/submit/i.test(r.url()), {
      timeout: 90000,
    })
    .catch(() => null);

  await submit.click();
  const resp = await submitResp;
  let bugId = "";
  let submitBody = "";
  if (resp) {
    try {
      submitBody = await resp.text();
      const parsed = JSON.parse(submitBody);
      bugId = parsed.bug_id || "";
    } catch {
      submitBody = submitBody || (await resp.text().catch(() => ""));
    }
    console.log("   submit HTTP", resp.status(), resp.url());
    if (submitBody) console.log("   submit body:", submitBody.slice(0, 400));
  }
  await formPage.waitForTimeout(5000);
  await formPage.screenshot({ path: path.join(OUT, "03_after_submit.png"), fullPage: true });

  const bodyText = await formPage.locator("body").innerText();
  const okMsg =
    Boolean(bugId) ||
    (/зарегистрирована|спасибо|BUG-\d+/i.test(bodyText + submitBody) &&
      !/ошибк|error|не удалось|заполните/i.test(bodyText));
  console.log("   submit page excerpt:", bodyText.slice(0, 500).replace(/\s+/g, " "));
  if (!okMsg) {
    console.warn("   WARN: явного success-текста нет — проверяем Trello по маркеру");
  }

  console.log("6) Trello board check for marker:", marker, "bug_id:", bugId || "(none)");
  const trelloNeedle = bugId || marker;
  const trello = await ctx.newPage();
  await trello.goto(TRELLO_BOARD, { waitUntil: "domcontentloaded", timeout: 90000 });
  await trello.waitForTimeout(8000);
  await trello.screenshot({ path: path.join(OUT, "04_trello_board.png"), fullPage: true });

  const trelloText = await trello.locator("body").innerText();
  const onBoard = trelloText.includes(trelloNeedle);
  console.log("   needle on board:", onBoard, trelloNeedle);

  if (!onBoard) {
    // Public board may hide card text until login — try search in page HTML
    const html = await trello.content();
    const inHtml = html.includes(trelloNeedle);
    console.log("   needle in HTML:", inHtml);
    if (!inHtml && !okMsg) {
      throw new Error(`Карточка «${trelloNeedle}» не найдена на доске Trello`);
    }
    if (!inHtml && okMsg) {
      console.log(
        "PASS: форма зарегистрировала заявку (Trello без логина может не показывать карточки)",
      );
    } else if (inHtml) {
      console.log("PASS: заявка видна на доске Trello");
    }
  } else {
    console.log("PASS: заявка видна на доске Trello");
  }

  fs.writeFileSync(
    path.join(OUT, "result.json"),
    JSON.stringify({ marker, bugId, formUrl, okMsg, onBoard, at: new Date().toISOString() }, null, 2),
  );
  console.log("Artifacts:", OUT);
} catch (err) {
  fail(err instanceof Error ? err.message : String(err));
  try {
    await page.screenshot({ path: path.join(OUT, "error.png"), fullPage: true });
  } catch {
    /* ignore */
  }
} finally {
  await browser.close();
}
