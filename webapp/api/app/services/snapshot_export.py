"""Свежий слепок FTP: файлы самой новой даты DD-MM-YYYY из web/ → tar.gz."""

from __future__ import annotations

import re
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import WEB_DATA_DIR, WEB_DB_PATH

_DATE_RE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")
# Рядом с БД на томе /data/db — переживает перезапуск контейнера
_EXPORTS_DIR = WEB_DB_PATH.parent / "exports"
_LATEST_LINK = _EXPORTS_DIR / "latest_snapshot.tar.gz"
_LATEST_META = _EXPORTS_DIR / "latest_snapshot.json"


def _parse_date_key(label: str) -> tuple[int, int, int] | None:
    m = _DATE_RE.fullmatch(label)
    if not m:
        return None
    day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        datetime(year, month, day)
    except ValueError:
        return None
    return year, month, day


def latest_snapshot_date(web_dir: Path | None = None) -> str | None:
    root = web_dir or WEB_DATA_DIR
    if not root.is_dir():
        return None
    best: tuple[int, int, int] | None = None
    best_label: str | None = None
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        for match in _DATE_RE.finditer(path.name):
            label = match.group(0)
            key = _parse_date_key(label)
            if key is None:
                continue
            if best is None or key > best:
                best = key
                best_label = label
    return best_label


def list_snapshot_files(date_label: str, web_dir: Path | None = None) -> list[Path]:
    root = web_dir or WEB_DATA_DIR
    if not root.is_dir():
        return []
    needle = date_label
    out: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and needle in path.name:
            out.append(path)
    return sorted(out, key=lambda p: str(p.relative_to(root)).casefold())


def snapshot_info() -> dict[str, Any]:
    date_label = latest_snapshot_date()
    files = list_snapshot_files(date_label) if date_label else []
    archive = _LATEST_LINK if _LATEST_LINK.is_file() else None
    meta: dict[str, Any] = {}
    if _LATEST_META.is_file():
        try:
            import json

            meta = json.loads(_LATEST_META.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    return {
        "ok": True,
        "web_dir": str(WEB_DATA_DIR),
        "snapshot_date": date_label,
        "files_count": len(files),
        "files": [str(p.relative_to(WEB_DATA_DIR)) for p in files[:80]],
        "archive_ready": bool(archive),
        "archive_name": meta.get("archive_name")
        or (archive.name if archive else None),
        "archive_size_bytes": archive.stat().st_size if archive else None,
        "archive_built_at": meta.get("built_at"),
        "archive_snapshot_date": meta.get("snapshot_date"),
    }


def build_latest_snapshot_archive(*, force: bool = True) -> dict[str, Any]:
    """Упаковать файлы свежей даты в data/exports и обновить latest_snapshot.tar.gz."""
    date_label = latest_snapshot_date()
    if not date_label:
        return {
            "ok": False,
            "error": "В web/ нет файлов с датой DD-MM-YYYY",
            "web_dir": str(WEB_DATA_DIR),
        }
    files = list_snapshot_files(date_label)
    if not files:
        return {
            "ok": False,
            "error": f"Нет файлов за дату {date_label}",
            "snapshot_date": date_label,
        }

    _EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    archive_name = f"showcase_ftp_snapshot_{date_label}.tar.gz"
    archive_path = _EXPORTS_DIR / archive_name

    if (
        not force
        and archive_path.is_file()
        and _LATEST_LINK.is_file()
        and _LATEST_META.is_file()
    ):
        try:
            import json

            meta = json.loads(_LATEST_META.read_text(encoding="utf-8"))
            if meta.get("snapshot_date") == date_label:
                return {
                    "ok": True,
                    "reused": True,
                    "snapshot_date": date_label,
                    "files_count": len(files),
                    "archive_name": archive_name,
                    "archive_path": str(archive_path),
                    "archive_size_bytes": archive_path.stat().st_size,
                }
        except Exception:
            pass

    # старые именные архивы не копятся
    for old in _EXPORTS_DIR.glob("showcase_ftp_snapshot_*.tar.gz"):
        try:
            old.unlink()
        except OSError:
            pass

    with tarfile.open(archive_path, "w:gz") as tar:
        for path in files:
            arcname = path.relative_to(WEB_DATA_DIR).as_posix()
            tar.add(path, arcname=arcname)

    # атомарно обновляем «latest»
    tmp_link = _EXPORTS_DIR / "latest_snapshot.tar.gz.tmp"
    tmp_link.write_bytes(archive_path.read_bytes())
    tmp_link.replace(_LATEST_LINK)

    built_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta = {
        "snapshot_date": date_label,
        "archive_name": archive_name,
        "files_count": len(files),
        "built_at": built_at,
        "size_bytes": archive_path.stat().st_size,
    }
    import json

    _LATEST_META.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return {
        "ok": True,
        "reused": False,
        "snapshot_date": date_label,
        "files_count": len(files),
        "files": [str(p.relative_to(WEB_DATA_DIR)) for p in files],
        "archive_name": archive_name,
        "archive_path": str(archive_path),
        "archive_size_bytes": archive_path.stat().st_size,
        "built_at": built_at,
    }


def latest_archive_path() -> Path | None:
    if _LATEST_LINK.is_file():
        return _LATEST_LINK
    return None
