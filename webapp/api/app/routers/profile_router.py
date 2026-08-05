from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.services.auth_context import require_active_user
from app.services.users_bridge import import_auth, import_logger

router = APIRouter(prefix="/api/profile", tags=["profile"])


def _require_user(authorization: str | None) -> str:
    return str(require_active_user(authorization)["username"])


class PasswordBody(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6)


class EmailBody(BaseModel):
    new_email: str | None = None


@router.post("/password")
def change_password(
    body: PasswordBody,
    authorization: str | None = Header(default=None),
):
    username = _require_user(authorization)
    auth = import_auth()
    ok, message = auth.change_password(username, body.old_password, body.new_password)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    logger = import_logger()
    logger.log_action(username, "change_password", "Пароль успешно изменен")
    return {"ok": True, "message": message}


@router.post("/email")
def change_email(
    body: EmailBody,
    authorization: str | None = Header(default=None),
):
    username = _require_user(authorization)
    email_value = (body.new_email or "").strip() or None
    if email_value and "@" not in email_value:
        raise HTTPException(status_code=400, detail="Введите корректный email адрес")
    auth = import_auth()
    ok, message = auth.update_user_email(username, email_value)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    logger = import_logger()
    logger.log_action(
        username,
        "change_email",
        f"Email изменен на: {email_value or 'удален'}",
    )
    user = auth.get_user_by_username(username)
    return {
        "ok": True,
        "message": message,
        "email": user.get("email") if user else email_value,
    }
