# Cutover checklist — ai.conall.ru → Next prod

## Уже сделано в git
- showcase: prod compose/scripts + `deploy-ai-conall-prod.yml` + `ftp-daily-ingest-prod.yml` (pushed `main`)
- bi-analytics: Streamlit VPS deploy только `workflow_dispatch` (pushed `main`)

## GitHub Secrets (showcase repo)
Добавить (или скопировать с WEBAPP_VPS_*):
- `PROD_VPS_HOST` = тот же, что `WEBAPP_VPS_HOST` (iivm / 94.141.105.174)
- `PROD_VPS_USER` = `iiuser`
- `PROD_VPS_PORT` = `2275`
- `PROD_VPS_PASSWORD` или `PROD_VPS_SSH_KEY`
- `PROD_VPS_PATH` = `/home/iiuser/apps/bi-analytics-webapp-prod`
- `XCA_ASK_*` уже есть

## Cutover на серверах (по одной команде)

### iivm (iiuser)
1. Clone + seed .env + deploy
2. Set admin password
3. Health check :3081
4. crontab sync OpenCode DB (optional daily)

### dash-ai-01 (dashai)
1. Backup nginx ai-conall
2. Change location / → 10.35.15.75:3081
3. nginx -t && reload
4. stop/disable bi-analytics.service

## Приёмка
- https://ai.conall.ru/login — admin / adminAIcon!2026X
- Экраны + FTP данные
- OpenCode / in-app AI
- cloudpub без изменений
