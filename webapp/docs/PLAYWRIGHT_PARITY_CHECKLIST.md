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
| 2 | **Агент открывает** `compare.html` (desktop + mobile + сводный) в браузере |
| 3 | **Агент пишет разбор:** что отличается, лучше / хуже / нейтрально; данные те же или нет |
| 4 | Вы смотрите открытые скрины → «ок» или список правок |
| 5 | Баг данных/UI → ✏ фикс → повтор шаг 1–4 |
| 6 | Ваше «ок» → commit + deploy cloudpub + ai.conall.ru |
| 7 | Smoke на ref → ✅ в таблице → следующий дашборд |

### Обязательно после каждого шага (агент)

1. `Start-Process` на три файла: `desktop/compare.html`, `mobile/compare.html`, корневой `compare.html`.
2. В чат — блок **«Разбор шага #N · &lt;id&gt;»** с подпунктами:
   - **Данные** (KPI, строки таблиц, графики — совпадают / расходятся)
   - **Desktop** — отличия local vs ref, оценка (лучше / хуже / ожидаемо до deploy)
   - **Mobile** — то же
   - **Вердикт:** ждём ваше «ок» / нужен фикс

**Не баг:** ожидаемые UI-отличия local vs ref **до** deploy (новый shell, Apply/Reset, skeleton).  
**Баг:** другие суммы/строки; пропавшие блоки; сломанные графики.

---

## Чеклист экранов

| # | id | Desktop | Mobile | Данные | UI local | Deploy |
|---|-----|---------|--------|--------|----------|--------|
| 1 | developer-projects | ✅ | ✅ | ✅ | ✅ | 🚀 | `walk_20260823_093209` — приёмка 2026-08-23 |
| 2 | bdds | ☐ | ☐ | ☐ | ☐ | ☐ |
| 3 | bdr | ☐ | ☐ | ☐ | ☐ | ☐ |
| 4 | approved-budget | ☐ | ☐ | ☐ | ☐ | ☐ |
| 5 | bdds-plan-fact | ☐ | ☐ | ☐ | ☐ | ☐ |
| 6 | control-points | ☐ | ☐ | ☐ | ☐ | ☐ |
| 7 | project-schedule | ☐ | ☐ | ☐ | ☐ | ☐ |
| 8 | deviation-reasons | ☐ | ☐ | ☐ | ☐ | ☐ |
| 9 | baseline-deviation | ☐ | ☐ | ☐ | ☐ | ☐ |
| 10 | project-documentation | ☐ | ☐ | ☐ | ☐ | ☐ |
| 11 | working-documentation | ☐ | ☐ | ☐ | ☐ | ☐ |
| 12 | gdrs-people | ☐ | ☐ | ☐ | ☐ | ☐ |
| 13 | gdrs-equipment | ☐ | ☐ | ☐ | ☐ | ☐ |
| 14 | prescriptions | ☐ | ☐ | ☐ | ☐ | ☐ |
| 15 | executive-docs | ☐ | ☐ | ☐ | ☐ | ☐ |
| 16 | debit-credit | ☐ | ☐ | ☐ | ☐ | ☐ |

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

**Вердикт:** данные не потеряны; UI local лучше по всем пунктам Visual QA. Ждём ваше **«ок»** → deploy.

---
