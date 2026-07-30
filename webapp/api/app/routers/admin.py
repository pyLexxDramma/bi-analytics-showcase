from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from app.config import ADMIN_SYNC_TOKEN, DATA_MODE
from app.services.db_ingest import db_status, run_db_ingest
from app.services.ftp_ingest import (
    clear_data_caches,
    run_ftp_sync,
    run_ftp_then_db_ingest,
    sync_status,
)
from app.services.jobs import get_job, list_jobs, start_job
from app.services.report_cache import cache_clear
from app.services.versions import activate_version

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _check_token(authorization: str | None, x_admin_token: str | None) -> None:
    if not ADMIN_SYNC_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="WEBAPP_ADMIN_TOKEN не задан — sync отключён.",
        )
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif x_admin_token:
        token = x_admin_token.strip()
    if token != ADMIN_SYNC_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/data-status")
def data_status():
    return sync_status()


@router.get("/jobs")
def jobs_list(
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
):
    _check_token(authorization, x_admin_token)
    return {"items": list_jobs()}


@router.get("/jobs/{job_id}")
def job_status(
    job_id: str,
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
):
    _check_token(authorization, x_admin_token)
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.post("/sync")
def sync_ftp(
    force: bool = False,
    background: bool = True,
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
):
    """FTP → web → web_data.db (как admin в [main]). По умолчанию в фоне (анти-502)."""
    _check_token(authorization, x_admin_token)
    if DATA_MODE != "ftp":
        raise HTTPException(
            status_code=400,
            detail="Включите WEBAPP_DATA_MODE=ftp для синхронизации с FTP. "
            "Для synthetic: POST /api/admin/ingest.",
        )
    if background:
        job_id = start_job("ftp_ingest", lambda: run_ftp_then_db_ingest(force=force))
        return {"ok": True, "async": True, "job_id": job_id, "status": sync_status()}
    return run_ftp_then_db_ingest(force=force)


@router.post("/sync-ftp-only")
def sync_ftp_only(
    force: bool = False,
    background: bool = True,
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
):
    """Только FTP → web/ без БД."""
    _check_token(authorization, x_admin_token)
    if DATA_MODE != "ftp":
        raise HTTPException(
            status_code=400,
            detail="Включите WEBAPP_DATA_MODE=ftp для синхронизации с FTP.",
        )
    if background:
        job_id = start_job("ftp_only", lambda: run_ftp_sync(force=force))
        return {"ok": True, "async": True, "job_id": job_id, "status": sync_status()}
    return run_ftp_sync(force=force)


@router.post("/ingest")
def ingest_web_to_db(
    background: bool = True,
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
):
    """web/ → web_data.db (без FTP). Работает в synthetic и ftp."""
    _check_token(authorization, x_admin_token)

    def _run() -> dict:
        result = run_db_ingest()
        clear_data_caches()
        result["status"] = sync_status()
        return result

    if background:
        job_id = start_job("ingest", _run)
        return {
            "ok": True,
            "async": True,
            "job_id": job_id,
            "db": db_status(),
            "status": sync_status(),
        }
    return _run()


@router.post("/versions/{version_id}/activate")
def activate_data_version(
    version_id: int,
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
):
    """Переключение активного снимка данных (селектор «Версия данных» в сайдбаре)."""
    _check_token(authorization, x_admin_token)
    result = activate_version(version_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "activate failed")
    # ключи disk-кэша включают mtime БД, поэтому чистим только in-process кэши
    clear_data_caches()
    return result


@router.post("/cache-clear")
def clear_caches(
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
):
    _check_token(authorization, x_admin_token)
    n = cache_clear()
    clear_data_caches()
    return {"ok": True, "report_cache_files_removed": n}

