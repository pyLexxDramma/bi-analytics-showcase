"""
web_loader.py — парсинг файлов из папки web/ и сохранение в SQLite (data/web_data.db).

Основная функция: load_all_from_web()
- Сканирует локальный web/, при наличии — каталог «Analitics/web» (см. config.get_analytics_sibling_web_dir),
  и дополнительные пути из BI_ANALYTICS_WEB_EXTRA_PATHS
- По умолчанию оставляет только последний снимок по дате в имени (1С/TESSA/MSP и др.); отключение:
  BI_ANALYTICS_WEB_LATEST_ONLY=0 (см. config.web_load_latest_snapshots_only).
- Сканирует web/ рекурсивно
- Определяет тип файла через ETL-парсер (etl/parser.py)
- Для MSP-файлов применяет маппинг колонок → формат дашбордов
- Для файлов ресурсов использует специальный загрузчик с 3-строчным заголовком
- Сохраняет строки в web_data с привязкой к версии
- Раскладывает данные в session_state для дашбордов

Чтение из БД: read_version_to_session(version_id)
- Загружает данные нужной версии из SQLite в session_state
"""
import csv
import io
import json
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import ignore_demo_data_files, web_load_latest_snapshots_only

import pandas as pd
import streamlit as st

from utils import norm_partner_join_key, ensure_msp_hierarchy_columns

from web_schema import (
    get_web_db_path,
    get_active_version_id,
    activate_version,
)


# ── Маппинг MSP-колонок → формат дашбордов ──────────────────────────────────

# MSP экспортирует файлы с русскими названиями колонок (Windows-1251).
# Дашборды ожидают английские canonical-имена из data_loader.column_mapping.
def _looks_like_msp_spurious_project_label(val: Any) -> bool:
    """
    Значение похоже на построчный штамп/UID выгрузки MSP, а не на человекочитаемое имя проекта.
    """
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return False
    s = str(val).replace("\xa0", "").strip()
    if len(s) < 14:
        return False
    if re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}", s):
        return True
    # 24-04-2024-15-41-47 / цепочки сегментов дата-время
    if re.match(r"^\d{2}-\d{2}-\d{4}-\d{2}-\d{2}-\d{2}", s):
        return True
    parts = re.split(r"[-_\s]+", s)
    if len(parts) >= 5:
        digit_segments = sum(1 for p in parts if p.isdigit())
        if digit_segments >= 4 and sum(c.isdigit() for c in s) >= 12:
            return True
    return False


def _coerce_msp_project_name_from_file_if_needed(
    df: pd.DataFrame, ru_from_file: str
) -> pd.DataFrame:
    """
    Если колонка project name заполнена «мусорными» построчными метками, заменяем на имя из файла.
    Один файл MSP у нас соответствует одному проекту (префикс msp_<slug>_…).
    """
    if (
        df is None
        or getattr(df, "empty", True)
        or not (ru_from_file or "").strip()
        or "project name" not in df.columns
    ):
        return df
    ser = df["project name"]
    cleaned = ser.dropna().astype(str).map(lambda x: str(x).strip())
    cleaned = cleaned[cleaned.str.len() > 0]
    cleaned = cleaned[~cleaned.str.lower().isin(("nan", "none", "<na>"))]
    if cleaned.empty:
        return df
    nuniq = int(cleaned.nunique())
    sample = cleaned.head(min(400, len(cleaned)))
    spurious_frac = float(sample.map(_looks_like_msp_spurious_project_label).mean())
    too_many_distinct = nuniq >= 10
    mostly_stamps = nuniq >= 4 and spurious_frac >= 0.35
    if not (too_many_distinct or mostly_stamps):
        return df
    out = df.copy()
    out["project name"] = ru_from_file.strip()
    return out


_MSP_COLUMN_REMAP: Dict[str, str] = {
    "Название задачи":       "task name",
    "Название":              "task name",
    "Начало":                "plan start",
    "Окончание":             "plan end",
    "Базовое_начало":        "base start",
    "Базовое_окончание":     "base end",
    "Причины_отклонений":    "reason of deviation",
    "БЛОК":                  "block",
    # Лот — отдельная колонка; «section» заполняется из иерархии (родитель ур. 2) в _postprocess_msp_df
    "ЛОТ":                   "lot",
    "Уровень_структуры":     "level structure",
    "Процент_завершения":    "pct complete",
    "Отклонение_окончания":  "deviation in days",
    "Отклонение_начала":     "deviation start days",
    "Шифр_ПД_и_РД":          "abbreviation",
    "ID_проекта":            "project id",
    "Уровень":               "level",
    "Тип":                   "task type",
    "Заметки":               "notes",
    "Базовая_длительность":  "base duration",
    "Длительность":          "duration",
    "Режим_задачи":          "task mode",
    "Календарь_задачи":      "calendar",
    "Предшественники":       "predecessors",
    "Последователи":         "successors",
    "Дата_ограничения":      "constraint date",
    "Уникальный_идентификатор": "unique id",
    "Ид":                    "task id seq",
    # Варианты с пробелами (экспорт MSP / Excel)
    "Базовое начало":       "base start",
    "Базовое окончание":    "base end",
    "План начало":          "plan start",
    "План окончание":       "plan end",
    # Фактическое окончание (если есть в экспорте MSP) — приоритетное «Факт» для дат окончания задачи
    "Фактическое_окончание": "actual finish",
    "Фактическое окончание": "actual finish",
}


def _parse_snapshot_date(date_str: str):
    """
    Парсит дату снимка из имени файла.
    '30-03-2026' или '30.03.2026' → datetime.date(2026, 3, 30)
    Возвращает None при ошибке.
    """
    if not date_str:
        return None
    from datetime import datetime as _dt
    for fmt in ("%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return _dt.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _msp_source_project_bucket(source_file: Any) -> Optional[str]:
    """Корень проекта из имени msp_<slug>_<date>.csv (независимо от регистра/подписи)."""
    if source_file is None or (isinstance(source_file, float) and pd.isna(source_file)):
        return None
    stem = Path(str(source_file).replace("\\", "/").split("/")[-1]).stem
    return _msp_project_bucket(stem)


def _snapshot_rows_per_key_date(part: pd.DataFrame, key_col: str) -> pd.Series:
    """Число строк на пару (ключ проекта, snapshot_date)."""
    return part.groupby([key_col, "snapshot_date"], dropna=False).size()


def _keep_latest_substantial_snapshot(part: pd.DataFrame, key_col: str) -> pd.DataFrame:
    """
    На ключ — один снимок: самый свежий среди «полных».

    Если более новый файл сильно урезан (типично budget/partial MSP),
    брать абсолютный max(snapshot_date) выкидывает ЗОС/КТ. Порог:
    строк >= 50% от максимального снимка этого ключа.
    """
    if part is None or part.empty:
        return part
    counts = _snapshot_rows_per_key_date(part, key_col)
    n_map = part.set_index([key_col, "snapshot_date"]).index.map(counts)
    n = pd.Series(n_map, index=part.index, dtype="float64")
    max_n = part.assign(_n=n).groupby(key_col, dropna=False)["_n"].transform("max")
    thresh = (max_n * 0.5).clip(lower=1.0)
    eligible = part.loc[n >= thresh]
    if eligible.empty:
        eligible = part
    chosen = eligible.groupby(key_col, dropna=False)["snapshot_date"].max()
    keep = part[key_col].map(chosen) == part["snapshot_date"]
    return part.loc[keep].copy()


def _deduplicate_project_snapshots(df: pd.DataFrame) -> pd.DataFrame:
    """
    Для проектных данных из MSP: оставляет один снимок на проект.

    Группировка: сначала bucket из ``__source_file`` / ``source_file``
    (msp_zhukovsky1_…), иначе точный ``project name``. Так июньский и июльский
    файлы одного slug не остаются рядом из‑за разных подписей проекта
    («zhukovsky1» vs «Жуковский») — иначе матрица Девелоперских смешивает
    снимки и отклонения обнуляются (у старых выгрузок base end == plan end).

    Строки без snapshot_date оставляет нетронутыми.

    Дополнительно:
    - среди дат снимка берём самый свежий *полный* (≥50% max строк ключа),
      чтобы урезанный поздний файл не затирал ЗОС/КТ;
    - строки без MSP-bucket (budget и т.п.) не затирают MSP: остаются только
      для проектов, которых нет в выбранных MSP-снимках.
    """
    if df is None or df.empty:
        return df
    if "snapshot_date" not in df.columns:
        return df

    df = df.copy()
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"], errors="coerce")

    # Строки без snapshot_date — оставляем как есть
    has_snap = df["snapshot_date"].notna()
    if not has_snap.any():
        return df

    snap_part = df[has_snap].copy()
    no_snap_part = df[~has_snap].copy()

    src_col = next(
        (c for c in ("__source_file", "source_file", "_source_file") if c in snap_part.columns),
        None,
    )
    if src_col is not None:
        msp_bucket = snap_part[src_col].map(_msp_source_project_bucket)
    else:
        msp_bucket = pd.Series([None] * len(snap_part), index=snap_part.index, dtype=object)

    has_msp = msp_bucket.notna() & (msp_bucket.astype(str).str.strip() != "")
    msp_part = snap_part.loc[has_msp].copy()
    other_part = snap_part.loc[~has_msp].copy()

    kept_parts: list[pd.DataFrame] = []
    if not msp_part.empty:
        msp_part = msp_part.copy()
        msp_part["_snap_proj_key"] = msp_bucket.loc[msp_part.index].astype(str)
        msp_kept = _keep_latest_substantial_snapshot(msp_part, "_snap_proj_key")
        msp_kept = msp_kept.drop(columns=["_snap_proj_key"], errors="ignore")
        kept_parts.append(msp_kept)
    else:
        msp_kept = msp_part

    msp_project_names: set[str] = set()
    if (
        not msp_kept.empty
        and "project name" in msp_kept.columns
    ):
        msp_project_names = {
            str(x).strip()
            for x in msp_kept["project name"].dropna().unique()
            if str(x).strip() and str(x).strip().lower() not in ("nan", "none", "nat")
        }

    if not other_part.empty:
        if "project name" in other_part.columns:
            _pn = other_part["project name"].map(
                lambda x: (
                    str(x).strip()
                    if x is not None
                    and not (isinstance(x, float) and pd.isna(x))
                    and str(x).strip()
                    else None
                )
            )
            other_part = other_part.copy()
            other_part["_snap_proj_key"] = _pn.fillna("__all__").astype(str)
            other_kept = _keep_latest_substantial_snapshot(other_part, "_snap_proj_key")
            other_kept = other_kept.drop(columns=["_snap_proj_key"], errors="ignore")
            if msp_project_names and "project name" in other_kept.columns:
                _names = other_kept["project name"].map(
                    lambda x: str(x).strip() if x is not None and not (isinstance(x, float) and pd.isna(x)) else ""
                )
                other_kept = other_kept.loc[~_names.isin(msp_project_names)].copy()
            if not other_kept.empty:
                kept_parts.append(other_kept)
        else:
            kept_parts.append(other_part)

    snap_kept = (
        pd.concat(kept_parts, ignore_index=True) if kept_parts else snap_part.iloc[0:0].copy()
    )
    result = pd.concat([no_snap_part, snap_kept], ignore_index=True)
    return result


def _deduplicate_project_snapshots_last_per_month(df: pd.DataFrame) -> pd.DataFrame:
    """
    Для MSP: последний снимок каждого проекта в каждом календарном месяце
    выгрузки (по snapshot_date). Нужен для динамики отклонений по plan end.
    Колонка snapshot_upload_month — месяц выгрузки файла на FTP.
    """
    if df is None or df.empty:
        return df
    if "snapshot_date" not in df.columns:
        return df

    df = df.copy()
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"], errors="coerce")

    has_snap = df["snapshot_date"].notna()
    if "project name" in df.columns:
        has_snap = has_snap & df["project name"].notna()

    if not has_snap.any():
        return df

    snap_part = df[has_snap].copy()
    no_snap_part = df[~has_snap].copy()

    snap_part["_upload_month"] = snap_part["snapshot_date"].dt.to_period("M")
    latest = snap_part.groupby(
        ["project name", "_upload_month"], observed=False
    )["snapshot_date"].transform("max")
    snap_part = snap_part[snap_part["snapshot_date"] == latest].copy()
    snap_part["snapshot_upload_month"] = snap_part["_upload_month"]
    snap_part = snap_part.drop(columns=["_upload_month"], errors="ignore")

    return pd.concat([no_snap_part, snap_part], ignore_index=True)


def _fill_section_from_task_tree(df: pd.DataFrame) -> pd.DataFrame:
    """
    Заполняет колонку section именем родительской задачи уровня 2 (для маппинга «Ковенанты»).
    Раньше колонка «ЛОТ» попадала в section — иерархия не считалась; при чтении из БД пересчитываем.
    Для каждого проекта обход в порядке строк в выгрузке (как в MSP).

    В MSP CSV «Уровень» и «Уровень_структуры» часто различаются; иерархия дерева — по outline
    (после ремапа: level structure), иначе родитель ур.2 и ветки «Ковенанты» считаются неверно.
    """
    if df is None or df.empty or "task name" not in df.columns:
        return df
    if "level" not in df.columns and "level structure" not in df.columns:
        return df
    df = df.copy()
    if "level" in df.columns:
        df["level"] = pd.to_numeric(df["level"], errors="coerce")
    if "level structure" in df.columns:
        df["level structure"] = pd.to_numeric(df["level structure"], errors="coerce")
    if "section" not in df.columns:
        df["section"] = ""

    def _outline_col(g: pd.DataFrame) -> Optional[str]:
        if "level structure" in g.columns and pd.to_numeric(g["level structure"], errors="coerce").notna().any():
            return "level structure"
        if "level" in g.columns:
            return "level"
        return None

    def _walk_one(g: pd.DataFrame) -> pd.DataFrame:
        g = g.sort_index()
        ocol = _outline_col(g)
        if ocol is None:
            return g
        current_sections: Dict[int, str] = {}
        proj_name = ""
        if "project name" in g.columns and len(g) > 0:
            v0 = g["project name"].iloc[0]
            proj_name = str(v0).strip() if pd.notna(v0) else ""
        # Поэлементный g.at[idx, ...] по Arrow-backed столбцам (pandas 3.0)
        # боксит pyarrow-скаляр и переписывает chunked-массив на каждой ячейке
        # (~O(n) на запись). Снимаем оверхед: читаем колонки в numpy/списки,
        # считаем section в чистом Python, пишем столбец одной операцией.
        lvl_arr = pd.to_numeric(g[ocol], errors="coerce").to_numpy()
        task_vals = g["task name"].tolist()
        section_vals = g["section"].astype(object).tolist()
        for i in range(len(g)):
            lvl = lvl_arr[i]
            tv = task_vals[i]
            task = str(tv).strip() if pd.notna(tv) else ""
            if pd.notna(lvl):
                lvl_int = int(lvl)
                if lvl_int == 1:
                    current_sections[lvl_int] = str(proj_name) if proj_name else task
                else:
                    current_sections[lvl_int] = task
                for k in list(current_sections.keys()):
                    if k > lvl_int:
                        del current_sections[k]
                if lvl_int >= 3 and 2 in current_sections:
                    section_vals[i] = current_sections[2]
                elif lvl_int >= 2 and 1 in current_sections:
                    section_vals[i] = current_sections[1]
        g["section"] = section_vals
        return g

    if "project name" in df.columns:
        parts = []
        for _, g in df.groupby("project name", sort=False, dropna=False):
            parts.append(_walk_one(g))
        if not parts:
            return _walk_one(df)
        out = pd.concat(parts)
        return out.sort_index()
    return _walk_one(df)


def _apply_msp_column_mapping(df: pd.DataFrame, project_name: str) -> pd.DataFrame:
    """
    Переименовывает MSP-колонки в canonical-имена дашбордов.
    Парсит числовые поля (deviation in days, pct complete).
    Вычисляет deviation in days из дат если колонка пустая.
    Устанавливает boolean-флаг deviation (True = задача запаздывает).
    Добавляет Period-колонки для группировки по месяцу/кварталу/году.
    """
    # ── Переименование колонок ───────────────────────────────────────────────
    # data_loader.load_data() уже мог частично переименовать MSP-колонки в canonical-имена
    # (plan start, plan end, task name, lot, level structure, level). Пропускаем те
    # переименования, которые создадут дубликат с уже существующей canonical-колонкой,
    # иначе далее df[col] возвращает DataFrame и df[col] = df[col].apply(...) падает KeyError.
    _existing = set(df.columns)
    remap = {
        k: v for k, v in _MSP_COLUMN_REMAP.items()
        if k in _existing and v not in _existing
    }
    df = df.rename(columns=remap)
    # Страховка: если дубликаты всё-таки появились (разные исходные имена → один canonical),
    # оставляем копию с бо́льшим числом непустых значений.
    if df.columns.duplicated().any():
        _cols = list(df.columns)
        _keep = [True] * len(_cols)
        _seen: Dict[str, int] = {}
        for _i, _c in enumerate(_cols):
            if _cols.count(_c) <= 1:
                continue
            _idxs = [j for j, cc in enumerate(_cols) if cc == _c]
            if _c in _seen:
                continue
            _best = max(_idxs, key=lambda j: int(df.iloc[:, j].notna().sum()))
            for j in _idxs:
                if j != _best:
                    _keep[j] = False
            _seen[_c] = _best
        df = df.iloc[:, _keep].copy()

    from config import get_msp_project_name_map

    _msp_name_map = get_msp_project_name_map()

    # Нормализованное имя проекта из имени файла (msp_<project_name>_<date>.csv).
    # Карта → автомат по 1С Projekts (транслит slug) → исходный slug.
    _file_key = (project_name or "").strip().lower().replace(" ", "")
    _file_key_base = re.sub(r"\d+$", "", _file_key)
    ru_from_file = (
        _msp_name_map.get(_file_key)
        or _msp_name_map.get(_file_key_base)
        or ""
    )
    if not ru_from_file:
        try:
            from dashboards.project_labels import match_latin_slug_to_russian_project

            ru_from_file = str(
                match_latin_slug_to_russian_project(project_name or _file_key) or ""
            ).strip()
        except Exception:
            ru_from_file = ""
    if not ru_from_file:
        ru_from_file = project_name or ""

    def _normalize_project_cell(x):
        if pd.isna(x):
            return ru_from_file
        s = str(x).strip()
        if not s or s.lower() in ("nan", "none", "<na>"):
            return ru_from_file
        lk = s.lower().replace(" ", "")
        lk_base = re.sub(r"\d+$", "", lk)
        hit = (
            _msp_name_map.get(s)
            or _msp_name_map.get(lk)
            or _msp_name_map.get(lk_base)
        )
        if hit:
            return hit
        try:
            from dashboards.project_labels import match_latin_slug_to_russian_project

            auto = match_latin_slug_to_russian_project(s)
            if auto:
                return str(auto).strip()
        except Exception:
            pass
        return ru_from_file or s

    if "project name" not in df.columns:
        df["project name"] = ru_from_file
    else:
        df["project name"] = df["project name"].apply(_normalize_project_cell)

    df = _coerce_msp_project_name_from_file_if_needed(df, ru_from_file)

    # ── Вспомогательные функции ──────────────────────────────────────────────
    def _parse_msp_date(val):
        """Парсит DD.MM.YY, DD.MM.YYYY, YYYY-MM-DD → pd.Timestamp.
        Явные форматы надёжнее format='mixed' для 2-значного года."""
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return pd.NaT
        # Уже-распарсенный Timestamp/datetime (data_loader мог сделать это раньше).
        # Никакого вторичного парсинга через str(val) — иначе pandas с dayfirst=True
        # инвертирует ISO-строку '2025-04-01 00:00:00' в 4 января 2025.
        if isinstance(val, pd.Timestamp):
            return pd.NaT if pd.isna(val) else val
        from datetime import date as _date, datetime as _dt
        if isinstance(val, _dt):
            return pd.Timestamp(val)
        if isinstance(val, _date):
            return pd.Timestamp(val)
        s = str(val).strip()
        if not s or s.lower() in ("nan", "none", "нд", "nd", "nat", ""):
            return pd.NaT
        for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
            try:
                return pd.Timestamp(_dt.strptime(s, fmt))
            except ValueError:
                continue
        # smart-парсер: ISO строки идут БЕЗ dayfirst, иначе pandas переворачивает.
        from utils import smart_to_datetime
        return smart_to_datetime(s)

    def _parse_days_str(val):
        """'5 дн' → 5.0, '-30 дн' → -30.0, '0 дн?' → 0.0, пустое → None."""
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return None
        s = str(val).strip().replace("\xa0", "")
        if not s or s.lower() in ("nan", "none", ""):
            return None
        m = re.search(r"(-?\s*\d+(?:[.,]\d+)?)", s)
        if m:
            try:
                return float(m.group(1).replace(",", ".").replace(" ", ""))
            except (ValueError, TypeError):
                return None
        return None

    # ── Даты: явные форматы вместо format='mixed' ────────────────────────────
    for col in ("plan start", "plan end", "base start", "base end", "actual finish"):
        if col in df.columns:
            df[col] = df[col].apply(_parse_msp_date)

    # ── pct complete: "5%" → 5.0 ────────────────────────────────────────────
    if "pct complete" in df.columns:
        from utils import parse_msp_pct_complete

        df["pct complete"] = df["pct complete"].apply(parse_msp_pct_complete)

    # ── deviation in days: "5 дн" → 5.0, "-30 дн" → -30.0 ─────────────────
    if "deviation in days" in df.columns:
        df["deviation in days"] = df["deviation in days"].apply(_parse_days_str)
    else:
        df["deviation in days"] = None

    # Fallback: если колонка пустая — вычисляем из дат (plan end - base end)
    if "plan end" in df.columns and "base end" in df.columns:
        mask_empty = df["deviation in days"].isna()
        calc_mask = mask_empty & df["plan end"].notna() & df["base end"].notna()
        if calc_mask.any():
            df.loc[calc_mask, "deviation in days"] = (
                df.loc[calc_mask, "plan end"] - df.loc[calc_mask, "base end"]
            ).dt.days

    # ── deviation start days: "5 дн" → 5.0 ─────────────────────────────────
    if "deviation start days" in df.columns:
        df["deviation start days"] = df["deviation start days"].apply(_parse_days_str)
    else:
        df["deviation start days"] = None

    if "plan start" in df.columns and "base start" in df.columns:
        mask_empty = df["deviation start days"].isna()
        calc_mask = mask_empty & df["plan start"].notna() & df["base start"].notna()
        if calc_mask.any():
            df.loc[calc_mask, "deviation start days"] = (
                df.loc[calc_mask, "plan start"] - df.loc[calc_mask, "base start"]
            ).dt.days

    # ── Флаг deviation: True если задача запаздывает ─────────────────────────
    # Дашборды фильтруют по: deviation == True или deviation == 1
    df["deviation"] = df["deviation in days"].apply(
        lambda x: True if (pd.notna(x) and float(x) > 0) else False
    )

    # ── Period-колонки для группировки (аналогично data_loader.py) ──────────
    for date_col, prefix in [
        ("plan start", "plan_start"),
        ("plan end", "plan"),
        ("base start", "base_start"),
        ("base end", "base"),
    ]:
        if date_col in df.columns:
            mask = df[date_col].notna()
            if mask.any():
                df.loc[mask, f"{prefix}_day"] = df.loc[mask, date_col].dt.date
                df.loc[mask, f"{prefix}_month"] = df.loc[mask, date_col].dt.to_period("M")
                df.loc[mask, f"{prefix}_quarter"] = df.loc[mask, date_col].dt.to_period("Q")
                df.loc[mask, f"{prefix}_year"] = df.loc[mask, date_col].dt.to_period("Y")

    if "plan end" in df.columns:
        mask = df["plan end"].notna()
        if mask.any():
            df.loc[mask, "plan_month"] = df.loc[mask, "plan end"].dt.to_period("M")
            df.loc[mask, "plan_quarter"] = df.loc[mask, "plan end"].dt.to_period("Q")
            df.loc[mask, "plan_year"] = df.loc[mask, "plan end"].dt.to_period("Y")

    if "base end" in df.columns:
        mask = df["base end"].notna()
        if mask.any():
            df.loc[mask, "actual_month"] = df.loc[mask, "base end"].dt.to_period("M")
            df.loc[mask, "actual_quarter"] = df.loc[mask, "base end"].dt.to_period("Q")
            df.loc[mask, "actual_year"] = df.loc[mask, "base end"].dt.to_period("Y")

    ensure_msp_hierarchy_columns(df)
    if "level" in df.columns and "task name" in df.columns:
        df = _fill_section_from_task_tree(df)

    df.attrs["data_type"] = "project"
    return df


def _load_rd_plan_file(filepath: Path) -> Optional[pd.DataFrame]:
    """B-12/13 (2026-05-07): загрузка `other_*_rd.csv` (план выдачи РД).

    В этих CSV 1-я строка обычно — длинное название проекта в одной
    «ячейке-заголовке» (`;;;;…;ПРОИЗВОДСТВЕННО — СКЛАДСКОЙ КОМПЛЕКС…;;;;;;;`),
    а реальные заголовки таблицы — на 2-й (`ID_проекта;№ п/п;Наименование…;
    № Договора;Шифр;Номер шифра;Блок;Шифр полный;…`). При чтении с `header=0`
    pandas получал `Unnamed: 0..7`, поэтому план «РД по Договору» / 12 / 13
    оставался пустым. Здесь пробуем `header_row ∈ {0,1,2}` и берём вариант
    с максимальным числом сигналов RD-колонок (ID_проекта / Шифр / Блок /
    «Наименование работ» / № Договора) минус штраф за `Unnamed*` в шапке.
    """
    # cp866 — DOS-кириллица, иногда встречается в выгрузках от подрядчика
    # (бьёт на cp1251 байтом 0x98). Без него `other_leninsky_30.04.2026_rd.csv`
    # не читался ни одним из основных пресетов.
    encodings = ["utf-8-sig", "utf-8", "windows-1251", "cp1251", "cp866"]
    seps = [";", ","]
    rd_signal_keys = (
        "id_проекта",
        "id проекта",
        "id проект",
        "шифр",
        "наименование",
        "блок",
        "договор",
        "загрузка в эдо",
        "статус рд",
    )
    best_df: Optional[pd.DataFrame] = None
    best_score = -1
    best_note = ""
    for header_row in (0, 1, 2, 3):
        for enc in encodings:
            for sep in seps:
                try:
                    df = pd.read_csv(
                        filepath,
                        sep=sep,
                        encoding=enc,
                        header=header_row,
                        quoting=csv.QUOTE_MINIMAL,
                        quotechar='"',
                        doublequote=True,
                        on_bad_lines="skip",
                        low_memory=False,
                    )
                except Exception:
                    continue
                if df is None or getattr(df, "empty", True) or len(df.columns) < 4:
                    continue
                df.columns = [
                    str(c).replace("\ufeff", "").replace("\n", " ").replace("\r", " ").strip()
                    for c in df.columns
                ]
                cols_low = [str(c).lower() for c in df.columns]
                signals = sum(
                    1 for k in rd_signal_keys if any(k in c for c in cols_low)
                )
                unnamed = sum(1 for c in cols_low if c.startswith("unnamed"))
                empty_names = sum(1 for c in cols_low if not c)
                score = signals * 10 - unnamed - empty_names
                if score > best_score:
                    best_score = score
                    best_df = df
                    best_note = f"header_row={header_row}, enc={enc}, sep={sep!r}, signals={signals}, unnamed={unnamed}"
    if best_df is None or best_score <= 0:
        # Fallback: некоторые `other_*_rd.csv` приходят с битыми байтами
        # (cp1251 0x98 и т.п.) и валятся на всех строгих кодировках. Берём
        # cp1251 + windows-1251 с `encoding_errors='replace'` — теряем редкие
        # «крякозябры» в шапке заголовка проекта, зато получаем нормальную
        # таблицу заголовка в строке 2.
        for header_row in (1, 2, 0):
            for enc in ("cp866", "cp1251", "windows-1251", "utf-8"):
                try:
                    df = pd.read_csv(
                        filepath,
                        sep=";",
                        encoding=enc,
                        encoding_errors="replace",
                        header=header_row,
                        quoting=csv.QUOTE_MINIMAL,
                        quotechar='"',
                        doublequote=True,
                        on_bad_lines="skip",
                        low_memory=False,
                    )
                except Exception:
                    continue
                if df is None or getattr(df, "empty", True) or len(df.columns) < 4:
                    continue
                df.columns = [
                    str(c).replace("\ufeff", "").replace("\n", " ").replace("\r", " ").strip()
                    for c in df.columns
                ]
                cols_low = [str(c).lower() for c in df.columns]
                signals = sum(
                    1 for k in rd_signal_keys if any(k in c for c in cols_low)
                )
                if signals >= 3:
                    df = df.dropna(how="all").reset_index(drop=True)
                    if df.empty:
                        continue
                    df = _rd_plan_unglue_name_columns(df)
                    df.attrs["data_type"] = "rd_plan"
                    df.attrs["rd_plan_header_note"] = (
                        f"FALLBACK header_row={header_row}, enc={enc}, sep=';', "
                        f"encoding_errors=replace, signals={signals}"
                    )
                    return df
        return None
    best_df = best_df.dropna(how="all").reset_index(drop=True)
    if best_df.empty:
        return None
    best_df = _rd_plan_unglue_name_columns(best_df)
    best_df.attrs["data_type"] = "rd_plan"
    best_df.attrs["rd_plan_header_note"] = best_note
    return best_df


# other_*_rd/pd.csv иногда склеивают уровни иерархии без пробела
# («…железобетонныеПлиты…», «…+4.500Покрытие…»).
_RD_PLAN_GLUED_NAME_RE = re.compile(
    r"(?<=[а-яёa-z])(?=[А-ЯЁA-Z])|(?<=[0-9])(?=[А-ЯЁA-Z])"
)


def _rd_plan_unglue_name_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Нормализует колонки «Наименование…» плана РД/ПД: вставляет пробелы в слитных именах."""
    if df is None or getattr(df, "empty", True):
        return df
    out = df
    for col in list(out.columns):
        cl = str(col).replace("\n", " ").replace("\r", " ").strip().casefold()
        if "наименован" not in cl:
            continue
        ser = out[col].map(
            lambda v: (
                ""
                if v is None or (isinstance(v, float) and pd.isna(v))
                else str(v).strip()
            )
        )
        fixed = ser.map(
            lambda s: (
                re.sub(r"\s+", " ", _RD_PLAN_GLUED_NAME_RE.sub(" ", s)).strip()
                if s and _RD_PLAN_GLUED_NAME_RE.search(s)
                else s
            )
        )
        if not fixed.equals(ser):
            if out is df:
                out = df.copy()
            out[col] = fixed
    return out


def _load_resources_file(filepath: Path) -> Optional[pd.DataFrame]:
    """
    Загружает файл ресурсов (other_*_resursi.csv) с многострочным заголовком.

    Поддерживаются ДВА варианта шапки:

    Вариант A (старый):
      Строка 0: пустая / разделители
      Строка 1: метки недель
      Строка 2: «Проект;Подрядчик;тип ресурсов;<даты>;…»

    Вариант B (новый, AI/other_*__resursi.csv):
      Строка 0: «?;;;;…» (мусор / BOM)
      Строка 1: «;;;;;;1 неделя;1 неделя;…»
      Строка 2: «ID Проекта;Наименование Проекта;ID Подрядчика;Подрядчик_new;Подрядчик_old;тип ресурсов;<даты>;тип ресурсов»

    Поэтому проверяем «контрагент/подрядчик» по подстроке (а не равенством),
    а «Проект» считаем найденным, если есть колонка «Наименование Проекта»
    или «Проект» как подстрока. После распознавания нормализуем:
      • Подрядчик_new (или Подрядчик / Подрядчик_old) → Контрагент;
      • Наименование Проекта → Проект.
    """
    encodings = ["utf-8-sig", "utf-8", "windows-1251", "cp1251"]
    seps = [";", ","]
    # На FTP иногда 2 или 1 строка «служебных» строк — пробуем несколько header
    for header_row in (2, 1, 0):
        for encoding in encodings:
            for sep in seps:
                try:
                    df = pd.read_csv(
                        filepath,
                        sep=sep,
                        encoding=encoding,
                        header=header_row,
                        quoting=csv.QUOTE_MINIMAL,
                        quotechar='"',
                        doublequote=True,
                        on_bad_lines="skip",
                    )
                    df.columns = [
                        str(c).replace("\ufeff", "").replace("\n", " ").replace("\r", " ").strip()
                        for c in df.columns
                    ]
                    df = df.dropna(how="all")
                    if df.empty or len(df.columns) < 3:
                        continue
                    cols_low = [str(c).lower() for c in df.columns]
                    # substring match: «Подрядчик_new» / «ID Подрядчика» тоже считаются
                    has_contractor = any(
                        any(s in cl for s in ("контрагент", "подрядчик", "contractor"))
                        for cl in cols_low
                    )
                    has_project = any(
                        ("проект" in cl) for cl in cols_low
                    )
                    if not has_contractor or not has_project:
                        continue

                    # Нормализуем «Подрядчик*» → «Контрагент» (новый формат:
                    # предпочитаем Подрядчик_new; иначе Подрядчик; иначе _old).
                    if "Контрагент" not in df.columns:
                        for cand in ("Подрядчик_new", "Подрядчик", "Подрядчик_old"):
                            if cand in df.columns:
                                df = df.rename(columns={cand: "Контрагент"})
                                break

                    # Нормализуем имя проекта: «Наименование Проекта» → «Проект».
                    if "Проект" not in df.columns:
                        for cand in ("Наименование Проекта", "Наименование проекта", "Название проекта"):
                            if cand in df.columns:
                                df = df.rename(columns={cand: "Проект"})
                                break

                    _ru_res_aliases = {
                        "тип ресурса": "тип ресурсов",
                        "Тип ресурса": "тип ресурсов",
                    }
                    for a, b in _ru_res_aliases.items():
                        if a in df.columns and b not in df.columns:
                            df = df.rename(columns={a: b})

                    from config import get_msp_project_name_map
                    _msp_name_map = get_msp_project_name_map()
                    if "Проект" in df.columns:
                        df["Проект"] = df["Проект"].apply(
                            lambda x: _msp_name_map.get(
                                str(x).strip().lower().replace(" ", ""), str(x).strip()
                            ) if pd.notna(x) else x
                        )

                    df.attrs["data_type"] = "resources"
                    return df
                except (UnicodeDecodeError, pd.errors.ParserError):
                    continue
                except Exception:
                    continue

    # ── Fallback: «pivot-aware» сборка шапки из нескольких строк ────────
    # Поддерживает третий формат other_*_resursi.csv (старая выгрузка):
    #   0: Период;Февраль;2026;…
    #   1: ;Подрядчик;;;Дмитров;…       ← подрядчик «спрятан» здесь
    #   2: Проект;;тип ресурсов;1 неделя;2 неделя;…
    #   3: ;;;01.02.26;02.02.26;…       ← даты как третий уровень шапки
    #   4+: данные
    # Никакой header=N такой формат не возьмёт, поэтому читаем raw и
    # склеиваем имена колонок руками: дата → дата; иначе из строки 2;
    # иначе из строки 1 (group label).
    for encoding in encodings:
        for sep in seps:
            try:
                raw = pd.read_csv(
                    filepath,
                    sep=sep,
                    encoding=encoding,
                    header=None,
                    quoting=csv.QUOTE_MINIMAL,
                    quotechar='"',
                    doublequote=True,
                    on_bad_lines="skip",
                )
            except Exception:
                continue
            if raw is None or raw.empty or len(raw) < 5:
                continue

            def _row(idx):
                if idx >= len(raw):
                    return [""] * len(raw.columns)
                return [
                    "" if pd.isna(v) else str(v).replace("\ufeff", "").strip()
                    for v in raw.iloc[idx].tolist()
                ]

            r0, r1, r2, r3 = _row(0), _row(1), _row(2), _row(3)
            ncols = len(raw.columns)
            date_re = re.compile(r"^\d{1,2}[.-/]\d{1,2}[.-/]\d{2,4}$")

            cols: List[str] = []
            data_start = 4
            for i in range(ncols):
                cell3 = r3[i] if i < len(r3) else ""
                cell2 = r2[i] if i < len(r2) else ""
                cell1 = r1[i] if i < len(r1) else ""
                cell0 = r0[i] if i < len(r0) else ""
                if cell3 and date_re.match(cell3):
                    cols.append(cell3)
                elif cell2 and cell2.lower() not in ("nan", ""):
                    cols.append(cell2)
                elif cell1 and cell1.lower() not in ("nan", ""):
                    cols.append(cell1)
                elif cell0 and cell0.lower() not in ("nan", ""):
                    cols.append(cell0)
                else:
                    cols.append(f"col_{i}")

            cols_low = [c.lower() for c in cols]
            has_proj = any("проект" in c for c in cols_low)
            has_contr = any(
                any(s in c for s in ("подрядчик", "контрагент", "contractor"))
                for c in cols_low
            )
            has_dates = any(date_re.match(c) for c in cols)
            if not (has_proj and has_contr and has_dates):
                continue

            cols_unique: List[str] = []
            seen: Dict[str, int] = {}
            for c in cols:
                if c in seen:
                    seen[c] += 1
                    cols_unique.append(f"{c}.{seen[c]}")
                else:
                    seen[c] = 0
                    cols_unique.append(c)

            try:
                data = raw.iloc[data_start:].reset_index(drop=True).copy()
                data.columns = cols_unique
            except Exception:
                continue
            data = data.dropna(how="all")
            if data.empty:
                continue

            for cand in ("Подрядчик_new", "Подрядчик", "Подрядчик_old"):
                if cand in data.columns and "Контрагент" not in data.columns:
                    data = data.rename(columns={cand: "Контрагент"})
                    break
            if "Контрагент" not in data.columns:
                for c in data.columns:
                    if "подрядчик" in str(c).lower() or "контрагент" in str(c).lower():
                        data = data.rename(columns={c: "Контрагент"})
                        break

            if "Проект" not in data.columns:
                for cand in ("Наименование Проекта", "Наименование проекта", "Название проекта"):
                    if cand in data.columns:
                        data = data.rename(columns={cand: "Проект"})
                        break
                if "Проект" not in data.columns:
                    for c in data.columns:
                        if "проект" in str(c).lower():
                            data = data.rename(columns={c: "Проект"})
                            break

            for a, b in (("тип ресурса", "тип ресурсов"), ("Тип ресурса", "тип ресурсов")):
                if a in data.columns and b not in data.columns:
                    data = data.rename(columns={a: b})

            try:
                from config import get_msp_project_name_map
                _msp_name_map = get_msp_project_name_map()
                if "Проект" in data.columns:
                    data["Проект"] = data["Проект"].apply(
                        lambda x: _msp_name_map.get(
                            str(x).strip().lower().replace(" ", ""), str(x).strip()
                        ) if pd.notna(x) else x
                    )
            except Exception:
                pass

            data.attrs["data_type"] = "resources"
            return data

    return None


def _load_1c_json_dk(filepath: Path) -> Optional[pd.DataFrame]:
    try:
        with open(filepath, encoding="utf-8") as f:
            raw = json.load(f)
        if not raw or not isinstance(raw, list):
            return None
        rows = []
        _summary_adv_rub = 0.0
        for item in raw:
            try:
                org = item.get("Организация") or {}
                contr = item.get("Контрагент") or {}
                dog = item.get("Договор") or {}
                # Итоговая строка выгрузки (Контрагент/Договор/Организация = null) — не контрагент.
                if not isinstance(contr, dict):
                    contr = {}
                if not isinstance(dog, dict):
                    dog = {}
                if not isinstance(org, dict):
                    org = {}
                _has_contr = bool(
                    str(contr.get("НаименованиеКонтрагента", "") or "").strip()
                    or str(contr.get("ID_Контрагента", "") or "").strip()
                )
                _has_dog = bool(
                    str(dog.get("ID_Договора", "") or "").strip()
                    or str(dog.get("НомерДоговора", "") or "").strip()
                )
                _has_org = bool(str(org.get("ID_Организации", "") or "").strip())
                if not _has_contr and not _has_dog and not _has_org:
                    try:
                        _summary_adv_rub += float(
                            item.get("ОстатокНаКонецПериодаПоАвансам", 0) or 0
                        )
                    except (TypeError, ValueError):
                        pass
                    continue
                flat = {}
                flat["Название организации"] = org.get("НаименованиеОрганизации", "")
                flat["ID_Организации"] = org.get("ID_Организации", "")
                flat["Название контрагента"] = contr.get("НаименованиеКонтрагента", "")
                flat["ID_Контрагента"] = contr.get("ID_Контрагента", "")
                flat["Номер договора"] = str(dog.get("НомерДоговора", "") or "").strip()
                flat["ID_Договора"] = dog.get("ID_Договора", "")
                flat["Дата договора"] = dog.get("ДатаДоговора", "")
                sum_str = str(dog.get("СуммаДоговора", "0") or "0").replace(",", "").replace(" ", "")
                try:
                    flat["Сумма в договоре"] = float(sum_str) if sum_str else 0.0
                except (ValueError, TypeError):
                    flat["Сумма в договоре"] = 0.0
                def _safe_float(val):
                    try:
                        return float(val) if val is not None else 0.0
                    except (ValueError, TypeError):
                        return 0.0
                flat["ОстатокНаНачало"] = _safe_float(item.get("ОстатокНаНачало", 0))
                flat["ОстатокНаНачалоПериода"] = _safe_float(item.get("ОстатокНаНачалоПериода", 0))
                flat["ОстатокНаНачалоПериодаПоАвансам"] = _safe_float(item.get("ОстатокНаНачалоПериодаПоАвансам", 0))
                flat["Выплачено"] = _safe_float(item.get("ВсегоОплат", 0))
                flat["Аванс"] = _safe_float(item.get("ВсегоОплат_Аванс", 0))
                flat["ОстатокНаКонец"] = _safe_float(item.get("ОстатокНаКонец", 0))
                flat["Остаток на конец периода"] = _safe_float(item.get("ОстатокНаКонецПериода", 0))
                flat["ОстатокНаКонецПериодаПоАвансам"] = _safe_float(item.get("ОстатокНаКонецПериодаПоАвансам", 0))
                rows.append(flat)
            except Exception:
                continue
        if not rows:
            return None
        df = pd.DataFrame(rows)
        df.attrs["data_type"] = "debit_credit"
        if _summary_adv_rub > 0:
            df.attrs["dk_summary_advance_rub"] = float(_summary_adv_rub)
        return df
    except Exception:
        return None


def _load_1c_json_spravochniki(filepath: Path) -> Optional[pd.DataFrame]:
    try:
        with open(filepath, encoding="utf-8") as f:
            raw = json.load(f)
        if not raw or not isinstance(raw, list):
            return None
        return pd.DataFrame(raw)
    except Exception:
        return None


def _json_df_matches_1c_turnover_columns(df: Optional[pd.DataFrame]) -> bool:
    """
    True, если JSON — массив оборотов 1С в духе *_dannye.json (поля для БДДС-план/факт).
    Используется, когда имя файла не попало под шаблоны _infer_file_type_by_name.
    """
    try:
        from dashboards.finance_from_1c import _pick_col
    except Exception:
        return False
    if df is None or getattr(df, "empty", True):
        return False
    return bool(
        _pick_col(df, ("ТипСтатьи", "article_type", "Тип статьи"))
        and _pick_col(df, ("Сценарий", "scenario"))
        and _pick_col(df, ("СтатьяОборотов", "Статья оборотов", "article"))
        and _pick_col(df, ("Сумма", "amount"))
    )


def _find_dannye_contractor_column(df: pd.DataFrame) -> Optional[str]:
    """Колонка контрагента в JSON «данные» 1С (обороты): Контрагент, Наименование…"""
    if df is None or df.empty:
        return None
    scored: List[Tuple[int, str]] = []
    for c in df.columns:
        s = str(c).strip().lower().replace("_", " ")
        sc = 0
        if "инн" in s or "кпп" in s:
            continue
        if s in ("контрагент", "контрагенты"):
            sc += 80
        if "контрагент" in s and "договор" not in s:
            sc += 40
        if "наименование" in s and "контрагент" in s:
            sc += 60
        if "организация" in s and "контрагент" not in s:
            sc += 5
        if sc > 0:
            scored.append((sc, str(c)))
    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    return scored[0][1]


def _find_dannye_project_column(df: pd.DataFrame) -> Optional[str]:
    """Колонка проекта в JSON «данные» 1С."""
    if df is None or df.empty:
        return None
    for c in df.columns:
        sl = str(c).strip().lower().replace("_", " ")
        if sl == "проект" or sl.endswith(" проект"):
            return str(c)
    for c in df.columns:
        sl = str(c).strip().lower().replace("_", " ")
        if "проект" in sl and "проектн" not in sl and "подпроект" not in sl:
            if "id" not in sl or sl == "id проекта":
                return str(c)
    return None


def _build_partner_project_map_from_dannye(df: pd.DataFrame) -> Dict[str, str]:
    """
    Контрагент → наиболее частый Проект по строкам dannye.json (обороты 1С).
    Ключи — norm_partner_join_key.
    """
    from collections import Counter

    if df is None or df.empty:
        return {}
    cc = _find_dannye_contractor_column(df)
    pc = _find_dannye_project_column(df)
    if not cc or not pc or cc not in df.columns or pc not in df.columns:
        return {}
    tmp = df[[cc, pc]].copy()
    tmp = tmp.dropna(how="any")
    tmp = tmp[tmp[cc].astype(str).str.strip() != ""]
    tmp = tmp[tmp[pc].astype(str).str.strip() != ""]
    if tmp.empty:
        return {}
    out: Dict[str, str] = {}
    for raw_k, g in tmp.groupby(tmp[cc].map(lambda x: norm_partner_join_key(x))):
        if not raw_k:
            continue
        cnt = Counter(g[pc].astype(str).str.strip())
        out[raw_k] = cnt.most_common(1)[0][0]
    return out


def _merge_partner_project_maps(
    old: Optional[Dict[str, str]], new: Optional[Dict[str, str]]
) -> Dict[str, str]:
    """Объединяет карты; при конфликте оставляет значение из new (свежий файл)."""
    a = dict(old or {})
    for k, v in (new or {}).items():
        if k and v:
            a[k] = v
    return a


def _tessa_tag_column(df) -> Optional[str]:
    if df is None or not hasattr(df, "columns"):
        return None
    cols = [str(c).strip() for c in df.columns]
    for cand in (
        "Tessa_Teg",
        "TessaTag",
        "TESSA_TEG",
        "tessa_teg",
        "ТегТесса",
        "Тег Тесса",
    ):
        cl = cand.casefold()
        for c in cols:
            if c.casefold() == cl:
                return c
    for c in cols:
        compact = "".join(c.casefold().replace("\xa0", " ").split())
        if "tessa" in compact and "teg" in compact:
            return c
    return None


def _tessa_drop_cancelled_tag_rows(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    """Исключить документы с тегом «Отмененный» в Tessa_Teg (не попадают в отчёты)."""
    if df is None or getattr(df, "empty", True):
        return df
    tag_col = _tessa_tag_column(df)
    if not tag_col:
        return df
    tags = (
        df[tag_col]
        .astype(str)
        .str.replace("\ufeff", "", regex=False)
        .str.replace("\xa0", " ", regex=False)
        .str.strip()
        .str.casefold()
    )
    empty_tag = tags.isin({"", "nan", "none", "<na>", "nat"})
    cancelled = tags.isin(
        {
            "отмененный",
            "отменённый",
            "отменен",
            "отменён",
            "cancelled",
            "canceled",
        }
    ) | tags.str.contains("отменен", na=False)
    return df.loc[~(cancelled & ~empty_tag)].copy().reset_index(drop=True)


def _load_tessa_file(filepath: Path) -> Optional[pd.DataFrame]:
    encodings = ["utf-8", "utf-8-sig", "windows-1251", "cp1251"]
    seps = [";", ","]
    for encoding in encodings:
        for sep in seps:
            try:
                df = pd.read_csv(
                    filepath,
                    sep=sep,
                    encoding=encoding,
                    quoting=csv.QUOTE_MINIMAL,
                    quotechar='"',
                    doublequote=True,
                    on_bad_lines="skip",
                )
                df.columns = [
                    str(c).replace("\ufeff", "").replace("\n", " ").replace("\r", " ").strip()
                    for c in df.columns
                ]
                df = df.dropna(how="all")
                if df.empty or len(df.columns) < 3:
                    continue
                df.attrs["data_type"] = "tessa"
                return _tessa_drop_cancelled_tag_rows(df)
            except (UnicodeDecodeError, pd.errors.ParserError):
                continue
    return None


def _load_reference_csv(filepath: Path) -> Optional[pd.DataFrame]:
    encodings = ["utf-8", "utf-8-sig", "windows-1251", "cp1251"]
    for encoding in encodings:
        try:
            df = pd.read_csv(filepath, sep=",", encoding=encoding, on_bad_lines="skip")
            df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
            if df.empty:
                continue
            return df
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    return None


def _format_skip_reason(rel_path: str, reason: str, detail: str = "") -> str:
    msg = f"{rel_path}: {reason}"
    if detail:
        msg += f" — {detail}"
    return msg


# ── Утилиты ─────────────────────────────────────────────────────────────────

def get_web_dir() -> Path:
    return Path(__file__).resolve().parent / "web"


def _iter_web_scan_roots() -> List[Tuple[Path, str]]:
    """
    Корни для CSV/JSON: локальный web/, при наличии .../Analitics/web, пути из BI_ANALYTICS_WEB_EXTRA_PATHS.
    Второй элемент кортежа — префикс для rel_path (уникальность при одинаковых именах в разных корнях).
    """
    from config import (
        get_analytics_sibling_web_dir,
        get_extra_web_dirs_from_env,
        get_showcase_web_dir,
        include_analytics_sibling_web_dir,
        is_showcase_mode,
    )

    roots: List[Tuple[Path, str]] = []
    seen: set = set()

    def _add(root: Path, prefix: str) -> None:
        try:
            key = str(root.resolve())
        except OSError:
            return
        if key in seen:
            return
        seen.add(key)
        roots.append((root, prefix))

    if is_showcase_mode():
        _showcase = get_showcase_web_dir()
        if _showcase is not None:
            _add(_showcase, "showcase")
        return roots

    _add(get_web_dir(), "")

    sib = get_analytics_sibling_web_dir() if include_analytics_sibling_web_dir() else None
    if sib is not None:
        try:
            if sib.resolve() != get_web_dir().resolve():
                _add(sib, "Analitics_web")
        except OSError:
            _add(sib, "Analitics_web")

    for ex in get_extra_web_dirs_from_env():
        label = ex.name.replace(" ", "_") or "extra_web"
        _add(ex, label)

    return roots


def web_dir_exists() -> bool:
    """True, если есть хотя бы один из каталогов данных (локальный web/, Analitics/web, extra из env)."""
    for root, _ in _iter_web_scan_roots():
        if root.is_dir():
            return True
    return False


def _is_demo_file(rel_path: str, name: str) -> bool:
    """
    Демо: имена sample_*, любой файл внутри каталога new_csv/ в пути.
    (Режим отключения — ``BI_ANALYTICS_IGNORE_DEMO`` через :func:`ignore_demo_data_files`.)
    """
    n = str(name).lower()
    if n.startswith("sample_"):
        return True
    for part in Path(str(rel_path).replace("\\", "/")).parts:
        if part.lower() == "new_csv":
            return True
    return False


def scan_web_files(extensions: tuple = (".csv", ".json")) -> List[Dict]:
    """Рекурсивно сканирует все настроенные корни данных и возвращает список файлов."""
    from config import is_prohibited_production_data_path, is_showcase_mode

    files: List[Dict] = []
    for root, prefix in _iter_web_scan_roots():
        if not root.exists():
            continue
        for ext in extensions:
            for filepath in sorted(root.rglob(f"*{ext}")):
                if filepath.is_file():
                    rel = filepath.relative_to(root)
                    rel_path = str(rel).replace("\\", "/")
                    if prefix:
                        rel_path = f"{prefix}/{rel_path}"
                    if not is_showcase_mode() and (
                        is_prohibited_production_data_path(rel_path)
                        or is_prohibited_production_data_path(filepath)
                    ):
                        continue
                    if ignore_demo_data_files() and _is_demo_file(rel_path, filepath.name):
                        continue
                    files.append({
                        "path": filepath,
                        "name": filepath.name,
                        "rel_path": rel_path,
                    })
    return files


def _dedupe_scan_files_by_identity(files: List[Dict]) -> Tuple[List[Dict], List[str]]:
    """
    Убирает повторную загрузку одного и того же файла, если он попал в список
    из нескольких корней (локальный web/, Analitics/web/, BI_ANALYTICS_WEB_EXTRA_PATHS):
    одинаковое имя и размер на диске считаем дубликатом, оставляем первый путь.

    Без этого concat в session_state даёт удвоение строк MSP и «лишние» записи в БД.
    """
    seen: Dict[Tuple[str, int], str] = {}
    out: List[Dict] = []
    warns: List[str] = []
    for f in files:
        try:
            sz = int(f["path"].stat().st_size)
        except OSError:
            out.append(f)
            continue
        key = (str(f["name"]).lower(), sz)
        if key in seen:
            warns.append(
                f"Пропуск дубликата (уже как «{seen[key]}»): {f['rel_path']}"
            )
            continue
        seen[key] = f["rel_path"]
        out.append(f)
    return out, warns


_ONE_C_STEM_RE = re.compile(
    r"^(?:1с_|1c_|lc_|лк_|lk_)(\d{2}-\d{2}-\d{4})(?:_(\d{2}-\d{2}))?(?:_(.+))?$",
    re.IGNORECASE,
)


def _file_mtime(path) -> float:
    try:
        p = path if isinstance(path, Path) else Path(str(path))
        return float(p.stat().st_mtime)
    except OSError:
        return 0.0


def _all_dates_in_stem(stem: str) -> List:
    """Извлекает все даты из стэма имени файла.

    Используем lookbehind/lookahead на цифру вместо \\b, потому что в стэмах
    типа 'msp_dmitrovsky1_28-04-2026' символ '_' считается word-char, и \\b
    между '_' и '2' не срабатывает — тогда даты вообще не находились,
    pick_latest_snapshot_files падал в фоллбэк по mtime и выбирал не самый
    свежий снимок (например 30-03 вместо 28-04).
    """
    out = []
    for m in re.finditer(r"(?<!\d)(\d{2}-\d{2}-\d{4})(?!\d)", stem):
        d = _parse_snapshot_date(m.group(1))
        if d is not None:
            out.append(d)
    for m in re.finditer(r"(?<!\d)(\d{2})\.(\d{2})\.(\d{4})(?!\d)", stem):
        d = _parse_snapshot_date(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
        if d is not None:
            out.append(d)
    for m in re.finditer(r"(?<!\d)(\d{2})_(\d{2})_(\d{4})(?!\d)", stem):
        d = _parse_snapshot_date(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
        if d is not None:
            out.append(d)
    for m in re.finditer(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)", stem):
        d = _parse_snapshot_date(m.group(1))
        if d is not None:
            out.append(d)
    return out


def _max_date_in_stem(stem: str):
    ds = _all_dates_in_stem(stem)
    return max(ds) if ds else None


def _one_c_snapshot_sort_key(stem: str):
    m = _ONE_C_STEM_RE.match(stem.lower())
    if not m:
        return None
    d = _parse_snapshot_date(m.group(1))
    if d is None:
        return None
    hhmm = m.group(2) or "00-00"
    return (d, hhmm)


def _one_c_file_family(stem: str) -> Optional[str]:
    """Семейство 1С JSON (dannye, dk, spravochniki, …) — последний снимок выбирается отдельно."""
    m = _ONE_C_STEM_RE.match(stem.lower())
    if not m:
        return None
    suffix = (m.group(3) or "").strip().lower()
    return suffix or "default"


def _generic_stem_family(stem: str) -> str:
    k = stem.lower()
    k = re.sub(r"\d{2}-\d{2}-\d{4}", "*", k)
    k = re.sub(r"\d{2}\.\d{2}\.\d{4}", "*", k)
    k = re.sub(r"\d{2}_\d{2}_\d{4}", "*", k)
    k = re.sub(r"\d{4}-\d{2}-\d{2}", "*", k)
    return k


def _rd_pd_plan_csv_has_status(path: Path) -> bool:
    """Есть ли в other_*_{rd|pd}.csv колонка статуса (для RD-01 «отменено»).

    Свежие slim-выгрузки иногда без «Статус» — тогда latest-only оставляет
    только их, и отменённые разделы снова попадают в KPI.
    """
    try:
        raw = Path(path).read_bytes()[:12288]
    except Exception:
        return False
    text = None
    for enc in ("utf-8-sig", "cp1251", "windows-1251", "utf-8", "cp866"):
        try:
            text = raw.decode(enc)
            break
        except Exception:
            continue
    if not text:
        return False
    for line in text.splitlines()[:8]:
        if "статус" in line.casefold():
            return True
    return False


def _tessa_kind_key(stem: str) -> str:
    """
    Формат имени:
      старый  - tessa_DD_MM_YYYY_HH-MM_<kind>.csv  (через подчёркивания)
      новый   - tessa_DD-MM-YYYY-HH-MM-<kind>.csv  (через дефисы)
    Раньше функция искала только подстроки "_task"/"_rd"/"_id" → новый формат
    с дефисом "-id"/"-rd"/"-task" попадал в bucket "other", из-за чего самый
    свежий ID/RD/TASK снимок не выбирался, и активная версия зависала на
    единственном "старом" файле tessa_27_03_2026_00-06_id.csv.
    """
    s = stem.lower()
    if (
        "tessa_tasks" in s
        or s.endswith("_task") or s.endswith("-task")
        or s.endswith("_tasks") or s.endswith("-tasks")
    ):
        return "task"
    if s.endswith("_rd") or s.endswith("-rd"):
        return "rd"
    if s.endswith("_id") or s.endswith("-id"):
        return "id"
    return "other"


# Формат tessa: tessa_DD-MM-YYYY-HH-MM-<kind> (новый) и
# tessa_DD_MM_YYYY_HH-MM_<kind> (старый).
_TESSA_NEW_RE = re.compile(
    r"^tessa[_-](\d{2})-(\d{2})-(\d{4})-(\d{2})-(\d{2})-(?:id|rd|task|tasks)$",
    re.IGNORECASE,
)
_TESSA_OLD_RE = re.compile(
    r"^tessa_(\d{2})_(\d{2})_(\d{4})_(\d{2})-(\d{2})_(?:id|rd|task|tasks)$",
    re.IGNORECASE,
)


def _tessa_snapshot_sort_key(stem: str):
    """Возвращает кортеж (date, hh-mm) для tessa-файла; None если имя не из шаблона."""
    from datetime import date as dt_date
    s = stem.lower()
    for regex in (_TESSA_NEW_RE, _TESSA_OLD_RE):
        m = regex.match(s)
        if m:
            try:
                d = dt_date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                return (d, f"{m.group(4)}-{m.group(5)}")
            except (ValueError, TypeError):
                pass
    return None


def _quick_csv_data_row_count(filepath: Path) -> int:
    """Быстрая оценка числа строк данных в CSV (без парсинга)."""
    try:
        with open(filepath, "rb") as fh:
            n = sum(1 for _ in fh)
        return max(0, n - 1)
    except OSError:
        return 0


def _pick_best_tessa_bucket_file(
    lst: List[Dict], kind_key: str
) -> Tuple[Dict, Optional[str]]:
    """
    Выбор одного TESSA-файла из bucket (id/rd/task/…).

    Для id: свежая выгрузка иногда приходит урезанной (десятки строк вместо сотен).
    Берём самый полный снимок среди файлов с датой не старше 14 дней от max даты.
    """
    from datetime import date as dt_date, timedelta

    rated: List[Tuple[tuple, float, Dict]] = []
    for f in lst:
        stem = Path(f["name"]).stem
        sk = _tessa_snapshot_sort_key(stem)
        if sk is None:
            md = _max_date_in_stem(stem)
            sk = (md or dt_date.min, "00-00")
        rated.append((sk, _file_mtime(f["path"]), f))
    if not rated:
        raise ValueError("empty tessa bucket")

    rated.sort(key=lambda x: (x[0], x[1]), reverse=True)
    best_sk, _, best_f = rated[0]

    if kind_key != "id" or len(rated) < 2:
        return best_f, None

    max_date = best_sk[0]
    window = [r for r in rated if (max_date - r[0][0]) <= timedelta(days=14)]
    scored: List[Tuple[Tuple[tuple, float, Dict], int]] = []
    for item in window:
        n = _quick_csv_data_row_count(item[2]["path"])
        if n > 0:
            scored.append((item, n))
    if not scored:
        return best_f, None

    richest_item, richest_rows = max(scored, key=lambda x: (x[1], x[0][0], x[0][1]))
    richest_f = richest_item[2]
    if richest_f["path"] == best_f["path"]:
        return best_f, None

    latest_rows = next((n for item, n in scored if item[2]["path"] == best_f["path"]), 0)
    warn = (
        f"TESSA id: «{best_f['name']}» ({latest_rows} строк) похожа на неполную выгрузку; "
        f"к загрузке выбран «{richest_f['name']}» ({richest_rows} строк)."
    )
    return richest_f, warn


def load_richest_tessa_id_from_web() -> Optional[pd.DataFrame]:
    """
    Самый полный tessa_*-id.csv из web/ (та же логика, что при pick_latest для id).
    Для fallback в дашбордах, если в session_state остался урезанный снимок из БД.
    """
    web = get_web_dir()
    if not web.is_dir():
        return None
    id_files = [
        {"name": p.name, "path": p, "rel_path": p.name}
        for p in web.glob("tessa_*-id.csv")
    ]
    if not id_files:
        return None
    best, _warn = _pick_best_tessa_bucket_file(id_files, "id")
    df = _load_tessa_file(best["path"])
    if df is None or df.empty:
        return None
    df = df.copy()
    df["__source_file"] = best["name"]
    return df


def _msp_project_bucket(stem: str) -> Optional[str]:
    s = stem.lower().replace(".csv", "")
    if not (s.startswith("msp_") or s.startswith("msp-")):
        return None
    parts = s.split("_")
    if len(parts) < 3:
        return s
    return "_".join(parts[1:-1]).lower()


def pick_latest_snapshot_files(files: List[Dict]) -> Tuple[List[Dict], List[str]]:
    """
    Оставляет только последние выгрузки по дате в имени файла (и времени снимка для JSON 1С).

    - JSON 1С с префиксом 1с_/1c_/…: один актуальный снимок (максимум пары дата + HH-MM).
    - TESSA: отдельно последний файл для task / rd / id / прочее.
    - MSP: по корню имени проекта — файл с максимальной датой в имени.
    - Остальные имена с распознанной датой: группа по шаблону без дат — файл с max датой.
    - Без даты в имени — без изменений.
    """
    from datetime import date as dt_date

    warns: List[str] = []
    if not files:
        return [], warns

    passthrough: List[Dict] = []
    one_c: List[Dict] = []
    tessa: List[Dict] = []
    msp: List[Dict] = []
    dated_other: List[Dict] = []

    for f in files:
        name = str(f.get("name") or "")
        stem = Path(name).stem
        nl = name.lower()

        if nl.endswith(".json") and re.match(r"(?i)^(1с_|1c_|lc_|лк_|lk_)", stem):
            one_c.append(f)
            continue
        if nl.startswith("tessa_"):
            tessa.append(f)
            continue
        sl = stem.lower()
        if sl.startswith("msp_") or sl.startswith("msp-"):
            msp.append(f)
            continue

        if _max_date_in_stem(stem) is not None:
            dated_other.append(f)
            continue

        passthrough.append(f)

    kept: List[Dict] = []
    kept_ids: set = set()

    def _add(fitem: Dict) -> None:
        pid = id(fitem["path"])
        if pid not in kept_ids:
            kept_ids.add(pid)
            kept.append(fitem)

    for f in passthrough:
        _add(f)

    one_c_fallback: List[Dict] = []
    buckets_1c: Dict[str, List[Dict]] = {}
    for f in one_c:
        stem = Path(f["name"]).stem
        fam = _one_c_file_family(stem)
        sk = _one_c_snapshot_sort_key(stem)
        if fam is None or sk is None:
            one_c_fallback.append(f)
        else:
            buckets_1c.setdefault(fam, []).append(f)
    _keep_all_one_c_families = frozenset({"dogovor", "kontr", "spravochniki"})
    for _fam, lst in buckets_1c.items():
        if _fam in _keep_all_one_c_families:
            for f in lst:
                _add(f)
            continue
        rated: List[Tuple[tuple, Dict]] = []
        for f in lst:
            sk = _one_c_snapshot_sort_key(Path(f["name"]).stem)
            if sk is not None:
                rated.append((sk, f))
        if not rated:
            continue
        best_sk = max(k for k, _ in rated)
        for k, f in rated:
            if k == best_sk:
                _add(f)
    for f in one_c_fallback:
        dated_other.append(f)

    buckets_t: Dict[str, List[Dict]] = {}
    for f in tessa:
        buckets_t.setdefault(_tessa_kind_key(Path(f["name"]).stem), []).append(f)
    for kind_key, lst in buckets_t.items():
        best_f, tessa_warn = _pick_best_tessa_bucket_file(lst, kind_key)
        if tessa_warn:
            warns.append(tessa_warn)
        _add(best_f)

    buckets_m: Dict[str, List[Dict]] = {}
    for f in msp:
        stem = Path(f["name"]).stem
        bk = _msp_project_bucket(stem) or stem.lower()
        buckets_m.setdefault(str(bk), []).append(f)
    for lst in buckets_m.values():
        by_month: Dict[tuple[int, int], List[Dict]] = {}
        undated: List[Dict] = []
        for f in lst:
            stem = Path(f["name"]).stem
            md = _max_date_in_stem(stem)
            if md is None:
                undated.append(f)
                continue
            by_month.setdefault((md.year, md.month), []).append(f)
        for month_lst in by_month.values():
            rated = []
            for f in month_lst:
                stem = Path(f["name"]).stem
                md = _max_date_in_stem(stem)
                rated.append(((md or dt_date.min, _file_mtime(f["path"])), f))
            best_f = max(rated, key=lambda x: x[0])[1]
            _add(best_f)
        for f in undated:
            _add(f)

    buckets_o: Dict[str, List[Dict]] = {}
    for f in dated_other:
        stem = Path(f["name"]).stem
        ext = Path(f["name"]).suffix.lower()
        fam = _generic_stem_family(stem) + "|" + ext
        buckets_o.setdefault(fam, []).append(f)
    for fam, lst in buckets_o.items():
        if "resursi" in fam or "resursy" in fam:
            for f in lst:
                _add(f)
            continue
        rated = []
        for f in lst:
            stem = Path(f["name"]).stem
            md = _max_date_in_stem(stem)
            rated.append(((md or dt_date.min, _file_mtime(f["path"])), f))
        best_f = max(rated, key=lambda x: x[0])[1]
        _add(best_f)
        # other_*_rd / other_*_pd: если самый свежий файл без колонки «Статус»
        # (slim), дополнительно берём самый свежий файл семейства СО статусом —
        # иначе RD-01 не видит «отменено» и завышает «Всего разделов».
        _best_stem = Path(best_f["name"]).stem.lower()
        if (
            _best_stem.startswith("other_")
            and (_best_stem.endswith("_rd") or _best_stem.endswith("_pd"))
            and not _rd_pd_plan_csv_has_status(best_f["path"])
        ):
            _with_status: List[Tuple[tuple, Dict]] = []
            for f in lst:
                if id(f["path"]) == id(best_f["path"]):
                    continue
                if not _rd_pd_plan_csv_has_status(f["path"]):
                    continue
                stem = Path(f["name"]).stem
                md = _max_date_in_stem(stem)
                _with_status.append(((md or dt_date.min, _file_mtime(f["path"])), f))
            if _with_status:
                _add(max(_with_status, key=lambda x: x[0])[1])

    total_in = len(files)
    total_kept = len(kept)
    if total_kept < total_in:
        warns.append(
            f"Режим последних снимков: файлов было {total_in}, к загрузке оставлено {total_kept}. "
            "Полная история (все даты в web/): переменная BI_ANALYTICS_WEB_LATEST_ONLY=0."
        )

    return kept, warns


def scan_new_csv_demo_files(extensions: tuple = (".csv",)) -> List[Dict]:
    """
    Демо-файлы из new_csv/ — подмешиваются к загрузке из web/, чтобы локально
    открывались финансовые отчёты и ДЗ/КЗ (колонки budget plan, дебиторка и т.д.).
    """
    base = Path(__file__).resolve().parent
    demo_dir = base / "new_csv"
    if not demo_dir.is_dir():
        return []
    names = (
        "sample_project_data_fixed.csv",
        "sample_budget_data.csv",
        "sample_debit_credit_data.csv",
        "sample_technique_data.csv",
    )
    out: List[Dict] = []
    for name in names:
        p = demo_dir / name
        if p.is_file() and p.suffix.lower() in extensions:
            out.append({
                "path": p,
                "name": name,
                "rel_path": f"new_csv/{name}",
            })
    return out


def get_web_file_list() -> List[str]:
    """Список относительных путей всех CSV в web/ (для отображения в UI)."""
    return [f["rel_path"] for f in scan_web_files()]


class _FileWrapper(io.BytesIO):
    """
    Обёртка над BytesIO — притворяется Streamlit UploadedFile.
    load_data() ожидает объект с атрибутом .name и методом .seek().
    """
    def __init__(self, content: bytes, name: str):
        super().__init__(content)
        self.name = name


def _infer_file_type(df: pd.DataFrame, file_name: str) -> str:
    """
    Определяет тип файла по содержимому DataFrame и имени файла.
    Вызывается только для файлов, чей тип не определён по имени (_infer_file_type_by_name).

    Возвращает: 'project' | 'resources' | 'technique' | 'budget' | 'debit_credit' | 'unknown'
    """
    name_lower = file_name.lower()
    cols = [str(c).lower() for c in df.columns]

    # MSP-файл: подчёркивания или пробелы в типичных заголовках
    has_msp_cols = any(c in cols for c in [
        "базовое_начало", "базовое_окончание", "причины_отклонений",
        "уровень_структуры",
        "базовое начало", "базовое окончание", "причины отклонений",
        "уровень структуры", "шифр_пд_и_рд", "шифр пд и рд",
    ])
    has_task_name = any(c in cols for c in ["название", "task name", "задача"])
    has_dates = any(c in cols for c in ["начало", "plan start", "старт план"])
    if has_msp_cols or (has_task_name and has_dates and "начало" in cols):
        return "msp"

    # Ресурсы: контрагент/подрядчик + недели или даты в заголовках (01.01.2026)
    has_contractor = any(c in cols for c in ["контрагент", "подрядчик", "contractor"])
    has_weeks = any("неделя" in c or "недели" in c for c in cols)
    has_date_headers = any(re.match(r"^\d{2}\.\d{2}\.\d{4}", c.strip()) for c in cols)
    if has_contractor and (has_weeks or has_date_headers):
        if "среднее за неделю" in " ".join(cols) or "техник" in name_lower:
            return "technique"
        return "resources"

    # Бюджет
    if "budget" in name_lower or "бюджет" in name_lower or "бддс" in name_lower:
        return "budget"
    has_scenario = any(c in cols for c in ["сценарий", "scenario"])
    if has_scenario:
        return "budget"

    # Дебиторка/Кредиторка
    if "debit" in name_lower or "credit" in name_lower or "задолженност" in name_lower:
        return "debit_credit"
    has_contract = any(c in cols for c in ["договор", "contract", "номер договора"])
    has_sum = any(c in cols for c in ["сумма", "sum", "выплачено"])
    if has_contract and has_sum:
        return "debit_credit"

    # Техника по содержимому
    if any("среднее за неделю" in c for c in cols):
        return "technique"
    if "technique" in name_lower or "техник" in name_lower or "tehnik" in name_lower:
        return "technique"

    return "unknown"


# ── Запись в SQLite ──────────────────────────────────────────────────────────

def _create_version(cur, files_count: int) -> int:
    """Создаёт новую запись версии и возвращает её id."""
    cur.execute(
        "INSERT INTO web_versions (status, files_count) VALUES ('pending', ?)",
        (files_count,)
    )
    return cur.lastrowid


def _count_version_ingested_files(cur, version_id: int) -> int:
    """Число файлов, реально записанных в web_files для версии (не «файлов в скане»)."""
    row = cur.execute(
        "SELECT COUNT(*) AS n FROM web_files WHERE version_id=?",
        (int(version_id),),
    ).fetchone()
    return int(row["n"] if row else 0)


def _load_json_array_file(filepath: Path) -> List[dict]:
    """JSON-массив объектов (Dogovor, Kontr, spravochniki, Projekts)."""
    encodings = ("utf-8-sig", "utf-8", "cp1251")
    for enc in encodings:
        try:
            raw = filepath.read_text(encoding=enc)
            data = json.loads(raw)
            if isinstance(data, list):
                return [r for r in data if isinstance(r, dict)]
            return []
        except Exception:
            continue
    return []


def _ingest_json_array(
    cur,
    version_id: int,
    file_info: Dict,
    file_type: str,
    filepath: Path,
    rel_path: str,
) -> tuple[bool, int]:
    records = _load_json_array_file(filepath)
    if not records:
        return False, 0
    file_id = _register_file(cur, version_id, file_info, file_type, len(records))
    cur.executemany(
        """
        INSERT INTO web_data (version_id, file_id, file_type, source_file, row_data)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                version_id,
                file_id,
                file_type,
                rel_path,
                json.dumps(r, ensure_ascii=False, default=str),
            )
            for r in records
        ],
    )
    return True, len(records)


def _register_file(cur, version_id: int, file_info: Dict, file_type: str, rows_count: int) -> int:
    """Регистрирует файл в web_files и возвращает его id."""
    cur.execute(
        """
        INSERT INTO web_files (version_id, file_name, rel_path, file_type, rows_count)
        VALUES (?, ?, ?, ?, ?)
        """,
        (version_id, file_info["name"], file_info["rel_path"], file_type, rows_count)
    )
    return cur.lastrowid


def _incremental_ingest_enabled() -> bool:
    """Инкрементальная загрузка: копировать строки неизменённых файлов из прошлой
    версии вместо повторного парсинга. По умолчанию ВКЛ. Отключить: =0."""
    return str(os.environ.get("BI_ANALYTICS_INCREMENTAL_INGEST", "1")).strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _file_signature(path: Path) -> Optional[str]:
    """Сигнатура файла ``size:mtime_ns`` для детекции изменений между версиями.

    FTP-скачивание пишет новый файл через os.replace → у изменённого файла меняется
    mtime. Совпадение size+mtime считаем «файл не изменился» — строки копируем из
    прошлой версии, без повторного парсинга.
    """
    try:
        stt = Path(path).stat()
        return f"{int(stt.st_size)}:{int(stt.st_mtime_ns)}"
    except Exception:
        return None


def _load_base_version_file_map(cur, base_version_id: int) -> Dict[str, list]:
    """rel_path → список записей web_files базовой версии (id, file_type, rows, sig).

    Один rel_path может иметь несколько записей (файл ресурсов → 'resources' + 'gdrs_fact').
    """
    out: Dict[str, list] = {}
    try:
        rows = cur.execute(
            "SELECT id, rel_path, file_type, rows_count, sig FROM web_files WHERE version_id=?",
            (int(base_version_id),),
        ).fetchall()
    except Exception:
        return out
    for r in rows:
        out.setdefault(str(r["rel_path"]), []).append(
            {
                "id": int(r["id"]),
                "file_type": r["file_type"],
                "rows_count": int(r["rows_count"] or 0),
                "sig": r["sig"],
            }
        )
    return out


def _copy_version_file(cur, new_version_id: int, base_version_id: int, base_file: dict, file_info: Dict) -> int:
    """Копирует один файл (web_files + его web_data) из базовой версии в новую.

    Возвращает число скопированных строк.
    """
    new_id = _register_file(
        cur, new_version_id, file_info, base_file["file_type"], int(base_file["rows_count"] or 0)
    )
    cur.execute(
        """
        INSERT INTO web_data (version_id, file_id, file_type, source_file, row_data)
        SELECT ?, ?, file_type, source_file, row_data
        FROM web_data
        WHERE version_id=? AND file_id=?
        """,
        (int(new_version_id), int(new_id), int(base_version_id), int(base_file["id"])),
    )
    n = cur.rowcount
    return int(n) if isinstance(n, int) and n >= 0 else int(base_file["rows_count"] or 0)


def _save_rows(cur, version_id: int, file_id: int, file_type: str, source_file: str, df: pd.DataFrame):
    """Сохраняет строки DataFrame в web_data как JSON."""
    # Колонки, которые нужно привести к строкам перед JSON (datetime / period).
    _dt_cols = list(df.select_dtypes(include=["datetime64[ns]", "datetimetz"]).columns)
    _period_cols: list = []
    for col in df.columns:
        if df[col].dtype == object or col in _dt_cols:
            continue
        try:
            if hasattr(df[col], "dt") and hasattr(df[col].dt, "to_timestamp"):
                _period_cols.append(col)
        except Exception:
            pass

    # Копируем только если реально есть что конвертировать — на больших кадрах
    # (ресурсы/MSP) лишний df.copy() заметно тормозит и ест память.
    if _dt_cols or _period_cols:
        df_copy = df.copy()
        for col in _dt_cols + _period_cols:
            df_copy[col] = df_copy[col].astype(str)
    else:
        df_copy = df

    rows = df_copy.where(pd.notnull(df_copy), None).to_dict(orient="records")
    cur.executemany(
        """
        INSERT INTO web_data (version_id, file_id, file_type, source_file, row_data)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (version_id, file_id, file_type, source_file, json.dumps(r, ensure_ascii=False, default=str))
            for r in rows
        ]
    )


# ── Основная функция загрузки ────────────────────────────────────────────────

def load_all_from_web(progress=None) -> Dict:
    """
    Сканирует web/, парсит CSV, сохраняет в SQLite.
    Возвращает {"loaded": N, "skipped": N, "errors": [], "version_id": int|None}

    ``progress`` — необязательный колбэк ``progress(done: int, total: int, name: str)``,
    вызывается перед обработкой каждого файла. Нужен для прогресс-бара с оценкой ETA
    в UI (кнопки загрузки). Исключения в колбэке подавляются.
    """
    from data_loader import load_data, ensure_data_session_state, update_session_with_loaded_file

    def _emit_progress(done: int, total: int, name: str) -> None:
        if progress is None:
            return
        try:
            progress(int(done), int(total), str(name))
        except Exception:
            pass

    result = {
        "loaded": 0,
        "skipped": 0,
        "errors": [],
        "warnings": [],
        "diagnostics": [],
        "version_id": None,
    }

    files = scan_web_files(extensions=(".csv", ".json"))
    files, dedupe_warns = _dedupe_scan_files_by_identity(files)
    result["warnings"].extend(dedupe_warns)
    if web_load_latest_snapshots_only():
        files, snap_warns = pick_latest_snapshot_files(files)
        result["warnings"].extend(snap_warns)
    if not files:
        result["errors"].append(
            "Нет CSV/JSON для загрузки: положите в web/ актуальные выгрузки MSP/1С/TESSA."
        )
        return result

    ensure_data_session_state()
    # Сбрасываем session_state перед новой загрузкой
    st.session_state.project_data = None
    st.session_state["project_data_all_snapshots"] = None
    st.session_state.resources_data = None
    st.session_state.technique_data = None
    st.session_state.debit_credit_data = None
    st.session_state.loaded_files_info = {}
    st.session_state.tessa_data = None
    st.session_state["tessa_tasks_data"] = None
    st.session_state["reference_contractors"] = None
    st.session_state["reference_krstates"] = None
    st.session_state["reference_docstates"] = None
    st.session_state["reference_execdockinds"] = None
    st.session_state["reference_1c_dannye"] = None
    st.session_state["reference_partner_to_project"] = None

    import sqlite3
    conn = sqlite3.connect(get_web_db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    # Настройки под массовую загрузку: пересборка идёт одной транзакцией и БД в любой
    # момент восстановима из web/, поэтому можно ослабить durability ради скорости.
    #   synchronous=OFF   — не ждём fsync на каждый коммит журнала (главный выигрыш);
    #   temp_store=MEMORY — временные структуры в RAM;
    #   cache_size ~128MB — меньше вытеснений страниц при сотнях тысяч INSERT;
    #   busy_timeout      — параллельный читатель ждёт, а не падает с "database is locked".
    try:
        cur.execute("PRAGMA busy_timeout=30000")
        cur.execute("PRAGMA synchronous=OFF")
        cur.execute("PRAGMA temp_store=MEMORY")
        cur.execute("PRAGMA cache_size=-131072")
    except Exception:
        pass

    # Инициализируем до try: используется после commit для гидрации сессии.
    _incremental_copied = 0

    try:
        version_id = _create_version(cur, len(files))
        result["version_id"] = version_id
        total_rows = 0

        # ── Инкрементальная загрузка: карта файлов базовой версии ─────────────
        # Для неизменённых файлов (совпадает size+mtime) копируем строки из базовой
        # версии, не парся заново. Базовая версия — активная, иначе последняя success.
        _incremental = _incremental_ingest_enabled()
        _base_version_id: Optional[int] = None
        _base_file_map: Dict[str, list] = {}
        if _incremental:
            try:
                _brow = cur.execute(
                    "SELECT id FROM web_versions WHERE is_active=1 AND id<>? ORDER BY id DESC LIMIT 1",
                    (version_id,),
                ).fetchone()
                if not _brow:
                    _brow = cur.execute(
                        "SELECT id FROM web_versions WHERE status='success' AND id<>? ORDER BY id DESC LIMIT 1",
                        (version_id,),
                    ).fetchone()
                if _brow:
                    _base_version_id = int(_brow["id"])
                    _base_file_map = _load_base_version_file_map(cur, _base_version_id)
            except Exception:
                _base_version_id = None
                _base_file_map = {}

        _total_files = len(files)
        for _file_idx, file_info in enumerate(files, start=1):
            filepath: Path = file_info["path"]
            name: str = file_info["name"]
            rel_path: str = file_info["rel_path"]
            _emit_progress(_file_idx, _total_files, name)

            # ── Инкремент: файл не изменился с базовой версии → копируем строки ──
            if _incremental and _base_version_id is not None:
                _sig_now = _file_signature(filepath)
                _base_entries = _base_file_map.get(rel_path)
                if (
                    _sig_now
                    and _base_entries
                    and all(str(be["sig"] or "") == _sig_now for be in _base_entries)
                ):
                    try:
                        _copied = 0
                        for be in _base_entries:
                            _copied += _copy_version_file(
                                cur, version_id, _base_version_id, be, file_info
                            )
                        total_rows += _copied
                        _incremental_copied += 1
                        result["loaded"] += 1
                        result["diagnostics"].append(
                            {
                                "file": rel_path,
                                "type": _base_entries[0]["file_type"],
                                "rows": int(_copied),
                                "incremental": True,
                            }
                        )
                        continue
                    except Exception as _inc_e:
                        # Любой сбой копирования → откатываемся к обычному парсингу
                        # этого файла (строки могли частично записаться — удалим их).
                        try:
                            cur.execute(
                                "DELETE FROM web_data WHERE version_id=? AND file_id IN "
                                "(SELECT id FROM web_files WHERE version_id=? AND rel_path=?)",
                                (version_id, version_id, rel_path),
                            )
                            cur.execute(
                                "DELETE FROM web_files WHERE version_id=? AND rel_path=?",
                                (version_id, rel_path),
                            )
                        except Exception:
                            pass
                        result.setdefault("warnings", []).append(
                            _format_skip_reason(
                                rel_path, "инкремент не удался, парсинг заново", str(_inc_e)
                            )
                        )

            try:
                # ── Определяем тип файла через ETL-парсер ──────────────────
                # Сначала определяем тип по имени файла (не нужен DataFrame)
                file_type_by_name = _infer_file_type_by_name(name)
                name_lower = name.lower()
                # JSON с «неузнаваемым» именем, но содержимым как обороты 1С (dannye):
                # иначе _infer_file_type_by_name даёт skip и файл никогда не попадает в reference_1c_dannye.
                if name_lower.endswith(".json") and file_type_by_name == "skip":
                    probe = _load_1c_json_spravochniki(filepath)
                    if _json_df_matches_1c_turnover_columns(probe):
                        file_type_by_name = "budget_json"

                # ── Особый случай: файлы ресурсов (multi-level header) ──────
                if file_type_by_name == "resources":
                    df = _load_resources_file(filepath)
                    if df is None or df.empty:
                        result["skipped"] += 1
                        # Это warning, а не error: нестандартный формат
                        # КОНКРЕТНОГО файла не должен превращать всю
                        # версию в partial и блокировать активацию.
                        result["warnings"].append(
                            _format_skip_reason(
                                rel_path,
                                "ресурсы не распознаны",
                                "ожидался многострочный заголовок (Проект;Подрядчик;…); "
                                "проверьте разделитель ; или , и кодировку",
                            )
                        )
                        continue
                    file_type = "resources"
                    file_id = _register_file(cur, version_id, file_info, file_type, len(df))
                    _save_rows(cur, version_id, file_id, file_type, name, df)
                    total_rows += len(df)
                    result["loaded"] += 1
                    df.attrs["data_type"] = "resources"
                    update_session_with_loaded_file(df, rel_path)
                    try:
                        from dashboards.gdrs_resursi import load_resursi_file

                        gdrs_df = load_resursi_file(filepath)
                        if gdrs_df is not None and not gdrs_df.empty:
                            gdrs_df = gdrs_df.copy()
                            gdrs_df["__source_file"] = name
                            gdrs_file_id = _register_file(
                                cur, version_id, file_info, "gdrs_fact", len(gdrs_df)
                            )
                            _save_rows(
                                cur, version_id, gdrs_file_id, "gdrs_fact", name, gdrs_df
                            )
                            total_rows += len(gdrs_df)
                    except Exception:
                        pass
                    result["diagnostics"].append({
                        "file": rel_path,
                        "type": "resources",
                        "rows": int(len(df)),
                        "columns": [str(c) for c in df.columns[:25]],
                    })
                    continue

                # ── Пропускаем ненужные файлы ──────────────────────────────
                if file_type_by_name == "skip":
                    result["skipped"] += 1
                    result["warnings"].append(
                        _format_skip_reason(rel_path, "тип файла не используется дашбордом")
                    )
                    continue

                # ── JSON файлы из 1С ─────────────────────────────────────────
                if file_type_by_name == "debit_credit_json":
                    df = _load_1c_json_dk(filepath)
                    if df is not None and not df.empty:
                        file_type = "debit_credit"
                        file_id = _register_file(cur, version_id, file_info, file_type, len(df))
                        _save_rows(cur, version_id, file_id, file_type, name, df)
                        total_rows += len(df)
                        result["loaded"] += 1
                        df.attrs["data_type"] = "debit_credit"
                        update_session_with_loaded_file(df, rel_path)
                        result["diagnostics"].append({
                            "file": rel_path, "type": "debit_credit", "rows": int(len(df)),
                            "columns": [str(c) for c in df.columns[:25]],
                        })
                    else:
                        result["skipped"] += 1
                        result["warnings"].append(
                            _format_skip_reason(rel_path, "JSON DK не распознан")
                        )
                    continue

                if file_type_by_name in (
                    "dogovor_json",
                    "kontr_json",
                    "projekts_json",
                    "spravochniki_json",
                ):
                    ok, nrows = _ingest_json_array(
                        cur,
                        version_id,
                        file_info,
                        file_type_by_name,
                        filepath,
                        rel_path,
                    )
                    if ok:
                        total_rows += nrows
                        result["loaded"] += 1
                        result["diagnostics"].append({
                            "file": rel_path,
                            "type": file_type_by_name,
                            "rows": int(nrows),
                        })
                    else:
                        result["skipped"] += 1
                        result["warnings"].append(
                            _format_skip_reason(rel_path, f"{file_type_by_name} пуст или не JSON-массив")
                        )
                    continue

                if file_type_by_name == "reference_json":
                    ok, nrows = _ingest_json_array(
                        cur,
                        version_id,
                        file_info,
                        "spravochniki_json",
                        filepath,
                        rel_path,
                    )
                    ref_df = _load_1c_json_spravochniki(filepath)
                    if ref_df is not None and not ref_df.empty:
                        st.session_state["reference_contractors"] = ref_df
                    if ok:
                        total_rows += nrows
                        result["loaded"] += 1
                        result["diagnostics"].append({
                            "file": rel_path,
                            "type": "spravochniki_json",
                            "rows": int(nrows),
                            "columns": (
                                [str(c) for c in ref_df.columns[:25]]
                                if ref_df is not None and not ref_df.empty
                                else []
                            ),
                        })
                    else:
                        result["skipped"] += 1
                        result["warnings"].append(
                            _format_skip_reason(rel_path, "справочник 1С пуст или не распознан")
                        )
                    continue

                if file_type_by_name == "budget_json":
                    ddf = _load_1c_json_spravochniki(filepath)
                    if ddf is not None and not ddf.empty:
                        ddf.attrs["data_type"] = "reference_dannye"
                        file_type_rd = "reference_dannye"
                        file_id = _register_file(
                            cur, version_id, file_info, file_type_rd, len(ddf)
                        )
                        _save_rows(cur, version_id, file_id, file_type_rd, name, ddf)
                        total_rows += len(ddf)
                        if st.session_state.get("reference_1c_dannye") is None:
                            st.session_state["reference_1c_dannye"] = ddf
                        else:
                            st.session_state["reference_1c_dannye"] = pd.concat(
                                [st.session_state["reference_1c_dannye"], ddf],
                                ignore_index=True,
                            )
                        pmap = _build_partner_project_map_from_dannye(ddf)
                        st.session_state["reference_partner_to_project"] = (
                            _merge_partner_project_maps(
                                st.session_state.get("reference_partner_to_project"),
                                pmap,
                            )
                        )
                        result["loaded"] += 1
                        result["diagnostics"].append({
                            "file": rel_path,
                            "type": "reference_dannye",
                            "rows": int(len(ddf)),
                            "columns": [str(c) for c in ddf.columns[:30]],
                            "partner_project_keys": int(len(pmap)),
                        })
                    else:
                        result["skipped"] += 1
                        result["warnings"].append(
                            _format_skip_reason(rel_path, "1С «данные» пусты или не распознаны")
                        )
                    continue

                # ── TESSA файлы ──────────────────────────────────────────────
                if file_type_by_name == "tessa_tasks":
                    df = _load_tessa_file(filepath)
                    if df is not None and not df.empty:
                        file_type = "tessa_tasks"
                        file_id = _register_file(cur, version_id, file_info, file_type, len(df))
                        _save_rows(cur, version_id, file_id, file_type, name, df)
                        total_rows += len(df)
                        result["loaded"] += 1
                        df.attrs["data_type"] = "tessa_tasks"
                        if st.session_state.get("tessa_tasks_data") is None:
                            st.session_state["tessa_tasks_data"] = df
                        else:
                            st.session_state["tessa_tasks_data"] = pd.concat(
                                [st.session_state["tessa_tasks_data"], df], ignore_index=True
                            )
                        result["diagnostics"].append({
                            "file": rel_path, "type": "tessa_tasks", "rows": int(len(df)),
                            "columns": [str(c) for c in df.columns[:25]],
                        })
                    else:
                        result["skipped"] += 1
                        result["warnings"].append(
                            _format_skip_reason(rel_path, "TESSA (задачи) пуст или не распознан")
                        )
                    continue

                if file_type_by_name == "tessa":
                    df = _load_tessa_file(filepath)
                    if df is not None and not df.empty:
                        file_type = "tessa"
                        file_id = _register_file(cur, version_id, file_info, file_type, len(df))
                        _save_rows(cur, version_id, file_id, file_type, name, df)
                        total_rows += len(df)
                        result["loaded"] += 1
                        if st.session_state.get("tessa_data") is None:
                            st.session_state["tessa_data"] = df
                        else:
                            st.session_state["tessa_data"] = pd.concat(
                                [st.session_state["tessa_data"], df], ignore_index=True
                            )
                        result["diagnostics"].append({
                            "file": rel_path, "type": "tessa", "rows": int(len(df)),
                            "columns": [str(c) for c in df.columns[:25]],
                        })
                    else:
                        result["skipped"] += 1
                        result["warnings"].append(
                            _format_skip_reason(rel_path, "TESSA пуст или не распознан")
                        )
                    continue

                # ── Справочники CSV (KrStates, DocStates) ────────────────────
                if file_type_by_name == "reference_csv":
                    ref_df = _load_reference_csv(filepath)
                    if ref_df is not None and not ref_df.empty:
                        nl_ref = name.lower()
                        if "krstate" in nl_ref:
                            ref_key = "krstates"
                        elif "execdockind" in nl_ref:
                            ref_key = "execdockinds"
                        else:
                            ref_key = "docstates"
                        st.session_state[f"reference_{ref_key}"] = ref_df
                        result["loaded"] += 1
                        result["diagnostics"].append({
                            "file": rel_path,
                            "type": f"reference_{ref_key}",
                            "rows": int(len(ref_df)),
                            "columns": [str(c) for c in ref_df.columns[:25]],
                        })
                    else:
                        result["skipped"] += 1
                        result["warnings"].append(
                            _format_skip_reason(rel_path, "справочник CSV пуст или не прочитан")
                        )
                    continue

                # ── RD/PD plan файлы (other_*_rd.csv | other_*_pd.csv) ──────
                # B-12/13 (2026-05-07): отдельный header-detect (`_load_rd_plan_file`).
                # Раньше шли через `load_data → _read_csv_best_effort` с `header=0` —
                # а в этих CSV 1-я строка это длинный заголовок проекта. Получали
                # `Unnamed: 0..7` и план «РД по Договору» оставался пустым.
                # B-12/13.2: симметричная поддержка `pd_plan` (other_*_pd.csv) с
                # тем же парсером — fallback в дашборде «Просрочка выдачи ПД».
                if file_type_by_name in ("rd_plan", "pd_plan"):
                    _doc_kind = file_type_by_name
                    df = _load_rd_plan_file(filepath)
                    if df is not None and not df.empty:
                        file_type = _doc_kind
                        df.attrs["data_type"] = _doc_kind
                        # B-12/13.2 (2026-05-07): project name из имени файла
                        # `other_<project>_<DD.MM.YYYY>_<rd|pd>.csv` — без него
                        # dashboard не может развести строки по проектам (в самих
                        # CSV нет колонки «project name»).
                        try:
                            from config import get_msp_project_name_map as _get_msp_name_map
                            _MSP_NAME_MAP = _get_msp_name_map()
                            _stem = name.lower().replace(".csv", "")
                            _parts = _stem.split("_")
                            _proj_token = _parts[1] if len(_parts) > 2 and _parts[0] == "other" else ""
                            _proj_label = _MSP_NAME_MAP.get(_proj_token, "")
                            if _proj_label and "project name" not in df.columns:
                                df["project name"] = _proj_label
                            _snap = None
                            for _p in reversed(_parts):
                                _snap = _parse_snapshot_date(_p)
                                if _snap is not None:
                                    break
                            if _snap is not None and "snapshot_date" not in df.columns:
                                df["snapshot_date"] = pd.Timestamp(_snap)
                        except Exception:
                            pass
                        file_id = _register_file(cur, version_id, file_info, file_type, len(df))
                        _save_rows(cur, version_id, file_id, file_type, name, df)
                        total_rows += len(df)
                        result["loaded"] += 1
                        # update_session_with_loaded_file подставит df в session_state по типу;
                        # сохраним отдельный ключ для совместимости.
                        _ss_key = "rd_plan_data" if _doc_kind == "rd_plan" else "pd_plan_data"
                        try:
                            if st.session_state.get(_ss_key) is None:
                                st.session_state[_ss_key] = df
                            else:
                                st.session_state[_ss_key] = pd.concat(
                                    [st.session_state[_ss_key], df], ignore_index=True
                                )
                        except Exception:
                            pass
                        update_session_with_loaded_file(df, rel_path)
                        result["diagnostics"].append({
                            "file": rel_path,
                            "type": _doc_kind,
                            "rows": int(len(df)),
                            "columns": [str(c) for c in df.columns[:25]],
                            "header_note": str(df.attrs.get("rd_plan_header_note", "")),
                        })
                    else:
                        result["skipped"] += 1
                        result["warnings"].append(
                            _format_skip_reason(rel_path, f"{_doc_kind} пуст или не распознан")
                        )
                    continue

                # ── Загружаем через data_loader ─────────────────────────────
                content = filepath.read_bytes()
                wrapped = _FileWrapper(content, name)
                # silent=True — пакетная загрузка из web/, любые ошибки
                # должны попадать только в result["errors"], а не в st.error
                # поверх UI клиента на release.
                df = load_data(wrapped, file_name=name, silent=True)

                if df is None or df.empty:
                    result["skipped"] += 1
                    # warning, не error: проблема в формате конкретного
                    # файла, не в коде. Не должна блокировать активацию.
                    result["warnings"].append(
                        _format_skip_reason(
                            rel_path,
                            "не удалось прочитать CSV",
                            "пустой файл, неверный разделитель (; ,), кодировка (UTF-8 / Windows-1251) или нет заголовков",
                        )
                    )
                    continue

                # ── Уточняем тип (с учётом содержимого) ────────────────────
                if file_type_by_name in ("unknown",):
                    file_type = _infer_file_type(df, name)
                else:
                    file_type = file_type_by_name

                # Если всё ещё unknown — берём тип от data_loader
                if file_type == "unknown":
                    file_type = df.attrs.get("data_type", "project")

                # Пропускаем skip-файлы (могли определиться только по колонкам)
                if file_type == "skip":
                    result["skipped"] += 1
                    result["warnings"].append(
                        _format_skip_reason(rel_path, "тип файла не используется дашбордом")
                    )
                    continue

                if file_type == "unknown":
                    preview = ", ".join(str(c) for c in list(df.columns)[:15])
                    result["warnings"].append(
                        f"{rel_path}: тип файла не распознан; первые колонки: {preview}"
                    )
                    result["skipped"] += 1
                    continue

                # ── MSP-файлы: применяем ремаппинг колонок ─────────────────
                if file_type == "msp":
                    # Извлекаем имя проекта из имени файла: msp_dmitrovsky1_... → dmitrovsky1
                    # Формат: msp_<project_slug>_<date>.csv (slug может содержать «_»)
                    parts = name.replace(".csv", "").split("_")
                    if len(parts) >= 3:
                        project_name = "_".join(parts[1:-1])
                    else:
                        project_name = parts[1] if len(parts) > 1 else name.replace(".csv", "")
                    # Дата снимка: последний сегмент до расширения (02-03-2026)
                    snapshot_date = _parse_snapshot_date(parts[-1]) if len(parts) > 2 else None
                    df = _apply_msp_column_mapping(df, project_name)
                    if snapshot_date is not None:
                        df["snapshot_date"] = pd.Timestamp(snapshot_date)
                    file_type = "project"
                elif file_type in ("resources", "technique"):
                    # Для ГДРС/техники: дата снимка из имени файла (other_01-02-2026_resursi.csv и т.п.)
                    _parts = name.replace(".csv", "").replace(".CSV", "").split("_")
                    _snap = None
                    for _p in reversed(_parts):
                        _snap = _parse_snapshot_date(_p)
                        if _snap is not None:
                            break
                    if _snap is not None and "snapshot_date" not in df.columns:
                        df["snapshot_date"] = pd.Timestamp(_snap)

                file_id = _register_file(cur, version_id, file_info, file_type, len(df))
                _save_rows(cur, version_id, file_id, file_type, name, df)

                total_rows += len(df)
                result["loaded"] += 1

                # Сразу кладём в session_state для немедленного отображения
                if file_type in ("resources", "technique"):
                    session_type = file_type
                elif file_type == "debit_credit":
                    session_type = "debit_credit"
                else:
                    session_type = "project"
                df.attrs["data_type"] = session_type
                update_session_with_loaded_file(df, rel_path)
                result["diagnostics"].append({
                    "file": rel_path,
                    "type": file_type,
                    "rows": int(len(df)),
                    "columns": [str(c) for c in df.columns[:25]],
                })

            except Exception as e:
                result["errors"].append(
                    _format_skip_reason(rel_path, "исключение при обработке", str(e))
                )
                result["skipped"] += 1

        # ── Backfill сигнатур: сохраняем size:mtime для всех файлов этой версии
        # (и распарсенных, и скопированных) — чтобы СЛЕДУЮЩАЯ загрузка могла
        # определить неизменённые файлы и не парсить их заново.
        try:
            for _fi in files:
                _s = _file_signature(_fi["path"])
                if _s:
                    cur.execute(
                        "UPDATE web_files SET sig=? WHERE version_id=? AND rel_path=?",
                        (_s, version_id, _fi["rel_path"]),
                    )
        except Exception:
            pass

        if _incremental_copied:
            result.setdefault("warnings", []).append(
                f"Инкрементальная загрузка: {_incremental_copied} неизменённых файлов "
                f"скопировано из версии id={_base_version_id} без повторного парсинга."
            )

        # Обновляем статус версии (warnings не делают partial, только errors)
        status = "partial" if result["errors"] else "success"
        cur.execute(
            "UPDATE web_versions SET status=?, rows_count=? WHERE id=?",
            (status, total_rows, version_id)
        )
        # Политика активации:
        # - `success`: становится активной, старые деактивируются.
        # - `partial`: активируется, ЕСЛИ её прогресс не хуже последней
        #   success-версии (loaded ≥ prev.loaded И rows ≥ prev.rows).
        #   Иначе оставляем активной прежнюю success — чтобы неполная
        #   загрузка не ломала уже работающий дашборд.
        #
        # Зачем так: один-единственный нестандартный CSV (например
        # AI/other_…__resursi.csv с двухстрочной шапкой без 'Проект;Подрядчик')
        # раньше превращал любую новую версию в partial и её НЕ активировал.
        # Получалось, что клиент годами сидел на устаревшей версии,
        # хотя 26 из 27 файлов в новой выгрузке корректные.
        if status == "success":
            # Не активировать «успешную», но более бедную выгрузку, если предыдущая
            # success-версия содержит строго больше файлов И строк (как у partial ниже).
            prev_success = cur.execute(
                "SELECT id, files_count, rows_count FROM web_versions "
                "WHERE status='success' AND id<>? ORDER BY id DESC LIMIT 1",
                (version_id,),
            ).fetchone()
            curr_files = int(len(files))
            curr_rows = int(total_rows or 0)
            prev_files = int(prev_success["files_count"] or 0) if prev_success else 0
            prev_rows = int(prev_success["rows_count"] or 0) if prev_success else 0
            keep_prev = (
                prev_success is not None
                and curr_files < prev_files
                and curr_rows < prev_rows
            )
            cur.execute("UPDATE web_versions SET is_active=0")
            if keep_prev:
                cur.execute(
                    "UPDATE web_versions SET is_active=1 WHERE id=?",
                    (int(prev_success["id"]),),
                )
                result.setdefault("warnings", []).append(
                    f"Версия {version_id} загружена как success, но НЕ сделана активной: "
                    f"меньше данных, чем версия id={prev_success['id']} "
                    f"({curr_files}/{prev_files} файлов в скане, {curr_rows}/{prev_rows} строк). "
                    f"Активной оставлена прежняя полная выгрузка. Выберите новую версию вручную в «Версия данных», если это снимок нужен."
                )
            else:
                cur.execute(
                    "UPDATE web_versions SET is_active=1 WHERE id=?", (version_id,)
                )
        else:
            # Сравниваем с текущей активной (или последней success), по числу
            # реально ingested-файлов в web_files — не со «сканом» files_count.
            prev_ref = cur.execute(
                "SELECT id, rows_count FROM web_versions "
                "WHERE is_active=1 AND id<>? ORDER BY id DESC LIMIT 1",
                (version_id,),
            ).fetchone()
            if prev_ref is None:
                prev_ref = cur.execute(
                    "SELECT id, rows_count FROM web_versions "
                    "WHERE status='success' AND id<>? ORDER BY id DESC LIMIT 1",
                    (version_id,),
                ).fetchone()
            curr_ingested = _count_version_ingested_files(cur, version_id)
            curr_rows = int(total_rows or 0)
            prev_ingested = (
                _count_version_ingested_files(cur, int(prev_ref["id"])) if prev_ref else 0
            )
            prev_rows = int(prev_ref["rows_count"] or 0) if prev_ref else 0
            err_n = len(result.get("errors") or [])
            promote_partial = (
                curr_ingested > 0
                and (
                    prev_ref is None
                    or curr_rows >= prev_rows
                    or curr_ingested >= prev_ingested
                    or (
                        prev_ingested > 0
                        and curr_ingested >= prev_ingested - err_n
                    )
                )
            )
            if promote_partial:
                cur.execute("UPDATE web_versions SET is_active=0")
                cur.execute(
                    "UPDATE web_versions SET is_active=1 WHERE id=?", (version_id,)
                )
                if prev_ref is not None:
                    result.setdefault("warnings", []).append(
                        f"Версия {version_id} помечена как partial (есть ошибки "
                        f"по отдельным файлам), но активирована — валидные файлы "
                        f"доступны в отчётах (ingested {curr_ingested}/{prev_ingested} "
                        f"файлов, {curr_rows}/{prev_rows} строк)."
                    )
            else:
                cur.execute("UPDATE web_versions SET is_active=0")
                cur.execute(
                    "UPDATE web_versions SET is_active=1 WHERE id=?",
                    (int(prev_ref["id"]),),
                )
                result.setdefault("warnings", []).append(
                    f"Версия {version_id} сохранена как partial и НЕ активирована "
                    f"(ingested {curr_ingested}/{prev_ingested} файлов, "
                    f"{curr_rows}/{prev_rows} строк) — активной оставлена "
                    f"предыдущая версия id={prev_ref['id']}."
                )

        # Автоочистка архива снимков: храним только N последних версий
        # (активную не трогаем). Делаем в этой же транзакции — атомарно с commit.
        try:
            from web_schema import prune_old_versions

            _pruned = prune_old_versions(cur=cur)
            if _pruned:
                result.setdefault("warnings", []).append(
                    f"Архив снимков: удалено старых версий — {len(_pruned)} "
                    f"(id: {', '.join(str(x) for x in _pruned[:10])}"
                    f"{'…' if len(_pruned) > 10 else ''})."
                )
        except Exception as _prune_e:
            result.setdefault("warnings", []).append(
                f"Не удалось очистить архив старых версий: {_prune_e}"
            )

        conn.commit()

    except Exception as e:
        conn.rollback()
        result["errors"].append(f"Критическая ошибка: {e}")
    finally:
        cur.close()
        conn.close()

    # ── Все снимки до дедупликации — для «Причины отклонений» → вкладка «Динамика по периодам» (ось по дате файла) ──
    if st.session_state.get("project_data") is not None:
        st.session_state["project_data_all_snapshots"] = st.session_state.project_data.copy()
        st.session_state.project_data = _deduplicate_project_snapshots(
            st.session_state.project_data
        )
    else:
        st.session_state["project_data_all_snapshots"] = None

    # ── Инкремент: скопированные файлы не наполняли session_state в цикле
    # (парсинг пропущен). Гидрируем сессию из активной версии БД — иначе
    # контракт данных и дашборды увидят пустую сессию (project_data=0).
    if _incremental_copied:
        try:
            from web_schema import get_active_version_id

            _active_id = get_active_version_id()
            if _active_id:
                read_version_to_session(int(_active_id))
        except Exception as _hydr_e:
            result.setdefault("warnings", []).append(
                f"Инкремент: не удалось гидрировать сессию из БД: {_hydr_e}"
            )

    return result


def _infer_file_type_by_name(file_name: str) -> str:
    """
    Быстрое определение типа файла ТОЛЬКО по имени (без чтения содержимого).
    Использует шаблоны имён из ETL-соглашения, без зависимости от etl-модуля.

    Возвращает: 'msp' | 'resources' | 'budget' | 'debit_credit' |
                'skip' | 'unknown'

    'msp'  — MSP-файл задач (msp_*.csv)
    'resources' — файл ресурсов (*resursi*.csv)
    'skip' — tessa_*, rd_plan, справочники — не нужны для дашбордов
    'unknown' — нужна проверка содержимого
    """
    name_lower = file_name.lower()
    # Убираем расширение для упрощённого сравнения
    stem = name_lower.rsplit(".", 1)[0]

    # ── MSP файлы проектов ───────────────────────────────────────────────────
    if stem.startswith("msp_") or stem.startswith("msp-") or "msp_" in name_lower:
        return "msp"

    # ── Файлы ресурсов (ГДРС) ────────────────────────────────────────────────
    if (
        "resursi" in stem
        or "resursy" in stem
        or "ресурс" in stem
        or "gdrs" in stem
        or "_gdrc" in stem
    ):
        return "resources"

    # ── Техника по имени ─────────────────────────────────────────────────────
    if any(
        x in stem
        for x in (
            "tehnik",
            "tehnika",
            "technique",
            "техник",
            "texnik",
            "other_techn",
        )
    ):
        return "technique"

    # ── Плановая выдача РД (other_*_rd.csv) ─────────────────────────────────
    if stem.startswith("other_") and stem.endswith("_rd"):
        return "rd_plan"

    # ── Плановая выдача ПД (other_*_pd.csv) ─────────────────────────────────
    # Симметрично «rd_plan»: если появятся файлы плана выдачи ПД с таким же
    # шаблоном имени, их парсит тот же `_load_rd_plan_file` (header-detect),
    # а UI берёт fallback-вью из `pd_plan_data`.
    if stem.startswith("other_") and stem.endswith("_pd"):
        return "pd_plan"

    # ── TESSA: задачи (CardId, KindName, …) — отдельный тип, чтобы join с Id по правкам ──
    # Имя «tessa_*_task.csv» (единственное task) должно считаться задачами, не только *_tasks*.
    # Поддерживаются оба формата: старый (tessa_DD_MM_YYYY_HH-MM_task.csv) и новый
    # (tessa_DD-MM-YYYY-HH-MM-task.csv) с дефисом перед kind.
    if (
        "tessa_tasks" in stem
        or (stem.startswith("tessa_") and (
            "tasks" in stem
            or stem.endswith("_task") or stem.endswith("-task")
            or stem.endswith("_tasks") or stem.endswith("-tasks")
        ))
    ):
        return "tessa_tasks"

    # ── TESSA файлы (карточки / Id) ──────────────────────────────────────────
    if stem.startswith("tessa_"):
        return "tessa"

    # ── Справочники KrStates / DocStates ─────────────────────────────────────
    if stem in ("docstates", "krstates", "execdockinds"):
        return "reference_csv"

    # ── Статические файлы — пропускаем ───────────────────────────────────────
    if stem in ("ui_tasks",):
        return "skip"

    # ── Демо new_csv: дебиторка / бюджет обороты ─────────────────────────────
    if "debit" in stem and "credit" in stem:
        return "debit_credit"
    if (
        "debitor" in stem
        or "debtor" in stem
        or "zadol" in stem
        or "дз" in stem
        or "кз" in stem
    ):
        return "debit_credit"
    if (
        "sample_budget" in stem
        or stem.startswith("sample_budget")
        or "bdds" in stem
        or "бддс" in stem
        or "budget" in stem
        or "бюджет" in stem
        or "oborot" in stem
        or "оборот" in stem
        or "oborotypopodryad" in stem
        or "oboroty_po_podryad" in stem
        or "оборотыпоподряд" in stem
        or "oborot_po_podryad" in stem
    ):
        return "budget"

    # ── 1C JSON файлы ──────────────────────────────────────────────────────────
    if name_lower.endswith(".json"):
        sl = stem  # уже lower-case (из name_lower)
        # Дебиторка: отдельные выгрузки *_DK.json и *_DK1.json (оба должны загружаться и concat в session).
        if re.search(r"(?:^|_)dk1?$", sl):
            return "debit_credit_json"
        if "dtkttpopodryad" in sl or "dtkt" in sl or "дткт" in sl:
            return "debit_credit_json"
        # Справочники контрагентов для ГДРС: по ключевым словам или префиксу 1c_/lc_* + «sprav…»
        _ref_prefix = sl.startswith(("1c_", "lc_", "1с_", "лк_", "lk_"))
        if (
            "spravochniki" in sl
            or "spravochnik" in sl
            or "справочник" in sl
            or (_ref_prefix and ("sprav" in sl or "справ" in sl))
        ):
            return "reference_json"
        if "dogovor" in sl:
            return "dogovor_json"
        if "kontr" in sl and "spravochnik" not in sl and "справочник" not in sl:
            return "kontr_json"
        if "projekts" in sl or "projects" in sl or "projekt" in sl:
            return "projekts_json"
        if "dannye" in sl or "данные" in sl:
            return "budget_json"
        if _ref_prefix or sl.startswith("1c") or sl.startswith("1с"):
            if any(
                k in sl
                for k in (
                    "oborot",
                    "оборот",
                    "budget",
                    "бюджет",
                    "bdds",
                    "бддс",
                    "bdr",
                    "бдр",
                )
            ):
                return "budget_json"
        return "skip"

    return "unknown"


# ── Чтение версии из БД в session_state ─────────────────────────────────────


def _web_db_mtime() -> float:
    try:
        return float(Path(get_web_db_path()).stat().st_mtime)
    except Exception:
        return 0.0


@st.cache_data(ttl=600, show_spinner=False)
def _load_version_data(
    version_id: int, file_type: str, _db_mtime: float = 0.0
) -> Optional[pd.DataFrame]:
    """Загружает строки нужного типа из web_data для указанной версии."""
    import sqlite3
    try:
        conn = sqlite3.connect(get_web_db_path())
        # Порядок строк = порядок вставки при загрузке (= порядок строк в CSV). Без ORDER BY
        # порядок не определён — ломается обход дерева и колонка section (родитель ур.2, «Ковенанты»).
        rows = conn.execute(
            "SELECT row_data, source_file FROM web_data WHERE version_id=? AND file_type=? ORDER BY id ASC",
            (version_id, file_type),
        ).fetchall()
        conn.close()
        if not rows:
            return None
        records = []
        for row_json, src_file in rows:
            rec = json.loads(row_json)
            if src_file:
                rec["__source_file"] = str(src_file)
            # Для старых версий БД: если snapshot_date не сохранён в row_data,
            # восстанавливаем его из имени source_file (other_01-02-2026_resursi.csv и т.п.).
            if "snapshot_date" not in rec and src_file:
                try:
                    parts = str(src_file).replace("\\", "/").split("/")[-1].replace(".csv", "").replace(".CSV", "").split("_")
                    snap = None
                    for p in reversed(parts):
                        snap = _parse_snapshot_date(p)
                        if snap is not None:
                            break
                    if snap is not None:
                        rec["snapshot_date"] = pd.Timestamp(snap)
                except Exception:
                    pass
            records.append(rec)
        return pd.DataFrame(records)
    except Exception:
        return None


def _restore_date_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Восстанавливает типы данных после чтения из SQLite (где всё хранится как строки).
    - datetime-колонки → pd.Timestamp
    - Period-колонки (_month, _quarter, _year) → pd.Period
    - _day-колонки → datetime.date
    """
    # Основные datetime-колонки
    for col in ("plan start", "plan end", "base start", "base end", "actual finish", "snapshot_date"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # Period-колонки. Парсим по уникальным значениям (месяцы/кварталы/годы имеют
    # низкую кардинальность относительно строк) — это эквивалент построчного
    # apply, но pd.Period вызывается один раз на уникальное значение.
    def _periods_from_series(s: pd.Series, freq: str) -> pd.Series:
        def _conv(x):
            return (
                pd.Period(x, freq)
                if pd.notna(x) and x not in ("NaT", "None", "nan", "")
                else pd.NaT
            )

        mapping = {v: _conv(v) for v in pd.unique(s)}
        return s.map(mapping)

    month_cols = [c for c in df.columns if c.endswith("_month") or c.endswith("_quarter") or c.endswith("_year")]
    for col in month_cols:
        if df[col].dtype == object:
            try:
                if col.endswith("_month"):
                    df[col] = _periods_from_series(df[col], "M")
                elif col.endswith("_quarter"):
                    df[col] = _periods_from_series(df[col], "Q")
                elif col.endswith("_year"):
                    df[col] = _periods_from_series(df[col], "Y")
            except Exception:
                pass

    # _day-колонки
    day_cols = [c for c in df.columns if c.endswith("_day")]
    for col in day_cols:
        if col in df.columns and df[col].dtype == object:
            try:
                df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
            except Exception:
                pass

    return df


@st.cache_data(ttl=600, show_spinner=False)
def _build_project_frames(
    version_id: int, _db_mtime: float = 0.0
) -> tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """Готовые кадры проектов из БД: (все снимки, дедуплицированные).

    Тяжёлая цепочка преобразований (восстановление дат/периодов, иерархия MSP,
    section по дереву задач, дедупликация снимков) кешируется на (version_id, mtime),
    чтобы не пересчитывать на каждый rerun/клик по фильтру. Все вызываемые
    функции чистые (не читают session_state), а st.cache_data возвращает копию,
    поэтому мутации у вызывающих не отравляют кэш.
    """
    dfs = []
    for ftype in ("project", "budget"):
        df = _load_version_data(version_id, ftype, _db_mtime)
        if df is not None and not df.empty:
            df = df.copy()
            df = _restore_date_columns(df)
            # Старые версии в БД могли иметь «ЛОТ» в section — пересчитываем родителя ур.2 при каждом чтении
            if ftype == "project":
                ensure_msp_hierarchy_columns(df)
                df = _fill_section_from_task_tree(df)
            dfs.append(df)

    combined = pd.concat(dfs, ignore_index=True) if dfs else None
    if combined is None:
        return None, None
    return combined, _deduplicate_project_snapshots(combined)


def read_version_to_session(version_id: int):
    """
    Загружает данные выбранной версии из SQLite в session_state.
    project_data  — объединение project + budget + debit_credit типов
    resources_data — данные ресурсов (для ГДРС)
    technique_data — данные техники (для ГДРС)
    """
    from data_loader import ensure_data_session_state

    ensure_data_session_state()
    _db_mtime = _web_db_mtime()

    # ── Данные проектов (без дебиторки — она в отдельном session_state) ─────
    combined, project_data = _build_project_frames(version_id, _db_mtime)
    st.session_state["project_data_all_snapshots"] = (
        combined.copy() if combined is not None else None
    )
    st.session_state.project_data = project_data

    deb = _load_version_data(version_id, "debit_credit", _db_mtime)
    if deb is not None and not deb.empty:
        st.session_state.debit_credit_data = deb
        _dk_adv = float(getattr(deb, "attrs", {}).get("dk_summary_advance_rub", 0) or 0)
        if _dk_adv > 0:
            st.session_state["dk_summary_advance_rub"] = _dk_adv
    else:
        st.session_state.debit_credit_data = None

    # ── Данные ресурсов ──────────────────────────────────────────────────────
    res = _load_version_data(version_id, "resources", _db_mtime)
    st.session_state.resources_data = res if (res is not None and not res.empty) else None

    # ── Данные техники ───────────────────────────────────────────────────────
    tech = _load_version_data(version_id, "technique", _db_mtime)
    st.session_state.technique_data = tech if (tech is not None and not tech.empty) else None

    # ── Данные TESSA (исполнительная документация) ────────────────────────
    tessa = _load_version_data(version_id, "tessa", _db_mtime)
    if tessa is not None and not tessa.empty:
        st.session_state["tessa_data"] = _tessa_drop_cancelled_tag_rows(tessa)
    elif st.session_state.get("tessa_data") is None:
        st.session_state["tessa_data"] = None

    # ── TESSA Tasks (отдельный файл для join CardId ↔ DocID) ───────────────
    tt = _load_version_data(version_id, "tessa_tasks", _db_mtime)
    if tt is not None and not tt.empty:
        st.session_state["tessa_tasks_data"] = tt
    elif st.session_state.get("tessa_tasks_data") is None:
        st.session_state["tessa_tasks_data"] = None

    # ── План выдачи РД/ПД (other_*_rd.csv / other_*_pd.csv) ────────────────
    # Восстанавливаем из БД, иначе после перезапуска (сессия пустая, версия
    # читается из БД) дашборды «Просрочка выдачи РД/ПД» теряют источник плана
    # (`rd_plan_data`/`pd_plan_data` кладётся только при импорте файлов).
    for _plan_kind, _plan_key in (("rd_plan", "rd_plan_data"), ("pd_plan", "pd_plan_data")):
        _plan_df = _load_version_data(version_id, _plan_kind, _db_mtime)
        if _plan_df is not None and not _plan_df.empty:
            st.session_state[_plan_key] = _plan_df
        elif st.session_state.get(_plan_key) is None:
            st.session_state[_plan_key] = None

    # ── Обороты 1С (dannye / бюджетные JSON): в БД как reference_dannye ───────
    rd_ref = _load_version_data(version_id, "reference_dannye", _db_mtime)
    if rd_ref is not None and not rd_ref.empty:
        st.session_state["reference_1c_dannye"] = rd_ref
        try:
            st.session_state["reference_partner_to_project"] = (
                _build_partner_project_map_from_dannye(rd_ref)
            )
        except Exception:
            st.session_state["reference_partner_to_project"] = None
    else:
        st.session_state["reference_1c_dannye"] = None
        st.session_state["reference_partner_to_project"] = None

    # ── Справочники (KrStates / DocStates) ────────────────────────────────
    # Загружаются из CSV при load_all_from_web(), не из БД;
    # если уже в session_state — не трогаем
    if st.session_state.get("reference_krstates") is None:
        kr_path = Path(__file__).resolve().parent / "web" / "KrStates.csv"
        if kr_path.exists():
            st.session_state["reference_krstates"] = _load_reference_csv(kr_path)
    if st.session_state.get("reference_execdockinds") is None:
        _edk_path = Path(__file__).resolve().parent / "web" / "ExecDocKinds.csv"
        if _edk_path.exists():
            st.session_state["reference_execdockinds"] = _load_reference_csv(_edk_path)
