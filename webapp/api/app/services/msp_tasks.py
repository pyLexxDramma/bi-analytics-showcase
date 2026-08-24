"""Список задач MSP для админского селектора «задача для KPI».

Паритет с [main] ``admin_panel_content._msp_metric_task_options``: уровень берём
не фиксированным, а тем, на котором лежит текущая задача (или ЗОС) — это и есть
«функциональный блок» нужной глубины в конкретной выгрузке.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

from app.services.core_bridge import load_msp_frame, prepare_web_db

_ZOS_WORD_RE = re.compile(r"(?<![а-яёa-z0-9])зос(?![а-яёa-z0-9])", flags=re.IGNORECASE)
_DEFAULT_TASK = "ЗОС"
_FALLBACK_LEVEL = 5


def _col(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    lowered = {str(c).strip().lower(): c for c in frame.columns}
    for cand in candidates:
        hit = lowered.get(cand.strip().lower())
        if hit is not None:
            return hit
    for cand in candidates:
        needle = cand.strip().lower()
        for low, original in lowered.items():
            if needle in low:
                return original
    return None


def _numeric_levels(series: pd.Series) -> pd.Series:
    num = pd.to_numeric(series, errors="coerce")
    mask_na = num.isna()
    if bool(mask_na.any()):
        extracted = (
            series[mask_na].astype(str).str.strip().str.extract(r"(-?\d+)", expand=False)
        )
        num.loc[mask_na] = pd.to_numeric(extracted, errors="coerce").values
    return num.round()


def _only_msp_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if "__source_file" not in frame.columns:
        return frame
    src = frame["__source_file"].astype(str).str.lower()
    is_msp = (
        src.str.startswith("msp_")
        | src.str.contains("/msp_", na=False)
        | src.str.contains(r"\\msp_", na=False, regex=True)
    )
    return frame.loc[is_msp].copy() if bool(is_msp.any()) else frame


def _mode_level(levels: pd.Series, mask: pd.Series) -> int | None:
    picked = levels.loc[mask].dropna()
    if picked.empty:
        return None
    return int(picked.mode().iloc[0])


def list_metric_task_options(current_task: str | None = None) -> dict[str, Any]:
    """Задачи MSP того же уровня, что и текущая задача KPI.

    Возвращает ``{options: [{level, name}], level, task_column, current, hint}``.
    ``hint`` заполнен, когда список пуст — UI показывает его и оставляет ручной ввод.
    """
    current = (current_task or "").strip()
    empty: dict[str, Any] = {
        "options": [],
        "level": None,
        "task_column": None,
        "current": current,
        "hint": None,
    }

    try:
        prepare_web_db()
        import web_schema  # type: ignore

        version_id = web_schema.get_active_version_id()
    except Exception as exc:  # noqa: BLE001
        empty["hint"] = f"Не удалось открыть web_data.db: {exc}"
        return empty

    if not version_id:
        empty["hint"] = "Нет активной версии данных — запустите загрузку web/ → БД."
        return empty

    frame = load_msp_frame(int(version_id))
    if frame is None or getattr(frame, "empty", True):
        empty["hint"] = "В активной версии нет выгрузки MSP (file_type=project)."
        return empty

    frame = _only_msp_rows(frame.copy())
    task_col = _col(frame, ["task name", "Task Name", "Название", "Задача"])
    level_col = _col(
        frame,
        ["level", "outline level", "Уровень", "уровень структуры", "Исходный уровень"],
    )
    if not task_col or not level_col:
        empty["hint"] = "В выгрузке MSP не найдены колонки с названием задачи и уровнем."
        return empty
    empty["task_column"] = str(task_col)

    levels = _numeric_levels(frame[level_col])
    names = frame[task_col].astype(str).str.strip()

    target_level: int | None = None
    if current:
        target_level = _mode_level(levels, names.str.casefold() == current.casefold())
    if target_level is None:
        zos_mask = names.str.contains(_ZOS_WORD_RE, na=False) | names.str.contains(
            "заключение о соответствии", case=False, na=False
        )
        target_level = _mode_level(levels, zos_mask)
    if target_level is None:
        target_level = _FALLBACK_LEVEL

    at_level = names.loc[levels == target_level]
    at_level = at_level[at_level.ne("") & at_level.str.casefold().ne("nan")]
    options = sorted(set(at_level.tolist()), key=lambda s: s.casefold())
    if not options:
        empty["level"] = int(target_level)
        empty["hint"] = f"В текущей выгрузке MSP нет задач уровня {int(target_level)}."
        return empty

    return {
        "options": [{"level": int(target_level), "name": name} for name in options],
        "level": int(target_level),
        "task_column": str(task_col),
        "current": current or _DEFAULT_TASK,
        "hint": None,
    }
