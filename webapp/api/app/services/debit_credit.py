"""ДЗ/КЗ подрядчиков — паритет с dashboard_debit_credit из web_data.db."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd

from app.config import DATA_MODE
from app.services.core_bridge import (
    active_version_id,
    import_dashboard_module,
    load_version_df,
    prepare_web_db,
    session_state,
)

_KS2_ARTICLES = {
    "поступление товаров и услуг",
    "поступление услуг из переработки",
    "поступления по основной деятельности",
}


def _clean(value: Any, empty: str = "—") -> str:
    text = str(value or "").strip()
    return empty if not text or text.casefold() in {"nan", "none", "nat", "<na>"} else text


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
            "date_min": None,
            "date_max": None,
            "applied": {},
        },
        "chart": {
            "rows": [],
            "mode": "group",
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
    }


def _semaphore(delta: float, contract_sum: float) -> dict[str, Any]:
    """Как main `_dc_advance_*`: 🟢 ≤30%, 🟡 30–80%, 🔴 ≥80% от договора при delta>0."""
    if contract_sum <= 0:
        return {"tone": "green" if delta <= 0 else "red", "pct": None}
    if delta <= 0:
        return {"tone": "green", "pct": round(delta / contract_sum * 100, 1)}
    ratio = delta / contract_sum
    pct = round(ratio * 100, 1)
    if ratio <= 0.30:
        return {"tone": "green", "pct": pct}
    if ratio < 0.80:
        return {"tone": "yellow", "pct": pct}
    return {"tone": "red", "pct": pct}


def _prepare_frame(version_id: int) -> pd.DataFrame:
    renderer = import_dashboard_module("_renderers")
    work = load_version_df(version_id, "debit_credit")
    reference = load_version_df(version_id, "reference_dannye")
    if reference is None or reference.empty:
        reference = load_version_df(version_id, "reference_1c_dannye")
    if work is None or work.empty:
        return pd.DataFrame()

    work = work.copy()
    work.columns = [str(c).strip() for c in work.columns]
    reference = (
        reference.copy()
        if reference is not None
        else pd.DataFrame()
    )
    if not reference.empty:
        reference.columns = [str(c).strip() for c in reference.columns]
    session_state()["reference_1c_dannye"] = reference
    session_state()["reference_dannye"] = reference

    find = renderer._find_col
    to_num = renderer._to_num

    contractor_col = find(
        work,
        [
            "Название контрагента",
            "Название организации",
            "Подрядчик",
            "Контрагент",
            "contractor",
        ],
    )
    partner_id_col = find(
        work, ["ID_Контрагента", "Контрагент_ID_Контрагента", "Контрагент.ID_Контрагента"]
    )
    contract_col = find(work, ["Номер договора", "НомерДоговора", "Договор", "contract"])
    dog_id_col = find(
        work, ["ID_Договора", "Договор_ID_Договора", "Договор.ID_Договора", "1C_ID_DOG"]
    )
    project_col = find(
        work, ["Наименование_Проекта", "Проект", "project name", "Project"]
    )
    date_col = find(work, ["Дата договора", "ДатаДоговора", "Дата Договора"])
    sum_col = find(
        work,
        [
            "Сумма в договоре",
            "СуммаДоговора",
            "Сумма_Договора",
            "Договор_СуммаДоговора",
            "Сумма договора",
        ],
    )
    advance_col = find(work, ["Аванс", "Авансированная сумма", "ВсегоОплат_Аванс", "advance"])
    advance_alt_col = find(
        work, ["ОстатокНаКонецПериодаПоАвансам", "Остаток на конец периода по авансам"]
    )
    paid_col = find(work, ["Выплачено", "Выплаченная сумма", "ВсегоОплат", "paid"])
    gross_col = find(
        work, ["ОстатокНаКонецПериода", "Остаток на конец периода", "ОстатокНаКонец"]
    )

    dog_ids = (
        work[dog_id_col].astype(str).str.strip().str.lower()
        if dog_id_col
        else pd.Series("", index=work.index)
    )
    dog_lookup = renderer._load_dogovor_lookup() or {}
    try:
        renderer._pred_projekts_1c_lookup()
    except Exception:
        pass

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
    contract_sum = to_num(work[sum_col]) if sum_col else pd.Series(0.0, index=work.index)
    for index, dog_id in dog_ids.items():
        record = dog_lookup.get(str(dog_id)) or {}
        if contracts.at[index] == "—":
            contracts.at[index] = _clean(record.get("Номер_Договора"))
        if projects.at[index] == "—":
            projects.at[index] = _clean(record.get("Наименование_Проекта"))
        if not float(contract_sum.at[index] or 0):
            contract_sum.at[index] = float(
                to_num(pd.Series([record.get("Сумма_Договора")])).iloc[0]
            )

    ks2 = pd.Series(0.0, index=work.index)
    if not reference.empty:
        article_col = find(reference, ["СтатьяОборотов", "Статья оборотов", "turnover item"])
        amount_col = find(reference, ["Сумма", "СуммаОборота", "amount"])
        ref_dog_col = find(reference, ["ID_Договора", "id_договора", "id_dogovora"])
        ref_partner_col = find(
            reference, ["ID_Контрагента", "id_контрагента", "id_kontragenta"]
        )
        if article_col and amount_col:
            so = reference[article_col].astype(str).str.strip().str.casefold()
            filtered = reference.loc[so.isin(_KS2_ARTICLES)].copy()
            if not filtered.empty:
                filtered["_sum"] = to_num(filtered[amount_col])
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

    advance = to_num(work[advance_col]) if advance_col else pd.Series(0.0, index=work.index)
    if float(advance.abs().sum()) < 1e-9 and advance_alt_col:
        advance = to_num(work[advance_alt_col])
    paid = to_num(work[paid_col]) if paid_col else pd.Series(0.0, index=work.index)
    gross = to_num(work[gross_col]) if gross_col else pd.Series(0.0, index=work.index)
    adv_end = (
        to_num(work[advance_alt_col])
        if advance_alt_col
        else pd.Series(0.0, index=work.index)
    )
    balance = gross - adv_end
    dates = (
        pd.to_datetime(work[date_col], errors="coerce", dayfirst=True)
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
    view = frame.copy()
    if project and project != "Все":
        view = view[view.project.eq(project)]
    if contractor and contractor != "Все":
        view = view[view.contractor.eq(contractor)]
    if contract_q:
        view = view[
            view.contract.str.casefold().str.contains(
                contract_q.strip().casefold(), na=False
            )
        ]
    if date_from:
        view = view[
            view.contract_date.isna() | view.contract_date.ge(pd.Timestamp(date_from))
        ]
    if date_to:
        view = view[
            view.contract_date.isna()
            | view.contract_date.lt(pd.Timestamp(date_to) + pd.Timedelta(days=1))
        ]

    # Chart always by contractor (main), top 20
    chart_src = (
        view.groupby("contractor", as_index=False)[["advance", "ks2"]]
        .sum()
        .rename(columns={"contractor": "label"})
    )
    chart_src["deviation"] = chart_src.ks2 - chart_src.advance
    chart_src["_rank"] = chart_src.advance.abs() + chart_src.ks2.abs()
    chart_src = chart_src.sort_values("_rank", ascending=False, kind="stable").head(20)
    chart_rows = []
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

    rows: list[dict[str, Any]] = []
    for _, row in view.iterrows():
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
        "contract_sum": round(float(view.contract_sum.sum()), 2),
        "advance": round(float(view.advance.sum()), 2),
        "ks2": round(float(view.ks2.sum()), 2),
        "fulfilled": round(float(view.fulfilled.sum()), 2),
        "paid": round(float(view.paid.sum()), 2),
        "balance": round(float(view.balance.sum()), 2),
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
                "project": project or "Все",
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
            "caption": f"Топ {len(chart_rows)} из {int(view.contractor.nunique())} контрагентов",
            "unit": "млн ₽",
        },
        "rows": rows,
        "totals": totals,
    }
