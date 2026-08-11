from __future__ import annotations

from fastapi import HTTPException

from app.services.auth_tokens import AuthTokenError, bearer_token, verify_token
from app.services.users_bridge import import_auth


def require_active_user(authorization: str | None) -> dict:
    try:
        username = str(verify_token(bearer_token(authorization))["sub"])
    except AuthTokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    auth = import_auth()
    user = auth.get_user_by_username(username)
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    return user


def optional_active_user(authorization: str | None) -> dict | None:
    """Bearer опционален: битый/просроченный токен = аноним, не 401 на весь отчёт."""
    if not (authorization or "").strip():
        return None
    try:
        return require_active_user(authorization)
    except HTTPException as exc:
        if exc.status_code == 401:
            return None
        raise


def require_admin_user(authorization: str | None) -> dict:
    user = require_active_user(authorization)
    auth = import_auth()
    if not auth.has_admin_access(user.get("role")):
        raise HTTPException(status_code=403, detail="Доступ только для администраторов")
    return user


def require_report_user(authorization: str | None) -> dict:
    user = require_active_user(authorization)
    auth = import_auth()
    if not auth.has_report_access(user.get("role")):
        raise HTTPException(status_code=403, detail="Нет доступа к отчётам")
    return user


def require_finance_editor(authorization: str | None) -> dict:
    user = require_active_user(authorization)
    auth = import_auth()
    if not auth.user_can_edit_finance_tables(user.get("role")):
        raise HTTPException(status_code=403, detail="Нет прав на редактирование БДДС")
    return user
