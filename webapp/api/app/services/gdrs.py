"""ГДРС (люди / техника) — паритет с [main] dashboard_gdrs, данные из web_data.db."""
from __future__ import annotations

import math
from functools import lru_cache
from typing import Any, Literal

import pandas as pd

from app.config import DATA_MODE, WEB_DB_PATH
from app.services.core_bridge import (
    active_version_id,
    import_dashboard_module as _import_dashboard_module,
    prepare_web_db,
)

ResourceKind = Literal["people", "equipment"]

_VID = {"people": "Рабочие", "equipment": "Техника"}
_UNIT = {"people": "люди", "equipment": "техника"}
_UNIT_GEN = {"people": "людей", "equipment": "техники"}
_DYN_OPTS = ["День", "Неделя", "Месяц"]


def _gdrs():
    return _import_dashboard_module("gdrs_resursi")


def _labels():
    return _import_dashboard_module("project_labels")


def _num(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    if math.isnan(x) or math.isinf(x):
        return default
    return x


def _pct_out(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    return round(_num(v), 1)


def _split_csv(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [p.strip() for p in str(raw).split(",") if p.strip()]


def _db_mtime() -> float:
    try:
        return float(WEB_DB_PATH.resolve().stat().st_mtime)
    except OSError:
        return 0.0


@lru_cache(maxsize=4)
def _cached_enriched_fact(version_id: int, db_mtime: float, dog_sig: tuple[str, ...]) -> pd.DataFrame:
    """Обогащённый факт из БД (без повторного fuzzy на каждый запрос)."""
    g = _gdrs()
    return g._gdrs_cached_enriched_fact(int(version_id), float(db_mtime), dog_sig)


@lru_cache(maxsize=4)
def _cached_term_index(version_id: int, db_mtime: float, dog_sig: tuple[str, ...]):
    g = _gdrs()
    return g._gdrs_cached_termination_index(int(version_id), float(db_mtime), dog_sig)


@lru_cache(maxsize=4)
def _cached_dannye(version_id: int, db_mtime: float):
    g = _gdrs()
    try:
        return g._gdrs_cached_dannye_maps(int(version_id), float(db_mtime))
    except Exception:
        return {}, {}, {}, {}, {}


@lru_cache(maxsize=32)
def _cached_plan(
    version_id: int,
    db_mtime: float,
    snapshot_iso: str,
    dog_sig: tuple[str, ...],
) -> pd.DataFrame:
    g = _gdrs()
    return g._gdrs_cached_plan_aggregate(
        int(version_id), float(db_mtime), snapshot_iso, dog_sig
    )


def clear_gdrs_caches() -> None:
    _cached_enriched_fact.cache_clear()
    _cached_term_index.cache_clear()
    _cached_dannye.cache_clear()
    _cached_plan.cache_clear()


def _empty_payload(
    *,
    resource_kind: ResourceKind,
    warning: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    g = _gdrs()
    unit = _UNIT.get(resource_kind, "люди")
    return {
        "meta": {
            "data_mode": DATA_MODE,
            "resource_kind": resource_kind,
            "unit": unit,
            "unit_gen": _UNIT_GEN.get(resource_kind, "людей"),
            "period_label": "",
            "rows": 0,
            "resursi_files": 0,
            "version_id": None,
            "source": "web_data.db",
            "parity": "main_dashboard_gdrs",
            "warning": warning or error,
            "error": error,
            "show_week_columns": False,
            "week_labels": [],
        },
        "filters": {
            "projects": [],
            "contractors": [],
            "months": [],
            "default_months": [],
            "agg_options": g.gdrs_agg_select_options(),
            "dyn_agg_options": list(_DYN_OPTS),
            "selected": {
                "projects": [],
                "contractors": [],
                "months": [],
                "plan_agg": "Среднее за месяц",
                "skud_agg": "Среднее за месяц",
                "dyn_agg": "День",
                "only_with_plan": False,
            },
        },
        "kpis": {"plan": 0, "fact": 0, "deviation": 0, "delta_pct": None},
        "tremor": {
            "by_project": [],
            "by_contractor": [],
            "pie": [],
            "dynamics": [],
        },
        "project_rows": [],
        "contractor_rows": [],
        "pie_rows": [],
        "matrix_rows": [],
        "matrix_meta": {
            "show_week_columns": False,
            "week_labels": [],
            "week_plan_keys": [],
            "week_skud_keys": [],
        },
        "dynamics_rows": [],
    }


def _build_contractors_chart_df(main_t: pd.DataFrame) -> pd.DataFrame:
    g = _gdrs()
    cols = ["project_name", "contractor_name", "plan", "skud"]
    raw = main_t.loc[
        main_t["row_kind"] == "row",
        [c for c in cols if c in main_t.columns],
    ].copy()
    if raw.empty or "contractor_name" not in raw.columns:
        return pd.DataFrame(columns=["Контрагент", "План", "Факт", "Отклонение"])
    if "project_name" in raw.columns:
        raw = raw.drop_duplicates(subset=["project_name", "contractor_name"], keep="first")
    raw["contractor_name"] = raw["contractor_name"].astype(str).str.strip()
    raw = raw[raw["contractor_name"] != ""]
    if raw.empty:
        return pd.DataFrame(columns=["Контрагент", "План", "Факт", "Отклонение"])
    raw["plan"] = pd.to_numeric(raw["plan"], errors="coerce").fillna(0.0)
    raw["skud"] = pd.to_numeric(raw["skud"], errors="coerce").fillna(0.0)
    raw["__cn__"] = raw["contractor_name"].map(g.normalize_name)

    def _pick_name(s: pd.Series) -> str:
        cnt = s.astype(str).str.strip().value_counts()
        return str(cnt.idxmax()) if not cnt.empty else ""

    agg = raw.groupby("__cn__", as_index=False).agg(
        contractor_name=("contractor_name", _pick_name),
        plan=("plan", "sum"),
        skud=("skud", "sum"),
    )
    agg = agg.drop(columns=["__cn__"], errors="ignore")
    agg.rename(
        columns={"contractor_name": "Контрагент", "plan": "План", "skud": "Факт"},
        inplace=True,
    )
    agg["План"] = agg["План"].round(0).astype(int)
    agg["Факт"] = agg["Факт"].round(0).astype(int)
    agg["Отклонение"] = (agg["Факт"] - agg["План"]).round(0).astype(int)
    return agg.sort_values("План", ascending=False).reset_index(drop=True)


def _pie_chart_rows(chart_df: pd.DataFrame, *, top_n: int = 10) -> list[dict[str, Any]]:
    pie_source = chart_df[pd.to_numeric(chart_df["Факт"], errors="coerce").fillna(0) > 0].copy()
    if pie_source.empty:
        return []
    df = pie_source.sort_values("Факт", ascending=False).reset_index(drop=True)
    if len(df) > top_n:
        top = df.iloc[:top_n].copy()
        rest = df.iloc[top_n:]
        other_val = float(pd.to_numeric(rest["Факт"], errors="coerce").fillna(0).sum())
        if other_val > 0:
            top = pd.concat(
                [
                    top,
                    pd.DataFrame(
                        [{"Контрагент": f"Прочие ({len(rest)})", "Факт": other_val}]
                    ),
                ],
                ignore_index=True,
            )
        df = top
    return [
        {"name": str(r["Контрагент"]), "value": int(round(_num(r["Факт"])))}
        for _, r in df.iterrows()
    ]


def _distribution_rows(chart_df: pd.DataFrame) -> list[dict[str, Any]]:
    src = chart_df[
        (pd.to_numeric(chart_df["План"], errors="coerce").fillna(0) > 0)
        | (pd.to_numeric(chart_df["Факт"], errors="coerce").fillna(0) > 0)
    ].copy()
    if src.empty:
        return []
    src = src.sort_values(["План", "Факт"], ascending=False)
    total_fact = float(pd.to_numeric(src["Факт"], errors="coerce").fillna(0).sum()) or 1.0
    out: list[dict[str, Any]] = []
    for _, r in src.iterrows():
        plan_v = int(round(_num(r["План"])))
        fact_v = int(round(_num(r["Факт"])))
        out.append(
            {
                "contractor": str(r["Контрагент"]),
                "plan": plan_v,
                "fact": fact_v,
                "deviation": fact_v - plan_v,
                "share_pct": round(100.0 * fact_v / total_fact, 1),
            }
        )
    return out


def build_gdrs_payload(
    *,
    resource_kind: ResourceKind = "people",
    projects: str | None = None,
    contractors: str | None = None,
    months: str | None = None,
    plan_agg: str | None = None,
    skud_agg: str | None = None,
    dyn_agg: str | None = None,
    only_with_plan: bool | None = None,
) -> dict[str, Any]:
    g = _gdrs()
    labels = _labels()

    vid = _VID.get(resource_kind, "Рабочие")
    unit = _UNIT.get(resource_kind, "люди")
    unit_gen = _UNIT_GEN.get(resource_kind, "людей")

    try:
        prepare_web_db()
    except Exception as exc:
        return _empty_payload(
            resource_kind=resource_kind,
            error=f"web_data.db недоступна: {exc}",
        )

    version_id = active_version_id()
    if not version_id:
        return _empty_payload(
            resource_kind=resource_kind,
            error="Нет active version_id в web_data.db",
        )

    from web_db_read import json_records_by_source, web_db_mtime  # type: ignore

    db_mtime = float(web_db_mtime())
    dog_sig = g._gdrs_dogovor_sources_sig(int(version_id))

    long_fact = _cached_enriched_fact(int(version_id), db_mtime, dog_sig)
    if long_fact is None or long_fact.empty:
        return _empty_payload(
            resource_kind=resource_kind,
            warning="Нет данных ресурсов в БД (gdrs_fact)",
        )

    dog_records = json_records_by_source(int(version_id), "dogovor_json")
    spr_records = json_records_by_source(int(version_id), "spravochniki_json")
    kontr_records = json_records_by_source(int(version_id), "kontr_json")
    kontr_flat = [r for recs in kontr_records.values() for r in recs]
    kontr_index = g.load_1c_kontr_index(records=kontr_flat) if kontr_flat else None
    term_index = _cached_term_index(int(version_id), db_mtime, dog_sig)
    by_dog, by_pc, by_sig_pc, by_sig, by_pc_sets = _cached_dannye(int(version_id), db_mtime)

    extra_source_names = sorted(set(dog_records.keys()) | set(spr_records.keys()))
    month_options = g.gdrs_month_select_options(
        long_fact,
        extra_paths=extra_source_names,
        dogovor_records=dog_records,
    )
    month_labels = [lbl for lbl, _ in month_options]
    default_months = g.gdrs_default_month_labels(month_options, long_fact)

    sel_projects = _split_csv(projects)
    sel_contractors = _split_csv(contractors)
    sel_month_labels = _split_csv(months)
    if not sel_month_labels:
        sel_month_labels = list(default_months)

    only_plan = bool(only_with_plan) if only_with_plan is not None else False

    project_options = labels.project_labels_for_filter(
        long_fact["project_name"],
        apply_exclude_names=False,
    ) if "project_name" in long_fact.columns else []

    sel_periods, _stale = g.gdrs_resolve_month_periods(month_options, sel_month_labels)
    date_from, date_to = g.gdrs_months_date_range(sel_periods)
    date_from = pd.to_datetime(date_from)
    date_to = pd.to_datetime(date_to)

    _wk_fact = g.gdrs_filter_fact_by_months(long_fact, sel_periods)
    _wk_fact = g.gdrs_filter_fact_resursi_source_for_periods(_wk_fact, sel_periods)
    weeks_with_fact = g.gdrs_week_numbers_with_fact(
        _wk_fact,
        vid=vid,
        date_from=date_from,
        date_to=date_to,
        projects=sel_projects or None,
        contractors=sel_contractors or None,
    )
    agg_opts = g.gdrs_agg_select_options_for_weeks(weeks_with_fact)
    plan_lbl = (plan_agg or "").strip() or "Среднее за месяц"
    skud_lbl = (skud_agg or "").strip() or "Среднее за месяц"
    if plan_lbl not in agg_opts:
        plan_lbl = agg_opts[0] if agg_opts else "Среднее за месяц"
    if skud_lbl not in agg_opts:
        skud_lbl = agg_opts[0] if agg_opts else "Среднее за месяц"
    _plan_agg = g.gdrs_agg_label_to_key(plan_lbl)
    _skud_agg = g.gdrs_agg_label_to_key(skud_lbl)

    dyn_lbl = (dyn_agg or "").strip() or "День"
    if dyn_lbl not in _DYN_OPTS:
        dyn_lbl = "День"

    # Контрагенты: fact ∪ plan без полного gdrs_contractor_filter_options (тяжёлый).
    contractor_options: list[str] = []
    if "contractor_name" in long_fact.columns:
        contractor_options = sorted(
            {
                str(x).strip()
                for x in long_fact["contractor_name"].dropna().unique()
                if str(x).strip()
            }
        )

    long_fact_period = g.gdrs_filter_fact_by_months(long_fact, sel_periods)
    long_fact_period = g.gdrs_filter_fact_resursi_source_for_periods(
        long_fact_period, sel_periods
    )

    warning = None
    if _stale:
        warning = "Выбранный месяц отсутствует — показаны все доступные месяцы"
    elif (
        long_fact is not None
        and not long_fact.empty
        and (long_fact_period is None or long_fact_period.empty)
    ):
        warning = "За выбранный месяц нет фактических данных СКУД"

    _plan_snap = g.gdrs_plan_snapshot_date(
        long_fact_period,
        vid=vid,
        date_from=date_from,
        date_to=date_to,
        plan_agg=_plan_agg,
        projects=sel_projects or None,
        contractors=sel_contractors or None,
    )
    snap_iso = pd.Timestamp(_plan_snap).normalize().isoformat()

    def _plan_loader(snap: pd.Timestamp) -> pd.DataFrame:
        iso = pd.Timestamp(snap).normalize().isoformat()
        return _cached_plan(int(version_id), db_mtime, iso, dog_sig)

    plan = _plan_loader(pd.Timestamp(_plan_snap).normalize())
    if plan is not None and not plan.empty and "contractor_name" in plan.columns:
        for name in plan["contractor_name"].dropna().unique():
            s = str(name).strip()
            if s and s not in contractor_options:
                contractor_options.append(s)
        contractor_options = sorted(contractor_options)

    weekly_plan_by_week: dict[int, pd.DataFrame] = {}
    weekly_plan_as_of: dict[int, pd.Timestamp] = {}
    show_week_cols = g.gdrs_matrix_show_week_columns(
        _plan_agg, _skud_agg, date_from=date_from, date_to=date_to
    )
    if show_week_cols:
        for wn in g.gdrs_week_numbers_in_period(date_from, date_to):
            w_end = g.week_end_in_filtered_fact(
                long_fact_period,
                vid=vid,
                date_from=date_from,
                date_to=date_to,
                week_num=wn,
                projects=sel_projects or None,
                contractors=sel_contractors or None,
            )
            if w_end is None or not pd.notna(w_end):
                continue
            weekly_plan_as_of[wn] = pd.Timestamp(w_end).normalize()
            weekly_plan_by_week[wn] = _plan_loader(weekly_plan_as_of[wn])

    main_t = g.build_main_table(
        long_fact_period,
        plan,
        vid=vid,
        date_from=date_from,
        date_to=date_to,
        projects=sel_projects or None,
        contractors=sel_contractors or None,
        only_with_plan=only_plan,
        article_by_contract_norm=by_dog or None,
        article_sig_pc_sets=by_sig_pc or None,
        article_sig_sets=by_sig or None,
        article_by_project_contractor=by_pc or None,
        article_pc_sets=by_pc_sets or None,
        plan_agg=_plan_agg,
        skud_agg=_skud_agg,
        weekly_plan_by_week=weekly_plan_by_week or None,
        weekly_plan_as_of=weekly_plan_as_of or None,
        kontr_index=kontr_index,
        term_index=term_index,
        plan_as_of=pd.Timestamp(_plan_snap).normalize(),
        plan_aggregate_loader=_plan_loader,
        resursi_all_fact=long_fact,
    )

    period_label = ""
    if pd.notna(date_from) and pd.notna(date_to):
        period_label = (
            f"{date_from.strftime('%d.%m.%Y')} — {date_to.strftime('%d.%m.%Y')}"
            if date_from != date_to
            else date_from.strftime("%d.%m.%Y")
        )

    base_filters = {
        "projects": project_options,
        "contractors": contractor_options,
        "months": month_labels,
        "default_months": default_months,
        "agg_options": agg_opts,
        "dyn_agg_options": list(_DYN_OPTS),
        "selected": {
            "projects": sel_projects,
            "contractors": sel_contractors,
            "months": sel_month_labels,
            "plan_agg": plan_lbl,
            "skud_agg": skud_lbl,
            "dyn_agg": dyn_lbl,
            "only_with_plan": only_plan,
        },
    }

    if main_t is None or main_t.empty:
        empty = _empty_payload(
            resource_kind=resource_kind,
            warning=warning or "Нет данных для выбранных фильтров",
        )
        empty["meta"].update(
            {
                "period_label": period_label,
                "version_id": int(version_id),
                "unit": unit,
                "unit_gen": unit_gen,
            }
        )
        empty["filters"] = base_filters
        return empty

    gt = main_t[main_t["row_kind"] == "grand_total"]
    if not gt.empty:
        row = gt.iloc[0]
        kpis = {
            "plan": int(round(_num(row.get("plan")))),
            "fact": int(round(_num(row.get("skud")))),
            "deviation": int(round(_num(row.get("deviation")))),
            "delta_pct": _pct_out(row.get("delta_pct")),
        }
    else:
        kpis = {"plan": 0, "fact": 0, "deviation": 0, "delta_pct": None}

    proj_df = main_t[main_t["row_kind"] == "subtotal"][
        ["project_name", "plan", "skud", "deviation", "delta_pct"]
    ].copy()
    project_rows: list[dict[str, Any]] = []
    by_project: list[dict[str, Any]] = []
    if not proj_df.empty:
        _pn = proj_df["project_name"].astype(str).str.strip()
        proj_df = proj_df[
            _pn.ne("")
            & ~_pn.str.casefold().isin(("nan", "none", "<na>", "nat", "—", "-", "null"))
        ].copy()
    if not proj_df.empty:
        proj_df = proj_df.sort_values("plan", ascending=False)
        for _, r in proj_df.iterrows():
            plan_v = int(round(_num(r["plan"])))
            fact_v = int(round(_num(r["skud"])))
            dev_v = int(round(_num(r["deviation"])))
            name = str(r["project_name"])
            project_rows.append(
                {
                    "project": name,
                    "plan": plan_v,
                    "fact": fact_v,
                    "deviation": dev_v,
                    "delta_pct": _pct_out(r.get("delta_pct")),
                }
            )
            by_project.append(
                {
                    "name": name,
                    "plan": plan_v,
                    "fact": fact_v,
                    "deviation": abs(dev_v),
                }
            )

    chart_df = _build_contractors_chart_df(main_t)
    contractor_rows = _distribution_rows(chart_df)
    pie_rows = _pie_chart_rows(chart_df)
    by_contractor = [
        {
            "name": r["contractor"],
            "plan": r["plan"],
            "fact": r["fact"],
            "deviation": abs(int(r["deviation"])),
        }
        for r in contractor_rows[:30]
    ]

    week_labels: list[str] = []
    week_plan_keys: list[str] = []
    week_skud_keys: list[str] = []
    if show_week_cols:
        date_series = (
            long_fact_period["date"]
            if long_fact_period is not None and not long_fact_period.empty
            else None
        )
        week_labels = list(
            g.gdrs_matrix_week_labels(date_from, date_to, date_series) or []
        )
        wk_n = min(len(week_labels) or 6, 6)
        if not week_labels:
            week_labels = list(g.GDRS_WEEK_LABELS[:wk_n])
        else:
            week_labels = week_labels[:wk_n]
        week_plan_keys = list(g.GDRS_WEEK_PLAN_KEYS[: len(week_labels)])
        week_skud_keys = list(g.GDRS_WEEK_SKUD_KEYS[: len(week_labels)])

    matrix_rows: list[dict[str, Any]] = []
    for _, r in main_t.iterrows():
        kind = str(r.get("row_kind") or "row")
        if kind == "subtotal":
            label = str(r.get("project_name") or "")
        elif kind == "grand_total":
            label = "Итого"
        else:
            label = str(r.get("contractor_name") or "")
        vid_raboty = str(r.get("vid_raboty") or r.get("contract_name") or "").strip() or "—"
        item: dict[str, Any] = {
            "kind": kind,
            "label": label,
            "vid_raboty": vid_raboty if kind == "row" else "",
            "plan": int(round(_num(r.get("plan")))),
            "skud": int(round(_num(r.get("skud")))),
            "deviation": int(round(_num(r.get("deviation")))),
            "delta_pct": _pct_out(r.get("delta_pct")),
        }
        if show_week_cols:
            for pk in week_plan_keys:
                item[pk] = int(round(_num(r.get(pk)))) if pk in r.index else 0
            for wk in week_skud_keys:
                item[wk] = int(round(_num(r.get(wk)))) if wk in r.index else 0
        matrix_rows.append(item)

    # Динамика
    fact_dyn = long_fact_period.copy() if long_fact_period is not None else pd.DataFrame()
    if not fact_dyn.empty and "vid_resursa" in fact_dyn.columns:
        fact_dyn = fact_dyn[
            fact_dyn["vid_resursa"].astype(str).str.casefold() == vid.casefold()
        ]
    if sel_projects and not fact_dyn.empty:
        fact_dyn = labels.filter_dataframe_by_project_labels(
            fact_dyn, sel_projects, col="project_name"
        )
    if sel_contractors and not fact_dyn.empty and "contractor_name" in fact_dyn.columns:
        fact_dyn = fact_dyn[fact_dyn["contractor_name"].isin(sel_contractors)]

    plan_col = "plan_workers" if vid.casefold() == "рабочие" else "plan_equipment"
    dyn_plan_pairs = None
    if fact_dyn.empty and main_t is not None and not main_t.empty:
        dyn_detail = main_t[main_t["row_kind"] == "row"].copy()
        if not dyn_detail.empty:
            dyn_detail = dyn_detail[
                pd.to_numeric(dyn_detail["plan"], errors="coerce").fillna(0) > 0
            ]
        if not dyn_detail.empty:
            for c in ("project_id", "project_name", "contractor_id", "contractor_name"):
                if c not in dyn_detail.columns:
                    dyn_detail[c] = ""
            dyn_plan_pairs = dyn_detail[
                ["project_id", "project_name", "contractor_id", "contractor_name"]
            ].drop_duplicates()

    dynamics_chart: list[dict[str, Any]] = []
    dynamics_rows: list[dict[str, Any]] = []
    if (not fact_dyn.empty) or (
        dyn_plan_pairs is not None and not dyn_plan_pairs.empty
    ):
        if not fact_dyn.empty:
            fact_dyn = fact_dyn.copy()
            fact_dyn["date"] = pd.to_datetime(fact_dyn["date"])
            uniq_pairs = fact_dyn[
                ["project_id", "project_name", "contractor_id", "contractor_name"]
            ].drop_duplicates()
        else:
            uniq_pairs = dyn_plan_pairs
            fact_dyn = pd.DataFrame(
                columns=[
                    "project_id",
                    "project_name",
                    "contractor_id",
                    "contractor_name",
                    "date",
                    "fact",
                    "vid_resursa",
                ]
            )

        dyn_from = date_from.normalize() if pd.notna(date_from) else pd.Timestamp.today().normalize()
        dyn_to = date_to.normalize() if pd.notna(date_to) else dyn_from
        try:
            dyn = g.gdrs_dynamics_build_series(
                fact_dyn,
                dyn_from,
                dyn_to,
                dyn_lbl,
                [],
                [],
                uniq_pairs,
                plan_col,
                plan_aggregate_loader=_plan_loader,
                month_periods=sel_periods,
                term_index=term_index,
                plan_agg=_plan_agg,
                skud_agg=_skud_agg,
            )
        except Exception:
            dyn = pd.DataFrame()

        if dyn is not None and not dyn.empty:
            plan_s = pd.to_numeric(dyn["План"], errors="coerce").fillna(0.0)
            fact_s = pd.to_numeric(dyn["Факт"], errors="coerce").fillna(0.0)
            for i, row in dyn.iterrows():
                p = int(round(_num(plan_s.loc[i])))
                f = int(round(_num(fact_s.loc[i])))
                period = str(row.get("Период") or row.get("x_label") or row.get("bucket") or "")
                dp = ((f - p) / p * 100.0) if p > 0 else None
                item = {
                    "period": period,
                    "plan": p,
                    "fact": f,
                    "deviation": f - p,
                    "delta_pct": None if dp is None else round(dp, 1),
                }
                dynamics_rows.append(item)
                dynamics_chart.append(
                    {"period": period, "plan": p, "fact": f, "name": period}
                )

    return {
        "meta": {
            "data_mode": DATA_MODE,
            "resource_kind": resource_kind,
            "unit": unit,
            "unit_gen": unit_gen,
            "period_label": period_label,
            "rows": int(len(main_t[main_t["row_kind"] == "row"])),
            "resursi_files": 0,
            "version_id": int(version_id),
            "source": "web_data.db",
            "parity": "main_dashboard_gdrs",
            "warning": warning,
            "error": None,
            "show_week_columns": bool(show_week_cols),
            "week_labels": week_labels,
            "dyn_title": f"Динамика {'людей' if resource_kind == 'people' else 'техники'}",
            "pie_title": f"Распределение {unit_gen} по контрагентам",
            "matrix_title": f"ГДРС ({unit})",
        },
        "filters": base_filters,
        "kpis": kpis,
        "tremor": {
            "by_project": by_project[:30],
            "by_contractor": by_contractor,
            "pie": pie_rows,
            "dynamics": dynamics_chart,
        },
        "project_rows": project_rows,
        "contractor_rows": contractor_rows,
        "pie_rows": pie_rows,
        "matrix_rows": matrix_rows,
        "matrix_meta": {
            "show_week_columns": bool(show_week_cols),
            "week_labels": week_labels,
            "week_plan_keys": week_plan_keys,
            "week_skud_keys": week_skud_keys,
        },
        "dynamics_rows": dynamics_rows,
    }
