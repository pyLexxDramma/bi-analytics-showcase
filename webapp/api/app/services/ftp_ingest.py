from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from app.config import CORE_APP_DIR, DATA_MODE, WEB_DATA_DIR
from app.services.debit_credit import load_debit_credit_frame, _source_mtime_key
from app.services.db_ingest import db_status, run_db_ingest
from app.services.report_cache import cache_clear


def clear_data_caches() -> None:
    load_debit_credit_frame.cache_clear()
    _source_mtime_key.cache_clear()
    try:
        from app.services.gdrs import clear_gdrs_caches

        clear_gdrs_caches()
    except Exception:
        pass
    try:
        from app.services.prescriptions import clear_prescriptions_caches

        clear_prescriptions_caches()
    except Exception:
        pass
    try:
        from app.services.executive_docs import clear_executive_docs_caches

        clear_executive_docs_caches()
    except Exception:
        pass
    try:
        cache_clear()
    except Exception:
        pass


def sync_status() -> dict[str, Any]:
    files = 0
    latest = None
    if WEB_DATA_DIR.is_dir():
        paths = [p for p in WEB_DATA_DIR.rglob("*") if p.is_file()]
        files = len(paths)
        if paths:
            latest = max(p.stat().st_mtime for p in paths)
    return {
        "data_mode": DATA_MODE,
        "web_dir": str(WEB_DATA_DIR),
        "files": files,
        "latest_mtime": latest,
        "ftp_configured": bool(
            __import__("os").environ.get("BI_FTP_HOST")
            and (
                __import__("os").environ.get("BI_FTP_USER")
                or __import__("os").environ.get("FTP_AI_USER")
            )
        ),
        "db": db_status(),
    }


def run_ftp_sync(*, force: bool = False) -> dict[str, Any]:
    """
    FTP → WEB_DATA_DIR (как на ai.conall.ru).
    Не пишет в showcase_data/web — только в каталог webapp (ftp mode).
    """
    if DATA_MODE != "ftp":
        return {
            "ok": False,
            "errors": [
                "WEBAPP_DATA_MODE != ftp. Для клиентских выгрузок задайте "
                "WEBAPP_DATA_MODE=ftp и BI_FTP_* (каталог webapp/data/web)."
            ],
        }

    core = CORE_APP_DIR.resolve()
    if not (core / "ftp_sync.py").is_file():
        return {
            "ok": False,
            "errors": [f"ftp_sync.py не найден в {core}"],
        }
    if str(core) not in sys.path:
        sys.path.insert(0, str(core))

    from ftp_sync import sync_ftp_to_web  # type: ignore
    import inspect

    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    # Safety: never sync into showcase_data/web (public synthetic)
    showcase_web = (Path(__file__).resolve().parents[3] / "showcase_data" / "web").resolve()
    if WEB_DATA_DIR.resolve() == showcase_web:
        return {
            "ok": False,
            "errors": [
                "Отказ: нельзя писать FTP в showcase_data/web. "
                "Укажите SHOWCASE_WEB_DIR=webapp/data/web."
            ],
        }

    kwargs: dict[str, Any] = {}
    params = inspect.signature(sync_ftp_to_web).parameters
    if "force_redownload" in params:
        kwargs["force_redownload"] = force
    if "use_interprocess_lock" in params:
        kwargs["use_interprocess_lock"] = True
    result = sync_ftp_to_web(WEB_DATA_DIR, **kwargs)
    clear_data_caches()
    result["web_dir"] = str(WEB_DATA_DIR)
    result["status"] = sync_status()
    # ftp_sync может вернуть ok=True без ключа; нормализуем
    if "ok" not in result:
        result["ok"] = not bool(result.get("errors"))
    return result


def run_ftp_then_db_ingest(*, force: bool = False) -> dict[str, Any]:
    """Как кнопка admin в [main]: FTP → web/ → load_all_from_web() → web_data.db."""
    ftp = run_ftp_sync(force=force)
    if not ftp.get("ok", False) and DATA_MODE == "ftp":
        # если FTP упал — не продолжаем
        return {
            "ok": False,
            "stage": "ftp",
            "ftp": ftp,
            "ingest": None,
            "status": sync_status(),
            "errors": list(ftp.get("errors") or ["FTP sync failed"]),
        }

    ingest = run_db_ingest()
    clear_data_caches()
    ok = bool(ingest.get("ok"))
    return {
        "ok": ok,
        "stage": "ingest" if ok else ("ingest" if ftp.get("ok", True) else "ftp"),
        "ftp": ftp if DATA_MODE == "ftp" else {"ok": True, "skipped": True, "reason": "not ftp mode"},
        "ingest": ingest,
        "status": sync_status(),
        "errors": list(ingest.get("errors") or []),
    }
