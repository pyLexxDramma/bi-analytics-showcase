from __future__ import annotations

import json
import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from app.config import DATA_MODE, WEB_DATA_DIR

_DATE_RE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")
_EXCLUDE_PROJECTS = frozenset({"Дмитровский-1", "Барышы 2"})
_GRANULARITY_MAP = {
    "day": "D",
    "week": "W-MON",
    "month": "M",
    "quarter": "Q-DEC",
    "year": "Y-DEC",
}
_GRANULARITY_LABELS = {
    "day": "День",
    "week": "Неделя",
    "month": "Месяц",
    "quarter": "Квартал",
    "year": "Год",
}


def _read_csv(path: Path) -> pd.DataFrame:
    last_err: Exception | None = None
    for enc in ("cp1251", "utf-8-sig", "utf-8", "cp866"):
        for sep in (";", ",", "\t"):
            try:
                df = pd.read_csv(path, sep=sep, encoding=enc, dtype=str, low_memory=False)
                if df.shape[1] >= 5:
                    df.columns = [str(c).strip() for c in df.columns]
                    return df
            except Exception as e:
                last_err = e
                continue
    if last_err:
        raise last_err
    return pd.DataFrame()


def _to_dt(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", dayfirst=True)


def _fmt_date(v: Any) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    ts = pd.to_datetime(v, errors="coerce")
    if pd.isna(ts):
        return None
    try:
        return ts.strftime("%d.%m.%Y")
    except Exception:
        return None


def _norm_key(v: Any) -> str:
    return str(v or "").strip().lower()


def _file_date_key(name: str) -> tuple:
    m = _DATE_RE.search(name)
    if not m:
        return (0, 0, 0)
    dd, mm, yy = m.groups()
    return (int(yy), int(mm), int(dd))


def _richest_tessa_id() -> Path | None:
    if not WEB_DATA_DIR.is_dir():
        return None
    files = list(WEB_DATA_DIR.glob("tessa_*-id.csv"))
    if not files:
        return None
    return max(files, key=lambda p: (p.stat().st_size, _file_date_key(p.name), p.stat().st_mtime))


def _matching_task(id_path: Path) -> Path | None:
    parts = id_path.name.split("_", 1)
    if len(parts) < 2:
        return None
    date_tok = "-".join(parts[1].split("-")[:3])
    candidates = list(WEB_DATA_DIR.glob(f"tessa_{date_tok}*-task.csv"))
    if not candidates:
        candidates = list(WEB_DATA_DIR.glob("tessa_*-task.csv"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: (_file_date_key(p.name), p.stat().st_mtime))


def _latest_json(suffix: str) -> Path | None:
    if not WEB_DATA_DIR.is_dir():
        return None
    files = list(WEB_DATA_DIR.glob(f"*{suffix}"))
    if not files:
        return None
    return max(files, key=lambda p: (_file_date_key(p.name), p.stat().st_mtime))


def _paths_sig(path: Path | None) -> tuple:
    if path is None or not path.is_file():
        return tuple()
    st = path.stat()
    return (str(path.resolve()), st.st_mtime_ns, st.st_size)


def _dogovor_dates_lookup(path: Path | None) -> dict[str, tuple[pd.Timestamp, pd.Timestamp]]:
    if path is None or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            return {}
    if not isinstance(data, list):
        return {}
    out: dict[str, tuple[pd.Timestamp, pd.Timestamp]] = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        did = str(row.get("ID_Договора") or row.get("ID_Договор") or "").strip().lower()
        if not did:
            continue
        end_dt = pd.to_datetime(
            row.get("Дата_Окончания_Договора") or "", errors="coerce", format="mixed"
        )
        recv_dt = pd.to_datetime(
            row.get("Дата_Получения_ИД") or "", errors="coerce", format="mixed"
        )
        out[did] = (end_dt, recv_dt)
    return out


def _task_date_maps(task_path: Path | None) -> tuple[dict[str, pd.Timestamp], dict[str, pd.Timestamp]]:
    """CardID → min Completed for transfer / accept-print."""
    transfer: dict[str, pd.Timestamp] = {}
    accept: dict[str, pd.Timestamp] = {}
    if task_path is None or not task_path.is_file():
        return transfer, accept
    try:
        t = _read_csv(task_path)
    except Exception:
        return transfer, accept
    if t.empty or "CardID" not in t.columns or "Completed" not in t.columns:
        # some files use CardId
        cid_col = "CardID" if "CardID" in t.columns else ("CardId" if "CardId" in t.columns else None)
        if cid_col is None or "Completed" not in t.columns:
            return transfer, accept
    else:
        cid_col = "CardID"

    oc_col = "OptionCaption" if "OptionCaption" in t.columns else None
    if not oc_col:
        return transfer, accept

    toc = t[oc_col].astype(str).str.strip().str.casefold()
    tcomp = _to_dt(t["Completed"])
    agree_mask = toc.str.contains("на согласование", na=False)
    print_mask = toc.str.contains("печатн", na=False) & toc.str.contains("форм", na=False)

    def _agg(mask: pd.Series) -> dict[str, pd.Timestamp]:
        sub = t.loc[mask].copy()
        sub["_tc"] = tcomp.loc[mask]
        sub = sub[sub["_tc"].notna()]
        if sub.empty:
            return {}
        gb = sub.groupby(cid_col, dropna=False)["_tc"].min()
        mp: dict[str, pd.Timestamp] = {}
        for raw_k, dt in zip(gb.index.tolist(), gb.values.tolist()):
            nk = _norm_key(raw_k)
            if nk and not pd.isna(dt):
                mp[nk] = dt
        return mp

    return _agg(agree_mask), _agg(print_mask)


def _period_label(p: pd.Period) -> str:
    try:
        f = str(getattr(p, "freqstr", "") or "").upper()
        if f.startswith("Y"):
            return str(int(p.year))
        if f.startswith("Q"):
            return f"{int(p.year)} Q{int(p.quarter)}"
        if f.startswith("W"):
            return f"Неделя {int(p.week)} ({p.start_time.strftime('%d.%m')}—{p.end_time.strftime('%d.%m.%Y')})"
        if f.startswith("D"):
            return p.strftime("%d.%m.%Y")
        months = (
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
        return f"{months[int(p.month)]} {p.year}"
    except Exception:
        return str(p)


def _empty_payload(warning: str | None, source: str | None = None) -> dict[str, Any]:
    return {
        "meta": {
            "rows": 0,
            "data_mode": DATA_MODE,
            "source": source,
            "task_source": None,
            "warning": warning,
            "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        },
        "filters": {
            "projects": ["Все"],
            "contractors": ["Все"],
            "date_min": None,
            "date_max": None,
            "granularities": [
                {"id": k, "label": v} for k, v in _GRANULARITY_LABELS.items()
            ],
            "applied": {},
        },
        "kpis": {
            "total_docs": 0,
            "declined": 0,
            "on_agree": 0,
            "signed": 0,
            "on_rework": 0,
            "overdue_total": 0,
            "contractor_overdue": {
                "count": 0,
                "bucket_0_7": 0,
                "bucket_8_30": 0,
                "bucket_30_plus": 0,
            },
            "customer_overdue": {
                "count": 0,
                "bucket_0_7": 0,
                "bucket_8_30": 0,
                "bucket_30_plus": 0,
            },
        },
        "tremor": {
            "by_status": [],
            "by_object": [],
            "overdue_contractor": [],
            "overdue_customer": [],
            "dynamics": [],
        },
        "rows": [],
    }


@lru_cache(maxsize=4)
def _load_base_frame(id_sig: tuple, task_sig: tuple, dog_sig: tuple) -> pd.DataFrame:
    id_path = Path(id_sig[0])
    df = _read_csv(id_path)
    if df.empty:
        return pd.DataFrame()

    # Drop cancelled tags
    if "Tessa_Teg" in df.columns:
        tags = (
            df["Tessa_Teg"]
            .astype(str)
            .str.replace("\ufeff", "", regex=False)
            .str.replace("\xa0", " ", regex=False)
            .str.strip()
            .str.casefold()
        )
        empty_tag = tags.isin({"", "nan", "none", "<na>", "nat"})
        cancelled = tags.str.contains("отменен", na=False) | tags.isin(
            {"cancelled", "canceled"}
        )
        df = df.loc[~(cancelled & ~empty_tag)].copy()

    # Exclude prescriptions
    if "KindName" in df.columns:
        df = df[
            ~df["KindName"].astype(str).str.contains("Предписан", case=False, na=False)
        ].copy()

    # Drop «Проект»
    if "KrStateID" in df.columns:
        kr = pd.to_numeric(df["KrStateID"], errors="coerce")
        df = df[kr.fillna(-1) != 0]
    if "KrState" in df.columns:
        df = df[
            ~df["KrState"].astype(str).str.strip().str.casefold().isin({"проект", "project"})
        ]

    # Require ObjectName
    if "ObjectName" in df.columns:
        df = df[
            df["ObjectName"].notna()
            & ~df["ObjectName"].astype(str).str.strip().isin(["", "nan", "None", "NaN"])
        ]
        df = df[
            ~df["ObjectName"].astype(str).str.strip().isin(_EXCLUDE_PROJECTS)
        ]

    if df.empty:
        return df

    # Dedupe by DocID keep latest CreationDate / Import_data
    id_col = "DocID" if "DocID" in df.columns else None
    sort_cols: list[str] = []
    if "Import_data" in df.columns:
        df["_imp"] = _to_dt(df["Import_data"])
        sort_cols.append("_imp")
    if "CreationDate" in df.columns:
        df["_cd"] = _to_dt(df["CreationDate"])
        sort_cols.append("_cd")
    if id_col and sort_cols:
        df = (
            df.sort_values(sort_cols, kind="stable")
            .drop_duplicates(subset=[id_col], keep="last")
            .reset_index(drop=True)
        )
    elif id_col:
        df = df.drop_duplicates(subset=[id_col], keep="last").reset_index(drop=True)

    if "_cd" not in df.columns:
        df["_cd"] = _to_dt(df["CreationDate"]) if "CreationDate" in df.columns else pd.NaT

    df["_status"] = (
        df["KrState"].astype(str).str.strip() if "KrState" in df.columns else ""
    )
    df["_plan"] = _to_dt(df["id_Deadline"]) if "id_Deadline" in df.columns else pd.NaT

    # Task enrich (vectorized map)
    transfer_map, accept_map = _task_date_maps(Path(task_sig[0]) if task_sig else None)
    keys = df["DocID"].map(_norm_key) if "DocID" in df.columns else pd.Series("", index=df.index)
    df["_transfer"] = keys.map(transfer_map)
    df["_accept"] = keys.map(accept_map)
    # Completed column fallback for fact
    if "Completed" in df.columns:
        df["_accept"] = df["_accept"].fillna(_to_dt(df["Completed"]))

    # Dogovor dates
    dog_map = _dogovor_dates_lookup(Path(dog_sig[0]) if dog_sig else None)
    if "1C_ID_DOG" in df.columns and dog_map:
        ends = []
        recvs = []
        for v in df["1C_ID_DOG"]:
            pair = dog_map.get(_norm_key(v), (pd.NaT, pd.NaT))
            ends.append(pair[0])
            recvs.append(pair[1])
        df["_dog_end"] = ends
        df["_dog_recv"] = recvs
    else:
        df["_dog_end"] = pd.NaT
        df["_dog_recv"] = pd.NaT

    return df.reset_index(drop=True)


def clear_executive_docs_caches() -> None:
    _load_base_frame.cache_clear()


def _late_days_plan(plan, fact, today: date) -> int | None:
    if plan is None or pd.isna(plan):
        return None
    try:
        pday = pd.Timestamp(plan).date()
    except Exception:
        return None
    if fact is not None and not pd.isna(fact):
        try:
            fday = pd.Timestamp(fact).date()
            return max(0, (fday - pday).days)
        except Exception:
            pass
    return max(0, (today - pday).days)


def _late_days_contractor(row, today: date) -> int | None:
    dog_end = row.get("_dog_end")
    if dog_end is not None and not pd.isna(dog_end):
        try:
            ed = pd.Timestamp(dog_end).normalize()
            recv = row.get("_dog_recv")
            if recv is not None and not pd.isna(recv):
                rd = pd.Timestamp(recv).normalize()
                return max(0, int((rd - ed).days))
            today_n = pd.Timestamp(today)
            return max(0, int((today_n - ed).days))
        except Exception:
            pass
    return _late_days_plan(row.get("_plan"), row.get("_accept"), today)


def _bucket_counts(days_list: list[int | None]) -> dict[str, int]:
    b07 = b830 = b30 = 0
    for d in days_list:
        if d is None:
            continue
        if d <= 7:
            b07 += 1
        elif d <= 30:
            b830 += 1
        else:
            b30 += 1
    return {"bucket_0_7": b07, "bucket_8_30": b830, "bucket_30_plus": b30}


def build_executive_docs_payload(
    *,
    project: str | None = None,
    contractor: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    granularity: str = "month",
    hide_overdue_if_signed: bool = True,
) -> dict[str, Any]:
    id_path = _richest_tessa_id()
    if id_path is None:
        return _empty_payload("Не найдены файлы tessa_*-id.csv")

    task_path = _matching_task(id_path)
    dog_path = _latest_json("_Dogovor.json")
    base = _load_base_frame(
        _paths_sig(id_path),
        _paths_sig(task_path),
        _paths_sig(dog_path),
    )
    if base is None or base.empty:
        return _empty_payload(
            "Нет строк ИД после исключения предписаний/проекта",
            source=id_path.name,
        )

    projects = sorted(
        {
            str(x).strip()
            for x in base.get("ObjectName", pd.Series(dtype=str)).dropna().unique()
            if str(x).strip()
        },
        key=str.casefold,
    )
    contractors = sorted(
        {
            str(x).strip()
            for x in base.get("CONTR", pd.Series(dtype=str)).dropna().unique()
            if str(x).strip()
        },
        key=str.casefold,
    )
    issue = base["_cd"]
    date_min = issue.min()
    date_max = issue.max()
    date_min_s = date_min.strftime("%Y-%m-%d") if pd.notna(date_min) else None
    date_max_s = date_max.strftime("%Y-%m-%d") if pd.notna(date_max) else None

    view = base
    if project and project not in ("Все", ""):
        view = view[view["ObjectName"].astype(str).str.strip() == project]
    if contractor and contractor not in ("Все", ""):
        view = view[view["CONTR"].astype(str).str.strip() == contractor]

    # Cumulative KPIs/charts: ignore period (Streamlit filtered_cumulative)
    cum = view.copy()

    # Period filter for dynamics + optional detail narrowing:
    # Streamlit uses period only for dynamics tab via filtered_period;
    # cumulative cards use all dates. We apply period to dynamics only,
    # but also expose period-filtered rows if dates set (practical UX).
    period = view.copy()
    if date_from is not None:
        period = period[period["_cd"].isna() | (period["_cd"] >= pd.Timestamp(date_from))]
    if date_to is not None:
        period = period[
            period["_cd"].isna()
            | (period["_cd"] < pd.Timestamp(date_to) + pd.Timedelta(days=1))
        ]

    # Use period view for table when dates applied, else cumulative
    table_src = period if (date_from is not None or date_to is not None) else cum
    # KPIs always on cumulative (project/contractor filtered)
    filtered = cum

    stu = filtered["_status"].astype(str)
    is_on_agree = stu.str.strip().str.casefold().eq("на согласовании")
    is_rework = stu.str.strip().str.casefold().eq("на доработке")
    is_declined = stu.str.strip().str.casefold().eq("отказ")
    is_signed = stu.str.strip().str.casefold().eq("подписан")
    if "KrStateID" in filtered.columns:
        is_signed = is_signed | (
            pd.to_numeric(filtered["KrStateID"], errors="coerce").eq(8)
        )
    is_signed = is_signed & (~is_on_agree)

    overdue_mask = (~is_signed) & (~is_declined)
    cnt_c = int((overdue_mask & is_rework).sum())
    cnt_u = int((overdue_mask & is_on_agree).sum())
    total_docs = (
        int(filtered["DocID"].nunique())
        if "DocID" in filtered.columns
        else int(len(filtered))
    )

    today = date.today()
    sub_c = filtered.loc[overdue_mask & is_rework]
    late_c = [_late_days_contractor(r, today) for _, r in sub_c.iterrows()] if len(sub_c) else []
    buckets_c = _bucket_counts(late_c)

    sub_u = filtered.loc[overdue_mask & is_on_agree]
    late_u = [
        _late_days_plan(r.get("_plan"), r.get("_accept"), today) for _, r in sub_u.iterrows()
    ] if len(sub_u) else []
    buckets_u = _bucket_counts(late_u)

    # Charts
    by_status: list[dict[str, Any]] = []
    if len(filtered):
        vc = filtered["_status"].astype(str).str.strip().replace({"": "—"}).value_counts()
        n = max(int(len(filtered)), 1)
        for status, cnt in vc.items():
            by_status.append(
                {
                    "status": str(status),
                    "count": int(cnt),
                    "share_pct": round(100.0 * int(cnt) / n, 1),
                }
            )

    by_object: list[dict[str, Any]] = []
    if len(filtered) and "ObjectName" in filtered.columns:
        vc = (
            filtered["ObjectName"]
            .astype(str)
            .str.strip()
            .replace({"": "—"})
            .value_counts()
            .head(20)
        )
        for obj, cnt in vc.items():
            by_object.append({"object": str(obj), "count": int(cnt)})

    overdue_contractor: list[dict[str, Any]] = []
    if cnt_c and "CONTR" in filtered.columns:
        g = (
            filtered.loc[overdue_mask & is_rework]
            .assign(_c=lambda d: d["CONTR"].astype(str).str.strip().replace({"": "—"}))
            .groupby("_c")
            .size()
            .reset_index(name="count")
            .sort_values("count", ascending=False)
        )
        for _, r in g.head(20).iterrows():
            overdue_contractor.append(
                {"contractor": str(r["_c"]), "count": int(r["count"])}
            )

    overdue_customer: list[dict[str, Any]] = []
    if cnt_u and "CONTR" in filtered.columns:
        g = (
            filtered.loc[overdue_mask & is_on_agree]
            .assign(_c=lambda d: d["CONTR"].astype(str).str.strip().replace({"": "—"}))
            .groupby("_c")
            .size()
            .reset_index(name="count")
            .sort_values("count", ascending=False)
        )
        for _, r in g.head(20).iterrows():
            overdue_customer.append(
                {"contractor": str(r["_c"]), "count": int(r["count"])}
            )

    # Dynamics from period view
    gran = (granularity or "month").strip().lower()
    if gran not in _GRANULARITY_MAP:
        gran = "month"
    freq = _GRANULARITY_MAP[gran]
    dynamics: list[dict[str, Any]] = []
    dyn_src = period if len(period) else filtered
    if "_cd" in dyn_src.columns and dyn_src["_cd"].notna().any():
        try:
            dyn = dyn_src.assign(_m=dyn_src["_cd"].dt.to_period(freq))
        except Exception:
            dyn = dyn_src.assign(_m=dyn_src["_cd"].dt.to_period("M"))
            gran = "month"
        dyn = dyn[dyn["_m"].notna()]
        if not dyn.empty:
            cnt = dyn.groupby("_m", sort=True).size().reset_index(name="new_docs")
            for _, r in cnt.iterrows():
                p = r["_m"]
                dynamics.append(
                    {
                        "period": _period_label(p) if isinstance(p, pd.Period) else str(p),
                        "new_docs": int(r["new_docs"]),
                    }
                )

    # Detail table: exclude signed
    stu_t = table_src["_status"].astype(str)
    is_signed_t = stu_t.str.strip().str.casefold().eq("подписан")
    if "KrStateID" in table_src.columns:
        is_signed_t = is_signed_t | (
            pd.to_numeric(table_src["KrStateID"], errors="coerce").eq(8)
        )
    is_on_agree_t = stu_t.str.strip().str.casefold().eq("на согласовании")
    is_signed_t = is_signed_t & (~is_on_agree_t)
    disp = table_src.loc[~is_signed_t].copy()
    disp = disp.sort_values("_cd", ascending=False, na_position="last")

    rows: list[dict[str, Any]] = []
    for _, r in disp.iterrows():
        st_l = str(r.get("_status") or "")
        st_low = st_l.casefold()
        transitional = ("на согласовани" in st_low) or ("на подписани" in st_low)
        signed_row = (
            any(x in st_low for x in ("подписан", "согласован", "принят"))
            and not transitional
        )
        hide_ov = bool(hide_overdue_if_signed) and signed_row

        plan_dt = r.get("_plan")
        fact_dt = r.get("_accept")
        transfer_dt = r.get("_transfer")
        agree_dt = None  # no agree column in id.csv typically

        submit_late: int | None = None
        agree_late: int | None = None
        if not hide_ov:
            submit_late = _late_days_plan(plan_dt, fact_dt, today)
            if transfer_dt is not None and not pd.isna(transfer_dt):
                try:
                    t1 = pd.Timestamp(transfer_dt).date()
                    if agree_dt is not None and not pd.isna(agree_dt):
                        agree_late = max(0, (pd.Timestamp(agree_dt).date() - t1).days)
                    else:
                        agree_late = max(0, (today - t1).days)
                except Exception:
                    agree_late = None

        rows.append(
            {
                "contractor": str(r.get("CONTR") or "—").strip() or "—",
                "project": str(r.get("ObjectName") or "—").strip() or "—",
                "doc_number": str(r.get("DocNumber") or r.get("DocID") or "—").strip()
                or "—",
                "kind": str(r.get("KindName") or "—").strip() or "—",
                "plan_date": _fmt_date(plan_dt),
                "fact_date": _fmt_date(fact_dt),
                "submit_late_days": None if hide_ov else submit_late,
                "transfer_date": _fmt_date(transfer_dt),
                "agree_date": _fmt_date(agree_dt),
                "agree_late_days": None if hide_ov else agree_late,
                "status": st_l or "—",
                "creation_date": _fmt_date(r.get("_cd")),
            }
        )

    return {
        "meta": {
            "rows": int(len(filtered)),
            "table_rows": len(rows),
            "data_mode": DATA_MODE,
            "source": id_path.name,
            "task_source": task_path.name if task_path else None,
            "warning": None,
            "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        },
        "filters": {
            "projects": ["Все", *projects],
            "contractors": ["Все", *contractors],
            "date_min": date_min_s,
            "date_max": date_max_s,
            "granularities": [
                {"id": k, "label": v} for k, v in _GRANULARITY_LABELS.items()
            ],
            "applied": {
                "project": project or "Все",
                "contractor": contractor or "Все",
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
                "granularity": gran,
                "hide_overdue_if_signed": hide_overdue_if_signed,
            },
        },
        "kpis": {
            "total_docs": total_docs,
            "declined": int(is_declined.sum()),
            "on_agree": int(is_on_agree.sum()),
            "signed": int(is_signed.sum()),
            "on_rework": int(is_rework.sum()),
            "overdue_total": int(cnt_c + cnt_u),
            "contractor_overdue": {"count": cnt_c, **buckets_c},
            "customer_overdue": {"count": cnt_u, **buckets_u},
        },
        "tremor": {
            "by_status": by_status,
            "by_object": by_object,
            "overdue_contractor": overdue_contractor,
            "overdue_customer": overdue_customer,
            "dynamics": dynamics,
        },
        "rows": rows,
    }
