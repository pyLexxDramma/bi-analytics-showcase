# -*- coding: utf-8 -*-
"""График динамики ПД: срез осн. ПД + «Раздел», без корректировок, обрыв линий."""
from __future__ import annotations

import pandas as pd

from app.services.project_documentation import (
    _is_issuance_pd_stage,
    _issuance_row_mask,
    _merge_pd_dynamics_series,
    _pd_stage_ancestor_labels,
    _parent_is_pd_stage,
    _splice_pd_forecast_from_fact,
)


def test_issuance_stage_allowlist() -> None:
    assert _is_issuance_pd_stage("Этап . Проектная документация") is True
    assert _is_issuance_pd_stage("Этап. ПРОЕКТНАЯ И РАБОЧАЯ ДОКУМЕНТАЦИЯ ПО ГАЗОСНАБЖЕНИЮ") is True
    assert _is_issuance_pd_stage("Этап. ПРИМЫКАНИЕ К УЛИЧНО-ДОРОЖНОЙ СЕТИ ") is True
    assert _is_issuance_pd_stage("Этап . КОРРЕКТИРОВКА ПРОЕКТНЫХ РАБОТ СТАДИИ П ") is False
    assert (
        _is_issuance_pd_stage(
            "Этап . ОБЩЕСТРОИТЕЛЬНАЯ ЭКСПЕРТИЗА ПРОЕКТНОЙ ДОКУМЕНТАЦИИ, ПОЛУЧЕНИЕ РАЗРЕШЕНИЯ НА СТРОИТЕЛЬСТВО"
        )
        is False
    )
    assert (
        _is_issuance_pd_stage(
            "Этап. КОРРЕКТИРОВКА. ОБЩЕСТРОИТЕЛЬНАЯ ЭКСПЕРТИЗА ПРОЕКТНОЙ ДОКУМЕНТАЦИИ"
        )
        is False
    )
    assert _is_issuance_pd_stage("Этап.Рабочая документация") is False
    assert _is_issuance_pd_stage("") is False


def test_issuance_mask_keeps_razdel_drops_tz_gas_correction() -> None:
    """Дмитровский #4: 17 «Раздел» осн. ПД; ТЗ/ТБЭ, газ (даже с «Раздел»), корр. — нет."""
    df = pd.DataFrame(
        {
            "level": [5, 5, 5, 5, 5, 5, 5, 5],
            "task name": [
                'Раздел 1 "ПЗ"',
                'Раздел 2 "СПОЗУ"',
                "ЗАДАНИЕ НА ПРОЕКТИРОВАНИЕ",
                'Проект "Требования к обеспечению безопасной эксплуатации объекта"',
                'Раздел 1 "ПЗ"',
                "Проектная документация ГСН (внеплощадочная сеть) ТП ЧАСТЬ",
                'Разработка ГСВ, в том числе Раздел 5.6. "Система газоснабжения"',
                "ПРИМЫКАНИЕ К УДС",
            ],
        },
        index=[10, 11, 12, 13, 14, 15, 16, 17],
    )
    stage = pd.Series(
        [
            "Этап . Проектная документация",
            "Этап . Проектная документация",
            "Этап . Проектная документация",
            "Этап . Проектная документация",
            "Этап . КОРРЕКТИРОВКА ПРОЕКТНЫХ РАБОТ СТАДИИ П ",
            "Этап. ПРОЕКТНАЯ И РАБОЧАЯ ДОКУМЕНТАЦИЯ ПО ГАЗОСНАБЖЕНИЮ",
            "Этап. ПРОЕКТНАЯ И РАБОЧАЯ ДОКУМЕНТАЦИЯ ПО ГАЗОСНАБЖЕНИЮ",
            "Этап. ПРИМЫКАНИЕ К УЛИЧНО-ДОРОЖНОЙ СЕТИ ",
        ],
        index=df.index,
    )
    cipher_ok = pd.Series(
        [True, True, True, True, True, True, True, False],
        index=df.index,
    )
    mask = _issuance_row_mask(
        level=df["level"],
        cipher_ok=cipher_ok,
        stage_by_index=stage,
        names=df["task name"],
    )
    assert list(mask.tolist()) == [True, True, False, False, False, False, False, False]


def test_ancestor_does_not_skip_correction_to_main_pd() -> None:
    """Если корректировка вложена в осн. ПД — ближайший этап остаётся корректировкой."""
    from app.services.core_bridge import ensure_core_path

    ensure_core_path()
    df = pd.DataFrame(
        {
            "level structure": [2, 3, 4],
            "task name": [
                "Этап . Проектная документация",
                "Этап . КОРРЕКТИРОВКА ПРОЕКТНЫХ РАБОТ СТАДИИ П ",
                'Раздел 3 "АР"',
            ],
        }
    )
    stage = _pd_stage_ancestor_labels(
        df,
        "level structure",
        "task name",
        is_stage=lambda n: _parent_is_pd_stage(n) or _is_issuance_pd_stage(n),
    )
    assert _is_issuance_pd_stage(stage.iloc[2]) is False
    assert "корректиров" in str(stage.iloc[2]).casefold()


def test_ancestor_attaches_gas_children() -> None:
    from app.services.core_bridge import ensure_core_path

    ensure_core_path()
    df = pd.DataFrame(
        {
            "level structure": [2, 3],
            "task name": [
                "Этап. ПРОЕКТНАЯ И РАБОЧАЯ ДОКУМЕНТАЦИЯ ПО ГАЗОСНАБЖЕНИЮ",
                "Проектная документация ГСН (внеплощадочная сеть) ТП ЧАСТЬ",
            ],
        }
    )
    stage = _pd_stage_ancestor_labels(
        df,
        "level structure",
        "task name",
        is_stage=lambda n: _parent_is_pd_stage(n) or _is_issuance_pd_stage(n),
    )
    assert _is_issuance_pd_stage(stage.iloc[1]) is True


def test_dynamics_stops_at_last_date_of_each_series() -> None:
    """Синяя до мая, рыжая до марта, зелёная до января — без хвоста к «сегодня»."""
    plan = pd.DataFrame(
        {
            "Дата": [pd.Timestamp("2025-03-01"), pd.Timestamp("2025-05-01")],
            "Количество": [19.0, 22.0],
        }
    )
    fact = pd.DataFrame(
        {"Дата": [pd.Timestamp("2025-01-01")], "Количество": [19.0]}
    )
    forecast = pd.DataFrame(
        {
            "Дата": [pd.Timestamp("2025-01-01"), pd.Timestamp("2025-03-01")],
            "Количество": [19.0, 22.0],
        }
    )
    rows = _merge_pd_dynamics_series(plan, fact, forecast)
    by = {r["period"]: r for r in rows}
    assert "2026-09-01" not in by
    assert max(by) == "2025-05-01"
    jan = by["2025-01-01"]
    assert jan["fact"] == 19.0
    assert jan["forecast"] == 19.0
    assert jan["plan_bp"] is None
    mar = by["2025-03-01"]
    assert mar["plan_bp"] == 19.0
    assert mar["forecast"] == 22.0
    assert mar["fact"] is None
    may = by["2025-05-01"]
    assert may["plan_bp"] == 22.0
    assert may["forecast"] is None
    assert may["fact"] is None


def test_forecast_starts_from_last_fact_remaining_only() -> None:
    """Рыжая от конца зелёной: только % ≠ 100; синяя не протягивается."""
    plan = pd.DataFrame(
        {
            "Дата": [pd.Timestamp("2025-03-01"), pd.Timestamp("2025-05-01")],
            "Количество": [19.0, 22.0],
        }
    )
    fact = pd.DataFrame({"Дата": [pd.Timestamp("2025-01-01")], "Количество": [19.0]})
    rows = _merge_pd_dynamics_series(plan, fact, pd.DataFrame())
    remaining = pd.Series(
        [pd.Timestamp("2025-03-31"), pd.Timestamp("2025-03-31"), pd.Timestamp("2025-03-31")]
    )
    mask = pd.Series([True, True, True])
    rows = _splice_pd_forecast_from_fact(
        rows,
        remaining_dates=remaining,
        remaining_mask=mask,
        gran_key="month",
    )
    by = {r["period"]: r for r in rows}
    jan = by["2025-01-01"]
    assert jan["fact"] == 19.0
    assert jan["forecast"] == 19.0
    mar = by["2025-03-01"]
    assert mar["forecast"] == 22.0
    assert mar["fact"] is None
    assert mar["plan_bp"] == 19.0
    may = by["2025-05-01"]
    assert may["plan_bp"] == 22.0
    assert may["forecast"] is None
    assert "2026-10-01" not in by


def test_forecast_absent_when_all_complete() -> None:
    """Ленинский: все 100% — рыжей дальше факта нет, синяя обрывается на своей дате."""
    plan = pd.DataFrame(
        {"Дата": [pd.Timestamp("2025-03-01")], "Количество": [22.0]}
    )
    fact = pd.DataFrame(
        {
            "Дата": [pd.Timestamp("2025-03-01"), pd.Timestamp("2026-05-01")],
            "Количество": [3.0, 22.0],
        }
    )
    rows = _merge_pd_dynamics_series(plan, fact, pd.DataFrame())
    rows = _splice_pd_forecast_from_fact(
        rows,
        remaining_dates=pd.Series(dtype="datetime64[ns]"),
        remaining_mask=pd.Series(dtype=bool),
        gran_key="month",
    )
    by = {r["period"]: r for r in rows}
    assert max(by) == "2026-05-01"
    assert by["2025-03-01"]["plan_bp"] == 22.0
    assert by["2026-05-01"]["plan_bp"] is None
    assert by["2026-05-01"]["fact"] == 22.0
    assert all(r["forecast"] is None for r in rows)
    assert "2026-10-01" not in by
