from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.config import ADMIN_SYNC_TOKEN
from app.services.ask_ai import (
    AskAiConfigError,
    build_ask_url,
    build_roles_catalog,
    role_can_open_screen,
)
from app.services.ask_ai_reports import NAV_BY_REPORT, get_screen, resolve_report
from app.services.auth_context import require_admin_user, require_report_user
from app.services.users_bridge import import_auth

router = APIRouter(prefix="/api/ask-ai", tags=["ask-ai"])


class AskAiLinkBody(BaseModel):
    nav_id: str | None = Field(default=None, max_length=64)
    report: str | None = Field(default=None, max_length=128)
    q: str | None = Field(default=None, max_length=200)
    ctx: str | None = Field(default=None, max_length=800)
    project: str | None = Field(default=None, max_length=200)
    period: str | None = Field(default=None, max_length=64)
    filters: dict[str, Any] | str | None = None
    src: str | None = Field(default=None, max_length=200)


def _assert_user_may_ask(user: dict, nav_id: str | None, report: str | None) -> str:
    """RBAC: ссылку подписываем только на экраны, доступные роли пользователя."""
    report_id, _screen = resolve_report(nav_id, report)
    nav = (nav_id or "").strip() or NAV_BY_REPORT.get(report_id)
    if not nav or not get_screen(nav):
        raise HTTPException(
            status_code=400,
            detail="Неизвестный экран / report для Ask AI",
        )
    auth = import_auth()
    if not role_can_open_screen(auth, str(user.get("role") or ""), nav):
        raise HTTPException(
            status_code=403,
            detail="У вашей роли нет доступа к этому отчёту для ИИ",
        )
    return nav


def _require_roles_catalog_access(
    authorization: str | None,
    x_admin_token: str | None,
) -> None:
    """Admin JWT или X-Admin-Token (для машинного доступа XCA)."""
    token = (x_admin_token or "").strip()
    if ADMIN_SYNC_TOKEN and token and token == ADMIN_SYNC_TOKEN:
        return
    require_admin_user(authorization)

@router.post("/link")
@router.post("/link/", include_in_schema=False)
def create_ask_ai_link(
    body: AskAiLinkBody,
    authorization: str | None = Header(default=None),
):
    user = require_report_user(authorization)
    if not (body.nav_id or body.report):
        raise HTTPException(status_code=400, detail="Нужен nav_id или report")
    nav = _assert_user_may_ask(user, body.nav_id, body.report)
    from app.services.project_scope import clamp_project_pipe, allowed_projects_for_user

    project = body.project
    allowed = allowed_projects_for_user(user)
    if allowed is not None:
        if project:
            project = clamp_project_pipe(user, project)
            if project == "__none__":
                raise HTTPException(
                    status_code=403,
                    detail="Нет доступа к выбранному проекту для ИИ",
                )
        elif len(allowed) == 1:
            project = allowed[0]
    try:
        result = build_ask_url(
            user=user,
            nav_id=nav,
            report=body.report,
            q=body.q,
            ctx=body.ctx,
            project=project,
            period=body.period,
            filters=body.filters,
            src=body.src,
        )
    except AskAiConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **result}


# Алиас как в гайде DASHBOARD_ASK_AI_INTEGRATION.md
legacy_router = APIRouter(tags=["ask-ai"])


@legacy_router.post("/api/ask-ai-link")
def create_ask_ai_link_legacy(
    body: AskAiLinkBody,
    authorization: str | None = Header(default=None),
):
    return create_ask_ai_link(body, authorization)


@router.get("/roles-catalog")
def roles_catalog(
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    """Справочник ролей для XCA. Ключ списка экранов в каждой роли — `reports` (screen_*)."""
    _require_roles_catalog_access(authorization, x_admin_token)
    return build_roles_catalog()


@router.get("/screens")
def list_screens(authorization: str | None = Header(default=None)):
    require_report_user(authorization)
    catalog = build_roles_catalog()
    return {"screens": catalog["screens"]}


@router.get("/my-screens")
def my_screens(authorization: str | None = Header(default=None)):
    """
    Полный scope текущего пользователя для ИИ:
    allowed_reports (screen_*) + allowed_projects (null = все).
    """
    from datetime import datetime, timezone

    from app.services.ask_ai_reports import SCREENS
    from app.services.project_scope import allowed_projects_for_user

    user = require_report_user(authorization)
    auth = import_auth()
    role = str(user.get("role") or "")
    nav_ids: list[str] = []
    reports: list[str] = []
    for nav_id, meta in SCREENS.items():
        if role_can_open_screen(auth, role, nav_id):
            nav_ids.append(nav_id)
            reports.append(str(meta["report"]))
    uid = (
        f"u_{user.get('id')}"
        if user.get("id") is not None
        else f"u_{user.get('username')}"
    )
    return {
        "ok": True,
        "uid": uid,
        "role": role,
        "allowed_nav_ids": nav_ids,
        "allowed_reports": reports,
        "allowed_projects": allowed_projects_for_user(user),
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
