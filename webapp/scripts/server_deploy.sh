#!/usr/bin/env bash
# Deploy Next+FastAPI webapp on VPS (run from repo root or webapp/).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WEBAPP="$ROOT/webapp"
cd "$WEBAPP"

mkdir -p data/web

echo "==> docker compose build/up in $WEBAPP"
docker compose pull edge || true
docker compose up -d --build --remove-orphans

echo "==> health"
sleep 3
curl -fsS "http://127.0.0.1:3080/api/health" || true
echo
curl -fsS -o /dev/null -w "UI %{http_code}\n" "http://127.0.0.1:3080/" || true
echo "Deploy OK. Edge: http://127.0.0.1:3080"
