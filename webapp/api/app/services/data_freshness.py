"""Актуальность активной версии данных + авто-синк при устаревании."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.config import (
    DATA_MODE,
    DATA_STALE_HOURS,
    ENSURE_FRESH_COOLDOWN_HOURS,
    ENSURE_FRESH_MARKER,
)
from app.services.ftp_ingest import run_ftp_then_db_ingest, sync_status
from app.services.jobs import list_jobs, start_job
from app.services.versions import list_versions

_MSK = ZoneInfo("Europe/Moscow")


def _parse_created_at(raw: str | None) -> float | None:
    s = (raw or "").strip()
    if not s:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S%z",
    ):
        try:
            dt = datetime.strptime(s.replace("Z", "+0000"), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_MSK)
            return dt.timestamp()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _human_age(hours: float | None) -> str:
    if hours is None:
        return "нет данных"
    if hours < 1:
        return f"{max(1, int(hours * 60))} мин"
    if hours < 48:
        return f"{hours:.1f} ч"
    return f"{hours / 24:.1f} сут"


def compute_freshness(*, now: float | None = None) -> dict[str, Any]:
    """Оценка свежести по активной версии (и mtime staging web/)."""
    now_ts = float(now if now is not None else time.time())
    status = sync_status()
    versions = list_versions()
    active_id = versions.get("active_version_id")
    created_at_raw = None
    for item in versions.get("items") or []:
        if int(item.get("id") or 0) == int(active_id or 0):
            created_at_raw = item.get("created_at")
            break

    version_ts = _parse_created_at(str(created_at_raw) if created_at_raw else None)
    latest_mtime = status.get("latest_mtime")
    try:
        file_ts = float(latest_mtime) if latest_mtime is not None else None
    except (TypeError, ValueError):
        file_ts = None

    # Для UI и stale — в первую очередь снимок БД (то, что видят дашборды).
    ref_ts = version_ts if version_ts is not None else file_ts
    age_hours = (now_ts - ref_ts) / 3600.0 if ref_ts is not None else None
    missing = active_id is None or ref_ts is None
    stale = missing or (age_hours is not None and age_hours > DATA_STALE_HOURS)

    label = "нет активной версии"
    if not missing and age_hours is not None:
        label = (
            f"устарели ({_human_age(age_hours)})"
            if stale
            else f"актуальны ({_human_age(age_hours)})"
        )

    msk_now = datetime.fromtimestamp(now_ts, tz=_MSK)
    return {
        "stale": bool(stale),
        "missing": bool(missing),
        "label": label,
        "age_hours": round(age_hours, 2) if age_hours is not None else None,
        "stale_after_hours": DATA_STALE_HOURS,
        "active_version_id": active_id,
        "active_version_created_at": created_at_raw,
        "ref_ts": ref_ts,
        "latest_file_mtime": file_ts,
        "data_mode": DATA_MODE,
        "checked_at": msk_now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "auto_sync_eligible": DATA_MODE == "ftp" and bool(status.get("ftp_configured")),
    }


def _cooldown_remaining_hours(now_ts: float) -> float:
    path = ENSURE_FRESH_MARKER
    if not path.is_file():
        return 0.0
    try:
        last = float(path.read_text(encoding="utf-8").strip().splitlines()[0])
    except (OSError, ValueError, IndexError):
        return 0.0
    elapsed_h = (now_ts - last) / 3600.0
    left = ENSURE_FRESH_COOLDOWN_HOURS - elapsed_h
    return max(0.0, left)


def _mark_ensure_attempt(now_ts: float) -> None:
    try:
        ENSURE_FRESH_MARKER.parent.mkdir(parents=True, exist_ok=True)
        ENSURE_FRESH_MARKER.write_text(
            f"{now_ts}\n{datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()}\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def _running_ftp_job() -> dict[str, Any] | None:
    for job in list_jobs(limit=30):
        if job.get("kind") not in ("ftp_ingest", "ftp_only", "ingest"):
            continue
        if job.get("status") in ("queued", "running"):
            return job
    return None


def ensure_fresh(*, force: bool = False, background: bool = True) -> dict[str, Any]:
    """
    Если данные stale и режим ftp — запускает FTP→БД (с cooldown).
    Иначе только возвращает статус свежести.
    """
    now_ts = time.time()
    freshness = compute_freshness(now=now_ts)
    out: dict[str, Any] = {
        "ok": True,
        "action": "none",
        "freshness": freshness,
        "status": sync_status(),
    }

    if not freshness.get("stale"):
        out["action"] = "fresh"
        return out

    if not freshness.get("auto_sync_eligible"):
        out["action"] = "skip_not_ftp"
        out["message"] = (
            "Данные устарели, но авто-синк только при WEBAPP_DATA_MODE=ftp "
            "и настроенных BI_FTP_*."
        )
        return out

    running = _running_ftp_job()
    if running:
        out["action"] = "already_running"
        out["job_id"] = running.get("id")
        out["message"] = f"Уже выполняется job {running.get('id')} ({running.get('status')})"
        return out

    cooldown_h = _cooldown_remaining_hours(now_ts)
    if cooldown_h > 0 and not force:
        out["action"] = "cooldown"
        out["cooldown_hours_left"] = round(cooldown_h, 2)
        out["message"] = (
            f"Данные устарели, но авто-синк на паузе ещё ~{cooldown_h:.1f} ч "
            f"(cooldown {ENSURE_FRESH_COOLDOWN_HOURS:g} ч)."
        )
        return out

    _mark_ensure_attempt(now_ts)
    if background:
        job_id = start_job("ftp_ingest", lambda: run_ftp_then_db_ingest(force=False))
        out["action"] = "started"
        out["async"] = True
        out["job_id"] = job_id
        out["message"] = "Запущено обновление FTP → БД"
        return out

    result = run_ftp_then_db_ingest(force=False)
    out["action"] = "synced"
    out["async"] = False
    out["result"] = result
    out["ok"] = bool(result.get("ok"))
    out["freshness"] = compute_freshness()
    out["status"] = sync_status()
    out["message"] = "Синхронизация завершена" if out["ok"] else "Синхронизация с ошибкой"
    return out


def attach_freshness(status: dict[str, Any]) -> dict[str, Any]:
    merged = dict(status)
    merged["freshness"] = compute_freshness()
    return merged
