# Ask AI с дашборда — страницы и аргументы для XCA

Дата: 2026-08-10  
Контракт: `DASHBOARD_ASK_AI_INTEGRATION.md` v1  
Стенд дашборда: showcase webapp (Next + FastAPI)

Документ для команды XCA AI: по каким экранам уходит вопрос и какие параметры в ссылке.  
На вашей стороне — приём `report` / аргументов и ответы агента.

---

## Как открываем

1. Пользователь на дашборде жмёт **«Спросить ИИ»** (desktop — кнопка в шапке; mobile — chip у заголовка).
2. Наш API `POST /api/ask-ai/link` проверяет **роль** → нет доступа к экрану → **403**, ссылку не выдаём.
3. Если ок — подписываем GET и открываем у вас `/ask?...` в новой вкладке.

**Доступ к ИИ = доступ к отчёту.** В ссылке всегда подписанные `uid` + `role`. Проверку роли по справочнику делаете **вы**, до обращения к модели.

Справочник ролей (формат §8 гайда): `GET /api/ask-ai/roles-catalog` (admin Bearer).  
Пока `projects: ["*"]` (project ACL на дашборде выключен).

Роли: системные `superadmin`, `admin`, `analyst`, `rp`, `financier`, `gip`, `manager` **и кастомные** из админки (матрица в `users.db`).  
Полное описание ACL + что учитывать при разработке ИИ: [`CUSTOM_ROLES_AND_ASK_AI.md`](./CUSTOM_ROLES_AND_ASK_AI.md).

---

## Аргументы ссылки

```
https://<домен-XCA>/ask?v=1&report=...&q=...&ctx=...&src=...&uid=...&role=...&ts=...&sig=...
[&project=...][&period=...][&filters=...]
```

| Параметр | Обяз. | Что передаём |
|----------|-------|----------------|
| `v` | да | `1` |
| `report` | да | page-level id экрана (`screen_*`, таблица ниже) |
| `q` | да | видимый вопрос ≤120 символов, напр. `Объясни дашборд «БДДС (расходы)»` |
| `ctx` | обычно | скрытый контекст экрана ≤600 символов; **без строк таблицы** |
| `src` | обычно | путь экрана для статистики, напр. `finance/bdds` |
| `uid` | да | внутренний id: `u_<id>` |
| `role` | да | код роли пользователя |
| `ts` | да | unix-секунды; ссылка жива ~10 минут |
| `sig` | да | HMAC-SHA256(secret, canonical), base64url без `=` |
| `project` | нет | точное имя проекта из фильтра экрана |
| `period` | нет | `YYYY-MM` или `YYYY-MM-DD..YYYY-MM-DD` |
| `filters` | нет | плоский JSON прочих фильтров ≤400 символов |

**Не передаём:** содержимое таблиц, цифры с экрана, ФИО, внутренние id строк БД.

Подпись только на бэкенде дашборда. Секрет: `XCA_ASK_SECRET`, база: `XCA_ASK_BASE_URL`.

---

## Страницы (16 экранов)

Одна кнопка на вкладку → один `report` = **весь экран** (+ фильтры выше).

| # | Страница (UI) | URL дашборда | `report` | типичный `src` | часто ещё |
|---|----------------|--------------|----------|----------------|-----------|
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

### Пример

```
report=screen_bdds
q=Объясни дашборд «БДДС (расходы)»
ctx=Отчёт «БДДС (расходы)». БДДС расходы по периодам. Суммы в рублях.
src=finance/bdds
project=Есипово-5
period=2026-08
filters={"block":"СМР"}
uid=u_1042
role=financier
ts=...
sig=...
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
| `screen_developer_projects`, `screen_bdr`, `screen_project_documentation`, `screen_debit_credit` | **нет** в текущем списке — нужна база знаний |

Просим добавить все `screen_*` в `xca-reports.json` (или пришлите свои id — поменяем маппинг).

---

## Что нужно от XCA

1. **Домен + общий секрет** (`XCA_ASK_BASE_URL`, `XCA_ASK_SECRET`) — без них кнопка на стенде отвечает `XCA_ASK_SECRET не задан`.
2. Приём всех `screen_*` и описание, **как отвечаете** по каждому экрану (с учётом `role` / `project` / `period` / `filters`).
3. Отказ по роли: «У вашей роли нет доступа к этому отчёту» (как в §7 гайда).
4. Позже: per-widget кнопки с вашими table-id.

POST длинного `ctx` пока не просим — только GET.

---

## Наш VPS (после получения секрета)

В `webapp/.env`:

```
XCA_ASK_BASE_URL=https://<домен-XCA>
XCA_ASK_SECRET=<общий-секрет-HMAC>
```

Затем:

```bash
cd webapp
docker compose up -d --force-recreate api
```

Секрет **не** коммитить в git. Локально — `webapp/api/.env`.

---

## Ответ на ASK_AI_XCA_REQUEST.md (стыковка)

### §1.1 Фильтры
Исправлено: в момент клика читаем `window.location.search`, кладём `project` / `period` (`date_from..date_to`) / прочее в `filters`. «Все» в project не передаём.

### §1.2 roles-catalog
- Ключ списка экранов в роли: **`reports`** (значения `screen_*`).
- Доступ: Bearer admin **или** заголовок `X-Admin-Token: <WEBAPP_ADMIN_TOKEN>` (тот же, что для FTP sync на стенде).

### §1.3 Подпись
Тестовый вектор с `test-secret` **совпал**: `Vzku4zNdQ0pAfCq0PfjIdHRGtQkwV9g17SGJvHE3wKo`.

### §1.4 Написание проектов
Пока в `project` уходит **имя как на текущем экране** (без единого справочника). Карту соответствий 1С ↔ MSP заводите у себя; мы можем позже нормализовать, если решите единый словарь.

### §3 Экраны без полного расчёта
Пока ок честный отказ / частичный ответ по `screen_bdr`, `screen_project_documentation`, `screen_debit_credit`. `screen_baseline_deviation` — сверяйте как реестр отклонений сроков (`task_shift` / `msp_block_smr`), не как `msp_levels`.

### §5 Роли
Принято: роль в ссылке — входной контроль, не полная защита чата. Полноценное RBAC на вашей стороне — когда определитесь с моделью ролей; до этого не обещаем заказчику «ИИ не скажет лишнего после открытия».
