# BI Analytics — Showcase (демо)

Отдельный репозиторий для публичного демо-дашборда. Не содержит клиентских данных и не подключается к FTP.

**Production URL:** https://bi-analytics-demo.streamlit.app/

Основной репозиторий (dev / release): [bi-analytics](https://github.com/pyLexxDramma/bi-analytics)

## Запуск локально

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
streamlit run showcase_app.py
```

Порт **8502** (основной дашборд обычно на 8501) — задан в `.streamlit/config.toml`.
Явно: `streamlit run showcase_app.py --server.port 8502`

Приложение: http://localhost:8502

## Next.js + FastAPI (пилот миграции)

Каркас в `webapp/` — UI по Tremor data-spec, данные synthetic или FTP (как ai.conall.ru).

**Стек для коллег:** [webapp/STACK.md](webapp/STACK.md)

```powershell
# FTP локально (секреты из основного .streamlit/secrets.toml)
python webapp\scripts\setup_local_ftp_env.py

cd webapp\api
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# синк FTP (один раз / по необходимости)
Invoke-RestMethod -Method POST -Uri http://127.0.0.1:8000/api/admin/sync -Headers @{ Authorization = "Bearer local-dev-sync" }

cd webapp\web
npm install
npm run dev
```

На Windows, если `:8000` недоступен — API на **8010**, в `webapp/web/.env.local`:
`NEXT_PUBLIC_API_BASE=http://127.0.0.1:8010`

- UI: http://localhost:3000  
- API docs: http://127.0.0.1:8000/docs (или `:8010`)  
- Публичный VPS (Next pilot): https://insipidly-carefree-husky.cloudpub.ru  
- Подробности: [webapp/README.md](webapp/README.md)
- **Стек для коллег:** [webapp/STACK.md](webapp/STACK.md)

Streamlit Cloud остаётся на синтетике. FTP — только при `WEBAPP_DATA_MODE=ftp` (локально или VPS).

## Структура

| Путь | Назначение |
|------|------------|
| `showcase_app.py` | Точка входа для Streamlit Cloud и локального запуска |
| `showcase/` | Bootstrap, тема, allowlist демо-экранов |
| `showcase_data/web/` | Фейковые выгрузки (1С, MSP, TESSA) |
| `bi-analytics-v-5-main/` | Код дашборда (экраны, auth, charts) |

Данные берутся **только** из `showcase_data/web/`. Каталог `bi-analytics-v-5-main/web/` (клиент) в demo не используется.

## Streamlit Cloud

- **Main file path:** `showcase_app.py`
- **Branch:** `main`
- Рекомендуемые secrets (опционально):

```toml
BI_STREAMLIT_PUBLIC_URL = "https://bi-analytics-demo.streamlit.app"
```

Bootstrap (`showcase/bootstrap.py`) автоматически выставляет `BI_ANALYTICS_SHOWCASE_MODE=1`, отключает FTP/ingest и AI-помощник.

## Демо-данные

Файлы в `showcase_data/web/` — синтетические. SQLite (`showcase_data/users.db`, `web_data.db`) создаются при первом запуске и в git не коммитятся.

## Синхронизация с основным репо

Общие экраны живут в `bi-analytics-v-5-main/`. При обновлении ядра в основном репо — cherry-pick или merge нужных коммитов в этот репозиторий.

## Что можно менять свободно

- UI/тема demo, KPI, тексты
- Демо-проекты и CSV в `showcase_data/web/`
- CSS в `showcase/theme/`

## Чего нет в этом репо

- Клиентские выгрузки и FTP
- OpenCode / AI-помощник (отключён)
- Deploy на VPS клиента
- test text
