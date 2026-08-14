#!/usr/bin/env bash
# Deploy Next+FastAPI prod stack for ai.conall.ru (edge :3081, no CloudPub).
# Run from repo root or webapp/. Uses COMPOSE_PROJECT_NAME=webapp-prod.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WEBAPP="$ROOT/webapp"
cd "$WEBAPP"

export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-webapp-prod}"
COMPOSE=(docker compose -p "$COMPOSE_PROJECT_NAME" -f docker-compose.yml -f docker-compose.prod.yml)

touch .env

_CI_XCA_ASK_SECRET="${XCA_ASK_SECRET:-}"
_CI_XCA_ASK_BASE_URL="${XCA_ASK_BASE_URL:-}"

set -a
# shellcheck disable=SC1091
source ./.env
set +a

if [[ -n "${_CI_XCA_ASK_SECRET}" ]]; then
  export XCA_ASK_SECRET="${_CI_XCA_ASK_SECRET}"
fi
if [[ -n "${_CI_XCA_ASK_BASE_URL}" ]]; then
  export XCA_ASK_BASE_URL="${_CI_XCA_ASK_BASE_URL}"
fi

mkdir -p data/web data/db data/report_cache data/jobs data/assistant_output

_upsert_env() {
  local key="$1" val="$2"
  [[ -n "$val" ]] || return 0
  local tmp
  tmp="$(mktemp)"
  if grep -qE "^${key}=" .env 2>/dev/null; then
    grep -vE "^${key}=" .env >"$tmp" || true
  else
    cp .env "$tmp"
  fi
  printf '%s=%s\n' "$key" "$val" >>"$tmp"
  mv "$tmp" .env
  export "${key}=${val}"
  echo "Configured ${key} in webapp/.env (len=${#val})"
}

auth_secret="${WEBAPP_AUTH_SECRET:-}"
if [[ ${#auth_secret} -lt 32 ]]; then
  auth_secret="$(
    grep -E '^WEBAPP_AUTH_SECRET=' .env 2>/dev/null \
      | tail -n 1 \
      | sed 's/^WEBAPP_AUTH_SECRET=//' \
      | tr -d '\r' \
      || true
  )"
fi
if [[ ${#auth_secret} -lt 32 ]]; then
  auth_secret="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  echo "Generated new WEBAPP_AUTH_SECRET (len=${#auth_secret})"
fi
_upsert_env WEBAPP_AUTH_SECRET "$auth_secret"
export WEBAPP_AUTH_SECRET="$auth_secret"

_upsert_env WEBAPP_DATA_MODE "ftp"
_upsert_env WEBAPP_CORS_ORIGINS "${WEBAPP_CORS_ORIGINS:-https://ai.conall.ru}"

if [[ -z "${SHOWCASE_VLLM_BASE_URL:-}" ]]; then
  SHOWCASE_VLLM_BASE_URL="http://host.docker.internal:8000/v1"
  _upsert_env SHOWCASE_VLLM_BASE_URL "$SHOWCASE_VLLM_BASE_URL"
fi
export SHOWCASE_AI_ENABLED=1
export NEXT_PUBLIC_AI_MODE=full
_upsert_env SHOWCASE_AI_ENABLED "1"
_upsert_env NEXT_PUBLIC_AI_MODE "full"

_upsert_env XCA_ASK_SECRET "${XCA_ASK_SECRET:-}"
_upsert_env XCA_ASK_BASE_URL "${XCA_ASK_BASE_URL:-}"

echo "==> prod compose up in $WEBAPP (project=$COMPOSE_PROJECT_NAME)"
"${COMPOSE[@]}" pull edge || true
"${COMPOSE[@]}" stop opencode >/dev/null 2>&1 || true
export XCA_ASK_SECRET="${XCA_ASK_SECRET:-}"
export XCA_ASK_BASE_URL="${XCA_ASK_BASE_URL:-}"
"${COMPOSE[@]}" up -d --build --remove-orphans --force-recreate db-init api web edge

echo "==> health :3081 (wait up to 90s)"
ok=0
for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:3081/api/health" >/tmp/webapp_prod_health.json 2>/dev/null; then
    echo "health ok (attempt $i): $(cat /tmp/webapp_prod_health.json)"
    ok=1
    break
  fi
  echo "health wait $i/30..."
  sleep 3
done
curl -fsS -o /dev/null -w "UI %{http_code}\n" "http://127.0.0.1:3081/" || true

if [[ "$ok" -ne 1 ]]; then
  echo "==> HEALTH FAILED — diagnostics"
  "${COMPOSE[@]}" ps -a || true
  "${COMPOSE[@]}" logs api --tail 200 || true
  exit 1
fi

echo "==> verify XCA Ask AI env inside api container"
"${COMPOSE[@]}" exec -T api python -c \
  'import os; s=(os.environ.get("XCA_ASK_SECRET") or "").strip(); b=(os.environ.get("XCA_ASK_BASE_URL") or "").strip(); print("xca_secret_len", len(s), "xca_base_len", len(b)); raise SystemExit(0 if s else "XCA_ASK_SECRET missing inside api container")'

echo "==> initialize users database"
"${COMPOSE[@]}" exec -T api python -c \
  'import sqlite3; from app.config import USERS_DB_PATH; from app.services.users_bridge import ensure_users_db; ensure_users_db(seed=True); c=sqlite3.connect(str(USERS_DB_PATH)); n=c.execute("SELECT COUNT(*) FROM users").fetchone()[0]; c.close(); raise SystemExit(0 if n > 0 else "users DB is empty; set BI_BOOTSTRAP_ADMIN_PASSWORD (>=16) for first deploy")'

echo "==> initialize active data version (FTP)"
if [[ "${WEBAPP_SKIP_SYNC:-0}" == "1" ]]; then
  "${COMPOSE[@]}" exec -T api python -c \
    'from app.services.db_ingest import db_status; s=db_status(); print(s); raise SystemExit(0 if s.get("active_version_id") is not None and not s.get("error") else "active data version is missing")'
else
  "${COMPOSE[@]}" exec -T api python -c \
    'from app.config import DATA_MODE; from app.services.db_ingest import db_status; from app.services.ftp_ingest import run_ftp_then_db_ingest; assert DATA_MODE == "ftp", DATA_MODE; r=run_ftp_then_db_ingest(force=False); s=db_status(); print(r); raise SystemExit(0 if r.get("ok") is True and s.get("active_version_id") is not None and not s.get("error") else "ftp ingest failed or active version missing")'
fi

echo "==> assistant readiness (in-app opencode)"
"${COMPOSE[@]}" up -d --build --force-recreate opencode
opencode_ok=0
for _ in $(seq 1 60); do
  cid="$("${COMPOSE[@]}" ps -q opencode 2>/dev/null || true)"
  status=""
  if [[ -n "$cid" ]]; then
    status="$(docker inspect "$cid" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>/dev/null || true)"
  fi
  if [[ "$status" == "healthy" ]]; then
    opencode_ok=1
    break
  fi
  sleep 2
done
if [[ "$opencode_ok" -ne 1 ]]; then
  echo "OpenCode health FAILED"
  "${COMPOSE[@]}" logs opencode --tail 200 || true
  exit 1
fi
"${COMPOSE[@]}" exec -T api python -c \
  'import asyncio,json; from app.services.assistant import health; r=asyncio.run(health()); print(json.dumps(r, ensure_ascii=False)); raise SystemExit(0 if r.get("ok") is True else "assistant readiness failed")' \
  || {
    "${COMPOSE[@]}" logs api --tail 200 || true
    "${COMPOSE[@]}" logs opencode --tail 200 || true
    exit 1
  }

# Sync prod DB → xca-opencode workspace (host OpenCode used by nginx /opencode)
if [[ -x "$WEBAPP/scripts/sync_prod_web_data_to_opencode.sh" ]]; then
  bash "$WEBAPP/scripts/sync_prod_web_data_to_opencode.sh" || echo "WARN: OpenCode DB sync failed (non-fatal)"
elif [[ -x "$ROOT/webapp/scripts/sync_prod_web_data_to_opencode.sh" ]]; then
  bash "$ROOT/webapp/scripts/sync_prod_web_data_to_opencode.sh" || echo "WARN: OpenCode DB sync failed (non-fatal)"
fi

echo "==> warmup (default filters)"
for path in "/api/developer-projects" "/api/bdds" "/api/bdr" "/api/debit-credit"; do
  curl -fsS -o /dev/null -m 600 -w "warm ${path} %{http_code} %{time_total}s\n" \
    "http://127.0.0.1:3081${path}" || echo "warm ${path} FAILED"
done

echo "Prod deploy OK. Edge: http://127.0.0.1:3081 (ai.conall.ru via nginx → 10.35.15.75:3081)"
