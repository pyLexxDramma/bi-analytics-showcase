# Баг-репорт → Trello: задача для коллеги по ИИ

Кратко: пользователь с дашборда пишет проблему → **ваш AI классифицирует** → карточка улетает в Trello.  
Пока AI нет — работает keyword-fallback. На проде **ai.conall.ru** путь до Trello уже живой.

Код клиента: `bug_report/` (репо `bi-analytics`).

---

## Что за фича

На **ai.conall.ru** (webapp) и в Streamlit-дашборде пользователь жмёт «Сообщить об ошибке / проблеме», описывает баг.

Дальше пайплайн:

1. Сохраняем заявку в SQLite (`bug_reports`).
2. Вызываем **ваш** endpoint классификации (если настроен).
3. Карточку **всегда** кладём в список **«Анализ»** (`TRELLO_LIST_TRIAGE`) + метку по категории.
4. Если AI недоступен / не ответил / кривой JSON — **fallback по ключевым словам** (уже есть).

Доска: https://trello.com/b/dZwWzXh4/аналитика-баги-клиент

Новые заявки с формы → колонка **Анализ** (разбор и апрув).  
Категория влияет только на **метку** (label), не на колонку:

| category | Смысл | Метка |
|----------|--------|--------|
| `urgent` | блокер / недоступность | Срочно + баг |
| `bug` | ошибка данных/логики | Ошибки |
| `ui_improvement` | интерфейс / вёрстка | UI |
| `new_feature` | запрос фичи | Фичи |
| `data_question` | вопрос «почему цифра» | Вопросы |
| `other` | непонятно | На разбор |

В «Нужно сделать» / рабочие колонки карточки переносятся **вручную** после апрува.
Priority: `critical` | `high` | `medium` | `low`

---

## Что уже сделано (наша сторона)

- UI формы + API `POST /api/bugform/submit` на **ai.conall.ru**
- Модуль `bug_report/` (классификатор, Trello-клиент, очередь SQLite)
- Trello Power-Up, API Key/Token, доска, списки, метки
- Secrets на проде (`TRELLO_*`), деплой проверен: карточка создаётся
- Fallback-классификация без AI
- Контракт ниже — клиент уже умеет ходить на ваш URL

**AI endpoint пока не подключён.** Env пустые → всегда fallback.

---

## Что нужно сделать тебе

### 1. Endpoint

`POST /api/classify-bug-report`  
Auth: `Authorization: Bearer <token>`

**Request:**

```json
{
  "text": "На вкладке БДР не сходятся итоги",
  "context": {
    "username": "ivanov",
    "user_role": "analyst",
    "report_tab": "БДР",
    "page_url": "...",
    "theme": "dark",
    "version_id": 42,
    "app_build": "webapp"
  }
}
```

`text` — обязателен. `context` — справочный, можно использовать в промпте.

**Response (строго JSON-объект):**

```json
{
  "category": "bug",
  "priority": "high",
  "title": "БДР: расхождение итогов",
  "summary": "Пользователь сообщает, что итоги на вкладке БДР не сходятся с ожидаемыми.",
  "confidence": 0.91
}
```

Правила:

- `category` — только из таблицы выше
- `priority` — только `critical` | `high` | `medium` | `low`
- `title` — до ~80 символов, без переносов
- `summary` — 1–2 предложения
- `confidence` — float `0..1`
- temperature модели ≈ 0, ответ **только JSON** (без markdown-обёртки)
- timeout: цель **≤ 5 сек**, клиент ждёт до ~10 сек (`BUG_REPORT_AI_TIMEOUT_SEC`)
- при `confidence < 0.7` и `category=urgent` клиент понижает категорию до `other` (страховка от ложных срочных)

Внутри — ваш vLLM / OpenCode, например  
`http://127.0.0.1:8000/v1/chat/completions`.

### 2. Health

`GET /health` → `200`  
(удобно для мониторинга; клиент баг-репорта его не дергает обязательно)

### 3. Сеть

Клиент ходит с **prod API контейнера ai.conall.ru** (VPS).

Нужен URL, доступный **с этого VPS** (internal / VPN / reverse-proxy).  
Tunnel OpenCode `:4096` сам по себе недостаточен — нужен отдельный HTTP wrapper с контрактом выше.

### 4. Передать нам после готовности

```
BUG_REPORT_AI_URL=https://<host-доступный-с-VPS>/api
BUG_REPORT_AI_TOKEN=<secret>
```

Опционально:

```
BUG_REPORT_AI_TIMEOUT_SEC=10
BUG_REPORT_AI_MIN_CONFIDENCE=0.7
```

Мы пропишем в GitHub Secrets / `.env` на проде и перезадеплоим.  
После этого в карточке/логах `ai_source=remote` вместо `fallback`.

---

## Как проверить у себя (acceptance)

```bash
curl -sS -X POST "https://<твой-host>/api/classify-bug-report" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"text":"Кнопка экспорта не работает на светлой теме","context":{"theme":"light","report_tab":"БДР"}}'
```

Ожидание: JSON с `category` (скорее `ui_improvement` или `bug`), `priority`, `title`, `summary`, `confidence`.

Ещё кейсы для промпта:

| Текст | Ожидаемая category |
|-------|-------------------|
| «Срочно, дашборд недоступен» | `urgent` |
| «Цифры в ГДРС не сходятся с 1С» | `bug` или `data_question` |
| «Хочу фильтр по региону» | `new_feature` |
| «Цвет легенды нечитаемый» | `ui_improvement` |

---

## Важно

- Trello и форму **не трогай** — это наша зона.
- Секреты Trello тебе не нужны.
- Пока endpoint не отдан — прод работает на fallback, заявки в Trello уже создаются.
- Код вызова: `bug_report/classifier.py` → `classify_remote()`.
