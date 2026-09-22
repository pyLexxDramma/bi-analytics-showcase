"""ТОП-дашборд: агрегатор существующих отчётов + мок прототипа 21.09."""

from __future__ import annotations

import logging
import re
import threading
import unicodedata
from datetime import date, timedelta
from typing import Any

from app.config import DATA_MODE, WEB_DB_PATH
from app.services.db_ingest import db_status
from app.services.report_cache import cache_get, cache_set

logger = logging.getLogger(__name__)

MILESTONES_TZ = [
    "Завершение СМР по блоку А до ЗОС",
    "Завершение СМР по блоку U1. U2 до ЗОС",
    "Завершение СМР по блоку U3. U4 до ЗОС",
    "Завершение СМР по КПП до ЗОС",
    "Завершение СМР по блокам",
    "Завершение СМР по техническим помещениям",
    "Завершение работ по отделке",
    "Завершение работ по эл.сетям + оборудование",
    "Завершение работ по газовым сетям + оборудование",
    "Завершение работ по НВК и оборудование",
    "Завершение СМР по ЗАВОД до ЗОС",
]

COVENANTS_TZ = [
    "ГПЗУ",
    "Стадия П",
    "Корректировка стадии П",
    "стадия РД",
    "СЗЗ",
    "Экспертиза",
    "Корректировка экспертизы",
    "Разрешение РС",
    "КОД, ОТКР. ФИНАНС. (начало финансирования)",
    "СМР (начало)",
    "Корректировка РС",
    "Пуск электричества",
    "Пуск газа",
    "ЗОС",
    "РВ",
    "Право 1",
    "ВЫКУП ЗУ",
    "Право 2",
]

CARD_COVENANTS = ("ЗОС", "Право 1", "ВЫКУП ЗУ", "Право 2")

_MONTHS_RU = (
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


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).casefold()
    return re.sub(r"[\s_./\\]+", " ", text).strip()


def _slug(name: str) -> str:
    raw = unicodedata.normalize("NFKD", str(name or "")).casefold()
    slug = re.sub(r"[^\w]+", "-", raw, flags=re.UNICODE).strip("-")
    return slug or "p"


_STABLE_IDS = (
    ("dmitr", "дмитров"),
    ("esip", "есипов"),
    ("zhuk", "жуковск"),
    ("len", "ленинск"),
    ("novo", "новориж"),
)


def _stem(value: Any) -> str:
    text = _norm(value)
    text = re.sub(r"[-–—]", " ", text)
    text = re.sub(r"\b(проект|жк|пк|корп|корпус)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _compact(value: Any) -> str:
    return re.sub(r"[\s\-–—]+", "", _stem(value))


def _match_score(needle: str, hay: str) -> int:
    n, h = _norm(needle), _norm(hay)
    if not n or not h:
        return 0
    if n == h:
        return 100
    ns, hs = _stem(needle), _stem(hay)
    if ns and hs and ns == hs:
        return 90
    nc, hc = _compact(needle), _compact(hay)
    if nc and hc and nc == hc:
        return 85
    if ns and hs and (ns in hs or hs in ns):
        ntok = ns.split()[0]
        htok = hs.split()[0]
        if ntok == htok or (len(ntok) >= 5 and (ntok in htok or htok in ntok)):
            return 70
    return 0


def _match_name(needle: str, hay: str) -> bool:
    return _match_score(needle, hay) >= 70


def _best_key(keys: list[str] | tuple[str, ...] | set[str], project: str) -> str | None:
    scored = [(key, _match_score(project, key)) for key in keys if str(key).strip()]
    scored = [(key, score) for key, score in scored if score > 0]
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[1], -len(str(item[0]))))
    best = scored[0][1]
    tops = [key for key, score in scored if score == best]
    if len(tops) > 1 and best < 90:
        return None
    return scored[0][0]


def _stable_id(name: str, idx: int) -> str:
    n = _norm(name)
    for sid, stem in _STABLE_IDS:
        if stem in n:
            return sid
    return _slug(name)


def _is_rv_task(task: str) -> bool:
    n = _stem(task)
    if not n:
        return False
    if n == "рв" or n.startswith("рв ") or n.endswith(" рв") or " рв " in n:
        return True
    return "разрешение на ввод" in n


def _reason_text(row: dict[str, Any]) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for key in ("reason", "notes", "comment", "main_reason"):
        val = str(row.get(key) or "").strip()
        if not val or val in {"—", "None", "nan", "NaT"}:
            continue
        low = val.casefold()
        if low in seen:
            continue
        seen.add(low)
        parts.append(val)
    return "; ".join(parts) if parts else "—"


def _filter_opts(raw: Any) -> list[str]:
    skip = {"", "все", "all", "итого", "всего"}
    out: list[str] = []
    for item in raw or []:
        if isinstance(item, dict):
            label = str(item.get("name") or item.get("id") or item.get("project") or "").strip()
        else:
            label = str(item or "").strip()
        if label and _norm(label) not in skip:
            out.append(label)
    return out


def _find_row(rows: list[dict[str, Any]], project: str, key: str = "project") -> dict[str, Any] | None:
    for row in rows:
        label = str(row.get(key) or row.get("object") or row.get("name") or "")
        if _match_name(project, label):
            return row
    return None


def _num(value: Any) -> float:
    try:
        if value is None or value == "" or value == "—":
            return 0.0
        return float(str(value).replace(" ", "").replace(",", ".").replace("%", ""))
    except (TypeError, ValueError):
        return 0.0


def _fmt_date(value: Any) -> str:
    if value is None or value == "" or str(value).strip() in {"—", "nan", "NaT", "None"}:
        return "—"
    parsed = None
    text = str(value).strip()
    if re.match(r"\d{2}\.\d{2}\.\d{4}$", text):
        return text
    try:
        import pandas as pd

        parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
        if parsed is not None and parsed == parsed:  # not NaT
            return parsed.strftime("%d.%m.%Y")
    except Exception:
        pass
    return text or "—"


def _delta_from_days(days: int | None) -> tuple[str, str]:
    if days is None:
        return "—", ""
    if days == 0:
        return "0д", ""
    if days > 0:
        return f"-{days}д", "delta-negative"
    return f"+{abs(days)}д", "delta-positive"


def _days_between(plan: str, fact: str) -> int | None:
    if not plan or plan == "—" or not fact or fact == "—":
        return None
    try:
        import pandas as pd

        p = pd.to_datetime(plan, errors="coerce", dayfirst=True)
        f = pd.to_datetime(fact, errors="coerce", dayfirst=True)
        if p != p or f != f:
            return None
        return int((f.normalize() - p.normalize()).days)
    except Exception:
        return None


def _indicator(plan: float, fact: float) -> str:
    if plan <= 0:
        return "green" if fact <= 0 else "red"
    ratio = fact / plan
    if ratio >= 0.95:
        return "green"
    if ratio >= 0.8:
        return "yellow"
    return "red"


def _status_from_indicators(inds: list[str]) -> str:
    if "red" in inds:
        return "critical"
    if "yellow" in inds:
        return "warning"
    return "good"


def _empty_date_row(name: str) -> dict[str, Any]:
    return {"name": name, "plan": "—", "fact": "—", "delta": "—", "statusClass": ""}


def _schedule_row(name: str, plan: str, fact: str, days: int | None = None) -> dict[str, Any]:
    if days is None:
        days = _days_between(plan, fact)
    delta, klass = _delta_from_days(days)
    return {"name": name, "plan": plan or "—", "fact": fact or "—", "delta": delta, "statusClass": klass}


def _gdrs_day_minus_one() -> tuple[str, str, str]:
    today = date.today()
    day = today - timedelta(days=1)
    month = f"{_MONTHS_RU[day.month - 1]} {day.year}"
    iso = day.isoformat()
    return month, iso, iso


def _mock_projects() -> list[dict[str, Any]]:
    raw = [
        {
            "id": "dmitr",
            "name": "Дмитровский 1",
            "short": "DMI-1",
            "status": "critical",
            "dds": {"plan": 3200, "fact": 3780},
            "bdr": {"plan": 2900, "fact": 3410},
            "labor": {"plan": 320, "fact": 184},
            "equip": {"plan": 45, "fact": 32},
            "smr": {"planPercent": 52, "factPercent": 47},
            "rd": {
                "planSheets": 420,
                "factSheets": 286,
                "planPercent": 100,
                "factPercent": 68,
                "customerOverdue": 14,
                "contractorOverdue": 23,
            },
            "prescriptions": {
                "totalIssued": 24,
                "closed": 12,
                "overdue": 12,
                "critOverdue": 4,
                "nonCritOverdue": 8,
            },
            "execDocs": {"total": 180, "done": 84},
            "reason": "Срыв поставок металлоконструкций, корректировка стадии П, дефицит кадров",
            "rvReason": "Задержка экспертизы и срыв поставок",
            "rvDate": {"plan": "01.12.2025", "fact": "—", "delta": "критический сдвиг"},
            "_shift": 20,
            "_len_like": False,
            "_harsh": True,
        },
        {
            "id": "esip",
            "name": "Есипово 5",
            "short": "ESP-5",
            "status": "warning",
            "dds": {"plan": 2750, "fact": 3020},
            "bdr": {"plan": 2520, "fact": 2790},
            "labor": {"plan": 245, "fact": 198},
            "equip": {"plan": 35, "fact": 27},
            "smr": {"planPercent": 68, "factPercent": 61},
            "rd": {
                "planSheets": 490,
                "factSheets": 363,
                "planPercent": 100,
                "factPercent": 74,
                "customerOverdue": 18,
                "contractorOverdue": 28,
            },
            "prescriptions": {
                "totalIssued": 19,
                "closed": 11,
                "overdue": 8,
                "critOverdue": 3,
                "nonCritOverdue": 5,
            },
            "execDocs": {"total": 210, "done": 128},
            "reason": "Задержка корректировки экспертизы, отставание по СМР",
            "rvReason": "Корректировка экспертизы затянулась",
            "rvDate": {"plan": "20.12.2025", "fact": "—", "delta": "под риском"},
            "_shift": 10,
            "_len_like": False,
            "_harsh": False,
        },
        {
            "id": "zhuk",
            "name": "Жуковский 1",
            "short": "ZHK-1",
            "status": "warning",
            "dds": {"plan": 2450, "fact": 2670},
            "bdr": {"plan": 2280, "fact": 2480},
            "labor": {"plan": 215, "fact": 168},
            "equip": {"plan": 32, "fact": 24},
            "smr": {"planPercent": 64, "factPercent": 53},
            "rd": {
                "planSheets": 370,
                "factSheets": 300,
                "planPercent": 100,
                "factPercent": 81,
                "customerOverdue": 9,
                "contractorOverdue": 17,
            },
            "prescriptions": {
                "totalIssued": 14,
                "closed": 7,
                "overdue": 7,
                "critOverdue": 2,
                "nonCritOverdue": 5,
            },
            "execDocs": {"total": 160, "done": 85},
            "reason": "Низкая явка ресурсов по техническим помещениям",
            "rvReason": "Отставание по эл.сетям и разрешению РС",
            "rvDate": {"plan": "01.11.2025", "fact": "—", "delta": "вероятен сдвиг"},
            "_shift": 10,
            "_len_like": False,
            "_harsh": False,
        },
        {
            "id": "len",
            "name": "Ленинский",
            "short": "LEN-2",
            "status": "good",
            "dds": {"plan": 2100, "fact": 1980},
            "bdr": {"plan": 1950, "fact": 1840},
            "labor": {"plan": 210, "fact": 228},
            "equip": {"plan": 28, "fact": 30},
            "smr": {"planPercent": 85, "factPercent": 89},
            "rd": {
                "planSheets": 315,
                "factSheets": 302,
                "planPercent": 100,
                "factPercent": 96,
                "customerOverdue": 2,
                "contractorOverdue": 5,
            },
            "prescriptions": {
                "totalIssued": 8,
                "closed": 8,
                "overdue": 0,
                "critOverdue": 0,
                "nonCritOverdue": 0,
            },
            "execDocs": {"total": 140, "done": 125},
            "reason": "Опережение графика, экономия бюджета",
            "rvReason": "—",
            "rvDate": {"plan": "15.10.2025", "fact": "10.10.2025", "delta": "-5д (опережение)"},
            "_shift": -15,
            "_len_like": True,
            "_harsh": False,
        },
        {
            "id": "novo",
            "name": "Новорижский",
            "short": "NOV-R",
            "status": "critical",
            "dds": {"plan": 3800, "fact": 4350},
            "bdr": {"plan": 3500, "fact": 4020},
            "labor": {"plan": 350, "fact": 205},
            "equip": {"plan": 50, "fact": 31},
            "smr": {"planPercent": 45, "factPercent": 29},
            "rd": {
                "planSheets": 610,
                "factSheets": 342,
                "planPercent": 100,
                "factPercent": 56,
                "customerOverdue": 35,
                "contractorOverdue": 52,
            },
            "prescriptions": {
                "totalIssued": 32,
                "closed": 12,
                "overdue": 20,
                "critOverdue": 7,
                "nonCritOverdue": 13,
            },
            "execDocs": {"total": 260, "done": 75},
            "reason": "Критическое отставание по экспертизе, срыв СМР",
            "rvReason": "Экспертиза не пройдена, пуск электричества отложен",
            "rvDate": {"plan": "30.06.2026", "fact": "—", "delta": "срыв сроков"},
            "_shift": 40,
            "_len_like": False,
            "_harsh": True,
        },
    ]
    out: list[dict[str, Any]] = []
    for item in raw:
        shift = int(item.pop("_shift"))
        len_like = bool(item.pop("_len_like"))
        harsh = bool(item.pop("_harsh"))
        item["milestones"] = _mock_milestones(item["id"], shift, len_like, harsh)
        item["covenants"] = _mock_covenants(item["id"], shift, len_like, harsh)
        rv = next((c for c in item["covenants"] if c["name"] == "РВ"), None)
        if rv:
            item["rvDate"] = {"plan": rv["plan"], "fact": rv["fact"], "delta": rv["delta"]}
        item["idOverdueContractor"] = _mock_overdue_rows(item["rd"]["contractorOverdue"], 5)
        item["idOverdueCustomer"] = _mock_overdue_rows(item["rd"]["customerOverdue"], 3)
        out.append(item)
    return out


def _mock_milestones(project_id: str, shift: int, len_like: bool, harsh: bool) -> list[dict[str, Any]]:
    from datetime import datetime

    base = datetime(2025, 1, 15)
    rows: list[dict[str, Any]] = []
    for idx, name in enumerate(MILESTONES_TZ):
        plan = base + timedelta(days=idx * 12 + shift)
        if len_like:
            days = -((idx % 4) + 1) if idx % 2 == 0 else (idx % 3) + 2
        elif harsh:
            days = 15 + (idx * 3) % 20
        else:
            days = ((idx * 5) % 21) - 5
        fact = plan + timedelta(days=days)
        rows.append(_schedule_row(name, plan.strftime("%d.%m.%Y"), fact.strftime("%d.%m.%Y"), days))
    return rows


def _mock_covenants(project_id: str, shift: int, len_like: bool, harsh: bool) -> list[dict[str, Any]]:
    from datetime import datetime

    base = datetime(2024, 9, 1)
    rows: list[dict[str, Any]] = []
    special = {"РВ", "ЗОС", "Право 1", "ВЫКУП ЗУ", "Право 2"}
    for idx, name in enumerate(COVENANTS_TZ):
        plan = base + timedelta(days=idx * 14 + shift)
        if name in special:
            days = -5 if len_like else 20 + (idx % 15)
        elif len_like:
            days = -((idx % 5) + 1) if idx % 2 == 0 else (idx % 6) + 2
        elif harsh:
            days = 15 + (idx * 2) % 30
        else:
            days = ((idx * 4) % 18) - 3
        fact = plan + timedelta(days=days)
        rows.append(_schedule_row(name, plan.strftime("%d.%m.%Y"), fact.strftime("%d.%m.%Y"), days))
    return rows


def _mock_overdue_rows(total: int, start_days: int) -> list[dict[str, Any]]:
    pool = ["ООО СтройМонтаж", "СК Развитие", "ГК Фундамент", "ООО ИнжСети"]
    if not total:
        return []
    show = min(int(total), 4)
    rows = [
        {
            "contractor": pool[i % len(pool)],
            "doc": f"ИД-{1000 + i * 7 + int(total)}",
            "days": f"{start_days + i * 2}д",
        }
        for i in range(show)
    ]
    if total > show:
        rows.append({"contractor": "", "doc": "", "days": f"…и ещё {int(total) - show}", "more": True})
    return rows


def mock_payload(*, project: str | None = None) -> dict[str, Any]:
    projects = _mock_projects()
    applied = (project or "all").strip() or "all"
    if applied not in {"all", "Все", ""}:
        filtered = [p for p in projects if p["id"] == applied or _match_name(applied, p["name"])]
        if filtered:
            projects = filtered
    return {
        "meta": {
            "source": "mock",
            "data_mode": DATA_MODE,
            "parity": "proto_21_09",
            "error": None,
            "db": db_status(),
        },
        "filters": {
            "projects": [{"id": p["id"], "name": p["name"]} for p in _mock_projects()],
            "applied": {"project": applied if applied not in {"Все", ""} else "all"},
        },
        "milestonesCatalog": list(MILESTONES_TZ),
        "covenantsCatalog": list(COVENANTS_TZ),
        "projects": projects,
    }


def _safe(label: str, fn, fallback: Any = None) -> Any:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        logger.warning("top-dashboard %s: %s", label, exc)
        return fallback


def _finance_map(payload: dict[str, Any] | None) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    if not payload:
        return out
    skip = {"", "все", "итого", "всего"}
    for row in payload.get("tremor", {}).get("by_project") or []:
        name = str(row.get("project") or "")
        if name and _norm(name) not in skip:
            out[name] = {"plan": _num(row.get("plan")), "fact": _num(row.get("fact"))}
    return out


def _gdrs_map(payload: dict[str, Any] | None) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    if not payload:
        return out
    skip = {"", "все", "итого", "всего"}
    for row in payload.get("project_rows") or []:
        name = str(row.get("project") or "")
        if name and _norm(name) not in skip:
            out[name] = {"plan": _num(row.get("plan")), "fact": _num(row.get("fact"))}
    return out


def _lookup_pair(mapping: dict[str, dict[str, float]], project: str) -> dict[str, float]:
    row = mapping.get(project)
    if row:
        return row
    key = _best_key(list(mapping.keys()), project)
    if key:
        return mapping[key]
    return {"plan": 0.0, "fact": 0.0}


def _presc_for_project(rows: list[dict[str, Any]], project: str) -> dict[str, int]:
    crit = 0
    non = 0
    total = 0
    closed = 0
    labels = {str(row.get("project") or "") for row in rows if str(row.get("project") or "").strip()}
    best = _best_key(labels, project) if project else None
    if project and not best:
        return {
            "totalIssued": 0,
            "closed": 0,
            "overdue": 0,
            "critOverdue": 0,
            "nonCritOverdue": 0,
        }
    for row in rows:
        label = str(row.get("project") or "")
        if project and label != best:
            continue
        total += 1
        status = str(row.get("status") or row.get("row_status") or "").casefold()
        resolved = bool(row.get("resolved")) or status in {"resolved", "closed", "снято"}
        if resolved:
            closed += 1
        overdue = bool(row.get("critical") is not None) and (
            status == "overdue" or _num(row.get("overdue_days")) > 0 and not resolved
        )
        if status == "overdue" or (not resolved and _num(row.get("overdue_days")) > 0):
            overdue = True
        if overdue:
            if row.get("critical"):
                crit += 1
            else:
                non += 1
    return {
        "totalIssued": total,
        "closed": closed,
        "overdue": crit + non,
        "critOverdue": crit,
        "nonCritOverdue": non,
    }


def _cell_to_sched(name: str, cell: dict[str, Any] | None) -> dict[str, Any]:
    if not cell:
        return _empty_date_row(name)
    plan = _fmt_date(cell.get("plan"))
    fact = _fmt_date(cell.get("fact"))
    otkl = str(cell.get("otkl") or "").strip()
    days = _days_between(plan, fact)
    if days is None:
        m = re.search(r"(-?\d+(?:[.,]\d+)?)", otkl.replace(" ", ""))
        if m:
            try:
                main_otkl = int(round(float(m.group(1).replace(",", "."))))
                # В матрице девпроектов: <0 опоздание, ≥0 вовремя/опережение.
                days = abs(main_otkl) if main_otkl < 0 or otkl.startswith("-") else -abs(main_otkl)
            except ValueError:
                days = None
    row = _schedule_row(name, plan, fact, days)
    if otkl and otkl not in {"—", "Н/Д"} and row["delta"] == "—":
        row["delta"] = otkl
    return row


def _matrix_covenants(project_row: dict[str, Any] | None, columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cells = (project_row or {}).get("cells") or {}
    out: list[dict[str, Any]] = []
    for name in COVENANTS_TZ:
        cell = None
        for col in columns:
            label = str(col.get("label") or col.get("key") or "")
            if _match_name(name, label):
                cell = cells.get(col.get("key")) or cells.get(label)
                break
        if cell is None:
            for key, value in cells.items():
                if _match_name(name, str(key)):
                    cell = value
                    break
        out.append(_cell_to_sched(name, cell if isinstance(cell, dict) else None))
    return out


def _match_schedule_rows(
    catalog: list[str],
    table_rows: list[dict[str, Any]],
    project: str,
    *,
    covenant: bool,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    used: set[int] = set()
    for name in catalog:
        found = None
        for idx, row in enumerate(table_rows):
            if idx in used:
                continue
            proj = str(row.get("project") or "")
            if project and proj and _match_score(project, proj) < 70:
                continue
            task = str(row.get("task") or row.get("label") or "")
            if _match_name(name, task) or (name == "РВ" and _is_rv_task(task)):
                found = row
                used.add(idx)
                break
        if not found:
            out.append(_empty_date_row(name))
            continue
        plan = _fmt_date(found.get("base_end") or found.get("plan_end"))
        fact = _fmt_date(found.get("plan_end"))
        days_i = _days_between(plan, fact)
        if days_i is None:
            days = found.get("dev_end_days")
            if isinstance(days, (int, float)):
                # Как в матрице: отрицательное = опоздание.
                days_i = abs(int(days)) if int(days) < 0 else -abs(int(days))
        out.append(_schedule_row(name, plan, fact, days_i))
    return out


def _smr_from_msp(frame: Any, project: str) -> dict[str, float] | None:
    if frame is None or getattr(frame, "empty", True):
        return None
    import pandas as pd

    work = frame.copy()
    work.columns = [str(c).strip() for c in work.columns]
    cols = {_norm(c): c for c in work.columns}
    proj_col = None
    for key in ("project name", "проект", "project"):
        if key in cols:
            proj_col = cols[key]
            break
    task_col = None
    for key in ("task name", "название", "block", "блок"):
        if key in cols:
            task_col = cols[key]
            break
    sub = work
    if proj_col:
        uniq = [str(x) for x in work[proj_col].dropna().astype(str).unique().tolist()]
        best = _best_key(uniq, project)
        if not best:
            return None
        sub = work.loc[work[proj_col].astype(str) == best]
    if task_col:
        smr_mask = sub[task_col].astype(str).str.contains("смр", case=False, na=False)
        if bool(smr_mask.any()):
            sub = sub.loc[smr_mask]
    if sub.empty:
        return None
    pct_col = None
    for key in ("процент завершения", "pct complete", "percent complete", "% завершения"):
        if key in cols and cols[key] in sub.columns:
            pct_col = cols[key]
            break
    fact = 0.0
    if pct_col:
        series = pd.to_numeric(sub[pct_col], errors="coerce").dropna()
        if not series.empty:
            mx = float(series.max())
            fact = mx * 100.0 if 0 < mx <= 1 else mx
    start_col = cols.get("base start") or cols.get("plan start")
    end_col = cols.get("base end") or cols.get("plan end")
    plan = fact
    if start_col and end_col and start_col in sub.columns and end_col in sub.columns:
        starts = pd.to_datetime(sub[start_col], errors="coerce")
        ends = pd.to_datetime(sub[end_col], errors="coerce")
        start = starts.min()
        end = ends.max()
        if pd.notna(start) and pd.notna(end) and end > start:
            total = max(int((end.normalize() - start.normalize()).days), 1)
            elapsed = int((pd.Timestamp(date.today()).normalize() - start.normalize()).days)
            elapsed = min(max(elapsed, 0), total)
            plan = 100.0 * elapsed / total
    return {"planPercent": round(plan), "factPercent": round(fact)}


def _exec_overdue_tables(payload: dict[str, Any] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    if not payload:
        return [], [], {"total": 0, "done": 0}
    kpis = payload.get("kpis") or {}
    total = int(kpis.get("total_docs") or 0)
    done = int(kpis.get("signed") or 0)
    rows = payload.get("rows") or []
    contractor: list[dict[str, Any]] = []
    customer: list[dict[str, Any]] = []
    for row in rows:
        item = {
            "contractor": str(row.get("contractor") or "—"),
            "doc": str(row.get("doc_number") or "—"),
            "days": f"{int(row.get('submit_late_days') or row.get('agree_late_days') or 0)}д",
        }
        late_c = row.get("submit_late_days")
        late_u = row.get("agree_late_days")
        if late_c and _num(late_c) > 0 and len(contractor) < 8:
            item["days"] = f"{int(_num(late_c))}д"
            contractor.append(item)
        elif late_u and _num(late_u) > 0 and len(customer) < 8:
            customer.append(
                {
                    "contractor": str(row.get("contractor") or "—"),
                    "doc": str(row.get("doc_number") or "—"),
                    "days": f"{int(_num(late_u))}д",
                }
            )
    return contractor, customer, {"total": total, "done": done}


def _short_code(name: str, idx: int) -> str:
    tokens = [t for t in re.split(r"\s+", str(name).strip()) if t]
    if not tokens:
        return f"P-{idx + 1}"
    letters = "".join(t[0] for t in tokens[:3] if t[:1].isalpha()).upper()
    digits = "".join(ch for ch in name if ch.isdigit())[:2]
    return (letters + (f"-{digits}" if digits else f"-{idx + 1}"))[:8]


def _plan_overdue_without_fact(row: dict[str, Any] | None) -> bool:
    plan = str((row or {}).get("plan") or "—")
    fact = str((row or {}).get("fact") or "—")
    if fact not in {"—", "", "None", "nan"}:
        return False
    if plan in {"—", "", "None", "nan"}:
        return False
    try:
        import pandas as pd

        parsed = pd.to_datetime(plan, errors="coerce", dayfirst=True)
        if parsed != parsed:
            return False
        return parsed.normalize() < pd.Timestamp(date.today()).normalize()
    except Exception:
        return False


def _finalize_project(proj: dict[str, Any]) -> dict[str, Any]:
    inds: list[str] = []
    dds_plan, dds_fact = _num(proj["dds"]["plan"]), _num(proj["dds"]["fact"])
    bdr_plan, bdr_fact = _num(proj["bdr"]["plan"]), _num(proj["bdr"]["fact"])
    if dds_plan > 0 or dds_fact > 0:
        inds.append(_indicator(dds_plan, dds_fact))
    if bdr_plan > 0 or bdr_fact > 0:
        inds.append(_indicator(bdr_plan, bdr_fact))
    labor_plan, labor_fact = _num(proj["labor"]["plan"]), _num(proj["labor"]["fact"])
    equip_plan, equip_fact = _num(proj["equip"]["plan"]), _num(proj["equip"]["fact"])
    if labor_plan > 0 or labor_fact > 0:
        inds.append(_indicator(labor_plan, labor_fact))
    if equip_plan > 0 or equip_fact > 0:
        inds.append(_indicator(equip_plan, equip_fact))
    if _num(proj["rd"].get("planSheets")) > 0:
        inds.append(_indicator(100.0, _num(proj["rd"].get("factPercent"))))
    smr_plan = _num(proj["smr"].get("planPercent"))
    smr_fact = _num(proj["smr"].get("factPercent"))
    if smr_plan > 0 or smr_fact > 0:
        inds.append(_indicator(smr_plan or 1.0, smr_fact))
    if _plan_overdue_without_fact(proj.get("rvDate")):
        inds.append("red")
    proj["status"] = _status_from_indicators(inds)
    return proj


def _build_live(*, project: str | None) -> dict[str, Any] | None:
    from app.services.bdds import build_bdds_payload
    from app.services.bdr import build_bdr_payload
    from app.services.core_bridge import load_msp_frame, prepare_web_db
    from app.services.developer_projects import build_developer_projects_payload
    from app.services.deviation_reasons import build_deviation_reasons_payload
    from app.services.executive_docs_db import build_executive_docs_payload
    from app.services.gdrs import build_gdrs_payload
    from app.services.prescriptions import build_prescriptions_payload
    from app.services.project_schedule import build_project_schedule_payload
    from app.services.working_documentation import build_working_documentation_payload

    if not WEB_DB_PATH.is_file():
        return None

    try:
        prepare_web_db()
    except Exception as exc:  # noqa: BLE001
        logger.warning("top-dashboard prepare_web_db: %s", exc)
        return None

    dev = _safe("developer-projects", lambda: build_developer_projects_payload())
    labels = _filter_opts((dev or {}).get("filters", {}).get("projects"))
    if not labels:
        return None

    bdds = _safe("bdds", lambda: build_bdds_payload(view="cumulative", hide_zero=False))
    bdr = _safe("bdr", lambda: build_bdr_payload(view="cumulative", hide_zero=False))
    people = _safe(
        "gdrs-people",
        lambda: build_gdrs_payload(
            resource_kind="people",
            plan_agg="За день",
            skud_agg="За день",
        ),
    )
    equip = _safe(
        "gdrs-equipment",
        lambda: build_gdrs_payload(
            resource_kind="equipment",
            plan_agg="За день",
            skud_agg="За день",
        ),
    )
    presc = _safe("prescriptions", lambda: build_prescriptions_payload(hide_resolved=False))
    reasons = _safe("deviation-reasons", lambda: build_deviation_reasons_payload())
    schedule = _safe("project-schedule", lambda: build_project_schedule_payload(show_reasons=True))
    exec_all = _safe("executive-docs", lambda: build_executive_docs_payload())
    rd_all = _safe("rd-opts", lambda: build_working_documentation_payload())
    rd_opts = _filter_opts(((rd_all or {}).get("filters") or {}).get("projects"))
    exec_opts = _filter_opts(((exec_all or {}).get("filters") or {}).get("projects"))

    bdds_map = _finance_map(bdds)
    bdr_map = _finance_map(bdr)
    labor_map = _gdrs_map(people)
    equip_map = _gdrs_map(equip)
    presc_rows = list((presc or {}).get("rows") or [])
    reason_rows = list((reasons or {}).get("rows") or [])
    sched_rows = list((schedule or {}).get("rows") or (schedule or {}).get("table") or [])
    if not sched_rows and isinstance(schedule, dict):
        sched_rows = list(schedule.get("gantt") or [])
    matrix = (dev or {}).get("matrix") or {}
    matrix_projects = list(matrix.get("projects") or [])
    matrix_cols = list(matrix.get("columns") or [])

    msp = None
    try:
        import web_schema  # type: ignore

        vid = web_schema.get_active_version_id()
        if vid:
            msp = load_msp_frame(int(vid))
    except Exception as exc:  # noqa: BLE001
        logger.warning("top-dashboard msp: %s", exc)

    projects: list[dict[str, Any]] = []
    for idx, label in enumerate(labels):
        dds = _lookup_pair(bdds_map, label)
        bdr_p = _lookup_pair(bdr_map, label)
        labor = _lookup_pair(labor_map, label)
        eq = _lookup_pair(equip_map, label)
        rd_opt = _best_key(rd_opts, label)
        rd_payload = (
            _safe(
                f"rd:{rd_opt}",
                lambda opt=rd_opt: build_working_documentation_payload(project=opt),
            )
            if rd_opt
            else None
        )
        rd_applied = ((rd_payload or {}).get("filters") or {}).get("applied") or {}
        rd_applied_p = rd_applied.get("projects") or rd_applied.get("project")
        if isinstance(rd_applied_p, str):
            rd_applied_p = [rd_applied_p]
        rd_ok = bool(rd_opt and rd_applied_p and "Все" not in rd_applied_p)
        rd_kpis = (rd_payload or {}).get("kpis") or {}
        plan_sheets = int(rd_kpis.get("plan_to_date") or rd_kpis.get("plan_total") or 0) if rd_ok else 0
        fact_sheets = int(rd_kpis.get("issued_production") or 0) if rd_ok else 0
        fact_pct = int(round(100.0 * fact_sheets / plan_sheets)) if plan_sheets else 0
        presc_p = _presc_for_project(presc_rows, label)
        exec_opt = _best_key(exec_opts, label)
        exec_p = (
            _safe(
                f"exec:{exec_opt}",
                lambda opt=exec_opt: build_executive_docs_payload(project=opt),
            )
            if exec_opt
            else None
        )
        id_c, id_u, exec_tot = _exec_overdue_tables(exec_p)
        matrix_names = [str(r.get("project") or "") for r in matrix_projects]
        matrix_best = _best_key(matrix_names, label)
        matrix_row = next(
            (r for r in matrix_projects if str(r.get("project") or "") == matrix_best),
            None,
        ) if matrix_best else None
        covenants = _matrix_covenants(matrix_row, matrix_cols)
        if all(c["plan"] == "—" for c in covenants) and sched_rows:
            covenants = _match_schedule_rows(COVENANTS_TZ, sched_rows, label, covenant=True)
        milestones = _match_schedule_rows(MILESTONES_TZ, sched_rows, label, covenant=False)
        rv = next((c for c in covenants if c["name"] == "РВ"), _empty_date_row("РВ"))
        rv_reason = "—"
        reason_labels = {str(row.get("project") or "") for row in reason_rows if str(row.get("project") or "").strip()}
        reason_best = _best_key(reason_labels, label)
        for row in reason_rows:
            proj = str(row.get("project") or "")
            if reason_best and proj != reason_best:
                continue
            if not reason_best and proj and _match_score(label, proj) < 70:
                continue
            task = str(row.get("task") or "")
            if _is_rv_task(task):
                text = _reason_text(row)
                if text != "—":
                    rv_reason = text
                    break
        smr = _smr_from_msp(msp, label) or {"planPercent": 0, "factPercent": 0}
        proj = {
            "id": _stable_id(label, idx),
            "name": label,
            "short": _short_code(label, idx),
            "status": "good",
            "dds": {"plan": round(dds["plan"]), "fact": round(dds["fact"])},
            "bdr": {"plan": round(bdr_p["plan"]), "fact": round(bdr_p["fact"])},
            "labor": {"plan": round(labor["plan"]), "fact": round(labor["fact"])},
            "equip": {"plan": round(eq["plan"]), "fact": round(eq["fact"])},
            "smr": smr,
            "rd": {
                "planSheets": plan_sheets,
                "factSheets": fact_sheets,
                "planPercent": 100,
                "factPercent": fact_pct,
                "customerOverdue": int(((exec_p or {}).get("kpis") or {}).get("customer_overdue", {}).get("count") or 0),
                "contractorOverdue": int(((exec_p or {}).get("kpis") or {}).get("contractor_overdue", {}).get("count") or 0),
            },
            "prescriptions": presc_p,
            "execDocs": {"total": exec_tot["total"], "done": exec_tot["done"]},
            "reason": rv_reason,
            "rvReason": rv_reason,
            "rvDate": {"plan": rv["plan"], "fact": rv["fact"], "delta": rv["delta"]},
            "milestones": milestones,
            "covenants": covenants,
            "idOverdueContractor": id_c,
            "idOverdueCustomer": id_u,
        }
        projects.append(_finalize_project(proj))

    applied = (project or "all").strip() or "all"
    visible = projects
    if applied not in {"all", "Все", ""}:
        visible = [p for p in projects if p["id"] == applied or _match_name(applied, p["name"])]
        if not visible:
            visible = projects
    return {
        "meta": {
            "source": "live",
            "data_mode": DATA_MODE,
            "parity": "web_data.db",
            "error": None,
            "db": db_status(),
        },
        "filters": {
            "projects": [{"id": p["id"], "name": p["name"]} for p in projects],
            "applied": {"project": applied if applied not in {"Все", ""} else "all"},
        },
        "milestonesCatalog": list(MILESTONES_TZ),
        "covenantsCatalog": list(COVENANTS_TZ),
        "projects": visible if applied not in {"all", "Все", ""} else projects,
    }


_live_lock = threading.Lock()
_live_inflight: set[str] = set()


def _live_job(applied: str, cache_key: str) -> None:
    try:
        live = _safe("live", lambda: _build_live(project=applied))
        if live and live.get("projects"):
            cache_set("top-dashboard", cache_key, live)
    finally:
        with _live_lock:
            _live_inflight.discard(cache_key)


def build_top_dashboard_payload(*, project: str | None = None) -> dict[str, Any]:
    applied = (project or "all").strip() or "all"
    cache_key = f"v2|p={applied}|db={WEB_DB_PATH}|mtime={db_status().get('mtime')}"
    cached = cache_get("top-dashboard", cache_key, max_age_sec=1800)
    if cached is not None:
        return cached
    with _live_lock:
        if cache_key not in _live_inflight:
            _live_inflight.add(cache_key)
            threading.Thread(
                target=_live_job,
                args=(applied, cache_key),
                daemon=True,
            ).start()
    return mock_payload(project=applied)
