from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Depends
from app.services.auth_context import require_report_access
from app.services.project_scope import (
    allowed_projects_for_user,
    clamp_projects_list,
    parse_project_pipe,
)

from app.services.baseline_deviation import build_baseline_deviation_payload

router = APIRouter(prefix="/api/baseline-deviation", tags=["baseline-deviation"], dependencies=[Depends(require_report_access("baseline-deviation"))])


@router.get("")
def baseline_deviation_report(
    user: dict = Depends(require_report_access("baseline-deviation")),
    project: Optional[str] = Query(None, description="Legacy: один проект или A|B"),
    projects: Optional[list[str]] = Query(None, description="Multiselect; пусто = все"),
    block: Optional[str] = Query(None, description="Функциональный блок"),
    building: Optional[str] = Query(None, description="Строение"),
    level: Optional[str] = Query("4", description="Уровень MSP: 4 или 5"),
    reason: Optional[str] = Query(None, description="Категория причины отклонения"),
    show_reasons: bool = Query(
        True,
        description="Показать причины отклонений (макет ур.5)",
    ),
    hide_completed: bool = Query(False, description="Скрыть завершённые 100%"),
    only_covenants: bool = Query(False, description="Только ковенанты"),
    only_neg_end: bool = Query(
        False,
        description="На графике только отклонение окончания < 0",
    ),
    show_dur: bool = Query(True, description="Показать отклонение длительности"),
    label_mode: Optional[str] = Query(
        "name",
        description="Подписи: name | lot",
    ),
):
    selected = [item for item in (projects or []) if item and item.strip() and item.strip() != "Все"]
    if not selected and project and project.strip() and project.strip() != "Все":
        selected = parse_project_pipe(project) or [project.strip()]
    selected = clamp_projects_list(user, selected)
    allowed = allowed_projects_for_user(user)
    if allowed is not None and not selected and not allowed:
        project_arg = "__no_access__"
    else:
        project_arg = "|".join(selected) if selected else None
    return build_baseline_deviation_payload(
        project=project_arg,
        block=block,
        building=building,
        level=level,
        reason=reason,
        show_reasons=show_reasons,
        hide_completed=hide_completed,
        only_covenants=only_covenants,
        only_neg_end=only_neg_end,
        show_dur=show_dur,
        label_mode=label_mode,
    )
