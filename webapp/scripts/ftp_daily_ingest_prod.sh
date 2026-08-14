#!/usr/bin/env bash
# Daily FTP → web/ → web_data.db for ai.conall.ru prod stack on iivm.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WEBAPP="$ROOT/webapp"
cd "$WEBAPP"

export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-webapp-prod}"
COMPOSE=(docker compose -p "$COMPOSE_PROJECT_NAME" -f docker-compose.yml -f docker-compose.prod.yml)

if [[ ! -f docker-compose.yml ]]; then
  echo "ERROR: docker-compose.yml not found in $WEBAPP"
  exit 1
fi

echo "==> FTP daily ingest PROD ($(date -Is)) project=$COMPOSE_PROJECT_NAME"
"${COMPOSE[@]}" exec -T api python -c \
  'from app.config import DATA_MODE; from app.services.db_ingest import db_status; from app.services.ftp_ingest import run_ftp_then_db_ingest; assert DATA_MODE == "ftp", f"WEBAPP_DATA_MODE={DATA_MODE!r}, expected ftp"; r=run_ftp_then_db_ingest(force=False); s=db_status(); print(r); print("db_status:", s); raise SystemExit(0 if r.get("ok") is True and s.get("active_version_id") is not None and not s.get("error") else "ftp daily ingest failed or active version missing")'

if [[ -x "$WEBAPP/scripts/sync_prod_web_data_to_opencode.sh" ]]; then
  bash "$WEBAPP/scripts/sync_prod_web_data_to_opencode.sh" || echo "WARN: OpenCode DB sync failed"
fi

echo "==> FTP daily ingest PROD OK"
