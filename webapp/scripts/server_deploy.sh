#!/usr/bin/env bash
# Deploy Next+FastAPI webapp on VPS (run from repo root or webapp/).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WEBAPP="$ROOT/webapp"
cd "$WEBAPP"

touch .env
set -a
source ./.env
set +a

mkdir -p data/web data/db data/report_cache data/jobs data/assistant_output

auth_secret="${WEBAPP_AUTH_SECRET:-}"
if [[ ${#auth_secret} -lt 32 ]]; then
  auth_secret="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  printf '\nWEBAPP_AUTH_SECRET=%s\n' "$auth_secret" >>.env
  export WEBAPP_AUTH_SECRET="$auth_secret"
  echo "Generated persistent WEBAPP_AUTH_SECRET in webapp/.env"
fi
if [[ -z "${SHOWCASE_VLLM_BASE_URL:-}" ]]; then
  SHOWCASE_VLLM_BASE_URL="http://10.35.15.75:8000/v1"
  printf '\nSHOWCASE_VLLM_BASE_URL=%s\n' "$SHOWCASE_VLLM_BASE_URL" >>.env
  export SHOWCASE_VLLM_BASE_URL
  echo "Configured showcase vLLM endpoint in webapp/.env"
fi
export SHOWCASE_AI_ENABLED=1
export NEXT_PUBLIC_AI_MODE=full

echo "==> docker compose build/up in $WEBAPP"
docker compose pull edge || true
docker compose stop opencode >/dev/null 2>&1 || true
docker compose up -d --build --remove-orphans --force-recreate db-init api web edge

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

echo "==> health (wait up to 90s)"
ok=0
for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:3080/api/health" >/tmp/webapp_health.json 2>/dev/null; then
    echo "health ok (attempt $i): $(cat /tmp/webapp_health.json)"
    ok=1
    break
  fi
  echo "health wait $i/30..."
  sleep 3
done
curl -fsS -o /dev/null -w "UI %{http_code}\n" "http://127.0.0.1:3080/" || true

if [[ "$ok" -ne 1 ]]; then
  echo "==> HEALTH FAILED — diagnostics"
  docker compose ps -a || true
  docker compose logs api --tail 200 || true
  docker compose logs opencode --tail 200 || true
  docker inspect "$(docker compose ps -q api)" \
    --format 'api State={{.State.Status}} Exit={{.State.ExitCode}} OOM={{.State.OOMKilled}} Err={{.State.Error}}' \
    2>/dev/null || true
  exit 1
fi

echo "==> initialize users database"
docker compose exec -T api python -c \
  'import sqlite3; from app.config import USERS_DB_PATH; from app.services.users_bridge import ensure_users_db; ensure_users_db(seed=True); c=sqlite3.connect(str(USERS_DB_PATH)); n=c.execute("SELECT COUNT(*) FROM users").fetchone()[0]; c.close(); raise SystemExit(0 if n > 0 else "users DB is empty; set strong BI_BOOTSTRAP_ADMIN_PASSWORD for first deploy")'

echo "==> initialize active data version"
if [[ "${WEBAPP_SKIP_SYNC:-0}" == "1" ]]; then
  docker compose exec -T api python -c \
    'from app.services.db_ingest import db_status; s=db_status(); print(s); raise SystemExit(0 if s.get("active_version_id") is not None and not s.get("error") else "active data version is missing")'
else
  docker compose exec -T api python -c \
    'from app.config import DATA_MODE; from app.services.db_ingest import db_status,run_db_ingest; from app.services.ftp_ingest import run_ftp_then_db_ingest; r=run_ftp_then_db_ingest(force=False) if DATA_MODE == "ftp" else run_db_ingest(); s=db_status(); print(r); raise SystemExit(0 if r.get("ok") is True and s.get("active_version_id") is not None and not s.get("error") else "data ingest failed or active version is missing")'
fi

echo "==> assistant readiness"
docker compose up -d --build --force-recreate opencode
opencode_ok=0
for _ in $(seq 1 60); do
  status="$(docker inspect "$(docker compose ps -q opencode)" \
    --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
    2>/dev/null || true)"
  if [[ "$status" == "healthy" ]]; then
    opencode_ok=1
    break
  fi
  sleep 2
done
if [[ "$opencode_ok" -ne 1 ]]; then
  echo "OpenCode health FAILED"
  docker compose logs opencode --tail 200 || true
  exit 1
fi
docker compose exec -T api python -c \
  'import asyncio,json; from app.services.assistant import health; r=asyncio.run(health()); print(json.dumps(r, ensure_ascii=False)); raise SystemExit(0 if r.get("ok") is True else "assistant readiness failed")' \
  || {
    docker compose logs api --tail 200 || true
    docker compose logs opencode --tail 200 || true
    docker compose exec -T opencode sh -lc \
      'curl -fsS --max-time 5 "${SHOWCASE_VLLM_BASE_URL%/}/models" || true' \
      2>/dev/null || true
    exit 1
  }

# Прогрев только HTTP (не в процессе API) и только дефолтные фильтры:
# первый клик по фильтру всё равно считается заново — известное ограничение.
echo "==> warmup (default filters)"
for path in "/api/developer-projects" "/api/bdds" "/api/bdr" "/api/debit-credit"; do
  curl -fsS -o /dev/null -m 600 -w "warm ${path} %{http_code} %{time_total}s\n" \
    "http://127.0.0.1:3080${path}" || echo "warm ${path} FAILED"
done

echo "Deploy OK. Edge: http://127.0.0.1:3080"
docker logs cloudpub-webapp --tail 5 2>/dev/null || true
