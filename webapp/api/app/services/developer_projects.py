from __future__ import annotations

import math
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from app.services.data_paths import latest_web_files_by_project

MILESTONES = [
    (
        "Аренда ЗУ",
        "land_lease",
        [
            "регистрация договора субаренды",
            "подготовка договора аренды",
            "договор субаренды",
            "субаренд",
            "аренда зу",
            "инвестиционная. аренда",
        ],
        "invest",
    ),
    (
        "Готовый Продукт",
        "ready_product",
        [
            "рассмотрение и утверждение на инвестиционном комитете",
            "инвестиционном комитете",
            "готовый продукт",
            "этап готовый продукт",
            "этап готовый",
            "инвестиционная. готовый",
        ],
        "invest",
    ),
    (
        "ГПЗУ",
        "gpzu",
        [
            "гпзу",
            "градплан",
            "градостроительн",
            "план территории",
            "градостроительного плана",
            "зонирования",
            "согласование гп",
            "планировочных решений",
            "эскизный проект",
        ],
        "invest",
    ),
    (
        "Экспертиза стадии П",
        "exp_pd",
        [
            "экспертиза стадии п",
            "экспертиза стадии",
            "экспертиза пд",
            "экспертиза проектной документации",
            "экспертиза",
        ],
        "life",
    ),
    (
        "КОМАНДА РП",
        "rp_team",
        [
            "подбор команды",
            "команда рп",
            "распоряжение руководителя холдинга",
            "руководителя холдинга об утверждении",
            "назначен руководител",
            "проектную группу",
            "руководител проекта",
            "назначени руководител",
        ],
        "life",
    ),
    (
        "РС",
        "rs",
        [
            "разрешение рс",
            "разрешение на строительство рс",
            "разрешение на строительство (рс)",
            "разрешение на строительство",
            "рс:",
            "(рс)",
            "рзу рс",
        ],
        "life",
    ),
    (
        "Стадия РД",
        "rd_stage",
        [
            "стадия рд",
            "стадия рабочая документация (рд)",
            "рабочая документация (рд)",
        ],
        "life",
    ),
    (
        "Начало финансирования",
        "fin_start",
        [
            "код_откр_финанс",
            "код откр финанс",
            "код, откр. финанс.",
            "код откр. финанс.",
            "откр. финанс.",
            "откр финанс",
            "(начало финансирования)",
            "начало финансирования",
        ],
        "life",
    ),
    ("Завершение СМР", "smr_finish", ["завершение смр"], "life"),
    (
        "ЗОС",
        "zos",
        [
            "заключение о соответствии",
            "зос)",
            "зос (участок",
            "зос  (участок",
            "зос - 1 этап",
            "зос - 2 этап",
        ],
        "life",
    ),
    (
        "РВ",
        "rv",
        [
            "разрешение на ввод в эксплуатацию (рв)",
            "разрешение на ввод в эксплуатацию",
            "разрешение на ввод объекта",
            "разрешение на ввод",
            "ввод в эксплуатацию",
            "рв - 1 этап",
            "рв - 2 этап",
            "рв",
        ],
        "life",
    ),
]

_COLUMN_ALIASES = {
    "project": ["project name", "проект", "название проекта", "наименование проекта"],
    "task": ["task name", "название", "наименование задачи", "задача"],
    "plan": ["plan end", "базовое окончание", "плановое окончание", "план окончания"],
    "fact": ["actual finish", "окончание", "фактическое окончание", "факт окончания"],
    "pct": ["% complete", "pct complete", "процент завершения", "% завершения"],
    "phase": ["phase", "фаза", "блок"],
}


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).casefold()
    return re.sub(r"[\s_]+", " ", text).strip()


def _column_map(columns: list[Any]) -> dict[str, str]:
    normalized = {_normalize(column): str(column) for column in columns}
    result: dict[str, str] = {}
    for target, aliases in _COLUMN_ALIASES.items():
        for alias in aliases:
            source = normalized.get(_normalize(alias))
            if source:
                result[target] = source
                break
    return result


def _read_msp(path: Path) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            frame = pd.read_csv(path, sep=None, engine="python", encoding=encoding)
            return frame
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    return pd.DataFrame()


def _project_from_path(path: Path) -> str:
    stem = path.stem
    slug = re.sub(r"^msp_", "", stem, flags=re.IGNORECASE)
    slug = re.sub(r"_\d{2}-\d{2}-\d{4}$", "", slug)
    return slug.replace("_", " ").strip().title() or path.stem


def _as_date(value: Any) -> date | None:
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    return parsed.date() if pd.notna(parsed) else None


def _as_pct(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().replace("%", "").replace(",", ".")
    try:
        result = float(text)
    except ValueError:
        return None
    return result * 100 if 0 < result <= 1 else result


def _format_date(value: date | None) -> str | None:
    return value.strftime("%d.%m.%Y") if value else None


def _status(plan: date | None, fact: date | None, pct: float | None) -> str:
    if not plan and not fact:
        return "missing"
    if fact and (pct is not None and pct >= 100 or plan and fact <= plan):
        return "done"
    if plan and ((not fact and plan < date.today()) or (fact and fact > plan)):
        return "overdue"
    return "on_track"


def _empty_payload() -> dict[str, Any]:
    from app.config import DATA_MODE

    return {
        "meta": {"rows": 0, "source": "msp", "data_mode": DATA_MODE, "files": 0},
        "filters": {"projects": ["Все"], "applied": {"project": "Все"}},
        "kpis": {
            "projects": 0,
            "milestones_found": 0,
            "completed_pct": 0,
            "overdue": 0,
            "missing_fact": 0,
        },
        "tremor": {
            "completion_by_project": [],
            "status_mix": [
                {"name": "Выполнено", "value": 0},
                {"name": "Просрочено", "value": 0},
                {"name": "Без факта", "value": 0},
                {"name": "В срок", "value": 0},
            ],
        },
        "rows": [],
        "matrix": {
            "phases": [
                {"id": "invest", "label": "Инвестиционная фаза"},
                {"id": "life", "label": "Жизнь проекта"},
            ],
            "milestones": [
                {"slug": slug, "title": title, "phase": phase}
                for title, slug, _, phase in MILESTONES
            ],
            "projects": [],
        },
    }


def build_developer_projects_payload(*, project: str | None = None) -> dict[str, Any]:
    files = latest_web_files_by_project()
    if not files:
        return _empty_payload()

    rows: list[dict[str, Any]] = []
    projects: set[str] = set()
    for path in files:
        frame = _read_msp(path)
        if frame.empty:
            continue
        columns = _column_map(list(frame.columns))
        if "task" not in columns:
            continue
        fallback_project = _project_from_path(path)
        for _, record in frame.iterrows():
            task = str(record.get(columns["task"], "") or "").strip()
            phase = str(record.get(columns.get("phase", ""), "") or "").strip()
            haystack = f"{task} {phase}".casefold()
            project_name = str(record.get(columns.get("project", ""), "") or "").strip()
            project_name = project_name or fallback_project
            projects.add(project_name)
            for milestone, slug, needles, _ in MILESTONES:
                if not any(needle.casefold() in haystack for needle in needles):
                    continue
                plan = _as_date(record.get(columns.get("plan", "")))
                fact = _as_date(record.get(columns.get("fact", "")))
                pct = _as_pct(record.get(columns.get("pct", "")))
                delta = (plan - fact).days if plan and fact else None
                rows.append(
                    {
                        "project": project_name,
                        "milestone": milestone,
                        "slug": slug,
                        "plan": _format_date(plan),
                        "fact": _format_date(fact),
                        "otkl_days": delta,
                        "otkl": f"{delta:+d} дн." if delta else "0 дн." if delta == 0 else "Н/Д",
                        "pct_complete": round(pct, 1) if pct is not None and math.isfinite(pct) else None,
                        "status": _status(plan, fact, pct),
                    }
                )

    matched_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["project"], row["slug"])
        existing = matched_by_key.get(key)
        if existing is None or (
            existing["plan"] is None and row["plan"] is not None
        ):
            matched_by_key[key] = row

    rows = []
    for project_name in projects:
        for milestone, slug, _, _ in MILESTONES:
            rows.append(
                matched_by_key.get(
                    (project_name, slug),
                    {
                        "project": project_name,
                        "milestone": milestone,
                        "slug": slug,
                        "plan": None,
                        "fact": None,
                        "otkl_days": None,
                        "otkl": "Н/Д",
                        "pct_complete": None,
                        "status": "missing",
                    },
                )
            )

    available_projects = ["Все"] + sorted(projects, key=str.casefold)
    applied_project = project if project in available_projects else "Все"
    filtered = [row for row in rows if applied_project == "Все" or row["project"] == applied_project]
    filtered_projects = {row["project"] for row in filtered}
    matrix_projects = []
    for project_name in sorted(filtered_projects, key=str.casefold):
        project_rows = [row for row in filtered if row["project"] == project_name]
        matrix_projects.append(
            {
                "project": project_name,
                "cells": {
                    row["slug"]: {
                        "plan": row["plan"],
                        "fact": row["fact"],
                        "otkl": row["otkl"],
                        "otkl_days": row["otkl_days"],
                        "status": row["status"],
                    }
                    for row in project_rows
                },
            }
        )
    matrix = {
        "phases": [
            {"id": "invest", "label": "Инвестиционная фаза"},
            {"id": "life", "label": "Жизнь проекта"},
        ],
        "milestones": [
            {"slug": slug, "title": title, "phase": phase}
            for title, slug, _, phase in MILESTONES
        ],
        "projects": matrix_projects,
    }
    completed = sum(row["status"] == "done" for row in filtered)
    overdue = sum(row["status"] == "overdue" for row in filtered)
    missing = sum(row["status"] == "missing" for row in filtered)
    total = len(filtered)

    by_project = []
    for project_name in sorted(filtered_projects, key=str.casefold):
        project_rows = [row for row in filtered if row["project"] == project_name]
        project_completed = sum(row["status"] == "done" for row in project_rows)
        by_project.append(
            {
                "project": project_name,
                "completed": project_completed,
                "total": len(project_rows),
                "pct": round(project_completed / len(project_rows) * 100, 1) if project_rows else 0,
            }
        )

    from app.config import DATA_MODE

    return {
        "meta": {"rows": total, "source": "msp", "data_mode": DATA_MODE, "files": len(files)},
        "filters": {"projects": available_projects, "applied": {"project": applied_project}},
        "kpis": {
            "projects": len(filtered_projects),
            "milestones_found": total,
            "completed_pct": round(completed / total * 100, 1) if total else 0,
            "overdue": overdue,
            "missing_fact": missing,
        },
        "tremor": {
            "completion_by_project": by_project,
            "status_mix": [
                {"name": "Выполнено", "value": completed},
                {"name": "Просрочено", "value": overdue},
                {"name": "Без факта", "value": missing},
                {"name": "В срок", "value": sum(row["status"] == "on_track" for row in filtered)},
            ],
        },
        "rows": sorted(filtered, key=lambda row: (row["project"].casefold(), row["slug"])),
        "matrix": matrix,
    }
