from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Query

from app.services.executive_docs import build_executive_docs_payload

router = APIRouter(prefix="/api/executive-docs", tags=["executive-docs"])


@router.get("")
def executive_docs_report(
    project: Optional[str] = Query(None, description="Фильтр проекта (ObjectName)"),
    contractor: Optional[str] = Query(None, description="Фильтр контрагента (CONTR)"),
    date_from: Optional[date] = Query(None, description="Дата создания с"),
    date_to: Optional[date] = Query(None, description="Дата создания по"),
    granularity: str = Query(
        "month",
        description="Гранулярность динамики: day|week|month|quarter|year",
    ),
    hide_overdue_if_signed: bool = Query(
        True,
        description="Не показывать просрочку, если ИД сдана/подписана",
    ),
):
    """Исполнительная документация (TESSA id + task, без предписаний)."""
    return build_executive_docs_payload(
        project=project,
        contractor=contractor,
        date_from=date_from,
        date_to=date_to,
        granularity=granularity,
        hide_overdue_if_signed=hide_overdue_if_signed,
    )
