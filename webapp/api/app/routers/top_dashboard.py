from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.services.auth_context import require_report_access
from app.services.project_scope import clamp_projects_list
from app.services.top_dashboard import build_top_dashboard_payload

router = APIRouter(
    prefix="/api/top-dashboard",
    tags=["top-dashboard"],
    dependencies=[Depends(require_report_access("top-dashboard"))],
)


@router.get("")
def top_dashboard_report(
    user: dict = Depends(require_report_access("top-dashboard")),
    project: Optional[str] = Query("all", description="all или id/имя проекта"),
):
    raw = (project or "all").strip() or "all"
    if raw not in {"all", "Все"}:
        scoped = clamp_projects_list(user, [raw])
        if not scoped:
            raw = "__no_access__"
        else:
            raw = scoped[0]
    return build_top_dashboard_payload(project=raw)
