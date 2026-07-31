# -*- coding: utf-8 -*-
"""Предупреждения при проблемах с данными или форматом под графиками и таблицами.

Показываются только если построение опирается на неполные данные, эвристики или ошибочный
формат выгрузки — не «справочные» сообщения при штатной работе.
"""

from __future__ import annotations

from typing import Any, Iterable


def _dedupe_preserve(seq: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in seq:
        s = str(x).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def collect_budget_1c_hints(
    attrs: dict[str, Any] | None,
    *,
    used_fallback_1c: bool = False,
    display_has_plan: bool | None = None,
    display_no_plan_scenario: bool = False,
) -> list[str]:
    """БДДС / план-факт: только если план в данных восстановлен оценкой (неполная выгрузка)."""
    _ = used_fallback_1c  # сохранён в сигнатуре для обратной совместимости вызовов
    a = attrs or {}
    hints: list[str] = []
    imputed = bool(a.get("bddds_plan_imputed_ratio"))
    beyond = str(a.get("bdds_1c_latest_month") or "").strip()
    if beyond:
        hints.append(
            f"Обороты 1С для БДДС доступны по {beyond} включительно; месяцы позже в таблице могут быть пустыми "
            "(календарь MSP) до появления новых выгрузок в web/."
        )
    if display_no_plan_scenario:
        hints.append(
            "Для выбранного проекта в выгрузке 1С нет сценария «План» по БДДС — на графике и в таблицах "
            "план не строится, отображается только факт."
        )
    if imputed and (display_has_plan is None or display_has_plan):
        hints.append(
            "В выгрузке 1С для части периодов не было строк «ПЛАН» при ненулевом «ФАКТ» — значение плана оценено как "
            "«Факт» × (Σплан/Σфакт) по месяцам с полными данными внутри того же проекта. "
            "Для точных планов добавьте строки плана в JSON или проверьте статьи/сценарии по ТЗ."
        )
    return _dedupe_preserve(hints)


def collect_bdr_hints(attrs: dict[str, Any] | None) -> list[str]:
    """Синтетический БДР из 1С: только явные проблемы разметки/формата или эвристики."""
    a = attrs or {}
    hints: list[str] = []
    if not bool(a.get("data_source_1c_synthetic_bdr")):
        return hints
    if bool(a.get("bdr_approx_no_bdr_marker")):
        hints.append(
            "В выгрузке не найдена явная маркировка статей БДР (например «(БДР)» в статье оборотов или типе статьи БДР). "
            "Для достоверного отчёта в 1С нужно явно размечать статьи БДР."
        )
    if bool(a.get("bdr_synthetic_rd_column")):
        hints.append(
            "Колонка «РасходДоход» отсутствует в выгрузке: расход определён по эвристике. Задайте колонку направления движения в 1С."
        )
    if bool(a.get("bdr_scenario_unsplit_all_to_fact")):
        hints.append(
            "Не удалось разделить строки на план и факт по сценарию по правилам ТЗ — суммы отнесены к фактическим расходам."
        )
    return _dedupe_preserve(hints)


def collect_forecast_bddcs_hints(attrs: dict[str, Any] | None) -> list[str]:
    """Прогнозный БДДС: только если распределение по лотам сделано равномерно из‑за нулевого плана в MSP."""
    a = attrs or {}
    hints: list[str] = []
    if bool(a.get("forecast_bddcs_uniform_lot_weights")):
        hints.append(
            "Сумма «budget plan» по строкам MSP для проекта была нулевой — суммы из 1С распределены по лотам поровну; это приближение."
        )
    return _dedupe_preserve(hints)


def collect_project_schedule_hints(
    *,
    only_finish_delay_active: bool,
    is_covenants: bool,
    base_end_column_present: bool,
    base_end_filled_ratio: float | None,
) -> list[str]:
    """Дашборд «График проекта» / MSP: фильтр просрочки по базовому окончанию."""
    hints: list[str] = []
    if is_covenants or not only_finish_delay_active:
        return _dedupe_preserve(hints)
    if not base_end_column_present:
        hints.append(
            "Фильтр «только просрочка по окончанию» по ТЗ опирается на колонку «base end» (базовое окончание). "
            "В текущей MSP-выгрузке её нет — отбор по просрочке не применён; добавьте базовый план в файл или снимите фильтр."
        )
        return _dedupe_preserve(hints)
    if base_end_filled_ratio is not None and base_end_filled_ratio < 0.15:
        pct = int(max(0, min(100, round(base_end_filled_ratio * 100))))
        hints.append(
            f"Базовое окончание заполнено лишь у ~{pct}% строк — при включённом фильтре просрочки график может быть почти пустым."
        )
    return _dedupe_preserve(hints)


def collect_developer_projects_hints(
    ss: Any,
    mdf: Any | None,
) -> list[str]:
    """
    Дашборд «Девелоперские проекты»: только отсутствие источника для оборотов ДС (TESSA опционален для MSP-fallback).
    """
    hints: list[str] = []
    if mdf is None or getattr(mdf, "empty", True):
        return _dedupe_preserve(hints)
    try:
        from dashboards.dev_projects_tz_matrix import (
            _bddds_df_for_dev_matrix,
            developer_projects_msp_snapshot_hints,
        )

        pd_obj = ss.get("project_data") if hasattr(ss, "get") else None
        bd = _bddds_df_for_dev_matrix(mdf, pd_obj, ss)
        if bd is None:
            hints.append(
                "Строка «Выборка ДС, млн руб.»: не найдены обороты 1С для выбранного проекта "
                "(`reference_1c_dannye` или `project_data` со столбцом «Сценарий»). По ТЗ источник — отчёт оборотов по бюджетам; без выгрузки отображается Н/Д."
            )
        hints.extend(developer_projects_msp_snapshot_hints(mdf, ss=ss))
    except Exception:
        pass
    return _dedupe_preserve(hints)


def render_quality_hints(_hints: list[str]) -> None:
    """Показывает предупреждения о проблемах данных/формата прямо под графиком/таблицей.

    Выводятся только реальные проблемы (неполная выгрузка, эвристики, неверный
    формат) — собранные ``collect_*`` функциями. При пустом списке — ничего.
    Управление: ``BI_ANALYTICS_HIDE_QUALITY_HINTS=1`` полностью скрывает блок.
    """
    hints = _dedupe_preserve(_hints or [])
    if not hints:
        return

    import os

    if str(os.environ.get("BI_ANALYTICS_HIDE_QUALITY_HINTS", "")).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return

    try:
        import html as _html

        import streamlit as st
    except Exception:
        return

    items = "".join(
        f'<li style="margin:0.15rem 0;">{_html.escape(h)}</li>' for h in hints
    )
    _light = False
    try:
        from dashboards.light_theme import is_light_preview_active

        _light = is_light_preview_active()
    except Exception:
        pass
    if _light:
        _box = (
            "border:1px solid rgba(180,83,9,0.45);border-radius:0.45rem;"
            "background:rgba(255,193,7,0.16);padding:0.55rem 0.8rem;margin:0.25rem 0 0.6rem 0;"
            "color:#78350f;line-height:1.4;"
        )
    else:
        _box = (
            "border:1px solid rgba(255,193,7,0.55);border-radius:0.45rem;"
            "background:rgba(255,193,7,0.10);padding:0.55rem 0.8rem;margin:0.25rem 0 0.6rem 0;"
            "color:#ffe8a3;line-height:1.4;"
        )
    body = (
        f'<div style="{_box}">'
        '<div style="font-weight:700;margin-bottom:0.25rem;">'
        "\u26a0 Данные для этого блока неполные — возможны пропуски/приближения:</div>"
        f'<ul style="margin:0;padding-left:1.1rem;">{items}</ul>'
        "</div>"
    )
    try:
        st.markdown(body, unsafe_allow_html=True)
    except Exception:
        pass
