from __future__ import annotations

import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.services import data_freshness as df

MSK = ZoneInfo("Europe/Moscow")


def test_parse_created_at_msk_naive():
    ts = df._parse_created_at("2026-08-06 11:00:00")
    assert ts is not None
    dt = datetime.fromtimestamp(ts, tz=MSK)
    assert dt.year == 2026 and dt.month == 8 and dt.day == 6


def test_compute_freshness_stale(monkeypatch):
    now = datetime(2026, 8, 7, 12, 0, tzinfo=MSK).timestamp()
    old = datetime(2026, 8, 5, 11, 0, tzinfo=MSK)

    monkeypatch.setattr(
        df,
        "sync_status",
        lambda: {
            "data_mode": "ftp",
            "web_dir": "/tmp",
            "files": 1,
            "latest_mtime": old.timestamp(),
            "ftp_configured": True,
            "db": {},
        },
    )
    monkeypatch.setattr(
        df,
        "list_versions",
        lambda: {
            "active_version_id": 7,
            "items": [
                {
                    "id": 7,
                    "created_at": old.strftime("%Y-%m-%d %H:%M:%S"),
                    "files_count": 10,
                    "rows_count": 100,
                    "is_active": True,
                }
            ],
        },
    )
    monkeypatch.setattr(df, "DATA_STALE_HOURS", 26.0)

    fr = df.compute_freshness(now=now)
    assert fr["stale"] is True
    assert fr["active_version_id"] == 7
    assert fr["age_hours"] and fr["age_hours"] > 26


def test_compute_freshness_fresh(monkeypatch):
    now_dt = datetime(2026, 8, 7, 12, 0, tzinfo=MSK)
    recent = now_dt - timedelta(hours=6)

    monkeypatch.setattr(
        df,
        "sync_status",
        lambda: {
            "data_mode": "ftp",
            "web_dir": "/tmp",
            "files": 1,
            "latest_mtime": recent.timestamp(),
            "ftp_configured": True,
            "db": {},
        },
    )
    monkeypatch.setattr(
        df,
        "list_versions",
        lambda: {
            "active_version_id": 8,
            "items": [
                {
                    "id": 8,
                    "created_at": recent.strftime("%Y-%m-%d %H:%M:%S"),
                    "files_count": 10,
                    "rows_count": 100,
                    "is_active": True,
                }
            ],
        },
    )
    monkeypatch.setattr(df, "DATA_STALE_HOURS", 26.0)

    fr = df.compute_freshness(now=now_dt.timestamp())
    assert fr["stale"] is False
    assert "актуальны" in fr["label"]


def test_ensure_fresh_cooldown(monkeypatch, tmp_path):
    marker = tmp_path / ".ensure_fresh_last"
    marker.write_text(str(time.time()), encoding="utf-8")
    monkeypatch.setattr(df, "ENSURE_FRESH_MARKER", marker)
    monkeypatch.setattr(df, "ENSURE_FRESH_COOLDOWN_HOURS", 4.0)
    monkeypatch.setattr(
        df,
        "compute_freshness",
        lambda now=None: {
            "stale": True,
            "auto_sync_eligible": True,
            "label": "устарели",
        },
    )
    monkeypatch.setattr(df, "sync_status", lambda: {"ok": True})
    monkeypatch.setattr(df, "_running_ftp_job", lambda: None)

    out = df.ensure_fresh(force=False, background=True)
    assert out["action"] == "cooldown"
    assert out["cooldown_hours_left"] > 0
