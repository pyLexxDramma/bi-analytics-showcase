"""Подпись ссылок XCA Ask AI и справочник ролей."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

from app.config import XCA_ASK_BASE_URL, XCA_ASK_SECRET
from app.services.ask_ai_reports import SCREENS, get_screen, resolve_report
from app.services.users_bridge import import_auth

MAX_Q = 120
MAX_CTX = 600
MAX_FILTERS = 400
MAX_URL = 1500


class AskAiConfigError(RuntimeError):
    pass


def _secret_bytes() -> bytes:
    secret = (XCA_ASK_SECRET or "").strip()
    if not secret:
        raise AskAiConfigError("XCA_ASK_SECRET не задан")
    return secret.encode("utf-8")


def _base_url() -> str:
    base = (XCA_ASK_BASE_URL or "").strip().rstrip("/")
    if not base:
        raise AskAiConfigError("XCA_ASK_BASE_URL не задан")
    if base.endswith("/ask"):
        return base
    return f"{base}/ask"


def sign_params(params: dict[str, str], secret: bytes | None = None) -> str:
    key = secret if secret is not None else _secret_bytes()
    canonical = "&".join(
        f"{k}={params[k]}" for k in sorted(params) if k != "sig" and params[k] is not None
    )
    digest = hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _clip(value: str, limit: int) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _filters_json(filters: dict[str, Any] | str | None) -> str | None:
    if filters is None:
        return None
    if isinstance(filters, str):
        raw = filters.strip()
        return _clip(raw, MAX_FILTERS) or None
    try:
        raw = json.dumps(filters, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return None
    return _clip(raw, MAX_FILTERS) or None


def build_ask_url(
    *,
    user: dict[str, Any],
    nav_id: str | None = None,
    report: str | None = None,
    q: str | None = None,
    ctx: str | None = None,
    project: str | None = None,
    period: str | None = None,
    filters: dict[str, Any] | str | None = None,
    src: str | None = None,
    ts: int | None = None,
) -> dict[str, Any]:
    report_id, screen = resolve_report(nav_id, report)
    title = (screen or {}).get("title") or report_id
    question = _clip(
        (q or "").strip() or f"Объясни дашборд «{title}»",
        MAX_Q,
    )
    if not question:
        question = "Объясни дашборд"

    default_ctx_parts = []
    if screen:
        default_ctx_parts.append(f"Отчёт «{screen['title']}».")
        hint = screen.get("ctx_hint")
        if hint:
            default_ctx_parts.append(str(hint))
    context = _clip((ctx or "").strip() or " ".join(default_ctx_parts), MAX_CTX)

    source = (src or "").strip() or (str(screen["src"]) if screen else "") or (nav_id or "")
    uid = f"u_{user.get('id')}" if user.get("id") is not None else f"u_{user.get('username')}"
    role = str(user.get("role") or "").strip().lower() or "analyst"
    stamp = int(ts if ts is not None else time.time())

    params: dict[str, str] = {
        "v": "1",
        "report": report_id,
        "q": question,
        "uid": uid,
        "role": role,
        "ts": str(stamp),
    }
    if context:
        params["ctx"] = context
    if project and str(project).strip():
        params["project"] = str(project).strip()
    if period and str(period).strip():
        params["period"] = str(period).strip()
    filters_s = _filters_json(filters)
    if filters_s:
        params["filters"] = filters_s
    if source:
        params["src"] = source

    # Укладываемся в лимит URL: режем ctx, не report/фильтры.
    params["sig"] = sign_params(params)
    url = f"{_base_url()}?{urlencode(params)}"
    while len(url) > MAX_URL and "ctx" in params and len(params["ctx"]) > 40:
        params["ctx"] = _clip(params["ctx"], max(40, len(params["ctx"]) - 80))
        params["sig"] = sign_params(params)
        url = f"{_base_url()}?{urlencode(params)}"
    if len(url) > MAX_URL and "filters" in params:
        params["filters"] = _clip(params["filters"], max(40, len(params["filters"]) // 2))
        params["sig"] = sign_params(params)
        url = f"{_base_url()}?{urlencode(params)}"
    if len(url) > MAX_URL:
        raise ValueError("Ссылка Ask AI длиннее 1500 символов даже после усечения ctx/filters")

    return {
        "url": url,
        "report": report_id,
        "nav_id": nav_id or (None),
        "ts": stamp,
        "expires_in": 600,
    }


def role_can_open_screen(auth: Any, role: str, nav_id: str) -> bool:
    screen = get_screen(nav_id)
    if not screen:
        return False
    r = str(role or "").strip().lower()
    if r in ("superadmin", "admin"):
        return True
    names = list(screen.get("auth_names") or [])
    if not names:
        return bool(auth.has_report_access(r)) if hasattr(auth, "has_report_access") else True
    return any(auth.user_can_open_report(r, name) for name in names)


def build_roles_catalog() -> dict[str, Any]:
    auth = import_auth()
    roles_out: list[dict[str, Any]] = []
    role_codes = list(getattr(auth, "ROLES", {}).keys()) or [
        "superadmin",
        "admin",
        "analyst",
        "rp",
        "financier",
        "gip",
        "manager",
    ]
    for code in role_codes:
        title = auth.get_user_role_display(code) if hasattr(auth, "get_user_role_display") else code
        reports: list[str] = []
        for nav_id, meta in SCREENS.items():
            if role_can_open_screen(auth, code, nav_id):
                reports.append(str(meta["report"]))
        roles_out.append(
            {
                "code": code,
                "title": title,
                "reports": reports,
                "projects": ["*"],
            }
        )
    return {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "roles": roles_out,
        "screens": [
            {
                "nav_id": nav_id,
                "report": meta["report"],
                "title": meta["title"],
                "src": meta["src"],
            }
            for nav_id, meta in SCREENS.items()
        ],
    }
