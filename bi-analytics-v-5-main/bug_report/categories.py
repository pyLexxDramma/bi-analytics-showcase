"""Категории баг-репорта и маппинг в Trello."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bug_report.settings import BugReportSettings

CATEGORY_LABELS_RU: dict[str, str] = {
    "urgent": "Срочно",
    "bug": "Ошибка / баг",
    "ui_improvement": "Доработка интерфейса",
    "new_feature": "Новая функция",
    "data_question": "Вопрос по данным",
    "other": "На разбор",
}

PRIORITY_LABELS_RU: dict[str, str] = {
    "critical": "Критический",
    "high": "Высокий",
    "medium": "Средний",
    "low": "Низкий",
}

VALID_CATEGORIES = frozenset(CATEGORY_LABELS_RU)
VALID_PRIORITIES = frozenset(PRIORITY_LABELS_RU)


@dataclass(frozen=True)
class TrelloTarget:
    list_id: str
    label_ids: tuple[str, ...]


def normalize_category(raw: str | None) -> str:
    cat = (raw or "").strip().lower()
    if cat in VALID_CATEGORIES:
        return cat
    return "other"


def normalize_priority(raw: str | None) -> str:
    pr = (raw or "").strip().lower()
    if pr in VALID_PRIORITIES:
        return pr
    return "medium"


def resolve_trello_target(category: str, settings: BugReportSettings) -> TrelloTarget:
    cat = normalize_category(category)
    list_by_cat = {
        "urgent": settings.trello_list_urgent,
        "bug": settings.trello_list_bug,
        "ui_improvement": settings.trello_list_ui,
        "new_feature": settings.trello_list_feature,
        "data_question": settings.trello_list_question,
        "other": settings.trello_list_triage,
    }
    labels_by_cat = {
        "urgent": (settings.trello_label_urgent, settings.trello_label_bug),
        "bug": (settings.trello_label_bug,),
        "ui_improvement": (settings.trello_label_ui,),
        "new_feature": (settings.trello_label_feature,),
        "data_question": (settings.trello_label_question,),
        "other": (settings.trello_label_triage,),
    }
    list_id = (list_by_cat.get(cat) or "").strip() or settings.trello_list_triage
    label_ids = tuple(x for x in labels_by_cat.get(cat, ()) if x)
    if not label_ids and settings.trello_label_triage:
        label_ids = (settings.trello_label_triage,)
    return TrelloTarget(list_id=list_id, label_ids=label_ids)


def category_display(category: str) -> str:
    return CATEGORY_LABELS_RU.get(normalize_category(category), CATEGORY_LABELS_RU["other"])


def priority_display(priority: str) -> str:
    return PRIORITY_LABELS_RU.get(normalize_priority(priority), PRIORITY_LABELS_RU["medium"])


def classification_schema_hint() -> dict[str, Any]:
    """Контракт ответа для коллеги (AI endpoint)."""
    return {
        "category": sorted(VALID_CATEGORIES),
        "priority": sorted(VALID_PRIORITIES),
        "title": "string, до 80 символов",
        "summary": "string, 1-2 предложения",
        "confidence": "float 0..1",
    }
