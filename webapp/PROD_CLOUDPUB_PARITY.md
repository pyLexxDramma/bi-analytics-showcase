# Паритет: ai.conall.ru (prod) ↔ cloudpub (эталон)

Цикл: visual walk одного экрана → triage → фикс реальных багов → re-walk → commit/push → **Deploy ai.conall.ru prod** → приёмка на prod → ✅ → следующий.

| | |
|---|---|
| Эталон | https://insipidly-carefree-husky.cloudpub.ru/ |
| Цель | https://ai.conall.ru |
| Репо | `bi-analytics-showcase` (`webapp/`) |
| Скрипт | `node scripts/visual_walk_parity.mjs` (`ONLY=<id>`) |
| Отчёты | `webapp/parity_out/walk_*/compare.html` |

**Не** подгонять порог/маски ради зелёного отчёта. Классификация:

1. **UI/логика** → код  
2. **Data drift** (разный `version_id`/FTP) → в заметку, не «чинить» график  
3. **Артефакт съёмки** → переснять / hardened wait в скрипте  

✅ в матрице — **только после «ок» пользователя на ai.conall.ru**.

## Матрица (прогон 2026-08-14)

| # | id | Экран | Walk | Статус | Заметки |
|---|-----|--------|------|--------|---------|
| 1 | developer-projects | Девелоперские проекты | `walk_20260815_101710` | ✅ принято | 15.08: fullscreen по центру; FTP-кнопка force+ingest fallback; принят на ai.conall после deploy |
| 2 | bdds | БДДС | `walk_20260815_104122` | ✅ принято | 15.08: факт teal; отклонение red/green; линия 0; выше график; принят на ai.conall после deploy |
| 3 | bdr | БДР | `walk_20260815_112814` | ✅ принято | 15.08: выше график; +откл. оранжевый; принят на ai.conall после deploy |
| 4 | approved-budget | Утверждённый бюджет | `walk_20260815_114633` | ✅ принято | 15.08: hide_zero+ФИЗ; KPI откл. по галочке; подписи 0; принят на ai.conall после deploy |
| 5 | bdds-plan-fact | БДДС план/факт | `walk_20260815_122633` | ✅ принято | 15.08: шире колонки; sticky Y + сетка; принят на ai.conall после deploy |
| 6 | control-points | Контрольные точки | `walk_20260815_130149` | ✅ принято | 15.08: multiselect проектов + фильтр строк; принят на ai.conall после deploy |
| 7 | project-schedule | График проекта | `walk_20260815_131826` | ✅ принято | 15.08: 9 кадров, pixel 0%; принят на ai.conall / cloudpub |
| 8 | deviation-reasons | Причины отклонений | `walk_20260814_1818` | 🔄 walk clean | 0% |
| 9 | baseline-deviation | Отклонение от БП | batch 1818+ | 🔄 walk clean | 0% |
| 10 | project-documentation | Проектная документация | `walk_20260814_1834` | 🔄 walk clean | первый прогон — timeout prod (артефакт); re-walk 0% |
| 11 | working-documentation | Рабочая документация | — | ❌ в работе | **Не принимать.** Причины: (1) prod `version_id=23` vs cloudpub `225` → KPI 722/403 vs 728/409; (2) prod «Проект»=UUID, cloudpub=имена; (3) monthly fact prod раздут cipher-fallback. Фикс UUID→имя + убран endswith; ждём deploy+визуальную приёмку |
| 12 | gdrs-people | ГДРС люди | `walk_20260814_1825` | 🔄 walk clean | 6 кадров, 0% |
| 13 | gdrs-equipment | ГДРС техника | `walk_20260814_1827` | 🔄 walk clean | 6 кадров, ≤0.12% |
| 14 | prescriptions | Предписания | `walk_20260814_1828` | 🔄 walk clean | 6 кадров, 0% |
| 15 | executive-docs | Исполнительная документация | `walk_20260814_184614` | 🔄 walk clean | после soft-ready + DEV_PASS=admin; 5 кадров, 0% |
| 16 | debit-credit | ДЗ/КЗ | `walk_20260814_1831` | 🔄 walk clean | 4 кадров, ≤0.04% |
| 17 | settings-profile | Профиль | — | ⏭ позже | |
| 18 | settings-admin | Админка | — | ⏭ позже | |

Легенда: ⬜ не начат · 🔄 walk clean / drift, ждём OK на prod · ✅ принято на prod · ⏭ отложено · ❌ баги UI

## Журнал

### 2026-08-14 — РД: почему cloudpub ≠ ai.conall (скрины 1–4 vs 5–8)

**Причины (не «пиксели»):**
1. Разные активные снимки: prod `#23` (115489 строк) vs cloudpub `#225` (115495) при одинаковых 334 файлах → KPI РД **722/403** vs **728/409**.
2. В prod в колонке «Проект» плана лежат **GUID**, на cloudpub — **Ленинский / Дмитровский-1** → красная таблица с UUID.
3. Из‑за (2) раньше включался cipher-fallback → monthly fact ~686 при KPI выдано 319 (на cloudpub ~593 / +9).

**Код (ещё не на prod):** UUID→имя из `projekts_json` в `_rd_plan_csv_sections_df`; TESSA-имя вместо GUID в деталке; убран `endswith` в monthly Status-join; cache `v19-rd-uuid-project-resolve`.

**Процесс:** дальше только экран «Рабочая документация» → deploy → скрины → ваша приёмка → ✅ → следующий.

### 2026-08-14 — полный прогон §1–§16 (устарел как приёмка)

- Пиксельный walk **не заменяет** визуальную приёмку. Массовые «walk clean» сняты с роли OK.
- Приёмка: только «ок» пользователя на ai.conall.ru по **одному** экрану.

### Health / versions (срез API)

- Оба стенда: `version` API 0.19.0, `data_mode=ftp`.
- `active_version_id`: prod **23**, cloudpub **225** (созданы почти одновременно 14:51, но содержимое rd_plan отличается).
