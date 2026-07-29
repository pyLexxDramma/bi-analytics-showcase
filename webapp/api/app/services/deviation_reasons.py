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
    _is_blank_block,
)

_COLUMN_ALIASES = {
    "task": ["task name", "название", "название задачи", "наименование задачи"],
    "plan_end": ["plan end", "окончание", "план окончание", "плановое окончание"],
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
    "reason": [
        "reason of deviation",
        "причины отклонений",
        "причины_отклонений",
        "причина отклонения",
        "причина отклонений",
    ],
    "notes": ["notes", "заметки"],
    "project": ["project name", "проект", "название проекта"],
}

REASON_BUCKETS: list[tuple[str, str]] = [
    ("Изменение объемов", "#cddc39"),
    ("Изменение расценки", "#fbc02d"),
    ("Не передан фронт работ", "#26c6da"),
    ("Переделка за предыдущим подрядчиком", "#8bc34a"),
    ("Увеличение сроков по вине подрядчика", "#9e9e9e"),
    ("Прочее", "#e91e63"),
]


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


def _reason_bucket(raw: str) -> tuple[str, str]:
    text = (raw or "").casefold()
    if "измен" in text and "объем" in text:
        return REASON_BUCKETS[0]
    if "измен" in text and any(x in text for x in ("расцен", "стоим", "цен")):
        return REASON_BUCKETS[1]
    if "не передан фронт" in text or ("фронт" in text and "не передан" in text):
        return REASON_BUCKETS[2]
    if "переделк" in text:
        return REASON_BUCKETS[3]
    if "увеличение срок" in text and "подрядчик" in text:
        return REASON_BUCKETS[4]
    return REASON_BUCKETS[5]


def _clean_reason(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.casefold() in {"nan", "none", "null", "-", "—"}:
        return ""
    return re.sub(r"\s+", " ", text)


def _empty_payload() -> dict[str, Any]:
    return {
        "meta": {
            "rows": 0,
            "source": "msp",
            "data_mode": DATA_MODE,
            "files": 0,
            "rule": "Ур.5 · причина · (база−план)<0 · без будущих окончаний",
        },
        "filters": {
            "projects": ["Все"],
            "blocks": ["Все"],
            "reasons": ["Все"],
            "period": {"min": None, "max": None},
            "applied": {
                "project": "Все",
                "block": "Все",
                "reason": "Все",
                "date_from": None,
                "date_to": None,
            },
        },
        "kpis": {
            "main_reason": "—",
            "main_reason_share_pct": 0.0,
            "main_reason_count": 0,
            "tasks": 0,
        },
        "tremor": {
            "by_reason": [],
            "reason_mix": [],
        },
        "rows": [],
    }


def build_deviation_reasons_payload(
    *,
    project: str | None = None,
    block: str | None = None,
    reason: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    files = latest_web_files_by_project()
    if not files:
        return _empty_payload()

    today = date.today()
    collected: list[dict[str, Any]] = []
    projects: set[str] = set()
    blocks: set[str] = set()

    for path in files:
        frame = _read_msp(path)
        if frame.empty:
            continue
        columns = _column_map(list(frame.columns))
        if "task" not in columns or "plan_end" not in columns or "reason" not in columns:
            continue
        fallback_project = _project_from_path(path)

        for _, record in frame.iterrows():
            lvl = _as_level(record.get(columns["level"])) if "level" in columns else None
            if lvl != 5:
                continue
            plan_end = _as_date(record.get(columns["plan_end"]))
            base_end = (
                _as_date(record.get(columns["base_end"])) if "base_end" in columns else None
            )
            if not plan_end or not base_end:
                continue
            # Streamlit maket: base − plan; keep only delays (negative)
            end_diff = (base_end - plan_end).days
            if end_diff >= 0:
                continue
            # Exclude future plan ends
            if plan_end > today:
                continue

            reason_text = _clean_reason(record.get(columns["reason"]))
            if not reason_text:
                continue

            task = _clean_task_label(record.get(columns["task"]))
            if not task:
                continue

            project_name = str(record.get(columns.get("project", ""), "") or "").strip()
            if not project_name or project_name.casefold().startswith("msp_"):
                project_name = fallback_project
            projects.add(project_name)

            raw_block = record.get(columns["block"], "") if "block" in columns else ""
            block_name = "" if _is_blank_block(raw_block) else str(raw_block).strip()
            if block_name:
                blocks.add(block_name)

            building = ""
            if "building" in columns and not _is_blank_block(record.get(columns["building"])):
                building = str(record.get(columns["building"])).strip()

            task_id = (
                str(record.get(columns["task_id"], "") or "").strip()
                if "task_id" in columns
                else ""
            )
            if task_id.casefold() in {"nan", "none"}:
                task_id = ""

            notes = ""
            if "notes" in columns:
                notes = _clean_reason(record.get(columns["notes"]))

            bucket, bucket_color = _reason_bucket(reason_text)
            collected.append(
                {
                    "project": project_name,
                    "task_id": task_id or None,
                    "block": block_name or None,
                    "building": building or None,
                    "task": task,
                    "base_end": _format_date(base_end),
                    "plan_end": _format_date(plan_end),
                    "plan_end_iso": plan_end.isoformat(),
                    "end_diff_days": end_diff,
                    "reason": reason_text,
                    "bucket": bucket,
                    "bucket_color": bucket_color,
                    "notes": notes or None,
                }
            )

    if not collected:
        empty = _empty_payload()
        empty["meta"]["files"] = len(files)
        return empty

    available_projects = ["Все"] + sorted(projects, key=str.casefold)
    available_blocks = ["Все"] + sorted(blocks, key=str.casefold)
    applied_project = project if project in available_projects else "Все"
    applied_block = block if block in available_blocks else "Все"

    period_dates = [date.fromisoformat(r["plan_end_iso"]) for r in collected]
    period_min = min(period_dates)
    period_max = min(max(period_dates), today)

    def _parse_bound(raw: str | None, fallback: date) -> date:
        if not raw:
            return fallback
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return fallback

    applied_from = _parse_bound(date_from, period_min)
    applied_to = _parse_bound(date_to, period_max)
    if applied_from > applied_to:
        applied_from, applied_to = applied_to, applied_from

    scoped = [
        row
        for row in collected
        if (applied_project == "Все" or row["project"] == applied_project)
        and (applied_block == "Все" or row["block"] == applied_block)
        and applied_from <= date.fromisoformat(row["plan_end_iso"]) <= applied_to
    ]

    available_reasons = ["Все"] + sorted(
        {row["reason"] for row in scoped}, key=str.casefold
    )
    applied_reason = reason if reason in available_reasons else "Все"
    filtered = [
        row
        for row in scoped
        if applied_reason == "Все" or row["reason"] == applied_reason
    ]
    filtered.sort(
        key=lambda row: (
            row["end_diff_days"],
            row["project"].casefold(),
            row["reason"].casefold(),
        )
    )

    counts: dict[str, int] = {}
    for row in filtered:
        counts[row["reason"]] = counts.get(row["reason"], 0) + 1
    total = len(filtered)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))
    main_reason, main_count = ranked[0] if ranked else ("—", 0)
    main_pct = round(main_count / total * 100, 1) if total else 0.0

    by_reason = []
    reason_mix = []
    for name, count in ranked:
        pct = round(count / total * 100, 1) if total else 0.0
        by_reason.append(
            {
                "reason": name if len(name) <= 48 else f"{name[:45]}…",
                "reason_full": name,
                "count": count,
                "pct": pct,
            }
        )
        reason_mix.append({"name": name if len(name) <= 40 else f"{name[:37]}…", "value": count})

    return {
        "meta": {
            "rows": total,
            "source": "msp",
            "data_mode": DATA_MODE,
            "files": len(files),
            "rule": "Ур.5 · причина · (база−план)<0 · без будущих окончаний",
        },
        "filters": {
            "projects": available_projects,
            "blocks": available_blocks,
            "reasons": available_reasons,
            "period": {
                "min": period_min.isoformat(),
                "max": period_max.isoformat(),
            },
            "applied": {
                "project": applied_project,
                "block": applied_block,
                "reason": applied_reason,
                "date_from": applied_from.isoformat(),
                "date_to": applied_to.isoformat(),
            },
        },
        "kpis": {
            "main_reason": main_reason[:50] + ("…" if len(main_reason) > 50 else ""),
            "main_reason_share_pct": main_pct,
            "main_reason_count": main_count,
            "tasks": total,
        },
        "tremor": {
            "by_reason": by_reason,
            "reason_mix": reason_mix,
        },
        "rows": [
            {
                "task_id": row["task_id"],
                "project": row["project"],
                "block": row["block"],
                "building": row["building"],
                "base_end": row["base_end"],
                "plan_end": row["plan_end"],
                "end_diff_days": row["end_diff_days"],
                "reason": row["reason"],
                "bucket": row["bucket"],
                "bucket_color": row["bucket_color"],
                "notes": row["notes"],
            }
            for row in filtered
        ],
    }
