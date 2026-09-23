# -*- coding: utf-8 -*-
"""РД: обрыв плана, прогноз только по датам, без комментариев и без хвоста."""
from __future__ import annotations

from datetime import date

import pandas as pd

from app.services.working_documentation import (
    _attach_forecast_from_fact,
    _build_dynamics,
    _forecast_month_increments,
    _parse_real_date,
    _plan_slice_from_detail,
)


class _Mod:
    """Статус как в TESSA: дата выдачи не делает строку выданной."""

    _RD_TESSA_STATUS_PRODUCTION = "Выдано в производство работ"

    @staticmethod
    def _rd_canonical_tessa_rd_status(value: object) -> str | None:
        s = str(value or "").strip()
        return s or None


def test_parse_real_date_keeps_msp_rejects_comments() -> None:
    assert pd.Timestamp(_parse_real_date("31.08.2026")).date() == date(2026, 8, 31)
    assert pd.isna(_parse_real_date("Приемка РД и выдача замечаний"))
    assert pd.isna(_parse_real_date("Согласно распоряжения №55 LI от 20.08.25 добавить витражи"))
    assert pd.isna(_parse_real_date(""))


def test_plan_slice_copies_forecast_date_not_contract() -> None:
    detail = pd.DataFrame(
        {
            "Дата выдачи разделов по Договору": ["31.10.2026", "31.10.2026"],
            "Прогнозная дата выдачи разделов": ["31.08.2026", "Приемка РД"],
            "Дата выдачи в производство работ": ["", ""],
            "Статус": ["Не выдано", "Не выдано"],
        }
    )
    out = _plan_slice_from_detail(detail, _Mod())
    assert pd.Timestamp(out["_forecast_dyn_dt"].iloc[0]).date() == date(2026, 8, 31)
    assert pd.isna(out["_forecast_dyn_dt"].iloc[1])
    assert pd.Timestamp(out["_plan_dt"].iloc[0]).date() == date(2026, 10, 31)


def test_plan_slice_keeps_not_issued_even_if_tessa_date_filled() -> None:
    """65-ХСА-1/24: в деталке «Не выдано», даже если в колонке даты есть значение."""
    detail = pd.DataFrame(
        {
            "Дата выдачи по договору": ["31.05.2025", "31.10.2026", "31.10.2026"],
            "Прогнозная дата выдачи": ["", "31.08.2026", "31.08.2026"],
            "Дата выдачи в производство работ": ["10.08.2026", "10.08.2026", ""],
            "Статус": [
                "Выдано в производство работ",
                "Не выдано",
                "Не выдано",
            ],
        }
    )
    out = _plan_slice_from_detail(detail, _Mod())
    assert int(out["_tessa_production_dt"].notna().sum()) == 1
    assert int(out["_forecast_dyn_dt"].notna().sum()) == 2
    inc = _forecast_month_increments(out, junction=pd.Timestamp("2026-08-01"))
    assert sum(inc.values()) == 2.0
    assert pd.Timestamp("2026-08-01") in inc


def test_build_dynamics_plan_stops_at_last_plan_date() -> None:
    plan_df = pd.DataFrame(
        {
            "_plan_dt": [pd.Timestamp("2025-05-15"), pd.Timestamp("2025-05-20")],
            "_tessa_production_dt": [pd.NaT, pd.Timestamp("2026-08-10")],
        }
    )
    rows = _build_dynamics(plan_df, _Mod())
    by = {r["period"]: r for r in rows}
    may = [r for r in rows if r["period"].startswith("2025-05")]
    assert may
    assert may[-1]["plan"] == 2.0
    aug = by.get("2026-08-01")
    assert aug is not None
    assert aug["plan"] is None
    assert aug["fact"] == 1.0


def test_forecast_two_dated_remaining_is_two_not_fact_plus() -> None:
    """Две строки 65-ХСА-1/24 с августом: рыжая = 2, не 0 и не 167/169."""
    plan_df = pd.DataFrame(
        {
            "_plan_dt": [
                pd.Timestamp("2025-05-15"),
                pd.Timestamp("2026-10-31"),
                pd.Timestamp("2026-10-31"),
            ],
            "_tessa_production_dt": [pd.Timestamp("2026-08-10"), pd.NaT, pd.NaT],
            "_forecast_dyn_dt": [
                pd.NaT,
                pd.Timestamp("2026-08-31"),
                pd.Timestamp("2026-08-31"),
            ],
        }
    )
    inc = _forecast_month_increments(plan_df, junction=pd.Timestamp("2026-08-01"))
    assert pd.Timestamp("2026-08-01") in inc
    assert pd.Timestamp("2026-10-01") not in inc
    assert sum(inc.values()) == 2.0

    dyn = [
        {
            "period": "2025-05-01",
            "period_label": "Май 2025",
            "plan": 198.0,
            "fact": None,
            "forecast": None,
        },
        {
            "period": "2026-08-01",
            "period_label": "Авг 2026",
            "plan": None,
            "fact": 167.0,
            "forecast": None,
        },
    ]
    out = _attach_forecast_from_fact(dyn, plan_df, today=date(2026, 9, 22))
    by = {r["period"]: r for r in out}
    assert "2026-10-01" not in by
    assert by["2026-08-01"]["forecast"] == 2.0
    assert by["2026-08-01"]["fact"] == 167.0
    assert by["2025-05-01"]["forecast"] is None
    assert by["2025-05-01"]["plan"] == 198.0


def test_forecast_survives_when_fact_line_missing() -> None:
    """Без зелёной (фильтр «Не выдано») рыжая всё равно = 2 в августе."""
    plan_df = pd.DataFrame(
        {
            "_plan_dt": [pd.Timestamp("2026-10-31"), pd.Timestamp("2026-10-31")],
            "_tessa_production_dt": [pd.NaT, pd.NaT],
            "_forecast_dyn_dt": [
                pd.Timestamp("2026-08-31"),
                pd.Timestamp("2026-08-31"),
            ],
        }
    )
    dyn = [
        {
            "period": "2025-05-01",
            "period_label": "Май 2025",
            "plan": 2.0,
            "fact": None,
            "forecast": None,
        }
    ]
    out = _attach_forecast_from_fact(dyn, plan_df, today=date(2026, 9, 23))
    by = {r["period"]: r for r in out}
    assert by["2026-08-01"]["forecast"] == 2.0
    assert by["2025-05-01"]["forecast"] is None
    assert by["2025-05-01"]["plan"] == 2.0


def test_forecast_skips_rows_without_date() -> None:
    plan_df = pd.DataFrame(
        {
            "_plan_dt": [pd.Timestamp("2026-10-31")],
            "_tessa_production_dt": [pd.NaT],
            "_forecast_dyn_dt": [pd.NaT],
        }
    )
    inc = _forecast_month_increments(plan_df, junction=pd.Timestamp("2026-09-01"))
    assert inc == {}
    dyn = [
        {
            "period": "2026-08-01",
            "period_label": "Авг 2026",
            "plan": None,
            "fact": 167.0,
            "forecast": None,
        }
    ]
    out = _attach_forecast_from_fact(dyn, plan_df, today=date(2026, 9, 23))
    assert all(r.get("forecast") is None for r in out)
