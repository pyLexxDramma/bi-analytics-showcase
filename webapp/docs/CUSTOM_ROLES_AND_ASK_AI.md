# Кастомные роли, ACL дашбордов и Ask AI (showcase webapp)

Документ для разработки ИИ-помощника и смежных фич.  
Репозиторий: `bi-analytics-showcase` · коммит фичи: `5e2d155` · дата: 2026-08-11.

Связанные материалы:

- Контракт ссылки Ask AI → XCA: `webapp/docs/ASK_AI_XCA_FEEDBACK.md`
- Реестр экранов (server): `webapp/api/app/services/ask_ai_reports.py`
- Реестр экранов (client): `webapp/web/src/lib/ask-ai-reports.ts`
- Нав. меню: `webapp/web/src/lib/nav.ts`

---

## 1. Что сделано (v1)

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
| Дефолтные фильтры роли при открытии дашборда | ❌ фаза 2 |
| Разрезка по проектам (`project_permissions`) | ❌ фаза 2 |
| Полный паритет Streamlit main с табличной матрицей | ❌ позже |

**Принцип для ИИ:** доступ к Ask AI по экрану = доступ к самому дашборду. Отдельной роли «можно спрашивать ИИ» нет.

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
| Ask AI link + catalog | `webapp/api/app/routers/ask_ai.py`, `…/services/ask_ai.py` |
| UI ролей | `webapp/web/src/components/settings/admin-roles-panel.tsx` |
| Сессия / `allowed_reports` | `webapp/web/src/lib/auth.ts` |
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

users.role               -- строковый код; логический FK на roles.code
```

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
  "can_admin": false
}
```

Клиент кладёт `allowed_reports` / `can_admin` в `localStorage` (`auth.ts`).

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
4. Создать роль (код латиницей: `a-z0-9_-`) → отметить дашборды → Сохранить.
5. **«Пользователи»** — назначить роль из dropdown (включая кастомные).

Пользователь с урезанной ролью:

- в сайдбаре / поиске / Cmd+K видит только разрешённые пункты;
- прямой URL запрещённого экрана → блок «Нет доступа» (данные API всё равно 403);
- кнопка **«Спросить ИИ»** не рендерится, если `nav.id ∉ allowed_reports`.

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
      "projects": ["*"]
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
- `projects: ["*"]` пока всегда: project ACL в Ask AI **не включён** (фаза 2).

`GET /api/ask-ai/screens` — только список экранов (нужен обычный report-user JWT).

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

1. Читать `role` / `allowed_reports` из сессии пользователя (тот же `users.db` / `/auth/me`).
2. Перед вызовом аналитических скриптов / proxy на dashboard API — `auth.role_can_open_report(role, nav_id)`.
3. В промпт/каталог доступных «tools/screens» отдавать только пересечение с матрицей (как `roles-catalog`, но per-user).
4. Не подставлять в контекст данные экранов вне матрицы (даже если скрипт физически может прочитать БД).
5. Не дублировать allowlists в коде агента — только `auth.py` / `role_reports`.

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
GET  /api/auth/me     → allowed_reports
GET  /api/bdds        Authorization: Bearer … → 403
GET  /api/working-documentation → 200
POST /api/ask-ai/link { "nav_id": "bdds", "q": "…" } → 403
POST /api/ask-ai/link { "nav_id": "working-documentation", "q": "…" } → 200 или 503 (нет XCA secret)
```

Тесты: `webapp/api/tests/test_ask_ai.py`.

---

## 9. Фаза 2 (не сделано — бэклог для ИИ/продукта)

1. **Default filters** — таблица `default_filters` уже есть + UI в админке, но при открытии дашборда в webapp **не применяется**. Нужно: при mount экрана читать фильтры роли и подставлять в URL/state.
2. **Project scope** — `project_permissions` + в `roles-catalog` поле `projects` не `["*"]`; Ask AI и dashboard API фильтруют данные.
3. **In-app assistant ACL** — те же `role_can_open_report` на tools/catalog.
4. **Streamlit main** — читать ту же матрицу, убрать дубли allowlists (сейчас webapp уже primary для showcase).

---

## 10. Типовые ошибки при разработке

| Симптом | Причина |
|---------|---------|
| Правки в `auth.py` «не видны» API | API смотрел не в тот core; сейчас приоритет `showcase/bi-analytics-v-5-main`. Проверь `CORE_APP_DIR` / `BI_CORE_APP_DIR`. |
| Новый экран есть в меню, но ни у кого в матрице | Сид не переписывает существующие `role_reports`. Добавь чекбоксом или скриптом. |
| Ask AI 403 при доступе к UI | Расхождение client `ASK_AI_SCREENS` и server `SCREENS`, или устаревший `allowed_reports` в localStorage → перелогин / `fetchAuthMe`. |
| `/link` 503 | Нет `XCA_ASK_SECRET` / `XCA_ASK_BASE_URL`. |
| Dashboard 401 у всех | Запросы без Bearer; нужны `authHeaders()` (уже default в api.ts). |
| Не удаляется роль | Есть пользователи с этим `role` или роль системная. |

---

## 11. Чеклист для следующего шага по ИИ

- [ ] Зафиксировать с XCA: кастомные `role.code` из каталога подхватываются у них автоматически (poll `roles-catalog`).
- [ ] Per-user catalog endpoint (опционально): `GET /api/ask-ai/my-screens` → только `allowed_reports` текущего юзера.
- [ ] Assistant tools: wrap через `role_can_open_report`.
- [ ] При ответе агента логировать `role` + `nav_id`/`report` (аудит).
- [ ] Фаза 2: default filters + projects в Ask AI ctx/`projects`.

---

*Источник истины по матрице доступа — таблицы `roles` / `role_reports` в `users.db`, функции в `auth.py`. UI и Ask AI — потребители этой матрицы.*
