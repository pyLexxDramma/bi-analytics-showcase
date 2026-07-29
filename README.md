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

```powershell
cd webapp\api
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

cd webapp\web
npm install
npm run dev
```

- UI: http://localhost:3000  
- API docs: http://127.0.0.1:8000/docs  
- Публичный VPS (Next pilot): https://insipidly-carefree-husky.cloudpub.ru  
- Подробности / FTP / Docker / VPS: [webapp/README.md](webapp/README.md)

Публичный Streamlit Cloud остаётся на фейковых данных. Клиентский FTP — только в режиме `WEBAPP_DATA_MODE=ftp` на VPS с секретами.

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
