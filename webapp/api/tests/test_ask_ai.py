from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import ask_ai as ask_ai_service
from app.services import auth_context
from app.services.ask_ai import sign_params
from app.services.auth_tokens import create_token


class _Auth:
    ROLES = {
        "superadmin": "Суперадминистратор",
        "manager": "Менеджер",
        "analyst": "Аналитик",
    }

    @staticmethod
    def get_user_by_username(username: str):
        if username == "admin":
            return {
                "id": 1,
                "username": "admin",
                "role": "superadmin",
                "is_active": 1,
                "email": None,
            }
        if username == "mgr":
            return {
                "id": 2,
                "username": "mgr",
                "role": "manager",
                "is_active": 1,
                "email": None,
            }
        return None

    @staticmethod
    def has_admin_access(role: str) -> bool:
        return role == "superadmin"

    @staticmethod
    def has_report_access(role: str) -> bool:
        return True

    @staticmethod
    def user_can_open_report(role: str, report_name: str) -> bool:
        if role == "superadmin":
            return True
        if role == "manager" and report_name in ("БДДС", "БДДС (расходы)"):
            return False
        return True

    @staticmethod
    def get_user_role_display(role: str) -> str:
        return _Auth.ROLES.get(role, role)


@pytest.fixture
def ask_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(auth_context, "import_auth", lambda: _Auth())
    monkeypatch.setattr(ask_ai_service, "import_auth", lambda: _Auth())
    monkeypatch.setattr(ask_ai_service, "XCA_ASK_BASE_URL", "https://xca.example")
    monkeypatch.setattr(ask_ai_service, "XCA_ASK_SECRET", "test-secret")
    return TestClient(app)


def test_sign_params_stable():
    params = {"v": "1", "report": "screen_bdds", "q": "hi", "ts": "1"}
    a = sign_params(params, b"test-secret")
    b = sign_params(dict(params), b"test-secret")
    assert a == b
    assert "=" not in a


def test_ask_ai_link_requires_auth(ask_client: TestClient):
    res = ask_client.post("/api/ask-ai/link", json={"nav_id": "bdds"})
    assert res.status_code == 401


def test_ask_ai_link_signed(ask_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ask_ai_service.time, "time", lambda: 1_700_000_000)

    token = create_token("admin")
    res = ask_client.post(
        "/api/ask-ai/link",
        json={
            "nav_id": "approved-budget",
            "project": "Есипово-5",
            "period": "2026-08",
            "filters": {"block": "СМР"},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["report"] == "screen_approved_budget"
    url = body["url"]
    assert url.startswith("https://xca.example/ask?")
    qs = parse_qs(urlparse(url).query)
    assert qs["v"] == ["1"]
    assert qs["report"] == ["screen_approved_budget"]
    assert qs["uid"] == ["u_1"]
    assert qs["role"] == ["superadmin"]
    assert qs["project"] == ["Есипово-5"]
    assert "sig" in qs

    params = {k: v[0] for k, v in qs.items()}
    sig = params.pop("sig")
    assert sign_params(params, b"test-secret") == sig


def test_ask_ai_link_legacy_alias(ask_client: TestClient):
    token = create_token("admin")
    res = ask_client.post(
        "/api/ask-ai-link",
        json={"nav_id": "gdrs-people"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["report"] == "screen_gdrs_people"


def test_roles_catalog_admin_only(ask_client: TestClient):
    token = create_token("admin")
    res = ask_client.get(
        "/api/ask-ai/roles-catalog",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "roles" in data and "screens" in data
    assert len(data["screens"]) == 16
    codes = {r["code"] for r in data["roles"]}
    assert "superadmin" in codes
    assert "manager" in codes
    mgr = next(r for r in data["roles"] if r["code"] == "manager")
    assert "screen_bdds" not in mgr["reports"]
    assert "screen_gdrs_people" in mgr["reports"]


def test_roles_catalog_forbidden_for_non_admin(ask_client: TestClient):
    token = create_token("mgr")
    res = ask_client.get(
        "/api/ask-ai/roles-catalog",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def test_ask_ai_link_forbidden_for_role_without_screen(ask_client: TestClient):
    token = create_token("mgr")
    res = ask_client.post(
        "/api/ask-ai/link",
        json={"nav_id": "bdds"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def test_ask_ai_link_allowed_for_role_with_screen(ask_client: TestClient):
    token = create_token("mgr")
    res = ask_client.post(
        "/api/ask-ai/link",
        json={"nav_id": "gdrs-people"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["report"] == "screen_gdrs_people"
