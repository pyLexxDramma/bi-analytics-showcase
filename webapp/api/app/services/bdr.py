from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from app.config import DATA_MODE, WEB_DB_PATH
from app.services.bdds import (
    _applied,
    _filters_block,
    _granularity,
    _period_rows,
    _total_period,
)
from app.services.db_ingest import db_status
from app.services.finance_1c import (
    GROUP_LABELS,
    GROUPS,
    MODE_UNAVAILABLE,
    VIEW_LABELS,
    BdrScreenFrame,
    aggregate_periods,
    aggregate_projects,
    cumulate,
    date_range_title_suffix,
    drop_zero_periods,
    load_bdr_screen_frame,
    mln,
    records,
)
from app.services.report_cache import cache_get, cache_set

CACHE_ID = "bdr"
CACHE_VERSION = "v2"
CACHE_MAX_AGE_SEC = 3600


def _labels(*, group: str, view: str, suffix: str, total_period: str) -> dict[str, str]:
    granularity = _granularity(group, view)
    def title(name: str) -> str:
        return f"Таблица {name} ({suffix})" if suffix else f"Таблица {name}"
    return {
        "period": GROUP_LABELS.get(group, "Месяц"),
        "total_period": total_period,
        "date_suffix": suffix,
        "chart_caption": f"БДР {granularity} ({suffix})" if suffix else f"БДР {granularity}",
        "period_table_title": title(f"БДР {granularity}"),
        "project_table_title": title("БДР по проектам"),
    }


def _empty_payload(*, applied: dict[str, Any], screen: BdrScreenFrame) -> dict[str, Any]:
    suffix = date_range_title_suffix(screen.cal_start, screen.cal_end)
    return {
        "meta": {
            "source": "web_data.db",
            "data_mode": DATA_MODE,
            "parity": "main_dashboard_bdr",
            "mode": screen.mode,
            "error": screen.error,
            "version_id": screen.version_id,
            "rows": 0,
            "rows_1c": screen.reference_rows,
            "db": db_status(),
        },
        "filters": _filters_block(
            all_projects=screen.project_options,
            date_min=screen.date_min,
            date_max=screen.date_max,
            applied=applied,
        ),
        "kpis": {"plan_mln": 0.0, "fact_mln": 0.0, "deviation_mln": 0.0, "periods": 0},
        "tremor": {"by_period": [], "by_project": []},
        "period_rows": [],
        "project_rows": [],
        "hints": screen.hints,
        "totals": {"plan": 0.0, "fact": 0.0, "deviation": 0.0},
        "labels": _labels(group=applied["group"], view=applied["view"], suffix=suffix, total_period=""),
    }


def build_bdr_payload(
    *,
    projects: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    group: str = "month",
    view: str = "monthly",
    hide_zero: bool | None = None,
    show_deviation: bool = False,
) -> dict[str, Any]:
    group = group if group in GROUPS else "month"
    view = view if view in VIEW_LABELS else "monthly"
    selected = [str(p).strip() for p in (projects or []) if str(p).strip() and str(p).strip() != "Все"]
    hide_zero_effective = (not selected) if hide_zero is None else bool(hide_zero)
    hide_zero_effective = hide_zero_effective and group == "month" and view == "monthly"
    cache_key = "|".join([
        CACHE_VERSION,
        f"projects={','.join(sorted(selected))}",
        f"from={date_from.isoformat() if date_from else ''}",
        f"to={date_to.isoformat() if date_to else ''}",
        f"group={group}", f"view={view}", f"hide_zero={int(hide_zero_effective)}",
        f"db={WEB_DB_PATH}", f"mtime={db_status().get('mtime')}",
    ])
    cached = cache_get(CACHE_ID, cache_key, max_age_sec=CACHE_MAX_AGE_SEC)
    if cached is not None:
        return cached
    screen = load_bdr_screen_frame(
        projects=selected,
        date_from=date_from,
        date_to=date_to,
        group=group,
        view=view,
    )
    applied = _applied(
        projects=selected, date_from=screen.cal_start, date_to=screen.cal_end,
        group=group, view=view, hide_zero=hide_zero_effective, show_deviation=bool(show_deviation),
    )
    if not screen.ok:
        return _empty_payload(applied=applied, screen=screen)
    summary = screen.summary
    assert summary is not None
    visible = drop_zero_periods(summary) if hide_zero_effective else summary
    chart_rows = aggregate_periods(summary)
    if hide_zero_effective:
        chart_rows = drop_zero_periods(chart_rows)
    if view == "cumulative":
        chart_rows = cumulate(chart_rows)
    period_rows = _period_rows(screen, view=view, hide_zero=hide_zero_effective)
    project_rows = aggregate_projects(visible)
    if view == "cumulative" and not chart_rows.empty:
        grand = {key: float(chart_rows.iloc[-1][key]) for key in ("plan", "fact", "deviation")}
    else:
        plan = float(pd.to_numeric(visible["plan"], errors="coerce").fillna(0.0).sum())
        fact = float(pd.to_numeric(visible["fact"], errors="coerce").fillna(0.0).sum())
        grand = {"plan": plan, "fact": fact, "deviation": fact - plan}
    suffix = date_range_title_suffix(screen.cal_start, screen.cal_end)
    payload = {
        "meta": {
            "source": "web_data.db", "data_mode": DATA_MODE, "parity": "main_dashboard_bdr",
            "mode": screen.mode, "error": None, "version_id": screen.version_id,
            "rows": int(len(summary)), "rows_1c": screen.reference_rows,
            "periods": int(len(chart_rows)), "db": db_status(),
        },
        "filters": _filters_block(all_projects=screen.project_options, date_min=screen.date_min, date_max=screen.date_max, applied=applied),
        "kpis": {"plan_mln": mln(grand["plan"]), "fact_mln": mln(grand["fact"]), "deviation_mln": mln(grand["deviation"]), "periods": int(len(chart_rows))},
        "tremor": {
            "by_period": [{key: (mln(row[key]) if key != "period" else row[key]) for key in ("period", "plan", "fact", "deviation")} for row in records(chart_rows, fields=("period", "plan", "fact", "deviation"))],
            "by_project": [{key: (mln(row[key]) if key != "project" else row[key]) for key in ("project", "plan", "fact", "deviation")} for row in records(project_rows, fields=("project", "plan", "fact", "deviation"))],
        },
        "period_rows": period_rows,
        "project_rows": records(project_rows, fields=("project", "plan", "fact", "deviation")),
        "hints": screen.hints,
        "totals": {key: round(grand[key], 2) for key in ("plan", "fact", "deviation")},
        "labels": _labels(group=group, view=view, suffix=suffix, total_period=_total_period(screen, chart_rows)),
    }
    cache_set(CACHE_ID, cache_key, payload)
    return payload
