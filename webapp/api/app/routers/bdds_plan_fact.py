from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Query

from app.services.bdds_plan_fact import build_bdds_plan_fact_payload

router = APIRouter(prefix="/api/bdds-plan-fact", tags=["bdds-plan-fact"])


@router.get("")
def bdds_plan_fact_report(
    project: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    view: str = Query("monthly", pattern="^(monthly|cumulative)$"),
):
    return build_bdds_plan_fact_payload(
        project=project,
        date_from=date_from,
        date_to=date_to,
        view=view,
    )
