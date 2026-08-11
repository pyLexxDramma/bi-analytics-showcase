from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Depends
from app.services.auth_context import require_report_access

from app.services.developer_projects import build_developer_projects_payload

router = APIRouter(prefix="/api/developer-projects", tags=["developer-projects"], dependencies=[Depends(require_report_access("developer-projects"))])


@router.get("")
def developer_projects_report(
    project: Optional[str] = Query(
        None,
        description="Устарело: один проект. Предпочтительно projects=",
    ),
    projects: Optional[list[str]] = Query(
        None,
        description="Multiselect проектов (как [main]); пусто = все",
    ),
):
    selected: list[str] = []
    if projects:
        selected.extend([p for p in projects if p and str(p).strip()])
    elif project and str(project).strip() and str(project).strip() != "Все":
        selected.append(str(project).strip())
    return build_developer_projects_payload(projects=selected)
