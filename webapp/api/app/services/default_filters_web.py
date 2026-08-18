"""Resolve default_filters for webapp nav.id → filter dict."""

from __future__ import annotations

import ast
import json
from typing import Any

from app.services.ask_ai_reports import SCREENS, get_screen
from app.services.users_bridge import import_filters

# Исторические подписи в users.db, которых уже нет в SCREENS.auth_names.
_EXTRA_ALIASES: dict[str, tuple[str, ...]] = {
    "prescriptions": ("Предписания по строительству",),
    "approved-budget": ("Утвержденный бюджет",),
}

# Старые имена из Streamlit users.db, которых нет в SCREENS.
_HISTORICAL_TITLES: tuple[str, ...] = ("Сроки проекта",)

_WILDCARD_CHARS = frozenset("?\ufffd")
_PUNCT = frozenset(" \t/().,-–—:+")


def report_names_for_nav(nav_id: str) -> list[str]:
    screen = get_screen(nav_id)
    names: list[str] = []
    if screen:
        title = str(screen.get("title") or "").strip()
        if title:
            names.append(title)
        for n in screen.get("auth_names") or []:
            s = str(n).strip()
            if s and s not in names:
                names.append(s)
    nid = (nav_id or "").strip()
    if nid and nid not in names:
        names.append(nid)
    return names


def _catalog() -> list[tuple[str, list[str]]]:
    """(каноническое имя, все алиасы включая nav.id)."""
    rows: list[tuple[str, list[str]]] = []
    for nav_id, meta in SCREENS.items():
        title = str(meta.get("title") or "").strip()
        if not title:
            continue
        names: list[str] = []
        for raw in (
            title,
            nav_id,
            *(str(n).strip() for n in (meta.get("auth_names") or [])),
            *_EXTRA_ALIASES.get(nav_id, ()),
        ):
            s = (raw or "").strip()
            if s and s not in names:
                names.append(s)
        rows.append((title, names))
    return rows


def catalog_report_titles() -> list[str]:
    titles: list[str] = []
    seen: set[str] = set()
    for title, _aliases in _catalog():
        if title not in seen:
            seen.add(title)
            titles.append(title)
    return titles


def _garbled_matches(stored: str, candidate: str) -> bool:
    if len(stored) != len(candidate):
        return False
    wild = False
    for a, b in zip(stored, candidate):
        if a == b:
            continue
        if a in _WILDCARD_CHARS and b not in _PUNCT:
            wild = True
            continue
        return False
    return wild


def report_display_name(
    stored: str | None,
    extra_titles: list[str] | None = None,
) -> str:
    """Человекочитаемое имя отчёта: nav.id и битая кириллица → title."""
    s = (stored or "").strip()
    if not s:
        return ""
    for title, aliases in _catalog():
        if s in aliases:
            return title
    if s in _HISTORICAL_TITLES:
        return s
    if any(ch in _WILDCARD_CHARS for ch in s):
        hits: list[str] = []
        for title, aliases in _catalog():
            for alias in aliases:
                if alias.isascii():
                    continue
                if _garbled_matches(s, alias) and title not in hits:
                    hits.append(title)
        for title in (*_HISTORICAL_TITLES, *(extra_titles or [])):
            t = (title or "").strip()
            if not t or not _garbled_matches(s, t):
                continue
            resolved = t
            for cat_title, aliases in _catalog():
                if t == cat_title or t in aliases:
                    resolved = cat_title
                    break
            if resolved not in hits:
                hits.append(resolved)
        if len(hits) == 1:
            return hits[0]
    return s


def report_name_matches(stored: str | None, selected: str | None) -> bool:
    """True, если stored — то же самое, что выбранный отчёт (title / nav.id / алиас)."""
    a = (stored or "").strip()
    b = (selected or "").strip()
    if not a or not b:
        return False
    if a == b:
        return True
    return report_display_name(a) == report_display_name(b)


def format_filter_value_display(value: Any) -> str:
    """Списки проектов: Есипово-5, Дмитровский — без скобок и кавычек."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(x).strip() for x in value if str(x).strip())
    raw = str(value).strip()
    if not raw:
        return ""
    parsed = _try_parse_list(raw)
    if isinstance(parsed, list):
        return ", ".join(str(x).strip() for x in parsed if str(x).strip())
    return raw


def _try_parse_list(raw: str) -> list[Any] | None:
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        try:
            parsed = ast.literal_eval(raw)
        except (ValueError, SyntaxError, MemoryError):
            return None
    return parsed if isinstance(parsed, list) else None


def is_garbled_report_name(name: str | None) -> bool:
    s = (name or "").strip()
    if not s:
        return False
    wild = sum(1 for ch in s if ch in _WILDCARD_CHARS)
    letters = sum(1 for ch in s if ch.isalpha())
    return wild >= 3 and wild >= max(letters, 1)


def load_default_filters_for_role(role: str, nav_id: str) -> dict[str, Any]:
    """Merge default_filters across all report_name aliases of the screen."""
    filters_mod = import_filters()
    merged: dict[str, Any] = {}
    for name in report_names_for_nav(nav_id):
        chunk = filters_mod.get_default_filters(role, name) or {}
        for key, val in chunk.items():
            if key not in merged:
                merged[key] = val
    # Alias: single "project" → projects list for multiselect UIs
    if "projects" not in merged and "project" in merged:
        p = merged["project"]
        if isinstance(p, list):
            merged["projects"] = p
        elif isinstance(p, str) and p.strip():
            merged["projects"] = [p.strip()]
    return merged
