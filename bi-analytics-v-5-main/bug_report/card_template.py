"""Шаблон карточки доски: номер, тип, суть, чеклист, статус.

Типы взяты с прошлых правок Марины: она пишет, что уже есть на экране,
что в этом месте не так, и какое число или поведение должно быть.
«Доработка» — место есть, значение неверное.
«Недоработка» — сданное не доведено (не хватает, закрыто, но не исправлено).
«Улучшение» — доработать уже существующий экран.
«Новая фича» — того, что просят, на экране ещё нет.
"""

from __future__ import annotations

import re

KIND_REWORK = "Доработка"
KIND_INCOMPLETE = "Недоработка"
KIND_IMPROVEMENT = "Улучшение"
KIND_FEATURE = "Новая фича"

_KINDS = (KIND_REWORK, KIND_INCOMPLETE, KIND_IMPROVEMENT, KIND_FEATURE)


def is_yanchurkin(context: dict | None) -> bool:
    blob = " ".join(
        str((context or {}).get(key) or "")
        for key in ("contact_email", "first_name", "last_name", "username")
    ).casefold()
    return "yanchurkin" in blob or "янчуркин" in blob


def card_kind(text: str, category: str = "") -> str:
    t = (text or "").casefold()
    if any(k in t for k in ("улучшени", "улучшить")):
        return KIND_IMPROVEMENT
    if category == "new_feature" or any(
        k in t for k in ("новая фича", "новый функционал", "новую функцию", "хочу добавить")
    ):
        return KIND_FEATURE
    if any(
        k in t
        for k in ("не хватает", "недоработ", "не устранена", "не додел", "закрыта, но", "не доделан")
    ):
        return KIND_INCOMPLETE
    return KIND_REWORK


def substance_line(text: str, ai_title: str = "") -> str:
    raw = (ai_title or "").strip() or (text or "").strip()
    raw = raw.split("\n", 1)[0]
    raw = re.sub(r"^[\*\"'«»\s]+|[\*\"'«»\s]+$", "", raw)
    raw = re.sub(
        r"(?i)^(улучшения|улучшение|доработка|недоработка|новая фича|фича)\s*[!.:]?\s*",
        "",
        raw,
    )
    raw = re.sub(r"\s+", " ", raw).strip(" *\"'«»")
    if not raw:
        raw = "Без описания"
    if len(raw) > 110:
        raw = raw[:109].rstrip() + "…"
    return raw


def format_board_title(user_seq: int | str | None, kind: str, substance: str) -> str:
    kind = kind if kind in _KINDS else KIND_REWORK
    body = f"{kind} · {substance}".strip()
    seq = str(user_seq or "").strip()
    if seq and seq not in ("0", "—", "None"):
        title = f"№{seq} · {body}"
    else:
        title = body
    return title[:160]


def checklist_items(text: str, substance: str) -> list[str]:
    items: list[str] = []
    for raw in (text or "").splitlines():
        match = re.match(r"^(?:\d+[\.\)]|[-·•])\s+(.+)$", raw.strip())
        if not match:
            continue
        item = re.sub(r"\s+", " ", match.group(1)).strip()
        if len(item) < 8:
            continue
        if item not in items:
            items.append(item[:180])
    if len(items) >= 2:
        return items[:8]
    one = substance.strip() or "Разобрать заявку"
    return [one[:180]]


def status_comment(list_name: str = "Анализ") -> str:
    return f"Статус: принята. Колонка «{list_name}», ждёт разбора."
