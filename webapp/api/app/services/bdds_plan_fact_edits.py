from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from app.config import REPORT_CACHE_DIR

EDITS_DIR = Path(
    os.environ.get(
        "WEBAPP_Bdds_PLAN_FACT_EDITS_DIR",
        str(REPORT_CACHE_DIR.parent / "bdds_plan_fact_edits"),
    )
)

_lock = threading.Lock()
_cache: dict[str, dict[str, Any]] = {}
_MAX_AGE_SEC = 7 * 24 * 3600
_MAX_FILES = 200


def _edit_path(store_key: str) -> Path:
    safe = store_key.replace("|", "__").replace("/", "_")[:180]
    return EDITS_DIR / f"{safe}.json"


def _read(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write(store_key: str, payload: dict[str, Any]) -> None:
    try:
        EDITS_DIR.mkdir(parents=True, exist_ok=True)
        target = _edit_path(store_key)
        fd, tmp = tempfile.mkstemp(dir=str(EDITS_DIR), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, default=str)
        os.replace(tmp, target)
    except OSError:
        pass


def _prune() -> None:
    if not EDITS_DIR.is_dir():
        return
    try:
        files = sorted(
            EDITS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )
    except OSError:
        return
    now = time.time()
    for index, path in enumerate(files):
        try:
            too_old = (now - path.stat().st_mtime) > _MAX_AGE_SEC
            if too_old or index >= _MAX_FILES:
                path.unlink()
        except OSError:
            pass


def store_key(username: str, project_norm: str) -> str:
    user = (username or "anonymous").strip().casefold() or "anonymous"
    proj = (project_norm or "").strip() or "__none__"
    return f"{user}|{proj}"


def get_saved_rows(username: str, project_norm: str) -> list[dict[str, Any]] | None:
    key = store_key(username, project_norm)
    with _lock:
        cached = _cache.get(key)
        if cached and isinstance(cached.get("rows"), list):
            return list(cached["rows"])
    data = _read(_edit_path(key))
    if not data or not isinstance(data.get("rows"), list):
        return None
    with _lock:
        _cache[key] = data
    return list(data["rows"])


def save_rows(
    username: str,
    project_norm: str,
    *,
    project_label: str,
    rows: list[dict[str, Any]],
    src_sig: tuple[int, float, float] | None = None,
) -> None:
    key = store_key(username, project_norm)
    payload: dict[str, Any] = {
        "username": username,
        "project_norm": project_norm,
        "project_label": project_label,
        "rows": rows,
        "updated_at": time.time(),
        "src_sig": list(src_sig) if src_sig else None,
    }
    with _lock:
        _cache[key] = payload
    _write(key, payload)
    _prune()


def clear_rows(username: str, project_norm: str) -> None:
    key = store_key(username, project_norm)
    with _lock:
        _cache.pop(key, None)
    try:
        path = _edit_path(key)
        if path.is_file():
            path.unlink()
    except OSError:
        pass
