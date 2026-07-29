from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.services.gdrs import build_gdrs_payload

router = APIRouter(prefix="/api/gdrs-equipment", tags=["gdrs-equipment"])


@router.get("")
def gdrs_equipment_report(
    projects: Optional[str] = Query(None, description="Проекты через запятую"),
    contractors: Optional[str] = Query(None, description="Контрагенты через запятую"),
    months: Optional[str] = Query(None, description="Месяцы через запятую, напр. Июль 2026"),
    plan_agg: Optional[str] = Query("Среднее за месяц", description="План: Среднее за месяц | N неделя"),
    skud_agg: Optional[str] = Query("Среднее за месяц", description="СКУД: Среднее за месяц | N неделя"),
):
    return build_gdrs_payload(
        resource_kind="equipment",
        projects=projects,
        contractors=contractors,
        months=months,
        plan_agg=plan_agg,
        skud_agg=skud_agg,
    )
