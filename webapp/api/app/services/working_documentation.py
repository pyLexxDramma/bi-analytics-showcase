"""Рабочая документация (РД) — паритет с [main] `_rd_plan_fallback_view` + `dashboard_rd_delay`.

План/TESSA — из `web_data.db` через `core_bridge`. Даты договора/прогноза: как в main —
сначала CSV lookup `other_*_rd.csv` из staging web/ (SHOWCASE_WEB_DIR), иначе
`_rd_plan_db_contract_lookup` из БД. UI не читает web/.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd

from app.config import CORE_APP_DIR, DATA_MODE, WEB_DATA_DIR, WEB_DB_PATH
from app.services.core_bridge import (
    ensure_core_path,
    ensure_streamlit_stub,
    load_version_df,
    prepare_web_db,
)
from app.services.report_cache import cache_get, cache_set

_BLANK = frozenset({"", "nan", "none", "null", "<na>", "-", "—", "нд", "nd", "nat"})
_MONTH_RU = (
    "",
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

_PIE_COLORS = {
    "Выдано в производство работ": "#27AE60",
    "На рассмотрении у ГИП": "#F1C40F",
    "Возвращено на доработку": "#C0392B",
    "Не выдано": "#F5A9C0",
}

_RENDERERS_MOD = "dashboards._renderers_rd"


def _parse_detail_date(mod: ModuleType, series: pd.Series) -> pd.Series:
    parse = getattr(mod, "_rd_parse_chart_date_cell", None)
    if callable(parse):
        return series.map(parse)
    return pd.to_datetime(series, errors="coerce", dayfirst=True)


def _plan_slice_from_detail(detail_tbl: pd.DataFrame, mod: ModuleType) -> pd.DataFrame:
    """План/факт только по отфильтрованным строкам детализации — без рыхлого джойна."""
    if detail_tbl is None or getattr(detail_tbl, "empty", True):
        return pd.DataFrame(columns=["_plan_dt", "_tessa_production_dt"])
    plan_col = "Дата выдачи разделов по Договору"
    prod_col = "Дата выдачи в производство работ"
    out = pd.DataFrame(index=detail_tbl.index)
    if plan_col in detail_tbl.columns:
        out["_plan_dt"] = _parse_detail_date(mod, detail_tbl[plan_col])
    else:
        out["_plan_dt"] = pd.NaT
    if prod_col in detail_tbl.columns:
        prod_dt = _parse_detail_date(mod, detail_tbl[prod_col])
    else:
        prod_dt = pd.Series(pd.NaT, index=detail_tbl.index)
    canon = getattr(mod, "_rd_canonical_tessa_rd_status", None)
    prod_key = getattr(mod, "_RD_TESSA_STATUS_PRODUCTION", "Выдано в производство работ")
    if "Статус" in detail_tbl.columns and callable(canon):
        issued = detail_tbl["Статус"].map(lambda x: canon(x) == prod_key).fillna(False)
        prod_dt = prod_dt.where(issued, pd.NaT)
    out["_tessa_production_dt"] = prod_dt
    return out


def _status_counts_from_detail(detail_tbl: pd.DataFrame, mod: ModuleType) -> dict[str, int]:
    """Счётчики статусов по уже отфильтрованной детальной таблице (TESSA)."""
    if detail_tbl is None or getattr(detail_tbl, "empty", True):
        return {}
    if "Статус" not in detail_tbl.columns:
        return {}
    canon = getattr(mod, "_rd_canonical_tessa_rd_status", None)
    counts: dict[str, int] = {}
    for raw in detail_tbl["Статус"].tolist():
        label = canon(raw) if callable(canon) else None
        if not label:
            s = str(raw or "").strip()
            if not s or s.casefold() in _BLANK:
                continue
            label = s
        counts[label] = counts.get(label, 0) + 1
    return counts


def _tessa_status_keys(mod: ModuleType) -> dict[str, str]:
    return {
        "production": getattr(mod, "_RD_TESSA_STATUS_PRODUCTION", "Выдано в производство работ"),
        "review": getattr(mod, "_RD_TESSA_STATUS_REVIEW", "На рассмотрении у ГИП"),
        "rework": getattr(mod, "_RD_TESSA_STATUS_REWORK", "Возвращено на доработку"),
        "not_issued": getattr(mod, "_RD_TESSA_STATUS_NOT_ISSUED", "Не выдано"),
    }


def _canon_rd_status(mod: ModuleType, raw: object) -> str | None:
    fn = getattr(mod, "_rd_canonical_tessa_rd_status", None)
    if callable(fn):
        return fn(raw)
    s = str(raw or "").strip()
    return s or None


def _sel_has_status(sel: list[str], label: str, mod: ModuleType) -> bool:
    if not sel or not label:
        return False
    expanded = mod._rd_status_filter_expand([label])
    return any(mod._rd_status_label_matches_filter(s, expanded) for s in sel)


def _sel_is_not_issued_only(sel: list[str], mod: ModuleType) -> bool:
    keys = _tessa_status_keys(mod)
    return bool(sel) and all(
        _sel_has_status([s], keys["not_issued"], mod) for s in sel
    )


def _not_issued_residual(plan_n: int, tz_counts: dict[str, int], keys: dict[str, str]) -> int:
    """Как карточка без фильтра: план − TESSA «Выдано в производство»."""
    prod_n = int((tz_counts or {}).get(keys["production"], 0) or 0)
    return max(0, int(plan_n) - prod_n)


def _pie_for_not_issued_residual(
    n: int,
    tz_counts: dict[str, int],
    keys: dict[str, str],
    not_issued_label: str,
) -> dict[str, int]:
    review_n = int((tz_counts or {}).get(keys["review"], 0) or 0)
    rework_n = int((tz_counts or {}).get(keys["rework"], 0) or 0)
    plain_n = max(0, int(n) - review_n - rework_n)
    out: dict[str, int] = {}
    if review_n > 0:
        out[keys["review"]] = review_n
    if rework_n > 0:
        out[keys["rework"]] = rework_n
    if plain_n > 0:
        out[not_issued_label] = plain_n
    return out


def _align_detail_to_not_issued_n(
    detail_tbl: pd.DataFrame,
    target: int,
    mod: ModuleType,
) -> pd.DataFrame:
    """Таблица «Не выдано» = тот же остаток, что и карточка (без лишней строки джойна)."""
    if detail_tbl is None or getattr(detail_tbl, "empty", True) or int(target) < 0:
        return detail_tbl
    if int(len(detail_tbl)) <= int(target):
        return detail_tbl
    cipher_col = "Шифр" if "Шифр" in detail_tbl.columns else None
    kept = detail_tbl
    if cipher_col:
        fake = pd.DataFrame({"_c": detail_tbl[cipher_col]}, index=detail_tbl.index)
        issued = _issued_mask_from_tessa_status(mod, fake, None, "_c")
        drop = issued.reindex(detail_tbl.index).fillna(False)
        if bool(drop.any()):
            kept = detail_tbl.loc[~drop].copy()
    if int(len(kept)) > int(target):
        kept = kept.iloc[: int(target)].copy()
    return kept.reset_index(drop=True)


def _sel_is_not_issued_family(sel: list[str], mod: ModuleType) -> bool:
    """Срез без «Выдано в производство»: Не выдано / ГИП / доработка."""
    if not sel:
        return False
    keys = _tessa_status_keys(mod)
    family = (keys["not_issued"], keys["review"], keys["rework"])
    return all(any(_sel_has_status([s], lab, mod) for lab in family) for s in sel)


def _detail_status_mask(detail_tbl: pd.DataFrame, sel: list[str], mod: ModuleType) -> pd.Series:
    """Маска строк детализации под фильтр статуса.

    «Не выдано» = всё, что не выдано в производство: сам статус, рассмотрение
    у ГИП, возврат на доработку и пустой статус.
    """
    if detail_tbl.empty or "Статус" not in detail_tbl.columns:
        return pd.Series(False, index=detail_tbl.index)
    keys = _tessa_status_keys(mod)
    raw = detail_tbl["Статус"]
    if _sel_is_not_issued_only(sel, mod):
        return raw.map(lambda x: _canon_rd_status(mod, x) != keys["production"]).fillna(True)
    expanded = mod._rd_status_filter_expand(sel)
    return raw.map(lambda x: mod._rd_status_label_matches_filter(x, expanded)).fillna(False)


def _empty_payload(*, error: str | None = None) -> dict[str, Any]:
    return {
        "meta": {
            "rows": 0,
            "source": "web_data.db",
            "data_mode": DATA_MODE,
            "files": 0,
            "doc_kind": "rd",
            "title": "Рабочая документация",
            "rule": "rd_plan+tessa БД; даты договора CSV web/ → DB fallback",
            "parity": "main_working_documentation_rd_plan_tessa",
            "version_id": None,
            "error": error,
        },
        "filters": {
            "projects": ["Все"],
            "sections": ["Все"],
            "statuses": [],
            "period_modes": ["Весь период (за всё время)", "Выбор диапазона дат"],
            "metric_modes": ["Количество разделов", "% от общего объёма"],
            "view_modes": [{"id": "project", "label": "По проекту"}, {"id": "section", "label": "По разделу"}],
            "applied": {
                "projects": ["Все"],
                "sections": ["Все"],
                "statuses": [],
                "period_mode": "Весь период (за всё время)",
                "date_from": None,
                "date_to": None,
                "metric_mode": "Количество разделов",
                "show_forecast": True,
                "view_mode": "project",
                "tab": "main",
            },
        },
        "kpis": {
            "total_sections": 0,
            "overdue": 0,
            "avg_delay": 0.0,
            "issued_production": 0,
            "not_issued": 0,
            "plan_total": 0,
            "plan_to_date": 0,
            "fact_to_date": 0,
            "deviation_to_date": 0,
            "planned_weekly": None,
            "fact_weekly": None,
            "nec_weekly": None,
        },
        "tremor": {
            "status_mix": [],
            "dynamics": [],
            "monthly": [],
        },
        "detail_rows": [],
        "detail_columns": [],
        "delay": {
            "gantt": {"rows": [], "range_start": None, "range_end": None},
            "detail_rows": [],
            "detail_columns": [],
        },
    }


def _ensure_showcase_web_in_extra_paths() -> None:
    """Чтобы `_r23_12_load_rd_plan_lookup` видел SHOWCASE_WEB_DIR / webapp data/web."""
    try:
        web = str(Path(WEB_DATA_DIR).resolve())
    except Exception:
        return
    if not web or not Path(web).is_dir():
        return
    cur = os.environ.get("BI_ANALYTICS_WEB_EXTRA_PATHS", "")
    parts = [p.strip() for p in cur.replace(";", ",").split(",") if p.strip()]
    resolved: set[str] = set()
    for p in parts:
        try:
            resolved.add(str(Path(p).expanduser().resolve()))
        except Exception:
            resolved.add(p)
    if web in resolved:
        return
    parts.append(web)
    os.environ["BI_ANALYTICS_WEB_EXTRA_PATHS"] = ",".join(parts)


def _load_rd_renderers() -> ModuleType:
    ensure_streamlit_stub()
    ensure_core_path()
    _ensure_showcase_web_in_extra_paths()
    existing = sys.modules.get(_RENDERERS_MOD)
    if existing is not None:
        fn = getattr(existing, "_r23_12_load_rd_plan_lookup", None)
        # Старый патч `lambda: {}` — перезагружаем модуль, чтобы вернуть CSV lookup.
        if callable(fn) and getattr(fn, "__name__", "") == "<lambda>":
            sys.modules.pop(_RENDERERS_MOD, None)
        else:
            try:
                clear = getattr(fn, "clear", None)
                if callable(clear):
                    clear()
            except Exception:
                pass
            return existing
    if "dashboards" not in sys.modules:
        pkg = ModuleType("dashboards")
        pkg.__path__ = [str((CORE_APP_DIR / "dashboards").resolve())]  # type: ignore[attr-defined]
        sys.modules["dashboards"] = pkg
    path = Path(CORE_APP_DIR) / "dashboards" / "_renderers.py"
    spec = importlib.util.spec_from_file_location(_RENDERERS_MOD, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_RENDERERS_MOD] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(_RENDERERS_MOD, None)
        raise
    # Как main: файловый CSV lookup + DB fallback внутри _build_rd_work_doc_detail_table.
    return module


def _issued_mask_from_tessa_status(
    mod: ModuleType,
    plan_df: pd.DataFrame,
    proj_col: str | None,
    code_col: str | None,
    *,
    full_cipher_col: str | None = None,
) -> pd.Series:
    """Выдано = TESSA Status как на пироге (не даты tasks и не KrState).

    Сначала (проект, шифр). На prod в плане проект = UUID, в TESSA — имя,
    этот join даёт 0 при KPI 319 — тогда матч только по шифру / полному шифру.
    """
    mask = pd.Series(False, index=plan_df.index)
    if plan_df.empty or not code_col or code_col not in plan_df.columns:
        return mask
    try:
        import streamlit as st  # type: ignore

        tdf = st.session_state.get("tessa_data")
    except Exception:
        return mask
    if tdf is None or getattr(tdf, "empty", True):
        return mask
    try:
        t = tdf.copy()
        t.columns = [str(c).strip() for c in t.columns]
        project_col = mod._tessa_find_column(t, ["ObjectProjectName", "ProjectName", "ObjectName"])
        cipher_col = mod._tessa_find_column(t, ["DivisionCipher", "Cipher"])
        status_col = mod._tessa_find_column(t, ["Status", "Статус"])
        internal_col = mod._tessa_find_column(t, ["InternalID", "Internal Id", "InternalId"])
        if not cipher_col or not status_col:
            return mask
        t = t[t[cipher_col].map(mod._tessa_cell_has_value).fillna(False)]
        t = mod._tessa_rd_dedupe_cards_latest(t)
        prod = getattr(mod, "_RD_TESSA_STATUS_PRODUCTION", "Выдано в производство работ")
        t = t.loc[t[status_col].map(mod._rd_canonical_tessa_rd_status).eq(prod)]
        if t.empty:
            return mask
        issued_ck: set[str] = set()
        issued_internal: set[str] = set()
        by_ciph: dict[str, set[str]] = {}
        for _, r in t.iterrows():
            ck = str(mod._tessa_norm_cipher_key(r.get(cipher_col, "")) or "")
            pk = (
                str(mod._tessa_norm_project_key(r.get(project_col, "")) or "")
                if project_col
                else ""
            )
            if ck:
                issued_ck.add(ck)
                if pk:
                    by_ciph.setdefault(ck, set()).add(pk)
            if internal_col:
                iid = str(mod._tessa_norm_cipher_key(r.get(internal_col, "")) or "")
                if iid:
                    issued_internal.add(iid)
        if not issued_ck and not issued_internal:
            return mask
        plan_ck = plan_df[code_col].map(mod._tessa_norm_cipher_key).fillna("").astype(str)
        plan_fc = (
            plan_df[full_cipher_col].map(mod._tessa_norm_cipher_key).fillna("").astype(str)
            if full_cipher_col and full_cipher_col in plan_df.columns
            else pd.Series("", index=plan_df.index)
        )
        if proj_col and proj_col in plan_df.columns and by_ciph:
            plan_pk = plan_df[proj_col].map(mod._tessa_norm_project_key).fillna("").astype(str)
            match_fn = getattr(mod, "_project_norm_key_matches_msp_keys", None)
            hits: list[bool] = []
            for p, c in zip(plan_pk.tolist(), plan_ck.tolist()):
                tessa_pks = by_ciph.get(c) or set()
                if not tessa_pks:
                    hits.append(False)
                    continue
                if p in tessa_pks:
                    hits.append(True)
                    continue
                ok = False
                if callable(match_fn) and p:
                    for tpk in tessa_pks:
                        if match_fn(tpk, {p}) or match_fn(p, {tpk}):
                            ok = True
                            break
                hits.append(ok)
            proj_hits = pd.Series(hits, index=plan_df.index)
            if proj_hits.any():
                return proj_hits
        # Только точный шифр / InternalID — без endswith (иначе monthly fact
        # раздувается до ~695 при KPI «выдано» 319).
        cipher_hits = plan_ck.isin(issued_ck) | plan_fc.isin(issued_ck) | plan_fc.isin(
            issued_internal
        )
        return cipher_hits.fillna(False)
    except Exception:
        return mask


def _seed_session(vid: int) -> None:
    import streamlit as st  # type: ignore

    ss = st.session_state
    ss["rd_plan_data"] = load_version_df(vid, "rd_plan")
    ss["tessa_data"] = load_version_df(vid, "tessa")
    ss["tessa_tasks_data"] = load_version_df(vid, "tessa_tasks")
    try:
        ss["debit_credit_data"] = load_version_df(vid, "debit_credit")
    except Exception:
        ss["debit_credit_data"] = pd.DataFrame()


def _parse_multi(raw: str | None, *, all_token: str = "Все") -> list[str] | None:
    if raw is None or not str(raw).strip():
        return None
    parts = [p.strip() for p in str(raw).split("|") if p.strip()]
    if not parts or (len(parts) == 1 and parts[0] == all_token):
        return None
    if all_token in parts and len(parts) == 1:
        return None
    return parts


def _iso(ts: Any) -> str | None:
    t = pd.to_datetime(ts, errors="coerce")
    if pd.isna(t):
        return None
    return pd.Timestamp(t).strftime("%Y-%m-%d")


def _cell(val: Any) -> str:
    if val is None:
        return ""
    try:
        if pd.isna(val):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(val, (pd.Timestamp,)):
        return val.strftime("%d.%m.%Y")
    s = str(val).strip()
    if not s or s.casefold() in _BLANK:
        return ""
    return s


def _month_label(period: Any) -> str:
    try:
        m = int(period.month)
        y = int(period.year)
        return f"{_MONTH_RU[m]} {y}"
    except Exception:
        return str(period)


def _axis_label(ts: pd.Timestamp) -> str:
    return f"{_MONTH_RU[int(ts.month)][:3]} {ts.year}"


def _detail_to_rows(df: pd.DataFrame) -> tuple[list[dict[str, Any]], list[str]]:
    if df is None or getattr(df, "empty", True):
        return [], []
    cols = [str(c) for c in df.columns.tolist()]
    rows: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        item: dict[str, Any] = {}
        for c in cols:
            v = r.get(c)
            is_dev = "отклонен" in c.casefold() or c.casefold().startswith("отклонение")
            if is_dev:
                if isinstance(v, str):
                    raw = v.strip().replace("\u2212", "-").replace(",", ".")
                    num = pd.to_numeric(raw, errors="coerce")
                else:
                    num = pd.to_numeric(v, errors="coerce")
                if pd.isna(num):
                    item[c] = None
                    item[f"{c}__label"] = "—"
                else:
                    n = int(round(float(num)))
                    item[c] = n
                    item[f"{c}__label"] = f"{n:+d}" if n != 0 else "0"
            else:
                item[c] = _cell(v)
        rows.append(item)
    return rows, cols


def _forecast_date_series(plan_df: pd.DataFrame) -> pd.Series:
    """«Прогнозная дата выдачи» из plan_df (_fact_dt после CSV pick или имя колонки)."""
    if plan_df is None or plan_df.empty:
        return pd.Series(dtype="datetime64[ns]")
    if "_forecast_dyn_dt" in plan_df.columns:
        s = pd.to_datetime(plan_df["_forecast_dyn_dt"], errors="coerce")
        if s.notna().any():
            return s
    if "_fact_dt" in plan_df.columns:
        s = pd.to_datetime(plan_df["_fact_dt"], errors="coerce")
        if s.notna().any():
            return s
    for col in (
        "Прогнозная дата выдачи разделов",
        "Прогнозная дата выдачи",
        "Прогнозная дата",
    ):
        if col in plan_df.columns:
            s = pd.to_datetime(
                plan_df[col], errors="coerce", dayfirst=True, format="mixed"
            )
            if s.notna().any():
                return s
    return pd.Series(pd.NaT, index=plan_df.index)


def _forecast_month_increments(
    plan_df: pd.DataFrame, *, junction: pd.Timestamp
) -> dict[pd.Timestamp, float]:
    """Не выданные разделы → прирост прогноза по месяцу «Прогнозной даты выдачи».

    Факт выдачи — `_tessa_production_dt`. Нет прогнозной даты — fallback на `_plan_dt`
    (иначе линия прогноза не строится при пустых датах CSV).
    """
    if plan_df is None or plan_df.empty:
        return {}
    df = plan_df
    if "_tessa_production_dt" in df.columns:
        issued = pd.to_datetime(df["_tessa_production_dt"], errors="coerce")
    else:
        issued = pd.Series(pd.NaT, index=df.index)
    fcst = _forecast_date_series(df)
    rem = issued.isna()
    if not rem.any():
        return {}
    use_dt = fcst.where(fcst.notna(), pd.to_datetime(df.get("_plan_dt"), errors="coerce"))
    rem = rem & use_dt.notna()
    if not rem.any():
        return {}
    jn = pd.Timestamp(junction).to_period("M").to_timestamp()
    months = use_dt.loc[rem].dt.to_period("M").dt.to_timestamp()
    months = months.where(months >= jn, jn)
    return {pd.Timestamp(k): float(v) for k, v in months.value_counts().items()}


def _attach_forecast_from_fact(
    dynamics: list[dict[str, Any]],
    plan_df: pd.DataFrame,
    *,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Прогноз: начало = точка факта на сегодня; далее — по «Прогнозной дате выдачи»."""
    if not dynamics:
        return dynamics
    today = today or date.today()
    junction = pd.Timestamp(today).to_period("M").to_timestamp().normalize()
    fact_at_j = 0.0
    last_period = None
    for row in dynamics:
        try:
            d = pd.Timestamp(str(row["period"])[:10]).normalize()
        except Exception:
            continue
        last_period = d
        if d <= junction:
            fact_at_j = float(row.get("fact") or 0.0)

    increments = _forecast_month_increments(plan_df, junction=junction)
    by_period: dict[str, dict[str, Any]] = {
        str(r["period"])[:10]: dict(r) for r in dynamics
    }
    jkey = junction.strftime("%Y-%m-%d")
    if jkey not in by_period:
        left: dict[str, Any] | None = None
        for row in dynamics:
            try:
                d = pd.Timestamp(str(row["period"])[:10]).normalize()
            except Exception:
                continue
            if d <= junction:
                left = dict(row)
        seed = left or {
            "period": jkey,
            "period_label": _axis_label(junction),
            "plan": 0.0,
            "fact": fact_at_j,
        }
        by_period[jkey] = {
            **seed,
            "period": jkey,
            "period_label": _axis_label(junction),
            "fact": fact_at_j,
        }
    for m in increments:
        k = pd.Timestamp(m).strftime("%Y-%m-%d")
        if k not in by_period:
            by_period[k] = {
                "period": k,
                "period_label": _axis_label(pd.Timestamp(m)),
                "plan": None,
                "fact": fact_at_j,
            }

    # Всегда нужна хотя бы одна точка после стыка — иначе «Прогноз» = одна точка на факте.
    need_tail = True
    if increments and any(pd.Timestamp(m) > junction for m in increments):
        need_tail = False
    if need_tail:
        nxt = (junction + pd.DateOffset(months=1)).to_period("M").to_timestamp()
        if last_period is not None and last_period > junction:
            nxt = max(nxt, last_period)
        nk = nxt.strftime("%Y-%m-%d")
        if nk not in by_period:
            by_period[nk] = {
                "period": nk,
                "period_label": _axis_label(nxt),
                "plan": None,
                "fact": fact_at_j,
            }

    ordered = sorted(by_period.values(), key=lambda r: str(r["period"])[:10])
    last_p = 0.0
    for r in ordered:
        if r.get("plan") is not None:
            last_p = float(r["plan"] or 0.0)
        r["plan"] = last_p
        d = pd.Timestamp(str(r["period"])[:10]).normalize()
        if d < junction:
            r["forecast"] = None
            continue
        if d == junction:
            r["fact"] = float(round(fact_at_j))
            r["forecast"] = float(round(fact_at_j))
            continue
        cum_inc = sum(float(v) for m, v in increments.items() if pd.Timestamp(m) <= d)
        capped = fact_at_j + cum_inc
        if last_p > 0:
            capped = min(capped, last_p)
        r["forecast"] = float(round(capped))
        r["fact"] = float(round(fact_at_j))
    return ordered


def _build_dynamics(plan_df: pd.DataFrame, mod: ModuleType) -> list[dict[str, Any]]:
    del mod
    if plan_df is None or plan_df.empty or "_plan_dt" not in plan_df.columns:
        return []
    df = plan_df.copy()
    if "_tessa_production_dt" in df.columns:
        df["_fact_dyn_dt"] = pd.to_datetime(df["_tessa_production_dt"], errors="coerce")
    else:
        # Без TESSA не подменяем факт прогнозной датой (_fact_dt) — иначе факт=прогноз.
        df["_fact_dyn_dt"] = pd.NaT
    parts: list[pd.DataFrame] = []
    pm = df["_plan_dt"].notna()
    if pm.any():
        gp = df.loc[pm].copy()
        gp["_dn"] = gp["_plan_dt"].dt.to_period("M").dt.to_timestamp()
        pg = gp.groupby("_dn").size().reset_index(name="Количество")
        pg.columns = ["Дата", "Количество"]
        pg["Тип"] = "План"
        parts.append(pg)
    fm = df["_fact_dyn_dt"].notna()
    if fm.any():
        gf = df.loc[fm].copy()
        gf["_dn"] = gf["_fact_dyn_dt"].dt.to_period("M").dt.to_timestamp()
        fg = gf.groupby("_dn").size().reset_index(name="Количество")
        fg.columns = ["Дата", "Количество"]
        fg["Тип"] = "Факт"
        parts.append(fg)
    if not parts:
        return []
    dynamics_df = pd.concat(parts, ignore_index=True)
    all_dates = pd.to_datetime(dynamics_df["Дата"], errors="coerce").dropna()
    if all_dates.empty:
        return []
    start_anchor = (all_dates.min() - pd.Timedelta(days=1)).normalize()
    dynamics_df = pd.concat(
        [
            pd.DataFrame(
                {
                    "Дата": [start_anchor, start_anchor],
                    "Количество": [0.0, 0.0],
                    "Тип": ["План", "Факт"],
                }
            ),
            dynamics_df,
        ],
        ignore_index=True,
    )
    dynamics_df = dynamics_df.sort_values(["Тип", "Дата"])
    pt_cap = float(len(df)) if len(df) > 0 else 0.0
    for typ in dynamics_df["Тип"].unique():
        mk = dynamics_df["Тип"] == typ
        dynamics_df.loc[mk, "Количество"] = dynamics_df.loc[mk, "Количество"].cumsum()
    if pt_cap > 0:
        pl_m = dynamics_df["Тип"] == "План"
        dynamics_df.loc[pl_m, "Количество"] = dynamics_df.loc[pl_m, "Количество"].clip(
            upper=pt_cap
        )
        if pl_m.any():
            cur = float(dynamics_df.loc[pl_m, "Количество"].max())
            if cur + 0.5 < pt_cap:
                pidx = pd.to_datetime(dynamics_df.loc[pl_m, "Дата"], errors="coerce").idxmax()
                dynamics_df.loc[pidx, "Количество"] = pt_cap

    plan_map = {
        pd.Timestamp(r["Дата"]).normalize(): float(r["Количество"])
        for _, r in dynamics_df[dynamics_df["Тип"] == "План"].iterrows()
    }
    fact_map = {
        pd.Timestamp(r["Дата"]).normalize(): float(r["Количество"])
        for _, r in dynamics_df[dynamics_df["Тип"] == "Факт"].iterrows()
    }
    all_x = sorted(set(plan_map) | set(fact_map))
    out: list[dict[str, Any]] = []
    last_p = last_f = 0.0
    for d in all_x:
        if d in plan_map:
            last_p = plan_map[d]
        if d in fact_map:
            last_f = fact_map[d]
        out.append(
            {
                "period": d.strftime("%Y-%m-%d"),
                "period_label": _axis_label(d),
                "plan": last_p,
                "fact": last_f,
                "forecast": None,
            }
        )
    return out


def _align_dynamics_fact_to_kpi(
    dynamics: list[dict[str, Any]],
    *,
    fact_kpi: float,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Кривая «Факт» на графике = KPI «Факт на текущую дату» (статусы TESSA).

    Иначе даты выдачи в plan_df завышают накопленный факт относительно pie/KPI.
    """
    if not dynamics:
        return dynamics
    today = today or date.today()
    target = max(0.0, float(fact_kpi or 0.0))
    curve_today = 0.0
    for row in dynamics:
        try:
            d = date.fromisoformat(str(row["period"])[:10])
        except ValueError:
            continue
        if d <= today:
            curve_today = float(row.get("fact") or 0.0)
    if target <= 0 or curve_today <= 0:
        return dynamics
    scale = target / curve_today
    out: list[dict[str, Any]] = []
    for row in dynamics:
        r = dict(row)
        try:
            d = date.fromisoformat(str(row["period"])[:10])
        except ValueError:
            out.append(r)
            continue
        fact_v = float(row.get("fact") or 0.0) * scale
        if d <= today:
            fact_v = min(fact_v, target)
        else:
            # После «сегодня» кривая не уезжает выше KPI.
            fact_v = target
        r["fact"] = round(fact_v, 1)
        out.append(r)
    # Точка «на сегодня» ровно равна KPI.
    for i in range(len(out) - 1, -1, -1):
        try:
            d = date.fromisoformat(str(out[i]["period"])[:10])
        except ValueError:
            continue
        if d <= today:
            out[i]["fact"] = float(round(target))
            break
    return out


def _exec_kpis(
    mod: ModuleType,
    plan_df: pd.DataFrame,
    dynamics: list[dict[str, Any]],
    selected_projects: list[str] | None,
    total_sections: int,
    *,
    status_filtered: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    today = date.today()
    pt = float(total_sections)
    pd_fb = 0.0
    fd_fb = 0.0
    if dynamics:
        for row in dynamics:
            d = date.fromisoformat(row["period"])
            if d <= today:
                pd_fb = float(row["plan"])
                fd_fb = float(row["fact"])
    rd_summ = None
    if not status_filtered:
        try:
            rd_summ = mod._compute_rd_exec_summary_from_csv_tessa(selected_projects)
        except Exception:
            rd_summ = None
    try:
        pd_fb, fd_fb, _dev_plan_minus_fact = mod._rd_kpi_plan_fact_deviation_today(
            today=today,
            csv_df=plan_df,
            plan_curve=pd_fb,
            fact_curve=fd_fb,
            rd_summ=rd_summ,
        )
    except Exception:
        pass
    if not status_filtered:
        try:
            tz = mod._count_rd_pie_tz(selected_projects)
            fd_tessa = float(
                int(tz.get(mod._RD_TESSA_STATUS_PRODUCTION, 0))
                + int(tz.get(mod._RD_TESSA_STATUS_REVIEW, 0))
            )
            if fd_tessa > 0:
                fd_fb = fd_tessa
        except Exception:
            pass

    # Как у пользователя и на ПД: факт − план; отставание — отрицательное.
    dev_fb = float(fd_fb - pd_fb)
    dynamics = _align_dynamics_fact_to_kpi(dynamics, fact_kpi=fd_fb, today=today)

    planned_weekly = fact_weekly = nec_weekly = None
    if rd_summ:
        planned_weekly = rd_summ.get("planned_weekly")
        fact_weekly = rd_summ.get("fact_weekly")
        nec_weekly = rd_summ.get("nec_weekly")
        if planned_weekly is None or fact_weekly is None:
            max_plan = plan_df["_plan_dt"].max().date() if plan_df["_plan_dt"].notna().any() else None
            max_fact = None
            if "_tessa_production_dt" in plan_df.columns and plan_df["_tessa_production_dt"].notna().any():
                max_fact = plan_df["_tessa_production_dt"].max().date()
            min_plan = plan_df["_plan_dt"].min().date() if plan_df["_plan_dt"].notna().any() else None
            pw, fw = mod._rd_weekly_from_curve_endpoints(
                float(pd_fb),
                float(fd_fb),
                max_plan,
                max_fact,
                today=today,
                min_plan_start=min_plan,
                plan_total=pt,
            )
            if planned_weekly is None:
                planned_weekly = pw
            if fact_weekly is None:
                fact_weekly = fw
        if nec_weekly is None and float(dev_fb) != 0:
            ref = mod._rd_nec_weekly_ref_date(rd_summ, today)
            # Нужна производительность по величине отставания (план − факт).
            lag = float(pd_fb - fd_fb)
            if ref is not None:
                dd = (ref - today).days
                nec_weekly = float(lag) / float(dd) * 7.0 if dd > 0 else float(lag) / 7.0
            else:
                nec_weekly = float(lag) / 7.0

    kpis = {
        "plan_total": int(round(pt)),
        "plan_to_date": int(round(float(pd_fb))),
        "fact_to_date": int(round(float(fd_fb))),
        "deviation_to_date": int(round(float(dev_fb))),
        "planned_weekly": float(planned_weekly) if planned_weekly is not None else None,
        "fact_weekly": float(fact_weekly) if fact_weekly is not None else None,
        "nec_weekly": float(nec_weekly) if nec_weekly is not None else None,
    }
    return kpis, dynamics


def _month_end(period: pd.Period, today: pd.Timestamp | None = None) -> pd.Timestamp:
    today = today if today is not None else pd.Timestamp.today().normalize()
    return min(pd.Timestamp(period.end_time).normalize(), today)


def _delta_fact_minus_plan_as_of(
    dynamics: list[dict[str, Any]],
    as_of: date | pd.Timestamp,
) -> float | None:
    """Факт − план на дату (как KPI / кривая «Динамика выдачи РД»)."""
    if not dynamics:
        return None
    if isinstance(as_of, pd.Timestamp):
        as_of_d = as_of.date()
    else:
        as_of_d = as_of
    last_p = last_f = None
    for row in dynamics:
        try:
            d = date.fromisoformat(str(row.get("period") or "")[:10])
        except ValueError:
            continue
        if d <= as_of_d:
            last_p = float(row.get("plan") or 0.0)
            last_f = float(row.get("fact") or 0.0)
    if last_p is None or last_f is None:
        return None
    return float(last_f - last_p)


def _align_monthly_delta_to_kpi(
    monthly_rows: list[dict[str, Any]],
    dynamics: list[dict[str, Any]],
    *,
    deviation_to_date: float,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Подписи справа на стеке = то же «факт − план», что KPI отклонения.

    У самого свежего месяца в выборке — ровно KPI ``deviation_to_date``.
    """
    if not monthly_rows:
        return monthly_rows
    today = today or date.today()
    parsed: list[tuple[dict[str, Any], pd.Period | None]] = []
    for row in monthly_rows:
        try:
            p = pd.Period(str(row.get("month") or ""), freq="M")
        except Exception:
            p = None
        parsed.append((dict(row), p))
    newest = max((p for _, p in parsed if p is not None), default=None)
    out: list[dict[str, Any]] = []
    for r, p in parsed:
        if p is None:
            out.append(r)
            continue
        if newest is not None and p == newest:
            r["delta"] = float(round(float(deviation_to_date)))
        else:
            as_of = _month_end(p, pd.Timestamp(today))
            dlt = _delta_fact_minus_plan_as_of(dynamics, as_of.date())
            if dlt is not None:
                r["delta"] = float(round(dlt))
            else:
                # fallback: не оставляем старый −overdue
                r["delta"] = float(round(float(r.get("delta") or 0)))
        out.append(r)
    return out


def build_working_documentation_payload(
    *,
    project: str | None = None,
    section: str | None = None,
    status: str | None = None,
    period_mode: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    metric_mode: str | None = None,
    show_forecast: bool | str | None = True,
    view_mode: str | None = None,
    tab: str | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    show_fc = True
    if isinstance(show_forecast, str):
        show_fc = show_forecast.strip().lower() not in ("0", "false", "no", "off")
    elif show_forecast is not None:
        show_fc = bool(show_forecast)

    metric = metric_mode if metric_mode in ("Количество разделов", "% от общего объёма") else "Количество разделов"
    period = period_mode or "Весь период (за всё время)"
    view = "section" if str(view_mode or "").casefold() in {"section", "по разделу"} else "project"
    tab_id = "delay" if str(tab or "").casefold() == "delay" else "main"

    sel_projects = _parse_multi(project)
    if project is not None and str(project).strip() in ("__no_access__", "__none__"):
        sel_projects = ["__no_access__"]
    sel_sections = _parse_multi(section)
    sel_statuses = _parse_multi(status, all_token="")

    cache_key = "|".join(
        [
            "v24-rd-not-issued-residual",
            str(sel_projects),
            str(sel_sections),
            str(sel_statuses),
            period,
            str(date_from),
            str(date_to),
            metric,
            str(show_fc),
            view,
            tab_id,
        ]
    )
    cached = cache_get("working-documentation", cache_key, max_age_sec=1800)
    if cached is not None:
        return cached

    if not WEB_DB_PATH.is_file():
        return _empty_payload(error="web_data.db нет — выполните POST /api/admin/ingest (или sync).")

    try:
        prepare_web_db()
        import web_schema  # type: ignore

        vid = web_schema.get_active_version_id()
        if not vid:
            return _empty_payload(error="Нет active version_id в web_data.db")

        _seed_session(int(vid))
        mod = _load_rd_renderers()
        # Гарантируем EXTRA paths + сброс st.cache_data lookup на каждый build
        # (иначе первый cold-start без EXTRA кэширует пустой dict → KPI 504).
        _ensure_showcase_web_in_extra_paths()
        try:
            _lk = getattr(mod, "_r23_12_load_rd_plan_lookup", None)
            _clear = getattr(_lk, "clear", None)
            if callable(_clear):
                _clear()
        except Exception:
            pass

        rd_raw = load_version_df(int(vid), "rd_plan")
        if rd_raw is None or getattr(rd_raw, "empty", True):
            return _empty_payload(error="Нет rd_plan в активной версии")

        plan_all = mod._rd_plan_csv_sections_df(None)
        if plan_all is None or plan_all.empty:
            return _empty_payload(error="Нет разделов РД после очистки плана")

        pc = mod._rd_plan_csv_pick_columns(plan_all)
        proj_col = pc.get("proj")
        code_col = pc.get("code")
        name_col = pc.get("name")

        projects = ["Все"]
        if proj_col and proj_col in plan_all.columns:
            projects += sorted(
                {
                    str(x).strip()
                    for x in plan_all[proj_col].dropna().tolist()
                    if str(x).strip() and str(x).strip().casefold() not in _BLANK
                },
                key=str.casefold,
            )

        applied_projects = sel_projects
        if applied_projects:
            if applied_projects == ["__no_access__"]:
                out = _empty_payload(error="Нет доступных проектов")
                out["filters"]["projects"] = projects
                return out
            applied_projects = [p for p in applied_projects if p in projects]
            if not applied_projects:
                applied_projects = None

        plan_df = mod._rd_plan_csv_sections_df(applied_projects)
        if plan_df.empty:
            out = _empty_payload(error="Нет строк после фильтра проектов")
            out["filters"]["projects"] = projects
            return out

        try:
            plan_df = mod._augment_df_with_tessa_rd(plan_df, proj_col, code_col)
        except Exception:
            pass

        nm_s = (
            plan_df[name_col].fillna("").astype(str).str.strip()
            if name_col and name_col in plan_df.columns
            else pd.Series("", index=plan_df.index)
        )
        cd_s = (
            plan_df[code_col].fillna("").astype(str).str.strip()
            if code_col and code_col in plan_df.columns
            else pd.Series("", index=plan_df.index)
        )
        nm_s = nm_s.where(~nm_s.str.lower().isin({"nan", "none"}), "")
        cd_s = cd_s.where(~cd_s.str.lower().isin({"nan", "none", "-", "—"}), "")
        sec_lbl = (cd_s + " " + nm_s).str.replace(r"\s+", " ", regex=True).str.strip()
        sec_lbl = sec_lbl.mask(sec_lbl.eq(""), "(не указано)")
        section_opts = sorted({str(v).strip() for v in sec_lbl.tolist() if str(v).strip()}, key=str.casefold)

        detail_tbl = mod._build_rd_work_doc_detail_table(
            selected_projects=applied_projects,
            selected_section=None,
        )

        status_opts: list[str] = []
        if not detail_tbl.empty and "Статус" in detail_tbl.columns:
            status_opts = sorted(
                {
                    str(v).strip()
                    for v in detail_tbl["Статус"].dropna().tolist()
                    if str(v).strip() and str(v).strip().casefold() not in _BLANK
                    and not mod._rd_status_is_excluded(v)
                },
                key=str.casefold,
            )
        not_issued = getattr(mod, "_RD_TESSA_STATUS_NOT_ISSUED", "Не выдано")
        if not_issued not in status_opts:
            status_opts = sorted(status_opts + [not_issued], key=str.casefold)

        if sel_sections and set(sel_sections) != set(section_opts):
            allow = {str(x).strip() for x in sel_sections}
            plan_df = plan_df.loc[sec_lbl.isin(allow)].copy()
            sec_lbl = sec_lbl.reindex(plan_df.index)
            if not detail_tbl.empty:
                lbl_d = (
                    detail_tbl["Шифр"].fillna("").astype(str).str.strip()
                    + " "
                    + detail_tbl["Наименование разделов работ"].fillna("").astype(str).str.strip()
                ).str.replace(r"\s+", " ", regex=True).str.strip()
                detail_tbl = detail_tbl.loc[lbl_d.isin(allow)].reset_index(drop=True)

        if period != "Весь период (за всё время)" and date_from and date_to:
            try:
                d0 = date.fromisoformat(date_from[:10])
                d1 = date.fromisoformat(date_to[:10])
                pn = plan_df["_plan_dt"].dt.normalize().dt.date
                plan_df = plan_df[plan_df["_plan_dt"].notna() & (pn >= d0) & (pn <= d1)].copy()
                if not detail_tbl.empty and "Дата выдачи разделов по Договору" in detail_tbl.columns:
                    dts = detail_tbl["Дата выдачи разделов по Договору"].map(mod._rd_parse_chart_date_cell)
                    detail_tbl = detail_tbl.loc[
                        dts.notna()
                        & (dts.dt.normalize().dt.date >= d0)
                        & (dts.dt.normalize().dt.date <= d1)
                    ].reset_index(drop=True)
            except Exception:
                pass

        plan_n_before_status = int(len(plan_df))
        tz_counts: dict[str, int] = {}
        try:
            tz_counts = {
                str(k): int(v) for k, v in (mod._count_rd_pie_tz(applied_projects) or {}).items()
            }
        except Exception:
            tz_counts = {}
        status_filtered = bool(
            sel_statuses and status_opts and set(sel_statuses) != set(status_opts)
        )
        if status_filtered and not detail_tbl.empty and "Статус" in detail_tbl.columns:
            # ГИП / доработка — карточки TESSA, не рыхлый джойн с планом.
            keys = _tessa_status_keys(mod)
            if not _sel_is_not_issued_only(sel_statuses, mod) and (
                _sel_has_status(sel_statuses, keys["review"], mod)
                or _sel_has_status(sel_statuses, keys["rework"], mod)
            ):
                try:
                    tessa_only = mod._build_tessa_rd_detail_table(
                        selected_projects=applied_projects
                    )
                    if tessa_only is not None and not tessa_only.empty and "Статус" in tessa_only.columns:
                        tessa_hit = tessa_only.loc[
                            _detail_status_mask(tessa_only, sel_statuses, mod)
                        ].copy()
                        if not tessa_hit.empty:
                            detail_tbl = tessa_hit
                except Exception:
                    pass
            if "Статус" in detail_tbl.columns:
                detail_tbl = detail_tbl.loc[
                    _detail_status_mask(detail_tbl, sel_statuses, mod)
                ].copy()
            plan_df = mod._rd_plan_df_filter_by_detail(
                plan_df,
                detail_tbl,
                proj_col,
                code_col,
                name_col,
                pc.get("full_cipher"),
            )
            if _sel_is_not_issued_only(sel_statuses, mod):
                ni_n = _not_issued_residual(
                    plan_n_before_status, tz_counts, _tessa_status_keys(mod)
                )
                detail_tbl = _align_detail_to_not_issued_n(detail_tbl, ni_n, mod)
                plan_df = mod._rd_plan_df_filter_by_detail(
                    plan_df,
                    detail_tbl,
                    proj_col,
                    code_col,
                    name_col,
                    pc.get("full_cipher"),
                )
        elif not detail_tbl.empty:
            detail_tbl = mod._rd_plan_detail_filter_by_plan(
                plan_df,
                detail_tbl,
                proj_col,
                code_col,
                name_col,
                pc.get("full_cipher"),
            )

        if status_filtered and not detail_tbl.empty:
            total_sections = int(len(detail_tbl))
        else:
            total_sections = int(len(plan_df))
        if not detail_tbl.empty:
            overdue, avg_delay = mod._rd_delay_section_overdue_kpis(detail_tbl)
        else:
            overdue, avg_delay = 0, 0.0

        # Pie
        pie_counts: dict[str, int] = {}
        if status_filtered and not detail_tbl.empty:
            pie_counts = {
                k: int(v)
                for k, v in _status_counts_from_detail(detail_tbl, mod).items()
                if int(v) > 0
            }
        else:
            tz_sum = sum(int(v) for v in tz_counts.values())
            if tz_sum > 0:
                total_units = total_sections if total_sections > 0 else 1
                capped = dict(tz_counts)
                if tz_sum > total_units > 0:
                    sc = float(total_units) / float(tz_sum)
                    capped = {k: max(int(round(float(v) * sc)), 0) for k, v in tz_counts.items()}
                not_iss = max(total_units - sum(int(v) for v in capped.values()), 0)
                pie_counts = {k: int(v) for k, v in capped.items() if int(v) > 0}
                if not_iss > 0:
                    pie_counts[not_issued] = not_iss

        status_mix = [
            {"name": k, "value": v, "color": _PIE_COLORS.get(k, "#7F8C8D")}
            for k, v in pie_counts.items()
            if v > 0
        ]

        keys = _tessa_status_keys(mod)
        _prod_key = keys["production"]
        issued_production = int(pie_counts.get(_prod_key, 0) or 0)
        if issued_production <= 0 and pie_counts:
            for _k, _v in pie_counts.items():
                if "производств" in str(_k).casefold():
                    issued_production = int(_v)
                    break
        not_issued_kpi = max(0, int(total_sections) - int(issued_production))

        # Срез «не выдано»: ГИП и доработка тоже не выданы → выдано всегда 0,
        # всего = не выдано = число документов среза (TESSA для ГИП/доработки).
        if status_filtered and _sel_is_not_issued_family(sel_statuses, mod):
            n = int(total_sections)
            if _sel_has_status(sel_statuses, keys["review"], mod) and not _sel_is_not_issued_only(
                sel_statuses, mod
            ):
                tz_n = int(tz_counts.get(keys["review"], 0) or 0)
                if tz_n > 0:
                    n = tz_n
            elif _sel_has_status(sel_statuses, keys["rework"], mod) and not _sel_is_not_issued_only(
                sel_statuses, mod
            ):
                tz_n = int(tz_counts.get(keys["rework"], 0) or 0)
                if tz_n > 0:
                    n = tz_n
            elif _sel_is_not_issued_only(sel_statuses, mod):
                n = _not_issued_residual(plan_n_before_status, tz_counts, keys)
            total_sections = n
            issued_production = 0
            not_issued_kpi = n
            if _sel_is_not_issued_only(sel_statuses, mod):
                pie_counts = _pie_for_not_issued_residual(n, tz_counts, keys, not_issued)
            else:
                pie_counts = {
                    k: v
                    for k, v in (pie_counts or {not_issued: n}).items()
                    if "производств" not in str(k).casefold()
                }
            if not pie_counts and n > 0:
                pie_counts = {not_issued: n}
            status_mix = [
                {"name": k, "value": v, "color": _PIE_COLORS.get(k, "#7F8C8D")}
                for k, v in pie_counts.items()
                if v > 0
            ]

        # Monthly bars — накопительный стек на конец каждого месяца (как ТЗ / скрин):
        # зелёный = «Выдано в производство» к as_of;
        # красный = не выдано и срок договора уже наступил (plan_date ≤ as_of);
        # жёлтый = не выдано и срок ещё впереди (plan_date > as_of).
        # Подпись delta = выдано − план_к_дате (= early − overdue): ≥0 зелёный, <0 красный.
        monthly_rows: list[dict[str, Any]] = []
        monthly_exc: str | None = None
        monthly_issued_n = 0
        try:
            month_df = plan_df[plan_df["_plan_dt"].notna()].copy()
            month_df["_rd_plan_n"] = 1.0
            month_df["_plan_end_dt"] = pd.to_datetime(month_df["_plan_dt"], errors="coerce")

            # Факт: дата TESSA, иначе статус «выдано» (на prod даты tasks часто пустые —
            # без этого стек рисует жёлтый план и fact=0, хотя KPI/пирог уже 319).
            if "_tessa_production_dt" in month_df.columns:
                _fact_dt = pd.to_datetime(month_df["_tessa_production_dt"], errors="coerce")
            elif "_fact_dt" in month_df.columns:
                _fact_dt = pd.to_datetime(month_df["_fact_dt"], errors="coerce")
            else:
                _fact_dt = pd.Series(pd.NaT, index=month_df.index)

            issued_mask = pd.Series(False, index=month_df.index)
            try:
                _prod_mask = mod._rd_in_production_mask(month_df)
                if isinstance(_prod_mask, pd.Series):
                    issued_mask = issued_mask | _prod_mask.reindex(month_df.index).fillna(False)
            except Exception:
                pass
            if "_tessa_status" in month_df.columns:
                _canon = getattr(mod, "_rd_canonical_tessa_rd_status", None)
                _prod = getattr(
                    mod, "_RD_TESSA_STATUS_PRODUCTION", "Выдано в производство работ"
                )
                if callable(_canon):
                    issued_mask = issued_mask | month_df["_tessa_status"].map(
                        lambda x: _canon(x) == _prod
                    ).fillna(False)
                else:
                    issued_mask = issued_mask | month_df["_tessa_status"].astype(
                        str
                    ).str.contains("производств", case=False, na=False)
            issued_mask = issued_mask | _issued_mask_from_tessa_status(
                mod,
                month_df,
                proj_col,
                code_col,
                full_cipher_col=pc.get("full_cipher"),
            )
            if "_tessa_kr_state" in month_df.columns:
                _kr = month_df["_tessa_kr_state"].astype(str)
                issued_mask = issued_mask | _kr.str.contains("производств", case=False, na=False)
            if not detail_tbl.empty and "Статус" in detail_tbl.columns:
                try:
                    month_df["_bucket"] = mod._rd_plan_map_buckets_from_detail(
                        month_df,
                        detail_tbl,
                        proj_col=proj_col,
                        code_col=code_col,
                        name_col=name_col,
                        full_cipher_col=pc.get("full_cipher"),
                    )
                    issued_mask = issued_mask | month_df["_bucket"].astype(str).str.strip().eq(
                        "Выдано в производство работ"
                    ) | month_df["_bucket"].isin(["Принято", "Передано подрядчику"])
                except Exception:
                    pass
            monthly_issued_n = int(issued_mask.fillna(False).sum())
            if issued_mask.any():
                _fact_dt = _fact_dt.where(
                    _fact_dt.notna(),
                    month_df["_plan_end_dt"].where(issued_mask),
                )

            _plan_n = month_df["_plan_end_dt"].dt.normalize()
            _fact_n = _fact_dt.dt.normalize()
            _w = _plan_n.notna()
            _plan_w = _plan_n[_w]
            _fact_w = _fact_n[_w]
            _weights = pd.to_numeric(month_df.loc[_w, "_rd_plan_n"], errors="coerce").fillna(1.0)
            total_plan = float(_weights.sum())
            use_pct = str(metric).strip().startswith("%")
            periods = sorted({p for p in _plan_w.dt.to_period("M").tolist() if p is not pd.NaT})
            _today = pd.Timestamp.today().normalize()
            cur_m = pd.Period(_today, freq="M")
            periods = [p for p in periods if p <= cur_m]
            rows_m: list[dict[str, Any]] = []
            prev_green = 0.0
            for p in periods:
                as_of = min(pd.Timestamp(p.end_time).normalize(), _today)
                issued = _fact_w.notna() & (_fact_w <= as_of)
                due = _plan_w <= as_of
                future = _plan_w > as_of
                done_v = float(_weights[issued].sum())
                overdue_v = float(_weights[(~issued) & due].sum())
                rest_v = float(_weights[(~issued) & future].sum())
                # Страховка от округления: сегменты покрывают весь план.
                covered = done_v + overdue_v + rest_v
                if abs(covered - total_plan) > 0.05 and total_plan > 0:
                    rest_v = max(0.0, total_plan - done_v - overdue_v)
                plan_due = done_v + overdue_v
                delta_v = done_v - plan_due  # = −overdue + early-issued-from-future
                # early: issued & future plan → в done, не в plan_due
                # equivalent: done_v - (total_plan - rest_v) = done_v - plan_due
                fact_inc = max(0.0, done_v - prev_green)
                prev_green = done_v
                # План на дату месяца (накопительно): due = выдано + ещё не выдано, но уже должно.
                plan_as_of = done_v + overdue_v
                if use_pct and total_plan > 0:
                    rows_m.append(
                        {
                            "month": str(p),
                            "month_label": _month_label(p),
                            "plan": round(plan_as_of / total_plan * 100, 1),
                            "done": round(done_v / total_plan * 100, 1),
                            "overdue": round(overdue_v / total_plan * 100, 1),
                            "rest": round(rest_v / total_plan * 100, 1),
                            "fact": round(done_v / total_plan * 100, 1),
                            "fact_inc": round(fact_inc / total_plan * 100, 1),
                            "delta": round(delta_v / total_plan * 100, 1),
                        }
                    )
                else:
                    rows_m.append(
                        {
                            "month": str(p),
                            "month_label": _month_label(p),
                            "plan": plan_as_of,
                            "done": done_v,
                            "overdue": overdue_v,
                            "rest": rest_v,
                            "fact": done_v,
                            "fact_inc": fact_inc,
                            "delta": delta_v,
                        }
                    )
            monthly_rows = list(reversed(rows_m))
        except Exception as exc:
            monthly_rows = []
            monthly_exc = str(exc)[:200]
        else:
            monthly_exc = None

        dyn_src = (
            _plan_slice_from_detail(detail_tbl, mod)
            if status_filtered and not detail_tbl.empty
            else plan_df
        )
        dynamics = _build_dynamics(dyn_src, mod)
        exec_kpis, dynamics = _exec_kpis(
            mod,
            dyn_src,
            dynamics,
            applied_projects,
            total_sections,
            status_filtered=status_filtered,
        )
        if show_fc:
            dynamics = _attach_forecast_from_fact(
                dynamics, dyn_src, today=date.today()
            )
        else:
            dynamics = [{**r, "forecast": None} for r in dynamics]
        monthly_rows = _align_monthly_delta_to_kpi(
            monthly_rows,
            dynamics,
            deviation_to_date=float(exec_kpis.get("deviation_to_date") or 0),
        )
        # Гарантия: верхний месяц стека = KPI «Отклонение на текущую дату»
        if monthly_rows:
            monthly_rows[0]["delta"] = float(
                round(float(exec_kpis.get("deviation_to_date") or 0))
            )

        detail_show = mod._rd_detail_prepare_for_display(
            detail_tbl.copy() if not detail_tbl.empty else pd.DataFrame(),
            show_forecast=show_fc,
        )
        if not detail_show.empty:
            detail_show = mod._drop_rd_detail_empty_rows(detail_show)
        detail_rows, detail_cols = _detail_to_rows(detail_show)

        # Delay gantt
        gantt_rows: list[dict[str, Any]] = []
        range_start = range_end = None
        try:
            gdf, _y = mod._rd_delay_build_date_rows(
                detail_tbl if not detail_tbl.empty else pd.DataFrame(),
                by_section=(view == "section"),
                ts_report=pd.Timestamp(date.today()),
                show_forecast=show_fc,
            )
            if not gdf.empty:
                label_col = "Раздел" if view == "section" and "Раздел" in gdf.columns else (
                    "Проект" if "Проект" in gdf.columns else gdf.columns[0]
                )
                starts = []
                ends = []
                for _, r in gdf.iterrows():
                    label = _cell(r.get(label_col))
                    if not label or label in {"—", "-", "–", "−"}:
                        continue
                    start = r.get("_start_dt")
                    bf = r.get("_bf_dt")
                    fin = r.get("_fin_dt")
                    delay_end = r.get("_delay_end_dt")
                    starts.append(pd.Timestamp(start))
                    for t in (bf, fin, delay_end):
                        if t is not None and pd.notna(t):
                            ends.append(pd.Timestamp(t))
                    gantt_rows.append(
                        {
                            "label": label,
                            "start": _iso(start),
                            "base_finish": _iso(bf),
                            "finish": _iso(fin),
                            "delay_end": _iso(delay_end),
                            "base_dur": float(r.get("_base_dur") or 0),
                            "fact_dur": float(r.get("_fact_dur") or 0),
                            "delay_dur": float(r.get("_delay_dur") or 0),
                            "late_complete": bool(r.get("_late_complete") or False),
                            "base_label": _cell(r.get("_lbl_yellow")),
                            "fact_label": _cell(r.get("_lbl_green")),
                            "delay_label": _cell(r.get("_lbl_red")),
                        }
                    )
                if starts:
                    range_start = min(starts).strftime("%Y-%m-%d")
                if ends:
                    range_end = max(ends).strftime("%Y-%m-%d")
        except Exception:
            pass

        payload: dict[str, Any] = {
            "meta": {
                "rows": total_sections,
                "source": "web_data.db",
                "data_mode": DATA_MODE,
                "files": 0,
                "doc_kind": "rd",
                "title": "Рабочая документация",
                "rule": "rd_plan+tessa БД; даты договора CSV web/ → DB fallback",
            "parity": "main_working_documentation_rd_plan_tessa",
            "version_id": int(vid),
            "error": None,
            "forecast_line": "v12",
            "monthly_issued_n": monthly_issued_n,
            "monthly_error": monthly_exc,
        },
            "filters": {
                "projects": projects,
                "sections": ["Все"] + section_opts,
                "statuses": status_opts,
                "period_modes": ["Весь период (за всё время)", "Выбор диапазона дат"],
                "metric_modes": ["Количество разделов", "% от общего объёма"],
                "view_modes": [
                    {"id": "project", "label": "По проекту"},
                    {"id": "section", "label": "По разделу"},
                ],
                "plan_date_min": _iso(plan_all["_plan_dt"].min()) if "_plan_dt" in plan_all.columns else None,
                "plan_date_max": _iso(plan_all["_plan_dt"].max()) if "_plan_dt" in plan_all.columns else None,
                "applied": {
                    "projects": applied_projects or ["Все"],
                    "sections": sel_sections or ["Все"],
                    "statuses": sel_statuses or status_opts,
                    "period_mode": period,
                    "date_from": date_from,
                    "date_to": date_to,
                    "metric_mode": metric,
                    "show_forecast": show_fc,
                    "view_mode": view,
                    "tab": tab_id,
                },
            },
            "kpis": {
                # total_sections — без изменений условий (len plan_df после фильтров)
                "total_sections": total_sections,
                "overdue": int(overdue),
                "avg_delay": round(float(avg_delay), 1) if overdue > 0 else 0.0,
                "issued_production": int(issued_production),
                "not_issued": int(not_issued_kpi),
                **exec_kpis,
            },
            "tremor": {
                "status_mix": status_mix,
                "dynamics": dynamics,
                "monthly": monthly_rows,
            },
            "detail_rows": detail_rows,
            "detail_columns": detail_cols,
            "delay": {
                "gantt": {
                    "rows": gantt_rows,
                    "range_start": range_start,
                    "range_end": range_end,
                },
                "detail_rows": detail_rows,
                "detail_columns": detail_cols,
            },
        }
        cache_set("working-documentation", cache_key, payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        return _empty_payload(error=str(exc)[:400])
