#!/usr/bin/env bash
# Deploy Next+FastAPI webapp on VPS (run from repo root or webapp/).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WEBAPP="$ROOT/webapp"
cd "$WEBAPP"

mkdir -p data/web

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
echo "Deploy OK. Edge: http://127.0.0.1:3080"
docker logs cloudpub-webapp --tail 5 2>/dev/null || true
