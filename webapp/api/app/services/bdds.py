from __future__ import annotations

import json
import math
import re
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from app.config import DATA_MODE
from app.services.data_paths import latest_web_file

_MONTHS = (
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
)


def _load_json_list(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.is_file():
        return []
    try:
        with path.open(encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        for key in ("data", "rows", "items"):
            if isinstance(data.get(key), list):
                return [row for row in data[key] if isinstance(row, dict)]
    return []


def _turnover_article_has_lot_and_sublot(raw: object) -> bool:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return False
    value = (
        str(raw)
        .replace("\xa0", " ")
        .replace("\u200b", "")
        .replace("\ufeff", "")
        .strip()
        .casefold()
        .replace("ё", "е")
    )
    if not value:
        return False
    if re.search(r"\bлот\b\s*[№#]?\s*\d", value):
        return True
    if re.search(r"\blots?\b\s*[#№]?\s*\d", value):
        return True
    if re.match(r"^\d+\.\d+(?:\.\d+)?\b", value):
        return True
    return any(marker in value for marker in ("подлот", "под лот", "сублот", "sub lot", "sublot"))


def _parse_money(value: Any) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else 0.0
    text = str(value).strip().replace("\xa0", "").replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(",", "")
    elif "," in text:
        parts = text.split(",")
        text = "".join(parts[:-1]) + "." + parts[-1] if len(parts[-1]) <= 2 else text.replace(",", "")
    try:
        amount = float(text)
    except ValueError:
        return 0.0
    return amount if math.isfinite(amount) else 0.0


def _parse_periods(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce", dayfirst=False, format="mixed")
    missing = parsed.isna()
    if missing.any():
        parsed.loc[missing] = pd.to_datetime(
            series.loc[missing], errors="coerce", dayfirst=True, format="mixed"
        )
    return parsed


def _mln(value: float) -> float:
    return round(float(value or 0.0) / 1_000_000, 1)


def _empty_payload(
    *,
    source: str,
    project: str | None,
    date_from: date | None,
    date_to: date | None,
    view: str,
) -> dict[str, Any]:
    return {
        "meta": {"rows": 0, "source": source, "data_mode": DATA_MODE, "files": 0},
        "filters": {
            "projects": ["Все"],
            "date_min": None,
            "date_max": None,
            "applied": {
                "project": project or "Все",
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
                "view": view,
            },
        },
        "kpis": {"plan_mln": 0.0, "fact_mln": 0.0, "deviation_mln": 0.0},
        "tremor": {"by_period": [], "by_project": []},
        "period_rows": [],
        "project_rows": [],
    }


def build_bdds_payload(
    *,
    project: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    view: str = "monthly",
) -> dict[str, Any]:
    view = view if view in {"monthly", "cumulative"} else "monthly"
    path = latest_web_file("_dannye.json")
    rows = _load_json_list(path)
    source = path.name if path else "1с_*_dannye.json"
    if not rows:
        return _empty_payload(source=source, project=project, date_from=date_from, date_to=date_to, view=view)

    frame = pd.DataFrame(rows)
    required = {"ТипСтатьи", "СтатьяОборотов", "Период", "Сумма"}
    if frame.empty or not required.issubset(frame.columns):
        return _empty_payload(source=source, project=project, date_from=date_from, date_to=date_to, view=view)

    article_type = frame["ТипСтатьи"].fillna("").astype(str).str.casefold()
    frame = frame[article_type.str.contains("бддс", regex=False)].copy()
    frame = frame[frame["СтатьяОборотов"].map(_turnover_article_has_lot_and_sublot).fillna(False)].copy()
    if frame.empty:
        return _empty_payload(source=source, project=project, date_from=date_from, date_to=date_to, view=view)

    if "РасходДоход" in frame:
        expense = frame["РасходДоход"].fillna("").astype(str).str.casefold().str.contains(
            "расход|expense", regex=True
        )
        if expense.any():
            frame = frame[expense].copy()

    frame["period_date"] = _parse_periods(frame["Период"])
    frame = frame[frame["period_date"].notna()].copy()
    frame["amount"] = frame["Сумма"].map(_parse_money)
    if not frame.empty and frame["amount"].abs().median() < 500_000:
        frame["amount"] *= 1000
    scenario = frame.get("Сценарий", pd.Series("", index=frame.index)).fillna("").astype(str).str.casefold()
    frame["kind"] = ""
    frame.loc[scenario.str.contains("факт", regex=False), "kind"] = "fact"
    plan_names = {"план", "план бюджет", "бюджет план"}
    plan_mask = (scenario.str.contains("план", regex=False) & ~scenario.str.contains("факт", regex=False)) | scenario.isin(plan_names)
    frame.loc[plan_mask & (frame["kind"] != "fact"), "kind"] = "plan"
    frame = frame[frame["kind"] != ""].copy()
    if frame.empty:
        return _empty_payload(source=source, project=project, date_from=date_from, date_to=date_to, view=view)

    frame["project"] = frame.get("Проект", pd.Series("—", index=frame.index)).fillna("—").astype(str).str.strip().replace("", "—")
    frame["period_key"] = frame["period_date"].dt.strftime("%Y-%m")
    frame["period"] = frame["period_date"].dt.month.map(lambda month: _MONTHS[month - 1]) + " " + frame["period_date"].dt.year.astype(str)
    projects = ["Все"] + sorted(frame["project"].unique().tolist(), key=str.casefold)
    date_min = frame["period_date"].min().date().isoformat()
    date_max = frame["period_date"].max().date().isoformat()

    filtered = frame
    if project and project != "Все":
        filtered = filtered[filtered["project"] == project]
    if date_from:
        filtered = filtered[filtered["period_date"].dt.date >= date_from]
    if date_to:
        filtered = filtered[filtered["period_date"].dt.date <= date_to]

    if filtered.empty:
        payload = _empty_payload(source=source, project=project, date_from=date_from, date_to=date_to, view=view)
        payload["meta"]["files"] = 1
        payload["filters"].update({"projects": projects, "date_min": date_min, "date_max": date_max})
        return payload

    grouped = (
        filtered.pivot_table(
            index=["project", "period_key", "period"],
            columns="kind",
            values="amount",
            aggfunc="sum",
            fill_value=0.0,
        )
        .reset_index()
    )
    for column in ("plan", "fact"):
        if column not in grouped:
            grouped[column] = 0.0
    grouped["deviation"] = grouped["fact"] - grouped["plan"]
    period_rows_df = grouped.groupby(["period_key", "period"], as_index=False)[["plan", "fact", "deviation"]].sum().sort_values("period_key")
    if view == "cumulative":
        period_rows_df[["plan", "fact", "deviation"]] = period_rows_df[["plan", "fact", "deviation"]].cumsum()
    project_rows_df = grouped.groupby("project", as_index=False)[["plan", "fact", "deviation"]].sum().sort_values("fact", ascending=False)

    def records(data: pd.DataFrame, label: str) -> list[dict[str, Any]]:
        return [
            {
                label: str(row[label]),
                "plan": round(float(row["plan"]), 2),
                "fact": round(float(row["fact"]), 2),
                "deviation": round(float(row["deviation"]), 2),
            }
            for _, row in data.iterrows()
        ]

    period_rows = records(period_rows_df, "period")
    project_rows = records(project_rows_df, "project")
    return {
        "meta": {"rows": len(filtered), "source": source, "data_mode": DATA_MODE, "files": 1},
        "filters": {
            "projects": projects,
            "date_min": date_min,
            "date_max": date_max,
            "applied": {
                "project": project or "Все",
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
                "view": view,
            },
        },
        "kpis": {
            "plan_mln": _mln(float(filtered.loc[filtered["kind"] == "plan", "amount"].sum())),
            "fact_mln": _mln(float(filtered.loc[filtered["kind"] == "fact", "amount"].sum())),
            "deviation_mln": _mln(float(filtered.loc[filtered["kind"] == "fact", "amount"].sum() - filtered.loc[filtered["kind"] == "plan", "amount"].sum())),
        },
        "tremor": {
            "by_period": [{**row, "plan": _mln(row["plan"]), "fact": _mln(row["fact"]), "deviation": _mln(row["deviation"])} for row in period_rows],
            "by_project": [{**row, "plan": _mln(row["plan"]), "fact": _mln(row["fact"]), "deviation": _mln(row["deviation"])} for row in project_rows],
        },
        "period_rows": period_rows,
        "project_rows": project_rows,
    }
