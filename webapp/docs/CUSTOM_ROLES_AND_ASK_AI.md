# Кастомные роли, ACL дашбордов и Ask AI (showcase webapp)

Документ для разработки ИИ-помощника и смежных фич.  
Репозиторий: `bi-analytics-showcase` · v1 ACL: `5e2d155` · фаза 2 (фильтры/проекты): см. последний push · дата: 2026-08-11.

Связанные материалы:

- Контракт ссылки Ask AI → XCA: `webapp/docs/ASK_AI_XCA_FEEDBACK.md`
- Реестр экранов (server): `webapp/api/app/services/ask_ai_reports.py`
- Реестр экранов (client): `webapp/web/src/lib/ask-ai-reports.ts`
- Нав. меню: `webapp/web/src/lib/nav.ts`

---

## 1. Что сделано (v1 + фаза 2)

| Возможность | Статус |
|-------------|--------|
| CRUD кастомных ролей в `users.db` | ✅ |
| Матрица «роль → набор дашбордов» (`role_reports`) | ✅ |
| Системные роли сидятся из старых allow/deny списков | ✅ |
| Скрытие пунктов меню / поиска / Cmd+K | ✅ |
| Заглушка «Нет доступа» при прямом URL | ✅ |
| `403` на dashboard API без права на экран | ✅ |
| Ask AI: кнопка скрыта + `/link` 403 без права | ✅ |
| `GET /api/ask-ai/roles-catalog` строится из БД-матрицы | ✅ |
| Дефолтные фильтры роли при открытии дашборда | ✅ фаза 2 |
| Разрезка по проектам (роль + пользователь) | ✅ фаза 2 |
| Ask AI catalog / link учитывает проекты роли/юзера | ✅ фаза 2 |
| `GET /api/ask-ai/my-screens` (полный scope user) | ✅ |
| Полный паритет Streamlit main с табличной матрицей | ❌ позже |
| In-app assistant tools ACL | ❌ позже |

**Принцип для ИИ:** доступ к Ask AI по экрану = доступ к самому дашборду. Отдельной роли «можно спрашивать ИИ» нет.  
Дополнительно: параметр `project` в ссылке и `projects` в catalog режутся scope’ом роли∩пользователя.

---

## 2. Где крутится код

| Слой | Путь |
|------|------|
| Таблицы + миграция | `bi-analytics-v-5-main/db.py` |
| RBAC helpers | `bi-analytics-v-5-main/auth.py` |
| Сид ролей при старте API | `webapp/api/app/services/users_bridge.py` → `ensure_roles_seeded(SCREENS)` |
| Выбор core-директории | `webapp/api/app/config.py` → сначала `SHOWCASE_ROOT/bi-analytics-v-5-main` |
| CRUD ролей / каталог экранов | `webapp/api/app/routers/settings_router.py` |
| Guard дашборд-API | `webapp/api/app/services/auth_context.py` → `require_report_access(nav_id)` |
| Clamp проектов | `webapp/api/app/services/project_scope.py` + роутеры отчётов |
| Default filters (read) | `webapp/api/app/services/default_filters_web.py`, `GET /api/auth/default-filters` |
| Ask AI link + catalog | `webapp/api/app/routers/ask_ai.py`, `…/services/ask_ai.py` |
| UI ролей (+ проекты роли) | `webapp/web/src/components/settings/admin-roles-panel.tsx` |
| UI проектов пользователя | `webapp/web/src/components/settings/admin-system-panel.tsx` |
| Сессия / `allowed_reports` / `allowed_projects` | `webapp/web/src/lib/auth.ts` |
| URL-фильтры + дефолты роли | `webapp/web/src/lib/use-url-filter-state.ts` (`navId`) |
| Меню | `webapp/web/src/components/app-sidebar.tsx` |
| Кнопка ИИ | `webapp/web/src/components/ask-ai-button.tsx` |
| Заглушка URL | `webapp/web/src/components/app-shell.tsx` |

Локально: API `:8000`, UI `:3000`.  
Прод-стенд: push в `main` showcase → GitHub Actions `Webapp CI + Deploy`.

---

## 3. Модель данных (`users.db`)

```text
roles(
  code TEXT PK,          -- 'manager', 'rd_only', …
  label TEXT,            -- отображаемое имя
  is_system INTEGER,     -- 1 = из ROLES, нельзя удалить
  can_admin INTEGER,     -- доступ к админке (осторожно для custom)
  created_at
)

role_reports(
  role_code TEXT,
  report_id TEXT,        -- = nav.id из nav.ts / ключ SCREENS
  PRIMARY KEY (role_code, report_id)
)

role_projects(
  role_code TEXT,
  project_name TEXT,     -- пусто в таблице для роли = все проекты
  PRIMARY KEY (role_code, project_name)
)

project_permissions(
  user_id INTEGER,
  project_name TEXT,     -- пусто для юзера = без user-ограничения
  … UNIQUE(user_id, project_name)
)

default_filters(         -- дефолты UI при открытии экрана
  role, report_name, filter_key, filter_value, filter_type, …
)

users.role               -- строковый код; логический FK на roles.code
```

**Итоговый scope проектов:** `admin/superadmin` → все; иначе пересечение  
`role_projects` ∩ `project_permissions` (если на уровне нет строк — уровень не ограничивает).

### Идентификаторы экранов (`report_id` / `nav.id`)

Это **не** русские названия Streamlit и **не** XCA `screen_*`.  
Это стабильные id из меню, например:

`developer-projects`, `bdds`, `bdr`, `approved-budget`, `bdds-plan-fact`,  
`control-points`, `project-schedule`, `deviation-reasons`, `baseline-deviation`,  
`project-documentation`, `working-documentation`, `gdrs-people`, `gdrs-equipment`,  
`prescriptions`, `executive-docs`, `debit-credit`.

Маппинг на XCA: `SCREENS[nav_id].report` → `screen_bdds`, `screen_working_documentation`, …

### Сид

При `ensure_users_db()`:

1. Создаются таблицы (если нет).
2. Для каждой записи из `auth.ROLES` — строка в `roles` (`is_system=1`).
3. Если у роли **ещё нет** строк в `role_reports` — заполняется по legacy allow/deny:
   - `superadmin` / `admin` → все экраны из каталога;
   - остальные → экран попадает в матрицу, если **все** `auth_names` экрана проходят старый `user_can_open_report`.
4. Повторный старт **не затирает** уже сохранённые `role_reports` (можно править в админке).

Legacy-списки остаются в `auth.py` (`_ROLE_REPORT_DENYLIST`, `_REPORT_ROLE_ALLOWLIST`) как fallback, если роли ещё нет в таблице `roles`.

---

## 4. API проверки доступа (ядро)

```python
# auth.py
role_can_open_report(role, report_id)   # nav.id → bool; admin/superadmin всегда True
user_can_open_report(role, report_name) # nav.id ИЛИ русское имя Streamlit
list_allowed_report_ids(role)           # список nav.id для /auth/me
list_roles() / create_role / update_role / delete_role
role_exists(code)
has_admin_access(role)                  # ADMIN_ROLES или roles.can_admin
has_report_access(role)                 # REPORT_ROLES или custom с ≥1 report
```

Правила удаления:

- системную роль удалить нельзя;
- кастомную — нельзя, если есть активные пользователи с этим `role`.
- у `admin` / `superadmin` список отчётов через API **не урезается**.

---

## 5. HTTP API (webapp)

### Сессия

`GET /api/auth/me` (и ответ логина) — в `user`:

```json
{
  "username": "…",
  "role": "rd_only",
  "role_label": "Только РД",
  "email": null,
  "allowed_reports": ["working-documentation"],
  "allowed_projects": ["Проект А", "Проект Б"],
  "can_admin": false
}
```

`allowed_projects: null` = все проекты. Клиент кладёт `allowed_reports` / `allowed_projects` / `can_admin` в `localStorage` (`auth.ts`).

### Админка ролей (только admin JWT)

| Метод | Путь | Назначение |
|-------|------|------------|
| GET | `/api/settings/roles` | список + `reports[]`, `is_system` |
| POST | `/api/settings/roles` | создать custom `{code, label, reports?, can_admin?}` |
| PATCH | `/api/settings/roles/{code}` | label / reports / can_admin |
| DELETE | `/api/settings/roles/{code}` | только custom без юзеров |
| GET | `/api/settings/report-catalog` | `{id, title, path}` для чекбоксов |

Создание/смена роли пользователя: `POST /api/settings/users`, `…/change-role` — код должен существовать в `roles` (`role_exists`), не только в хардкоде `ROLES`.

### Dashboard API

На каждом роутере отчёта:

```python
dependencies=[Depends(require_report_access("bdds"))]  # пример
```

Без Bearer → **401**. Роль без `report_id` в матрице → **403** `"Нет доступа к этому отчёту"`.  
Клиентские `apiGet` / `apiPost` / … по умолчанию подмешивают `authHeaders()`.

---

## 6. UI: где коллега / админ настраивает роли

1. Войти как **admin** / **superadmin** (или custom с `can_admin=1`).
2. **Настройки → Административная панель** (`/settings/admin`).
3. Вкладка **«Система» → «Права доступа»**.
4. Создать роль (код латиницей: `a-z0-9_-`) → отметить дашборды **и при необходимости проекты роли** → Сохранить.
5. **«Пользователи»** — назначить роль; при необходимости ограничить **проекты пользователя**.
6. Дефолт-фильтры роли — в той же админке (таблица `default_filters`, ключи как в URL вьюхи).

Пользователь с урезанной ролью:

- в сайдбаре / поиске / Cmd+K видит только разрешённые пункты;
- прямой URL запрещённого экрана → блок «Нет доступа» (данные API всё равно 403);
- кнопка **«Спросить ИИ»** не рендерится, если `nav.id ∉ allowed_reports`;
- списки проектов в фильтрах / API / Ask AI — только в scope роли∩пользователя;
- при первом открытии экрана без query — подставляются default_filters роли.

---

## 7. Ask AI — подробно для разработки ИИ

### 7.1. Поток

```text
[Дашборд] AskAiButton
    → canAccessReport(nav.id)? иначе null
    → POST /api/ask-ai/link { nav_id, q, ctx, project, period, filters, src }
        → require_report_user
        → role_can_open_screen(role, nav_id)  // читает матрицу БД
        → иначе 403
        → build_ask_url → подписанный URL XCA /ask?...
    → window.open(url)
```

На стороне **XCA** в query уже есть `uid`, `role`, `report` (`screen_*`).  
Ожидание: XCA **ещё раз** сверяет роль со справочником до вызова модели (см. `ASK_AI_XCA_FEEDBACK.md`). Дашборд не полагается только на «честный» UI.

### 7.2. Справочник для XCA

`GET /api/ask-ai/roles-catalog`  
Доступ: admin Bearer **или** заголовок `X-Admin-Token` (= `ADMIN_SYNC_TOKEN`).

Формат (упрощённо):

```json
{
  "updated_at": "2026-08-11T…Z",
  "roles": [
    {
      "code": "manager",
      "title": "Менеджер",
      "reports": ["screen_developer_projects", "screen_working_documentation", "…"],
      "projects": ["*"]
    },
    {
      "code": "rd_only",
      "title": "Только РД",
      "reports": ["screen_working_documentation"],
      "projects": ["Проект А", "Проект Б"]
    }
  ],
  "screens": [
    { "nav_id": "bdds", "report": "screen_bdds", "title": "…", "src": "finance/bdds" }
  ]
}
```

Важно:

- В `roles[].reports` — **XCA ids** (`screen_*`), не `nav.id`.
- Список ролей берётся из `auth.list_roles()` (системные **и** кастомные).
- Набор `reports` считается через `role_can_open_screen` → фактически из `role_reports`.
- `projects`: из `role_projects`; если для роли строк нет → `["*"]`. На `/link` дополнительно clamp по user `project_permissions` (один проект подставляется сам, чужой → 403).

`GET /api/ask-ai/screens` — только список экранов (нужен обычный report-user JWT).

`GET /api/auth/me` также отдаёт `allowed_projects: string[] | null` (`null` = все) и `allowed_reports`.  
`GET /api/auth/default-filters?nav_id=` — дефолты роли для экрана (с учётом project ACL).

### 7.3. Реестр `SCREENS` — единая точка правды для ИИ-экранов

Файл: `webapp/api/app/services/ask_ai_reports.py`.

```python
SCREENS = {
  "working-documentation": {
    "report": "screen_working_documentation",  # id для XCA
    "title": "Рабочая документация",
    "src": "docs/working-documentation",
    "auth_names": ["Рабочая документация", "Просрочка выдачи РД"],  # legacy Streamlit
    "ctx_hint": "…",  # подсказка в ctx ссылки
  },
  …
}
```

**Как добавить новый экран в Ask AI + ACL:**

1. Добавить пункт в `nav.ts` с новым `id`.
2. Добавить запись в `SCREENS` (+ зеркало в `web/src/lib/ask-ai-reports.ts` при необходимости UI).
3. Повесить `require_report_access("<id>")` на соответствующий API-роутер.
4. Перезапустить API → `ensure_roles_seeded` **не** допишет новый экран в уже заполненные роли автоматически (у них уже есть строки в `role_reports`).  
   → админ вручную отметит чекбокс **или** нужен одноразовый migration/script «добавить report_id всем системным ролям по legacy».
5. Обновить `ASK_AI_XCA_FEEDBACK.md` / контракт с командой XCA.

Клиентская кнопка смотрит `ASK_AI_SCREENS[nav.id]` — нет записи → кнопки нет (даже при доступе к дашборду).

### 7.4. Что ИИ-агент (OpenCode / in-app assistant) должен учитывать

Отдельно от XCA Ask AI есть in-app assistant (`/api/assistant/…`). Сейчас он **не** режет инструменты по `role_reports` так же жёстко, как dashboard GET + Ask link.  

При доработке ИИ-агента рекомендуется:

1. Читать `role` / `allowed_reports` / `allowed_projects` из сессии (`/auth/me`).
2. Перед вызовом аналитических скриптов / proxy на dashboard API — `auth.role_can_open_report(role, nav_id)` и `auth.resolve_allowed_projects` / clamp списка проектов.
3. В промпт/каталог доступных «tools/screens» отдавать только пересечение с матрицей (как `roles-catalog`, но per-user).
4. Не подставлять в контекст данные экранов/проектов вне матрицы (даже если скрипт физически может прочитать БД).
5. Не дублировать allowlists в коде агента — только `auth.py` / таблицы.

Цифры по-прежнему только через БД (`web_data.db` + analytics-скрипты), не через сырой `web/` — см. правила data architecture.

### 7.5. Подпись ссылки (кратко)

Параметры + HMAC (`XCA_ASK_SECRET`), TTL по `ts`.  
Конфиг: `XCA_ASK_BASE_URL`, `XCA_ASK_SECRET` в env API.  
Без секрета → `/link` отвечает **503**, не 403.

---

## 8. Как проверить руками / автоматом

### Админ UI

1. Создать роль `rd_only` → только «Рабочая документация».
2. Юзер с этой ролью: в меню один РД; `/finance/bdds` → «Нет доступа»; Ask AI на РД видна, на финансах — нет.

### API (идея smoke)

```text
POST /api/auth/login {username, password} → token
GET  /api/auth/me     → allowed_reports, allowed_projects
GET  /api/auth/default-filters?nav_id=working-documentation → filters{}
GET  /api/bdds        Authorization: Bearer … → 403 (если экран не в роли)
GET  /api/working-documentation → 200 (проекты уже clamped)
POST /api/ask-ai/link { "nav_id": "bdds", "q": "…" } → 403
POST /api/ask-ai/link { "nav_id": "working-documentation", "q": "…" } → 200 или 503 (нет XCA secret)
GET  /api/ask-ai/roles-catalog → roles[].projects не всегда ["*"]
```

Тесты: `webapp/api/tests/test_ask_ai.py` (+ полный `pytest tests`).

---

## 9. Фаза 2 — сделано

| Возможность | Статус |
|-------------|--------|
| Default filters при открытии дашборда | ✅ `GET /api/auth/default-filters?nav_id=` + `useUrlFilterState({ navId })` |
| Проекты роли (`role_projects`) | ✅ админка «Права доступа», Ask AI catalog |
| Проекты пользователя (`project_permissions`) | ✅ админка «Пользователи» |
| Clamp проектов в dashboard API | ✅ `project_scope.py` |
| Ask AI `/link` учитывает scope | ✅ |

**Default filters:** URL важнее дефолтов. Ключи = `INITIAL` вьюхи (`projects`, `date_from`, …).  
`report_name` в админке фильтров — title / `auth_names` экрана.

**Ещё позже:** паритет Streamlit main; in-app assistant tools ACL.

---

## 10. Типовые ошибки при разработке

| Симптом | Причина |
|---------|---------|
| Правки в `auth.py` «не видны» API | API смотрел не в тот core; приоритет `showcase/bi-analytics-v-5-main`. `CORE_APP_DIR` / `BI_CORE_APP_DIR`. |
| Новый экран есть в меню, но ни у кого в матрице | Сид не переписывает существующие `role_reports`. Чекбокс или скрипт. |
| Ask AI 403 при доступе к UI | Расхождение `ASK_AI_SCREENS` / `SCREENS`, или устаревший `allowed_reports` → перелогин. |
| Ask AI 403 на project | Юзер/роль без этого проекта в scope. |
| `/link` 503 | Нет `XCA_ASK_SECRET` / `XCA_ASK_BASE_URL`. |
| Dashboard 401 у всех | Запросы без Bearer (`authHeaders()` уже default в api.ts). |
| Не удаляется роль | Есть пользователи с этим `role` или роль системная. |
| Дефолт-фильтр не применяется | Ключ не совпал с `INITIAL`, или уже есть query в URL. |

---

## 11. Чеклист для следующего шага по ИИ

- [ ] Зафиксировать с XCA: кастомные `role.code` и не-`*` `projects` из `roles-catalog` подхватываются (poll).
- [x] Per-user catalog: `GET /api/ask-ai/my-screens` → `allowed_reports` (`screen_*`) + `allowed_projects`.
- [ ] Assistant tools: wrap через `role_can_open_report` + project clamp.
- [ ] При ответе агента логировать `role` + `nav_id`/`report` + `project` (аудит).
- [ ] Единый справочник написания проектов (1С ↔ UI ↔ XCA).
- [ ] Вебхук «матрица/данные обновились» (пока poll `roles-catalog` + `GET /api/admin/data-status`).

---

## 12. Ответы коллеге по ИИ (API дашборда + роли)

Стенд: `https://insipidly-carefree-husky.cloudpub.ru`  
Секрет машинного доступа: `WEBAPP_ADMIN_TOKEN` → заголовок `X-Admin-Token` (тот же, что FTP sync).

### 12.1. Токен к `GET /api/ask-ai/roles-catalog`

**Уже готово.** Доступ:

```http
GET /api/ask-ai/roles-catalog
Authorization: Bearer <admin JWT>
# или
X-Admin-Token: <WEBAPP_ADMIN_TOKEN>
```

Ответ: `roles[].code`, `roles[].reports` (**`screen_*`**), `roles[].projects` (`["*"]` или явный список из `role_projects`), плюс `screens[]`.  
Матрица живая из `users.db` — **не хардкодить** у себя; poll после админских правок.

### 12.2. Вызов data-API от имени пользователя

Все dashboard GET режутся JWT пользователя:

```http
POST /api/auth/login  {"username","password"} → { token, user }
GET  /api/<report>    Authorization: Bearer <token>
```

| `screen_*` | HTTP (пример) |
|------------|----------------|
| `screen_bdds` | `GET /api/bdds?...` |
| `screen_bdr` | `GET /api/bdr?...` |
| `screen_working_documentation` | `GET /api/working-documentation?...` |
| … | префикс `/api/<kebab-nav>` как в `src` / роутерах |

Правила:

- Без Bearer → **401**; экран вне роли → **403**; проект вне scope → clamp / пустой результат / 403 на Ask.
- Токен = HMAC session (`WEBAPP_AUTH_TOKEN_TTL_SECONDS`, по умолчанию **8 ч**). В payload только `sub=username`; **роль читается из БД на каждый запрос** → смена роли в админке действует на data-API сразу.
- **Impersonation / service-token «как user X» пока нет.** Варианты для XCA:
  1. (рекомендуем сейчас) белый список команд из `roles-catalog` / `my-screens` + **свои** витрины/DWH;
  2. если нужны именно цифры дашборда — нужен **user Bearer** (логин пользователя или будущий short-lived data-token в `/link`); отдельный machine→user proxy не делали.

### 12.3. Полный scope пользователя — `GET /api/ask-ai/my-screens`

**Сделано.** User Bearer (любой report-user):

```json
{
  "ok": true,
  "uid": "u_1042",
  "role": "rd_only",
  "allowed_nav_ids": ["working-documentation"],
  "allowed_reports": ["screen_working_documentation"],
  "allowed_projects": ["Есипово-5"],
  "updated_at": "2026-08-11T…"
}
```

- `allowed_projects: null` = все проекты (admin или без ограничений).
- Дублирует смысл `/api/auth/me`, но `allowed_reports` сразу в **`screen_*`** (для белого списка команд).
- `/link` по-прежнему кладёт в URL **один** `project` (текущий фильтр экрана, уже clamped). Полный набор берите из `my-screens`, не из query.

Эквивалент UI-сессии: `GET /api/auth/me` → `allowed_reports` (**nav.id**) + `allowed_projects`.

### 12.4. Фильтры экрана в ссылке (`project`, `period`, `filters`)

**Уже передаём** с кнопки «Спросить ИИ»: в момент клика читается `window.location.search` → `POST /api/ask-ai/link`.

| Параметр | Когда есть |
|----------|------------|
| `project` | выбран конкретный проект (не «Все»); иначе может подставиться единственный из ACL |
| `period` | `YYYY-MM` или `YYYY-MM-DD..YYYY-MM-DD` из date_from/date_to |
| `filters` | прочий JSON (block, …), ≤400 символов |

На стороне XCA: **если параметра нет — не считать «весь портфель за всё время» для пользователя с ACL**; взять `allowed_projects` из `my-screens` и разумный дефолт периода (или спросить). Пустой `project` у admin без фильтра = действительно широкий scope, как на экране.

### 12.5. Единое написание проектов

Сейчас источник имени в `project` = **строка фильтра UI** (= имя в данных дашборда / БД), без нормализации `Дмитровский` ↔ `Дмитровский-1`.  
Сопоставление алиасов — зона XCA **или** будущий общий справочник на дашборде.  
Для ACL: сравнение **exact string** с `role_projects` / `project_permissions`. Промах имени = отказ или «чужой» проект — согласны, это риск; пока админ должен выбирать те же строки, что в фильтрах.

### 12.6. Регламент прав во времени + свежесть данных

| Событие | Поведение |
|---------|-----------|
| Смена роли / матрицы / проектов в админке | **Data-API и `/link` / `my-screens`:** на следующем запросе (роль из БД). **UI меню / localStorage:** до `fetchAuthMe` или перелогина может быть устаревшим. |
| JWT пользователя | TTL **8 ч** (`WEBAPP_AUTH_TOKEN_TTL_SECONDS`); после expiry — 401, новый login. |
| Ссылка Ask `/ask?…&ts&sig` | TTL **~10 мин** (`expires_in: 600`). Отзыв «тикета» раньше — только отказом на вашей стороне по `roles-catalog`/`my-screens` (мы ссылку не инвалидируем централизованно). |
| Обновление матрицы ролей для XCA | Пока **poll** `roles-catalog` (нет вебхука). Рекомендация: раз в N минут + после админских правок вручную. |
| Свежая выгрузка данных | `GET /api/admin/data-status` (публичный freshness) / `POST /api/admin/ensure-fresh` (Bearer или `X-Admin-Token`). Вебхука «данные залиты» пока нет — poll или свой cron. |

---

*Источник истины: `roles` / `role_reports` / `role_projects` / `project_permissions` / `default_filters` в `users.db`, функции в `auth.py`. UI и Ask AI — потребители.*
