"""FTP/web → web_data.db — тот же ETL, что admin «FTP → web/ → БД» в [main]."""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from typing import Any

from app.config import CORE_APP_DIR, WEB_DATA_DIR, WEB_DB_PATH


def _ensure_streamlit_stub() -> None:
    if "streamlit" in sys.modules:
        return

    class _FakeSessionState:
        def __init__(self) -> None:
            self._d: dict = {}

        def __contains__(self, k: object) -> bool:
            return k in self._d

        def __getitem__(self, k: str):
            return self._d[k]

        def __setitem__(self, k: str, v) -> None:
            self._d[k] = v

        def get(self, k: str, default=None):
            return self._d.get(k, default)

        def pop(self, k: str, default=None):
            return self._d.pop(k, default) if k in self._d else default

        def __getattr__(self, name: str):
            if name == "_d" or name.startswith("__"):
                raise AttributeError(name)
            return self._d.get(name)

        def __setattr__(self, name: str, value) -> None:
            if name == "_d":
                object.__setattr__(self, name, value)
            else:
                if not hasattr(self, "_d"):
                    object.__setattr__(self, "_d", {})
                self._d[name] = value

    mock = types.ModuleType("streamlit")
    mock.session_state = _FakeSessionState()
    mock.error = lambda *a, **kw: None
    mock.warning = lambda *a, **kw: None
    mock.cache_data = lambda *a, **kw: (lambda f: f)
    mock.cache_resource = lambda *a, **kw: (lambda f: f)
    sys.modules["streamlit"] = mock


def _prepare_core_imports() -> Path:
    core = CORE_APP_DIR.resolve()
    if not (core / "web_loader.py").is_file():
        raise FileNotFoundError(f"web_loader.py не найден в {core}")
    if str(core) not in sys.path:
        sys.path.insert(0, str(core))

    db_path = WEB_DB_PATH.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    os.environ["WEB_DB_PATH"] = str(db_path)
    # Не тянуть соседний Analitics/web и лишние корни — только WEB_DATA_DIR через monkeypatch.
    os.environ["BI_ANALYTICS_WEB_INCLUDE_SIBLING"] = "0"
    os.environ["BI_ANALYTICS_AUTO_FTP_ON_START"] = "0"
    os.environ.pop("BI_ANALYTICS_WEB_EXTRA_PATHS", None)

    _ensure_streamlit_stub()
    return core


def db_status() -> dict[str, Any]:
    path = WEB_DB_PATH.resolve()
    out: dict[str, Any] = {
        "web_db_path": str(path),
        "exists": path.is_file(),
        "size_bytes": path.stat().st_size if path.is_file() else 0,
        "mtime": path.stat().st_mtime if path.is_file() else None,
        "active_version_id": None,
    }
    if not path.is_file():
        return out
    try:
        _prepare_core_imports()
        import web_schema  # type: ignore

        web_schema.WEB_DB_PATH = str(path)
        out["active_version_id"] = web_schema.get_active_version_id()
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
    return out


def run_db_ingest(*, web_dir: Path | None = None) -> dict[str, Any]:
    """
    web/ → web_data.db через load_all_from_web() из bi-analytics-v-5-main.
    Каталог данных: WEB_DATA_DIR (synthetic или ftp), не showcase_data случайно мимо config.
    """
    target_web = (web_dir or WEB_DATA_DIR).resolve()
    if not target_web.is_dir():
        return {
            "ok": False,
            "errors": [f"Каталог web не найден: {target_web}"],
            "web_dir": str(target_web),
            "web_db_path": str(WEB_DB_PATH),
        }

    try:
        _prepare_core_imports()
        import web_schema  # type: ignore
        import web_loader  # type: ignore

        db_path = str(WEB_DB_PATH.resolve())
        web_schema.WEB_DB_PATH = db_path
        # Только наш web/: подмена корня сканирования.
        web_loader.get_web_dir = lambda: target_web  # type: ignore[assignment]

        web_schema.init_web_schema()
        if not web_loader.web_dir_exists():
            return {
                "ok": False,
                "errors": [f"web_dir_exists()=False для {target_web}"],
                "web_dir": str(target_web),
                "web_db_path": db_path,
            }

        result = web_loader.load_all_from_web()
        version_id = result.get("version_id")
        active = web_schema.get_active_version_id()
        ok = version_id is not None
        return {
            "ok": ok,
            "web_dir": str(target_web),
            "web_db_path": db_path,
            "loaded": result.get("loaded"),
            "skipped": result.get("skipped"),
            "version_id": version_id,
            "active_version_id": active,
            "errors": list(result.get("errors") or []),
            "db": db_status(),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "errors": [str(exc)],
            "web_dir": str(target_web),
            "web_db_path": str(WEB_DB_PATH),
        }
