from __future__ import annotations

from typing import Any

import pandas as pd

from app.config import DATA_MODE, WEB_DB_PATH
from app.services.bdds import _total_period
from app.services.db_ingest import db_status
from app.services.finance_1c import (
    BddsScreenFrame,
    aggregate_periods,
    bdds_project_totals,
    drop_zero_periods,
    load_approved_budget_screen_frame,
    mln,
    records,
)
from app.services.report_cache import cache_get, cache_set

CACHE_ID = "approved_budget"
CACHE_VERSION = "v4"
CACHE_MAX_AGE_SEC = 3600


def _applied(
    *,
    projects: list[str],
    fiz: str | None,
    hide_zero: bool,
    show_deviation: bool,
) -> dict[str, Any]:
    return {
        "projects": projects,
        "fiz": fiz or "Все",
        "hide_zero": hide_zero,
        "show_deviation": show_deviation,
    }


def _empty_payload(
    *,
    applied: dict[str, Any],
    screen: BddsScreenFrame | None = None,
    fiz_options: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "meta": {
            "rows": 0,
            "source": "web_data.db",
            "data_mode": DATA_MODE,
            "parity": "main_bdds_cumulative",
            "mode": screen.mode if screen else "unavailable",
            "error": screen.error if screen else None,
            "version_id": screen.version_id if screen else None,
            "db": db_status(),
        },
        "filters": {
            "projects": list(screen.project_options) if screen else [],
            "fiz": fiz_options or [],
            "mode": "multiselect",
            "empty_means_all": True,
            "applied": applied,
        },
        "kpis": {
            "plan_mln": 0.0,
            "fact_mln": 0.0,
            "deviation_mln": 0.0,
            "remainder_mln": 0.0,
        },
        "gauge": {
            "plan": 0.0, "fact": 0.0, "deviation": 0.0,
            "plan_mlrd": 0.0, "fact_mlrd": 0.0, "deviation_mlrd": 0.0,
            "fact_pct": 0.0, "deviation_pct": 0.0, "axis_max_mlrd": 0.0,
        },
        "tremor": {"by_period": [], "by_project": []},
        "period_rows": [],
        "project_rows": [],
        "totals": {"plan": 0.0, "fact": 0.0, "deviation": 0.0, "remainder": 0.0},
        "hints": list(screen.hints) if screen else [],
        "labels": {
            "period_table_title": "Сводная таблица по месяцам",
            "project_table_title": "Таблица утверждённого бюджет план/факт по проектам",
            "total_period": "",
        },
    }


def build_approved_budget_payload(
    *,
    projects: list[str] | None = None,
    fiz: str | None = None,
    hide_zero: bool | None = None,
    show_deviation: bool = False,
) -> dict[str, Any]:
    """Полный путь «Утверждённый бюджет» = накопительный срез БДДС экрана [main]."""
    selected = [str(item).strip() for item in (projects or []) if str(item).strip() and str(item).strip() != "Все"]
    hide_zero_effective = (not selected and not fiz) if hide_zero is None else bool(hide_zero)
    cache_key = "|".join([
        CACHE_VERSION,
        f"projects={','.join(sorted(selected))}",
        f"fiz={fiz or ''}",
        f"hide_zero={int(hide_zero_effective)}",
        f"db={WEB_DB_PATH}",
        f"mtime={db_status().get('mtime')}",
    ])
    cached = cache_get(CACHE_ID, cache_key, max_age_sec=CACHE_MAX_AGE_SEC)
    if cached is not None:
        return cached

    screen, fiz_options = load_approved_budget_screen_frame(projects=selected, fiz=fiz)
    applied = _applied(
        projects=selected,
        fiz=fiz,
        hide_zero=hide_zero_effective,
        show_deviation=bool(show_deviation),
    )
    if not screen.ok:
        return _empty_payload(applied=applied, screen=screen, fiz_options=fiz_options)

    summary = screen.summary
    assert summary is not None
    chart_rows = aggregate_periods(summary)
    visible_periods = drop_zero_periods(chart_rows) if hide_zero_effective else chart_rows
    project_frame = bdds_project_totals(summary)
    project_frame["remainder"] = project_frame["plan"] - project_frame["fact"]
    project_frame["completion_pct"] = project_frame.apply(
        lambda row: (float(row["fact"]) / float(row["plan"]) * 100.0) if float(row["plan"]) else None,
        axis=1,
    )
    project_frame["contract_coverage_pct"] = 0.0
    plan_sum = float(pd.to_numeric(summary["plan"], errors="coerce").fillna(0.0).sum())
    fact_sum = float(pd.to_numeric(summary["fact"], errors="coerce").fillna(0.0).sum())
    deviation = fact_sum - plan_sum
    axis_max = max(plan_sum, fact_sum, 1.0) * 1.08
    period_records = records(visible_periods, fields=("period", "plan", "fact", "deviation"))
    project_rows = []
    for row in project_frame.to_dict("records"):
        project_rows.append({
            "project": str(row["project"]),
            "plan": round(float(row["plan"]), 2),
            "fact": round(float(row["fact"]), 2),
            "remainder": round(float(row["remainder"]), 2),
            "deviation": round(float(row["deviation"]), 2),
            "completion_pct": round(float(row["completion_pct"]), 1) if pd.notna(row["completion_pct"]) else 0.0,
            "contract_coverage_pct": 0.0,
        })

    payload = {
        "meta": {
            "rows": int(len(summary)),
            "source": "web_data.db",
            "data_mode": DATA_MODE,
            "parity": "main_bdds_cumulative",
            "mode": screen.mode,
            "error": None,
            "version_id": screen.version_id,
            "rows_1c": screen.reference_rows,
            "db": db_status(),
        },
        "filters": {
            "projects": screen.project_options,
            "fiz": fiz_options,
            "mode": "multiselect",
            "empty_means_all": True,
            "applied": applied,
        },
        "kpis": {
            "plan_mln": mln(plan_sum),
            "fact_mln": mln(fact_sum),
            "deviation_mln": mln(deviation),
            "remainder_mln": mln(plan_sum - fact_sum),
        },
        "gauge": {
            "plan": round(plan_sum, 2),
            "fact": round(fact_sum, 2),
            "deviation": round(deviation, 2),
            "plan_mlrd": round(plan_sum / 1_000_000_000, 2),
            "fact_mlrd": round(fact_sum / 1_000_000_000, 2),
            "deviation_mlrd": round(deviation / 1_000_000_000, 2),
            "fact_pct": round(fact_sum / plan_sum * 100.0, 1) if plan_sum else 0.0,
            "deviation_pct": round(deviation / plan_sum * 100.0, 1) if plan_sum else 0.0,
            "axis_max_mlrd": round(axis_max / 1_000_000_000, 2),
        },
        "tremor": {
            "by_period": [
                {"period": row["period"], "plan": mln(row["plan"]), "fact": mln(row["fact"]), "deviation": mln(row["deviation"])}
                for row in period_records
            ],
            "by_project": [
                {
                    "project": row["project"],
                    "plan": mln(row["plan"]),
                    "fact": mln(row["fact"]),
                    "deviation": mln(row["deviation"]),
                }
                for row in project_rows
            ]
        },
        "period_rows": period_records,
        "project_rows": project_rows,
        "totals": {
            "plan": round(plan_sum, 2),
            "fact": round(fact_sum, 2),
            "deviation": round(deviation, 2),
            "remainder": round(plan_sum - fact_sum, 2),
        },
        "hints": screen.hints,
        "labels": {
            "period_table_title": "Сводная таблица по месяцам",
            "project_table_title": "Таблица утверждённого бюджет план/факт по проектам",
            "total_period": _total_period(screen, visible_periods),
        },
    }
    cache_set(CACHE_ID, cache_key, payload)
    return payload
