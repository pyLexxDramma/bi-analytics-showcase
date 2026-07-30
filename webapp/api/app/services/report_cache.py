"""Disk-кэш payload’ов отчётов (после ingest). Redis — следующий шаг."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from app.config import REPORT_CACHE_DIR


def _key_path(report_id: str, cache_key: str) -> Path:
    digest = hashlib.sha256(f"{report_id}:{cache_key}".encode("utf-8")).hexdigest()[:40]
    return REPORT_CACHE_DIR / report_id / f"{digest}.json"


def cache_get(report_id: str, cache_key: str, *, max_age_sec: float | None = None) -> dict[str, Any] | None:
    path = _key_path(report_id, cache_key)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if max_age_sec is not None:
        ts = float(raw.get("_cached_at") or 0)
        if ts <= 0 or (time.time() - ts) > max_age_sec:
            return None
    payload = raw.get("payload")
    return payload if isinstance(payload, dict) else None


def cache_set(report_id: str, cache_key: str, payload: dict[str, Any]) -> Path:
    path = _key_path(report_id, cache_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"_cached_at": time.time(), "report_id": report_id, "cache_key": cache_key, "payload": payload}
    path.write_text(json.dumps(body, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def cache_clear(report_id: str | None = None) -> int:
    root = REPORT_CACHE_DIR
    if not root.is_dir():
        return 0
    removed = 0
    targets = [root / report_id] if report_id else [root]
    for base in targets:
        if not base.exists():
            continue
        for path in base.rglob("*.json"):
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    return removed
