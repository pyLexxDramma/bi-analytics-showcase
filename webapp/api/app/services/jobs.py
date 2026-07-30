"""Фоновые jobs: FTP/ingest вне HTTP-воркера (анти-502 на слабом VPS)."""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Callable

_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}


def get_job(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def list_jobs(limit: int = 20) -> list[dict[str, Any]]:
    with _lock:
        items = sorted(_jobs.values(), key=lambda j: float(j.get("created_at") or 0), reverse=True)
        return [dict(j) for j in items[:limit]]


def start_job(kind: str, fn: Callable[[], dict[str, Any]]) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = {
            "id": job_id,
            "kind": kind,
            "status": "queued",
            "created_at": time.time(),
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
        }

    def _run() -> None:
        with _lock:
            job = _jobs.get(job_id)
            if not job:
                return
            job["status"] = "running"
            job["started_at"] = time.time()
        try:
            result = fn()
            with _lock:
                job = _jobs[job_id]
                job["status"] = "ok" if result.get("ok", True) else "error"
                job["result"] = result
                job["finished_at"] = time.time()
                if not result.get("ok", True):
                    errs = result.get("errors") or []
                    job["error"] = "; ".join(str(e) for e in errs[:5]) if errs else "failed"
        except Exception as exc:  # noqa: BLE001
            with _lock:
                job = _jobs[job_id]
                job["status"] = "error"
                job["error"] = str(exc)
                job["finished_at"] = time.time()

    threading.Thread(target=_run, name=f"webapp-job-{kind}-{job_id}", daemon=True).start()
    return job_id
