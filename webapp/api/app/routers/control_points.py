from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Depends
from app.services.auth_context import require_report_access

from app.services.control_points import build_control_points_payload

router = APIRouter(prefix="/api/control-points", tags=["control-points"], dependencies=[Depends(require_report_access("control-points"))])


@router.get("")
def control_points_report(
    project: Optional[str] = Query(None, description="Фильтр проекта"),
):
    return build_control_points_payload(project=project)
