from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.config import USERS_DB_PATH
from app.services.users_bridge import ensure_users_db, import_auth, user_payload

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


@router.get("/status")
def auth_status():
    exists = USERS_DB_PATH.is_file()
    return {
        "users_db_exists": exists,
        "users_db_path": str(USERS_DB_PATH),
        "demo_fallback": not exists,
    }


@router.post("/login")
def login(body: LoginBody):
    auth = import_auth()
    ok, user = auth.authenticate(body.username.strip(), body.password)
    if not ok or not user:
        raise HTTPException(status_code=401, detail="Неверное имя пользователя или пароль")
    return {"ok": True, "user": user_payload(user, auth)}


@router.get("/me")
def me(x_auth_user: str | None = Header(default=None)):
    username = (x_auth_user or "").strip()
    if not username:
        raise HTTPException(status_code=401, detail="X-Auth-User required")
    auth = import_auth()
    user = auth.get_user_by_username(username)
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    return {"ok": True, "user": user_payload(user, auth)}


@router.post("/init-demo")
def init_demo_db():
    ensure_users_db(seed=True)
    return {"ok": True, "users_db_path": str(USERS_DB_PATH)}
