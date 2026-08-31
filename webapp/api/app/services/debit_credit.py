"""ДЗ/КЗ подрядчиков — паритет с dashboard_debit_credit из web_data.db."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

import pandas as pd

from app.config import DATA_MODE
from app.services.core_bridge import (
    active_version_id,
    load_version_df,
    prepare_web_db,
)
from app.services.project_scope import applied_project_label, resolve_selected_projects

_KS2_ARTICLES = {
    "поступление товаров и услуг",
    "поступление услуг из переработки",
    "поступления по основной деятельности",
}


def _clean(value: Any, empty: str = "—") -> str:
    text = str(value or "").strip()
    return empty if not text or text.casefold() in {"nan", "none", "nat", "<na>"} else text


def _find_col(df: pd.DataFrame, names: list[str]) -> str | None:
    """Как main `_find_col`, но сначала точное имя — иначе «Аванс» ловит «…ПоАвансам»."""
    cols = [str(c) for c in df.columns]
    cols_lower = [c.lower().strip() for c in cols]
    for name in names:
        needle = name.lower().strip()
        for i, col in enumerate(cols_lower):
            if col == needle:
                return cols[i]
    for name in names:
        needle = name.lower().strip()
        for i, col in enumerate(cols_lower):
            if needle in col or col in needle:
                return cols[i]
    return None


def _partner_brand_key(name: str) -> str:
    key = " ".join(str(name or "").casefold().split())
    if "есипово" in key and key.startswith("ис "):
        return "ис есипово"
    if "есипово" in key:
        return "ис есипово"
    return key


def _read_orphan_advance_mln() -> float:
    """Аванс из итоговой строки DK (без контрагента/договора), млн руб. — как main."""
    import json

    from app.config import WEB_DATA_DIR

    if not WEB_DATA_DIR.is_dir():
        return 0.0
    files = sorted(
        [
            p
            for p in WEB_DATA_DIR.iterdir()
            if p.is_file() and "DK" in p.name.upper() and p.suffix.lower() == ".json"
        ],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:5]
    for path in files:
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if not isinstance(raw, list):
            continue
        total = 0.0
        for item in raw:
            if not isinstance(item, dict):
                continue
            contr = item.get("Контрагент") or {}
            dog = item.get("Договор") or {}
            org = item.get("Организация") or {}
            has_c = isinstance(contr, dict) and bool(
                str(contr.get("НаименованиеКонтрагента", "") or "").strip()
                or str(contr.get("ID_Контрагента", "") or "").strip()
            )
            has_d = isinstance(dog, dict) and bool(
                str(dog.get("ID_Договора", "") or "").strip()
                or str(dog.get("НомерДоговора", "") or "").strip()
            )
            has_o = isinstance(org, dict) and bool(
                str(org.get("ID_Организации", "") or "").strip()
            )
            if has_c or has_d or has_o:
                continue
            try:
                total += float(item.get("ОстатокНаКонецПериодаПоАвансам", 0) or 0)
            except (TypeError, ValueError):
                pass
        if total > 1e-6:
            return total / 1e6
    return 0.0


def _apply_orphan_advance_to_chart_rows(
    chart_rows: list[dict[str, Any]], orphan_mln: float
) -> list[dict[str, Any]]:
    """Переносит orphan-аванс на ИС Есипово / max КС-2 — стек получает синий сегмент."""
    if orphan_mln <= 1e-6 or not chart_rows:
        return chart_rows
    rows = [dict(r) for r in chart_rows]
    pick = None
    best_ks2 = -1.0
    for i, row in enumerate(rows):
        brand = _partner_brand_key(str(row.get("label", "")))
        ks2 = float(row.get("КС-2") or 0)
        if brand == "ис есипово" and ks2 > best_ks2:
            best_ks2 = ks2
            pick = i
    if pick is None:
        for i, row in enumerate(rows):
            if abs(float(row.get("Аванс") or 0)) > 1e-6:
                continue
            ks2 = float(row.get("КС-2") or 0)
            if ks2 > best_ks2:
                best_ks2 = ks2
                pick = i
    if pick is None:
        pick = max(range(len(rows)), key=lambda i: float(rows[i].get("КС-2") or 0))
    adv = float(rows[pick].get("Аванс") or 0) + orphan_mln
    ks2 = float(rows[pick].get("КС-2") or 0)
    rows[pick]["Аванс"] = round(adv, 3)
    dev = ks2 - adv
    rows[pick]["Отклонение ≥0"] = round(max(dev, 0.0), 3)
    rows[pick]["Отклонение <0"] = round(min(dev, 0.0), 3)
    return rows


def _to_num(series: pd.Series) -> pd.Series:
    """Как main `_to_num`: пробелы; запятая — десятичный или тысячный разделитель."""
    s = (
        series.astype(str)
        .str.replace("\u00a0", "", regex=False)
        .str.replace(" ", "", regex=False)
        .str.strip()
    )
    both = s.str.contains(",") & s.str.contains(r"\.")
    s = s.where(~both, s.str.replace(",", "", regex=False))
    s = s.str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce").fillna(0.0)


def _dogovor_lookup() -> dict[str, dict]:
    try:
        prepare_web_db()
        from web_db_read import load_dogovor_lookup_from_db  # type: ignore

        return load_dogovor_lookup_from_db() or {}
    except Exception:
        return {}


def _empty(message: str | None = None) -> dict[str, Any]:
    return {
        "meta": {
            "rows": 0,
            "version_id": None,
            "data_mode": DATA_MODE,
            "source": "web_data.db",
            "parity": "main_dashboard_debit_credit",
            "warning": message,
        },
        "filters": {
            "projects": ["Все"],
            "contractors": ["Все"],
            "contract_nos": [],
            "date_min": None,
            "date_max": None,
            "applied": {},
        },
        "chart": {
            "rows": [],
            "mode": "group",
            "aggregation": "by_contractor",
            "caption": "Топ 0 из 0 контрагентов",
            "unit": "млн ₽",
        },
        "rows": [],
        "totals": {
            "contract_sum": 0,
            "advance": 0,
            "ks2": 0,
            "fulfilled": 0,
            "paid": 0,
            "balance": 0,
            "advance_ks2": 0,
            "advance_pct": None,
        },
        "kpis": {
            "contract_sum": 0,
            "advance": 0,
            "ks2": 0,
            "fulfilled": 0,
            "paid": 0,
            "balance": 0,
            "advance_ks2": 0,
        },
    }


def _semaphore(delta: float, contract_sum: float) -> dict[str, Any]:
    """Светофор авансирования: 🟢 ≤30%, 🟡 30–60%, 🔴 ≥60% от договора при delta>0."""
    if contract_sum <= 0:
        return {"tone": "green" if delta <= 0 else "red", "pct": None}
    if delta <= 0:
        return {"tone": "green", "pct": round(delta / contract_sum * 100, 1)}
    ratio = delta / contract_sum
    pct = round(ratio * 100, 1)
    if ratio <= 0.30:
        return {"tone": "green", "pct": pct}
    if ratio < 0.60:
        return {"tone": "yellow", "pct": pct}
    return {"tone": "red", "pct": pct}


def _prepare_frame(version_id: int) -> pd.DataFrame:
    # Не тянем dashboards._renderers (~40k строк) — OOM на VPS (mem_limit ~1200m).
    work = load_version_df(version_id, "debit_credit")
    reference = load_version_df(version_id, "reference_dannye")
    if reference is None or reference.empty:
        reference = load_version_df(version_id, "reference_1c_dannye")
    if work is None or work.empty:
        return pd.DataFrame()

    work = work.copy()
    work.columns = [str(c).strip() for c in work.columns]
    reference = reference.copy() if reference is not None else pd.DataFrame()
    if not reference.empty:
        reference.columns = [str(c).strip() for c in reference.columns]

    contractor_col = _find_col(
        work,
        [
            "Название контрагента",
            "Название организации",
            "Подрядчик",
            "Контрагент",
            "contractor",
        ],
    )
    partner_id_col = _find_col(
        work, ["ID_Контрагента", "Контрагент_ID_Контрагента", "Контрагент.ID_Контрагента"]
    )
    contract_col = _find_col(work, ["Номер договора", "НомерДоговора", "Договор", "contract"])
    dog_id_col = _find_col(
        work, ["ID_Договора", "Договор_ID_Договора", "Договор.ID_Договора", "1C_ID_DOG"]
    )
    project_col = _find_col(
        work, ["Наименование_Проекта", "Проект", "project name", "Project"]
    )
    date_col = _find_col(work, ["Дата договора", "ДатаДоговора", "Дата Договора"])
    sum_col = _find_col(
        work,
        [
            "Сумма в договоре",
            "СуммаДоговора",
            "Сумма_Договора",
            "Договор_СуммаДоговора",
            "Сумма договора",
        ],
    )
    advance_col = _find_col(
        work, ["Аванс", "Авансированная сумма", "ВсегоОплат_Аванс", "advance"]
    )
    advance_end_col = _find_col(
        work,
        [
            "ОстатокНаКонецПериодаПоАвансам",
            "Остаток на конец периода по авансам",
        ],
    )
    advance_alt_col = _find_col(
        work, ["ОстатокНаНачалоПериодаПоАвансам", "Остаток на начало периода по авансам"]
    )
    paid_col = _find_col(work, ["Выплачено", "Выплаченная сумма", "ВсегоОплат", "paid"])
    gross_col = _find_col(
        work, ["ОстатокНаКонецПериода", "Остаток на конец периода", "ОстатокНаКонец"]
    )

    dog_ids = (
        work[dog_id_col].astype(str).str.strip().str.lower()
        if dog_id_col
        else pd.Series("", index=work.index)
    )
    dog_lookup = _dogovor_lookup()

    contractors = (
        work[contractor_col].map(_clean)
        if contractor_col
        else pd.Series("—", index=work.index)
    )
    contracts = (
        work[contract_col].map(_clean)
        if contract_col
        else pd.Series("—", index=work.index)
    )
    projects = (
        work[project_col].map(_clean)
        if project_col
        else pd.Series("—", index=work.index)
    )
    contract_sum = _to_num(work[sum_col]) if sum_col else pd.Series(0.0, index=work.index)
    for index, dog_id in dog_ids.items():
        record = dog_lookup.get(str(dog_id)) or {}
        if contracts.at[index] == "—":
            contracts.at[index] = _clean(record.get("Номер_Договора"))
        if projects.at[index] == "—":
            projects.at[index] = _clean(record.get("Наименование_Проекта"))
        if not float(contract_sum.at[index] or 0):
            contract_sum.at[index] = float(
                _to_num(pd.Series([record.get("Сумма_Договора")])).iloc[0]
            )

    ks2 = pd.Series(0.0, index=work.index)
    if not reference.empty:
        article_col = _find_col(reference, ["СтатьяОборотов", "Статья оборотов", "turnover item"])
        amount_col = _find_col(reference, ["Сумма", "СуммаОборота", "amount"])
        ref_dog_col = _find_col(reference, ["ID_Договора", "id_договора", "id_dogovora"])
        ref_partner_col = _find_col(
            reference, ["ID_Контрагента", "id_контрагента", "id_kontragenta"]
        )
        if article_col and amount_col:
            so = reference[article_col].astype(str).str.strip().str.casefold()
            filtered = reference.loc[so.isin(_KS2_ARTICLES)].copy()
            if not filtered.empty:
                filtered["_sum"] = _to_num(filtered[amount_col])
                if ref_dog_col and ref_dog_col in filtered.columns:
                    by_dog = (
                        filtered.assign(
                            _dog=filtered[ref_dog_col]
                            .astype(str)
                            .str.strip()
                            .str.lower()
                        )
                        .groupby("_dog")["_sum"]
                        .sum()
                    )
                    ks2 = dog_ids.map(by_dog.to_dict()).fillna(0.0)
                if partner_id_col and ref_partner_col:
                    by_partner = (
                        filtered.assign(
                            _p=filtered[ref_partner_col]
                            .astype(str)
                            .str.strip()
                            .str.lower()
                        )
                        .groupby("_p")["_sum"]
                        .sum()
                    )
                    partner_ids = (
                        work[partner_id_col].astype(str).str.strip().str.lower()
                    )
                    ks2 = ks2.where(
                        ks2.ne(0), partner_ids.map(by_partner.to_dict()).fillna(0.0)
                    )

    # Как main: «Аванс» часто пустой → берём ОстатокНаКонецПериодаПоАвансам (не «НаНачало»).
    advance = _to_num(work[advance_col]) if advance_col else pd.Series(0.0, index=work.index)
    if float(advance.abs().sum()) < 1e-9 and advance_end_col:
        advance = _to_num(work[advance_end_col])
    paid = _to_num(work[paid_col]) if paid_col else pd.Series(0.0, index=work.index)
    gross = _to_num(work[gross_col]) if gross_col else pd.Series(0.0, index=work.index)
    adv_end = (
        _to_num(work[advance_end_col])
        if advance_end_col
        else (
            _to_num(work[advance_alt_col])
            if advance_alt_col
            else pd.Series(0.0, index=work.index)
        )
    )
    balance = gross - adv_end
    # UTC→naive: иначе фильтр периода падает (tz-aware vs Timestamp).
    dates = (
        pd.to_datetime(work[date_col], errors="coerce", dayfirst=True, utc=True)
        .dt.tz_localize(None)
        if date_col
        else pd.Series(pd.NaT, index=work.index)
    )
    return pd.DataFrame(
        {
            "project": projects,
            "contractor": contractors,
            "contract": contracts,
            "contract_date": dates,
            "contract_sum": contract_sum.astype(float),
            "advance": advance.astype(float),
            "ks2": ks2.astype(float),
            "paid": paid.astype(float),
            "balance": balance.astype(float),
        }
    ).assign(fulfilled=lambda df: df.advance + df.ks2)


def build_debit_credit_payload(
    *,
    project: str | None = None,
    contractor: str | None = None,
    contract_q: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    display_view: str = "Без группировки",
) -> dict[str, Any]:
    try:
        prepare_web_db()
        version_id = active_version_id()
        frame = _prepare_frame(int(version_id)) if version_id else pd.DataFrame()
    except Exception as exc:
        return _empty(f"Не удалось подготовить данные из web_data.db: {exc}")
    if frame.empty:
        payload = _empty("В active version нет строк debit_credit")
        payload["meta"]["version_id"] = version_id
        return payload

    projects = ["Все"] + sorted(
        {_clean(value) for value in frame.project if _clean(value) != "—"},
        key=str.casefold,
    )
    contractors = ["Все"] + sorted(
        {_clean(value) for value in frame.contractor if _clean(value) != "—"},
        key=str.casefold,
    )
    _uuid_re = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        re.I,
    )
    contract_nos: list[str] = []
    _seen_contracts: set[str] = set()
    for value in frame.contract.dropna().tolist():
        text = _clean(value, "")
        if not text or text == "—" or _uuid_re.match(text):
            continue
        key = text.casefold()
        if key in _seen_contracts:
            continue
        _seen_contracts.add(key)
        contract_nos.append(text)
    contract_nos.sort(key=str.casefold)
    view = frame.copy()
    selected_projects = resolve_selected_projects(project, projects)
    applied_project = applied_project_label(selected_projects)
    if selected_projects:
        view = view[view.project.isin(selected_projects)]
    if contractor and contractor != "Все":
        view = view[view.contractor.eq(contractor)]
    if contract_q:
        view = view[
            view.contract.str.casefold().str.contains(
                contract_q.strip().casefold(), na=False
            )
        ]
    contract_dates = pd.to_datetime(view.contract_date, errors="coerce")
    if getattr(contract_dates.dtype, "tz", None) is not None:
        contract_dates = contract_dates.dt.tz_convert("UTC").dt.tz_localize(None)
    if date_from:
        view = view[
            contract_dates.isna() | contract_dates.ge(pd.Timestamp(date_from))
        ]
    if date_to:
        view = view[
            contract_dates.isna()
            | contract_dates.lt(pd.Timestamp(date_to) + pd.Timedelta(days=1))
        ]

    # Исключительный кейс: Все проекты + Все подрядчики + без фильтра договора
    # → агрегация только по типу суммы. Но «С группировкой» остаётся
    # прежним режимом стека по подрядчику.
    all_open = (
        (not selected_projects)
        and (not contractor or contractor == "Все")
        and not (contract_q and str(contract_q).strip())
    )
    use_metric_chart = all_open and display_view != "С группировкой"

    orphan_mln = _read_orphan_advance_mln()
    chart_aggregation = "by_metric" if use_metric_chart else "by_contractor"
    chart_rows: list[dict[str, Any]] = []

    if use_metric_chart:
        contract_mln = float(view.contract_sum.sum()) / 1e6 if len(view) else 0.0
        fulfilled_mln = float(view.fulfilled.sum()) / 1e6 if len(view) else 0.0
        ks2_mln = float(view.ks2.sum()) / 1e6 if len(view) else 0.0
        adv_mln = float(view.advance.sum()) / 1e6 if len(view) else 0.0
        if orphan_mln > 1e-6:
            adv_mln += orphan_mln
        dev_mln = ks2_mln - adv_mln
        chart_rows = [
            {
                "label": "Договор стоимость",
                "value": round(contract_mln, 3),
                "color": "#2E86AB",
            },
            {
                "label": "Всего выполненных обязательств по платежам",
                "value": round(fulfilled_mln, 3),
                "color": "#95A5A6",
            },
            {
                "label": "КС-2",
                "value": round(ks2_mln, 3),
                "color": "#B7950B",
            },
            {
                "label": "Аванс",
                "value": round(adv_mln, 3),
                "color": "#F7DC6F",
            },
            {
                "label": "КС-2 − Аванс",
                "value": round(dev_mln, 3),
                "color": "#95A5A6" if dev_mln >= 0 else "#F1948A",
            },
        ]
        chart_caption = (
            "Сводка по типам сумм (все проекты, подрядчики и договоры)."
        )
    else:
        chart_src = (
            view.groupby("contractor", as_index=False)[["advance", "ks2"]]
            .sum()
            .rename(columns={"contractor": "label"})
        )
        chart_src["deviation"] = chart_src.ks2 - chart_src.advance
        chart_src["_rank"] = chart_src[["advance", "ks2", "deviation"]].abs().max(axis=1)
        chart_src = chart_src.sort_values("_rank", ascending=False, kind="stable").head(28)
        for _, row in chart_src.iterrows():
            adv = float(row.advance) / 1e6
            ks2 = float(row.ks2) / 1e6
            dev = float(row.deviation) / 1e6
            chart_rows.append(
                {
                    "label": _clean(row.label),
                    "Аванс": round(adv, 3),
                    "КС-2": round(ks2, 3),
                    "Отклонение ≥0": round(max(dev, 0.0), 3),
                    "Отклонение <0": round(min(dev, 0.0), 3),
                }
            )

        chart_rows = _apply_orphan_advance_to_chart_rows(chart_rows, orphan_mln)
        chart_caption = (
            f"График показывает топ-{len(chart_rows)} из "
            f"{int(view.contractor.nunique())} контрагентов/договоров "
            "по убыванию значения."
        )

    detail = (
        view.groupby(["project", "contractor", "contract"], as_index=False, dropna=False)
        .agg(
            contract_date=("contract_date", "min"),
            contract_sum=("contract_sum", "max"),
            advance=("advance", "sum"),
            ks2=("ks2", "sum"),
            fulfilled=("fulfilled", "sum"),
            paid=("paid", "sum"),
            balance=("balance", "sum"),
        )
    )

    rows: list[dict[str, Any]] = []
    for _, row in detail.iterrows():
        delta = float(row.advance) - float(row.ks2)
        contract = float(row.contract_sum)
        sem = _semaphore(delta, contract)
        rows.append(
            {
                "project": _clean(row.project),
                "contractor": _clean(row.contractor),
                "contract": _clean(row.contract),
                "contract_date": (
                    row.contract_date.strftime("%d.%m.%Y")
                    if pd.notna(row.contract_date)
                    else None
                ),
                "contract_sum": round(contract, 2),
                "advance": round(float(row.advance), 2),
                "ks2": round(float(row.ks2), 2),
                "fulfilled": round(float(row.fulfilled), 2),
                "paid": round(float(row.paid), 2),
                "balance": round(float(row.balance), 2),
                "advance_ks2": round(delta, 2),
                "advance_pct": sem["pct"],
                "advance_tone": sem["tone"],
            }
        )

    totals = {
        "contract_sum": round(float(detail.contract_sum.sum()), 2),
        "advance": round(float(detail.advance.sum()), 2),
        "ks2": round(float(detail.ks2.sum()), 2),
        "fulfilled": round(float(detail.fulfilled.sum()), 2),
        "paid": round(float(detail.paid.sum()), 2),
        "balance": round(float(detail.balance.sum()), 2),
    }
    totals["advance_ks2"] = round(totals["advance"] - totals["ks2"], 2)
    total_sem = _semaphore(totals["advance_ks2"], totals["contract_sum"])
    totals["advance_pct"] = total_sem["pct"]
    totals["advance_tone"] = total_sem["tone"]

    mode = "stack" if display_view == "С группировкой" else "group"
    return {
        "meta": {
            "rows": len(rows),
            "version_id": version_id,
            "data_mode": DATA_MODE,
            "source": "web_data.db",
            "parity": "main_dashboard_debit_credit",
            "warning": None,
            "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        },
        "filters": {
            "projects": projects,
            "contractors": contractors,
            "contract_nos": contract_nos,
            "date_min": (
                frame.contract_date.min().date().isoformat()
                if frame.contract_date.notna().any()
                else None
            ),
            "date_max": (
                frame.contract_date.max().date().isoformat()
                if frame.contract_date.notna().any()
                else None
            ),
            "applied": {
                "project": applied_project,
                "contractor": contractor or "Все",
                "contract_q": contract_q or "",
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
                "display_view": display_view,
            },
        },
        "chart": {
            "rows": chart_rows,
            "mode": mode,
            "aggregation": chart_aggregation,
            "caption": chart_caption,
            "unit": "млн ₽",
        },
        "rows": rows,
        "totals": totals,
        "kpis": {
            "contract_sum": totals["contract_sum"],
            "advance": totals["advance"],
            "ks2": totals["ks2"],
            "fulfilled": totals["fulfilled"],
            "paid": totals["paid"],
            "balance": totals["balance"],
            "advance_ks2": totals["advance_ks2"],
        },
    }
