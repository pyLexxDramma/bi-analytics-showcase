# Showcase Webapp (Next.js + Tremor + FastAPI)

Пилот миграции UI по макету `bi-analytics-data-spec` (Tremor).  
Пилот-экран: **дебиторка подрядчиков**.

## Стек (для коллег)

Полный список платформ/фреймворков: **[STACK.md](STACK.md)**

## Локально (с FTP)

```powershell
python webapp\scripts\setup_local_ftp_env.py

cd webapp\api
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# в другом терминале — синк FTP → webapp/data/web
Invoke-RestMethod -Method POST -Uri http://127.0.0.1:8000/api/admin/sync `
  -Headers @{ Authorization = "Bearer local-dev-sync" }

cd webapp\web
npm install
npm run dev
```

Или API одной кнопкой: `webapp\start-api-ftp.bat`

- UI: http://localhost:3000/debit-credit  
- Health: http://127.0.0.1:8000/api/health → `"data_mode":"ftp"`  
- Streamlit demo: http://localhost:8502 (synthetic, без изменений)

Без FTP: удалите `webapp/api/.env` или поставьте `WEBAPP_DATA_MODE=synthetic`.

## Данные

| Режим | Env | Каталог | Назначение |
|-------|-----|---------|------------|
| `synthetic` | `WEBAPP_DATA_MODE=synthetic` | `showcase_data/web` | Публичное демо |
| `ftp` | `WEBAPP_DATA_MODE=ftp` + `BI_FTP_*` | `webapp/data/web` | Как ai.conall.ru |

FTP **не** пишет в `showcase_data/web`.

```http
POST /api/admin/sync
Authorization: Bearer <WEBAPP_ADMIN_TOKEN>
```

## Публичный деплой (VPS)

- Docker: `api` + `web` + Caddy edge **:3080**
- CloudPub: https://insipidly-carefree-husky.cloudpub.ru/debit-credit  
- Каталог: `~/apps/bi-analytics-showcase`  
- CI: `.github/workflows/webapp.yml` (`WEBAPP_VPS_*`)
- Daily FTP→БД (стенд `ftp`): `.github/workflows/ftp-daily-ingest.yml` ≈ 11:00 МСК → `webapp/scripts/ftp_daily_ingest.sh`

```powershell
cd webapp
docker compose up -d --build
```
