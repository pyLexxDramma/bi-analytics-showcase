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
| 8 | deviation-reasons | Причины отклонений | `walk_20260815_132440` | ✅ принято | 15.08: 5 кадров, pixel 0%; принят на ai.conall / cloudpub |
| 9 | baseline-deviation | Отклонение от БП | `walk_20260815_141841` | ✅ принято | 15.08: выравнивание баров; prefix проекта; sort по проекту; pad x-origin; принят на ai.conall после deploy |
| 10 | project-documentation | Проектная документация | `walk_20260816_102334` | ✅ принято | 16.08: 5 кадров 0%; sticky «Проект» opaque; принят на ai.conall после deploy |
| 11 | working-documentation | Рабочая документация | `walk_20260816_104631` | ✅ принято | 16.08: 6 кадров 0%; sticky «Проект» opaque; принят на ai.conall после deploy |
| 12 | gdrs-people | ГДРС люди | `walk_20260816_110017` | ✅ принято | 16.08: 6 кадров 0%; недели План/СКУД = с фактом (как Streamlit); принят на ai.conall |
| 13 | gdrs-equipment | ГДРС техника | `walk_20260816_111541` | ✅ принято | 16.08: ≤0.06%; fullscreen графиков + shimmer ⛶; принят на ai.conall после deploy |
| 14 | prescriptions | Предписания | `walk_20260816_113829` | ✅ принято | 16.08: 0%; sticky 3 кол.; выноски мелких сегментов; принят на ai.conall после deploy |
| 15 | executive-docs | Исполнительная документация | `walk_20260816_121954` | ✅ принято | 16.08: 6 кадров, ≤0.01%; принят на ai.conall после deploy |
| 16 | debit-credit | ДЗ/КЗ | `walk_20260816_122214` | 🔄 ждём OK | 16.08: стек — цифры только сверху; modebar гориз. + pin при scroll; после deploy |
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
