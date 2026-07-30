"""Девелоперские проекты — матрица как в [main] (dev_projects_tz_matrix + web_data.db)."""
from __future__ import annotations

import importlib.util
import os
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any

import pandas as pd

from app.config import CORE_APP_DIR, DATA_MODE, WEB_DB_PATH
from app.services.db_ingest import db_status
from app.services.report_cache import cache_get, cache_set


# --- shared helpers (используют control_points / timeline / docs) ---


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).casefold()
    return re.sub(r"[\s_]+", " ", text).strip()


def _read_msp(path: Path) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return pd.read_csv(path, sep=None, engine="python", encoding=encoding)
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    return pd.DataFrame()


def _project_from_path(path: Path) -> str:
    stem = path.stem
    slug = re.sub(r"^msp_", "", stem, flags=re.IGNORECASE)
    slug = re.sub(r"_\d{2}-\d{2}-\d{4}$", "", slug)
    return slug.replace("_", " ").strip().title() or path.stem


def _as_date(value: Any) -> date | None:
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    return parsed.date() if pd.notna(parsed) else None


def _as_pct(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().replace("%", "").replace(",", ".")
    try:
        result = float(text)
    except ValueError:
        return None
    return result * 100 if 0 < result <= 1 else result


def _format_date(value: date | None) -> str | None:
    return value.strftime("%d.%m.%Y") if value else None


def _status(plan: date | None, fact: date | None, pct: float | None) -> str:
    if not plan and not fact:
        return "missing"
    if fact and (pct is not None and pct >= 100 or plan and fact <= plan):
        return "done"
    if plan and ((not fact and plan < date.today()) or (fact and fact > plan)):
        return "overdue"
    return "on_track"


def _ensure_core_path() -> None:
    core = str(CORE_APP_DIR.resolve())
    if core not in sys.path:
        sys.path.insert(0, core)


def _ensure_streamlit_stub() -> None:
    existing = sys.modules.get("streamlit")
    if existing is not None and getattr(existing, "cache_data", None) is not None:
        return
    try:
        if importlib.util.find_spec("streamlit") is not None:
            import streamlit  # noqa: F401

            return
    except ModuleNotFoundError:
        pass

    st = ModuleType("streamlit")

    def cache_data(*args, **kwargs):
        def decorator(fn):
            return fn

        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]
        return decorator

    class _SS(dict):
        def __getattr__(self, name: str):
            try:
                return self[name]
            except KeyError as exc:
                raise AttributeError(name) from exc

        def __setattr__(self, name: str, value: Any) -> None:
            self[name] = value

    st.cache_data = cache_data  # type: ignore[attr-defined]
    st.session_state = _SS()  # type: ignore[attr-defined]
    st.error = lambda *a, **kw: None  # type: ignore[attr-defined]
    st.warning = lambda *a, **kw: None  # type: ignore[attr-defined]
    sys.modules["streamlit"] = st


def _import_dashboard_module(name: str):
    _ensure_streamlit_stub()
    _ensure_core_path()
    full = f"dashboards.{name}"
    existing = sys.modules.get(full)
    if existing is not None:
        return existing
    if "dashboards" not in sys.modules:
        pkg = ModuleType("dashboards")
        pkg.__path__ = [str((CORE_APP_DIR / "dashboards").resolve())]  # type: ignore[attr-defined]
        sys.modules["dashboards"] = pkg
    path = CORE_APP_DIR / "dashboards" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(full, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full] = mod
    spec.loader.exec_module(mod)
    return mod


def _prepare_web_db() -> None:
    _ensure_streamlit_stub()
    _ensure_core_path()
    db_path = str(WEB_DB_PATH.resolve())
    os.environ["WEB_DB_PATH"] = db_path
    import web_schema  # type: ignore

    web_schema.WEB_DB_PATH = db_path


def _empty_payload(*, error: str | None = None) -> dict[str, Any]:
    return {
        "meta": {
            "source": "web_data.db",
            "data_mode": DATA_MODE,
            "parity": "main_tz_matrix",
            "version_id": None,
            "rows": 0,
            "error": error,
            "db": db_status(),
        },
        "filters": {
            "projects": [],
            "applied": {"projects": []},
            "mode": "multiselect",
            "empty_means_all": True,
        },
        "hints": [],
        "legend": {
            "pct100": "План/Факт — задача в MSP закрыта на 100%",
            "pos": "Откл. ≥ 0 (в срок / опережение)",
            "neg": "Откл. < 0 (просрочка / недовыполнение)",
        },
        "kpis": {
            "projects": 0,
            "milestones_found": 0,
            "completed_pct": 0,
            "overdue": 0,
            "missing_fact": 0,
        },
        "tremor": {
            "completion_by_project": [],
            "status_mix": [
                {"name": "Выполнено", "value": 0},
                {"name": "Просрочено", "value": 0},
                {"name": "Без факта", "value": 0},
                {"name": "В срок", "value": 0},
            ],
        },
        "matrix": {
            "phases": [
                {"id": "invest", "label": "Инвестиционная фаза"},
                {"id": "life", "label": "Жизнь проекта"},
            ],
            "columns": [],
            "projects": [],
        },
    }


def _cell_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "plan": row.get("plan"),
        "fact": row.get("fact"),
        "otkl": row.get("otkl"),
        "pct_complete_100": bool(row.get("pct_complete_100")),
        "warn": bool(row.get("warn")),
        "otkl_fact_lt_plan": bool(row.get("otkl_fact_lt_plan")),
        "subcolumn_labels": row.get("subcolumn_labels"),
    }


def _serialize_matrix(
    blocks: list[tuple[str, list[dict[str, Any]]]],
) -> dict[str, Any]:
    columns: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, rows in blocks:
        for row in rows:
            key = str(row.get("row_key") or row.get("label") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            columns.append(
                {
                    "key": key,
                    "label": row.get("label"),
                    "phase": row.get("phase") or "life",
                    "group": row.get("group"),
                    "subcolumn_labels": row.get("subcolumn_labels"),
                }
            )

    projects_out: list[dict[str, Any]] = []
    for label, rows in blocks:
        cells: dict[str, Any] = {}
        for row in rows:
            key = str(row.get("row_key") or row.get("label") or "")
            if key:
                cells[key] = _cell_from_row(row)
        projects_out.append({"project": label, "cells": cells})

    return {
        "phases": [
            {"id": "invest", "label": "Инвестиционная фаза"},
            {"id": "life", "label": "Жизнь проекта"},
        ],
        "columns": columns,
        "projects": projects_out,
    }


def _otkl_num(otkl: Any) -> float | None:
    text = str(otkl or "").replace(",", ".").replace(" ", "")
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _cell_status(cell: dict[str, Any]) -> str:
    plan = str(cell.get("plan") or "").strip()
    fact = str(cell.get("fact") or "").strip()
    otkl = str(cell.get("otkl") or "").strip()
    if (not plan or plan in ("Н/Д", "—", "-")) and (not fact or fact in ("Н/Д", "—", "-")):
        return "missing"
    if cell.get("pct_complete_100"):
        return "done"
    n = _otkl_num(otkl)
    if n is not None and n < 0:
        return "overdue"
    if fact and fact not in ("Н/Д", "—", "-"):
        return "done"
    if n is not None and n >= 0 and plan:
        return "on_track"
    return "on_track"


def _summarize_from_matrix(matrix: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    projects = matrix.get("projects") or []
    columns = matrix.get("columns") or []
    completed = overdue = missing = on_track = 0
    by_project: list[dict[str, Any]] = []
    for proj in projects:
        cells = proj.get("cells") or {}
        p_done = p_total = 0
        for col in columns:
            key = col.get("key")
            if not key:
                continue
            cell = cells.get(key) or {}
            st = _cell_status(cell)
            p_total += 1
            if st == "done":
                completed += 1
                p_done += 1
            elif st == "overdue":
                overdue += 1
            elif st == "missing":
                missing += 1
            else:
                on_track += 1
        by_project.append(
            {
                "project": proj.get("project"),
                "completed": p_done,
                "total": p_total,
                "pct": round(p_done / p_total * 100, 1) if p_total else 0,
            }
        )
    total = completed + overdue + missing + on_track
    kpis = {
        "projects": len(projects),
        "milestones_found": total,
        "completed_pct": round(completed / total * 100, 1) if total else 0,
        "overdue": overdue,
        "missing_fact": missing,
    }
    tremor = {
        "completion_by_project": by_project,
        "status_mix": [
            {"name": "Выполнено", "value": completed},
            {"name": "Просрочено", "value": overdue},
            {"name": "Без факта", "value": missing},
            {"name": "В срок", "value": on_track},
        ],
    }
    return kpis, tremor


def build_developer_projects_payload(
    *,
    projects: list[str] | None = None,
) -> dict[str, Any]:
    """
    Паритет с dashboard_developer_projects / render_dev_tz_matrix.
    projects: multiselect; пустой список = все проекты (как в [main]).
    """
    sel = [str(p).strip() for p in (projects or []) if str(p).strip()]
    cache_key = f"v3|projects={','.join(sorted(sel))}|db={WEB_DB_PATH}|mtime={db_status().get('mtime')}"
    cached = cache_get("developer-projects", cache_key, max_age_sec=3600)
    if cached is not None:
        return cached

    if not WEB_DB_PATH.is_file():
        return _empty_payload(
            error="web_data.db нет — выполните POST /api/admin/ingest (или sync)."
        )

    try:
        _prepare_web_db()
        import web_schema  # type: ignore
        from web_loader import _build_project_frames, _web_db_mtime  # type: ignore
        from web_db_read import load_version_dataframe  # type: ignore

        mtx = _import_dashboard_module("dev_projects_tz_matrix")

        vid = web_schema.get_active_version_id()
        if not vid:
            return _empty_payload(error="Нет active version_id в web_data.db")

        _, mdf = _build_project_frames(int(vid), _web_db_mtime())
        if mdf is None or getattr(mdf, "empty", True):
            return _empty_payload(error="Нет MSP (file_type=project) в активной версии")

        try:
            mdf = mtx.dedupe_msp_for_developer_projects(mdf)
        except Exception:
            pass

        pcol = "project name"
        if pcol not in mdf.columns:
            return _empty_payload(error="В MSP нет колонки project name")

        ss: dict[str, Any] = {
            "project_data": mdf,
            "reference_1c_dannye": load_version_dataframe(int(vid), "reference_dannye"),
            "tessa_tasks_data": load_version_dataframe(int(vid), "tessa_tasks"),
            "tessa_data": load_version_dataframe(int(vid), "tessa"),
        }

        grouped: dict[str, list[str]] = defaultdict(list)
        for raw in mdf[pcol].dropna().astype(str).str.strip().unique().tolist():
            if not raw or raw.lower() in ("nan", "none", "nat"):
                continue
            gk = str(mtx._control_points_project_group_key(raw))
            grouped[gk].append(raw)

        def _label(gk: str, raws: list[str]) -> str:
            return str(mtx._control_points_project_label(gk, raws))

        all_labels = sorted(
            (_label(gk, vs) for gk, vs in grouped.items()),
            key=lambda x: str(x).casefold(),
        )

        if sel:
            sel_gks = {str(mtx._control_points_project_group_key(p)) for p in sel}
            # также матч по готовой подписи
            label_to_gk = {_label(gk, vs): gk for gk, vs in grouped.items()}
            for p in sel:
                if p in label_to_gk:
                    sel_gks.add(label_to_gk[p])
            grouped = {gk: vs for gk, vs in grouped.items() if gk in sel_gks}

        blocks: list[tuple[str, list[dict[str, Any]]]] = []
        for gk in sorted(
            grouped.keys(),
            key=lambda k: _label(k, grouped[k]).casefold(),
        ):
            label = _label(gk, grouped[gk])
            raws = sorted(set(grouped[gk]))
            sub = mdf[mdf[pcol].astype(str).str.strip().isin(raws)].copy()
            for blab, rows in mtx.build_dev_tz_matrix_blocks(
                sub,
                mdf,
                ss,
                project_label_for_scope=label,
            ):
                blocks.append((str(blab or label).strip(), rows))

        hints: list[str] = []
        try:
            dq = _import_dashboard_module("data_quality_hints")
            raw_hints = dq.collect_developer_projects_hints(ss, mdf)
            if isinstance(raw_hints, list):
                for h in raw_hints:
                    if isinstance(h, dict):
                        hints.append(str(h.get("message") or h.get("text") or h))
                    else:
                        hints.append(str(h))
        except Exception:
            pass

        matrix = _serialize_matrix(blocks)
        kpis, tremor = _summarize_from_matrix(matrix)
        payload = {
            "meta": {
                "source": "web_data.db",
                "data_mode": DATA_MODE,
                "parity": "main_tz_matrix",
                "version_id": int(vid),
                "rows": len(blocks),
                "columns": len(matrix.get("columns") or []),
                "cells": kpis.get("milestones_found"),
                "db": db_status(),
            },
            "filters": {
                "projects": all_labels,
                "applied": {"projects": sel},
                "mode": "multiselect",
                "empty_means_all": True,
            },
            "hints": hints,
            "legend": {
                "pct100": "План/Факт — задача в MSP закрыта на 100%",
                "pos": "Откл. ≥ 0 (в срок / опережение)",
                "neg": "Откл. < 0 (просрочка / недовыполнение)",
            },
            "kpis": kpis,
            "tremor": tremor,
            "matrix": matrix,
        }
        cache_set("developer-projects", cache_key, payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        return _empty_payload(error=str(exc))
