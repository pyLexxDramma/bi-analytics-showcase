from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse

from app.config import ADMIN_SYNC_TOKEN, DATA_MODE
from app.services.auth_context import require_active_user
from app.services.data_freshness import attach_freshness, ensure_fresh
from app.services.db_ingest import db_status, run_db_ingest
from app.services.ftp_ingest import (
    clear_data_caches,
    run_ftp_sync,
    run_ftp_then_db_ingest,
    sync_status,
)
from app.services.jobs import get_job, list_jobs, start_job
from app.services.report_cache import cache_clear
from app.services.snapshot_export import (
    build_latest_snapshot_archive,
    latest_archive_path,
    snapshot_info,
)
from app.services.users_bridge import import_auth
from app.services.versions import activate_version

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _token_ok(x_admin_token: str | None) -> bool:
    if not ADMIN_SYNC_TOKEN:
        return False
    token = (x_admin_token or "").strip()
    return bool(token) and token == ADMIN_SYNC_TOKEN


def _check_ops_access(
    authorization: str | None,
    x_admin_token: str | None,
    *,
    need_ftp: bool = False,
) -> None:
    if _token_ok(x_admin_token):
        return
    user = require_active_user(authorization)
    auth = import_auth()
    role = user.get("role")
    if need_ftp:
        if not auth.user_can_ftp_sync(role):
            raise HTTPException(
                status_code=403,
                detail="FTP-синк доступен ролям admin / superadmin / analyst.",
            )
        return
    # activate version / jobs: любой активный пользователь сессии
    return


@router.get("/data-status")
def data_status():
    return attach_freshness(sync_status())


@router.post("/ensure-fresh")
def ensure_data_fresh(
    force: bool = False,
    background: bool = True,
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
):
    """Проверить свежесть; при устаревании запустить FTP→БД (cooldown)."""
    _check_ops_access(authorization, x_admin_token)
    return ensure_fresh(force=force, background=background)


@router.get("/jobs")
def jobs_list(
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
):
    _check_ops_access(authorization, x_admin_token)
    return {"items": list_jobs()}


@router.get("/jobs/{job_id}")
def job_status(
    job_id: str,
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
):
    _check_ops_access(authorization, x_admin_token)
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
    _check_ops_access(authorization, x_admin_token, need_ftp=True)
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
    _check_ops_access(authorization, x_admin_token, need_ftp=True)
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
    _check_ops_access(authorization, x_admin_token, need_ftp=True)

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
    _check_ops_access(authorization, x_admin_token)
    result = activate_version(version_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "activate failed")
    clear_data_caches()
    cache_clear()
    return result


@router.post("/cache-clear")
def clear_caches(
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
):
    _check_ops_access(authorization, x_admin_token)
    n = cache_clear()
    clear_data_caches()
    return {"ok": True, "report_cache_files_removed": n}


@router.get("/snapshot-export")
def get_snapshot_export_info(
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
):
    """Метаданные свежего слепка (дата, число файлов, готов ли архив)."""
    _check_ops_access(authorization, x_admin_token, need_ftp=True)
    return snapshot_info()


@router.post("/snapshot-export")
def rebuild_snapshot_export(
    force: bool = True,
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
):
    """Пересобрать tar.gz свежей даты из web/."""
    _check_ops_access(authorization, x_admin_token, need_ftp=True)
    result = build_latest_snapshot_archive(force=force)
    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error") or "Не удалось собрать слепок",
        )
    return result


@router.get("/snapshot-export/download")
def download_snapshot_export(
    rebuild: bool = False,
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
):
    """
    Скачать свежий слепок FTP (файлы самой новой даты).
    Доступен всегда под логином admin/analyst — архив обновляется после FTP-синка.
    """
    _check_ops_access(authorization, x_admin_token, need_ftp=True)
    info = snapshot_info()
    need_rebuild = (
        rebuild
        or not info.get("archive_ready")
        or info.get("archive_snapshot_date") != info.get("snapshot_date")
    )
    if need_rebuild:
        built = build_latest_snapshot_archive(force=True)
        if not built.get("ok"):
            raise HTTPException(
                status_code=400,
                detail=built.get("error") or "Не удалось собрать слепок",
            )
        filename = str(built.get("archive_name") or "showcase_ftp_snapshot.tar.gz")
    else:
        filename = str(info.get("archive_name") or "showcase_ftp_snapshot.tar.gz")

    path = latest_archive_path()
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Архив слепка не найден")
    return FileResponse(
        path,
        media_type="application/gzip",
        filename=filename,
    )
