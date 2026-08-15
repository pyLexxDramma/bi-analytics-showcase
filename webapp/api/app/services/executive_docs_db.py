"""Исполнительная документация — паритет с dashboard_executive_documentation из web_data.db."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

import numpy as np
import pandas as pd

from app.config import DATA_MODE
from app.services.core_bridge import (
    active_version_id,
    import_dashboard_module,
    load_version_df,
    prepare_web_db,
    session_state,
)
from app.services.project_scope import applied_project_label, resolve_selected_projects

GRANULARITIES = {
    "day": ("День", "D"),
    "week": ("Неделя", "W-MON"),
    "month": ("Месяц", "M"),
    "quarter": ("Квартал", "Q-DEC"),
    "year": ("Год", "Y-DEC"),
}


def _empty(warning: str | None = None) -> dict[str, Any]:
    return {
        "meta": {
            "rows": 0,
            "table_rows": 0,
            "version_id": None,
            "data_mode": DATA_MODE,
            "source": "web_data.db",
            "parity": "main_dashboard_executive_documentation",
            "warning": warning,
        },
        "filters": {
            "projects": ["Все"],
            "contractors": ["Все"],
            "doc_kinds": ["Все"],
            "catalog": [],
            "date_min": None,
            "date_max": None,
            "granularities": [{"id": k, "label": v[0]} for k, v in GRANULARITIES.items()],
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


def _text(value: Any, empty: str = "—") -> str:
    text = str(value or "").strip()
    return empty if not text or text.casefold() in {"nan", "none", "nat", "<na>"} else text


def _fmt_date(value: Any) -> str | None:
    ts = pd.to_datetime(value, errors="coerce")
    return ts.strftime("%d.%m.%Y") if pd.notna(ts) else None


def _naive_norm(ts: Any) -> pd.Timestamp:
    if ts is None or (isinstance(ts, float) and pd.isna(ts)) or pd.isna(ts):
        return pd.NaT
    try:
        t = pd.Timestamp(ts)
    except Exception:
        return pd.NaT
    if getattr(t, "tzinfo", None) is not None:
        try:
            t = t.tz_convert("UTC").tz_localize(None)
        except Exception:
            try:
                t = t.tz_localize(None)
            except Exception:
                return pd.NaT
    try:
        return t.normalize()
    except Exception:
        return pd.NaT


def _series_datetime(frame: pd.DataFrame, col: str | None) -> pd.Series:
    if not col or col not in frame.columns:
        return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")
    return pd.to_datetime(frame[col], errors="coerce")


def _buckets(values: pd.Series) -> dict[str, int]:
    vals = pd.to_numeric(values, errors="coerce")
    return {
        "bucket_0_7": int(((vals >= 0) & (vals <= 7)).sum()),
        "bucket_8_30": int(((vals > 7) & (vals <= 30)).sum()),
        "bucket_30_plus": int((vals > 30).sum()),
    }


def _status_chip(status: str) -> str:
    s = str(status or "").strip().casefold()
    if s == "на согласовании":
        return "customer"
    if s == "на доработке":
        return "contractor"
    if s in {"подписан", "согласован"}:
        return "accepted"
    if s == "отказ":
        return "declined"
    return "neutral"


def _status_display(status: str) -> str:
    s = str(status or "").strip().casefold()
    if s == "на согласовании":
        return "У Заказчика"
    if s == "на доработке":
        return "У Подрядчика"
    if s in {"подписан", "согласован"}:
        return "Принято"
    if s == "отказ":
        return "Отказ"
    return _text(status)


def _late_days_plan(plan: Any, fact: Any, today: date) -> Optional[int]:
    p = _naive_norm(plan)
    if pd.isna(p):
        return None
    f = _naive_norm(fact)
    end = f if not pd.isna(f) else _naive_norm(pd.Timestamp(today))
    if pd.isna(end):
        return None
    return max(0, int((end - p).days))


def _contractor_late_days(row: pd.Series, today: date) -> float:
    end = _naive_norm(row.get("_end"))
    if not pd.isna(end):
        recv = _naive_norm(row.get("_recv"))
        if not pd.isna(recv):
            return float(max(0, (recv - end).days))
        today_n = _naive_norm(pd.Timestamp(today))
        if not pd.isna(today_n):
            return float(max(0, (today_n - end).days))
    base = _late_days_plan(row.get("_plan"), row.get("_fact"), today)
    return float(base) if base is not None else np.nan


def build_executive_docs_payload(
    *,
    project: str | None = None,
    contractor: str | None = None,
    doc_kind: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    granularity: str = "month",
    hide_overdue_if_signed: bool = True,
) -> dict[str, Any]:
    try:
        prepare_web_db()
        version_id = active_version_id()
        if not version_id:
            return _empty("Нет active version_id в web_data.db")
        renderer = import_dashboard_module("_renderers")
        work = load_version_df(int(version_id), "tessa")
        tasks = load_version_df(int(version_id), "tessa_tasks")
        session_state()["tessa_tasks_data"] = (
            tasks if tasks is not None else pd.DataFrame()
        )
        if work is None or work.empty:
            return _empty("Нет TESSA в active version web_data.db")

        work = work.copy()
        work.columns = [str(c).strip() for c in work.columns]
        try:
            from web_loader import _tessa_drop_cancelled_tag_rows  # type: ignore

            work = _tessa_drop_cancelled_tag_rows(work)
        except Exception:
            pass
        work = renderer._tessa_fill_card_from_doc_lookup(work)

        kind = renderer._tessa_find_column(work, ["KindName", "kindname", "Вид"])
        obj = renderer._tessa_find_column(
            work, ["ObjectName", "objectname", "Объект", "ProjectName", "Проект"]
        )
        if not kind or not obj:
            return _empty("В TESSA нет полей вида документа или объекта")

        mask_id = pd.Series(False, index=work.index)
        if "KrStateID" in work.columns:
            mask_id = mask_id | work["KrStateID"].notna()
        mask_id = mask_id | (
            work[kind].notna()
            & ~work[kind].astype(str).str.strip().isin(["", "nan", "None", "NaN"])
        )
        work = work[mask_id].copy()
        work = work[
            ~work[kind].astype(str).str.contains("Предписан", case=False, na=False)
        ].copy()
        work = work[
            work[obj].notna()
            & ~work[obj].astype(str).str.strip().isin(["", "nan", "None", "NaN"])
        ].copy()
        if work.empty:
            payload = _empty("Нет строк ИД после исключения предписаний")
            payload["meta"]["version_id"] = version_id
            return payload

        work = renderer._exec_enrich_task_and_contract_dates(work)
        work["Статус"] = renderer._tessa_resolve_status_series(work)
        work = renderer._tessa_drop_project_state_rows(work)
        lookup, _, _ = renderer._pred_projekts_1c_lookup()
        if lookup:
            work[obj] = renderer._resolve_project_display_labels(work[obj], lookup)
        work = renderer._pred_filter_by_projekts_registry(work, obj)
        exclude = getattr(renderer, "MSP_PROJECT_FILTER_EXCLUDE_NAMES", frozenset())
        if exclude:
            work = work[
                ~work[obj].astype(str).str.strip().isin(exclude)
            ].reset_index(drop=True)
        if work.empty:
            payload = _empty("Нет строк ИД после фильтра Projekts")
            payload["meta"]["version_id"] = version_id
            return payload

        contr = renderer._tessa_find_column(work, ["CONTR", "Контрагент", "contr"])
        card = renderer._tessa_find_column(
            work, ["CardId", "CardID", "cardId", "DocID", "DocId"]
        )
        created = renderer._tessa_find_column(
            work, ["CreationDate", "creationdate", "Дата создания"]
        )
        plan = renderer._tessa_find_column(
            work, ["id_Deadline", "id_deadline", "PlanDate", "DueDate", "Deadline"]
        )
        completed = renderer._tessa_find_column(
            work, ["Completed", "CompletionDate", "Дата завершения"]
        )
        doc_num = renderer._tessa_find_column(
            work, ["DocNumber", "DocumentNumber", "НомерДокумента"]
        )

        work["_cd"] = _series_datetime(work, created)
        work["_plan"] = _series_datetime(work, plan)
        fact_task = (
            pd.to_datetime(work["_exec_accept_print_dt"], errors="coerce")
            if "_exec_accept_print_dt" in work.columns
            else pd.Series(pd.NaT, index=work.index)
        )
        fact_base = _series_datetime(work, completed)
        work["_fact"] = fact_task.combine_first(fact_base)
        work["_transfer"] = (
            pd.to_datetime(work["_exec_transfer_customer_dt"], errors="coerce")
            if "_exec_transfer_customer_dt" in work.columns
            else pd.Series(pd.NaT, index=work.index)
        )
        work["_end"] = (
            pd.to_datetime(work["_dog_contract_end_dt"], errors="coerce")
            if "_dog_contract_end_dt" in work.columns
            else pd.Series(pd.NaT, index=work.index)
        )
        work["_recv"] = (
            pd.to_datetime(work["_dog_id_received_dt"], errors="coerce")
            if "_dog_id_received_dt" in work.columns
            else pd.Series(pd.NaT, index=work.index)
        )

        catalog = renderer._EXEC_DOC_KINDS_DEFAULT.copy()
        view = work.copy()
        projects_opts = sorted(
            {
                str(v).strip()
                for v in (work[obj].tolist() if obj else [])
                if str(v).strip() and str(v).strip().casefold() not in {"nan", "none", ""}
            },
            key=str.casefold,
        ) if obj else []
        selected_projects = resolve_selected_projects(project, ["Все", *projects_opts])
        applied_project = applied_project_label(selected_projects)
        if selected_projects and obj:
            view = view[view[obj].astype(str).str.strip().isin(selected_projects)]
        if contractor and contractor != "Все" and contr:
            view = view[view[contr].astype(str).str.strip().eq(contractor)]
        if doc_kind and doc_kind != "Все":
            names = renderer._exec_doc_kind_names_for_filter_label(doc_kind, catalog)
            view = view[view[kind].astype(str).str.strip().isin(names)]

        sort_cols: list[str] = []
        if "Import_data" in view.columns:
            view = view.copy()
            view["_imp"] = pd.to_datetime(view["Import_data"], errors="coerce")
            sort_cols.append("_imp")
        sort_cols.append("_cd")
        if card and card in view.columns:
            cumulative = (
                view.sort_values(sort_cols, kind="stable", na_position="last")
                .drop_duplicates(card, keep="last")
                .reset_index(drop=True)
            )
        else:
            cumulative = view.reset_index(drop=True)

        if cumulative.empty:
            payload = _empty("Нет документов при выбранных фильтрах")
            payload["meta"]["version_id"] = version_id
            return payload

        status = cumulative["Статус"].astype(str).str.strip()
        low = status.str.casefold()
        agree = low.eq("на согласовании")
        rework = low.eq("на доработке")
        declined = low.eq("отказ")
        signed = low.eq("подписан")
        if "KrStateID" in cumulative.columns:
            signed = signed | pd.to_numeric(
                cumulative["KrStateID"], errors="coerce"
            ).eq(8)
        signed = signed & ~agree
        overdue = (~signed) & (~declined)
        today = date.today()

        contractor_mask = overdue & rework
        customer_mask = overdue & agree
        sub_c = cumulative.loc[contractor_mask].copy()
        sub_u = cumulative.loc[customer_mask].copy()
        if not sub_c.empty:
            sub_c["_late_days"] = sub_c.apply(
                lambda r: _contractor_late_days(r, today), axis=1
            )
        else:
            sub_c["_late_days"] = pd.Series(dtype=float)
        if not sub_u.empty:
            sub_u["_late_days"] = sub_u.apply(
                lambda r: _late_days_plan(r.get("_plan"), r.get("_fact"), today),
                axis=1,
            )
        else:
            sub_u["_late_days"] = pd.Series(dtype=float)

        def _group(mask: pd.Series) -> list[dict[str, Any]]:
            if not contr or not bool(mask.any()):
                return []
            counts = (
                cumulative.loc[mask, contr]
                .map(_text)
                .value_counts()
                .head(30)
            )
            return [
                {"contractor": str(name), "count": int(value)}
                for name, value in counts.items()
            ]

        gran = granularity if granularity in GRANULARITIES else "month"
        # Dynamics: main uses cumulative (period filter unused for digits)
        dyn_src = cumulative.dropna(subset=["_cd"]).copy()
        if date_from:
            dyn_src = dyn_src[dyn_src["_cd"] >= pd.Timestamp(date_from)]
        if date_to:
            dyn_src = dyn_src[
                dyn_src["_cd"] < pd.Timestamp(date_to) + pd.Timedelta(days=1)
            ]
        dynamics: list[dict[str, Any]] = []
        if not dyn_src.empty:
            period_code = GRANULARITIES[gran][1]
            grouped = (
                dyn_src.assign(_period=dyn_src["_cd"].dt.to_period(period_code))
                .groupby("_period", sort=True)
                .size()
            )
            for key, value in grouped.items():
                try:
                    label = renderer._exec_period_human_label(key)
                except Exception:
                    label = str(key)
                dynamics.append({"period": label, "new_docs": int(value)})

        rows: list[dict[str, Any]] = []
        detail = cumulative.loc[~signed].copy()
        detail = detail.sort_values("_cd", ascending=False, kind="stable")
        for _, row in detail.iterrows():
            submit_late = _late_days_plan(row.get("_plan"), row.get("_fact"), today)
            agree_late = None
            if pd.notna(row.get("_transfer")):
                agree_late = _late_days_plan(row.get("_transfer"), None, today)
            if hide_overdue_if_signed and bool(signed.loc[row.name]):
                submit_late = None
                agree_late = None
            raw_status = _text(row.get("Статус"))
            rows.append(
                {
                    "contractor": _text(row.get(contr)) if contr else "—",
                    "project": _text(row.get(obj)),
                    "doc_number": _text(
                        row.get(doc_num) if doc_num else row.get("DocID")
                    ),
                    "kind": _text(row.get(kind)),
                    "plan_date": _fmt_date(row.get("_plan")),
                    "fact_date": _fmt_date(row.get("_fact")),
                    "submit_late_days": submit_late,
                    "transfer_date": _fmt_date(row.get("_transfer")),
                    "agree_date": None,
                    "agree_late_days": agree_late,
                    "status": raw_status,
                    "status_display": _status_display(raw_status),
                    "status_chip": _status_chip(raw_status),
                    "creation_date": _fmt_date(row.get("_cd")),
                }
            )

        catalog_df = renderer._exec_doc_kinds_catalog_display(
            cumulative, kind, catalog
        ).fillna("")
        issue_min = cumulative["_cd"].min()
        issue_max = cumulative["_cd"].max()
        projects = sorted(
            {_text(x, "") for x in cumulative[obj] if _text(x, "")},
            key=str.casefold,
        )
        contractors = (
            sorted(
                {_text(x, "") for x in cumulative[contr] if _text(x, "")},
                key=str.casefold,
            )
            if contr
            else []
        )
        total_docs = (
            int(cumulative[card].nunique()) if card and card in cumulative.columns else len(cumulative)
        )
        return {
            "meta": {
                "rows": int(len(cumulative)),
                "table_rows": len(rows),
                "version_id": version_id,
                "data_mode": DATA_MODE,
                "source": "web_data.db",
                "parity": "main_dashboard_executive_documentation",
                "warning": None,
                "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            },
            "filters": {
                "projects": ["Все", *projects],
                "contractors": ["Все", *contractors],
                "doc_kinds": [
                    "Все",
                    *renderer._exec_doc_kind_filter_options(cumulative, kind, catalog),
                ],
                "catalog": catalog_df.to_dict(orient="records"),
                "date_min": issue_min.date().isoformat() if pd.notna(issue_min) else None,
                "date_max": issue_max.date().isoformat() if pd.notna(issue_max) else None,
                "granularities": [
                    {"id": key, "label": label}
                    for key, (label, _) in GRANULARITIES.items()
                ],
                "applied": {
                    "project": applied_project,
                    "contractor": contractor or "Все",
                    "doc_kind": doc_kind or "Все",
                    "date_from": date_from.isoformat() if date_from else None,
                    "date_to": date_to.isoformat() if date_to else None,
                    "granularity": gran,
                    "hide_overdue_if_signed": hide_overdue_if_signed,
                },
            },
            "kpis": {
                "total_docs": total_docs,
                "declined": int(declined.sum()),
                "on_agree": int(agree.sum()),
                "signed": int(signed.sum()),
                "on_rework": int(rework.sum()),
                "overdue_total": int(contractor_mask.sum() + customer_mask.sum()),
                "contractor_overdue": {
                    "count": int(contractor_mask.sum()),
                    **_buckets(sub_c["_late_days"]),
                },
                "customer_overdue": {
                    "count": int(customer_mask.sum()),
                    **_buckets(sub_u["_late_days"]),
                },
            },
            "tremor": {
                "by_status": [
                    {
                        "status": str(name),
                        "count": int(value),
                        "share_pct": round(100.0 * value / max(len(cumulative), 1), 1),
                    }
                    for name, value in status.value_counts().items()
                ],
                "by_object": [
                    {"object": str(name), "count": int(value)}
                    for name, value in cumulative[obj].map(_text).value_counts().items()
                ],
                "overdue_contractor": _group(contractor_mask),
                "overdue_customer": _group(customer_mask),
                "dynamics": dynamics,
            },
            "rows": rows,
        }
    except Exception as exc:
        return _empty(f"Не удалось подготовить данные из web_data.db: {exc}")
