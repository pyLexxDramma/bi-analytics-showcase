from __future__ import annotations

import importlib.util
import math
import sys
from functools import lru_cache
from types import ModuleType
from typing import Any, Literal

import pandas as pd

from app.config import CORE_APP_DIR, DATA_MODE, WEB_DATA_DIR

ResourceKind = Literal["people", "equipment"]

_VID = {"people": "Рабочие", "equipment": "Техника"}
_UNIT = {"people": "люди", "equipment": "техника"}


def _ensure_core_path() -> None:
    core = str(CORE_APP_DIR.resolve())
    if core not in sys.path:
        sys.path.insert(0, core)


def _ensure_streamlit_stub() -> None:
    """API-образ без Streamlit: gdrs_resursi тянет st.cache_data на уровне модуля."""
    existing = sys.modules.get("streamlit")
    if existing is not None and getattr(existing, "cache_data", None) is not None:
        return
    try:
        if importlib.util.find_spec("streamlit") is not None:
            import streamlit  # noqa: F401

            return
    except ModuleNotFoundError:
        pass

    st = ModuleType("streamlit")

    def cache_data(*args, **kwargs):
        def decorator(fn):
            return fn

        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]
        return decorator

    st.cache_data = cache_data  # type: ignore[attr-defined]
    sys.modules["streamlit"] = st


def _import_dashboard_module(name: str):
    """Загрузка dashboards.<name> без выполнения dashboards/__init__.py (streamlit)."""
    _ensure_streamlit_stub()
    _ensure_core_path()
    full = f"dashboards.{name}"
    existing = sys.modules.get(full)
    if existing is not None:
        return existing
    if "dashboards" not in sys.modules:
        pkg = ModuleType("dashboards")
        pkg.__path__ = [str((CORE_APP_DIR / "dashboards").resolve())]  # type: ignore[attr-defined]
        sys.modules["dashboards"] = pkg
    path = CORE_APP_DIR / "dashboards" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(full, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full] = mod
    spec.loader.exec_module(mod)
    return mod


def _gdrs():
    return _import_dashboard_module("gdrs_resursi")


def _labels():
    return _import_dashboard_module("project_labels")


def _paths_mtime_sig(paths: list) -> tuple:
    from pathlib import Path as P

    sig: list[tuple] = []
    for p in sorted({str(P(x).resolve()) for x in paths}):
        pp = P(p)
        if pp.is_file():
            stt = pp.stat()
            sig.append((p, stt.st_mtime_ns, stt.st_size))
    return tuple(sig)


def _discover_files() -> dict[str, list]:
    from pathlib import Path as P

    web = WEB_DATA_DIR
    ai = web / "AI"
    resursi = sorted(ai.glob("*resursi*.csv")) if ai.is_dir() else []
    if not resursi and web.is_dir():
        resursi = sorted(web.glob("*resursi*.csv"))
    dogovor = sorted(web.glob("*_Dogovor.json")) if web.is_dir() else []
    sprav = sorted(web.glob("*_spravochniki.json")) if web.is_dir() else []
    kontr = sorted(web.glob("*_Kontr.json")) if web.is_dir() else []
    dannye: list[P] = []
    for base in (web, ai):
        if base.is_dir():
            for pat in ("*dannye*.json", "*Dannye*.json"):
                dannye.extend(base.glob(pat))
    dannye = sorted({p.resolve() for p in dannye if p.is_file()})
    return {
        "resursi": resursi,
        "dogovor": dogovor,
        "sprav": sprav,
        "kontr": kontr,
        "dannye": dannye,
    }


@lru_cache(maxsize=4)
def _cached_long_fact(res_sig: tuple) -> pd.DataFrame:
    from pathlib import Path as P

    g = _gdrs()
    labels = _labels()
    df = g.load_resursi_files([P(p[0]) for p in res_sig])
    if df is None or df.empty:
        return pd.DataFrame()
    return labels.apply_unified_project_column(df, "project_name")


@lru_cache(maxsize=32)
def _cached_plan(dog_sig: tuple, spr_sig: tuple, snapshot_iso: str) -> pd.DataFrame:
    from pathlib import Path as P

    g = _gdrs()
    snap = pd.Timestamp(snapshot_iso) if snapshot_iso else None
    return g.load_plan_aggregate(
        [P(p[0]) for p in dog_sig],
        [P(p[0]) for p in spr_sig],
        snapshot_date=snap,
    )


@lru_cache(maxsize=4)
def _cached_dannye(dannye_sig: tuple):
    from pathlib import Path as P

    if not dannye_sig:
        return {}, {}, {}, {}, {}
    return _gdrs().load_1c_dannye_article_maps([P(p[0]) for p in dannye_sig])


def clear_gdrs_caches() -> None:
    _cached_long_fact.cache_clear()
    _cached_plan.cache_clear()
    _cached_dannye.cache_clear()


def _num(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    if math.isnan(x) or math.isinf(x):
        return default
    return x


def _split_csv(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [p.strip() for p in str(raw).split(",") if p.strip()]


def _enrich_fact(long_fact: pd.DataFrame, files: dict[str, list]):
    g = _gdrs()
    kontr_index = g.load_1c_kontr_index(files["kontr"]) if files["kontr"] else None
    long_fact = g.enrich_gdrs_fact_contractor_ids(
        long_fact,
        dogovor_paths=files["dogovor"],
        kontr=kontr_index,
    )
    long_fact = g.enrich_gdrs_fact_project_ids(
        long_fact,
        dogovor_paths=files["dogovor"],
    )
    long_fact = g.gdrs_filter_fact_kontr_intersection(long_fact, kontr_index)
    term_index = g.load_gdrs_termination_index(files["dogovor"])
    long_fact = g.gdrs_filter_fact_by_termination(long_fact, term_index)
    return long_fact, kontr_index, term_index


def build_gdrs_payload(
    *,
    resource_kind: ResourceKind = "people",
    projects: str | None = None,
    contractors: str | None = None,
    months: str | None = None,
    plan_agg: str | None = None,
    skud_agg: str | None = None,
) -> dict[str, Any]:
    g = _gdrs()
    labels = _labels()

    vid = _VID.get(resource_kind, "Рабочие")
    unit = _UNIT.get(resource_kind, "люди")
    files = _discover_files()

    empty = {
        "meta": {
            "data_mode": DATA_MODE,
            "resource_kind": resource_kind,
            "unit": unit,
            "period_label": "",
            "rows": 0,
            "resursi_files": 0,
            "warning": None,
        },
        "filters": {
            "projects": [],
            "contractors": [],
            "months": [],
            "default_months": [],
            "agg_options": g.gdrs_agg_select_options(),
            "selected": {
                "projects": [],
                "contractors": [],
                "months": [],
                "plan_agg": "Среднее за месяц",
                "skud_agg": "Среднее за месяц",
            },
        },

        "kpis": {"plan": 0, "fact": 0, "deviation": 0, "delta_pct": None},
        "tremor": {"by_project": [], "by_contractor": []},
        "project_rows": [],
        "contractor_rows": [],
        "matrix_rows": [],
    }

    if not files["resursi"]:
        empty["meta"]["warning"] = "Не найдены файлы other_*_resursi.csv в web/AI"
        return empty

    res_sig = _paths_mtime_sig(files["resursi"])
    dog_sig = _paths_mtime_sig(files["dogovor"])
    spr_sig = _paths_mtime_sig(files["sprav"])
    dannye_sig = _paths_mtime_sig(files["dannye"])

    long_fact = _cached_long_fact(res_sig)
    if long_fact is None or long_fact.empty:
        empty["meta"]["warning"] = "Файлы ресурсов не распознаны"
        empty["meta"]["resursi_files"] = len(files["resursi"])
        return empty

    long_fact, kontr_index, term_index = _enrich_fact(long_fact.copy(), files)

    month_options = g.gdrs_month_select_options(
        long_fact,
        extra_paths=list(files["resursi"]) + list(files["dogovor"]),
    )
    month_labels = [lbl for lbl, _ in month_options]
    default_months = g.gdrs_default_month_labels(month_options, long_fact)

    sel_projects = _split_csv(projects)
    sel_contractors = _split_csv(contractors)
    sel_month_labels = _split_csv(months)
    if not sel_month_labels:
        sel_month_labels = list(default_months)

    agg_opts = g.gdrs_agg_select_options()
    plan_lbl = (plan_agg or "").strip() or "Среднее за месяц"
    skud_lbl = (skud_agg or "").strip() or "Среднее за месяц"
    if plan_lbl not in agg_opts:
        plan_lbl = "Среднее за месяц"
    if skud_lbl not in agg_opts:
        skud_lbl = "Среднее за месяц"
    _plan_agg = g.gdrs_agg_label_to_key(plan_lbl)
    _skud_agg = g.gdrs_agg_label_to_key(skud_lbl)

    project_options = (
        labels.project_labels_for_filter(long_fact["project_name"])
        if "project_name" in long_fact.columns
        else []
    )

    filter_plan_snap = (
        pd.Timestamp(month_options[-1][1].end_time).normalize() if month_options else None
    )
    contractor_options = g.gdrs_contractor_filter_options(
        long_fact,
        files["dogovor"],
        files["sprav"],
        projects=sel_projects or None,
        snapshot_date=filter_plan_snap,
    )

    sel_periods, _stale = g.gdrs_resolve_month_periods(month_options, sel_month_labels)
    date_from, date_to = g.gdrs_months_date_range(sel_periods)
    date_from = pd.to_datetime(date_from)
    date_to = pd.to_datetime(date_to)
    long_fact_period = g.gdrs_filter_fact_by_months(long_fact, sel_periods)

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
    plan = _cached_plan(dog_sig, spr_sig, snap_iso)

    by_dog, by_pc, by_sig_pc, by_sig, by_pc_sets = _cached_dannye(dannye_sig)

    def _plan_loader(snap: pd.Timestamp) -> pd.DataFrame:
        iso = pd.Timestamp(snap).normalize().isoformat()
        return _cached_plan(dog_sig, spr_sig, iso)

    main_t = g.build_main_table(
        long_fact_period,
        plan,
        vid=vid,
        date_from=date_from,
        date_to=date_to,
        projects=sel_projects or None,
        contractors=sel_contractors or None,
        only_with_plan=True,
        article_by_contract_norm=by_dog or None,
        article_sig_pc_sets=by_sig_pc or None,
        article_sig_sets=by_sig or None,
        article_by_project_contractor=by_pc or None,
        article_pc_sets=by_pc_sets or None,
        plan_agg=_plan_agg,
        skud_agg=_skud_agg,
        kontr_index=kontr_index,
        term_index=term_index,
        plan_as_of=pd.Timestamp(_plan_snap).normalize(),
        plan_aggregate_loader=_plan_loader,
    )

    period_label = ""
    if pd.notna(date_from) and pd.notna(date_to):
        period_label = (
            f"{date_from.strftime('%d.%m.%Y')} — {date_to.strftime('%d.%m.%Y')}"
            if date_from != date_to
            else date_from.strftime("%d.%m.%Y")
        )

    if main_t is None or main_t.empty:
        return {
            **empty,
            "meta": {
                "data_mode": DATA_MODE,
                "resource_kind": resource_kind,
                "unit": unit,
                "period_label": period_label,
                "rows": 0,
                "resursi_files": len(files["resursi"]),
                "warning": warning or "Нет данных для выбранных фильтров",
            },
            "filters": {
                "projects": project_options,
                "contractors": contractor_options,
                "months": month_labels,
                "default_months": default_months,
                "agg_options": agg_opts,
                "selected": {
                    "projects": sel_projects,
                    "contractors": sel_contractors,
                    "months": sel_month_labels,
                    "plan_agg": plan_lbl,
                    "skud_agg": skud_lbl,
                },
            },
        }

    # KPIs from grand_total
    gt = main_t[main_t["row_kind"] == "grand_total"]
    if not gt.empty:
        row = gt.iloc[0]
        kpis = {
            "plan": int(round(_num(row.get("plan")))),
            "fact": int(round(_num(row.get("skud")))),
            "deviation": int(round(_num(row.get("deviation")))),
            "delta_pct": (
                None
                if row.get("delta_pct") is None or (isinstance(row.get("delta_pct"), float) and math.isnan(row.get("delta_pct")))
                else round(_num(row.get("delta_pct")), 1)
            ),
        }
    else:
        kpis = {"plan": 0, "fact": 0, "deviation": 0, "delta_pct": None}

    # Projects
    proj_df = main_t[main_t["row_kind"] == "subtotal"][
        ["project_name", "plan", "skud", "deviation", "delta_pct"]
    ].copy()
    project_rows: list[dict[str, Any]] = []
    by_project: list[dict[str, Any]] = []
    if not proj_df.empty:
        proj_df = proj_df.sort_values("plan", ascending=False)
        for _, r in proj_df.iterrows():
            plan_v = int(round(_num(r["plan"])))
            fact_v = int(round(_num(r["skud"])))
            dev_v = int(round(_num(r["deviation"])))
            dp = r.get("delta_pct")
            dp_out = (
                None
                if dp is None or (isinstance(dp, float) and math.isnan(dp))
                else round(_num(dp), 1)
            )
            name = str(r["project_name"])
            project_rows.append(
                {
                    "project": name,
                    "plan": plan_v,
                    "fact": fact_v,
                    "deviation": dev_v,
                    "delta_pct": dp_out,
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

    # Contractors chart
    raw = main_t.loc[
        main_t["row_kind"] == "row",
        [c for c in ("project_name", "contractor_name", "plan", "skud") if c in main_t.columns],
    ].copy()
    contractor_rows: list[dict[str, Any]] = []
    by_contractor: list[dict[str, Any]] = []
    if not raw.empty and "contractor_name" in raw.columns:
        if "project_name" in raw.columns:
            raw = raw.drop_duplicates(subset=["project_name", "contractor_name"], keep="first")
        raw["contractor_name"] = raw["contractor_name"].astype(str).str.strip()
        raw = raw[raw["contractor_name"] != ""]
        raw["plan"] = pd.to_numeric(raw["plan"], errors="coerce").fillna(0.0)
        raw["skud"] = pd.to_numeric(raw["skud"], errors="coerce").fillna(0.0)
        agg = (
            raw.groupby("contractor_name", as_index=False)
            .agg(plan=("plan", "sum"), skud=("skud", "sum"))
            .sort_values("plan", ascending=False)
        )
        total_fact = float(agg["skud"].sum()) or 1.0
        for _, r in agg.iterrows():
            plan_v = int(round(_num(r["plan"])))
            fact_v = int(round(_num(r["skud"])))
            dev_v = fact_v - plan_v
            share = round(100.0 * fact_v / total_fact, 1)
            name = str(r["contractor_name"])
            contractor_rows.append(
                {
                    "contractor": name,
                    "plan": plan_v,
                    "fact": fact_v,
                    "deviation": dev_v,
                    "share_pct": share,
                }
            )
            by_contractor.append(
                {
                    "name": name,
                    "plan": plan_v,
                    "fact": fact_v,
                    "deviation": abs(dev_v),
                }
            )

    # Matrix (simplified, no week columns)
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
        dp = r.get("delta_pct")
        matrix_rows.append(
            {
                "kind": kind,
                "label": label,
                "vid_raboty": vid_raboty if kind == "row" else "",
                "plan": int(round(_num(r.get("plan")))),
                "skud": int(round(_num(r.get("skud")))),
                "deviation": int(round(_num(r.get("deviation")))),
                "delta_pct": (
                    None
                    if dp is None or (isinstance(dp, float) and math.isnan(dp))
                    else round(_num(dp), 1)
                ),
            }
        )

    return {
        "meta": {
            "data_mode": DATA_MODE,
            "resource_kind": resource_kind,
            "unit": unit,
            "period_label": period_label,
            "rows": int(len(main_t[main_t["row_kind"] == "row"])),
            "resursi_files": len(files["resursi"]),
            "warning": warning,
        },
        "filters": {
            "projects": project_options,
            "contractors": contractor_options,
            "months": month_labels,
            "default_months": default_months,
            "agg_options": agg_opts,
            "selected": {
                "projects": sel_projects,
                "contractors": sel_contractors,
                "months": sel_month_labels,
                "plan_agg": plan_lbl,
                "skud_agg": skud_lbl,
            },
        },
        "kpis": kpis,
        "tremor": {
            "by_project": by_project[:30],
            "by_contractor": by_contractor[:30],
        },
        "project_rows": project_rows,
        "contractor_rows": contractor_rows,
        "matrix_rows": matrix_rows,
    }
