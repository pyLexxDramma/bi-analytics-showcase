#!/usr/bin/env bash
# Pick first model from vLLM /models and upsert SHOWCASE_VLLM_MODEL in webapp/.env.
# Fixes deploy when .env still references a retired model id.
set -euo pipefail

_sync_vllm_model() {
  local base="${SHOWCASE_VLLM_BASE_URL:-}"
  [[ -n "$base" ]] || return 0
  local picked=""
  picked="$(
    curl -fsS --max-time 20 "${base%/}/models" 2>/dev/null | python3 -c "
import json, sys
try:
    payload = json.load(sys.stdin)
    rows = payload.get('data') if isinstance(payload, dict) else payload
    for row in rows or []:
        if isinstance(row, dict):
            mid = str(row.get('id') or row.get('name') or '').strip()
            if mid:
                print(mid)
                break
except Exception:
    pass
" 2>/dev/null || true
  )"
  if [[ -z "$picked" ]]; then
    echo "WARN: could not read vLLM /models from ${base}"
    return 0
  fi
  if [[ "${SHOWCASE_VLLM_MODEL:-}" == "$picked" ]]; then
    echo "SHOWCASE_VLLM_MODEL already $picked"
    return 0
  fi
  _upsert_env SHOWCASE_VLLM_MODEL "$picked"
  export SHOWCASE_VLLM_MODEL="$picked"
  echo "Synced SHOWCASE_VLLM_MODEL=$picked from vLLM"
}
