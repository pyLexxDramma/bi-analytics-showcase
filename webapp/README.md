# Showcase Webapp (Next.js + Tremor + FastAPI)

Пилот миграции UI по макету `bi-analytics-data-spec` (Tremor).  
Пилот-экран: **дебиторка подрядчиков**.

## Локально

```powershell
# API (synthetic demo data)
cd webapp\api
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# UI
cd webapp\web
npm install
npm run dev
```

- UI: http://localhost:3000  
- API: http://127.0.0.1:8000/docs  
- Streamlit demo: http://localhost:8502 (без изменений)

## Данные

| Режим | Env | Каталог | Назначение |
|-------|-----|---------|------------|
| `synthetic` (default) | `WEBAPP_DATA_MODE=synthetic` | `showcase_data/web` | Публичное демо, без FTP |
| `ftp` | `WEBAPP_DATA_MODE=ftp` + `BI_FTP_*` | `webapp/data/web` | Как ai.conall.ru |

FTP **не** пишет в `showcase_data/web` (защита публичного демо).

Синхронизация (только ftp + токен):

```http
POST /api/admin/sync
Authorization: Bearer <WEBAPP_ADMIN_TOKEN>
```

Секреты как на проде: `BI_FTP_HOST`, `BI_FTP_USER`, `BI_FTP_PASSWORD`, `BI_FTP_REMOTE_DIR=/web`.

## Docker

```powershell
cd webapp
copy api\.env.example .env   # при необходимости
docker compose up --build
```

## Деплой (GitHub → VPS)

Workflow: `.github/workflows/webapp.yml`

1. CI всегда: smoke API + build Next  
2. Deploy на VPS — если заданы secrets:
   - `WEBAPP_VPS_HOST`
   - `WEBAPP_VPS_USER`
   - `WEBAPP_VPS_SSH_KEY`
   - `WEBAPP_VPS_PATH` (например `/opt/bi-analytics-showcase`)

На VPS в `.env` webapp: `WEBAPP_DATA_MODE=ftp` + FTP-секреты (не в git).

Публичный Streamlit Cloud (`bi-analytics-demo.streamlit.app`) остаётся на синтетике.
