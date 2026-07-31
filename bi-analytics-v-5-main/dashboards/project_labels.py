"""
Единые подписи проектов для фильтров, таблиц и выгрузок (MSP / 1С / СКУД).

Использует MSP_PROJECT_NAME_MAP и правила из dev_projects_tz_matrix
(«Дмитровский-1», «Есипово-5» из 1с_*_Projekts.json вместо лат. slug / римских V).

Для новых msp_<latin_slug>_*.csv без ручной карты: транслит slug → сопоставление
с наименованиями из 1с_*_Projekts.json (zhukovsky1 → Жуковский).
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import List, Optional, Set, Tuple

import pandas as pd

from config import MSP_PROJECT_FILTER_EXCLUDE_NAMES

# Многосимвольные замены латиницы (GOST-подобно для slug MSP) — до посимвольных.
_LATIN_MULTI = (
    ("shch", "щ"),
    ("sch", "щ"),
    ("skiy", "ский"),
    ("skij", "ский"),
    ("sky", "ский"),  # zhukovsky → жуковский (не «жуковски»)
    ("cki", "цки"),
    ("yo", "ё"),
    ("zh", "ж"),
    ("kh", "х"),
    ("ts", "ц"),
    ("ch", "ч"),
    ("sh", "ш"),
    ("yu", "ю"),
    ("ya", "я"),
    ("ye", "е"),
    ("iy", "ий"),
    ("yy", "ый"),
)
_LATIN_ONE = {
    "a": "а",
    "b": "б",
    "c": "к",
    "d": "д",
    "e": "е",
    "f": "ф",
    "g": "г",
    "h": "х",
    "i": "и",
    "j": "й",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "q": "к",
    "r": "р",
    "s": "с",
    "t": "т",
    "u": "у",
    "v": "в",
    "w": "в",
    "x": "кс",
    "y": "и",
    "z": "з",
}


def project_name_is_latin_slug(raw: object) -> bool:
    """True, если имя похоже на латинский slug файла MSP (Zhukovsky1), а не на русское."""
    s = _clean_raw_name(raw)
    if not s:
        return False
    if re.search(r"[а-яё]", s, flags=re.IGNORECASE):
        return False
    return bool(re.search(r"[a-z]", s, flags=re.IGNORECASE))


def latin_msp_slug_to_cyrillic(raw: object) -> str:
    """zhukovsky1 / Novorizhskiy → жуковский1 / новорижский (грубый транслит для матча)."""
    s = _clean_raw_name(raw).lower().replace(" ", "").replace("-", "").replace("_", "")
    if not s:
        return ""
    out: list[str] = []
    i = 0
    while i < len(s):
        if s[i].isdigit():
            out.append(s[i])
            i += 1
            continue
        hit = False
        for lat, cyr in _LATIN_MULTI:
            if s.startswith(lat, i):
                out.append(cyr)
                i += len(lat)
                hit = True
                break
        if hit:
            continue
        ch = s[i]
        out.append(_LATIN_ONE.get(ch, ch))
        i += 1
    return "".join(out)


def _projekts_russian_names() -> List[str]:
    """Все русские наименования проектов из БД / web/*_Projekts.json."""
    names: list[str] = []
    seen: set[str] = set()

    def _add(raw: object) -> None:
        t = _clean_raw_name(raw)
        if not t or t.lower() in seen:
            return
        if not re.search(r"[а-яё]", t, flags=re.IGNORECASE):
            return
        seen.add(t.lower())
        names.append(t)

    try:
        from web_db_read import load_project_id_to_name_lookup

        for v in load_project_id_to_name_lookup().values():
            _add(v)
    except Exception:
        pass
    # Всегда дополняем из web/*_Projekts.json и карты: в БД справочник
    # может быть неполным / без поля «Наименование».
    try:
        import json
        from pathlib import Path

        roots = [
            Path("web"),
            Path(__file__).resolve().parent.parent / "web",
        ]
        paths: list[Path] = []
        for root in roots:
            if not root.is_dir():
                continue
            paths.extend(root.glob("*_Projekts.json"))
            paths.extend(root.glob("*Projekts.json"))
        for p in sorted(set(paths))[-6:]:
            try:
                with open(p, encoding="utf-8") as f:
                    rows = json.load(f)
            except Exception:
                continue
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                _add(
                    row.get("Наименование_Проекта")
                    or row.get("Наименование проекта")
                    or row.get("Наименование")
                    or row.get("Проект")
                )
    except Exception:
        pass
    try:
        from config import MSP_PROJECT_NAME_MAP as M

        for v in M.values():
            _add(v)
    except Exception:
        pass
    return names


def _norm_compact(s: str) -> str:
    t = (
        str(s or "")
        .strip()
        .lower()
        .replace("ё", "е")
        .replace(" ", "")
        .replace("-", "")
        .replace("_", "")
        .replace(".", "")
    )
    return t


def match_latin_slug_to_russian_project(raw: object) -> Optional[str]:
    """
    Авто: латинский slug MSP → русское имя из 1С Projekts.

    zhukovsky1 → Жуковский; esipovo5 → Есипово-5.
    Предпочитает короткое точное совпадение базы имени, не «ИС Жуковский ЦПК 1».
    """
    if not project_name_is_latin_slug(raw):
        return None
    cyr = latin_msp_slug_to_cyrillic(raw)
    if not cyr:
        return None
    cyr_base = re.sub(r"\d+$", "", cyr)
    digit_tail = ""
    m_dig = re.search(r"(\d+)$", cyr)
    if m_dig:
        digit_tail = m_dig.group(1)

    candidates = _projekts_russian_names()
    if not candidates:
        return None

    scored: list[Tuple[tuple, str]] = []
    for name in candidates:
        nk = _norm_compact(name)
        if not nk:
            continue
        # Убрать служебные префиксы для сравнения базы
        nk_core = re.sub(r"^(ис|мсп|проект)", "", nk)
        score: Optional[tuple] = None
        if digit_tail and (
            nk == cyr
            or nk == cyr_base + digit_tail
            or nk_core == cyr
            or nk_core == cyr_base + digit_tail
        ):
            # Есипово-5 ↔ esipovo5
            score = (0, len(name), name)
        elif cyr_base and (nk == cyr_base or nk_core == cyr_base):
            # Жуковский ↔ zhukovsky1
            score = (1, len(name), name)
        elif cyr_base and len(cyr_base) >= 4 and (
            nk.startswith(cyr_base) or cyr_base in nk or nk_core.startswith(cyr_base)
        ):
            # длинные «ИС Жуковский…» — запасной вариант
            score = (2, len(name), name)
        if score is not None:
            scored.append((score, name))

    if not scored:
        return None
    scored.sort(key=lambda x: (x[0][0], x[0][1]))
    return scored[0][1]

_ROMAN_PROJECT_TAIL = {
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4,
    "V": 5,
    "VI": 6,
    "VII": 7,
    "VIII": 8,
    "IX": 9,
    "X": 10,
}

_PROJECT_CHILD_SUFFIX_RE = re.compile(r"^(\d{1,4}|[IVX]{1,4})$", re.I)


def _project_name_fusion_base(s: str) -> str:
    if not s:
        return ""
    t = (
        str(s)
        .replace("\xa0", " ")
        .replace("\u200b", "")
        .replace("\ufeff", "")
        .replace("-", " ")
    )
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return ""
    m_num = re.fullmatch(r"(.+?)\s+(\d{1,4})\s*", t, flags=re.I)
    if m_num:
        return f"{m_num.group(1).strip()} {int(m_num.group(2))}"
    m_rom = re.fullmatch(r"(.+?)\s+([IVX]{1,4})\s*", t, flags=re.I)
    if m_rom:
        rom = m_rom.group(2).upper()
        n = _ROMAN_PROJECT_TAIL.get(rom)
        if n is not None:
            return f"{m_rom.group(1).strip()} {n}"
    return t


def project_filter_norm_key(val) -> str:
    """Ключ сравнения названий проекта (пробел/дефис, римские → арабские)."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = (
        str(val)
        .replace("\xa0", " ")
        .replace("\u200b", "")
        .replace("\ufeff", "")
        .strip()
    )
    while "  " in s:
        s = s.replace("  ", " ")
    s = _project_name_fusion_base(s)
    if s:
        try:
            s2 = re.sub(r"([А-Яа-яЁёA-Za-z])(\d{1,4})$", r"\1 \2", s)
        except re.error:
            s2 = s
        if s2 != s:
            s = re.sub(r"\s+", " ", str(s2)).strip()
    sl = s.casefold()
    if sl in ("", "nan", "none", "nat"):
        return ""
    return sl


def _project_norm_key_matches_msp_keys(row_key: str, msp_keys: Set[str]) -> bool:
    if not msp_keys:
        return True
    if not row_key:
        return False
    rk = str(row_key).strip()
    try:
        rk2 = re.sub(r"([а-яёa-z])(\d{1,4})$", r"\1 \2", rk)
        if rk2 != rk:
            rk = re.sub(r"\s+", " ", rk2).strip()
    except re.error:
        pass
    if rk in msp_keys:
        return True
    for k in msp_keys:
        if not k:
            continue
        pref = k + " "
        if rk.startswith(pref):
            rest = rk[len(pref) :]
            if rest and _PROJECT_CHILD_SUFFIX_RE.fullmatch(rest):
                return True
    for k in msp_keys:
        if not k:
            continue
        pref = rk + " "
        if rk and k.startswith(pref):
            rest = k[len(pref) :]
            if rest and _PROJECT_CHILD_SUFFIX_RE.fullmatch(rest):
                return True
    return False


def _clean_raw_name(raw: object) -> str:
    s = (
        str(raw)
        .replace("\xa0", " ")
        .replace("\u200b", "")
        .replace("\ufeff", "")
        .strip()
    )
    while "  " in s:
        s = s.replace("  ", " ")
    return s


def unified_project_display_label(raw: object) -> str:
    """Каноническая подпись проекта для UI и таблиц."""
    s = _clean_raw_name(raw)
    if not s or s.lower() in ("nan", "none", "nat"):
        return ""
    try:
        from dashboards.dev_projects_tz_matrix import (
            _control_points_project_group_key,
            _control_points_project_label,
        )

        gk = _control_points_project_group_key(s)
        return str(_control_points_project_label(gk, [s])).strip() or s
    except Exception:
        lk = s.lower().replace(" ", "")
        try:
            from config import MSP_PROJECT_NAME_MAP as M

            if lk in M:
                return str(M[lk]).strip()
        except Exception:
            pass
        return s


def project_labels_for_filter(
    series: pd.Series, *, apply_exclude_names: bool = True
) -> List[str]:
    """Уникальные подписи для select/multiselect: один пункт на логический проект."""
    if series is None or getattr(series, "empty", True):
        return []
    try:
        from dashboards.dev_projects_tz_matrix import _control_points_project_group_key
    except Exception:
        _control_points_project_group_key = None  # type: ignore[assignment]

    by_gk: dict[str, list[str]] = defaultdict(list)
    for raw in series.dropna().unique():
        s = _clean_raw_name(raw)
        if not s or s.lower() in ("nan", "none", "nat"):
            continue
        if _control_points_project_group_key is not None:
            by_gk[str(_control_points_project_group_key(s))].append(s)
        else:
            by_gk[project_filter_norm_key(s) or s].append(s)

    def _raws_for_group_label(raws: list[str]) -> list[str]:
        """Исключать дубли написания только если в группе есть другой вариант имени."""
        raws_u = sorted(set(raws))
        if not apply_exclude_names or len(raws_u) <= 1:
            return raws_u
        kept = [r for r in raws_u if r not in MSP_PROJECT_FILTER_EXCLUDE_NAMES]
        return kept if kept else raws_u

    labels: list[str] = []
    if _control_points_project_group_key is not None:
        try:
            from dashboards.dev_projects_tz_matrix import _control_points_project_label

            for gk, raws in by_gk.items():
                use_raws = _raws_for_group_label(raws)
                lab = str(_control_points_project_label(gk, use_raws)).strip()
                if lab:
                    labels.append(lab)
        except Exception:
            for raws in by_gk.values():
                use_raws = _raws_for_group_label(raws)
                labels.append(unified_project_display_label(use_raws[0]))
    else:
        for raws in by_gk.values():
            use_raws = _raws_for_group_label(raws)
            labels.append(unified_project_display_label(use_raws[0]))
    out: list[str] = []
    for lab in labels:
        s = str(lab).strip()
        if not s:
            continue
        if s in MSP_PROJECT_FILTER_EXCLUDE_NAMES:
            lk = s.lower().replace(" ", "").replace("-", "")
            if lk.startswith("дмитров"):
                s = "Дмитровский"
            else:
                continue
        out.append(s)
    return sorted(set(out), key=lambda x: x.casefold())


def apply_unified_project_column(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Подменяет значения колонки проекта на единые подписи."""
    if df is None or getattr(df, "empty", True) or col not in df.columns:
        return df
    out = df.copy()
    # Считаем подпись один раз на уникальное значение: unified_project_display_label
    # дорогая (нормализация + справочник), а строк в таблицах десятки/сотни тысяч
    # при ~сотне уникальных проектов. Прямой .map по всем строкам давал десятки
    # секунд на тяжёлых дашбордах («Причины отклонений» и т.п.).
    _uniq = out[col].dropna().unique()
    _label_map = {v: unified_project_display_label(v) for v in _uniq}
    out[col] = out[col].map(
        lambda z: _label_map.get(z, z)
        if z is not None and not (isinstance(z, float) and pd.isna(z))
        else z
    )
    return out


def filter_dataframe_by_project_labels(
    df: pd.DataFrame,
    selected_labels: list[str],
    *,
    col: str = "project_name",
) -> pd.DataFrame:
    """Оставить строки выбранных проектов (сопоставление по norm-key)."""
    if df is None or getattr(df, "empty", True) or col not in df.columns:
        return df
    labels = [str(x).strip() for x in (selected_labels or []) if str(x).strip()]
    if not labels:
        return df.copy()
    keys = {project_filter_norm_key(x) for x in labels}
    keys.discard("")
    if not keys:
        return df.copy()
    rk = df[col].map(project_filter_norm_key)
    return df[rk.map(lambda k: _project_norm_key_matches_msp_keys(k, keys))].copy()
