"""Каталог фильтров и виджетов для UI ACL (зеркало web/src/lib/report-ui-catalog.ts)."""

from __future__ import annotations

from typing import Any

_FINANCE_FILTERS = [
    {"id": "projects", "label": "Проект"},
    {"id": "date_from", "label": "Период с"},
    {"id": "date_to", "label": "Период по"},
    {"id": "group", "label": "Группировать по"},
    {"id": "view", "label": "Представление"},
    {"id": "show_deviation", "label": "Показать отклонение"},
    {"id": "hide_zero", "label": "Скрывать нулевые месяцы"},
]

_FINANCE_WIDGETS = [
    {"id": "kpi", "label": "Сводка (KPI)"},
    {"id": "chart_period", "label": "График по периодам"},
    {"id": "table_period", "label": "Таблица по периодам"},
    {"id": "chart_project", "label": "График по проектам"},
    {"id": "table_project", "label": "Таблица по проектам"},
]

_GDRS_FILTERS = [
    {"id": "projects", "label": "Проект"},
    {"id": "contractors", "label": "Контрагент"},
    {"id": "months", "label": "Месяц"},
    {"id": "plan_agg", "label": "Агрегация план"},
    {"id": "skud_agg", "label": "Агрегация СКУД"},
    {"id": "dyn_agg", "label": "Агрегация динамики"},
    {"id": "only_with_plan", "label": "Только с планом"},
]

_GDRS_WIDGETS = [
    {"id": "kpi", "label": "Сводка (KPI)"},
    {"id": "chart_projects", "label": "График по проектам"},
    {"id": "table_projects", "label": "Таблица по проектам"},
    {"id": "pie", "label": "Распределение (pie)"},
    {"id": "dynamics", "label": "Динамика"},
    {"id": "matrix", "label": "Матрица"},
]

REPORT_UI_CATALOG: list[dict[str, Any]] = [
    {
        "nav_id": "bdds",
        "title": "БДДС (расходы)",
        "filters": _FINANCE_FILTERS,
        "widgets": _FINANCE_WIDGETS,
    },
    {
        "nav_id": "bdr",
        "title": "БДР (расходы)",
        "filters": _FINANCE_FILTERS,
        "widgets": _FINANCE_WIDGETS,
    },
    {
        "nav_id": "working-documentation",
        "title": "Рабочая документация",
        "filters": [
            {"id": "projects", "label": "Проект"},
            {"id": "sections", "label": "Раздел"},
            {"id": "statuses", "label": "Статус"},
            {"id": "periodMode", "label": "Период"},
            {"id": "dateFrom", "label": "Дата с"},
            {"id": "dateTo", "label": "Дата по"},
            {"id": "metricMode", "label": "Метрика"},
            {"id": "showForecast", "label": "Прогноз"},
            {"id": "viewMode", "label": "Отображение"},
        ],
        "widgets": [
            {"id": "kpi", "label": "KPI-карточки"},
            {"id": "pie", "label": "Исполнение РД (pie)"},
            {"id": "dynamics", "label": "Динамика по месяцам"},
            {"id": "delay_chart", "label": "Просрочка выдачи"},
            {"id": "tables", "label": "Таблицы"},
        ],
    },
    {
        "nav_id": "gdrs-people",
        "title": "ГДРС (люди)",
        "filters": _GDRS_FILTERS,
        "widgets": _GDRS_WIDGETS,
    },
    {
        "nav_id": "gdrs-equipment",
        "title": "ГДРС (техника)",
        "filters": _GDRS_FILTERS,
        "widgets": _GDRS_WIDGETS,
    },
    {
        "nav_id": "developer-projects",
        "title": "Девелоперские проекты",
        "filters": [{"id": "projects", "label": "Проект"}],
        "widgets": [
            {"id": "kpi", "label": "Сводка"},
            {"id": "matrix", "label": "Матрица контрольных точек"},
        ],
    },
    {
        "nav_id": "prescriptions",
        "title": "Предписания",
        "filters": [
            {"id": "projects", "label": "Проект"},
            {"id": "contractors", "label": "Подрядчик"},
            {"id": "contract_q", "label": "Поиск договора"},
            {"id": "date_from", "label": "Дата с"},
            {"id": "date_to", "label": "Дата по"},
            {"id": "hide_resolved", "label": "Скрыть устранённые"},
        ],
        "widgets": [
            {"id": "kpi", "label": "KPI / статусы"},
            {"id": "chart_status", "label": "График по статусам"},
            {"id": "chart_objects", "label": "График по объектам"},
            {"id": "table", "label": "Таблица предписаний"},
        ],
    },
]


def list_ui_catalog() -> list[dict[str, Any]]:
    return list(REPORT_UI_CATALOG)


def get_screen_catalog(nav_id: str) -> dict[str, Any] | None:
    nid = (nav_id or "").strip()
    for row in REPORT_UI_CATALOG:
        if row["nav_id"] == nid:
            return row
    return None
