from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from app.config import DATA_MODE, WEB_DATA_DIR

_DATE_RE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")


def _finite(v: Any) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 0.0
    return x if math.isfinite(x) else 0.0


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
    # tessa_29-07-2026-00-00-id.csv → tessa_29-07-2026*-task.csv
    parts = id_path.name.split("_", 1)
    if len(parts) < 2:
        return None
    date_tok = "-".join(parts[1].split("-")[:3])
    candidates = list(WEB_DATA_DIR.glob(f"tessa_{date_tok}*-task.csv"))
    if not candidates:
        candidates = list(WEB_DATA_DIR.glob("tessa_*-task.csv"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: ( _file_date_key(p.name), p.stat().st_mtime))


def _latest_json(suffix: str) -> Path | None:
    if not WEB_DATA_DIR.is_dir():
        return None
    files = list(WEB_DATA_DIR.glob(f"*{suffix}"))
    if not files:
        return None
    return max(files, key=lambda p: (_file_date_key(p.name), p.stat().st_mtime))


def _dogovor_number_lookup(path: Path | None) -> dict[str, str]:
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
    out: dict[str, str] = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        did = str(row.get("ID_Договора") or row.get("ID_Договор") or "").strip().lower()
        num = str(row.get("Номер_Договора") or row.get("Номер_договора") or "").strip()
        if did and num:
            out[did] = num
    return out


@lru_cache(maxsize=4)
def _load_base_frame(id_sig: tuple, task_sig: tuple, dog_sig: tuple) -> pd.DataFrame:
    id_path = Path(id_sig[0])
    df = _read_csv(id_path)
    if df.empty or "KindName" not in df.columns:
        return pd.DataFrame()

    pred = df[df["KindName"].astype(str).str.strip().str.casefold().eq("предписания")].copy()
    if pred.empty:
        return pred

    # Drop «Проект»
    if "KrStateID" in pred.columns:
        kr = pd.to_numeric(pred["KrStateID"], errors="coerce")
        pred = pred[kr.fillna(-1) != 0]
    if "KrState" in pred.columns:
        pred = pred[
            ~pred["KrState"].astype(str).str.strip().str.casefold().isin({"проект", "project"})
        ]

    # Require object/project
    if "ObjectName" in pred.columns:
        pred = pred[
            pred["ObjectName"].notna()
            & ~pred["ObjectName"].astype(str).str.strip().isin(["", "nan", "None", "NaN"])
        ]

    # Dedupe by DocID keep latest CreationDate
    if "DocID" in pred.columns:
        if "CreationDate" in pred.columns:
            pred["_cd"] = _to_dt(pred["CreationDate"])
            pred = pred.sort_values("_cd", na_position="last")
        pred = pred.drop_duplicates(subset=["DocID"], keep="last")

    pred["_resolved"] = False
    if "KrStateID" in pred.columns:
        pred["_resolved"] = pd.to_numeric(pred["KrStateID"], errors="coerce") == 13

    pred["_status"] = pred["KrState"].astype(str).str.strip() if "KrState" in pred.columns else ""
    pred.loc[pred["_resolved"], "_status"] = "Снято"

    # Task completion: Проверка + Принято
    completion_by_card: dict[str, pd.Timestamp] = {}
    if task_sig:
        try:
            tdf = _read_csv(Path(task_sig[0]))
            if not tdf.empty:
                type_ok = (
                    tdf["TypeCaption"].astype(str).str.contains("Проверка", case=False, na=False)
                    if "TypeCaption" in tdf.columns
                    else pd.Series(False, index=tdf.index)
                )
                opt_ok = (
                    tdf["OptionCaption"].astype(str).str.contains("Принято", case=False, na=False)
                    if "OptionCaption" in tdf.columns
                    else pd.Series(False, index=tdf.index)
                )
                done = tdf[type_ok & opt_ok].copy()
                if "Completed" in done.columns and "CardID" in done.columns:
                    done["_c"] = _to_dt(done["Completed"])
                    for _, r in done.dropna(subset=["_c"]).iterrows():
                        cid = str(r.get("CardID") or "").strip().lower()
                        if cid:
                            prev = completion_by_card.get(cid)
                            ts = r["_c"]
                            if prev is None or ts > prev:
                                completion_by_card[cid] = ts
        except Exception:
            pass

    pred["_completion_dt"] = pd.NaT
    if "DocID" in pred.columns:
        for idx, row in pred.iterrows():
            if not bool(row.get("_resolved")):
                continue
            for key in ("DocID", "CardID", "CardId"):
                if key not in pred.columns:
                    continue
                cid = str(row.get(key) or "").strip().lower()
                if cid and cid in completion_by_card:
                    pred.at[idx, "_completion_dt"] = completion_by_card[cid]
                    break

    pred["_issue_dt"] = _to_dt(pred["CreationDate"]) if "CreationDate" in pred.columns else pd.NaT
    pred["_due"] = _to_dt(pred["id_Deadline"]) if "id_Deadline" in pred.columns else pd.NaT

    today = date.today()

    def _overdue_days(r) -> int:
        due = r.get("_due")
        if due is None or pd.isna(due):
            return 0
        try:
            d_due = pd.Timestamp(due).date()
        except Exception:
            return 0
        if bool(r.get("_resolved")):
            comp = r.get("_completion_dt")
            if comp is None or pd.isna(comp):
                return 0
            try:
                d_comp = pd.Timestamp(comp).date()
            except Exception:
                return 0
            return max(0, (d_comp - d_due).days)
        if today > d_due:
            return (today - d_due).days
        return 0

    pred["_overdue_days"] = pred.apply(_overdue_days, axis=1)
    pred["_overdue_open"] = (~pred["_resolved"].astype(bool)) & (pred["_overdue_days"] > 0)

    teg = pred["Tessa_Teg"].astype(str) if "Tessa_Teg" in pred.columns else pd.Series("", index=pred.index)
    teg_cf = teg.str.casefold()
    pred["_critical"] = teg_cf.str.contains("критич", na=False)
    pred["_stop_work"] = teg_cf.str.contains("приостанов", na=False) | teg_cf.str.contains(
        "остановк", na=False
    )

    # Contract number from Dogovor
    dog_map = _dogovor_number_lookup(Path(dog_sig[0]) if dog_sig else None)
    if "1C_ID_DOG" in pred.columns and dog_map:
        pred["_contract_no"] = pred["1C_ID_DOG"].map(
            lambda v: dog_map.get(str(v or "").strip().lower(), str(v or "").strip())
        )
    elif "1C_ID_DOG" in pred.columns:
        pred["_contract_no"] = pred["1C_ID_DOG"].astype(str)
    else:
        pred["_contract_no"] = ""

    return pred.reset_index(drop=True)


def clear_prescriptions_caches() -> None:
    _load_base_frame.cache_clear()


def _paths_sig(path: Path | None) -> tuple:
    if path is None or not path.is_file():
        return tuple()
    st = path.stat()
    return (str(path.resolve()), st.st_mtime_ns, st.st_size)


def build_prescriptions_payload(
    *,
    project: str | None = None,
    contractor: str | None = None,
    contract_q: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    hide_resolved: bool = False,
) -> dict[str, Any]:
    id_path = _richest_tessa_id()
    if id_path is None:
        return {
            "meta": {
                "rows": 0,
                "data_mode": DATA_MODE,
                "source": None,
                "warning": "Не найдены файлы tessa_*-id.csv",
            },
            "filters": {
                "projects": ["Все"],
                "contractors": ["Все"],
                "date_min": None,
                "date_max": None,
                "applied": {},
            },
            "kpis": {
                "total": 0,
                "resolved": 0,
                "unresolved": 0,
                "non_overdue": 0,
                "overdue_unresolved": 0,
                "critical": 0,
                "stop_work": 0,
            },
            "tremor": {"by_contractor": [], "by_status": []},
            "rows": [],
        }

    task_path = _matching_task(id_path)
    dog_path = _latest_json("_Dogovor.json")
    pred = _load_base_frame(
        _paths_sig(id_path),
        _paths_sig(task_path),
        _paths_sig(dog_path),
    )

    empty_kpis = {
        "total": 0,
        "resolved": 0,
        "unresolved": 0,
        "non_overdue": 0,
        "overdue_unresolved": 0,
        "critical": 0,
        "stop_work": 0,
    }
    if pred is None or pred.empty:
        return {
            "meta": {
                "rows": 0,
                "data_mode": DATA_MODE,
                "source": id_path.name,
                "warning": "Нет строк KindName=Предписания",
            },
            "filters": {
                "projects": ["Все"],
                "contractors": ["Все"],
                "date_min": None,
                "date_max": None,
                "applied": {},
            },
            "kpis": empty_kpis,
            "tremor": {"by_contractor": [], "by_status": []},
            "rows": [],
        }

    projects = sorted(
        {
            str(x).strip()
            for x in pred.get("ObjectName", pd.Series(dtype=str)).dropna().unique()
            if str(x).strip()
        },
        key=str.casefold,
    )
    contractors = sorted(
        {
            str(x).strip()
            for x in pred.get("CONTR", pd.Series(dtype=str)).dropna().unique()
            if str(x).strip()
        },
        key=str.casefold,
    )

    issue = pred["_issue_dt"]
    date_min = issue.min()
    date_max = issue.max()
    date_min_s = date_min.strftime("%Y-%m-%d") if pd.notna(date_min) else None
    date_max_s = date_max.strftime("%Y-%m-%d") if pd.notna(date_max) else None

    view = pred
    if project and project not in ("Все", ""):
        view = view[view["ObjectName"].astype(str).str.strip() == project]
    if contractor and contractor not in ("Все", ""):
        view = view[view["CONTR"].astype(str).str.strip() == contractor]
    if contract_q and str(contract_q).strip():
        q = str(contract_q).strip().casefold()
        view = view[view["_contract_no"].astype(str).str.casefold().str.contains(q, na=False)]
    if date_from is not None:
        view = view[view["_issue_dt"].isna() | (view["_issue_dt"] >= pd.Timestamp(date_from))]
    if date_to is not None:
        view = view[
            view["_issue_dt"].isna()
            | (view["_issue_dt"] < pd.Timestamp(date_to) + pd.Timedelta(days=1))
        ]
    if hide_resolved:
        view = view[~view["_resolved"].astype(bool)]

    view = view.copy()
    total = int(len(view))
    resolved = int(view["_resolved"].astype(bool).sum()) if total else 0
    unresolved = total - resolved
    overdue_unresolved = int(view["_overdue_open"].astype(bool).sum()) if total else 0
    non_overdue = total - overdue_unresolved
    critical = int(view["_critical"].astype(bool).sum()) if total else 0
    stop_work = int(view["_stop_work"].astype(bool).sum()) if total else 0

    # Charts
    by_contractor: list[dict[str, Any]] = []
    if total and "CONTR" in view.columns:
        g = (
            view.assign(_c=view["CONTR"].astype(str).str.strip().replace({"": "—"}))
            .groupby("_c", dropna=False)
            .agg(total=("_c", "size"), overdue=("_overdue_open", "sum"))
            .reset_index()
            .sort_values("total", ascending=False)
        )
        for _, r in g.head(20).iterrows():
            by_contractor.append(
                {
                    "contractor": str(r["_c"]),
                    "total": int(r["total"]),
                    "overdue": int(r["overdue"]),
                }
            )

    by_status: list[dict[str, Any]] = []
    if total:
        vc = view["_status"].astype(str).str.strip().replace({"": "—"}).value_counts()
        for status, cnt in vc.items():
            by_status.append(
                {
                    "status": str(status),
                    "count": int(cnt),
                    "share_pct": round(100.0 * int(cnt) / max(total, 1), 1),
                }
            )

    # Table rows — sort critical+overdue first
    view = view.assign(
        _sort_key=(
            view["_critical"].astype(int) * 2 + view["_overdue_open"].astype(int)
        )
    ).sort_values(["_sort_key", "_overdue_days"], ascending=[False, False])

    rows: list[dict[str, Any]] = []
    for _, r in view.iterrows():
        rows.append(
            {
                "status": str(r.get("_status") or "—"),
                "contractor": str(r.get("CONTR") or "—").strip() or "—",
                "project": str(r.get("ObjectName") or "—").strip() or "—",
                "contract_no": str(r.get("_contract_no") or "—").strip() or "—",
                "doc_number": str(r.get("DocNumber") or "—").strip() or "—",
                "pred_number": str(r.get("InternalID") or "—").strip() or "—",
                "name": str(r.get("Name") or "—").strip() or "—",
                "issue_date": _fmt_date(r.get("_issue_dt")),
                "issue_block": str(r.get("Comment") or "—").strip() or "—",
                "due_date": _fmt_date(r.get("_due")),
                "completion_date": _fmt_date(r.get("_completion_dt")),
                "overdue_days": int(_finite(r.get("_overdue_days"))),
                "critical": bool(r.get("_critical")),
                "stop_work": bool(r.get("_stop_work")),
            }
        )

    return {
        "meta": {
            "rows": total,
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
            "applied": {
                "project": project or "Все",
                "contractor": contractor or "Все",
                "contract_q": contract_q or "",
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
                "hide_resolved": hide_resolved,
            },
        },
        "kpis": {
            "total": total,
            "resolved": resolved,
            "unresolved": unresolved,
            "non_overdue": non_overdue,
            "overdue_unresolved": overdue_unresolved,
            "critical": critical,
            "stop_work": stop_work,
        },
        "tremor": {
            "by_contractor": by_contractor,
            "by_status": by_status,
        },
        "rows": rows,
    }
