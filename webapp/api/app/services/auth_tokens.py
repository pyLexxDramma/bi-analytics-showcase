from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from app.config import AUTH_SECRET, AUTH_TOKEN_TTL_SECONDS


class AuthTokenError(ValueError):
    pass


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_token(
    username: str,
    *,
    ttl_seconds: int = AUTH_TOKEN_TTL_SECONDS,
    now: int | None = None,
) -> str:
    issued_at = int(time.time() if now is None else now)
    payload = {
        "sub": username,
        "iat": issued_at,
        "exp": issued_at + ttl_seconds,
    }
    encoded = _encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = hmac.new(
        AUTH_SECRET.encode("utf-8"),
        encoded.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{encoded}.{_encode(signature)}"


def verify_token(token: str, *, now: int | None = None) -> dict[str, Any]:
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected_signature = hmac.new(
            AUTH_SECRET.encode("utf-8"),
            encoded.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(expected_signature, _decode(supplied_signature)):
            raise AuthTokenError("Недействительная подпись токена")
        payload = json.loads(_decode(encoded))
    except AuthTokenError:
        raise
    except Exception as exc:
        raise AuthTokenError("Некорректный токен") from exc
    current_time = int(time.time() if now is None else now)
    username = str(payload.get("sub") or "").strip()
    expires_at = int(payload.get("exp") or 0)
    if not username:
        raise AuthTokenError("Токен не содержит пользователя")
    if expires_at <= current_time:
        raise AuthTokenError("Срок действия токена истёк")
    return payload


def bearer_token(authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthTokenError("Bearer token required")
    return token.strip()
