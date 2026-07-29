from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from app.config import DATA_MODE
from app.services.finance_period import _mln, build_finance_period_payload

_MONTH_INDEX = {
    "январь": 1,
    "февраль": 2,
    "март": 3,
    "апрель": 4,
    "май": 5,
    "июнь": 6,
    "июль": 7,
    "август": 8,
    "сентябрь": 9,
    "октябрь": 10,
    "ноябрь": 11,
    "декабрь": 12,
}


def _period_start(label: str) -> date | None:
    parts = str(label or "").strip().split()
    if len(parts) != 2:
        return None
    month = _MONTH_INDEX.get(parts[0].casefold())
    try:
        year = int(parts[1])
    except ValueError:
        return None
    if not month:
        return None
    return date(year, month, 1)


def build_bdds_plan_fact_payload(
    *,
    project: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    view: str = "monthly",
) -> dict[str, Any]:
    """БДДС: план / факт / уточнённый план.

    В 1С нет сценария «уточнённый» — MVP:
    прошлые месяцы → факт (иначе план), текущий и будущие → план.
    """
    view = view if view in {"monthly", "cumulative"} else "monthly"
    base = build_finance_period_payload(
        tip_needle="бддс",
        project=project,
        date_from=date_from,
        date_to=date_to,
        view="monthly",
    )
    today = date.today().replace(day=1)

    period_rows: list[dict[str, Any]] = []
    for row in base.get("period_rows") or []:
        plan = float(row.get("plan") or 0)
        fact = float(row.get("fact") or 0)
        start = _period_start(str(row.get("period") or ""))
        if start is None:
            revised = plan
        elif start < today:
            revised = fact if abs(fact) > 1e-9 else plan
        else:
            revised = plan
        period_rows.append(
            {
                "period": row["period"],
                "plan": round(plan, 2),
                "fact": round(fact, 2),
                "revised": round(revised, 2),
                "deviation": round(fact - plan, 2),
            }
        )

    if view == "cumulative" and period_rows:
        frame = pd.DataFrame(period_rows)
        for col in ("plan", "fact", "revised", "deviation"):
            frame[col] = frame[col].cumsum()
        period_rows = [
            {
                "period": str(row["period"]),
                "plan": round(float(row["plan"]), 2),
                "fact": round(float(row["fact"]), 2),
                "revised": round(float(row["revised"]), 2),
                "deviation": round(float(row["deviation"]), 2),
            }
            for _, row in frame.iterrows()
        ]

    project_rows = [
        {
            "project": row["project"],
            "plan": round(float(row.get("plan") or 0), 2),
            "fact": round(float(row.get("fact") or 0), 2),
            "revised": round(float(row.get("plan") or 0), 2),
            "deviation": round(float(row.get("deviation") or 0), 2),
        }
        for row in base.get("project_rows") or []
    ]

    if view == "cumulative" and period_rows:
        last = period_rows[-1]
        plan_kpi, fact_kpi, revised_kpi = last["plan"], last["fact"], last["revised"]
    else:
        plan_kpi = sum(r["plan"] for r in period_rows)
        fact_kpi = sum(r["fact"] for r in period_rows)
        revised_kpi = sum(r["revised"] for r in period_rows)

    applied = dict((base.get("filters") or {}).get("applied") or {})
    applied["view"] = view

    return {
        "meta": {
            **(base.get("meta") or {}),
            "data_mode": DATA_MODE,
            "rule": "Уточнённый план: прошлые месяцы = факт (или план), текущий/будущие = план",
        },
        "filters": {**(base.get("filters") or {}), "applied": applied},
        "kpis": {
            "plan_mln": _mln(plan_kpi),
            "fact_mln": _mln(fact_kpi),
            "revised_mln": _mln(revised_kpi),
            "deviation_mln": _mln(fact_kpi - plan_kpi),
        },
        "tremor": {
            "by_period": [
                {
                    "period": row["period"],
                    "plan": _mln(row["plan"]),
                    "fact": _mln(row["fact"]),
                    "revised": _mln(row["revised"]),
                }
                for row in period_rows
            ],
            "by_project": [
                {
                    "project": row["project"],
                    "plan": _mln(row["plan"]),
                    "fact": _mln(row["fact"]),
                    "revised": _mln(row["revised"]),
                }
                for row in project_rows
            ],
        },
        "period_rows": period_rows,
        "project_rows": project_rows,
    }
