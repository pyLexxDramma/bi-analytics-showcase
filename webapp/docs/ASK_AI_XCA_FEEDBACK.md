# ОС для XCA: страницы Ask AI и аргументы ссылки

Дата: 2026-08-10. Контракт: `DASHBOARD_ASK_AI_INTEGRATION.md` v1.  
Путь файла: `d:\AI_codding\Analitics\bi-analytics-showcase\webapp\docs\ASK_AI_XCA_FEEDBACK.md`

---

## Как открываем ИИ

1. Пользователь на дашборде (desktop) жмёт **«Спросить ИИ»** в шапке вкладки.
2. Наш API `POST /api/ask-ai/link` (алиас `/api/ask-ai-link`) **проверяет роль** → если к экрану нет доступа, **403**, ссылку не выдаём.
3. Если ок — подписываем GET-ссылку и открываем у вас `/ask?...` в новой вкладке.

**Доступ к ИИ = доступ к отчёту.** Та же RBAC, что у дашборда (`auth.py`: allow/deny по роли). В ссылке всегда уходят подписанные `uid` + `role` — у вас проверка по справочнику ролей **до** модели (подделанный `role=` без валидной `sig` не пройдёт).

Справочник: `GET /api/ask-ai/roles-catalog` (admin Bearer), формат §8 вашего гайда + список `screens`. Пока `projects: ["*"]` (project ACL на дашборде выключен).

Роли: `superadmin`, `admin`, `analyst`, `rp`, `financier`, `gip`, `manager`.

---

## Аргументы в ссылке (что передаём всегда / опционально)

База:

```
https://<домен-XCA>/ask?v=1&report=...&q=...&ctx=...&src=...&uid=...&role=...&ts=...&sig=...
```

| Параметр | Обязателен | Что кладём |
|----------|------------|------------|
| `v` | да | `1` |
| `report` | да | page-level id экрана, см. таблицу ниже (`screen_*`) |
| `q` | да | видимый вопрос, до 120 символов, напр. `Объясни дашборд «БДДС (расходы)»` |
| `ctx` | нет* | скрытый контекст экрана (название + краткая справка), до 600 символов; **без строк таблицы** |
| `src` | нет* | путь экрана для статистики, напр. `finance/bdds` |
| `uid` | да | внутренний id: `u_<id>` |
| `role` | да | код роли пользователя |
| `ts` | да | unix-секунды генерации (ссылка жива ~10 мин) |
| `sig` | да | HMAC-SHA256(secret, canonical), base64url без `=` |
| `project` | нет | точное имя проекта из фильтра экрана, если был |
| `period` | нет | `YYYY-MM` или `YYYY-MM-DD..YYYY-MM-DD` |
| `filters` | нет | плоский JSON прочих фильтров (block, contractor, …), до 400 символов |

\* На практике `ctx` и `src` мы почти всегда заполняем.

**Не передаём:** содержимое таблиц, цифры с экрана, ФИО, внутренние id строк БД.

Подпись — только на нашем бэкенде. Секрет: `XCA_ASK_SECRET`, база: `XCA_ASK_BASE_URL`.

---

## По каким страницам спрашиваем (16 экранов)

Одна кнопка на вкладку → один `report` = **весь экран** (+ фильтры выше).

| # | Страница (UI) | URL дашборда | `report` (наш id) | типичный `src` | что ещё может уйти |
|---|----------------|--------------|-------------------|----------------|--------------------|
| 1 | Девелоперские проекты | `/developer-projects` | `screen_developer_projects` | `developer-projects` | `project`, `filters` |
| 2 | БДДС (расходы) | `/finance/bdds` | `screen_bdds` | `finance/bdds` | `project`, `period`, `filters` |
| 3 | БДР (расходы) | `/finance/bdr` | `screen_bdr` | `finance/bdr` | `project`, `period`, `filters` |
| 4 | Утверждённый бюджет план/факт | `/finance/approved-budget` | `screen_approved_budget` | `finance/approved-budget` | `project`, `period`, `filters` |
| 5 | БДДС план/факт/уточн. план | `/finance/bdds-plan-fact` | `screen_bdds_plan_fact` | `finance/bdds-plan-fact` | `project`, `period`, `filters` |
| 6 | Контрольные точки | `/timeline/control-points` | `screen_control_points` | `timeline/control-points` | `project`, `filters` |
| 7 | График проекта | `/timeline/project-schedule` | `screen_project_schedule` | `timeline/project-schedule` | `project`, `filters` |
| 8 | Причины отклонений | `/timeline/deviation-reasons` | `screen_deviation_reasons` | `timeline/deviation-reasons` | `project`, `filters` |
| 9 | Отклонение от базового плана | `/timeline/baseline-deviation` | `screen_baseline_deviation` | `timeline/baseline-deviation` | `project`, `filters` |
| 10 | Проектная документация | `/docs/project-documentation` | `screen_project_documentation` | `docs/project-documentation` | `project`, `filters` |
| 11 | Рабочая документация | `/docs/working-documentation` | `screen_working_documentation` | `docs/working-documentation` | `project`, `filters` |
| 12 | ГДРС (люди) | `/gdrs/people` | `screen_gdrs_people` | `gdrs/people` | `project`, `period`, `filters` |
| 13 | ГДРС (техника) | `/gdrs/equipment` | `screen_gdrs_equipment` | `gdrs/equipment` | `project`, `period`, `filters` |
| 14 | Предписания по подрядчикам | `/prescriptions` | `screen_prescriptions` | `prescriptions` | `project`, `filters` |
| 15 | Исполнительная документация | `/executive-docs` | `screen_executive_docs` | `executive-docs` | `project`, `filters` |
| 16 | ДЗ/КЗ подрядчиков | `/debit-credit` | `screen_debit_credit` | `debit-credit` | `project`, `filters` |

### Пример `q` / `ctx`

```
q=Объясни дашборд «БДДС (расходы)»
ctx=Отчёт «БДДС (расходы)». БДДС расходы по периодам. Суммы в рублях.
src=finance/bdds
report=screen_bdds
project=Есипово-5
period=2026-08
filters={"block":"СМР"}
uid=u_1042
role=financier
```

---

## Сопоставление с вашими table-id (ориентир)

| наш `report` | ближайший ваш table-id |
|--------------|------------------------|
| `screen_approved_budget` | `bdds_plan_fact` |
| `screen_bdds` | `bdds_monthly` |
| `screen_bdds_plan_fact` | `bdds_forecast` |
| `screen_control_points` | `control_points` |
| `screen_project_schedule` | `task_shift` |
| `screen_deviation_reasons` | `commissioning_reasons` |
| `screen_baseline_deviation` | `msp_levels` |
| `screen_working_documentation` | `rd_overdue` |
| `screen_gdrs_people` | `gdrs_people` |
| `screen_gdrs_equipment` | `gdrs_technique` |
| `screen_prescriptions` | `prescriptions_overdue` / `_critical` / `_monthly` |
| `screen_executive_docs` | `id_transfer_pct` / `id_overdue_*` |
| `screen_developer_projects`, `screen_bdr`, `screen_project_documentation`, `screen_debit_credit` | **нет** в вашем списке — нужна база знаний |

Просим добавить все `screen_*` в `xca-reports.json` (или пришлите свои id — поменяем маппинг).

---

## Что просим от вас

1. Домен + секрет.
2. Приём `screen_*` + ответы агента по каждому экрану (с учётом `role` / `project` / `period` / `filters`).
3. На отказе по роли у вас: «У вашей роли нет доступа к этому отчёту» (как в §7 гайда) — у нас ссылку с запрещённым экраном уже не подписываем.
4. Когда будете готовы к per-widget кнопкам — расширим `report` до ваших table-id.

POST-форму длинного `ctx` пока не просим — только GET.
