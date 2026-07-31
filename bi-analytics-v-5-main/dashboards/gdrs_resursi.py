# -*- coding: utf-8 -*-
"""
B-16/17 ГДРС (2026-05-07) — загрузка ресурсов и агрегация план/факт по СКУДу.

Источники:
  • web/AI/other_<DD-MM-YYYY>_resursi.csv
        - один файл = один календарный месяц.
        - формат: 1-я строка — «надстрока» (1 неделя | 2 неделя | …),
          2-я строка — заголовки колонок: ID Проекта | Наименование проекта |
          Подрядчик (ИЛИ ID Подрядчика + Подрядчик_new + Подрядчик_old) |
          Тип ресурсов (рабочие/техника) | <дата1> | <дата2> | … | <Тип ресурсов>.
        - данные начинаются с 3-й строки.
        - встречается 3 формата шапки (январь — c колонкой «среднее значение за день»
          внутри каждой недели; март — без неё; апрель — расширенный набор колонок
          подрядчика).

  • web/1с_<...>_Dogovor.json
        - список договоров; ключевые поля: ID_Контрагента, ID_Проекта,
          Наименование_Контрагента, Наименование_Проекта, Наименование_Договора,
          Количество_Людей, Количество_Техники, Дата_Начала_Договора,
          Дата_Окончания_Договора, Сумма_Договора.
        - используется как ПЛАН по ключу (ID_Проекта, ID_Контрагента).

  • web/1с_*dannye*.json (или *dannye*.json в web / web/AI)
        - обороты 1С: поля «ДоговорКонтрагента», «СтатьяОборотов»; по нормализованному
          наименованию договора связываются с «Наименование_Договора» из Dogovor
          для колонки «Вид работы» в таблице ГДРС.

  • web/1с_<...>_spravochniki.json
        - fallback для ПЛАНа (КоличествоРаботников / КоличествоСпецТехники)
          по ключу (ID_Проекта, ID_Контрагента).

Архитектура (long-формат):
    long DataFrame: project_id, project_name, contractor_id, contractor_name,
    vid_resursa ∈ {"Рабочие","Техника"}, date (datetime), fact (float).

    Дополнительно к long-факту строится PLAN-таблица per (project_id × contractor_id × vid).

API:
    load_resursi_files(paths) -> long_fact_df
    load_plan_from_dogovor(json_path) -> plan_df
    load_plan_from_spravochniki(json_path) -> plan_df
    merge_plan(dogovor_plan, sprav_plan) -> plan_df  (Dogovor приоритет, fallback Sprav)
    build_main_table(long, plan, period_from, period_to, vid)  (Таб 1, Скрин 11)
    build_summary_table(long, plan, …)                          (Таб 3, Скрин 5)
"""
from __future__ import annotations

import functools
import json
import re
from bisect import bisect_right
from datetime import datetime as _dt
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

import numpy as np
import pandas as pd


@functools.lru_cache(maxsize=200000)
def _fast_parse_date_cached(s: str):
    """Быстрый разбор строки-даты с кэшем (строки дат массово повторяются).

    Сохраняет семантику ``_snapshot_history``: сначала ISO, затем dayfirst-fallback.
    ``datetime.fromisoformat`` на порядок быстрее ``pd.to_datetime`` на скаляре —
    а кэш по строке убирает повторный разбор одинаковых дат (в ГДРС это десятки
    тысяч одинаковых значений на загрузку).
    """
    try:
        return pd.Timestamp(_dt.fromisoformat(s))
    except Exception:
        pass
    try:
        return pd.Timestamp(_dt.fromisoformat(s[:19]))
    except Exception:
        pass
    d = pd.to_datetime(s, errors="coerce", dayfirst=True)
    return None if pd.isna(d) else pd.Timestamp(d)


def _fast_parse_date(d_raw: object):
    """Скаляр → ``pd.Timestamp`` или ``None`` (быстро, с кэшем)."""
    if d_raw is None:
        return None
    if isinstance(d_raw, pd.Timestamp):
        return d_raw
    if isinstance(d_raw, _dt):
        return pd.Timestamp(d_raw)
    s = str(d_raw).strip()
    if not s or s.lower() in ("nan", "none", "null", "nat"):
        return None
    return _fast_parse_date_cached(s)


def _dearrow_object_columns(df: "pd.DataFrame") -> "pd.DataFrame":
    """pandas 3.0: строковые колонки по умолчанию arrow-backed (dtype ``str``).

    План ГДРС многократно делает построчный доступ (``.tolist()``/groupby-chop/
    итерации) по ``project_id``/``contractor_id``/``contract_name`` — на arrow это
    дорогие ``pyarrow.compute`` вызовы (в профиле — ~8с в ``arrow.array.__getitem__``).
    Перевод строк в numpy ``object`` ускоряет scalar-доступ и groupby. Идемпотентно.
    """
    if df is None or getattr(df, "empty", True):
        return df
    try:
        conv = {}
        for col, dt in df.dtypes.items():
            s = str(dt).lower()
            if s == "str" or s.startswith("string") or "[pyarrow]" in s:
                conv[col] = "object"
        if conv:
            df = df.astype(conv)
    except Exception:
        pass
    return df

# =====================================================================
# Парсер resursi.csv
# =====================================================================

_DATE_RE = re.compile(r"^(\d{1,2})\.{1,2}(\d{1,2})\.(\d{2}|\d{4})$")


def _is_date_label(val: object) -> bool:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return False
    s = str(val).strip()
    return bool(_DATE_RE.match(s))


def _is_avg_label(val: object) -> bool:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return False
    return "сред" in str(val).strip().lower()


def _parse_date_label(val: object) -> Optional[pd.Timestamp]:
    if not _is_date_label(val):
        return None
    s = str(val).strip().replace("..", ".")
    try:
        return pd.to_datetime(s, dayfirst=True, errors="coerce")
    except Exception:
        return None


def _read_csv_best_effort(path: Path) -> pd.DataFrame:
    """Читает CSV не интерпретируя 1-ю строку как заголовок (header=None)."""
    last_err: Optional[Exception] = None
    for enc in ("utf-8-sig", "utf-8", "cp1251", "cp866"):
        for sep in (";", ",", "\t", "|"):
            try:
                df = pd.read_csv(
                    path,
                    encoding=enc,
                    sep=sep,
                    header=None,
                    engine="python",
                    dtype=str,
                    keep_default_na=False,
                )
                if df.shape[1] >= 4:
                    return df
            except Exception as e:
                last_err = e
                continue
    if last_err is not None:
        raise last_err
    return pd.DataFrame()


@dataclass
class _ResursiSchema:
    """Схема одного `resursi.csv`: позиции колонок и список (col_idx, date)."""
    col_id_project: Optional[int]  # None если в файле нет колонки «ID Проекта»
    col_name_project: int
    col_contractor: int  # позиция «человекочитаемого» названия подрядчика (new или legacy)
    col_contractor_fallback: Optional[int]  # Подрядчик_old — если new пустой
    col_id_contractor: Optional[int]  # отдельная колонка ID подрядчика, если есть
    col_vid: int  # позиция колонки «Тип ресурсов»
    date_columns: list[tuple[int, pd.Timestamp]]
    header_row: int  # индекс строки с заголовками (0-based)


def _detect_schema(df_raw: pd.DataFrame) -> Optional[_ResursiSchema]:
    """Найти строку-заголовок (где есть «ID Проекта» или «Наименование проекта»)."""
    if df_raw.empty:
        return None
    n_scan = min(6, len(df_raw))
    date_row = None
    best_count = 0
    for r in range(n_scan):
        row = df_raw.iloc[r].tolist()
        cnt = sum(1 for v in row if _is_date_label(v))
        if cnt > best_count:
            best_count = cnt
            date_row = r
    if date_row is None or best_count == 0:
        return None

    text_row = None
    for r in range(date_row, -1, -1):
        row = df_raw.iloc[r].astype(str).str.strip().str.lower()
        if any(
            ("id проекта" in v) or ("наименование проекта" in v) or (v == "проект")
            for v in row
        ):
            text_row = r
            break
    if text_row is None:
        return None

    header_row = max(text_row, date_row)
    above_rows = df_raw.iloc[: header_row + 1].astype(str).fillna("")
    combined_headers: list[str] = []
    for col in range(df_raw.shape[1]):
        parts = []
        for r in range(header_row + 1):
            v = above_rows.iloc[r, col].strip() if col < above_rows.shape[1] else ""
            if v and v.lower() not in {"nan", "none"} and v not in parts:
                parts.append(v)
        combined_headers.append(" | ".join(parts))
    headers = combined_headers
    headers_norm = [h.strip().lower() for h in headers]

    def _find_first(*kws: str, exclude_idx: Optional[int] = None) -> Optional[int]:
        for i, h in enumerate(headers_norm):
            if i == exclude_idx:
                continue
            if all(k in h for k in kws):
                return i
        return None

    col_id_project = _find_first("id", "проект")
    if col_id_project is None:
        col_id_project = _find_first("идентификатор", "проект")
    col_name_project = _find_first("наименование", "проект")
    if col_name_project is None:
        col_name_project = _find_first("проект", exclude_idx=col_id_project)

    col_id_contractor = _find_first("id", "подряд")
    col_contractor_new = _find_first("подрядчик_new")
    col_contractor_old = _find_first("подрядчик_old")
    col_contractor = col_contractor_new or _find_first("подряд", exclude_idx=col_id_contractor)
    if col_contractor is None and col_contractor_old is not None:
        col_contractor = col_contractor_old
    col_vid = _find_first("тип", "ресурс")

    if col_name_project is None or col_contractor is None or col_vid is None:
        return None

    date_row_values = df_raw.iloc[date_row].tolist()
    date_columns: list[tuple[int, pd.Timestamp]] = []
    for i, raw in enumerate(date_row_values):
        ts = _parse_date_label(raw)
        if ts is not None:
            date_columns.append((i, ts))
    if not date_columns:
        return None

    return _ResursiSchema(
        col_id_project=col_id_project,
        col_name_project=col_name_project,
        col_contractor=col_contractor,
        col_contractor_fallback=col_contractor_old,
        col_id_contractor=col_id_contractor,
        col_vid=col_vid,
        date_columns=date_columns,
        header_row=header_row,
    )


_NAME_NOISE_RE = re.compile(r"[\s\.,\-_/\\\"'«»()\[\]]+")
_NAME_LEGAL_RE = re.compile(
    r"\b(ооо|ао|зао|пао|оао|ип|оу|ук|нко|спк|кфх|апсх|нпф|чоп|снт|тсж)\b",
    re.IGNORECASE,
)
# Хвост «ИНН …» / «ОГРН …» в Kontr без скобок: «СТРОЙСЕРВИС ООО ИНН5009105977».
_NAME_REG_ID_RE = re.compile(
    r"\b(?:инн|огрн|кпп)\s*[:№#]?\s*\d{9,15}\b",
    re.IGNORECASE,
)


def normalize_name(s: object) -> str:
    """Нормализация названия (контрагента, проекта) для fuzzy-match.

    Убирает легальный префикс/суффикс ООО/АО/ЗАО/…, регистр, пробелы,
    скобочные пояснения, кавычки.
    Примеры:
      «ООО Альфа С (БЛОК U3 U4)»  → «альфас»
      «АЛЬФА С ООО»                → «альфас»
      «ООО "СК Сети"»              → «сксети»
      «АО Марафон»                 → «марафон»
      «СТРОЙСЕРВИС ООО ИНН5009105977» → «стройсервис»
      «ПЛАСТСЕРВИС ООО (ИНН 3316012350)» → «пластсервис»
    """
    if s is None:
        return ""
    txt = str(s).strip()
    if not txt:
        return ""
    return _normalize_name_cached(txt)


@functools.lru_cache(maxsize=100000)
def _normalize_name_cached(txt: str) -> str:
    txt = re.sub(r"\(.*?\)", " ", txt)
    txt = txt.replace("«", " ").replace("»", " ").replace('"', " ").replace("'", " ")
    txt = _NAME_REG_ID_RE.sub(" ", txt)
    # «ООО_» / «ООО.» — подчёркивание/точка слитно с ОПФ ломают \\b у _NAME_LEGAL_RE.
    txt = re.sub(r"_+", " ", txt)
    txt = _NAME_LEGAL_RE.sub(" ", txt)
    txt = _NAME_NOISE_RE.sub("", txt).casefold()
    return txt


_CONTRACT_SIG_RE = re.compile(
    r"(?i)(?<![\w/])(\d{1,4})\s*[-_]\s*[СC]\s*[АA]\s*[/ _]?\s*(\d{2,4})(?![\w/])"
)
_CONTRACT_SIG_SKA_RE = re.compile(
    r"(?i)(?<![\w/])(\d{1,4})\s*[-_]\s*[СC]\s*[КK]\s*[АA]\s*[/ _]?\s*(\d{2,4})(?![\w/])"
)


def contract_signatures(s: object) -> list[str]:
    """Из строки договора извлечь сигнатуры «NN-СА/YY» → ключ «nn-са/yy».

    Сопоставляет короткие строки оборотов («106-СА/25 от …») с длинными из Dogovor
    («Дог. № 106-СА/25 …_ДС …»).
    """
    if s is None:
        return []
    txt = str(s).strip()
    if not txt:
        return []
    return list(_contract_signatures_cached(txt))


@functools.lru_cache(maxsize=100000)
def _contract_signatures_cached(txt: str) -> tuple:
    sigs: list[str] = []
    for m in _CONTRACT_SIG_RE.finditer(txt):
        sigs.append(f"{m.group(1)}-са/{m.group(2)}".casefold())
    for m in _CONTRACT_SIG_SKA_RE.finditer(txt):
        sigs.append(f"{m.group(1)}-ска/{m.group(2)}".casefold())
    return tuple(sigs)


def _pick_best_articles(arts: set[str], contract_hint: str) -> str:
    """Если для одного договора несколько статей — предпочесть строку с «Лот» или номер лота из подсказки."""
    if not arts:
        return ""
    if len(arts) == 1:
        return next(iter(arts))
    hint = str(contract_hint or "")
    hm = re.search(r"лот\s*№?\s*0*(\d+)", hint, re.IGNORECASE)
    if hm:
        num = re.escape(hm.group(1))
        rx = re.compile(rf"лот\s*№?\s*0*{num}\b", re.IGNORECASE)
        matched = [a for a in arts if rx.search(a)]
        if len(matched) == 1:
            return matched[0]
    lot_arts = {a for a in arts if "лот" in a.casefold()}
    if len(lot_arts) == 1:
        return next(iter(lot_arts))
    return " · ".join(sorted(arts))


def _normalize_vid(raw: object) -> str:
    """Нормализация значения «Тип ресурсов» → 'Рабочие' | 'Техника' | ''."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return ""
    s = str(raw).strip().lower()
    if not s:
        return ""
    if "рабоч" in s or "люд" in s or "people" in s or "worker" in s:
        return "Рабочие"
    if "техн" in s or "машин" in s or "механ" in s or "оборуд" in s or "equip" in s:
        return "Техника"
    return ""


def _coerce_int(val: object) -> Optional[float]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    if s == "" or s.lower() in {"nan", "none", "null"}:
        return None
    try:
        return float(s)
    except Exception:
        return None


_CONTRACTOR_ID_PLACEHOLDERS = frozenset({"", "nan", "none", "null", "#н/д", "н/д", "#n/d", "n/d"})

def _sanitize_contractor_id(raw: object) -> str:
    s = str(raw or "").strip()
    if not s or s.casefold() in _CONTRACTOR_ID_PLACEHOLDERS:
        return ""
    if s.startswith("#"):
        return ""
    return s if _is_uuid_like(s) else ""

def _contractor_name_from_row(row: pd.Series, schema: _ResursiSchema) -> str:
    for col in (schema.col_contractor, schema.col_contractor_fallback):
        if col is None or col >= len(row):
            continue
        name = str(row.iloc[col]).strip()
        if name and name.casefold() not in {"nan", "none"}:
            return name
    return ""

def load_resursi_file(path: Path) -> pd.DataFrame:
    """Загрузить один resursi.csv → long DataFrame.

    Возвращаемые столбцы:
        project_id, project_name, contractor_id (опц., может быть пустой строкой),
        contractor_name, vid_resursa ∈ {Рабочие, Техника}, date (datetime), fact (float).
    """
    raw = _read_csv_best_effort(Path(path))
    schema = _detect_schema(raw)
    if schema is None:
        return pd.DataFrame(
            columns=[
                "project_id", "project_name", "contractor_id",
                "contractor_name", "vid_resursa", "date", "fact",
            ]
        )

    body = raw.iloc[schema.header_row + 1 :].reset_index(drop=True).copy()
    out_rows: list[dict] = []
    for _, row in body.iterrows():
        proj_id = (
            str(row.iloc[schema.col_id_project]).strip()
            if schema.col_id_project is not None
            else ""
        )
        proj_name = str(row.iloc[schema.col_name_project]).strip()
        if not proj_name or proj_name.lower() in {"nan", "none"}:
            continue
        contractor_id = (
            _sanitize_contractor_id(row.iloc[schema.col_id_contractor])
            if schema.col_id_contractor is not None
            else ""
        )
        contractor_name = _contractor_name_from_row(row, schema)
        if not contractor_name:
            continue
        vid = _normalize_vid(row.iloc[schema.col_vid])
        if not vid:
            continue
        for col_idx, ts in schema.date_columns:
            if col_idx >= len(row):
                continue
            v = _coerce_int(row.iloc[col_idx])
            if v is None:
                continue
            out_rows.append(
                {
                    "project_id": proj_id,
                    "project_name": proj_name,
                    "contractor_id": contractor_id,
                    "contractor_name": contractor_name,
                    "vid_resursa": vid,
                    "date": ts,
                    "fact": float(v),
                }
            )
    if not out_rows:
        return pd.DataFrame(
            columns=[
                "project_id", "project_name", "contractor_id",
                "contractor_name", "vid_resursa", "date", "fact",
            ]
        )
    out = pd.DataFrame(out_rows)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out[out["date"].notna()].copy()
    return out


_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _is_uuid_like(s: object) -> bool:
    if s is None:
        return False
    return bool(_UUID_RE.match(str(s).strip()))


def _strip_display_name_artifacts(name: object) -> str:
    """Убирает хвостовые/начальные «мусорные» символы из имени для UI (напр. «ООО_»)."""
    s = str(name or "").strip()
    if not s:
        return s
    s = re.sub(r"^[\s_\-/\\.,]+|[\s_\-/\\.,]+$", "", s).strip()
    return s


def _contractor_name_display_rank(name: str) -> tuple:
    """Меньше — лучше: без хвостового _, короче."""
    s = str(name).strip()
    trailing = bool(re.search(r"[_\.,\-\s/\\]+$", s))
    leading = bool(re.search(r"^[_\.,\-\s/\\]+", s))
    return (trailing, leading, len(s), s.casefold())


def _pick_canonical_name(names: pd.Series) -> Optional[str]:
    """Самое популярное (mode) НЕ-UUID имя в серии. Используется для канонизации."""
    cnt = names.astype(str).str.strip().value_counts()
    cnt = cnt[~cnt.index.to_series().apply(_is_uuid_like)]
    if cnt.empty:
        return None
    max_cnt = cnt.max()
    top = [str(n) for n in cnt[cnt == max_cnt].index]
    return _strip_display_name_artifacts(min(top, key=_contractor_name_display_rank))


def _gdrs_blank_project_name(val) -> bool:
    s = str(val or "").strip()
    return (not s) or s.casefold() in ("nan", "none", "<na>", "nat", "—", "-", "null")


def _canonicalize_project_names(df: pd.DataFrame) -> pd.DataFrame:
    """Подменяет UUID-подобные `project_name` на каноническое человекочитаемое имя.
    Канонический выбор — самое популярное не-UUID имя для того же `project_id`,
    или (если ID нет/пуст) — самое популярное по нормализованному имени.
    Также схлопывает варианты типа «Дмитровский1» / «Дмитровский-1».
    Пустые имена тоже заполняются из `project_id`, если для него известно имя.
    """
    if df is None or df.empty:
        return df
    work = df.copy()
    work["__name_norm__"] = work["project_name"].astype(str).map(normalize_name)

    by_id: dict[str, str] = {}
    for pid, grp in work[work["project_id"].astype(str).str.strip() != ""].groupby("project_id"):
        canon = _pick_canonical_name(grp["project_name"].astype(str))
        if canon:
            by_id[str(pid).strip()] = canon
    by_norm: dict[str, str] = {}
    for nn, grp in work.groupby("__name_norm__"):
        canon = _pick_canonical_name(grp["project_name"].astype(str))
        if canon:
            by_norm[str(nn)] = canon

    def _resolve(row) -> str:
        name = str(row["project_name"]).strip()
        pid = str(row["project_id"]).strip()
        if _gdrs_blank_project_name(name) or _is_uuid_like(name):
            return by_id.get(pid, "" if _gdrs_blank_project_name(name) else name)
        return by_norm.get(str(row["__name_norm__"]), name)

    work["project_name"] = work.apply(_resolve, axis=1)
    work = work.drop(columns="__name_norm__")
    try:
        from dashboards.project_labels import apply_unified_project_column

        work = apply_unified_project_column(work, "project_name")
    except Exception:
        pass
    return work


def _gdrs_ensure_project_names(df: pd.DataFrame) -> pd.DataFrame:
    """Перед сводкой по проектам: заполнить пустые имена из project_id, иначе отбросить строку.

    Иначе `groupby(project_name)` даёт субтотал с пустой ячейкой «Проект» (сиротский план).
    """
    if df is None or df.empty or "project_name" not in df.columns:
        return df
    work = df.copy()
    work["project_name"] = work["project_name"].map(
        lambda v: "" if _gdrs_blank_project_name(v) else str(v).strip()
    )
    if "project_id" in work.columns:
        by_id: dict[str, str] = {}
        named = work[
            work["project_name"].ne("")
            & ~work["project_name"].map(_is_uuid_like)
            & work["project_id"].astype(str).str.strip().ne("")
        ]
        for pid, grp in named.groupby(named["project_id"].astype(str).str.strip()):
            canon = _pick_canonical_name(grp["project_name"])
            if canon:
                by_id[str(pid)] = canon
        if by_id:
            empty = work["project_name"].eq("") | work["project_name"].map(_is_uuid_like)
            filled = (
                work.loc[empty, "project_id"]
                .astype(str)
                .str.strip()
                .map(by_id)
                .fillna("")
            )
            work.loc[empty, "project_name"] = filled.to_numpy()
    return work[work["project_name"].ne("")].copy()


def _fuzzy_cluster(norms: list[str], cutoff: float = 0.86) -> dict[str, str]:
    """Строит DSU-кластеры по фуззи-похожести нормализованных имён.
    Возвращает маппинг norm → root_norm (по самому раннему совпадению в списке).

    Помогает схлопнуть typo подрядчиков 1С:
      «констракшн» ↔ «контракшн» ↔ «констракшен»
    """
    import difflib as _dl

    parent: dict[str, str] = {n: n for n in norms}

    def _find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(a: str, b: str) -> None:
        ra, rb = _find(a), _find(b)
        if ra == rb:
            return
        if len(ra) <= len(rb):
            parent[rb] = ra
        else:
            parent[ra] = rb

    for n in norms:
        if not n:
            continue
        for m in _dl.get_close_matches(n, norms, n=5, cutoff=cutoff):
            if m != n:
                _union(n, m)
    return {n: _find(n) for n in norms}


def _canonicalize_contractor_names(df: pd.DataFrame) -> pd.DataFrame:
    """Схлопывает разные написания имени контрагента в одно каноническое.
    Этапы:
      (1) точное совпадение `normalize_name` — «ООО СК Сети» / «СК СЕТИ ООО».
      (2) фуззи (difflib, cutoff 0.86) — typo «Констракшн/Контракшн/Констракшен».
    Канонический выбор — самое популярное по числу строк (value_counts.idxmax).

    Дополнительно: если у каноники имеется не-пустой `contractor_id` хотя бы в одной
    строке — заполняем им пустые `contractor_id` тех же строк (нужно для матчинга плана).
    """
    if df is None or df.empty:
        return df
    work = df.copy()
    work["__cn_norm__"] = work["contractor_name"].astype(str).map(normalize_name)
    norms_unique = sorted({n for n in work["__cn_norm__"].unique() if n})
    fuzzy_root = _fuzzy_cluster(norms_unique, cutoff=0.93)
    work["__cn_root__"] = work["__cn_norm__"].map(lambda x: fuzzy_root.get(x, x))

    by_root_name: dict[str, str] = {}
    by_root_id: dict[str, str] = {}
    for root, grp in work.groupby("__cn_root__"):
        if not root:
            continue
        canon = _pick_canonical_name(grp["contractor_name"].astype(str))
        if canon:
            by_root_name[str(root)] = canon
        ids = [i for i in grp["contractor_id"].astype(str).str.strip().unique() if i]
        if ids:
            by_root_id[str(root)] = ids[0]

    def _name(row) -> str:
        root = str(row["__cn_root__"])
        return by_root_name.get(root, str(row["contractor_name"]).strip())

    def _id(row) -> str:
        cur = str(row["contractor_id"]).strip()
        if cur:
            return cur
        return by_root_id.get(str(row["__cn_root__"]), "")

    work["contractor_name"] = work.apply(_name, axis=1)
    work["contractor_id"] = work.apply(_id, axis=1)
    work = work.drop(columns=["__cn_norm__", "__cn_root__"])
    return work


def load_resursi_files(paths: Iterable[Path | str]) -> pd.DataFrame:
    sorted_paths = sorted(
        (Path(p) for p in paths),
        key=lambda p: _resursi_snapshot_sort_key(p),
    )
    frames = []
    for p in sorted_paths:
        try:
            df = load_resursi_file(p)
        except Exception:
            df = pd.DataFrame()
        if df is not None and not df.empty:
            tagged = df.copy()
            tagged["__source_file"] = p.name
            frames.append(tagged)
    if not frames:
        return pd.DataFrame(
            columns=[
                "project_id", "project_name", "contractor_id",
                "contractor_name", "vid_resursa", "date", "fact",
            ]
        )
    out = pd.concat(frames, ignore_index=True)
    out = _canonicalize_project_names(out)
    out = _canonicalize_contractor_names(out)
    return gdrs_dedupe_fact_prefer_latest_source(out)

@dataclass(frozen=True)
class GdrsKontrIndex:
    """Справочник 1С Kontr."""

    ids: frozenset[str]
    norm_names: frozenset[str]
    id_by_norm: dict[str, str]
    name_by_norm: dict[str, str]
    name_by_id: dict[str, str]


@dataclass(frozen=True)
class GdrsTerminationIndex:
    """Даты расторжения по парам проект×контрагент (из Dogovor.json)."""

    by_id: dict[tuple[str, str], pd.Timestamp]
    by_norm: dict[tuple[str, str], pd.Timestamp]

    @staticmethod
    def empty() -> GdrsTerminationIndex:
        return GdrsTerminationIndex(by_id={}, by_norm={})


def load_gdrs_termination_index(
    dogovor_paths: Iterable[Path | str] = (),
    *,
    dogovor_records: dict[str, list[dict]] | None = None,
) -> GdrsTerminationIndex:
    """Минимальная дата заявки/расторжения по (project_id, contractor_id) из Dogovor.json."""
    sentinel = pd.Timestamp("0001-01-01")
    by_id: dict[tuple[str, str], pd.Timestamp] = {}
    by_norm: dict[tuple[str, str], pd.Timestamp] = {}

    def _accum(
        term_ts: pd.Timestamp,
        pid: str,
        cid: str,
        pn: str,
        cn: str,
    ) -> None:
        if term_ts is None or not pd.notna(term_ts) or term_ts <= sentinel:
            return
        term_ts = pd.Timestamp(term_ts).normalize()
        if pid and cid:
            key = (pid, cid)
            by_id[key] = min(by_id[key], term_ts) if key in by_id else term_ts
        if pn and cn:
            nkey = (pn, cn)
            by_norm[nkey] = min(by_norm[nkey], term_ts) if nkey in by_norm else term_ts

    file_items: list[tuple[Optional[pd.Timestamp], str, list]] = []
    if dogovor_records is not None:
        for key in sorted(
            dogovor_records.keys(),
            key=lambda s: (_dogovor_snapshot_sort_key(s), str(s)),
        ):
            recs = dogovor_records[key]
            sk = _dogovor_snapshot_sort_key(key)
            fs = None if sk[0] is pd.Timestamp.min else pd.Timestamp(sk[0]).normalize()
            if isinstance(recs, list):
                file_items.append((fs, str(key), recs))
    else:
        for raw in sorted(dogovor_paths, key=lambda p: (_dogovor_snapshot_sort_key(p), str(p))):
            sk = _dogovor_snapshot_sort_key(raw)
            fs = None if sk[0] is pd.Timestamp.min else pd.Timestamp(sk[0]).normalize()
            data = _safe_json(Path(raw))
            if isinstance(data, list):
                file_items.append((fs, str(raw), data))
    file_items.sort(key=lambda t: (t[0] is None, t[0] or pd.Timestamp.min, t[1]))

    for file_snapshot, _src_key, data in file_items:
        for r in data:
            if not isinstance(r, dict):
                continue
            cn_raw = r.get("Наименование_Договора")
            if _is_gdrs_termination_application_name(cn_raw):
                term_dt = _gdrs_record_termination_event_date(r, file_snapshot=file_snapshot)
            else:
                term_dt = _gdrs_valid_contract_date(_contract_termination_date_raw(r))
            if term_dt is None:
                continue
            pid = str(r.get("ID_Проекта") or "").strip()
            cid = str(r.get("ID_Контрагента") or "").strip()
            pn = normalize_name(str(r.get("Наименование_Проекта") or ""))
            cn = normalize_name(str(r.get("Наименование_Контрагента") or ""))
            _accum(term_dt, pid, cid, pn, cn)

    return GdrsTerminationIndex(by_id=by_id, by_norm=by_norm)


def _gdrs_contractor_termination_date(
    project_id: str,
    contractor_id: str,
    project_name: str,
    contractor_name: str,
    term_index: Optional[GdrsTerminationIndex],
) -> Optional[pd.Timestamp]:
    if term_index is None:
        return None
    pid, cid = str(project_id or "").strip(), str(contractor_id or "").strip()
    if pid and cid and (pid, cid) in term_index.by_id:
        return term_index.by_id[(pid, cid)]
    pn = normalize_name(project_name)
    cn = normalize_name(contractor_name)
    if pn and cn and (pn, cn) in term_index.by_norm:
        return term_index.by_norm[(pn, cn)]
    return None


def gdrs_contractor_terminated_as_of(
    project_id: str,
    contractor_id: str,
    project_name: str,
    contractor_name: str,
    as_of: pd.Timestamp,
    term_index: Optional[GdrsTerminationIndex],
) -> bool:
    """True если as_of >= даты заявки/расторжения (в этот день подрядчик уже не учитывается)."""
    term = _gdrs_contractor_termination_date(
        project_id, contractor_id, project_name, contractor_name, term_index
    )
    if term is None or not pd.notna(term):
        return False
    return pd.Timestamp(as_of).normalize() >= pd.Timestamp(term).normalize()


def gdrs_filter_fact_by_termination(
    df: pd.DataFrame,
    term_index: Optional[GdrsTerminationIndex],
) -> pd.DataFrame:
    if df is None or df.empty or term_index is None:
        return df
    if not term_index.by_id and not term_index.by_norm:
        return df
    work = df.copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    mask = work.apply(
        lambda r: not gdrs_contractor_terminated_as_of(
            str(r.get("project_id", "")),
            str(r.get("contractor_id", "")),
            str(r.get("project_name", "")),
            str(r.get("contractor_name", "")),
            r["date"],
            term_index,
        ),
        axis=1,
    )
    return work.loc[mask].copy()


def load_1c_kontr_index(
    paths: Iterable[Path | str] = (),
    *,
    records: Iterable[dict] | None = None,
) -> GdrsKontrIndex:
    ids: set[str] = set()
    norm_names: set[str] = set()
    id_by_norm: dict[str, str] = {}
    name_by_norm: dict[str, str] = {}
    name_by_id: dict[str, str] = {}

    def _consume(data):
        if not isinstance(data, list):
            return
        for r in data:
            if not isinstance(r, dict):
                continue
            cid = str(r.get("ID_Контрагента") or "").strip()
            cname = str(r.get("Наименование_Контрагента") or r.get("Наименование") or "").strip()
            if not cid and not cname:
                continue
            nn = normalize_name(cname) if cname else ""
            if cid:
                ids.add(cid)
                if cname:
                    name_by_id.setdefault(cid, cname)
            if nn:
                norm_names.add(nn)
                if cname:
                    name_by_norm.setdefault(nn, cname)
                if cid and nn not in id_by_norm:
                    id_by_norm[nn] = cid

    if records is not None:
        _consume(list(records))
    else:
        for p in paths:
            _consume(_safe_json(Path(p)))
    return GdrsKontrIndex(
        frozenset(ids),
        frozenset(norm_names),
        id_by_norm,
        name_by_norm,
        name_by_id,
    )


def build_dogovor_contractor_id_lookup(
    dogovor_paths: Iterable[Path | str] = (),
    *,
    dogovor_records: dict[str, list[dict]] | None = None,
) -> tuple[dict[tuple[str, str], str], dict[str, str]]:
    by_proj: dict[tuple[str, str], str] = {}
    by_name: dict[str, str] = {}

    def _consume(df: pd.DataFrame) -> None:
        if df is None or df.empty:
            return
        # Проход по numpy вместо iterrows (последний создаёт Series на КАЖДУЮ строку —
        # десятки тысяч Series.__init__/sanitize_array). Порядок строк и «first wins»
        # (setdefault) сохранены. normalize_name считаем один раз на уникальное имя.
        pids = df["project_id"].astype(str).to_numpy()
        cids = df["contractor_id"].astype(str).to_numpy()
        cnames = df["contractor_name"].astype(str).to_numpy()
        _nmap = {u: normalize_name(u) for u in pd.unique(cnames)}
        for pid_r, cid_r, cname_r in zip(pids, cids, cnames):
            cid = cid_r.strip()
            if not cid:
                continue
            nn = _nmap[cname_r]
            if nn:
                by_name.setdefault(nn, cid)
                pid = pid_r.strip()
                if pid:
                    by_proj.setdefault((pid, nn), cid)

    if dogovor_records is not None:
        for src, recs in dogovor_records.items():
            _consume(load_plan_from_dogovor(records=recs, snapshot_date=None, cache_key=str(src)))
    else:
        for p in dogovor_paths:
            _consume(load_plan_from_dogovor(Path(p), snapshot_date=None))
    return by_proj, by_name


def build_dogovor_project_id_lookup(
    dogovor_paths: Iterable[Path | str] = (),
    *,
    dogovor_records: dict[str, list[dict]] | None = None,
) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    """norm(project_name) → project_id; (norm(project), norm(contractor)) → project_id."""
    by_name: dict[str, str] = {}
    by_pair: dict[tuple[str, str], str] = {}

    def _consume(df: pd.DataFrame) -> None:
        if df is None or df.empty:
            return
        # Проход по numpy вместо iterrows (см. build_dogovor_contractor_id_lookup):
        # порядок и «first wins» сохранены, normalize_name — один раз на уникум.
        pids = df["project_id"].astype(str).to_numpy()
        pnames = df["project_name"].astype(str).to_numpy()
        cnames = df["contractor_name"].astype(str).to_numpy()
        _pmap = {u: normalize_name(u) for u in pd.unique(pnames)}
        _cmap = {u: normalize_name(u) for u in pd.unique(cnames)}
        for pid_r, pname_r, cname_r in zip(pids, pnames, cnames):
            pid = pid_r.strip()
            if not pid:
                continue
            pn = _pmap[pname_r]
            cn = _cmap[cname_r]
            if pn:
                by_name.setdefault(pn, pid)
            if pn and cn:
                by_pair.setdefault((pn, cn), pid)

    if dogovor_records is not None:
        for src, recs in dogovor_records.items():
            _consume(load_plan_from_dogovor(records=recs, snapshot_date=None, cache_key=str(src)))
    else:
        for p in dogovor_paths:
            _consume(load_plan_from_dogovor(Path(p), snapshot_date=None))
    return by_name, by_pair


def enrich_gdrs_fact_project_ids(
    df: pd.DataFrame,
    *,
    dogovor_paths: Optional[Iterable[Path | str]] = None,
    dogovor_records: dict[str, list[dict]] | None = None,
) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    work = df.copy()
    by_name, by_pair = build_dogovor_project_id_lookup(
        dogovor_paths or [],
        dogovor_records=dogovor_records,
    )

    # Проход по numpy вместо apply(axis=1) (создаёт Series на строку). Логика и
    # порядок проверок идентичны; normalize_name — только для нерешённых строк.
    _cur = work["project_id"].astype(str).to_numpy()
    _pn_arr = work["project_name"].astype(str).to_numpy()
    _cn_arr = work["contractor_name"].astype(str).to_numpy()
    _out = []
    for cur_r, pname_r, cname_r in zip(_cur, _pn_arr, _cn_arr):
        cur = cur_r.strip()
        if cur:
            _out.append(cur)
            continue
        pn = normalize_name(pname_r)
        cn = normalize_name(cname_r)
        if pn and cn and (pn, cn) in by_pair:
            _out.append(by_pair[(pn, cn)])
        elif pn and pn in by_name:
            _out.append(by_name[pn])
        else:
            _out.append("")
    work["project_id"] = _out
    return work


def enrich_gdrs_fact_contractor_ids(
    df: pd.DataFrame,
    *,
    dogovor_paths: Optional[Iterable[Path | str]] = None,
    dogovor_records: dict[str, list[dict]] | None = None,
    kontr: Optional[GdrsKontrIndex] = None,
) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    work = df.copy()
    by_proj, by_name = build_dogovor_contractor_id_lookup(
        dogovor_paths or [],
        dogovor_records=dogovor_records,
    )

    # Проход по numpy вместо apply(axis=1). Логика и порядок проверок идентичны.
    _cid_arr = work["contractor_id"].to_numpy()
    _pid_arr = work["project_id"].astype(str).to_numpy()
    _cname_arr = work["contractor_name"].astype(str).to_numpy()
    _has_kontr = bool(kontr)
    _out = []
    for cid_r, pid_r, cname_r in zip(_cid_arr, _pid_arr, _cname_arr):
        cur = _sanitize_contractor_id(cid_r)
        if cur:
            _out.append(cur)
            continue
        pid = pid_r.strip()
        nn = normalize_name(cname_r)
        if pid and nn and (pid, nn) in by_proj:
            _out.append(by_proj[(pid, nn)])
        elif nn and nn in by_name:
            _out.append(by_name[nn])
        elif _has_kontr and nn and nn in kontr.id_by_norm:
            _out.append(kontr.id_by_norm[nn])
        else:
            _out.append("")
    work["contractor_id"] = _out
    return work


def gdrs_kontr_contractor_display(
    contractor_id: str,
    contractor_name: str,
    kontr: Optional[GdrsKontrIndex],
) -> tuple[str, str]:
    """Каноническое имя и ID контрагента — только из справочника 1С Kontr."""
    cid = _sanitize_contractor_id(contractor_id)
    raw_name = _strip_display_name_artifacts(contractor_name)
    if kontr is None or (not kontr.ids and not kontr.norm_names):
        return cid, raw_name
    nn = normalize_name(raw_name)
    # Имя в Kontr важнее ID из resursi/Dogovor (там бывают чужие UUID).
    if nn and nn in kontr.name_by_norm:
        canon_id = kontr.id_by_norm.get(nn, cid)
        return canon_id or cid, _strip_display_name_artifacts(kontr.name_by_norm[nn])
    if cid and cid in kontr.name_by_id:
        return cid, _strip_display_name_artifacts(kontr.name_by_id[cid])
    return cid, raw_name


def _gdrs_resolve_contractor_display(
    df: pd.DataFrame,
    kontr: Optional[GdrsKontrIndex],
) -> pd.DataFrame:
    """Каноническое имя контрагента для UI: Kontr → без хвостового «_» и пр."""
    if df is None or df.empty or "contractor_name" not in df.columns:
        return df
    work = df.copy()
    if "row_kind" in work.columns:
        detail = work["row_kind"].astype(str) == "row"
    else:
        detail = pd.Series(True, index=work.index)
    if not detail.any():
        return work

    def _resolve(row) -> pd.Series:
        cid, cname = gdrs_kontr_contractor_display(
            str(row.get("contractor_id", "")),
            str(row.get("contractor_name", "")),
            kontr,
        )
        return pd.Series([cid, cname])

    resolved = work.loc[detail].apply(_resolve, axis=1, result_type="expand")
    work.loc[detail, "contractor_id"] = resolved[0].values
    work.loc[detail, "contractor_name"] = resolved[1].values
    return work


def _gdrs_project_key(project_id: str, project_name: str) -> str:
    pid = str(project_id or "").strip()
    if pid and _is_uuid_like(pid):
        return pid
    pn = normalize_name(project_name)
    return f"name:{pn}" if pn else ""


def _gdrs_contractor_key(
    contractor_id: str,
    contractor_name: str,
    kontr: Optional[GdrsKontrIndex] = None,
) -> str:
    cid, _ = gdrs_kontr_contractor_display(
        str(contractor_id or "").strip(),
        str(contractor_name or ""),
        kontr,
    )
    cid = _sanitize_contractor_id(cid)
    if cid:
        return cid
    cn = normalize_name(contractor_name)
    return f"name:{cn}" if cn else ""


def _gdrs_add_pair_keys(
    df: pd.DataFrame,
    kontr: Optional[GdrsKontrIndex],
    *,
    dedupe_fact: bool = False,
) -> pd.DataFrame:
    """Ключи пары проект×контрагент: UUID из Kontr, иначе fallback по normalize_name."""
    if df is None or df.empty:
        return df
    work = gdrs_apply_kontr_contractor_names(df, kontr, dedupe_fact=dedupe_fact) if kontr else df.copy()
    for col, default in (("project_id", ""), ("contractor_id", ""), ("project_name", ""), ("contractor_name", "")):
        if col not in work.columns:
            work[col] = default
    work["_gk_proj"] = work.apply(
        lambda r: _gdrs_project_key(str(r.get("project_id", "")), str(r.get("project_name", ""))),
        axis=1,
    )
    work["_gk_ctr"] = work.apply(
        lambda r: _gdrs_contractor_key(
            str(r.get("contractor_id", "")),
            str(r.get("contractor_name", "")),
            kontr,
        ),
        axis=1,
    )
    return work


def _gdrs_pair_group_cols(df: pd.DataFrame) -> list[str]:
    if (
        df is not None
        and not df.empty
        and "_gk_proj" in df.columns
        and "_gk_ctr" in df.columns
    ):
        return ["_gk_proj", "_gk_ctr"]
    return ["project_name", "contractor_name"]


def gdrs_apply_kontr_contractor_names(
    df: pd.DataFrame,
    kontr: Optional[GdrsKontrIndex],
    *,
    dedupe_fact: bool = True,
) -> pd.DataFrame:
    """Подменяет `contractor_name` на написание из 1С Kontr; схлопывает дубли факта."""
    if df is None or df.empty or kontr is None:
        return df
    if not kontr.ids and not kontr.norm_names:
        return df
    work = df.copy()
    # Проход по numpy вместо apply(axis=1, expand) (Series на КАЖДУЮ строку).
    # Логика прежняя; normalize_name внутри display кеширован (lru_cache).
    _cid_arr = work["contractor_id"].to_numpy()
    _cname_arr = work["contractor_name"].to_numpy()
    _ids = []
    _names = []
    for cid_r, cname_r in zip(_cid_arr, _cname_arr):
        _a, _b = gdrs_kontr_contractor_display(str(cid_r), str(cname_r), kontr)
        _ids.append(_a)
        _names.append(_b)
    work["contractor_id"] = _ids
    work["contractor_name"] = _names
    if dedupe_fact and {"vid_resursa", "date"}.issubset(work.columns):
        if "date" in work.columns:
            work["date"] = pd.to_datetime(work["date"], errors="coerce")
        work = _gdrs_stable_sort_for_fact_dedupe(work, include_source_snap=True)
        work = work.drop_duplicates(
            subset=["project_name", "contractor_name", "vid_resursa", "date"],
            keep="last",
        )
        work = _gdrs_cleanup_dedupe_sort_cols(work)
    return work


def gdrs_contractor_in_kontr(
    contractor_id: str,
    contractor_name: str,
    kontr: Optional[GdrsKontrIndex],
) -> bool:
    if kontr is None or (not kontr.ids and not kontr.norm_names):
        return True
    cid = _sanitize_contractor_id(contractor_id)
    if cid and cid in kontr.ids:
        return True
    nn = normalize_name(str(contractor_name or ""))
    return bool(nn and nn in kontr.norm_names)


def gdrs_contractor_plan_eligible(
    contractor_id: str,
    contractor_name: str,
    kontr: Optional[GdrsKontrIndex],
    term_index: Optional[GdrsTerminationIndex],
    *,
    project_id: str = "",
    project_name: str = "",
    plan_as_of: Optional[pd.Timestamp] = None,
) -> bool:
    """План из Dogovor: без расторжения до plan_as_of. Kontr/resursi не требуются."""
    if plan_as_of is not None and term_index is not None:
        if gdrs_contractor_terminated_as_of(
            project_id,
            contractor_id,
            project_name,
            contractor_name,
            plan_as_of,
            term_index,
        ):
            return False
    return True


def gdrs_apply_kontr_plan_gate(
    rows: pd.DataFrame,
    kontr: Optional[GdrsKontrIndex],
    *,
    term_index: Optional[GdrsTerminationIndex] = None,
    plan_as_of: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    if rows is None or rows.empty:
        return rows
    if kontr is None or (not kontr.ids and not kontr.norm_names):
        if term_index is None or plan_as_of is None:
            return rows
    work = rows.copy()
    detail = work["row_kind"].astype(str) == "row"
    for idx in work.index[detail]:
        r = work.loc[idx]
        if gdrs_contractor_plan_eligible(
            str(r.get("contractor_id", "")),
            str(r.get("contractor_name", "")),
            kontr,
            term_index,
            project_id=str(r.get("project_id", "")),
            project_name=str(r.get("project_name", "")),
            plan_as_of=plan_as_of,
        ):
            continue
        work.loc[idx, "plan"] = 0.0
        for pk in ("p1", "p2", "p3", "p4", "p5", "p6"):
            if pk in work.columns:
                work.loc[idx, pk] = 0.0
    return work


def gdrs_filter_fact_kontr_intersection(
    df: pd.DataFrame,
    kontr: Optional[GdrsKontrIndex],
) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    if kontr is None or (not kontr.ids and not kontr.norm_names):
        return df
    mask = df.apply(
        lambda r: gdrs_contractor_in_kontr(
            str(r.get("contractor_id", "")),
            str(r.get("contractor_name", "")),
            kontr,
        ),
        axis=1,
    )
    return df.loc[mask].copy()


# =====================================================================
# Парсер плана (Dogovor.json + spravochniki.json fallback)
# =====================================================================

def _safe_json(path: Path) -> object:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        try:
            return json.loads(Path(path).read_text(encoding="utf-8-sig"))
        except Exception:
            return None


# Точное имя поля расторжения в 1С сообщат позже — перечисляем известные варианты.
_CONTRACT_TERMINATION_KEYS = (
    "Дата_Расторжения_Договора",
    "Дата расторжения договора",
    "ДатаРасторженияДоговора",
)


def _contract_termination_date_raw(record: dict) -> object:
    if not isinstance(record, dict):
        return None
    for key in _CONTRACT_TERMINATION_KEYS:
        val = record.get(key)
        if val is not None and str(val).strip() not in ("", "0001-01-01T00:00:00Z"):
            return val
    return None


def _is_gdrs_termination_application_name(contract_name: object) -> bool:
    """Заявки/соглашения о расторжении — с их даты подрядчик не идёт в план/факт ГДРС."""
    cn = str(contract_name or "").casefold().replace("ё", "е")
    if "заявка на акт" in cn and "строительн" in cn and "площад" in cn:
        return True
    if "заявка" in cn and "расторжен" in cn:
        return True
    if "соглашение" in cn and "расторжен" in cn:
        return True
    if "уведомление" in cn and "расторжен" in cn:
        return True
    return False


def _is_gdrs_excluded_plan_application(contract_name: object) -> bool:
    """Alias для обратной совместимости."""
    return _is_gdrs_termination_application_name(contract_name)


# Контрагенты, которых по решению заказчика не выводим в ГДРС (не трудовые ресурсы:
# поставка/сервис — «Охрана труда, спецодежда» и т.п.). Сравнение по нормализованному
# имени (normalize_name), поэтому регистр/порядок слов/«ООО» не важны.
GDRS_EXCLUDED_CONTRACTOR_NAMES: frozenset[str] = frozenset(
    {
        normalize_name("Строй Альянс"),
    }
)


def gdrs_is_excluded_contractor(contractor_name: object) -> bool:
    """True, если контрагента нужно скрыть из ГДРС (по стоп-листу имён)."""
    nn = normalize_name(str(contractor_name or ""))
    return bool(nn) and nn in GDRS_EXCLUDED_CONTRACTOR_NAMES


def gdrs_drop_excluded_contractors(df: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Убрать строки контрагентов из стоп-листа (по `contractor_name`)."""
    if df is None or df.empty or "contractor_name" not in df.columns:
        return df
    if not GDRS_EXCLUDED_CONTRACTOR_NAMES:
        return df
    keep = ~df["contractor_name"].map(gdrs_is_excluded_contractor)
    if bool(keep.all()):
        return df
    return df.loc[keep].copy()


def _gdrs_valid_contract_date(val: object) -> Optional[pd.Timestamp]:
    sentinel = pd.Timestamp("0001-01-01")
    ts = _fast_parse_date(val)
    if ts is None or not pd.notna(ts):
        return None
    ts = pd.Timestamp(ts)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    ts = ts.normalize()
    if ts <= sentinel:
        return None
    return ts


def _gdrs_record_termination_event_date(
    record: dict,
    *,
    file_snapshot: Optional[pd.Timestamp] = None,
) -> Optional[pd.Timestamp]:
    """Дата события расторжения из строки Dogovor.json."""
    if not isinstance(record, dict):
        return None
    for key in (
        "Дата_Окончания_Договора",
        "Дата_Начала_Договора",
        "Дата_Получения_ИД",
    ):
        ts = _gdrs_valid_contract_date(record.get(key))
        if ts is not None:
            return ts
    ts = _gdrs_valid_contract_date(_contract_termination_date_raw(record))
    if ts is not None:
        return ts
    cn = record.get("Наименование_Договора")
    if _is_gdrs_termination_application_name(cn) and file_snapshot is not None:
        return pd.Timestamp(file_snapshot).normalize()
    return None


def _gdrs_row_termination_event_date(
    row: pd.Series,
    *,
    file_snapshot: Optional[pd.Timestamp] = None,
) -> Optional[pd.Timestamp]:
    for col in ("date_end", "date_start"):
        if col in row.index:
            ts = _gdrs_valid_contract_date(row.get(col))
            if ts is not None:
                return ts
    if "date_termination" in row.index:
        ts = _gdrs_valid_contract_date(row.get("date_termination"))
        if ts is not None:
            return ts
    if _is_gdrs_termination_application_name(row.get("contract_name")) and file_snapshot is not None:
        return pd.Timestamp(file_snapshot).normalize()
    return None


def _gdrs_dogovor_contract_key(contract_name: object, contract_number: object = "") -> str:
    cn = str(contract_name or "").strip()
    sigs = contract_signatures(cn)
    if sigs:
        return sigs[0]
    num = str(contract_number or "").strip()
    sigs_num = contract_signatures(num)
    if sigs_num:
        return sigs_num[0]
    return "name::" + normalize_name(cn or num)


_GDRS_DS_CONTRACT_RE = re.compile(
    r"(?:"
    r"^\s*дс\b"  # «ДС …», «ДС№1 …»
    r"|^\s*согласование\s*дс"  # «Согласование ДС№3 …»
    r"|[_\s]дс\s*№"  # «…_ДС №2 …», «ДС №5 …» внутри строки
    r")",
    re.IGNORECASE,
)


def _gdrs_norm_dogovor_cn(contract_name: object) -> str:
    return str(contract_name or "").strip().casefold().replace("ё", "е")


def _gdrs_is_ds_dogovor_record(contract_name: object) -> bool:
    """Доп. соглашение: «ДС …», «…_ДС №…», «Согласование ДС…» и т.п."""
    cn = _gdrs_norm_dogovor_cn(contract_name)
    if not cn:
        return False
    return bool(_GDRS_DS_CONTRACT_RE.search(cn))


def _gdrs_is_primary_dogovor_record(contract_name: object) -> bool:
    """Первичный договор: «Дог.» / «Договор …», но не строки с признаком ДС."""
    if _gdrs_is_ds_dogovor_record(contract_name):
        return False
    cn = _gdrs_norm_dogovor_cn(contract_name)
    return cn.startswith("дог.") or cn.startswith("договор") or cn.startswith("дог ")


def _gdrs_plan_snapshot_valid(val: object) -> bool:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return False
    try:
        return float(val) > 0
    except (TypeError, ValueError):
        return False


def _merge_dogovor_primary_ds_plan(group: pd.DataFrame) -> pd.Series:
    """План по одной сигнатуре договора: ДС замещает «Дог.»/«Договор», если в ДС есть >0."""
    primary = group[group["contract_name"].map(_gdrs_is_primary_dogovor_record)]
    ds_rows = group[group["contract_name"].map(_gdrs_is_ds_dogovor_record)]
    other = group[
        ~group["contract_name"].map(_gdrs_is_primary_dogovor_record)
        & ~group["contract_name"].map(_gdrs_is_ds_dogovor_record)
    ]
    out: dict[str, float] = {}
    for col in ("plan_workers", "plan_equipment"):
        pval = np.nan
        if not primary.empty:
            pvals = pd.to_numeric(primary[col], errors="coerce").dropna()
            if not pvals.empty:
                pval = float(pvals.iloc[0])
        dval = np.nan
        if not ds_rows.empty:
            vals = pd.to_numeric(ds_rows[col], errors="coerce").tolist()
            for v in reversed(vals):
                if _gdrs_plan_snapshot_valid(v):
                    dval = float(v)
                    break
        if _gdrs_plan_snapshot_valid(dval):
            out[col] = dval
        elif _gdrs_plan_snapshot_valid(pval):
            out[col] = pval
        elif not other.empty:
            ovals = pd.to_numeric(other[col], errors="coerce").dropna()
            out[col] = float(ovals.max()) if not ovals.empty else np.nan
        else:
            out[col] = np.nan
    return pd.Series(out)


def _dogovor_row_contract_keys(df: pd.DataFrame) -> pd.Series:
    """Сигнатура договора для строки: из имени или Номер_Договора (важно для «ДС …»)."""
    cn = df["contract_name"].fillna("").astype(str).str.strip()
    has_num = "contract_number" in df.columns
    if has_num:
        nums = df["contract_number"].fillna("").astype(str).str.strip()
        return pd.Series(
            [
                _gdrs_dogovor_contract_key(cn.iat[i], nums.iat[i])
                for i in range(len(df))
            ],
            index=df.index,
        )
    return cn.map(lambda x: _gdrs_dogovor_contract_key(x, ""))


def _apply_gdrs_dogovor_plan_exclusions(
    df: pd.DataFrame,
    *,
    snapshot_date: Optional[pd.Timestamp] = None,
    file_snapshot_date: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    """Исключить заявки на расторжение; с даты заявки обнулить план по всем договорам подрядчика."""
    if df is None or df.empty:
        return df
    out = df.copy()
    cn = out["contract_name"].fillna("").astype(str).str.strip()
    excluded = cn.map(_is_gdrs_termination_application_name)
    snap = pd.Timestamp(snapshot_date).normalize() if snapshot_date is not None else None
    file_snap = (
        pd.Timestamp(file_snapshot_date).normalize()
        if file_snapshot_date is not None
        else snap
    )
    contractor_cutoffs: dict[tuple[str, str], pd.Timestamp] = {}
    if bool(excluded.any()):
        for idx in out.index[excluded]:
            row = out.loc[idx]
            de = _gdrs_row_termination_event_date(row, file_snapshot=file_snap)
            if de is None:
                continue
            pid = str(row.get("project_id", "")).strip()
            cid = str(row.get("contractor_id", "")).strip()
            if not pid or not cid:
                continue
            key = (pid, cid)
            contractor_cutoffs[key] = min(contractor_cutoffs[key], de) if key in contractor_cutoffs else de
        out = out.loc[~excluded].copy()
    if out.empty:
        return out
    if snap is not None and contractor_cutoffs:
        pids = out["project_id"].astype(str).str.strip()
        cids = out["contractor_id"].astype(str).str.strip()
        drop_plan = []
        for i in range(len(out)):
            cut = contractor_cutoffs.get((pids.iat[i], cids.iat[i]))
            drop_plan.append(cut is not None and snap >= cut)
        if any(drop_plan):
            mask = pd.Series(drop_plan, index=out.index)
            out.loc[mask, ["plan_workers", "plan_equipment"]] = np.nan
    return out


def _snapshot_history(history: object, target_date: Optional[pd.Timestamp]) -> Optional[float]:
    """Из истории `[{'Дата': 'YYYY-MM-DD', 'Количество': 'N'}, ...]` взять последнее значение
    с `Дата <= target_date`. Если history скаляр — вернуть его. Если target_date is None —
    вернуть последнее значение в истории.
    """
    if history is None:
        return None
    if isinstance(history, (int, float)):
        return float(history)
    if isinstance(history, str):
        return _coerce_int(history)
    if not isinstance(history, list) or not history:
        return None
    items = []
    for item in history:
        if not isinstance(item, dict):
            continue
        d_raw = item.get("Дата") or item.get("дата")
        n_raw = item.get("Количество") or item.get("количество")
        d = _fast_parse_date(d_raw)
        n = _coerce_int(n_raw)
        if d is None or n is None:
            continue
        items.append((d, n))
    if not items:
        return None
    items.sort(key=lambda x: x[0])
    if target_date is None:
        return float(items[-1][1])
    candidates = [n for d, n in items if d <= target_date]
    if candidates:
        return float(candidates[-1])
    return None


def _dogovor_file_date(path) -> Optional[pd.Timestamp]:
    """Дата снапшота из имени файла «1с_DD-MM-YYYY_…» → Timestamp (или None)."""
    return _source_file_date(path)


def _prep_history(history: object):
    """Однократный разбор истории плана в вид, пригодный для быстрого snapshot-запроса.

    Возвращает:
      - None — истории нет;
      - ("s", value) — скаляр/строка (value может быть None при неразборе строки);
      - ("h", ts_list, cnt_list) — отсортированные по дате (asc) списки Timestamp и float.

    Логика идентична прежней (внутри ``_snapshot_history``), но выполняется один раз
    на файл, а не заново для каждой из snapshot-дат.
    """
    if history is None:
        return None
    if isinstance(history, (int, float)):
        return ("s", float(history))
    if isinstance(history, str):
        return ("s", _coerce_int(history))
    if not isinstance(history, list) or not history:
        return None
    items = []
    for item in history:
        if not isinstance(item, dict):
            continue
        d_raw = item.get("Дата") or item.get("дата")
        n_raw = item.get("Количество") or item.get("количество")
        d = _fast_parse_date(d_raw)
        n = _coerce_int(n_raw)
        if d is None or n is None:
            continue
        items.append((d, n))
    if not items:
        return None
    items.sort(key=lambda x: x[0])
    ts_list = [d for d, _ in items]
    cnt_list = [float(n) for _, n in items]
    return ("h", ts_list, cnt_list)


def _snapshot_from_prepped(prepped, target_date: Optional[pd.Timestamp]) -> Optional[float]:
    """Значение плана на дату из предразобранной истории (см. ``_prep_history``).

    Точный аналог ``_snapshot_history``: для списка — последнее значение с датой
    ``<= target_date`` (или последнее при ``target_date is None``).
    """
    if prepped is None:
        return None
    if prepped[0] == "s":
        return prepped[1]
    ts_list = prepped[1]
    cnt_list = prepped[2]
    if not ts_list:
        return None
    if target_date is None:
        return cnt_list[-1]
    idx = bisect_right(ts_list, target_date)
    if idx > 0:
        return cnt_list[idx - 1]
    return None


# Кэш «базы» файла Dogovor: статические колонки + разобранные даты + предразобранные
# истории плана. Ключ — (id(records), len). records приходят из кэшированного
# json_records_by_source, поэтому ссылки стабильны в пределах версии БД. База не
# зависит от snapshot_date, поэтому переиспользуется для всех 6 снапшотов + lookup'ов.
_DOG_BASE_CACHE: dict[tuple, tuple] = {}

_DOGOVOR_EMPTY_COLS = [
    "project_id", "contractor_id", "project_name", "contractor_name",
    "contract_name", "contract_number", "plan_workers", "plan_equipment",
    "date_start", "date_end", "date_termination",
]


def _dog_build_base(data: list) -> tuple:
    """Snapshot-независимый разбор файла Dogovor → (static_df, hist_workers, hist_equip)."""
    rows = []
    hist_w = []
    hist_e = []
    for r in data:
        if not isinstance(r, dict):
            continue
        rows.append(
            {
                "project_id": str(r.get("ID_Проекта") or "").strip(),
                "contractor_id": str(r.get("ID_Контрагента") or "").strip(),
                "project_name": str(r.get("Наименование_Проекта") or "").strip(),
                "contractor_name": str(r.get("Наименование_Контрагента") or "").strip(),
                "contract_name": str(r.get("Наименование_Договора") or "").strip(),
                "contract_number": str(r.get("Номер_Договора") or "").strip(),
                "date_start": r.get("Дата_Начала_Договора"),
                "date_end": r.get("Дата_Окончания_Договора"),
                "date_termination": _contract_termination_date_raw(r),
            }
        )
        hist_w.append(_prep_history(r.get("Количество_Людей")))
        hist_e.append(_prep_history(r.get("Количество_Техники")))
    df = pd.DataFrame(rows)
    if df.empty:
        return df, [], []
    df = _dearrow_object_columns(df)
    df["date_start"] = pd.to_datetime(df["date_start"], errors="coerce", utc=True).dt.tz_localize(None)
    df["date_end"] = pd.to_datetime(df["date_end"], errors="coerce", utc=True).dt.tz_localize(None)
    df["date_termination"] = pd.to_datetime(df["date_termination"], errors="coerce", utc=True).dt.tz_localize(None)
    return df, hist_w, hist_e


def load_plan_from_dogovor(
    path: Path | str | None = None,
    *,
    records: list[dict] | None = None,
    snapshot_date: Optional[pd.Timestamp] = None,
    cache_key: object = None,
) -> pd.DataFrame:
    """Из 1с_*_Dogovor.json (по состоянию на `snapshot_date`) → DataFrame.

    ``cache_key`` — стабильный идентификатор источника (имя файла/ключ records_map).
    st.cache_data отдаёт свежие списки records при каждом обращении, поэтому
    id(records) как ключ бесполезен между снапшотами; при наличии cache_key базу
    файла (snapshot-независимую) строим один раз на источник, а не заново под
    каждую из 6 snapshot-дат.
    """
    key = None
    if records is not None:
        data = records
        if cache_key is not None and isinstance(records, list):
            key = (cache_key, len(records))
    else:
        data = _safe_json(Path(path))
    if not isinstance(data, list):
        return pd.DataFrame(columns=_DOGOVOR_EMPTY_COLS)
    base = _DOG_BASE_CACHE.get(key) if key is not None else None
    if base is None:
        base = _dog_build_base(data)
        if key is not None:
            if len(_DOG_BASE_CACHE) > 200:
                _DOG_BASE_CACHE.clear()
            _DOG_BASE_CACHE[key] = base
    base_df, hist_w, hist_e = base
    if base_df is None or base_df.empty:
        return base_df if base_df is not None else pd.DataFrame(columns=_DOGOVOR_EMPTY_COLS)
    df = base_df.copy()
    # План на дату — из предразобранных историй (без повторного парсинга дат/сортировки).
    df["plan_workers"] = [_snapshot_from_prepped(h, snapshot_date) for h in hist_w]
    df["plan_equipment"] = [_snapshot_from_prepped(h, snapshot_date) for h in hist_e]
    if snapshot_date is not None:
        # Договоры с реальной Дата_Окончания, истёкшей до даты снапшота, не действуют:
        # их «Количество_Людей» нередко обрывается без закрывающего 0, и snapshot тянет
        # старое значение в период. Аналогично — ещё не начавшиеся договоры и расторжение.
        snap = pd.Timestamp(snapshot_date).normalize()
        sentinel = pd.Timestamp("0001-01-01")
        de = df["date_end"]
        ds = df["date_start"]
        dt = df["date_termination"]
        # Истёкшие: date_end раньше начала ISO-недели месяца снапшота (как в 1С:
        # план действует до недели окончания договора включительно, не до конца недели).
        week_start = _gdrs_plan_expiry_week_start(snap)
        expired = de.notna() & (de > sentinel) & (de.dt.normalize() < week_start)
        not_started = ds.notna() & (ds > sentinel) & (ds.dt.normalize() > snap)
        terminated = dt.notna() & (dt > sentinel) & (dt.dt.normalize() <= snap)
        drop = expired | not_started | terminated
        df.loc[drop, ["plan_workers", "plan_equipment"]] = np.nan
    return df


def load_plan_from_spravochniki(
    path: Path | str | None = None,
    *,
    records: list[dict] | None = None,
    snapshot_date: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    """Из 1с_*_spravochniki.json (snapshot на дату) → DataFrame с агрегированным планом."""
    if records is not None:
        data = records
    else:
        data = _safe_json(Path(path))
    if not isinstance(data, list):
        return pd.DataFrame(columns=["project_id", "contractor_id", "plan_workers", "plan_equipment"])
    rows = []
    for r in data:
        if not isinstance(r, dict):
            continue
        rows.append(
            {
                "project_id": str(r.get("ID_Проекта") or "").strip(),
                "contractor_id": str(r.get("ID_Контрагента") or "").strip(),
                "plan_workers": _snapshot_history(r.get("КоличествоРаботников"), snapshot_date),
                "plan_equipment": _snapshot_history(r.get("КоличествоСпецТехники"), snapshot_date),
            }
        )
    return _dearrow_object_columns(pd.DataFrame(rows))


_FILE_DATE_RE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")
_RESURSI_STEM_SNAP_RE = re.compile(
    r"^other_(\d{2})-(\d{2})-(\d{4})(?:_(\d{2})-(\d{2}))?",
    re.IGNORECASE,
)
_ONE_C_DGOVOR_STEM_RE = re.compile(
    r"^(?:1с_|1c_|lc_|лк_|lk_)(\d{2}-\d{2}-\d{4})(?:_(\d{2}-\d{2}))?(?:_(.+))?$",
    re.IGNORECASE,
)


def _dogovor_snapshot_sort_key(path) -> tuple[pd.Timestamp, str]:
    """Пара (дата, HH-MM) из имени 1с_*_Dogovor.json — для выбора последней выгрузки за день."""
    name = _source_file_name(path)
    stem = Path(name).stem
    m = _ONE_C_DGOVOR_STEM_RE.match(stem.lower())
    if m:
        fd = _source_file_date(path)
        hhmm = str(m.group(2) or "00-00").strip()
        if fd is not None:
            return (pd.Timestamp(fd).normalize(), hhmm)
    fd = _dogovor_file_date(path)
    if fd is not None:
        return (pd.Timestamp(fd).normalize(), "00-00")
    return (pd.Timestamp.min, "00-00")


def _first_nonempty(series) -> str:
    for x in series:
        s = str(x).strip()
        if s and s.lower() not in ("nan", "none"):
            return s
    return ""


def _source_file_name(path) -> str:
    if isinstance(path, str):
        return Path(path).name
    if hasattr(path, "name"):
        return str(getattr(path, "name"))
    return Path(path).name


def _source_file_date(path) -> Optional[pd.Timestamp]:
    """Дата снапшота из имени файла «…_DD-MM-YYYY_…» (Dogovor, resursi) → Timestamp."""
    m = _FILE_DATE_RE.search(_source_file_name(path))
    if not m:
        return None
    dd, mm, yyyy = m.groups()
    try:
        return pd.Timestamp(year=int(yyyy), month=int(mm), day=int(dd))
    except ValueError:
        return None


def _resursi_snapshot_sort_key(path) -> tuple[pd.Timestamp, int]:
    """Ключ сортировки resursi: (дата выгрузки, минуты HH:MM из имени other_DD-MM-YYYY_HH-MM_…)."""
    stem = Path(_source_file_name(path)).stem.replace("__", "_")
    m = _RESURSI_STEM_SNAP_RE.match(stem)
    if m:
        try:
            ts = pd.Timestamp(
                year=int(m.group(3)), month=int(m.group(2)), day=int(m.group(1))
            )
        except ValueError:
            ts = pd.Timestamp.min
        hhmm = 0
        if m.group(4) is not None and m.group(5) is not None:
            hhmm = int(m.group(4)) * 60 + int(m.group(5))
        return ts, hhmm
    ts = _source_file_date(path) or pd.Timestamp.min
    return ts, 0


def _resursi_source_sort_key_from_name(source_file: str) -> tuple[pd.Timestamp, int]:
    """Ключ выбора строки при дублях по неделе: строка из более поздней выгрузки (по дате в имени)."""
    return _resursi_snapshot_sort_key(source_file)


def _gdrs_stable_sort_for_fact_dedupe(
    df: pd.DataFrame,
    *,
    include_source_snap: bool = True,
) -> pd.DataFrame:
    """Детерминированный порядок строк перед drop_duplicates(keep='last')."""
    if df is None or df.empty:
        return df
    work = df.copy()
    sort_cols: list[str] = []
    if include_source_snap and "__source_file" in work.columns:
        work["_dedupe_src"] = work["__source_file"].astype(str).map(
            _resursi_source_sort_key_from_name
        )
        sort_cols.extend(["_dedupe_src", "__source_file"])
    for c in (
        "date",
        "project_name",
        "contractor_name",
        "contractor_id",
        "project_id",
        "vid_resursa",
        "fact",
    ):
        if c in work.columns and c not in sort_cols:
            sort_cols.append(c)
    work["_dedupe_ord"] = np.arange(len(work), dtype=np.int64)
    sort_cols.append("_dedupe_ord")
    return work.sort_values(sort_cols, kind="mergesort")


def _gdrs_cleanup_dedupe_sort_cols(df: pd.DataFrame) -> pd.DataFrame:
    return df.drop(columns=["_dedupe_src", "_dedupe_ord"], errors="ignore")


def gdrs_dedupe_fact_prefer_latest_source(df: pd.DataFrame) -> pd.DataFrame:
    """При нескольких resursi.csv на одну дату — строка из файла с более поздней выгрузкой."""
    if df is None or df.empty:
        return df
    work = df.copy()
    src_col = "__source_file" if "__source_file" in work.columns else None
    if src_col is None:
        return work
    subset = [
        c
        for c in ("project_name", "contractor_name", "vid_resursa", "date")
        if c in work.columns
    ]
    if len(subset) < 4:
        return work
    if "date" in work.columns:
        work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work = _gdrs_stable_sort_for_fact_dedupe(work, include_source_snap=True)
    work = work.drop_duplicates(subset=subset, keep="last")
    return _gdrs_cleanup_dedupe_sort_cols(work)


def _pick_dogovor_path_for_snapshot(
    paths: Iterable[Path | str],
    snapshot_date: Optional[pd.Timestamp],
) -> Optional[Path]:
    """Файл Dogovor для среза плана: последний с датой в имени ≤ snapshot_date;
    если таких нет — самый поздний из будущих (в нём полнее история Количество_Людей)."""
    snap = pd.Timestamp(snapshot_date).normalize() if snapshot_date is not None else None
    dated: list[tuple[tuple[pd.Timestamp, str], Path]] = []
    undated: list[Path] = []
    for raw in paths:
        p = Path(raw)
        sk = _dogovor_snapshot_sort_key(p)
        if sk[0] is pd.Timestamp.min:
            undated.append(p)
            continue
        dated.append((sk, p))
    if not dated:
        return undated[0] if undated else None
    if snap is None:
        dated.sort(key=lambda t: t[0])
        return dated[-1][1]
    le = [t for t in dated if t[0][0] <= snap]
    if le:
        le.sort(key=lambda t: t[0])
        return le[-1][1]
    dated.sort(key=lambda t: t[0])
    return dated[-1][1]


def _aggregate_dog_plan_batch(dog_all: pd.DataFrame) -> pd.DataFrame:
    """Агрегация плана Dogovor по ВСЕМ файлам за один проход (вместо per-file groupby).

    Вход: сырые отфильтрованные строки всех файлов с ``__order__`` (индекс файла по
    возрастанию даты снапшота), ``__cn__`` (contract_name, stripped), ``__key__``
    (сигнатура договора/ДС). Логика идентична прежней per-file + cross-file:
      1) в пределах файла по сигнатуре договора: ДС замещает «Дог.»/«Договор»;
      2) в пределах файла SUM по разным договорам пары (pid, cid);
      3) между файлами — значение из последнего снапшота (last по ``__order__``,
         пропуская NaN); имена — первое непустое; contract_name — последнее непустое.

    Ключ группировки включает ``__order__``, поэтому шаги 1–2 остаются
    «поф айловыми», но выполняются одним groupby на весь объём, а не 528 раз.
    """
    if dog_all is None or dog_all.empty:
        return dog_all
    dog_all = dog_all.copy()
    # plan_* приходят из _snapshot_history смешанными типами (int/float/None) →
    # object dtype, из-за чего groupby.max()/.sum() уходят в pure-python
    # (_agg_py_fallback, ~сотни тысяч numpy.max по группам). Приводим к float —
    # значения числовые, результат идентичен, но включается cython-путь.
    for _c in ("plan_workers", "plan_equipment"):
        dog_all[_c] = pd.to_numeric(dog_all[_c], errors="coerce")
    grp_pf = ["__order__", "project_id", "contractor_id"]
    # 1) По сигнатуре договора внутри файла: ДС замещает «Дог.»/«Договор» (не SUM/MAX с базой)
    parts = []
    for keys, chunk in dog_all.groupby(grp_pf + ["__key__"], dropna=False):
        order, pid, cid, ckey = keys
        merged = _merge_dogovor_primary_ds_plan(chunk)
        parts.append(
            {
                "__order__": order,
                "project_id": pid,
                "contractor_id": cid,
                "__key__": ckey,
                "plan_workers": merged.get("plan_workers", np.nan),
                "plan_equipment": merged.get("plan_equipment", np.nan),
            }
        )
    per_key = pd.DataFrame(parts)
    # 2) SUM по разным договорам пары внутри файла
    plan_pf = per_key.groupby(grp_pf, dropna=False, as_index=False)[
        ["plan_workers", "plan_equipment"]
    ].sum(min_count=1)
    # 3) cross-file: последнее непустое значение плана (по __order__)
    plan_pf = plan_pf.sort_values("__order__", kind="stable")
    plan_final = plan_pf.groupby(
        ["project_id", "contractor_id"], dropna=False, as_index=False
    )[["plan_workers", "plan_equipment"]].last()

    # Имена: сначала first в пределах файла (как в прежнем meta), затем cross-file
    # первое непустое (маска пустых → NaN + cython first, пропускающий NaN).
    names_pf = dog_all.groupby(grp_pf, dropna=False, as_index=False).agg(
        project_name=("project_name", "first"),
        contractor_name=("contractor_name", "first"),
    )
    names_pf = names_pf.sort_values("__order__", kind="stable")
    for _nc in ("project_name", "contractor_name"):
        _stripped = names_pf[_nc].astype(str).str.strip()
        _empty = _stripped.eq("") | _stripped.str.casefold().isin(["nan", "none"])
        names_pf[_nc] = names_pf[_nc].astype("object").where(~_empty, np.nan)
    names_final = names_pf.groupby(
        ["project_id", "contractor_id"], dropna=False, as_index=False
    ).agg(
        project_name=("project_name", "first"),
        contractor_name=("contractor_name", "first"),
    )
    for _nc in ("project_name", "contractor_name"):
        names_final[_nc] = names_final[_nc].where(names_final[_nc].notna(), "")

    # contract_name: склейка sorted(unique) имён договоров в пределах файла (по паре)
    # одним O(n) проходом по numpy, затем cross-file последнее непустое.
    cn_src = dog_all.loc[
        dog_all["__cn__"] != "", ["__order__", "project_id", "contractor_id", "__cn__"]
    ].drop_duplicates()
    if cn_src.empty:
        contract_final = pd.DataFrame(
            columns=["project_id", "contractor_id", "contract_name"]
        )
    else:
        cn_src = cn_src.sort_values(
            ["__order__", "project_id", "contractor_id", "__cn__"], kind="stable"
        )
        _o = cn_src["__order__"].to_numpy()
        _pid = cn_src["project_id"].to_numpy()
        _cid = cn_src["contractor_id"].to_numpy()
        _cnv = cn_src["__cn__"].to_numpy()
        _ko, _kp, _kc, _vals = [], [], [], []
        _n = len(_cnv)
        _i = 0
        while _i < _n:
            _j = _i + 1
            while (
                _j < _n
                and _o[_j] == _o[_i]
                and _pid[_j] == _pid[_i]
                and _cid[_j] == _cid[_i]
            ):
                _j += 1
            _ko.append(_o[_i])
            _kp.append(_pid[_i])
            _kc.append(_cid[_i])
            _vals.append(" · ".join(_cnv[_i:_j]))
            _i = _j
        cn_pf = pd.DataFrame(
            {"__order__": _ko, "project_id": _kp, "contractor_id": _kc, "contract_name": _vals}
        ).sort_values("__order__", kind="stable")
        contract_final = cn_pf.groupby(
            ["project_id", "contractor_id"], dropna=False, as_index=False
        )["contract_name"].last()

    out = names_final.merge(plan_final, on=["project_id", "contractor_id"], how="left")
    out = out.merge(contract_final, on=["project_id", "contractor_id"], how="left")
    out["contract_name"] = out["contract_name"].where(out["contract_name"].notna(), "")
    return out[
        [
            "project_id", "contractor_id", "project_name", "contractor_name",
            "contract_name", "plan_workers", "plan_equipment",
        ]
    ]


def load_plan_aggregate(
    dogovor_paths: Iterable[Path | str] = (),
    sprav_paths: Iterable[Path | str] = (),
    *,
    dogovor_records: dict[str, list[dict]] | None = None,
    sprav_records: dict[str, list[dict]] | None = None,
    snapshot_date: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    """Загрузить план из ВСЕХ файлов Dogovor.json + spravochniki.json
    и агрегировать в единую таблицу.

    Алгоритм:
        - Dogovor: **всегда последний файл выгрузки** (max дата в имени); период фильтра
          задаёт только snapshot_date для полей «Дата»/«Количество» внутри JSON и сроков
          договора — не отбор файлов по дате в имени.
        - Для каждого Dogovor.json берём snapshot на дату snapshot_date.
        - Внутри файла план по (project_id, contractor_id) суммируется по РАЗНЫМ
          договорам, но дубли одного договора и его доп.соглашений (ДС) схлопываются
          по сигнатуре «NN-СА/YY» (в т.ч. номер из поля Номер_Договора для «ДС …»):
          ДС замещает базовый «Дог.»/«Договор», если в ДС на срез есть >0; иначе база.
        - Между файлами берём значение из ПОСЛЕДНЕГО снапшота ≤ snapshot_date
          (по дате в имени файла), а не MAX по дням: max завышал план, цепляясь
          за день с лишними/транзитными строками ДС.
        - spravochniki.json — fallback, если в Dogovor плана нет.
    """
    def _per_file_dog(p: Path | str, *, records: list[dict] | None = None) -> pd.DataFrame:
        if records is not None:
            df = load_plan_from_dogovor(
                records=records, snapshot_date=snapshot_date, cache_key=str(p)
            )
        else:
            df = load_plan_from_dogovor(Path(p), snapshot_date=snapshot_date)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df[
            (df["project_id"].astype(str).str.strip() != "")
            & (df["contractor_id"].astype(str).str.strip() != "")
        ]
        if df.empty:
            return pd.DataFrame()
        _fsk = _dogovor_snapshot_sort_key(p)
        _file_snap = None if _fsk[0] is pd.Timestamp.min else pd.Timestamp(_fsk[0]).normalize()
        df = _apply_gdrs_dogovor_plan_exclusions(
            df,
            snapshot_date=snapshot_date,
            file_snapshot_date=_file_snap,
        )
        if df.empty:
            return pd.DataFrame()
        # Возвращаем СЫРОЙ отфильтрованный кадр (+ __cn__/__key__). Агрегацию
        # (MAX по сигнатуре договора → SUM по паре → cross-file last) делаем один
        # раз батчем по всем файлам в _aggregate_dog_plan_batch: раньше здесь на
        # КАЖДЫЙ файл (×528) гонялись 3-4 groupby, накладные которых и давали
        # основную задержку ГДРС.
        df = df.copy()
        cn = df["contract_name"].fillna("").astype(str).str.strip()
        df["__cn__"] = cn
        df["__key__"] = _dogovor_row_contract_keys(df)
        return df[
            [
                "project_id", "contractor_id", "project_name", "contractor_name",
                "contract_name", "__cn__", "__key__", "plan_workers", "plan_equipment",
            ]
        ]

    def _per_file_sprav(p: Path | str, *, records: list[dict] | None = None) -> pd.DataFrame:
        if records is not None:
            df = load_plan_from_spravochniki(records=records, snapshot_date=snapshot_date)
        else:
            df = load_plan_from_spravochniki(Path(p), snapshot_date=snapshot_date)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df[(df["project_id"].astype(str).str.strip() != "") & (df["contractor_id"].astype(str).str.strip() != "")]
        if df.empty:
            return pd.DataFrame()
        return (
            df.groupby(["project_id", "contractor_id"], dropna=False, as_index=False)[
                ["plan_workers", "plan_equipment"]
            ]
            .sum(min_count=1)
        )

    def _ordered_with_index(paths, fn, *, records_map: dict[str, list[dict]] | None = None) -> pd.DataFrame:
        """Собрать кадры по файлам, упорядочив по дате снапшота из имени (asc)."""
        snap = pd.Timestamp(snapshot_date).normalize() if snapshot_date is not None else None
        items_le: list[tuple[tuple[pd.Timestamp, str], pd.DataFrame]] = []
        items_future: list[tuple[tuple[pd.Timestamp, str], pd.DataFrame]] = []
        if records_map is not None:
            path_iter = sorted(records_map.keys())
        else:
            path_iter = list(paths)
        for p in path_iter:
            sk = _dogovor_snapshot_sort_key(p)
            if records_map is not None:
                fr = fn(p, records=records_map.get(str(p), []))
            else:
                fr = fn(Path(p))
            if fr is None or fr.empty:
                continue
            if snap is not None and sk[0] is not pd.Timestamp.min and sk[0] > snap:
                items_future.append((sk, fr))
            else:
                items_le.append((sk, fr))
        items = items_le
        if not items and items_future:
            items_future.sort(key=lambda t: t[0])
            items = [items_future[-1]]
        items.sort(key=lambda t: t[0])
        for i, (_, fr) in enumerate(items):
            fr["__order__"] = i
        return pd.concat([fr for _, fr in items], ignore_index=True) if items else pd.DataFrame()

    def _latest_dogovor_records_map(records_map: dict[str, list[dict]]) -> dict[str, list[dict]]:
        """План Dogovor: всегда последний файл выгрузки (дата в имени max)."""
        if not records_map:
            return {}
        latest = max(
            records_map.keys(),
            key=lambda s: (_dogovor_snapshot_sort_key(s), str(s)),
        )
        return {latest: records_map[latest]}

    def _latest_dogovor_paths(paths: Iterable[Path | str]) -> list:
        lst = list(paths)
        if not lst:
            return []
        return [max(lst, key=lambda p: (_dogovor_snapshot_sort_key(p), str(p)))]

    if dogovor_records is not None:
        dog_all = _ordered_with_index(
            [], _per_file_dog, records_map=_latest_dogovor_records_map(dogovor_records)
        )
    else:
        dog_all = _ordered_with_index(_latest_dogovor_paths(dogovor_paths), _per_file_dog)
    if sprav_records is not None:
        sprav_all = _ordered_with_index([], _per_file_sprav, records_map=sprav_records)
    else:
        sprav_all = _ordered_with_index(sprav_paths, _per_file_sprav)

    if not dog_all.empty:
        dog_all = _aggregate_dog_plan_batch(dog_all)
    if not sprav_all.empty:
        sprav_all = sprav_all.sort_values("__order__")
        sprav_all = (
            sprav_all.groupby(["project_id", "contractor_id"], dropna=False, as_index=False)
            .agg(plan_workers=("plan_workers", "last"), plan_equipment=("plan_equipment", "last"))
        )
    merged = merge_plan(dog_all, sprav_all)
    if merged is not None and not merged.empty and "project_name" in merged.columns:
        try:
            from dashboards.project_labels import apply_unified_project_column

            merged = apply_unified_project_column(merged, "project_name")
        except Exception:
            pass
    return merged


def _norm_header_key(k: object) -> str:
    return re.sub(r"[\s_\-]", "", str(k).casefold().replace("ё", "е"))


def _pick_row_field_ci(row: dict, *aliases: str) -> str:
    """
    Значение поля по имени колонки (алиасы, без учёта регистра / пробелов / подчёркиваний).
    """
    if not isinstance(row, dict) or not row:
        return ""
    canon = {_norm_header_key(k): v for k, v in row.items()}
    for alias in aliases:
        nk = _norm_header_key(alias)
        if nk in canon:
            val = canon[nk]
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return ""
            return str(val).strip()
    for alias in aliases:
        na = _norm_header_key(alias)
        for nk_key, v in canon.items():
            if na and (na in nk_key or nk_key.endswith(na)):
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    continue
                return str(v).strip()
    return ""


def load_1c_dannye_article_maps(
    paths: Iterable[Path | str],
) -> tuple[
    dict[str, str],
    dict[tuple[str, str], str],
    dict[tuple[str, str, str], set[str]],
    dict[str, set[str]],
    dict[tuple[str, str], set[str]],
]:
    """
    Из `*dannye*.json` строит:
    1) По договору: normalize(ДоговорКонтрагента) → СтатьяОборотов (как в выгрузке 1С).
    2) Fallback по паре: (normalize(Проект), normalize(Контрагент)) → объединённые статьи,
       т.к. в данных «ДоговорКонтрагента» в оборотах часто не совпадает с «Наименование_Договора»
       в договорах (разные форматы строк).
    3) По сигнатуре договора (`NN-СА/YY` / `NN-СА_YY`) + проект + контрагент — наборы статей
       для сопоставления с длинными строками Dogovor.
    4) По сигнатуре без контекста — запасной словарь наборов статей.
    """
    from collections import defaultdict

    acc_dog: dict[str, set[str]] = defaultdict(set)
    acc_pc: dict[tuple[str, str], set[str]] = defaultdict(set)
    acc_sig: dict[str, set[str]] = defaultdict(set)
    acc_sig_pc: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for raw_path in paths:
        p = Path(raw_path)
        if not p.is_file():
            continue
        data = _safe_json(p)
        if not isinstance(data, list):
            continue
        for r in data:
            if not isinstance(r, dict):
                continue
            art = _pick_row_field_ci(
                r,
                "СтатьяОборотов",
                "Статья оборотов",
                "Article",
            )
            if not art:
                continue
            art_s = str(art).strip()
            dog = _pick_row_field_ci(
                r,
                "ДоговорКонтрагента",
                "Договор контрагента",
            )
            proj = _pick_row_field_ci(r, "Проект", "Project")
            contr = _pick_row_field_ci(r, "Контрагент", "Контрагенты", "Counterparty")
            pn = normalize_name(proj) if proj else ""
            cn = normalize_name(contr) if contr else ""
            if dog:
                acc_dog[normalize_name(dog)].add(art_s)
                for sig in contract_signatures(dog):
                    acc_sig[sig].add(art_s)
                    if pn and cn:
                        acc_sig_pc[(sig, pn, cn)].add(art_s)
            if proj and contr:
                acc_pc[(pn, cn)].add(art_s)
    out_dog = {k: " · ".join(sorted(v)) for k, v in acc_dog.items() if k}
    out_pc = {k: " · ".join(sorted(v)) for k, v in acc_pc.items() if k[0] and k[1]}
    out_sig_pc_sets = {k: set(v) for k, v in acc_sig_pc.items()}
    out_sig_sets = {k: set(v) for k, v in acc_sig.items()}
    pc_sets = {k: set(v) for k, v in acc_pc.items() if k[0] and k[1]}
    return out_dog, out_pc, out_sig_pc_sets, out_sig_sets, pc_sets


def load_1c_dannye_article_maps_from_df(
    df: pd.DataFrame,
) -> tuple[
    dict[str, str],
    dict[tuple[str, str], str],
    dict[tuple[str, str, str], set[str]],
    dict[str, set[str]],
    dict[tuple[str, str], set[str]],
]:
    """Как load_1c_dannye_article_maps, но из строк reference_dannye в БД."""
    if df is None or df.empty:
        return {}, {}, {}, {}, {}
    rows = df.to_dict(orient="records")
    return load_1c_dannye_article_maps_from_records(rows)


def load_1c_dannye_article_maps_from_records(
    records: Iterable[dict],
) -> tuple[
    dict[str, str],
    dict[tuple[str, str], str],
    dict[tuple[str, str, str], set[str]],
    dict[str, set[str]],
    dict[tuple[str, str], set[str]],
]:
    from collections import defaultdict

    acc_dog: dict[str, set[str]] = defaultdict(set)
    acc_pc: dict[tuple[str, str], set[str]] = defaultdict(set)
    acc_sig: dict[str, set[str]] = defaultdict(set)
    acc_sig_pc: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for r in records:
        if not isinstance(r, dict):
            continue
        art = _pick_row_field_ci(
            r,
            "СтатьяОборотов",
            "Статья оборотов",
            "Article",
        )
        if not art:
            continue
        art_s = str(art).strip()
        dog = _pick_row_field_ci(
            r,
            "ДоговорКонтрагента",
            "Договор контрагента",
        )
        proj = _pick_row_field_ci(r, "Проект", "Project")
        contr = _pick_row_field_ci(r, "Контрагент", "Контрагенты", "Counterparty")
        pn = normalize_name(proj) if proj else ""
        cn = normalize_name(contr) if contr else ""
        if dog:
            acc_dog[normalize_name(dog)].add(art_s)
            for sig in contract_signatures(dog):
                acc_sig[sig].add(art_s)
                if pn and cn:
                    acc_sig_pc[(sig, pn, cn)].add(art_s)
        if proj and contr:
            acc_pc[(pn, cn)].add(art_s)
    out_dog = {k: " · ".join(sorted(v)) for k, v in acc_dog.items() if k}
    out_pc = {k: " · ".join(sorted(v)) for k, v in acc_pc.items() if k[0] and k[1]}
    out_sig_pc_sets = {k: set(v) for k, v in acc_sig_pc.items()}
    out_sig_sets = {k: set(v) for k, v in acc_sig.items()}
    pc_sets = {k: set(v) for k, v in acc_pc.items() if k[0] and k[1]}
    return out_dog, out_pc, out_sig_pc_sets, out_sig_sets, pc_sets


def load_1c_dannye_article_by_contract(paths: Iterable[Path | str]) -> dict[str, str]:
    """
    Из файлов `1с_*dannye*.json` (и др. *dannye*.json): словарь
    normalize(ДоговорКонтрагента) → объединённая СтатьяОборотов.

    Сопоставление с договором из Dogovor: то же наименование, что «Наименование_Договора»,
    сверяется через normalize_name (как и для полей в таблице ГДРС).

    См. также `load_1c_dannye_article_maps` — при несовпадении строк договора используется
    пара (Проект, Контрагент) в `build_main_table`.
    """
    d, _, _, _, _ = load_1c_dannye_article_maps(paths)
    return d


def _article_one_contract_part(
    part: str,
    article_by_norm: Optional[dict[str, str]],
    article_sig_pc_sets: Optional[dict[tuple[str, str, str], set[str]]],
    article_sig_sets: Optional[dict[str, set[str]]],
    pn: str,
    cn: str,
    contract_hint: str,
) -> str:
    if not part:
        return ""
    nk = normalize_name(part)
    if article_by_norm and nk in article_by_norm:
        raw = article_by_norm[nk]
        if " · " in raw:
            return _pick_best_articles(set(re.split(r"\s*·\s*", raw)), contract_hint)
        return raw
    for sig in contract_signatures(part):
        if article_sig_pc_sets and pn and cn:
            k3 = (sig, pn, cn)
            if k3 in article_sig_pc_sets:
                return _pick_best_articles(article_sig_pc_sets[k3], contract_hint)
    for sig in contract_signatures(part):
        if article_sig_sets and sig in article_sig_sets:
            return _pick_best_articles(article_sig_sets[sig], contract_hint)
    return ""


def _article_for_contract_name(
    contract_name: str,
    article_by_norm: Optional[dict[str, str]],
    article_sig_pc_sets: Optional[dict[tuple[str, str, str], set[str]]],
    article_sig_sets: Optional[dict[str, set[str]]],
    project_name: str,
    contractor_name: str,
) -> str:
    if not str(contract_name or "").strip():
        return ""
    s = str(contract_name).strip()
    pn = normalize_name(project_name or "")
    cn = normalize_name(contractor_name or "")
    hint = s
    parts = re.split(r"\s*·\s*", s)
    got: list[str] = []
    for part in parts:
        one = _article_one_contract_part(
            part.strip(),
            article_by_norm,
            article_sig_pc_sets,
            article_sig_sets,
            pn,
            cn,
            hint,
        )
        if one:
            got.append(one)
    if not got:
        whole = normalize_name(s)
        if article_by_norm and whole in article_by_norm:
            raw = article_by_norm[whole]
            if " · " in raw:
                return _pick_best_articles(set(re.split(r"\s*·\s*", raw)), hint)
            return raw
        return ""
    if len(got) == 1:
        return got[0]
    return _pick_best_articles(set(got), hint)


def _article_from_project_contractor(
    project_name: str,
    contractor_name: str,
    article_pc: Optional[dict[tuple[str, str], str]],
    article_pc_sets: Optional[dict[tuple[str, str], set[str]]],
    contract_hint: str,
) -> str:
    pn = normalize_name(project_name or "")
    cn = normalize_name(contractor_name or "")
    if not pn or not cn:
        return ""
    key = (pn, cn)
    if article_pc_sets and key in article_pc_sets:
        return _pick_best_articles(article_pc_sets[key], contract_hint)
    if article_pc and key in article_pc:
        raw = article_pc[key]
        if " · " in raw:
            return _pick_best_articles(set(re.split(r"\s*·\s*", raw)), contract_hint)
        return raw
    return ""


def _vid_raboty_display(
    contract_name: str,
    article_by_norm: Optional[dict[str, str]],
    article_sig_pc_sets: Optional[dict[tuple[str, str, str], set[str]]] = None,
    article_sig_sets: Optional[dict[str, set[str]]] = None,
    article_by_project_contractor: Optional[dict[tuple[str, str], str]] = None,
    article_pc_sets: Optional[dict[tuple[str, str], set[str]]] = None,
    project_name: str = "",
    contractor_name: str = "",
) -> str:
    art = _article_for_contract_name(
        contract_name,
        article_by_norm,
        article_sig_pc_sets,
        article_sig_sets,
        project_name,
        contractor_name,
    )
    if art:
        return art
    art2 = _article_from_project_contractor(
        project_name,
        contractor_name,
        article_by_project_contractor,
        article_pc_sets,
        str(contract_name or ""),
    )
    if art2:
        return art2
    return extract_vid_raboty(str(contract_name or ""))


def merge_plan(dogovor: pd.DataFrame, sprav: pd.DataFrame) -> pd.DataFrame:
    """Слить план из Dogovor (приоритет) и spravochniki (fallback) per (project_id, contractor_id).

    Если у нескольких договоров на один (project_id, contractor_id) есть план — суммируем.
    """
    if dogovor is None or dogovor.empty:
        d = pd.DataFrame(
            columns=[
                "project_id", "contractor_id", "project_name", "contractor_name",
                "contract_name", "plan_workers", "plan_equipment",
            ]
        )
    else:
        # Прежде project_name/contractor_name считались python-функцией _first_nonempty,
        # а contract_name — lambda-join: оба гнали groupby по pure-python пути
        # (_aggregate_series_pure_python, секунды). Векторизуем, сохраняя семантику:
        #   - имена: первое непустое (stripped) значение в порядке строк группы;
        #   - contract_name: " · ".join(sorted(уникальных непустых)).
        keys = ["project_id", "contractor_id"]
        tmp = dogovor.copy()
        for _nc in ("project_name", "contractor_name"):
            _stripped = tmp[_nc].astype(str).str.strip()
            _empty = _stripped.eq("") | _stripped.str.casefold().isin(["nan", "none"])
            # Храним именно stripped-значение (как возвращал _first_nonempty).
            tmp[_nc] = _stripped.where(~_empty, np.nan)
        gd = tmp.groupby(keys, dropna=False, as_index=False)
        d = gd.agg(
            project_name=("project_name", "first"),
            contractor_name=("contractor_name", "first"),
        )
        for _nc in ("project_name", "contractor_name"):
            d[_nc] = d[_nc].where(d[_nc].notna(), "")
        # contract_name: sorted(unique непустых) одним O(n) проходом по numpy.
        _cn = dogovor["contract_name"]
        cn_src = dogovor.loc[
            _cn.notna() & (_cn.astype(str) != ""), keys + ["contract_name"]
        ].drop_duplicates()
        if cn_src.empty:
            d["contract_name"] = ""
        else:
            cn_src = cn_src.sort_values(keys + ["contract_name"], kind="stable")
            _pid = cn_src["project_id"].to_numpy()
            _cid = cn_src["contractor_id"].to_numpy()
            _cnv = cn_src["contract_name"].to_numpy()
            _kp, _kc, _vals = [], [], []
            _n = len(_cnv)
            _i = 0
            while _i < _n:
                _j = _i + 1
                while _j < _n and _pid[_j] == _pid[_i] and _cid[_j] == _cid[_i]:
                    _j += 1
                _kp.append(_pid[_i])
                _kc.append(_cid[_i])
                _vals.append(" · ".join(_cnv[_i:_j]))
                _i = _j
            _cn_join = pd.DataFrame(
                {"project_id": _kp, "contractor_id": _kc, "contract_name": _vals}
            )
            d = d.merge(_cn_join, on=keys, how="left")
            d["contract_name"] = d["contract_name"].fillna("")
        # План — cython sum(min_count=1); выравниваем по ключам через merge.
        d_sum = dogovor.groupby(keys, dropna=False, as_index=False)[
            ["plan_workers", "plan_equipment"]
        ].sum(min_count=1)
        d = d.merge(d_sum, on=keys, how="left")
    if sprav is not None and not sprav.empty:
        s = (
            sprav.groupby(["project_id", "contractor_id"], dropna=False, as_index=False)[
                ["plan_workers", "plan_equipment"]
            ]
            .sum(min_count=1)
            .rename(columns={"plan_workers": "plan_workers_s", "plan_equipment": "plan_equipment_s"})
        )
        merged = d.merge(s, on=["project_id", "contractor_id"], how="outer")
        merged["plan_workers"] = merged["plan_workers"].combine_first(merged["plan_workers_s"])
        merged["plan_equipment"] = merged["plan_equipment"].combine_first(merged["plan_equipment_s"])
        merged = merged.drop(columns=["plan_workers_s", "plan_equipment_s"], errors="ignore")
        # spravochniki даёт только ID+план: outer-join оставляет NaN в именах.
        # Подтягиваем Наименование_Проекта / контрагента из других строк Dogovor
        # с тем же project_id / contractor_id (иначе в сводке появляется «пустой» проект).
        if not d.empty:
            _pid_name = (
                d.loc[d["project_name"].astype(str).str.strip().ne(""), ["project_id", "project_name"]]
                .drop_duplicates("project_id", keep="first")
                .set_index("project_id")["project_name"]
            )
            _cid_name = (
                d.loc[
                    d["contractor_name"].astype(str).str.strip().ne(""),
                    ["contractor_id", "contractor_name"],
                ]
                .drop_duplicates("contractor_id", keep="first")
                .set_index("contractor_id")["contractor_name"]
            )
            _pn = merged["project_name"]
            _pn_blank = _pn.isna() | _pn.astype(str).str.strip().str.casefold().isin(
                ("", "nan", "none")
            )
            if _pn_blank.any() and not _pid_name.empty:
                merged.loc[_pn_blank, "project_name"] = (
                    merged.loc[_pn_blank, "project_id"].map(_pid_name)
                )
            _cn = merged["contractor_name"]
            _cn_blank = _cn.isna() | _cn.astype(str).str.strip().str.casefold().isin(
                ("", "nan", "none")
            )
            if _cn_blank.any() and not _cid_name.empty:
                merged.loc[_cn_blank, "contractor_name"] = (
                    merged.loc[_cn_blank, "contractor_id"].map(_cid_name)
                )
        for _nc in ("project_name", "contractor_name", "contract_name"):
            if _nc in merged.columns:
                merged[_nc] = merged[_nc].fillna("")
        return merged
    return d


# =====================================================================
# Сборка таблицы (Скрин 11)
# =====================================================================

def _build_plan_lookup(plan: Optional[pd.DataFrame], plan_col: str) -> tuple[dict, dict, dict]:
    """Возвращает три словаря для матчинга плана:
    by_id        — (project_id, contractor_id)         → plan_value
    by_id_name   — (project_id, contractor_name_norm)  → plan_value
    by_norm_name — (project_name_norm, contractor_name_norm) → plan_value
    Также contract_lookup_by_norm — для подписи «Вид работы» (Наименование_Договора).
    """
    by_id: dict = {}
    by_id_name: dict = {}
    by_norm_name: dict = {}
    contract_by_norm: dict = {}
    if plan is None or plan.empty:
        return by_id, by_id_name, by_norm_name
    cols = plan.columns
    # iterrows строит pd.Series на каждую строку (113k Series.__init__ в профиле);
    # читаем нужные столбцы в numpy и идём zip-ом — логика аккумуляции прежняя.
    # normalize_name уже кеширован (lru_cache), поэтому повторные имена дешёвые.
    if plan_col not in cols:
        by_id_name["__contract_by_norm__"] = contract_by_norm
        return by_id, by_id_name, by_norm_name
    n = len(plan)
    vals = pd.to_numeric(plan[plan_col], errors="coerce").to_numpy()
    proj_id_arr = plan["project_id"].astype(str).str.strip().to_numpy() if "project_id" in cols else None
    contr_id_arr = plan["contractor_id"].astype(str).str.strip().to_numpy() if "contractor_id" in cols else None
    proj_name_arr = plan["project_name"].to_numpy() if "project_name" in cols else None
    contr_name_arr = plan["contractor_name"].to_numpy() if "contractor_name" in cols else None
    has_cn = "contract_name" in cols
    cn_arr = (
        plan["contract_name"].fillna("").astype(str).str.strip().to_numpy()
        if has_cn
        else None
    )
    for i in range(n):
        v = vals[i]
        if pd.isna(v):
            continue
        v = float(v)
        proj_id = proj_id_arr[i] if proj_id_arr is not None else ""
        contr_id = contr_id_arr[i] if contr_id_arr is not None else ""
        proj_norm = normalize_name(proj_name_arr[i]) if proj_name_arr is not None else ""
        contr_norm = normalize_name(contr_name_arr[i]) if contr_name_arr is not None else ""
        contract_name = str(cn_arr[i]).strip() if has_cn else ""
        if contract_name.lower() in ("nan", "none", "null", "<na>"):
            contract_name = ""
        if proj_id and contr_id:
            by_id[(proj_id, contr_id)] = by_id.get((proj_id, contr_id), 0.0) + v
        if proj_id and contr_norm:
            by_id_name[(proj_id, contr_norm)] = by_id_name.get((proj_id, contr_norm), 0.0) + v
        if proj_norm and contr_norm:
            by_norm_name[(proj_norm, contr_norm)] = by_norm_name.get((proj_norm, contr_norm), 0.0) + v
        if contract_name and proj_norm and contr_norm:
            existing = str(contract_by_norm.get((proj_norm, contr_norm), "") or "").strip()
            if contract_name not in existing:
                contract_by_norm[(proj_norm, contr_norm)] = (
                    f"{existing} · {contract_name}".strip(" ·") if existing else contract_name
                )
    by_id_name["__contract_by_norm__"] = contract_by_norm  # piggyback
    return by_id, by_id_name, by_norm_name


def _gdrs_dynamics_period_freq(agg_kind: str) -> str:
    k = str(agg_kind or "").strip().casefold()
    if k == "день":
        return "D"
    if k == "неделя":
        return "W"
    if k == "месяц":
        return "M"
    if k == "год":
        return "Y"
    return "W"


def _gdrs_month_iso_week_keys(year: int, month: int) -> list[int]:
    """ISO-ключи (year*100+week) недель месяца в порядке дат — как надстрока resursi 1С."""
    month_start = pd.Timestamp(int(year), int(month), 1)
    month_end = month_start + pd.offsets.MonthEnd(0)
    grid = pd.date_range(month_start, month_end, freq="D")
    iso = grid.isocalendar()
    keys = (iso["year"].astype(int) * 100 + iso["week"].astype(int)).tolist()
    return list(dict.fromkeys(keys))


def _gdrs_month_week_bounds(
    year: int,
    month: int,
    week_num: int,
) -> tuple[Optional[pd.Timestamp], Optional[pd.Timestamp]]:
    """Границы N-й недели месяца (пн–вс / ISO, обрезанные днями месяца), как в resursi."""
    wn = int(week_num)
    if wn < 1 or wn > 6:
        return None, None
    month_start = pd.Timestamp(int(year), int(month), 1)
    month_end = month_start + pd.offsets.MonthEnd(0)
    keys = _gdrs_month_iso_week_keys(year, month)
    if wn > len(keys):
        return None, None
    target = keys[wn - 1]
    grid = pd.date_range(month_start, month_end, freq="D")
    iso = grid.isocalendar()
    key_s = iso["year"].astype(int) * 100 + iso["week"].astype(int)
    mask = key_s == target
    if not mask.any():
        return None, None
    days = grid[mask]
    return pd.Timestamp(days.min()).normalize(), pd.Timestamp(days.max()).normalize()


def _gdrs_calendar_week_num(day: pd.Timestamp, month_lo: pd.Timestamp) -> int:
    """Номер недели месяца 1..6: ISO-недели (пн–вс) внутри месяца, как в выгрузке resursi 1С."""
    d = pd.Timestamp(day).normalize()
    lo = pd.Timestamp(month_lo).normalize()
    y, m = int(lo.year), int(lo.month)
    if int(d.year) != y or int(d.month) != m:
        y, m = int(d.year), int(d.month)
    keys = _gdrs_month_iso_week_keys(y, m)
    if not keys:
        return 1
    d_iso = d.isocalendar()
    d_key = int(d_iso.year) * 100 + int(d_iso.week)
    try:
        wn = keys.index(d_key) + 1
    except ValueError:
        wn = 1
    return min(max(wn, 1), 6)


def _gdrs_plan_expiry_week_start(snap: pd.Timestamp) -> pd.Timestamp:
    """Первый день ISO-недели месяца (в границах месяца) для проверки date_end."""
    d = pd.Timestamp(snap).normalize()
    wn = _gdrs_calendar_week_num(d, pd.Timestamp(d.year, d.month, 1))
    start, _ = _gdrs_month_week_bounds(d.year, d.month, wn)
    return start if start is not None else pd.Timestamp(d.year, d.month, 1)


def _gdrs_calendar_days_in_week(
    date_from: pd.Timestamp,
    date_to: pd.Timestamp,
    week_num: int,
) -> int:
    """Число календарных дней N-й недели в периоде (пересечение с date_from..date_to)."""
    lo = pd.Timestamp(date_from).normalize()
    hi = pd.Timestamp(date_to).normalize()
    wn = int(week_num)
    if wn < 1 or wn > 6 or hi < lo:
        return 0
    if _gdrs_single_calendar_month(lo, hi):
        week_lo, week_hi = _gdrs_month_week_bounds(lo.year, lo.month, wn)
        if week_lo is None or week_hi is None:
            return 0
        eff_lo = max(week_lo, lo)
        eff_hi = min(week_hi, hi)
        if eff_hi < eff_lo:
            return 0
        return int((eff_hi - eff_lo).days) + 1
    grid = pd.date_range(lo, hi, freq="D")
    if len(grid) == 0:
        return 0
    week_idx, _ = _iso_week_groups(pd.Series(grid))
    mask = week_idx == wn
    if not mask.any():
        return 0
    return int(mask.sum())


def _gdrs_calendar_week_bucket_start(day: pd.Timestamp, month_lo: pd.Timestamp) -> pd.Timestamp:
    lo = pd.Timestamp(month_lo).normalize()
    d = pd.Timestamp(day).normalize()
    wn = _gdrs_calendar_week_num(d, lo)
    start, _ = _gdrs_month_week_bounds(lo.year, lo.month, wn)
    return start if start is not None else pd.Timestamp(lo.year, lo.month, 1)


def _gdrs_dynamics_month_lo_for_day(day: pd.Timestamp) -> pd.Timestamp:
    d = pd.Timestamp(day).normalize()
    return pd.Timestamp(d.year, d.month, 1)


def _gdrs_bucket_calendar_week_num(
    bucket_start: pd.Timestamp,
    *,
    date_from: Optional[pd.Timestamp] = None,
    date_to: Optional[pd.Timestamp] = None,
) -> Optional[int]:
    """Номер ISO-недели месяца (1–6) для bucket/дня — как в resursi 1С."""
    b = pd.Timestamp(bucket_start).normalize()
    lo = pd.Timestamp(date_from).normalize() if date_from is not None else None
    hi = pd.Timestamp(date_to).normalize() if date_to is not None else None
    if lo is not None and hi is not None and _gdrs_single_calendar_month(lo, hi):
        return _gdrs_calendar_week_num(b, lo)
    return _gdrs_calendar_week_num(b, _gdrs_dynamics_month_lo_for_day(b))


def _gdrs_day_matches_week_filter(
    day: pd.Timestamp,
    bucket: pd.Timestamp,
    agg_kind: str,
    week_num: int,
    date_from: pd.Timestamp,
    date_to: pd.Timestamp,
) -> bool:
    """День попадает в выбранную N-ю неделю месяца (фильтры План/СКУД)."""
    d = pd.Timestamp(day).normalize()
    b = pd.Timestamp(bucket).normalize()
    kind = str(agg_kind or "").strip().casefold()
    month_lo = _gdrs_dynamics_month_lo_for_day(d if kind == "день" else b)
    if _gdrs_calendar_week_num(d, month_lo) != int(week_num):
        return False
    if kind == "неделя":
        week_end = b + pd.Timedelta(days=6)
        return d >= b and d <= week_end
    return True


def _gdrs_dynamics_week_filter_suffix(
    plan_agg: str,
    skud_agg: str,
) -> str:
    """Суффикс подписи периода при фильтре по неделе."""
    pw = gdrs_agg_week_num(plan_agg)
    sw = gdrs_agg_week_num(skud_agg)
    if pw is None and sw is None:
        return ""
    if pw is not None and sw is not None and pw != sw:
        return f" · пн{pw}/сн{sw}"
    wn = pw if pw is not None else sw
    return f" · н{wn}"


def gdrs_dynamics_bucket_display_label(
    bucket_start: pd.Timestamp,
    agg_kind: str,
    *,
    date_from: Optional[pd.Timestamp] = None,
    date_to: Optional[pd.Timestamp] = None,
    plan_agg: str = "month_avg",
    skud_agg: str = "month_avg",
) -> str:
    """Подпись bucket для оси X (неделя — не dd.mm как «день»)."""
    b = pd.Timestamp(bucket_start).normalize()
    kind = str(agg_kind or "").strip().casefold()
    lo = pd.Timestamp(date_from).normalize() if date_from is not None else None
    hi = pd.Timestamp(date_to).normalize() if date_to is not None else None
    _wk_suffix = _gdrs_dynamics_week_filter_suffix(plan_agg, skud_agg)
    if kind == "неделя":
        if lo is not None and hi is not None and _gdrs_single_calendar_month(lo, hi):
            wn = _gdrs_calendar_week_num(b, lo)
            return f"н{wn} · {b.strftime('%m.%Y')}{_wk_suffix}"
        w_end = b + pd.Timedelta(days=6)
        if hi is not None:
            w_end = min(w_end, hi)
        return f"{b.strftime('%d.%m')}–{w_end.strftime('%d.%m.%y')}{_wk_suffix}"
    if kind == "месяц":
        return b.strftime("%m.%Y") + _wk_suffix
    if kind == "год":
        return str(b.year)
    return b.strftime("%d.%m.%Y")


def gdrs_dynamics_assign_buckets(
    dates: pd.Series,
    agg_kind: str,
    *,
    date_from: Optional[pd.Timestamp] = None,
    date_to: Optional[pd.Timestamp] = None,
) -> pd.Series:
    """Начало периода (неделя/месяц/год) для каждой даты факта — как в groupby динамики."""
    dts = pd.to_datetime(dates, errors="coerce")
    kind = str(agg_kind or "").strip().casefold()
    if kind == "неделя" and _gdrs_single_calendar_month(date_from, date_to):
        lo = pd.Timestamp(date_from).normalize()
        return dts.apply(lambda d: _gdrs_calendar_week_bucket_start(d, lo))
    freq = _gdrs_dynamics_period_freq(agg_kind)
    return dts.dt.to_period(freq).apply(lambda p: p.start_time.normalize())


def _gdrs_bucket_calendar_days(
    bucket_start: pd.Timestamp,
    agg_kind: str,
    date_from: pd.Timestamp,
    date_to: pd.Timestamp,
) -> list[pd.Timestamp]:
    """Календарные дни внутри периода группировки (пересечение с фильтром дат)."""
    b = pd.Timestamp(bucket_start).normalize()
    lo = pd.Timestamp(date_from).normalize()
    hi = pd.Timestamp(date_to).normalize()
    kind = str(agg_kind or "").strip().casefold()
    if kind == "день":
        period_end = b
    elif kind == "неделя" and _gdrs_single_calendar_month(lo, hi):
        wn = _gdrs_calendar_week_num(b, lo)
        end = gdrs_week_period_end(lo, hi, wn)
        period_end = end if end is not None and pd.notna(end) else b + pd.Timedelta(days=6)
    elif kind == "неделя":
        period_end = b + pd.Timedelta(days=6)
    elif kind == "месяц":
        period_end = (b + pd.offsets.MonthEnd(0)).normalize()
    else:
        period_end = b
    start = max(b, lo)
    end = min(period_end, hi)
    if end < start:
        return []
    return [pd.Timestamp(d).normalize() for d in pd.date_range(start, end, freq="D")]


def gdrs_dynamics_bucket_starts(
    date_from: pd.Timestamp,
    date_to: pd.Timestamp,
    agg_kind: str,
) -> pd.DatetimeIndex:
    """Все периоды в выбранном фильтре дат (включая без факта в CSV)."""
    start = pd.Timestamp(date_from).normalize()
    end = pd.Timestamp(date_to).normalize()
    if end < start:
        start, end = end, start
    kind = str(agg_kind or "").strip().casefold()
    if kind == "неделя" and _gdrs_single_calendar_month(start, end):
        month_last = int((start + pd.offsets.MonthEnd(0)).day)
        buckets: list[pd.Timestamp] = []
        for wn in range(1, 7):
            sd = (wn - 1) * 7 + 1
            if sd > month_last:
                break
            buckets.append(pd.Timestamp(start.year, start.month, sd))
        return pd.DatetimeIndex(buckets)
    freq = _gdrs_dynamics_period_freq(agg_kind)
    p0, p1 = start.to_period(freq), end.to_period(freq)
    periods = pd.period_range(p0, p1, freq=freq)
    buckets = pd.DatetimeIndex([p.start_time.normalize() for p in periods])
    return buckets.unique().sort_values()


def gdrs_plan_period_month_weighted_average(
    *,
    date_from: pd.Timestamp,
    date_to: pd.Timestamp,
    project_id: str,
    contractor_id: str,
    project_name: str,
    contractor_name: str,
    plan_col: str,
    plan_aggregate_loader: Callable[[pd.Timestamp], pd.DataFrame],
    term_index: Optional[GdrsTerminationIndex] = None,
    month_lookup_cache: Optional[dict[pd.Timestamp, tuple]] = None,
) -> float:
    """Среднее план/день за мульти-месячный период: вес по числу дней в каждом месяце."""
    lo = pd.Timestamp(date_from).normalize()
    hi = pd.Timestamp(date_to).normalize()
    if hi < lo or not pd.notna(lo) or not pd.notna(hi):
        return 0.0
    cache = month_lookup_cache if month_lookup_cache is not None else {}
    weighted = 0.0
    days_total = 0
    for per in pd.period_range(lo.to_period("M"), hi.to_period("M"), freq="M"):
        seg_lo = max(lo, per.start_time.normalize())
        seg_hi = min(hi, per.end_time.normalize())
        nd = int((seg_hi - seg_lo).days) + 1
        if nd <= 0:
            continue
        snap = pd.Timestamp(seg_hi).normalize()
        if snap not in cache:
            cache[snap] = _build_plan_lookup(plan_aggregate_loader(snap), plan_col)
        lu = cache[snap]
        weighted += nd * _lookup_plan(
            project_id,
            contractor_id,
            project_name,
            contractor_name,
            lu[0],
            lu[1],
            lu[2],
            as_of_date=snap,
            term_index=term_index,
        )
        days_total += nd
    return weighted / days_total if days_total else 0.0


def gdrs_plan_sum_for_pairs(
    pairs: pd.DataFrame,
    by_id: dict,
    by_id_name: dict,
    by_norm: dict,
    *,
    as_of_date: Optional[pd.Timestamp] = None,
    term_index: Optional[GdrsTerminationIndex] = None,
) -> int:
    """Сумма плана по уникальным парам проект×подрядчик (без повторного матчинга)."""
    if pairs is None or pairs.empty:
        return 0
    total = 0.0
    seen: set[tuple] = set()
    for _, pr in pairs.iterrows():
        pid = str(pr.get("project_id", "")).strip()
        cid = str(pr.get("contractor_id", "")).strip()
        pn = str(pr.get("project_name", ""))
        cn = str(pr.get("contractor_name", ""))
        key = (pid, cid, normalize_name(pn), normalize_name(cn))
        if key in seen:
            continue
        seen.add(key)
        total += _lookup_plan(
            pid, cid, pn, cn, by_id, by_id_name, by_norm,
            as_of_date=as_of_date, term_index=term_index,
        )
    return int(round(total))


def gdrs_dynamics_build_series(
    fact_df: pd.DataFrame,
    date_from: pd.Timestamp,
    date_to: pd.Timestamp,
    agg_kind: str,
    dogovor_paths: Iterable[Path | str],
    sprav_paths: Iterable[Path | str],
    pairs: pd.DataFrame,
    plan_col: str,
    *,
    plan_aggregate_loader=None,
    month_periods: Optional[Iterable[pd.Period]] = None,
    term_index: Optional[GdrsTerminationIndex] = None,
    plan_agg: str = "month_avg",
    skud_agg: str = "month_avg",
) -> pd.DataFrame:
    """Факт по периодам + план из 1С на конец каждого периода; сетка по всему диапазону фильтра.

    plan_aggregate_loader: optional (snapshot_date) -> plan_df; для кэширования в Streamlit.
    plan_agg / skud_agg — те же ключи, что в фильтрах «План» / «СКУД» (month_avg или week:N).
    """
    _load_plan = plan_aggregate_loader
    if _load_plan is None:
        def _load_plan(snap: pd.Timestamp) -> pd.DataFrame:
            return load_plan_aggregate(dogovor_paths, sprav_paths, snapshot_date=snap)
    dyn_from = pd.Timestamp(date_from).normalize()
    dyn_to = pd.Timestamp(date_to).normalize()
    f2 = gdrs_filter_fact_by_termination(fact_df, term_index)
    f2 = f2.copy()
    f2["date"] = pd.to_datetime(f2["date"])
    f2["bucket"] = gdrs_dynamics_assign_buckets(
        f2["date"], agg_kind, date_from=dyn_from, date_to=dyn_to
    )
    f2["_day"] = f2["date"].dt.normalize()

    plan_wn = gdrs_agg_week_num(plan_agg)
    skud_wn = gdrs_agg_week_num(skud_agg)
    _agg_cf = str(agg_kind or "").strip().casefold()

    daily_totals = (
        f2.groupby(["bucket", "_day"], as_index=False)["fact"]
        .sum()
    )
    if skud_wn is not None:
        if _agg_cf == "неделя":
            daily_totals = daily_totals[
                daily_totals["bucket"].map(
                    lambda b: _gdrs_bucket_calendar_week_num(
                        b, date_from=dyn_from, date_to=dyn_to
                    )
                    == skud_wn
                )
            ]
        else:
            daily_totals = daily_totals[
                daily_totals.apply(
                    lambda r: _gdrs_day_matches_week_filter(
                        r["_day"],
                        r["bucket"],
                        agg_kind,
                        skud_wn,
                        dyn_from,
                        dyn_to,
                    ),
                    axis=1,
                )
            ]
    agg = (
        daily_totals.groupby("bucket", as_index=False)["fact"]
        .mean()
        .rename(columns={"fact": "Факт"})
    )
    agg["Факт"] = pd.to_numeric(agg["Факт"], errors="coerce").fillna(0).round(0).astype(int)

    grid = pd.DataFrame({"bucket": gdrs_dynamics_bucket_starts(dyn_from, dyn_to, agg_kind)})
    if month_periods:
        _mset = set(month_periods)
        grid = grid[grid["bucket"].dt.to_period("M").isin(_mset)].reset_index(drop=True)
    dyn = grid.merge(agg[["bucket", "Факт"]], on="bucket", how="left")
    dyn["Факт"] = dyn["Факт"].fillna(0).astype(int)
    dyn["x_label"] = [
        gdrs_dynamics_bucket_display_label(
            b,
            agg_kind,
            date_from=dyn_from,
            date_to=dyn_to,
            plan_agg=plan_agg,
            skud_agg=skud_agg,
        )
        for b in dyn["bucket"]
    ]
    dyn["Период"] = dyn["x_label"]

    # План и факт — среднее за день внутри периода группировки (день/неделя/месяц).
    plan_cache: dict = {}
    plans: list[int] = []
    for bkt in dyn["bucket"]:
        if plan_wn is not None and _agg_cf == "неделя":
            _bwn = _gdrs_bucket_calendar_week_num(
                bkt, date_from=dyn_from, date_to=dyn_to
            )
            if _bwn != plan_wn:
                plans.append(0)
                continue
        day_plan_vals: list[float] = []
        _plan_days = _gdrs_bucket_calendar_days(bkt, agg_kind, dyn_from, dyn_to)
        if plan_wn is not None and _agg_cf != "неделя":
            _plan_days = [
                d
                for d in _plan_days
                if _gdrs_day_matches_week_filter(
                    d, bkt, agg_kind, plan_wn, dyn_from, dyn_to
                )
            ]
        if plan_wn is not None and _agg_cf == "месяц":
            month_lo = pd.Timestamp(bkt).normalize()
            month_hi = min(
                (month_lo + pd.offsets.MonthEnd(0)).normalize(),
                dyn_to,
            )
            month_lo = max(month_lo, dyn_from)
            snap = gdrs_week_period_end(month_lo, month_hi, plan_wn)
            if snap is None or not pd.notna(snap):
                plans.append(0)
                continue
            sk = pd.Timestamp(snap).normalize()
            if sk not in plan_cache:
                plan_df = _load_plan(sk)
                plan_cache[sk] = _build_plan_lookup(plan_df, plan_col)
            plans.append(int(gdrs_plan_sum_for_pairs(
                pairs, *plan_cache[sk], as_of_date=sk, term_index=term_index,
            )))
            continue
        for day in _plan_days:
            snap = gdrs_dynamics_bucket_snapshot_end(
                day, "День", dyn_to, date_from=dyn_from, date_to=dyn_to
            )
            sk = pd.Timestamp(snap).normalize()
            if sk not in plan_cache:
                plan_df = _load_plan(sk)
                plan_cache[sk] = _build_plan_lookup(plan_df, plan_col)
            day_plan_vals.append(float(gdrs_plan_sum_for_pairs(
                pairs, *plan_cache[sk], as_of_date=sk, term_index=term_index,
            )))
        if day_plan_vals:
            plans.append(int(round(float(np.mean(day_plan_vals)))))
        else:
            snap = gdrs_dynamics_bucket_snapshot_end(
                bkt, agg_kind, dyn_to, date_from=dyn_from, date_to=dyn_to
            )
            sk = pd.Timestamp(snap).normalize()
            if sk not in plan_cache:
                plan_df = _load_plan(sk)
                plan_cache[sk] = _build_plan_lookup(plan_df, plan_col)
            plans.append(int(gdrs_plan_sum_for_pairs(
                pairs, *plan_cache[sk], as_of_date=sk, term_index=term_index,
            )))
    dyn["План"] = plans
    return dyn


def gdrs_dynamics_bucket_snapshot_end(
    bucket_start: pd.Timestamp,
    agg_kind: str,
    period_end: pd.Timestamp,
    *,
    date_from: Optional[pd.Timestamp] = None,
    date_to: Optional[pd.Timestamp] = None,
) -> pd.Timestamp:
    """Конец периода группировки (неделя/месяц/год) для snapshot плана из 1С."""
    b = pd.Timestamp(bucket_start).normalize()
    end = pd.Timestamp(period_end).normalize()
    lo = pd.Timestamp(date_from).normalize() if date_from is not None else None
    hi = pd.Timestamp(date_to).normalize() if date_to is not None else None
    kind = str(agg_kind or "").strip().casefold()
    if kind == "день" and lo is not None and hi is not None and _gdrs_single_calendar_month(lo, hi):
        wn = _gdrs_calendar_week_num(b, lo)
        snap = gdrs_week_period_end(lo, hi, wn)
        if snap is None or not pd.notna(snap):
            snap = b
    elif kind == "день":
        snap = pd.Timestamp(b.to_period("W").end_time).normalize()
    elif kind == "неделя" and lo is not None and hi is not None and _gdrs_single_calendar_month(lo, hi):
        wn = _gdrs_calendar_week_num(b, lo)
        snap = gdrs_week_period_end(lo, hi, wn)
        if snap is None or not pd.notna(snap):
            snap = b + pd.Timedelta(days=6)
    elif kind == "неделя":
        snap = b + pd.Timedelta(days=6)
    elif kind == "месяц":
        snap = (b + pd.offsets.MonthEnd(0)).normalize()
    elif kind == "год":
        snap = (b + pd.offsets.YearEnd(0)).normalize()
    else:
        snap = b
    return min(pd.Timestamp(snap).normalize(), end)


def gdrs_dynamics_plan_total_for_pairs(
    dogovor_paths: Iterable[Path | str],
    sprav_paths: Iterable[Path | str],
    pairs: pd.DataFrame,
    plan_col: str,
    snapshot_date: pd.Timestamp,
) -> int:
    """Сумма плана по выбранным парам проект×подрядчик на дату snapshot из 1С."""
    plan_df = load_plan_aggregate(dogovor_paths, sprav_paths, snapshot_date=snapshot_date)
    by_id, by_id_name, by_norm = _build_plan_lookup(plan_df, plan_col)
    total = 0.0
    if pairs is None or pairs.empty:
        return 0
    for _, pr in pairs.iterrows():
        total += _lookup_plan(
            str(pr.get("project_id", "")),
            str(pr.get("contractor_id", "")),
            str(pr.get("project_name", "")),
            str(pr.get("contractor_name", "")),
            by_id,
            by_id_name,
            by_norm,
        )
    return int(round(total))


def _lookup_plan(
    project_id: str,
    contractor_id: str,
    project_name: str,
    contractor_name: str,
    by_id: dict,
    by_id_name: dict,
    by_norm: dict,
    *,
    fuzzy_threshold: float = 0.86,
    as_of_date: Optional[pd.Timestamp] = None,
    term_index: Optional[GdrsTerminationIndex] = None,
) -> float:
    """Многоуровневый матчинг плана:
    1) точно по (project_id, contractor_id);
    2) точно по (project_id, contractor_name_norm);
    3) точно по (project_name_norm, contractor_name_norm);
    4) фуззи по (project_name_norm, contractor_name_norm) — difflib SequenceMatcher
       (typo: «Констракшн»↔«Контракшн», «Констракшн»↔«Констракшен» и т.п.).
    """
    import difflib as _dl

    if as_of_date is not None and gdrs_contractor_terminated_as_of(
        project_id, contractor_id, project_name, contractor_name, as_of_date, term_index
    ):
        return 0.0

    pid, cid = str(project_id or "").strip(), str(contractor_id or "").strip()
    if pid and cid and (pid, cid) in by_id:
        return float(by_id[(pid, cid)])
    cn = normalize_name(contractor_name)
    if pid and cn and (pid, cn) in by_id_name:
        return float(by_id_name[(pid, cn)])
    pn = normalize_name(project_name)
    if pn and cn and (pn, cn) in by_norm:
        return float(by_norm[(pn, cn)])
    if pn and cn and by_norm:
        candidates = [k_cn for (k_pn, k_cn) in by_norm.keys() if k_pn == pn and k_cn != "__contract_by_norm__"]
        if candidates:
            best = _dl.get_close_matches(cn, candidates, n=1, cutoff=fuzzy_threshold)
            if best:
                return float(by_norm[(pn, best[0])])
    return 0.0


def _lookup_contract_name(
    project_name: str,
    contractor_name: str,
    by_id_name: dict,
) -> str:
    contract_by_norm: dict = by_id_name.get("__contract_by_norm__", {}) or {}
    pn = normalize_name(project_name)
    cn = normalize_name(contractor_name)
    return str(contract_by_norm.get((pn, cn), "") or "")


# ТЗ заказчика 2026-05-08 (скрин ГДРС): расширен список паттернов
# для «Вид работы» — добавлены ЛЭП, АЦБ, ЗОМ и ГРЩ (через «и»),
# Вертикальная планировка, ВК (наружные сети), ИИВ, Газопровод
# (ГСВ/ГСН/ГСЗ), ИНК; добавлен fallback «БЛОК X» (без префикса «СМР»),
# т.к. в реальных contract_name из 1С чаще встречается «АЛЬФА-С БЛОК А»,
# «БЛОК U3U4», а не «СМР Блок A». Без fallback покрытие было ~2%.
_VID_PATTERNS: list[tuple[str, "re.Pattern[str]"]] = [
    ("СМР Блок", re.compile(r"\b(?:смр|cmp)[\s\-_]*блок[\s\-_]*[a-zа-яёA-ZА-ЯЁ0-9]+", re.IGNORECASE)),
    ("АУПТ", re.compile(r"\bаупт\b", re.IGNORECASE)),
    ("АЦБ", re.compile(r"\bацб\b", re.IGNORECASE)),
    ("ВОС", re.compile(r"\bв\.?\s?о\.?\s?с\b", re.IGNORECASE)),
    ("ЛЭП", re.compile(r"\bлэп\b", re.IGNORECASE)),
    ("ЗОМ и ГРЩ", re.compile(r"\bзом[\s\+иand]+грщ\b", re.IGNORECASE)),
    ("Вынос сетей", re.compile(r"вынос\s+сетей", re.IGNORECASE)),
    ("Газоразрядка котельной", re.compile(r"газоразрядк", re.IGNORECASE)),
    ("Газопровод (ГСВ/ГСН)", re.compile(r"газопровод|\bгсв\b|\bгсн\b|\bгсз\b", re.IGNORECASE)),
    ("Вертикальная планировка", re.compile(r"вертикальн\w*\s+планир", re.IGNORECASE)),
    ("ВК (наружные сети)", re.compile(r"\bвк\b[\s\-_]*\(?\s*наруж", re.IGNORECASE)),
    ("ИНК", re.compile(r"\bинк\b", re.IGNORECASE)),
    ("ИИВ", re.compile(r"\bиив\b", re.IGNORECASE)),
    ("Огнезащита", re.compile(r"огнезащит", re.IGNORECASE)),
    ("Благоустройство", re.compile(r"благоустр", re.IGNORECASE)),
    ("Подпорные стены", re.compile(r"подпорн", re.IGNORECASE)),
    ("ЛК ввод/вывод", re.compile(r"ливневая\s+канал", re.IGNORECASE)),
    ("НВК", re.compile(r"\bнвк\b", re.IGNORECASE)),
    ("НПС/ПС/Эксплуатация", re.compile(r"\b(нпс|пс|эксплуатац)\b", re.IGNORECASE)),
    ("Электрооборудование", re.compile(r"электрообор|эл\.\s?обор|электросн", re.IGNORECASE)),
    ("Монтаж резервуара", re.compile(r"монтаж\s+резервуар", re.IGNORECASE)),
    ("Мобилизация", re.compile(r"мобилизац", re.IGNORECASE)),
    # Fallback: «БЛОК X» (X = A/B/C/D/E/F/G/U/U1/U2/U3U4/0/1/2/3/4/5).
    # Должен идти ПОСЛЕДНИМ — иначе перехватит более точные «СМР Блок».
    ("Блок", re.compile(r"\bблок[\s\-_]*[a-zа-яёA-ZА-ЯЁ0-9]+", re.IGNORECASE)),
]


def extract_vid_raboty(contract_name: str) -> str:
    """Из `Наименование_Договора` извлечь «Вид работы» по эвристикам ТЗ заказчика.

    Примеры:
      «Дог. № 28-СА/25 от 22.07.25 (Есипово-5) СМР Блок А, АУПТ» → «СМР Блок А · АУПТ».
      «… Вынос сетей …» → «Вынос сетей».
      «… ШТРАФ» → «—».
    Если ничего не извлечь — возвращает пустую строку (UI отображает «—»).
    """
    if not contract_name:
        return ""
    s = str(contract_name).strip()
    if not s:
        return ""
    matches = []
    for label, pat in _VID_PATTERNS:
        for m in pat.finditer(s):
            txt = m.group(0).strip()
            # Для паттернов, содержащих «блок», возвращаем буквальный
            # текст совпадения (например, «БЛОК A», «Блок U3U4») —
            # чтобы различать разные блоки в рамках одного контрагента.
            # Для остальных — фиксированный label.
            matches.append(txt if "блок" in label.lower() else label)
    if matches:
        seen = []
        for m in matches:
            if m not in seen:
                seen.append(m)
        return " · ".join(seen)
    return ""


def _iso_week_groups(dates: pd.Series) -> tuple[pd.Series, dict[int, int]]:
    """Для серии дат (выборка одного отчётного периода) возвращает:
       (1) Series — порядковый номер ISO-недели в выборке (1..N), 1 = самая ранняя.
       (2) dict   — {номер_недели : число_дней_в_неделе_в_выборке}.
    """
    iso = dates.dt.isocalendar()
    key = iso["year"].astype(int) * 100 + iso["week"].astype(int)
    sorted_keys = sorted(set(key.dropna().tolist()))
    key_to_idx = {k: i + 1 for i, k in enumerate(sorted_keys)}
    week_idx = key.map(key_to_idx).fillna(0).astype(int)
    days_per_week: dict[int, int] = {}
    for k, idx in key_to_idx.items():
        mask = key == k
        days_per_week[idx] = int(dates[mask].dt.normalize().nunique())
    return week_idx, days_per_week


def _gdrs_single_calendar_month(
    date_from: Optional[pd.Timestamp],
    date_to: Optional[pd.Timestamp],
) -> bool:
    """Один календарный месяц в фильтре — недели 1–6 как ISO-недели месяца (resursi 1С)."""
    if date_from is None or date_to is None:
        return False
    lo = pd.Timestamp(date_from).normalize()
    hi = pd.Timestamp(date_to).normalize()
    return lo.to_period("M") == hi.to_period("M")


def _gdrs_week_groups(
    dates: pd.Series,
    *,
    date_from: Optional[pd.Timestamp] = None,
    date_to: Optional[pd.Timestamp] = None,
) -> tuple[pd.Series, dict[int, int]]:
    """Недели 1..6 в таблице ГДРС.

    Для одного календарного месяца — ISO-недели (пн–вс) внутри месяца, как надстрока
    «1 неделя»… в resursi.csv 1С. Иначе — порядковые ISO-недели по факту в выборке.
    """
    dates = pd.to_datetime(dates, errors="coerce")
    if _gdrs_single_calendar_month(date_from, date_to):
        lo = pd.Timestamp(date_from).normalize()
        hi = pd.Timestamp(date_to).normalize()
        week_idx = dates.map(
            lambda x: _gdrs_calendar_week_num(x, lo) if pd.notna(x) else 0
        ).astype(int)
        days_per_week: dict[int, int] = {}
        for wn in gdrs_week_numbers_in_period(lo, hi):
            nd = _gdrs_calendar_days_in_week(lo, hi, wn)
            if nd > 0:
                days_per_week[int(wn)] = nd
        return week_idx, days_per_week
    return _iso_week_groups(dates)


def gdrs_week_period_start(
    date_from: pd.Timestamp,
    date_to: pd.Timestamp,
    week_num: int,
) -> Optional[pd.Timestamp]:
    """Первый день N-й недели периода (ISO-недели месяца или порядковые ISO)."""
    lo = pd.Timestamp(date_from).normalize()
    hi = pd.Timestamp(date_to).normalize()
    wn = int(week_num)
    if wn < 1 or wn > 6:
        return None
    if _gdrs_single_calendar_month(lo, hi):
        start, _ = _gdrs_month_week_bounds(lo.year, lo.month, wn)
        if start is None:
            return None
        return max(start, lo)
    grid = pd.date_range(lo, hi, freq="D")
    if len(grid) == 0:
        return None
    week_idx, _ = _iso_week_groups(pd.Series(grid))
    mask = week_idx == wn
    if not mask.any():
        return None
    return pd.to_datetime(grid[mask.to_numpy()]).min()


def gdrs_week_period_end(
    date_from: pd.Timestamp,
    date_to: pd.Timestamp,
    week_num: int,
) -> Optional[pd.Timestamp]:
    """Последний день N-й недели периода (для среза плана из 1С)."""
    lo = pd.Timestamp(date_from).normalize()
    hi = pd.Timestamp(date_to).normalize()
    wn = int(week_num)
    if wn < 1 or wn > 6:
        return None
    if _gdrs_single_calendar_month(lo, hi):
        _, end = _gdrs_month_week_bounds(lo.year, lo.month, wn)
        if end is None:
            return None
        return min(end, hi)
    # Мульти-месяц: последний день N-й ISO-недели в диапазоне (без привязки к факту).
    grid = pd.date_range(lo, hi, freq="D")
    if len(grid) == 0:
        return None
    week_idx, _ = _iso_week_groups(pd.Series(grid))
    mask = week_idx == wn
    if not mask.any():
        return None
    return pd.to_datetime(grid[mask.to_numpy()]).max()


def gdrs_week_numbers_in_period(
    date_from: Optional[pd.Timestamp],
    date_to: Optional[pd.Timestamp],
) -> list[int]:
    """Номера недель 1..N, которые реально есть в выбранном периоде (N ≤ 6).

    Один календарный месяц — ISO-недели месяца (как надстрока resursi 1С).
    Иначе — порядковые ISO-недели в диапазоне дат.
    """
    if date_from is None or date_to is None:
        return []
    lo = pd.Timestamp(date_from).normalize()
    hi = pd.Timestamp(date_to).normalize()
    if not pd.notna(lo) or not pd.notna(hi) or hi < lo:
        return []
    out: list[int] = []
    for wn in range(1, 7):
        if gdrs_week_period_end(lo, hi, wn) is not None:
            out.append(wn)
    return out


def gdrs_matrix_week_count(
    date_from: Optional[pd.Timestamp],
    date_to: Optional[pd.Timestamp],
) -> int:
    return len(gdrs_week_numbers_in_period(date_from, date_to))


def gdrs_week_numbers_with_fact(
    long_fact: pd.DataFrame,
    *,
    vid: str,
    date_from: Optional[pd.Timestamp],
    date_to: Optional[pd.Timestamp],
    projects: Optional[list[str]] = None,
    contractors: Optional[list[str]] = None,
) -> list[int]:
    """Номера недель 1..N (из периода), в которых реально есть даты факта СКУД.

    Нужно, чтобы фильтр «N неделя» не предлагал недели без факта: напр. неполный
    месяц (факт только до середины последней ISO-недели) — хвост пуст, и выбор
    пустой недели даёт пустые диаграмму/таблицу. Оставляем только недели, где есть
    хотя бы один день факта в выбранном периоде. Нумерация — как в resursi 1С.
    """
    period_weeks = gdrs_week_numbers_in_period(date_from, date_to)
    if not period_weeks:
        return []
    fact = _filter_fact_slice(
        long_fact,
        vid=vid,
        date_from=date_from,
        date_to=date_to,
        projects=projects,
        contractors=contractors,
    )
    if fact is None or fact.empty or "date" not in fact.columns:
        return []
    dates = pd.to_datetime(fact["date"], errors="coerce").dropna()
    if dates.empty:
        return []
    week_idx, _ = _gdrs_week_groups(dates, date_from=date_from, date_to=date_to)
    present = {int(w) for w in week_idx.unique() if int(w) >= 1}
    return [wn for wn in period_weeks if wn in present]


GDRS_AGG_MONTH = "month_avg"
GDRS_AGG_LABELS: dict[str, str] = {
    GDRS_AGG_MONTH: "Среднее за месяц",
    "week:1": "1 неделя",
    "week:2": "2 неделя",
    "week:3": "3 неделя",
    "week:4": "4 неделя",
    "week:5": "5 неделя",
    "week:6": "6 неделя",
}


def gdrs_agg_select_options() -> list[str]:
    return list(GDRS_AGG_LABELS.values())


def gdrs_agg_select_options_for_weeks(weeks: Optional[Iterable[int]]) -> list[str]:
    """Опции агрегации «Среднее за месяц» + только недели из ``weeks``.

    Если ``weeks`` пуст/``None`` — вернуть только «Среднее за месяц» (недель с
    фактом нет, предлагать «N неделя» бессмысленно).
    """
    opts = [GDRS_AGG_LABELS[GDRS_AGG_MONTH]]
    for wn in sorted({int(w) for w in (weeks or []) if 1 <= int(w) <= 6}):
        opts.append(GDRS_AGG_LABELS[f"week:{wn}"])
    return opts


def gdrs_agg_label_to_key(label: str) -> str:
    for key, text in GDRS_AGG_LABELS.items():
        if text == label:
            return key
    return GDRS_AGG_MONTH


def gdrs_agg_week_num(agg_key: str) -> Optional[int]:
    if not str(agg_key).startswith("week:"):
        return None
    try:
        n = int(str(agg_key).split(":", 1)[1])
    except (IndexError, ValueError):
        return None
    return n if 1 <= n <= 6 else None


_GDRS_MONTH_NAMES_RU = (
    "",
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
)


def gdrs_month_periods_from_paths(paths: Iterable[Path | str]) -> set[pd.Period]:
    """Календарные месяцы из дат в именах файлов (Dogovor, resursi)."""
    out: set[pd.Period] = set()
    for raw in paths:
        ts = _source_file_date(Path(raw))
        if ts is not None and pd.notna(ts):
            out.add(ts.to_period("M"))
    return out


def gdrs_month_periods_from_dogovor_records(
    dogovor_records: dict[str, list[dict]] | None,
) -> set[pd.Period]:
    """Месяцы плана из последнего Dogovor: шаги Количество_* и хвост до date_end."""
    if not dogovor_records:
        return set()
    sentinel = pd.Timestamp("0001-01-01")
    latest_src = max(dogovor_records.keys(), key=lambda s: _dogovor_snapshot_sort_key(s))
    records = dogovor_records.get(latest_src) or []
    months: set[pd.Period] = set()
    for r in records:
        if not isinstance(r, dict):
            continue
        hist_dates: list[pd.Timestamp] = []
        for key in ("Количество_Людей", "Количество_Техники"):
            hist = r.get(key)
            if not isinstance(hist, list):
                continue
            for item in hist:
                if not isinstance(item, dict):
                    continue
                d = _fast_parse_date(item.get("Дата") or item.get("дата"))
                if d is not None:
                    hist_dates.append(pd.Timestamp(d).normalize())
        if not hist_dates:
            continue
        for d in hist_dates:
            months.add(d.to_period("M"))
        last_plan = max(hist_dates)
        de = pd.NaT
        for dk in ("Дата_Окончания_Договора", "ДатаОкончания"):
            de = pd.to_datetime(r.get(dk), errors="coerce", utc=True)
            if de is not pd.NaT and pd.notna(de):
                break
        if de is not pd.NaT and pd.notna(de):
            de = pd.Timestamp(de).tz_localize(None).normalize()
            if de > sentinel and de > last_plan:
                for p in pd.period_range(last_plan.to_period("M"), de.to_period("M"), freq="M"):
                    months.add(p)
            elif de <= sentinel:
                # бессрочный: пролонгация плана от last_plan на год вперёд (без date_end)
                end_p = (last_plan + pd.DateOffset(months=12)).to_period("M")
                for p in pd.period_range(last_plan.to_period("M"), end_p, freq="M"):
                    months.add(p)
        else:
            end_p = (last_plan + pd.DateOffset(months=12)).to_period("M")
            for p in pd.period_range(last_plan.to_period("M"), end_p, freq="M"):
                months.add(p)
    return months


def gdrs_month_select_options(
    long_fact: pd.DataFrame,
    *,
    extra_paths: Optional[Iterable[Path | str]] = None,
    dogovor_records: dict[str, list[dict]] | None = None,
) -> list[tuple[str, pd.Period]]:
    """Список (подпись «Апрель 2026», Period[M]) по датам факта СКУД.

    Дополнительно — месяцы из Dogovor/resursi **после** последнего месяца с
    фактом СКУД: план 1С может прийти раньше resursi (напр. июльский Dogovor при
    факте до июня). Диапазон шагов плана и дат окончания договоров — из последнего
    Dogovor в БД (напр. 37-СА/26 до 28.09.2026 → июль–сентябрь).
    """
    period_set: set[pd.Period] = set()
    fact_periods: set[pd.Period] = set()
    if long_fact is not None and not long_fact.empty and "date" in long_fact.columns:
        for p in pd.to_datetime(long_fact["date"], errors="coerce").dt.to_period("M").dropna().unique():
            period_set.add(p)
            fact_periods.add(p)
    ahead: set[pd.Period] = set()
    if extra_paths:
        ahead |= gdrs_month_periods_from_paths(extra_paths)
    if dogovor_records:
        ahead |= gdrs_month_periods_from_dogovor_records(dogovor_records)
    if ahead:
        if not fact_periods:
            period_set |= ahead
        else:
            last_fact = max(fact_periods)
            period_set |= {p for p in ahead if p > last_fact}
    if not period_set:
        return []
    out: list[tuple[str, pd.Period]] = []
    for p in sorted(period_set):
        try:
            m = int(p.month)
            y = int(p.year)
            name = _GDRS_MONTH_NAMES_RU[m] if 1 <= m <= 12 else str(m)
            out.append((f"{name} {y}", p))
        except Exception:
            continue
    return out


def gdrs_default_month_labels(
    month_options: list[tuple[str, pd.Period]],
    long_fact: pd.DataFrame,
) -> list[str]:
    """Последний календарный месяц, в котором есть строки факта СКУД."""
    if not month_options:
        return []
    if long_fact is None or long_fact.empty or "date" not in long_fact.columns:
        return [month_options[-1][0]]
    fact_periods = set(
        pd.to_datetime(long_fact["date"], errors="coerce").dt.to_period("M").dropna().unique()
    )
    for lbl, per in reversed(month_options):
        if per in fact_periods:
            return [lbl]
    return [month_options[-1][0]]


def gdrs_resolve_month_periods(
    month_options: list[tuple[str, pd.Period]],
    selected_labels: Optional[list[str]],
) -> tuple[list[pd.Period], bool]:
    """Периоды для фильтра; при устаревшем выборе — все доступные месяцы."""
    if not month_options:
        return [], False
    label_to_period = {lbl: per for lbl, per in month_options}
    labels = [str(x).strip() for x in (selected_labels or []) if str(x).strip()]
    if not labels:
        return [per for _, per in month_options], False
    periods = [label_to_period[lbl] for lbl in labels if lbl in label_to_period]
    if periods:
        return periods, False
    return [per for _, per in month_options], True


def gdrs_months_date_range(periods: Iterable[pd.Period]) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Календарные границы выбранных месяцев (для плана/подписей)."""
    plist = list(periods)
    if not plist:
        return pd.NaT, pd.NaT
    starts = [pd.Timestamp(p.start_time).normalize() for p in plist]
    ends = [pd.Timestamp(p.end_time).normalize() for p in plist]
    return min(starts), max(ends)


def gdrs_filter_fact_by_months(
    long_fact: pd.DataFrame,
    periods: Iterable[pd.Period],
) -> pd.DataFrame:
    """Оставить строки факта только в выбранных календарных месяцах."""
    if long_fact is None or long_fact.empty:
        return long_fact
    plist = list(periods)
    if not plist:
        return long_fact
    fact = long_fact.copy()
    fact["date"] = pd.to_datetime(fact["date"], errors="coerce")
    pset = set(plist)
    mask = fact["date"].dt.to_period("M").isin(pset)
    return fact[mask].copy()


def gdrs_filter_fact_resursi_source_for_periods(
    long_fact: pd.DataFrame,
    periods: Iterable[pd.Period],
) -> pd.DataFrame:
    """Факт СКУД: для каждого месяца фильтра — resursi с max датой в имени файла за этот месяц."""
    if long_fact is None or long_fact.empty or "__source_file" not in long_fact.columns:
        return long_fact
    plist = list(periods)
    if not plist:
        return long_fact
    allowed: set[str] = set()
    for per in plist:
        candidates: list[tuple[tuple, str]] = []
        for src in long_fact["__source_file"].astype(str).unique():
            fd = _source_file_date(src)
            if fd is not None and pd.notna(fd) and fd.to_period("M") == per:
                candidates.append((_resursi_snapshot_sort_key(src), src))
        if candidates:
            candidates.sort(key=lambda x: (x[0], x[1]))
            allowed.add(candidates[-1][1])
    if not allowed:
        return long_fact
    return long_fact[long_fact["__source_file"].astype(str).isin(allowed)].copy()


def gdrs_contractor_filter_options(
    long_fact: pd.DataFrame,
    dogovor_paths: Iterable[Path | str] = (),
    sprav_paths: Iterable[Path | str] = (),
    *,
    dogovor_records: dict[str, list[dict]] | None = None,
    sprav_records: dict[str, list[dict]] | None = None,
    projects: Optional[list[str]] = None,
    snapshot_date: Optional[pd.Timestamp] = None,
    kontr: Optional[GdrsKontrIndex] = None,
) -> list[str]:
    """Список контрагентов для фильтра: факт (СКУД) + план (1С), т.к. в CSV факта может не быть."""
    names: set[str] = set()
    if long_fact is not None and not long_fact.empty and "contractor_name" in long_fact.columns:
        fact = long_fact
        if projects:
            try:
                from dashboards.project_labels import filter_dataframe_by_project_labels

                fact = filter_dataframe_by_project_labels(fact, list(projects), col="project_name")
            except Exception:
                proj_keys = {p.strip().casefold() for p in projects}
                fact = fact[
                    fact["project_name"].astype(str).str.strip().str.casefold().isin(proj_keys)
                ]
        for raw in fact["contractor_name"].dropna().unique():
            s = str(raw).strip()
            if s:
                _, canon = gdrs_kontr_contractor_display("", s, kontr)
                names.add(canon or s)
    try:
        plan = load_plan_aggregate(
            dogovor_paths,
            sprav_paths,
            dogovor_records=dogovor_records,
            sprav_records=sprav_records,
            snapshot_date=snapshot_date,
        )
        plan = _filter_plan_slice(plan, projects, None)
        if plan is not None and not plan.empty:
            if kontr is not None:
                plan = gdrs_apply_kontr_contractor_names(plan, kontr, dedupe_fact=False)
            for raw in plan["contractor_name"].dropna().unique():
                s = str(raw).strip()
                if s:
                    names.add(s)
    except Exception:
        pass
    return sorted(names, key=lambda x: x.casefold())


def _filter_plan_slice(
    plan: pd.DataFrame,
    projects: Optional[list[str]] = None,
    contractors: Optional[list[str]] = None,
) -> pd.DataFrame:
    if plan is None or plan.empty:
        return pd.DataFrame()
    work = plan.copy()
    if projects:
        try:
            from dashboards.project_labels import filter_dataframe_by_project_labels

            work = filter_dataframe_by_project_labels(work, list(projects), col="project_name")
        except Exception:
            proj_keys = {p.strip().casefold() for p in projects}
            work = work[work["project_name"].astype(str).str.strip().str.casefold().isin(proj_keys)]
    if contractors:
        c_keys = {c.strip().casefold() for c in contractors}
        work = work[work["contractor_name"].astype(str).str.strip().str.casefold().isin(c_keys)]
    return work


def _filter_fact_slice(
    long_fact: pd.DataFrame,
    *,
    vid: str,
    date_from: Optional[pd.Timestamp],
    date_to: Optional[pd.Timestamp],
    projects: Optional[list[str]] = None,
    contractors: Optional[list[str]] = None,
) -> pd.DataFrame:
    if long_fact is None or long_fact.empty:
        return pd.DataFrame()
    fact = long_fact[long_fact["vid_resursa"].astype(str).str.casefold() == vid.casefold()].copy()
    if fact.empty:
        return fact
    if date_from is not None and pd.notna(date_from):
        fact = fact[fact["date"] >= pd.to_datetime(date_from)]
    if date_to is not None and pd.notna(date_to):
        fact = fact[fact["date"] <= pd.to_datetime(date_to)]
    if projects:
        try:
            from dashboards.project_labels import filter_dataframe_by_project_labels

            fact = filter_dataframe_by_project_labels(fact, list(projects), col="project_name")
        except Exception:
            proj_keys = {p.strip().casefold() for p in projects}
            fact = fact[fact["project_name"].astype(str).str.strip().str.casefold().isin(proj_keys)]
    if contractors:
        c_keys = {c.strip().casefold() for c in contractors}
        fact = fact[fact["contractor_name"].astype(str).str.strip().str.casefold().isin(c_keys)]
    return fact


def week_end_in_filtered_fact(
    long_fact: pd.DataFrame,
    *,
    vid: str,
    date_from: pd.Timestamp,
    date_to: pd.Timestamp,
    week_num: int,
    projects: Optional[list[str]] = None,
    contractors: Optional[list[str]] = None,
) -> Optional[pd.Timestamp]:
    """Последний день N-й недели в выборке (нумерация как в таблице w1..w6)."""
    fact = _filter_fact_slice(
        long_fact,
        vid=vid,
        date_from=date_from,
        date_to=date_to,
        projects=projects,
        contractors=contractors,
    )
    if fact.empty:
        return gdrs_week_period_end(date_from, date_to, week_num)
    dates = pd.to_datetime(fact["date"])
    week_idx, _ = _gdrs_week_groups(dates, date_from=date_from, date_to=date_to)
    mask = week_idx == int(week_num)
    if not mask.any():
        return gdrs_week_period_end(date_from, date_to, week_num)
    return pd.to_datetime(dates[mask]).max()


def gdrs_plan_snapshot_date(
    long_fact: pd.DataFrame,
    *,
    vid: str,
    date_from: pd.Timestamp,
    date_to: pd.Timestamp,
    plan_agg: str,
    projects: Optional[list[str]] = None,
    contractors: Optional[list[str]] = None,
) -> pd.Timestamp:
    """Дата среза плана из 1С: конец выбранной недели или конец периода (среднее за месяц)."""
    wn = gdrs_agg_week_num(plan_agg)
    if wn is not None:
        end = week_end_in_filtered_fact(
            long_fact,
            vid=vid,
            date_from=date_from,
            date_to=date_to,
            week_num=wn,
            projects=projects,
            contractors=contractors,
        )
        if end is not None and pd.notna(end):
            return pd.to_datetime(end)
    return pd.to_datetime(date_to)


def _skud_agg_per_pair(
    fact: pd.DataFrame,
    skud_agg: str,
    *,
    date_from: Optional[pd.Timestamp] = None,
    date_to: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    """СКУД (среднее за день) по паре проект×контрагент для режима month_avg или week:N."""
    total_days = int(fact["date"].dt.normalize().nunique())
    pair_cols = _gdrs_pair_group_cols(fact)
    skud_sum = (
        fact.groupby(pair_cols, dropna=False)["fact"]
        .sum()
        .reset_index(name="skud_sum")
    )
    wn = gdrs_agg_week_num(skud_agg)
    if wn is None:
        skud_sum["skud_val"] = skud_sum["skud_sum"] / max(1, total_days)
        return skud_sum[pair_cols + ["skud_val"]]

    week_idx, days_per_week = _gdrs_week_groups(
        fact["date"], date_from=date_from, date_to=date_to
    )
    fact = fact.assign(week=week_idx)
    week_sum = (
        fact.groupby(pair_cols + ["week"], dropna=False)["fact"]
        .sum()
        .reset_index(name="daily_sum")
    )
    week_sum["skud_val"] = week_sum.apply(
        lambda r: r["daily_sum"] / max(1, days_per_week.get(int(r["week"]), 1)), axis=1
    )
    week_only = week_sum[week_sum["week"] == wn][pair_cols + ["skud_val"]]
    return skud_sum[pair_cols].merge(
        week_only, on=pair_cols, how="left"
    ).assign(skud_val=lambda d: d["skud_val"].fillna(0.0))


def gdrs_matrix_show_week_columns(
    plan_agg: str,
    skud_agg: str,
    *,
    date_from: Optional[pd.Timestamp] = None,
    date_to: Optional[pd.Timestamp] = None,
) -> bool:
    """Колонки «1–6 неделя» — только «Среднее за месяц» и один календарный месяц в фильтре."""
    if gdrs_agg_week_num(plan_agg) is not None or gdrs_agg_week_num(skud_agg) is not None:
        return False
    if date_from is not None and date_to is not None and pd.notna(date_from) and pd.notna(date_to):
        if not _gdrs_single_calendar_month(date_from, date_to):
            return False
    return True


def gdrs_matrix_week_labels(
    date_from: pd.Timestamp,
    date_to: pd.Timestamp,
    dates: pd.Series,
) -> list[str]:
    """Подписи недель 1–N (N ≤ 6) с диапазоном дат (для шапки таблицы)."""
    lo = pd.Timestamp(date_from).normalize()
    hi = pd.Timestamp(date_to).normalize()
    week_nums = gdrs_week_numbers_in_period(lo, hi)
    if not week_nums:
        return [f"{i} нед" for i in range(1, 7)]
    dts = pd.to_datetime(dates, errors="coerce").dropna()
    if not dts.empty:
        dts = dts[(dts >= lo) & (dts <= hi)]
    week_idx, _ = (
        _gdrs_week_groups(dts, date_from=lo, date_to=hi) if not dts.empty else (None, {})
    )
    # Если есть факт — оставляем только недели с фактом (пустые календарные
    # недели неполного месяца не показываем, чтобы шапка совпадала с колонками
    # таблицы). Без факта — прежнее поведение (все недели периода).
    if week_idx is not None and not dts.empty:
        weeks_with_fact = {int(w) for w in week_idx.unique() if int(w) >= 1}
        _wn = [wi for wi in week_nums if wi in weeks_with_fact]
        if _wn:
            week_nums = _wn
    labels: list[str] = []
    for wi in week_nums:
        if week_idx is not None and not dts.empty:
            mask = week_idx == wi
            if mask.any():
                sub = dts[mask]
                labels.append(f"{wi} нед ({sub.min().strftime('%d.%m')}-{sub.max().strftime('%d.%m')})")
                continue
        end = gdrs_week_period_end(lo, hi, wi)
        if end is not None and pd.notna(end):
            labels.append(f"{wi} нед ({end.strftime('%d.%m')})")
        else:
            labels.append(f"{wi} нед")
    return labels


def build_gdrs_audit_export_frames(
    long_fact: pd.DataFrame,
    plan: pd.DataFrame,
    dogovor_paths: Iterable[Path | str],
    *,
    vid: str,
    date_from: pd.Timestamp,
    date_to: pd.Timestamp,
    plan_snapshot: pd.Timestamp,
    projects: Optional[list[str]] = None,
    contractors: Optional[list[str]] = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """CSV для проверки: факт СКУД, агрегированный план, план по каждому договору на дату среза."""
    plan_col = "plan_workers" if str(vid).casefold() == "рабочие" else "plan_equipment"
    fact_slice = _filter_fact_slice(
        long_fact,
        vid=vid,
        date_from=date_from,
        date_to=date_to,
        projects=projects,
        contractors=contractors,
    )
    fact_export = fact_slice.copy()
    if not fact_export.empty:
        fact_export = fact_export.sort_values(["project_name", "contractor_name", "date"])

    plan_slice = _filter_plan_slice(plan, projects, contractors)
    if plan_slice is not None and not plan_slice.empty:
        plan_export = plan_slice[
            [
                c
                for c in (
                    "project_id",
                    "project_name",
                    "contractor_id",
                    "contractor_name",
                    "contract_name",
                    plan_col,
                )
                if c in plan_slice.columns
            ]
        ].copy()
        plan_export = plan_export.rename(columns={plan_col: "План_1С"})
    else:
        plan_export = pd.DataFrame()

    snap = pd.Timestamp(plan_snapshot).normalize()
    latest_path = _pick_dogovor_path_for_snapshot(dogovor_paths, snap)
    if latest_path is None:
        contract_export = pd.DataFrame()
    else:
        raw = load_plan_from_dogovor(latest_path, snapshot_date=snap)
        _fsk = _dogovor_snapshot_sort_key(latest_path)
        _file_snap = None if _fsk[0] is pd.Timestamp.min else pd.Timestamp(_fsk[0]).normalize()
        raw = _apply_gdrs_dogovor_plan_exclusions(
            raw, snapshot_date=snap, file_snapshot_date=_file_snap
        )
        if projects:
            try:
                from dashboards.project_labels import filter_dataframe_by_project_labels

                raw = filter_dataframe_by_project_labels(raw, list(projects), col="project_name")
            except Exception:
                pass
        if contractors:
            c_keys = {c.strip().casefold() for c in contractors}
            raw = raw[raw["contractor_name"].astype(str).str.strip().str.casefold().isin(c_keys)]
        keep = [
            c
            for c in (
                "project_id",
                "project_name",
                "contractor_id",
                "contractor_name",
                "contract_name",
                "plan_workers",
                "plan_equipment",
                "date_start",
                "date_end",
                "date_termination",
            )
            if c in raw.columns
        ]
        contract_export = raw[keep].copy() if not raw.empty else pd.DataFrame()
        if not contract_export.empty:
            contract_export.insert(0, "Срез_плана", snap.strftime("%Y-%m-%d"))
            contract_export.insert(1, "Файл_Dogovor", latest_path.name)

    return fact_export, plan_export, contract_export


def _gdrs_collapse_rows_by_contractor_key(
    rows: pd.DataFrame,
    kontr: Optional[GdrsKontrIndex] = None,
) -> pd.DataFrame:
    """Схлопывает строки с одним контрагентом (Kontr ID / pair key) внутри проекта."""
    if rows is None or rows.empty:
        return rows
    work = rows.copy()
    if "_gk_proj" not in work.columns or "_gk_ctr" not in work.columns:
        work = _gdrs_add_pair_keys(work, kontr, dedupe_fact=False)
    pair_cols = ["_gk_proj", "_gk_ctr"]
    sum_cols = [
        c
        for c in (
            "skud",
            "skud_avg",
            "deviation",
            "w1",
            "w2",
            "w3",
            "w4",
            "w5",
            "w6",
        )
        if c in work.columns
    ]
    max_cols = [c for c in ("plan", "p1", "p2", "p3", "p4", "p5", "p6") if c in work.columns]

    parts: list[pd.DataFrame] = []
    for proj, chunk in work.groupby("project_name", sort=False):
        chunk = chunk.copy()
        _sort_by = [c for c in pair_cols + ["contractor_name", "contractor_id"] if c in chunk.columns]
        if _sort_by:
            chunk = chunk.sort_values(_sort_by, kind="mergesort")
        if chunk.groupby(pair_cols).ngroups == len(chunk):
            parts.append(chunk)
            continue
        agg_dict: dict[str, tuple] = {c: (c, "sum") for c in sum_cols}
        agg_dict.update({c: (c, "max") for c in max_cols})
        if "contractor_name" in chunk.columns:
            agg_dict["contractor_name"] = ("contractor_name", _first_nonempty)
        if "contractor_id" in chunk.columns:
            agg_dict["contractor_id"] = ("contractor_id", _first_nonempty)
        if "project_id" in chunk.columns:
            agg_dict["project_id"] = ("project_id", _first_nonempty)
        if "contract_name" in chunk.columns:
            agg_dict["contract_name"] = ("contract_name", _first_nonempty)
        if "vid_raboty" in chunk.columns:
            agg_dict["vid_raboty"] = ("vid_raboty", _first_nonempty)
        if "row_kind" in chunk.columns:
            agg_dict["row_kind"] = ("row_kind", "first")
        collapsed = chunk.groupby(pair_cols, as_index=False).agg(**agg_dict)
        collapsed["project_name"] = proj
        if "deviation" in collapsed.columns and "plan" in collapsed.columns and "skud" in collapsed.columns:
            collapsed["deviation"] = (collapsed["skud"] - collapsed["plan"]).round(0)
        if "delta_pct" in work.columns:
            collapsed["delta_pct"] = collapsed.apply(
                lambda r: ((r["skud"] - r["plan"]) / r["plan"] * 100.0)
                if r["plan"] not in (0.0, None) and float(r["plan"]) != 0.0
                else np.nan,
                axis=1,
            )
        parts.append(collapsed)
    return pd.concat(parts, ignore_index=True) if parts else work


def build_main_table(
    long_fact: pd.DataFrame,
    plan: pd.DataFrame,
    *,
    vid: str,
    date_from: Optional[pd.Timestamp] = None,
    date_to: Optional[pd.Timestamp] = None,
    projects: Optional[list[str]] = None,
    contractors: Optional[list[str]] = None,
    only_with_plan: bool = False,
    article_by_contract_norm: Optional[dict[str, str]] = None,
    article_sig_pc_sets: Optional[dict[tuple[str, str, str], set[str]]] = None,
    article_sig_sets: Optional[dict[str, set[str]]] = None,
    article_by_project_contractor: Optional[dict[tuple[str, str], str]] = None,
    article_pc_sets: Optional[dict[tuple[str, str], set[str]]] = None,
    plan_agg: str = GDRS_AGG_MONTH,
    skud_agg: str = GDRS_AGG_MONTH,
    weekly_plan_by_week: Optional[dict[int, pd.DataFrame]] = None,
    weekly_plan_as_of: Optional[dict[int, pd.Timestamp]] = None,
    kontr_index: Optional[GdrsKontrIndex] = None,
    term_index: Optional[GdrsTerminationIndex] = None,
    plan_as_of: Optional[pd.Timestamp] = None,
    plan_aggregate_loader: Optional[Callable[[pd.Timestamp], pd.DataFrame]] = None,
    resursi_all_fact: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Сборка главной таблицы (Скрин 11): Контрагент × недели × отклонение × дельта.

    Возвращает DataFrame с колонками:
        project_name, contractor_name, contract_name,
        plan, skud, deviation, w1..w6, delta_pct, row_kind ∈ {"row","subtotal","grand_total"}.

    Логика расчёта:
    - Неделя = ISO-неделя; нумерация в порядке возрастания внутри выборки (1..6 для месяца).
    - weekly_avg(подрядчик, неделя) = ∑ daily / N_дней_в_неделе_в_выборке.
    - skud: по `skud_agg` — среднее за день за период (month_avg) или weekly_avg выбранной недели (week:N).
    - plan: из plan-таблицы 1С на срез `plan_agg` (конец недели или конец периода).
    - deviation = skud − План (факт − план); delta_pct = (deviation / План) × 100 (при План≠0).
  """
    if long_fact is None:
        long_fact = pd.DataFrame()
    fact = _filter_fact_slice(
        long_fact,
        vid=vid,
        date_from=date_from,
        date_to=date_to,
        projects=projects,
        contractors=contractors,
    )
    fact = gdrs_filter_fact_by_termination(fact, term_index)
    fact = _gdrs_add_pair_keys(fact, kontr_index, dedupe_fact=True)
    # После Kontr: каноническое имя может появиться только здесь — стоп-лист по contractor_name.
    fact = gdrs_drop_excluded_contractors(fact)

    plan_work = plan.copy() if plan is not None and not plan.empty else pd.DataFrame()
    if not plan_work.empty:
        plan_work = _gdrs_add_pair_keys(plan_work, kontr_index, dedupe_fact=False)
        plan_work = gdrs_drop_excluded_contractors(plan_work)

    plan_col = "plan_workers" if vid.casefold() == "рабочие" else "plan_equipment"
    by_id, by_id_name, by_norm = _build_plan_lookup(plan_work, plan_col)

    # Эталон (AI_DATA_RULES §70): состав строк отчёта = пересечение other_*_resursi ∩ 1C_Kontr.
    # План берётся из Dogovor, но контрагент попадает в отчёт только если он присутствует
    # в resursi. Иначе plan-only контрагенты из Dogovor (например, есть в Kontr, но нет в
    # resursi) протекают в отчёт. Набор допустимых контрагентов — по ключу `_gk_ctr`
    # (id/имя из Kontr) из ПОЛНОГО resursi (все месяцы), а не только выбранного периода.
    _resursi_ctr_keys: Optional[set] = None
    _membership_src = resursi_all_fact if resursi_all_fact is not None else long_fact
    if _membership_src is not None and not _membership_src.empty:
        _mem = _membership_src
        if "vid_resursa" in _mem.columns:
            _mem = _mem[_mem["vid_resursa"].astype(str).str.casefold() == vid.casefold()]
        _mem_cols = [c for c in ("contractor_id", "contractor_name") if c in _mem.columns]
        if _mem is not None and not _mem.empty and _mem_cols:
            _mem = _mem[_mem_cols].drop_duplicates()
            _mem = _gdrs_add_pair_keys(_mem, kontr_index, dedupe_fact=False)
            _mem = gdrs_drop_excluded_contractors(_mem)
            if _mem is not None and not _mem.empty and "_gk_ctr" in _mem.columns:
                _resursi_ctr_keys = set(_mem["_gk_ctr"].astype(str))

    _plan_snap = pd.Timestamp(plan_as_of).normalize() if plan_as_of is not None and pd.notna(plan_as_of) else (
        pd.Timestamp(date_to).normalize() if date_to is not None and pd.notna(date_to) else None
    )

    pair_cols = ["_gk_proj", "_gk_ctr"]
    id_pick = pd.DataFrame(
        columns=["_gk_proj", "_gk_ctr", "project_name", "contractor_name", "project_id", "contractor_id"]
    )
    if fact is not None and not fact.empty:
        fact = fact.copy()
        fact["date"] = pd.to_datetime(fact["date"])
        week_idx, days_per_week = _gdrs_week_groups(
            fact["date"], date_from=date_from, date_to=date_to
        )
        fact["week"] = week_idx

        id_pick = (
            fact.groupby(pair_cols, dropna=False)
            .agg(
                project_name=("project_name", _first_nonempty),
                contractor_name=("contractor_name", _first_nonempty),
                project_id=("project_id", _first_nonempty),
                contractor_id=("contractor_id", _first_nonempty),
            )
            .reset_index()
        )

        week_sum = (
            fact.groupby(pair_cols + ["week"], dropna=False)["fact"]
            .sum()
            .reset_index(name="daily_sum")
        )
        week_sum["weekly_avg"] = week_sum.apply(
            lambda r: r["daily_sum"] / max(1, days_per_week.get(int(r["week"]), 1)), axis=1
        )

        pivot = week_sum.pivot_table(
            index=pair_cols,
            columns="week",
            values="weekly_avg",
            aggfunc="sum",
            fill_value=0.0,
        ).reset_index()
    else:
        pivot = pd.DataFrame(columns=pair_cols)

    for w in (1, 2, 3, 4, 5, 6):
        if w not in pivot.columns:
            pivot[w] = 0.0
    for col in pair_cols:
        if col not in pivot.columns:
            pivot[col] = []
    pivot.rename(columns={1: "w1", 2: "w2", 3: "w3", 4: "w4", 5: "w5", 6: "w6"}, inplace=True)

    # Обнаружение пар «проект×подрядчик» из плана. На мультимесячном периоде со
    # «Среднее за месяц» план подрядчика может быть >0 в одном из месяцев и 0 на срез
    # date_to. Если искать plan-only пары только по срезу date_to (plan_work), такой
    # подрядчик (план есть, факта нет) теряется целиком: main_t пустеет → «Нет данных
    # для выбранных фильтров», хотя в отдельном месяце он виден. Поэтому для мультимесяца
    # пары ищем по ОБЪЕДИНЕНИЮ снапшотов всех месяцев периода (значение плана всё равно
    # усредняется помесячно ниже через gdrs_plan_period_month_weighted_average).
    _plan_pairs_source = plan_work
    _pairs_multi_month = (
        gdrs_agg_week_num(plan_agg) is None
        and date_from is not None
        and date_to is not None
        and pd.notna(date_from)
        and pd.notna(date_to)
        and not _gdrs_single_calendar_month(date_from, date_to)
        and plan_aggregate_loader is not None
    )
    if _pairs_multi_month:
        _pp_lo = pd.Timestamp(date_from).normalize()
        _pp_hi = pd.Timestamp(date_to).normalize()
        _pp_frames: list[pd.DataFrame] = []
        for _pp_per in pd.period_range(_pp_lo.to_period("M"), _pp_hi.to_period("M"), freq="M"):
            _pp_snap = pd.Timestamp(min(_pp_hi, _pp_per.end_time.normalize())).normalize()
            _pp_df = plan_aggregate_loader(_pp_snap)
            if _pp_df is not None and not _pp_df.empty:
                _pp_frames.append(_pp_df)
        if _pp_frames:
            _plan_union = pd.concat(_pp_frames, ignore_index=True)
            _plan_union = _gdrs_add_pair_keys(_plan_union, kontr_index, dedupe_fact=False)
            _plan_union = gdrs_drop_excluded_contractors(_plan_union)
            _plan_pairs_source = _plan_union

    plan_pairs_df = _filter_plan_slice(_plan_pairs_source, projects, contractors)
    if plan_pairs_df is not None and not plan_pairs_df.empty:
        plan_pairs_df = plan_pairs_df.copy()
        if "_gk_proj" not in plan_pairs_df.columns:
            plan_pairs_df = _gdrs_add_pair_keys(plan_pairs_df, kontr_index, dedupe_fact=False)
        try:
            from dashboards.project_labels import apply_unified_project_column

            plan_pairs_df = apply_unified_project_column(plan_pairs_df, "project_name")
        except Exception:
            pass
        plan_pairs_df["_plan_val"] = pd.to_numeric(plan_pairs_df[plan_col], errors="coerce").fillna(0.0)
        plan_pairs_df = plan_pairs_df[plan_pairs_df["_plan_val"] > 0]
        # Эталон resursi ∩ Kontr: plan-only контрагента добавляем, только если он есть в resursi.
        if _resursi_ctr_keys is not None and not plan_pairs_df.empty and "_gk_ctr" in plan_pairs_df.columns:
            plan_pairs_df = plan_pairs_df[
                plan_pairs_df["_gk_ctr"].astype(str).isin(_resursi_ctr_keys)
            ]
        if not plan_pairs_df.empty:
            plan_ids = (
                plan_pairs_df.groupby(pair_cols, dropna=False)
                .agg(
                    project_name=("project_name", _first_nonempty),
                    contractor_name=("contractor_name", _first_nonempty),
                    project_id=("project_id", _first_nonempty),
                    contractor_id=("contractor_id", _first_nonempty),
                )
                .reset_index()
            )
            id_pick = pd.concat([id_pick, plan_ids], ignore_index=True)
            id_pick = id_pick.sort_values(pair_cols, kind="mergesort").drop_duplicates(
                subset=pair_cols, keep="first"
            )
            plan_only = plan_ids[pair_cols].copy()
            for w in (1, 2, 3, 4, 5, 6):
                plan_only[f"w{w}"] = 0.0
            if pivot.empty:
                pivot = plan_only
            else:
                have = set(
                    zip(
                        pivot["_gk_proj"].astype(str).str.strip(),
                        pivot["_gk_ctr"].astype(str).str.strip(),
                    )
                )
                add = plan_only[
                    ~plan_only.apply(
                        lambda r, _h=have: (
                            str(r["_gk_proj"]).strip(),
                            str(r["_gk_ctr"]).strip(),
                        )
                        in _h,
                        axis=1,
                    )
                ]
                if not add.empty:
                    pivot = pd.concat([pivot, add], ignore_index=True)

    if fact is not None and not fact.empty:
        skud_per = _skud_agg_per_pair(
            fact, skud_agg, date_from=date_from, date_to=date_to
        ).rename(columns={"skud_val": "skud_avg"})
    else:
        skud_per = pivot[pair_cols].copy()
        skud_per["skud_val"] = 0.0

    rows = pivot.merge(skud_per, on=pair_cols, how="left")
    if "skud_avg" not in rows.columns:
        if "skud_val" in rows.columns:
            rows["skud_avg"] = rows["skud_val"]
        else:
            rows["skud_avg"] = 0.0
    if id_pick is not None and not id_pick.empty:
        rows = rows.merge(id_pick, on=pair_cols, how="left")
    else:
        rows["project_name"] = ""
        rows["contractor_name"] = ""
        rows["project_id"] = ""
        rows["contractor_id"] = ""

    if rows.empty:
        return pd.DataFrame()

    _use_period_plan_avg = (
        gdrs_agg_week_num(plan_agg) is None
        and date_from is not None
        and date_to is not None
        and pd.notna(date_from)
        and pd.notna(date_to)
        and not _gdrs_single_calendar_month(date_from, date_to)
        and plan_aggregate_loader is not None
    )
    _month_plan_lu_cache: dict[pd.Timestamp, tuple] = {}
    if _use_period_plan_avg:
        _plo = pd.Timestamp(date_from).normalize()
        _phi = pd.Timestamp(date_to).normalize()
        for _per in pd.period_range(_plo.to_period("M"), _phi.to_period("M"), freq="M"):
            _snap = pd.Timestamp(min(_phi, _per.end_time.normalize())).normalize()
            if _snap not in _month_plan_lu_cache:
                _pdf = gdrs_drop_excluded_contractors(plan_aggregate_loader(_snap))
                _month_plan_lu_cache[_snap] = _build_plan_lookup(_pdf, plan_col)

    if _use_period_plan_avg:
        rows["plan"] = rows.apply(
            lambda r: gdrs_plan_period_month_weighted_average(
                date_from=pd.Timestamp(date_from),
                date_to=pd.Timestamp(date_to),
                project_id=str(r.get("project_id", "")),
                contractor_id=str(r.get("contractor_id", "")),
                project_name=str(r.get("project_name", "")),
                contractor_name=str(r.get("contractor_name", "")),
                plan_col=plan_col,
                plan_aggregate_loader=plan_aggregate_loader,
                term_index=term_index,
                month_lookup_cache=_month_plan_lu_cache,
            ),
            axis=1,
        ).astype(float)
    else:
        rows["plan"] = rows.apply(
            lambda r: _lookup_plan(
                str(r.get("project_id", "")), str(r.get("contractor_id", "")),
                str(r.get("project_name", "")), str(r.get("contractor_name", "")),
                by_id, by_id_name, by_norm,
                as_of_date=_plan_snap, term_index=term_index,
            ),
            axis=1,
        ).astype(float)
    rows["contract_name"] = rows.apply(
        lambda r: _lookup_contract_name(str(r.get("project_name", "")), str(r.get("contractor_name", "")), by_id_name),
        axis=1,
    )
    rows["vid_raboty"] = rows.apply(
        lambda r: _vid_raboty_display(
            str(r.get("contract_name", "")),
            article_by_contract_norm,
            article_sig_pc_sets,
            article_sig_sets,
            article_by_project_contractor,
            article_pc_sets,
            str(r.get("project_name", "")),
            str(r.get("contractor_name", "")),
        ),
        axis=1,
    )
    rows["skud"] = rows["skud_avg"].fillna(0.0).round(0)
    rows = rows.drop(columns=["skud_val"], errors="ignore")
    # Отклонение = Факт (СКУД) − План: «+» если факт > плана, «−» если наоборот.
    # Отклонение % = (Отклонение / План) × 100.
    rows["deviation"] = (rows["skud"] - rows["plan"]).round(0)
    rows["delta_pct"] = rows.apply(
        lambda r: ((r["skud"] - r["plan"]) / r["plan"] * 100.0)
        if r["plan"] not in (0.0, None) and float(r["plan"]) != 0.0
        else np.nan,
        axis=1,
    )
    _show_week_cols = gdrs_matrix_show_week_columns(
        plan_agg, skud_agg, date_from=date_from, date_to=date_to
    )
    _week_nums = (
        gdrs_week_numbers_in_period(date_from, date_to) if _show_week_cols else []
    )
    # Только недели, где реально есть факт СКУД. Неполный месяц: хвост ISO-недель
    # без дней факта не включаем — иначе «Среднее за месяц» делится на лишние
    # пустые недели (занижение факта). Пустые недели не показываем и в среднее не берём.
    if _week_nums and fact is not None and not fact.empty and "week" in fact.columns:
        _weeks_with_fact = {int(w) for w in fact["week"].dropna().unique() if int(w) >= 1}
        _restricted = [wn for wn in _week_nums if wn in _weeks_with_fact]
        if _restricted:
            _week_nums = _restricted
    _weekly_plan_lu: dict[int, tuple] = {}
    if _show_week_cols and weekly_plan_by_week:
        for _wn, _wp_df in weekly_plan_by_week.items():
            if _wp_df is not None and not _wp_df.empty:
                _weekly_plan_lu[int(_wn)] = _build_plan_lookup(_wp_df, plan_col)
    for w in ("w1", "w2", "w3", "w4", "w5", "w6"):
        wi = int(w[1:])
        if _show_week_cols and wi not in _week_nums:
            rows[w] = 0.0
        else:
            rows[w] = rows[w].fillna(0.0).round(0)
    for wi, pk in enumerate(("p1", "p2", "p3", "p4", "p5", "p6"), start=1):
        if _show_week_cols and wi not in _week_nums:
            rows[pk] = 0.0
        elif _show_week_cols and wi in _weekly_plan_lu:
            _lu = _weekly_plan_lu[wi]
            _wasof = None
            if weekly_plan_as_of and wi in weekly_plan_as_of:
                _wasof = pd.Timestamp(weekly_plan_as_of[wi]).normalize()
            rows[pk] = rows.apply(
                lambda r, _lookup=_lu, _snap=_wasof: _lookup_plan(
                    str(r.get("project_id", "")),
                    str(r.get("contractor_id", "")),
                    str(r.get("project_name", "")),
                    str(r.get("contractor_name", "")),
                    _lookup[0],
                    _lookup[1],
                    _lookup[2],
                    as_of_date=_snap,
                    term_index=term_index,
                ),
                axis=1,
            ).astype(float).round(0)
        elif _show_week_cols:
            rows[pk] = rows["plan"].fillna(0.0).round(0)
        else:
            rows[pk] = rows["plan"].fillna(0.0).round(0)
    if (
        _show_week_cols
        and _week_nums
        and gdrs_agg_week_num(plan_agg) is None
        and gdrs_agg_week_num(skud_agg) is None
    ):
        _p_cols = [f"p{wn}" for wn in _week_nums]
        _w_cols = [f"w{wn}" for wn in _week_nums]
        rows["plan"] = rows[_p_cols].mean(axis=1).round(0)
        rows["skud"] = rows[_w_cols].mean(axis=1).round(0)
        rows["deviation"] = (rows["skud"] - rows["plan"]).round(0)
        rows["delta_pct"] = rows.apply(
            lambda r: ((r["skud"] - r["plan"]) / r["plan"] * 100.0)
            if r["plan"] not in (0.0, None) and float(r["plan"]) != 0.0
            else np.nan,
            axis=1,
        )
    rows["row_kind"] = "row"

    rows = _gdrs_collapse_rows_by_contractor_key(rows, kontr_index)
    rows = _gdrs_resolve_contractor_display(rows, kontr_index)
    rows = rows.drop(columns=["_gk_proj", "_gk_ctr"], errors="ignore")
    rows = gdrs_apply_kontr_plan_gate(
        rows,
        kontr_index,
        term_index=term_index,
        plan_as_of=_plan_snap,
    )
    rows = gdrs_drop_excluded_contractors(rows)

    if only_with_plan:
        rows = rows[rows["plan"] > 0].copy()
        if rows.empty:
            return pd.DataFrame()

    _compact = not gdrs_matrix_show_week_columns(
        plan_agg, skud_agg, date_from=date_from, date_to=date_to
    )
    if _compact:
        rows = rows[(rows["plan"] > 0) | (rows["skud"] > 0)].copy()
        if rows.empty:
            return pd.DataFrame()

    rows = _gdrs_ensure_project_names(rows)
    if rows.empty:
        return pd.DataFrame()

    out_blocks: list[pd.DataFrame] = []
    for proj, chunk in rows.groupby("project_name", sort=True):
        block = chunk.sort_values("contractor_name").copy()
        plan_sum = float(block["plan"].sum())
        skud_sum = float(block["skud"].sum())
        dev_sum = skud_sum - plan_sum
        sub = pd.DataFrame(
            [{
                "project_name": proj,
                "contractor_name": "",
                "contractor_id": "",
                "project_id": "",
                "contract_name": "",
                "plan": plan_sum,
                "skud": skud_sum,
                "deviation": dev_sum,
                "delta_pct": ((skud_sum - plan_sum) / plan_sum * 100.0) if plan_sum > 0 else np.nan,
                "w1": float(block["w1"].sum()),
                "w2": float(block["w2"].sum()),
                "w3": float(block["w3"].sum()),
                "w4": float(block["w4"].sum()),
                "w5": float(block["w5"].sum()),
                "w6": float(block["w6"].sum()),
                "p1": float(block["p1"].sum()),
                "p2": float(block["p2"].sum()),
                "p3": float(block["p3"].sum()),
                "p4": float(block["p4"].sum()),
                "p5": float(block["p5"].sum()),
                "p6": float(block["p6"].sum()),
                "row_kind": "subtotal",
            }]
        )
        out_blocks.append(sub)
        out_blocks.append(block)

    if not out_blocks:
        return pd.DataFrame()

    body = pd.concat(out_blocks, ignore_index=True)
    sub_only = body[body["row_kind"] == "subtotal"]
    plan_total = float(sub_only["plan"].sum())
    skud_total_v = float(sub_only["skud"].sum())
    dev_total = skud_total_v - plan_total
    grand = pd.DataFrame(
        [{
            "project_name": "Итого",
            "contractor_name": "",
            "contractor_id": "",
            "project_id": "",
            "contract_name": "",
            "plan": plan_total,
            "skud": skud_total_v,
            "deviation": dev_total,
            "delta_pct": ((skud_total_v - plan_total) / plan_total * 100.0)
            if plan_total > 0
            else np.nan,
            "w1": float(sub_only["w1"].sum()),
            "w2": float(sub_only["w2"].sum()),
            "w3": float(sub_only["w3"].sum()),
            "w4": float(sub_only["w4"].sum()),
            "w5": float(sub_only["w5"].sum()),
            "w6": float(sub_only["w6"].sum()),
            "p1": float(sub_only["p1"].sum()),
            "p2": float(sub_only["p2"].sum()),
            "p3": float(sub_only["p3"].sum()),
            "p4": float(sub_only["p4"].sum()),
            "p5": float(sub_only["p5"].sum()),
            "p6": float(sub_only["p6"].sum()),
            "row_kind": "grand_total",
        }]
    )
    final = pd.concat([body, grand], ignore_index=True)
    return final


def build_summary_table(
    long_fact: pd.DataFrame,
    plan: pd.DataFrame,
    *,
    vid: str,
    date_from: Optional[pd.Timestamp] = None,
    date_to: Optional[pd.Timestamp] = None,
    projects: Optional[list[str]] = None,
    contractors: Optional[list[str]] = None,
    skud_agg: str = GDRS_AGG_MONTH,
    term_index: Optional[GdrsTerminationIndex] = None,
    plan_as_of: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    """Сводка по контрагентам (Скрин 5): Контрагент / План / Среднее за месяц / Отклонение."""
    if long_fact is None or long_fact.empty:
        return pd.DataFrame()
    fact = _filter_fact_slice(
        long_fact,
        vid=vid,
        date_from=date_from,
        date_to=date_to,
        projects=projects,
        contractors=contractors,
    )
    fact = gdrs_filter_fact_by_termination(fact, term_index)
    if fact.empty:
        return pd.DataFrame()

    plan_col = "plan_workers" if vid.casefold() == "рабочие" else "plan_equipment"
    by_id, by_id_name, by_norm = _build_plan_lookup(plan, plan_col)
    _plan_snap = pd.Timestamp(plan_as_of).normalize() if plan_as_of is not None and pd.notna(plan_as_of) else (
        pd.Timestamp(date_to).normalize() if date_to is not None and pd.notna(date_to) else None
    )

    fact["date"] = pd.to_datetime(fact["date"])
    id_pick = (
        fact.groupby(["project_name", "contractor_name"], dropna=False)
        .agg(
            project_id=("project_id", lambda s: next((x for x in s.astype(str) if x.strip()), "")),
            contractor_id=("contractor_id", lambda s: next((x for x in s.astype(str) if x.strip()), "")),
        )
        .reset_index()
    )
    skud_vals = _skud_agg_per_pair(fact, skud_agg)
    summary = skud_vals.merge(id_pick, on=["project_name", "contractor_name"], how="left")
    summary["mean_per_day"] = summary["skud_val"].round(0)
    summary["plan"] = summary.apply(
        lambda r: _lookup_plan(
            str(r.get("project_id", "")), str(r.get("contractor_id", "")),
            str(r.get("project_name", "")), str(r.get("contractor_name", "")),
            by_id, by_id_name, by_norm,
            as_of_date=_plan_snap, term_index=term_index,
        ),
        axis=1,
    ).astype(float)
    out = (
        summary.groupby("contractor_name", as_index=False)
        .agg(plan=("plan", "sum"), mean_per_day=("mean_per_day", "sum"))
    )
    # Отклонение = Факт − План (среднее за день для периода).
    out["deviation"] = (out["mean_per_day"] - out["plan"]).round(0)
    return out[["contractor_name", "plan", "mean_per_day", "deviation"]]


GDRS_WEEK_LABELS: tuple[str, ...] = tuple(f"{i} неделя" for i in range(1, 7))
GDRS_WEEK_PLAN_KEYS: tuple[str, ...] = ("p1", "p2", "p3", "p4", "p5", "p6")
GDRS_WEEK_SKUD_KEYS: tuple[str, ...] = ("w1", "w2", "w3", "w4", "w5", "w6")


def gdrs_delta_pct_cell_bg_style(raw, *, theme: str = "dark") -> str:
    """Фон ячейки «Отклонение %» (факт − план в %): >0 зелёный, <0 красный, 0 нейтральный."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return ""
    try:
        v = float(raw)
    except Exception:
        return ""
    _light = str(theme or "").strip().lower() == "light"
    if v > 0:
        return (
            "background-color:rgba(21,128,61,0.22) !important;"
            if _light
            else "background-color:rgba(70,214,138,0.32) !important;"
        )
    if v < 0:
        t = min(max(-v, 0.0), 100.0) / 100.0
        alpha = 0.20 + 0.30 * t if _light else 0.24 + 0.36 * t
        if _light:
            return f"background-color:rgba(185,28,28,{alpha:.3f}) !important;"
        return f"background-color:rgba(255,84,84,{alpha:.3f}) !important;"
    return (
        "background-color:rgba(107,114,128,0.14) !important;"
        if _light
        else "background-color:rgba(136,153,170,0.18) !important;"
    )


def gdrs_deviation_cell_bg_style(raw, *, theme: str = "dark") -> str:
    """Фон ячейки «Отклонение» (факт − план): >0 зелёный, <0 красный, 0 нейтральный."""
    return gdrs_delta_pct_cell_bg_style(raw, theme=theme)


def _gdrs_matrix_table_css(wrap_id: str) -> str:
    """Сетка и рамки как в «Девелоперских проектах»; цвета колонок по ТЗ ГДРС."""
    w = wrap_id
    return f"""
<style>
html, body {{
  overflow-x: hidden !important;
  width: 100% !important;
  max-width: 100% !important;
  box-sizing: border-box !important;
}}
.bi-sortable-html-root {{
  width: 100% !important;
  max-width: 100% !important;
  overflow-x: hidden !important;
  box-sizing: border-box !important;
}}
#{w}.gdrs-table-wrap {{
  display: block !important;
  overflow-x: auto !important;
  overflow-y: visible !important;
  min-width: 0 !important;
  width: 100% !important;
  max-width: 100% !important;
  margin: 0.5rem 0;
  -webkit-overflow-scrolling: touch !important;
  scrollbar-width: thin;
  scrollbar-color: rgba(121,154,192,0.5) #141820;
}}
#{w}.gdrs-table-wrap::-webkit-scrollbar {{
  height: 10px;
}}
#{w}.gdrs-table-wrap::-webkit-scrollbar-thumb {{
  background: rgba(121,154,192,0.65);
  border-radius: 5px;
}}
#{w} .gdrs-matrix-table {{
  border: 3px solid #ffffff;
  border-collapse: separate !important;
  border-spacing: 0 !important;
  width: 100%;
  min-width: 100%;
  table-layout: fixed;
  font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 13px;
}}
#{w} .gdrs-matrix-table th.gdrs-col-equal,
#{w} .gdrs-matrix-table td.gdrs-col-equal {{
  width: 5.25rem;
  min-width: 4.5rem;
  max-width: 6.5rem;
  white-space: nowrap !important;
  box-sizing: border-box;
}}
#{w} .gdrs-matrix-table th.gdrs-td-text,
#{w} .gdrs-matrix-table td.gdrs-td-text {{
  width: auto;
  min-width: 9rem;
  max-width: 22rem;
  white-space: normal !important;
}}
#{w} .gdrs-matrix-table th,
#{w} .gdrs-matrix-table td {{
  border: 1px solid #5a6f82 !important;
  padding: 6px 8px !important;
  vertical-align: middle !important;
  background-clip: padding-box;
  text-align: center !important;
  overflow: visible !important;
  text-overflow: clip !important;
}}
#{w} .gdrs-matrix-table thead th {{
  background: #17314b !important;
  color: #86efac !important;
  font-size: 16px !important;
  font-weight: 800 !important;
  text-align: center !important;
  white-space: normal !important;
  word-wrap: break-word !important;
  overflow-wrap: anywhere !important;
  line-height: 1.25 !important;
  max-width: 11em !important;
  vertical-align: bottom !important;
}}
#{w} .gdrs-matrix-table tbody td {{
  white-space: normal !important;
  word-wrap: break-word !important;
  overflow-wrap: anywhere !important;
  max-width: 28em !important;
}}
#{w} .gdrs-matrix-table tbody td.gdrs-col-plan,
#{w} .gdrs-matrix-table tbody td.gdrs-col-skud,
#{w} .gdrs-matrix-table tbody td.gdrs-col-dev {{
  white-space: nowrap !important;
}}
#{w} .gdrs-matrix-table thead th.gdrs-col-equal,
#{w} .gdrs-matrix-table tbody td.gdrs-col-equal {{
  max-width: 6.5rem !important;
}}
#{w} .gdrs-matrix-table thead tr.gdrs-h-title th,
#{w} .gdrs-matrix-table thead tr.gdrs-h-period th {{
  background: #17314b !important;
  color: #ffffff !important;
  font-weight: 800 !important;
}}
#{w} .gdrs-matrix-table thead tr.gdrs-h-title th {{
  font-size: 18px !important;
  border-bottom: none !important;
}}
#{w} .gdrs-matrix-table thead tr.gdrs-h-period th {{
  font-size: 16px !important;
  border-top: none !important;
}}
#{w} .gdrs-matrix-table thead th.gdrs-h-plan-group {{
  background: #1e3d2f !important;
  color: #bbf7d0 !important;
  font-size: 17px !important;
  font-weight: 800 !important;
}}
#{w} .gdrs-matrix-table thead th.gdrs-h-skud-group {{
  background: #2a3440 !important;
  color: #e2e8f0 !important;
  font-size: 17px !important;
  font-weight: 800 !important;
}}
#{w} .gdrs-matrix-table thead th.gdrs-h-week {{
  font-size: 15px !important;
  font-weight: 800 !important;
  text-align: center !important;
}}
#{w} .gdrs-matrix-table thead th.gdrs-h-week-plan {{
  background: #1a3328 !important;
  color: #86efac !important;
}}
#{w} .gdrs-matrix-table thead th.gdrs-h-week-skud {{
  background: #252d38 !important;
  color: #cbd5e1 !important;
}}
#{w} .gdrs-matrix-table tbody td {{
  background-color: #0c1219 !important;
  color: #fafafa !important;
  font-weight: 700 !important;
  text-align: center !important;
}}
#{w} .gdrs-matrix-table tbody td.gdrs-col-plan {{
  background-color: rgba(134, 239, 172, 0.14) !important;
}}
#{w} .gdrs-matrix-table tbody td.gdrs-col-skud {{
  background-color: rgba(148, 163, 184, 0.16) !important;
}}
#{w} .gdrs-matrix-table tbody td.gdrs-col-dev {{
  background-color: rgba(148, 163, 184, 0.22) !important;
}}
#{w} .gdrs-matrix-table tbody td.gdrs-td-contractor {{
  color: #7dd3fc !important;
  font-weight: 700 !important;
}}
#{w} .gdrs-matrix-table tbody td.gdrs-td-text {{
  text-align: left !important;
  vertical-align: top !important;
  white-space: normal !important;
  word-wrap: break-word !important;
  overflow-wrap: anywhere !important;
  max-width: 36em !important;
  min-width: 10em !important;
}}
#{w} .gdrs-sep-l-strong {{
  box-shadow: inset 3px 0 0 #ffffff;
}}
#{w} .gdrs-sep-r-strong {{
  box-shadow: inset -3px 0 0 #ffffff;
}}
#{w} tr.gdrs-rk-project td,
#{w} tr.gdrs-rk-subtotal td {{
  font-size: 16px !important;
  font-weight: 800 !important;
}}
#{w} tr.gdrs-rk-project td.gdrs-col-plan,
#{w} tr.gdrs-rk-subtotal td.gdrs-col-plan {{
  background-color: rgba(134, 239, 172, 0.22) !important;
}}
#{w} tr.gdrs-rk-project td.gdrs-col-skud,
#{w} tr.gdrs-rk-subtotal td.gdrs-col-skud {{
  background-color: rgba(148, 163, 184, 0.24) !important;
}}
#{w} tr.gdrs-rk-project td.gdrs-col-dev,
#{w} tr.gdrs-rk-subtotal td.gdrs-col-dev {{
  background-color: rgba(148, 163, 184, 0.3) !important;
}}
#{w} tr.gdrs-rk-project td:not(.gdrs-col-plan):not(.gdrs-col-skud):not(.gdrs-col-dev),
#{w} tr.gdrs-rk-subtotal td:not(.gdrs-col-plan):not(.gdrs-col-skud):not(.gdrs-col-dev) {{
  background: #1f2630 !important;
}}
#{w} tr.gdrs-rk-project td:first-child,
#{w} tr.gdrs-rk-subtotal td:first-child {{
  color: #ffffff !important;
  font-size: 20px !important;
  font-weight: 900 !important;
}}
#{w} tr.gdrs-rk-project td {{
  border-top: 2px solid rgba(255,255,255,0.75) !important;
  border-bottom: 2px solid rgba(255,255,255,0.75) !important;
}}
#{w} tr.gdrs-rk-total td,
#{w} tr.gdrs-rk-grand td {{
  font-size: 16px !important;
  font-weight: 800 !important;
  border-top: 2px solid rgba(160,220,255,0.9) !important;
  border-bottom: 2px solid rgba(160,220,255,0.9) !important;
}}
#{w} tr.gdrs-rk-total td.gdrs-col-plan,
#{w} tr.gdrs-rk-grand td.gdrs-col-plan {{
  background-color: rgba(134, 239, 172, 0.22) !important;
}}
#{w} tr.gdrs-rk-total td.gdrs-col-skud,
#{w} tr.gdrs-rk-grand td.gdrs-col-skud {{
  background-color: rgba(148, 163, 184, 0.24) !important;
}}
#{w} tr.gdrs-rk-total td.gdrs-col-dev,
#{w} tr.gdrs-rk-grand td.gdrs-col-dev {{
  background-color: rgba(148, 163, 184, 0.3) !important;
}}
#{w} tr.gdrs-rk-total td:not(.gdrs-col-plan):not(.gdrs-col-skud):not(.gdrs-col-dev),
#{w} tr.gdrs-rk-grand td:not(.gdrs-col-plan):not(.gdrs-col-skud):not(.gdrs-col-dev) {{
  background: #102b3a !important;
}}
#{w} td.gdrs-u, #{w} td.gdrs-u span {{ color: #ff5454 !important; font-weight: 800 !important; }}
#{w} td.gdrs-o, #{w} td.gdrs-o span {{ color: #46d68a !important; font-weight: 800 !important; }}
#{w} td.gdrs-z, #{w} td.gdrs-z span {{ color: #8899aa !important; }}
</style>
"""


def render_gdrs_matrix_table_html(
    view: "pd.DataFrame",
    *,
    fixed_cols: list[str],
    delta_col: str,
    kind_col: str = "__kind__",
    wrap_id: str | None = None,
    title_line: str = "",
    period_line: str = "",
    delta_bg_style=None,
    show_week_columns: bool = True,
    week_labels: Optional[list[str]] = None,
    theme: str = "dark",
) -> str:
    """HTML-таблица ГДРС: двухуровневая шапка «План» / «СКУД» над неделями 1–6 или компакт без недель."""
    import html as html_module

    if view is None or getattr(view, "empty", True):
        return ""

    if delta_bg_style is None:
        delta_bg_style = lambda raw: gdrs_delta_pct_cell_bg_style(raw, theme=theme)

    wk_labels = list(week_labels or GDRS_WEEK_LABELS)
    wk_n = min(len(wk_labels), 6)
    wk_labels = wk_labels[:wk_n]
    plan_keys = list(GDRS_WEEK_PLAN_KEYS[:wk_n])
    skud_keys = list(GDRS_WEEK_SKUD_KEYS[:wk_n])
    if show_week_columns:
        show_cols = list(fixed_cols) + [delta_col] + plan_keys + skud_keys
    else:
        show_cols = list(fixed_cols) + [delta_col]
    ncols = len(show_cols)
    wid = wrap_id or ("gdrs_mtx_" + str(abs(id(view))))
    n_fixed = len(fixed_cols)
    if show_week_columns:
        i_delta = n_fixed
        i_plan0 = n_fixed + 1
        i_plan1 = n_fixed + wk_n
        i_skud0 = n_fixed + wk_n + 1
        i_skud1 = n_fixed + 2 * wk_n
    else:
        i_plan0 = i_plan1 = i_skud0 = i_skud1 = -1
        i_delta = n_fixed
    text_cols = {"Контрагент", "Вид работ", "Вид работы"}
    numeric_cols = set(fixed_cols[2:]) | set(plan_keys) | set(skud_keys)

    def _border_cls(ci: int) -> str:
        parts = ["gdrs-cell"]
        if ci == 1:
            parts.append("gdrs-sep-r-strong")
        if ci == n_fixed - 1:
            parts.append("gdrs-sep-r-strong")
        if show_week_columns:
            if ci == i_plan0:
                parts.append("gdrs-sep-l-strong")
            if ci == i_plan1:
                parts.append("gdrs-sep-r-strong")
            if ci == i_skud0:
                parts.append("gdrs-sep-l-strong")
            if ci == i_skud1:
                parts.append("gdrs-sep-r-strong")
        if ci == i_delta:
            parts.append("gdrs-sep-l-strong")
        return " ".join(parts)

    def _fmt_num(v) -> str:
        try:
            return f"{int(v):,}".replace(",", " ")
        except (TypeError, ValueError):
            return "0"

    plan_keys_set = set(plan_keys)
    skud_keys_set = set(skud_keys)

    def _metric_cls(col: str) -> str:
        if col == "План" or col in plan_keys_set:
            return "gdrs-col-plan"
        if col == "СКУД" or col in skud_keys_set:
            return "gdrs-col-skud"
        if col == "Отклонение":
            return "gdrs-col-dev"
        if col == delta_col:
            return "gdrs-col-dev"
        return ""

    def _th_metric_cls(col: str) -> str:
        if col == "План":
            return "gdrs-col-plan"
        if col == "СКУД":
            return "gdrs-col-skud"
        if col == "Отклонение":
            return "gdrs-col-dev"
        if col == delta_col:
            return "gdrs-col-dev"
        return ""

    def _td_html(
        ci: int,
        col: str,
        inner: str,
        *,
        raw_val=None,
        extra_cls: str = "",
        extra_style: str = "",
        is_detail: bool = False,
    ) -> str:
        cls = _border_cls(ci)
        mc = _metric_cls(col)
        if mc:
            cls += f" {mc}"
        if col not in text_cols:
            cls += " gdrs-col-equal"
        if col in text_cols:
            cls += " gdrs-td-text"
            if is_detail and col in ("Контрагент",):
                cls += " gdrs-td-contractor"
        if extra_cls:
            cls += f" {extra_cls}"
        st = extra_style or ""
        sort_attr = ""
        if col in numeric_cols or col == "Отклонение":
            try:
                rv = raw_val if raw_val is not None else inner
                if isinstance(rv, str):
                    rv = rv.replace(" ", "").replace(" ", "").replace(",", ".")
                fv = float(rv)
                if fv == fv:
                    sort_attr = f' data-sort-val="{fv}"'
            except (TypeError, ValueError):
                pass
        return f'<td class="{cls.strip()}" style="{st}"{sort_attr}>{inner}</td>'

    def _row_html(row) -> str:
        kind = str(row.get(kind_col, "") or "").strip().casefold()
        is_detail = kind not in ("project", "subtotal", "grand_total", "total")
        tr_cls = ""
        if kind == "project":
            tr_cls = ' class="gdrs-rk-project"'
        elif kind == "subtotal":
            tr_cls = ' class="gdrs-rk-subtotal"'
        elif kind == "grand_total":
            tr_cls = ' class="gdrs-rk-grand"'
        elif kind == "total":
            tr_cls = ' class="gdrs-rk-total"'
        cells: list[str] = []
        for ci, col in enumerate(show_cols):
            v = row.get(col, "")
            if col == "Отклонение":
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    fv = None
                if fv is not None and fv == fv:
                    dev_cls = "gdrs-o" if fv > 0 else ("gdrs-u" if fv < 0 else "gdrs-z")
                    dev_bg = gdrs_deviation_cell_bg_style(fv, theme=theme)
                    inner = "0" if int(round(fv)) == 0 else f"{int(round(fv)):+d}"
                    cells.append(
                        _td_html(
                            ci,
                            col,
                            html_module.escape(inner),
                            raw_val=fv,
                            extra_cls=dev_cls,
                            extra_style=dev_bg,
                            is_detail=is_detail,
                        )
                    )
                else:
                    cells.append(_td_html(ci, col, "—", is_detail=is_detail))
            elif col == delta_col:
                raw_pct = row.get("_delta_pct_raw", v)
                try:
                    pct = float(raw_pct)
                except (TypeError, ValueError):
                    pct = float("nan")
                if pct == pct:
                    grad = (delta_bg_style(raw_pct) if delta_bg_style else "") or ""
                    pct_cls = "gdrs-o" if pct > 0 else ("gdrs-u" if pct < 0 else "gdrs-z")
                    sign = "+" if pct > 0 else ""
                    cells.append(
                        _td_html(
                            ci,
                            col,
                            html_module.escape(f"{sign}{pct:.0f}%"),
                            extra_cls=pct_cls,
                            extra_style=grad,
                            is_detail=is_detail,
                        )
                    )
                elif isinstance(v, str) and str(v).strip() and str(v).strip() != "—":
                    cells.append(_td_html(ci, col, html_module.escape(str(v)), is_detail=is_detail))
                else:
                    cells.append(_td_html(ci, col, "—", is_detail=is_detail))
            elif col in numeric_cols:
                cells.append(_td_html(ci, col, html_module.escape(_fmt_num(v)), raw_val=v, is_detail=is_detail))
            else:
                cells.append(
                    _td_html(
                        ci,
                        col,
                        html_module.escape(str(v) if v is not None else ""),
                        is_detail=is_detail,
                    )
                )
        return f"<tr{tr_cls}>" + "".join(cells) + "</tr>"

    thead_parts: list[str] = []
    if title_line:
        thead_parts.append(
            f'<tr class="gdrs-h-title"><th colspan="{ncols}">'
            f"{html_module.escape(title_line)}</th></tr>"
        )
    if period_line:
        thead_parts.append(
            f'<tr class="gdrs-h-period"><th colspan="{ncols}">'
            f"{html_module.escape(period_line)}</th></tr>"
        )
    thead_parts.append("<tr class=\"gdrs-h-metrics\">")
    if show_week_columns:
        delta_title = "Отклонение %" if delta_col in ("Дельта (%)", "Дельта %", "Δ %", "Δ%") else delta_col
        for ci, col in enumerate(fixed_cols):
            hmc = _th_metric_cls(col)
            hcls = _border_cls(ci) + (f" {hmc}" if hmc else "")
            if col not in text_cols:
                hcls += " gdrs-col-equal"
            _sort = ' data-gdrs-sort="1" data-sort-label="' + html_module.escape(col) + '"' if col in ("Контрагент", "Вид работ", "План", "СКУД", "Отклонение") or col == delta_col else ""
            thead_parts.append(
                f'<th rowspan="2" class="{hcls.strip()}"{_sort}>{html_module.escape(col)}</th>'
            )
        thead_parts.append(
            f'<th rowspan="2" class="{_border_cls(i_delta)} gdrs-col-equal gdrs-col-dev gdrs-sep-r-strong">'
            f'{html_module.escape(delta_title)}</th>'
        )
        thead_parts.append(
            f'<th colspan="{wk_n}" class="gdrs-h-plan-group gdrs-sep-l-strong gdrs-sep-r-strong">План</th>'
        )
        thead_parts.append(
            f'<th colspan="{wk_n}" class="gdrs-h-skud-group gdrs-sep-l-strong gdrs-sep-r-strong">СКУД</th>'
        )
        thead_parts.append("</tr><tr>")
        for wi, lbl in enumerate(wk_labels):
            wcls = "gdrs-h-week gdrs-h-week-plan gdrs-col-plan"
            if wi == 0:
                wcls += " gdrs-sep-l-strong"
            if wi == wk_n - 1:
                wcls += " gdrs-sep-r-strong"
            wcls += " gdrs-col-equal"
            thead_parts.append(f'<th class="{wcls}" data-gdrs-sort="1" data-sort-label="{html_module.escape(lbl)}">{html_module.escape(lbl)}</th>')
        for wi, lbl in enumerate(wk_labels):
            wcls = "gdrs-h-week gdrs-h-week-skud gdrs-col-skud"
            if wi == 0:
                wcls += " gdrs-sep-l-strong"
            if wi == wk_n - 1:
                wcls += " gdrs-sep-r-strong"
            wcls += " gdrs-col-equal"
            thead_parts.append(f'<th class="{wcls}" data-gdrs-sort="1" data-sort-label="{html_module.escape(lbl)}">{html_module.escape(lbl)}</th>')
        thead_parts.append("</tr>")
    else:
        for ci, col in enumerate(show_cols):
            hmc = _th_metric_cls(col)
            hcls = _border_cls(ci) + (f" {hmc}" if hmc else "")
            if col not in text_cols:
                hcls += " gdrs-col-equal"
            _sort = ' data-gdrs-sort="1" data-sort-label="' + html_module.escape(col) + '"' if col in ("Контрагент", "Вид работ", "План", "СКУД", "Отклонение") or col == delta_col else ""
            thead_parts.append(
                f'<th class="{hcls.strip()}"{_sort}>{html_module.escape(col)}</th>'
            )
        thead_parts.append("</tr>")

    body = "".join(_row_html(r) for _, r in view.iterrows())
    from dashboards.gdrs_theme import get_gdrs_theme, gdrs_matrix_table_css

    _th = get_gdrs_theme(theme)
    _wrap_cls = "gdrs-table-wrap gdrs-light-table" if _th.name == "light" else "gdrs-table-wrap"
    return (
f'<div id="{wid}" class="{_wrap_cls}">'
        + gdrs_matrix_table_css(wid, _th)
        + '<table class="gdrs-matrix-table bi-sortable-table bi-sort-click-only"><thead>'
        + "".join(thead_parts)
        + "</thead><tbody>"
        + body
        + "</tbody></table></div>"
    )

# =====================================================================
# Disk-кэш для отчёта ГДРС (@st.cache_data)
# =====================================================================
import streamlit as st


def _gdrs_paths_mtime_sig(paths) -> tuple:
    from pathlib import Path as _P

    sig: list[tuple] = []
    for p in sorted({str(_P(x).resolve()) for x in paths}):
        pp = _P(p)
        if pp.is_file():
            stt = pp.stat()
            sig.append((p, stt.st_mtime_ns, stt.st_size))
    return tuple(sig)


@st.cache_data(show_spinner=False, ttl=3600)
def _gdrs_cached_load_resursi(version_id: int, db_mtime: float) -> pd.DataFrame:
    from web_db_read import load_gdrs_fact_long

    return load_gdrs_fact_long(int(version_id))


@st.cache_data(show_spinner=False, ttl=3600)
def _gdrs_cached_plan_aggregate(
    version_id: int,
    db_mtime: float,
    snapshot_iso: str,
    dogovor_sources_sig: tuple[str, ...],
) -> pd.DataFrame:
    from web_db_read import json_records_by_source

    snap = pd.Timestamp(snapshot_iso) if snapshot_iso else None
    dog = json_records_by_source(int(version_id), "dogovor_json")
    spr = json_records_by_source(int(version_id), "spravochniki_json")
    plan_df = load_plan_aggregate(
        dogovor_records=dog,
        sprav_records=spr,
        snapshot_date=snap,
    )
    return gdrs_drop_excluded_contractors(plan_df)


@st.cache_data(show_spinner=False, ttl=3600)
def _gdrs_cached_termination_index(
    version_id: int,
    db_mtime: float,
    dogovor_sources_sig: tuple[str, ...],
) -> GdrsTerminationIndex:
    from web_db_read import json_records_by_source

    dog = json_records_by_source(int(version_id), "dogovor_json")
    return load_gdrs_termination_index(dogovor_records=dog)


@st.cache_data(show_spinner=False, ttl=3600)
def _gdrs_cached_dannye_maps(version_id: int, db_mtime: float):
    from web_db_read import load_version_dataframe

    df = load_version_dataframe(int(version_id), "reference_dannye")
    return load_1c_dannye_article_maps_from_df(df)


@st.cache_data(show_spinner=False, ttl=3600)
def _gdrs_cached_enriched_fact(
    version_id: int,
    db_mtime: float,
    dogovor_sources_sig: tuple[str, ...],
) -> pd.DataFrame:
    """Обогащённый факт ГДРС (project/contractor ids + kontr-имена + termination).

    Не зависит от значений фильтров, только от версии данных БД. Раньше вся цепочка
    enrich_* пересчитывалась на каждую смену фильтра (секунды на ререндер) — теперь
    считается один раз на версию БД и переиспользуется из кэша.
    """
    from dashboards.project_labels import apply_unified_project_column
    from web_db_read import json_records_by_source, load_gdrs_fact_long

    long_fact = load_gdrs_fact_long(int(version_id))
    if long_fact is None or long_fact.empty:
        return long_fact

    dog = json_records_by_source(int(version_id), "dogovor_json")
    kontr_records = json_records_by_source(int(version_id), "kontr_json")
    kontr_flat = [r for recs in kontr_records.values() for r in recs]

    long_fact = apply_unified_project_column(long_fact, "project_name")
    kontr_index = load_1c_kontr_index(records=kontr_flat) if kontr_flat else None
    long_fact = enrich_gdrs_fact_contractor_ids(
        long_fact, dogovor_records=dog, kontr=kontr_index
    )
    long_fact = enrich_gdrs_fact_project_ids(long_fact, dogovor_records=dog)
    long_fact = gdrs_apply_kontr_contractor_names(long_fact, kontr_index)
    term_index = _gdrs_cached_termination_index(
        int(version_id), db_mtime, dogovor_sources_sig
    )
    long_fact = gdrs_filter_fact_by_termination(long_fact, term_index)
    long_fact = gdrs_drop_excluded_contractors(long_fact)
    return long_fact


def _gdrs_dogovor_sources_sig(version_id: int) -> tuple[str, ...]:
    try:
        from web_db_read import json_records_by_source

        return tuple(sorted(json_records_by_source(int(version_id), "dogovor_json").keys()))
    except Exception:
        return ()


def _gdrs_plan_loader(version_id: int, db_mtime: float):
    dog_sig = _gdrs_dogovor_sources_sig(version_id)

    def _load(snap: pd.Timestamp) -> pd.DataFrame:
        iso = pd.Timestamp(snap).normalize().isoformat()
        return _gdrs_cached_plan_aggregate(version_id, db_mtime, iso, dog_sig)

    return _load


def warm_gdrs_disk_caches() -> None:
    """Прогрев кэша ГДРС из БД до отрисовки отчёта."""
    try:
        from web_db_read import resolve_version_id, web_db_mtime

        vid = resolve_version_id()
        if not vid:
            return
        mtime = web_db_mtime()
        _gdrs_cached_load_resursi(vid, mtime)
        _gdrs_cached_dannye_maps(vid, mtime)
    except Exception:
        pass
