from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Depends
from app.services.auth_context import require_report_access
from app.services.project_scope import clamp_project_pipe, clamp_projects_list

from app.services.gdrs import build_gdrs_payload

router = APIRouter(prefix="/api/gdrs-equipment", tags=["gdrs-equipment"], dependencies=[Depends(require_report_access("gdrs-equipment"))])


@router.get("")
def gdrs_equipment_report(
    user: dict = Depends(require_report_access("gdrs-equipment")),
    projects: Optional[str] = Query(None, description="Проекты через запятую"),
    contractors: Optional[str] = Query(None, description="Контрагенты через запятую"),
    months: Optional[str] = Query(None, description="Месяцы через запятую, напр. Июль 2026"),
    plan_agg: Optional[str] = Query("Среднее за месяц", description="План: Среднее за месяц | N неделя"),
    skud_agg: Optional[str] = Query("Среднее за месяц", description="СКУД: Среднее за месяц | N неделя"),
    dyn_agg: Optional[str] = Query("День", description="Группировка динамики: День|Неделя|Месяц"),
    only_with_plan: bool = Query(False, description="Только с планом"),
):
    project = clamp_project_pipe(user, project)
    if project == "__none__":
        project = "__no_access__"
    return build_gdrs_payload(
        resource_kind="equipment",
        projects=projects,
        contractors=contractors,
        months=months,
        plan_agg=plan_agg,
        skud_agg=skud_agg,
        dyn_agg=dyn_agg,
        only_with_plan=only_with_plan,
    )
