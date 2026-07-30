"""#2 БДДС (расходы) — паритет с `dashboard_budget_by_period` [main].

Данные: `finance_1c.load_finance_frame("bdds")` → `try_synthetic_budget_from_1c_dannye`
по активной версии `web_data.db`. Фильтры, группировка, «скрывать нулевые месяцы»,
накопительный вид и структура таблиц повторяют экран [main].
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from app.config import DATA_MODE, WEB_DB_PATH
from app.services.db_ingest import db_status
from app.services.finance_1c import (
    GROUP_LABELS,
    GROUPS,
    MODE_UNAVAILABLE,
    VIEW_LABELS,
    aggregate_periods,
    aggregate_projects,
    cumulate,
    date_bounds,
    drop_zero_periods,
    expand_period_grid,
    filter_frame,
    group_by_period,
    load_finance_frame,
    mln,
    project_labels,
    records,
    totals,
)
from app.services.report_cache import cache_get, cache_set

CACHE_ID = "bdds"
CACHE_VERSION = "v2"
CACHE_MAX_AGE_SEC = 3600


def _applied(
    *,
    projects: list[str],
    date_from: date | None,
    date_to: date | None,
    group: str,
    view: str,
    hide_zero: bool,
    show_deviation: bool,
) -> dict[str, Any]:
    return {
        "projects": projects,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "group": group,
        "view": view,
        "hide_zero": hide_zero,
        "show_deviation": show_deviation,
    }


def _filters_block(
    *,
    all_projects: list[str],
    date_min: date | None,
    date_max: date | None,
    applied: dict[str, Any],
) -> dict[str, Any]:
    return {
        "projects": all_projects,
        "date_min": date_min.isoformat() if date_min else None,
        "date_max": date_max.isoformat() if date_max else None,
        "groups": [{"id": key, "label": label} for key, label in GROUP_LABELS.items()],
        "views": [{"id": key, "label": label} for key, label in VIEW_LABELS.items()],
        "mode": "multiselect",
        "empty_means_all": True,
        "applied": applied,
    }


def _empty_payload(
    *,
    applied: dict[str, Any],
    mode: str = MODE_UNAVAILABLE,
    error: str | None = None,
    version_id: int | None = None,
    all_projects: list[str] | None = None,
    date_min: date | None = None,
    date_max: date | None = None,
) -> dict[str, Any]:
    return {
        "meta": {
            "source": "web_data.db",
            "data_mode": DATA_MODE,
            "parity": "main_budget_by_period",
            "mode": mode,
            "error": error,
            "version_id": version_id,
            "rows": 0,
            "db": db_status(),
        },
        "filters": _filters_block(
            all_projects=all_projects or [],
            date_min=date_min,
            date_max=date_max,
            applied=applied,
        ),
        "kpis": {"plan_mln": 0.0, "fact_mln": 0.0, "deviation_mln": 0.0, "periods": 0},
        "tremor": {"by_period": [], "by_project": []},
        "period_rows": [],
        "project_rows": [],
        "totals": {"plan": 0.0, "fact": 0.0, "deviation": 0.0},
        "labels": {"period": GROUP_LABELS.get(str(applied.get("group")), "Месяц"), "total_period": ""},
    }


def _period_total_label(rows: pd.DataFrame, *, date_from: date | None, date_to: date | None) -> str:
    """Подпись периода в строке ИТОГО — как `_bdds_period_total_disp` в [main]."""
    if date_from and date_to:
        return f"{date_from.strftime('%d.%m.%Y')} — {date_to.strftime('%d.%m.%Y')}"
    if rows is None or rows.empty:
        return ""
    first = str(rows.iloc[0]["period"])
    last = str(rows.iloc[-1]["period"])
    return first if first == last else f"{first} — {last}"


def _table_rows(
    grouped: pd.DataFrame,
    *,
    labels: list[str],
    view: str,
    hide_zero: bool,
) -> list[dict[str, Any]]:
    """Блоки как в сводной таблице [main]: заголовок проекта + его периоды."""
    if grouped is None or grouped.empty:
        return []

    def block(project: str) -> pd.DataFrame:
        rows = grouped[grouped["project"].astype(str) == project].sort_values("period_key")
        if hide_zero:
            rows = drop_zero_periods(rows)
        if rows.empty:
            return rows
        return cumulate(rows) if view == "cumulative" else rows

    present = [label for label in labels if not block(label).empty]
    out: list[dict[str, Any]] = []
    if len(present) > 1:
        for project in present:
            out.append(
                {
                    "kind": "project",
                    "project": project,
                    "period": "",
                    "plan": 0.0,
                    "fact": 0.0,
                    "deviation": 0.0,
                }
            )
            for row in records(block(project), fields=("period", "plan", "fact", "deviation")):
                out.append({"kind": "data", "project": "", **row})
        return out
    if len(present) == 1:
        project = present[0]
        for row in records(block(project), fields=("period", "plan", "fact", "deviation")):
            out.append({"kind": "data", "project": project, **row})
    return out


def _all_projects_rows(
    grouped: pd.DataFrame,
    *,
    view: str,
    hide_zero: bool,
) -> list[dict[str, Any]]:
    """Одна колонка «Все» — как в [main], когда проектов в срезе нет (свод по периодам)."""
    rows = aggregate_periods(grouped)
    if hide_zero:
        rows = drop_zero_periods(rows)
    if view == "cumulative":
        rows = cumulate(rows)
    return [
        {"kind": "data", "project": "Все", **row}
        for row in records(rows, fields=("period", "plan", "fact", "deviation"))
    ]


def build_bdds_payload(
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
    # main: чекбокс включён по умолчанию, когда проект не выбран (все проекты)
    hide_zero_effective = (not selected) if hide_zero is None else bool(hide_zero)
    # скрытие нулей действует только для месячной разбивки без накопления (как в main)
    hide_zero_effective = hide_zero_effective and group == "month" and view == "monthly"
    applied = _applied(
        projects=selected,
        date_from=date_from,
        date_to=date_to,
        group=group,
        view=view,
        hide_zero=hide_zero_effective,
        show_deviation=bool(show_deviation),
    )

    cache_key = "|".join(
        [
            CACHE_VERSION,
            f"projects={','.join(sorted(selected))}",
            f"from={date_from.isoformat() if date_from else ''}",
            f"to={date_to.isoformat() if date_to else ''}",
            f"group={group}",
            f"view={view}",
            f"hide_zero={int(hide_zero_effective)}",
            f"db={WEB_DB_PATH}",
            f"mtime={db_status().get('mtime')}",
        ]
    )
    cached = cache_get(CACHE_ID, cache_key, max_age_sec=CACHE_MAX_AGE_SEC)
    if cached is not None:
        cached.setdefault("filters", {})["applied"] = applied
        return cached

    finance = load_finance_frame("bdds")
    if not finance.ok:
        return _empty_payload(
            applied=applied,
            mode=finance.mode,
            error=finance.error,
            version_id=finance.version_id,
        )

    frame = finance.frame
    assert frame is not None
    all_projects = project_labels(frame)
    date_min, date_max = date_bounds(frame)

    filtered = filter_frame(frame, projects=selected, date_from=date_from, date_to=date_to)
    if filtered.empty:
        payload = _empty_payload(
            applied=applied,
            mode=finance.mode,
            error=None,
            version_id=finance.version_id,
            all_projects=all_projects,
            date_min=date_min,
            date_max=date_max,
        )
        payload["labels"]["period"] = GROUP_LABELS[group]
        return payload

    grouped = group_by_period(filtered, group=group)
    if group == "month" and view == "monthly":
        grouped = expand_period_grid(grouped, group=group, date_from=date_from, date_to=date_to)

    chart_rows = aggregate_periods(grouped)
    if hide_zero_effective:
        chart_rows = drop_zero_periods(chart_rows)
    if view == "cumulative":
        chart_rows = cumulate(chart_rows)

    labels = selected or [p for p in all_projects if p in set(grouped["project"].astype(str))]
    period_rows = _table_rows(grouped, labels=labels, view=view, hide_zero=hide_zero_effective)
    if not period_rows:
        period_rows = _all_projects_rows(grouped, view=view, hide_zero=hide_zero_effective)

    project_rows_df = aggregate_projects(grouped)
    grand = totals(filtered)
    if view == "cumulative" and not chart_rows.empty:
        last = chart_rows.iloc[-1]
        grand = {
            "plan": float(last["plan"]),
            "fact": float(last["fact"]),
            "deviation": float(last["fact"]) - float(last["plan"]),
        }

    payload: dict[str, Any] = {
        "meta": {
            "source": "web_data.db",
            "data_mode": DATA_MODE,
            "parity": "main_budget_by_period",
            "mode": finance.mode,
            "error": None,
            "version_id": finance.version_id,
            "rows": int(len(filtered)),
            "periods": int(len(chart_rows)),
            "db": db_status(),
        },
        "filters": _filters_block(
            all_projects=all_projects,
            date_min=date_min,
            date_max=date_max,
            applied=applied,
        ),
        "kpis": {
            "plan_mln": mln(grand["plan"]),
            "fact_mln": mln(grand["fact"]),
            "deviation_mln": mln(grand["deviation"]),
            "periods": int(len(chart_rows)),
        },
        "tremor": {
            "by_period": [
                {
                    "period": row["period"],
                    "plan": mln(row["plan"]),
                    "fact": mln(row["fact"]),
                    "deviation": mln(row["deviation"]),
                }
                for row in records(chart_rows, fields=("period", "plan", "fact", "deviation"))
            ],
            "by_project": [
                {
                    "project": row["project"],
                    "plan": mln(row["plan"]),
                    "fact": mln(row["fact"]),
                    "deviation": mln(row["deviation"]),
                }
                for row in records(project_rows_df, fields=("project", "plan", "fact", "deviation"))
            ],
        },
        "period_rows": period_rows,
        "project_rows": records(project_rows_df, fields=("project", "plan", "fact", "deviation")),
        "totals": {
            "plan": round(grand["plan"], 2),
            "fact": round(grand["fact"], 2),
            "deviation": round(grand["deviation"], 2),
        },
        "labels": {
            "period": GROUP_LABELS[group],
            "total_period": _period_total_label(chart_rows, date_from=date_from, date_to=date_to),
        },
    }
    cache_set(CACHE_ID, cache_key, payload)
    return payload
