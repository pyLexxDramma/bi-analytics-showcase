"""Реестр экранов webapp → report id для XCA Ask AI (page-level, вариант 1)."""

from __future__ import annotations

from typing import Any

# nav.id → XCA report (+ метаданные для ctx / roles-catalog)
# Пока XCA публикует table-level ids; page-level screen_* — черновик для их реестра.
SCREENS: dict[str, dict[str, Any]] = {
    "developer-projects": {
        "report": "screen_developer_projects",
        "title": "Девелоперские проекты",
        "src": "developer-projects",
        "auth_names": ["Девелоперские проекты"],
        "ctx_hint": "Матрица девелоперских проектов: статусы, сроки, ключевые метрики по проектам.",
    },
    "bdds": {
        "report": "screen_bdds",
        "title": "БДДС (расходы)",
        "src": "finance/bdds",
        "auth_names": ["БДДС (расходы)", "БДДС"],
        "ctx_hint": "БДДС расходы по периодам. Суммы в рублях. Ближайший table-id у XCA: bdds_monthly.",
    },
    "bdr": {
        "report": "screen_bdr",
        "title": "БДР (расходы)",
        "src": "finance/bdr",
        "auth_names": ["БДР (расходы)", "БДР"],
        "ctx_hint": "БДР расходы. Отдельного report в реестре XCA пока нет.",
    },
    "approved-budget": {
        "report": "screen_approved_budget",
        "title": "Утверждённый бюджет план/факт",
        "src": "finance/approved-budget",
        "auth_names": ["Утвержденный бюджет", "Утверждённый бюджет план/факт"],
        "ctx_hint": "Утверждённый бюджет план и факт. Ближайший table-id: bdds_plan_fact.",
    },
    "bdds-plan-fact": {
        "report": "screen_bdds_plan_fact",
        "title": "БДДС расходы (план, факт, уточненный план)",
        "src": "finance/bdds-plan-fact",
        "auth_names": [
            "БДДС (утверждённый/прогнозный)",
            "Прогнозный БДДС",
            "Прогнозный бюджет",
            "Бюджет план/факт",
        ],
        "ctx_hint": "План, факт и уточнённый план БДДС. Ближайший table-id: bdds_forecast.",
    },
    "control-points": {
        "report": "screen_control_points",
        "title": "Контрольные точки",
        "src": "timeline/control-points",
        "auth_names": ["Контрольные точки"],
        "ctx_hint": "Контрольные точки графика. Ближайший table-id: control_points.",
    },
    "project-schedule": {
        "report": "screen_project_schedule",
        "title": "График проекта",
        "src": "timeline/project-schedule",
        "auth_names": ["График проекта"],
        "ctx_hint": "График проекта / смещение задач. Ближайший table-id: task_shift.",
    },
    "deviation-reasons": {
        "report": "screen_deviation_reasons",
        "title": "Причины отклонений",
        "src": "timeline/deviation-reasons",
        "auth_names": ["Причины отклонений"],
        "ctx_hint": "Причины отклонений / срыва. Ближайший table-id: commissioning_reasons.",
    },
    "baseline-deviation": {
        "report": "screen_baseline_deviation",
        "title": "Отклонение от базового плана",
        "src": "timeline/baseline-deviation",
        "auth_names": ["Отклонение от базового плана"],
        "ctx_hint": "Отклонение от базового плана MSP. Ближайший table-id: msp_levels.",
    },
    "project-documentation": {
        "report": "screen_project_documentation",
        "title": "Проектная документация",
        "src": "docs/project-documentation",
        "auth_names": ["Проектная документация", "Просрочка выдачи ПД"],
        "ctx_hint": "Проектная документация целиком. В реестре XCA отдельных page-id нет.",
    },
    "working-documentation": {
        "report": "screen_working_documentation",
        "title": "Рабочая документация",
        "src": "docs/working-documentation",
        "auth_names": ["Рабочая документация", "Просрочка выдачи РД"],
        "ctx_hint": "Рабочая документация. Ближайший table-id: rd_overdue.",
    },
    "gdrs-people": {
        "report": "screen_gdrs_people",
        "title": "ГДРС (люди)",
        "src": "gdrs/people",
        "auth_names": ["ГДРС (люди)", "ГДРС", "График движения рабочей силы"],
        "ctx_hint": "ГДРС люди план/факт. Ближайший table-id: gdrs_people.",
    },
    "gdrs-equipment": {
        "report": "screen_gdrs_equipment",
        "title": "ГДРС (техника)",
        "src": "gdrs/equipment",
        "auth_names": ["ГДРС (техника)", "ГДРС Техника"],
        "ctx_hint": "ГДРС техника план/факт. Ближайший table-id: gdrs_technique.",
    },
    "prescriptions": {
        "report": "screen_prescriptions",
        "title": "Предписания по подрядчикам",
        "src": "prescriptions",
        "auth_names": [
            "Предписания по подрядчикам",
            "Неустраненные предписания",
        ],
        "ctx_hint": "Экран предписаний целиком. Ближайшие table-id: prescriptions_overdue / prescriptions_critical / prescriptions_monthly.",
    },
    "executive-docs": {
        "report": "screen_executive_docs",
        "title": "Исполнительная документация",
        "src": "executive-docs",
        "auth_names": ["Исполнительная документация"],
        "ctx_hint": "Исполнительная документация. Ближайшие table-id: id_transfer_pct / id_overdue_contractors.",
    },
    "debit-credit": {
        "report": "screen_debit_credit",
        "title": "Дебиторская и кредиторская задолженность подрядчиков",
        "src": "debit-credit",
        "auth_names": [
            "Дебиторская и кредиторская задолженность подрядчиков",
            "Дебиторская и кредиторская задолженность",
        ],
        "ctx_hint": "ДЗ/КЗ подрядчиков. Точного report в реестре XCA нет (advances — другое).",
    },
}

REPORT_BY_NAV = {k: str(v["report"]) for k, v in SCREENS.items()}
NAV_BY_REPORT = {str(v["report"]): k for k, v in SCREENS.items()}


def get_screen(nav_id: str) -> dict[str, Any] | None:
    return SCREENS.get((nav_id or "").strip())


def resolve_report(nav_id: str | None, report: str | None) -> tuple[str, dict[str, Any] | None]:
    """Вернуть (report_id, screen_meta|None)."""
    if nav_id:
        screen = get_screen(nav_id)
        if screen:
            return str(screen["report"]), screen
    rid = (report or "").strip()
    if rid:
        nav = NAV_BY_REPORT.get(rid)
        if nav:
            return rid, SCREENS[nav]
        return rid, None
    return "free", None
