from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Depends
from app.services.auth_context import require_report_access
from app.services.project_scope import clamp_project_pipe, clamp_projects_list

from app.services.deviation_reasons import build_deviation_reasons_payload

router = APIRouter(prefix="/api/deviation-reasons", tags=["deviation-reasons"], dependencies=[Depends(require_report_access("deviation-reasons"))])


@router.get("")
def deviation_reasons_report(
    user: dict = Depends(require_report_access("deviation-reasons")),
    project: Optional[str] = Query(None, description="Фильтр проекта"),
    block: Optional[str] = Query(None, description="Функциональный блок"),
    building: Optional[str] = Query(None, description="Строение"),
    reason: Optional[str] = Query(None, description="Причина отклонения"),
    date_from: Optional[str] = Query(None, description="Начало периода (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Конец периода (YYYY-MM-DD)"),
    top5: bool = Query(False, description="ТОП 5 причин на диаграммах"),
):
    project = clamp_project_pipe(user, project)
    if project == "__none__":
        project = "__no_access__"
    return build_deviation_reasons_payload(
        project=project,
        block=block,
        building=building,
        reason=reason,
        date_from=date_from,
        date_to=date_to,
        top5=top5,
    )
