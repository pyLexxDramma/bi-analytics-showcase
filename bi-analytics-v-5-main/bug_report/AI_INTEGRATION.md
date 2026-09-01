# Баг-репорт: интеграция AI (задача для OpenCode / vLLM)

Дашборд: **форма → AI endpoint → Trello / SQLite**

Код: `bug_report/`

## Сделано на стороне дашборда

- Кнопка «Сообщить о проблеме» в сайдбаре
- Автоконтекст (вкладка, тема, user, version_id, сборка)
- Fallback-классификатор без AI
- Очередь SQLite `bug_reports`
- Клиент Trello

## Нужно от коллеги (OpenCode / vLLM)

### Endpoint

`POST /api/classify-bug-report`  
Auth: `Authorization: Bearer <token>`

Request:

```json
{
  "text": "На вкладке БДР не сходятся итоги",
  "context": {
    "username": "ivanov",
    "user_role": "analyst",
    "report_tab": "БДР",
    "theme": "dark",
    "version_id": 42
  }
}
```

Response:

```json
{
  "category": "bug",
  "priority": "high",
  "title": "БДР: расхождение итогов",
  "summary": "...",
  "confidence": 0.91
}
```

**category:** `urgent` | `bug` | `ui_improvement` | `new_feature` | `data_question` | `other`  
**priority:** `critical` | `high` | `medium` | `low`

Внутри — вызов vLLM `http://127.0.0.1:8000/v1/chat/completions`, temperature=0, только JSON.

### Сеть

Доступ с VPS дашборда (`ai.conall.ru`) на internal URL endpoint.  
Tunnel :4096 OpenCode недостаточен — нужен отдельный wrapper или internal API.

### Передать дашборду

```
BUG_REPORT_AI_URL=https://<internal-host>/api
BUG_REPORT_AI_TOKEN=<secret>
```

Health: `GET /health` → 200. SLA ≤ 5 сек.

## Env дашборда (Trello — ваши)

### Получить API Key и Token (2026)

Старая страница https://trello.com/app-key перенаправляет в **Power-Up Admin Portal**.

1. Откройте портал (ссылка «Go to the Power-Up Admin Portal» на app-key).
2. **Новое** → создайте приложение.
3. **URL iframe** — нужен живой HTTPS с Power-Up stub (не дашборд и не example.com):
   - папка `bug_report/trello_connector_stub/` → Netlify Drop **или** публичный gist;
   - пример (stub в gist): `https://gist.githubusercontent.com/pyLexxDramma/9494902f8cf69ea75b7433033e953920/raw/index.html`
4. После создания: **API Key** + ссылка **Token** → Allow.
5. Key/Token — только в `.env`, не в чат.

Пошаговая настройка доски: **`scripts/trello_setup_board.py`**

Доска: https://trello.com/b/dZwWzXh4/аналитика-баги-клиент

```bash
# 1. В .env (не в чат!):
TRELLO_API_KEY=...
TRELLO_TOKEN=...

# 2. Создать списки/метки и вывести ID для .env:
python scripts/trello_setup_board.py --create-missing

# 3. Опционально — тестовая карточка:
python scripts/trello_setup_board.py --create-missing --test-card
```

```
TRELLO_API_KEY, TRELLO_TOKEN, TRELLO_BOARD_ID
TRELLO_LIST_URGENT, TRELLO_LIST_BUG, TRELLO_LIST_UI, TRELLO_LIST_FEATURE, TRELLO_LIST_QUESTION, TRELLO_LIST_TRIAGE
TRELLO_LABEL_URGENT, TRELLO_LABEL_BUG, TRELLO_LABEL_UI, TRELLO_LABEL_FEATURE, TRELLO_LABEL_QUESTION, TRELLO_LABEL_TRIAGE
```

## Локальный тест

```
BUG_REPORT_DRY_RUN=1
```

```sql
SELECT id, category, ai_source, status, ai_title FROM bug_reports ORDER BY id DESC;
```

## curl acceptance

```bash
curl -sS -X POST "https://<host>/api/classify-bug-report" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"text":"Кнопка экспорта не работает на светлой теме","context":{"theme":"light"}}'
```
