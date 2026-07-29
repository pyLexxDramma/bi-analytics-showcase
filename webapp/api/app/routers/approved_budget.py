from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.services.approved_budget import build_approved_budget_payload

router = APIRouter(prefix="/api/approved-budget", tags=["approved-budget"])


@router.get("")
def approved_budget_report(
    project: Optional[str] = Query(None, description="Фильтр проекта"),
):
    return build_approved_budget_payload(project=project)
