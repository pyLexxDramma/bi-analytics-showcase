from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import assistant as assistant_router
from app.services import assistant, auth_context
from app.services.auth_tokens import create_token


@pytest.fixture
def isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(assistant, "ASSISTANT_DB_PATH", tmp_path / "assistant.db")
    monkeypatch.setattr(assistant, "ASSISTANT_OUTPUT_DIR", tmp_path / "output")
    (tmp_path / "output").mkdir()


def test_sessions_are_isolated_by_owner(
    isolated_store: None,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_request(method: str, path: str, **kwargs):
        assert method == "POST"
        return {"id": "server-1"}

    monkeypatch.setattr(assistant, "_request", fake_request)
    session = asyncio.run(assistant.create_session("alice"))

    assert assistant.list_sessions("alice")[0]["id"] == session["id"]
    assert assistant.list_sessions("bob") == []
    with pytest.raises(assistant.AssistantError) as exc:
        asyncio.run(assistant.get_messages("bob", session["id"]))
    assert exc.value.status_code == 404


def test_send_and_poll_complete_async_request(
    isolated_store: None,
    monkeypatch: pytest.MonkeyPatch,
):
    server_messages: list[dict] = []

    async def fake_request(method: str, path: str, **kwargs):
        if method == "POST" and path.startswith("/session?"):
            return {"id": "server-2"}
        if method == "GET" and "/message" in path:
            return server_messages
        if method == "GET" and path == "/session/status":
            return {"server-2": {"type": "idle"}}
        if method == "POST" and path.endswith("/prompt_async"):
            text = kwargs["payload"]["parts"][0]["text"]
            server_messages.extend(
                [
                    {
                        "info": {"id": "user-1", "role": "user"},
                        "parts": [{"type": "text", "text": text}],
                    },
                    {
                        "info": {"id": "assistant-1", "role": "assistant"},
                        "parts": [{"type": "text", "text": "Готовый ответ"}],
                    },
                ]
            )
            return None
        if method == "GET" and path == "/question":
            return []
        raise AssertionError((method, path))

    monkeypatch.setattr(assistant, "_request", fake_request)
    session = asyncio.run(assistant.create_session("alice"))
    sent = asyncio.run(assistant.send_message("alice", session["id"], "  Итоги проекта  "))
    first_poll = asyncio.run(assistant.get_messages("alice", session["id"]))
    result = asyncio.run(assistant.get_messages("alice", session["id"]))

    assert sent["busy"] is True
    assert first_poll["busy"] is True
    assert result["busy"] is False
    assert [message["role"] for message in result["items"]] == ["user", "assistant"]
    assert assistant.list_sessions("alice")[0]["title"] == "Итоги проекта"


def test_asset_path_validation(isolated_store: None):
    with assistant._connect() as conn:
        now = assistant._now()
        conn.execute(
            """
            INSERT INTO assistant_sessions
                (id, owner, server_session_id, title, created_at, updated_at)
            VALUES ('session-a', 'alice', 'server-a', 'A', ?, ?)
            """,
            (now, now),
        )
        conn.commit()
    chart = assistant.ASSISTANT_OUTPUT_DIR / "run" / "chart.png"
    chart.parent.mkdir()
    chart.write_bytes(b"png")
    asset_id = assistant._register_asset("alice", "session-a", chart).rsplit("/", 1)[-1]

    served = assistant.resolve_asset("alice", "session-a", asset_id)
    assert served != chart.resolve()
    assert served.read_bytes() == b"png"
    assert served.parent.name == "session-a"
    with pytest.raises(assistant.AssistantError):
        assistant.resolve_asset("bob", "session-a", asset_id)
    with pytest.raises(assistant.AssistantError):
        assistant.resolve_asset("alice", "session-a", str(__import__("uuid").uuid4()))


def test_message_hides_workspace_path_and_returns_protected_image(
    isolated_store: None,
):
    chart = assistant.ASSISTANT_OUTPUT_DIR / "run" / "chart.png"
    chart.parent.mkdir()
    chart.write_bytes(b"png")
    payload = [
        {
            "info": {"id": "assistant-1", "role": "assistant"},
            "parts": [
                {
                    "type": "text",
                    "text": "Итог.\nГрафик: [chart](file:///workspace/analytics/output/run/chart.png)",
                }
            ],
        }
    ]

    with assistant._connect() as conn:
        now = assistant._now()
        conn.execute(
            """
            INSERT INTO assistant_sessions
                (id, owner, server_session_id, title, created_at, updated_at)
            VALUES ('session-a', 'alice', 'server-a', 'A', ?, ?)
            """,
            (now, now),
        )
        conn.commit()
    message = assistant._normalize_messages(payload, "alice", "session-a")[0]

    assert "/workspace/" not in message["text"]
    assert message["images"][0].startswith("/api/assistant/assets/session-a/")


def _pending_session(
    owner: str = "alice",
    session_id: str = "session-poll",
    server_id: str = "server-poll",
    *,
    age_seconds: int = 0,
) -> None:
    now = datetime.now(timezone.utc)
    pending = {
        "message_ids": ["user-old"],
        "started_at": (now - timedelta(seconds=age_seconds)).isoformat(),
        "last_count": 1,
        "stable_polls": 0,
    }
    with assistant._connect() as conn:
        conn.execute(
            """
            INSERT INTO assistant_sessions
                (id, owner, server_session_id, title, pending_json, created_at, updated_at)
            VALUES (?, ?, ?, 'Poll', ?, ?, ?)
            """,
            (
                session_id,
                owner,
                server_id,
                json.dumps(pending),
                now.isoformat(),
                now.isoformat(),
            ),
        )
        conn.commit()


def _assistant_messages() -> list[dict]:
    return [
        {
            "info": {"id": "assistant-new", "role": "assistant"},
            "parts": [{"type": "text", "text": "Промежуточный или итоговый ответ"}],
        }
    ]


def test_intermediate_text_does_not_finish_busy_session(
    isolated_store: None,
    monkeypatch: pytest.MonkeyPatch,
):
    _pending_session()

    async def fake_request(method: str, path: str, **kwargs):
        if "/message" in path:
            return _assistant_messages()
        if path == "/session/status":
            return {"server-poll": {"type": "busy"}}
        if path == "/question":
            return []
        raise AssertionError((method, path))

    monkeypatch.setattr(assistant, "_request", fake_request)
    result = asyncio.run(assistant.get_messages("alice", "session-poll"))

    assert result["busy"] is True
    assert assistant.list_sessions("alice")[0]["busy"] is True


def test_idle_status_finishes_with_final_message(
    isolated_store: None,
    monkeypatch: pytest.MonkeyPatch,
):
    _pending_session()

    async def fake_request(method: str, path: str, **kwargs):
        if "/message" in path:
            return _assistant_messages()
        if path == "/session/status":
            return {"server-poll": {"type": "idle"}}
        raise AssertionError((method, path))

    monkeypatch.setattr(assistant, "_request", fake_request)
    result = asyncio.run(assistant.get_messages("alice", "session-poll"))

    assert result["busy"] is False
    assert result["error"] is None


def test_failed_status_clears_pending_and_returns_error(
    isolated_store: None,
    monkeypatch: pytest.MonkeyPatch,
):
    _pending_session()

    async def fake_request(method: str, path: str, **kwargs):
        if "/message" in path:
            return []
        if path == "/session/status":
            return {"server-poll": {"type": "error", "message": "model failed"}}
        raise AssertionError((method, path))

    monkeypatch.setattr(assistant, "_request", fake_request)
    result = asyncio.run(assistant.get_messages("alice", "session-poll"))

    assert result["busy"] is False
    assert result["error"] == "model failed"
    assert assistant.list_sessions("alice")[0]["busy"] is False


def test_timeout_clears_pending(
    isolated_store: None,
    monkeypatch: pytest.MonkeyPatch,
):
    _pending_session(age_seconds=30)
    monkeypatch.setattr(assistant, "ASSISTANT_PENDING_TIMEOUT_SECONDS", 10)

    async def fake_request(method: str, path: str, **kwargs):
        if "/message" in path:
            return []
        raise AssertionError((method, path))

    monkeypatch.setattr(assistant, "_request", fake_request)
    result = asyncio.run(assistant.get_messages("alice", "session-poll"))

    assert result["busy"] is False
    assert "истекло" in result["error"]


class _FakeAuth:
    @staticmethod
    def get_user_by_username(username: str):
        if username == "alice":
            return {"username": "alice", "role": "analyst", "is_active": 1}
        return None

    @staticmethod
    def has_report_access(role: str) -> bool:
        return role == "analyst"


def test_assistant_rejects_spoofed_user_header(
    isolated_store: None,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(auth_context, "import_auth", lambda: _FakeAuth())
    response = TestClient(app).get(
        "/api/assistant/sessions",
        headers={"X-Auth-User": "alice"},
    )
    assert response.status_code == 401


def test_assistant_accepts_valid_signed_token(
    isolated_store: None,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(auth_context, "import_auth", lambda: _FakeAuth())
    monkeypatch.setattr(assistant_router, "AI_ENABLED", True)
    response = TestClient(app).get(
        "/api/assistant/sessions",
        headers={"Authorization": f"Bearer {create_token('alice')}"},
    )
    assert response.status_code == 200


def test_stub_mode_health_does_not_call_ai_backend(
    isolated_store: None,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(auth_context, "import_auth", lambda: _FakeAuth())
    monkeypatch.setattr(assistant_router, "AI_ENABLED", False)

    async def forbidden_health():
        raise AssertionError("stub mode must not call OpenCode or vLLM")

    monkeypatch.setattr(assistant, "health", forbidden_health)
    response = TestClient(app).get(
        "/api/assistant/health",
        headers={"Authorization": f"Bearer {create_token('alice')}"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "enabled": False, "mode": "stub"}


@pytest.mark.parametrize("kind", ["expired", "tampered"])
def test_assistant_rejects_invalid_tokens(
    isolated_store: None,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
):
    monkeypatch.setattr(auth_context, "import_auth", lambda: _FakeAuth())
    token = create_token("alice", ttl_seconds=-1)
    if kind == "tampered":
        encoded, signature = create_token("alice").split(".", 1)
        replacement = "A" if signature[0] != "A" else "B"
        token = f"{encoded}.{replacement}{signature[1:]}"
    response = TestClient(app).get(
        "/api/assistant/sessions",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Auth-User": "alice",
        },
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ({"exists": True, "active_version_id": None}, False),
        ({"exists": True, "active_version_id": 7}, True),
        ({"exists": True, "active_version_id": 7, "error": "bad schema"}, False),
    ],
)
def test_database_readiness_requires_active_valid_version(
    monkeypatch: pytest.MonkeyPatch,
    status: dict,
    expected: bool,
):
    monkeypatch.setattr(assistant, "db_status", lambda: status)
    assert assistant._database_health()["ok"] is expected
