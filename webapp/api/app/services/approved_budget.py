from __future__ import annotations

from typing import Any

import pandas as pd

from app.config import DATA_MODE
from app.services.data_paths import latest_web_file
from app.services.finance_period import _load_json_list, _mln, _parse_money


def _empty_payload(*, source: str, project: str | None) -> dict[str, Any]:
    return {
        "meta": {"rows": 0, "source": source, "data_mode": DATA_MODE, "files": 0},
        "filters": {
            "projects": ["Все"],
            "applied": {"project": project or "Все"},
        },
        "kpis": {
            "plan_mln": 0.0,
            "fact_mln": 0.0,
            "deviation_mln": 0.0,
            "remainder_mln": 0.0,
        },
        "tremor": {"by_project": []},
        "project_rows": [],
    }


def build_approved_budget_payload(*, project: str | None = None) -> dict[str, Any]:
    """Утверждённый бюджет план/факт (ТЗ 2026-05-07): БДДС ПЛАН без (БДР) / БДДС ФАКТ, без фильтра лотов."""
    path = latest_web_file("_dannye.json")
    rows = _load_json_list(path)
    source = path.name if path else "1с_*_dannye.json"
    if not rows:
        return _empty_payload(source=source, project=project)

    frame = pd.DataFrame(rows)
    needed = {"ТипСтатьи", "Сценарий", "СтатьяОборотов", "Сумма"}
    if frame.empty or not needed.issubset(frame.columns):
        return _empty_payload(source=source, project=project)

    tip = frame["ТипСтатьи"].fillna("").astype(str).str.strip().str.casefold()
    frame = frame[tip.eq("бддс")].copy()
    if frame.empty:
        return _empty_payload(source=source, project=project)

    scen = frame["Сценарий"].fillna("").astype(str).str.strip().str.casefold()
    art = (
        frame["СтатьяОборотов"]
        .fillna("")
        .astype(str)
        .str.replace("\xa0", " ", regex=False)
        .str.replace("\u200b", "", regex=False)
        .str.strip()
        .str.casefold()
    )
    has_bdr = art.str.contains(r"\(бдр\)", regex=True, na=False) | art.eq("бдр")
    amount = frame["Сумма"].map(_parse_money)
    if float(amount.abs().median() or 0) < 500_000:
        amount = amount * 1000.0

    plan_mask = scen.eq("план") & ~has_bdr
    fact_mask = scen.eq("факт")
    frame["plan"] = amount.where(plan_mask, 0.0)
    frame["fact"] = amount.where(fact_mask, 0.0)
    frame["project"] = (
        frame.get("Проект", pd.Series("—", index=frame.index))
        .fillna("—")
        .astype(str)
        .str.strip()
        .replace("", "—")
    )

    projects = ["Все"] + sorted(frame["project"].unique().tolist(), key=str.casefold)
    filtered = frame if not project or project == "Все" else frame[frame["project"] == project]
    if filtered.empty:
        payload = _empty_payload(source=source, project=project)
        payload["meta"]["files"] = 1
        payload["filters"]["projects"] = projects
        return payload

    grouped = (
        filtered.groupby("project", as_index=False)[["plan", "fact"]]
        .sum()
        .sort_values("fact", ascending=False)
    )
    grouped["deviation"] = grouped["fact"] - grouped["plan"]
    grouped["remainder"] = grouped["plan"] - grouped["fact"]

    project_rows = [
        {
            "project": str(row["project"]),
            "plan": round(float(row["plan"]), 2),
            "fact": round(float(row["fact"]), 2),
            "deviation": round(float(row["deviation"]), 2),
            "remainder": round(float(row["remainder"]), 2),
        }
        for _, row in grouped.iterrows()
    ]
    plan_sum = float(grouped["plan"].sum())
    fact_sum = float(grouped["fact"].sum())
    return {
        "meta": {
            "rows": int(len(filtered)),
            "source": source,
            "data_mode": DATA_MODE,
            "files": 1,
            "rule": "БДДС∧ПЛАН без (БДР) / БДДС∧ФАКТ, без фильтра лотов",
        },
        "filters": {
            "projects": projects,
            "applied": {"project": project or "Все"},
        },
        "kpis": {
            "plan_mln": _mln(plan_sum),
            "fact_mln": _mln(fact_sum),
            "deviation_mln": _mln(fact_sum - plan_sum),
            "remainder_mln": _mln(plan_sum - fact_sum),
        },
        "tremor": {
            "by_project": [
                {
                    "project": row["project"],
                    "plan": _mln(row["plan"]),
                    "fact": _mln(row["fact"]),
                    "deviation": _mln(row["deviation"]),
                }
                for row in project_rows
            ]
        },
        "project_rows": project_rows,
    }
