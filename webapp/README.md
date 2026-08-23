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

## Visual walk (prod vs cloudpub)

Скриншоты всех отчётов, вкладок, фильтров, чекбоксов и тёмной темы на [ai.conall.ru](https://ai.conall.ru) и [cloudpub](https://insipidly-carefree-husky.cloudpub.ru/), затем pixel-diff 1:1.

```powershell
cd d:\AI_codding\Analitics\bi-analytics-showcase\webapp
node scripts/visual_walk_parity.mjs
```

Или двойной клик: `webapp\scripts\visual_walk_parity.bat`

Отчёт: `webapp/parity_out/walk_*/compare.html` (prod | cloudpub | diff).

| Задача | Команда |
|---|---|
| Оба стенда, все экраны | `node scripts/visual_walk_parity.mjs` |
| Один экран | `$env:ONLY="working-documentation"; node scripts/visual_walk_parity.mjs` |
| Только prod | `$env:SITE="prod"; node scripts/visual_walk_parity.mjs` |
| Только cloudpub | `$env:SITE="dev"; node scripts/visual_walk_parity.mjs` |
| Порог (по умолчанию 0.3%) | `$env:DIFF_THRESHOLD="0.003"; node scripts/visual_walk_parity.mjs` |

Логин: `PROD_USER` / `PROD_PASS`, `DEV_USER` / `DEV_PASS` (на cloudpub если не зайдёт — скрипт сам пробует `admin` / `admin`).

Первый раз на машине: `npm install playwright pngjs pixelmatch` и `npx playwright install chromium` из `webapp/`.
