from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Depends
from app.services.auth_context import require_report_access

from app.services.project_schedule import build_project_schedule_payload

router = APIRouter(prefix="/api/project-schedule", tags=["project-schedule"], dependencies=[Depends(require_report_access("project-schedule"))])


@router.get("")
def project_schedule_report(
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
