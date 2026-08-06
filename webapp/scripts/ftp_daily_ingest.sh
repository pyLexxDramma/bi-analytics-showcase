#!/usr/bin/env bash
# Daily FTP → web/ → web_data.db on showcase VPS (no full redeploy).
# Run from repo root or webapp/. Requires docker compose api up and WEBAPP_DATA_MODE=ftp.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WEBAPP="$ROOT/webapp"
cd "$WEBAPP"

if [[ ! -f docker-compose.yml ]]; then
  echo "ERROR: docker-compose.yml not found in $WEBAPP"
  exit 1
fi

echo "==> FTP daily ingest ($(date -Is))"
docker compose exec -T api python -c \
  'from app.config import DATA_MODE; from app.services.db_ingest import db_status; from app.services.ftp_ingest import run_ftp_then_db_ingest; assert DATA_MODE == "ftp", f"WEBAPP_DATA_MODE={DATA_MODE!r}, expected ftp"; r=run_ftp_then_db_ingest(force=False); s=db_status(); print(r); print("db_status:", s); raise SystemExit(0 if r.get("ok") is True and s.get("active_version_id") is not None and not s.get("error") else "ftp daily ingest failed or active version missing")'

echo "==> FTP daily ingest OK"
