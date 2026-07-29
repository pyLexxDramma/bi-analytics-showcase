from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from app.config import ADMIN_SYNC_TOKEN, DATA_MODE
from app.services.ftp_ingest import run_ftp_sync, sync_status

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


@router.post("/sync")
def sync_ftp(
    force: bool = False,
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
):
    """Ручной FTP → web (как ежедневный ingest на VPS)."""
    _check_token(authorization, x_admin_token)
    if DATA_MODE != "ftp":
        raise HTTPException(
            status_code=400,
            detail="Включите WEBAPP_DATA_MODE=ftp для синхронизации с FTP.",
        )
    return run_ftp_sync(force=force)
