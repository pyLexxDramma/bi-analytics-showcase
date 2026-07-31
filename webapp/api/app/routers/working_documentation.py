from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.services.documentation import build_working_documentation_payload

router = APIRouter(prefix="/api/working-documentation", tags=["working-documentation"])


@router.get("")
def working_documentation_report(
    project: Optional[str] = Query(None, description="Проекты через | или Все"),
    section: Optional[str] = Query(None, description="Разделы (шифр+имя) через |"),
    status: Optional[str] = Query(None, description="Статусы через |"),
    period_mode: Optional[str] = Query(
        "Весь период (за всё время)",
        description="Весь период (за всё время) | Выбор диапазона дат",
    ),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    metric_mode: Optional[str] = Query(
        "Количество разделов",
        description="Количество разделов | % от общего объёма",
    ),
    show_forecast: Optional[bool] = Query(True, description="Показать прогнозную дату"),
    view_mode: Optional[str] = Query("project", description="project|section"),
    tab: Optional[str] = Query("main", description="main|delay"),
):
    return build_working_documentation_payload(
        project=project,
        section=section,
        status=status,
        period_mode=period_mode,
        date_from=date_from,
        date_to=date_to,
        metric_mode=metric_mode,
        show_forecast=show_forecast,
        view_mode=view_mode,
        tab=tab,
    )
