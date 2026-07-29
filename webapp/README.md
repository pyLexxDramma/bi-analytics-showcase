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

## Публичный деплой (VPS)

Сейчас запущено на VPS:

- Docker: `api` + `web` + Caddy edge **:3080**
- Туннель CloudPub: https://insipidly-carefree-husky.cloudpub.ru  
  - UI: https://insipidly-carefree-husky.cloudpub.ru/debit-credit  
  - API: https://insipidly-carefree-husky.cloudpub.ru/api/health  

Каталог на сервере: `~/apps/bi-analytics-showcase`  
Деплой: push в `main` → GitHub Actions (`WEBAPP_VPS_*`) или `bash webapp/scripts/server_deploy.sh`

Данные по умолчанию: **synthetic** (`showcase_data/web`).  
FTP как на ai.conall.ru: на VPS в `webapp/.env` задать `WEBAPP_DATA_MODE=ftp` + `BI_FTP_*`, затем `POST /api/admin/sync`.

## Docker / VPS (локально / сервер)

```powershell
cd webapp
docker compose up -d --build
# http://127.0.0.1:3080
```

На VPS: `bash webapp/scripts/server_deploy.sh`  
CI: push в `main` → `.github/workflows/webapp.yml` (secrets `WEBAPP_VPS_*`).

Публичный Streamlit Cloud остаётся на синтетике. Клиентский FTP — только `WEBAPP_DATA_MODE=ftp` + `BI_FTP_*` на VPS.
