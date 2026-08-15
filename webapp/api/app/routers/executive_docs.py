from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Query, Depends
from app.services.auth_context import require_report_access
from app.services.project_scope import (
    allowed_projects_for_user,
    clamp_projects_list,
    parse_project_pipe,
)

from app.services.executive_docs_db import build_executive_docs_payload

router = APIRouter(prefix="/api/executive-docs", tags=["executive-docs"], dependencies=[Depends(require_report_access("executive-docs"))])


@router.get("")
def executive_docs_report(
    user: dict = Depends(require_report_access("executive-docs")),
    project: Optional[str] = Query(None, description="Legacy: один проект или A|B"),
    projects: Optional[list[str]] = Query(None, description="Multiselect; пусто = все"),
    contractor: Optional[str] = Query(None, description="Фильтр контрагента (CONTR)"),
    doc_kind: Optional[str] = Query(None, description="Группа вида документа ИД"),
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
    selected = [item for item in (projects or []) if item and item.strip() and item.strip() != "Все"]
    if not selected and project and project.strip() and project.strip() != "Все":
        selected = parse_project_pipe(project) or [project.strip()]
    selected = clamp_projects_list(user, selected)
    allowed = allowed_projects_for_user(user)
    if allowed is not None and not selected and not allowed:
        project_arg = "__no_access__"
    else:
        project_arg = "|".join(selected) if selected else None
    return build_executive_docs_payload(
        project=project_arg,
        contractor=contractor,
        doc_kind=doc_kind,
        date_from=date_from,
        date_to=date_to,
        granularity=granularity,
        hide_overdue_if_signed=hide_overdue_if_signed,
    )
