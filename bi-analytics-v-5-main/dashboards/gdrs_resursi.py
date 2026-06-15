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


def normalize_name(s: object) -> str:
    """Нормализация названия (контрагента, проекта) для fuzzy-match.

    Убирает легальный префикс/суффикс ООО/АО/ЗАО/…, регистр, пробелы,
    скобочные пояснения, кавычки.
    Примеры:
      «ООО Альфа С (БЛОК U3 U4)»  → «альфас»
      «АЛЬФА С ООО»                → «альфас»
      «ООО "СК Сети"»              → «сксети»
      «АО Марафон»                 → «марафон»
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


def _pick_canonical_name(names: pd.Series) -> Optional[str]:
    """Самое популярное (mode) НЕ-UUID имя в серии. Используется для канонизации."""
    cnt = names.value_counts()
    cnt = cnt[~cnt.index.to_series().apply(_is_uuid_like)]
    if cnt.empty:
        return None
    return str(cnt.idxmax())


def _canonicalize_project_names(df: pd.DataFrame) -> pd.DataFrame:
    """Подменяет UUID-подобные `project_name` на каноническое человекочитаемое имя.
    Канонический выбор — самое популярное не-UUID имя для того же `project_id`,
    или (если ID нет/пуст) — самое популярное по нормализованному имени.
    Также схлопывает варианты типа «Дмитровский1» / «Дмитровский-1».
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
        if _is_uuid_like(name):
            return by_id.get(pid, name)
        return by_norm.get(str(row["__name_norm__"]), name)

    work["project_name"] = work.apply(_resolve, axis=1)
    work = work.drop(columns="__name_norm__")
    try:
        from dashboards.project_labels import apply_unified_project_column

        work = apply_unified_project_column(work, "project_name")
    except Exception:
        pass
    return work


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
    frames = []
    for p in paths:
        try:
            df = load_resursi_file(Path(p))
        except Exception:
            df = pd.DataFrame()
        if df is not None and not df.empty:
            frames.append(df)
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
    out = out.drop_duplicates(
        subset=["project_name", "contractor_name", "vid_resursa", "date"], keep="last"
    )
    return out

@dataclass(frozen=True)
class GdrsKontrIndex:
    """Справочник 1С Kontr."""

    ids: frozenset[str]
    norm_names: frozenset[str]
    id_by_norm: dict[str, str]


@dataclass(frozen=True)
class GdrsTerminationIndex:
    """Даты расторжения по парам проект×контрагент (из Dogovor.json)."""

    by_id: dict[tuple[str, str], pd.Timestamp]
    by_norm: dict[tuple[str, str], pd.Timestamp]

    @staticmethod
    def empty() -> GdrsTerminationIndex:
        return GdrsTerminationIndex(by_id={}, by_norm={})


def load_gdrs_termination_index(
    dogovor_paths: Iterable[Path | str],
) -> GdrsTerminationIndex:
    """Минимальная дата расторжения по (project_id, contractor_id) из последнего Dogovor.json."""
    dated: list[tuple[pd.Timestamp, Path]] = []
    undated: list[Path] = []
    for raw in dogovor_paths:
        p = Path(raw)
        fd = _dogovor_file_date(p)
        if fd is None:
            undated.append(p)
            continue
        dated.append((fd, p))
    if not dated:
        path = undated[0] if undated else None
    else:
        dated.sort(key=lambda t: t[0])
        path = dated[-1][1]
    if path is None:
        return GdrsTerminationIndex.empty()
    raw = load_plan_from_dogovor(path, snapshot_date=None)
    if raw is None or raw.empty or "date_termination" not in raw.columns:
        return GdrsTerminationIndex.empty()
    sentinel = pd.Timestamp("0001-01-01")
    by_id: dict[tuple[str, str], pd.Timestamp] = {}
    by_norm: dict[tuple[str, str], pd.Timestamp] = {}
    for _, r in raw.iterrows():
        term = r.get("date_termination")
        if term is None or (isinstance(term, float) and pd.isna(term)):
            continue
        term_ts = pd.to_datetime(term, errors="coerce")
        if term_ts is None or not pd.notna(term_ts):
            continue
        term_ts = pd.Timestamp(term_ts).normalize()
        if term_ts <= sentinel:
            continue
        pid = str(r.get("project_id", "")).strip()
        cid = str(r.get("contractor_id", "")).strip()
        pn = normalize_name(str(r.get("project_name", "")))
        cn = normalize_name(str(r.get("contractor_name", "")))
        if pid and cid:
            key = (pid, cid)
            by_id[key] = min(by_id[key], term_ts) if key in by_id else term_ts
        if pn and cn:
            nkey = (pn, cn)
            by_norm[nkey] = min(by_norm[nkey], term_ts) if nkey in by_norm else term_ts
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
    """С даты расторжения (включительно) контрагент не учитывается в плане и факте."""
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


def load_1c_kontr_index(paths: Iterable[Path | str]) -> GdrsKontrIndex:
    ids: set[str] = set()
    norm_names: set[str] = set()
    id_by_norm: dict[str, str] = {}
    for p in paths:
        data = _safe_json(Path(p))
        if not isinstance(data, list):
            continue
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
            if nn:
                norm_names.add(nn)
                if cid and nn not in id_by_norm:
                    id_by_norm[nn] = cid
    return GdrsKontrIndex(frozenset(ids), frozenset(norm_names), id_by_norm)


def build_dogovor_contractor_id_lookup(
    dogovor_paths: Iterable[Path | str],
) -> tuple[dict[tuple[str, str], str], dict[str, str]]:
    by_proj: dict[tuple[str, str], str] = {}
    by_name: dict[str, str] = {}
    for p in dogovor_paths:
        df = load_plan_from_dogovor(Path(p), snapshot_date=None)
        if df is None or df.empty:
            continue
        for _, r in df.iterrows():
            pid = str(r.get("project_id", "")).strip()
            cid = str(r.get("contractor_id", "")).strip()
            cname = str(r.get("contractor_name", "")).strip()
            if not cid:
                continue
            nn = normalize_name(cname)
            if nn:
                by_name.setdefault(nn, cid)
                if pid:
                    by_proj.setdefault((pid, nn), cid)
    return by_proj, by_name


def build_dogovor_project_id_lookup(
    dogovor_paths: Iterable[Path | str],
) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    """norm(project_name) → project_id; (norm(project), norm(contractor)) → project_id."""
    by_name: dict[str, str] = {}
    by_pair: dict[tuple[str, str], str] = {}
    for p in dogovor_paths:
        df = load_plan_from_dogovor(Path(p), snapshot_date=None)
        if df is None or df.empty:
            continue
        for _, r in df.iterrows():
            pid = str(r.get("project_id", "")).strip()
            pname = str(r.get("project_name", "")).strip()
            cname = str(r.get("contractor_name", "")).strip()
            if not pid:
                continue
            pn = normalize_name(pname)
            cn = normalize_name(cname)
            if pn:
                by_name.setdefault(pn, pid)
            if pn and cn:
                by_pair.setdefault((pn, cn), pid)
    return by_name, by_pair


def enrich_gdrs_fact_project_ids(
    df: pd.DataFrame,
    *,
    dogovor_paths: Optional[Iterable[Path | str]] = None,
) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    work = df.copy()
    by_name, by_pair = build_dogovor_project_id_lookup(dogovor_paths or [])

    def _resolve_pid(row: pd.Series) -> str:
        cur = str(row.get("project_id", "")).strip()
        if cur:
            return cur
        pn = normalize_name(str(row.get("project_name", "")))
        cn = normalize_name(str(row.get("contractor_name", "")))
        if pn and cn and (pn, cn) in by_pair:
            return by_pair[(pn, cn)]
        if pn and pn in by_name:
            return by_name[pn]
        return ""

    work["project_id"] = work.apply(_resolve_pid, axis=1)
    return work


def enrich_gdrs_fact_contractor_ids(
    df: pd.DataFrame,
    *,
    dogovor_paths: Optional[Iterable[Path | str]] = None,
    kontr: Optional[GdrsKontrIndex] = None,
) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    work = df.copy()
    by_proj, by_name = build_dogovor_contractor_id_lookup(dogovor_paths or [])

    def _resolve_id(row: pd.Series) -> str:
        cur = _sanitize_contractor_id(row.get("contractor_id", ""))
        if cur:
            return cur
        pid = str(row.get("project_id", "")).strip()
        nn = normalize_name(str(row.get("contractor_name", "")))
        if pid and nn and (pid, nn) in by_proj:
            return by_proj[(pid, nn)]
        if nn and nn in by_name:
            return by_name[nn]
        if kontr and nn and nn in kontr.id_by_norm:
            return kontr.id_by_norm[nn]
        return ""

    work["contractor_id"] = work.apply(_resolve_id, axis=1)
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


def gdrs_apply_kontr_plan_gate(
    rows: pd.DataFrame,
    kontr: Optional[GdrsKontrIndex],
) -> pd.DataFrame:
    if rows is None or rows.empty or kontr is None:
        return rows
    if not kontr.ids and not kontr.norm_names:
        return rows
    work = rows.copy()
    detail = work["row_kind"].astype(str) == "row"
    for idx in work.index[detail]:
        r = work.loc[idx]
        if gdrs_contractor_in_kontr(
            str(r.get("contractor_id", "")),
            str(r.get("contractor_name", "")),
            kontr,
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


def load_plan_from_dogovor(
    path: Path,
    *,
    snapshot_date: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    """Из 1с_*_Dogovor.json (по состоянию на `snapshot_date`) → DataFrame.

    Поля «Количество_Людей» и «Количество_Техники» — массивы вида
    `[{Дата: ..., Количество: ...}, ...]`. snapshot берётся «не позднее snapshot_date».
    Если snapshot_date is None — берётся последнее значение.
    """
    data = _safe_json(Path(path))
    if not isinstance(data, list):
        return pd.DataFrame(
            columns=[
                "project_id", "contractor_id", "project_name", "contractor_name",
                "contract_name", "plan_workers", "plan_equipment", "date_start", "date_end",
                "date_termination",
            ]
        )
    rows = []
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
                "plan_workers": _snapshot_history(r.get("Количество_Людей"), snapshot_date),
                "plan_equipment": _snapshot_history(r.get("Количество_Техники"), snapshot_date),
                # Сырые строки — парсим колонку векторно один раз ниже (без 2× to_datetime на строку).
                "date_start": r.get("Дата_Начала_Договора"),
                "date_end": r.get("Дата_Окончания_Договора"),
                "date_termination": _contract_termination_date_raw(r),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = _dearrow_object_columns(df)
    df["date_start"] = pd.to_datetime(df["date_start"], errors="coerce", utc=True).dt.tz_localize(None)
    df["date_end"] = pd.to_datetime(df["date_end"], errors="coerce", utc=True).dt.tz_localize(None)
    df["date_termination"] = pd.to_datetime(df["date_termination"], errors="coerce", utc=True).dt.tz_localize(None)
    if snapshot_date is not None:
        # Договоры с реальной Дата_Окончания, истёкшей до даты снапшота, не действуют:
        # их «Количество_Людей» нередко обрывается без закрывающего 0, и snapshot тянет
        # старое значение в период. Аналогично — ещё не начавшиеся договоры и расторжение.
        snap = pd.Timestamp(snapshot_date).normalize()
        sentinel = pd.Timestamp("0001-01-01")
        de = df["date_end"]
        ds = df["date_start"]
        dt = df["date_termination"]
        expired = de.notna() & (de > sentinel) & (de.dt.normalize() < snap)
        not_started = ds.notna() & (ds > sentinel) & (ds.dt.normalize() > snap)
        terminated = dt.notna() & (dt > sentinel) & (dt.dt.normalize() <= snap)
        drop = expired | not_started | terminated
        df.loc[drop, ["plan_workers", "plan_equipment"]] = np.nan
    return df


def load_plan_from_spravochniki(
    path: Path,
    *,
    snapshot_date: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    """Из 1с_*_spravochniki.json (snapshot на дату) → DataFrame с агрегированным планом.

    «КоличествоРаботников» и «КоличествоСпецТехники» — массивы вида
    `[{Дата, Количество}, ...]`.
    """
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


def _first_nonempty(series) -> str:
    for x in series:
        s = str(x).strip()
        if s and s.lower() not in ("nan", "none"):
            return s
    return ""


def _source_file_date(path: Path) -> Optional[pd.Timestamp]:
    """Дата снапшота из имени файла «…_DD-MM-YYYY_…» (Dogovor, resursi) → Timestamp."""
    m = _FILE_DATE_RE.search(Path(path).name)
    if not m:
        return None
    dd, mm, yyyy = m.groups()
    try:
        return pd.Timestamp(year=int(yyyy), month=int(mm), day=int(dd))
    except ValueError:
        return None


def _dogovor_file_date(path: Path) -> Optional[pd.Timestamp]:
    """Дата снапшота из имени файла «1с_DD-MM-YYYY_…» → Timestamp (или None)."""
    return _source_file_date(path)


def _pick_dogovor_path_for_snapshot(
    paths: Iterable[Path | str],
    snapshot_date: Optional[pd.Timestamp],
) -> Optional[Path]:
    """Файл Dogovor для среза плана: последний с датой в имени ≤ snapshot_date;
    если таких нет — самый поздний из будущих (в нём полнее история Количество_Людей)."""
    snap = pd.Timestamp(snapshot_date).normalize() if snapshot_date is not None else None
    dated: list[tuple[pd.Timestamp, Path]] = []
    undated: list[Path] = []
    for raw in paths:
        p = Path(raw)
        fd = _dogovor_file_date(p)
        if fd is None:
            undated.append(p)
            continue
        dated.append((fd, p))
    if not dated:
        return undated[0] if undated else None
    if snap is None:
        dated.sort(key=lambda t: t[0])
        return dated[-1][1]
    le = [t for t in dated if t[0] <= snap]
    if le:
        le.sort(key=lambda t: t[0])
        return le[-1][1]
    dated.sort(key=lambda t: t[0])
    return dated[-1][1]


def load_plan_aggregate(
    dogovor_paths: Iterable[Path | str],
    sprav_paths: Iterable[Path | str],
    *,
    snapshot_date: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    """Загрузить план из ВСЕХ файлов Dogovor.json + spravochniki.json
    и агрегировать в единую таблицу.

    Алгоритм:
        - Для каждого Dogovor.json берём snapshot на дату snapshot_date.
        - Внутри файла план по (project_id, contractor_id) суммируется по РАЗНЫМ
          договорам, но дубли одного договора и его доп.соглашений (ДС) схлопываются
          по сигнатуре «NN-СА/YY»: ДС замещает базовый договор (берём MAX по сигнатуре),
          а не суммируется с ним — иначе план задваивается.
        - Между файлами берём значение из ПОСЛЕДНЕГО снапшота ≤ snapshot_date
          (по дате в имени файла), а не MAX по дням: max завышал план, цепляясь
          за день с лишними/транзитными строками ДС.
        - spravochniki.json — fallback, если в Dogovor плана нет.
    """
    def _contract_key(cn: str) -> str:
        """Ключ схлопывания: сигнатура договора «NN-СА/YY» или «name::<норм. имя>»."""
        sigs = contract_signatures(cn)
        return sigs[0] if sigs else ("name::" + normalize_name(cn))

    def _per_file_dog(p: Path) -> pd.DataFrame:
        df = load_plan_from_dogovor(Path(p), snapshot_date=snapshot_date)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df[
            (df["project_id"].astype(str).str.strip() != "")
            & (df["contractor_id"].astype(str).str.strip() != "")
        ]
        if df.empty:
            return pd.DataFrame()
        # Векторно вместо построчного _dedup по группам (~22с на 32k групп):
        # 1) ключ договора по уникальным именам (кэшированные функции),
        # 2) MAX плана по сигнатуре договора/ДС, 3) сумма по разным договорам.
        df = df.copy()
        cn = df["contract_name"].fillna("").astype(str).str.strip()
        df["__cn__"] = cn
        uniq = pd.unique(cn.to_numpy())
        key_map = {nm: _contract_key(nm) for nm in uniq}
        df["__key__"] = cn.map(key_map)
        per_key = (
            df.groupby(["project_id", "contractor_id", "__key__"], dropna=False, as_index=False)[
                ["plan_workers", "plan_equipment"]
            ].max()
        )
        plan = (
            per_key.groupby(["project_id", "contractor_id"], dropna=False, as_index=False)[
                ["plan_workers", "plan_equipment"]
            ].sum(min_count=1)
        )
        meta = df.groupby(["project_id", "contractor_id"], dropna=False, as_index=False).agg(
            project_name=("project_name", "first"),
            contractor_name=("contractor_name", "first"),
            contract_name=("__cn__", lambda s: " · ".join(sorted({x for x in s if x}))),
        )
        out = meta.merge(plan, on=["project_id", "contractor_id"], how="left")
        return out[
            [
                "project_id", "contractor_id", "project_name", "contractor_name",
                "contract_name", "plan_workers", "plan_equipment",
            ]
        ]

    def _per_file_sprav(p: Path) -> pd.DataFrame:
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

    def _ordered_with_index(paths, fn) -> pd.DataFrame:
        """Собрать кадры по файлам, упорядочив по дате снапшота из имени (asc).
        Файлы со снапшотом > snapshot_date отбрасываются (берём «последний ≤ даты»).
        Если таких нет — берём самый поздний доступный файл: в актуальной выгрузке
        история «Количество_Людей» полнее, чем в ранних снапшотах (февраль при выгрузке в мае).
        Файлы без даты в имени — fallback. `__order__` растёт с датой."""
        snap = pd.Timestamp(snapshot_date).normalize() if snapshot_date is not None else None
        items_le: list[tuple[Optional[pd.Timestamp], pd.DataFrame]] = []
        items_future: list[tuple[Optional[pd.Timestamp], pd.DataFrame]] = []
        for p in paths:
            fdate = _dogovor_file_date(Path(p))
            fr = fn(Path(p))
            if fr is None or fr.empty:
                continue
            if snap is not None and fdate is not None and fdate > snap:
                items_future.append((fdate, fr))
            else:
                items_le.append((fdate, fr))
        items = items_le
        if not items and items_future:
            items_future.sort(key=lambda t: t[0] if t[0] is not None else pd.Timestamp.min)
            items = [items_future[-1]]
        items.sort(key=lambda t: t[0] if t[0] is not None else pd.Timestamp.min)
        for i, (_, fr) in enumerate(items):
            fr["__order__"] = i
        return pd.concat([fr for _, fr in items], ignore_index=True) if items else pd.DataFrame()

    dog_all = _ordered_with_index(dogovor_paths, _per_file_dog)
    sprav_all = _ordered_with_index(sprav_paths, _per_file_sprav)

    if not dog_all.empty:
        dog_all = dog_all.sort_values("__order__")
        # Векторные built-in вместо python-лямбд (_last_valid/_last_nonempty): groupby.last()
        # пропускает NaN → «последнее непустое значение» в порядке снапшотов. Для contract_name
        # пустые строки маскируем в NaN, чтобы last() вернул последнее НЕпустое имя.
        cn = dog_all["contract_name"].astype("object")
        dog_all["contract_name"] = cn.where(cn.map(lambda v: isinstance(v, str) and v.strip() != ""), np.nan)
        dog_all = (
            dog_all.groupby(["project_id", "contractor_id"], dropna=False, as_index=False)
            .agg(
                project_name=("project_name", _first_nonempty),
                contractor_name=("contractor_name", _first_nonempty),
                contract_name=("contract_name", "last"),
                plan_workers=("plan_workers", "last"),
                plan_equipment=("plan_equipment", "last"),
            )
        )
        dog_all["contract_name"] = dog_all["contract_name"].where(dog_all["contract_name"].notna(), "")
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
        gd = dogovor.groupby(["project_id", "contractor_id"], dropna=False, as_index=False)
        # built-in sum(min_count=1) == float(np.nansum(s)) if any(notna) else None, но в разы быстрее.
        d = gd.agg(
            project_name=("project_name", _first_nonempty),
            contractor_name=("contractor_name", _first_nonempty),
            contract_name=("contract_name", lambda s: " · ".join(sorted({x for x in s if x}))),
        )
        d_sum = gd[["plan_workers", "plan_equipment"]].sum(min_count=1)
        d["plan_workers"] = d_sum["plan_workers"].to_numpy()
        d["plan_equipment"] = d_sum["plan_equipment"].to_numpy()
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
    for _, p in plan.iterrows():
        v = p.get(plan_col)
        if v is None or pd.isna(v):
            continue
        try:
            v = float(v)
        except Exception:
            continue
        proj_id = str(p.get("project_id", "")).strip()
        contr_id = str(p.get("contractor_id", "")).strip()
        proj_norm = normalize_name(p.get("project_name", ""))
        contr_norm = normalize_name(p.get("contractor_name", ""))
        contract_name = str(p.get("contract_name", "")).strip() if "contract_name" in p else ""
        if proj_id and contr_id:
            by_id[(proj_id, contr_id)] = by_id.get((proj_id, contr_id), 0.0) + v
        if proj_id and contr_norm:
            by_id_name[(proj_id, contr_norm)] = by_id_name.get((proj_id, contr_norm), 0.0) + v
        if proj_norm and contr_norm:
            by_norm_name[(proj_norm, contr_norm)] = by_norm_name.get((proj_norm, contr_norm), 0.0) + v
        if contract_name and proj_norm and contr_norm:
            existing = contract_by_norm.get((proj_norm, contr_norm), "")
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


def _gdrs_calendar_week_num(day: pd.Timestamp, month_lo: pd.Timestamp) -> int:
    d = int(pd.Timestamp(day).normalize().day)
    return min(max((d - 1) // 7 + 1, 1), 6)


def _gdrs_calendar_week_bucket_start(day: pd.Timestamp, month_lo: pd.Timestamp) -> pd.Timestamp:
    lo = pd.Timestamp(month_lo).normalize()
    start_day = (_gdrs_calendar_week_num(day, lo) - 1) * 7 + 1
    return pd.Timestamp(lo.year, lo.month, start_day)


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
) -> pd.DataFrame:
    """Факт по периодам + план из 1С на конец каждого периода; сетка по всему диапазону фильтра.

    plan_aggregate_loader: optional (snapshot_date) -> plan_df; для кэширования в Streamlit.
    """
    _load_plan = plan_aggregate_loader
    if _load_plan is None:
        def _load_plan(snap: pd.Timestamp) -> pd.DataFrame:
            return load_plan_aggregate(dogovor_paths, sprav_paths, snapshot_date=snap)
    f2 = gdrs_filter_fact_by_termination(fact_df, term_index)
    f2 = f2.copy()
    f2["date"] = pd.to_datetime(f2["date"])
    f2["bucket"] = gdrs_dynamics_assign_buckets(
        f2["date"], agg_kind, date_from=date_from, date_to=date_to
    )
    f2["_day"] = f2["date"].dt.normalize()

    daily_totals = (
        f2.groupby(["bucket", "_day"], as_index=False)["fact"]
        .sum()
    )
    agg = (
        daily_totals.groupby("bucket", as_index=False)["fact"]
        .mean()
        .rename(columns={"fact": "Факт"})
    )
    agg["Факт"] = pd.to_numeric(agg["Факт"], errors="coerce").fillna(0).round(0).astype(int)

    grid = pd.DataFrame({"bucket": gdrs_dynamics_bucket_starts(date_from, date_to, agg_kind)})
    if month_periods:
        _mset = set(month_periods)
        grid = grid[grid["bucket"].dt.to_period("M").isin(_mset)].reset_index(drop=True)
    dyn = grid.merge(agg[["bucket", "Факт"]], on="bucket", how="left")
    dyn["Факт"] = dyn["Факт"].fillna(0).astype(int)
    dyn["Период"] = dyn["bucket"].dt.strftime("%d.%m.%Y")

    # План и факт — среднее за день внутри периода группировки (день/неделя/месяц).
    plan_cache: dict = {}
    dyn_to = pd.Timestamp(date_to).normalize()
    dyn_from = pd.Timestamp(date_from).normalize()
    plans: list[int] = []
    for bkt in dyn["bucket"]:
        day_plan_vals: list[float] = []
        for day in _gdrs_bucket_calendar_days(bkt, agg_kind, dyn_from, dyn_to):
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
    """Один календарный месяц в фильтре — недели 1–6 считаем по дням месяца (1–7, 8–14, …)."""
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

    Для одного календарного месяца — «1-я неделя» = дни 1–7, «3-я» = 15–21 (как в 1С).
    Иначе — ISO-недели по факту в выборке.
    """
    dates = pd.to_datetime(dates, errors="coerce")
    if _gdrs_single_calendar_month(date_from, date_to):
        days = dates.dt.day
        week_idx = ((days - 1) // 7 + 1).clip(lower=1, upper=6).astype(int)
        days_per_week: dict[int, int] = {}
        for wi in sorted(week_idx.unique()):
            if int(wi) <= 0:
                continue
            mask = week_idx == wi
            days_per_week[int(wi)] = int(dates[mask].dt.normalize().nunique())
        return week_idx, days_per_week
    return _iso_week_groups(dates)


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
        month_last = int((lo + pd.offsets.MonthEnd(0)).day)
        start_day = (wn - 1) * 7 + 1
        if start_day > month_last:
            return None
        end_day = min(wn * 7, month_last)
        end = pd.Timestamp(lo.year, lo.month, end_day)
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


def gdrs_month_select_options(
    long_fact: pd.DataFrame,
    *,
    extra_paths: Optional[Iterable[Path | str]] = None,
) -> list[tuple[str, pd.Period]]:
    """Список (подпись «Апрель 2026», Period[M]) по датам факта СКУД.

    Месяцы из имён файлов (Dogovor/resursi) добавляются только если в long_fact
    нет ни одной даты — иначе в фильтре появлялись периоды с планом 1С, но без
    строк СКУД (например «Июнь 2026» из снапшота Dogovor при факте до мая).
    """
    period_set: set[pd.Period] = set()
    fact_periods: set[pd.Period] = set()
    if long_fact is not None and not long_fact.empty and "date" in long_fact.columns:
        for p in pd.to_datetime(long_fact["date"], errors="coerce").dt.to_period("M").dropna().unique():
            period_set.add(p)
            fact_periods.add(p)
    if extra_paths and not fact_periods:
        period_set |= gdrs_month_periods_from_paths(extra_paths)
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


def gdrs_contractor_filter_options(
    long_fact: pd.DataFrame,
    dogovor_paths: Iterable[Path | str],
    sprav_paths: Iterable[Path | str],
    *,
    projects: Optional[list[str]] = None,
    snapshot_date: Optional[pd.Timestamp] = None,
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
                names.add(s)
    try:
        plan = load_plan_aggregate(dogovor_paths, sprav_paths, snapshot_date=snapshot_date)
        plan = _filter_plan_slice(plan, projects, None)
        if plan is not None and not plan.empty:
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
    skud_sum = (
        fact.groupby(["project_name", "contractor_name"], dropna=False)["fact"]
        .sum()
        .reset_index(name="skud_sum")
    )
    wn = gdrs_agg_week_num(skud_agg)
    if wn is None:
        skud_sum["skud_val"] = skud_sum["skud_sum"] / max(1, total_days)
        return skud_sum[["project_name", "contractor_name", "skud_val"]]

    week_idx, days_per_week = _gdrs_week_groups(
        fact["date"], date_from=date_from, date_to=date_to
    )
    fact = fact.assign(week=week_idx)
    week_sum = (
        fact.groupby(["project_name", "contractor_name", "week"], dropna=False)["fact"]
        .sum()
        .reset_index(name="daily_sum")
    )
    week_sum["skud_val"] = week_sum.apply(
        lambda r: r["daily_sum"] / max(1, days_per_week.get(int(r["week"]), 1)), axis=1
    )
    week_only = week_sum[week_sum["week"] == wn][["project_name", "contractor_name", "skud_val"]]
    return skud_sum[["project_name", "contractor_name"]].merge(
        week_only, on=["project_name", "contractor_name"], how="left"
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
    """Подписи недель 1–6 в порядке периода с диапазоном дат (для шапки таблицы)."""
    _default = [f"{i} нед" for i in range(1, 7)]
    dts = pd.to_datetime(dates, errors="coerce").dropna()
    if dts.empty:
        return _default
    lo = pd.Timestamp(date_from).normalize()
    hi = pd.Timestamp(date_to).normalize()
    dts = dts[(dts >= lo) & (dts <= hi)]
    if dts.empty:
        return _default
    week_idx, _ = _gdrs_week_groups(dts, date_from=lo, date_to=hi)
    labels: list[str] = []
    for wi in range(1, 7):
        mask = week_idx == wi
        if not mask.any():
            end = gdrs_week_period_end(lo, hi, wi)
            if end is not None and pd.notna(end):
                labels.append(f"{wi} нед ({end.strftime('%d.%m')})")
            else:
                labels.append(f"{wi} нед")
            continue
        sub = dts[mask]
        labels.append(f"{wi} нед ({sub.min().strftime('%d.%m')}-{sub.max().strftime('%d.%m')})")
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

    plan_col = "plan_workers" if vid.casefold() == "рабочие" else "plan_equipment"
    by_id, by_id_name, by_norm = _build_plan_lookup(plan, plan_col)
    _plan_snap = pd.Timestamp(plan_as_of).normalize() if plan_as_of is not None and pd.notna(plan_as_of) else (
        pd.Timestamp(date_to).normalize() if date_to is not None and pd.notna(date_to) else None
    )

    id_pick = pd.DataFrame(columns=["project_name", "contractor_name", "project_id", "contractor_id"])
    if fact is not None and not fact.empty:
        fact = fact.copy()
        fact["date"] = pd.to_datetime(fact["date"])
        week_idx, days_per_week = _gdrs_week_groups(
            fact["date"], date_from=date_from, date_to=date_to
        )
        fact["week"] = week_idx

        id_pick = (
            fact.groupby(["project_name", "contractor_name"], dropna=False)
            .agg(
                project_id=("project_id", lambda s: next((x for x in s.astype(str) if x.strip()), "")),
                contractor_id=("contractor_id", lambda s: next((x for x in s.astype(str) if x.strip()), "")),
            )
            .reset_index()
        )

        week_sum = (
            fact.groupby(["project_name", "contractor_name", "week"], dropna=False)["fact"]
            .sum()
            .reset_index(name="daily_sum")
        )
        week_sum["weekly_avg"] = week_sum.apply(
            lambda r: r["daily_sum"] / max(1, days_per_week.get(int(r["week"]), 1)), axis=1
        )

        pivot = week_sum.pivot_table(
            index=["project_name", "contractor_name"],
            columns="week",
            values="weekly_avg",
            aggfunc="sum",
            fill_value=0.0,
        ).reset_index()
    else:
        pivot = pd.DataFrame(columns=["project_name", "contractor_name"])

    for w in (1, 2, 3, 4, 5, 6):
        if w not in pivot.columns:
            pivot[w] = 0.0
    if "project_name" not in pivot.columns:
        pivot["project_name"] = []
        pivot["contractor_name"] = []
    pivot.rename(columns={1: "w1", 2: "w2", 3: "w3", 4: "w4", 5: "w5", 6: "w6"}, inplace=True)

    plan_pairs_df = _filter_plan_slice(plan, projects, contractors)
    if plan_pairs_df is not None and not plan_pairs_df.empty:
        plan_pairs_df = plan_pairs_df.copy()
        try:
            from dashboards.project_labels import apply_unified_project_column

            plan_pairs_df = apply_unified_project_column(plan_pairs_df, "project_name")
        except Exception:
            pass
        plan_pairs_df["_plan_val"] = pd.to_numeric(plan_pairs_df[plan_col], errors="coerce").fillna(0.0)
        plan_pairs_df = plan_pairs_df[plan_pairs_df["_plan_val"] > 0]
        if not plan_pairs_df.empty:
            extra_pairs = plan_pairs_df[["project_name", "contractor_name"]].drop_duplicates()
            pivot_pairs = pivot[["project_name", "contractor_name"]].drop_duplicates()
            all_pairs = pd.concat([pivot_pairs, extra_pairs], ignore_index=True).drop_duplicates()
            pivot = all_pairs.merge(pivot, on=["project_name", "contractor_name"], how="left")
            for wc in ("w1", "w2", "w3", "w4", "w5", "w6"):
                if wc in pivot.columns:
                    pivot[wc] = pd.to_numeric(pivot[wc], errors="coerce").fillna(0.0)
                else:
                    pivot[wc] = 0.0
            plan_ids = (
                plan_pairs_df.groupby(["project_name", "contractor_name"], dropna=False)
                .agg(
                    project_id=("project_id", _first_nonempty),
                    contractor_id=("contractor_id", _first_nonempty),
                )
                .reset_index()
            )
            id_pick = pd.concat([id_pick, plan_ids], ignore_index=True).drop_duplicates(
                subset=["project_name", "contractor_name"], keep="first"
            )

    if fact is not None and not fact.empty:
        skud_per = _skud_agg_per_pair(
            fact, skud_agg, date_from=date_from, date_to=date_to
        ).rename(columns={"skud_val": "skud_avg"})
    else:
        skud_per = pivot[["project_name", "contractor_name"]].copy()
        skud_per["skud_val"] = 0.0

    rows = pivot.merge(skud_per, on=["project_name", "contractor_name"], how="left")
    if "skud_avg" not in rows.columns:
        if "skud_val" in rows.columns:
            rows["skud_avg"] = rows["skud_val"]
        else:
            rows["skud_avg"] = 0.0
    if id_pick is not None and not id_pick.empty:
        rows = rows.merge(id_pick, on=["project_name", "contractor_name"], how="left")
    else:
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
                _month_plan_lu_cache[_snap] = _build_plan_lookup(
                    plan_aggregate_loader(_snap), plan_col
                )

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
    _weekly_plan_lu: dict[int, tuple] = {}
    if _show_week_cols and weekly_plan_by_week:
        for _wn, _wp_df in weekly_plan_by_week.items():
            if _wp_df is not None and not _wp_df.empty:
                _weekly_plan_lu[int(_wn)] = _build_plan_lookup(_wp_df, plan_col)
    for w in ("w1", "w2", "w3", "w4", "w5", "w6"):
        rows[w] = rows[w].fillna(0.0).round(0)
    for wi, pk in enumerate(("p1", "p2", "p3", "p4", "p5", "p6"), start=1):
        if _show_week_cols and wi in _weekly_plan_lu:
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
        else:
            rows[pk] = rows["plan"].fillna(0.0).round(0)
    rows["row_kind"] = "row"

    rows = gdrs_apply_kontr_plan_gate(rows, kontr_index)

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


def gdrs_delta_pct_cell_bg_style(raw) -> str:
    """Фон ячейки «Отклонение %» (факт − план в %): >0 зелёный, <0 красный, 0 нейтральный."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return ""
    try:
        v = float(raw)
    except Exception:
        return ""
    if v > 0:
        return "background-color:rgba(70,214,138,0.32) !important;"
    if v < 0:
        t = min(max(-v, 0.0), 100.0) / 100.0
        alpha = 0.24 + 0.36 * t
        return f"background-color:rgba(255,84,84,{alpha:.3f}) !important;"
    return "background-color:rgba(136,153,170,0.18) !important;"


def gdrs_deviation_cell_bg_style(raw) -> str:
    """Фон ячейки «Отклонение» (факт − план): >0 зелёный, <0 красный, 0 нейтральный."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return ""
    try:
        v = float(raw)
    except Exception:
        return ""
    if v > 0:
        return "background-color:rgba(70,214,138,0.32) !important;"
    if v < 0:
        t = min(max(-v, 0.0), 100.0) / 100.0
        alpha = 0.24 + 0.36 * t
        return f"background-color:rgba(255,84,84,{alpha:.3f}) !important;"
    return "background-color:rgba(136,153,170,0.18) !important;"


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
        delta_bg_style = gdrs_delta_pct_cell_bg_style

    wk_labels = list(week_labels or GDRS_WEEK_LABELS)
    if len(wk_labels) < 6:
        wk_labels = wk_labels + list(GDRS_WEEK_LABELS[len(wk_labels):])
    wk_labels = wk_labels[:6]
    wk_n = len(wk_labels)
    plan_keys = list(GDRS_WEEK_PLAN_KEYS)
    skud_keys = list(GDRS_WEEK_SKUD_KEYS)
    if show_week_columns:
        show_cols = list(fixed_cols) + plan_keys + skud_keys + [delta_col]
    else:
        show_cols = list(fixed_cols) + [delta_col]
    ncols = len(show_cols)
    wid = wrap_id or ("gdrs_mtx_" + str(abs(id(view))))
    n_fixed = len(fixed_cols)
    if show_week_columns:
        i_plan0 = n_fixed
        i_plan1 = n_fixed + wk_n - 1
        i_skud0 = n_fixed + wk_n
        i_skud1 = n_fixed + 2 * wk_n - 1
        i_delta = n_fixed + 2 * wk_n
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
        return ""

    def _th_metric_cls(col: str) -> str:
        if col == "План":
            return "gdrs-col-plan"
        if col == "СКУД":
            return "gdrs-col-skud"
        if col == "Отклонение":
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
                    dev_bg = gdrs_deviation_cell_bg_style(fv)
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
        for ci, col in enumerate(fixed_cols):
            hmc = _th_metric_cls(col)
            hcls = _border_cls(ci) + (f" {hmc}" if hmc else "")
            if col not in text_cols:
                hcls += " gdrs-col-equal"
            _sort = ' data-gdrs-sort="1" data-sort-label="' + html_module.escape(col) + '"' if col in ("Контрагент", "Вид работ", "План", "СКУД", "Отклонение") else ""
            thead_parts.append(
                f'<th rowspan="2" class="{hcls.strip()}"{_sort}>{html_module.escape(col)}</th>'
            )
        thead_parts.append(
            f'<th colspan="{wk_n}" class="gdrs-h-plan-group gdrs-sep-l-strong gdrs-sep-r-strong">План</th>'
        )
        thead_parts.append(
            f'<th colspan="{wk_n}" class="gdrs-h-skud-group gdrs-sep-l-strong gdrs-sep-r-strong">СКУД</th>'
        )
        delta_title = "Отклонение %" if delta_col in ("Дельта (%)", "Дельта %", "Δ %", "Δ%") else delta_col
        thead_parts.append(
            f'<th rowspan="2" class="{_border_cls(i_delta)} gdrs-col-equal">{html_module.escape(delta_title)}</th>'
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
            _sort = ' data-gdrs-sort="1" data-sort-label="' + html_module.escape(col) + '"' if col in ("Контрагент", "Вид работ", "План", "СКУД", "Отклонение") else ""
            thead_parts.append(
                f'<th class="{hcls.strip()}"{_sort}>{html_module.escape(col)}</th>'
            )
        thead_parts.append("</tr>")

    body = "".join(_row_html(r) for _, r in view.iterrows())
    n_body_rows = len(view)
    from dashboards.gdrs_theme import get_gdrs_theme, gdrs_matrix_table_css

    _th = get_gdrs_theme(theme)
    _wrap_cls = "gdrs-table-wrap gdrs-light-table" if _th.name == "light" else "gdrs-table-wrap"
    return (
f'<div id="{wid}" class="{_wrap_cls}">'
        + gdrs_matrix_table_css(wid, _th)
        + '<table class="gdrs-matrix-table bi-sortable-table bi-sort-click-only"><thead>'
        + "".join(thead_parts)
        + f'</thead><tbody data-bi-rows="{n_body_rows}">'
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
def _gdrs_cached_load_resursi(paths_sig: tuple) -> pd.DataFrame:
    from pathlib import Path as _P

    return load_resursi_files([_P(p[0]) for p in paths_sig])


@st.cache_data(show_spinner=False, ttl=3600)
def _gdrs_cached_plan_aggregate(
    dog_sig: tuple,
    spr_sig: tuple,
    snapshot_iso: str,
) -> pd.DataFrame:
    from pathlib import Path as _P

    snap = pd.Timestamp(snapshot_iso) if snapshot_iso else None
    return load_plan_aggregate(
        [_P(p[0]) for p in dog_sig],
        [_P(p[0]) for p in spr_sig],
        snapshot_date=snap,
    )


@st.cache_data(show_spinner=False, ttl=3600)
def _gdrs_cached_dannye_maps(dannye_sig: tuple):
    from pathlib import Path as _P

    return load_1c_dannye_article_maps([_P(p[0]) for p in dannye_sig])


def _gdrs_plan_loader(dog_sig: tuple, spr_sig: tuple):
    def _load(snap: pd.Timestamp) -> pd.DataFrame:
        iso = pd.Timestamp(snap).normalize().isoformat()
        return _gdrs_cached_plan_aggregate(dog_sig, spr_sig, iso)

    return _load


def warm_gdrs_disk_caches() -> None:
    """Прогрев CSV/JSON-кэша ГДРС до отрисовки отчёта."""
    try:
        root = Path(__file__).resolve().parent.parent
        web_dir = root / "web"
        ai_dir = web_dir / "AI"
        resursi_files = sorted(ai_dir.glob("*resursi*.csv"))
        if not resursi_files:
            resursi_files = sorted(web_dir.glob("*resursi*.csv"))
        if resursi_files:
            _gdrs_cached_load_resursi(_gdrs_paths_mtime_sig(resursi_files))
        dannye_paths = sorted(web_dir.glob("*dannye*.json"))
        if dannye_paths:
            _gdrs_cached_dannye_maps(_gdrs_paths_mtime_sig(dannye_paths))
    except Exception:
        pass
