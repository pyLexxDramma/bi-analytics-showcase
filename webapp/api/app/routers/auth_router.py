from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.config import AUTH_TOKEN_TTL_SECONDS, USERS_DB_PATH
from app.services.auth_context import require_active_user
from app.services.auth_tokens import create_token
from app.services.users_bridge import import_auth, user_payload

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


@router.get("/status")
def auth_status():
    exists = USERS_DB_PATH.is_file()
    initialized = False
    if exists:
        try:
            with sqlite3.connect(str(USERS_DB_PATH)) as conn:
                initialized = bool(
                    conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                )
        except sqlite3.Error:
            initialized = False
    return {
        "users_db_exists": exists,
        "initialized": initialized,
    }


@router.post("/login")
def login(body: LoginBody):
    auth = import_auth()
    ok, user = auth.authenticate(body.username.strip(), body.password)
    if not ok or not user:
        raise HTTPException(status_code=401, detail="Неверное имя пользователя или пароль")
    return {
        "ok": True,
        "user": user_payload(user, auth),
        "token": create_token(user["username"]),
        "expires_in": AUTH_TOKEN_TTL_SECONDS,
    }


@router.get("/me")
def me(authorization: str | None = Header(default=None)):
    active_user = require_active_user(authorization)
    username = active_user["username"]
    auth = import_auth()
    return {"ok": True, "user": user_payload(active_user, auth)}
