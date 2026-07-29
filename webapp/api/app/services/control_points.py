from __future__ import annotations

import math
from typing import Any

from app.config import DATA_MODE
from app.services.data_paths import latest_web_files_by_project
from app.services.developer_projects import (
    _as_date,
    _as_pct,
    _format_date,
    _normalize,
    _project_from_path,
    _read_msp,
    _status,
)

# Streamlit CONTROL_POINT_MILESTONES — needles only (level/covenant soft-match via substring)
CONTROL_POINT_MILESTONES: list[tuple[str, str, list[str]]] = [
    ("ГПЗУ", "gpzu", ["гпзу"]),
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
    ),
    (
        "Стадия РД",
        "rd_stage",
        [
            "стадия рд",
            "стадия рабочая документация (рд)",
            "рабочая документация (рд)",
        ],
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
    ),
    ("Завершение СМР", "smr_finish", ["завершение смр"]),
    ("Пуск электричества", "power_on", ["пуск электричества"]),
    ("Пуск газа", "gas_on", ["пуск газа"]),
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
    ),
    ("Право 1", "pravo1", ["право 1", "право 1 - 1 этап", "право 1 - 2 этап"]),
    ("Выкуп ЗУ", "vykup_zu", ["выкуп зу", "выкуп земельного участка"]),
    ("Право 2", "pravo2", ["право 2", "право 2 на застройщика"]),
]

_CP_COLUMN_ALIASES = {
    "project": ["project name", "проект", "название проекта", "наименование проекта"],
    "task": ["task name", "название", "наименование задачи", "задача"],
    # Streamlit CP: Plan = base end (fallback plan end); Fact = plan end
    "base": ["base end", "базовое окончание", "baseline finish", "базовый конец"],
    "plan": ["plan end", "плановое окончание", "план окончания", "окончание"],
    "fact": ["actual finish", "фактическое окончание", "факт окончания"],
    "pct": ["% complete", "pct complete", "процент завершения", "% завершения"],
    "phase": ["phase", "фаза", "блок", "section", "раздел"],
}


def _cp_column_map(columns: list[Any]) -> dict[str, str]:
    normalized = {_normalize(column): str(column) for column in columns}
    result: dict[str, str] = {}
    for target, aliases in _CP_COLUMN_ALIASES.items():
        for alias in aliases:
            source = normalized.get(_normalize(alias))
            if source:
                result[target] = source
                break
    return result


def _empty_payload() -> dict[str, Any]:
    return {
        "meta": {"rows": 0, "source": "msp", "data_mode": DATA_MODE, "files": 0},
        "filters": {"projects": ["Все"], "applied": {"project": "Все"}},
        "kpis": {
            "projects": 0,
            "milestones_found": 0,
            "completed_pct": 0.0,
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
        "matrix": {
            "milestones": [
                {"slug": slug, "title": title} for title, slug, _ in CONTROL_POINT_MILESTONES
            ],
            "projects": [],
        },
        "rows": [],
    }


def build_control_points_payload(*, project: str | None = None) -> dict[str, Any]:
    files = latest_web_files_by_project()
    if not files:
        return _empty_payload()

    matched: dict[tuple[str, str], dict[str, Any]] = {}
    projects: set[str] = set()

    for path in files:
        frame = _read_msp(path)
        if frame.empty:
            continue
        columns = _cp_column_map(list(frame.columns))
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

            for title, slug, needles in CONTROL_POINT_MILESTONES:
                if not any(n.casefold() in haystack for n in needles):
                    continue
                # CP semantics: plan≈base end, fact≈plan end (schedule)
                base = _as_date(record.get(columns.get("base", "")))
                plan_end = _as_date(record.get(columns.get("plan", "")))
                actual = _as_date(record.get(columns.get("fact", "")))
                plan = base or plan_end
                fact = plan_end or actual
                pct = _as_pct(record.get(columns.get("pct", "")))
                delta = (plan - fact).days if plan and fact else None
                if delta is None:
                    otkl = "Н/Д"
                elif delta == 0:
                    otkl = "0 дн."
                else:
                    otkl = f"{delta:+d} дн."
                row = {
                    "project": project_name,
                    "milestone": title,
                    "slug": slug,
                    "plan": _format_date(plan),
                    "fact": _format_date(fact),
                    "otkl_days": delta,
                    "otkl": otkl,
                    "pct_complete": round(pct, 1) if pct is not None and math.isfinite(pct) else None,
                    "status": _status(plan, fact, pct),
                }
                key = (project_name, slug)
                existing = matched.get(key)
                if existing is None or (existing["plan"] is None and row["plan"] is not None):
                    matched[key] = row

    rows: list[dict[str, Any]] = []
    for project_name in projects:
        for title, slug, _ in CONTROL_POINT_MILESTONES:
            rows.append(
                matched.get(
                    (project_name, slug),
                    {
                        "project": project_name,
                        "milestone": title,
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

    available = ["Все"] + sorted(projects, key=str.casefold)
    applied = project if project in available else "Все"
    filtered = [r for r in rows if applied == "Все" or r["project"] == applied]
    filtered_projects = {r["project"] for r in filtered}

    matrix_projects = []
    for project_name in sorted(filtered_projects, key=str.casefold):
        project_rows = [r for r in filtered if r["project"] == project_name]
        matrix_projects.append(
            {
                "project": project_name,
                "cells": {
                    r["slug"]: {
                        "plan": r["plan"],
                        "fact": r["fact"],
                        "otkl": r["otkl"],
                        "otkl_days": r["otkl_days"],
                        "status": r["status"],
                    }
                    for r in project_rows
                },
            }
        )

    completed = sum(r["status"] == "done" for r in filtered)
    overdue = sum(r["status"] == "overdue" for r in filtered)
    missing = sum(r["status"] == "missing" for r in filtered)
    total = len(filtered)

    by_project = []
    for project_name in sorted(filtered_projects, key=str.casefold):
        project_rows = [r for r in filtered if r["project"] == project_name]
        done = sum(r["status"] == "done" for r in project_rows)
        by_project.append(
            {
                "project": project_name,
                "completed": done,
                "total": len(project_rows),
                "pct": round(done / len(project_rows) * 100, 1) if project_rows else 0,
            }
        )

    return {
        "meta": {
            "rows": total,
            "source": "msp",
            "data_mode": DATA_MODE,
            "files": len(files),
            "rule": "План = base end (или plan end); Факт = plan end (или actual finish)",
        },
        "filters": {"projects": available, "applied": {"project": applied}},
        "kpis": {
            "projects": len(filtered_projects),
            "milestones_found": total,
            "completed_pct": round(completed / total * 100, 1) if total else 0.0,
            "overdue": overdue,
            "missing_fact": missing,
        },
        "tremor": {
            "completion_by_project": by_project,
            "status_mix": [
                {"name": "Выполнено", "value": completed},
                {"name": "Просрочено", "value": overdue},
                {"name": "Без факта", "value": missing},
                {
                    "name": "В срок",
                    "value": sum(r["status"] == "on_track" for r in filtered),
                },
            ],
        },
        "matrix": {
            "milestones": [
                {"slug": slug, "title": title} for title, slug, _ in CONTROL_POINT_MILESTONES
            ],
            "projects": matrix_projects,
        },
        "rows": sorted(filtered, key=lambda r: (r["project"].casefold(), r["slug"])),
    }
