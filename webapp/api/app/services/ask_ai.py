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
LINK_TTL_SECONDS = 600

# Имена в UI/ACL дашборда → имена в витрине XCA (см. ASK_AI_LINK_CONTRACT.md §5).
PROJECT_NAME_ALIASES_FOR_XCA: dict[str, str] = {
    "Дмитровский": "Дмитровский-1",
    "Дмитровский1": "Дмитровский-1",
}


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


def map_project_name_for_xca(name: str) -> str:
    raw = (name or "").strip()
    if not raw:
        return raw
    return PROJECT_NAME_ALIASES_FOR_XCA.get(raw, raw)


def format_projects_param(names: list[str] | None) -> str:
    """`*` = все; иначе имена через `|` (как в дашборде), с алиасами под XCA."""
    if names is None:
        return "*"
    mapped = [map_project_name_for_xca(n) for n in names if str(n).strip()]
    # Стабильный порядок для подписи / сверки на стороне XCA.
    uniq = sorted({m for m in mapped if m})
    return "|".join(uniq) if uniq else "*"


def format_reports_param(screen_ids: list[str] | None) -> str:
    """`*` = все экраны; иначе `screen_*` через запятую."""
    if screen_ids is None:
        return "*"
    ids = [str(s).strip() for s in screen_ids if str(s).strip()]
    return ",".join(ids) if ids else "*"


def user_projects_param(user: dict[str, Any]) -> str:
    from app.services.project_scope import allowed_projects_for_user

    return format_projects_param(allowed_projects_for_user(user))


def user_reports_param(user: dict[str, Any]) -> str:
    auth = import_auth()
    role = str(user.get("role") or "").strip().lower()
    if role in ("superadmin", "admin"):
        return "*"
    reports: list[str] = []
    for nav_id, meta in SCREENS.items():
        if role_can_open_screen(auth, role, nav_id):
            reports.append(str(meta["report"]))
    return format_reports_param(reports)


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
    exp: int | None = None,
    free: bool = False,
    projects: str | None = None,
    reports: str | None = None,
) -> dict[str, Any]:
    if free or (report or "").strip() == "free" or (
        not (nav_id or "").strip() and not (report or "").strip()
    ):
        report_id = "free"
        screen = None
        # Свободный чат: вопрос пишет пользователь, ctx не обязателен.
        question = _clip((q or "").strip(), MAX_Q)
        context = _clip((ctx or "").strip(), MAX_CTX)
    else:
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
    if free and not source:
        source = "sidebar"
    uid = f"u_{user.get('id')}" if user.get("id") is not None else f"u_{user.get('username')}"
    role = str(user.get("role") or "").strip().lower() or "analyst"
    stamp = int(ts if ts is not None else time.time())
    exp_ts = int(exp) if exp is not None else stamp + LINK_TTL_SECONDS

    projects_s = (projects if projects is not None else user_projects_param(user)).strip()
    reports_s = (reports if reports is not None else user_reports_param(user)).strip()

    params: dict[str, str] = {
        "v": "1",
        "report": report_id,
        "uid": uid,
        "role": role,
        "ts": str(stamp),
        "exp": str(exp_ts),
        "projects": projects_s or "*",
        "reports": reports_s or "*",
    }
    if question:
        params["q"] = question
    if context:
        params["ctx"] = context
    if project and str(project).strip():
        # Подсказка «на что смотрел» — тоже через алиас XCA.
        first = str(project).strip().split("|")[0].strip()
        if first:
            params["project"] = map_project_name_for_xca(first)
    if period and str(period).strip():
        params["period"] = str(period).strip()
    filters_s = _filters_json(filters)
    if filters_s:
        params["filters"] = filters_s
    if source:
        params["src"] = source

    # Укладываемся в лимит URL: режем ctx, не report/фильтры/ACL.
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
    if len(url) > MAX_URL and "q" in params and len(params["q"]) > 40:
        params["q"] = _clip(params["q"], max(40, len(params["q"]) - 40))
        params["sig"] = sign_params(params)
        url = f"{_base_url()}?{urlencode(params)}"
    if len(url) > MAX_URL:
        raise ValueError("Ссылка Ask AI длиннее 1500 символов даже после усечения ctx/filters")

    return {
        "url": url,
        "report": report_id,
        "nav_id": nav_id,
        "ts": stamp,
        "exp": exp_ts,
        "expires_in": max(0, exp_ts - stamp),
        "projects": projects_s or "*",
        "reports": reports_s or "*",
    }


def role_can_open_screen(auth: Any, role: str, nav_id: str) -> bool:
    screen = get_screen(nav_id)
    if not screen:
        return False
    r = str(role or "").strip().lower()
    if r in ("superadmin", "admin"):
        return True
    if hasattr(auth, "role_can_open_report"):
        return bool(auth.role_can_open_report(r, nav_id))
    names = list(screen.get("auth_names") or [])
    if not names:
        return bool(auth.has_report_access(r)) if hasattr(auth, "has_report_access") else True
    return all(auth.user_can_open_report(r, name) for name in names)


def build_roles_catalog() -> dict[str, Any]:
    auth = import_auth()
    roles_out: list[dict[str, Any]] = []
    role_rows = []
    if hasattr(auth, "list_roles"):
        try:
            role_rows = list(auth.list_roles())
        except Exception:
            role_rows = []
    if role_rows:
        iterable = [(r["code"], r.get("label") or r["code"]) for r in role_rows]
    else:
        iterable = [
            (code, auth.get_user_role_display(code) if hasattr(auth, "get_user_role_display") else code)
            for code in (list(getattr(auth, "ROLES", {}).keys()) or [
                "superadmin",
                "admin",
                "analyst",
                "rp",
                "financier",
                "gip",
                "manager",
            ])
        ]
    for code, title in iterable:
        reports: list[str] = []
        for nav_id, meta in SCREENS.items():
            if role_can_open_screen(auth, code, nav_id):
                reports.append(str(meta["report"]))
        roles_out.append(
            {
                "code": code,
                "title": title,
                "reports": reports,
                "projects": (
                    (
                        list(auth.get_role_projects(code))
                        if auth.get_role_projects(code) is not None
                        else ["*"]
                    )
                    if hasattr(auth, "get_role_projects")
                    else ["*"]
                ),
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
