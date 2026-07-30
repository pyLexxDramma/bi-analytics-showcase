"""#2 БДДС (расходы) — паритет с `dashboard_budget_by_period` [main].

Свод считает `finance_1c.load_bdds_screen_frame`: это транскрипция пути экрана
(кадр MSP → фильтры → 1С-fallback → overlay 1С → сетка месяцев → finalize),
а не «голый» `try_synthetic_budget_from_1c_dannye`. Заголовки, подписи периодов
и структура таблиц повторяют `_renderers.py` (строки 14472–15683).
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
    BddsScreenFrame,
    aggregate_periods,
    bdds_block_labels,
    bdds_block_rows,
    bdds_project_totals,
    cumulate,
    date_range_title_suffix,
    drop_zero_periods,
    load_bdds_screen_frame,
    mln,
    records,
)
from app.services.report_cache import cache_get, cache_set

CACHE_ID = "bdds"
CACHE_VERSION = "v4"
CACHE_MAX_AGE_SEC = 3600

GRANULARITY: dict[str, str] = {"month": "по месяцам", "quarter": "по кварталам", "year": "по годам"}


def _granularity(group: str, view: str) -> str:
    """`utils.format_report_granularity_label`."""
    return "накопительно" if view == "cumulative" else GRANULARITY.get(group, "по месяцам")


def _title(name: str, suffix: str) -> str:
    """`utils.format_table_title`: «Таблица …» + диапазон дат в скобках."""
    return f"Таблица {name} ({suffix})" if suffix else f"Таблица {name}"


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


def _labels(*, group: str, view: str, suffix: str, total_period: str) -> dict[str, str]:
    gran = _granularity(group, view)
    return {
        "period": GROUP_LABELS.get(group, "Месяц"),
        "total_period": total_period,
        "date_suffix": suffix,
        "chart_caption": f"БДДС {gran} ({suffix})" if suffix else f"БДДС {gran}",
        "period_table_title": _title(f"БДДС {gran}", suffix),
        "project_table_title": _title("БДДС по проектам", suffix),
    }


def _empty_payload(
    *,
    applied: dict[str, Any],
    screen: BddsScreenFrame | None = None,
    mode: str = MODE_UNAVAILABLE,
    error: str | None = None,
) -> dict[str, Any]:
    group = str(applied.get("group") or "month")
    view = str(applied.get("view") or "monthly")
    suffix = (
        date_range_title_suffix(screen.cal_start, screen.cal_end)
        if screen is not None and screen.cal_start and screen.cal_end
        else ""
    )
    return {
        "meta": {
            "source": "web_data.db",
            "data_mode": DATA_MODE,
            "parity": "main_budget_by_period",
            "mode": mode,
            "error": error,
            "version_id": screen.version_id if screen else None,
            "rows": 0,
            "rows_1c": screen.reference_rows if screen else 0,
            "db": db_status(),
        },
        "filters": _filters_block(
            all_projects=list(screen.project_options) if screen else [],
            date_min=screen.date_min if screen else None,
            date_max=screen.date_max if screen else None,
            applied=applied,
        ),
        "kpis": {"plan_mln": 0.0, "fact_mln": 0.0, "deviation_mln": 0.0, "periods": 0},
        "tremor": {"by_period": [], "by_project": []},
        "period_rows": [],
        "project_rows": [],
        "hints": list(screen.hints) if screen else [],
        "totals": {"plan": 0.0, "fact": 0.0, "deviation": 0.0},
        "labels": _labels(group=group, view=view, suffix=suffix, total_period=""),
    }


def _total_period(screen: BddsScreenFrame, rows: pd.DataFrame) -> str:
    """`_bdds_period_total_disp`: диапазон календаря, иначе первый — последний период."""
    if screen.cal_start and screen.cal_end:
        return f"{screen.cal_start.strftime('%d.%m.%Y')} — {screen.cal_end.strftime('%d.%m.%Y')}"
    if rows is None or rows.empty:
        return ""
    first = str(rows.iloc[0]["period"])
    last = str(rows.iloc[-1]["period"])
    return first if first == last else f"{first} — {last}"


def _period_rows(
    screen: BddsScreenFrame,
    *,
    view: str,
    hide_zero: bool,
) -> list[dict[str, Any]]:
    """Блоки сводной таблицы [main]: строка-заголовок проекта + его периоды."""
    summary = screen.summary
    assert summary is not None

    def block(label: str) -> pd.DataFrame:
        rows = bdds_block_rows(summary, label)
        if hide_zero:
            rows = drop_zero_periods(rows)
        if rows.empty:
            return rows
        return cumulate(rows) if view == "cumulative" else rows

    labels = bdds_block_labels(summary)
    blocks = [(label, block(label)) for label in labels]
    present = [(label, rows) for label, rows in blocks if not rows.empty]

    out: list[dict[str, Any]] = []
    if len(present) > 1:
        for label, rows in present:
            out.append(
                {
                    "kind": "project",
                    "project": label,
                    "period": "",
                    "plan": 0.0,
                    "fact": 0.0,
                    "deviation": 0.0,
                }
            )
            for row in records(rows, fields=("period", "plan", "fact", "deviation")):
                out.append({"kind": "data", "project": "", **row})
        return out
    if len(present) == 1:
        label, rows = present[0]
        for row in records(rows, fields=("period", "plan", "fact", "deviation")):
            out.append({"kind": "data", "project": label, **row})
        return out
    # Проектов в срезе нет — одна серия «Все» (ветка else в [main]).
    rows = aggregate_periods(summary)
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
    # main: `value=bool(_bdds_all_projects)` — включён, пока не выбран конкретный проект
    hide_zero_effective = (not selected) if hide_zero is None else bool(hide_zero)
    # чекбокс существует только для месячной разбивки без накопления
    hide_zero_effective = hide_zero_effective and group == "month" and view == "monthly"

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
        return cached

    screen = load_bdds_screen_frame(
        projects=selected,
        date_from=date_from,
        date_to=date_to,
        group=group,
        view=view,
    )
    applied = _applied(
        projects=selected,
        date_from=screen.cal_start,
        date_to=screen.cal_end,
        group=group,
        view=view,
        hide_zero=hide_zero_effective,
        show_deviation=bool(show_deviation),
    )
    if not screen.ok:
        return _empty_payload(applied=applied, screen=screen, mode=screen.mode, error=screen.error)

    summary = screen.summary
    assert summary is not None
    visible = drop_zero_periods(summary) if hide_zero_effective else summary

    chart_rows = aggregate_periods(summary)
    if hide_zero_effective:
        chart_rows = drop_zero_periods(chart_rows)
    if view == "cumulative":
        chart_rows = cumulate(chart_rows)

    period_rows = _period_rows(screen, view=view, hide_zero=hide_zero_effective)
    project_rows_df = bdds_project_totals(visible)

    if view == "cumulative" and not chart_rows.empty:
        last = chart_rows.iloc[-1]
        grand = {
            "plan": float(last["plan"]),
            "fact": float(last["fact"]),
            "deviation": float(last["fact"]) - float(last["plan"]),
        }
    else:
        plan = float(pd.to_numeric(visible["plan"], errors="coerce").fillna(0.0).sum())
        fact = float(pd.to_numeric(visible["fact"], errors="coerce").fillna(0.0).sum())
        grand = {"plan": plan, "fact": fact, "deviation": fact - plan}

    suffix = date_range_title_suffix(screen.cal_start, screen.cal_end)
    payload: dict[str, Any] = {
        "meta": {
            "source": "web_data.db",
            "data_mode": DATA_MODE,
            "parity": "main_budget_by_period",
            "mode": screen.mode,
            "error": None,
            "version_id": screen.version_id,
            "rows": int(len(summary)),
            "rows_1c": screen.reference_rows,
            "periods": int(len(chart_rows)),
            "db": db_status(),
        },
        "filters": _filters_block(
            all_projects=list(screen.project_options),
            date_min=screen.date_min,
            date_max=screen.date_max,
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
        "hints": list(screen.hints),
        "totals": {
            "plan": round(grand["plan"], 2),
            "fact": round(grand["fact"], 2),
            "deviation": round(grand["deviation"], 2),
        },
        "labels": _labels(
            group=group,
            view=view,
            suffix=suffix,
            total_period=_total_period(screen, chart_rows),
        ),
    }
    cache_set(CACHE_ID, cache_key, payload)
    return payload
