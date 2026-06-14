"""
Список отчётов для демо-инстанса (showcase).

Production не импортирует этот модуль. Сырые/неготовые разделы (Гант, ПД/РД, ИД, предписания) исключены.
"""
from __future__ import annotations

from typing import Dict, FrozenSet, List, Sequence

# Канонические имена как в ``dashboards.REPORT_CATEGORIES``.
SHOWCASE_REPORT_ALLOWLIST: FrozenSet[str] = frozenset(
    {
        "Девелоперские проекты",
        "Контрольные точки",
        "БДДС",
        "БДР",
        "Утверждённый бюджет план/факт",
        "Прогнозный бюджет",
        "Причины отклонений",
        "Отклонение от базового плана",
        "ГДРС (превью — светлая, люди)",
        "ГДРС (превью — светлая, техника)",
        "Дебиторская и кредиторская задолженность подрядчиков",
    }
)

# Короткие подписи в меню showcase (ключ — каноническое имя из REPORT_CATEGORIES).
SHOWCASE_REPORT_LABELS: Dict[str, str] = {
    "ГДРС (превью — светлая, люди)": "ГДРС (люди)",
    "ГДРС (превью — светлая, техника)": "ГДРС (техника)",
}


def showcase_report_label(report_name: str) -> str:
    """Подпись отчёта в sidebar showcase; production-имена не меняет."""
    return SHOWCASE_REPORT_LABELS.get(report_name, report_name)


def filter_showcase_reports(report_names: Sequence[str]) -> List[str]:
    """Оставляет только отчёты из allowlist, сохраняя порядок входного списка."""
    allowed = SHOWCASE_REPORT_ALLOWLIST
    return [n for n in report_names if n in allowed]
