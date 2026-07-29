from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from app.services.data_paths import latest_web_file

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_KS2_MARKERS = (
    "поступление товаров и услуг",
    "поступление услуг из переработки",
)


def _finite(v: Any, nd: int | None = None) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(x):
        return 0.0
    if nd is None:
        return x
    return round(x, nd)


def _parse_money(v: Any) -> float:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return 0.0
    if isinstance(v, (int, float)):
        return _finite(v)
    s = str(v).strip().replace("\u00a0", " ").replace(" ", "")
    if not s:
        return 0.0
    if "," in s and "." in s:
        # 49,500,000.00
        s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        if len(parts[-1]) <= 2:
            s = "".join(parts[:-1]) + "." + parts[-1]
        else:
            s = s.replace(",", "")
    try:
        return _finite(float(s))
    except ValueError:
        return 0.0


def _nested_str(obj: Any, *keys: str) -> str:
    if not isinstance(obj, dict):
        return str(obj or "").strip()
    for k in keys:
        if k in obj and obj[k] not in (None, ""):
            return str(obj[k]).strip()
    return ""


def _extract_uuid(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, dict):
        for k in (
            "ID_Договора",
            "id_договора",
            "ID_Контрагента",
            "id_контрагента",
            "ID_Проекта",
            "id",
            "ID",
        ):
            if k in v and v[k]:
                return str(v[k]).strip().lower()
        return ""
    m = _UUID_RE.search(str(v))
    return m.group(0).lower() if m else ""


def _load_json_list(path: Path | None) -> list[dict]:
    if path is None or not path.is_file():
        return []
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("data", "rows", "items"):
            if isinstance(data.get(key), list):
                return [x for x in data[key] if isinstance(x, dict)]
    return []


def _build_ks2_by_contract(dannye: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in dannye:
        article = str(row.get("СтатьяОборотов") or "").casefold()
        if not any(m in article for m in _KS2_MARKERS):
            continue
        dog_id = str(row.get("ID_Договора") or "").strip().lower()
        if not dog_id or dog_id.startswith("00000000"):
            continue
        out[dog_id] = out.get(dog_id, 0.0) + _parse_money(row.get("Сумма"))
    return out


def _build_project_lookup(projekts: list[dict], dannye: list[dict]) -> dict[str, str]:
    """Map contract / partner / project id → display name."""
    by_project_id: dict[str, str] = {}
    for row in projekts:
        pid = _extract_uuid(
            row.get("ID_Проекта")
            or row.get("Проект")
            or row
        )
        name = _nested_str(
            row,
            "НаименованиеПроекта",
            "Наименование",
            "Проект",
            "project name",
            "name",
        )
        if isinstance(row.get("Проект"), dict):
            pid = pid or _extract_uuid(row["Проект"])
            name = name or _nested_str(
                row["Проект"], "НаименованиеПроекта", "Наименование", "name"
            )
        if pid and name:
            by_project_id[pid] = name

    for row in dannye:
        pid = str(row.get("ID_Проекта") or "").strip().lower()
        name = str(row.get("Проект") or "").strip()
        if pid and name and not pid.startswith("00000000"):
            by_project_id.setdefault(pid, name)
    return by_project_id


def _dogovor_maps(dogovor: list[dict]) -> tuple[dict[str, float], dict[str, str]]:
    sums: dict[str, float] = {}
    projects: dict[str, str] = {}
    for row in dogovor:
        dog = row.get("Договор") if isinstance(row.get("Договор"), dict) else row
        dog_id = _extract_uuid(dog) or str(row.get("ID_Договора") or "").strip().lower()
        if not dog_id:
            continue
        amount = _parse_money(
            (dog or {}).get("СуммаДоговора")
            if isinstance(dog, dict)
            else None
        ) or _parse_money(row.get("СуммаДоговора") or row.get("Сумма договора"))
        if amount:
            sums[dog_id] = amount
        proj = row.get("Проект")
        if isinstance(proj, dict):
            pname = _nested_str(proj, "НаименованиеПроекта", "Наименование", "name")
            if pname:
                projects[dog_id] = pname
        elif proj:
            projects[dog_id] = str(proj).strip()
        elif row.get("НаименованиеПроекта"):
            projects[dog_id] = str(row["НаименованиеПроекта"]).strip()
    return sums, projects


@lru_cache(maxsize=1)
def _source_mtime_key() -> tuple[float, ...]:
    paths = [
        latest_web_file("_DK.json"),
        latest_web_file("_Dogovor.json"),
        latest_web_file("_dannye.json"),
        latest_web_file("_Projekts.json"),
    ]
    return tuple(p.stat().st_mtime if p and p.is_file() else 0.0 for p in paths)


@lru_cache(maxsize=4)
def load_debit_credit_frame(_mtime_key: tuple[float, ...]) -> pd.DataFrame:
    del _mtime_key  # cache busting only
    dk_rows = _load_json_list(latest_web_file("_DK.json"))
    dog_rows = _load_json_list(latest_web_file("_Dogovor.json"))
    dannye_rows = _load_json_list(latest_web_file("_dannye.json"))
    proj_rows = _load_json_list(latest_web_file("_Projekts.json"))

    dog_sums, dog_projects = _dogovor_maps(dog_rows)
    ks2_by_dog = _build_ks2_by_contract(dannye_rows)
    project_names = _build_project_lookup(proj_rows, dannye_rows)

    records: list[dict[str, Any]] = []
    for row in dk_rows:
        contractor = _nested_str(
            row.get("Контрагент"),
            "НаименованиеКонтрагента",
            "Наименование",
            "name",
        ) or str(row.get("Название контрагента") or "").strip()
        dog = row.get("Договор") if isinstance(row.get("Договор"), dict) else {}
        contract_no = _nested_str(dog, "НомерДоговора", "Номер договора", "name")
        dog_id = _extract_uuid(dog) or str(row.get("ID_Договора") or "").strip().lower()
        contract_date_raw = dog.get("ДатаДоговора") if isinstance(dog, dict) else None
        contract_sum = _parse_money(dog.get("СуммаДоговора") if isinstance(dog, dict) else None)
        if not contract_sum and dog_id:
            contract_sum = dog_sums.get(dog_id, 0.0)

        project = dog_projects.get(dog_id, "")
        if not project:
            # fallback: project from dannye by contract
            for d in dannye_rows:
                if str(d.get("ID_Договора") or "").strip().lower() == dog_id:
                    project = str(d.get("Проект") or "").strip()
                    if project:
                        break
        if not project:
            org = row.get("Организация")
            project = _nested_str(org, "НаименованиеОрганизации") if isinstance(org, dict) else ""

        paid = _parse_money(row.get("ВсегоОплат") or row.get("Выплачено"))
        advance = _parse_money(row.get("ВсегоОплат_Аванс") or row.get("Аванс"))
        end_gross = _parse_money(
            row.get("ОстатокНаКонецПериода") or row.get("ОстатокНаКонец")
        )
        end_adv = _parse_money(row.get("ОстатокНаКонецПериодаПоАвансам"))
        if abs(advance) < 1e-6 and abs(end_adv) > 1e-6:
            advance = end_adv
        balance_net = end_gross - end_adv if (end_gross or end_adv) else _parse_money(
            row.get("Остаток на конец периода")
        )
        ks2 = ks2_by_dog.get(dog_id, 0.0)
        period_dt = pd.to_datetime(contract_date_raw, errors="coerce", utc=True)
        if pd.notna(period_dt) and getattr(period_dt, "year", 9999) <= 1:
            period_dt = pd.NaT

        records.append(
            {
                "contractor": contractor,
                "project": project or "—",
                "contract": contract_no or "—",
                "contract_id": dog_id,
                "contract_date": (
                    period_dt.date().isoformat() if pd.notna(period_dt) else None
                ),
                "contract_sum": contract_sum,
                "paid": paid,
                "advance": advance,
                "ks2": ks2,
                "fulfilled": advance + ks2,
                "balance": balance_net,
                "deviation": (advance + ks2) - contract_sum if contract_sum else 0.0,
            }
        )

    return pd.DataFrame.from_records(records)


def get_frame() -> pd.DataFrame:
    return load_debit_credit_frame(_source_mtime_key()).copy()


def _apply_filters(
    df: pd.DataFrame,
    *,
    project: str | None = None,
    contractor: str | None = None,
    contract_q: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> pd.DataFrame:
    out = df
    if project and project != "Все":
        out = out[out["project"].astype(str).str.strip() == project.strip()]
    if contractor and contractor != "Все":
        out = out[out["contractor"].astype(str).str.strip() == contractor.strip()]
    q = (contract_q or "").strip()
    if q:
        ql = q.casefold()
        out = out[out["contract"].astype(str).map(lambda s: ql in s.casefold())]
    if date_from or date_to:
        dts = pd.to_datetime(out["contract_date"], errors="coerce")
        start = date_from or date.min
        end = date_to or date.max
        out = out[
            dts.isna()
            | (
                dts.notna()
                & (dts.dt.date >= start)
                & (dts.dt.date <= end)
            )
        ]
    return out


def _mln(v: float) -> float:
    return round(float(v or 0.0) / 1_000_000.0, 3)


def build_debit_credit_payload(
    *,
    project: str | None = None,
    contractor: str | None = None,
    contract_q: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    df = get_frame()
    if df.empty:
        from app.config import DATA_MODE, WEB_DATA_DIR

        return {
            "meta": {
                "rows": 0,
                "source": str(WEB_DATA_DIR),
                "data_mode": DATA_MODE,
                "pilot": "debit_credit",
            },
            "filters": {
                "projects": ["Все"],
                "contractors": ["Все"],
                "date_min": None,
                "date_max": None,
            },
            "kpis": {},
            "chart": {"categories": [], "series": []},
            "tremor": {
                "contract_vs_advance": [],
                "advance_by_project": [],
                "risk_note": "",
            },
            "rows": [],
        }

    projects = ["Все"] + sorted(
        {str(x).strip() for x in df["project"].dropna() if str(x).strip()},
        key=str.casefold,
    )
    contractors = ["Все"] + sorted(
        {str(x).strip() for x in df["contractor"].dropna() if str(x).strip()},
        key=str.casefold,
    )
    dts = pd.to_datetime(df["contract_date"], errors="coerce").dropna()
    date_min = dts.min().date().isoformat() if not dts.empty else None
    date_max = dts.max().date().isoformat() if not dts.empty else None

    filtered = _apply_filters(
        df,
        project=project,
        contractor=contractor,
        contract_q=contract_q,
        date_from=date_from,
        date_to=date_to,
    )

    group_col = "contractor" if contractor in (None, "", "Все") else "contract"
    grouped = (
        filtered.groupby(group_col, dropna=False)
        .agg(
            advance=("advance", "sum"),
            ks2=("ks2", "sum"),
            deviation=("deviation", "sum"),
            contract_sum=("contract_sum", "sum"),
            paid=("paid", "sum"),
            balance=("balance", "sum"),
            fulfilled=("fulfilled", "sum"),
        )
        .reset_index()
        .rename(columns={group_col: "label"})
    )
    grouped = grouped.sort_values("contract_sum", ascending=False)

    categories = grouped["label"].astype(str).tolist()
    chart = {
        "categories": categories,
        "series": [
            {
                "key": "advance",
                "name": "Аванс",
                "color": "#3B82F6",
                "values": [_mln(v) for v in grouped["advance"].tolist()],
            },
            {
                "key": "ks2",
                "name": "КС-2",
                "color": "#EAB308",
                "values": [_mln(v) for v in grouped["ks2"].tolist()],
            },
            {
                "key": "deviation_pos",
                "name": "Отклонение ≥ 0",
                "color": "#94A3B8",
                "values": [
                    _mln(v) if v >= 0 else 0.0 for v in grouped["deviation"].tolist()
                ],
            },
            {
                "key": "deviation_neg",
                "name": "Отклонение < 0",
                "color": "#F1948A",
                "values": [
                    _mln(v) if v < 0 else 0.0 for v in grouped["deviation"].tolist()
                ],
            },
        ],
        "unit": "млн ₽",
    }

    contract_sum_mln = _mln(float(filtered["contract_sum"].sum()))
    advance_mln = _mln(float(filtered["advance"].sum()))
    ks2_mln = _mln(float(filtered["ks2"].sum()))
    advance_pct = (
        round((float(filtered["advance"].sum()) / float(filtered["contract_sum"].sum())) * 100, 1)
        if float(filtered["contract_sum"].sum()) > 0
        else 0.0
    )
    kpis = {
        "contracts": int(len(filtered)),
        "contract_sum_mln": contract_sum_mln,
        "advance_mln": advance_mln,
        "ks2_mln": ks2_mln,
        "fulfilled_mln": _mln(float(filtered["fulfilled"].sum())),
        "balance_mln": _mln(float(filtered["balance"].sum())),
        "deviation_mln": _mln(float(filtered["deviation"].sum())),
        "advance_pct": advance_pct,
    }

    def _short(label: str, n: int = 18) -> str:
        s = str(label or "").strip()
        return s if len(s) <= n else s[: n - 1] + "…"

    contract_vs_advance = [
        {
            "label": _short(row["label"]),
            "Стоимость договора": _mln(float(row["contract_sum"])),
            "Аванс выдан": _mln(float(row["advance"])),
        }
        for _, row in grouped.iterrows()
    ]
    by_project = (
        filtered.groupby("project", dropna=False)["advance"]
        .sum()
        .reset_index()
        .sort_values("advance", ascending=False)
    )
    advance_by_project = [
        {
            "project": str(r["project"] or "—"),
            "advance": _mln(float(r["advance"])),
        }
        for _, r in by_project.iterrows()
        if float(r["advance"]) > 0
    ]

    rows = []
    for _, r in filtered.iterrows():
        rows.append(
            {
                "project": r["project"],
                "contractor": r["contractor"],
                "contract": r["contract"],
                "contract_date": r["contract_date"],
                "contract_sum": round(float(r["contract_sum"]), 2),
                "advance": round(float(r["advance"]), 2),
                "ks2": round(float(r["ks2"]), 2),
                "fulfilled": round(float(r["fulfilled"]), 2),
                "paid": round(float(r["paid"]), 2),
                "balance": round(float(r["balance"]), 2),
                "deviation": round(float(r["deviation"]), 2),
            }
        )

    from app.config import DATA_MODE, WEB_DATA_DIR

    return {
        "meta": {
            "rows": len(rows),
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "source": str(WEB_DATA_DIR),
            "data_mode": DATA_MODE,
            "pilot": "debit_credit",
        },
        "filters": {
            "projects": projects,
            "contractors": contractors,
            "date_min": date_min,
            "date_max": date_max,
            "applied": {
                "project": project or "Все",
                "contractor": contractor or "Все",
                "contract_q": contract_q or "",
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
            },
        },
        "kpis": kpis,
        "chart": chart,
        "tremor": {
            "contract_vs_advance": contract_vs_advance,
            "advance_by_project": advance_by_project,
            "risk_note": (
                f"По {len(filtered)} договорам авансы {advance_mln:.1f} млн ₽, "
                f"КС-2 = {ks2_mln:.1f} млн ₽."
                + (
                    " Работы по КС-2 пока не закрывают авансы — риск дебиторки."
                    if ks2_mln <= 0 and advance_mln > 0
                    else ""
                )
            ),
        },
        "rows": rows,
    }
