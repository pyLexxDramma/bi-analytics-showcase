from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Depends
from app.services.auth_context import require_report_access
from app.services.project_scope import (
    allowed_projects_for_user,
    clamp_projects_list,
    parse_project_pipe,
)

from app.services.deviation_reasons import build_deviation_reasons_payload

router = APIRouter(prefix="/api/deviation-reasons", tags=["deviation-reasons"], dependencies=[Depends(require_report_access("deviation-reasons"))])


@router.get("")
def deviation_reasons_report(
    user: dict = Depends(require_report_access("deviation-reasons")),
    project: Optional[str] = Query(None, description="Legacy: один проект или A|B"),
    projects: Optional[list[str]] = Query(None, description="Multiselect; пусто = все"),
    block: Optional[str] = Query(None, description="Функциональный блок"),
    building: Optional[str] = Query(None, description="Строение"),
    reason: Optional[str] = Query(None, description="Причина отклонения"),
    date_from: Optional[str] = Query(None, description="Начало периода (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Конец периода (YYYY-MM-DD)"),
    top5: bool = Query(False, description="ТОП 5 причин на диаграммах"),
):
    selected = [item for item in (projects or []) if item and item.strip() and item.strip() != "Все"]
    if not selected and project and project.strip() and project.strip() != "Все":
        selected = parse_project_pipe(project) or [project.strip()]
    selected = clamp_projects_list(user, selected)
    allowed = allowed_projects_for_user(user)
    if allowed is not None and not selected and not allowed:
        project_arg = "__no_access__"
    else:
        project_arg = "|".join(selected) if selected else None
    return build_deviation_reasons_payload(
        project=project_arg,
        block=block,
        building=building,
        reason=reason,
        date_from=date_from,
        date_to=date_to,
        top5=top5,
    )
