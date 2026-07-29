from __future__ import annotations

import re
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


def latest_web_files_by_project() -> list[Path]:
    """Return the newest msp_<project>_<dd-mm-yyyy>.csv export for each project."""
    if not WEB_DATA_DIR.is_dir():
        return []
    pattern = re.compile(r"^msp_(.+)_\d{2}-\d{2}-\d{4}\.csv$", re.IGNORECASE)
    newest: dict[str, Path] = {}
    for path in WEB_DATA_DIR.rglob("msp_*.csv"):
        if not path.is_file():
            continue
        match = pattern.match(path.name)
        if not match:
            continue
        slug = match.group(1).casefold()
        current = newest.get(slug)
        if current is None or path.stat().st_mtime > current.stat().st_mtime:
            newest[slug] = path
    return sorted(newest.values(), key=lambda path: path.name.casefold())
