from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Query, Depends
from app.services.auth_context import require_report_access
from app.services.project_scope import clamp_project_pipe, clamp_projects_list

from app.services.bdr import build_bdr_payload

router = APIRouter(prefix="/api/bdr", tags=["bdr"], dependencies=[Depends(require_report_access("bdr"))])


@router.get("")
def bdr_report(
    user: dict = Depends(require_report_access("bdr")),
    project: Optional[str] = Query(None, description="Устарело: один проект. Предпочтительно projects="),
    projects: Optional[list[str]] = Query(None, description="Multiselect проектов; пусто = все"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    group: str = Query("month", pattern="^(month|quarter|year)$"),
    view: str = Query("monthly", pattern="^(monthly|cumulative)$"),
    hide_zero: Optional[bool] = Query(None),
    show_deviation: bool = Query(False),
):
    selected: list[str] = []
    if projects:
        selected.extend([p for p in projects if p and str(p).strip()])
    elif project and str(project).strip() and str(project).strip() != "Все":
        selected.append(str(project).strip())
    selected = clamp_projects_list(user, selected)
    return build_bdr_payload(
        projects=selected,
        date_from=date_from,
        date_to=date_to,
        group=group,
        view=view,
        hide_zero=hide_zero,
        show_deviation=show_deviation,
    )
