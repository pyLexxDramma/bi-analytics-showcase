from __future__ import annotations

import json
import re
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from app.config import (
    ASSISTANT_PENDING_TIMEOUT_SECONDS,
    ASSISTANT_DB_PATH,
    ASSISTANT_OUTPUT_DIR,
    OPENCODE_BASE_URL,
    OPENCODE_TIMEOUT_SECONDS,
    OPENCODE_WORKSPACE,
    VLLM_API_KEY,
    VLLM_BASE_URL,
    VLLM_MODEL,
)
from app.services.db_ingest import db_status

_IMAGE_RE = re.compile(
    r"(?:file://)?/workspace/analytics/output/([^\s\]\)\"']+\.(?:png|jpg|jpeg|webp|gif))",
    re.IGNORECASE,
)
_MARKDOWN_IMAGE_RE = re.compile(
    r"!?\[([^\]]*)\]\((?:file://)?/workspace/analytics/output/"
    r"[^\s\]\)\"']+\.(?:png|jpg|jpeg|webp|gif)\)",
    re.IGNORECASE,
)
_IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


class AssistantError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    ASSISTANT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(ASSISTANT_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS assistant_sessions (
            id TEXT PRIMARY KEY,
            owner TEXT NOT NULL,
            server_session_id TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            pending_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(assistant_sessions)").fetchall()
    }
    if "error_text" not in columns:
        conn.execute("ALTER TABLE assistant_sessions ADD COLUMN error_text TEXT")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS assistant_assets (
            id TEXT PRIMARY KEY,
            owner TEXT NOT NULL,
            session_id TEXT NOT NULL,
            origin_path TEXT NOT NULL,
            source_path TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(owner, session_id, origin_path),
            FOREIGN KEY(session_id) REFERENCES assistant_sessions(id) ON DELETE CASCADE
        )
        """
    )
    asset_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(assistant_assets)").fetchall()
    }
    if "origin_path" not in asset_columns:
        conn.execute("ALTER TABLE assistant_assets ADD COLUMN origin_path TEXT")
        conn.execute(
            "UPDATE assistant_assets SET origin_path = source_path "
            "WHERE origin_path IS NULL"
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_assistant_owner_updated "
        "ON assistant_sessions(owner, updated_at DESC)"
    )
    conn.commit()
    return conn


def _public_session(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "busy": bool(row["pending_json"]),
        "error": row["error_text"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_sessions(owner: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM assistant_sessions WHERE owner = ? ORDER BY updated_at DESC",
            (owner,),
        ).fetchall()
    return [_public_session(row) for row in rows]


def _get_session(owner: str, session_id: str) -> sqlite3.Row:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM assistant_sessions WHERE id = ? AND owner = ?",
            (session_id, owner),
        ).fetchone()
    if row is None:
        raise AssistantError("Сессия не найдена", 404)
    return row


async def _request(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> Any:
    try:
        async with httpx.AsyncClient(
            base_url=OPENCODE_BASE_URL,
            timeout=timeout or OPENCODE_TIMEOUT_SECONDS,
        ) as client:
            response = await client.request(method, path, json=payload)
    except httpx.HTTPError as exc:
        raise AssistantError(f"OpenCode недоступен: {exc}") from exc
    if response.status_code >= 400:
        detail = response.text.strip()
        raise AssistantError(
            f"OpenCode вернул HTTP {response.status_code}: {detail[:300]}",
            502,
        )
    if response.status_code == 204 or not response.content:
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise AssistantError("OpenCode вернул некорректный ответ") from exc


def _database_health() -> dict[str, Any]:
    database_status = db_status()
    active_version_id = database_status.get("active_version_id")
    return {
        "ok": bool(
            database_status.get("exists")
            and active_version_id is not None
            and not database_status.get("error")
        ),
        "active_version_id": active_version_id,
    }


async def health() -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "opencode": {"ok": False},
        "vllm": {"ok": False},
        "database": _database_health(),
    }
    try:
        payload = await _request("GET", "/global/health", timeout=5)
        result["opencode"] = {"ok": True, "details": payload}
    except AssistantError as exc:
        result["opencode"] = {"ok": False, "error": str(exc)}
    if not VLLM_BASE_URL:
        result["vllm"] = {"ok": False, "error": "SHOWCASE_VLLM_BASE_URL не задан"}
    else:
        headers = {"Authorization": f"Bearer {VLLM_API_KEY}"} if VLLM_API_KEY else {}
        try:
            async with httpx.AsyncClient(timeout=5, headers=headers) as client:
                response = await client.get(f"{VLLM_BASE_URL}/models")
                response.raise_for_status()
                payload = response.json()
            models = payload.get("data") if isinstance(payload, dict) else payload
            model_ids = [
                str(item.get("id") or item.get("name") or "")
                for item in (models or [])
                if isinstance(item, dict)
            ]
            expected = VLLM_MODEL.strip()
            model_ok = not expected or any(
                expected == model_id
                or expected in model_id
                or model_id.endswith(expected)
                for model_id in model_ids
            )
            result["vllm"] = {
                "ok": model_ok,
                "model": expected,
                "available_models": model_ids,
                **({} if model_ok else {"error": "Настроенная модель не найдена"}),
            }
        except (httpx.HTTPError, ValueError) as exc:
            result["vllm"] = {"ok": False, "error": str(exc)}
    result["ok"] = bool(
        result["opencode"]["ok"]
        and result["vllm"]["ok"]
        and result["database"]["ok"]
    )
    return result


async def create_session(owner: str, title: str = "Новый чат") -> dict[str, Any]:
    payload = await _request(
        "POST",
        f"/session?directory={quote(OPENCODE_WORKSPACE, safe='')}",
        payload={"title": title},
    )
    server_id = str((payload or {}).get("id") or "").strip()
    if not server_id:
        raise AssistantError("OpenCode не вернул идентификатор сессии")
    local_id = str(uuid.uuid4())
    timestamp = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO assistant_sessions
                (id, owner, server_session_id, title, pending_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, NULL, ?, ?)
            """,
            (local_id, owner, server_id, title[:80], timestamp, timestamp),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM assistant_sessions WHERE id = ?", (local_id,)
        ).fetchone()
    return _public_session(row)


def _message_id(payload: dict[str, Any]) -> str:
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    return str(
        info.get("id")
        or info.get("messageID")
        or info.get("messageId")
        or payload.get("id")
        or ""
    )


def _message_role(payload: dict[str, Any]) -> str:
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    return str(info.get("role") or payload.get("role") or "").lower()


def _message_text(payload: dict[str, Any]) -> str:
    parts = payload.get("parts")
    if not isinstance(parts, list):
        return str(payload.get("text") or "").strip()
    chunks: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        part_type = str(part.get("type") or "text").lower()
        text = part.get("text")
        if isinstance(text, str) and part_type in {"text", "final", "answer", "output"}:
            chunks.append(text.strip())
    return "\n\n".join(chunk for chunk in chunks if chunk).strip()


def _register_asset(
    owner: str,
    session_id: str,
    source_path: Path,
) -> str:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, source_path FROM assistant_assets
            WHERE owner = ? AND session_id = ? AND origin_path = ?
            """,
            (owner, session_id, str(source_path)),
        ).fetchone()
        asset_id = str(row["id"]) if row else str(uuid.uuid4())
        served_path = (
            Path(row["source_path"])
            if row
            else ASSISTANT_OUTPUT_DIR
            / "served"
            / session_id
            / f"{asset_id}{source_path.suffix.lower()}"
        )
        if row is None:
            served_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, served_path)
            conn.execute(
                """
                INSERT INTO assistant_assets(
                    id, owner, session_id, origin_path, source_path, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    asset_id,
                    owner,
                    session_id,
                    str(source_path),
                    str(served_path),
                    _now(),
                ),
            )
            conn.commit()
    return f"/api/assistant/assets/{quote(session_id, safe='')}/{quote(asset_id, safe='')}"


def _image_urls(text: str, owner: str, session_id: str) -> list[str]:
    urls: list[str] = []
    output_root = ASSISTANT_OUTPUT_DIR.resolve()
    for match in _IMAGE_RE.finditer(text):
        relative = Path(match.group(1))
        candidate = (output_root / relative).resolve()
        try:
            safe_relative = candidate.relative_to(output_root)
        except ValueError:
            continue
        if candidate.is_file() and candidate.suffix.lower() in _IMAGE_TYPES:
            url = _register_asset(owner, session_id, output_root / safe_relative)
            if url not in urls:
                urls.append(url)
    return urls


def _sanitize_message_text(text: str) -> str:
    cleaned = _MARKDOWN_IMAGE_RE.sub(lambda match: match.group(1), text)
    cleaned = _IMAGE_RE.sub("", cleaned)
    lines = [
        line.rstrip()
        for line in cleaned.splitlines()
        if line.strip().lower() not in {"график:", "график"}
    ]
    return "\n".join(lines).strip()


def _normalize_messages(
    payload: Any,
    owner: str = "",
    session_id: str = "",
) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    messages: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        role = _message_role(item)
        if role not in {"user", "assistant"}:
            continue
        raw_text = _message_text(item)
        if not raw_text:
            continue
        images = _image_urls(raw_text, owner, session_id) if owner and session_id else []
        text = _sanitize_message_text(raw_text) or ("График готов." if images else "")
        if not text:
            continue
        info = item.get("info") if isinstance(item.get("info"), dict) else {}
        time_info = info.get("time") if isinstance(info.get("time"), dict) else {}
        messages.append(
            {
                "id": _message_id(item),
                "role": role,
                "text": text,
                "images": images,
                "created_at": time_info.get("created") or time_info.get("completed"),
            }
        )
    return messages


async def _server_messages(
    owner: str,
    session_id: str,
    server_session_id: str,
) -> list[dict[str, Any]]:
    payload = await _request(
        "GET",
        f"/session/{quote(server_session_id, safe='')}/message?limit=200",
    )
    return _normalize_messages(payload, owner, session_id)


def _set_pending(
    owner: str,
    session_id: str,
    pending: dict[str, Any] | None,
    error: str | None = None,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE assistant_sessions
            SET pending_json = ?, error_text = ?, updated_at = ?
            WHERE id = ? AND owner = ?
            """,
            (
                json.dumps(pending) if pending is not None else None,
                error,
                _now(),
                session_id,
                owner,
            ),
        )
        conn.commit()


def _status_value(value: Any) -> tuple[str, str | None]:
    if isinstance(value, str):
        status = value.lower()
        details = None
    elif isinstance(value, dict):
        status = str(
            value.get("type")
            or value.get("status")
            or value.get("state")
            or ""
        ).lower()
        details = str(value.get("error") or value.get("message") or "").strip() or None
    else:
        return "unknown", None
    if status in {"idle", "completed", "complete", "done", "ready"}:
        return "idle", details
    if status in {"failed", "error", "cancelled", "canceled"}:
        return "error", details or "OpenCode завершил запрос с ошибкой"
    if status in {"busy", "running", "pending", "retry", "queued"}:
        return "busy", details
    return "unknown", details


async def _session_status(server_session_id: str) -> tuple[str, str | None]:
    payload = await _request("GET", "/session/status", timeout=10)
    if isinstance(payload, dict):
        direct = payload.get(server_session_id)
        if direct is not None:
            return _status_value(direct)
        for key in ("sessions", "data", "items"):
            nested = payload.get(key)
            if isinstance(nested, dict) and server_session_id in nested:
                return _status_value(nested[server_session_id])
            if isinstance(nested, list):
                payload = nested
                break
        else:
            return "idle", None
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            item_id = str(
                item.get("sessionID")
                or item.get("sessionId")
                or item.get("id")
                or ""
            )
            if item_id == server_session_id:
                return _status_value(item)
        return "idle", None
    return "unknown", None


def _pending_age_seconds(pending: dict[str, Any]) -> float:
    try:
        started_at = datetime.fromisoformat(str(pending["started_at"]))
        return max(0.0, (datetime.now(timezone.utc) - started_at).total_seconds())
    except (KeyError, TypeError, ValueError):
        return float(ASSISTANT_PENDING_TIMEOUT_SECONDS + 1)


async def get_messages(owner: str, session_id: str) -> dict[str, Any]:
    row = _get_session(owner, session_id)
    try:
        messages = await _server_messages(
            owner,
            session_id,
            row["server_session_id"],
        )
    except AssistantError as exc:
        if row["pending_json"]:
            _set_pending(owner, session_id, None, str(exc))
        return {
            "items": [],
            "busy": False,
            "question": None,
            "error": str(exc),
        }
    pending = json.loads(row["pending_json"]) if row["pending_json"] else None
    busy = bool(pending)
    error = row["error_text"]
    if pending:
        if _pending_age_seconds(pending) > ASSISTANT_PENDING_TIMEOUT_SECONDS:
            error = "Время ожидания ответа XCA AI истекло"
            _set_pending(owner, session_id, None, error)
            return {
                "items": messages,
                "busy": False,
                "question": None,
                "error": error,
            }
        baseline = set(pending.get("message_ids") or [])
        new_assistant = [
            message
            for message in messages
            if message["role"] == "assistant" and message["id"] not in baseline
        ]
        try:
            status, status_error = await _session_status(row["server_session_id"])
        except AssistantError as exc:
            error = str(exc)
            _set_pending(owner, session_id, None, error)
            return {
                "items": messages,
                "busy": False,
                "question": None,
                "error": error,
            }
        if status == "error":
            error = status_error or "OpenCode завершил запрос с ошибкой"
            _set_pending(owner, session_id, None, error)
            busy = False
        elif status == "idle" and new_assistant:
            current_count = len(messages)
            previous_count = int(pending.get("last_count", -1))
            stable_polls = int(pending.get("idle_stable_polls", 0))
            stable_polls = stable_polls + 1 if current_count == previous_count else 0
            pending["last_count"] = current_count
            pending["idle_stable_polls"] = stable_polls
            if stable_polls >= 1:
                busy = False
                error = None
                _set_pending(owner, session_id, None)
            else:
                _set_pending(owner, session_id, pending)
        elif status == "idle" and _pending_age_seconds(pending) >= 10:
            busy = False
            error = "OpenCode завершил запрос без итогового ответа"
            _set_pending(owner, session_id, None, error)
        elif status == "unknown":
            current_count = len(messages)
            pending["last_count"] = current_count
            pending["status_unknown_polls"] = int(
                pending.get("status_unknown_polls", 0)
            ) + 1
            _set_pending(owner, session_id, pending)
    question = None
    if busy:
        try:
            question = await _pending_question(row["server_session_id"])
        except AssistantError as exc:
            error = str(exc)
            busy = False
            _set_pending(owner, session_id, None, error)
    return {
        "items": messages,
        "busy": busy,
        "question": question,
        "error": error,
    }


async def send_message(owner: str, session_id: str, text: str) -> dict[str, Any]:
    cleaned = " ".join(text.split()).strip()
    if not cleaned:
        raise AssistantError("Введите сообщение", 422)
    if len(cleaned) > 8000:
        raise AssistantError("Сообщение длиннее 8000 символов", 422)
    row = _get_session(owner, session_id)
    if row["pending_json"]:
        raise AssistantError("Дождитесь ответа или отмените текущий запрос", 409)
    messages = await _server_messages(owner, session_id, row["server_session_id"])
    baseline = [_message["id"] for _message in messages if _message["id"]]
    await _request(
        "POST",
        f"/session/{quote(row['server_session_id'], safe='')}/prompt_async",
        payload={"parts": [{"type": "text", "text": cleaned}]},
    )
    title = row["title"]
    if title == "Новый чат":
        title = cleaned[:60]
    timestamp = _now()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE assistant_sessions
            SET title = ?, pending_json = ?, error_text = NULL, updated_at = ?
            WHERE id = ? AND owner = ?
            """,
            (
                title,
                json.dumps(
                    {
                        "message_ids": baseline,
                        "started_at": timestamp,
                        "last_count": len(messages),
                        "stable_polls": 0,
                    }
                ),
                timestamp,
                session_id,
                owner,
            ),
        )
        conn.commit()
    return {"ok": True, "busy": True}


async def cancel(owner: str, session_id: str) -> dict[str, Any]:
    row = _get_session(owner, session_id)
    try:
        await _request(
            "POST",
            f"/session/{quote(row['server_session_id'], safe='')}/abort",
            payload={},
        )
    except AssistantError as exc:
        _set_pending(owner, session_id, None, str(exc))
        raise
    _set_pending(owner, session_id, None)
    return {"ok": True}


async def delete_session(owner: str, session_id: str) -> None:
    row = _get_session(owner, session_id)
    try:
        await _request(
            "DELETE", f"/session/{quote(row['server_session_id'], safe='')}"
        )
    finally:
        with _connect() as conn:
            conn.execute(
                "DELETE FROM assistant_assets WHERE session_id = ? AND owner = ?",
                (session_id, owner),
            )
            conn.execute(
                "DELETE FROM assistant_sessions WHERE id = ? AND owner = ?",
                (session_id, owner),
            )
            conn.commit()


async def _pending_question(server_session_id: str) -> dict[str, Any] | None:
    payload = await _request("GET", "/question")
    if not isinstance(payload, list):
        return None
    for item in payload:
        if not isinstance(item, dict) or item.get("sessionID") != server_session_id:
            continue
        question = (item.get("questions") or [{}])[0]
        if not isinstance(question, dict):
            question = {}
        options = []
        for option in question.get("options") or []:
            if isinstance(option, dict):
                value = str(option.get("value") or option.get("label") or "").strip()
                if value:
                    options.append(
                        {
                            "label": str(option.get("label") or value),
                            "value": value,
                            "description": str(option.get("description") or ""),
                        }
                    )
        return {
            "id": str(item.get("id") or ""),
            "text": str(question.get("question") or question.get("header") or "Уточните запрос"),
            "options": options[:6],
        }
    return None


async def reply_question(
    owner: str, session_id: str, question_id: str, answer: str
) -> dict[str, Any]:
    row = _get_session(owner, session_id)
    question = await _pending_question(row["server_session_id"])
    if not question or question["id"] != question_id:
        raise AssistantError("Уточнение больше не актуально", 409)
    await _request(
        "POST",
        f"/question/{quote(question_id, safe='')}/reply",
        payload={"answers": [[answer]]},
    )
    return {"ok": True, "busy": True}


def resolve_asset(owner: str, session_id: str, asset_id: str) -> Path:
    _get_session(owner, session_id)
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT source_path FROM assistant_assets
            WHERE id = ? AND session_id = ? AND owner = ?
            """,
            (asset_id, session_id, owner),
        ).fetchone()
    if row is None:
        raise AssistantError("Файл не найден", 404)
    output_root = (ASSISTANT_OUTPUT_DIR / "served" / session_id).resolve()
    candidate = Path(row["source_path"]).resolve()
    try:
        candidate.relative_to(output_root)
    except ValueError as exc:
        raise AssistantError("Файл не найден", 404) from exc
    if not candidate.is_file() or candidate.suffix.lower() not in _IMAGE_TYPES:
        raise AssistantError("Файл не найден", 404)
    return candidate
