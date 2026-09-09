# -*- coding: utf-8 -*-
"""ГДРС: режим агрегации «За день» для План и СКУД (day:YYYY-MM-DD)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

CORE = Path(__file__).resolve().parents[3] / "bi-analytics-v-5-main"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

API = Path(__file__).resolve().parents[1]
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

from dashboards.gdrs_resursi import (  # noqa: E402
    GDRS_AGG_MONTH,
    _skud_agg_per_pair,
    gdrs_agg_day_date,
    gdrs_agg_day_display,
    gdrs_agg_day_key,
    gdrs_agg_label_to_key,
    gdrs_agg_week_num,
    gdrs_matrix_show_week_columns,
    gdrs_plan_snapshot_date,
)


def _fact() -> pd.DataFrame:
    """Три дня факта по двум парам проект×контрагент."""
    rows = []
    for day, (a, b) in {
        "2026-07-01": (10.0, 4.0),
        "2026-07-02": (20.0, 0.0),
        "2026-07-03": (30.0, 8.0),
    }.items():
        rows.append(
            {
                "project_name": "Проект А",
                "contractor_name": "Контрагент 1",
                "vid_resursa": "Рабочие",
                "date": day,
                "fact": a,
                "__source_file": "other_31-07-2026_07-00_resursi.csv",
            }
        )
        rows.append(
            {
                "project_name": "Проект А",
                "contractor_name": "Контрагент 2",
                "vid_resursa": "Рабочие",
                "date": day,
                "fact": b,
                "__source_file": "other_31-07-2026_07-00_resursi.csv",
            }
        )
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


def test_day_key_roundtrip():
    key = gdrs_agg_day_key("2026-09-15")
    assert key == "day:2026-09-15"
    assert gdrs_agg_day_date(key) == pd.Timestamp("2026-09-15")
    assert gdrs_agg_day_display(key) == "За день 15.09.2026"
    # Дневной ключ не путается с недельным и не ломает разбор подписей.
    assert gdrs_agg_week_num(key) is None
    assert gdrs_agg_day_date(GDRS_AGG_MONTH) is None
    assert gdrs_agg_day_date("week:2") is None
    assert gdrs_agg_label_to_key("Среднее за месяц") == GDRS_AGG_MONTH
    assert gdrs_agg_day_key("мусор") == GDRS_AGG_MONTH


def test_skud_day_is_source_value_not_average():
    fact = _fact()
    lo, hi = pd.Timestamp("2026-07-01"), pd.Timestamp("2026-07-31")

    day = _skud_agg_per_pair(
        fact, gdrs_agg_day_key("2026-07-03"), date_from=lo, date_to=hi
    ).set_index("contractor_name")["skud_val"]
    assert day["Контрагент 1"] == 30.0
    assert day["Контрагент 2"] == 8.0

    # Среднее за месяц по тем же данным — другое число (3 дня в знаменателе).
    month = _skud_agg_per_pair(
        fact, GDRS_AGG_MONTH, date_from=lo, date_to=hi
    ).set_index("contractor_name")["skud_val"]
    assert month["Контрагент 1"] == 20.0


def test_skud_day_without_source_rows_is_zero():
    fact = _fact()
    vals = _skud_agg_per_pair(
        fact,
        gdrs_agg_day_key("2026-07-10"),
        date_from=pd.Timestamp("2026-07-01"),
        date_to=pd.Timestamp("2026-07-31"),
    )
    # Пары сохраняются (список контрагентов стабилен), значения — нули.
    assert set(vals["contractor_name"]) == {"Контрагент 1", "Контрагент 2"}
    assert list(vals["skud_val"]) == [0.0, 0.0]


def test_plan_snapshot_is_selected_day():
    snap = gdrs_plan_snapshot_date(
        _fact(),
        vid="Рабочие",
        date_from=pd.Timestamp("2026-07-01"),
        date_to=pd.Timestamp("2026-07-31"),
        plan_agg=gdrs_agg_day_key("2026-07-15"),
    )
    assert snap == pd.Timestamp("2026-07-15")


def test_week_columns_off_in_day_mode():
    lo, hi = pd.Timestamp("2026-07-01"), pd.Timestamp("2026-07-31")
    day = gdrs_agg_day_key("2026-07-15")
    assert gdrs_matrix_show_week_columns(GDRS_AGG_MONTH, GDRS_AGG_MONTH, date_from=lo, date_to=hi)
    assert not gdrs_matrix_show_week_columns(day, GDRS_AGG_MONTH, date_from=lo, date_to=hi)
    assert not gdrs_matrix_show_week_columns(GDRS_AGG_MONTH, day, date_from=lo, date_to=hi)


def test_service_day_parsing_and_clamp():
    from app.services.gdrs import clamp_day_to_period, parse_day

    assert parse_day("2026-09-15") == pd.Timestamp("2026-09-15")
    assert parse_day("15.09.2026") == pd.Timestamp("2026-09-15")
    assert parse_day("") is None
    assert parse_day("не дата") is None

    lo, hi = pd.Timestamp("2026-09-01"), pd.Timestamp("2026-09-30")
    inside, moved = clamp_day_to_period(pd.Timestamp("2026-09-15"), lo, hi)
    assert inside == pd.Timestamp("2026-09-15") and not moved
    after, moved_after = clamp_day_to_period(pd.Timestamp("2026-10-05"), lo, hi)
    assert after == hi and moved_after
    before, moved_before = clamp_day_to_period(pd.Timestamp("2026-08-20"), lo, hi)
    assert before == lo and moved_before
