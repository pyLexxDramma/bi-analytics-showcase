"""Снимки данных (`web_versions`) — как селектор «Версия данных» в сайдбаре [main]."""
from __future__ import annotations

from typing import Any

from app.services.core_bridge import prepare_web_db


def list_versions() -> dict[str, Any]:
    try:
        prepare_web_db()
        import web_schema  # type: ignore

        rows = web_schema.get_all_versions()
        active = web_schema.get_active_version_id()
    except Exception as exc:  # noqa: BLE001
        return {"items": [], "active_version_id": None, "error": str(exc)}

    items = [
        {
            "id": int(row.get("id")),
            "created_at": str(row.get("created_at") or ""),
            "label": row.get("label"),
            "status": row.get("status"),
            "files_count": int(row.get("files_count") or 0),
            "rows_count": int(row.get("rows_count") or 0),
            "is_active": bool(row.get("is_active")),
        }
        for row in rows or []
    ]
    return {
        "items": items,
        "active_version_id": int(active) if active else None,
        "error": None,
    }


def activate_version(version_id: int) -> dict[str, Any]:
    try:
        prepare_web_db()
        import web_schema  # type: ignore

        known = {int(row.get("id")) for row in web_schema.get_all_versions() or []}
        if int(version_id) not in known:
            return {"ok": False, "error": f"Версия {version_id} не найдена"}
        web_schema.activate_version(int(version_id))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    return {"ok": True, **list_versions()}
