"""Project scope helpers for dashboard routers + Ask AI."""

from __future__ import annotations

from typing import Any, Optional

from app.services.users_bridge import import_auth


def allowed_projects_for_user(user: dict) -> list[str] | None:
    auth = import_auth()
    return auth.resolve_allowed_projects(user.get("role") or "", user.get("id"))


def clamp_projects_list(user: dict, requested: Optional[list[str]]) -> list[str]:
    auth = import_auth()
    return auth.clamp_projects_for_user(
        user.get("role") or "",
        user.get("id"),
        requested,
    )


def parse_project_pipe(raw: Optional[str]) -> list[str]:
    if not raw or not str(raw).strip() or str(raw).strip() == "Все":
        return []
    return [p.strip() for p in str(raw).split("|") if p.strip() and p.strip() != "Все"]


def resolve_selected_projects(
    raw: Optional[str],
    available: list[Any] | None = None,
) -> list[str]:
    """Выбранные проекты. [] = все. Поддерживает «A» и «A|B».

    Sentinel ``__no_access__`` / ``__none__`` → непустой список-заглушка
    (не совпадёт с реальными лейблами → пустой датафрейм, не «все»).
    """
    if raw is not None and str(raw).strip() in ("__no_access__", "__none__"):
        return ["__no_access__"]
    selected = parse_project_pipe(raw)
    if not selected:
        return []
    if available is None:
        return selected
    allow = {
        str(p).strip()
        for p in available
        if p is not None and str(p).strip() and str(p).strip() != "Все"
    }
    return [p for p in selected if p in allow]


def applied_project_label(selected: list[str]) -> str:
    return "|".join(selected) if selected else "Все"


def clamp_project_pipe(user: dict, raw: Optional[str]) -> Optional[str]:
    """Для эндпоинтов с project='A|B'. Unrestricted + пусто → None/как было."""
    auth = import_auth()
    allowed = auth.resolve_allowed_projects(user.get("role") or "", user.get("id"))
    requested = parse_project_pipe(raw)
    if allowed is None:
        return raw
    clamped = auth.clamp_projects_for_user(
        user.get("role") or "",
        user.get("id"),
        requested,
    )
    if not clamped:
        # явный пустой scope — нет проектов
        return "__none__"
    return "|".join(clamped)


def filter_options_projects(user: dict, options: list[Any]) -> list[Any]:
    allowed = allowed_projects_for_user(user)
    if allowed is None:
        return options
    allow = set(allowed)
    out = []
    for item in options:
        if isinstance(item, str):
            if item in allow:
                out.append(item)
        elif isinstance(item, dict):
            name = item.get("project") or item.get("name") or item.get("label")
            if name in allow:
                out.append(item)
        else:
            out.append(item)
    return out
