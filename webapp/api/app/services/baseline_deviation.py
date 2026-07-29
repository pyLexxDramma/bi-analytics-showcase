from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.config import DATA_MODE
from app.services.data_paths import latest_web_files_by_project
from app.services.developer_projects import (
    _as_date,
    _format_date,
    _normalize,
    _project_from_path,
    _read_msp,
)
from app.services.project_schedule import (
    _as_level,
    _clean_task_label,
    _fmt_dev,
    _is_blank_block,
    _is_covenant_block,
)

CHART_CAP = 400
_ZOS_WORD_RE = re.compile(
    r"(?<![а-яёa-z0-9])зос(?![а-яёa-z0-9])",
    flags=re.IGNORECASE,
)

_COLUMN_ALIASES = {
    "task": ["task name", "название", "название задачи", "наименование задачи"],
    "plan_start": ["plan start", "начало", "план начало", "плановое начало"],
    "plan_end": ["plan end", "окончание", "план окончание", "плановое окончание"],
    "base_start": [
        "base start",
        "базовое начало",
        "базовое_начало",
        "baseline start",
    ],
    "base_end": [
        "base end",
        "базовое окончание",
        "базовое_окончание",
        "baseline finish",
        "baseline end",
    ],
    "level": ["level", "уровень"],
    "block": ["block", "блок", "функциональный блок", "section", "раздел"],
    "building": ["строение", "корпус", "здание", "building", "лот", "lot"],
    "task_id": ["task id", "ид", "id", "уникальный идентификатор", "task id seq"],
    "project": ["project name", "проект", "название проекта"],
}


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


def _is_zos_task(name: str) -> bool:
    text = (name or "").strip()
    if not text:
        return False
    lower = text.casefold()
    if "заключение о соответствии" in lower:
        return True
    return bool(_ZOS_WORD_RE.search(text))


def _zos_rank(name: str) -> int:
    if not _is_zos_task(name):
        return 99
    lower = name.casefold().strip()
    if lower == "зос" or lower.startswith("зос"):
        return 0
    if "заключение о соответствии" in lower:
        return 1
    if "до зос" in lower:
        return 8
    return 2


def _empty_payload() -> dict[str, Any]:
    return {
        "meta": {
            "rows": 0,
            "chart_rows": 0,
            "source": "msp",
            "data_mode": DATA_MODE,
            "files": 0,
            "rule": "Откл. = база − текущий план; таблица: откл. окончания < 0",
        },
        "filters": {
            "projects": ["Все"],
            "blocks": ["Все"],
            "buildings": ["Все"],
            "levels": [
                {"id": "4", "label": "Уровень 4 (укрупнённо)"},
                {"id": "5", "label": "Уровень 5 (детально)"},
            ],
            "applied": {
                "project": "Все",
                "block": "Все",
                "building": "Все",
                "level": "4",
                "level_skipped": False,
            },
        },
        "kpis": {
            "max_abs_dev_days": 0,
            "zos_rows": [],
        },
        "chart": {
            "range_start": None,
            "range_end": None,
            "rows": [],
            "capped": False,
        },
        "rows": [],
    }


def build_baseline_deviation_payload(
    *,
    project: str | None = None,
    block: str | None = None,
    building: str | None = None,
    level: str | None = "4",
) -> dict[str, Any]:
    files = latest_web_files_by_project()
    if not files:
        return _empty_payload()

    collected: list[dict[str, Any]] = []
    projects: set[str] = set()
    blocks: set[str] = set()
    buildings: set[str] = set()

    for path in files:
        frame = _read_msp(path)
        if frame.empty:
            continue
        columns = _column_map(list(frame.columns))
        if "task" not in columns:
            continue
        if "plan_end" not in columns and "base_end" not in columns:
            continue
        fallback_project = _project_from_path(path)

        for _, record in frame.iterrows():
            task = _clean_task_label(record.get(columns["task"]))
            if not task:
                continue

            plan_start = (
                _as_date(record.get(columns["plan_start"]))
                if "plan_start" in columns
                else None
            )
            plan_end = (
                _as_date(record.get(columns["plan_end"])) if "plan_end" in columns else None
            )
            base_start = (
                _as_date(record.get(columns["base_start"]))
                if "base_start" in columns
                else None
            )
            base_end = (
                _as_date(record.get(columns["base_end"])) if "base_end" in columns else None
            )
            if not ((plan_start and plan_end) or (base_start and base_end)):
                if not (plan_end or base_end):
                    continue

            project_name = str(record.get(columns.get("project", ""), "") or "").strip()
            if not project_name or project_name.casefold().startswith("msp_"):
                project_name = fallback_project
            projects.add(project_name)

            lvl = _as_level(record.get(columns["level"])) if "level" in columns else None
            raw_block = record.get(columns["block"], "") if "block" in columns else ""
            block_name = "" if _is_blank_block(raw_block) else str(raw_block).strip()
            if block_name:
                blocks.add(block_name)

            building_name = ""
            if "building" in columns and not _is_blank_block(record.get(columns["building"])):
                building_name = str(record.get(columns["building"])).strip()
                buildings.add(building_name)

            task_id = (
                str(record.get(columns["task_id"], "") or "").strip()
                if "task_id" in columns
                else ""
            )
            if task_id.casefold() in {"nan", "none"}:
                task_id = ""

            # Streamlit: base − plan
            dev_start = (
                (base_start - plan_start).days if base_start and plan_start else None
            )
            dev_end = (base_end - plan_end).days if base_end and plan_end else None
            base_dur = (base_end - base_start).days if base_end and base_start else None
            plan_dur = (plan_end - plan_start).days if plan_end and plan_start else None
            dev_dur = (
                (base_dur - plan_dur)
                if base_dur is not None and plan_dur is not None
                else None
            )

            collected.append(
                {
                    "project": project_name,
                    "task_id": task_id or None,
                    "level": lvl,
                    "block": block_name or None,
                    "building": building_name or None,
                    "task": task,
                    "is_zos": _is_zos_task(task),
                    "plan_start": _format_date(plan_start),
                    "plan_end": _format_date(plan_end),
                    "base_start": _format_date(base_start),
                    "base_end": _format_date(base_end),
                    "plan_start_iso": plan_start.isoformat() if plan_start else None,
                    "plan_end_iso": plan_end.isoformat() if plan_end else None,
                    "base_start_iso": base_start.isoformat() if base_start else None,
                    "base_end_iso": base_end.isoformat() if base_end else None,
                    "dev_start_days": dev_start,
                    "dev_end_days": dev_end,
                    "dev_start": _fmt_dev(dev_start),
                    "dev_end": _fmt_dev(dev_end),
                    "base_dur_days": base_dur,
                    "plan_dur_days": plan_dur,
                    "dev_dur_days": dev_dur,
                    "dev_dur": _fmt_dev(dev_dur),
                }
            )

    available_projects = ["Все"] + sorted(projects, key=str.casefold)
    available_blocks = ["Все"] + sorted(blocks, key=str.casefold)
    available_buildings = ["Все"] + sorted(buildings, key=str.casefold)
    applied_project = project if project in available_projects else "Все"
    applied_block = block if block in available_blocks else "Все"
    applied_building = building if building in available_buildings else "Все"
    applied_level = level if level in {"4", "5"} else "4"
    level_int = int(applied_level)
    skip_level = _is_covenant_block(applied_block)

    scoped = [
        row
        for row in collected
        if (applied_project == "Все" or row["project"] == applied_project)
        and (applied_block == "Все" or row["block"] == applied_block)
        and (applied_building == "Все" or row["building"] == applied_building)
        and (skip_level or row["level"] == level_int)
    ]

    # KPI / ZOS from project+block scoped but without level (Streamlit: plates before detail level)
    zos_scope = [
        row
        for row in collected
        if (applied_project == "Все" or row["project"] == applied_project)
        and (applied_block == "Все" or row["block"] == applied_block)
        and row["is_zos"]
        and row["dev_end_days"] is not None
    ]
    # Prefer one ZOS per project (best ZOS rank, then worst abs deviation)
    zos_by_project: dict[str, dict[str, Any]] = {}
    for row in zos_scope:
        current = zos_by_project.get(row["project"])
        candidate_key = (_zos_rank(row["task"]), -abs(row["dev_end_days"]))
        if current is None:
            zos_by_project[row["project"]] = row
            continue
        current_key = (_zos_rank(current["task"]), -abs(current["dev_end_days"]))
        if candidate_key < current_key:
            zos_by_project[row["project"]] = row
    zos_rows = [
        {
            "project": row["project"],
            "task": row["task"],
            "base_end": row["base_end"],
            "plan_end": row["plan_end"],
            "dev_end_days": row["dev_end_days"],
            "dev_end": row["dev_end"],
        }
        for row in sorted(zos_by_project.values(), key=lambda r: r["project"].casefold())
    ]
    abs_devs = [
        abs(row["dev_end_days"])
        for row in scoped
        if row["dev_end_days"] is not None
    ]
    max_abs = max(abs_devs) if abs_devs else 0

    # Chart: all scoped with end dates
    chart_source = [
        row
        for row in scoped
        if row["base_end_iso"] or row["plan_end_iso"]
    ]
    chart_source.sort(
        key=lambda row: (
            row["dev_end_days"] if row["dev_end_days"] is not None else 0,
            row["project"].casefold(),
            row["task"].casefold(),
        )
    )
    chart_capped = len(chart_source) > CHART_CAP
    chart_source = chart_source[:CHART_CAP]

    range_dates: list[date] = []
    for row in chart_source:
        for key in ("base_end_iso", "plan_end_iso", "base_start_iso", "plan_start_iso"):
            raw = row.get(key)
            if raw:
                range_dates.append(date.fromisoformat(str(raw)))
    range_start = min(range_dates).isoformat() if range_dates else None
    range_end = max(range_dates).isoformat() if range_dates else None

    chart_rows = [
        {
            "project": row["project"],
            "task": row["task"],
            "label": (
                row["task"]
                if applied_project != "Все"
                else f"{row['project']}: {row['task']}"
            ),
            "base_end": row["base_end_iso"],
            "plan_end": row["plan_end_iso"],
            "dev_end_days": row["dev_end_days"],
        }
        for row in chart_source
    ]

    # Table: only finish delays (base − plan < 0)
    table_rows = [
        {
            "project": row["project"],
            "task_id": row["task_id"],
            "task": row["task"],
            "block": row["block"],
            "building": row["building"],
            "base_start": row["base_start"],
            "plan_start": row["plan_start"],
            "dev_start": row["dev_start"],
            "dev_start_days": row["dev_start_days"],
            "base_end": row["base_end"],
            "plan_end": row["plan_end"],
            "dev_end": row["dev_end"],
            "dev_end_days": row["dev_end_days"],
            "base_dur_days": row["base_dur_days"],
            "plan_dur_days": row["plan_dur_days"],
            "dev_dur": row["dev_dur"],
            "dev_dur_days": row["dev_dur_days"],
        }
        for row in scoped
        if row["dev_end_days"] is not None and row["dev_end_days"] < 0
    ]
    table_rows.sort(
        key=lambda row: (
            row["dev_end_days"],
            row["project"].casefold(),
            row["task"].casefold(),
        )
    )

    return {
        "meta": {
            "rows": len(table_rows),
            "chart_rows": len(chart_rows),
            "source": "msp",
            "data_mode": DATA_MODE,
            "files": len(files),
            "rule": "Откл. = база − текущий план; таблица: откл. окончания < 0",
        },
        "filters": {
            "projects": available_projects,
            "blocks": available_blocks,
            "buildings": available_buildings,
            "levels": [
                {"id": "4", "label": "Уровень 4 (укрупнённо)"},
                {"id": "5", "label": "Уровень 5 (детально)"},
            ],
            "applied": {
                "project": applied_project,
                "block": applied_block,
                "building": applied_building,
                "level": applied_level,
                "level_skipped": skip_level,
            },
        },
        "kpis": {
            "max_abs_dev_days": max_abs,
            "zos_rows": zos_rows,
        },
        "chart": {
            "range_start": range_start,
            "range_end": range_end,
            "rows": chart_rows,
            "capped": chart_capped,
        },
        "rows": table_rows,
    }
