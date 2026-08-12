"""Проектная документация — паритет с [main] dashboard_project_documentation, данные из web_data.db."""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from app.config import DATA_MODE, WEB_DB_PATH
from app.services.core_bridge import import_dashboard_module, load_msp_frame, prepare_web_db
from app.services.db_ingest import db_status
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
_GRAN = {
    "day": ("day", 1, 1, "за день"),
    "week": ("week", 7, 7, "за неделю"),
    "month": ("month", 30, 30, "за месяц"),
}


def _normalize(value: Any) -> str:
    text = str(value or "").casefold().replace("_", " ")
    return re.sub(r"\s+", " ", text).strip()


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.casefold() in _BLANK:
        return ""
    return re.sub(r"\s+", " ", text)


def _col(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    cols = {_normalize(c): str(c) for c in frame.columns}
    for name in candidates:
        hit = cols.get(_normalize(name))
        if hit:
            return hit
    for name in candidates:
        nn = _normalize(name)
        for ck, cv in cols.items():
            if nn in ck or ck in nn:
                return cv
    return None


def _fmt_date(value: Any) -> str | None:
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.strftime("%d.%m.%Y")


def _fmt_dev(days: Any) -> str:
    num = pd.to_numeric(days, errors="coerce")
    if pd.isna(num):
        return ""
    n = int(round(float(num)))
    if n == 0:
        return "0"
    return f"{n:+d}"


def _to_dt(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", dayfirst=True, format="mixed")


def _pct_series(df: pd.DataFrame) -> pd.Series:
    col = _col(
        df,
        [
            "pct complete",
            "% complete",
            "процент завершения",
            "процент_завершения",
            "% завершения",
        ],
    )
    if not col or col not in df.columns:
        return pd.Series(0.0, index=df.index)
    raw = (
        df[col]
        .astype(str)
        .str.replace("%", "", regex=False)
        .str.replace(",", ".", regex=False)
        .str.strip()
    )
    pc = pd.to_numeric(raw, errors="coerce").fillna(0.0)
    if pc.gt(0).any() and float(pc.max()) <= 1.0 + 1e-9:
        pc = pc * 100.0
    return pc


def _cipher_mask(df: pd.DataFrame) -> tuple[str | None, pd.Series]:
    cipher_col = _col(
        df,
        [
            "abbreviation",
            "Шифр_ПД_и_РД",
            "Шифр ПД и РД",
            "шифр пд и рд",
            "Шифр ПД РД",
            "Шифр ПД/РД",
            "Шифр",
            "Cipher",
            "DivisionCipher",
        ],
    )
    if not cipher_col or cipher_col not in df.columns:
        return cipher_col, pd.Series(False, index=df.index)
    cs = df[cipher_col].astype(str).str.strip()
    ok = cs.ne("") & ~cs.str.lower().isin(("nan", "none", "-", "—", "null", "<na>"))
    return cipher_col, ok


def _parent_is_pd_stage(parent_name: str) -> bool:
    s = str(parent_name or "").casefold()
    if "этап" not in s or "проектная документация" not in s:
        return False
    if "корректиров" in s or "рабоч" in s:
        return False
    return True


def _immediate_parents(df: pd.DataFrame, level_col: str, name_col: str) -> pd.Series:
    from utils import outline_level_numeric  # type: ignore

    lv = outline_level_numeric(df[level_col])
    nm = df[name_col].map(lambda x: "" if pd.isna(x) else str(x))
    stack: list[tuple[float, str]] = []
    out: list[str] = []
    for i in range(len(df)):
        raw_l = lv.iloc[i]
        n = nm.iloc[i] or ""
        if pd.isna(raw_l):
            out.append("")
            continue
        l = float(raw_l)
        while stack and stack[-1][0] >= l:
            stack.pop()
        out.append(stack[-1][1] if stack else "")
        stack.append((l, n))
    return pd.Series(out, index=df.index)


def _ancestor_under_pd(
    df: pd.DataFrame, level_col: str, name_col: str, block_col: str | None
) -> pd.Series:
    from utils import outline_level_numeric  # type: ignore

    lv = outline_level_numeric(df[level_col])
    nm = df[name_col].map(lambda x: "" if pd.isna(x) else str(x))
    blk = (
        df[block_col].astype(str).str.strip().str.casefold()
        if block_col and block_col in df.columns
        else pd.Series("", index=df.index)
    )
    stack: list[tuple[float, str]] = []
    out: list[bool] = []
    for i in range(len(df)):
        raw_l = lv.iloc[i]
        n = nm.iloc[i] or ""
        if pd.isna(raw_l):
            out.append(False)
            continue
        l = float(raw_l)
        while stack and stack[-1][0] >= l:
            stack.pop()
        ancestors = [s[1] for s in stack]
        is_pd = any("проектная документация" in str(a).casefold() for a in ancestors if a)
        if blk.iloc[i] in ("пд", "пд и рд"):
            is_pd = True
        out.append(is_pd)
        stack.append((l, n))
    return pd.Series(out, index=df.index)


def _hierarchy_cols(df: pd.DataFrame) -> dict[str, str | None]:
    from utils import ensure_msp_hierarchy_columns  # type: ignore

    ensure_msp_hierarchy_columns(df)
    if "block" not in df.columns:
        for c in df.columns:
            if str(c).strip().casefold() in ("блок", "block"):
                df["block"] = df[c]
                break
    return {
        "hier": "level structure" if "level structure" in df.columns else None,
        "level": "level" if "level" in df.columns else None,
        "name": "task name" if "task name" in df.columns else None,
        "block": "block" if "block" in df.columns else None,
    }


def _section_masks(df: pd.DataFrame) -> dict[str, Any]:
    from utils import outline_level_numeric  # type: ignore

    cols = _hierarchy_cols(df)
    cipher_col, cipher_ok = _cipher_mask(df)
    empty = pd.Series(False, index=df.index)
    result: dict[str, Any] = {
        "metrics_mask": empty,
        "dynamics_mask": empty,
        "cipher_col": cipher_col,
        **{f"{k}_col": v for k, v in cols.items()},
        "hier_col": cols["hier"],
        "level_col": cols["level"],
        "name_col": cols["name"],
        "block_col": cols["block"],
    }
    hier, name = cols["hier"], cols["name"]
    if not hier or hier not in df.columns or not name or name not in df.columns:
        return result
    ancestor_pd = _ancestor_under_pd(df, hier, name, cols["block"])
    cipher_m = cipher_ok.fillna(False) if cipher_col else empty
    level_col = cols["level"]
    lv_num = (
        outline_level_numeric(df[level_col])
        if level_col and level_col in df.columns
        else pd.Series(np.nan, index=df.index)
    )
    parent_names = _immediate_parents(df, hier, name)
    parent_pd = parent_names.map(_parent_is_pd_stage)
    lv_task = lv_num
    if hier in df.columns:
        lv_struct = outline_level_numeric(df[hier])
        lv_task = lv_task.where(lv_task.notna(), lv_struct) if lv_task.notna().any() else lv_struct
    tz = lv_task.eq(5) & parent_pd & cipher_m
    if not tz.any():
        tz = lv_task.eq(5) & ancestor_pd & cipher_m
    if not tz.any() and cipher_m.any():
        tz = cipher_m
    result["metrics_mask"] = tz
    result["dynamics_mask"] = tz
    return result


def _find_baseline_finish(df: pd.DataFrame) -> str | None:
    for cand in ("base end", "baseline finish", "базовое окончание"):
        hit = _col(df, [cand])
        if hit:
            return hit
    for c in df.columns:
        cl = str(c).strip().lower()
        if ("базов" in cl or "baseline" in cl) and ("оконч" in cl or "finish" in cl):
            return c
    return None


def _find_schedule_finish(df: pd.DataFrame) -> str | None:
    for cand in ("plan end", "finish", "окончание"):
        if cand in df.columns:
            return cand
    hit = _col(df, ["plan end", "окончание", "finish"])
    if hit:
        cl = str(hit).lower()
        if "базов" not in cl and "baseline" not in cl:
            return hit
    return None


def _find_baseline_start(df: pd.DataFrame) -> str | None:
    for cand in ("base start", "baseline start", "базовое начало"):
        hit = _col(df, [cand])
        if hit:
            return hit
    return None


def _find_schedule_start(df: pd.DataFrame) -> str | None:
    for cand in ("plan start", "start", "начало"):
        if cand in df.columns:
            return cand
    return _col(df, ["plan start", "начало", "start"])


def _find_actual_finish(df: pd.DataFrame) -> str | None:
    hit = _col(df, ["actual finish", "фактическое окончание", "окончание факт"])
    return hit


def _pick_finish(
    df: pd.DataFrame, mask: pd.Series, *, baseline: str | None, schedule: str | None
) -> str | None:
    m = mask.fillna(False)
    best, best_n = None, -1
    for cand in (baseline, schedule):
        if not cand or cand not in df.columns:
            continue
        n = int((m & _to_dt(df[cand]).notna()).sum()) if m.any() else int(_to_dt(df[cand]).notna().sum())
        if n > best_n:
            best, best_n = cand, n
    return best


def _mask_with_finish(df: pd.DataFrame, mask: pd.Series, fin_col: str | None) -> pd.Series:
    m = mask.fillna(False)
    if not fin_col or fin_col not in df.columns:
        return m & False
    return m & _to_dt(df[fin_col]).notna()


def _mask_with_start_finish(
    df: pd.DataFrame, mask: pd.Series, start_col: str | None, fin_col: str | None
) -> pd.Series:
    m = _mask_with_finish(df, mask, fin_col)
    if start_col and start_col in df.columns:
        sm = _to_dt(df[start_col]).notna()
        both = m & sm
        if both.any():
            return both
    return m


def _cumsum_by_granularity(dates: pd.Series, row_mask: pd.Series, gran_key: str) -> pd.DataFrame:
    dt = _to_dt(dates)
    m = row_mask.fillna(False) & dt.notna()
    if not m.any():
        return pd.DataFrame(columns=["Дата", "Количество"])
    s = dt.loc[m].dt.normalize()
    if gran_key == "week":
        bucket = s - pd.to_timedelta(s.dt.dayofweek, unit="D")
    elif gran_key == "month":
        bucket = s - pd.to_timedelta(s.dt.day - 1, unit="D")
    else:
        bucket = s
    daily = bucket.groupby(bucket).size().reset_index(name="cnt")
    daily.columns = ["Дата", "cnt"]
    daily = daily.sort_values("Дата")
    daily["Количество"] = daily["cnt"].cumsum()
    return daily[["Дата", "Количество"]]


def _bucket_ts(ts: pd.Timestamp, gran_key: str) -> pd.Timestamp:
    s = pd.Timestamp(ts).normalize()
    if gran_key == "week":
        return s - pd.to_timedelta(int(s.dayofweek), unit="D")
    if gran_key == "month":
        return s - pd.to_timedelta(int(s.day) - 1, unit="D")
    return s


def _splice_pd_forecast_from_fact(
    dynamics: list[dict[str, Any]],
    *,
    remaining_dates: pd.Series,
    remaining_mask: pd.Series,
    report: date,
    fact_at_report: float,
    gran_key: str,
) -> list[dict[str, Any]]:
    """Прогноз ПД: стык с фактом на дату отчёта; дальше — срок окончания невыданных."""
    if not dynamics:
        return dynamics
    junction = _bucket_ts(pd.Timestamp(report), gran_key)
    rem = remaining_mask.fillna(False)
    dt = _to_dt(remaining_dates)
    rem = rem & dt.notna()
    increments: dict[pd.Timestamp, float] = {}
    if rem.any():
        for raw in dt.loc[rem]:
            b = _bucket_ts(pd.Timestamp(raw), gran_key)
            if b < junction:
                b = junction
            increments[b] = increments.get(b, 0.0) + 1.0

    by_period: dict[str, dict[str, Any]] = {
        str(r["period"])[:10]: dict(r) for r in dynamics
    }
    jkey = junction.strftime("%Y-%m-%d")
    if jkey not in by_period:
        left = None
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
            "plan_bp": 0.0,
            "fact": fact_at_report,
            "forecast": fact_at_report,
        }
        by_period[jkey] = {
            **seed,
            "period": jkey,
            "period_label": _axis_label(junction),
            "fact": float(fact_at_report),
        }
    for m in increments:
        k = pd.Timestamp(m).strftime("%Y-%m-%d")
        if k not in by_period:
            by_period[k] = {
                "period": k,
                "period_label": _axis_label(pd.Timestamp(m)),
                "plan_bp": None,
                "fact": float(fact_at_report),
                "forecast": None,
            }
    if increments and not any(pd.Timestamp(m) > junction for m in increments):
        if gran_key == "week":
            nxt = junction + pd.Timedelta(days=7)
        elif gran_key == "month":
            nxt = (junction + pd.DateOffset(months=1)).normalize()
        else:
            nxt = junction + pd.Timedelta(days=1)
        nxt = _bucket_ts(nxt, gran_key)
        nk = nxt.strftime("%Y-%m-%d")
        if nk not in by_period:
            by_period[nk] = {
                "period": nk,
                "period_label": _axis_label(nxt),
                "plan_bp": None,
                "fact": float(fact_at_report),
                "forecast": None,
            }

    ordered = sorted(by_period.values(), key=lambda r: str(r["period"])[:10])
    last_p = 0.0
    for r in ordered:
        if r.get("plan_bp") is not None:
            last_p = float(r["plan_bp"] or 0.0)
        r["plan_bp"] = last_p
        d = pd.Timestamp(str(r["period"])[:10]).normalize()
        if d < junction:
            r["forecast"] = None
            continue
        if d == junction:
            r["fact"] = float(round(fact_at_report))
            r["forecast"] = float(round(fact_at_report))
            continue
        cum_inc = sum(float(v) for m, v in increments.items() if pd.Timestamp(m) <= d)
        r["forecast"] = float(round(fact_at_report + cum_inc))
        # Факт после даты отчёта не продлеваем — плато на факте отчёта
        r["fact"] = float(round(fact_at_report))
    return ordered


def _necessary_productivity(
    deviation_to_date: float,
    baseline_finish: pd.Series,
    report_date: date,
    period_multiplier: float,
    *,
    schedule_finish: pd.Series | None = None,
) -> float | None:
    """
    Необходимая производительность за период (день/неделя/месяц).

    ``deviation_to_date`` = план − факт на дату:
    - ≤ 0 (план выполнен или перевыполнен) → 0;
    - > 0 (отставание) → (отставание / дней до срока) × множитель (1/7/30).
    """
    lag = float(deviation_to_date or 0)
    if lag <= 0:
        return 0.0
    rem_days: int | None = None
    bf = _to_dt(baseline_finish).dropna()
    if not bf.empty:
        rem_days = (bf.max().date() - report_date).days
    if (rem_days is None or rem_days <= 0) and schedule_finish is not None:
        sf = _to_dt(schedule_finish).dropna()
        if not sf.empty:
            rem_days = (sf.max().date() - report_date).days
    if rem_days is None or rem_days <= 0:
        rem_days = max(int(period_multiplier) or 1, 1)
    return (lag / float(rem_days)) * float(period_multiplier)


def _period_label(ts: pd.Timestamp) -> str:
    return f"{_MONTH_RU[int(ts.month)]} {ts.year}"


def _axis_label(ts: Any) -> str:
    t = pd.to_datetime(ts, errors="coerce")
    if pd.isna(t):
        return ""
    return _period_label(pd.Timestamp(t))


def _dedupe_latest(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or getattr(df, "empty", True):
        return df
    out = df.copy()
    if "snapshot_date" not in out.columns:
        out["snapshot_date"] = pd.NaT
    out["snapshot_date"] = pd.to_datetime(out["snapshot_date"], errors="coerce")
    pc = "project name" if "project name" in out.columns else None
    id_col = next((c for c in ("unique id", "task id seq", "Ид") if c in out.columns), None)
    if not pc or not id_col:
        return out
    ok = out[id_col].notna() & (out[id_col].astype(str).str.strip().ne(""))
    if not ok.any():
        return out
    part_ok = (
        out.loc[ok]
        .sort_values("snapshot_date", ascending=True, kind="mergesort")
        .drop_duplicates(subset=[pc, id_col], keep="last")
    )
    return pd.concat([out.loc[~ok], part_ok]).sort_index().reset_index(drop=True)


def _snapshot_month_labels(df: pd.DataFrame) -> list[str]:
    if "snapshot_date" not in df.columns:
        return []
    s = pd.to_datetime(df["snapshot_date"], errors="coerce").dropna()
    if s.empty:
        return []
    periods = sorted({pd.Timestamp(t).to_period("M") for t in s}, reverse=True)
    return [f"{_MONTH_RU[p.month]} {p.year}" for p in periods]


def _apply_period_months(df: pd.DataFrame, months: list[str] | None) -> pd.DataFrame:
    if not months or "snapshot_date" not in df.columns:
        return df
    wanted = set()
    for label in months:
        for i, name in enumerate(_MONTH_RU):
            if i and name and name.casefold() in label.casefold():
                year_m = re.search(r"(20\d{2})", label)
                if year_m:
                    wanted.add(f"{year_m.group(1)}-{i:02d}")
    if not wanted:
        return df
    snap = pd.to_datetime(df["snapshot_date"], errors="coerce")
    keys = snap.dt.strftime("%Y-%m")
    return df.loc[keys.isin(wanted)].copy()


def _section_labels(df: pd.DataFrame, masks: dict[str, Any]) -> pd.Series:
    cipher_col = masks.get("cipher_col")
    name_col = masks.get("name_col") or ("task name" if "task name" in df.columns else None)
    work = df
    dyn = masks.get("dynamics_mask")
    if isinstance(dyn, pd.Series) and dyn.fillna(False).any():
        work = df.loc[dyn.fillna(False)].copy()
    cipher = (
        work[cipher_col].astype(str).str.strip()
        if cipher_col and cipher_col in work.columns
        else pd.Series("", index=work.index)
    )
    cipher = cipher.mask(cipher.str.lower().isin(_BLANK), "")
    names = (
        work[name_col].astype(str).str.strip()
        if name_col and name_col in work.columns
        else pd.Series("", index=work.index)
    )
    labels = (cipher + " " + names).str.strip()
    labels = labels.where(labels.ne(""), cipher.where(cipher.ne(""), names))
    out = pd.Series("", index=df.index, dtype=object)
    out.loc[work.index] = labels.values
    return out


def _clamp_dates(s: pd.Series, ts_report: pd.Timestamp) -> pd.Series:
    ser = _to_dt(s)
    ymin = pd.Timestamp("2000-01-01")
    ymax = pd.Timestamp(ts_report).normalize() + pd.DateOffset(years=10)
    return ser.mask(ser.notna() & ((ser < ymin) | (ser > ymax)))


def _delay_segments(
    start_n: pd.Timestamp,
    bf_n: pd.Timestamp,
    fin_n: pd.Timestamp | None,
    *,
    done: bool,
) -> dict[str, Any]:
    start_n = pd.Timestamp(start_n).normalize()
    bf_n = pd.Timestamp(bf_n).normalize()
    fin_ts = (
        pd.Timestamp(fin_n).normalize()
        if fin_n is not None and pd.notna(fin_n)
        else pd.NaT
    )
    base_dur = max(int((bf_n - start_n).days), 0)
    fact_dur = 0.0
    delay_dur = 0
    delay_end = None
    fin_iso = None
    if pd.notna(fin_ts) and fin_ts > bf_n:
        delay_dur = int((fin_ts - bf_n).days)
        delay_end = fin_ts.strftime("%Y-%m-%d")
        fin_iso = fin_ts.strftime("%Y-%m-%d")
    elif done and pd.notna(fin_ts) and fin_ts <= bf_n:
        fact_dur = float(max(int((fin_ts - start_n).days), 0))
        fin_iso = fin_ts.strftime("%Y-%m-%d")
    return {
        "start": start_n.strftime("%Y-%m-%d"),
        "base_finish": bf_n.strftime("%Y-%m-%d"),
        "finish": fin_iso,
        "delay_end": delay_end,
        "base_dur": float(base_dur),
        "fact_dur": float(fact_dur),
        "delay_dur": float(delay_dur),
        "base_label": bf_n.strftime("%d.%m.%Y"),
        "finish_label": pd.Timestamp(fin_ts).strftime("%d.%m.%Y") if pd.notna(fin_ts) else "",
    }


def _aggregate_delay_seg(
    idx: pd.Index,
    *,
    bs_dt: pd.Series,
    ss_dt: pd.Series,
    bf_dt: pd.Series,
    sf_dt: pd.Series,
    af_dt: pd.Series,
    pct: pd.Series,
    ts_report: pd.Timestamp,
) -> dict[str, Any] | None:
    if len(idx) == 0:
        return None
    bs = _clamp_dates(bs_dt.reindex(idx), ts_report)
    ss = _clamp_dates(ss_dt.reindex(idx), ts_report)
    bf = _clamp_dates(bf_dt.reindex(idx), ts_report)
    af = _clamp_dates(af_dt.reindex(idx), ts_report)
    sf = _clamp_dates(sf_dt.reindex(idx), ts_report)
    pc = pct.reindex(idx).fillna(0.0)
    starts: list[pd.Timestamp] = []
    for i in idx:
        s = bs.loc[i]
        if pd.isna(s):
            s = ss.loc[i]
        if pd.isna(s):
            s = bf.loc[i]
        if pd.notna(s):
            starts.append(pd.Timestamp(s).normalize())
    bf_valid = [pd.Timestamp(bf.loc[i]).normalize() for i in idx if pd.notna(bf.loc[i])]
    sf_valid = [pd.Timestamp(sf.loc[i]).normalize() for i in idx if pd.notna(sf.loc[i])]
    if not starts and not bf_valid and not sf_valid:
        return None
    start_n = min(starts) if starts else (min(sf_valid) if sf_valid else min(bf_valid))
    bf_n = max(bf_valid) if bf_valid else pd.NaT
    fin_all: list[pd.Timestamp] = []
    all_done = True
    for i in idx:
        pc_i = float(pc.loc[i]) if pd.notna(pc.loc[i]) else 0.0
        if pc_i < 99.99:
            all_done = False
        fin_i = sf.loc[i] if pd.notna(sf.loc[i]) else af.loc[i]
        if pd.notna(fin_i):
            fin_all.append(pd.Timestamp(fin_i).normalize())
    fin_n = max(fin_all) if fin_all else pd.NaT
    if pd.isna(bf_n) and pd.notna(fin_n):
        bf_n = fin_n
    if pd.isna(bf_n):
        return None
    done = bool(fin_all and all_done)
    return _delay_segments(start_n, bf_n, fin_n if pd.notna(fin_n) else None, done=done)


def _plan_due_mask(plan_finish: pd.Series, plan_start: pd.Series, ts: pd.Timestamp) -> pd.Series:
    ts_n = pd.Timestamp(ts).normalize()
    pf = _to_dt(plan_finish)
    ps = _to_dt(plan_start)
    due_finish = pf.notna() & (pf.dt.normalize() <= ts_n)
    due_start = (
        ps.notna()
        & (ps.dt.normalize() <= ts_n)
        & (~due_finish)
        & (pf.isna() | (pf.dt.normalize() > ts_n))
    )
    return (due_finish | due_start).fillna(False)


def _dedupe_by_cipher(
    month_df: pd.DataFrame, *, cipher_col: str | None, project_col: str | None
) -> pd.DataFrame:
    if month_df is None or getattr(month_df, "empty", True) or not cipher_col or cipher_col not in month_df.columns:
        return month_df
    out = month_df.copy()
    ck = out[cipher_col].fillna("").astype(str).str.strip()
    ck = ck.mask(ck.str.lower().isin({"", "nan", "none", "<na>"}), "")
    if project_col and project_col in out.columns:
        pk = out[project_col].fillna("").astype(str).str.strip()
        out["_key"] = pk + "||" + ck
    else:
        out["_key"] = ck
    empty = out["_key"].isin({"", "||"})
    keep_empty = out.loc[empty].copy()
    has_key = out.loc[~empty].copy()
    if has_key.empty:
        return month_df.drop(columns=["_key"], errors="ignore")
    rows: list[pd.Series] = []
    for _, g in has_key.groupby("_key", sort=False):
        ord_s = g["_plan_end_dt"] if "_plan_end_dt" in g.columns else pd.Series(pd.NaT, index=g.index)
        i = ord_s.idxmax() if ord_s.notna().any() else g.index[0]
        row = g.loc[i].copy()
        for flag in ("_pd_row_overdue", "_pd_row_fact"):
            if flag in g.columns:
                row[flag] = int(pd.to_numeric(g[flag], errors="coerce").fillna(0).gt(0).any())
        if "_pd_row_fact" in row.index and "_pd_row_overdue" in row.index:
            row["_pd_row_fact_ontime"] = int(int(row["_pd_row_fact"]) > 0 and int(row["_pd_row_overdue"]) <= 0)
        rows.append(row)
    merged = pd.concat([pd.DataFrame(rows), keep_empty], ignore_index=True)
    return merged.drop(columns=["_key"], errors="ignore")


def _empty_payload(*, error: str | None = None) -> dict[str, Any]:
    today = date.today().isoformat()
    return {
        "meta": {
            "rows": 0,
            "source": "web_data.db",
            "data_mode": DATA_MODE,
            "files": 0,
            "doc_kind": "pd",
            "title": "Проектная документация",
            "rule": "MSP ур.5 + шифр + этап «Проектная документация»",
            "parity": "main_project_documentation",
            "version_id": None,
            "error": error,
        },
        "filters": {
            "projects": ["Все"],
            "sections": ["Все"],
            "periods": [],
            "granularities": [
                {"id": "day", "label": "За день"},
                {"id": "week", "label": "За неделю"},
                {"id": "month", "label": "За месяц"},
            ],
            "view_modes": [
                {"id": "project", "label": "По проекту"},
                {"id": "section", "label": "По разделу"},
            ],
            "status_legend": [
                {"id": "issued", "label": "Выдано в производство работ", "tone": "bad"},
                {"id": "overdue", "label": "Просрочено подрядчиком", "tone": "bad"},
            ],
            "applied": {
                "project": "Все",
                "section": "Все",
                "period": "Все месяцы",
                "granularity": "week",
                "report_date": today,
                "view_mode": "project",
                "tab": "main",
            },
        },
        "kpis": {
            "plan_total": 0,
            "plan_to_date": 0,
            "fact_to_date": 0,
            "deviation_to_date": 0,
            "current_productivity": 0.0,
            "required_productivity": 0.0,
            "productivity_label": "за неделю",
            "required_label": "в неделю",
        },
        "tremor": {
            "status_mix": [],
            "dynamics": [],
            "monthly": [],
        },
        "rows": [],
        "delay": {
            "gantt": {"rows": [], "range_start": None, "range_end": None},
            "cards": [],
            "detail_rows": [],
            "detail_columns": [
                "Проект",
                "Наименование раздела работ",
                "Раздел",
                "Статус",
                "Начало",
                "Базовое начало",
                "Окончание",
                "Базовое окончание",
                "Отклонение начала, дн",
                "Отклонение окончания, дн",
            ],
            "summary_rows": [],
            "summary_columns": ["Проект", "План ПД", "Факт ПД", "Просрочка ПД"],
        },
    }


def build_project_documentation_payload(
    *,
    project: str | None = None,
    section: str | None = None,
    period: str | None = None,
    granularity: str | None = "week",
    report_date: str | None = None,
    view_mode: str | None = "project",
    tab: str | None = "main",
) -> dict[str, Any]:
    cache_key = (
        f"v9-forecast-legend|p={project or 'Все'}|s={section or 'Все'}|per={period or ''}"
        f"|g={granularity or 'week'}|d={report_date or ''}|vm={view_mode or 'project'}"
        f"|t={tab or 'main'}|db={WEB_DB_PATH}|mtime={db_status().get('mtime')}"
    )
    cached = cache_get("project-documentation", cache_key, max_age_sec=3600)
    if cached is not None:
        return cached

    if not WEB_DB_PATH.is_file():
        return _empty_payload(error="web_data.db нет — выполните POST /api/admin/ingest (или sync).")

    try:
        prepare_web_db()
        import web_schema  # type: ignore
        from utils import sanitize_display_label  # type: ignore

        labels_mod = import_dashboard_module("project_labels")
        version_id = web_schema.get_active_version_id()
        if not version_id:
            return _empty_payload(error="Нет active version_id в web_data.db")

        work = load_msp_frame(int(version_id))
        if work is None or getattr(work, "empty", True):
            return _empty_payload(error="Нет MSP (file_type=project) в активной версии")

        work = work.copy()
        if "__source_file" in work.columns:
            src = work["__source_file"].astype(str).str.lower()
            is_msp = (
                src.str.startswith("msp_")
                | src.str.contains("/msp_", na=False)
                | src.str.contains(r"\\msp_", na=False, regex=True)
            )
            if bool(is_msp.any()):
                work = work.loc[is_msp].copy()

        proj_col = _col(work, ["project name", "Проект", "проект", "Project"])
        if proj_col:
            work = labels_mod.apply_unified_project_column(work, proj_col)
            if proj_col != "project name":
                if "project name" not in work.columns:
                    work = work.rename(columns={proj_col: "project name"})
                else:
                    work["project name"] = work[proj_col]
        proj_col = "project name" if "project name" in work.columns else proj_col

        period_labels = _snapshot_month_labels(work)
        periods_applied: list[str] = []
        if period and period not in ("Все", "Все месяцы", ""):
            periods_applied = [p.strip() for p in str(period).split("|") if p.strip()]
        if periods_applied:
            work = _apply_period_months(work, periods_applied)
        work = _dedupe_latest(work)

        available_projects = ["Все"]
        if proj_col and proj_col in work.columns:
            available_projects += labels_mod.project_labels_for_filter(work[proj_col])
        applied_project = project if project in available_projects else "Все"

        scoped = work
        if applied_project != "Все" and proj_col and proj_col in scoped.columns:
            scoped = labels_mod.filter_dataframe_by_project_labels(
                scoped, [applied_project], col=proj_col
            )

        masks = _section_masks(scoped)
        labels_series = _section_labels(scoped, masks)
        section_opts = sorted(
            {
                str(v).strip()
                for v in labels_series.tolist()
                if str(v).strip() and str(v).strip().lower() not in _BLANK
            },
            key=str.casefold,
        )
        if not section_opts:
            cipher_col, cipher_ok = _cipher_mask(scoped)
            if cipher_col and cipher_col in scoped.columns:
                section_opts = sorted(
                    {
                        str(v).strip()
                        for v in scoped.loc[cipher_ok.fillna(False), cipher_col].tolist()
                        if str(v).strip()
                    },
                    key=str.casefold,
                )
        available_sections = ["Все"] + section_opts
        applied_section = section if section in available_sections else "Все"
        if applied_section != "Все":
            scoped = scoped.loc[labels_series.reindex(scoped.index).fillna("") == applied_section].copy()
            masks = _section_masks(scoped)

        today = date.today()
        try:
            report = date.fromisoformat((report_date or "")[:10]) if report_date else today
        except ValueError:
            report = today
        gran_id = granularity if granularity in _GRAN else "week"
        gran_key, mult_nec, win_days, gran_ru = _GRAN[gran_id]
        view = "section" if str(view_mode or "").casefold() in {"section", "по разделу"} else "project"
        ts_today = pd.Timestamp(report)

        metrics = masks["metrics_mask"].fillna(False)
        if not metrics.any():
            metrics = masks["dynamics_mask"].fillna(False)
        pc = _pct_series(scoped)
        done_v = int((metrics & (pc >= 99.99)).sum())
        prog_v = int((metrics & (pc > 0) & (pc < 99.99)).sum())
        wait_v = int((metrics & (pc <= 0)).sum())
        status_mix = []
        for name, val, color in (
            ("Завершено (100%)", done_v, "#2E86AB"),
            ("В работе", prog_v, "#F39C12"),
            ("Не начато", wait_v, "#E74C3C"),
        ):
            if val > 0:
                status_mix.append({"name": name, "value": val, "color": color})

        b_base = _find_baseline_finish(scoped)
        s_fin = _find_schedule_finish(scoped)
        b_start = _find_baseline_start(scoped)
        s_start = _find_schedule_start(scoped)
        act_col = _find_actual_finish(scoped)
        af = _to_dt(scoped[act_col]) if act_col and act_col in scoped.columns else pd.Series(pd.NaT, index=scoped.index)

        chart_mask = metrics.copy()
        chart_b = _pick_finish(scoped, chart_mask, baseline=b_base, schedule="plan end" if "plan end" in scoped.columns else s_fin) or b_base
        chart_s = _pick_finish(scoped, chart_mask, baseline=s_fin, schedule="plan end" if "plan end" in scoped.columns else s_fin) or s_fin
        plan_line = _mask_with_start_finish(scoped, chart_mask, b_start, chart_b)
        fcst_line = _mask_with_start_finish(scoped, chart_mask, s_start, chart_s)
        if not plan_line.any():
            plan_line = _mask_with_finish(scoped, chart_mask, chart_b)
        if not fcst_line.any():
            fcst_line = _mask_with_finish(scoped, chart_mask, chart_s)

        bf_bp = _to_dt(scoped[b_base]) if b_base and b_base in scoped.columns else pd.Series(pd.NaT, index=scoped.index)
        if chart_b and chart_b in scoped.columns:
            pick_bp = _to_dt(scoped[chart_b])
            bf_bp = bf_bp.where(bf_bp.notna(), pick_bp)
        sf = _to_dt(scoped[chart_s]) if chart_s and chart_s in scoped.columns else pd.Series(pd.NaT, index=scoped.index)
        plan_dates = bf_bp.where(bf_bp.notna(), _to_dt(scoped[chart_b]) if chart_b and chart_b in scoped.columns else bf_bp)

        m_sec = chart_mask.fillna(False)
        m_kpi = plan_line.fillna(False)
        m_kpi_bp = m_kpi & plan_dates.notna()
        plan_total = float(m_sec.sum()) if m_sec.any() else float(m_kpi_bp.sum())
        plan_to_date = int((m_kpi_bp & (plan_dates.dt.normalize() <= ts_today)).sum())
        done_sec = m_sec & ((pc >= 99.99) | (af.notna() & (af.dt.normalize() <= ts_today)))
        fact_to_date = int(done_sec.sum())
        deviation_to_date = int(fact_to_date - plan_to_date)
        done_sec_dated = m_kpi_bp & ((pc >= 99.99) | (af.notna() & (af.dt.normalize() <= ts_today)))

        plan_curve = _cumsum_by_granularity(plan_dates, m_kpi_bp, gran_key)
        fcst_curve = _cumsum_by_granularity(sf, fcst_line, gran_key)
        fact_dates = af.copy()
        proxy = done_sec_dated & fact_dates.isna()
        if proxy.any():
            fact_dates = fact_dates.where(~proxy, sf)
        fact_curve = _cumsum_by_granularity(fact_dates, done_sec_dated & fact_dates.notna(), gran_key)

        all_dates = sorted(
            set(plan_curve["Дата"].tolist() if not plan_curve.empty else [])
            | set(fcst_curve["Дата"].tolist() if not fcst_curve.empty else [])
            | set(fact_curve["Дата"].tolist() if not fact_curve.empty else [])
        )
        dynamics: list[dict[str, Any]] = []
        if all_dates:
            anchor = (pd.Timestamp(min(all_dates)) - pd.Timedelta(days=1)).normalize()
            plan_map = {pd.Timestamp(r["Дата"]): float(r["Количество"]) for _, r in plan_curve.iterrows()} if not plan_curve.empty else {}
            fcst_map = {pd.Timestamp(r["Дата"]): float(r["Количество"]) for _, r in fcst_curve.iterrows()} if not fcst_curve.empty else {}
            fact_map = {pd.Timestamp(r["Дата"]): float(r["Количество"]) for _, r in fact_curve.iterrows()} if not fact_curve.empty else {}
            last_p = last_f = last_a = 0.0
            seq = [anchor] + [pd.Timestamp(d) for d in all_dates]
            for d in seq:
                if d in plan_map:
                    last_p = plan_map[d]
                if d in fcst_map:
                    last_f = fcst_map[d]
                if d in fact_map:
                    last_a = fact_map[d]
                dynamics.append(
                    {
                        "period": d.strftime("%Y-%m-%d"),
                        "period_label": _axis_label(d),
                        "plan_bp": last_p,
                        "forecast": last_f,
                        "fact": last_a,
                    }
                )
            # Прогноз стыкуется с фактом на дату отчёта; дальше — срок окончания невыданных.
            remaining = chart_mask.fillna(False) & (~done_sec.fillna(False)) & sf.notna()
            dynamics = _splice_pd_forecast_from_fact(
                dynamics,
                remaining_dates=sf,
                remaining_mask=remaining,
                report=report,
                fact_at_report=float(fact_to_date),
                gran_key=gran_key,
            )

        nec = _necessary_productivity(
            float(plan_to_date - fact_to_date),
            plan_dates.loc[m_kpi_bp],
            report,
            mult_nec,
            schedule_finish=sf.loc[fcst_line.fillna(False)],
        )
        period_start = report - timedelta(days=int(win_days) - 1)
        prod_n = int(
            (
                done_sec
                & af.notna()
                & (af.dt.normalize() >= pd.Timestamp(period_start))
                & (af.dt.normalize() <= ts_today)
            ).sum()
        )
        if nec is None:
            nec_val = 0.0
        else:
            nec_val = float(nec)

        tbl_mask = (plan_line | fcst_line).fillna(False)
        idx_sec = scoped.index[tbl_mask]
        cipher_col = masks.get("cipher_col")
        rows_out: list[dict[str, Any]] = []
        if len(idx_sec):
            blank = set(_BLANK)
            if cipher_col and cipher_col in scoped.columns:
                raw_c = scoped.loc[idx_sec, cipher_col]
                sec_disp = raw_c.astype(str).str.strip()
                keep = ~(raw_c.isna() | sec_disp.str.lower().isin(blank))
            else:
                name_col = masks.get("name_col")
                sec_disp = (
                    scoped.loc[idx_sec, name_col].astype(str).str.strip()
                    if name_col and name_col in scoped.columns
                    else pd.Series("", index=idx_sec)
                )
                keep = ~sec_disp.str.lower().isin(blank)
            idx_sec = idx_sec[keep.to_numpy()]
            sec_disp = sec_disp.loc[idx_sec]
            if len(idx_sec):
                tbl = pd.DataFrame({"Раздел": sec_disp.values}, index=idx_sec)
                tbl["Проект"] = (
                    scoped.loc[idx_sec, proj_col].astype(str).str.strip().values
                    if proj_col and proj_col in scoped.columns
                    else ""
                )
                tbl["_bf"] = bf_bp.reindex(idx_sec).dt.normalize()
                tbl["_sf"] = sf.reindex(idx_sec).dt.normalize()
                tbl["_dev"] = (tbl["_bf"] - tbl["_sf"]).dt.days
                tbl = (
                    tbl.sort_values(["Проект", "_dev", "Раздел"], ascending=[True, False, True], kind="mergesort")
                    .drop_duplicates(subset=["Проект", "Раздел"], keep="last")
                )
                for i, (_, r) in enumerate(tbl.iterrows(), start=1):
                    days = pd.to_numeric(r["_dev"], errors="coerce")
                    days_i = int(round(float(days))) if pd.notna(days) else None
                    rows_out.append(
                        {
                            "n": i,
                            "project": sanitize_display_label(r["Проект"]),
                            "section": sanitize_display_label(r["Раздел"]),
                            "task": "",
                            "base_end": _fmt_date(r["_bf"]),
                            "plan_end": _fmt_date(r["_sf"]),
                            "dev_end": _fmt_dev(days_i) if days_i is not None else "",
                            "dev_end_days": days_i,
                            "pct_complete": None,
                            "status": "",
                            "ahead": bool(days_i is not None and days_i > 0),
                        }
                    )

        # --- delay tab ---
        delay_mask = metrics.copy()
        delay_df = scoped.loc[delay_mask.fillna(False)].copy()
        bs_dt = _to_dt(delay_df[b_start]) if b_start and b_start in delay_df.columns else pd.Series(pd.NaT, index=delay_df.index)
        ss_dt = _to_dt(delay_df[s_start]) if s_start and s_start in delay_df.columns else pd.Series(pd.NaT, index=delay_df.index)
        bf_dt = _to_dt(delay_df[b_base]) if b_base and b_base in delay_df.columns else pd.Series(pd.NaT, index=delay_df.index)
        sf_dt = _to_dt(delay_df[s_fin]) if s_fin and s_fin in delay_df.columns else pd.Series(pd.NaT, index=delay_df.index)
        af_dt = af.reindex(delay_df.index)
        pc_d = pc.reindex(delay_df.index).fillna(0.0)
        ts_rep = pd.Timestamp(report).normalize()

        plan_fin = bf_dt.where(bf_dt.notna(), sf_dt)
        start_dt = bs_dt.where(bs_dt.notna(), ss_dt)
        delay_df["_pd_row_plan"] = _plan_due_mask(plan_fin, start_dt, ts_rep).astype(int)
        delay_df["_pd_row_fact"] = (
            (pc_d >= 99.99) | (af_dt.notna() & (af_dt.dt.normalize() <= ts_rep))
        ).astype(int)
        delay_df["_pd_row_overdue"] = (
            bf_dt.notna()
            & (bf_dt.dt.normalize() <= ts_rep)
            & sf_dt.notna()
            & (sf_dt.dt.normalize() > bf_dt.dt.normalize())
        ).astype(int)
        delay_df["_pd_row_fact_ontime"] = (
            (delay_df["_pd_row_fact"] > 0) & (delay_df["_pd_row_overdue"] <= 0)
        ).astype(int)
        delay_df["_plan_end_dt"] = plan_fin
        kpi_df = _dedupe_by_cipher(
            delay_df, cipher_col=cipher_col if isinstance(cipher_col, str) else None, project_col=proj_col
        )

        gantt_rows: list[dict[str, Any]] = []
        cards: list[dict[str, Any]] = []
        summary_rows: list[dict[str, Any]] = []
        if proj_col and proj_col in delay_df.columns and not delay_df.empty:
            if view == "project":
                for proj in delay_df[proj_col].drop_duplicates():
                    idx = delay_df.index[delay_df[proj_col] == proj]
                    seg = _aggregate_delay_seg(
                        idx,
                        bs_dt=bs_dt,
                        ss_dt=ss_dt,
                        bf_dt=bf_dt,
                        sf_dt=sf_dt,
                        af_dt=af_dt,
                        pct=pc_d,
                        ts_report=ts_rep,
                    )
                    if seg:
                        gantt_rows.append({"label": str(proj).strip() or "—", **seg})
            else:
                name_col = masks.get("name_col")
                for idx, row in delay_df.iterrows():
                    lbl = ""
                    if cipher_col and cipher_col in delay_df.columns:
                        lbl = _clean(row.get(cipher_col))
                    if not lbl and name_col:
                        lbl = _clean(row.get(name_col))
                    if proj_col and applied_project == "Все":
                        # При «Все»/нескольких — «Проект | раздел»; при одном проекте — только шифр/раздел.
                        lbl = f"{_clean(row.get(proj_col))} | {lbl or '—'}"
                    elif not lbl:
                        lbl = "—"
                    start = bs_dt.loc[idx] if pd.notna(bs_dt.loc[idx]) else ss_dt.loc[idx]
                    if pd.isna(start):
                        start = bf_dt.loc[idx]
                    bf = bf_dt.loc[idx]
                    if pd.isna(start) or pd.isna(bf):
                        continue
                    fin = sf_dt.loc[idx] if pd.notna(sf_dt.loc[idx]) else af_dt.loc[idx]
                    done = float(pc_d.loc[idx] or 0) >= 99.99
                    seg = _delay_segments(
                        pd.Timestamp(start).normalize(),
                        pd.Timestamp(bf).normalize(),
                        fin if pd.notna(fin) else None,
                        done=done and pd.notna(fin),
                    )
                    gantt_rows.append({"label": lbl or "—", **seg})

            grp = (
                kpi_df.groupby(proj_col, as_index=False)
                .agg(
                    plan=("_pd_row_plan", "sum"),
                    fact=("_pd_row_fact_ontime", "sum"),
                    overdue=("_pd_row_overdue", "sum"),
                )
                .rename(columns={proj_col: "project"})
            )
            for _, r in grp.iterrows():
                ovd = int(r["overdue"])
                cards.append(
                    {
                        "project": str(r["project"]),
                        "overdue": ovd,
                        "label": f"Просрочка {ovd} док." if ovd > 0 else "Без просрочки",
                        "tone": "bad" if ovd > 0 else "ok",
                    }
                )
                summary_rows.append(
                    {
                        "project": str(r["project"]),
                        "plan": int(r["plan"]),
                        "fact": int(r["fact"]),
                        "overdue": -ovd if ovd > 0 else 0,
                        "overdue_label": _fmt_dev(-ovd) if ovd > 0 else "0",
                    }
                )

        monthly: list[dict[str, Any]] = []
        if not delay_df.empty and delay_df["_plan_end_dt"].notna().any():
            msrc = delay_df[delay_df["_plan_end_dt"].notna()].copy()
            msrc = _dedupe_by_cipher(
                msrc, cipher_col=cipher_col if isinstance(cipher_col, str) else None, project_col=proj_col
            )
            # После dedupe пересчитать ontime (как main `_pd_monthly_dedupe_by_cipher`).
            if "_pd_row_fact" in msrc.columns and "_pd_row_overdue" in msrc.columns:
                msrc["_pd_row_fact_ontime"] = (
                    (pd.to_numeric(msrc["_pd_row_fact"], errors="coerce").fillna(0) > 0)
                    & (pd.to_numeric(msrc["_pd_row_overdue"], errors="coerce").fillna(0) <= 0)
                ).astype(int)
            msrc["_month"] = _to_dt(msrc["_plan_end_dt"]).dt.to_period("M")
            cur_m = pd.Period(pd.Timestamp.today().normalize(), freq="M")
            msrc = msrc[msrc["_month"] <= cur_m]
            if not msrc.empty:
                # Как main `_rd_monthly_sections_aggregate(..., overdue_col=_pd_row_overdue)`:
                # done = факт вовремя; overdue = просрочка (в т.ч. сдано с опозданием).
                _ov = pd.to_numeric(msrc["_pd_row_overdue"], errors="coerce").fillna(0).gt(0)
                _fact = pd.to_numeric(msrc["_pd_row_fact"], errors="coerce").fillna(0)
                _plan = pd.to_numeric(msrc["_pd_row_plan"], errors="coerce").fillna(0)
                msrc["_overdue_n"] = np.where(_ov, _plan, 0.0)
                msrc["_done_n"] = np.where(~_ov & (_fact > 0), np.minimum(_plan, _fact), 0.0)
                agg = (
                    msrc.groupby("_month", as_index=False)
                    .agg(
                        plan=("_pd_row_plan", "sum"),
                        done=("_done_n", "sum"),
                        overdue=("_overdue_n", "sum"),
                    )
                    .sort_values("_month")
                )
                agg = agg[agg["plan"] > 0].copy()
                cum_p = cum_d = cum_o = 0
                rows_m = []
                for _, r in agg.iterrows():
                    p_inc = int(r["plan"])
                    d_inc = int(r["done"])
                    o_inc = int(r["overdue"])
                    cum_p += p_inc
                    cum_d += d_inc
                    cum_o += o_inc
                    fact_inc = d_inc + o_inc
                    rest = max(0, cum_p - cum_d - cum_o)
                    p = r["_month"]
                    rows_m.append(
                        {
                            "month": f"{p.year}-{int(p.month):02d}",
                            "month_label": f"{_MONTH_RU[int(p.month)]} {p.year}",
                            "plan": cum_p,
                            "done": cum_d,
                            "overdue": cum_o,
                            "rest": rest,
                            "fact": cum_d + cum_o,
                            "fact_inc": fact_inc,
                        }
                    )
                monthly = list(reversed(rows_m))

        detail_rows: list[dict[str, Any]] = []
        if not delay_df.empty:
            name_col = masks.get("name_col")
            tn = (
                delay_df[name_col].astype(str).str.strip()
                if name_col and name_col in delay_df.columns
                else pd.Series("", index=delay_df.index)
            )
            cipher = (
                delay_df[cipher_col].astype(str).str.strip()
                if cipher_col and cipher_col in delay_df.columns
                else pd.Series("", index=delay_df.index)
            )
            cipher = cipher.mask(cipher.str.lower().isin(_BLANK), "")
            razdel = cipher.where(cipher.ne(""), tn.str.extract(r"(Раздел\s+[\d.]+)", flags=re.I, expand=False).fillna(""))
            for idx in delay_df.index:
                pcv = float(pc_d.loc[idx] or 0)
                if pcv >= 99.99:
                    st_lbl = "Завершено (100%)"
                elif pcv <= 0.0001:
                    st_lbl = "Не начато (0%)"
                else:
                    st_lbl = f"В работе ({pcv:.0f}%)"
                if pd.notna(bs_dt.loc[idx]) and pd.notna(ss_dt.loc[idx]):
                    d_start = int((bs_dt.loc[idx] - ss_dt.loc[idx]).days)
                else:
                    d_start = None
                if pd.notna(bf_dt.loc[idx]) and pd.notna(sf_dt.loc[idx]):
                    d_end = int((bf_dt.loc[idx] - sf_dt.loc[idx]).days)
                else:
                    d_end = None
                detail_rows.append(
                    {
                        "project": _clean(delay_df.loc[idx, proj_col]) if proj_col else "",
                        "work_name": _clean(tn.loc[idx]) or "—",
                        "section": _clean(razdel.loc[idx]) or "—",
                        "status": st_lbl,
                        "start": _fmt_date(ss_dt.loc[idx]) or "—",
                        "base_start": _fmt_date(bs_dt.loc[idx]) or "—",
                        "finish": _fmt_date(sf_dt.loc[idx]) or "—",
                        "base_finish": _fmt_date(bf_dt.loc[idx]) or "—",
                        "dev_start": _fmt_dev(d_start) if d_start is not None else "",
                        "dev_start_days": d_start,
                        "dev_end": _fmt_dev(d_end) if d_end is not None else "",
                        "dev_end_days": d_end,
                    }
                )
            detail_rows.sort(key=lambda r: (r["dev_end_days"] is None, r["dev_end_days"] if r["dev_end_days"] is not None else 0))

        range_start = range_end = None
        if gantt_rows:
            starts = [r["start"] for r in gantt_rows if r.get("start")]
            ends = []
            for r in gantt_rows:
                for k in ("delay_end", "finish", "base_finish"):
                    if r.get(k):
                        ends.append(r[k])
                        break
            if starts:
                range_start = min(starts)
            if ends:
                range_end = max(ends)

        payload = {
            "meta": {
                "rows": len(rows_out),
                "source": "web_data.db",
                "data_mode": DATA_MODE,
                "files": 0,
                "doc_kind": "pd",
                "title": "Проектная документация",
                "rule": "MSP ур.5 + шифр + этап «Проектная документация»",
                "parity": "main_project_documentation",
                "version_id": int(version_id),
                "error": None,
            },
            "filters": {
                "projects": available_projects,
                "sections": available_sections,
                "periods": period_labels,
                "granularities": [
                    {"id": "day", "label": "За день"},
                    {"id": "week", "label": "За неделю"},
                    {"id": "month", "label": "За месяц"},
                ],
                "view_modes": [
                    {"id": "project", "label": "По проекту"},
                    {"id": "section", "label": "По разделу"},
                ],
                "status_legend": [
                    {"id": "issued", "label": "Выдано в производство работ", "tone": "bad"},
                    {"id": "overdue", "label": "Просрочено подрядчиком", "tone": "bad"},
                ],
                "applied": {
                    "project": applied_project,
                    "section": applied_section,
                    "period": " | ".join(periods_applied) if periods_applied else "Все месяцы",
                    "granularity": gran_id,
                    "report_date": report.isoformat(),
                    "view_mode": view,
                    "tab": tab or "main",
                },
            },
            "kpis": {
                "plan_total": int(plan_total),
                "plan_to_date": int(plan_to_date),
                "fact_to_date": int(fact_to_date),
                "deviation_to_date": int(deviation_to_date),
                "current_productivity": float(prod_n),
                "required_productivity": round(nec_val, 1) if abs(nec_val) < 10 else float(round(nec_val)),
                "productivity_label": gran_ru,
                "required_label": gran_ru.replace("за ", "в ") if gran_ru.startswith("за ") else gran_ru,
            },
            "tremor": {
                "status_mix": status_mix,
                "dynamics": dynamics,
                "monthly": monthly,
            },
            "rows": rows_out,
            "delay": {
                "gantt": {
                    "rows": gantt_rows,
                    "range_start": range_start,
                    "range_end": range_end,
                    "legend": [
                        {"id": "base", "label": "Базовое окончание", "color": "#F1C40F"},
                        {"id": "finish", "label": "Окончание", "color": "#27AE60"},
                        {"id": "delay", "label": "Просрочка", "color": "#C0392B"},
                    ],
                },
                "cards": cards,
                "detail_rows": detail_rows,
                "detail_columns": [
                    "Проект",
                    "Наименование раздела работ",
                    "Раздел",
                    "Статус",
                    "Начало",
                    "Базовое начало",
                    "Окончание",
                    "Базовое окончание",
                    "Отклонение начала, дн",
                    "Отклонение окончания, дн",
                ],
                "summary_rows": summary_rows,
                "summary_columns": ["Проект", "План ПД", "Факт ПД", "Просрочка ПД"],
            },
        }
        cache_set("project-documentation", cache_key, payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        out = _empty_payload(error=str(exc)[:400])
        return out
