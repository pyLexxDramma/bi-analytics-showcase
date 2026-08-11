"""Resolve default_filters for webapp nav.id → filter dict."""

from __future__ import annotations

from typing import Any

from app.services.ask_ai_reports import get_screen
from app.services.users_bridge import import_filters


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
