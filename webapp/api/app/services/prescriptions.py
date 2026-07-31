"""Предписания по подрядчикам — паритет с dashboard_predpisania из web_data.db."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

import pandas as pd

from app.config import DATA_MODE
from app.services.core_bridge import (
    active_version_id,
    import_dashboard_module,
    load_version_df,
    prepare_web_db,
    session_state,
)


def _split_csv(raw: str | None) -> list[str]:
    return [value.strip() for value in str(raw or "").split(",") if value.strip()]


def _clean(value: Any, empty: str = "—") -> str:
    text = str(value or "").strip()
    return empty if not text or text.casefold() in {"nan", "none", "nat", "<na>"} else text


def _date_text(value: Any) -> str | None:
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    return parsed.strftime("%d.%m.%Y") if pd.notna(parsed) else None


def _empty_payload(message: str | None = None) -> dict[str, Any]:
    return {
        "meta": {
            "rows": 0,
            "version_id": None,
            "data_mode": DATA_MODE,
            "source": "web_data.db",
            "parity": "main_dashboard_predpisania",
            "warning": message,
        },
        "filters": {
            "projects": [],
            "contractors": [],
            "date_min": None,
            "date_max": None,
            "applied": {
                "projects": [],
                "contractors": [],
                "contract_q": "",
                "date_from": None,
                "date_to": None,
                "hide_resolved": False,
            },
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
        "tremor": {"by_contractor": [], "by_status": [], "by_object": []},
        "rows": [],
    }


def _renderer():
    return import_dashboard_module("_renderers")


def _column(renderer, frame: pd.DataFrame, names: list[str]) -> str | None:
    return renderer._tessa_find_column(frame, names)


def _calendar_date(ts) -> Optional[date]:
    if ts is None or (isinstance(ts, float) and pd.isna(ts)):
        return None
    if hasattr(ts, "date") and callable(getattr(ts, "date")):
        try:
            out = ts.date()
            return out if isinstance(out, date) else None
        except Exception:
            pass
    parsed = pd.to_datetime(ts, errors="coerce")
    if pd.isna(parsed):
        return None
    try:
        return parsed.date()
    except Exception:
        return None


def _overdue_days_row(row: pd.Series) -> int:
    """Как main `_overdue_days_row`: открытые ≥0; снятые вовремя — отрицательные дни."""
    d_due = _calendar_date(row.get("_due"))
    if bool(row.get("_resolved")):
        d_comp = _calendar_date(row.get("_completion_dt"))
        if d_due and d_comp:
            if d_comp > d_due:
                return (d_comp - d_due).days
            if d_comp < d_due:
                return -(d_due - d_comp).days
            return 0
        return 0
    if d_due and date.today() > d_due:
        return (date.today() - d_due).days
    return 0


def _prepare_frame(version_id: int) -> pd.DataFrame:
    renderer = _renderer()
    tessa = load_version_df(version_id, "tessa")
    tasks = load_version_df(version_id, "tessa_tasks")
    if tessa is None or tessa.empty:
        return pd.DataFrame()

    session_state()["tessa_tasks_data"] = tasks if tasks is not None else pd.DataFrame()
    work = tessa.copy()
    work.columns = [str(column).strip() for column in work.columns]
    try:
        from web_loader import _tessa_drop_cancelled_tag_rows  # type: ignore

        work = _tessa_drop_cancelled_tag_rows(work)
    except Exception:
        pass
    work = renderer._tessa_fill_card_from_doc_lookup(work)

    kind_col = _column(renderer, work, ["KindName", "kindname", "Вид"])
    if kind_col or "KrStateID" in work.columns:
        mask_id = pd.Series(False, index=work.index)
        if "KrStateID" in work.columns:
            mask_id = mask_id | work["KrStateID"].notna()
        if kind_col and kind_col in work.columns:
            mask_id = mask_id | (
                work[kind_col].notna()
                & (~work[kind_col].astype(str).str.strip().isin(["", "nan", "None", "NaN"]))
            )
        work = work[mask_id].reset_index(drop=True)

    if not kind_col:
        return pd.DataFrame()
    pred = work[
        work[kind_col].astype(str).str.strip().str.casefold().eq("предписания")
    ].copy()
    if pred.empty:
        return pred

    obj_col = _column(
        renderer, pred, ["ObjectName", "objectname", "Объект", "ProjectName", "Проект"]
    )
    if obj_col:
        pred = pred[
            pred[obj_col].notna()
            & (~pred[obj_col].astype(str).str.strip().isin(["", "nan", "None", "NaN"]))
        ].reset_index(drop=True)
    if pred.empty or not obj_col:
        return pd.DataFrame()

    proj_lookup, _valid_ids, _valid_names = renderer._pred_projekts_1c_lookup()
    if proj_lookup:
        pred[obj_col] = renderer._resolve_project_display_labels(pred[obj_col], proj_lookup)
    pred = renderer._pred_filter_by_projekts_registry(pred, obj_col)
    if pred.empty:
        return pred
    try:
        pred = renderer._project_column_apply_canonical(pred, obj_col)
    except Exception:
        pass

    pred = renderer._tessa_fill_card_from_doc_lookup(pred)
    doc_col = _column(
        renderer, pred, ["DocID", "DocId", "DocumentID", "DocumentId", "Id", "ID"]
    )
    card_col = _column(
        renderer, pred, ["CardId", "CardID", "cardId", "TaskCardId", "ИдКарточки"]
    )
    creation_col = _column(renderer, pred, ["CreationDate", "creationdate", "Дата создания"])
    pred["Статус"] = renderer._tessa_resolve_status_series(pred)
    pred = renderer._tessa_drop_project_state_rows(pred)
    if pred.empty:
        return pred

    pred = renderer._pred_dedupe_by_docid(
        pred, doc_col, creation_col, pred_card_col=card_col
    )
    pred = renderer._pred_merge_completion_from_tasks(pred, card_col, doc_col)
    pred["Статус"] = renderer._tessa_resolve_status_series(pred)
    pred = renderer._tessa_drop_project_state_rows(pred)
    if pred.empty:
        return pred

    contractor_col = _column(renderer, pred, ["CONTR", "Контрагент", "contr"])
    contract_col = _column(
        renderer,
        pred,
        [
            "1C_ID_DOG",
            "1c_id_dog",
            "ID_DOG",
            "ContractNumber",
            "НомерДоговора",
            "Номер договора",
            "Номер_договора",
        ],
    )
    due_col = _column(
        renderer,
        pred,
        ["id_Deadline", "id_deadline", "Deadline", "DueDate", "Срок устранения"],
    )
    completion_col = _column(
        renderer,
        pred,
        ["Completed", "CompletionDate", "Дата завершения", "Факт устранения"],
    )
    issue_block_col = _column(
        renderer,
        pred,
        [
            "Comment",
            "comment",
            "Комментарий",
            "BlockName",
            "IssueBlock",
            "Блок выдачи предписания",
            "Блок выдачи",
            "Блок",
        ],
    )
    name_col = _column(renderer, pred, ["Name", "name", "Наименование", "Title"])
    doc_number_col = _column(
        renderer, pred, ["DocNumber", "DocumentNumber", "НомерДокумента"]
    )
    pred_number_col = _column(
        renderer,
        pred,
        ["InternalID", "Internal Id", "InternalId", "Номер предписания", "НомерПредписания"],
    )

    if contract_col and contract_col in pred.columns:
        try:
            dog_lookup = renderer._load_dogovor_lookup() or {}
        except Exception:
            dog_lookup = {}
        if dog_lookup:

            def _resolve_contract_no(value: Any) -> Any:
                if value is None or (isinstance(value, float) and pd.isna(value)):
                    return value
                key = str(value).strip().lower()
                if not key:
                    return value
                rec = dog_lookup.get(key)
                if not rec:
                    return value
                num = (
                    rec.get("Номер_Договора") or rec.get("Номер_договора") or ""
                ).strip()
                return num if num else value

            pred[contract_col] = pred[contract_col].map(_resolve_contract_no)

    pred["_resolved"] = False
    if "KrStateID" in pred.columns:
        krstate_num = pd.to_numeric(pred["KrStateID"], errors="coerce")
        proj_state = renderer._pred_project_state_mask(pred)
        pred["_resolved"] = (krstate_num == 13) & (~proj_state)

    base_comp = (
        renderer._tessa_to_datetime(pred[completion_col])
        if completion_col and completion_col in pred.columns
        else pd.Series(pd.NaT, index=pred.index)
    )
    task_comp = (
        renderer._tessa_to_datetime(pred["_completion_from_task"])
        if "_completion_from_task" in pred.columns
        else pd.Series(pd.NaT, index=pred.index)
    )
    pred["_completion_dt"] = pd.Series(pd.NaT, index=pred.index)
    resolved_mask = pred["_resolved"].astype(bool)
    pred.loc[resolved_mask, "_completion_dt"] = task_comp.loc[resolved_mask].combine_first(
        base_comp.loc[resolved_mask]
    )
    pred.loc[~resolved_mask, "_completion_dt"] = base_comp.loc[~resolved_mask].combine_first(
        task_comp.loc[~resolved_mask]
    )
    pred["_issue_dt"] = (
        renderer._tessa_to_datetime(pred[creation_col])
        if creation_col
        else pd.Series(pd.NaT, index=pred.index)
    )
    pred["_due"] = (
        renderer._tessa_to_datetime(pred[due_col])
        if due_col
        else pd.Series(pd.NaT, index=pred.index)
    )
    pred["_overdue_days"] = pred.apply(_overdue_days_row, axis=1)
    pred["_overdue_open"] = (~pred["_resolved"].astype(bool)) & (pred["_overdue_days"] > 0)

    tag_col = _column(
        renderer,
        pred,
        ["Tessa_Teg", "TessaTag", "TESSA_TEG", "tessa_teg", "ТегТесса", "Тег"],
    )
    kind_id_col = _column(renderer, pred, ["KindID", "KindId", "kindId"])
    kind_ok = pd.Series(True, index=pred.index)
    try:
        kind_target = renderer._pred_norm_uuid_str(renderer._KIND_ID_PREDPISE)
        if kind_id_col and kind_id_col in pred.columns:
            raw_k = pred[kind_id_col]
            sk = raw_k.astype(str).str.strip()
            has_kind = (
                raw_k.notna()
                & sk.ne("")
                & ~sk.str.casefold().isin({"nan", "none", "<na>", "nat"})
            )
            kid_norm = raw_k.map(renderer._pred_norm_uuid_str)
            kind_ok = (~has_kind) | kid_norm.eq(kind_target)
    except Exception:
        kind_ok = pd.Series(True, index=pred.index)

    tags = renderer._pred_tessa_tag_series(pred, tag_col)
    pred["_critical"] = (
        renderer._pred_tag_contains_any(
            tags, ("критичный", "критическое", "критичное", "critical")
        )
        & kind_ok
    )
    pred["_stop_work"] = (
        renderer._pred_tag_contains_any(tags, ("приостановка работ",)) & kind_ok
    )

    pred["_object_col"] = obj_col
    pred["_contractor_col"] = contractor_col
    pred["_contract_col"] = contract_col
    pred["_issue_block_col"] = issue_block_col
    pred["_name_col"] = name_col
    pred["_doc_number_col"] = doc_number_col
    pred["_pred_number_col"] = pred_number_col
    return pred


def build_prescriptions_payload(
    *,
    projects: str | None = None,
    contractors: str | None = None,
    contract_q: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    hide_resolved: bool = False,
) -> dict[str, Any]:
    try:
        prepare_web_db()
        version_id = active_version_id()
        if not version_id:
            return _empty_payload("Нет active version_id в web_data.db")
        pred = _prepare_frame(int(version_id))
    except Exception as exc:
        return _empty_payload(f"Не удалось подготовить данные из web_data.db: {exc}")

    if pred.empty:
        payload = _empty_payload("Нет строк KindName=Предписания в active version")
        payload["meta"]["version_id"] = version_id
        return payload

    renderer = _renderer()
    obj_col = str(pred["_object_col"].iloc[0])
    contractor_col_raw = pred["_contractor_col"].iloc[0]
    contractor_col = (
        str(contractor_col_raw) if pd.notna(contractor_col_raw) and contractor_col_raw else ""
    )
    contract_col_raw = pred["_contract_col"].iloc[0]
    contract_col = (
        str(contract_col_raw) if pd.notna(contract_col_raw) and contract_col_raw else ""
    )
    issue_block_col_raw = pred["_issue_block_col"].iloc[0]
    issue_block_col = (
        str(issue_block_col_raw)
        if pd.notna(issue_block_col_raw) and issue_block_col_raw
        else ""
    )
    name_col_raw = pred["_name_col"].iloc[0]
    name_col = str(name_col_raw) if pd.notna(name_col_raw) and name_col_raw else ""
    doc_number_col_raw = pred["_doc_number_col"].iloc[0]
    doc_number_col = (
        str(doc_number_col_raw)
        if pd.notna(doc_number_col_raw) and doc_number_col_raw
        else ""
    )
    pred_number_col_raw = pred["_pred_number_col"].iloc[0]
    pred_number_col = (
        str(pred_number_col_raw)
        if pd.notna(pred_number_col_raw) and pred_number_col_raw
        else ""
    )

    project_values = sorted(
        {_clean(value, "") for value in pred[obj_col] if _clean(value, "")},
        key=str.casefold,
    )
    contractor_values = sorted(
        (
            {_clean(value, "") for value in pred[contractor_col] if _clean(value, "")}
            if contractor_col
            else set()
        ),
        key=str.casefold,
    )
    selected_projects = _split_csv(projects)
    selected_contractors = _split_csv(contractors)
    view = pred.copy()
    if selected_projects:
        view = view[view[obj_col].astype(str).str.strip().isin(selected_projects)]
    if selected_contractors and contractor_col:
        view = view[view[contractor_col].astype(str).str.strip().isin(selected_contractors)]
    if contract_q and contract_q.strip() and contract_col:
        view = view[
            view[contract_col]
            .astype(str)
            .str.casefold()
            .str.contains(contract_q.strip().casefold(), na=False)
        ]
    if date_from:
        view = view[view["_issue_dt"].isna() | view["_issue_dt"].ge(pd.Timestamp(date_from))]
    if date_to:
        view = view[
            view["_issue_dt"].isna()
            | view["_issue_dt"].lt(pd.Timestamp(date_to) + pd.Timedelta(days=1))
        ]
    if hide_resolved:
        view = view[~view["_resolved"]].copy()

    total = int(len(view))
    resolved = int(view["_resolved"].sum())
    unresolved = total - resolved
    overdue_open = int(view["_overdue_open"].sum())
    critical = int((~view["_resolved"] & view["_critical"]).sum())
    stop_work = int((~view["_resolved"] & view["_stop_work"]).sum())
    non_overdue = int(pd.to_numeric(view["_overdue_days"], errors="coerce").fillna(0).le(0).sum())

    contractors_chart = (
        view.assign(
            _contractor=(
                view[contractor_col].map(lambda value: _clean(value))
                if contractor_col
                else "—"
            ),
            _crit_od=(view["_critical"] & view["_overdue_open"]).astype(int),
        )
        .groupby("_contractor", as_index=False)
        .agg(
            total=("_contractor", "size"),
            overdue=("_overdue_open", "sum"),
            crit_overdue=("_crit_od", "sum"),
        )
        .sort_values(
            ["crit_overdue", "overdue", "total", "_contractor"],
            ascending=[False, False, False, True],
        )
    )
    pie = renderer._pred_build_status_pie_df(view)
    objects = renderer._pred_build_by_object_status_df(
        view, obj_col, hide_resolved=hide_resolved
    )
    view = view.assign(
        _sort=(view["_critical"] & view["_overdue_open"]).astype(int)
    ).sort_values(
        ["_sort", "_overdue_open", "_overdue_days"], ascending=False, kind="stable"
    )

    rows: list[dict[str, Any]] = []
    for _, row in view.iterrows():
        resolved_row = bool(row["_resolved"])
        overdue_days = int(row["_overdue_days"] or 0)
        display_overdue = overdue_days if overdue_days > 0 else 0
        rows.append(
            {
                "status": renderer._pred_status_display_label(
                    row.get("Статус"), resolved=resolved_row, overdue_days=overdue_days
                ),
                "contractor": _clean(row.get(contractor_col)) if contractor_col else "—",
                "project": _clean(row.get(obj_col)),
                "contract_no": _clean(row.get(contract_col), "Без номера")
                if contract_col
                else "Без номера",
                "doc_number": renderer._pred_fmt_doc_full(
                    row.get(doc_number_col) if doc_number_col else None
                ),
                "pred_number": renderer._pred_fmt_doc_full(
                    row.get(pred_number_col) if pred_number_col else None
                ),
                "name": _clean(row.get(name_col)) if name_col else "—",
                "issue_date": _date_text(row["_issue_dt"]),
                "issue_block": _clean(row.get(issue_block_col))
                if issue_block_col
                else "—",
                "due_date": _date_text(row["_due"]),
                "completion_date": _date_text(row["_completion_dt"]),
                "overdue_days": display_overdue,
                "critical": bool(row["_critical"]),
                "stop_work": bool(row["_stop_work"]),
                "resolved": resolved_row,
                "row_tone": (
                    "overdue"
                    if bool(row["_overdue_open"])
                    else ("resolved" if resolved_row else "neutral")
                ),
                "status_chip": (
                    "overdue"
                    if bool(row["_overdue_open"])
                    else ("ok" if resolved_row and overdue_days <= 0 else "warn")
                ),
            }
        )

    issue_min, issue_max = pred["_issue_dt"].min(), pred["_issue_dt"].max()
    status_order = renderer._pred_objects_chart_status_order(hide_resolved=hide_resolved)
    return {
        "meta": {
            "rows": total,
            "version_id": version_id,
            "data_mode": DATA_MODE,
            "source": "web_data.db",
            "parity": "main_dashboard_predpisania",
            "warning": None,
            "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        },
        "filters": {
            "projects": project_values,
            "contractors": contractor_values,
            "date_min": issue_min.date().isoformat() if pd.notna(issue_min) else None,
            "date_max": issue_max.date().isoformat() if pd.notna(issue_max) else None,
            "applied": {
                "projects": selected_projects,
                "contractors": selected_contractors,
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
            "overdue_unresolved": overdue_open,
            "critical": critical,
            "stop_work": stop_work,
        },
        "tremor": {
            "by_contractor": [
                {
                    "contractor": str(row["_contractor"]),
                    "total": int(row["total"]),
                    "overdue": int(row["overdue"]),
                }
                for _, row in contractors_chart.iterrows()
            ],
            "by_status": [
                {
                    "name": str(row["Статус"]),
                    "status": str(row["Статус"]),
                    "value": int(row["Количество"]),
                    "count": int(row["Количество"]),
                    "share_pct": float(row["Доля"]),
                }
                for _, row in pie.iterrows()
            ],
            "by_object": [
                {
                    "object": _clean(row[obj_col]),
                    "total": int(row["_total"]),
                    **{key: int(row.get(key, 0) or 0) for key in status_order},
                }
                for _, row in objects.iterrows()
            ],
        },
        "rows": rows,
    }
