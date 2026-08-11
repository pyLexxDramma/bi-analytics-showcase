from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import admin, bdds_plan_fact, profile_router, settings_router
from app.services import auth_context
from app.services.auth_tokens import create_token


class _Auth:
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
        return None

    @staticmethod
    def has_admin_access(role: str) -> bool:
        return role == "superadmin"

    @staticmethod
    def has_report_access(role: str) -> bool:
        return True

    @staticmethod
    def role_can_open_report(role: str, report_id: str) -> bool:
        return True

    @staticmethod
    def user_can_edit_finance_tables(role: str) -> bool:
        return role == "superadmin"

    @staticmethod
    def user_can_ftp_sync(role: str) -> bool:
        return True

    @staticmethod
    def get_user_role_display(role: str) -> str:
        return role

    @staticmethod
    def update_user_email(username: str, email: str | None):
        return True, "ok"


class _Logger:
    @staticmethod
    def log_action(*args, **kwargs):
        return None


@pytest.fixture
def protected_client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(auth_context, "import_auth", lambda: _Auth())
    database = tmp_path / "users.db"
    with sqlite3.connect(database) as conn:
        conn.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                role TEXT,
                email TEXT,
                created_at TEXT,
                last_login TEXT,
                is_active INTEGER
            )
            """
        )
        conn.execute(
            """
            INSERT INTO users(username, role, created_at, is_active)
            VALUES ('admin', 'superadmin', '2026-01-01', 1)
            """
        )
        conn.commit()
    monkeypatch.setattr(settings_router, "USERS_DB_PATH", database)
    monkeypatch.setattr(settings_router, "import_auth", lambda: _Auth())
    monkeypatch.setattr(profile_router, "import_auth", lambda: _Auth())
    monkeypatch.setattr(profile_router, "import_logger", lambda: _Logger())
    monkeypatch.setattr(admin, "cache_clear", lambda: 0)
    monkeypatch.setattr(admin, "clear_data_caches", lambda: None)
    monkeypatch.setattr(
        bdds_plan_fact,
        "apply_bdds_plan_fact_edits",
        lambda **kwargs: {"ok": True},
    )
    return TestClient(app)


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/api/settings/users", None),
        ("post", "/api/admin/cache-clear", {}),
        ("post", "/api/profile/email", {"new_email": "admin@example.com"}),
        (
            "post",
            "/api/bdds-plan-fact/apply",
            {"project": "Project", "rows": []},
        ),
    ],
)
def test_spoofed_user_header_is_rejected(
    protected_client: TestClient,
    method: str,
    path: str,
    body: dict | None,
):
    response = protected_client.request(
        method.upper(),
        path,
        headers={"X-Auth-User": "admin"},
        json=body,
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/api/settings/users", None),
        ("post", "/api/admin/cache-clear", {}),
        ("post", "/api/profile/email", {"new_email": "admin@example.com"}),
        (
            "post",
            "/api/bdds-plan-fact/apply",
            {"project": "Project", "rows": []},
        ),
    ],
)
def test_valid_bearer_is_accepted(
    protected_client: TestClient,
    method: str,
    path: str,
    body: dict | None,
):
    response = protected_client.request(
        method.upper(),
        path,
        headers={"Authorization": f"Bearer {create_token('admin')}"},
        json=body,
    )
    assert response.status_code == 200


def test_public_demo_bootstrap_endpoint_is_removed():
    response = TestClient(app).post("/api/auth/init-demo")
    assert response.status_code == 404
