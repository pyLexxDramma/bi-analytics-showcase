#!/usr/bin/env bash
# Deploy Next+FastAPI webapp on VPS (run from repo root or webapp/).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WEBAPP="$ROOT/webapp"
cd "$WEBAPP"

mkdir -p data/web data/db data/report_cache data/jobs

echo "==> docker compose build/up in $WEBAPP"
docker compose pull edge || true
docker compose up -d --build --remove-orphans --force-recreate

echo "==> ensure CloudPub publish for :3080"
if docker ps -a --format '{{.Names}}' | grep -qx cloudpub-webapp; then
  docker start cloudpub-webapp >/dev/null || true
elif docker ps -a --format '{{.Names}}' | grep -qx cloudpub-tunnel; then
  TOKEN="$(docker inspect cloudpub-tunnel --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^TOKEN=//p')"
  IMG="$(docker inspect cloudpub-tunnel --format '{{.Config.Image}}')"
  if [[ -n "${TOKEN:-}" ]]; then
    docker run -d --name cloudpub-webapp --restart unless-stopped --network host \
      -e TOKEN="$TOKEN" "$IMG" publish http 3080
  fi
fi

echo "==> health"
sleep 3
curl -fsS "http://127.0.0.1:3080/api/health" || true
echo
curl -fsS -o /dev/null -w "UI %{http_code}\n" "http://127.0.0.1:3080/" || true

# Данные стенда обновляются только по кнопке «FTP + перезагрузить БД», а она требует
# admin-токен. Внутри контейнера токен не нужен, поэтому синк делаем на деплое —
# иначе стенд остаётся на старом снимке 1С и цифры расходятся с основным дашбордом.
if [[ "${WEBAPP_SKIP_SYNC:-0}" == "1" ]]; then
  echo "==> data sync skipped (WEBAPP_SKIP_SYNC=1)"
else
  echo "==> data sync (FTP -> web/ -> web_data.db)"
  docker compose exec -T api python -c \
    'from app.services.ftp_ingest import run_ftp_then_db_ingest; print(run_ftp_then_db_ingest(force=False))' \
    || echo "data sync FAILED (docker compose logs api)"
fi

# Прогрев только HTTP (не в процессе API) и только дефолтные фильтры:
# первый клик по фильтру всё равно считается заново — известное ограничение.
echo "==> warmup (default filters)"
for path in "/api/developer-projects" "/api/bdds" "/api/bdr"; do
  curl -fsS -o /dev/null -m 600 -w "warm ${path} %{http_code} %{time_total}s\n" \
    "http://127.0.0.1:3080${path}" || echo "warm ${path} FAILED"
done

echo "Deploy OK. Edge: http://127.0.0.1:3080"
docker logs cloudpub-webapp --tail 5 2>/dev/null || true
