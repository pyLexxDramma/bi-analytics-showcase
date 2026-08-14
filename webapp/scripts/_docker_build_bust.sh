#!/usr/bin/env bash
# Stamp build ids + rebuild api/web so Docker BuildKit cannot serve a stale Next/API image.
# Usage: source from server_deploy*.sh after ROOT/WEBAPP/GIT_SHA are set.
# Env:
#   WEBAPP_DOCKER_NO_CACHE=1  — full --no-cache (default on prod)
#   COMPOSE=(docker compose ...)  — optional; default: docker compose

_webapp_stamp_and_build_api_web() {
  local compose_cmd=()
  if declare -p COMPOSE 2>/dev/null | grep -q '^declare -a'; then
    compose_cmd=("${COMPOSE[@]}")
  else
    compose_cmd=(docker compose)
  fi

  local sha="${GIT_SHA:-unknown}"
  local stamp
  stamp="$(date -u +%Y%m%dT%H%M%SZ)+${sha}"

  printf '%s\n' "$stamp" >"$WEBAPP/web/.build-id"
  printf '%s\n' "$stamp" >"$WEBAPP/api/.build-id"
  echo "Build stamp: $stamp"

  local build_args=(--build-arg "GIT_SHA=$sha")
  if [[ "${WEBAPP_DOCKER_NO_CACHE:-0}" == "1" ]]; then
    echo "Docker build: --no-cache api web (sha=${sha:0:7})"
    "${compose_cmd[@]}" build --no-cache "${build_args[@]}" api web
  else
    echo "Docker build: api web (sha=${sha:0:7}, stamp bust)"
    "${compose_cmd[@]}" build "${build_args[@]}" api web
  fi
}

_webapp_verify_image_sha() {
  local compose_cmd=()
  if declare -p COMPOSE 2>/dev/null | grep -q '^declare -a'; then
    compose_cmd=("${COMPOSE[@]}")
  else
    compose_cmd=(docker compose)
  fi
  local expected="${GIT_SHA:-unknown}"
  local api_sha web_sha
  api_sha="$("${compose_cmd[@]}" exec -T api printenv WEBAPP_GIT_SHA 2>/dev/null || true)"
  web_sha="$("${compose_cmd[@]}" exec -T web printenv NEXT_PUBLIC_GIT_SHA 2>/dev/null || true)"
  api_sha="$(printf '%s' "$api_sha" | tr -d '\r\n')"
  web_sha="$(printf '%s' "$web_sha" | tr -d '\r\n')"
  echo "Verify image SHA: expected=${expected:0:7} api=${api_sha:0:7} web=${web_sha:0:7}"
  if [[ -z "$api_sha" || "$api_sha" != "$expected" ]]; then
    echo "ERROR: api WEBAPP_GIT_SHA mismatch (got='$api_sha' expected='$expected')"
    return 1
  fi
  if [[ -z "$web_sha" || "$web_sha" != "$expected" ]]; then
    echo "ERROR: web NEXT_PUBLIC_GIT_SHA mismatch (got='$web_sha' expected='$expected')"
    return 1
  fi
}
