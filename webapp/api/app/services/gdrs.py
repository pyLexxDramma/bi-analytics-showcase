from __future__ import annotations

import math
from functools import lru_cache
from typing import Any, Literal

import pandas as pd

from app.config import DATA_MODE, WEB_DATA_DIR
from app.services.core_bridge import import_dashboard_module as _import_dashboard_module

ResourceKind = Literal["people", "equipment"]

_VID = {"people": "Рабочие", "equipment": "Техника"}
_UNIT = {"people": "люди", "equipment": "техника"}


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
    resursi = _keep_recent_by_name_date(resursi, limit=3)
    dogovor = sorted(web.glob("*_Dogovor.json")) if web.is_dir() else []
    sprav = sorted(web.glob("*_spravochniki.json")) if web.is_dir() else []
    kontr = sorted(web.glob("*_Kontr.json")) if web.is_dir() else []
    dannye: list[P] = []
    for base in (web, ai):
        if base.is_dir():
            for pat in ("*dannye*.json", "*Dannye*.json"):
                dannye.extend(base.glob(pat))
    dannye = sorted({p.resolve() for p in dannye if p.is_file()})
    # Docker/VPS: полный набор 1С JSON слишком тяжёлый для синхронного API —
    # оставляем недавние снапшоты (семантика среза плана сохраняется).
    dogovor = _keep_recent_by_name_date(dogovor, limit=2)
    sprav = _keep_recent_by_name_date(sprav, limit=1)
    kontr = _keep_recent_by_name_date(kontr, limit=1)
    dannye = []
    return {
        "resursi": resursi,
        "dogovor": dogovor,
        "sprav": sprav,
        "kontr": kontr,
        "dannye": dannye,
    }


def _keep_recent_by_name_date(paths: list, *, limit: int) -> list:
    """Оставить последние `limit` файлов по дате в имени (DD-MM-YYYY), иначе по mtime."""
    import re

    if limit <= 0:
        return []
    if len(paths) <= limit:
        return list(paths)
    date_re = re.compile(r"(\d{2})-(\d{2})-(\d{4})")
    dated: list[tuple] = []
    for p in paths:
        m = date_re.search(p.name)
        if m:
            dd, mm, yy = m.groups()
            key = (int(yy), int(mm), int(dd), p.stat().st_mtime if p.is_file() else 0.0)
        else:
            key = (0, 0, 0, p.stat().st_mtime if p.is_file() else 0.0)
        dated.append((key, p))
    dated.sort(key=lambda x: x[0])
    return [p for _, p in dated[-limit:]]


@lru_cache(maxsize=4)
def _cached_long_fact(res_sig: tuple) -> pd.DataFrame:
    from pathlib import Path as P

    g = _gdrs()
    frames: list[pd.DataFrame] = []
    for item in res_sig:
        try:
            df = g.load_resursi_file(P(item[0]))
        except Exception:
            continue
        if df is not None and not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    # Без fuzzy-canonicalize и unified project labels (на VPS — десятки секунд CPU).
    return out.drop_duplicates(
        subset=["project_name", "contractor_name", "vid_resursa", "date"],
        keep="last",
    )


@lru_cache(maxsize=32)
def _cached_plan(dog_sig: tuple, spr_sig: tuple, snapshot_iso: str) -> pd.DataFrame:
    """План из 1–2 последних Dogovor (без полного load_plan_aggregate по десяткам файлов)."""
    from pathlib import Path as P

    g = _gdrs()
    snap = pd.Timestamp(snapshot_iso) if snapshot_iso else None
    paths = [P(p[0]) for p in dog_sig][-1:]
    frames: list[pd.DataFrame] = []
    for path in paths:
        try:
            df = g.load_plan_from_dogovor(path, snapshot_date=snap)
        except Exception:
            continue
        if df is not None and not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame(
            columns=[
                "project_id",
                "contractor_id",
                "project_name",
                "contractor_name",
                "contract_name",
                "plan_workers",
                "plan_equipment",
            ]
        )
    plan = pd.concat(frames, ignore_index=True)
    return (
        plan.groupby(["project_id", "contractor_id"], dropna=False, as_index=False)
        .agg(
            project_name=("project_name", "first"),
            contractor_name=("contractor_name", "first"),
            contract_name=("contract_name", "first"),
            plan_workers=("plan_workers", "sum"),
            plan_equipment=("plan_equipment", "sum"),
        )
    )


@lru_cache(maxsize=4)
def _cached_dannye(dannye_sig: tuple):
    # Вид работ из dannye на VPS слишком дорог — пропускаем.
    return {}, {}, {}, {}, {}


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
    # Полный gate Kontr/termination на VPS — минуты; для showcase MVP не применяем.
    return long_fact, None, None


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

    project_options = sorted(
        {
            str(x).strip()
            for x in long_fact["project_name"].dropna().unique()
            if str(x).strip()
        }
    ) if "project_name" in long_fact.columns else []

    # Не вызывать gdrs_contractor_filter_options — внутри load_plan_aggregate (минуты на VPS).
    contractor_options: list[str] = []
    if "contractor_name" in long_fact.columns:
        contractor_options = sorted(
            {
                str(x).strip()
                for x in long_fact["contractor_name"].dropna().unique()
                if str(x).strip()
            }
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
