"""Общий слой финансовых экранов на коде [main] (`dashboards/finance_from_1c.py`).

Единый источник — `reference_dannye` активной версии `web_data.db` (правило
`dashboard-data-architecture`: каталог `web/` — это ETL, экраны читают только БД).

Экраны, которые сюда ходят:
  #2 БДДС              — `try_synthetic_budget_from_1c_dannye`
  #3 БДР               — `try_synthetic_bdr_from_1c_dannye`
  #4 утв. бюджет       — накопительный срез БДДС (та же рамка, group="month")
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

import pandas as pd

from app.services.core_bridge import (
    active_version_id,
    ensure_core_path,
    import_dashboard_module,
    load_version_df,
)

PROJECT_COL = "project name"
PERIOD_END_COL = "plan end"
PLAN_COL = "budget plan"
FACT_COL = "budget fact"

GROUPS: dict[str, str] = {"month": "plan_month", "quarter": "plan_quarter", "year": "plan_year"}
GROUP_LABELS: dict[str, str] = {"month": "Месяц", "quarter": "Квартал", "year": "Год"}
GROUP_FREQ: dict[str, str] = {"month": "M", "quarter": "Q", "year": "Y"}
VIEW_LABELS: dict[str, str] = {"monthly": "По месяцам", "cumulative": "Накопительно"}

# main `_FINANCE_CHART_MIN_MONTH_RUB`: месяц считается пустым, если |план| + |факт| < 0.5 млн
ZERO_PERIOD_THRESHOLD_RUB = 500_000.0

Kind = Literal["bdds", "bdr"]

_KIND_FUNC: dict[str, str] = {
    "bdds": "try_synthetic_budget_from_1c_dannye",
    "bdr": "try_synthetic_bdr_from_1c_dannye",
}
# БДР в [main] отдаёт помесячные расходы в своих колонках — приводим к общей схеме.
_KIND_COLUMNS: dict[str, tuple[str, str]] = {
    "bdds": (PLAN_COL, FACT_COL),
    "bdr": ("bdr_plan_expense", "bdr_fact_expense"),
}

MODE_SYNTHETIC = "synthetic_1c"
MODE_UNAVAILABLE = "unavailable"


@dataclass
class FinanceFrame:
    """Кадр финансового экрана + режим данных и причина, если данных нет."""

    kind: Kind
    version_id: int | None = None
    frame: pd.DataFrame | None = None
    mode: str = MODE_UNAVAILABLE
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.frame is not None and not self.frame.empty


def format_period(value: Any) -> str:
    """Подпись периода как в [main] (`utils.format_period_ru`): «Июль 2026», «К3 2026», «2026»."""
    ensure_core_path()
    try:
        from utils import format_period_ru  # type: ignore

        return str(format_period_ru(value))
    except Exception:  # noqa: BLE001 — подпись не должна ломать отчёт
        try:
            return str(pd.Period(value))
        except Exception:  # noqa: BLE001
            return str(value)


def mln(value: Any) -> float:
    try:
        return round(float(value or 0.0) / 1_000_000, 1)
    except (TypeError, ValueError):
        return 0.0


def load_finance_frame(kind: Kind = "bdds") -> FinanceFrame:
    """Кадр [main] по активной версии БД: project name / plan end / plan / fact / plan_*."""
    if kind not in _KIND_FUNC:
        return FinanceFrame(kind=kind, error=f"Неизвестный финансовый экран: {kind}")
    try:
        vid = active_version_id()
    except Exception as exc:  # noqa: BLE001
        return FinanceFrame(kind=kind, error=f"web_data.db недоступна: {exc}")
    if not vid:
        return FinanceFrame(
            kind=kind,
            error="В web_data.db нет активной версии — выполните ingest в админке.",
        )

    try:
        reference = load_version_df(vid, "reference_dannye")
    except Exception as exc:  # noqa: BLE001
        return FinanceFrame(kind=kind, version_id=vid, error=f"Не читается reference_dannye: {exc}")
    if reference is None or getattr(reference, "empty", True):
        return FinanceFrame(
            kind=kind,
            version_id=vid,
            error=f"В версии {vid} нет оборотов 1С (file_type=reference_dannye).",
        )

    try:
        module = import_dashboard_module("finance_from_1c")
        func = getattr(module, _KIND_FUNC[kind])
        frame = func(reference_1c_dannye=reference)
    except Exception as exc:  # noqa: BLE001
        return FinanceFrame(
            kind=kind,
            version_id=vid,
            error=f"{_KIND_FUNC[kind]} ({type(exc).__name__}): {exc}",
        )
    if frame is None or getattr(frame, "empty", True):
        return FinanceFrame(
            kind=kind,
            version_id=vid,
            error=(
                "Обороты 1С есть, но по правилам ТЗ (лот+подлот, сценарий План/Факт) "
                "не собралось ни одной строки."
            ),
        )

    normalized = _normalize_frame(frame, kind=kind)
    if normalized.empty:
        return FinanceFrame(
            kind=kind,
            version_id=vid,
            error=f"{_KIND_FUNC[kind]}: нет строк с разобранным периодом.",
        )
    return FinanceFrame(kind=kind, version_id=vid, frame=normalized, mode=MODE_SYNTHETIC)


def _normalize_frame(frame: pd.DataFrame, *, kind: Kind) -> pd.DataFrame:
    plan_src, fact_src = _KIND_COLUMNS[kind]
    out = frame.copy()
    if plan_src != PLAN_COL and plan_src in out.columns:
        out = out.rename(columns={plan_src: PLAN_COL})
    if fact_src != FACT_COL and fact_src in out.columns:
        out = out.rename(columns={fact_src: FACT_COL})
    for column in (PLAN_COL, FACT_COL):
        out[column] = pd.to_numeric(out.get(column), errors="coerce").fillna(0.0)
    if PROJECT_COL not in out.columns:
        out[PROJECT_COL] = "—"
    out[PROJECT_COL] = out[PROJECT_COL].fillna("—").astype(str).str.strip().replace("", "—")

    end = pd.to_datetime(out.get(PERIOD_END_COL), errors="coerce")
    if end.isna().all():
        for group_col in GROUPS.values():
            if group_col in out.columns:
                end = pd.PeriodIndex(out[group_col]).to_timestamp(how="end").to_series(index=out.index)
                break
    out[PERIOD_END_COL] = end
    out = out[out[PERIOD_END_COL].notna()].copy()
    if out.empty:
        return out
    out["plan_month"] = out[PERIOD_END_COL].dt.to_period("M")
    out["plan_quarter"] = out[PERIOD_END_COL].dt.to_period("Q")
    out["plan_year"] = out[PERIOD_END_COL].dt.to_period("Y")
    return out


def project_labels(frame: pd.DataFrame) -> list[str]:
    if frame is None or frame.empty or PROJECT_COL not in frame.columns:
        return []
    values = {str(v).strip() for v in frame[PROJECT_COL].dropna().tolist()}
    return sorted((v for v in values if v and v.lower() not in ("nan", "none", "nat")), key=str.casefold)


def date_bounds(frame: pd.DataFrame) -> tuple[date | None, date | None]:
    if frame is None or frame.empty or PERIOD_END_COL not in frame.columns:
        return None, None
    series = pd.to_datetime(frame[PERIOD_END_COL], errors="coerce").dropna()
    if series.empty:
        return None, None
    return series.min().date(), series.max().date()


def filter_frame(
    frame: pd.DataFrame,
    *,
    projects: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> pd.DataFrame:
    """Фильтры БДДС [main]: multiselect проектов (пусто = все) + диапазон по «Конец план»."""
    out = frame
    selected = [str(p).strip() for p in (projects or []) if str(p).strip()]
    if selected:
        wanted = {p.casefold() for p in selected}
        out = out[out[PROJECT_COL].astype(str).str.strip().str.casefold().isin(wanted)]
    if date_from is not None:
        out = out[out[PERIOD_END_COL].dt.date >= date_from]
    if date_to is not None:
        out = out[out[PERIOD_END_COL].dt.date <= date_to]
    return out.copy()


def group_by_period(frame: pd.DataFrame, *, group: str = "month") -> pd.DataFrame:
    """project / period_key (Period) / period (подпись) / plan / fact / deviation."""
    group_col = GROUPS.get(group, GROUPS["month"])
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["project", "period_key", "period", "plan", "fact", "deviation"])
    grouped = (
        frame.groupby([PROJECT_COL, group_col], dropna=False, sort=True)[[PLAN_COL, FACT_COL]]
        .sum()
        .reset_index()
        .rename(columns={PROJECT_COL: "project", group_col: "period_key", PLAN_COL: "plan", FACT_COL: "fact"})
    )
    grouped = grouped[grouped["period_key"].notna()].copy()
    grouped["period"] = grouped["period_key"].map(format_period)
    grouped["deviation"] = grouped["fact"] - grouped["plan"]
    return grouped.sort_values(["project", "period_key"]).reset_index(drop=True)


def expand_period_grid(
    rows: pd.DataFrame,
    *,
    group: str,
    date_from: date | None = None,
    date_to: date | None = None,
) -> pd.DataFrame:
    """Полная сетка периодов как `expand_budget_month_grid` в [main] (пустые = 0)."""
    if rows is None or rows.empty:
        return rows
    freq = GROUP_FREQ.get(group, "M")
    keys = pd.PeriodIndex(rows["period_key"])
    start = pd.Period(date_from, freq=freq) if date_from else keys.min()
    end = pd.Period(date_to, freq=freq) if date_to else keys.max()
    if start > end:
        start, end = end, start
    full = pd.period_range(start=start, end=end, freq=freq)
    parts: list[pd.DataFrame] = []
    for project, chunk in rows.groupby("project", sort=True):
        indexed = chunk.set_index("period_key").reindex(full)
        indexed["project"] = project
        indexed[["plan", "fact", "deviation"]] = indexed[["plan", "fact", "deviation"]].fillna(0.0)
        indexed = indexed.reset_index().rename(columns={"index": "period_key"})
        indexed["period"] = indexed["period_key"].map(format_period)
        parts.append(indexed)
    if not parts:
        return rows
    out = pd.concat(parts, ignore_index=True)
    return out.sort_values(["project", "period_key"]).reset_index(drop=True)


def aggregate_periods(rows: pd.DataFrame) -> pd.DataFrame:
    """Свод по периодам (все выбранные проекты вместе)."""
    if rows is None or rows.empty:
        return pd.DataFrame(columns=["period_key", "period", "plan", "fact", "deviation"])
    out = (
        rows.groupby("period_key", dropna=False, sort=True)[["plan", "fact"]]
        .sum()
        .reset_index()
    )
    out["period"] = out["period_key"].map(format_period)
    out["deviation"] = out["fact"] - out["plan"]
    return out.sort_values("period_key").reset_index(drop=True)


def aggregate_projects(rows: pd.DataFrame) -> pd.DataFrame:
    if rows is None or rows.empty:
        return pd.DataFrame(columns=["project", "plan", "fact", "deviation"])
    out = rows.groupby("project", dropna=False, sort=True)[["plan", "fact"]].sum().reset_index()
    out["deviation"] = out["fact"] - out["plan"]
    return out.sort_values("project", key=lambda s: s.astype(str).str.casefold()).reset_index(drop=True)


def cumulate(rows: pd.DataFrame) -> pd.DataFrame:
    """Накопительный вид [main]: cumsum план/факт, отклонение пересчитывается."""
    if rows is None or rows.empty:
        return rows
    out = rows.copy()
    out[["plan", "fact"]] = out[["plan", "fact"]].fillna(0.0).cumsum()
    out["deviation"] = out["fact"] - out["plan"]
    return out


def drop_zero_periods(rows: pd.DataFrame) -> pd.DataFrame:
    """«Скрывать месяцы, где план и факт равны 0» — порог [main] 0.5 млн."""
    if rows is None or rows.empty:
        return rows
    plan = rows["plan"].fillna(0.0).abs()
    fact = rows["fact"].fillna(0.0).abs()
    return rows.loc[(plan + fact) >= ZERO_PERIOD_THRESHOLD_RUB].copy()


def totals(frame: pd.DataFrame) -> dict[str, float]:
    """ИТОГО как в [main]: суммы план/факт и отклонение = факт − план."""
    if frame is None or frame.empty:
        return {"plan": 0.0, "fact": 0.0, "deviation": 0.0}
    plan = float(pd.to_numeric(frame[PLAN_COL], errors="coerce").fillna(0.0).sum())
    fact = float(pd.to_numeric(frame[FACT_COL], errors="coerce").fillna(0.0).sum())
    return {"plan": plan, "fact": fact, "deviation": fact - plan}


def records(rows: pd.DataFrame, *, fields: tuple[str, ...]) -> list[dict[str, Any]]:
    """Строки в JSON: суммы в рублях (округление до копеек), подписи — строками."""
    if rows is None or rows.empty:
        return []
    out: list[dict[str, Any]] = []
    for row in rows.to_dict("records"):
        item: dict[str, Any] = {}
        for field in fields:
            value = row.get(field)
            if field in ("plan", "fact", "deviation"):
                item[field] = round(float(value or 0.0), 2)
            else:
                item[field] = "" if value is None else str(value)
        out.append(item)
    return out
