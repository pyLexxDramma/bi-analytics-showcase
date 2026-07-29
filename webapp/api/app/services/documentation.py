from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Literal

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
from app.services.project_schedule import (
    _as_level,
    _clean_task_label,
    _fmt_dev,
    _is_blank_block,
)

DocKind = Literal["pd", "rd"]

_COLUMN_ALIASES = {
    "task": ["task name", "название", "название задачи"],
    "plan_start": ["plan start", "начало", "план начало"],
    "plan_end": ["plan end", "окончание", "план окончание"],
    "base_start": ["base start", "базовое начало", "базовое_начало"],
    "base_end": ["base end", "базовое окончание", "базовое_окончание"],
    "actual_finish": [
        "actual finish",
        "фактическое окончание",
        "фактическое_окончание",
    ],
    "pct": [
        "pct complete",
        "% complete",
        "процент завершения",
        "процент_завершения",
        "% завершения",
    ],
    "level": ["level", "уровень"],
    "level_structure": [
        "level structure",
        "уровень структуры",
        "уровень_структуры",
        "outline level",
    ],
    "block": ["block", "блок", "функциональный блок"],
    "cipher": [
        "abbreviation",
        "шифр пд и рд",
        "шифр_пд_и_рд",
        "шифр пд",
        "шифр рд",
    ],
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


def _is_pd_stage_name(name: str) -> bool:
    text = (name or "").casefold()
    if "проектная документация" not in text:
        return False
    if "корректиров" in text:
        return False
    if "рабоч" in text and "проектн" not in text:
        return False
    return True


def _is_rd_stage_name(name: str) -> bool:
    text = (name or "").casefold()
    return "рабочая документация" in text or text.strip() in {"рд", "стадия рд"}


def _is_doc_block(block: str | None, doc_kind: DocKind) -> bool:
    text = (block or "").casefold().strip()
    if doc_kind == "pd":
        return text in {"пд", "пд и рд"}
    return text in {"рд", "пд и рд"}


def _cipher_value(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text or text.casefold() in {"nan", "none", "null", "-", "—"}:
        return ""
    return text


def _week_start(value: date) -> date:
    return value - timedelta(days=value.weekday())


def _empty_payload(doc_kind: DocKind) -> dict[str, Any]:
    title = "Проектная документация" if doc_kind == "pd" else "Рабочая документация"
    return {
        "meta": {
            "rows": 0,
            "source": "msp",
            "data_mode": DATA_MODE,
            "files": 0,
            "doc_kind": doc_kind,
            "title": title,
            "rule": "MSP разделы с шифром в ветке документации",
        },
        "filters": {
            "projects": ["Все"],
            "sections": ["Все"],
            "granularities": [
                {"id": "day", "label": "За день"},
                {"id": "week", "label": "За неделю"},
                {"id": "month", "label": "За месяц"},
            ],
            "applied": {
                "project": "Все",
                "section": "Все",
                "granularity": "week",
                "report_date": date.today().isoformat(),
            },
        },
        "kpis": {
            "plan_total": 0,
            "plan_to_date": 0,
            "fact_to_date": 0,
            "deviation_to_date": 0,
            "current_productivity": 0.0,
            "required_productivity": 0.0,
        },
        "tremor": {
            "status_mix": [
                {"name": "Завершено", "value": 0},
                {"name": "В работе", "value": 0},
                {"name": "Не начато", "value": 0},
            ],
            "dynamics": [],
        },
        "rows": [],
    }


def _collect_sections(doc_kind: DocKind) -> list[dict[str, Any]]:
    files = latest_web_files_by_project()
    collected: list[dict[str, Any]] = []

    for path in files:
        frame = _read_msp(path)
        if frame.empty:
            continue
        columns = _column_map(list(frame.columns))
        if "task" not in columns:
            continue
        fallback_project = _project_from_path(path)

        # Outline stack: (level_structure or level, task_name, is_doc_stage)
        stack: list[tuple[float, str, bool]] = []

        for _, record in frame.iterrows():
            task = _clean_task_label(record.get(columns["task"]))
            if not task:
                continue

            lvl = _as_level(record.get(columns["level"])) if "level" in columns else None
            lvl_struct = (
                _as_level(record.get(columns["level_structure"]))
                if "level_structure" in columns
                else None
            )
            outline = float(lvl_struct if lvl_struct is not None else (lvl if lvl is not None else 0))

            raw_block = record.get(columns["block"], "") if "block" in columns else ""
            block_name = "" if _is_blank_block(raw_block) else str(raw_block).strip()
            cipher = _cipher_value(record.get(columns["cipher"])) if "cipher" in columns else ""

            while stack and stack[-1][0] >= outline:
                stack.pop()
            ancestors = [item[1] for item in stack]
            under_named = any(
                (_is_pd_stage_name(a) if doc_kind == "pd" else _is_rd_stage_name(a))
                for a in ancestors
            )
            under_block = _is_doc_block(block_name, doc_kind)
            under_doc = under_named or under_block

            is_stage = (
                _is_pd_stage_name(task) if doc_kind == "pd" else _is_rd_stage_name(task)
            )
            stack.append((outline, task, is_stage or under_doc))

            # metrics mask: structure 4 OR (structure 3 & level 5) + cipher + under_doc
            metrics_ok = False
            if under_doc and cipher:
                if lvl_struct == 4:
                    metrics_ok = True
                elif lvl_struct == 3 and lvl == 5:
                    metrics_ok = True
                elif lvl_struct is None and lvl == 5:
                    metrics_ok = True

            if not metrics_ok:
                continue

            project_name = str(record.get(columns.get("project", ""), "") or "").strip()
            if not project_name or project_name.casefold().startswith("msp_"):
                project_name = fallback_project

            plan_end = (
                _as_date(record.get(columns["plan_end"])) if "plan_end" in columns else None
            )
            base_end = (
                _as_date(record.get(columns["base_end"])) if "base_end" in columns else None
            )
            actual = (
                _as_date(record.get(columns["actual_finish"]))
                if "actual_finish" in columns
                else None
            )
            pct = _as_pct(record.get(columns["pct"])) if "pct" in columns else None
            completed = bool(
                (pct is not None and pct >= 99.99)
                or (actual is not None)
            )
            in_progress = bool(not completed and pct is not None and pct > 0)
            if base_end and plan_end:
                end_diff = (base_end - plan_end).days
            else:
                end_diff = None

            collected.append(
                {
                    "project": project_name,
                    "section": cipher,
                    "task": task,
                    "block": block_name or None,
                    "pct_complete": round(pct, 1)
                    if pct is not None and math.isfinite(pct)
                    else None,
                    "completed": completed,
                    "in_progress": in_progress,
                    "base_end": _format_date(base_end),
                    "plan_end": _format_date(plan_end),
                    "base_end_iso": base_end.isoformat() if base_end else None,
                    "plan_end_iso": plan_end.isoformat() if plan_end else None,
                    "actual_finish_iso": actual.isoformat() if actual else None,
                    "dev_end_days": end_diff,
                    "dev_end": _fmt_dev(end_diff),
                }
            )

    # Deduplicate by project+section keeping latest base/plan presence
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for row in collected:
        key = (row["project"], row["section"])
        existing = best.get(key)
        if existing is None:
            best[key] = row
            continue
        # Prefer completed / higher pct / later plan end
        score_new = (
            1 if row["completed"] else 0,
            row["pct_complete"] or -1,
            row["plan_end_iso"] or "",
        )
        score_old = (
            1 if existing["completed"] else 0,
            existing["pct_complete"] or -1,
            existing["plan_end_iso"] or "",
        )
        if score_new >= score_old:
            best[key] = row
    return list(best.values())


def build_documentation_payload(
    *,
    doc_kind: DocKind = "pd",
    project: str | None = None,
    section: str | None = None,
    granularity: str | None = "week",
    report_date: str | None = None,
) -> dict[str, Any]:
    files = latest_web_files_by_project()
    if not files:
        return _empty_payload(doc_kind)

    sections = _collect_sections(doc_kind)
    if not sections:
        empty = _empty_payload(doc_kind)
        empty["meta"]["files"] = len(files)
        return empty

    projects = sorted({row["project"] for row in sections}, key=str.casefold)
    available_projects = ["Все"] + projects
    applied_project = project if project in available_projects else "Все"

    scoped = [
        row
        for row in sections
        if applied_project == "Все" or row["project"] == applied_project
    ]
    section_opts = sorted({row["section"] for row in scoped}, key=str.casefold)
    available_sections = ["Все"] + section_opts
    applied_section = section if section in available_sections else "Все"
    filtered = [
        row
        for row in scoped
        if applied_section == "Все" or row["section"] == applied_section
    ]

    today = date.today()
    try:
        report = date.fromisoformat((report_date or "")[:10]) if report_date else today
    except ValueError:
        report = today
    if report > today:
        report = today

    gran = granularity if granularity in {"day", "week", "month"} else "week"

    plan_total = len(filtered)
    plan_to_date = sum(
        1
        for row in filtered
        if row["base_end_iso"] and date.fromisoformat(row["base_end_iso"]) <= report
    )
    fact_to_date = sum(1 for row in filtered if row["completed"])
    # Prefer fact by actual/complete; if no actual dates, completed count is fine
    deviation = fact_to_date - plan_to_date

    # Productivity windows
    if gran == "day":
        window_days = 1
    elif gran == "month":
        window_days = 30
    else:
        window_days = 7
    window_start = report - timedelta(days=window_days - 1)
    current_prod = sum(
        1
        for row in filtered
        if row["completed"]
        and row["plan_end_iso"]
        and window_start <= date.fromisoformat(row["plan_end_iso"]) <= report
    )
    # Required: remaining baseline after report / days to last baseline
    remaining = sum(
        1
        for row in filtered
        if (not row["completed"])
        and row["base_end_iso"]
        and date.fromisoformat(row["base_end_iso"]) > report
    )
    future_bases = [
        date.fromisoformat(row["base_end_iso"])
        for row in filtered
        if row["base_end_iso"] and date.fromisoformat(row["base_end_iso"]) > report
    ]
    if future_bases and remaining > 0:
        days_left = max((max(future_bases) - report).days, 1)
        required = round(remaining / days_left * window_days, 1)
    else:
        required = 0.0

    completed = sum(1 for row in filtered if row["completed"])
    in_progress = sum(1 for row in filtered if row["in_progress"])
    not_started = plan_total - completed - in_progress

    # Dynamics cumulative
    bucket_fn = {
        "day": lambda d: d,
        "week": _week_start,
        "month": lambda d: d.replace(day=1),
    }[gran]

    base_buckets: dict[date, int] = defaultdict(int)
    plan_buckets: dict[date, int] = defaultdict(int)
    for row in filtered:
        if row["base_end_iso"]:
            base_buckets[bucket_fn(date.fromisoformat(row["base_end_iso"]))] += 1
        if row["plan_end_iso"]:
            plan_buckets[bucket_fn(date.fromisoformat(row["plan_end_iso"]))] += 1

    all_keys = sorted(set(base_buckets) | set(plan_buckets))
    dynamics = []
    cum_base = 0
    cum_plan = 0
    for key in all_keys:
        cum_base += base_buckets.get(key, 0)
        cum_plan += plan_buckets.get(key, 0)
        dynamics.append(
            {
                "period": key.isoformat(),
                "period_label": key.strftime("%d.%m.%Y"),
                "plan_bp": cum_base,
                "forecast": cum_plan,
            }
        )

    table_rows = sorted(
        filtered,
        key=lambda row: (
            row["project"].casefold(),
            row["dev_end_days"] if row["dev_end_days"] is not None else 0,
            row["section"].casefold(),
        ),
    )

    title = "Проектная документация" if doc_kind == "pd" else "Рабочая документация"
    rule = (
        "Разделы с шифром в ветке ПД (ур.структуры 4 или 3+ур.5)"
        if doc_kind == "pd"
        else "Разделы с шифром в ветке РД (ур.структуры 4 или 3+ур.5)"
    )
    return {
        "meta": {
            "rows": len(table_rows),
            "source": "msp",
            "data_mode": DATA_MODE,
            "files": len(files),
            "doc_kind": doc_kind,
            "title": title,
            "rule": rule,
        },
        "filters": {
            "projects": available_projects,
            "sections": available_sections,
            "granularities": [
                {"id": "day", "label": "За день"},
                {"id": "week", "label": "За неделю"},
                {"id": "month", "label": "За месяц"},
            ],
            "applied": {
                "project": applied_project,
                "section": applied_section,
                "granularity": gran,
                "report_date": report.isoformat(),
            },
        },
        "kpis": {
            "plan_total": plan_total,
            "plan_to_date": plan_to_date,
            "fact_to_date": fact_to_date,
            "deviation_to_date": deviation,
            "current_productivity": float(current_prod),
            "required_productivity": float(required),
        },
        "tremor": {
            "status_mix": [
                {"name": "Завершено", "value": completed},
                {"name": "В работе", "value": max(in_progress, 0)},
                {"name": "Не начато", "value": max(not_started, 0)},
            ],
            "dynamics": dynamics,
        },
        "rows": [
            {
                "project": row["project"],
                "section": row["section"],
                "task": row["task"],
                "base_end": row["base_end"],
                "plan_end": row["plan_end"],
                "dev_end": row["dev_end"],
                "dev_end_days": row["dev_end_days"],
                "pct_complete": row["pct_complete"],
                "status": (
                    "Завершено"
                    if row["completed"]
                    else ("В работе" if row["in_progress"] else "Не начато")
                ),
            }
            for row in table_rows
        ],
    }


def build_project_documentation_payload(**kwargs: Any) -> dict[str, Any]:
    return build_documentation_payload(doc_kind="pd", **kwargs)


def build_working_documentation_payload(**kwargs: Any) -> dict[str, Any]:
    return build_documentation_payload(doc_kind="rd", **kwargs)
