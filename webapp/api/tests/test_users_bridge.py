from __future__ import annotations

import sqlite3
import sys
from types import SimpleNamespace

from app.services import users_bridge


def test_existing_admin_password_is_never_rewritten(tmp_path, monkeypatch):
    database = tmp_path / "users.db"
    with sqlite3.connect(database) as conn:
        conn.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password_hash TEXT)"
        )
        conn.execute(
            "INSERT INTO users(username, password_hash) VALUES ('admin', 'original-hash')"
        )
        conn.commit()

    fake_auth = SimpleNamespace(
        init_db=lambda quiet=True: None,
        create_user=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("existing users must not be reseeded")
        ),
    )
    fake_config = SimpleNamespace(DB_PATH="")
    monkeypatch.setattr(users_bridge, "USERS_DB_PATH", database)
    monkeypatch.setattr(users_bridge, "prepare_core_env", lambda: None)
    monkeypatch.setitem(sys.modules, "auth", fake_auth)
    monkeypatch.setitem(sys.modules, "config", fake_config)
    monkeypatch.setattr(users_bridge, "_prepared", False)

    users_bridge.ensure_users_db(seed=True)

    with sqlite3.connect(database) as conn:
        stored_hash = conn.execute(
            "SELECT password_hash FROM users WHERE username = 'admin'"
        ).fetchone()[0]
    assert stored_hash == "original-hash"


def test_empty_users_db_is_not_seeded_without_strong_password(tmp_path, monkeypatch):
    database = tmp_path / "users.db"
    with sqlite3.connect(database) as conn:
        conn.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password_hash TEXT)"
        )
        conn.commit()
    created = []
    fake_auth = SimpleNamespace(
        init_db=lambda quiet=True: None,
        create_user=lambda *args, **kwargs: created.append(args),
    )
    monkeypatch.setattr(users_bridge, "USERS_DB_PATH", database)
    monkeypatch.setattr(users_bridge, "BOOTSTRAP_ADMIN_PASSWORD", "short")
    monkeypatch.setattr(users_bridge, "prepare_core_env", lambda: None)
    monkeypatch.setitem(sys.modules, "auth", fake_auth)
    monkeypatch.setitem(sys.modules, "config", SimpleNamespace(DB_PATH=""))
    monkeypatch.setattr(users_bridge, "_prepared", False)

    users_bridge.ensure_users_db(seed=True)

    assert created == []


def test_empty_users_db_seeds_only_with_strong_bootstrap_password(
    tmp_path,
    monkeypatch,
):
    database = tmp_path / "users.db"
    with sqlite3.connect(database) as conn:
        conn.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password_hash TEXT)"
        )
        conn.commit()
    created = []
    fake_auth = SimpleNamespace(
        init_db=lambda quiet=True: None,
        create_user=lambda *args, **kwargs: created.append(args),
    )
    monkeypatch.setattr(users_bridge, "USERS_DB_PATH", database)
    monkeypatch.setattr(users_bridge, "BOOTSTRAP_ADMIN_USERNAME", "owner")
    monkeypatch.setattr(
        users_bridge,
        "BOOTSTRAP_ADMIN_PASSWORD",
        "strong-bootstrap-password",
    )
    monkeypatch.setattr(users_bridge, "prepare_core_env", lambda: None)
    monkeypatch.setitem(sys.modules, "auth", fake_auth)
    monkeypatch.setitem(sys.modules, "config", SimpleNamespace(DB_PATH=""))
    monkeypatch.setattr(users_bridge, "_prepared", False)

    users_bridge.ensure_users_db(seed=True)

    assert created == [
        ("owner", "strong-bootstrap-password", "superadmin", None, "system")
    ]


def test_core_default_admin_is_replaced_by_configured_bootstrap(
    tmp_path,
    monkeypatch,
):
    database = tmp_path / "users.db"

    def init_db(quiet=True):
        with sqlite3.connect(database) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS users "
                "(id INTEGER PRIMARY KEY, username TEXT, password_hash TEXT)"
            )
            conn.execute(
                "INSERT INTO users(username, password_hash) VALUES (?, ?)",
                ("admin", "hash-of-admin123"),
            )
            conn.commit()

    def create_user(username, password, *_args):
        with sqlite3.connect(database) as conn:
            conn.execute(
                "INSERT INTO users(username, password_hash) VALUES (?, ?)",
                (username, f"hash-of-{password}"),
            )
            conn.commit()

    fake_auth = SimpleNamespace(init_db=init_db, create_user=create_user)
    monkeypatch.setattr(users_bridge, "USERS_DB_PATH", database)
    monkeypatch.setattr(users_bridge, "BOOTSTRAP_ADMIN_USERNAME", "owner")
    monkeypatch.setattr(
        users_bridge,
        "BOOTSTRAP_ADMIN_PASSWORD",
        "strong-bootstrap-password",
    )
    monkeypatch.setattr(users_bridge, "prepare_core_env", lambda: None)
    monkeypatch.setitem(sys.modules, "auth", fake_auth)
    monkeypatch.setitem(sys.modules, "config", SimpleNamespace(DB_PATH=""))
    monkeypatch.setattr(users_bridge, "_prepared", False)

    users_bridge.ensure_users_db(seed=True)

    with sqlite3.connect(database) as conn:
        users = conn.execute(
            "SELECT username, password_hash FROM users ORDER BY id"
        ).fetchall()
    assert users == [("owner", "hash-of-strong-bootstrap-password")]
