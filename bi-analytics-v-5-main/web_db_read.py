# -*- coding: utf-8 -*-
"""Чтение данных дашборда только из SQLite (web_data.db).

UI и AI-скрипты используют этот модуль вместо прямого доступа к web/ или FTP.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd

from web_schema import get_active_version_id, get_web_db_path


@dataclass(frozen=True)
class SourceRef:
    """Ссылка на файл-источник в БД (имя для парсинга даты снапшота)."""

    name: str

    @property
    def stem(self) -> str:
        return Path(self.name).stem


def web_db_mtime() -> float:
    try:
        return float(Path(get_web_db_path()).stat().st_mtime)
    except Exception:
        return 0.0


def resolve_version_id(version_id: Optional[int] = None) -> Optional[int]:
    if version_id is not None and int(version_id) > 0:
        return int(version_id)
    try:
        vid = get_active_version_id()
        return int(vid) if vid else None
    except Exception:
        return None


# Кеш распарсенных JSON-записей по (path, version_id, file_type, mtime БД).
# ГДРС и справочники дергают json_records_by_source на КАЖДЫЙ ререндер фрагмента
# (смена фильтра) — без кеша это полный скан web_data + json.loads тысяч строк
# каждый раз (задержки 10-20с). Инвалидируется при обновлении web_data.db.
_JSON_RECORDS_CACHE: dict[tuple[str, int, str, float], Dict[str, List[dict]]] = {}


def json_records_by_source(
    version_id: int,
    file_type: str,
    *,
    db_path: str | None = None,
) -> Dict[str, List[dict]]:
    """Сырые JSON-записи из web_data, сгруппированные по source_file (кешируется)."""
    path = db_path or get_web_db_path()
    _key = (str(path), int(version_id), str(file_type), web_db_mtime())
    _hit = _JSON_RECORDS_CACHE.get(_key)
    if _hit is not None:
        return _hit
    out: Dict[str, List[dict]] = {}
    try:
        conn = sqlite3.connect(path)
        rows = conn.execute(
            """
            SELECT source_file, row_data
            FROM web_data
            WHERE version_id = ? AND file_type = ?
            ORDER BY id ASC
            """,
            (int(version_id), str(file_type)),
        ).fetchall()
        conn.close()
    except Exception:
        return out
    for source_file, row_json in rows:
        key = str(source_file or "").strip()
        if not key:
            continue
        try:
            rec = json.loads(row_json)
        except Exception:
            continue
        if isinstance(rec, dict):
            out.setdefault(key, []).append(rec)
    # Ограничиваем рост кеша: держим только свежие срезы (разные file_type одной версии).
    if len(_JSON_RECORDS_CACHE) > 24:
        _JSON_RECORDS_CACHE.clear()
    _JSON_RECORDS_CACHE[_key] = out
    return out


def source_refs(version_id: int, file_type: str) -> List[SourceRef]:
    records = json_records_by_source(version_id, file_type)
    return [SourceRef(name=k) for k in sorted(records.keys())]


def load_version_dataframe(
    version_id: int,
    file_type: str,
    *,
    db_path: str | None = None,
) -> Optional[pd.DataFrame]:
    """DataFrame из web_data (как web_loader._load_version_data)."""
    from web_loader import _load_version_data

    return _load_version_data(int(version_id), str(file_type), web_db_mtime())


def load_gdrs_fact_long(version_id: int) -> pd.DataFrame:
    from dashboards.gdrs_resursi import gdrs_dedupe_fact_prefer_latest_source

    df = load_version_dataframe(version_id, "gdrs_fact")
    if df is None or df.empty:
        return pd.DataFrame(
            columns=[
                "project_id",
                "project_name",
                "contractor_id",
                "contractor_name",
                "vid_resursa",
                "date",
                "fact",
            ]
        )
    out = df.copy()
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
    return gdrs_dedupe_fact_prefer_latest_source(out)


def iter_json_records(
    version_id: int,
    file_type: str,
) -> Iterable[tuple[str, dict]]:
    for source, records in json_records_by_source(version_id, file_type).items():
        for rec in records:
            yield source, rec


def load_dogovor_lookup_from_db(version_id: Optional[int] = None) -> dict[str, dict]:
    """Q15/Q30: ID_Договора → поля договора из всех снимков Dogovor в версии БД."""
    vid = resolve_version_id(version_id)
    if not vid:
        return {}
    out: dict[str, dict] = {}
    for _src, records in json_records_by_source(vid, "dogovor_json").items():
        fdate = _source_file_date(_src)
        for r in records:
            guid = str(r.get("ID_Договора") or "").strip().lower()
            if not guid:
                continue
            num = str(
                r.get("Номер_Договора")
                or r.get("Номер_договора")
                or r.get("Номер")
                or ""
            ).strip()
            name = str(r.get("Наименование_Договора") or r.get("Наименование") or "").strip()
            contractor = str(
                r.get("Наименование_Контрагента") or r.get("Контрагент") or ""
            ).strip()
            summa = None
            for _sk in ("Сумма_Договора", "СуммаДоговора"):
                try:
                    summa_raw = r.get(_sk)
                    if summa_raw not in (None, "", "null"):
                        summa = float(summa_raw)
                        break
                except (TypeError, ValueError):
                    continue
            issue_id = str(
                r.get("Дата_Получения_ИД") or r.get("ДатаПолученияИД") or ""
            ).strip()
            date_start = str(
                r.get("Дата_Начала_Договора") or r.get("ДатаНачала") or ""
            ).strip()
            date_end = str(
                r.get("Дата_Окончания_Договора")
                or r.get("ДатаОкончанияДатаОкончания")
                or r.get("ДатаОкончания")
                or ""
            ).strip()
            project_name = str(r.get("Наименование_Проекта") or r.get("Проект") or "").strip()
            project_id = str(r.get("ID_Проекта") or "").strip()
            prev = out.get(guid)
            if prev is not None:
                prev_date = prev.get("__file_date")
                if fdate is not None and prev_date is not None and fdate < prev_date:
                    continue
            out[guid] = {
                "Номер_Договора": num,
                "Сумма_Договора": summa,
                "Наименование_Договора": name,
                "Наименование_Контрагента": contractor,
                "Дата_Получения_ИД": issue_id,
                "Дата_Начала_Договора": date_start,
                "Дата_Окончания_Договора": date_end,
                "Наименование_Проекта": project_name,
                "ID_Проекта": project_id,
                "__file_date": fdate,
            }
    for guid in list(out.keys()):
        out[guid].pop("__file_date", None)
    return out


_PROJECT_ID_NAME_CACHE: dict[tuple[int, float], dict[str, str]] = {}


def load_project_id_to_name_lookup(version_id: Optional[int] = None) -> dict[str, str]:
    vid = resolve_version_id(version_id)
    if not vid:
        return {}
    # Кеш по (версия, mtime БД): справочник дергается на каждую строку таблиц
    # (unified_project_display_label в .map по 6000+ строк) — без кеша это тысячи
    # запросов к SQLite за один рендер. Инвалидируется при обновлении web_data.db.
    _key = (int(vid), web_db_mtime())
    _hit = _PROJECT_ID_NAME_CACHE.get(_key)
    if _hit is not None:
        return _hit
    out: dict[str, str] = {}
    for _src, records in json_records_by_source(vid, "projekts_json").items():
        for row in records:
            pid = str(
                row.get("ID_Проекта")
                or row.get("id_проекта")
                or row.get("ID_Project")
                or ""
            ).strip().lower()
            pname = str(
                row.get("Наименование_Проекта")
                or row.get("Наименование проекта")
                or row.get("Наименование")
                or row.get("Проект")
                or ""
            ).strip()
            if pid and pname:
                out[pid] = pname
    if len(_PROJECT_ID_NAME_CACHE) > 4:
        _PROJECT_ID_NAME_CACHE.clear()
    _PROJECT_ID_NAME_CACHE[_key] = out
    return out


def _source_file_date(name: str) -> Optional[pd.Timestamp]:
    import re

    m = re.search(r"(\d{2})-(\d{2})-(\d{4})", str(name))
    if not m:
        return None
    dd, mm, yyyy = m.groups()
    try:
        return pd.Timestamp(year=int(yyyy), month=int(mm), day=int(dd))
    except ValueError:
        return None
