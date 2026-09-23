# -*- coding: utf-8 -*-
"""РД: обрыв плана, прогноз по явным датам (включая уже выданные)."""
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


def test_forecast_includes_issued_es_and_rework_gp_in_august() -> None:
    """Стенд: ЭС выдано 12.08 + ГП на доработке 03.08 → рыжая 2 в августе, не сентябре."""
    detail = pd.DataFrame(
        {
            "Полный шифр": ["65-ХСА-1/24-ЭС", "65-ХСА-1/24-ГП", "65-ХСА-1/24-НСП"],
            "Дата выдачи по договору": ["31.10.2026", "31.10.2026", "31.05.2025"],
            "Прогнозная дата выдачи": ["12.08.2026", "03.08.2026", ""],
            "Дата выдачи в производство работ": ["12.08.2026", "", "03.05.2026"],
            "Статус": [
                "Выдано в производство работ",
                "Возвращено на доработку",
                "Выдано в производство работ",
            ],
        }
    )
    out = _plan_slice_from_detail(detail, _Mod())
    assert int(out["_forecast_dyn_dt"].notna().sum()) == 2
    inc = _forecast_month_increments(out, junction=pd.Timestamp("2026-09-01"))
    assert sum(inc.values()) == 2.0
    assert pd.Timestamp("2026-08-01") in inc
    assert pd.Timestamp("2026-09-01") not in inc
    assert pd.Timestamp("2026-10-01") not in inc

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
        {
            "period": "2026-09-01",
            "period_label": "Сен 2026",
            "plan": None,
            "fact": 170.0,
            "forecast": None,
        },
    ]
    attached = _attach_forecast_from_fact(dyn, out, today=date(2026, 9, 23))
    by = {r["period"]: r for r in attached}
    assert by["2026-08-01"]["forecast"] == 2.0
    assert by["2026-08-01"]["fact"] == 167.0
    assert by["2026-09-01"]["forecast"] is None
    assert by["2026-09-01"]["fact"] == 170.0
    assert by["2025-05-01"]["forecast"] is None
    assert by["2025-05-01"]["plan"] == 198.0
    assert "2026-10-01" not in by


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


def test_forecast_survives_when_fact_line_missing() -> None:
    """Без зелёной рыжая всё равно = 2 в августе."""
    plan_df = pd.DataFrame(
        {
            "_plan_dt": [pd.Timestamp("2026-10-31"), pd.Timestamp("2026-10-31")],
            "_tessa_production_dt": [pd.NaT, pd.NaT],
            "_forecast_dyn_dt": [
                pd.Timestamp("2026-08-12"),
                pd.Timestamp("2026-08-03"),
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
