#!/usr/bin/env bash
# Copy prod web_data.db into xca-opencode workspace on iivm.
set -euo pipefail

SRC="${PROD_WEB_DB:-$HOME/apps/bi-analytics-webapp-prod/webapp/data/db/web_data.db}"
DST="${OPENCODE_WEB_DB:-$HOME/opencode_web/opencode_only/workspace/web_data.db}"

if [[ ! -f "$SRC" ]]; then
  echo "WARN: prod DB missing: $SRC"
  exit 0
fi

mkdir -p "$(dirname "$DST")"
cp -f "$SRC" "${DST}.tmp"
mv -f "${DST}.tmp" "$DST"
echo "Synced $(du -h "$DST" | awk '{print $1}') → $DST"
