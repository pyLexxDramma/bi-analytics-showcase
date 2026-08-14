"""Общий слой финансовых экранов на коде [main] (`dashboards/finance_from_1c.py`).

Единый источник — `reference_dannye` активной версии `web_data.db` (правило
`dashboard-data-architecture`: каталог `web/` — это ETL, экраны читают только БД).

Экраны, которые сюда ходят:
  #2 БДДС              — `try_synthetic_budget_from_1c_dannye`
  #3 БДР               — `try_synthetic_bdr_from_1c_dannye`
  #4 утв. бюджет       — накопительный срез БДДС (та же рамка, group="month")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

import pandas as pd

from app.services.core_bridge import (
    active_version_id,
    ensure_core_path,
    ensure_renderers_shim,
    import_dashboard_module,
    load_msp_frame,
    load_version_df,
    session_state,
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


# ==================== путь экрана «БДДС (расходы)» ====================
# Транскрипция `dashboards/_renderers.py::dashboard_budget_by_period` (строки 14472–15683):
# кадр MSP → фильтры → 1С-fallback → сводка по (период × проект) → overlay 1С →
# сетка месяцев по календарю → finalize. Считать по «голому»
# `try_synthetic_budget_from_1c_dannye` нельзя: экран берёт границы календаря из MSP
# («Конец план»), сужает синтетику до проектов MSP и достраивает пустые месяцы.

PERIOD_KEY_COL = "period_original"
RESERVE_COL = "reserve budget"


@dataclass
class BddsScreenFrame:
    """Свод БДДС в том виде, в котором его рисует экран [main]."""

    version_id: int | None = None
    summary: pd.DataFrame | None = None
    reference_rows: int = 0
    project_options: list[str] = field(default_factory=list)
    date_min: date | None = None
    date_max: date | None = None
    cal_start: date | None = None
    cal_end: date | None = None
    mode: str = MODE_UNAVAILABLE
    used_1c: bool = False
    hints: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.summary is not None and not self.summary.empty


def _core_modules() -> tuple[Any, Any, Any, Any]:
    """(finance_from_1c, project_labels, data_quality_hints, utils) кода [main]."""
    ensure_core_path()
    ensure_renderers_shim()
    import utils  # type: ignore

    return (
        import_dashboard_module("finance_from_1c"),
        import_dashboard_module("project_labels"),
        import_dashboard_module("data_quality_hints"),
        utils,
    )


def _as_date(value: Any) -> date | None:
    ts = pd.to_datetime(value, errors="coerce")
    return ts.date() if pd.notna(ts) else None


def _clamp(value: date | None, low: date | None, high: date | None) -> date | None:
    """main отдаёт границы через `st.date_input(min_value=…, max_value=…)`."""
    if value is None:
        return None
    if low is not None and value < low:
        return low
    if high is not None and value > high:
        return high
    return value


def _recalc_reserve(frame: pd.DataFrame) -> pd.DataFrame:
    """`_renderers._bdds_recalc_reserve`: отклонение БДДС = факт − план."""
    if frame is None or frame.empty:
        return frame
    out = frame.copy()
    if PLAN_COL not in out.columns or FACT_COL not in out.columns:
        return out
    plan = pd.to_numeric(out[PLAN_COL], errors="coerce").fillna(0.0)
    fact = pd.to_numeric(out[FACT_COL], errors="coerce").fillna(0.0)
    out[RESERVE_COL] = fact - plan
    return out


def _to_period(value: Any, freq: str) -> Any:
    if isinstance(value, pd.Period):
        return value if value.freqstr[0] == freq else value.asfreq(freq)
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return pd.NaT
    try:
        return pd.Period(str(value), freq=freq)
    except (ValueError, TypeError):
        pass
    ts = pd.to_datetime(value, errors="coerce")
    return ts.to_period(freq) if pd.notna(ts) else pd.NaT


def _normalize_period_keys(frame: pd.DataFrame, *, freq: str) -> pd.DataFrame:
    """`_renderers._bdds_normalize_period_original` с учётом выбранной группировки."""
    if frame is None or frame.empty or PERIOD_KEY_COL not in frame.columns:
        return frame
    out = frame.copy()
    out[PERIOD_KEY_COL] = out[PERIOD_KEY_COL].map(lambda v: _to_period(v, freq))
    return out[out[PERIOD_KEY_COL].notna()].copy()


def _regroup_periods(frame: pd.DataFrame, *, freq: str) -> pd.DataFrame:
    """Месячная сетка → кварталы/годы: суммы по (проект × период) новой частоты."""
    if frame is None or frame.empty or PERIOD_KEY_COL not in frame.columns:
        return frame
    out = frame.copy()
    out[PERIOD_KEY_COL] = out[PERIOD_KEY_COL].map(lambda v: _to_period(v, freq))
    out = out[out[PERIOD_KEY_COL].notna()]
    grouped = (
        out.groupby([PROJECT_COL, PERIOD_KEY_COL], dropna=False)[[PLAN_COL, FACT_COL]]
        .sum()
        .reset_index()
    )
    return _recalc_reserve(grouped)


def _restrict_project_options(
    fin: Any,
    labels_mod: Any,
    options: list[str],
    msp: pd.DataFrame,
) -> list[str]:
    """`restrict_project_filter_labels_to_finance_data`: в фильтре только проекты с суммами.

    В копии ядра showcase этой функции ещё нет (она новее) — тогда повторяем её
    логику здесь: ключи проектов из MSP-колонок бюджета и из синтетики 1С.
    """
    if not options:
        return list(options)
    try:
        return list(fin.restrict_project_filter_labels_to_finance_data(options, msp, kind="bdds"))
    except AttributeError:
        pass
    except Exception:  # noqa: BLE001 — список фильтра не должен ломать отчёт
        return list(options)

    data_keys: set[str] = set()
    money_cols = [c for c in (PLAN_COL, FACT_COL) if c in msp.columns]
    if money_cols and PROJECT_COL in msp.columns:
        amounts = None
        for column in money_cols:
            values = pd.to_numeric(msp[column], errors="coerce").fillna(0.0).abs()
            amounts = values if amounts is None else amounts + values
        if amounts is not None:
            by_project = amounts.groupby(msp[PROJECT_COL]).sum()
            for name, total in by_project.items():
                if float(total) > 0.0:
                    key = labels_mod.project_filter_norm_key(name)
                    if key:
                        data_keys.add(key)
    try:
        syn = fin.try_synthetic_budget_from_1c_dannye()
    except Exception:  # noqa: BLE001
        syn = None
    if syn is not None and not getattr(syn, "empty", True) and PROJECT_COL in syn.columns:
        for name in syn[PROJECT_COL].dropna().unique():
            key = labels_mod.project_filter_norm_key(name)
            if key:
                data_keys.add(key)
    if not data_keys:
        return list(options)
    out: list[str] = []
    for label in options:
        key = labels_mod.project_filter_norm_key(label)
        if key and labels_mod._project_norm_key_matches_msp_keys(key, data_keys):
            out.append(str(label).strip())
    return out


def load_bdds_screen_frame(
    *,
    projects: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    group: str = "month",
    view: str = "monthly",
) -> BddsScreenFrame:
    """Свод БДДС по пути экрана [main] (кадр MSP + обороты 1С активной версии БД)."""
    group = group if group in GROUPS else "month"
    view = view if view in VIEW_LABELS else "monthly"
    # Обороты 1С месячные: overlay/finalize [main] считаем по месяцам, а квартал
    # и год получаем перегруппировкой готовой месячной сетки.
    group_col = GROUPS["month"]
    freq = GROUP_FREQ["month"]
    target_freq = GROUP_FREQ[group]
    selected = [str(p).strip() for p in (projects or []) if str(p).strip()]

    try:
        vid = active_version_id()
    except Exception as exc:  # noqa: BLE001
        return BddsScreenFrame(error=f"web_data.db недоступна: {exc}")
    if not vid:
        return BddsScreenFrame(error="В web_data.db нет активной версии — выполните ingest в админке.")

    try:
        fin, labels_mod, hints_mod, utils_mod = _core_modules()
    except Exception as exc:  # noqa: BLE001
        return BddsScreenFrame(version_id=vid, error=f"Код [main] не загружается: {type(exc).__name__}: {exc}")

    try:
        reference = load_version_df(vid, "reference_dannye")
    except Exception as exc:  # noqa: BLE001
        return BddsScreenFrame(version_id=vid, error=f"Не читается reference_dannye: {exc}")
    if reference is None or getattr(reference, "empty", True):
        return BddsScreenFrame(
            version_id=vid,
            error=f"В версии {vid} нет оборотов 1С (file_type=reference_dannye).",
        )
    # Код [main] (`resolve_reference_1c_dannye`) берёт обороты из session_state.
    session_state()["reference_1c_dannye"] = reference

    msp = load_msp_frame(vid)
    if msp is None or getattr(msp, "empty", True):
        return BddsScreenFrame(
            version_id=vid,
            error=f"В версии {vid} нет MSP (file_type=project) — экран БДДС берёт из него календарь.",
        )
    msp = labels_mod.apply_unified_project_column(msp.copy(), PROJECT_COL)

    options = _restrict_project_options(fin, labels_mod, main_project_labels(msp[PROJECT_COL]), msp)

    proj_df = msp
    if selected:
        proj_df = labels_mod.filter_dataframe_by_project_labels(msp, selected, col=PROJECT_COL)
    utils_mod.ensure_date_columns(proj_df)

    end_all = pd.to_datetime(msp.get(PERIOD_END_COL), errors="coerce")
    end_sel = pd.to_datetime(proj_df.get(PERIOD_END_COL), errors="coerce")
    def_start = _as_date(end_sel.min()) if end_sel is not None and end_sel.notna().any() else None
    def_end = _as_date(end_sel.max()) if end_sel is not None and end_sel.notna().any() else None
    min_all = _as_date(end_all.min()) if end_all is not None and end_all.notna().any() else def_start
    max_all = _as_date(end_all.max()) if end_all is not None and end_all.notna().any() else def_end

    narrow_key: str | None = None
    if len(selected) == 1:
        narrow_key = str(labels_mod.project_filter_norm_key(selected[0])).strip() or None
        try:
            lo, hi = fin.bdds_project_turnover_date_bounds(
                str(selected[0]), reference_1c_dannye=reference
            )
        except Exception:  # noqa: BLE001
            lo = hi = None
        if lo is not None and hi is not None:
            def_start = lo if def_start is None or lo < def_start else def_start
            def_end = hi if def_end is None or hi > def_end else def_end
            min_all = lo if min_all is None or lo < min_all else min_all
            max_all = hi if max_all is None or hi > max_all else max_all

    cal_start = _clamp(date_from, min_all, max_all) or def_start
    cal_end = _clamp(date_to, min_all, max_all) or def_end
    if cal_start and cal_end and cal_start > cal_end:
        cal_start, cal_end = cal_end, cal_start

    filtered = proj_df.copy()
    if cal_start is not None and cal_end is not None and PERIOD_END_COL in filtered.columns:
        end_series = pd.to_datetime(filtered[PERIOD_END_COL], errors="coerce")
        start_ts = pd.Timestamp(cal_start)
        end_ts = pd.Timestamp(cal_end)
        end_inclusive = end_ts + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        if "plan start" in filtered.columns:
            start_col = pd.to_datetime(filtered["plan start"], errors="coerce")
            keep = (
                end_series.notna()
                & start_col.notna()
                & (start_col <= end_inclusive)
                & (end_series >= start_ts)
            )
        else:
            keep = (end_series >= start_ts) & (end_series <= end_inclusive)
        filtered = filtered[keep].copy()

    utils_mod.ensure_budget_columns(filtered)
    # Явно передаём reference: stub/streamlit session в API не всегда виден коду [main].
    # force_from_1c — MSP-календарь без реальных сумм не должен блокировать обороты 1С.
    filtered, used_1c = fin.ensure_budget_frame_with_fallback(
        filtered,
        show_caption=False,
        restrict_projects_from_df=True,
        period_start=pd.Timestamp(cal_start) if cal_start else None,
        period_end=pd.Timestamp(cal_end) if cal_end else None,
        force_from_1c=True,
        narrow_to_project_norm_key=narrow_key,
        reference_1c_dannye=reference,
    )
    if not used_1c:
        try:
            syn = fin.try_synthetic_budget_from_1c_dannye(reference_1c_dannye=reference)
            if syn is not None and not getattr(syn, "empty", True):
                filtered = syn
                used_1c = True
        except Exception:  # noqa: BLE001
            pass
    if selected:
        filtered = labels_mod.filter_dataframe_by_project_labels(filtered, selected, col=PROJECT_COL)
    utils_mod.ensure_date_columns(filtered)
    utils_mod.ensure_budget_columns(filtered)
    if filtered is None or filtered.empty:
        return BddsScreenFrame(
            version_id=vid,
            reference_rows=int(len(reference)),
            project_options=list(options),
            date_min=min_all,
            date_max=max_all,
            cal_start=cal_start,
            cal_end=cal_end,
            mode=MODE_SYNTHETIC if used_1c else MODE_UNAVAILABLE,
            used_1c=bool(used_1c),
        )

    frame_attrs = dict(getattr(filtered, "attrs", {}) or {})
    # MSP-календарь часто без budget plan/fact — колонки появятся из 1С overlay,
    # но ensure_* может их не создать; без них был KeyError → API 500.
    for _col in (PLAN_COL, FACT_COL):
        if _col not in filtered.columns:
            filtered[_col] = 0.0
    filtered[PLAN_COL] = pd.to_numeric(filtered[PLAN_COL], errors="coerce")
    filtered[FACT_COL] = pd.to_numeric(filtered[FACT_COL], errors="coerce")
    filtered = _recalc_reserve(filtered)

    if group_col not in filtered.columns and PERIOD_END_COL in filtered.columns:
        end_series = pd.to_datetime(filtered[PERIOD_END_COL], errors="coerce")
        filtered[group_col] = end_series.dt.to_period(freq)
    if group_col not in filtered.columns:
        return BddsScreenFrame(
            version_id=vid,
            reference_rows=int(len(reference)),
            project_options=list(options),
            date_min=min_all,
            date_max=max_all,
            cal_start=cal_start,
            cal_end=cal_end,
            error=f"Столбец периода «{group_col}» не найден.",
        )

    summary = (
        filtered.groupby([group_col, PROJECT_COL], dropna=False)
        .agg({PLAN_COL: "sum", FACT_COL: "sum", RESERVE_COL: "sum"})
        .reset_index()
    )
    summary[PERIOD_KEY_COL] = summary[group_col]
    summary[group_col] = summary[group_col].apply(utils_mod.format_period_ru)

    project_keys = {labels_mod.project_filter_norm_key(p) for p in selected}
    project_keys.discard("")

    summary, overlay_1c = fin.overlay_1c_on_budget_summary(
        summary,
        period_col=group_col,
        period_start=pd.Timestamp(cal_start) if cal_start else None,
        period_end=pd.Timestamp(cal_end) if cal_end else None,
        project_norm_keys=project_keys or None,
        narrow_to_project_norm_key=narrow_key,
        reference_1c_dannye=reference,
    )
    used_1c = bool(used_1c or overlay_1c)
    summary = _normalize_period_keys(_recalc_reserve(summary), freq=freq)

    if group == "month" and view == "monthly":
        summary = fin.expand_budget_month_grid(
            summary,
            period_col=group_col,
            cal_start=cal_start,
            cal_end=cal_end,
            fill_columns=(PLAN_COL, FACT_COL, RESERVE_COL),
            group_by=PROJECT_COL if PROJECT_COL in summary.columns else None,
        )
        summary = _normalize_period_keys(_recalc_reserve(summary), freq=freq)

    summary = fin.finalize_budget_summary_for_display(
        summary,
        period_col=group_col,
        period_start=pd.Timestamp(cal_start) if cal_start else None,
        period_end=pd.Timestamp(cal_end) if cal_end else None,
        project_norm_keys=project_keys or None,
        narrow_to_project_norm_key=narrow_key,
        reference_1c_dannye=reference,
    )
    summary = _normalize_period_keys(_recalc_reserve(summary), freq=freq)
    if target_freq != freq:
        summary = _regroup_periods(summary, freq=target_freq)

    out = summary.rename(
        columns={PROJECT_COL: "project", PLAN_COL: "plan", FACT_COL: "fact", RESERVE_COL: "deviation"}
    )
    out["period"] = out[PERIOD_KEY_COL].map(format_period)
    out = out.rename(columns={PERIOD_KEY_COL: "period_key"})
    out = out[["project", "period_key", "period", "plan", "fact", "deviation"]]
    out = out.sort_values(["project", "period_key"]).reset_index(drop=True)

    return BddsScreenFrame(
        version_id=vid,
        summary=out,
        reference_rows=int(len(reference)),
        project_options=list(options),
        date_min=min_all,
        date_max=max_all,
        cal_start=cal_start,
        cal_end=cal_end,
        mode=MODE_SYNTHETIC if used_1c else MODE_UNAVAILABLE,
        used_1c=used_1c,
        hints=_bdds_hints(
            fin,
            hints_mod,
            labels_mod,
            attrs=frame_attrs,
            summary=out,
            reference=reference,
            selected=selected,
            used_1c=used_1c,
        ),
    )


def _approved_budget_fiz_map(reference: pd.DataFrame) -> dict[str, set[str]]:
    """Связь «проект → ФИЗ» из оборотов 1С для фильтра утверждённого бюджета."""
    project_candidates = (
        "Проект",
        "project",
        "проект",
        "проектдляотчетов",
        "проект для отчетов",
        "ИмяПроекта",
    )
    fiz_candidates = (
        "ФИЗ",
        "Физ",
        "Организация",
        "Название организации",
        "НаименованиеОрганизации",
        "ЮрЛицо",
        "Юридическое лицо",
    )
    project_col = next((col for col in project_candidates if col in reference.columns), None)
    fiz_col = next((col for col in fiz_candidates if col in reference.columns), None)
    if not project_col or not fiz_col:
        return {}
    out: dict[str, set[str]] = {}
    for project, fiz in zip(reference[project_col], reference[fiz_col]):
        project_name = str(project or "").strip()
        fiz_name = str(fiz or "").strip()
        if project_name and fiz_name and fiz_name.casefold() not in {"nan", "none"}:
            out.setdefault(project_name.casefold(), set()).add(fiz_name)
    return out


def load_approved_budget_screen_frame(
    *,
    projects: list[str] | None = None,
    fiz: str | None = None,
) -> tuple[BddsScreenFrame, list[str]]:
    """Утверждённый бюджет — накопительный итог полного пути БДДС [main]."""
    selected = [str(project).strip() for project in (projects or []) if str(project).strip()]
    try:
        vid = active_version_id()
        reference = load_version_df(vid, "reference_dannye") if vid else None
    except Exception as exc:  # noqa: BLE001
        return BddsScreenFrame(error=f"Не читаются обороты 1С: {exc}"), []
    fiz_map = _approved_budget_fiz_map(reference) if reference is not None else {}
    fiz_options = sorted({item for values in fiz_map.values() for item in values}, key=str.casefold)
    if fiz and fiz != "Все":
        matching = {
            project
            for project, values in fiz_map.items()
            if any(value.casefold() == fiz.casefold() for value in values)
        }
        selected = [
            project
            for project in selected
            if project.casefold() in matching
        ] if selected else list(matching)
    screen = load_bdds_screen_frame(projects=selected, group="month", view="monthly")
    return screen, fiz_options


def _bdds_hints(
    fin: Any,
    hints_mod: Any,
    labels_mod: Any,
    *,
    attrs: dict[str, Any],
    summary: pd.DataFrame,
    reference: pd.DataFrame,
    selected: list[str],
    used_1c: bool,
) -> list[str]:
    """Жёлтая карточка под таблицами — `collect_budget_1c_hints` [main]."""
    hint_attrs = dict(attrs)
    try:
        syn = fin.try_synthetic_budget_from_1c_dannye(reference_1c_dannye=reference)
        if syn is not None and not syn.empty and "plan_month" in syn.columns:
            hint_attrs["bdds_1c_latest_month"] = format_period(
                pd.Period(syn["plan_month"].max(), freq="M")
            )
    except Exception:  # noqa: BLE001
        pass
    plan_sum = float(pd.to_numeric(summary.get("plan"), errors="coerce").fillna(0.0).sum())
    fact_sum = float(pd.to_numeric(summary.get("fact"), errors="coerce").fillna(0.0).sum())
    if plan_sum < ZERO_PERIOD_THRESHOLD_RUB:
        hint_attrs.pop("bddds_plan_imputed_ratio", None)
    try:
        no_plan_keys = fin.bddds_project_norm_keys_without_plan_scenario(reference)
    except Exception:  # noqa: BLE001
        no_plan_keys = set()
    display_no_plan = False
    if no_plan_keys and fact_sum >= ZERO_PERIOD_THRESHOLD_RUB:
        display_no_plan = (
            any(labels_mod.project_filter_norm_key(p) in no_plan_keys for p in selected)
            if selected
            else True
        )
    try:
        return list(
            hints_mod.collect_budget_1c_hints(
                hint_attrs,
                used_fallback_1c=bool(used_1c),
                display_has_plan=plan_sum >= ZERO_PERIOD_THRESHOLD_RUB,
                display_no_plan_scenario=display_no_plan,
            )
        )
    except Exception:  # noqa: BLE001
        return []


def main_project_labels(names: Any, *, apply_exclude_names: bool = True) -> list[str]:
    """Подписи проектов из ядра — `project_labels_for_filter` [main]."""
    if names is None or getattr(names, "empty", True):
        return []
    _, labels_mod, _, _ = _core_modules()
    return list(
        labels_mod.project_labels_for_filter(
            pd.Series(names), apply_exclude_names=apply_exclude_names
        )
    )


def bdds_block_labels(summary: pd.DataFrame) -> list[str]:
    """Подписи проектов для блоков сводной таблицы — `_unique_project_labels_for_select`."""
    if summary is None or summary.empty or "project" not in summary.columns:
        return []
    return main_project_labels(summary["project"], apply_exclude_names=False)


def bdds_block_rows(summary: pd.DataFrame, label: str) -> pd.DataFrame:
    """Строки блока одного проекта — `_bdds_slice_for_project` (свод по периодам)."""
    empty = pd.DataFrame(columns=["period_key", "period", "plan", "fact", "deviation"])
    if summary is None or summary.empty:
        return empty
    _, labels_mod, _, _ = _core_modules()
    key = labels_mod.project_filter_norm_key(label)
    match = summary["project"].map(labels_mod.project_filter_norm_key).map(
        lambda rk: labels_mod._project_norm_key_matches_msp_keys(rk, {key})
    )
    rows = summary[match]
    if rows.empty:
        return empty
    out = rows.groupby("period_key", dropna=False, sort=True)[["plan", "fact"]].sum().reset_index()
    out["period"] = out["period_key"].map(format_period)
    out["deviation"] = out["fact"] - out["plan"]
    return out.sort_values("period_key").reset_index(drop=True)


def bdds_project_totals(summary: pd.DataFrame) -> pd.DataFrame:
    """Таблица «БДДС по проектам»: свод по norm-key, подпись — самое длинное имя (как в [main])."""
    empty = pd.DataFrame(columns=["project", "plan", "fact", "deviation"])
    if summary is None or summary.empty:
        return empty
    _, labels_mod, _, _ = _core_modules()
    work = summary.copy()
    work["_pk"] = work["project"].map(labels_mod.project_filter_norm_key)
    name_by_pk: dict[str, str] = {}
    for name, key in zip(work["project"], work["_pk"]):
        if not key:
            continue
        if key not in name_by_pk or len(str(name)) > len(name_by_pk[key]):
            name_by_pk[key] = str(name)
    out = work.groupby("_pk", dropna=False)[["plan", "fact"]].sum().reset_index()
    out["project"] = out["_pk"].map(lambda k: name_by_pk.get(str(k), str(k)))
    out["deviation"] = out["fact"] - out["plan"]
    return (
        out[["project", "plan", "fact", "deviation"]]
        .sort_values("project", key=lambda s: s.astype(str).str.casefold())
        .reset_index(drop=True)
    )


def date_range_title_suffix(start: date | None, end: date | None) -> str:
    """«23.03.2024 – 30.07.2029» как `utils.format_date_range_title_suffix` [main].

    Считаем здесь: в копии ядра showcase этой функции ещё нет, а суффикс нужен
    в заголовках графика и таблиц.
    """
    if start is None or end is None:
        return ""
    return f"{start.strftime('%d.%m.%Y')} – {end.strftime('%d.%m.%Y')}"


@dataclass
class BdrScreenFrame:
    version_id: int | None = None
    summary: pd.DataFrame | None = None
    reference_rows: int = 0
    project_options: list[str] = field(default_factory=list)
    date_min: date | None = None
    date_max: date | None = None
    cal_start: date | None = None
    cal_end: date | None = None
    mode: str = MODE_UNAVAILABLE
    used_1c: bool = False
    hints: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.summary is not None and not self.summary.empty


def load_bdr_screen_frame(
    *,
    projects: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    group: str = "month",
    view: str = "monthly",
) -> BdrScreenFrame:
    """Путь `dashboard_bdr` [main]: MSP → fallback 1С → фильтры → свод."""
    group = group if group in GROUPS else "month"
    selected = [str(p).strip() for p in (projects or []) if str(p).strip()]
    try:
        vid = active_version_id()
        fin, labels_mod, hints_mod, utils_mod = _core_modules()
        reference = load_version_df(vid, "reference_dannye") if vid else None
        msp = load_msp_frame(vid) if vid else None
    except Exception as exc:  # noqa: BLE001
        return BdrScreenFrame(error=f"Не читаются данные экрана БДР: {exc}")
    if not vid:
        return BdrScreenFrame(error="В web_data.db нет активной версии — выполните ingest в админке.")
    if reference is None or getattr(reference, "empty", True):
        return BdrScreenFrame(version_id=vid, error=f"В версии {vid} нет оборотов 1С (file_type=reference_dannye).")
    if msp is None or getattr(msp, "empty", True):
        return BdrScreenFrame(version_id=vid, error=f"В версии {vid} нет MSP (file_type=project).")

    session_state()["reference_1c_dannye"] = reference
    source = labels_mod.apply_unified_project_column(msp.copy(), PROJECT_COL)
    options = main_project_labels(source[PROJECT_COL])
    try:
        work, used_1c = fin.ensure_bdr_frame_with_fallback(source, restrict_projects_from_df=True)
    except Exception as exc:  # noqa: BLE001
        return BdrScreenFrame(version_id=vid, reference_rows=int(len(reference)), error=f"БДР fallback 1С: {exc}")
    if work is None or work.empty:
        return BdrScreenFrame(version_id=vid, reference_rows=int(len(reference)), project_options=options)

    work = labels_mod.apply_unified_project_column(work.copy(), PROJECT_COL)
    utils_mod.ensure_date_columns(work)
    plan_src, fact_src = _KIND_COLUMNS["bdr"]
    if plan_src not in work.columns or fact_src not in work.columns:
        return BdrScreenFrame(version_id=vid, reference_rows=int(len(reference)), project_options=options, error="В кадре БДР не найдены колонки расходов.")
    work[PLAN_COL] = pd.to_numeric(work[plan_src], errors="coerce").fillna(0.0)
    work[FACT_COL] = pd.to_numeric(work[fact_src], errors="coerce").fillna(0.0)
    work[PERIOD_END_COL] = pd.to_datetime(work.get(PERIOD_END_COL), errors="coerce")
    work = work[work[PERIOD_END_COL].notna()].copy()
    if work.empty:
        return BdrScreenFrame(version_id=vid, reference_rows=int(len(reference)), project_options=options)

    date_min, date_max = _as_date(work[PERIOD_END_COL].min()), _as_date(work[PERIOD_END_COL].max())
    filtered = labels_mod.filter_dataframe_by_project_labels(work, selected, col=PROJECT_COL) if selected else work
    defaults = filtered if not filtered.empty else work
    cal_start = _clamp(date_from, date_min, date_max) or _as_date(defaults[PERIOD_END_COL].min())
    cal_end = _clamp(date_to, date_min, date_max) or _as_date(defaults[PERIOD_END_COL].max())
    if cal_start and cal_end and cal_start > cal_end:
        cal_start, cal_end = cal_end, cal_start
    if cal_start is not None:
        start_ts = pd.Timestamp(cal_start)
        filtered = filtered[filtered[PERIOD_END_COL] >= start_ts]
    if cal_end is not None:
        end_ts = pd.Timestamp(cal_end)
        end_inclusive = end_ts + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        filtered = filtered[filtered[PERIOD_END_COL] <= end_inclusive]

    attrs = dict(getattr(work, "attrs", {}) or {})
    return BdrScreenFrame(
        version_id=vid,
        summary=group_by_period(filtered, group=group),
        reference_rows=int(len(reference)),
        project_options=options,
        date_min=date_min,
        date_max=date_max,
        cal_start=cal_start,
        cal_end=cal_end,
        mode=MODE_SYNTHETIC if used_1c else MODE_UNAVAILABLE,
        used_1c=bool(used_1c),
        hints=list(hints_mod.collect_bdr_hints(attrs)),
    )


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
