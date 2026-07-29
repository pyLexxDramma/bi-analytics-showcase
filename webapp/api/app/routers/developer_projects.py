from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.services.developer_projects import build_developer_projects_payload

router = APIRouter(prefix="/api/developer-projects", tags=["developer-projects"])


@router.get("")
def developer_projects_report(
    project: Optional[str] = Query(None, description="Фильтр проекта"),
):
    return build_developer_projects_payload(project=project)
