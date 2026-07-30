"""Фоновые jobs: FTP/ingest вне HTTP-воркера (анти-502 на слабом VPS).

Состояние дублируется на диск: при нескольких uvicorn-воркерах POST и последующий
GET /api/admin/jobs/{id} попадают в разные процессы, и памяти одного процесса мало.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from app.config import JOBS_DIR

_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}

_MAX_AGE_SEC = 24 * 3600
_MAX_FILES = 50


def _job_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def _write(job: dict[str, Any]) -> None:
    try:
        JOBS_DIR.mkdir(parents=True, exist_ok=True)
        target = _job_path(str(job.get("id")))
        fd, tmp = tempfile.mkstemp(dir=str(JOBS_DIR), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(job, handle, ensure_ascii=False, default=str)
        os.replace(tmp, target)
    except OSError:
        pass  # диск недоступен — остаётся in-memory режим


def _read(job_id: str) -> dict[str, Any] | None:
    path = _job_path(job_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _prune() -> None:
    if not JOBS_DIR.is_dir():
        return
    try:
        files = sorted(JOBS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
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


def _touch(job_id: str, **changes: Any) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id) or _read(job_id)
        if not job:
            return None
        job.update(changes)
        _jobs[job_id] = job
        snapshot = dict(job)
    _write(snapshot)
    return snapshot


def get_job(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        if job:
            return dict(job)
    return _read(job_id)


def list_jobs(limit: int = 20) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    if JOBS_DIR.is_dir():
        try:
            for path in JOBS_DIR.glob("*.json"):
                data = _read(path.stem)
                if data and data.get("id"):
                    merged[str(data["id"])] = data
        except OSError:
            pass
    with _lock:
        for job_id, job in _jobs.items():
            merged[job_id] = dict(job)
    items = sorted(
        merged.values(), key=lambda j: float(j.get("created_at") or 0), reverse=True
    )
    return items[:limit]


def start_job(kind: str, fn: Callable[[], dict[str, Any]]) -> str:
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "kind": kind,
        "status": "queued",
        "created_at": time.time(),
        "started_at": None,
        "finished_at": None,
        "result": None,
        "error": None,
        "pid": os.getpid(),
    }
    with _lock:
        _jobs[job_id] = job
        snapshot = dict(job)
    _write(snapshot)
    _prune()

    def _run() -> None:
        _touch(job_id, status="running", started_at=time.time())
        try:
            result = fn()
            ok = bool(result.get("ok", True))
            errors = result.get("errors") or []
            _touch(
                job_id,
                status="ok" if ok else "error",
                result=result,
                finished_at=time.time(),
                error=None if ok else ("; ".join(str(e) for e in errors[:5]) or "failed"),
            )
        except Exception as exc:  # noqa: BLE001
            _touch(job_id, status="error", error=str(exc), finished_at=time.time())

    threading.Thread(target=_run, name=f"webapp-job-{kind}-{job_id}", daemon=True).start()
    return job_id
