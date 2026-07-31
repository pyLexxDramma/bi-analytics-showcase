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
    return build_baseline_deviation_payload(
        project=project,
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
