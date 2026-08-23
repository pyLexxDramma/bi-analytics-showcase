# Visual QA fixes — статус реализации

Источник багов: `d:\AI_codding\visual-qa\visual-qa\REPORT.md`  
Репозиторий: `bi-analytics-showcase` / `webapp/`  
Дата: 2026-08-21

## Волны

| Волна | Статус | Корень |
|-------|--------|--------|
| 1.1 Fullscreen close/height | Implemented | `fullscreen-panel.tsx`, `globals.css` |
| 1.2 Plotly zoom | Implemented | `plotly-figure.tsx`, `plotly-config.ts` |
| 1.3 Loading skeleton only | Implemented | `dashboard-loading.tsx` |
| 1.4 Dark contrast | Implemented | `globals.css`, logout styles |
| 1.5 Hide version_id | Implemented | gdrs / debit / prescriptions / executive views |
| 2.1 Mobile shell | Implemented | `app-shell`, `mobile-tab-bar`, sidebar drawer |
| 2.2 Desktop shell | Implemented | Ask AI flat, collapsed icons, no «?» |
| 2.3 Mobile polish | Implemented | dates nowrap, Y-axis, overflow |
| 3.1 Filters Apply | Implemented | `useDeferredUrlFilters` + FiltersCard |
| 3.2 BDDS hide_zero / timeout | Implemented | `bdds_plan_fact.py`, `api.ts` 180s |
| 3.3 Admin confirm | Implemented | admin-data-sync + sidebar |
| 4 Controls / DS / settings | Implemented | selects, hover, scrollbars, admin layout |
| 5 Closeout | Tracking | приёмка на ai.conall.ru — у владельца |

## Кластеры → закрытие дублей

При приёмке корня отмечать Fixed и дочерние Duplicate:

- Fullscreen close/layout → 012,018,019,020,024,027,028,033,035,040,042,045–050
- Plotly zoom → 015,020,025,029,030,032,034,038,039,041
- Loader → 014,017,073
- Dark → 056–062
- Mobile shell → 064,068
- Filters apply → 010
- hide_zero → 072
- Admin confirm → 055

## Ожидает приёмки владельца

1. Локально: http://localhost:3000 — smoke БДДС / РД / ГДРС, dark+light, mobile tab bar  
2. Деплой showcase webapp → https://ai.conall.ru  
3. Подтверждение ✅ по волнам в Trello / REPORT  

## Не Fully покрыто кодом (проверить вручную)

- Контрольные точки — полный visual pass  
- Android 360 vs 411  
- Sticky filters на девелоперских проектах (007) — partial  
- Полная замена native select на headless UI — styled native, не новый виджет  
