# Стек Showcase Next (пилот миграции со Streamlit)

Кратко для коллег: что за что отвечает и как запускать.

## Продукт

| | |
|---|---|
| Репозиторий | `pyLexxDramma/bi-analytics-showcase` |
| Назначение | Демо + пилот нового UI (не путать с prod `bi-analytics` / ai.conall.ru) |
| Публичный URL (сейчас) | https://insipidly-carefree-husky.cloudpub.ru |
| Streamlit-демо (старое) | https://bi-analytics-demo.streamlit.app · локально `:8502` |

## Архитектура webapp

```
Браузер (Next.js :3000)
    │  HTTP /api/*
    ▼
FastAPI (:8000)
    │
    ├─ synthetic → showcase_data/web/
    └─ ftp → webapp/data/web/  ← те же выгрузки, что на ai.conall.ru
         ▲
         FTP (BI_FTP_*)
```

На VPS перед UI стоит **Caddy :3080** (same-origin: `/` → Next, `/api` → FastAPI) + туннель CloudPub.

## Платформы и фреймворки

### Frontend (`webapp/web`)

| Технология | Зачем |
|------------|--------|
| **Next.js 15** (App Router) | UI, роутинг, SSR/static |
| **React 19** | Компоненты |
| **TypeScript** | Типы |
| **Tailwind CSS 3** | Стили |
| **Tremor** (`@tremor/react`) | KPI, Card, BarChart, DonutChart (макет как data-spec) |
| **Recharts** (через Tremor) | Графики |
| **npm** | Пакеты |

Визуальный референс: `bi-analytics-data-spec` (Vite+Tremor прототип дашбордов).

### Backend (`webapp/api`)

| Технология | Зачем |
|------------|--------|
| **Python 3.11** | Рантайм |
| **FastAPI** | REST API |
| **Uvicorn** | ASGI-сервер |
| **pandas** | Агрегации DK / фильтры |
| **Pydantic v2** | (через FastAPI) |
| **ftp_sync.py** из `bi-analytics-v-5-main/` | Скачивание с FTP как на проде |

### Данные

| Режим | Env | Каталог |
|-------|-----|---------|
| synthetic (демо) | `WEBAPP_DATA_MODE=synthetic` | `showcase_data/web/` |
| ftp (клиентские) | `WEBAPP_DATA_MODE=ftp` + `BI_FTP_*` | `webapp/data/web/` |

Секреты FTP: те же, что у Streamlit — `[ftp]` в `.streamlit/secrets.toml` основного приложения (`host` / `user` / `password` / `remote_dir`).

Пилот-экран: **дебиторка подрядчиков** (`/debit-credit` ← `/api/debit-credit`).

### Инфра / деплой

| Технология | Зачем |
|------------|--------|
| **Docker Compose** | api + web + edge |
| **Caddy 2** | reverse proxy :3080 |
| **GitHub Actions** | CI + SSH deploy (`.github/workflows/webapp.yml`) |
| **CloudPub** | публичный HTTPS-туннель на VPS |
| **VPS (Linux)** | рантайм Docker |

Секреты Actions: `WEBAPP_VPS_HOST`, `WEBAPP_VPS_PORT`, `WEBAPP_VPS_USER`, `WEBAPP_VPS_PASSWORD`, `WEBAPP_VPS_PATH`.

### Что остаётся на Streamlit (пока)

- Основной клиентский дашборд: **Streamlit + Plotly + pandas + SQLite** (`bi-analytics`, ai.conall.ru)
- Showcase Streamlit: тот же стек, порт **8502**, данные только synthetic

## Локальный запуск (с FTP)

```powershell
# 1) .env с FTP (читает secrets.toml основного репо)
python webapp\scripts\setup_local_ftp_env.py

# 2) API
cd webapp\api
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# если :8000 занят/запрещён Windows — используйте :8010
# uvicorn app.main:app --reload --port 8010
# и в web/.env.local: NEXT_PUBLIC_API_BASE=http://127.0.0.1:8010


# 3) Синк FTP → webapp/data/web
# PowerShell:
Invoke-RestMethod -Method POST -Uri http://127.0.0.1:8000/api/admin/sync `
  -Headers @{ Authorization = "Bearer local-dev-sync" }

# 4) UI
cd webapp\web
npm install
npm run dev
# http://localhost:3000/debit-credit
```

Проверка режима: http://127.0.0.1:8000/api/health → `"data_mode":"ftp"`.

Без FTP (синтетика): не создавайте `api/.env` или поставьте `WEBAPP_DATA_MODE=synthetic`.

## Полезные URL

| | |
|---|---|
| UI local | http://localhost:3000 |
| API docs | http://127.0.0.1:8000/docs (Windows часто :8010) |
| Health | http://127.0.0.1:8010/api/health |
| Sync | `POST /api/admin/sync` + Bearer `WEBAPP_ADMIN_TOKEN` |
| Streamlit showcase | http://localhost:8502 |

## Важно

- Клиентский FTP **не** пишется в `showcase_data/web` (публичное демо).
- `webapp/api/.env` и `webapp/data/` в git не коммитятся.
- Полный перенос всех экранов со Streamlit — по одному; сейчас пилот только дебиторка.
