from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Depends
from app.services.auth_context import require_report_access
from app.services.project_scope import clamp_project_pipe, clamp_projects_list

from app.services.control_points import build_control_points_payload

router = APIRouter(prefix="/api/control-points", tags=["control-points"], dependencies=[Depends(require_report_access("control-points"))])


@router.get("")
def control_points_report(
    user: dict = Depends(require_report_access("control-points")),
    project: Optional[str] = Query(None, description="Фильтр проекта"),
):
    project = clamp_project_pipe(user, project)
    if project == "__none__":
        project = "__no_access__"
    return build_control_points_payload(project=project)
