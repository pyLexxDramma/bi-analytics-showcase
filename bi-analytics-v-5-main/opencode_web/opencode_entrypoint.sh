#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${SHOWCASE_VLLM_BASE_URL:-}" ]]; then
  echo "SHOWCASE_VLLM_BASE_URL is required"
  exit 1
fi

for attempt in $(seq 1 30); do
  [[ -r /workspace/data/web_data.db ]] && break
  echo "waiting for /workspace/data/web_data.db ($attempt/30)"
  sleep 2
done
if [[ ! -r /workspace/data/web_data.db ]]; then
  echo "database is still unavailable; OpenCode will start with degraded readiness"
fi

vllm_headers=()
if [[ -n "${SHOWCASE_VLLM_API_KEY:-}" ]]; then
  vllm_headers=(-H "Authorization: Bearer ${SHOWCASE_VLLM_API_KEY}")
fi
vllm_ready=0
for attempt in $(seq 1 15); do
  if curl -fsS --max-time 5 "${vllm_headers[@]}" \
    "${SHOWCASE_VLLM_BASE_URL%/}/models" >/tmp/vllm-models.json; then
    vllm_ready=1
    break
  fi
  echo "waiting for vLLM models endpoint ($attempt/15)"
  sleep 2
done
if [[ "$vllm_ready" -ne 1 ]]; then
  echo "vLLM models endpoint is unavailable; OpenCode will start with degraded readiness"
fi

python - <<'PY'
import json
import os
from pathlib import Path

path = Path("/workspace/opencode.json")
config = json.loads(path.read_text(encoding="utf-8"))
model_name = os.environ.get("SHOWCASE_VLLM_MODEL", "Qwen3.5-35B-A3B-GPTQ-Int4")
model_id = os.environ.get("SHOWCASE_VLLM_MODEL_ID", model_name)
model_ref = f"vllm/{model_name}"
provider = config["provider"]["vllm"]
provider["options"]["baseURL"] = os.environ["SHOWCASE_VLLM_BASE_URL"].rstrip("/")
api_key = os.environ.get("SHOWCASE_VLLM_API_KEY", "").strip()
if api_key:
    provider["options"]["apiKey"] = api_key
provider["models"] = {
    model_name: {
        "id": model_id,
        "tool_call": True,
        "reasoning": False,
        "limit": {
            "context": int(os.environ.get("SHOWCASE_VLLM_CONTEXT", "32768")),
            "output": int(os.environ.get("SHOWCASE_VLLM_OUTPUT", "8192")),
        },
        "options": {"chat_template_kwargs": {"enable_thinking": False}},
    }
}
config["model"] = model_ref
for name in ("title", "compaction", "xca"):
    if name in config.get("agent", {}):
        config["agent"][name]["model"] = model_ref
path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
PY

exec opencode serve --hostname "${OPENCODE_HOST:-0.0.0.0}" --port "${OPENCODE_PORT:-4096}"
