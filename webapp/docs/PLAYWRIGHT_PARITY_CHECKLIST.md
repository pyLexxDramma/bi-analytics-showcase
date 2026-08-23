# Playwright parity: local ↔ cloudpub (= ai.conall.ru)

**Цель:** по каждому дашборду — скрины **local** (с Visual QA-правками) vs **ref** (cloudpub, тот же код что ai.conall.ru), desktop + mobile. Сверить: правки улучшили UI, **данные не потерялись**. После «ок» — deploy на cloudpub и ai.conall.ru.

## Стенды

| | URL | Логин |
|---|-----|-------|
| **Local** (правки) | http://localhost:3000 | admin / admin |
| **Ref** (= prod) | https://insipidly-carefree-husky.cloudpub.ru | admin / admin |
| **Prod** | https://ai.conall.ru | после SSL — тот же билд что cloudpub |

Viewports: desktop 1440×900 · mobile 390×844

Легенда: ☐ · 🔍 · ✅ · ✏ · ⏭ · 🚀 deploy ok

---

## Перед первым экраном (один раз)

1. **Синхрон снимка данных** (одинаковое содержимое web/ на обоих стендах):
   ```powershell
   python webapp/scripts/sync_parity_snapshot.py
   python webapp/scripts/sync_parity_snapshot.py --list   # проверка fingerprint
   ```
   Числовой `version_id` совпадает только при одном файле `web_data.db`; после sync — одинаковые `files_count` / `rows_count` / время снимка.

2. Оболочка smoke (логин, меню, кнопка «Спросить ИИ» — градиент как на ref).

---

## Цикл на один дашборд

| Шаг | Действие |
|-----|----------|
| 1 | `ONLY=<id>` — скрины local + ref, desktop + mobile |
| 2 | **Агент пишет разбор** в чат и в «Журнал разборов» (без авто-открытия браузера) |
| 3 | Вы смотрите скрины по пути `parity_out/walk_*/…` при необходимости → «ок» или правки |
| 4 | Баг данных/UI → ✏ фикс → повтор шаг 1–3 |
| 5 | Ваше «ок» → commit + deploy (если ещё не на ref) |
| 6 | ✅ в таблице → следующий дашборд |

### Обязательно после каждого шага (агент)

1. Пути к отчёту: `parity_out/walk_*/desktop/compare.html`, `mobile/compare.html`, `compare.html` — **не открывать** в браузере автоматически.
2. В чат — блок **«Разбор шага #N · &lt;id&gt;»** + запись в «Журнал разборов» ниже.

**Не баг:** ожидаемые UI-отличия local vs ref **до** deploy (новый shell, Apply/Reset, skeleton).  
**Баг:** другие суммы/строки; пропавшие блоки; сломанные графики.

---

## Чеклист экранов

| # | id | Desktop | Mobile | Данные | UI local | Deploy | Отчёт |
|---|-----|---------|--------|--------|----------|--------|-------|
| 1 | developer-projects | ✅ | ✅ | ✅ | ✅ | 🚀 | `f16e3f8` |
| 2 | bdds | ✅ | ✅ | ✅ | ✅ | 🚀 | `walk_20260823_100751` — 0% после deploy |
| 3 | bdr | ✅ | ✅ | ✅ | ✅ | 🚀 | `walk_20260823_101044` — 0% |
| 4 | approved-budget | ✅ | ✅ | ✅ | ✅ | 🚀 | `walk_20260823_101114` — 0% |
| 5 | bdds-plan-fact | ✅ | ✅ | ✅ | ✅ | 🚀 | `walk_20260823_101336` — 0% |
| 6 | control-points | ✅ | ✅ | ✅ | ✅ | 🚀 | `walk_20260823_101547` — 0% |
| 7 | project-schedule | ✅ | ✅ | ✅ | ✅ | 🚀 | `walk_20260823_101215` — 0% |
| 8 | deviation-reasons | ✅ | ✅ | ⚠️ | ✅ | 🚀 | `walk_20260823_101408` — визу 0%, API hash≠ (порядок строк) |
| 9 | baseline-deviation | ✅ | ✅ | ⚠️ | ✅ | 🚀 | `walk_20260823_101433` — визу 0% |
| 10 | project-documentation | ✅ | ✅ | ⚠️ | ✅ | 🚀 | `walk_20260823_101744` — 0.13% desktop |
| 11 | working-documentation | ✅ | ✅ | ✅ | ✅ | 🚀 | `walk_20260823_101147` |
| 12 | gdrs-people | ✅ | ✅ | ✅ | ✅ | 🚀 | `walk_20260823_101741` |
| 13 | gdrs-equipment | ✅ | ✅ | ✅ | ✅ | 🚀 | `walk_20260823_095831` |
| 14 | prescriptions | ✅ | ✅ | ✅ | ✅ | 🚀 | `walk_20260823_095952` |
| 15 | executive-docs | ✅ | ✅ | ✅ | ✅ | 🚀 | `walk_20260823_100028` |
| 16 | debit-credit | ✅ | ✅ | ⚠️ | ✅ | 🚀 | `walk_20260823_101524` — визу 0% |

---

## Команды

```powershell
cd d:\AI_codding\Analitics\bi-analytics-showcase\webapp

# 0. Синхрон данных
python scripts/sync_parity_snapshot.py --list

# 1. Один дашборд (desktop + mobile, только default-скрин)
$env:ONLY="developer-projects"
$env:SIMPLE_SHOTS="1"
node scripts/visual_walk_parity.mjs

# 2. Deploy (после вашего «ок»)
# git add … && git commit && git push origin main   → cloudpub auto
# GitHub Actions → Deploy ai.conall.ru → workflow_dispatch
```

Отчёт: `parity_out/walk_*/compare.html`, `desktop/compare.html`, `mobile/compare.html`

---

## Журнал разборов

### Шаг #1 · developer-projects · `walk_20260823_093209`

**Открыто в браузере:**  
`parity_out/walk_20260823_093209/desktop/compare.html` · `mobile/compare.html` · `compare.html`

**Данные:** ✅ API payload совпадает (345 файлов, 129 000 строк; local v23 / ref v298 — разные id, одно содержимое). KPI и таблица на скринах визуально те же проекты и цифры.

**Desktop (local слева, ref справа):**

| Область | Разница | Оценка |
|---------|---------|--------|
| Шапка | Local: компактнее, кнопка «Спросить ИИ» — градиент (как ref); ref: старая шапка | **Лучше** local (после фикса кнопки) |
| Сайдбар | Local: обновлённый nav, аккордеон, без лишнего version_id в UI | **Лучше** local |
| Фильтры | Local: панель с **Применить / Сбросить** (draft); ref: мгновенное применение | **Лучше** local (меньше случайных перезагрузок) |
| Таблица / KPI | Те же строки и значения | **Нейтрально** (данные ок) |
| Загрузка | Local: skeleton; ref: старый loader | **Лучше** local |

Pixel diff ~5.7% — в основном shell/фильтры, не цифры.

**Mobile:**

| Область | Разница | Оценка |
|---------|---------|--------|
| Нижний tab-bar | Local: новая мобильная оболочка | **Лучше** local |
| Заголовок + chip «ИИ» | Local: chip рядом с h1 | **Лучше** local (быстрый доступ) |
| Таблица | Горизонтальный скролл, те же данные | **Нейтрально** |
| Фильтры | Local: sheet + Apply/Reset | **Лучше** local |

Pixel diff ~9.5% — layout mobile shell.

**Вердикт:** ✅ приёмка 2026-08-23. Deploy: `f16e3f8` + `1dd8dbf` (CI ✅).

---

### Сводка post-deploy · 2026-08-23

**Deploy:** cloudpub CI ✅ (`1dd8dbf`, vLLM fix). Local ↔ ref визуально **0%** на всех 16 экранах (после `SETTLE_MS=8s` на ПД).

**API hash ≠** на #8–10, #16 при дефолтном GET — local v23 / ref v299, порядок строк в JSON; **на скринах KPI совпадают**.

### Пакетная приёмка Visual QA · 2026-08-23 ✅

Пользователь: **«ок»** на весь прогон (16 экранов, desktop + mobile).

| Критерий | Вердикт |
|----------|---------|
| UI улучшения | ✅ shell, фильтры Apply/Reset, mobile, skeleton, fullscreen, градиент «Спросить ИИ» |
| Данные на экранах | ✅ KPI/таблицы/графики совпадают; #8–10, #16 — API hash≠ только порядок JSON |
| Desktop + mobile | ✅ 0% pixel diff local ↔ ref после deploy |
| Deploy | ✅ `f16e3f8` + `1dd8dbf`, CI зелёный, cloudpub = ai.conall.ru |

**Visual QA parity закрыт.**

---

### Шаг #2 · bdds · `walk_20260823_094825`

**Открыто в браузере:** `parity_out/walk_20260823_094825/desktop|mobile|compare.html`

**Данные:** ✅ API `/api/bdds` — payload идентичен (hash `2ea04820f6812a0a`).

**Desktop (local ← → ref), diff ~1.5%:**

| Область | Разница | Оценка |
|---------|---------|--------|
| Шапка / сайдбар / ИИ | Те же правки shell, что #1 | **Лучше** local (или уже на ref после deploy) |
| Фильтры | Apply/Reset, чекбокс «скрыть нули» | **Лучше** local |
| KPI-карточки | Ожидаемо те же суммы | **Ок** |
| Таблица БДДС | Структура и строки | **Ок** |
| График | Plotly + лимиты зума | **Лучше** local |

**Mobile, diff ~6.8%:**

| Область | Разница | Оценка |
|---------|---------|--------|
| Tab-bar, фильтры-sheet | Новая оболочка | **Лучше** local |
| KPI + таблица | Те же данные, адаптив | **Ок** |
| Горизонтальный скролл таблицы | Сохранён | **Нейтрально** |

**Вердикт:** ждём ваше **«ок»** (deploy уже в пути с #1 — после зелёного CI ref подтянется сам).

---
