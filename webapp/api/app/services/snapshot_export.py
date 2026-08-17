"""Слепок данных дашборда: актуальные файлы web/ (MSP, other, 1С, TESSA) → tar.gz.

Раньше упаковывалась только одна календарная дата DD-MM-YYYY — в архив не попадали
msp_* и other_* с другими датами (в т.ч. DD.MM.YYYY у РД). Теперь тот же отбор, что
при ingest: web_loader.pick_latest_snapshot_files — latest per family/slug.
"""

from __future__ import annotations

import json
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import WEB_DATA_DIR, WEB_DB_PATH

_EXPORTS_DIR = WEB_DB_PATH.parent / "exports"
_LATEST_LINK = _EXPORTS_DIR / "latest_snapshot.tar.gz"
_LATEST_META = _EXPORTS_DIR / "latest_snapshot.json"


def _scan_web_file_dicts(web_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not web_dir.is_dir():
        return out
    for path in web_dir.rglob("*"):
        if not path.is_file():
            continue
        # служебное / мусор
        name = path.name
        if name.startswith(".") or name.endswith(".tmp"):
            continue
        out.append(
            {
                "name": name,
                "path": str(path.resolve()),
                "rel": path.relative_to(web_dir).as_posix(),
            }
        )
    return out


def _pick_dashboard_files(web_dir: Path | None = None) -> tuple[list[Path], list[str], str | None]:
    """Файлы для слепка + предупреждения + метка «свежести» (max дата в именах)."""
    root = web_dir or WEB_DATA_DIR
    scanned = _scan_web_file_dicts(root)
    if not scanned:
        return [], ["web/ пуст или недоступен"], None

    from app.services.core_bridge import prepare_web_db

    prepare_web_db()
    from web_loader import pick_latest_snapshot_files, _max_date_in_stem  # type: ignore

    picked, warns = pick_latest_snapshot_files(scanned)
    paths: list[Path] = []
    for item in picked:
        p = Path(str(item.get("path") or ""))
        if p.is_file():
            paths.append(p)
    paths = sorted(paths, key=lambda p: str(p.relative_to(root)).casefold())

    best_label: str | None = None
    best_key: tuple[int, int, int] | None = None
    for p in paths:
        md = _max_date_in_stem(p.stem)
        if md is None:
            continue
        key = (md.year, md.month, md.day)
        label = md.strftime("%d-%m-%Y")
        if best_key is None or key > best_key:
            best_key = key
            best_label = label

    return paths, list(warns or []), best_label


def _classify_counts(files: list[Path]) -> dict[str, int]:
    counts = {
        "msp": 0,
        "other_resursi": 0,
        "other_rd": 0,
        "other_pd": 0,
        "one_c": 0,
        "tessa": 0,
        "other": 0,
    }
    for p in files:
        nl = p.name.lower()
        stem = p.stem.lower()
        if stem.startswith("msp_") or stem.startswith("msp-"):
            counts["msp"] += 1
        elif "resursi" in nl or "resursy" in nl:
            counts["other_resursi"] += 1
        elif nl.startswith("other_") and ("_rd" in nl or nl.endswith("rd.csv")):
            counts["other_rd"] += 1
        elif nl.startswith("other_") and ("_pd" in nl or nl.endswith("pd.csv")):
            counts["other_pd"] += 1
        elif nl.endswith(".json") and stem[:3] in ("1с_", "1c_", "lc_", "лк_", "lk_"):
            counts["one_c"] += 1
        elif nl.startswith("tessa_"):
            counts["tessa"] += 1
        else:
            counts["other"] += 1
    return counts


def latest_snapshot_date(web_dir: Path | None = None) -> str | None:
    """Обратная совместимость: самая свежая дата среди файлов слепка дашборда."""
    _files, _warns, label = _pick_dashboard_files(web_dir)
    return label


def list_snapshot_files(date_label: str | None = None, web_dir: Path | None = None) -> list[Path]:
    """Актуальный портфель файлов дашборда (MSP/other/1С/TESSA), не «одна дата»."""
    files, _warns, _label = _pick_dashboard_files(web_dir)
    if date_label:
        # опционально сузить (редко нужно); по умолчанию игнор
        narrowed = [p for p in files if date_label in p.name or date_label.replace("-", ".") in p.name]
        if narrowed:
            return narrowed
    return files


def snapshot_info() -> dict[str, Any]:
    files, warns, date_label = _pick_dashboard_files()
    archive = _LATEST_LINK if _LATEST_LINK.is_file() else None
    meta: dict[str, Any] = {}
    if _LATEST_META.is_file():
        try:
            meta = json.loads(_LATEST_META.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    counts = _classify_counts(files)
    return {
        "ok": True,
        "web_dir": str(WEB_DATA_DIR),
        "snapshot_date": date_label,
        "files_count": len(files),
        "files": [str(p.relative_to(WEB_DATA_DIR)) for p in files[:120]],
        "family_counts": counts,
        "warns": warns[:12],
        "archive_ready": bool(archive),
        "archive_name": meta.get("archive_name")
        or (archive.name if archive else None),
        "archive_size_bytes": archive.stat().st_size if archive else None,
        "archive_built_at": meta.get("built_at"),
        "archive_snapshot_date": meta.get("snapshot_date"),
        "mode": "dashboard_latest_per_family",
    }


def build_latest_snapshot_archive(*, force: bool = True) -> dict[str, Any]:
    """Упаковать актуальный портфель web/ (как при ingest) в tar.gz."""
    files, warns, date_label = _pick_dashboard_files()
    if not files:
        return {
            "ok": False,
            "error": "В web/ нет файлов для слепка дашборда (MSP/other/1С/TESSA)",
            "web_dir": str(WEB_DATA_DIR),
            "warns": warns,
        }

    stamp = date_label or datetime.now().strftime("%d-%m-%Y")
    _EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    archive_name = f"showcase_ftp_snapshot_{stamp}.tar.gz"
    archive_path = _EXPORTS_DIR / archive_name
    counts = _classify_counts(files)

    if (
        not force
        and archive_path.is_file()
        and _LATEST_LINK.is_file()
        and _LATEST_META.is_file()
    ):
        try:
            meta = json.loads(_LATEST_META.read_text(encoding="utf-8"))
            if (
                meta.get("snapshot_date") == stamp
                and meta.get("files_count") == len(files)
                and meta.get("mode") == "dashboard_latest_per_family"
            ):
                return {
                    "ok": True,
                    "reused": True,
                    "snapshot_date": stamp,
                    "files_count": len(files),
                    "family_counts": counts,
                    "archive_name": archive_name,
                    "archive_path": str(archive_path),
                    "archive_size_bytes": archive_path.stat().st_size,
                    "mode": "dashboard_latest_per_family",
                }
        except Exception:
            pass

    for old in _EXPORTS_DIR.glob("showcase_ftp_snapshot_*.tar.gz"):
        try:
            old.unlink()
        except OSError:
            pass

    with tarfile.open(archive_path, "w:gz") as tar:
        for path in files:
            arcname = path.relative_to(WEB_DATA_DIR).as_posix()
            tar.add(path, arcname=arcname)

    tmp_link = _EXPORTS_DIR / "latest_snapshot.tar.gz.tmp"
    tmp_link.write_bytes(archive_path.read_bytes())
    tmp_link.replace(_LATEST_LINK)

    built_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta = {
        "snapshot_date": stamp,
        "archive_name": archive_name,
        "files_count": len(files),
        "family_counts": counts,
        "built_at": built_at,
        "size_bytes": archive_path.stat().st_size,
        "mode": "dashboard_latest_per_family",
        "warns": warns[:20],
    }
    _LATEST_META.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return {
        "ok": True,
        "reused": False,
        "snapshot_date": stamp,
        "files_count": len(files),
        "family_counts": counts,
        "files": [str(p.relative_to(WEB_DATA_DIR)) for p in files],
        "archive_name": archive_name,
        "archive_path": str(archive_path),
        "archive_size_bytes": archive_path.stat().st_size,
        "built_at": built_at,
        "mode": "dashboard_latest_per_family",
        "warns": warns[:20],
    }


def latest_archive_path() -> Path | None:
    if _LATEST_LINK.is_file():
        return _LATEST_LINK
    return None
