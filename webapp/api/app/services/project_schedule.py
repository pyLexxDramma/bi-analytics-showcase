from __future__ import annotations

import math
import re
from datetime import date
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
)

GANTT_CAP = 600

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
    "pct": [
        "pct complete",
        "% complete",
        "percent complete",
        "процент завершения",
        "процент_завершения",
        "% завершения",
        "процент выполнения",
    ],
    "level": ["level", "уровень", "outline level"],
    "block": ["block", "блок", "функциональный блок", "section", "раздел"],
    "task_id": ["task id", "ид", "id", "уникальный идентификатор", "task id seq"],
    "lot": ["lot", "лот"],
    "reason": [
        "reason of deviation",
        "причины отклонений",
        "причины_отклонений",
        "причина отклонения",
    ],
    "notes": ["notes", "заметки"],
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


def _clean_task_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.casefold() in {"nan", "none"}:
        return ""
    text = re.sub(r"(?i)^\s*задача\s+\d+\s+", "", text)
    text = re.sub(r"(?i)^\s*задача\s+", "", text)
    return text.strip()


def _as_level(value: Any) -> int | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        return int(float(str(value).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return None


def _fmt_dev(days: int | None) -> str:
    if days is None:
        return "Н/Д"
    if days == 0:
        return "0 дн."
    return f"{days:+d} дн."


def _is_blank_block(value: Any) -> bool:
    text = str(value or "").strip()
    return not text or text.casefold() in {"nan", "none", "null", "-"}


def _is_covenant_block(value: str | None) -> bool:
    text = (value or "").casefold()
    return "овенант" in text or "covenant" in text


def _empty_payload() -> dict[str, Any]:
    return {
        "meta": {
            "rows": 0,
            "gantt_rows": 0,
            "source": "msp",
            "data_mode": DATA_MODE,
            "files": 0,
            "rule": "План = базовые даты; Факт = текущий план (Начало/Окончание)",
        },
        "filters": {
            "projects": ["Все"],
            "levels": [
                {"id": "4", "label": "Верхний уровень (4)"},
                {"id": "5", "label": "Детальный уровень (5)"},
            ],
            "blocks": ["Все"],
            "applied": {
                "project": "Все",
                "level": "4",
                "block": "Все",
                "hide_completed": False,
                "only_delay": False,
                "level_skipped": False,
            },
        },
        "kpis": {
            "tasks": 0,
            "avg_pct": 0.0,
            "delayed": 0,
            "completed": 0,
        },
        "gantt": {
            "range_start": None,
            "range_end": None,
            "rows": [],
            "capped": False,
        },
        "rows": [],
    }


def build_project_schedule_payload(
    *,
    project: str | None = None,
    level: str | None = "4",
    block: str | None = None,
    hide_completed: bool = False,
    only_delay: bool = False,
) -> dict[str, Any]:
    files = latest_web_files_by_project()
    if not files:
        return _empty_payload()

    collected: list[dict[str, Any]] = []
    projects: set[str] = set()
    blocks: set[str] = set()

    for path in files:
        frame = _read_msp(path)
        if frame.empty:
            continue
        columns = _column_map(list(frame.columns))
        if "task" not in columns or "plan_start" not in columns or "plan_end" not in columns:
            continue
        fallback_project = _project_from_path(path)

        for _, record in frame.iterrows():
            plan_start = _as_date(record.get(columns["plan_start"]))
            plan_end = _as_date(record.get(columns["plan_end"]))
            if not plan_start or not plan_end:
                continue
            task = _clean_task_label(record.get(columns["task"]))
            if not task:
                continue

            project_name = str(record.get(columns.get("project", ""), "") or "").strip()
            if not project_name or project_name.casefold().startswith("msp_"):
                project_name = fallback_project
            projects.add(project_name)

            base_start = (
                _as_date(record.get(columns["base_start"]))
                if "base_start" in columns
                else None
            )
            base_end = (
                _as_date(record.get(columns["base_end"])) if "base_end" in columns else None
            )
            pct = _as_pct(record.get(columns["pct"])) if "pct" in columns else None
            lvl = _as_level(record.get(columns["level"])) if "level" in columns else None
            raw_block = record.get(columns["block"], "") if "block" in columns else ""
            block_name = "" if _is_blank_block(raw_block) else str(raw_block).strip()
            if block_name:
                blocks.add(block_name)

            task_id = (
                str(record.get(columns["task_id"], "") or "").strip()
                if "task_id" in columns
                else ""
            )
            if task_id.casefold() in {"nan", "none"}:
                task_id = ""

            start_dev = (
                (plan_start - base_start).days if plan_start and base_start else None
            )
            end_dev = (plan_end - base_end).days if plan_end and base_end else None

            collected.append(
                {
                    "project": project_name,
                    "task_id": task_id or None,
                    "level": lvl,
                    "block": block_name or None,
                    "task": task,
                    "pct_complete": round(pct, 1)
                    if pct is not None and math.isfinite(pct)
                    else None,
                    "plan_start": _format_date(plan_start),
                    "plan_end": _format_date(plan_end),
                    "base_start": _format_date(base_start),
                    "base_end": _format_date(base_end),
                    "plan_start_iso": plan_start.isoformat(),
                    "plan_end_iso": plan_end.isoformat(),
                    "base_start_iso": base_start.isoformat() if base_start else None,
                    "base_end_iso": base_end.isoformat() if base_end else None,
                    "dev_start_days": start_dev,
                    "dev_end_days": end_dev,
                    "dev_start": _fmt_dev(start_dev),
                    "dev_end": _fmt_dev(end_dev),
                    "delayed": bool(end_dev is not None and end_dev > 0),
                    "completed": bool(pct is not None and pct >= 99.999),
                }
            )

    available_projects = ["Все"] + sorted(projects, key=str.casefold)
    available_blocks = ["Все"] + sorted(blocks, key=str.casefold)
    applied_project = project if project in available_projects else "Все"
    applied_block = block if block in available_blocks else "Все"
    applied_level = level if level in {"4", "5"} else "4"
    level_int = int(applied_level)
    skip_level = _is_covenant_block(applied_block)

    filtered = [
        row
        for row in collected
        if (applied_project == "Все" or row["project"] == applied_project)
        and (applied_block == "Все" or row["block"] == applied_block)
        and (skip_level or row["level"] == level_int)
    ]
    if hide_completed:
        filtered = [row for row in filtered if not row["completed"]]
    if only_delay:
        filtered = [row for row in filtered if row["delayed"]]

    filtered.sort(
        key=lambda row: (
            row["project"].casefold(),
            row["level"] if row["level"] is not None else 99,
            (row["block"] or "").casefold(),
            row["plan_start_iso"] or "",
            row["task"].casefold(),
        )
    )

    pct_vals = [row["pct_complete"] for row in filtered if row["pct_complete"] is not None]
    delayed = sum(1 for row in filtered if row["delayed"])
    completed = sum(1 for row in filtered if row["completed"])

    gantt_source = filtered[:GANTT_CAP]
    range_dates: list[date] = []
    for row in gantt_source:
        for key in ("base_start_iso", "base_end_iso", "plan_start_iso", "plan_end_iso"):
            raw = row.get(key)
            if raw:
                range_dates.append(date.fromisoformat(str(raw)))

    range_start = min(range_dates).isoformat() if range_dates else None
    range_end = max(range_dates).isoformat() if range_dates else None

    gantt_rows = []
    for row in gantt_source:
        gantt_rows.append(
            {
                "project": row["project"],
                "task": row["task"],
                "label": (
                    row["task"]
                    if applied_project != "Все"
                    else f"{row['project']}: {row['task']}"
                ),
                "pct_complete": row["pct_complete"],
                "baseline": {
                    "start": row["base_start_iso"] or row["plan_start_iso"],
                    "end": row["base_end_iso"] or row["plan_end_iso"],
                },
                "current": {
                    "start": row["plan_start_iso"],
                    "end": row["plan_end_iso"],
                },
                "dev_end_days": row["dev_end_days"],
            }
        )

    table_rows = [
        {
            "project": row["project"],
            "task_id": row["task_id"],
            "level": row["level"],
            "task": row["task"],
            "pct_complete": row["pct_complete"],
            "plan_start": row["plan_start"],
            "base_start": row["base_start"],
            "dev_start": row["dev_start"],
            "dev_start_days": row["dev_start_days"],
            "plan_end": row["plan_end"],
            "base_end": row["base_end"],
            "dev_end": row["dev_end"],
            "dev_end_days": row["dev_end_days"],
        }
        for row in filtered
    ]

    return {
        "meta": {
            "rows": len(filtered),
            "gantt_rows": len(gantt_rows),
            "source": "msp",
            "data_mode": DATA_MODE,
            "files": len(files),
            "rule": "План = базовые даты; Факт = текущий план (Начало/Окончание)",
        },
        "filters": {
            "projects": available_projects,
            "levels": [
                {"id": "4", "label": "Верхний уровень (4)"},
                {"id": "5", "label": "Детальный уровень (5)"},
            ],
            "blocks": available_blocks,
            "applied": {
                "project": applied_project,
                "level": applied_level,
                "block": applied_block,
                "hide_completed": hide_completed,
                "only_delay": only_delay,
                "level_skipped": skip_level,
            },
        },
        "kpis": {
            "tasks": len(filtered),
            "avg_pct": round(sum(pct_vals) / len(pct_vals), 1) if pct_vals else 0.0,
            "delayed": delayed,
            "completed": completed,
        },
        "gantt": {
            "range_start": range_start,
            "range_end": range_end,
            "rows": gantt_rows,
            "capped": len(filtered) > GANTT_CAP,
        },
        "rows": table_rows,
    }
