from __future__ import annotations

from pathlib import Path

from app.config import WEB_DATA_DIR


def latest_web_file(suffix: str) -> Path | None:
    """Find newest showcase_data/web file ending with suffix (e.g. _DK.json)."""
    if not WEB_DATA_DIR.is_dir():
        return None
    matches = [
        p
        for p in WEB_DATA_DIR.iterdir()
        if p.is_file() and p.name.endswith(suffix)
    ]
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)
