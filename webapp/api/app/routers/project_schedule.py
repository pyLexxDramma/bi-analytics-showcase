from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.services.project_schedule import build_project_schedule_payload

router = APIRouter(prefix="/api/project-schedule", tags=["project-schedule"])


@router.get("")
def project_schedule_report(
    project: Optional[str] = Query(None, description="Фильтр проекта"),
    level: Optional[str] = Query("4", description="Уровень MSP: 4 или 5"),
    block: Optional[str] = Query(None, description="Функциональный блок"),
    hide_completed: bool = Query(False, description="Скрыть задачи с 100%"),
    only_delay: bool = Query(False, description="Только просрочка по окончанию"),
):
    return build_project_schedule_payload(
        project=project,
        level=level,
        block=block,
        hide_completed=hide_completed,
        only_delay=only_delay,
    )
