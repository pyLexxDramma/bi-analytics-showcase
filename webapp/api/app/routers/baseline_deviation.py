from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.services.baseline_deviation import build_baseline_deviation_payload

router = APIRouter(prefix="/api/baseline-deviation", tags=["baseline-deviation"])


@router.get("")
def baseline_deviation_report(
    project: Optional[str] = Query(None, description="Фильтр проекта"),
    block: Optional[str] = Query(None, description="Функциональный блок"),
    building: Optional[str] = Query(None, description="Строение"),
    level: Optional[str] = Query("4", description="Уровень MSP: 4 или 5"),
):
    return build_baseline_deviation_payload(
        project=project,
        block=block,
        building=building,
        level=level,
    )
