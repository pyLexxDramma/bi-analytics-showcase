"""Контрольные точки — матрица [main] из активной версии web_data.db."""
from __future__ import annotations

import re
from typing import Any

from app.config import DATA_MODE, WEB_DB_PATH
from app.services.core_bridge import import_dashboard_module, load_msp_frame, prepare_web_db
from app.services.db_ingest import db_status
from app.services.report_cache import cache_get, cache_set


def _empty_payload(*, error: str | None = None) -> dict[str, Any]:
    return {
        "meta": {
            "source": "web_data.db",
            "data_mode": DATA_MODE,
            "parity": "main_control_points",
            "version_id": None,
            "rows": 0,
            "error": error,
            "db": db_status(),
        },
        "filters": {
            "projects": [],
            "mode": "multiselect",
            "empty_means_all": True,
            "applied": {"projects": []},
        },
        "groups": [],
        "projects": [],
    }


def _otkl_days(value: Any) -> int | None:
    match = re.search(r"-?\d+", str(value or ""))
    return int(match.group()) if match else None


def build_control_points_payload(*, projects: list[str] | None = None) -> dict[str, Any]:
    selected = [
        str(item).strip()
        for item in (projects or [])
        if str(item).strip() and str(item).strip() != "Все"
    ]
    cache_key = (
        f"v4|projects={','.join(sorted(selected))}|"
        f"db={WEB_DB_PATH}|mtime={db_status().get('mtime')}"
    )
    cached = cache_get("control-points", cache_key, max_age_sec=3600)
    if cached is not None:
        return cached

    if not WEB_DB_PATH.is_file():
        return _empty_payload(error="web_data.db нет — выполните POST /api/admin/ingest (или sync).")

    try:
        prepare_web_db()
        import web_schema  # type: ignore

        matrix = import_dashboard_module("dev_projects_tz_matrix")
        version_id = web_schema.get_active_version_id()
        if not version_id:
            return _empty_payload(error="Нет active version_id в web_data.db")

        mdf = load_msp_frame(int(version_id))
        if mdf is None or getattr(mdf, "empty", True):
            return _empty_payload(error="Нет MSP (file_type=project) в активной версии")

        name_to_raws = matrix._control_points_project_label_to_raw_names(mdf)
        available = sorted(name_to_raws, key=str.casefold)
        applied = [name for name in selected if name in name_to_raws]
        filtered = mdf
        if applied:
            project_column = matrix._project_name_column(mdf)
            raw_names: list[str] = []
            for name in applied:
                raw_names.extend(name_to_raws.get(name, []))
            if project_column and raw_names:
                filtered = mdf[mdf[project_column].astype(str).str.strip().isin(raw_names)].copy()

        view = matrix.build_control_points_df(filtered, hide_completed=False)
        # Подписи вроде «Есипово-5 (1 этап)» делят одни raw MSP-имена —
        # после сборки оставляем только выбранные строки матрицы.
        if applied:
            view = view[view["project"].astype(str).isin(applied)].copy()
        specs = [(title, slug) for title, slug, _ in matrix.get_control_point_milestones_effective()]
        groups = [
            {
                "id": f"group-{index}",
                "milestones": [{"title": title, "slug": slug} for title, slug in group],
            }
            for index, group in enumerate(matrix._control_points_split_groups(specs), start=1)
        ]
        projects_out = []
        for _, row in view.iterrows():
            cells = {}
            for _, slug in specs:
                otkl = str(row.get(f"{slug}_otkl", "Н/Д") or "Н/Д")
                cells[slug] = {
                    "plan": str(row.get(f"{slug}_plan", "Н/Д") or "Н/Д"),
                    "fact": str(row.get(f"{slug}_fact", "Н/Д") or "Н/Д"),
                    "otkl": otkl,
                    "otkl_days": _otkl_days(otkl),
                    "status": "ok" if bool(row.get(f"{slug}_ok", False)) else "bad",
                    "pct_complete_100": bool(row.get(f"{slug}_pct100", False)),
                }
            projects_out.append({"project": str(row.get("project", "")), "cells": cells})

        payload = {
            "meta": {
                "source": "web_data.db",
                "data_mode": DATA_MODE,
                "parity": "main_control_points",
                "version_id": int(version_id),
                "rows": len(projects_out),
                "cells": len(projects_out) * len(specs),
                "error": None,
                "db": db_status(),
            },
            "filters": {
                "projects": available,
                "mode": "multiselect",
                "empty_means_all": True,
                "applied": {"projects": applied},
            },
            "groups": groups,
            "projects": projects_out,
        }
        cache_set("control-points", cache_key, payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        return _empty_payload(error=str(exc))
