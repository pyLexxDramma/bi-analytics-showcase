"""Регрессия core_bridge: stub, импорт dashboards.*, чтение web_data.db, payload девпроектов.

Запуск: python webapp/scripts/check_core_bridge.py (exit code != 0 при провале).
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))


def case(name: str, fn):
    try:
        result = fn()
        print(f"OK   {name}: {result}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL {name}: {type(exc).__name__}: {exc}")
        return False


# 1. Битый stub в sys.modules (__spec__ is None) — прошлая ошибка на VPS
broken = ModuleType("streamlit")
broken.__spec__ = None
sys.modules["streamlit"] = broken

from app.services import core_bridge  # noqa: E402

ok = True
ok &= case("ensure_streamlit_stub на битом stub", lambda: type(core_bridge.ensure_streamlit_stub()).__name__)
ok &= case("session_state есть", lambda: type(sys.modules["streamlit"].session_state).__name__)
ok &= case("cache_data-декоратор", lambda: sys.modules["streamlit"].cache_data(lambda: 1)())
ok &= case("неизвестный атрибут не падает", lambda: bool(sys.modules["streamlit"].popover("x")))
ok &= case("идемпотентность", lambda: core_bridge.ensure_streamlit_stub() is sys.modules["streamlit"])

ok &= case("prepare_web_db", core_bridge.prepare_web_db)
ok &= case("active_version_id", core_bridge.active_version_id)
ok &= case(
    "import dev_projects_tz_matrix",
    lambda: core_bridge.import_dashboard_module("dev_projects_tz_matrix").__name__,
)

vid = core_bridge.active_version_id()
if vid:
    ok &= case(
        "load_version_df(reference_dannye)",
        lambda: len(core_bridge.load_version_df(vid, "reference_dannye")),
    )

from app.services.developer_projects import build_developer_projects_payload  # noqa: E402


def dev_projects():
    payload = build_developer_projects_payload()
    meta = payload["meta"]
    if meta.get("error"):
        raise RuntimeError(meta["error"])
    return (
        f"projects={len(payload['matrix']['projects'])} "
        f"columns={meta.get('columns')} cells={meta.get('cells')}"
    )


ok &= case("build_developer_projects_payload", dev_projects)

from app.services.db_ingest import db_status  # noqa: E402

ok &= case("db_status", lambda: db_status().get("active_version_id"))

print("RESULT:", "ALL OK" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
