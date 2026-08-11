from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Depends
from app.services.auth_context import require_report_access
from app.services.project_scope import clamp_project_pipe, clamp_projects_list

from app.services.project_schedule import build_project_schedule_payload

router = APIRouter(prefix="/api/project-schedule", tags=["project-schedule"], dependencies=[Depends(require_report_access("project-schedule"))])


@router.get("")
def project_schedule_report(
    user: dict = Depends(require_report_access("project-schedule")),
    project: Optional[str] = Query(None, description="Фильтр проекта"),
    level: Optional[str] = Query("Верхний уровень", description="Верхний / Детальный уровень"),
    block: Optional[str] = Query(None, description="Функциональный блок"),
    building: Optional[str] = Query(None, description="Строение"),
    hide_completed: bool = Query(False, description="Скрыть задачи с 100%"),
    only_delay: bool = Query(False, description="Только просрочка по окончанию"),
    show_reasons: bool = Query(False, description="Показать причины отклонений"),
    show_lots: bool = Query(False, description="Отображать в лотах"),
    label_pct: bool = Query(False, description="Показать % на полосах"),
):
    project = clamp_project_pipe(user, project)
    if project == "__none__":
        project = "__no_access__"
    return build_project_schedule_payload(
        project=project,
        level=level,
        block=block,
        building=building,
        hide_completed=hide_completed,
        only_delay=only_delay,
        show_reasons=show_reasons,
        show_lots=show_lots,
        label_pct=label_pct,
    )
