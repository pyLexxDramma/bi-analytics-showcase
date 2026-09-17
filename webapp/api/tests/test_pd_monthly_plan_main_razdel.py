# -*- coding: utf-8 -*-
"""Месячный план ПД: только осн. этап + «Раздел» в названии (вариант 1 / Дмитровский)."""
from __future__ import annotations

import pandas as pd

from app.services.project_documentation import (
    _has_razdel_in_task_name,
    _is_main_pd_stage_only,
    _monthly_chart_row_mask,
)


def test_main_pd_stage_excludes_correction_and_expertise() -> None:
    assert _is_main_pd_stage_only("Этап . Проектная документация") is True
    assert _is_main_pd_stage_only("Проектная документация") is True
    assert _is_main_pd_stage_only("Этап . КОРРЕКТИРОВКА ПРОЕКТНЫХ РАБОТ СТАДИИ П") is False
    assert _is_main_pd_stage_only("Этап . Экспертиза ПД") is False
    assert _is_main_pd_stage_only("") is False


def test_razdel_name_filter() -> None:
    assert _has_razdel_in_task_name('Раздел 1 "Пояснительная записка"') is True
    assert _has_razdel_in_task_name("ЗАДАНИЕ НА ПРОЕКТИРОВАНИЕ") is False
    assert (
        _has_razdel_in_task_name(
            'Проект "Требования к обеспечению безопасной эксплуатации объекта"'
        )
        is False
    )


def test_monthly_chart_mask_keeps_main_razdel_only() -> None:
    """Как Дмитровский: 19 осн. + 18 корр. → в график плана 17 (без ТЗ/ТБЭ)."""
    df = pd.DataFrame(
        {
            "task name": [
                'Раздел 1 "ПЗ"',
                'Раздел 2 "СПОЗУ"',
                "ЗАДАНИЕ НА ПРОЕКТИРОВАНИЕ",
                'Проект "Требования..."',
                'Раздел 1 "ПЗ"',
                'Раздел 3 "АР"',
            ],
        },
        index=[10, 11, 12, 13, 14, 15],
    )
    stage = pd.Series(
        [
            "Этап . Проектная документация",
            "Этап . Проектная документация",
            "Этап . Проектная документация",
            "Этап . Проектная документация",
            "Этап . КОРРЕКТИРОВКА ПРОЕКТНЫХ РАБОТ СТАДИИ П",
            "Этап . КОРРЕКТИРОВКА ПРОЕКТНЫХ РАБОТ СТАДИИ П",
        ],
        index=df.index,
    )
    mask = _monthly_chart_row_mask(df, stage_by_index=stage, name_col="task name")
    assert int(mask.sum()) == 2
    assert mask.loc[10] and mask.loc[11]
    assert not mask.loc[12] and not mask.loc[13]
    assert not mask.loc[14] and not mask.loc[15]
