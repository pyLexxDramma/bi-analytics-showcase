from __future__ import annotations

from fastapi import APIRouter

from app.services.versions import list_versions

router = APIRouter(prefix="/api", tags=["versions"])


@router.get("/versions")
def versions():
    """Список снимков данных для селектора «Версия данных» (чтение — без токена)."""
    return list_versions()
