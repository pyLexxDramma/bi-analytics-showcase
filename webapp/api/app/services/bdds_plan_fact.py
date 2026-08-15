from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

import pandas as pd

from app.config import DATA_MODE, WEB_DB_PATH
from app.services import bdds_plan_fact_edits as edit_store
from app.services.core_bridge import (
    active_version_id,
    import_renderers_module,
    load_msp_frame,
    load_version_df,
    session_state,
)
from app.services.db_ingest import db_status
from app.services.finance_1c import GROUP_LABELS, GROUPS, VIEW_LABELS, _clamp, main_project_labels
from app.services.project_scope import resolve_selected_projects
from app.services.report_cache import cache_get, cache_set
from app.services.users_bridge import import_auth

CACHE_ID = "bdds_plan_fact"
CACHE_VERSION = "v6-syn-unfiltered"
CACHE_MAX_AGE_SEC = 3600

GROUP_TO_EN = {"month": "Month", "quarter": "Quarter", "year": "Year"}
PERIOD_LABEL_EN = {"Month": "Месяц", "Quarter": "Квартал", "Year": "Год"}
PROJECT_COL_CANDIDATES = ("project name", "Проект")
EDITOR_COLUMNS = (
    "Раздел",
    "Лот",
    "Условие распределения",
    "План. начало",
    "План. окончание",
    "БДДС план (утверждённый), млн руб.",
    "БДДС факт, млн руб.",
    "A, %",
    "B, %",
    "C, %",
)
DIST_OPTIONS = ["Равномерно", "% Распределения"]


def _project_col(frame: pd.DataFrame) -> str | None:
    for col in PROJECT_COL_CANDIDATES:
        if col in frame.columns:
            return col
    return None


def _mln(value: float) -> float:
    return round(float(value or 0) / 1_000_000, 2)


def _renderers():
    return import_renderers_module()


def _utils():
    from app.services.core_bridge import ensure_core_path

    ensure_core_path()
    import utils  # type: ignore

    return utils


def _labels_mod():
    from app.services.core_bridge import import_dashboard_module

    return import_dashboard_module("project_labels")


def _fin_mod():
    from app.services.core_bridge import import_dashboard_module

    return import_dashboard_module("finance_from_1c")


def _turnover_from_reference(
    *,
    reference: pd.DataFrame,
    project_labels: list[str],
    date_from: date | None,
    date_to: date | None,
    ren: Any,
) -> dict[Any, tuple[float, float]]:
    """План/факт по месяцам из reference_dannye без зависимости от st.session_state."""
    session_state()["reference_1c_dannye"] = reference
    fin = _fin_mod()
    agg: dict[Any, list[float]] = {}
    for lab in project_labels:
        try:
            prep = fin._bdds_turnover_g_for_project(
                project_name=str(lab),
                period_start=date_from,
                period_end=date_to,
                reference_1c_dannye=reference,
                prefer_budget_scenario=True,
            )
        except Exception:  # noqa: BLE001
            prep = None
        if prep is None:
            continue
        g = prep[0]
        if g is None or getattr(g, "empty", True) or "_m" not in g.columns:
            continue
        for m in sorted(g["_m"].dropna().unique(), key=lambda x: str(x)):
            mk = ren._forecast_norm_month_period(m)
            if mk is pd.NaT or (isinstance(mk, float) and pd.isna(mk)):
                continue
            chunk = g.loc[g["_m"] == m]
            plan_v = float(pd.to_numeric(chunk.get("_plan"), errors="coerce").fillna(0).sum())
            fact_v = float(pd.to_numeric(chunk.get("_fact"), errors="coerce").fillna(0).sum())
            if plan_v + fact_v <= 50_000.0:
                continue
            if mk not in agg:
                agg[mk] = [0.0, 0.0]
            agg[mk][0] += plan_v
            agg[mk][1] += fact_v
    if agg:
        return {m: (v[0], v[1]) for m, v in agg.items()}

    try:
        syn = fin.try_synthetic_budget_from_1c_dannye(reference_1c_dannye=reference)
    except Exception:  # noqa: BLE001
        syn = None
    if syn is None or getattr(syn, "empty", True):
        return {}
    work = syn.copy()
    if project_labels:
        labels_mod = _labels_mod()
        col = "project name" if "project name" in work.columns else None
        if col:
            keys = {labels_mod.project_filter_norm_key(x) for x in project_labels}
            filtered = work[work[col].map(labels_mod.project_filter_norm_key).isin(keys)].copy()
            # MSP-имена и 1С «Проект» часто расходятся — для свода «Все» берём весь 1С.
            if not filtered.empty:
                work = filtered
    month_col = "plan_month" if "plan_month" in work.columns else None
    if month_col is None and "plan end" in work.columns:
        work["_m"] = pd.to_datetime(work["plan end"], errors="coerce").dt.to_period("M")
        month_col = "_m"
    if not month_col or work.empty:
        return {}
    out: dict[Any, tuple[float, float]] = {}
    for m, chunk in work.groupby(month_col, sort=True):
        mk = ren._forecast_norm_month_period(m)
        if mk is pd.NaT or (isinstance(mk, float) and pd.isna(mk)):
            continue
        pl = float(pd.to_numeric(chunk.get("budget plan"), errors="coerce").fillna(0).sum())
        fc = float(pd.to_numeric(chunk.get("budget fact"), errors="coerce").fillna(0).sum())
        if pl + fc <= 50_000.0:
            continue
        out[mk] = (pl, fc)
    return out


def _applied(
    *,
    project: str,
    date_from: date | None,
    date_to: date | None,
    group: str,
    view: str,
    dev_base: str,
    hide_deviation: bool,
    hide_zero: bool,
) -> dict[str, Any]:
    return {
        "project": project,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "group": group,
        "view": view,
        "dev_base": dev_base,
        "hide_deviation": hide_deviation,
        "hide_zero": hide_zero,
    }


def _empty_payload(*, applied: dict[str, Any], error: str | None = None) -> dict[str, Any]:
    group = str(applied.get("group") or "month")
    view = str(applied.get("view") or "monthly")
    dev_base = str(applied.get("dev_base") or "plan")
    hide_dev = bool(applied.get("hide_deviation"))
    period_label = GROUP_LABELS.get(group, "Месяц")
    dev_col = (
        "Откл. (факт − прогноз), млн"
        if dev_base == "fact"
        else "Откл. (план − прогноз), млн"
    )
    return {
        "meta": {
            "rows": 0,
            "source": "web_data.db",
            "data_mode": DATA_MODE,
            "parity": "main_dashboard_forecast_budget",
            "error": error,
            "version_id": None,
            "db": db_status(),
        },
        "filters": {
            "projects": [],
            "date_min": None,
            "date_max": None,
            "groups": [{"id": key, "label": label} for key, label in GROUP_LABELS.items()],
            "views": [{"id": key, "label": label} for key, label in VIEW_LABELS.items()],
            "dev_bases": [
                {"id": "plan", "label": "БДДС план"},
                {"id": "fact", "label": "БДДС факт"},
            ],
            "applied": applied,
        },
        "tremor": {"by_period": []},
        "period_rows": [],
        "status_rows": [],
        "totals": {"plan": 0.0, "fact": 0.0, "forecast": 0.0, "deviation": 0.0},
        "labels": {
            "period_column": period_label,
            "deviation_column": dev_col,
            "chart_title": "График Прогнозный бюджет",
            "period_table_title": "Таблица Прогнозный бюджет",
            "status_table_title": "Статус",
            "total_period": "",
            "edit_banner": "Редактирование лотов в таблице: в фильтре Проект выберите один проект (не «Все»).",
        },
        "hints": [],
    }


def _date_bounds(msp: pd.DataFrame) -> tuple[date | None, date | None, date | None, date | None]:
    utils = _utils()
    utils.ensure_date_columns(msp)
    end_all = pd.to_datetime(msp.get("plan end"), errors="coerce")
    if end_all is None or not end_all.notna().any():
        return None, None, None, None
    def_start = end_all.min()
    def_end = end_all.max()
    min_all = def_start
    max_all = def_end
    return (
        def_start.date() if pd.notna(def_start) else None,
        def_end.date() if pd.notna(def_end) else None,
        min_all.date() if pd.notna(min_all) else None,
        max_all.date() if pd.notna(max_all) else None,
    )


def _resolve_calendar(
    *,
    msp: pd.DataFrame,
    scope: pd.DataFrame,
    date_from: date | None,
    date_to: date | None,
) -> tuple[date | None, date | None, date | None, date | None]:
    _, _, min_all, max_all = _date_bounds(msp)
    end_sel = pd.to_datetime(scope.get("plan end"), errors="coerce")
    def_start = end_sel.min().date() if end_sel is not None and end_sel.notna().any() else min_all
    def_end = end_sel.max().date() if end_sel is not None and end_sel.notna().any() else max_all
    cal_start = _clamp(date_from, min_all, max_all) or def_start
    cal_end = _clamp(date_to, min_all, max_all) or def_end
    if cal_start and cal_end and cal_start > cal_end:
        cal_start, cal_end = cal_end, cal_start
    return cal_start, cal_end, min_all, max_all


def _can_edit_forecast(username: str | None) -> bool:
    name = (username or "").strip()
    if not name:
        return False
    try:
        auth = import_auth()
        user = auth.get_user_by_username(name)
        if user:
            return bool(auth.user_can_edit_forecast_budget(user.get("role")))
    except Exception:  # noqa: BLE001
        pass
    return name.casefold() in {"admin", "superadmin"}


def _project_norm(project: str, ren: Any) -> str:
    return str(ren._project_filter_norm_key(project))


def _src_sig(project_df: pd.DataFrame) -> tuple[int, float, float]:
    bp = float(pd.to_numeric(project_df.get("budget plan"), errors="coerce").fillna(0.0).sum())
    bf = float(pd.to_numeric(project_df.get("budget fact"), errors="coerce").fillna(0.0).sum())
    return (len(project_df), round(bp, 2), round(bf, 2))


def _prepare_single_project_df(
    filtered_scope: pd.DataFrame,
    selected_project: str,
) -> tuple[pd.DataFrame | None, str | None]:
    ren = _renderers()
    project_df, prep_err = ren._forecast_prepare_msp_slice(filtered_scope, selected_project)
    if project_df is None or prep_err:
        return None, prep_err or "Не удалось подготовить данные проекта."
    lot_attrs = dict(getattr(project_df, "attrs", {}) or {})
    project_df = ren._forecast_aggregate_by_lot(project_df)
    try:
        project_df.attrs.update(lot_attrs)
    except Exception:
        pass
    return project_df, None


def _build_forecast_edit_frame(pdf: pd.DataFrame, ren: Any) -> pd.DataFrame:
    cur = pdf.copy().reset_index(drop=True)
    ps = cur["plan start"].map(ren._forecast_parse_editor_date)
    pe = cur["plan end"].map(ren._forecast_parse_editor_date)
    bp = pd.to_numeric(cur["budget plan"], errors="coerce").fillna(0.0)
    if "budget fact" in cur.columns:
        bf = pd.to_numeric(cur["budget fact"], errors="coerce").fillna(0.0)
    else:
        bf = pd.Series(0.0, index=cur.index)
    plan_start_str = pd.to_datetime(ps, errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    plan_end_str = pd.to_datetime(pe, errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    n = len(cur)
    block = cur["section"].astype(str)
    if "BLOCK" in cur.columns:
        blk = cur["BLOCK"].astype(str).str.strip()
        block = block.mask(block.str.strip().eq(""), blk)
    lot_lbl = ren._forecast_lot_label_series(cur)
    return pd.DataFrame(
        {
            "Раздел": block,
            "Лот": lot_lbl.astype(str),
            "Условие распределения": ["Равномерно"] * n,
            "План. начало": plan_start_str,
            "План. окончание": plan_end_str,
            "БДДС план (утверждённый), млн руб.": (bp / 1e6).round(4),
            "БДДС факт, млн руб.": (bf / 1e6).round(4),
            "A, %": [34.0] * n,
            "B, %": [33.0] * n,
            "C, %": [33.0] * n,
        }
    )


def _rows_to_frame(rows: list[dict[str, Any]] | None) -> pd.DataFrame | None:
    if not rows:
        return None
    frame = pd.DataFrame(rows)
    for col in EDITOR_COLUMNS:
        if col not in frame.columns:
            frame[col] = "" if col not in {"A, %", "B, %", "C, %"} else 0.0
    return frame[list(EDITOR_COLUMNS)].copy()


def _frame_to_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rec in frame.to_dict("records"):
        row: dict[str, Any] = {}
        for col in EDITOR_COLUMNS:
            val = rec.get(col)
            if col in {"A, %", "B, %", "C, %"}:
                row[col] = float(pd.to_numeric(val, errors="coerce") or 0.0)
            elif col in {
                "БДДС план (утверждённый), млн руб.",
                "БДДС факт, млн руб.",
            }:
                row[col] = float(pd.to_numeric(val, errors="coerce") or 0.0)
            else:
                row[col] = "" if val is None else str(val)
        out.append(row)
    return out


def _validate_edit_rows(ed_rows: pd.DataFrame, ren: Any) -> list[str]:
    errors: list[str] = []
    if ed_rows is None or ed_rows.empty:
        return errors
    for i in range(len(ed_rows)):
        mode = str(ed_rows.iloc[i].get("Условие распределения", "") or "")
        if not ren._forecast_row_modes_use_abc(mode):
            continue
        a = ed_rows.iloc[i]["A, %"]
        b = ed_rows.iloc[i]["B, %"]
        c = ed_rows.iloc[i]["C, %"]
        if ren._bdds_abc_is_valid(a, b, c):
            continue
        lot = str(ed_rows.iloc[i].get("Лот", "") or "").strip() or f"строка {i + 1}"
        errors.append(
            f"{lot}: A+B+C={ren._bdds_abc_sum(a, b, c):.2f}% (нужно 100%)"
        )
    return errors


def _apply_edit_rows_to_project(
    project_df: pd.DataFrame,
    ed_rows: pd.DataFrame,
    ren: Any,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    if len(project_df) != len(ed_rows):
        raise ValueError("Несовпадение числа строк таблицы и данных проекта.")
    return ren._forecast_work_df_from_edit_rows(project_df, ed_rows.reset_index(drop=True))


def _compute_monthly(
    *,
    scope: pd.DataFrame,
    project_col: str,
    selected_project: str,
    cal_start: date | None,
    cal_end: date | None,
    project_df: pd.DataFrame | None = None,
    edit_rows: pd.DataFrame | None = None,
) -> tuple[
    pd.DataFrame,
    str | None,
    pd.DataFrame | None,
    pd.Series | None,
    pd.DataFrame | None,
    pd.DataFrame | None,
]:
    ren = _renderers()
    many = selected_project == "Все"
    calc_error: str | None = None
    updated_data: pd.DataFrame | None = None
    row_modes: pd.Series | None = None
    abc_src: pd.DataFrame | None = None
    if many:
        forecast_df, _approved_mln, combine_note = ren._forecast_combine_monthly_all_projects(
            scope, project_col
        )
        if forecast_df.empty:
            calc_error = combine_note or "Нет данных для расчёта."
        return forecast_df, calc_error, None, None, None, None

    if project_df is None:
        project_df, prep_err = _prepare_single_project_df(scope, selected_project)
        if project_df is None or prep_err:
            return pd.DataFrame(), prep_err, None, None, None, None

    work_df = project_df
    if edit_rows is not None and not edit_rows.empty:
        try:
            updated_data, row_modes, abc_src = _apply_edit_rows_to_project(
                project_df, edit_rows, ren
            )
            work_df = updated_data
        except ValueError as exc:
            return pd.DataFrame(), str(exc), project_df, None, None, None

    forecast_df, calc_error = ren.calculate_forecast_budget(
        scope,
        edited_data=work_df,
        distribution_mode="uniform",
        abc_source=abc_src,
        row_modes=row_modes,
    )
    return forecast_df, calc_error, project_df, updated_data, row_modes, abc_src


def _build_lot_recalc_payload(
    *,
    updated_data: pd.DataFrame,
    abc_src: pd.DataFrame | None,
    row_modes: pd.Series | None,
    period_label: str,
    only_month: Any,
    ren: Any,
    utils_mod: Any,
) -> dict[str, Any]:
    period_all_lbl = "Весь срок (итог по лоту)"
    month_opts = ren._forecast_lot_oldnew_month_options(
        updated_data, abc_source=abc_src, row_modes=row_modes
    )
    period_choices = [period_all_lbl] + [utils_mod.format_period_ru(m) for m in month_opts]
    # «Весь срок» + % A/B/C → Δ=0 (меняется только раскладка по месяцам).
    # Месяц пользователь выбирает сам — как после применения A/B/C в Streamlit,
    # если selectbox уже был на «весь срок».
    sel_period_lbl = period_label if period_label in period_choices else period_all_lbl
    only = None
    if sel_period_lbl != period_all_lbl:
        for m in month_opts:
            if utils_mod.format_period_ru(m) == sel_period_lbl:
                only = m
                break
    uniform_modes = pd.Series(
        ["Равномерно"] * len(updated_data),
        index=updated_data.index,
        dtype=object,
    )
    base_tot = ren._forecast_per_lot_distribution_totals(
        updated_data,
        abc_source=abc_src,
        row_modes=uniform_modes,
        only_month=only,
    )
    cur_tot = ren._forecast_per_lot_distribution_totals(
        updated_data,
        abc_source=abc_src,
        row_modes=row_modes,
        only_month=only,
    )
    if cur_tot.empty:
        return {
            "period_choices": period_choices,
            "selected_period": sel_period_lbl,
            "rows": [],
            "caption": "",
        }
    pcol = "БДДС план (утверждённый), млн руб."
    fcol = "БДДС факт, млн руб."
    gcol = "БДДС прогноз (итого), млн руб."
    if only is not None:
        fc_col_old = f"Прогноз равномерно ({sel_period_lbl}), млн руб."
        fc_col_new = f"Прогноз по условию ({sel_period_lbl}), млн руб."
        delta_col = f"Δ прогноз ({sel_period_lbl}), млн руб."
        caption = (
            f"Сравнение на текущих датах/суммах: равномерно vs условие строки "
            f"за {sel_period_lbl}. % A/B/C: A — месяц начала, C — окончания, "
            f"B — поровну по промежуточным."
        )
    else:
        fc_col_old = "Прогноз равномерно (весь срок), млн руб."
        fc_col_new = "Прогноз по условию (весь срок), млн руб."
        delta_col = "Δ прогноз (весь срок), млн руб."
        caption = (
            "Сравнение на текущих датах/суммах редактора: «равномерно» vs ваше условие (% A/B/C). "
            "За весь срок сумма одинакова (Δ = 0) — меняется только раскладка по месяцам. "
            "Выберите месяц в «Прогноз за период», чтобы увидеть Δ."
        )
    base_by_lot = base_tot.set_index("Лот") if not base_tot.empty else pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for _, cr in cur_tot.iterrows():
        lot = str(cr.get("Лот", ""))
        bp_new = float(cr.get(pcol, 0.0) or 0.0)
        bf_new = float(cr.get(fcol, 0.0) or 0.0)
        fc_new = float(cr.get(gcol, 0.0) or 0.0)
        if not base_by_lot.empty and lot in base_by_lot.index:
            br = base_by_lot.loc[lot]
            if isinstance(br, pd.DataFrame):
                br = br.iloc[0]
            fc_old = float(br.get(gcol, 0.0) or 0.0)
        else:
            fc_old = fc_new
        rows.append(
            {
                "lot": lot,
                "plan_mln": round(bp_new, 1),
                "fact_mln": round(bf_new, 1),
                "forecast_uniform_mln": round(fc_old, 1),
                "forecast_cond_mln": round(fc_new, 1),
                "delta_mln": round(fc_new - fc_old, 1),
            }
        )
    rows.sort(key=lambda r: abs(float(r.get("delta_mln") or 0)), reverse=True)
    return {
        "period_choices": period_choices,
        "selected_period": sel_period_lbl,
        "forecast_uniform_column": fc_col_old,
        "forecast_cond_column": fc_col_new,
        "delta_column": delta_col,
        "caption": caption,
        "rows": rows,
    }


def _build_period_rows(
    mf: pd.DataFrame,
    *,
    period_label: str,
    dev_base: str,
    hide_deviation: bool,
    utils_mod: Any,
) -> tuple[list[dict[str, Any]], dict[str, float], str]:
    dev_col = (
        "Откл. (факт − прогноз), млн"
        if dev_base == "fact"
        else "Откл. (план − прогноз), млн"
    )
    rows: list[dict[str, Any]] = []
    for _, row in mf.iterrows():
        plan = float(row.get("bdds_plan_msp") or 0)
        fact = float(row.get("bdds_fact") or 0)
        forecast = float(row.get("bdds_forecast") or 0)
        dev = float(row.get("_dev") or 0)
        rows.append(
            {
                "period": str(row.get("Период") or utils_mod.format_period_ru(row.get("month"))),
                "plan": round(plan, 2),
                "fact": round(fact, 2),
                "forecast": round(forecast, 2),
                "deviation": round(dev, 2),
            }
        )
    tot_plan = float(pd.to_numeric(mf["bdds_plan_msp"], errors="coerce").fillna(0).sum())
    tot_fact = float(pd.to_numeric(mf["bdds_fact"], errors="coerce").fillna(0).sum())
    tot_forecast = float(pd.to_numeric(mf["bdds_forecast"], errors="coerce").fillna(0).sum())
    if dev_base == "fact":
        tot_dev = tot_fact - tot_forecast
    else:
        tot_dev = tot_plan - tot_forecast
    totals = {
        "plan": round(tot_plan, 2),
        "fact": round(tot_fact, 2),
        "forecast": round(tot_forecast, 2),
        "deviation": round(tot_dev, 2),
    }
    total_row: dict[str, Any] = {
        "period": "ИТОГО",
        "plan": totals["plan"],
        "fact": totals["fact"],
        "forecast": totals["forecast"],
        "deviation": totals["deviation"],
        "kind": "total",
    }
    rows.append(total_row)
    return rows, totals, dev_col


def build_bdds_plan_fact_payload(
    *,
    project: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    group: str = "month",
    view: str = "monthly",
    dev_base: str = "plan",
    hide_deviation: bool = False,
    hide_zero: bool | None = None,
    edit_rows: list[dict[str, Any]] | None = None,
    username: str | None = None,
    lot_recalc_period: str | None = None,
    skip_cache: bool = False,
) -> dict[str, Any]:
    group = group if group in GROUPS else "month"
    view = view if view in VIEW_LABELS else "monthly"
    dev_base = dev_base if dev_base in {"plan", "fact"} else "plan"
    selected_project = str(project or "Все").strip() or "Все"
    hide_zero_effective = True if hide_zero is None and group == "month" else bool(hide_zero)
    period_type_en = GROUP_TO_EN[group]
    period_label = PERIOD_LABEL_EN[period_type_en]
    dev_base_ru = "БДДС факт" if dev_base == "fact" else "БДДС план"

    applied = _applied(
        project=selected_project,
        date_from=date_from,
        date_to=date_to,
        group=group,
        view=view,
        dev_base=dev_base,
        hide_deviation=hide_deviation,
        hide_zero=hide_zero_effective,
    )

    cache_key = "|".join(
        [
            CACHE_VERSION,
            f"project={selected_project}",
            f"from={date_from or ''}",
            f"to={date_to or ''}",
            f"group={group}",
            f"view={view}",
            f"dev={dev_base}",
            f"hide_dev={int(hide_deviation)}",
            f"hide_zero={int(hide_zero_effective)}",
            f"db={WEB_DB_PATH}",
            f"mtime={db_status().get('mtime')}",
            f"edits={hashlib.sha1(json.dumps(edit_rows or [], sort_keys=True, default=str).encode()).hexdigest()[:12] if edit_rows else ''}",
            f"user={username or ''}",
        ]
    )
    if not skip_cache and edit_rows is None:
        cached = cache_get(CACHE_ID, cache_key, max_age_sec=CACHE_MAX_AGE_SEC)
        if cached is not None:
            return cached

    try:
        vid = active_version_id()
    except Exception as exc:  # noqa: BLE001
        return _empty_payload(applied=applied, error=f"web_data.db недоступна: {exc}")
    if not vid:
        return _empty_payload(applied=applied, error="В web_data.db нет активной версии.")

    labels_mod = _labels_mod()
    utils_mod = _utils()
    ren = _renderers()

    try:
        reference = load_version_df(vid, "reference_dannye")
    except Exception as exc:  # noqa: BLE001
        return _empty_payload(applied=applied, error=f"Не читается reference_dannye: {exc}")
    if reference is None or getattr(reference, "empty", True):
        return _empty_payload(
            applied=applied,
            error=f"В версии {vid} нет оборотов 1С (reference_dannye).",
        )
    session_state()["reference_1c_dannye"] = reference

    msp = load_msp_frame(vid)
    if msp is None or getattr(msp, "empty", True):
        return _empty_payload(applied=applied, error=f"В версии {vid} нет MSP (project).")

    df_work = msp.copy()
    project_col = _project_col(df_work)
    if not project_col:
        return _empty_payload(
            applied=applied,
            error="Колонка проекта не найдена (project name / Проект).",
        )
    df_work = labels_mod.apply_unified_project_column(df_work, project_col)
    project_options = ["Все"] + main_project_labels(df_work[project_col])
    selected_labels = resolve_selected_projects(selected_project, project_options)
    scope = df_work.copy()
    if selected_labels:
        scope = labels_mod.filter_dataframe_by_project_labels(
            scope, selected_labels, col=project_col
        )

    cal_start, cal_end, min_all, max_all = _resolve_calendar(
        msp=df_work, scope=scope, date_from=date_from, date_to=date_to
    )
    applied["date_from"] = cal_start.isoformat() if cal_start else None
    applied["date_to"] = cal_end.isoformat() if cal_end else None

    if scope.empty:
        empty = _empty_payload(applied=applied, error="Нет строк для выбранных фильтров.")
        empty["filters"]["projects"] = project_options
        empty["filters"]["date_min"] = min_all.isoformat() if min_all else None
        empty["filters"]["date_max"] = max_all.isoformat() if max_all else None
        empty["filters"]["applied"] = applied
        return empty

    filtered_scope = ren._forecast_filter_rows_by_plan_end_range(
        scope, date_from=cal_start, date_to=cal_end
    )
    if filtered_scope is None or filtered_scope.empty:
        empty = _empty_payload(applied=applied, error="Нет строк для выбранных фильтров.")
        empty["filters"]["projects"] = project_options
        empty["filters"]["date_min"] = min_all.isoformat() if min_all else None
        empty["filters"]["date_max"] = max_all.isoformat() if max_all else None
        empty["filters"]["applied"] = applied
        return empty

    many_projects = len(selected_labels) != 1
    single_project = selected_labels[0] if len(selected_labels) == 1 else "Все"
    project_df: pd.DataFrame | None = None
    edit_frame: pd.DataFrame | None = None
    edit_errors: list[str] = []
    if not many_projects:
        project_df, prep_err = _prepare_single_project_df(filtered_scope, single_project)
        if project_df is None or prep_err:
            empty = _empty_payload(applied=applied, error=prep_err)
            empty["filters"]["projects"] = project_options
            empty["meta"]["version_id"] = vid
            return empty
        edit_frame = _build_forecast_edit_frame(project_df, ren)
        proj_norm = _project_norm(single_project, ren)
        effective_rows = edit_rows
        if effective_rows is None and username:
            saved = edit_store.get_saved_rows(username, proj_norm)
            if saved and len(saved) == len(project_df):
                effective_rows = saved
        edit_rows_df = _rows_to_frame(effective_rows)
        if edit_rows_df is not None:
            edit_errors = _validate_edit_rows(edit_rows_df, ren)
            if edit_errors:
                edit_rows_df = None
    else:
        edit_rows_df = None

    forecast_df, calc_error, project_df, updated_data, row_modes, abc_src = _compute_monthly(
        scope=filtered_scope,
        project_col=project_col,
        selected_project=single_project if not many_projects else "Все",
        cal_start=cal_start,
        cal_end=cal_end,
        project_df=project_df,
        edit_rows=edit_rows_df,
    )
    if forecast_df.empty:
        empty = _empty_payload(applied=applied, error=calc_error or "Нет данных для расчёта.")
        empty["filters"]["projects"] = project_options
        empty["filters"]["date_min"] = min_all.isoformat() if min_all else None
        empty["filters"]["date_max"] = max_all.isoformat() if max_all else None
        empty["filters"]["applied"] = applied
        empty["meta"]["version_id"] = vid
        return empty

    if many_projects:
        turn_labels = sorted(
            {
                ren._clean_display_str(x)
                for x in filtered_scope[project_col].dropna().unique()
                if str(x).strip()
            },
            key=lambda s: str(s).casefold(),
        )
    else:
        turn_labels = [single_project]

    turnover = ren._forecast_turnover_monthly_plan_fact_scope(
        turn_labels, date_from=cal_start, date_to=cal_end
    )
    if not turnover:
        turnover = _turnover_from_reference(
            reference=reference,
            project_labels=turn_labels,
            date_from=cal_start,
            date_to=cal_end,
            ren=ren,
        )
    mf_fc = ren._forecast_overlay_turnover_on_monthly(forecast_df.sort_values("month").copy(), turnover)
    # Если overlay не сработал (старый код/кэш) — принудительно залить 1С в пустой MSP-ряд.
    pl_sum = float(pd.to_numeric(mf_fc.get("bdds_plan_msp"), errors="coerce").fillna(0).abs().sum())
    fc_sum = float(pd.to_numeric(mf_fc.get("bdds_fact"), errors="coerce").fillna(0).abs().sum())
    if turnover and (pl_sum + fc_sum) <= 50_000.0:
        mf_fc = ren._forecast_overlay_turnover_on_monthly(
            forecast_df.sort_values("month").copy(), turnover
        )
        # Прямая подстановка, если функция overlay ещё без 1С-fill (prod lag).
        pl_sum = float(pd.to_numeric(mf_fc.get("bdds_plan_msp"), errors="coerce").fillna(0).abs().sum())
        fc_sum = float(pd.to_numeric(mf_fc.get("bdds_fact"), errors="coerce").fillna(0).abs().sum())
        if (pl_sum + fc_sum) <= 50_000.0:
            rows = []
            for mk, (pl, fc) in turnover.items():
                rows.append(
                    {
                        "month": mk,
                        "bdds_plan_msp": float(pl),
                        "bdds_fact": float(fc),
                        "bdds_forecast": float(pl),
                    }
                )
            if rows:
                mf_fc = pd.DataFrame(rows).sort_values("month").reset_index(drop=True)
    mf_tot_snapshot = mf_fc.copy()

    if cal_start is not None and cal_end is not None:
        keep = mf_fc["month"].map(
            lambda m: ren._forecast_month_calendar_intersects(
                m, date_from=cal_start, date_to=cal_end
            )
        )
        mf_fc = mf_fc.loc[keep].reset_index(drop=True)
        mf_tot_snapshot = mf_tot_snapshot.loc[keep].reset_index(drop=True)

    mf_fc = ren._forecast_resample_monthly_dataframe(mf_fc, period_type_en)
    mf_tot_snapshot = ren._forecast_resample_monthly_dataframe(mf_tot_snapshot, period_type_en)
    if mf_fc is None or mf_fc.empty:
        empty = _empty_payload(applied=applied, error="Нет данных после агрегирования по периоду.")
        empty["filters"]["projects"] = project_options
        empty["meta"]["version_id"] = vid
        return empty

    if view == "cumulative":
        mf_fc = ren._forecast_apply_view_cumulative(mf_fc)

    if dev_base == "fact":
        mf_fc["_dev"] = mf_fc["bdds_fact"] - mf_fc["bdds_forecast"]
    else:
        mf_fc["_dev"] = mf_fc["bdds_plan_msp"] - mf_fc["bdds_forecast"]

    mf_fc["Период"] = mf_fc["month"].apply(utils_mod.format_period_ru)

    chart_df = mf_fc.copy()
    if group == "month" and hide_zero_effective:
        chart_df = ren._forecast_filter_chart_months(chart_df, hide_zero_months=True)

    period_rows, totals, dev_col = _build_period_rows(
        mf_fc,
        period_label=period_label,
        dev_base=dev_base,
        hide_deviation=hide_deviation,
        utils_mod=utils_mod,
    )

    # Последний рубеж: если свод всё ещё нулевой — собрать периоды прямо из 1С.
    if (
        abs(float(totals.get("plan") or 0))
        + abs(float(totals.get("fact") or 0))
        + abs(float(totals.get("forecast") or 0))
        <= 50_000.0
    ):
        if not turnover:
            turnover = _turnover_from_reference(
                reference=reference,
                project_labels=turn_labels if not many_projects else [],
                date_from=cal_start,
                date_to=cal_end,
                ren=ren,
            )
        if turnover:
            rows = []
            for mk, (pl, fc) in sorted(turnover.items(), key=lambda x: str(x[0])):
                rows.append(
                    {
                        "month": mk,
                        "bdds_plan_msp": float(pl),
                        "bdds_fact": float(fc),
                        "bdds_forecast": float(pl),
                        "_dev": float(pl) - float(pl),
                        "Период": utils_mod.format_period_ru(mk),
                    }
                )
            mf_fc = pd.DataFrame(rows)
            if not mf_fc.empty:
                if view == "cumulative":
                    mf_fc = ren._forecast_apply_view_cumulative(mf_fc)
                    if dev_base == "fact":
                        mf_fc["_dev"] = mf_fc["bdds_fact"] - mf_fc["bdds_forecast"]
                    else:
                        mf_fc["_dev"] = mf_fc["bdds_plan_msp"] - mf_fc["bdds_forecast"]
                    mf_fc["Период"] = mf_fc["month"].apply(utils_mod.format_period_ru)
                chart_df = mf_fc.copy()
                if group == "month" and hide_zero_effective:
                    chart_df = ren._forecast_filter_chart_months(chart_df, hide_zero_months=True)
                period_rows, totals, dev_col = _build_period_rows(
                    mf_fc,
                    period_label=period_label,
                    dev_base=dev_base,
                    hide_deviation=hide_deviation,
                    utils_mod=utils_mod,
                )
                calc_error = None
                # hint added below when hints list is built

    chart_points = []
    for _, row in chart_df.iterrows():
        plan = float(row.get("bdds_plan_msp") or 0)
        fact = float(row.get("bdds_fact") or 0)
        forecast = float(row.get("bdds_forecast") or 0)
        dev = float(row.get("_dev") or 0)
        chart_points.append(
            {
                "period": str(row.get("Период") or ""),
                "plan": _mln(plan),
                "fact": _mln(fact),
                "forecast": _mln(forecast),
                "deviation": _mln(dev),
            }
        )

    status_df = ren._forecast_financier_status_dataset(
        filtered_scope=filtered_scope,
        project_col=project_col,
        all_projects=many_projects,
        selected_project_label=None if many_projects else single_project,
        period_type_en=period_type_en,
        date_from=cal_start,
        date_to=cal_end,
        single_updated_data=updated_data if not many_projects else None,
        abc_source=abc_src if not many_projects else None,
        row_modes=row_modes if not many_projects else None,
        monthly_snapshot=mf_tot_snapshot if not many_projects else None,
        dev_base=dev_base_ru,
    )
    status_rows = []
    if status_df is not None and not status_df.empty:
        for rec in status_df.to_dict("records"):
            status_rows.append(
                {
                    "month": str(rec.get("Месяц") or ""),
                    "project": str(rec.get("Проект") or ""),
                    "plan_mln": float(rec.get("БДДС (план), млн") or 0),
                    "fact_mln": float(rec.get("БДДС (факт), млн") or 0),
                    "forecast_mln": float(rec.get("БДДС (прогноз), млн") or 0),
                    "deviation_mln": float(rec.get("Отклонение по сумме, млн") or 0),
                    "status": str(rec.get("Статус") or ""),
                }
            )

    fc_name, fc_dates = utils_mod.report_title_parts(
        "Прогнозный бюджет",
        period_label,
        cumulative=(view == "cumulative"),
        date_start=cal_start,
        date_end=cal_end,
    )
    chart_title = utils_mod.format_chart_title(fc_name, fc_dates)
    table_suffix = utils_mod.format_date_range_title_suffix(cal_start, cal_end) or ""
    period_table_title = (
        f"Таблица {fc_name} ({table_suffix})" if table_suffix else f"Таблица {fc_name}"
    )
    total_period = (
        f"{cal_start.strftime('%d.%m.%Y')} — {cal_end.strftime('%d.%m.%Y')}"
        if cal_start and cal_end
        else ""
    )

    lot_recalc: dict[str, Any] | None = None
    if not many_projects and updated_data is not None and not getattr(updated_data, "empty", True):
        lot_recalc = _build_lot_recalc_payload(
            updated_data=updated_data,
            abc_src=abc_src,
            row_modes=row_modes,
            period_label=lot_recalc_period or "",
            only_month=None,
            ren=ren,
            utils_mod=utils_mod,
        )

    hints: list[str] = []
    if calc_error:
        hints.append(str(calc_error))
    hints.extend(edit_errors)
    if abs(float(totals.get("plan") or 0)) + abs(float(totals.get("fact") or 0)) > 50_000.0:
        if any(
            abs(float(r.get("plan") or 0)) + abs(float(r.get("fact") or 0)) > 50_000.0
            for r in period_rows
            if r.get("kind") != "total"
        ):
            # already filled from 1C path
            pass
    if turnover and abs(float(totals.get("plan") or 0)) > 50_000.0:
        hints.append("Суммы подставлены из оборотов 1С (MSP budget пуст).")

    payload = {
        "meta": {
            "rows": int(len(mf_fc)),
            "source": "web_data.db",
            "data_mode": DATA_MODE,
            "parity": "main_dashboard_forecast_budget",
            "error": calc_error,
            "version_id": vid,
            "rows_1c": int(len(reference)),
            "turnover_months": int(len(turnover or {})),
            "cache_version": CACHE_VERSION,
            "db": db_status(),
            "edit_errors": edit_errors,
        },
        "filters": {
            "projects": project_options,
            "date_min": min_all.isoformat() if min_all else None,
            "date_max": max_all.isoformat() if max_all else None,
            "groups": [{"id": key, "label": label} for key, label in GROUP_LABELS.items()],
            "views": [{"id": key, "label": label} for key, label in VIEW_LABELS.items()],
            "dev_bases": [
                {"id": "plan", "label": "БДДС план"},
                {"id": "fact", "label": "БДДС факт"},
            ],
            "applied": applied,
        },
        "tremor": {"by_period": chart_points},
        "period_rows": period_rows,
        "status_rows": status_rows,
        "totals": totals,
        "labels": {
            "period_column": period_label,
            "deviation_column": dev_col,
            "chart_title": chart_title,
            "period_table_title": period_table_title,
            "status_table_title": "Статус",
            "total_period": total_period,
            "edit_banner": (
                "Редактирование лотов в таблице: в фильтре Проект выберите один проект (не «Все»)."
            ),
        },
        "hints": hints,
        "lot_recalc": lot_recalc,
    }
    if not skip_cache and edit_rows is None:
        cache_set(CACHE_ID, cache_key, payload)
    return payload


def build_editor_payload(
    *,
    project: str,
    username: str | None = None,
    show_struct: bool = False,
) -> dict[str, Any]:
    selected_project = str(project or "").strip()
    if not selected_project or selected_project == "Все":
        return {"error": "Выберите один проект (не «Все»)."}

    ren = _renderers()
    can_edit = _can_edit_forecast(username)
    help_md = getattr(ren, "_FORECAST_EDITOR_HELP_MD", "")

    try:
        vid = active_version_id()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"web_data.db недоступна: {exc}"}
    if not vid:
        return {"error": "В web_data.db нет активной версии."}

    labels_mod = _labels_mod()
    try:
        reference = load_version_df(vid, "reference_dannye")
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Не читается reference_dannye: {exc}"}
    if reference is not None and not getattr(reference, "empty", True):
        session_state()["reference_1c_dannye"] = reference

    msp = load_msp_frame(vid)
    if msp is None or getattr(msp, "empty", True):
        return {"error": f"В версии {vid} нет MSP (project)."}

    df_work = msp.copy()
    project_col = _project_col(df_work)
    if not project_col:
        return {"error": "Колонка проекта не найдена."}
    df_work = labels_mod.apply_unified_project_column(df_work, project_col)
    scope = labels_mod.filter_dataframe_by_project_labels(
        df_work, [selected_project], col=project_col
    )
    if scope.empty:
        return {"error": "Нет строк для выбранного проекта."}

    cal_start, cal_end, _, _ = _resolve_calendar(
        msp=df_work, scope=scope, date_from=None, date_to=None
    )
    filtered_scope = ren._forecast_filter_rows_by_plan_end_range(
        scope, date_from=cal_start, date_to=cal_end
    )
    project_df, prep_err = _prepare_single_project_df(filtered_scope, selected_project)
    if project_df is None or prep_err:
        return {"error": prep_err or "Не удалось подготовить данные проекта."}

    baseline = _build_forecast_edit_frame(project_df, ren)
    proj_norm = _project_norm(selected_project, ren)
    sig = _src_sig(project_df)
    rows = _frame_to_rows(baseline)
    applied = False
    if username:
        saved = edit_store.get_saved_rows(username, proj_norm)
        if saved and len(saved) == len(project_df):
            rows = saved
            applied = True

    vis_mask = pd.Series(True, index=project_df.index)
    if not show_struct:
        vis_mask = ren._forecast_editor_visible_mask(project_df)
    visible_indices = list(vis_mask[vis_mask].index.astype(int))
    bp_vis = pd.to_numeric(
        pd.Series([r.get("БДДС план (утверждённый), млн руб.", 0) for r in rows]),
        errors="coerce",
    ).fillna(0.0)
    bf_vis = pd.to_numeric(
        pd.Series([r.get("БДДС факт, млн руб.", 0) for r in rows]),
        errors="coerce",
    ).fillna(0.0)
    score = (bp_vis + bf_vis).to_numpy()
    visible_indices = sorted(
        visible_indices,
        key=lambda i: (-float(score[i] if i < len(score) else 0), str(rows[i].get("Лот", ""))),
    )

    return {
        "project": selected_project,
        "project_norm": proj_norm,
        "can_edit": can_edit,
        "help_md": help_md,
        "dist_options": DIST_OPTIONS,
        "columns": list(EDITOR_COLUMNS),
        "rows": rows,
        "baseline_rows": _frame_to_rows(baseline),
        "src_sig": list(sig),
        "applied": applied,
        "visible_indices": visible_indices,
        "total_rows": len(rows),
        "visible_rows": len(visible_indices),
        "hidden_struct_rows": len(rows) - len(visible_indices),
    }


def preview_bdds_plan_fact(
    *,
    project: str,
    edit_rows: list[dict[str, Any]],
    date_from: date | None = None,
    date_to: date | None = None,
    group: str = "month",
    view: str = "monthly",
    dev_base: str = "plan",
    hide_deviation: bool = False,
    hide_zero: bool | None = None,
    lot_recalc_period: str | None = None,
    username: str | None = None,
) -> dict[str, Any]:
    ren = _renderers()
    ed_rows = _rows_to_frame(edit_rows)
    errors: list[str] = []
    if ed_rows is not None:
        errors = _validate_edit_rows(ed_rows, ren)
    payload = build_bdds_plan_fact_payload(
        project=project,
        date_from=date_from,
        date_to=date_to,
        group=group,
        view=view,
        dev_base=dev_base,
        hide_deviation=hide_deviation,
        hide_zero=hide_zero,
        edit_rows=edit_rows if not errors else None,
        username=username,
        lot_recalc_period=lot_recalc_period,
        skip_cache=True,
    )
    payload["validation_errors"] = errors
    if errors:
        payload["meta"]["edit_errors"] = errors
        payload["hints"] = list(payload.get("hints") or []) + errors
    return payload


def apply_bdds_plan_fact_edits(
    *,
    project: str,
    edit_rows: list[dict[str, Any]],
    username: str,
    date_from: date | None = None,
    date_to: date | None = None,
    group: str = "month",
    view: str = "monthly",
    dev_base: str = "plan",
    hide_deviation: bool = False,
    hide_zero: bool | None = None,
    lot_recalc_period: str | None = None,
) -> dict[str, Any]:
    if not _can_edit_forecast(username):
        return {"error": "Редактирование недоступно для вашей роли.", "ok": False}

    ren = _renderers()
    ed_rows = _rows_to_frame(edit_rows)
    if ed_rows is None:
        return {"error": "Пустая таблица правок.", "ok": False}
    errors = _validate_edit_rows(ed_rows, ren)
    if errors:
        return {"error": "; ".join(errors[:5]), "validation_errors": errors, "ok": False}

    proj_norm = _project_norm(project, ren)
    sig: tuple[int, float, float] | None = None
    try:
        vid = active_version_id()
        labels_mod = _labels_mod()
        msp = load_msp_frame(vid) if vid else None
        if msp is not None and not msp.empty:
            project_col = _project_col(msp)
            if project_col:
                scope = labels_mod.filter_dataframe_by_project_labels(
                    labels_mod.apply_unified_project_column(msp.copy(), project_col),
                    [project],
                    col=project_col,
                )
                cal_start, cal_end, _, _ = _resolve_calendar(
                    msp=labels_mod.apply_unified_project_column(msp.copy(), project_col),
                    scope=scope,
                    date_from=None,
                    date_to=None,
                )
                filtered = ren._forecast_filter_rows_by_plan_end_range(
                    scope, date_from=cal_start, date_to=cal_end
                )
                pdf, _ = _prepare_single_project_df(filtered, project)
                if pdf is not None:
                    sig = _src_sig(pdf)
    except Exception:  # noqa: BLE001
        sig = None

    edit_store.save_rows(
        username,
        proj_norm,
        project_label=project,
        rows=edit_rows,
        src_sig=sig,
    )
    payload = build_bdds_plan_fact_payload(
        project=project,
        date_from=date_from,
        date_to=date_to,
        group=group,
        view=view,
        dev_base=dev_base,
        hide_deviation=hide_deviation,
        hide_zero=hide_zero,
        edit_rows=edit_rows,
        username=username,
        lot_recalc_period=lot_recalc_period,
        skip_cache=True,
    )
    payload["ok"] = True
    payload["applied"] = True
    return payload
