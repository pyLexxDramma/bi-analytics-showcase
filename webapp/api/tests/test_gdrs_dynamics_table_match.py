# -*- coding: utf-8 -*-
"""ГДРС: точка «Динамики» = «Итого» таблицы при тех же фильтрах (тикет 23)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

import pandas as pd

CORE = Path(__file__).resolve().parents[3] / "bi-analytics-v-5-main"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

API = Path(__file__).resolve().parents[1]
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

from dashboards.gdrs_resursi import (  # noqa: E402
    GDRS_AGG_MONTH,
    build_main_table,
    gdrs_agg_day_key,
    gdrs_dynamics_bucket_snapshot_end,
    gdrs_dynamics_build_day_series_matching_table,
    gdrs_dynamics_build_series,
    gdrs_dynamics_month_points_from_table_totals,
    gdrs_plan_snapshot_date,
    gdrs_week_numbers_in_period,
    week_end_in_filtered_fact,
)


def _fact_july() -> pd.DataFrame:
    """Факт с дробными значениями — чтобы округление по парам отличалось от сырой суммы."""
    rows = []
    for day, vals in {
        "2026-07-01": (10.4, 4.4),
        "2026-07-02": (20.6, 0.0),
        "2026-07-03": (30.4, 8.4),
        "2026-07-06": (12.0, 3.0),
        "2026-07-07": (11.0, 5.0),
    }.items():
        a, b = vals
        rows.append(
            {
                "project_id": "p1",
                "project_name": "Проект А",
                "contractor_id": "c1",
                "contractor_name": "Контрагент 1",
                "vid_resursa": "Рабочие",
                "date": day,
                "fact": a,
            }
        )
        rows.append(
            {
                "project_id": "p1",
                "project_name": "Проект А",
                "contractor_id": "c2",
                "contractor_name": "Контрагент 2",
                "vid_resursa": "Рабочие",
                "date": day,
                "fact": b,
            }
        )
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _plan_loader_factory() -> Callable[[pd.Timestamp], pd.DataFrame]:
    """План зависит от даты среза: внутри одной недели 01–05 и 06–07 различаются."""

    def _loader(snap: pd.Timestamp) -> pd.DataFrame:
        d = pd.Timestamp(snap).normalize()
        rows = [
            {
                "project_id": "p1",
                "project_name": "Проект А",
                "contractor_id": "c1",
                "contractor_name": "Контрагент 1",
                "plan_workers": 100.0 if d <= pd.Timestamp("2026-07-05") else 80.0,
                "plan_equipment": 0.0,
            },
            {
                "project_id": "p1",
                "project_name": "Проект А",
                "contractor_id": "c2",
                "contractor_name": "Контрагент 2",
                "plan_workers": 40.0 if d <= pd.Timestamp("2026-07-05") else 35.0,
                "plan_equipment": 0.0,
            },
        ]
        if d == pd.Timestamp("2026-07-02"):
            rows.append(
                {
                    "project_id": "p1",
                    "project_name": "Проект А",
                    "contractor_id": "c3",
                    "contractor_name": "Контрагент 3",
                    "plan_workers": 25.0,
                    "plan_equipment": 0.0,
                }
            )
        return pd.DataFrame(rows)

    return _loader


def _table_day_totals(
    fact: pd.DataFrame, day: str, loader: Callable[[pd.Timestamp], pd.DataFrame]
) -> tuple[int, int]:
    day_ts = pd.Timestamp(day)
    lo, hi = pd.Timestamp("2026-07-01"), pd.Timestamp("2026-07-31")
    day_key = gdrs_agg_day_key(day_ts)
    plan = loader(day_ts)
    main = build_main_table(
        fact,
        plan,
        vid="Рабочие",
        date_from=lo,
        date_to=hi,
        plan_agg=day_key,
        skud_agg=day_key,
        plan_as_of=day_ts,
        plan_aggregate_loader=loader,
    )
    gt = main[main["row_kind"] == "grand_total"].iloc[0]
    return int(round(float(gt["plan"]))), int(round(float(gt["skud"])))


def test_table_day_plan_snapshot_is_calendar_day():
    """Таблица «За день» режет план на выбранную дату (не через bucket_snapshot_end)."""
    lo, hi = pd.Timestamp("2026-09-01"), pd.Timestamp("2026-09-30")
    assert gdrs_plan_snapshot_date(
        _fact_july(),
        vid="Рабочие",
        date_from=lo,
        date_to=hi,
        plan_agg=gdrs_agg_day_key("2026-09-22"),
    ) == pd.Timestamp("2026-09-22")


def test_build_series_day_kind_still_uses_week_end_snapshot():
    """Внутри бакета build_series для kind «день» берёт конец недели — как до тикета 23."""
    lo, hi = pd.Timestamp("2026-09-01"), pd.Timestamp("2026-09-30")
    snap = gdrs_dynamics_bucket_snapshot_end(
        pd.Timestamp("2026-09-22"),
        "День",
        hi,
        date_from=lo,
        date_to=hi,
    )
    # 22.09 — не конец недели периода; helper не должен вернуть сам день.
    assert snap != pd.Timestamp("2026-09-22")
    assert snap == gdrs_dynamics_bucket_snapshot_end(
        pd.Timestamp("2026-09-21"),
        "День",
        hi,
        date_from=lo,
        date_to=hi,
    )


def test_day_dynamics_point_equals_table_grand_total():
    fact = _fact_july()
    loader = _plan_loader_factory()
    lo, hi = pd.Timestamp("2026-07-01"), pd.Timestamp("2026-07-31")

    dyn = gdrs_dynamics_build_day_series_matching_table(
        fact,
        lo,
        hi,
        vid="Рабочие",
        plan_col="plan_workers",
        plan_aggregate_loader=loader,
    )
    by_day = {
        pd.Timestamp(r["bucket"]).normalize(): (int(r["План"]), int(r["Факт"]))
        for _, r in dyn.iterrows()
    }

    for day in ("2026-07-01", "2026-07-02", "2026-07-06"):
        want_plan, want_fact = _table_day_totals(fact, day, loader)
        got_plan, got_fact = by_day[pd.Timestamp(day)]
        assert (got_plan, got_fact) == (want_plan, want_fact), (
            f"{day}: dynamics={(got_plan, got_fact)} table={(want_plan, want_fact)}"
        )


def test_day_dynamics_neighbors_not_forced_to_week_end_plan():
    """Соседние дни одной недели с разным срезом плана не схлопываются в полку конца недели."""
    fact = _fact_july()
    loader = _plan_loader_factory()
    lo, hi = pd.Timestamp("2026-07-01"), pd.Timestamp("2026-07-31")

    dyn = gdrs_dynamics_build_day_series_matching_table(
        fact,
        lo,
        hi,
        vid="Рабочие",
        plan_col="plan_workers",
        plan_aggregate_loader=loader,
    )
    by_day = {
        pd.Timestamp(r["bucket"]).normalize(): int(r["План"])
        for _, r in dyn.iterrows()
    }
    assert by_day[pd.Timestamp("2026-07-01")] != by_day[pd.Timestamp("2026-07-06")]
    assert by_day[pd.Timestamp("2026-07-02")] > by_day[pd.Timestamp("2026-07-01")]


def test_week_dynamics_keeps_week_end_plan_when_midweek_plan_changes():
    """Точка «Неделя»: внутренние дни бакета на week-end snapshot, не среднее дневных срезов."""
    fact = _fact_july()
    loader = _plan_loader_factory()
    lo, hi = pd.Timestamp("2026-07-01"), pd.Timestamp("2026-07-31")
    pairs = fact[
        ["project_id", "project_name", "contractor_id", "contractor_name"]
    ].drop_duplicates()

    week_dyn = gdrs_dynamics_build_series(
        fact,
        lo,
        hi,
        "Неделя",
        [],
        [],
        pairs,
        "plan_workers",
        plan_aggregate_loader=loader,
        plan_agg=GDRS_AGG_MONTH,
        skud_agg=GDRS_AGG_MONTH,
    )
    assert not week_dyn.empty
    # 1-я календарная неделя июля (01–07): план меняется 06.07 (100+40 → 80+35).
    # Week-end snapshot = 07.07 → 115. Среднее реальных дневных срезов было бы выше.
    first_week = week_dyn.iloc[0]
    week_end_snap = gdrs_dynamics_bucket_snapshot_end(
        pd.Timestamp(first_week["bucket"]),
        "Неделя",
        hi,
        date_from=lo,
        date_to=hi,
    )
    from dashboards.gdrs_resursi import gdrs_plan_sum_for_pairs, _build_plan_lookup

    lu = _build_plan_lookup(loader(week_end_snap), "plan_workers")
    expected_flat = int(
        gdrs_plan_sum_for_pairs(pairs, *lu, as_of_date=week_end_snap)
    )
    assert int(first_week["План"]) == expected_flat

    # Контроль: среднее планов на календарные дни недели ≠ week-end (иначе тест слаб).
    day_plans = []
    for d in pd.date_range("2026-07-01", "2026-07-07", freq="D"):
        lu_d = _build_plan_lookup(loader(pd.Timestamp(d)), "plan_workers")
        day_plans.append(
            float(gdrs_plan_sum_for_pairs(pairs, *lu_d, as_of_date=pd.Timestamp(d)))
        )
    daily_mean = int(round(sum(day_plans) / len(day_plans)))
    assert daily_mean != expected_flat
    assert int(first_week["План"]) != daily_mean


def test_month_dynamics_point_equals_table_month_avg_total():
    """Одна точка «Месяц» при «Среднее за месяц» = Итого таблицы, не среднее дневных."""
    fact = _fact_july()
    loader = _plan_loader_factory()
    lo, hi = pd.Timestamp("2026-07-01"), pd.Timestamp("2026-07-31")

    weekly_plan_by_week: dict = {}
    weekly_plan_as_of: dict = {}
    for wn in gdrs_week_numbers_in_period(lo, hi):
        w_end = week_end_in_filtered_fact(
            fact, vid="Рабочие", date_from=lo, date_to=hi, week_num=wn
        )
        if w_end is None or not pd.notna(w_end):
            continue
        weekly_plan_as_of[wn] = pd.Timestamp(w_end).normalize()
        weekly_plan_by_week[wn] = loader(weekly_plan_as_of[wn])

    main = build_main_table(
        fact,
        loader(hi),
        vid="Рабочие",
        date_from=lo,
        date_to=hi,
        plan_agg=GDRS_AGG_MONTH,
        skud_agg=GDRS_AGG_MONTH,
        weekly_plan_by_week=weekly_plan_by_week,
        weekly_plan_as_of=weekly_plan_as_of,
        plan_as_of=hi,
        plan_aggregate_loader=loader,
    )
    gt = main[main["row_kind"] == "grand_total"].iloc[0]
    table_plan = int(round(float(gt["plan"])))
    table_fact = int(round(float(gt["skud"])))

    pairs = fact[
        ["project_id", "project_name", "contractor_id", "contractor_name"]
    ].drop_duplicates()
    old = gdrs_dynamics_build_series(
        fact,
        lo,
        hi,
        "Месяц",
        [],
        [],
        pairs,
        "plan_workers",
        plan_aggregate_loader=loader,
        plan_agg=GDRS_AGG_MONTH,
        skud_agg=GDRS_AGG_MONTH,
    )
    assert len(old) == 1
    old_plan, old_fact = int(old.iloc[0]["План"]), int(old.iloc[0]["Факт"])
    # Старая формула (среднее дневных / fact-only) расходится с таблицей.
    assert (old_plan, old_fact) != (table_plan, table_fact)

    month_dyn = gdrs_dynamics_month_points_from_table_totals(
        [
            {
                "period": pd.Period("2026-07", freq="M"),
                "plan": table_plan,
                "fact": table_fact,
            }
        ]
    )
    assert int(month_dyn.iloc[0]["План"]) == table_plan
    assert int(month_dyn.iloc[0]["Факт"]) == table_fact
