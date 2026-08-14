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
| 1 | developer-projects | Девелоперские проекты | `walk_20260814_1802` | 🔄 walk clean | 5 кадров, 0% |
| 2 | bdds | БДДС | `walk_20260814_1806` | 🔄 walk clean | 7 кадров, 0% |
| 3 | bdr | БДР | `walk_20260814_1808` | 🔄 walk clean | 7 кадров, 0% |
| 4 | approved-budget | Утверждённый бюджет | `walk_20260814_1810` | 🔄 walk clean | 7 кадров, 0% |
| 5 | bdds-plan-fact | БДДС план/факт | `walk_20260814_1811` | 🔄 walk clean | 6 кадров, 0% |
| 6 | control-points | Контрольные точки | `walk_20260814_1814` | 🔄 walk clean | 4 кадров, 0% |
| 7 | project-schedule | График проекта | `walk_20260814_1815` | 🔄 walk clean | 9 кадров, 0% |
| 8 | deviation-reasons | Причины отклонений | `walk_20260814_1818` | 🔄 walk clean | 0% |
| 9 | baseline-deviation | Отклонение от БП | batch 1818+ | 🔄 walk clean | 0% |
| 10 | project-documentation | Проектная документация | `walk_20260814_1834` | 🔄 walk clean | первый прогон — timeout prod (артефакт); re-walk 0% |
| 11 | working-documentation | Рабочая документация | `walk_20260814_1837` | 🔄 data drift | default ≤0.16% OK; checkbox/dark ~0.63–0.65% — monthly fact (prod cipher-fallback vs cloudpub dates); не UI |
| 12 | gdrs-people | ГДРС люди | `walk_20260814_1825` | 🔄 walk clean | 6 кадров, 0% |
| 13 | gdrs-equipment | ГДРС техника | `walk_20260814_1827` | 🔄 walk clean | 6 кадров, ≤0.12% |
| 14 | prescriptions | Предписания | `walk_20260814_1828` | 🔄 walk clean | 6 кадров, 0% |
| 15 | executive-docs | Исполнительная документация | `walk_20260814_184614` | 🔄 walk clean | после soft-ready + DEV_PASS=admin; 5 кадров, 0% |
| 16 | debit-credit | ДЗ/КЗ | `walk_20260814_1831` | 🔄 walk clean | 4 кадров, ≤0.04% |
| 17 | settings-profile | Профиль | — | ⏭ позже | |
| 18 | settings-admin | Админка | — | ⏭ позже | |

Легенда: ⬜ не начат · 🔄 walk clean / drift, ждём OK на prod · ✅ принято на prod · ⏭ отложено · ❌ баги UI

## Журнал

### 2026-08-14 — полный прогон §1–§16

- Инструмент: `visual_walk_parity.mjs` (SITE=both, DIFF_THRESHOLD=0.003).
- UI-багов prod≠cloudpub по пикселям **не найдено** (кроме РД data drift).
- Скрипт: stamp с секундами; `isLoading` игнор sr-only; soft_ready; cloudpub `DEV_PASS` default `admin`.
- РД: known data drift monthly fact (prod UUID↔TESSA cipher fallback vs cloudpub task dates) — см. коммиты `5609c80` / API.
- Приёмка: пользователь ставит ✅ по экранам на ai.conall.ru (можно пакетом «§1–§16 ок» если визуально совпадает).

### Health / versions (срез API)

- Оба стенда: `version` API 0.19.0, `data_mode=ftp`.
- `active_version_id` различается (prod vs cloudpub) — цифры РД/ИД могут плыть при том же UI.
