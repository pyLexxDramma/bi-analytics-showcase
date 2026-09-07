"""Клиентские статусы заявки (без внутренних деталей Trello)."""

from __future__ import annotations

CLIENT_STATUS_ACCEPTED = "accepted"
CLIENT_STATUS_IN_PROGRESS = "in_progress"
CLIENT_STATUS_ON_HOLD = "on_hold"
CLIENT_STATUS_READY = "ready"

CLIENT_STATUS_LABELS_RU: dict[str, str] = {
    CLIENT_STATUS_ACCEPTED: "Принята",
    CLIENT_STATUS_IN_PROGRESS: "В работе",
    CLIENT_STATUS_ON_HOLD: "На холде (ждём вас / данные)",
    CLIENT_STATUS_READY: "Готово к проверке",
}


def client_status_label(status: str | None) -> str:
    key = (status or CLIENT_STATUS_ACCEPTED).strip().lower()
    return CLIENT_STATUS_LABELS_RU.get(key, CLIENT_STATUS_LABELS_RU[CLIENT_STATUS_ACCEPTED])


def map_trello_list_to_client_status(list_name: str | None) -> str:
    """Маппинг имени колонки Trello → client_status."""
    n = (list_name or "").strip().casefold()
    if not n:
        return CLIENT_STATUS_IN_PROGRESS
    if "анализ" in n or "analysis" in n or "triage" in n or "разбор" in n:
        return CLIENT_STATUS_ACCEPTED
    if "холд" in n or "hold" in n or "когда" in n or "отлож" in n:
        return CLIENT_STATUS_ON_HOLD
    if "готов" in n or n == "done" or "закрыт" in n:
        return CLIENT_STATUS_READY
    # Нужно сделать / Фичи / В работе / На проверку / …
    return CLIENT_STATUS_IN_PROGRESS
