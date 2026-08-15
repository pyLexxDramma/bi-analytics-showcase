from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Depends
from app.services.auth_context import require_report_access
from app.services.project_scope import clamp_projects_list

from app.services.control_points import build_control_points_payload

router = APIRouter(prefix="/api/control-points", tags=["control-points"], dependencies=[Depends(require_report_access("control-points"))])


@router.get("")
def control_points_report(
    user: dict = Depends(require_report_access("control-points")),
    project: Optional[str] = Query(None, description="Устарело: один проект. Предпочтительно projects="),
    projects: Optional[list[str]] = Query(None, description="Multiselect проектов; пусто = все"),
):
    selected = [item for item in (projects or []) if item and item.strip() and item.strip() != "Все"]
    if not selected and project and project.strip() and project.strip() != "Все":
        selected = [project.strip()]
    selected = clamp_projects_list(user, selected)
    return build_control_points_payload(projects=selected)
