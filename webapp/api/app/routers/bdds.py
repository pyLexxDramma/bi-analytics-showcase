from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Query

from app.services.bdds import build_bdds_payload

router = APIRouter(prefix="/api/bdds", tags=["bdds"])


@router.get("")
def bdds_report(
    project: Optional[str] = Query(None, description="Устарело: один проект. Предпочтительно projects="),
    projects: Optional[list[str]] = Query(None, description="Multiselect проектов; пусто = все"),
    date_from: Optional[date] = Query(None, description="Диапазон по «Конец план»"),
    date_to: Optional[date] = Query(None),
    group: str = Query("month", pattern="^(month|quarter|year)$", description="Группировать по"),
    view: str = Query("monthly", pattern="^(monthly|cumulative)$", description="Представление"),
    hide_zero: Optional[bool] = Query(
        None,
        description="Скрывать месяцы, где план и факт равны 0 (по умолчанию — когда выбраны все проекты)",
    ),
    show_deviation: bool = Query(False, description="Показывать отклонение на графике"),
):
    selected: list[str] = []
    if projects:
        selected.extend([p for p in projects if p and str(p).strip()])
    elif project and str(project).strip() and str(project).strip() != "Все":
        selected.append(str(project).strip())
    return build_bdds_payload(
        projects=selected,
        date_from=date_from,
        date_to=date_to,
        group=group,
        view=view,
        hide_zero=hide_zero,
        show_deviation=show_deviation,
    )
