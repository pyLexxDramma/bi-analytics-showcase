"""FTP/web → web_data.db — тот же ETL, что admin «FTP → web/ → БД» в [main]."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import WEB_DATA_DIR, WEB_DB_PATH
from app.services.core_bridge import import_web_loader
from app.services.core_bridge import prepare_core_env as _prepare_core_imports


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


def _loaded_files(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Имена реально загруженных файлов из diagnostics load_all_from_web().

    `columns` из diagnostics отбрасываем: в ответе admin-кнопки нужен список
    «что подтянулось», а не превью схемы каждого файла.
    """
    out: list[dict[str, Any]] = []
    for item in result.get("diagnostics") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("file") or "").strip()
        if not name:
            continue
        out.append(
            {
                "file": name,
                "type": str(item.get("type") or ""),
                "rows": int(item.get("rows") or 0),
                "incremental": bool(item.get("incremental")),
            }
        )
    out.sort(key=lambda x: x["file"].lower())
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

        web_loader = import_web_loader()

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
            "loaded_files": _loaded_files(result),
            "warnings": list(result.get("warnings") or []),
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
