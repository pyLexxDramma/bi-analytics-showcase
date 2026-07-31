# -*- coding: utf-8 -*-
"""
Матрица «Девелоперские проекты» по ТЗ (правки): строки-показатели; у вех — План / Факт / Откл.,
у блока «ПРЕДПИСАНИЯ» — Всего / Критические / Критические просроченные предписания.
Источники: MSP (canonical колонки после web_loader), project_data (БДДС), tessa_tasks_data.
"""
from __future__ import annotations

import base64
import copy
import html as html_module
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from utils import outline_level_numeric

from settings import SETTING_KEYS

DEV_MATRIX_JSON_KEY = "developer_projects_matrix_json"


def _dearrow_object_columns(df: "pd.DataFrame") -> "pd.DataFrame":
    """pandas 3.0: строковые колонки по умолчанию arrow-backed (dtype ``str``).

    Матрица «Девелоперские проекты» делает тысячи поэлементных ``.at[]``-записей
    и масок на широком MSP-кадре. На arrow каждая scalar-запись дробит
    ChunkedArray → последующие ``take`` деградируют (в профиле — десятки секунд
    в ``pyarrow.compute.take``). Перевод строковых колонок в numpy ``object``
    делает scalar set ~8x быстрее и убирает фрагментацию. Семантика ``.str`` /
    масок / сравнения сохраняется (проверено), меняется только бэкенд хранения.

    Конвертация дешёвая и идемпотентная: если arrow-строк нет — кадр возвращается
    как есть.
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

# Подколонки вехи «ПРЕДПИСАНИЯ» (ТЗ 04.05): без План/Факт/Откл.
_DEV_MATRIX_PREDS_SUBCOLS: Dict[str, str] = {
    "plan": "Всего предписаний",
    "fact": "Критические предписания",
    "otkl": "Критические просроченные предписания",
}

# Стабильные ключи строк матрицы (порядок = порядок колонок отчёта), для titles/matches в JSON.
_DEV_MATRIX_ROW_KEYS: List[str] = [
    "inv_arenda_zu",
    "inv_gotovy_produkt",
    "inv_gpzu",
    "life_ekspertiza_st_p",
    "life_komanda_rp",
    "life_rs",
    "life_rd_1var",
    "life_fin_ds",
    "life_tessa_preds",
    "life_ird_elvo",
    "life_ird_udc",
    "life_pos_1var",
    "life_fin_smr_start",
    "life_smr_start",
    "life_tech_pri",
    "life_zos",
    "life_rv",
    "life_pravo1",
    "life_vykup_zu",
    "life_pravo2",
    "life_boxes_res",
]


def load_developer_projects_matrix_prefs() -> Dict[str, Any]:
    """Подписи План/Факт/Откл., умолчание вертикальных дат, заголовки вех и patch match-критериев к MSP."""
    try:
        from settings import get_setting

        raw = (get_setting(DEV_MATRIX_JSON_KEY) or "").strip()
        base: Dict[str, Any] = {
            "subcolumns": {"plan": "План", "fact": "Факт", "otkl": "Откл."},
            "default_vertical_dates": False,
            "titles": {},
            "matches": {},
        }
        if not raw:
            return base
        data = json.loads(raw)
        if not isinstance(data, dict):
            return base
        sc = data.get("subcolumns")
        if isinstance(sc, dict):
            for k in ("plan", "fact", "otkl"):
                v = sc.get(k)
                if isinstance(v, str) and v.strip():
                    base["subcolumns"][k] = v.strip()
        dv = data.get("default_vertical_dates")
        if isinstance(dv, bool):
            base["default_vertical_dates"] = dv
        tt = data.get("titles")
        if isinstance(tt, dict):
            base["titles"] = {
                str(a).strip(): str(b).strip() for a, b in tt.items() if str(a).strip()
            }
        mt = data.get("matches")
        if isinstance(mt, dict):
            base["matches"] = mt
        return base
    except Exception:
        return {
            "subcolumns": {"plan": "План", "fact": "Факт", "otkl": "Откл."},
            "default_vertical_dates": False,
            "titles": {},
            "matches": {},
        }


def developer_projects_matrix_default_prefs_json() -> str:
    return json.dumps(
        {
            "subcolumns": {"plan": "План", "fact": "Факт", "otkl": "Откл."},
            "default_vertical_dates": False,
            "titles": {},
            "matches": {},
        },
        ensure_ascii=False,
        indent=2,
    )


def save_developer_projects_matrix_prefs_json(json_str: str, updated_by: str) -> Tuple[bool, str]:
    """Сохранение JSON; пустая строка — сброс подписей/маппинга."""
    try:
        from settings import set_setting

        s = (json_str or "").strip()
        desc = ""
        try:
            desc = str(SETTING_KEYS.get(DEV_MATRIX_JSON_KEY, ""))
        except Exception:
            desc = ""
        if not s:
            set_setting(
                DEV_MATRIX_JSON_KEY,
                "",
                description=desc,
                updated_by=updated_by,
            )
            return True, "Сброшено на правила из кода / пустые переопределения."
        data = json.loads(s)
        if not isinstance(data, dict):
            return False, "Ожидается JSON-объект (subcolumns, default_vertical_dates, titles, matches)."
        out: Dict[str, Any] = {
            "subcolumns": {"plan": "План", "fact": "Факт", "otkl": "Откл."},
            "default_vertical_dates": bool(data.get("default_vertical_dates", False)),
            "titles": {},
            "matches": {},
        }
        sc = data.get("subcolumns")
        if isinstance(sc, dict):
            for k in ("plan", "fact", "otkl"):
                vv = sc.get(k)
                if isinstance(vv, str) and vv.strip():
                    out["subcolumns"][k] = vv.strip()
        tt = data.get("titles")
        if isinstance(tt, dict):
            for a, b in tt.items():
                ak = str(a).strip()
                if ak:
                    out["titles"][ak] = str(b).strip()
        mt = data.get("matches")
        if isinstance(mt, dict):
            for a, patch in mt.items():
                ak = str(a).strip()
                if ak and isinstance(patch, dict):
                    out["matches"][ak] = patch
        set_setting(
            DEV_MATRIX_JSON_KEY,
            json.dumps(out, ensure_ascii=False, separators=(",", ":")),
            description=desc,
            updated_by=updated_by,
        )
        return True, "Сохранено."
    except json.JSONDecodeError as e:
        return False, f"Ошибка JSON: {e}"
    except Exception as e:
        return False, str(e)[:500]


def _guess_msp_project_slug_for_loader(df: pd.DataFrame) -> str:
    """
    Ключ для web_loader._apply_msp_column_mapping (MSP_PROJECT_NAME_MAP / имя файла):
    по имени файла msp_<slug>_… при наличии в attrs, иначе из первой ячейки колонки проекта.
    """
    try:
        fn = str(df.attrs.get("file_name") or "").strip()
    except Exception:
        fn = ""
    if fn:
        base = fn.replace("\\", "/").split("/")[-1]
        low = base.lower()
        if low.startswith("msp_") and low.endswith(".csv"):
            stem = base[:-4]
            parts = stem.split("_")
            if len(parts) >= 2 and parts[1].strip():
                return parts[1].strip().lower()
    try:
        from config import MSP_PROJECT_NAME_MAP as M
    except Exception:
        M = {}
    pc = _find_col(df, ["project name", "Проект", "Project", "проект"])
    if not pc or pc not in df.columns:
        return ""
    s = df[pc].dropna().astype(str).str.strip()
    if s.empty:
        return ""
    raw = str(s.iloc[0]).strip()
    lk = raw.lower().replace(" ", "").replace("\xa0", "")
    if lk in M:
        return str(lk)
    for k, v in M.items():
        if str(v).strip().lower() == raw.lower():
            return str(k).strip().lower()
    return lk


def _needs_msp_web_loader_normalize(df: pd.DataFrame) -> bool:
    """Русская выгрузка без прохода через web_loader: нет canonical-колонок дат/задачи/уровня."""
    if df is None or getattr(df, "empty", True):
        return False
    cl = {str(c).strip().lower() for c in df.columns}
    if "plan end" not in cl and _find_col(df, ["Окончание", "План окончание", "План_окончание"]) is not None:
        return True
    if "task name" not in cl and _find_col(df, ["Название", "Название задачи", "Task Name"]) is not None:
        return True
    if "level" not in cl and _find_col(df, ["Уровень"]) is not None:
        return True
    if "base end" not in cl and _find_col(df, ["Базовое_окончание", "Базовое окончание"]) is not None:
        return True
    return False


def ensure_msp_df_for_dev_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """
    Единая схема MSP для матрицы: canonical-колонки, даты, section из дерева (как при load_all_from_web).
    """
    if df is None or getattr(df, "empty", True):
        return df
    out = df.copy()
    if _needs_msp_web_loader_normalize(out):
        try:
            from web_loader import _apply_msp_column_mapping

            slug = _guess_msp_project_slug_for_loader(out)
            out = _apply_msp_column_mapping(out, slug)
        except Exception:
            out = _control_points_prepare_msp_dates(out)
    else:
        out = _control_points_prepare_msp_dates(out)
    try:
        from web_loader import _coerce_msp_project_name_from_file_if_needed
        from config import MSP_PROJECT_NAME_MAP

        slug = (_guess_msp_project_slug_for_loader(out) or "").strip().lower()
        if slug:
            ru_from_file = str(MSP_PROJECT_NAME_MAP.get(slug, slug)).strip()
            if ru_from_file:
                out = _coerce_msp_project_name_from_file_if_needed(out, ru_from_file)
    except Exception:
        pass
    return out


def _find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    if df is None or not hasattr(df, "columns"):
        return None
    cols = list(df.columns)
    for cand in candidates:
        c0 = cand.strip().lower()
        for c in cols:
            if str(c).strip().lower() == c0:
                return c
    for cand in candidates:
        c0 = cand.strip().lower()
        for c in cols:
            if c0 in str(c).strip().lower():
                return c
    return None


def _find_building_column(df: pd.DataFrame) -> Optional[str]:
    if df is None or not hasattr(df, "columns"):
        return None
    for col in df.columns:
        cn = str(col).lower()
        for kw in ("building", "строение", "лот", "lot", "bldg"):
            if str(kw).lower() in cn:
                return str(col)
    return None


def _krstate_bucket(raw: Any) -> str:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return "other"
    s = str(raw).strip()
    sl = s.lower()
    if "declined" in sl or "отказ" in sl:
        return "declined"
    if "active" in sl or "doc_active" in sl:
        return "active"
    # Подписано: Tessa KrState / справочники (в т.ч. KrStates_Doc_Signed)
    if "signed" in sl or "doc_signed" in sl:
        return "signed"
    if re.search(r"не\s*подпис", sl) or "на подпис" in sl:
        return "other"
    if "подписан" in sl or "подписано" in sl:
        return "signed"
    return "other"


def _norm_join_key(val: Any) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    try:
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            fv = float(val)
            if fv == int(fv):
                return str(int(fv))
    except (TypeError, ValueError, OverflowError):
        pass
    s = str(val).strip()
    if len(s) > 2 and s.endswith(".0") and s[:-2].replace("-", "").isdigit():
        return s[:-2]
    return s


from utils import smart_to_datetime as _smart_to_dt
from utils import smart_to_datetime_series as _smart_to_dt_series


def _fmt_date_ru(v: Any) -> str:
    if v is None:
        return "Н/Д"
    try:
        if pd.isna(v):
            return "Н/Д"
    except (TypeError, ValueError):
        pass
    if isinstance(v, float) and pd.isna(v):
        return "Н/Д"
    if isinstance(v, pd.Timestamp):
        return v.strftime("%d.%m.%Y")
    from datetime import date, datetime

    if isinstance(v, datetime):
        return v.strftime("%d.%m.%Y")
    if isinstance(v, date):
        return v.strftime("%d.%m.%Y")
    # Чистое число без календарного контекста — не показываем как дату (частая ошибка маппинга)
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if pd.isna(v):
            return "Н/Д"
        fv = float(v)
        if 1900 <= fv <= 2100 and fv == int(fv):
            return "Н/Д"
    if isinstance(v, str):
        s = v.strip()
        if not s or s.lower() in ("nan", "nat", "none", ""):
            return "Н/Д"
        if re.fullmatch(r"[-+]?\d+([.,]\d+)?", s.replace(" ", "").replace("\u00a0", "")):
            return "Н/Д"
        s2 = s.replace("/", ".").replace("\\", ".")
        ts = _smart_to_dt(s2)
        if pd.isna(ts):
            return "Н/Д"
        return ts.strftime("%d.%m.%Y")
    ts = _smart_to_dt(v)
    if pd.isna(ts):
        return "Н/Д"
    return ts.strftime("%d.%m.%Y")


def _level_series(df: pd.DataFrame) -> pd.Series:
    """
    Фильтр «уровень N» по ТЗ — колонка MSP «Уровень» (не outline).
    В выгрузке «Уровень» и «Уровень_структуры» различаются (напр. ГПЗУ: Уровень=5, структура=3).
    Родителя «Ковенанты» считаем в web_loader по outline — см. _fill_section_from_task_tree.
    """
    if "level" in df.columns:
        return pd.to_numeric(df["level"], errors="coerce")
    if "level structure" in df.columns:
        return pd.to_numeric(df["level structure"], errors="coerce")
    return pd.Series(np.nan, index=df.index)


def _task_name_col(df: pd.DataFrame) -> Optional[str]:
    if "task name" in df.columns:
        return "task name"
    return _find_col(df, ["Название задачи", "Название", "Task Name"])


def _series_first_value(row: pd.Series, col: str) -> Any:
    """
    Скаляр из ячейки: при дублирующихся именах колонок (напр. два «plan end» после
    ремапа «Окончание» и «План окончание») берётся первое непустое значение.
    """
    if col not in row.index:
        return pd.NaT
    v = row[col]
    if isinstance(v, pd.Series):
        v2 = v.dropna()
        if v2.empty:
            return pd.NaT
        return v2.iloc[0]
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return pd.NaT
    return v


def _msp_row_date_completeness(row: pd.Series) -> float:
    """
    Оценка полноты дат для дедупликации (проект×задача): приоритет строке с План/Факт (base/plan end),
    иначе дедуп оставлял первую пустую строку — в матрице веха уходила в «Н/Д» при наличии данных в Excel.
    """
    be = _series_first_value(row, "base end")
    pe = _series_first_value(row, "plan end")
    if pd.isna(be) and pd.isna(pe):
        return 0.0
    if pd.isna(be) or pd.isna(pe):
        return 1.0
    return 2.0


def _dev_tz_pct_complete_series(df: pd.DataFrame, col: str = "pct complete") -> Optional[pd.Series]:
    """Одна серия колонки процента (при дублях имён — первый столбец)."""
    if df is None or getattr(df, "empty", True) or col not in df.columns:
        return None
    ser = df[col]
    if isinstance(ser, pd.DataFrame):
        ser = ser.iloc[:, 0]
    return ser if isinstance(ser, pd.Series) else None


def _pct_scale_max_from_frame(ref: Optional[pd.DataFrame], col: str = "pct complete") -> Optional[float]:
    """
    Max сырого процента по столбцу (после strip % / запятая), как в _parse_msp_percent_complete_series.
    Нужен, чтобы отличить доли 0..1 от шкалы 0..100 без ошибки «1% → 100%».
    """
    ser = _dev_tz_pct_complete_series(ref, col=col) if ref is not None else None
    if ser is None or ser.empty:
        return None
    from utils import parse_msp_pct_complete

    vals: list[float] = []
    for raw in ser.tolist():
        v = parse_msp_pct_complete(raw)
        if v is not None:
            vals.append(v)
    if not vals:
        return None
    return float(max(vals))


def _normalized_pct_0_100(pct: Any, *, pct_scale_max: Any = None) -> Optional[float]:
    """Возвращает число в шкале 0..100+ или None; логика согласована с _is_pct_complete_not_100."""
    if pct is None:
        return None
    try:
        if isinstance(pct, float) and pd.isna(pct):
            return None
    except (TypeError, ValueError):
        return None
    from utils import parse_msp_pct_complete

    if not isinstance(pct, (int, float)) or isinstance(pct, bool):
        parsed = parse_msp_pct_complete(pct)
        if parsed is not None:
            pct = parsed
    if isinstance(pct, (int, float)) and not isinstance(pct, bool):
        v = float(pct)
        sm: Optional[float] = None
        if pct_scale_max is not None:
            try:
                if isinstance(pct_scale_max, float) and pd.isna(pct_scale_max):
                    sm = None
                else:
                    sm = float(pct_scale_max)
            except (TypeError, ValueError):
                sm = None
        if sm is not None and sm <= 1.000001:
            v = v * 100.0
        elif sm is None:
            if 0.0 <= v <= 1.0:
                v = v * 100.0
        return float(v)
    s = str(pct).strip().replace("%", "").replace(" ", "").replace(",", ".")
    if not s or s.lower() in ("nan", "none", "nat"):
        return None
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    sm: Optional[float] = None
    if pct_scale_max is not None:
        try:
            if isinstance(pct_scale_max, float) and pd.isna(pct_scale_max):
                sm = None
            else:
                sm = float(pct_scale_max)
        except (TypeError, ValueError):
            sm = None
    if sm is not None and sm <= 1.000001:
        v = v * 100.0
    elif sm is None:
        if 0.0 <= v <= 1.0:
            v = v * 100.0
    return float(v)


def _is_pct_complete_not_100(pct: Any, *, pct_scale_max: Any = None) -> bool:
    """
    ТЗ «Контрольные точки»: оранжевый акцент, если % задан и в интервале (0, 100); 0% и 100% — без акцента.

    pct_scale_max — max сырого «pct complete» по тому же ref-датафрейму, что и _pct_scale_max_from_frame.
    """
    v = _normalized_pct_0_100(pct, pct_scale_max=pct_scale_max)
    if v is None:
        return False
    if abs(v) <= 1e-3:
        return False
    return abs(v - 100.0) > 1e-3


def _is_pct_complete_not_100_dev_matrix(pct: Any, *, pct_scale_max: Any = None) -> bool:
    """Экспорт/флаги: % выполнения в MSP задан и ≠ 100%."""
    v = _normalized_pct_0_100(pct, pct_scale_max=pct_scale_max)
    if v is None:
        return False
    return abs(v - 100.0) > 1e-3


def _is_pct_complete_100_dev_matrix(pct: Any, *, pct_scale_max: Any = None) -> bool:
    """Девелоперские проекты: оранжевый текст (#f09355), если задача закрыта на 100%."""
    v = _normalized_pct_0_100(pct, pct_scale_max=pct_scale_max)
    if v is None:
        return False
    return abs(v - 100.0) <= 1e-3


_MSP_NA_TOKENS = {"", "нд", "н/д", "n/d", "n/a", "—", "-", "nan", "nat", "none", "null"}


def _msp_value_is_na(v: Any) -> bool:
    """True для NaT/NaN/None/строк-плейсхолдеров «НД», «Н/Д», «—», «-», «N/A» и т.п.

    В выгрузках MSP пустые даты часто пишутся словом «НД» (см. msp_esipovo5_*.csv:
    «Базовое_окончание = НД» при заполненном «Окончание»). Без этой нормализации
    условие `pd.isna(...)` возвращало False, и для «Плана» не подхватывался
    fallback на «Окончание» — в матрице оба столбца становились «Н/Д».
    """
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return True
        if pd.isna(v):
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(v, str):
        s = v.strip().lower().replace("\xa0", " ")
        while "  " in s:
            s = s.replace("  ", " ")
        if s in _MSP_NA_TOKENS:
            return True
    return False


def _msp_plan_fact_pct(row: pd.Series) -> Tuple[Any, Any, Any]:
    """
    ТЗ: План = «Базовое окончание» (base end); Факт = «Окончание» (после web_loader — plan end).
    Без подмены на «Фактическое окончание»: только колонка окончания срока из MSP.
    Если базовое окончание пусто — для «Плана» берём то же «Окончание».

    Текстовые плейсхолдеры «НД» / «Н/Д» / «—» в base end и plan end считаются пустыми
    (см. _msp_value_is_na): иначе для Есипово V / Ленинский строка «Регистрация
    договора субаренды» давала «Н/Д» в обеих колонках, хотя в данных есть «Окончание».
    """
    be = _series_first_value(row, "base end")
    fe = _series_first_value(row, "plan end")
    if _msp_value_is_na(be):
        be = pd.NaT
    if _msp_value_is_na(fe):
        fe = pd.NaT
    if pd.isna(be):
        be = fe
    pc = _series_first_value(row, "pct complete") if "pct complete" in row.index else pd.NaT
    return be, fe, pc


def _delta_days_plan_minus_fact(plan_d: Any, fact_d: Any) -> Optional[int]:
    if pd.isna(plan_d) or pd.isna(fact_d):
        return None
    try:
        # smart-парсер: pd.Timestamp("01.04.2025") инвертировало бы DMY-строку,
        # а _smart_to_dt отличает ISO от DMY.
        pd_ts = _smart_to_dt(plan_d) if isinstance(plan_d, str) else pd.Timestamp(plan_d)
        fd_ts = _smart_to_dt(fact_d) if isinstance(fact_d, str) else pd.Timestamp(fact_d)
        if pd.isna(pd_ts) or pd.isna(fd_ts):
            return None
        return int((pd_ts.normalize() - fd_ts.normalize()).days)
    except Exception:
        return None


def _fmt_delta_days(d: Optional[int]) -> str:
    if d is None:
        return "Н/Д"
    try:
        di = int(d)
    except (TypeError, ValueError):
        return "Н/Д"
    if di == 0:
        return "0 дн."
    sign = "+" if di > 0 else "-" if di < 0 else ""
    return f"{sign}{abs(di)} дн."


_OTKL_DAYS_DISPLAY_RE = re.compile(r"([+\-−]?\d+)\s*дн", re.IGNORECASE)


def _parse_otkl_mln_display(s: Any) -> Optional[float]:
    """Число из «Откл.» в млн руб. (напр. «121,8» / «-2123,5») для раскраски бюджета."""
    if s is None:
        return None
    t = str(s).strip()
    if not t or t.upper() in ("Н/Д", "N/D", "—", "-"):
        return None
    if _OTKL_DAYS_DISPLAY_RE.search(t):
        return None
    t = t.replace("\xa0", "").replace("\u202f", "").replace(" ", "").replace(",", ".").replace("−", "-")
    try:
        return float(t)
    except ValueError:
        return None

def _parse_otkl_days_display(s: Any) -> Optional[int]:
    """Число дней из строки вида «+3 дн.» / «0 дн.» для раскраски «Откл.» (План−Факт)."""
    if s is None:
        return None
    t = str(s).strip()
    if not t or t.upper() in ("Н/Д", "N/D", "—", "-"):
        return None
    m = _OTKL_DAYS_DISPLAY_RE.search(t)
    if not m:
        return None
    try:
        v = int(m.group(1).replace("−", "-"))
        return v
    except ValueError:
        return None


def _norm_cell_for_date_check(s: Any) -> str:
    """Нормализация текста ячейки: NBSP/ZWSP, чтобы облако/Excel не ломали матч даты."""
    if s is None:
        return ""
    t = (
        str(s)
        .replace("\xa0", " ")
        .replace("\u2009", " ")
        .replace("\u200b", "")
        .replace("\ufeff", "")
        .strip()
    )
    while "  " in t:
        t = t.replace("  ", " ")
    return t


def _looks_like_ru_date_cell(s: Any) -> bool:
    if s is None:
        return False
    t = _norm_cell_for_date_check(s)
    if not t or t.upper() in ("Н/Д", "N/D", "—", "-"):
        return False
    # Строго DD.MM.YYYY или дата в начале («01.03.2026 г.», хвост от экспорта)
    if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", t):
        return True
    if re.match(r"^\d{2}\.\d{2}\.\d{4}\b", t):
        return True
    # Иногда в CSV/Excel приходит ISO
    if re.match(r"^\d{4}-\d{2}-\d{2}\b", t):
        return True
    return False


def _dev_tz_apply_vert_date(vertical_dates: bool, col: str, cell_val: Any) -> bool:
    """Нужны и класс, и inline-style (на Streamlit Cloud стили из <style> иногда не цепляются к ячейкам)."""
    return bool(
        vertical_dates
        and col in ("plan", "fact")
        and _looks_like_ru_date_cell(cell_val)
    )


def _find_phase_column(df: pd.DataFrame) -> Optional[str]:
    """Колонка вехи по макету правок: «Инвестиционная. Аренда ЗУ» и т.п. (не имена задач MSP)."""
    if df is None or not hasattr(df, "columns"):
        return None
    for c in df.columns:
        cl = str(c).strip().lower()
        if cl in ("фаза", "phase"):
            return str(c)
    return _find_col(df, ["Фаза", "Phase", "фаза"])


def _match_by_phase_needles(
    mdf: pd.DataFrame,
    needles: List[str],
    exclude_needles: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Внутренние CSV: веха в «Фаза». Чистый MSP без «Фаза»: те же подстроки ищем в «Задача» / notes / «Заметки».
    exclude_needles — применяются к колонке «Фаза», если она есть (разделение двух столбцов ИРД).
    """
    if mdf is None or mdf.empty or not needles:
        return mdf.iloc[0:0].copy()
    _lit = dict(case=False, na=False, regex=False)
    pc = _find_phase_column(mdf)
    nm = _task_name_col(mdf)
    text_cols: List[str] = []
    if pc and pc in mdf.columns:
        text_cols.append(pc)
    for c in (nm, "notes", "Заметки"):
        if c and c in mdf.columns and c not in text_cols:
            text_cols.append(str(c))
    if not text_cols:
        return mdf.iloc[0:0].copy()
    masks: List[pd.Series] = []
    for needle in needles:
        n = str(needle).strip()
        if not n:
            continue
        for c in text_cols:
            masks.append(mdf[c].astype(str).str.contains(n, **_lit))
    if not masks:
        return mdf.iloc[0:0].copy()
    mm = masks[0]
    for x in masks[1:]:
        mm = mm | x
    out = mdf[mm].copy()
    if exclude_needles and pc and pc in out.columns:
        s2 = out[pc].astype(str)
        for ex in exclude_needles:
            exs = str(ex).strip()
            if exs:
                out = out[~s2.str.contains(exs, **_lit)]
    return out


def _match_msp(
    mdf: pd.DataFrame,
    *,
    level: Optional[float],
    name_contains: Optional[str] = None,
    names_any: Optional[List[str]] = None,
    names_exact_any: Optional[List[str]] = None,
    parent_l2_contains: Optional[str] = None,
    block_contains: Optional[str] = None,
) -> pd.DataFrame:
    if mdf is None or mdf.empty:
        return mdf.iloc[0:0].copy()
    out = mdf
    nm = _task_name_col(out)
    if nm is None:
        return out.iloc[0:0].copy()
    _nm_clean = (
        out[nm]
        .astype(str)
        .str.replace("\xa0", " ", regex=False)
        .str.replace("\u200b", "", regex=False)
        .str.replace("\ufeff", "", regex=False)
        .str.strip()
    )
    lvl = _level_series(out)
    if level is not None and lvl.notna().any():
        out = out[lvl == float(level)]
    _lit = dict(case=False, na=False, regex=False)  # иначе «(РД)» и др. ломают regex
    if block_contains and "block" in out.columns:
        out = out[out["block"].astype(str).str.contains(block_contains, **_lit)]
    if parent_l2_contains:
        # Родитель ур.2: section из дерева задач; для «Ковенанты» — по подстроке «ковенант» (склонения/опечатки)
        l2c = _find_col(out, ["l2 parent", "l2_parent", "parent l2", "Раздел"])
        col = l2c if l2c and l2c in out.columns else ("section" if "section" in out.columns else None)
        if col is None:
            return out.iloc[0:0].copy()
        sc = out[col].astype(str)
        if "ковенант" in str(parent_l2_contains).lower():
            mask_cov = sc.str.contains("ковенант", **_lit)
            if "block" in out.columns:
                mask_cov = mask_cov | out["block"].astype(str).str.contains("ковенант", **_lit)
            # Вехи «ЗОС - 2 этап» без БЛОК/section «Ковенанты» (типично Дмитровский).
            if nm:
                nm_s = _nm_clean.loc[out.index]
                mask_cov = mask_cov | nm_s.str.contains(
                    r"^(?:ЗОС|РВ|Право\s*1|Право\s*2)\s*-\s*\d+\s*этап\s*$",
                    case=False,
                    na=False,
                    regex=True,
                ) | nm_s.str.contains(
                    r"(?:ВЫКУП\s+ЗУ|Право\s*2).+\(\s*1\s+и\s+2\s+этап",
                    case=False,
                    na=False,
                    regex=True,
                )
            out = out[mask_cov]
        else:
            out = out[sc.str.contains(str(parent_l2_contains), **_lit)]
    name_masks: List[pd.Series] = []
    if names_any:
        for needle in names_any:
            if needle:
                nd = str(needle).replace("\xa0", " ").strip()
                name_masks.append(_nm_clean.loc[out.index].str.contains(nd, **_lit))
    if names_exact_any:
        nv = _nm_clean.loc[out.index].str.casefold()
        for xs in names_exact_any:
            if xs is None or str(xs).strip() == "":
                continue
            xf = str(xs).strip().casefold()
            name_masks.append(nv.eq(xf))
    if name_contains:
        name_masks.append(
            _nm_clean.loc[out.index].str.contains(str(name_contains), **_lit)
        )
    if name_masks:
        mm_nm = name_masks[0]
        for xm in name_masks[1:]:
            mm_nm = mm_nm | xm
        out = out[mm_nm]
    return out


def _match_tasks_like_msp_row(mdf: pd.DataFrame, kw: dict) -> pd.DataFrame:
    """
    Те же шаги отбора задач MSP, что и для строки матрицы «Девелоперские проекты»
    (ослабление родителя ур.2, уровня, блока → «Фаза»).
    """
    if mdf is None or getattr(mdf, "empty", True):
        return mdf.iloc[0:0].copy()
    kw_m = {
        k: v
        for k, v in kw.items()
        if k not in ("phase_needles", "phase_exclude_needles", "names_exact_any")
    }
    _nex = kw.get("names_exact_any")
    phase_needles = kw.get("phase_needles")
    phase_exclude = kw.get("phase_exclude_needles")
    sub = _match_msp(
        mdf,
        level=kw_m.get("level"),
        name_contains=kw_m.get("name_contains"),
        names_any=kw_m.get("names_any"),
        names_exact_any=_nex,
        parent_l2_contains=kw_m.get("parent_l2_contains"),
        block_contains=kw_m.get("block_contains"),
    )
    if sub.empty and kw_m.get("parent_l2_contains"):
        sub = _match_msp(
            mdf,
            level=kw_m.get("level"),
            name_contains=kw_m.get("name_contains"),
            names_any=kw_m.get("names_any"),
            names_exact_any=_nex,
            parent_l2_contains=None,
            block_contains=kw_m.get("block_contains"),
        )
    if sub.empty and kw_m.get("level") is not None:
        sub = _match_msp(
            mdf,
            level=None,
            name_contains=kw_m.get("name_contains"),
            names_any=kw_m.get("names_any"),
            names_exact_any=_nex,
            parent_l2_contains=None,
            block_contains=kw_m.get("block_contains"),
        )
    if sub.empty:
        sub = _match_msp(
            mdf,
            level=None,
            name_contains=kw_m.get("name_contains"),
            names_any=kw_m.get("names_any"),
            names_exact_any=_nex,
            parent_l2_contains=None,
            block_contains=kw_m.get("block_contains"),
        )
    if sub.empty and kw_m.get("block_contains"):
        sub = _match_msp(
            mdf,
            level=None,
            name_contains=kw_m.get("name_contains"),
            names_any=kw_m.get("names_any"),
            names_exact_any=_nex,
            parent_l2_contains=None,
            block_contains=None,
        )
    if sub.empty and phase_needles:
        sub = _match_by_phase_needles(mdf, phase_needles, phase_exclude)
    return sub


def _unicode_dash_fold(s: str) -> str:
    """Единый дефис: длинное/короткое тире из MSP/Excel → '-', чтобы ключи группировки совпадали."""
    t = str(s)
    for ch in ("\u2013", "\u2014", "\u2212", "\u00ad"):
        t = t.replace(ch, "-")
    return t


def _norm_dev_project_key(val: Any) -> str:
    """
    Сопоставление подписи проекта MSP / 1С / TESSA: регистр, пробелы, «-», хвостовые
    римские цифры I..X → арабские 1..10 (чтобы «Есипово V» и «Есипово-5»,
    «Дмитровский I» и «Дмитровский-1» имели один ключ группировки).
    """
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip().lower().replace("ё", "е")
    s = re.sub(r"[\s\-_]+", "", s)
    _roman_tail = {
        "iii": 3, "ii": 2, "iv": 4, "ix": 9, "viii": 8, "vii": 7, "vi": 6,
        "v": 5, "i": 1, "x": 10,
    }
    for _rom in ("viii", "iii", "vii", "iv", "ix", "vi", "ii", "v", "x", "i"):
        if s.endswith(_rom) and len(s) > len(_rom) and s[-len(_rom) - 1].isalpha():
            s = s[: -len(_rom)] + str(_roman_tail[_rom])
            break
    return s


def _control_points_project_group_key(raw: Any) -> str:
    """
    Группировка строк в «Контрольные точки»: один логический проект (дубли «Дмитровский» / «Дмитровский-1»).
    """
    try:
        from config import MSP_PROJECT_NAME_MAP as M
    except Exception:
        M = {}
    s = (
        _unicode_dash_fold(str(raw))
        .replace("\u00a0", " ")
        .replace("\u200b", "")
        .replace("\ufeff", "")
        .strip()
    )
    # «Имя-1» / «Имя – 1» после фолда тире — тот же логический проект, что «Имя» (типовой дубль выгрузок)
    if re.search(r"-\s*1\s*$", s):
        s_alt = re.sub(r"-\s*1\s*$", "", s).strip()
        if len(s_alt) >= 3:
            s = s_alt
    lk = s.lower().replace(" ", "")
    mapped = None
    for k in (lk, re.sub(r"\d+$", "", lk), _norm_dev_project_key(s)):
        if k and k in M:
            mapped = M[k]
            break
    if mapped:
        nk = _norm_dev_project_key(mapped)
    else:
        nk = _norm_dev_project_key(s)
    # После маппинга: «Дмитровский», «Дмитровский 1», «Дмитровский I» — один проект.
    nk_base = re.sub(r"(?:1|i)$", "", nk)
    if nk in ("дмитровский", "дмитровский1", "дмитровскийi") or nk_base == "дмитровский":
        return "unified_dmitrovsky1"
    return nk


_PROJEKTS_DISPLAY_BY_NK_CACHE: Dict[tuple, Dict[str, str]] = {}


def _projekts_display_by_norm_key() -> Dict[str, str]:
    """Наименование_Проекта из 1с_*_Projekts.json (справочник) по norm-key группировки."""
    # Вызывается на каждую строку таблиц через _control_points_project_label; без
    # кеша norm-key словарь перестраивается тысячи раз за рендер. Ключ — (версия,
    # mtime БД), инвалидируется при обновлении данных.
    try:
        from web_db_read import resolve_version_id, web_db_mtime

        _key = (resolve_version_id(), web_db_mtime())
        _hit = _PROJEKTS_DISPLAY_BY_NK_CACHE.get(_key)
        if _hit is not None:
            return _hit
    except Exception:
        _key = None
    by_nk: Dict[str, str] = {}
    try:
        from web_db_read import load_project_id_to_name_lookup

        for pname in load_project_id_to_name_lookup().values():
            s = str(pname).strip()
            if not s:
                continue
            nk = _norm_dev_project_key(s)
            if nk:
                by_nk[nk] = s
    except Exception:
        pass
    if by_nk:
        if _key is not None:
            if len(_PROJEKTS_DISPLAY_BY_NK_CACHE) > 4:
                _PROJEKTS_DISPLAY_BY_NK_CACHE.clear()
            _PROJEKTS_DISPLAY_BY_NK_CACHE[_key] = by_nk
        return by_nk
    try:
        import json
        from pathlib import Path

        paths = sorted(Path("web").glob("*_Projekts.json"))
        if paths:
            with open(paths[-1], encoding="utf-8") as f:
                rows = json.load(f)
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    s = str(
                        row.get("Наименование_Проекта")
                        or row.get("Наименование проекта")
                        or row.get("Наименование")
                        or row.get("Проект")
                        or ""
                    ).strip()
                    nk = _norm_dev_project_key(s)
                    if nk:
                        by_nk[nk] = s
    except Exception:
        pass
    if _key is not None and by_nk:
        if len(_PROJEKTS_DISPLAY_BY_NK_CACHE) > 4:
            _PROJEKTS_DISPLAY_BY_NK_CACHE.clear()
        _PROJEKTS_DISPLAY_BY_NK_CACHE[_key] = by_nk
    return by_nk


def _msp_map_lookup_keys(raw: Any) -> List[str]:
    """Ключи для MSP_PROJECT_NAME_MAP: as-is, без пробелов, без хвостовой цифры (zhukovsky1→zhukovsky)."""
    s = str(raw or "").strip()
    if not s:
        return []
    keys: List[str] = []
    for cand in (
        s.lower().replace(" ", "").replace("\xa0", ""),
        _norm_dev_project_key(s),
        re.sub(r"\d+$", "", s.lower().replace(" ", "").replace("\xa0", "")),
        re.sub(r"\d+$", "", _norm_dev_project_key(s)),
    ):
        c = str(cand or "").strip()
        if c and c not in keys:
            keys.append(c)
    return keys


def resolve_msp_project_display_name(raw: Any) -> str:
    """
    Единая русская подпись проекта для матрицы/фильтров.

    1) MSP_PROJECT_NAME_MAP; 2) 1С Projekts по norm-key;
    3) авто: латинский slug (Zhukovsky1) → транслит → матч с Projekts.
    """
    s = str(raw or "").strip()
    if not s:
        return ""
    try:
        from config import MSP_PROJECT_NAME_MAP as M
    except Exception:
        M = {}
    for k in _msp_map_lookup_keys(s):
        if k in M:
            return str(M[k]).strip()
    # 1С Projekts: «Жуковский» по norm-key (в т.ч. после map slug→рус.)
    try:
        proj_ref = _projekts_display_by_norm_key()
        for k in _msp_map_lookup_keys(s):
            if k in proj_ref:
                return str(proj_ref[k]).strip()
            mapped = M.get(k) if isinstance(M, dict) else None
            if mapped:
                nk = _norm_dev_project_key(mapped)
                if nk and nk in proj_ref:
                    return str(proj_ref[nk]).strip()
        nk0 = _norm_dev_project_key(s)
        if nk0 and nk0 in proj_ref:
            return str(proj_ref[nk0]).strip()
    except Exception:
        pass
    # Авто для новых msp_<latin>_*.csv без ручной записи в карту
    try:
        from dashboards.project_labels import match_latin_slug_to_russian_project

        auto = match_latin_slug_to_russian_project(s)
        if auto:
            return str(auto).strip()
    except Exception:
        pass
    return s


def _control_points_project_label(group_key: str, raw_names: List[str]) -> str:
    """Подпись столбца «Проект» после группировки."""
    if group_key == "unified_dmitrovsky1":
        try:
            from config import MSP_PROJECT_NAME_MAP as M

            return str(M.get("dmitrovsky", M.get("дмитровский", "Дмитровский"))).strip()
        except Exception:
            return "Дмитровский"
    proj_ref = _projekts_display_by_norm_key()
    for r in raw_names:
        nk = _norm_dev_project_key(r)
        if nk and nk in proj_ref:
            return proj_ref[nk]
    gk_nk = _norm_dev_project_key(group_key)
    if gk_nk and gk_nk in proj_ref:
        return proj_ref[gk_nk]
    # Карта slug→рус. (zhukovsky1 / Zhukovsky1 → Жуковский), как у Новорижского.
    for r in list(raw_names) + [group_key]:
        disp = resolve_msp_project_display_name(r)
        if disp and disp != str(r or "").strip():
            return disp
        if disp and re.search(r"[а-яё]", disp, flags=re.IGNORECASE):
            return disp
    try:
        from config import MSP_PROJECT_NAME_MAP as M
    except Exception:
        M = {}
    # Сначала точный ключ из карты (без нормализации римских), чтобы не потерять имена вида
    # «Дмитровский-1». Далее — по нормализованному ключу (римские хвосты тоже сводятся).
    for r in raw_names:
        for lk in _msp_map_lookup_keys(r):
            if lk in M:
                return str(M[lk]).strip()
    for r in raw_names:
        s = str(r).strip()
        if s and re.search(r"[а-яё]", s, flags=re.IGNORECASE):
            return s
    if raw_names:
        return resolve_msp_project_display_name(raw_names[0]) or str(raw_names[0]).strip()
    return resolve_msp_project_display_name(group_key) or str(group_key or "").strip()


def _bddds_df_for_dev_matrix(
    mdf: pd.DataFrame,
    project_data: Optional[pd.DataFrame],
    ss: Any,
) -> Optional[pd.DataFrame]:
    """
    Обороты 1С для строки «Выборка ДС»: из session_state.reference_1c_dannye по колонке «Проект»,
    с тем же ключом, что и MSP «project name». Иначе — project_data, если там есть «Сценарий».
    """
    pname = ""
    if mdf is not None and not getattr(mdf, "empty", True) and "project name" in mdf.columns:
        s0 = mdf["project name"].dropna().astype(str).str.strip()
        if not s0.empty:
            pname = str(s0.iloc[0]).strip()
    ref = ss.get("reference_1c_dannye") if hasattr(ss, "get") else None
    if ref is not None and not getattr(ref, "empty", True) and pname:
        pc = _find_col(ref, ["Проект", "Project", "проект"])
        if pc and pc in ref.columns:
            pk = _norm_dev_project_key(pname)
            m = ref[pc].map(lambda x: _norm_dev_project_key(x) == pk)
            sub = ref.loc[m.fillna(False)].copy()
            if not sub.empty:
                return sub
            try:
                from config import MSP_PROJECT_NAME_MAP

                for _k, v in MSP_PROJECT_NAME_MAP.items():
                    if _norm_dev_project_key(v) == pk or _norm_dev_project_key(str(_k)) == pk:
                        m2 = ref[pc].map(lambda x: _norm_dev_project_key(x) == _norm_dev_project_key(v))
                        sub2 = ref.loc[m2.fillna(False)].copy()
                        if not sub2.empty:
                            return sub2
            except Exception:
                pass
            if pk:
                def _soft_dev_proj_cell(x: Any) -> bool:
                    nk = _norm_dev_project_key(x)
                    if not nk:
                        return False
                    if nk == pk:
                        return True
                    a, b = (nk, pk) if len(nk) <= len(pk) else (pk, nk)
                    return len(a) >= 4 and (a in b)

                m_soft = ref[pc].map(_soft_dev_proj_cell)
                sub_s = ref.loc[m_soft.fillna(False)].copy()
                if not sub_s.empty:
                    return sub_s
    if project_data is None or getattr(project_data, "empty", True):
        return None
    scen = _find_col(project_data, ["Сценарий", "Scenario"])
    if not scen or scen not in project_data.columns:
        return None
    if pname:
        pc2 = _find_col(project_data, ["Проект", "Project", "проект"])
        if pc2 and pc2 in project_data.columns:
            pk = _norm_dev_project_key(pname)
            m3 = project_data[pc2].map(lambda x: _norm_dev_project_key(x) == pk)
            if m3.fillna(False).any():
                return project_data.loc[m3.fillna(False)].copy()
            if pk:
                def _soft_proj_pd(x: Any) -> bool:
                    nk = _norm_dev_project_key(x)
                    if not nk:
                        return False
                    if nk == pk:
                        return True
                    a, b = (nk, pk) if len(nk) <= len(pk) else (pk, nk)
                    return len(a) >= 4 and (a in b)

                ms = project_data[pc2].map(_soft_proj_pd)
                if ms.fillna(False).any():
                    return project_data.loc[ms.fillna(False)].copy()
    return project_data


def _dev_matrix_bddds_totals_mln(
    ss: Any,
    pname: str,
    project_data: Optional[pd.DataFrame],
    mdf: pd.DataFrame,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    «Выборка ДС, млн руб.»: те же источники и срез, что дашборд БДДС.

    Берётся синтетика `try_synthetic_budget_from_1c_dannye`, фильтр по проекту строки матрицы,
    затем — как на БДДС: «Год» (`budget_plan_end_year`), календарь «С»/«По» по `plan end`
    (`budget_period_from` / `budget_period_to`), группировка «Месяц/Квартал/Год» (`budget_period`),
    вид «Накопительно» / «По месяцам» (`budget_period_view`). Если отчёт БДДС ещё не открывали
    и ключей нет — используется полный диапазон дат по данным проекта и режим «Накопительно».

    При неудаче — прежний fallback по оборотам `reference_1c_dannye` / `project_data`.
    """
    try:
        from dashboards.finance_from_1c import try_synthetic_budget_from_1c_dannye
    except Exception:
        try_synthetic_budget_from_1c_dannye = None  # type: ignore[misc]

    def _ss_get(key: str, default: Any = None) -> Any:
        if hasattr(ss, "get"):
            return ss.get(key, default)
        return default

    ref = _ss_get("reference_1c_dannye")
    pname = str(pname or "").strip()

    if (
        try_synthetic_budget_from_1c_dannye is None
        or ref is None
        or not isinstance(ref, pd.DataFrame)
        or getattr(ref, "empty", True)
        or not pname
    ):
        bdd = _bddds_df_for_dev_matrix(mdf, project_data, ss)
        return _ds_plan_fact_otkl_mln(bdd)

    syn = try_synthetic_budget_from_1c_dannye(reference_1c_dannye=ref)
    if syn is None or syn.empty or "project name" not in syn.columns:
        bdd = _bddds_df_for_dev_matrix(mdf, project_data, ss)
        return _ds_plan_fact_otkl_mln(bdd)

    try:
        from dashboards._renderers import (
            _project_filter_norm_key,
            _project_norm_key_matches_msp_keys,
        )
    except Exception:
        bdd = _bddds_df_for_dev_matrix(mdf, project_data, ss)
        return _ds_plan_fact_otkl_mln(bdd)

    pk = _norm_dev_project_key(pname)
    _rk = syn["project name"].map(_project_filter_norm_key)
    m_eq = _rk == pk

    def _soft_row(x: Any) -> bool:
        nk = _norm_dev_project_key(x)
        if not nk:
            return False
        if nk == pk:
            return True
        return len(pk) >= 4 and (pk in nk or nk in pk)

    sub = syn.loc[m_eq.fillna(False)].copy()
    if sub.empty:
        sub = syn.loc[syn["project name"].map(_soft_row)].copy()
    if sub.empty:
        _sel_pk = _project_filter_norm_key(pname)
        if _sel_pk:
            sub = syn.loc[
                syn["project name"]
                .map(_project_filter_norm_key)
                .map(lambda rk: _project_norm_key_matches_msp_keys(rk, {_sel_pk}))
            ].copy()
    if sub.empty:
        bdd = _bddds_df_for_dev_matrix(mdf, project_data, ss)
        return _ds_plan_fact_otkl_mln(bdd)

    # Год по plan end (как селектор «Год» на БДДС)
    sel_year = _ss_get("budget_plan_end_year", "Все")
    sy = str(sel_year).strip() if sel_year is not None else "Все"
    if sy not in ("", "Все", "None") and sy.isdigit():
        _pe_y = pd.to_datetime(sub["plan end"], errors="coerce")
        sub = sub[_pe_y.dt.year == int(sy)].copy()
        if sub.empty:
            bdd = _bddds_df_for_dev_matrix(mdf, project_data, ss)
            return _ds_plan_fact_otkl_mln(bdd)

    # Календарь «С» / «По» по plan end (те же ключи, что date_input на БДДС)
    _pe = pd.to_datetime(sub["plan end"], errors="coerce")
    pf = _ss_get("budget_period_from")
    pt = _ss_get("budget_period_to")
    if pf is not None and pt is not None:
        ts = pd.to_datetime(pf, errors="coerce")
        te = pd.to_datetime(pt, errors="coerce")
        if pd.notna(ts) and pd.notna(te):
            if ts > te:
                ts, te = te, ts
            sub = sub[
                _pe.notna()
                & (_pe >= ts.normalize())
                & (
                    _pe
                    <= (te.normalize() + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))
                )
            ].copy()
    if sub.empty:
        bdd = _bddds_df_for_dev_matrix(mdf, project_data, ss)
        return _ds_plan_fact_otkl_mln(bdd)

    period_ui = str(_ss_get("budget_period", "Месяц") or "Месяц").strip()
    period_col_map = {"Месяц": "plan_month", "Квартал": "plan_quarter", "Год": "plan_year"}
    period_col = period_col_map.get(period_ui, "plan_month")

    if period_col not in sub.columns and "plan end" in sub.columns:
        _pe2 = pd.to_datetime(sub["plan end"], errors="coerce")
        if period_col == "plan_month":
            sub = sub.assign(plan_month=_pe2.dt.to_period("M"))
        elif period_col == "plan_quarter":
            sub = sub.assign(plan_quarter=_pe2.dt.to_period("Q"))
        elif period_col == "plan_year":
            sub = sub.assign(plan_year=_pe2.dt.to_period("Y"))

    if period_col not in sub.columns:
        bdd = _bddds_df_for_dev_matrix(mdf, project_data, ss)
        return _ds_plan_fact_otkl_mln(bdd)

    sub = sub[sub[period_col].notna()].copy()
    if sub.empty:
        bdd = _bddds_df_for_dev_matrix(mdf, project_data, ss)
        return _ds_plan_fact_otkl_mln(bdd)

    sub["budget plan"] = pd.to_numeric(sub.get("budget plan", 0), errors="coerce").fillna(0.0)
    sub["budget fact"] = pd.to_numeric(sub.get("budget fact", 0), errors="coerce").fillna(0.0)

    g = (
        sub.groupby(period_col, dropna=False, sort=False)[["budget plan", "budget fact"]]
        .sum()
        .reset_index()
    )
    if g.empty:
        bdd = _bddds_df_for_dev_matrix(mdf, project_data, ss)
        return _ds_plan_fact_otkl_mln(bdd)

    try:
        g = g.sort_values(period_col)
    except Exception:
        pass

    view_type = str(_ss_get("budget_period_view", "Накопительно") or "Накопительно").strip()
    if view_type == "Накопительно":
        plan_sum = float(g["budget plan"].cumsum().iloc[-1])
        fact_sum = float(g["budget fact"].cumsum().iloc[-1])
    else:
        plan_sum = float(g["budget plan"].sum())
        fact_sum = float(g["budget fact"].sum())

    diff = fact_sum - plan_sum
    return plan_sum / 1e6, fact_sum / 1e6, diff / 1e6


def _ds_plan_fact_otkl_mln(project_data: Optional[pd.DataFrame]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if project_data is None or project_data.empty:
        return None, None, None
    bd = project_data.copy()
    bd.columns = [str(c).strip() for c in bd.columns]
    scen_col = _find_col(bd, ["Сценарий", "Scenario"])
    sum_col = _find_col(bd, ["Сумма", "Sum", "Amount", "СуммаОборота"])
    art_col = _find_col(bd, ["Статья оборотов", "СтатьяОборотов", "Статья"])
    if not scen_col or not sum_col:
        return None, None, None
    b = bd[bd[scen_col].notna()].copy()
    b = b[b[scen_col].astype(str).str.strip() != ""]
    if b.empty:
        return None, None, None
    scen_s = b[scen_col].astype(str)
    art_s = b[art_col].astype(str) if art_col and art_col in b.columns else pd.Series("", index=b.index)
    # ТЗ (file-003): статьи оборотов — все, кроме содержащих «(БДР)» в названии
    bdr_in_article = art_s.str.contains(r"\(\s*бдр\s*\)", case=False, na=False, regex=True)
    # B-2.2/B-06 (2026-05-07): план распознаётся не только по «бюджет», но и
    # по «план/plan» — в выгрузках 1С `*_dannye.json` сценарии обозначаются
    # значениями `ПЛАН/ФАКТ` (см. план-документ: «830 строк ТипСтатьи=БДДС,
    # Сценарий: ФАКТ=731 / ПЛАН=99»). Раньше «ПЛАН» в Сценарии полностью
    # игнорировался, отсюда «План=0.0» в матрице.
    is_fact_scen = scen_s.str.contains(r"факт|fact", case=False, na=False, regex=True)
    is_plan_scen = scen_s.str.contains(
        r"бюджет|budget|\bплан\b|\bplan\b", case=False, na=False, regex=True
    ) & ~is_fact_scen
    plan_mask = (
        is_plan_scen
        & art_s.astype(str).str.strip().ne("")
        & ~bdr_in_article
    )
    fact_mask = is_fact_scen
    if art_col and art_col in b.columns:
        fact_mask = (
            fact_mask
            & art_s.astype(str).str.strip().ne("")
            & ~bdr_in_article
        )
    plan_sum = pd.to_numeric(b.loc[plan_mask, sum_col], errors="coerce").fillna(0).sum()
    fact_sum = pd.to_numeric(b.loc[fact_mask, sum_col], errors="coerce").fillna(0).sum()
    # B-2.2/B-06 (2026-05-07): обороты 1С приходят в **тыс. руб.** (см. эталон
    # `finance_from_1c.try_synthetic_budget_from_1c_dannye`, L295: «1С обороты
    # … передаются в тыс. руб.; приводим к рублям»). Раньше тут было `/ 1e6`
    # без множителя × 1000 — значения матрицы оказывались занижены в 1000 раз.
    # Корректная формула: `× 1000 (тыс.руб → руб) / 1e6 (руб → млн.руб) = / 1000`.
    plan_mln = float(plan_sum) / 1000.0
    fact_mln = float(fact_sum) / 1000.0
    return plan_mln, fact_mln, fact_mln - plan_mln


def _tessa_to_dt(series: pd.Series) -> pd.Series:
    """Smart-парсинг колонки дат: ISO 'YYYY-MM-DD' и DMY 'DD.MM.YYYY' одновременно."""
    return _smart_to_dt_series(series)


def _resolve_tessa_pred_source(ss: Any) -> Tuple[pd.DataFrame, Optional[str], str]:
    """B-2.1 (2026-05-07): источник предписаний для матрицы «Девелоперские проекты».

    Старая логика брала только `tessa_tasks_data` (`*-task.csv`), но `KindName`
    обычно лежит в `tessa_data` (`*-id.csv`) — отсюда вечное «Н/Д» в строке
    «ПРЕДПИСАНИЯ». Здесь идём по двум источникам и берём первый, в котором есть
    колонка `KindName` И хотя бы одна строка `KindName ~ предписани`.

    Возвращает (DataFrame со строками предписаний, имя колонки KindName, ключ
    источника `"tessa_tasks_data"` / `"tessa_data"` / `""`).
    """
    for key in ("tessa_tasks_data", "tessa_data"):
        tdf = ss.get(key) if hasattr(ss, "get") else None
        if tdf is None or getattr(tdf, "empty", True):
            continue
        tk = tdf.copy()
        tk.columns = [str(c).strip() for c in tk.columns]
        try:
            from web_loader import _tessa_drop_cancelled_tag_rows

            tk = _tessa_drop_cancelled_tag_rows(tk)
        except Exception:
            pass
        kk = _find_col(tk, ["KindName", "kindname", "Вид"])
        if not kk:
            continue
        pred = tk[tk[kk].astype(str).str.contains(r"предписани", case=False, na=False, regex=True)].copy()
        if not pred.empty:
            return pred, kk, key
    return pd.DataFrame(), None, ""


def _tessa_pred_exclude_project_rows(pred: pd.DataFrame) -> pd.DataFrame:
    """Исключить документы в статусе «Проект» (KrStateID=0), как в отчёте «Предписания»."""
    if pred is None or pred.empty:
        return pred
    out = pred.copy()
    drop = pd.Series(False, index=out.index)
    if "KrStateID" in out.columns:
        drop = drop | pd.to_numeric(out["KrStateID"], errors="coerce").eq(0)
    state_c = _find_col(out, ["KrState", "KrStateName", "State", "Состояние", "Статус"])
    if state_c and state_c in out.columns:
        st_s = out[state_c].astype(str).str.strip().str.casefold()
        drop = drop | st_s.eq("проект")
    return out.loc[~drop.fillna(False)].copy()


def _tessa_pred_critical_series(pred: pd.DataFrame) -> pd.Series:
    """Критичность: тег «КРИТИЧНЫЙ» в Tessa_Teg (как dashboard_predpisania)."""
    crit = pd.Series(False, index=pred.index)
    tag_col = _find_col(
        pred,
        [
            "Tessa_Teg",
            "TessaTag",
            "TESSA_TEG",
            "tessa_teg",
            "ТегТесса",
            "Тег Тесса",
            "Тег",
            "Тэг",
        ],
    )
    if not tag_col:
        for _cn in pred.columns:
            _compact = "".join(str(_cn).strip().casefold().replace("\xa0", " ").split())
            if "tessa" in _compact and "teg" in _compact:
                tag_col = _cn
                break
    if tag_col and tag_col in pred.columns:
        _tag_norm = (
            pred[tag_col]
            .astype(str)
            .str.replace("\ufeff", "", regex=False)
            .str.replace("\xa0", " ", regex=False)
            .str.strip()
            .str.casefold()
        )
        crit = _tag_norm.isin(
            {"критичный", "критический", "критическое", "критичное", "critical"}
        )
    return crit


def _tessa_counts(ss: Any, project_name_hint: str = "") -> Tuple[str, str, str, str]:
    """Метрики вехи «ПРЕДПИСАНИЯ»: всего / критические / критические просроченные (по карточкам)."""
    pred, kk, src_key = _resolve_tessa_pred_source(ss)
    if pred.empty:
        # Если хоть один из источников загружен, но без «Предписания» в KindName —
        # это валидный «0»; если оба пусты — «Н/Д».
        any_loaded = any(
            (ss.get(k) is not None and not getattr(ss.get(k), "empty", True))
            for k in ("tessa_tasks_data", "tessa_data") if hasattr(ss, "get")
        )
        return ("0", "0", "0", "") if any_loaded else ("Н/Д", "Н/Д", "Н/Д", "")
    hint = (project_name_hint or "").strip()
    if hint:
        pred_f = build_predpisaniya_detail_df(ss, hint)
        if pred_f is not None and not pred_f.empty:
            pred = pred_f
        else:
            any_loaded = any(
                (ss.get(k) is not None and not getattr(ss.get(k), "empty", True))
                for k in ("tessa_tasks_data", "tessa_data")
                if hasattr(ss, "get")
            )
            if any_loaded:
                return "0", "0", "0", ""
            return "Н/Д", "Н/Д", "Н/Д", "Нет строк предписаний Tessa после фильтра по проекту."
    pred = _tessa_pred_exclude_project_rows(pred)
    if pred.empty:
        return "0", "0", "0", ""
    card_c = _find_col(pred, ["CardId", "CardID", "cardId", "DocID", "DocId", "Doc Id"])
    state_c = _find_col(pred, ["KrStateName", "KrState", "State", "Состояние", "Статус", "KrStateID"])
    due_c = _find_col(
        pred,
        [
            "id_Deadline",
            "id_deadline",
            "PlanDate",
            "DueDate",
            "Срок",
            "Крайний срок",
            "Срок устранения",
            "PlannedEnd",
            "Deadline",
        ],
    )
    if not card_c:
        n_rows = len(pred)
        return str(n_rows), "0", str(n_rows), ""
    pred = pred.assign(_card=pred[card_c].map(_norm_join_key))
    pred = pred[pred["_card"].astype(str).str.len() > 0]
    if pred.empty:
        return "0", "0", "0", ""

    pred["_critical"] = _tessa_pred_critical_series(pred)
    if "KrStateID" in pred.columns:
        _krs = pd.to_numeric(pred["KrStateID"], errors="coerce")
        pred["_resolved"] = _krs.eq(13)
    elif state_c and state_c in pred.columns:
        pred["_resolved"] = pred[state_c].map(lambda x: _krstate_bucket(x) == "signed")
    else:
        pred["_resolved"] = False

    card_resolved = pred.groupby("_card", group_keys=False)["_resolved"].agg(lambda s: bool(s.any()))
    card_critical = pred.groupby("_card", group_keys=False)["_critical"].agg(lambda s: bool(s.any()))
    n_total = int(len(card_resolved))
    n_critical = int((~card_resolved & card_critical).sum())

    card_overdue = pd.Series(False, index=card_resolved.index)
    if due_c and due_c in pred.columns:
        now = pd.Timestamp.now().normalize()
        open_rows = pred.loc[~pred["_resolved"].astype(bool)].copy()
        if not open_rows.empty:
            dts = _tessa_to_dt(open_rows[due_c])
            open_rows["_overdue"] = (dts.dt.normalize() < now) & dts.notna()
            card_overdue = open_rows.groupby("_card", group_keys=False)["_overdue"].agg(
                lambda s: bool(s.any())
            ).reindex(card_resolved.index, fill_value=False)

    n_critical_overdue = int(
        (~card_resolved & card_critical & card_overdue.fillna(False)).sum()
    )

    tail_hint = ""
    if n_critical_overdue:
        tail_hint = f"Критические просроченные (срок сдачи прошёл): {n_critical_overdue}"

    return str(n_total), str(n_critical), str(n_critical_overdue), tail_hint


def _predpisaniya_combined(mdf: pd.DataFrame, ss: Any, project_name: str = "") -> Tuple[str, str, str, bool, str]:
    """
    Строка «ПРЕДПИСАНИЯ»: только TESSA (как смежные отчёты по tessa_*), с фильтром по проекту MSP.
    Колонки: всего / критические / критические просроченные предписания (ТЗ 04.05).
    """
    n_total, n_critical, n_critical_overdue, hint = _tessa_counts(ss, project_name)
    if not (n_total == "Н/Д" and n_critical == "Н/Д" and n_critical_overdue == "Н/Д"):
        try:
            nco = int(str(n_critical_overdue).strip())
        except (TypeError, ValueError):
            nco = 0
        try:
            nc = int(str(n_critical).strip())
        except (TypeError, ValueError):
            nc = 0
        warn_t = nco > 0 or nc > 0
        return n_total, n_critical, n_critical_overdue, warn_t, hint
    return (
        n_total,
        n_critical,
        n_critical_overdue,
        False,
        (hint or "Нет данных Tessa по предписаниям (tessa_tasks_data / tessa_data не загружены или без KindName)."),
    )


def build_predpisaniya_detail_df(ss: Any, project_name_hint: str = "") -> pd.DataFrame:
    """Все строки предписаний из Tessa, опционально — фильтр по названию проекта/объекта.

    B-2.1 (2026-05-07): источник определяется через `_resolve_tessa_pred_source` —
    предпочитаем `tessa_tasks_data` (`*-task.csv`), фолбэк — `tessa_data`
    (`*-id.csv`, обычно именно там KindName=«Предписания»).
    """
    pred, kk, _src = _resolve_tessa_pred_source(ss)
    if pred.empty:
        return pd.DataFrame()
    hint = (project_name_hint or "").strip()
    if hint:
        pk = _norm_dev_project_key(hint)
        proj_cols = [
            _find_col(pred, ["ObjectName", "Object Name", "Объект"]),
            _find_col(pred, ["Проект", "Project", "project", "ProjectName"]),
        ]
        matched = False
        for proj_c in proj_cols:
            if not proj_c or proj_c not in pred.columns:
                continue

            def _row_match_cell(x: Any) -> bool:
                nk = _norm_dev_project_key(x)
                if not nk:
                    return False
                if nk == pk:
                    return True
                try:
                    if _control_points_project_group_key(hint) == _control_points_project_group_key(x):
                        return True
                except Exception:
                    pass
                a, b = (nk, pk) if len(nk) <= len(pk) else (pk, nk)
                return len(a) >= 4 and (a in b)

            m = pred[proj_c].map(_row_match_cell)
            if m.fillna(False).any():
                pred = pred.loc[m.fillna(False)].copy()
                matched = True
                break
        if not matched and pk:
            return pd.DataFrame()
    try:
        from tessa_status_utils import tessa_format_status_display_df

        return tessa_format_status_display_df(pred.reset_index(drop=True))
    except Exception:
        return pred.reset_index(drop=True)


def render_developer_predpisaniya_expander(
    ss: Any,
    project_names: Optional[List[str]] = None,
    *,
    expanded: bool = False,
) -> None:
    """Полная таблица предписаний Tessa под матрицей + выгрузка."""
    import streamlit as st

    from utils import render_dataframe_sortable

    raw_names = [str(n).strip() for n in (project_names or []) if str(n).strip()]
    if len(raw_names) == 1:
        exp_title = f"Предписания (Tessa), полная выгрузка — «{raw_names[0]}»"
    elif len(raw_names) > 1:
        exp_title = f"Предписания (Tessa), полная выгрузка — проектов: {len(raw_names)}"
    else:
        exp_title = "Предписания (Tessa), полная выгрузка"

    with st.expander(exp_title, expanded=expanded):
        if not raw_names:
            df_all = build_predpisaniya_detail_df(ss, "")
            if df_all.empty:
                return
            render_dataframe_sortable(df_all, file_stem="predpisaniya_tessa", key_prefix="dev_pred_all_tbl", use_styler=False)

            return

        chunks: List[pd.DataFrame] = []
        for pname in raw_names:
            chunk = build_predpisaniya_detail_df(ss, pname)
            if not chunk.empty:
                c2 = chunk.copy()
                c2.insert(0, "проект_фильтр", pname)
                chunks.append(c2)

        if not chunks:
            df_fallback = build_predpisaniya_detail_df(ss, "")
            if df_fallback.empty:
                return
            render_dataframe_sortable(df_fallback, file_stem="predpisaniya_tessa", key_prefix="dev_pred_fb_tbl", use_styler=False)

            return

        merged = pd.concat(chunks, ignore_index=True)
        render_dataframe_sortable(merged, file_stem="predpisaniya_tessa_by_project", key_prefix="dev_pred_detail_tbl", use_styler=False)



def developer_projects_msp_snapshot_hints(
    mdf: pd.DataFrame | None,
    *,
    ss: Any = None,
) -> list[str]:
    """Подсказки по снимку MSP и сбоям FTP (550 на msp_*_DD-MM-YYYY)."""
    hints: list[str] = []
    if ss is not None:
        try:
            for raw in ss.get("_last_ftp_sync_transient") or []:
                line = str(raw).strip()
                if not line or "msp_" not in line.casefold():
                    continue
                m = re.search(r"msp_[\w-]+", line, flags=re.IGNORECASE)
                stem = m.group(0) if m else line.split(":", 1)[0].strip()
                hints.append(
                    f"На FTP есть {stem}, но скачать не удалось (файл занят / 550). "
                    "Дашборд остаётся на предыдущем msp_* из web/. Повторите «FTP → перезагрузить БД» "
                    "через 5–10 мин после 07:00 или попросите IT проверить выгрузку MSP на FTP."
                )
        except Exception:
            pass
    if mdf is not None and not getattr(mdf, "empty", True) and "snapshot_date" in mdf.columns:
        try:
            snap = pd.to_datetime(mdf["snapshot_date"], errors="coerce").max()
            if pd.notna(snap):
                hints.append(
                    f"Активный снимок MSP в матрице: {pd.Timestamp(snap).strftime('%d.%m.%Y')} "
                    "(последний успешно загруженный msp_* в web/)."
                )
        except Exception:
            pass
    return hints


def _msp_row_source_project_bucket(source_file: Any) -> str:
    """msp_<slug>_DD-MM-YYYY → slug; иначе пусто."""
    if source_file is None or (isinstance(source_file, float) and pd.isna(source_file)):
        return ""
    try:
        from web_loader import _msp_project_bucket

        stem = Path(str(source_file).replace("\\", "/").split("/")[-1]).stem
        return str(_msp_project_bucket(stem) or "").strip().lower()
    except Exception:
        return ""


def _keep_latest_msp_snapshot_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Жёстко оставляет только max(snapshot_date) на логический MSP-проект.

    Нужно до dedupe по unique id: иначе при разных подписях project name
    (zhukovsky1 / Жуковский) или multi-proj keep=(project,id) в кадре остаются
    и июнь, и июль — вехи с нулевым Откл. из старого снимка перебивают актуальные.
    """
    if df is None or getattr(df, "empty", True) or "snapshot_date" not in df.columns:
        return df
    out = df.copy()
    out["_snap_ord"] = pd.to_datetime(out["snapshot_date"], errors="coerce")
    has = out["_snap_ord"].notna()
    if not bool(has.any()):
        return out.drop(columns=["_snap_ord"], errors="ignore")

    src_col = next(
        (c for c in ("__source_file", "source_file", "_source_file") if c in out.columns),
        None,
    )
    pc = _find_col(out, ["project name", "Проект", "Project", "проект"])
    if src_col is not None:
        keys = out[src_col].map(_msp_row_source_project_bucket).astype(str)
    else:
        keys = pd.Series([""] * len(out), index=out.index, dtype=object)
    if pc and pc in out.columns:
        try:
            gk = out[pc].map(
                lambda x: str(_control_points_project_group_key(x) or "").strip()
            )
        except Exception:
            gk = out[pc].map(lambda x: str(x or "").strip().lower())
        keys = keys.where(keys.str.strip() != "", gk)
    keys = keys.fillna("").astype(str).str.strip().replace("", "__all__")
    out["_snap_proj_key"] = keys

    snap = out.loc[has].copy()
    nosnap = out.loc[~has].copy()
    latest = snap.groupby("_snap_proj_key", dropna=False)["_snap_ord"].transform("max")
    snap = snap[snap["_snap_ord"] == latest]
    out = pd.concat([snap, nosnap], ignore_index=False)
    return out.drop(columns=["_snap_ord", "_snap_proj_key"], errors="ignore")


def dedupe_msp_for_developer_projects(df: pd.DataFrame) -> pd.DataFrame:
    """
    ТЗ: нет дублирования проектов и задач в «Девелоперские проекты».
    Сначала — только последний MSP-снимок на проект (snapshot_date / msp_* файл).
    Затем по идентификатору задачи MSP (если колонка есть и не пустая).
    При **нескольких проектах** в одном кадре дедупликация по id ведётся в паре
    с логическим ключом проекта — иначе совпадающие номера id у разных проектов
    схлопываются и вехи пропадают (режим «Все проекты»).
    Иначе по (проект, задача) / по задаче.

    Если в колонке id часть строк без значения, нельзя делать ``drop_duplicates`` по всему кадру:
    строки без id считаются дубликатами друг друга и схлопываются в одну (матрица уходит в Н/Д).
    """
    if df is None or getattr(df, "empty", True):
        return df
    out = _keep_latest_msp_snapshot_rows(df.copy())

    # При нескольких MSP-снимках одного проекта строку на задачу берём из самой
    # свежей выгрузки по дате (snapshot_date), а не случайную по порядку склейки.
    # Иначе дата (напр. ЗОС) могла прийти из старого снимка. Всегда берётся
    # последняя дата (в т.ч. будущая) — «плохие» файлы убираются удалением с FTP.
    if "snapshot_date" in out.columns:
        try:
            _sd = pd.to_datetime(out["snapshot_date"], errors="coerce")
            out = out.assign(_snap_ord=_sd)
            out = out.sort_values(
                by="_snap_ord",
                ascending=False,
                kind="mergesort",
                na_position="last",
            ).drop(columns=["_snap_ord"], errors="ignore")
        except Exception:
            pass

    def _series_id_valid(ser: pd.Series) -> pd.Series:
        s2 = ser.astype(str).str.strip()
        low = s2.str.lower()
        return ser.notna() & ~low.isin(("", "nan", "none", "<na>", "nat"))

    def _dedupe_by_id_nonempty(frame: pd.DataFrame, id_col: str) -> pd.DataFrame:
        ok = _series_id_valid(frame[id_col])
        if int(ok.sum()) == 0:
            return frame
        # keep="first" после сортировки по snapshot_date desc
        part_ok = frame.loc[ok].drop_duplicates(subset=[id_col], keep="first")
        part_miss = frame.loc[~ok]
        return pd.concat([part_miss, part_ok], ignore_index=True)

    def _dedupe_by_id_and_project_nonempty(
        frame: pd.DataFrame, id_col: str, proj_key_col: str
    ) -> pd.DataFrame:
        """Составной ключ (логический проект, id): ID MSP могут совпадать между проектами."""
        ok = _series_id_valid(frame[id_col])
        if int(ok.sum()) == 0:
            return frame
        sub = frame.loc[ok]
        if proj_key_col in sub.columns:
            part_ok = sub.drop_duplicates(subset=[proj_key_col, id_col], keep="first")
        else:
            part_ok = sub.drop_duplicates(subset=[id_col], keep="first")
        part_miss = frame.loc[~ok]
        return pd.concat([part_miss, part_ok], ignore_index=True)

    pc_for_id = _find_col(out, ["project name", "Проект", "Project", "проект"])
    _proj_key_col = None
    _multi_proj = False
    if pc_for_id and pc_for_id in out.columns:
        try:
            out = out.copy()
            out["_dev_proj_gk"] = out[pc_for_id].map(
                lambda x: str(_control_points_project_group_key(x) or "").strip()
                or str(x or "").strip().lower()
            )
            _proj_key_col = "_dev_proj_gk"
            _multi_proj = int(out["_dev_proj_gk"].replace("", pd.NA).dropna().nunique()) > 1
        except Exception:
            _multi_proj = int(out[pc_for_id].dropna().astype(str).str.strip().nunique()) > 1
            _proj_key_col = pc_for_id

    for id_c in (
        "unique id",
        "Уникальный_идентификатор",
        "task id seq",
        "Ид",
    ):
        if id_c not in out.columns:
            continue
        if int(_series_id_valid(out[id_c]).sum()) == 0:
            continue
        if _multi_proj and _proj_key_col and _proj_key_col in out.columns:
            out = _dedupe_by_id_and_project_nonempty(out, id_c, _proj_key_col)
        else:
            out = _dedupe_by_id_nonempty(out, id_c)
        return out.drop(columns=["_dev_proj_gk"], errors="ignore").reset_index(drop=True)
    pc = _find_col(out, ["project name", "Проект", "Project", "проект"])
    tc = _task_name_col(out)
    if pc and tc and pc in out.columns and tc in out.columns:
        _score = out.apply(_msp_row_date_completeness, axis=1)
        # Сначала полнота дат, затем свежесть снимка — не потерять июльский Откл.
        _sd = (
            pd.to_datetime(out["snapshot_date"], errors="coerce")
            if "snapshot_date" in out.columns
            else pd.Series(pd.NaT, index=out.index)
        )
        _ord = (
            out.assign(_d=_score, _snap=_sd)
            .sort_values(by=["_d", "_snap"], ascending=[False, False], kind="mergesort")
            .drop(columns=["_d", "_snap"])
        )
        return (
            _ord.drop_duplicates(subset=[pc, tc], keep="first")
            .drop(columns=["_dev_proj_gk"], errors="ignore")
            .reset_index(drop=True)
        )
    if tc and tc in out.columns:
        return (
            out.drop_duplicates(subset=[tc], keep="first")
            .drop(columns=["_dev_proj_gk"], errors="ignore")
            .reset_index(drop=True)
        )
    return out.drop(columns=["_dev_proj_gk"], errors="ignore")




_PLOT_SECTION_RE = re.compile(
    r"(?:\u0443\u0447\u0430\u0441\u0442\u043e\u043a|\u0443\u0447\.?)\s*\u2116\s*(\d+)",
    re.IGNORECASE | re.UNICODE,
)
# Дмитровский и др.: «ЗОС - 2 этап» — отдельные строки матрицы по номеру этапа.
_STAGE_SECTION_RE = re.compile(
    r"(\d+)\s*\u044d\u0442\u0430\u043f",
    re.IGNORECASE | re.UNICODE,
)

# \u0417\u0430\u0434\u0430\u0447\u0438 MSP, \u043a\u043e\u0442\u043e\u0440\u044b\u0435 \u043c\u043e\u0433\u0443\u0442 \u0434\u0443\u0431\u043b\u0438\u0440\u043e\u0432\u0430\u0442\u044c\u0441\u044f \u043f\u043e \u0443\u0447\u0430\u0441\u0442\u043a\u0430\u043c (\u0422\u04173).
_PLOT_SECTION_TASK_HINTS = (
    "\u0437\u043e\u0441",
    " \u0440\u0432",
    "\u0440\u0432)",
    "\u0432\u044b\u043a\u0443\u043f",
    "\u043f\u0440\u0430\u0432\u043e 1",
    "\u043f\u0440\u0430\u0432\u043e 2",
    "\u0442\u0435\u0445\u043f\u0440\u0438\u0441\u043e\u0435\u0434",
)


def _task_plot_section(task_name: object) -> Optional[str]:
    s = str(task_name or "").strip()
    if not s:
        return None
    m = _PLOT_SECTION_RE.search(s)
    if m:
        return str(m.group(1)).strip()
    m2 = _STAGE_SECTION_RE.search(s)
    if m2:
        return str(m2.group(1)).strip()
    return None


def _row_plot_section(row: pd.Series, task_col: Optional[str] = None) -> Optional[str]:
    """Участок №N: из имени задачи или родительского section/block (Есипово 5: «Получение ЗОС…» под «…участок №2»)."""
    tc = task_col or _task_name_col(row.to_frame().T)
    if tc and tc in row.index:
        ps = _task_plot_section(row.get(tc))
        if ps:
            return ps
    for col in ("section", "block", "l2 parent", "l2_parent", "parent l2", "Раздел"):
        if col in row.index:
            ps = _task_plot_section(row.get(col))
            if ps:
                return ps
    return None


def _task_name_suggests_plot_section(task_name: object) -> bool:
    t = str(task_name or "").casefold()
    if not t:
        return False
    if _task_plot_section(task_name):
        return True
    return any(h in t for h in _PLOT_SECTION_TASK_HINTS)


def _filter_milestone_tasks_by_plot_section(
    sub: pd.DataFrame,
    plot_section: str,
) -> pd.DataFrame:
    """\u0415\u0441\u043b\u0438 \u0441\u0440\u0435\u0438 \u0432\u0435\u0445\u0438 \u0435\u0441\u0442\u044c \u0443\u0447\u0430\u0441\u0442\u043e\u043a \u2014 \u043e\u0441\u0442\u0430\u0432\u043b\u044f\u0435\u043c \u0442\u043e\u043b\u044c\u043a\u043e \u0437\u0430\u0434\u0430\u0447\u0438 \u044d\u0442\u043e\u0433\u043e \u2116; \u0438\u043d\u0430\u0447\u0435 \u0431\u0435\u0437 \u0444\u0438\u043b\u044c\u0442\u0440\u0430 (\u043e\u0431\u0449\u0438\u0435 \u0432\u0435\u0445\u0438)."""
    if sub is None or getattr(sub, "empty", True):
        return sub
    tc = _task_name_col(sub)
    if not tc or tc not in sub.columns:
        return sub
    sec = str(plot_section or "").strip()
    if not sec:
        return sub
    has_sectioned = False
    for _ix, rr in sub.iterrows():
        if _row_plot_section(rr, tc):
            has_sectioned = True
            break
    if not has_sectioned:
        return sub
    keep = []
    for ix, rr in sub.iterrows():
        ps = _row_plot_section(rr, tc)
        if ps == sec:
            keep.append(ix)
    if keep:
        return sub.loc[keep].copy()
    # Общие вехи без маркера участка — только если нет задач с явным № участка.
    keep = []
    for ix, rr in sub.iterrows():
        if _row_plot_section(rr, tc) is None:
            keep.append(ix)
    if not keep:
        return sub.iloc[0:0].copy()
    return sub.loc[keep].copy()


def _detect_plot_sections_from_msp(mdf: pd.DataFrame) -> List[str]:
    if mdf is None or getattr(mdf, "empty", True):
        return []
    tc = _task_name_col(mdf)
    if not tc or tc not in mdf.columns:
        return []
    found: set[str] = set()
    for tn in mdf[tc].astype(str):
        if not _task_name_suggests_plot_section(tn):
            continue
        ps = _task_plot_section(tn)
        if ps:
            found.add(ps)
    if len(found) < 2:
        return []

    def _sort_key(x: str) -> tuple:
        try:
            return (0, int(x))
        except ValueError:
            return (1, x)

    return sorted(found, key=_sort_key)



def _msp_is_unified_dmitrovsky(mdf: pd.DataFrame) -> bool:
    """Дмитровский 1 — одна строка матрицы/КТ, без деления по «N этап»."""
    if mdf is None or getattr(mdf, "empty", True):
        return False
    pcol = _project_name_column(mdf)
    if not pcol or pcol not in mdf.columns:
        return False
    for raw in mdf[pcol].dropna().astype(str).str.strip().unique():
        if _control_points_project_group_key(raw) == "unified_dmitrovsky1":
            return True
    return False

def _control_points_stage_from_project_label(label: object) -> Optional[str]:
    s = str(label or "").strip()
    if not s:
        return None
    m = re.search(r"\((\d+)\s*\u044d\u0442\u0430\u043f\)\s*$", s, flags=re.IGNORECASE)
    if m:
        return str(m.group(1)).strip()
    return None


def _control_points_base_project_label(label: object) -> str:
    s = str(label or "").strip()
    if not s:
        return ""
    return re.sub(
        r"\s*\(\d+\s*\u044d\u0442\u0430\u043f\)\s*$",
        "",
        s,
        flags=re.IGNORECASE,
    ).strip()


def build_dev_tz_matrix_blocks(
    mdf: pd.DataFrame,
    project_data: Optional[pd.DataFrame],
    ss: Any,
    *,
    project_label_for_scope: str = "",
) -> List[Tuple[str, List[Dict[str, Any]]]]:
    """\u041e\u0434\u0438\u043d \u043f\u0440\u043e\u0435\u043a\u0442 \u2014 \u043e\u0434\u043d\u0430 \u0441\u0442\u0440\u043e\u043a\u0430; \u043f\u0440\u0438 \u043d\u0435\u0441\u043a\u043e\u043b\u044c\u043a\u0438\u0445 \u0443\u0447\u0430\u0441\u0442\u043a\u0445 \u2014 \u043d\u0435\u0441\u043a\u043e\u043b\u044c\u043a\u043e \u0441\u0442\u0440\u043e\u043a (\u0443\u0447. \u2116N)."""
    if mdf is None or getattr(mdf, "empty", True):
        return []
    # pandas 3.0: один раз снимаем arrow-строки (см. _dearrow_object_columns) —
    # дальше build_dev_tz_matrix_rows работает уже по numpy object.
    mdf = _dearrow_object_columns(mdf)
    if project_data is not None:
        project_data = _dearrow_object_columns(project_data)
    sections = _detect_plot_sections_from_msp(mdf)
    if _msp_is_unified_dmitrovsky(mdf):
        sections = []
    rows0, label0 = build_dev_tz_matrix_rows(
        mdf,
        project_data,
        ss,
        project_label_for_scope=project_label_for_scope,
        plot_section=None,
    )
    base = str(label0 or project_label_for_scope or "").strip()
    if not sections:
        return [(base, rows0)] if rows0 or base else []
    blocks: List[Tuple[str, List[Dict[str, Any]]]] = []
    for sec in sections:
        rows_s, _ = build_dev_tz_matrix_rows(
            mdf,
            project_data,
            ss,
            project_label_for_scope=project_label_for_scope,
            plot_section=sec,
        )
        lbl = f"{base} ({sec} \u044d\u0442\u0430\u043f)" if base else f"{sec} \u044d\u0442\u0430\u043f"
        blocks.append((lbl, rows_s))
    return blocks


def build_dev_tz_matrix_blocks_cached(
    mdf: pd.DataFrame,
    project_data: Optional[pd.DataFrame],
    ss: Any,
    *,
    project_label_for_scope: str = "",
) -> List[Tuple[str, List[Dict[str, Any]]]]:
    if mdf is None or getattr(mdf, "empty", True):
        return []
    if ss is None:
        return build_dev_tz_matrix_blocks(
            mdf, project_data, ss, project_label_for_scope=project_label_for_scope
        )
    cache = _dev_matrix_cache(ss)
    key = (
        "blocks",
        _df_fingerprint(mdf),
        _matrix_project_scope_tag(mdf),
        _df_fingerprint(project_data),
        str(project_label_for_scope or ""),
        _prefs_fingerprint(),
    )
    cached = cache.get(key)
    if isinstance(cached, list):
        return cached  # type: ignore[return-value]
    res = build_dev_tz_matrix_blocks(
        mdf, project_data, ss, project_label_for_scope=project_label_for_scope
    )
    try:
        cache[key] = res
    except Exception:
        pass
    return res

def build_dev_tz_matrix_rows(
    mdf: pd.DataFrame,
    project_data: Optional[pd.DataFrame],
    ss: Any,
    *,
    project_label_for_scope: str = "",
    plot_section: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], str]:
    rows: List[Dict[str, Any]] = []

    if mdf is None or getattr(mdf, "empty", True):
        return [], ""
    mdf = ensure_msp_df_for_dev_matrix(mdf)
    if mdf is None or getattr(mdf, "empty", True):
        return [], ""
    # pandas 3.0: убираем arrow-строки до тяжёлой поэлементной обработки —
    # иначе scalar .at[]-записи фрагментируют ChunkedArray и take деградирует.
    mdf = _dearrow_object_columns(mdf)
    if project_data is not None:
        project_data = _dearrow_object_columns(project_data)

    # Один столбец матрицы = одна подпись проекта. Если в кадре смешаны сырые «Дмитровский» и «Дмитровский 1»
    # (общий group key), без сужения вехи матчились по всем строкам и бралась задача «чужого» варианта имени.
    plab = str(project_label_for_scope or "").strip()
    if plab and "project name" in mdf.columns:
        try:
            # Жуковский (подпись) и Zhukovsky1 (slug файла) — один group key после карты.
            pk_tgt = str(_control_points_project_group_key(plab) or "").strip()
            if pk_tgt:
                m_scoped = mdf[
                    mdf["project name"].map(
                        lambda x, pk=pk_tgt: str(_control_points_project_group_key(x) or "").strip()
                        == pk
                    )
                ]
                if m_scoped is not None and not getattr(m_scoped, "empty", True):
                    mdf = m_scoped
        except Exception:
            pass

    # На всякий случай пересчитываем section из дерева (старые сессии/БД могли иметь ЛОТ вместо родителя ур.2)
    if mdf is not None and not getattr(mdf, "empty", True) and "task name" in mdf.columns:
        try:
            from web_loader import _fill_section_from_task_tree

            mdf = _fill_section_from_task_tree(mdf.copy())
        except Exception:
            pass
    if mdf is not None and not getattr(mdf, "empty", True):
        mdf = dedupe_msp_for_developer_projects(mdf)
    # Подпись в колонке «Проект»: всегда русская карта (не slug из msp_zhukovsky1_*).
    if mdf is not None and not getattr(mdf, "empty", True) and "project name" in mdf.columns:
        try:
            mdf = mdf.copy()
            mdf["project name"] = mdf["project name"].map(
                lambda x: resolve_msp_project_display_name(x) or str(x or "").strip()
            )
        except Exception:
            pass

    _prefs = load_developer_projects_matrix_prefs()

    def effective_title(row_key: str, default_title: str) -> str:
        tt = (_prefs.get("titles") or {}).get(row_key)
        if isinstance(tt, str) and tt.strip():
            return tt.strip()
        return default_title

    def effective_match(row_key: str, kw: dict) -> dict:
        patch = (_prefs.get("matches") or {}).get(row_key)
        out = copy.deepcopy(kw)
        if isinstance(patch, dict) and patch:
            out.update(patch)
        return out

    def add_row(
        group: str,
        label: str,
        plan_s: str,
        fact_s: str,
        otkl_s: str,
        *,
        warn_pct: bool = False,
        pct_complete_100: bool = False,
        warn_directives: bool = False,
        otkl_fact_lt_plan: bool = False,
        subcolumn_labels: Optional[Dict[str, str]] = None,
        phase: str = "",
        row_key: str = "",
    ) -> None:
        # Sanity sync: если План и Факт — обычные даты вида ДД.ММ.ГГГГ, гарантируем,
        # что «Откл.» = План − Факт (календарные дни) ровно по показанным датам.
        # Это устраняет рассинхрон, когда исходник Δ берётся из иной строки матча.
        try:
            _ds = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})\.(\d{4})\s*$")
            mp = _ds.match(str(plan_s or ""))
            mf = _ds.match(str(fact_s or ""))
            if mp and mf:
                pdt = pd.Timestamp(year=int(mp.group(3)), month=int(mp.group(2)), day=int(mp.group(1)))
                fdt = pd.Timestamp(year=int(mf.group(3)), month=int(mf.group(2)), day=int(mf.group(1)))
                d = int((pdt.normalize() - fdt.normalize()).days)
                otkl_s = _fmt_delta_days(d)
        except Exception:
            pass
        rows.append(
            {
                "group": group,
                "label": label,
                "plan": plan_s,
                "fact": fact_s,
                "otkl": otkl_s,
                "warn": bool(warn_pct or warn_directives),
                "warn_pct": bool(warn_pct),
                "pct_complete_100": bool(pct_complete_100),
                "warn_directives": bool(warn_directives),
                "otkl_fact_lt_plan": bool(otkl_fact_lt_plan),
                "subcolumn_labels": dict(subcolumn_labels) if subcolumn_labels else None,
                "phase": phase,
                "row_key": str(row_key or "").strip(),
            }
        )

    cap = ""
    if "project name" in mdf.columns and mdf["project name"].notna().any():
        cap = str(mdf["project name"].dropna().astype(str).iloc[0]).strip()
    # Подпись блока (фильтр «Все» → по проектам): для TESSA/1С не брать случайный iloc[0].
    # Всегда через карту: иначе cap остаётся Zhukovsky1 при пустом plab.
    scope_label = resolve_msp_project_display_name(plab or cap) or (plab or cap).strip()

    def _msp_row(
        phase: str,
        group: str,
        label: str,
        kw: dict,
        *,
        row_key: str,
    ) -> None:
        lab = effective_title(row_key, label)
        kw2 = effective_match(row_key, kw)
        sub = _match_tasks_like_msp_row(mdf, kw2)
        if plot_section:
            sub = _filter_milestone_tasks_by_plot_section(sub, str(plot_section))
        if sub is None or sub.empty:
            add_row(group, lab, "Н/Д", "Н/Д", "Н/Д", phase=phase, row_key=row_key)
            return
        # ТЗ: в каждой ячейке План/Факт/Откл. — одно значение (одна дата / один текст отклонения), без «дата1 / дата2».
        ps, fs, os, _ok, w, pct100 = _one_milestone_cell(sub, pct_scale_ref=mdf)
        add_row(
            group,
            lab,
            ps,
            fs,
            os,
            warn_pct=bool(w),
            pct_complete_100=bool(pct100),
            phase=phase,
            row_key=row_key,
        )

    # Порядок столбцов — по референсу (file-002: вехи Ковенантов; file-003: ДС/ТЕССА до ИРД/ПОС)
    _rk = iter(_DEV_MATRIX_ROW_KEYS)
    specs_invest_msp: List[Tuple[str, str, str, dict]] = [
        # По ТЗ: в реальной MSP — имя задачи + ур.5; во внутренних CSV вехи часто в колонке «Фаза» (см. phase_needles).
        (
            "invest",
            "ЗУ / Ковенанты",
            "Аренда ЗУ",
            {
                "level": 5.0,
                "parent_l2_contains": "Ковенанты",
                # ТЗ: дочерняя «Аренда земельного участка (ЗУ)» (ур.5) под родителем «КОВЕНАНТЫ» (ур.2).
                "names_exact_any": [
                    "Аренда земельного участка (ЗУ)",
                ],
                "names_any": [
                    "Аренда земельного участка",
                    "аренда земельного участка",
                ],
                "phase_needles": [
                    "Аренда ЗУ",
                    "Аренда земельного участка",
                    "земельного участка (ЗУ)",
                    "Инвестиционная. Аренда",
                    "аренда зу",
                ],
            },
        ),
        (
            "invest",
            "Ковенанты",
            "Готовый Продукт",
            {
                "level": 5.0,
                "names_any": [
                    "Рассмотрение и утверждение на инвестиционном комитете",
                    "инвестиционном комитете",
                    "Готовый продукт",
                    "готовый продукт",
                    "ГОТОВЫЙ ПРОДУКТ",
                    "Этап ГОТОВЫЙ ПРОДУКТ",
                    "Этап ГОТОВЫЙ",
                    "Инвестиционная. Готовый",
                ],
                "phase_needles": [
                    "Готовый продукт",
                    "готовый продукт",
                    "ГОТОВЫЙ ПРОДУКТ",
                    "Этап ГОТОВЫЙ ПРОДУКТ",
                    "Этап ГОТОВЫЙ",
                    "Инвестиционная. Готовый",
                    "инвестиционная. готовый",
                ],
            },
        ),
        (
            "invest",
            "Ковенанты",
            "ГПЗУ",
            {
                "level": 5.0,
                "parent_l2_contains": "Ковенанты",
                "names_any": [
                    "ГПЗУ",
                    "гпзу",
                    "Градплан",
                    "градостроительн",
                    "план территории",
                    "градостроительного плана",
                    "городской план",
                    "зонирования территории",
                    "Согласование ГП",
                    "( ГП,",
                    "ГП, АР",
                    "планировочных решений",
                    "Предварительные планировочные",
                    "Предварительные планировочные решения",
                    "Эскизный проект (",
                ],
                "phase_needles": [
                    "ГПЗУ",
                    "гпзу",
                    "градостроительн",
                    "план территории",
                    "Градплан",
                    "Инвестиционная. ГПЗУ",
                    "градостроительного плана",
                    "зонирования",
                    "Согласование ГП",
                    "( ГП,",
                    "ГП, АР",
                    "планировочных решений",
                    "Предварительные планировочные",
                    "Предварительные планировочные решения",
                ],
            },
        ),
        (
            "life",
            "Ковенанты",
            "Экспертиза стадия ст П",
            {
                "level": 5.0,
                "names_any": ["Экспертиза ПД", "Экспертиза", "экспертиза пд"],
                "parent_l2_contains": "Ковенанты",
                "phase_needles": ["Экспертиза стадия", "Экспертиза ПД", "Экспертиза стП"],
            },
        ),
        (
            "life",
            "Ковенанты",
            "КОМАНДА РП",
            {
                "level": 5.0,
                "names_any": [
                    "Подбор команды",
                    "Команда РП",
                    "КОМАНДА РП",
                    "Распоряжение Руководителя Холдинга",
                    "Руководителя Холдинга об утверждении",
                    "назначен руководител",
                    "проектную группу",
                ],
                "parent_l2_contains": "Ковенанты",
                "phase_needles": [
                    "Команда РП",
                    "КОМАНДА РП",
                    "Подбор команды",
                    "руководител проекта",
                    "назначени руководител",
                ],
            },
        ),
        (
            "life",
            "Ковенанты",
            "РС",
            {
                "level": 5.0,
                "names_any": [
                    "Разрешение РС",
                    "Разрешение на строительство РС",
                    "Разрешение на строительство (РС)",
                    "Разрешение на строительство",
                    "разрешение на строительство",
                    "РС:",
                    "(РС)",
                    "РЗУ РС",
                ],
                "names_exact_any": ["РС", "Рс", "рс"],
                "parent_l2_contains": "Ковенанты",
                "phase_needles": [
                    ". РС",
                    " РС",
                    "Разрешение на строительство",
                    "Разрешение на строительство РС",
                    "Инвестиционная. РС",
                    "инвестиционная. рс",
                    "Жизнь проекта. РС",
                    "РЗУ РС",
                ],
            },
        ),
        (
            "life",
            "Ковенанты",
            "РД (1вар)",
            {
                "level": 5.0,
                "names_any": [
                    "Стадия Рабочая Документация (РД)",
                    "Рабочая Документация (РД)",
                    "стадия РД",
                    "стадия рабочая документация",
                ],
                "parent_l2_contains": "Ковенанты",
                "phase_needles": ["РД (1", "1вар)", "1 вар)", "Рабочая Документация", "стадия РД"],
            },
        ),
    ]
    for phase, group, label, kw in specs_invest_msp:
        _msp_row(phase, group, label, kw, row_key=str(next(_rk)))

    def _fmtml(v: float) -> str:
        # Правки куратора 08.05.2026: финансовые показатели округляются до
        # десятых (1 знак после запятой), а не до сотых.
        return f"{v:.1f}".replace(".", ",")

    def _fmtml_otkl(v: float) -> str:
        """Отклонение «Выборка ДС»: явный +/− по знаку (Факт − План)."""
        if v > 0:
            return f"+{_fmtml(v)}"
        if v < 0:
            return f"-{_fmtml(abs(v))}"
        return _fmtml(v)

    rk_ds = str(next(_rk))
    pm, fm, om = _dev_matrix_bddds_totals_mln(ss, scope_label, project_data, mdf)
    if pm is None:
        add_row(
            "Финансы",
            effective_title(rk_ds, "Выборка ДС, млн руб."),
            "Н/Д",
            "Н/Д",
            "Н/Д",
            phase="life",
            row_key=rk_ds,
        )
    else:
        add_row(
            "Финансы",
            effective_title(rk_ds, "Выборка ДС, млн руб."),
            _fmtml(pm),
            _fmtml(fm),
            _fmtml_otkl(om),
            otkl_fact_lt_plan=bool(fm < pm),
            phase="life",
            row_key=rk_ds,
        )

    rk_tp = str(next(_rk))
    n_total, n_critical, n_critical_overdue, warn_t, _tessa_hint = _predpisaniya_combined(
        mdf, ss, scope_label
    )
    add_row(
        "ТЕССА",
        effective_title(rk_tp, "ПРЕДПИСАНИЯ"),
        n_total,
        n_critical,
        n_critical_overdue,
        warn_directives=warn_t,
        subcolumn_labels=dict(_DEV_MATRIX_PREDS_SUBCOLS),
        phase="life",
        row_key=rk_tp,
    )

    specs_invest_tail: List[Tuple[str, str, str, dict]] = [
        (
            "life",
            "ИРД",
            "Подготовительный этап (ТУ, ПРОЕКТ временные сети ЭЛ-ВО)",
            {
                "level": 4.0,
                "names_any": ["Электроснабжение:", "Электроснабжение"],
                "block_contains": "ИРД",
                "phase_needles": [
                    "Электроснабжение",
                    "временные сети ЭЛ",
                    "ЭЛ-ВО",
                    "Эл-во",
                    "сети ЭЛ",
                    "ИСЭ",
                    "инженерные сети: электро",
                    "ВНУТРИПЛОЩАДОЧНЫЕ ИНЖЕНЕРНЫЕ СЕТИ: ЭЛЕКТРО",
                ],
                # Не смешивать со столбцом «примыкания» (часто та же длинная строка «Подготовительный этап…»)
                "phase_exclude_needles": ["Примыкания", "УДС", "примыкания к удс"],
            },
        ),
        (
            "life",
            "ИРД",
            "Подготовительный этап (ТУ, ПРОЕКТ временные примыкания)",
            {
                "level": 4.0,
                "names_any": ["Примыкания к УДС:", "Примыкания к УДС"],
                "block_contains": "ИРД",
                "phase_needles": ["Примыкания к УДС", "временные примыкания"],
                "phase_exclude_needles": ["ЭЛ-ВО", "Электроснабжение", "сети ЭЛ", "ИСЭ"],
            },
        ),
        (
            "life",
            "Проектные работы",
            "ПОС (1 вар)",
            {
                "level": None,
                "names_any": [
                    "Согласование ПЗУ, ПОС, ПОДД с КРМО, МОЭСК, Мособлгаз, Мосавтодор",
                    "Согласование ПЗУ",
                    "ПОС, ПОДД",
                ],
                "block_contains": "ПРОЕКТ",
                "phase_needles": [
                    "ПОС (1 вар)",
                    "ПОС (1вар)",
                    "ПОС (1 этап)",
                    "ПОС (1этап)",
                    "ПОС (1 очер",
                    "Согласование ПЗУ",
                ],
            },
        ),
        (
            "life",
            "Ковенанты",
            "Начало финансирования СМР",
            {
                "level": 5.0,
                "name_contains": "Начало финансирования",
                "parent_l2_contains": "Ковенанты",
                "phase_needles": ["Начало финансирования"],
            },
        ),
        (
            "life",
            "Ковенанты",
            "Начало СМР",
            {
                "level": 5.0,
                "names_any": [
                    "Начало СМР",
                    "начало смр",
                    "СМР (начало)",
                    "смр (начало)",
                ],
                "parent_l2_contains": "Ковенанты",
                "phase_needles": ["Начало СМР", "СМР (начало)", "смр (начало)"],
            },
        ),
    ]
    for phase, group, label, kw in specs_invest_tail:
        _msp_row(phase, group, label, kw, row_key=str(next(_rk)))

    specs_life: List[Tuple[str, str, str, dict]] = [
        (
            "life",
            "Ковенанты",
            "ТЕХ.ПРИСОЕДИНЕНИЯ (ГАЗ, ЭЛ-ВО, ВОДА)",
            {
                "level": 5.0,
                "names_any": [
                    "Пуск электричества",
                    "Пуск газа",
                    "Пуск воды",
                    "Пуск водоснабжения",
                    "водоснабжения",
                    "ТЕХПРИСОЕДИНЕНИЯ",
                    "техприсоединения",
                    "ГАЗ, ЭП",
                    "ЭП, ВО",
                    "ВИС",
                    "вода",
                ],
                "parent_l2_contains": "Ковенанты",
                "phase_needles": [
                    "ТЕХ.ПРИСОЕДИНЕНИЯ",
                    "ТЕХПРИСОЕДИНЕНИЯ",
                    "ПРИСОЕДИНЕНИЯ (ГАЗ",
                    "ГАЗ, ЭЛ-ВО",
                    "ГАЗ, ЭП",
                    "ЭП, ВО",
                    "ЭП ВО",
                    "ГАЗ, ВОД",
                    "ВОДА",
                    "водоснабж",
                    "Пуск электричества",
                    "Пуск газа",
                    "Пуск вод",
                    "Жизнь проекта. ТЕХ",
                    "Жизнь проекта. ТЕХПРИСОЕДИНЕНИЯ",
                    "Инвестиционная. ТЕХ",
                ],
            },
        ),
        (
            "life",
            "Ковенанты",
            "ЗОС",
            {
                "level": 5.0,
                # Колонка «ЗОС» = веха-ковенант, названная именно «ЗОС» (или «ЗОС (участок №N)»),
                # а не СМР-задача «Получение Заключения о соответствии … (ЗОС)». У большинства
                # проектов их даты совпадают, но у Новорижского расходятся — нужен ковенант «ЗОС».
                # Поэтому не матчим по «Заключение о соответствии»/«(ЗОС)» в names_any.
                "names_exact_any": ["ЗОС"],
                "names_any": [
                    "ЗОС (участок",
                    "ЗОС  (участок",
                    "ЗОС - 1 этап",
                    "ЗОС - 2 этап",
                    "ЗОС -",
                ],
                "parent_l2_contains": "Ковенанты",
                # Фаза-фолбэк (срабатывает только если по имени ничего не найдено):
                # оставляем «Заключение о соответствии» для проектов без отдельной вехи «ЗОС».
                "phase_needles": [
                    ". ЗОС",
                    "Жизнь проекта. ЗОС",
                    "Инвестиционная. ЗОС",
                    "инвестиционная. зос",
                    "ЗОС (участок",
                    "Заключение о соответствии",
                ],
            },
        ),
        (
            "life",
            "Ковенанты",
            "РВ",
            {
                "level": 5.0,
                "names_any": [
                    "Разрешение на ввод в эксплуатацию (РВ)",
                    "Разрешение на ввод",
                    "ввод в эксплуатацию",
                    "Разрешение на ввод объекта",
                    "Разрешение на ввод в эксплуатацию",
                    "РВ - 1 этап",
                    "РВ - 2 этап",
                    "РВ -",
                ],
                "parent_l2_contains": "Ковенанты",
                "phase_needles": [
                    ". РВ",
                    " РВ",
                    "Разрешение на ввод",
                    "ввод в эксплуатацию",
                    "Разрешение на ввод объекта",
                    "Жизнь проекта. РВ",
                    "Инвестиционная. РВ",
                ],
            },
        ),
        (
            "life",
            "Ковенанты",
            "Право 1",
            {
                "level": 5.0,
                "names_any": [
                    "Право 1",
                    "Право1",
                    "право 1",
                    "Право 1 на",
                    "Право 1 - 1 этап",
                    "Право 1 - 2 этап",
                ],
                "parent_l2_contains": "Ковенанты",
                "phase_needles": [
                    "Право 1",
                    "Право1",
                    "право 1",
                    "Право 1 на",
                    "Жизнь проекта. Право 1",
                    "Инвестиционная. Право 1",
                ],
            },
        ),
        (
            "life",
            "Ковенанты",
            "Выкуп ЗУ",
            {
                "level": 5.0,
                "names_any": [
                    "Выкуп земельного участка",
                    "Выкуп ЗУ",
                    "Выкуп участка",
                    "выкуп земли",
                    "выкуп земельного",
                ],
                "parent_l2_contains": "Ковенанты",
                "phase_needles": [
                    "Выкуп ЗУ",
                    "Выкуп земельного",
                    "Выкуп участка",
                    "выкуп земли",
                    "Жизнь проекта. Выкуп",
                    "Инвестиционная. Выкуп",
                ],
            },
        ),
        (
            "life",
            "Ковенанты",
            "Право 2 на Застройщика",
            {
                "level": 5.0,
                "names_any": [
                    "Право 2 на Застройщика",
                    "Право 2",
                    "Право2",
                ],
                "parent_l2_contains": "Ковенанты",
                "phase_needles": [
                    "Право 2 на Застройщика",
                    "Право 2",
                    "Жизнь проекта. Право 2",
                    "Инвестиционная. Право 2",
                ],
            },
        ),
        (
            "life",
            "Ковенанты",
            "Передача БОКСОВ резидентам",
            {
                "level": 5.0,
                "names_any": [
                    "Передача боксов резидентам",
                    "Передача боксов",
                    "Передача бокс",
                    "боксов резидент",
                    "передачи резидент",
                    "передаче резидент",
                    "для передачи резидент",
                    "сформированная документация для передачи",
                    "по боксам)",
                    "БОНУСОВ",
                    "бонусов резидент",
                    "передача бонус",
                ],
                "parent_l2_contains": "Ковенанты",
                "phase_needles": [
                    "Передача боксов",
                    "передачи резидент",
                    "БОКСОВ",
                    "БОНУСОВ",
                    "бонусов резидент",
                    "Передача бонус",
                    "Жизнь проекта. Передача",
                    "Инвестиционная. Передача",
                ],
            },
        ),
    ]
    for phase, group, label, kw in specs_life:
        _msp_row(phase, group, label, kw, row_key=str(next(_rk)))

    try:
        next(_rk)
    except StopIteration:
        pass
    else:
        raise RuntimeError("_DEV_MATRIX_ROW_KEYS не совпадает с генерацией строк матрицы")

    return rows, scope_label or cap


# Streamlit Cloud: родительская страница иногда даёт iframe opacity/filter — сбрасываем.
_DEV_MATRIX_STREAMLIT_HOST_CSS = """
<style>
div[data-testid="stElementContainer"] iframe.dev-tz-matrix-iframe,
div[data-testid="stHtml"] iframe.dev-tz-matrix-iframe,
iframe.dev-tz-matrix-iframe[title="streamlit_components_v1"] {
  opacity: 1 !important;
  filter: none !important;
  mix-blend-mode: normal !important;
  background: transparent !important;
  display: block !important;
  margin: 0 !important;
  padding: 0 !important;
  border: none !important;
  vertical-align: top !important;
  overflow: hidden !important;
}
div[data-testid="stElementContainer"]:has(iframe.dev-tz-matrix-iframe) {
  margin-bottom: 0 !important;
  padding-bottom: 0 !important;
}
</style>
"""

_DEV_MATRIX_STREAMLIT_HOST_CSS_LIGHT = """
<style>
html body.gdrs-light-preview div[data-testid="stElementContainer"]:has(iframe[title="streamlit_components_v1"]) {
  background: transparent !important;
  opacity: 1 !important;
  filter: none !important;
}
html body.gdrs-light-preview iframe[title="streamlit_components_v1"] {
  opacity: 1 !important;
  filter: none !important;
  mix-blend-mode: normal !important;
  background: transparent !important;
}
</style>
"""

_DEV_TZ_MATRIX_CSS = """
<style>
/* Одна таблица: горизонтальный скролл целиком; колонка «Проект» не закреплена. */
.dev-tz-matrix-wrap {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  margin-bottom: 0.75rem;
  box-sizing: border-box;
  overflow-x: auto;
  overscroll-behavior-x: contain;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: thin;
  scrollbar-color: rgba(121, 154, 192, 0.5) #141820;
}
.dev-tz-matrix-wrap::-webkit-scrollbar {
  height: 10px;
}
.dev-tz-matrix-wrap::-webkit-scrollbar-track {
  background: #141820;
  border-radius: 5px;
}
.dev-tz-matrix-wrap::-webkit-scrollbar-thumb {
  background: rgba(121, 154, 192, 0.42);
  border-radius: 5px;
  border: 2px solid #141820;
}
.dev-tz-matrix-wrap::-webkit-scrollbar-thumb:hover {
  background: rgba(121, 154, 192, 0.65);
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide {
  border: 3px solid #ffffff;
  border-collapse: separate;
  border-spacing: 0;
  width: max-content !important;
  min-width: max(720px, 100%) !important;
  max-width: none !important;
  font-family: Inter, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 16px;
  font-weight: 700;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead th {
  border-width: 1px !important;
  border-style: solid !important;
  border-color: #5a6f82 !important;
  border-bottom-width: 2px !important;
  border-bottom-color: #6b7f94 !important;
  box-sizing: border-box;
  background-clip: padding-box;
  position: relative !important;
  top: auto !important;
  white-space: normal !important;
  overflow: visible !important;
  text-overflow: clip !important;
  max-width: none !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide tbody td {
  border-width: 1px !important;
  border-style: solid !important;
  border-color: #5a6f82 !important;
  vertical-align: middle !important;
  text-align: center !important;
  font-size: 16px;
  font-weight: 700;
  line-height: 1.45;
  padding: 14px 12px !important;
  color: #fafafa;
  background-color: #0c1219 !important;
  background-clip: padding-box;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide tbody tr:hover td {
  background: inherit;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide tbody tr:nth-child(even) td {
  background: inherit;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead th.dev-tz-th-project {
  text-align: center !important;
  vertical-align: middle !important;
  font-weight: 700;
  font-size: 17px;
  padding: 12px 14px;
  color: #f0f4f8;
  box-sizing: border-box;
  background: #1a3328 !important;
  border-top: 3px solid #ffffff !important;
  border-left: 3px solid #ffffff !important;
  border-right: 3px solid #ffffff !important;
  border-bottom: 3px solid #ffffff !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-ghead {
  text-align: center !important;
  vertical-align: middle !important;
  font-weight: 700;
  font-size: 18px;
  padding: 12px 14px;
  background: linear-gradient(180deg, rgba(34, 139, 34, 0.35) 0%, rgba(25, 90, 25, 0.25) 100%) !important;
  color: #f0f4f8;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead tr:first-child th.dev-tz-ghead {
  border-top: 3px solid #ffffff !important;
  border-bottom: 3px solid #ffffff !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead tr:first-child th.dev-tz-ghead-inv {
  border-right: 3px solid #ffffff !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-ghead-life {
  text-align: center !important;
  vertical-align: middle !important;
  font-weight: 700;
  font-size: 18px;
  padding: 12px 14px;
  background: linear-gradient(180deg, rgba(92, 100, 115, 0.58) 0%, rgba(55, 61, 72, 0.48) 100%) !important;
  color: #f0f4f8 !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead tr:first-child th.dev-tz-ghead-life {
  border-left: 3px solid #ffffff !important;
  border-right: 3px solid #ffffff !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-milestone {
  text-align: center !important;
  vertical-align: middle !important;
  font-size: 17px;
  font-weight: 700;
  line-height: 1.45;
  min-width: 6.5em;
  max-width: none !important;
  white-space: normal !important;
  word-break: break-word;
  overflow-wrap: anywhere;
  hyphens: manual;
  overflow: visible !important;
  text-overflow: clip !important;
  padding: 12px 10px;
  color: #f0f4f8;
  background: rgba(26, 28, 35, 0.92) !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-sub {
  text-align: center !important;
  vertical-align: middle !important;
  font-size: 16px;
  font-weight: 700;
  color: #f0f4f8;
  min-width: 4.5em;
  max-width: none !important;
  white-space: normal !important;
  word-break: break-word;
  overflow-wrap: anywhere;
  overflow: visible !important;
  text-overflow: clip !important;
  padding: 10px 8px;
  background: rgba(22, 24, 32, 0.95) !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-milestone.dev-tz-inv-block,
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-sub.dev-tz-inv-block {
  background: linear-gradient(180deg, rgba(34, 139, 34, 0.35) 0%, rgba(25, 90, 25, 0.25) 100%) !important;
  color: #f0f4f8 !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-sub.dev-tz-inv-block {
  text-align: center !important;
  vertical-align: middle !important;
  font-weight: 700;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-milestone.dev-tz-life-block,
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-sub.dev-tz-life-block {
  background: linear-gradient(180deg, rgba(92, 100, 115, 0.58) 0%, rgba(55, 61, 72, 0.48) 100%) !important;
  color: #f0f4f8 !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-sub.dev-tz-life-block {
  text-align: center !important;
  vertical-align: middle !important;
  font-weight: 700;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide td.dev-tz-td-project {
  text-align: left !important;
  font-weight: 700;
  font-size: 18px;
  padding: 14px 12px !important;
  background: #161f2b !important;
  color: #f0f4f8;
  word-wrap: break-word;
  overflow-wrap: anywhere;
  vertical-align: middle !important;
  border-right: 3px solid #ffffff !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide td.dev-tz-text-pct-done {
  color: #f09355 !important;
  font-weight: 700 !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead th.dev-tz-sortable {
  cursor: pointer;
  user-select: none;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead th.dev-tz-sortable:hover {
  filter: brightness(1.08);
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide td.dev-tz-otkl-ok {
  color: #28a745 !important;
  font-weight: 700 !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide td.dev-tz-otkl-bad {
  color: #d9534f !important;
  font-weight: 700 !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide td.dev-tz-date-vert {
  writing-mode: vertical-rl;
  text-orientation: mixed;
  max-height: 7.5em;
  white-space: nowrap;
  vertical-align: middle;
  text-align: center;
  padding: 8px 4px !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide td.dev-tz-directives-warn {
  background: rgba(234, 88, 12, 0.15) !important;
}
/* Блок вехи (План / Факт / Откл.): толстая непрозрачная белая рамка (без rgba — иначе
   на фоне оранжевых дат граница визуально «персиковая») */
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-milestone.dev-tz-ms-block {
  border-left: 3px solid #ffffff !important;
  border-right: 3px solid #ffffff !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-sub.dev-tz-ms-first,
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide td.dev-tz-ms-first {
  border-left: 3px solid #ffffff !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-sub.dev-tz-ms-last,
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide td.dev-tz-ms-last {
  border-right: 3px solid #ffffff !important;
}
/* Дублируем белые разделители через inset box-shadow (устойчиво на Streamlit Cloud). */
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-milestone.dev-tz-ms-block {
  box-shadow: inset 3px 0 0 #ffffff, inset -3px 0 0 #ffffff;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-sub.dev-tz-ms-first,
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide td.dev-tz-ms-first {
  box-shadow: inset 3px 0 0 #ffffff;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-sub.dev-tz-ms-last,
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide td.dev-tz-ms-last {
  box-shadow: inset -3px 0 0 #ffffff;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead th.dev-tz-th-project,
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide tbody td.dev-tz-td-project {
  box-shadow: inset -3px 0 0 #ffffff;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead tr:first-child th.dev-tz-ghead {
  box-shadow: inset 0 3px 0 #ffffff, inset 0 -3px 0 #ffffff;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead tr:first-child th.dev-tz-ghead-inv {
  box-shadow: inset -3px 0 0 #ffffff, inset 0 3px 0 #ffffff, inset 0 -3px 0 #ffffff;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead tr:first-child th.dev-tz-ghead-life {
  box-shadow: inset 3px 0 0 #ffffff, inset -3px 0 0 #ffffff, inset 0 3px 0 #ffffff, inset 0 -3px 0 #ffffff;
}
</style>
"""

_DEV_TZ_MATRIX_CSS_LIGHT = """
<style>
.dev-tz-matrix-wrap {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  margin-bottom: 0.75rem;
  box-sizing: border-box;
  overflow-x: auto;
  overscroll-behavior-x: contain;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: thin;
  scrollbar-color: #64748b #e5e7eb;
}
.dev-tz-matrix-wrap::-webkit-scrollbar { height: 10px; }
.dev-tz-matrix-wrap::-webkit-scrollbar-track { background: #e5e7eb; border-radius: 5px; }
.dev-tz-matrix-wrap::-webkit-scrollbar-thumb {
  background: #94a3b8; border-radius: 5px; border: 2px solid #e5e7eb;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide {
  border: 3px solid #94a3b8;
  border-collapse: separate;
  border-spacing: 0;
  width: max-content !important;
  min-width: max(720px, 100%) !important;
  max-width: none !important;
  font-family: Inter, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 16px;
  font-weight: 700;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead th {
  border-width: 1px !important;
  border-style: solid !important;
  border-color: #cbd5e1 !important;
  border-bottom-width: 2px !important;
  border-bottom-color: #94a3b8 !important;
  box-sizing: border-box;
  background-clip: padding-box;
  position: relative !important;
  top: auto !important;
  white-space: normal !important;
  overflow: visible !important;
  text-overflow: clip !important;
  max-width: none !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide tbody td {
  border-width: 1px !important;
  border-style: solid !important;
  border-color: #cbd5e1 !important;
  vertical-align: middle !important;
  text-align: center !important;
  font-size: 16px;
  font-weight: 700;
  line-height: 1.45;
  padding: 14px 12px !important;
  color: #111827;
  background-color: #ffffff !important;
  background-clip: padding-box;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead th.dev-tz-th-project {
  text-align: center !important;
  vertical-align: middle !important;
  font-weight: 700;
  font-size: 17px;
  padding: 12px 14px;
  color: #111827;
  background: #e8f0fe !important;
  border-top: 3px solid #94a3b8 !important;
  border-left: 3px solid #94a3b8 !important;
  border-right: 3px solid #94a3b8 !important;
  border-bottom: 3px solid #94a3b8 !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-ghead {
  text-align: center !important;
  vertical-align: middle !important;
  font-weight: 700;
  font-size: 18px;
  padding: 12px 14px;
  background: #dcfce7 !important;
  color: #14532d;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead tr:first-child th.dev-tz-ghead {
  border-top: 3px solid #94a3b8 !important;
  border-bottom: 3px solid #94a3b8 !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead tr:first-child th.dev-tz-ghead-inv {
  border-right: 3px solid #94a3b8 !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-ghead-life {
  text-align: center !important;
  vertical-align: middle !important;
  font-weight: 700;
  font-size: 18px;
  padding: 12px 14px;
  background: #e2e8f0 !important;
  color: #1f2937 !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead tr:first-child th.dev-tz-ghead-life {
  border-left: 3px solid #94a3b8 !important;
  border-right: 3px solid #94a3b8 !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-milestone {
  text-align: center !important;
  vertical-align: middle !important;
  font-size: 17px;
  font-weight: 700;
  line-height: 1.45;
  min-width: 6.5em;
  max-width: none !important;
  white-space: normal !important;
  word-break: break-word;
  overflow-wrap: anywhere;
  padding: 12px 10px;
  color: #111827;
  background: #f3f4f6 !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-sub {
  text-align: center !important;
  vertical-align: middle !important;
  font-size: 16px;
  font-weight: 700;
  color: #111827;
  min-width: 4.5em;
  padding: 10px 8px;
  background: #f9fafb !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-milestone.dev-tz-inv-block,
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-sub.dev-tz-inv-block {
  background: #dcfce7 !important;
  color: #14532d !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-milestone.dev-tz-life-block,
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-sub.dev-tz-life-block {
  background: #e2e8f0 !important;
  color: #1f2937 !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide td.dev-tz-td-project {
  text-align: left !important;
  font-weight: 700;
  font-size: 18px;
  padding: 14px 12px !important;
  background: #f9fafb !important;
  color: #111827;
  word-wrap: break-word;
  overflow-wrap: anywhere;
  vertical-align: middle !important;
  border-right: 3px solid #94a3b8 !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide td.dev-tz-text-pct-done {
  color: #ea580c !important;
  font-weight: 700 !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide td.dev-tz-otkl-ok {
  color: #15803d !important;
  font-weight: 700 !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide td.dev-tz-otkl-bad {
  color: #b91c1c !important;
  font-weight: 700 !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-milestone.dev-tz-ms-block {
  border-left: 3px solid #94a3b8 !important;
  border-right: 3px solid #94a3b8 !important;
  box-shadow: inset 3px 0 0 #94a3b8, inset -3px 0 0 #94a3b8;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-sub.dev-tz-ms-first,
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide td.dev-tz-ms-first {
  border-left: 3px solid #94a3b8 !important;
  box-shadow: inset 3px 0 0 #94a3b8;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-sub.dev-tz-ms-last,
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide td.dev-tz-ms-last {
  border-right: 3px solid #94a3b8 !important;
  box-shadow: inset -3px 0 0 #94a3b8;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead th.dev-tz-th-project,
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide tbody td.dev-tz-td-project {
  box-shadow: inset -3px 0 0 #94a3b8;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide td.dev-tz-directives-warn {
  background: rgba(234, 88, 12, 0.12) !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead th.dev-tz-sortable {
  cursor: pointer;
  user-select: none;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead th.dev-tz-sortable:hover {
  filter: brightness(0.97);
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide tbody tr:hover td {
  background: inherit;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide tbody tr:nth-child(even) td {
  background: inherit;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide td.dev-tz-date-vert {
  writing-mode: vertical-rl;
  text-orientation: mixed;
  max-height: 7.5em;
  white-space: nowrap;
  vertical-align: middle;
  text-align: center;
  padding: 8px 4px !important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead tr:first-child th.dev-tz-ghead {
  box-shadow: inset 0 3px 0 #94a3b8, inset 0 -3px 0 #94a3b8;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead tr:first-child th.dev-tz-ghead-inv {
  box-shadow: inset -3px 0 0 #94a3b8, inset 0 3px 0 #94a3b8, inset 0 -3px 0 #94a3b8;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead tr:first-child th.dev-tz-ghead-life {
  box-shadow: inset 3px 0 0 #94a3b8, inset -3px 0 0 #94a3b8, inset 0 3px 0 #94a3b8, inset 0 -3px 0 #94a3b8;
}
</style>
"""


def _dev_tz_matrix_css_raw(theme: str = "dark") -> str:
    css = _DEV_TZ_MATRIX_CSS_LIGHT if str(theme or "").strip().lower() == "light" else _DEV_TZ_MATRIX_CSS
    return css.replace("<style>", "").replace("</style>", "")


def _dev_tz_matrix_iframe_sticky_css(theme: str = "dark") -> str:
    if str(theme or "").strip().lower() == "light":
        return """
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:#ffffff;color:#111827;overflow:hidden;
  opacity:1!important;filter:none!important;isolation:isolate}
.dev-tz-matrix-wrap{width:100%;max-width:100%;margin:0!important;padding:0!important;
  overflow-x:auto;overflow-y:hidden;
  -webkit-overflow-scrolling:touch;overscroll-behavior-x:contain;
  scrollbar-width:thin;scrollbar-color:#64748b #e5e7eb}
.dev-tz-matrix-wrap::-webkit-scrollbar{height:10px}
.dev-tz-matrix-wrap::-webkit-scrollbar-track{background:#e5e7eb;border-radius:5px}
.dev-tz-matrix-wrap::-webkit-scrollbar-thumb{background:#94a3b8;border-radius:5px;border:2px solid #e5e7eb}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide tbody td{background-color:#ffffff!important;color:#111827!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead th.dev-tz-th-project{
  z-index:5!important;background:#e8f0fe!important;color:#111827!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide tbody td.dev-tz-td-project{
  z-index:4!important;background:#f9fafb!important;color:#111827!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead th.dev-tz-th-project,
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide tbody td.dev-tz-td-project{
  position:sticky!important;left:0!important;
  border-right:3px solid #94a3b8!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide{
  border-collapse:separate!important;border-spacing:0!important;
  width:max-content!important;min-width:100%!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead th.dev-tz-th-project{
  border-top:3px solid #94a3b8!important;border-left:3px solid #94a3b8!important;
  border-bottom:3px solid #94a3b8!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-ghead,
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-ghead-life{
  font-size:18px!important;padding:12px 14px!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-milestone{
  font-size:17px!important;padding:12px 10px!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-sub{
  font-size:16px!important;padding:10px 8px!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-milestone.dev-tz-ms-block,
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-sub.dev-tz-ms-first,
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide td.dev-tz-ms-first{
  border-left:3px solid #94a3b8!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-sub.dev-tz-ms-last,
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide td.dev-tz-ms-last{
  border-right:3px solid #94a3b8!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead tr:first-child th.dev-tz-ghead{
  border-top:3px solid #94a3b8!important;border-bottom:3px solid #94a3b8!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead tr:first-child th.dev-tz-ghead-inv{
  border-right:3px solid #94a3b8!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead tr:first-child th.dev-tz-ghead-life{
  border-left:3px solid #94a3b8!important;border-right:3px solid #94a3b8!important}
"""
    return """
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:transparent;color:#e6edf3;overflow:hidden;
  opacity:1!important;filter:none!important;isolation:isolate}
.dev-tz-matrix-wrap{width:100%;max-width:100%;margin:0!important;padding:0!important;
  overflow-x:auto;overflow-y:hidden;
  -webkit-overflow-scrolling:touch;overscroll-behavior-x:contain;
  scrollbar-width:thin;scrollbar-color:rgba(121,154,192,0.5) transparent}
.dev-tz-matrix-wrap::-webkit-scrollbar{height:10px}
.dev-tz-matrix-wrap::-webkit-scrollbar-track{background:transparent;border-radius:5px}
.dev-tz-matrix-wrap::-webkit-scrollbar-thumb{background:rgba(121,154,192,0.42);border-radius:5px;border:2px solid #141820}
.dev-tz-matrix-wrap::-webkit-scrollbar-thumb:hover{background:rgba(121,154,192,0.65)}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide{
  border-collapse:separate!important;border-spacing:0!important;
  width:max-content!important;min-width:100%!important;
  font-family:Inter,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif!important;
  font-size:16px!important;font-weight:700!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide tbody td{
  font-size:16px!important;line-height:1.45!important;padding:14px 12px!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead th.dev-tz-th-project{
  font-size:17px!important;padding:12px 14px!important;color:#f0f4f8!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide tbody td.dev-tz-td-project{
  font-size:18px!important;padding:14px 12px!important;color:#f0f4f8!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-ghead,
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-ghead-life{
  font-size:18px!important;padding:12px 14px!important;color:#f0f4f8!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-milestone{
  font-size:17px!important;padding:12px 10px!important;color:#f0f4f8!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-sub{
  font-size:16px!important;padding:10px 8px!important;color:#f0f4f8!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead th,
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide tbody td{
  border-width:1px!important;border-style:solid!important;
  border-color:#5a6f82!important;background-clip:padding-box!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide tbody td{
  background-color:#0c1219!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-milestone.dev-tz-ms-block{
  border-left:3px solid #ffffff!important;
  border-right:3px solid #ffffff!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-sub.dev-tz-ms-first,
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide td.dev-tz-ms-first{
  border-left:3px solid #ffffff!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-sub.dev-tz-ms-last,
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide td.dev-tz-ms-last{
  border-right:3px solid #ffffff!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead tr:first-child th.dev-tz-ghead{
  border-top:3px solid #ffffff!important;border-bottom:3px solid #ffffff!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead tr:first-child th.dev-tz-ghead-inv{
  border-right:3px solid #ffffff!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead tr:first-child th.dev-tz-ghead-life{
  border-left:3px solid #ffffff!important;border-right:3px solid #ffffff!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead th.dev-tz-th-project,
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide tbody td.dev-tz-td-project{
  position:sticky!important;left:0!important;
  border-right:3px solid #ffffff!important;
}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead th.dev-tz-th-project{
  border-top:3px solid #ffffff!important;border-left:3px solid #ffffff!important;
  border-bottom:3px solid #ffffff!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead th.dev-tz-th-project{
  z-index:5!important;background:#1a3328!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide tbody td.dev-tz-td-project{
  z-index:4!important;background:#161f2b!important}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-milestone.dev-tz-ms-block{
  box-shadow:inset 3px 0 0 #fff,inset -3px 0 0 #fff}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-sub.dev-tz-ms-first,
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide td.dev-tz-ms-first{box-shadow:inset 3px 0 0 #fff}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide th.dev-tz-sub.dev-tz-ms-last,
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide td.dev-tz-ms-last{box-shadow:inset -3px 0 0 #fff}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead th.dev-tz-th-project,
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide tbody td.dev-tz-td-project{box-shadow:inset -3px 0 0 #fff}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead tr:first-child th.dev-tz-ghead{
  box-shadow:inset 0 3px 0 #fff,inset 0 -3px 0 #fff}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead tr:first-child th.dev-tz-ghead-inv{
  box-shadow:inset -3px 0 0 #fff,inset 0 3px 0 #fff,inset 0 -3px 0 #fff}
.dev-tz-matrix-wrap table.rendered-table.dev-tz-wide thead tr:first-child th.dev-tz-ghead-life{
  box-shadow:inset 3px 0 0 #fff,inset -3px 0 0 #fff,inset 0 3px 0 #fff,inset 0 -3px 0 #fff}
"""


def _dev_tz_matrix_row_key(r: Dict[str, Any]) -> Tuple[str, str]:
    """Стабильный ключ строки матрицы для сопоставления блоков разных проектов."""
    rid = str(r.get("row_key") or "").strip()
    if rid:
        return ("__devmx_key__", rid)
    return (str(r.get("group") or ""), str(r.get("label") or ""))


def _dev_tz_matrix_cell_classes(
    r: Dict[str, Any],
    col: str,
    *,
    vertical_dates: bool,
) -> str:
    """CSS-классы для ячейки План / Факт / Откл."""
    parts: List[str] = []
    v = r.get(col) or ""
    subcols = r.get("subcolumn_labels")
    is_special = bool(subcols)

    if not is_special:
        if bool(r.get("pct_complete_100")) and col in ("plan", "fact"):
            parts.append("dev-tz-text-pct-done")
        if _dev_tz_apply_vert_date(vertical_dates, col, v):
            parts.append("dev-tz-date-vert")
        if col == "otkl":
            dd = _parse_otkl_days_display(v)
            if dd is not None:
                parts.append("dev-tz-otkl-ok" if dd >= 0 else "dev-tz-otkl-bad")
            else:
                mv = _parse_otkl_mln_display(v)
                if mv is not None:
                    parts.append("dev-tz-otkl-ok" if mv >= 0 else "dev-tz-otkl-bad")
        return " ".join(parts).strip()

    # Блоки «ПРЕДПИСАНИЯ» и «Выборка ДС»: белый текст, цвет только у отклонений.
    otkl_lbl = str((subcols or {}).get("otkl") or "").lower()
    is_preds = "предпис" in otkl_lbl
    if col in ("plan", "fact"):
        return ""
    if col == "otkl":
        if is_preds:
            try:
                if int(str(v or "").strip()) > 0:
                    parts.append("dev-tz-otkl-bad")
            except (TypeError, ValueError):
                pass
        else:
            mv = _parse_otkl_mln_display(v)
            if mv is not None:
                parts.append("dev-tz-otkl-ok" if mv >= 0 else "dev-tz-otkl-bad")
            elif bool(r.get("otkl_fact_lt_plan")):
                parts.append("dev-tz-otkl-bad")
            else:
                sv = str(v or "").strip()
                if sv and sv.upper() not in ("Н/Д", "N/D", "—", "-"):
                    parts.append("dev-tz-otkl-ok")
    return " ".join(parts).strip()


# Кнопка «на весь экран» в iframe-матрице — Fullscreen API + fallback для iOS/Safari (нет Fullscreen у div).
_MATRIX_IFRAME_FULLSCREEN_SHELL_CSS = """
.matrix-fs-root{position:relative;display:flex;flex-direction:column;width:100%;min-height:0}
.matrix-fs-topbar{position:absolute;top:6px;right:6px;z-index:30;display:flex;justify-content:flex-end;
  align-items:center;padding:0;min-height:0;pointer-events:none}
.matrix-fs-topbar .matrix-fs-btn{pointer-events:auto}
.matrix-fs-body{flex:0 0 auto;width:100%}
.matrix-fs-btn{
  box-sizing:border-box;width:32px;height:32px;margin:0;padding:0;
  border:1px solid rgba(68,84,108,0.55);border-radius:2px;
  background:rgba(35,43,56,0.96);color:#e8eef5;
  cursor:pointer;font-size:17px;line-height:1;text-align:center;
  touch-action:manipulation;-webkit-tap-highlight-color:transparent;
}
.matrix-fs-btn:hover{background:rgba(55,65,82,0.98);color:#fff;border-color:rgba(121,154,192,0.55)}
.matrix-fs-btn:focus-visible{outline:2px solid rgba(121,154,192,0.75);outline-offset:1px}
#matrix-fs-root:fullscreen,#matrix-fs-root:-webkit-full-screen,#matrix-fs-root:-moz-full-screen{
  min-height:100%!important;
  background:#0e1520;padding:10px;box-sizing:border-box;
  width:100vw!important;height:100vh!important;max-height:-webkit-fill-available!important;
  overflow:hidden!important;display:flex!important;flex-direction:column!important;
}
#matrix-fs-root:fullscreen .matrix-fs-body:not(.dev-tz-fs-body):not(.cp-body-stack),
#matrix-fs-root:-webkit-full-screen .matrix-fs-body:not(.dev-tz-fs-body):not(.cp-body-stack),
#matrix-fs-root:-moz-full-screen .matrix-fs-body:not(.dev-tz-fs-body):not(.cp-body-stack){
  flex:1 1 auto;min-height:0;overflow:hidden!important;
}

#matrix-fs-root:fullscreen .gdrs-table-wrap,
#matrix-fs-root:-webkit-full-screen .gdrs-table-wrap,
#matrix-fs-root:-moz-full-screen .gdrs-table-wrap{
  max-height:calc(100vh - 64px)!important;max-height:calc(100dvh - 64px)!important;
  overflow:auto!important;-webkit-overflow-scrolling:touch!important;
}
#matrix-fs-root.matrix-fs-pseudo-on .gdrs-table-wrap,
#matrix-fs-pseudo-shell.dev-tz-fs-shell .gdrs-table-wrap{
  max-height:calc(100% - 48px)!important;overflow:auto!important;-webkit-overflow-scrolling:touch!important;
}
#matrix-fs-root:fullscreen .matrix-fs-body.gdrs-fs-body,
#matrix-fs-root:-webkit-full-screen .matrix-fs-body.gdrs-fs-body,
#matrix-fs-root:-moz-full-screen .matrix-fs-body.gdrs-fs-body,
#matrix-fs-root.matrix-fs-pseudo-on .matrix-fs-body.gdrs-fs-body,
#matrix-fs-pseudo-shell.dev-tz-fs-shell .matrix-fs-body.gdrs-fs-body{
  position:relative!important;flex:1 1 auto!important;min-height:0!important;width:100%!important;
  overflow:auto!important;-webkit-overflow-scrolling:touch!important;box-sizing:border-box!important;
}
#matrix-fs-root:fullscreen .cp-table-wrap,
#matrix-fs-root:-webkit-full-screen .cp-table-wrap,
#matrix-fs-root:-moz-full-screen .cp-table-wrap{
  max-height:calc(100vh - 64px)!important;max-height:calc(100dvh - 64px)!important;
  overflow:auto!important;-webkit-overflow-scrolling:touch!important;
}
/* Fallback без Fullscreen API: разворот на весь iframe (если родитель недоступен). */
#matrix-fs-root.matrix-fs-pseudo-on{
  position:fixed!important;top:0!important;left:0!important;right:0!important;bottom:0!important;
  width:100%!important;height:100%!important;max-height:-webkit-fill-available!important;
  z-index:2147483647!important;background:#0e1520!important;padding:10px!important;
  box-sizing:border-box!important;display:flex!important;flex-direction:column!important;
  overflow:hidden!important;
}
#matrix-fs-root.matrix-fs-pseudo-on .matrix-fs-body:not(.dev-tz-fs-body):not(.cp-body-stack){
  flex:1 1 auto;min-height:0;overflow:hidden!important;}
#matrix-fs-root.matrix-fs-pseudo-on .cp-table-wrap{
  max-height:calc(100% - 48px)!important;overflow:auto!important;-webkit-overflow-scrolling:touch!important;
}
/* Контрольные точки: несколько таблиц в одном iframe */
.cp-tables-stack{display:flex;flex-direction:column;align-items:stretch;gap:40px;width:100%;
  padding:8px 8px 18px;box-sizing:border-box}
.cp-table-wrap.cp-table-block{
  background:#121a24;border:2px solid rgba(255,255,255,0.42);border-radius:10px;
  padding:12px 14px;box-shadow:0 6px 18px rgba(0,0,0,0.42);isolation:isolate}
.cp-table-wrap.cp-table-block+.cp-table-wrap.cp-table-block{margin-top:0}
.matrix-fs-body.cp-body-stack{overflow-x:hidden!important;overflow-y:auto!important;
  -webkit-overflow-scrolling:touch}
/* Полноэкран — как «Девелоперские проекты»: 100% ширина, центр по вертикали (JS) */
#matrix-fs-root:fullscreen .matrix-fs-body.cp-body-stack,
#matrix-fs-root:-webkit-full-screen .matrix-fs-body.cp-body-stack,
#matrix-fs-root:-moz-full-screen .matrix-fs-body.cp-body-stack,
#matrix-fs-root.matrix-fs-pseudo-on .matrix-fs-body.cp-body-stack,
#matrix-fs-pseudo-shell.dev-tz-fs-shell .matrix-fs-body.cp-body-stack{
  position:relative!important;flex:1 1 auto!important;min-height:0!important;width:100%!important;
  overflow:auto!important;-webkit-overflow-scrolling:touch!important;box-sizing:border-box!important}
#matrix-fs-root:fullscreen .matrix-fs-body.cp-body-stack .cp-tables-stack,
#matrix-fs-root:-webkit-full-screen .matrix-fs-body.cp-body-stack .cp-tables-stack,
#matrix-fs-root:-moz-full-screen .matrix-fs-body.cp-body-stack .cp-tables-stack,
#matrix-fs-root.matrix-fs-pseudo-on .matrix-fs-body.cp-body-stack .cp-tables-stack,
#matrix-fs-pseudo-shell.dev-tz-fs-shell .cp-tables-stack{
  width:100%!important;max-width:100%!important;min-width:0!important;margin-left:0!important;margin-right:0!important;
  box-sizing:border-box!important;align-items:stretch!important;padding-left:0!important;padding-right:0!important}
#matrix-fs-root:fullscreen .matrix-fs-body.cp-body-stack .cp-table-wrap,
#matrix-fs-root:-webkit-full-screen .matrix-fs-body.cp-body-stack .cp-table-wrap,
#matrix-fs-root:-moz-full-screen .matrix-fs-body.cp-body-stack .cp-table-wrap,
#matrix-fs-root.matrix-fs-pseudo-on .matrix-fs-body.cp-body-stack .cp-table-wrap,
#matrix-fs-pseudo-shell.dev-tz-fs-shell .cp-table-wrap{
  width:100%!important;max-width:100%!important;min-width:0!important;margin-left:0!important;margin-right:0!important;
  box-sizing:border-box!important;overflow-x:auto!important;overflow-y:visible!important;max-height:none!important}
#matrix-fs-root:fullscreen .matrix-fs-body.cp-body-stack .cp-table-wrap table.rendered-table,
#matrix-fs-root:-webkit-full-screen .matrix-fs-body.cp-body-stack .cp-table-wrap table.rendered-table,
#matrix-fs-root:-moz-full-screen .matrix-fs-body.cp-body-stack .cp-table-wrap table.rendered-table,
#matrix-fs-root.matrix-fs-pseudo-on .matrix-fs-body.cp-body-stack .cp-table-wrap table.rendered-table,
#matrix-fs-pseudo-shell.dev-tz-fs-shell .cp-table-wrap table.rendered-table{
  width:100%!important;min-width:100%!important;max-width:100%!important}
/* Девелоперские проекты: полноэкран — ширина 100% (вертикальный центр через JS margin-top) */
#matrix-fs-root:fullscreen .matrix-fs-body.dev-tz-fs-body,
#matrix-fs-root:-webkit-full-screen .matrix-fs-body.dev-tz-fs-body,
#matrix-fs-root:-moz-full-screen .matrix-fs-body.dev-tz-fs-body,
#matrix-fs-root.matrix-fs-pseudo-on .matrix-fs-body.dev-tz-fs-body,
#matrix-fs-pseudo-shell.dev-tz-fs-shell .matrix-fs-body.dev-tz-fs-body{
  position:relative!important;flex:1 1 auto!important;min-height:0!important;width:100%!important;
  overflow:auto!important;-webkit-overflow-scrolling:touch!important;box-sizing:border-box!important}
#matrix-fs-root:fullscreen .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap,
#matrix-fs-root:-webkit-full-screen .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap,
#matrix-fs-root:-moz-full-screen .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap,
#matrix-fs-root.matrix-fs-pseudo-on .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap,
#matrix-fs-pseudo-shell.dev-tz-fs-shell .dev-tz-matrix-wrap{
  width:100%!important;max-width:100%!important;min-width:0!important;margin-left:0!important;margin-right:0!important;
  box-sizing:border-box!important;overflow-x:auto!important;overflow-y:visible!important}
#matrix-fs-root:fullscreen .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap table.rendered-table.dev-tz-wide,
#matrix-fs-root:-webkit-full-screen .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap table.rendered-table.dev-tz-wide,
#matrix-fs-root:-moz-full-screen .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap table.rendered-table.dev-tz-wide,
#matrix-fs-root.matrix-fs-pseudo-on .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap table.rendered-table.dev-tz-wide,
#matrix-fs-pseudo-shell.dev-tz-fs-shell .dev-tz-matrix-wrap table.rendered-table.dev-tz-wide{
  width:max-content!important;min-width:100%!important;max-width:none!important}
/* Девелоперские проекты: без переносов в Проект / План / Факт / Откл. */
#matrix-fs-root:fullscreen .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap th.dev-tz-th-project,
#matrix-fs-root:fullscreen .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap td.dev-tz-td-project,
#matrix-fs-root:fullscreen .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap th.dev-tz-sub,
#matrix-fs-root:fullscreen .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap td.dev-tz-ms-first,
#matrix-fs-root:fullscreen .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap td.dev-tz-ms-fact,
#matrix-fs-root:fullscreen .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap td.dev-tz-ms-last,
#matrix-fs-root:-webkit-full-screen .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap th.dev-tz-th-project,
#matrix-fs-root:-webkit-full-screen .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap td.dev-tz-td-project,
#matrix-fs-root:-webkit-full-screen .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap th.dev-tz-sub,
#matrix-fs-root:-webkit-full-screen .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap td.dev-tz-ms-first,
#matrix-fs-root:-webkit-full-screen .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap td.dev-tz-ms-fact,
#matrix-fs-root:-webkit-full-screen .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap td.dev-tz-ms-last,
#matrix-fs-root:-moz-full-screen .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap th.dev-tz-th-project,
#matrix-fs-root:-moz-full-screen .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap td.dev-tz-td-project,
#matrix-fs-root:-moz-full-screen .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap th.dev-tz-sub,
#matrix-fs-root:-moz-full-screen .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap td.dev-tz-ms-first,
#matrix-fs-root:-moz-full-screen .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap td.dev-tz-ms-fact,
#matrix-fs-root:-moz-full-screen .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap td.dev-tz-ms-last,
#matrix-fs-root.matrix-fs-pseudo-on .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap th.dev-tz-th-project,
#matrix-fs-root.matrix-fs-pseudo-on .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap td.dev-tz-td-project,
#matrix-fs-root.matrix-fs-pseudo-on .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap th.dev-tz-sub,
#matrix-fs-root.matrix-fs-pseudo-on .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap td.dev-tz-ms-first,
#matrix-fs-root.matrix-fs-pseudo-on .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap td.dev-tz-ms-fact,
#matrix-fs-root.matrix-fs-pseudo-on .matrix-fs-body.dev-tz-fs-body .dev-tz-matrix-wrap td.dev-tz-ms-last,
#matrix-fs-pseudo-shell.dev-tz-fs-shell .dev-tz-matrix-wrap th.dev-tz-th-project,
#matrix-fs-pseudo-shell.dev-tz-fs-shell .dev-tz-matrix-wrap td.dev-tz-td-project,
#matrix-fs-pseudo-shell.dev-tz-fs-shell .dev-tz-matrix-wrap th.dev-tz-sub,
#matrix-fs-pseudo-shell.dev-tz-fs-shell .dev-tz-matrix-wrap td.dev-tz-ms-first,
#matrix-fs-pseudo-shell.dev-tz-fs-shell .dev-tz-matrix-wrap td.dev-tz-ms-fact,
#matrix-fs-pseudo-shell.dev-tz-fs-shell .dev-tz-matrix-wrap td.dev-tz-ms-last{
  white-space:nowrap!important;word-break:keep-all!important;overflow-wrap:normal!important;
  hyphens:none!important;text-overflow:clip!important;min-width:5.5em}
#matrix-fs-pseudo-shell.dev-tz-fs-shell .dev-tz-matrix-wrap td.dev-tz-td-project{
  min-width:9em}
#matrix-fs-pseudo-shell.dev-tz-fs-shell .dev-tz-matrix-wrap td.dev-tz-ms-last,
#matrix-fs-pseudo-shell.dev-tz-fs-shell .dev-tz-matrix-wrap th.dev-tz-sub.dev-tz-ms-last{
  min-width:6.5em}
/* Девелоперские проекты: overlay в родителе Streamlit */
#matrix-fs-pseudo-shell.dev-tz-fs-shell{display:flex!important;flex-direction:column!important;
  width:100vw!important;height:100vh!important;max-height:-webkit-fill-available!important;
  box-sizing:border-box!important}
"""

_MATRIX_IFRAME_FULLSCREEN_SHELL_CSS_LIGHT = """
body[data-bi-color-scheme="light"] .matrix-fs-btn{
  border:1px solid #cbd5e1!important;
  background:#ffffff!important;
  color:#111827!important;
  box-shadow:0 1px 2px rgba(0,0,0,0.06);
}
body[data-bi-color-scheme="light"] .matrix-fs-btn:hover{
  background:#f3f4f6!important;
  color:#111827!important;
  border-color:#94a3b8!important;
}
body[data-bi-color-scheme="light"] .matrix-fs-btn:focus-visible{
  outline:2px solid #3b82f6!important;
  outline-offset:1px;
}
body[data-bi-color-scheme="light"] #matrix-fs-root:fullscreen,
body[data-bi-color-scheme="light"] #matrix-fs-root:-webkit-full-screen,
body[data-bi-color-scheme="light"] #matrix-fs-root:-moz-full-screen{
  background:#f3f4f6!important;
}
body[data-bi-color-scheme="light"] #matrix-fs-root.matrix-fs-pseudo-on{
  background:#f3f4f6!important;
}
"""


def _matrix_iframe_fullscreen_shell_css(theme: str = "dark") -> str:
    css = _MATRIX_IFRAME_FULLSCREEN_SHELL_CSS
    if str(theme or "").strip().lower() == "light":
        css += _MATRIX_IFRAME_FULLSCREEN_SHELL_CSS_LIGHT
    return css


_MATRIX_IFRAME_FULLSCREEN_SCRIPT = """
<script>
(function(){
  var root=document.getElementById("matrix-fs-root");
  var btn=document.getElementById("matrix-fs-btn");
  if(!root||!btn) return;

  function matrixFsScheme(){
    var b=document.body;
    return (b&&b.getAttribute("data-bi-color-scheme")==="light")?"light":"dark";
  }
  function matrixFsShellBg(){
    return matrixFsScheme()==="light"?"#f3f4f6":"#0e1520";
  }
  function matrixFsCloseBtnStyle(){
    if(matrixFsScheme()==="light"){
      return "width:40px;height:40px;font-size:18px;border-radius:4px;"
        +"border:1px solid #cbd5e1;background:#ffffff;color:#111827;"
        +"box-shadow:0 1px 2px rgba(0,0,0,0.06);"
        +"touch-action:manipulation;-webkit-tap-highlight-color:transparent;";
    }
    return "width:40px;height:40px;font-size:18px;border-radius:4px;"
      +"border:1px solid rgba(121,154,192,0.55);background:rgba(35,43,56,0.96);color:#e8eef5;"
      +"touch-action:manipulation;-webkit-tap-highlight-color:transparent;";
  }

  var parentDoc=null;
  try{
    if(window.parent&&window.parent!==window&&window.parent.document){parentDoc=window.parent.document;}
  }catch(err){parentDoc=null;}

  var pseudoShell=null;
  var prevParentOverflow="";
  var prevIframeOverflow="";
  var MATRIX_FS_WIDE_SEL=".matrix-fs-body.dev-tz-fs-body,.matrix-fs-body.cp-body-stack";

  function matrixFsWideBody(el){
    return !!(el&&el.classList&&(el.classList.contains("dev-tz-fs-body")||el.classList.contains("cp-body-stack")||el.classList.contains("gdrs-fs-body")));
  }

  function matrixFsFindWrap(scrollEl){
    if(!scrollEl) return null;
    return scrollEl.querySelector(".dev-tz-matrix-wrap")
      ||scrollEl.querySelector(".cp-tables-stack")
      ||scrollEl.querySelector(".cp-table-wrap")
      ||scrollEl.querySelector(".gdrs-table-wrap");
  }

  function matrixFsStyleTable(tbl){
    if(!tbl) return;
    if(tbl.classList&&tbl.classList.contains("dev-tz-wide")){
      devTzSetImp(tbl,"width","max-content");
      devTzSetImp(tbl,"min-width","100%");
      devTzSetImp(tbl,"max-width","none");
    }else{
      devTzSetImp(tbl,"width","100%");
      devTzSetImp(tbl,"min-width","100%");
      devTzSetImp(tbl,"max-width","100%");
    }
  }

  function matrixFsStyleWrap(w){
    if(!w) return;
    devTzSetImp(w,"width","100%");
    devTzSetImp(w,"max-width","100%");
    devTzSetImp(w,"min-width","0");
    devTzSetImp(w,"box-sizing","border-box");
    devTzSetImp(w,"margin-left","0");
    devTzSetImp(w,"margin-right","0");
  }

  function matrixFsApplyWrapStyles(wrap){
    if(!wrap) return;
    matrixFsStyleWrap(wrap);
    if(wrap.classList&&wrap.classList.contains("cp-tables-stack")){
      var blocks=wrap.querySelectorAll(".cp-table-wrap");
      for(var i=0;i<blocks.length;i++){
        matrixFsStyleWrap(blocks[i]);
        matrixFsStyleTable(blocks[i].querySelector("table"));
      }
    }else{
      matrixFsStyleTable(wrap.querySelector("table"));
    }
  }

  function matrixFsResetWrapStyles(scrollEl){
    if(!scrollEl) return;
    var wraps=scrollEl.querySelectorAll(".dev-tz-matrix-wrap,.cp-tables-stack,.cp-table-wrap");
    for(var i=0;i<wraps.length;i++){
      wraps[i].removeAttribute("style");
      var tbls=wraps[i].querySelectorAll("table");
      for(var j=0;j<tbls.length;j++){tbls[j].removeAttribute("style");}
    }
  }

  function matrixFsWideBodyEl(scope){
    scope=scope||root;
    if(!scope||!scope.querySelector) return null;
    return scope.querySelector(MATRIX_FS_WIDE_SEL);
  }

  function injectParentHeadStyles(doc){
    if(!doc||!doc.head) return;
    var id="matrix-fs-pseudo-parent-css";
    if(!doc.getElementById(id)){
      var s=doc.createElement("style");
      s.id=id;
      s.type="text/css";
      var parts=[];
      var styles=document.head.querySelectorAll("style");
      for(var i=0;i<styles.length;i++){parts.push(styles[i].textContent||"");}
      s.textContent=parts.join("\\n");
      doc.head.appendChild(s);
    }
    var devId="matrix-fs-devtz-parent-css";
    var oldDev=doc.getElementById(devId);
    if(oldDev&&oldDev.parentNode){oldDev.parentNode.removeChild(oldDev);}
    var ds=doc.createElement("style");
    ds.id=devId;
    ds.type="text/css";
    ds.textContent=(
      "#matrix-fs-pseudo-shell.dev-tz-fs-shell{display:flex!important;flex-direction:column!important;"
      +"width:100vw!important;height:100vh!important;max-height:-webkit-fill-available!important;"
      +"box-sizing:border-box!important}"
      +"#matrix-fs-pseudo-shell.dev-tz-fs-shell .matrix-fs-body.dev-tz-fs-body{"
      +"position:relative!important;width:100%!important;flex:1 1 auto!important;min-height:0!important;"
      +"overflow:auto!important;-webkit-overflow-scrolling:touch!important;box-sizing:border-box!important}"
      +"#matrix-fs-pseudo-shell.dev-tz-fs-shell .dev-tz-matrix-wrap{"
      +"width:100%!important;max-width:100%!important;min-width:0!important;margin-left:0!important;margin-right:0!important;"
      +"box-sizing:border-box!important;overflow-x:auto!important;overflow-y:visible!important}"
      +"#matrix-fs-pseudo-shell.dev-tz-fs-shell .dev-tz-matrix-wrap table.rendered-table.dev-tz-wide,"
      +"#matrix-fs-pseudo-shell.dev-tz-fs-shell table.rendered-table.dev-tz-wide{"
      +"width:max-content!important;min-width:100%!important;max-width:none!important;"
      +"table-layout:auto!important}"
      +"#matrix-fs-pseudo-shell.dev-tz-fs-shell .dev-tz-matrix-wrap th.dev-tz-th-project,"
      +"#matrix-fs-pseudo-shell.dev-tz-fs-shell .dev-tz-matrix-wrap td.dev-tz-td-project,"
      +"#matrix-fs-pseudo-shell.dev-tz-fs-shell .dev-tz-matrix-wrap th.dev-tz-sub,"
      +"#matrix-fs-pseudo-shell.dev-tz-fs-shell .dev-tz-matrix-wrap td.dev-tz-ms-first,"
      +"#matrix-fs-pseudo-shell.dev-tz-fs-shell .dev-tz-matrix-wrap td.dev-tz-ms-fact,"
      +"#matrix-fs-pseudo-shell.dev-tz-fs-shell .dev-tz-matrix-wrap td.dev-tz-ms-last{"
      +"white-space:nowrap!important;word-break:keep-all!important;overflow-wrap:normal!important}"
      +"#matrix-fs-pseudo-shell.dev-tz-fs-shell .matrix-fs-body.cp-body-stack{"
      +"position:relative!important;width:100%!important;flex:1 1 auto!important;min-height:0!important;"
      +"overflow:auto!important;-webkit-overflow-scrolling:touch!important;box-sizing:border-box!important}"
      +"#matrix-fs-pseudo-shell.dev-tz-fs-shell .cp-tables-stack{"
      +"width:100%!important;max-width:100%!important;min-width:0!important;margin-left:0!important;margin-right:0!important;"
      +"box-sizing:border-box!important;align-items:stretch!important}"
      +"#matrix-fs-pseudo-shell.dev-tz-fs-shell .cp-table-wrap{"
      +"width:100%!important;max-width:100%!important;min-width:0!important;margin-left:0!important;margin-right:0!important;"
      +"box-sizing:border-box!important;overflow-x:auto!important;overflow-y:visible!important}"
      +"#matrix-fs-pseudo-shell.dev-tz-fs-shell .cp-table-wrap table.rendered-table{"
      +"width:100%!important;min-width:100%!important;max-width:100%!important;table-layout:auto!important}"
    );
    doc.head.appendChild(ds);
  }

  function removeParentHeadStyles(doc){
    if(!doc) return;
    var el=doc.getElementById("matrix-fs-pseudo-parent-css");
    if(el&&el.parentNode){el.parentNode.removeChild(el);}
    var devEl=doc.getElementById("matrix-fs-devtz-parent-css");
    if(devEl&&devEl.parentNode){devEl.parentNode.removeChild(devEl);}
  }

  function exitPseudo(){
    if(pseudoShell&&pseudoShell.parentNode){
      pseudoShell.parentNode.removeChild(pseudoShell);
    }
    pseudoShell=null;
    try{removeParentHeadStyles(parentDoc);}catch(e0){}
    try{
      if(parentDoc&&parentDoc.body){
        parentDoc.body.style.overflow=prevParentOverflow;
      }
    }catch(e1){}
    try{
      document.body.style.overflow=prevIframeOverflow;
    }catch(e2){}
    root.classList.remove("matrix-fs-pseudo-on");
    var bodyEl=matrixFsWideBodyEl();
    if(bodyEl){devTzResetFsLayout(bodyEl);}
    else{devTzReflowIframe();}
    requestAnimationFrame(devTzReflowIframe);
    setTimeout(devTzReflowIframe,0);
    setTimeout(devTzReflowIframe,120);
    setTimeout(devTzReflowIframe,350);
  }

  function devTzWrapHtml(bodyEl){
    var wrap=matrixFsFindWrap(bodyEl);
    return wrap?wrap.outerHTML:bodyEl.innerHTML;
  }

  function devTzSetImp(el,prop,val){
    if(!el) return;
    try{el.style.setProperty(prop,val,"important");}catch(e){el.style[prop]=val;}
  }

  function devTzIsScrollFsActive(scrollEl){
    if(!scrollEl) return false;
    if(pseudoShell&&pseudoShell.contains(scrollEl)) return true;
    if(!root) return false;
    if(activeNative()||root.classList.contains("matrix-fs-pseudo-on")){
      return !!scrollEl.closest&&scrollEl.closest("#matrix-fs-root")===root;
    }
    return false;
  }

  function devTzClearFsTimers(scrollEl){
    if(!scrollEl||!scrollEl.__devTzFsTimerIds) return;
    for(var i=0;i<scrollEl.__devTzFsTimerIds.length;i++){clearTimeout(scrollEl.__devTzFsTimerIds[i]);}
    scrollEl.__devTzFsTimerIds=null;
  }

  function devTzMeasureIframeHeight(){
    var root=document.getElementById("matrix-fs-root");
    if(!root) return 0;
    var wrap=root.querySelector(".dev-tz-matrix-wrap,.cp-tables-stack,.cp-table-wrap");
    if(!wrap){
      return Math.ceil(root.getBoundingClientRect().height||0);
    }
    var rr=wrap.getBoundingClientRect();
    var rt=root.getBoundingClientRect();
    return Math.ceil((rr.bottom||0)-(rt.top||0)+2);
  }

  function devTzReflowIframe(){
    try{
      var fe=window.frameElement;
      var root=document.getElementById("matrix-fs-root");
      if(!fe||!root) return;
      root.style.height="auto";
      root.style.minHeight="0";
      var body=root.querySelector(".matrix-fs-body");
      if(body){
        body.style.height="auto";
        body.style.minHeight="0";
      }
      var h=devTzMeasureIframeHeight();
      if(h<40) return;
      fe.style.height=h+"px";
      fe.style.minHeight="0";
      fe.style.maxHeight="none";
      fe.style.overflow="hidden";
      if(typeof window.__devTzMatrixRemeasure==="function"){
        window.__devTzMatrixRemeasure();
      }
    }catch(e){}
  }

  function devTzResetFsLayout(scrollEl){
    if(!scrollEl) return;
    devTzClearFsTimers(scrollEl);
    if(scrollEl.__devTzFsResizeHandler){
      try{window.removeEventListener("resize",scrollEl.__devTzFsResizeHandler);}catch(e){}
      scrollEl.__devTzFsResizeHandler=null;
    }
    var wrap=matrixFsFindWrap(scrollEl);
    if(wrap){
      matrixFsResetWrapStyles(scrollEl);
    }
    scrollEl.removeAttribute("style");
    scrollEl.__devTzFsFitBound=false;
    scrollEl.__devTzFsFit=null;
    devTzReflowIframe();
    requestAnimationFrame(devTzReflowIframe);
    setTimeout(devTzReflowIframe,0);
    setTimeout(devTzReflowIframe,120);
    setTimeout(devTzReflowIframe,350);
  }

  function devTzApplyFsLayout(scrollEl,shellEl,toolbarEl,win){
    if(!scrollEl) return;
    win=win||window;
    var wrap=matrixFsFindWrap(scrollEl);
    if(!wrap) return;
    matrixFsApplyWrapStyles(wrap);
    devTzSetImp(scrollEl,"position","relative");
    devTzSetImp(scrollEl,"width","100%");
    devTzSetImp(scrollEl,"box-sizing","border-box");
    devTzSetImp(scrollEl,"overflow","auto");
    devTzSetImp(scrollEl,"-webkit-overflow-scrolling","touch");
    function fit(){
      if(!devTzIsScrollFsActive(scrollEl)) return;
      if(!shellEl||!scrollEl||!wrap) return;
      var tbH=toolbarEl?toolbarEl.offsetHeight:0;
      var shellRect=shellEl.getBoundingClientRect?shellEl.getBoundingClientRect():null;
      var vh=shellRect&&shellRect.height?shellRect.height:0;
      if(!vh){vh=win.innerHeight||0;}
      if(!vh&&win.document&&win.document.documentElement){
        vh=win.document.documentElement.clientHeight||0;
      }
      var avail=Math.max(120,Math.floor(vh-tbH-8));
      devTzSetImp(scrollEl,"min-height",avail+"px");
      devTzSetImp(scrollEl,"height",avail+"px");
      var wrapH=wrap.offsetHeight||0;
      if(!wrapH&&wrap.getBoundingClientRect){wrapH=wrap.getBoundingClientRect().height||0;}
      if(wrapH>0&&wrapH<avail-4){
        devTzSetImp(wrap,"position","absolute");
        devTzSetImp(wrap,"top","50%");
        devTzSetImp(wrap,"left","0");
        devTzSetImp(wrap,"right","0");
        devTzSetImp(wrap,"transform","translateY(-50%)");
        devTzSetImp(wrap,"margin-top","0");
        devTzSetImp(wrap,"margin-bottom","0");
      }else{
        devTzSetImp(wrap,"position","relative");
        devTzSetImp(wrap,"top","0");
        devTzSetImp(wrap,"left","0");
        devTzSetImp(wrap,"right","0");
        devTzSetImp(wrap,"transform","none");
        var topPx=wrapH>0?Math.max(0,Math.floor((avail-wrapH)/2)):Math.floor(avail*0.22);
        devTzSetImp(wrap,"margin-top",topPx+"px");
        devTzSetImp(wrap,"margin-bottom","0");
      }
    }
    fit();
    requestAnimationFrame(fit);
    if(!scrollEl.__devTzFsTimerIds){scrollEl.__devTzFsTimerIds=[];}
    scrollEl.__devTzFsTimerIds.push(setTimeout(fit,0));
    scrollEl.__devTzFsTimerIds.push(setTimeout(fit,60));
    scrollEl.__devTzFsTimerIds.push(setTimeout(fit,180));
    scrollEl.__devTzFsTimerIds.push(setTimeout(fit,400));
    if(!scrollEl.__devTzFsResizeHandler){
      scrollEl.__devTzFsResizeHandler=fit;
      scrollEl.__devTzFsFitBound=true;
      win.addEventListener("resize",fit);
    }
    scrollEl.__devTzFsFit=fit;
  }

  function enterPseudoParent(){
    exitPseudo();
    var doc=parentDoc;
    var bodyEl=document.querySelector(".matrix-fs-body");
    if(!doc||!doc.body||!bodyEl){enterPseudoIframe();return;}
    pseudoShell=doc.createElement("div");
    pseudoShell.id="matrix-fs-pseudo-shell";
    var _wideFs=matrixFsWideBody(bodyEl);
    if(_wideFs){pseudoShell.classList.add("dev-tz-fs-shell");}
    pseudoShell.setAttribute("style",
      "position:fixed!important;z-index:2147483646!important;left:0!important;top:0!important;right:0!important;bottom:0!important;"
      +"width:100%!important;height:100%!important;max-height:-webkit-fill-available!important;"
      +"background:"+matrixFsShellBg()+"!important;display:flex!important;flex-direction:column!important;"
      +"padding:max(8px,env(safe-area-inset-top)) max(8px,env(safe-area-inset-right))"
      +" max(8px,env(safe-area-inset-bottom)) max(8px,env(safe-area-inset-left))!important;"
      +"box-sizing:border-box!important;overflow:hidden!important;");
    injectParentHeadStyles(doc);
    var tb=doc.createElement("div");
    tb.setAttribute("style","flex:0 0 auto;display:flex;justify-content:flex-end;align-items:center;padding:2px 0 8px 0;");
    var xb=doc.createElement("button");
    xb.type="button";
    xb.textContent="\\u2715";
    xb.setAttribute("style",matrixFsCloseBtnStyle());
    xb.addEventListener("click",function(ev){ev.preventDefault();exitPseudo();sync();});
    tb.appendChild(xb);
    var scroll=doc.createElement("div");
    scroll.className=bodyEl.className||"";
    scroll.setAttribute("style","flex:1 1 auto;min-height:0;overflow:auto;width:100%;box-sizing:border-box;position:relative;");
    scroll.innerHTML=_wideFs?devTzWrapHtml(bodyEl):bodyEl.innerHTML;
    pseudoShell.appendChild(tb);
    pseudoShell.appendChild(scroll);
    prevParentOverflow=doc.body.style.overflow||"";
    doc.body.appendChild(pseudoShell);
    doc.body.style.overflow="hidden";
    if(_wideFs){devTzApplyFsLayout(scroll,pseudoShell,tb,doc.defaultView||window);}
    sync();
  }

  function enterPseudoIframe(){
    exitPseudo();
    prevIframeOverflow=document.body.style.overflow||"";
    root.classList.add("matrix-fs-pseudo-on");
    try{document.body.style.overflow="hidden";}catch(e){}
    sync();
  }

  function isPseudo(){
    return !!(pseudoShell&&pseudoShell.parentNode)||root.classList.contains("matrix-fs-pseudo-on");
  }

  function activeNative(){
    return document.fullscreenElement===root||document.webkitFullscreenElement===root
      ||document.mozFullScreenElement===root||document.msFullscreenElement===root;
  }

  function active(){return activeNative()||isPseudo();}

  function sync(){
    var on=active();
    btn.textContent=on?"\\u2715":"\\u26F6";
    btn.setAttribute("title", on?
      "\\u0412\\u044b\\u0439\\u0442\\u0438 \\u0438\\u0437 \\u043f\\u043e\\u043b\\u043d\\u043e\\u044d\\u043a\\u0440\\u0430\\u043d\\u043d\\u043e\\u0433\\u043e \\u0440\\u0435\\u0436\\u0438\\u043c\\u0430":
      "\\u041d\\u0430 \\u0432\\u0435\\u0441\\u044c \\u044d\\u043a\\u0440\\u0430\\u043d");
    if(on&&!pseudoShell){
      var bodyEl=matrixFsWideBodyEl();
      if(bodyEl){
        requestAnimationFrame(function(){
          devTzApplyFsLayout(bodyEl,root,root.querySelector(".matrix-fs-topbar"),window);
        });
      }
    }else if(on&&pseudoShell){
      var pScroll=matrixFsWideBodyEl(pseudoShell);
      var pTb=pseudoShell.firstElementChild;
      if(pScroll){
        requestAnimationFrame(function(){
          var pwin=parentDoc&&parentDoc.defaultView?parentDoc.defaultView:window;
          devTzApplyFsLayout(pScroll,pseudoShell,pTb,pwin);
        });
      }
    }else{
      var offBody=matrixFsWideBodyEl();
      if(offBody){devTzResetFsLayout(offBody);}
    }
  }

  function exitNative(){
    if(document.exitFullscreen) document.exitFullscreen();
    else if(document.webkitExitFullscreen) document.webkitExitFullscreen();
    else if(document.mozCancelFullScreen) document.mozCancelFullScreen();
    else if(document.msExitFullscreen) document.msExitFullscreen();
  }

  function enterNative(){
    var req=root.requestFullscreen||root.webkitRequestFullscreen||root.mozRequestFullScreen||root.msRequestFullscreen;
    if(!req){return Promise.reject(new Error("no fullscreen api"));}
    try{return req.call(root);}catch(e){return Promise.reject(e);}
  }

  btn.addEventListener("click",function(e){
    e.preventDefault();
    e.stopPropagation();
    if(active()){
      exitPseudo();
      exitNative();
      sync();
      return;
    }
    /* Streamlit: overlay в родителе — iframe не трогаем, иначе ломается вёрстка после выхода */
    if(parentDoc){
      enterPseudoParent();
      return;
    }
    var p=enterNative();
    if(p&&p.then){
      p.then(function(){sync();}).catch(function(){enterPseudoIframe();});
    }else{
      enterPseudoIframe();
    }
  });

  function onFsChange(){
    if(!activeNative()&&!isPseudo()){
      var bodyEl=matrixFsWideBodyEl();
      if(bodyEl){devTzResetFsLayout(bodyEl);}
    }
    sync();
  }
  document.addEventListener("fullscreenchange",onFsChange);
  document.addEventListener("webkitfullscreenchange",onFsChange);
  document.addEventListener("mozfullscreenchange",onFsChange);
  document.addEventListener("MSFullscreenChange",onFsChange);

  function escClose(ev){
    if(ev.key==="Escape"&&isPseudo()){exitPseudo();if(activeNative()) exitNative();sync();}
  }
  document.addEventListener("keydown",escClose);
  try{if(parentDoc){parentDoc.addEventListener("keydown",escClose);}}catch(e3){}

  sync();
})();
</script>
"""

_MATRIX_IFRAME_FIT_HEIGHT_SCRIPT = """
<script>
(function(){
  // Высота, до которой нужно ужать iframe и контейнер (= высота контента таблицы).
  var H=0;
  var mo=null, moTarget=null;
  function measure(){
    var root=document.getElementById("matrix-fs-root");
    if(!root) return 0;
    var wrap=root.querySelector(".dev-tz-matrix-wrap,.cp-tables-stack,.cp-table-wrap,.gdrs-table-wrap");
    if(wrap){
      var rr=wrap.getBoundingClientRect();
      var rt=root.getBoundingClientRect();
      return Math.ceil(rr.bottom-rt.top+2);
    }
    return Math.ceil(root.getBoundingClientRect().height);
  }
  function container(){
    var fe=window.frameElement;
    if(!fe) return null;
    var p=fe.parentElement;
    while(p){
      if(p.getAttribute&&p.getAttribute("data-testid")==="stElementContainer") return p;
      p=p.parentElement;
    }
    return null;
  }
  function setContainer(c,h){
    // Контейнер Streamlit держит высоту = height из components.html (emotion-класс),
    // и она не зависит от ужатого iframe — под таблицей до кнопки «Скачать таблицу»
    // остаётся пустота. Явно ужимаем контейнер по высоте контента таблицы.
    c.style.setProperty("height",h+"px","important");
    c.style.setProperty("min-height","0","important");
    c.style.setProperty("max-height",h+"px","important");
    c.style.setProperty("margin-bottom","0","important");
    c.style.setProperty("padding-bottom","0","important");
  }
  function defend(){
    // React Streamlit при ререндере сбрасывает inline-height контейнера обратно к
    // Python-высоте. Следим за style/class контейнера и возвращаем нашу высоту.
    var c=container();
    if(!c) return;
    if(mo && moTarget===c) return;
    if(mo){ try{mo.disconnect();}catch(e){} }
    moTarget=c;
    mo=new MutationObserver(function(){
      if(!H) return;
      var cc=container();
      if(!cc) return;
      var cur=Math.round(cc.getBoundingClientRect().height);
      if(Math.abs(cur-H)>2){
        try{mo.disconnect();}catch(e){}
        setContainer(cc,H);
        moTarget=cc;
        try{mo.observe(moTarget,{attributes:true,attributeFilter:["style","class"]});}catch(e){}
      }
    });
    try{mo.observe(c,{attributes:true,attributeFilter:["style","class"]});}catch(e){}
  }
  function apply(){
    var h=measure();
    if(h<40) return;
    try{
      var fe=window.frameElement;
      if(!fe) return;
      var root=document.getElementById("matrix-fs-root");
      if(root){
        root.style.height="auto";
        root.style.minHeight="0";
        var body=root.querySelector(".matrix-fs-body");
        if(body){body.style.height="auto";body.style.minHeight="0";}
      }
      fe.style.height=h+"px";
      fe.style.minHeight="0";
      fe.style.maxHeight="none";
      fe.style.overflow="hidden";
      fe.classList.add("dev-tz-matrix-iframe");
      H=h;
      var c=container();
      if(c){ setContainer(c,h); defend(); }
    }catch(e){}
  }
  function schedule(){requestAnimationFrame(apply);}
  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",schedule);
  else schedule();
  window.addEventListener("load",schedule);
  // Повторные проходы: первые несколько секунд контент таблицы ещё доуточняет высоту.
  var n=0; var iv=setInterval(function(){ apply(); if(++n>=12) clearInterval(iv); },350);
  try{
    var w=document.querySelector(".dev-tz-matrix-wrap,.cp-tables-stack,.gdrs-table-wrap");
    if(w&&typeof ResizeObserver!=="undefined") new ResizeObserver(schedule).observe(w);
  }catch(e){}
  window.__devTzMatrixRemeasure=apply;
})();
</script>
"""

_DEV_TZ_MATRIX_SORT_SCRIPT = """
<script>
(function(){
  function parseNum(t){
    var s=String(t||"").replace(/\\s/g,"").replace(/\\u00a0/g,"").replace(",",".");
    var m=s.match(/-?\\d+(?:\\.\\d+)?/);
    return m?parseFloat(m[0]):NaN;
  }
  function cellKey(tr, colIdx){
    if(!tr||!tr.cells||!tr.cells[colIdx]) return "";
    var c=tr.cells[colIdx];
    var dv=c.getAttribute("data-sort-val");
    if(dv!==null&&dv!=="") return dv;
    return (c.textContent||"").trim();
  }
  function compare(at,bt,dir){
    var an=parseNum(at), bn=parseNum(bt), cmp=0;
    if(!isNaN(an)&&!isNaN(bn)) cmp=an-bn;
    else cmp=String(at).localeCompare(String(bt),"ru",{numeric:true,sensitivity:"base"});
    return dir>0?cmp:-cmp;
  }
  var tbl=document.querySelector("table.dev-tz-wide");
  if(!tbl) return;
  var tbody=tbl.querySelector("tbody");
  if(!tbody) return;
  function paint(th, base, dir){
    tbl.querySelectorAll("thead th.dev-tz-sortable").forEach(function(x){
      x.removeAttribute("data-sort-dir");
      var lb=x.getAttribute("data-sort-label")||"";
      x.textContent=lb;
    });
    th.setAttribute("data-sort-dir", String(dir));
    th.textContent=base+(dir>0?" \\u25B2":" \\u25BC");
  }
  function sortByCol(colIdx, th, baseLabel){
    var cur=th.getAttribute("data-sort-dir");
    var dir=cur==="1"?-1:1;
    paint(th, baseLabel, dir);
    var rows=Array.prototype.slice.call(tbody.querySelectorAll("tr"));
    rows.sort(function(a,b){return compare(cellKey(a,colIdx),cellKey(b,colIdx),dir);});
    rows.forEach(function(r){tbody.appendChild(r);});
    try{window.dispatchEvent(new Event("resize"));}catch(e){}
  }
  var projTh=tbl.querySelector("thead th.dev-tz-th-project");
  if(projTh){
    projTh.classList.add("dev-tz-sortable");
    var plab=(projTh.textContent||"Проект").trim();
    projTh.setAttribute("data-sort-label", plab);
    projTh.title="Клик — сортировка по проекту";
    projTh.addEventListener("click",function(ev){ev.preventDefault();sortByCol(0,projTh,plab);});
  }
  tbl.querySelectorAll("thead tr:nth-child(2) th.dev-tz-milestone").forEach(function(th){
    th.classList.add("dev-tz-sortable");
    var lab=(th.textContent||"").trim();
    th.setAttribute("data-sort-label", lab);
    th.title="Клик — сортировка по вехе";
    var colIdx=th.cellIndex||0;
    th.addEventListener("click",function(ev){ev.preventDefault();sortByCol(colIdx,th,lab);});
  });
  tbl.querySelectorAll("thead tr:nth-child(3) th.dev-tz-sub").forEach(function(th){
    th.classList.add("dev-tz-sortable");
    var lab=(th.textContent||"").trim();
    th.setAttribute("data-sort-label", lab);
    th.title="Клик — сортировка по колонке";
    var colIdx=th.cellIndex||0;
    th.addEventListener("click",function(ev){ev.preventDefault();sortByCol(colIdx,th,lab);});
  });
})();
</script>
"""


def _matrix_iframe_html_document(
    head_styles: str,
    scroll_block_inner: str,
    *,
    extra_body_suffix: str = "",
    body_class: str = "",
    color_scheme: str = "dark",
) -> str:
    """
    Полный HTML-документ для st.components.v1.html: матрица + кнопка полноэкранного режима.
    ``scroll_block_inner`` — готовый блок с обёрткой (.dev-tz-matrix-wrap / .cp-table-wrap) и таблицей.
    ``extra_body_suffix`` — доп. HTML/скрипты перед ``</body>`` (напр. поповер «Контрольные точки»).
    """
    # Сортировка только из extra_body_suffix (dev-tz / control-points).
    # Общий table_sort_inject в iframe не подключаем: даёт дубли <select>Все</select> рядом с кликом по th.
    _extra = extra_body_suffix or ""
    _scheme = "light" if str(color_scheme or "").strip().lower() == "light" else "dark"
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f'<meta name="color-scheme" content="{_scheme}">'
        '<meta name="viewport" content="width=device-width,initial-scale=5,viewport-fit=cover">'
        "<style>"
        + head_styles
        + _matrix_iframe_fullscreen_shell_css(color_scheme)
        + "</style></head><body"
        + f' data-bi-color-scheme="{_scheme}">'
        + '<div id="matrix-fs-root" class="matrix-fs-root">'
        + '<div class="matrix-fs-topbar" role="toolbar" aria-label="Таблица">'
        + '<button type="button" class="matrix-fs-btn" id="matrix-fs-btn" title="На весь экран">\u26F6</button>'
        + "</div>"
        + '<div class="matrix-fs-body'
        + ((" " + body_class.strip()) if body_class and body_class.strip() else "")
        + '">'
        + scroll_block_inner
        + "</div></div>"
        + _MATRIX_IFRAME_FULLSCREEN_SCRIPT
        + _MATRIX_IFRAME_FIT_HEIGHT_SCRIPT
        + _extra
        + "</body></html>"
    )


def _dev_tz_matrix_legend_palette(theme: str) -> dict[str, str]:
    if str(theme or "").strip().lower() == "light":
        return {
            "done": "#ea580c",
            "ok": "#15803d",
            "bad": "#b91c1c",
            "muted": "#6b7280",
            "text": "#111827",
            "border": "#d1d5db",
            "bg": "#f9fafb",
        }
    return {
        "done": "#f09355",
        "ok": "#28a745",
        "bad": "#d9534f",
        "muted": "#8899aa",
        "text": "#e8eef5",
        "border": "#3d4f63",
        "bg": "rgba(23, 49, 75, 0.35)",
    }


def render_dev_tz_matrix_color_legend(st, *, theme: str = "dark") -> None:
    """Легенда цветов шрифта матрицы «Девелоперские проекты» (под таблицей)."""
    p = _dev_tz_matrix_legend_palette(theme)
    st.markdown(
        f"""
<div class="dev-tz-color-legend" role="note" aria-label="Легенда цветов таблицы">
  <span class="dev-tz-color-legend-title">Легенда:</span>
  <span class="dev-tz-color-legend-item">
    <span class="dev-tz-color-swatch dev-tz-color-swatch-done">100%</span>
    <span class="dev-tz-color-legend-text">План / Факт — задача в MSP выполнена на 100%</span>
  </span>
  <span class="dev-tz-color-legend-item">
    <span class="dev-tz-color-swatch dev-tz-color-swatch-ok">+0</span>
    <span class="dev-tz-color-legend-text">Откл. — нулевое или положительное отклонение</span>
  </span>
  <span class="dev-tz-color-legend-item">
    <span class="dev-tz-color-swatch dev-tz-color-swatch-bad">−0</span>
    <span class="dev-tz-color-legend-text">Откл. — отрицательное отклонение (просрочка / недовыполнение)</span>
  </span>
</div>
<style>
.dev-tz-color-legend {{
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.55rem 1.35rem;
  margin: 0.45rem 0 0.75rem;
  padding: 0.55rem 0.85rem;
  border: 1px solid {p["border"]};
  border-radius: 8px;
  background: {p["bg"]};
  font-size: 0.875rem;
  line-height: 1.35;
  color: {p["text"]};
}}
.dev-tz-color-legend-title {{
  font-weight: 700;
  color: {p["text"]};
  margin-right: 0.15rem;
}}
.dev-tz-color-legend-item {{
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
}}
.dev-tz-color-swatch {{
  display: inline-block;
  min-width: 2.1rem;
  padding: 0.1rem 0.35rem;
  border-radius: 4px;
  font-weight: 800;
  text-align: center;
  line-height: 1.25;
}}
.dev-tz-color-swatch-done {{ color: {p["done"]} !important; }}
.dev-tz-color-swatch-ok {{ color: {p["ok"]} !important; }}
.dev-tz-color-swatch-bad {{ color: {p["bad"]} !important; }}
.dev-tz-color-legend-text {{ color: {p["text"]}; }}
@media (max-width: 720px) {{
  .dev-tz-color-legend {{ flex-direction: column; align-items: flex-start; gap: 0.45rem; }}
}}
</style>
""",
        unsafe_allow_html=True,
    )


def render_dev_tz_matrix(
    rows: Union[List[Dict[str, Any]], List[List[Dict[str, Any]]]],
    table_css: str,
    *,
    project_labels: Optional[List[str]] = None,
    vertical_dates: bool = False,
    theme: str = "dark",
) -> None:
    """
    Первая колонка «Проект» — только название; далее «Инвестиционная фаза» / «Жизнь проекта»
    и под каждой вехой План / Факт / Откл.

    ``project_labels``: подпись в колонке «Проект» для каждой строки (порядок = порядок блоков).
    ``vertical_dates``: писать даты в План/Факт вертикально (ТЗ).
    """
    import streamlit as st

    blocks: List[List[Dict[str, Any]]]
    if rows and isinstance(rows[0], dict):
        blocks = [rows]  # type: ignore[list-item]
    else:
        blocks = [b for b in (rows or []) if isinstance(b, list)]  # type: ignore[assignment]

    if not blocks or not blocks[0]:
        st.info("Нет строк матрицы.")
        return

    n_blocks = len(blocks)
    if project_labels is None:
        row_labels = [""] * n_blocks
    else:
        row_labels = [str(x or "").strip() for x in project_labels]
        if len(row_labels) < n_blocks:
            row_labels.extend([""] * (n_blocks - len(row_labels)))
        else:
            row_labels = row_labels[:n_blocks]

    template = blocks[0]
    esc = html_module.escape
    prefs = load_developer_projects_matrix_prefs()
    sc_map = prefs.get("subcolumns") or {}
    l_plan = str(sc_map.get("plan") or "План").strip() or "План"
    l_fact = str(sc_map.get("fact") or "Факт").strip() or "Факт"
    l_otkl = str(sc_map.get("otkl") or "Откл.").strip() or "Откл."
    invest_labels = [r["label"] for r in template if r.get("phase") == "invest"]
    life_labels = [r["label"] for r in template if r.get("phase") == "life"]
    n_inv = max(1, len(invest_labels))
    n_life = max(0, len(life_labels))
    col_span_inv = n_inv * 3
    col_span_life = n_life * 3

    mline: List[str] = []
    subline: List[str] = []
    for r in template:
        lab = r.get("label") or ""
        ph = str(r.get("phase") or "life").strip().lower()
        band = "dev-tz-inv-block" if ph == "invest" else "dev-tz-life-block"
        mline.append(
            f'<th colspan="3" class="dev-tz-milestone dev-tz-ms-block {band}" title="{esc(str(lab))}">{esc(str(lab))}</th>'
        )
        row_sc = r.get("subcolumn_labels") if isinstance(r.get("subcolumn_labels"), dict) else {}
        lbl_plan = str(row_sc.get("plan") or l_plan).strip() or l_plan
        lbl_fact = str(row_sc.get("fact") or l_fact).strip() or l_fact
        lbl_otkl = str(row_sc.get("otkl") or l_otkl).strip() or l_otkl
        subline.extend(
            [
                f'<th class="dev-tz-sub dev-tz-ms-first {band}">{esc(lbl_plan)}</th>',
                f'<th class="dev-tz-sub {band}">{esc(lbl_fact)}</th>',
                f'<th class="dev-tz-sub dev-tz-ms-last {band}">{esc(lbl_otkl)}</th>',
            ]
        )

    head_rows: List[str] = [
        "<tr>"
        '<th rowspan="3" class="dev-tz-th-project">Проект</th>'
        f'<th colspan="{col_span_inv}" class="dev-tz-ghead dev-tz-ghead-inv" style="text-align:center;vertical-align:middle;">Инвестиционная фаза</th>'
        f'<th colspan="{col_span_life}" class="dev-tz-ghead dev-tz-ghead-life" style="text-align:center;vertical-align:middle;">Жизнь проекта</th>'
        "</tr>"
    ]
    head_rows.append("<tr>" + "".join(mline) + "</tr>")
    head_rows.append("<tr>" + "".join(subline) + "</tr>")
    thead = "<thead>" + "".join(head_rows) + "</thead>"

    body_trs: List[str] = []
    tmpl_keys: List[Tuple[str, str]] = [_dev_tz_matrix_row_key(r) for r in template]
    for bi, block in enumerate(blocks):
        row_by_key = {_dev_tz_matrix_row_key(r): r for r in block}
        body_cells: List[str] = []
        for k in tmpl_keys:
            r = row_by_key.get(k)
            if r is None:
                for key in ("plan", "fact", "otkl"):
                    ms = "dev-tz-ms-first" if key == "plan" else ("dev-tz-ms-last" if key == "otkl" else "")
                    oc = f' class="{ms}"' if ms else ""
                    body_cells.append(f"<td{oc}>Н/Д</td>")
                continue
            for key in ("plan", "fact", "otkl"):
                v = r.get(key) or ""
                cls = _dev_tz_matrix_cell_classes(r, key, vertical_dates=vertical_dates)
                if key == "plan":
                    cls = (cls + " dev-tz-ms-first").strip()
                elif key == "otkl":
                    cls = (cls + " dev-tz-ms-last").strip()
                elif key == "fact":
                    cls = (cls + " dev-tz-ms-fact").strip()
                oc = f' class="{esc(cls)}"' if cls else ""
                iv = ""
                if _dev_tz_apply_vert_date(vertical_dates, key, v):
                    iv = (
                        ' style="writing-mode:vertical-rl;text-orientation:mixed;'
                        "max-height:7.5em;white-space:nowrap;vertical-align:middle;"
                        'text-align:center;padding:8px 4px;"'
                    )
                tip = ""
                if key in ("plan", "fact") and r.get("pct_complete_100") and "dev-tz-text-pct-done" in cls:
                    tip = ' title="' + esc("% выполнения в MSP для выбранной задачи — 100% (закрыта).") + '"'
                body_cells.append(f"<td{oc}{iv}{tip}>{esc(str(v))}</td>")
        plab = row_labels[bi] if bi < len(row_labels) else ""
        body_trs.append(
            '<tr><td class="dev-tz-td-project">' + esc(plab) + "</td>" + "".join(body_cells) + "</tr>"
        )

    html_tbl = (
        '<table class="rendered-table dev-tz-wide bi-sortable-table bi-sort-click-only" border="0">'
        + thead
        + "<tbody>"
        + "".join(body_trs)
        + "</tbody></table>"
    )
    # Рендер в iframe (components.html) — единственный способ получить надёжную
    # фиксацию первой колонки при горизонтальном скролле в Streamlit, так как
    # внешние контейнеры st.markdown/st.html ломают position:sticky.
    import streamlit.components.v1 as _components
    _dev_css_raw = _dev_tz_matrix_css_raw(theme)
    _sticky_css = _dev_tz_matrix_iframe_sticky_css(theme)
    _n_rows = len(blocks)
    _row_h = 56
    _iframe_h = max(220, 6 + 3 * _row_h + _n_rows * _row_h + 12)
    _head_styles = _dev_css_raw + _sticky_css
    _scroll_block = '<div class="dev-tz-matrix-wrap">' + html_tbl + "</div>"
    _iframe_html = _matrix_iframe_html_document(
        _head_styles,
        _scroll_block,
        body_class="dev-tz-fs-body",
        extra_body_suffix=_DEV_TZ_MATRIX_SORT_SCRIPT,
        color_scheme=theme,
    )
    st.markdown(
        _DEV_MATRIX_STREAMLIT_HOST_CSS_LIGHT
        if str(theme or "").strip().lower() == "light"
        else _DEV_MATRIX_STREAMLIT_HOST_CSS,
        unsafe_allow_html=True,
    )
    _components.html(_iframe_html, height=_iframe_h, scrolling=False)
    render_dev_tz_matrix_color_legend(st, theme=theme)


# ── Контрольные точки (Сроки / макет file-009): проекты × вехи ───────────────

# Вехи «Контрольные точки»: при % ≠ 100% для ГПЗУ / Экспертизы стадии П — оранжевый текст в ячейках (не заливка).
CONTROL_POINTS_ORANGE_PCT_SLUGS: frozenset = frozenset({"gpzu", "exp_pd"})


def _is_orange_pct_milestone(slug: str, title: str) -> bool:
    """Определить, что веха относится к ГПЗУ/Экспертизе стадии П (в т.ч. при кастомном slug)."""
    s_slug = str(slug or "").strip().lower()
    if s_slug in CONTROL_POINTS_ORANGE_PCT_SLUGS:
        return True
    s_title = str(title or "").strip().lower().replace("ё", "е")
    return ("гпзу" in s_title) or ("экспертиз" in s_title)

# Контрольные точки: список и правила сопоставления по согласованному ТЗ.
# Контрольные точки (ТЗ скрин): задачи блока «Ковенанты», План = Базовое окончание, Факт = Окончание,
# столбцы MSP → см. маппинг web_loader (_MSP_COLUMN_REMAP).
CONTROL_POINT_MILESTONES: List[Tuple[str, str, dict]] = [
    ("ГПЗУ", "gpzu", {"level": 5.0, "names_any": ["ГПЗУ"], "parent_l2_contains": "Ковенанты"}),
    (
        "Экспертиза стадии П",
        "exp_pd",
        {
            "level": 5.0,
            "names_any": [
                "Экспертиза стадии П",
                "Экспертиза стадии",
                "Экспертиза ПД",
                "экспертиза пд",
                "Экспертиза проектной документации",
                "экспертиза проектной документации",
                "Экспертиза",
            ],
            "parent_l2_contains": "Ковенанты",
        },
    ),
    (
        "Начало финансирования",
        "fin_start",
        {
            "level": 5.0,
            "names_any": [
                "КОД_ОТКР_ФИНАНС",
                "КОД ОТКР ФИНАНС",
                "КОД, ОТКР. ФИНАНС.",
                "КОД ОТКР. ФИНАНС.",
                "ОТКР. ФИНАНС.",
                "ОТКР ФИНАНС",
                "(начало финансирования)",
                "Начало финансирования",
                "начало финансирования",
                "КОД, ОТКР. ФИНАНС. (начало финансирования)",
            ],
            "parent_l2_contains": "Ковенанты",
        },
    ),
    (
        "Стадия РД",
        "rd_stage",
        {
            "level": 5.0,
            "names_any": ["Стадия РД", "Стадия Рабочая Документация (РД)", "Рабочая Документация (РД)"],
            "parent_l2_contains": "Ковенанты",
        },
    ),
    (
        "РС",
        "rs",
        {
            "level": 5.0,
            "names_any": [
                "Разрешение РС",
                "Разрешение на строительство РС",
                "Разрешение на строительство (РС)",
                "Разрешение на строительство",
                "разрешение на строительство",
                "РС:",
                "(РС)",
                "РЗУ РС",
            ],
            "parent_l2_contains": "Ковенанты",
        },
    ),
    ("Завершение СМР", "smr_finish", {"level": 5.0, "names_any": ["Завершение СМР"], "parent_l2_contains": "Ковенанты"}),
    ("Пуск электричества", "power_on", {"level": 5.0, "names_any": ["Пуск электричества"], "parent_l2_contains": "Ковенанты"}),
    ("Пуск газа", "gas_on", {"level": 5.0, "names_any": ["Пуск газа"], "parent_l2_contains": "Ковенанты"}),
    (
        "ЗОС",
        "zos",
        {
            "level": 5.0,
            "names_any": [
                "Заключение о соответствии",
                "ЗОС)",
                "ЗОС (участок",
                "ЗОС  (участок",
                "ЗОС - 1 этап",
                "ЗОС - 2 этап",
            ],
            "parent_l2_contains": "Ковенанты",
        },
    ),
    (
        "РВ",
        "rv",
        {
            "level": 5.0,
            "names_any": [
                "Разрешение на ввод в эксплуатацию (РВ)",
                "Разрешение на ввод в эксплуатацию",
                "Разрешение на ввод объекта",
                "Разрешение на ввод",
                "ввод в эксплуатацию",
                "РВ - 1 этап",
                "РВ - 2 этап",
            ],
            "names_exact_any": ["РВ"],
            "parent_l2_contains": "Ковенанты",
        },
    ),
    ("Право 1", "pravo1", {
        "level": 5.0,
        "names_any": ["Право 1", "Право 1 - 1 этап", "Право 1 - 2 этап"],
        "parent_l2_contains": "Ковенанты",
    }),
    ("Выкуп ЗУ", "vykup_zu", {"level": 5.0, "names_any": ["Выкуп ЗУ", "Выкуп земельного участка"], "parent_l2_contains": "Ковенанты"}),
    ("Право 2", "pravo2", {"level": 5.0, "names_any": ["Право 2", "Право 2 на Застройщика"], "parent_l2_contains": "Ковенанты"}),
]

_CP_MILESTONES_JSON_KEY = "control_points_milestones_json"


def get_control_point_milestones_effective() -> List[Tuple[str, str, dict]]:
    """
    Вехи для отчёта «Контрольные точки»: из настроек БД (JSON) или встроенный список CONTROL_POINT_MILESTONES.
    Админ задаёт title (заголовок столбца), slug (ключ колонок), match (правила сопоставления с MSP).
    """
    try:
        from settings import get_setting

        raw = (get_setting(_CP_MILESTONES_JSON_KEY) or "").strip()
        if not raw:
            return CONTROL_POINT_MILESTONES
        import json

        data = json.loads(raw)
        if not isinstance(data, list):
            return CONTROL_POINT_MILESTONES
        out: List[Tuple[str, str, dict]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            slug = str(item.get("slug", "")).strip()
            match = item.get("match")
            if not title or not slug or not isinstance(match, dict):
                continue
            out.append((title, slug, match))
        return out if out else CONTROL_POINT_MILESTONES
    except Exception:
        return CONTROL_POINT_MILESTONES


def control_point_milestones_default_json() -> str:
    """JSON по умолчанию (как в коде) — для админки и сброса."""
    import json

    data = [{"title": t, "slug": s, "match": m} for t, s, m in CONTROL_POINT_MILESTONES]
    return json.dumps(data, ensure_ascii=False, indent=2)


def save_control_point_milestones_json(json_str: str, updated_by: str) -> Tuple[bool, str]:
    """Сохранение JSON величин вех; пустая строка = сброс на встроенные правила."""
    try:
        import json

        from settings import set_setting

        s = (json_str or "").strip()
        if not s:
            set_setting(
                _CP_MILESTONES_JSON_KEY,
                "",
                description="Вехи «Контрольные точки» (JSON); пусто = код по умолчанию",
                updated_by=updated_by,
            )
            return True, "Сброшено на встроенные правила из кода."
        parsed = json.loads(s)
        if not isinstance(parsed, list):
            return False, "Ожидается JSON-массив объектов с полями title, slug, match."
        out: List[Tuple[str, str, dict]] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            slug = str(item.get("slug", "")).strip()
            match = item.get("match")
            if not title or not slug or not isinstance(match, dict):
                return False, "Каждый элемент: { \"title\", \"slug\", \"match\": { ... } }."
            out.append((title, slug, match))
        if not out:
            return False, "Нет ни одной валидной вехи."
        set_setting(
            _CP_MILESTONES_JSON_KEY,
            s,
            description="Вехи «Контрольные точки» (JSON): заголовки и match к MSP",
            updated_by=updated_by,
        )
        return True, f"Сохранено вех: {len(out)}."
    except Exception as e:
        return False, str(e)[:500]


def _control_points_project_filter_options(
    df: pd.DataFrame,
) -> Tuple[List[str], Dict[str, List[str]], Dict[str, str]]:
    """Список ключей группы проекта, карта gk→сырые значения в колонке проекта, gk→подпись в UI.

    Раньше опции строились по человекочитаемой подписи: при совпадении подписи у двух разных
    групп (одинаковый `lab`) списки raw_name сливались — фильтр «один проект» оставлял строки
    нескольких проектов. Теперь в selectbox значения — уникальные `gk`, подпись только через
    `format_func`.
    """
    if df is None or df.empty:
        return [], {}, {}
    pcol = _project_name_column(df)
    if not pcol or pcol not in df.columns:
        return [], {}, {}
    raws = df[pcol].dropna().astype(str).str.strip().unique().tolist()
    groups: Dict[str, List[str]] = defaultdict(list)
    for p in raws:
        groups[_control_points_project_group_key(p)].append(str(p).strip())
    gk_to_raws: Dict[str, List[str]] = {}
    gk_to_lab: Dict[str, str] = {}
    for gk, rlist in groups.items():
        rlist = sorted(set(rlist))
        gk_to_raws[gk] = rlist
        gk_to_lab[gk] = _control_points_project_label(gk, rlist)
    ordered_gks = sorted(gk_to_raws.keys(), key=lambda gk: (gk_to_lab.get(gk, gk).lower(), str(gk)))
    return ordered_gks, gk_to_raws, gk_to_lab


def _control_points_prepare_msp_dates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Для «Контрольные точки»: гарантировать canonical-колонки base end / plan end (и при наличии actual finish),
    если в файле русские/альтернативные заголовки без прохода через web_loader.
    """
    if df is None or getattr(df, "empty", True):
        return df
    out = df.copy()
    if "base end" not in out.columns:
        be = _find_col(
            out,
            ["base end", "Baseline Finish", "Базовое окончание", "Базовое_окончание"],
        )
        if be:
            out["base end"] = out[be]
    if "plan end" not in out.columns:
        pe = _find_col(
            out,
            ["plan end", "План окончание", "План_окончание", "Окончание"],
        )
        if pe:
            out["plan end"] = out[pe]
    if "actual finish" not in out.columns:
        af = _find_col(
            out,
            ["actual finish", "Фактическое окончание", "Фактическое_окончание"],
        )
        if af:
            out["actual finish"] = out[af]
    if "pct complete" not in out.columns:
        pc = _find_col(
            out,
            [
                "pct complete",
                "percent complete",
                "% complete",
                "Процент_завершения",
                "Процент завершения",
                "процент выполнения",
            ],
        )
        if not pc:
            # Fallback для выгрузок с нестандартными заголовками колонки процента.
            for c in out.columns:
                cl = str(c).strip().lower().replace("_", " ")
                if (
                    "%" in cl
                    or "percent" in cl
                    or "процент" in cl
                    or "выполн" in cl
                    or "готов" in cl
                ):
                    pc = c
                    break
        if pc:
            out["pct complete"] = out[pc]
    return out


def _project_name_column(df: pd.DataFrame) -> Optional[str]:
    if "project name" in df.columns:
        return "project name"
    return _find_col(df, ["Проект", "Project", "project"])


def _match_milestone_tasks(mdf: pd.DataFrame, kw: dict) -> pd.DataFrame:
    """Те же правила, что и строка матрицы девелоперских проектов."""
    return _match_tasks_like_msp_row(mdf, kw)


def _pick_representative_milestone_row(
    rows: pd.DataFrame,
    *,
    pct_scale_max: Any = None,
) -> pd.Series:
    """Строка-репрезентант вехи: свежий snapshot, затем мин. % выполнения (просрочка/0%)."""
    if rows is None or getattr(rows, "empty", True):
        return rows.iloc[0]

    work = rows
    if "snapshot_date" in rows.columns and len(rows) > 1:
        try:
            _sd = pd.to_datetime(rows["snapshot_date"], errors="coerce")
            if bool(_sd.notna().any()):
                _max = _sd.max()
                _latest = rows.loc[_sd == _max]
                if _latest is not None and not getattr(_latest, "empty", True):
                    work = _latest
        except Exception:
            work = rows

    def _both_dates_ok(rr: pd.Series) -> bool:
        pdt, fdt, _p = _msp_plan_fact_pct(rr)
        return (not pd.isna(pdt)) and (not pd.isna(fdt))

    if "pct complete" in work.columns:
        best_ix = None
        best_val: float | None = None
        for ix, rr in work.iterrows():
            raw = rr.get("pct complete", np.nan)
            if isinstance(raw, pd.Series):
                raw2 = raw.dropna()
                raw = raw2.iloc[0] if len(raw2) else np.nan
            nv = _normalized_pct_0_100(raw, pct_scale_max=pct_scale_max)
            if nv is None:
                continue
            if best_val is None or nv < best_val:
                best_val = nv
                best_ix = ix
        if best_ix is not None:
            cand = work.loc[best_ix]
            if _both_dates_ok(cand):
                return cand
            for _ix, rr in work.iterrows():
                if _both_dates_ok(rr):
                    return rr
            return cand
    for _ix, rr in work.iterrows():
        if _both_dates_ok(rr):
            return rr
    tc = _task_name_col(work)
    if tc and tc in work.columns:
        return work.sort_values(by=tc).iloc[0]
    return work.iloc[0]


def _one_milestone_cell(
    rows: pd.DataFrame,
    *,
    pct_scale_ref: Optional[pd.DataFrame] = None,
) -> Tuple[str, str, str, bool, bool, bool]:
    """
    План = базовое окончание (base end), Факт = «Окончание» (plan end после загрузки MSP).
    Откл. = План − Факт (календарные дни), как в матрице девелоперских проектов.
    warn_pct — % ≠ 100 (для экспорта); pct_complete_100 — закрыто на 100% (оранжевый текст План/Факт).
    """
    if rows is None or rows.empty:
        return "Н/Д", "Н/Д", "Н/Д", False, False, False
    ref_for_scale = pct_scale_ref if pct_scale_ref is not None else rows
    try:
        pct_scale_max = _pct_scale_max_from_frame(ref_for_scale)
    except Exception:
        pct_scale_max = None
    r = _pick_representative_milestone_row(rows, pct_scale_max=pct_scale_max)
    pdt, fdt, pct = _msp_plan_fact_pct(r)
    warn_pct = bool(_is_pct_complete_not_100_dev_matrix(pct, pct_scale_max=pct_scale_max))
    pct_complete_100 = bool(_is_pct_complete_100_dev_matrix(pct, pct_scale_max=pct_scale_max))
    pl = _fmt_date_ru(pdt)
    fl = _fmt_date_ru(fdt)
    if pd.isna(pdt) or pd.isna(fdt):
        return pl, fl, "Н/Д", False, warn_pct, pct_complete_100
    dev_days = _delta_days_plan_minus_fact(pdt, fdt)
    otk = _fmt_delta_days(dev_days)
    # План − Факт: ≥0 — факт не позже плана (в срок или раньше); <0 — просрочка.
    ok = bool(dev_days is not None and dev_days >= 0)
    return pl, fl, otk, ok, warn_pct, pct_complete_100


def _cp_hide_completed_candidates(sub: pd.DataFrame) -> pd.DataFrame:
    """Строки с % выполнения ≠ 100 или без процента; если пусто — исходный кадр (без потери вехи)."""
    if sub is None or getattr(sub, "empty", True) or "pct complete" not in sub.columns:
        return sub
    pc = pd.to_numeric(sub["pct complete"], errors="coerce")
    keep = (~pc.fillna(np.nan).eq(100.0)) | pc.isna()
    out = sub.loc[keep.fillna(False)]
    return out if not getattr(out, "empty", True) else sub


def _control_point_matching_row_indices(mdf: pd.DataFrame) -> set:
    """Индексы строк, попавших под любую встроенную/админскую веху «Контрольные точки»."""
    idx: set = set()
    if mdf is None or getattr(mdf, "empty", True):
        return idx
    for _t, _s, kw in get_control_point_milestones_effective():
        hit = _match_milestone_tasks(mdf, kw)
        if hit is not None and not hit.empty:
            idx.update(hit.index.tolist())
    return idx


def build_control_points_df(mdf: pd.DataFrame, *, hide_completed: bool = False) -> pd.DataFrame:
    """Одна строка на проект; столбцы project, row_ok, {slug}_plan|_fact|_otkl|_warn_pct."""
    pcol = _project_name_column(mdf)
    if pcol is None or mdf is None or mdf.empty:
        return pd.DataFrame()
    work = mdf.copy()
    raw_vals = work[pcol].dropna().astype(str).str.strip().unique().tolist()
    key_to_raws: Dict[str, List[str]] = defaultdict(list)
    for p in raw_vals:
        key_to_raws[_control_points_project_group_key(p)].append(str(p).strip())
    for gk in key_to_raws:
        key_to_raws[gk] = sorted(set(key_to_raws[gk]))

    rows_out: List[Dict[str, Any]] = []
    for gk, raws in sorted(
        key_to_raws.items(),
        key=lambda it: _control_points_project_label(it[0], it[1]).lower(),
    ):
        sub = work[work[pcol].astype(str).str.strip().isin(raws)]
        display_base = _control_points_project_label(gk, raws)
        sections = _detect_plot_sections_from_msp(sub)
        if gk == "unified_dmitrovsky1":
            sections = []
        stage_labels: List[Tuple[str, Optional[str]]]
        if sections:
            stage_labels = [(f"{display_base} ({sec} этап)", sec) for sec in sections]
        else:
            stage_labels = [(display_base, None)]
        for display, plot_sec in stage_labels:
            rec: Dict[str, Any] = {"project": display, "row_ok": True}
            for title, slug, kw in get_control_point_milestones_effective():
                sub_m = _cp_hide_completed_candidates(sub) if hide_completed else sub
                m = _match_milestone_tasks(sub_m, kw)
                if hide_completed and (m is None or getattr(m, "empty", True)):
                    m = _match_milestone_tasks(sub, kw)
                if plot_sec:
                    m = _filter_milestone_tasks_by_plot_section(m, str(plot_sec))
                pl, fl, otk, ok, warn_pct, _pct100 = _one_milestone_cell(
                    m, pct_scale_ref=sub
                )
                rec[f"{slug}_plan"] = pl
                rec[f"{slug}_fact"] = fl
                rec[f"{slug}_otkl"] = otk
                rec[f"{slug}_ok"] = ok
                rec[f"{slug}_warn_pct"] = bool(warn_pct)
                rec[f"{slug}_pct100"] = bool(_pct100)
                if not ok:
                    rec["row_ok"] = False
            rows_out.append(rec)
    return pd.DataFrame(rows_out)


_CONTROL_POINTS_CSS = """
<style>
.cp-tables-stack {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 40px;
  width: 100%;
  padding: 8px 8px 18px;
  box-sizing: border-box;
}
.cp-table-wrap {
  overflow-x: auto;
  min-width: 0;
  max-width: 100%;
  scrollbar-width: thin;
  scrollbar-color: rgba(121, 154, 192, 0.5) #141820;
}
.cp-table-wrap.cp-table-block {
  background: #121a24;
  border: 2px solid rgba(255, 255, 255, 0.42);
  border-radius: 10px;
  padding: 12px 14px;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.42);
  isolation: isolate;
}
.cp-table-wrap::-webkit-scrollbar {
  height: 10px;
}
.cp-table-wrap::-webkit-scrollbar-track {
  background: #141820;
  border-radius: 5px;
}
.cp-table-wrap::-webkit-scrollbar-thumb {
  background: rgba(121, 154, 192, 0.42);
  border-radius: 5px;
  border: 2px solid #141820;
}
.cp-table-wrap::-webkit-scrollbar-thumb:hover {
  background: rgba(121, 154, 192, 0.65);
}
/* border-collapse:separate обязателен для position:sticky на ячейках */
.cp-table-wrap .rendered-table {
  border: 3px solid #ffffff;
  border-collapse: separate !important;
  border-spacing: 0 !important;
  font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
  font-size: 13px;
  font-weight: 700;
}
.cp-table-wrap .rendered-table th,
.cp-table-wrap .rendered-table td {
  border-width: 1px !important;
  border-style: solid !important;
  border-color: #5a6f82 !important;
  background-clip: padding-box;
}
.cp-table-wrap .rendered-table tbody td {
  background-color: #0c1219 !important;
}
.cp-table-wrap .rendered-table th {
  font-size: 17px !important;
  font-weight: 700 !important;
  color: #f0f4f8 !important;
  background: #17314b !important;
  padding: 10px 10px !important;
  text-align: center !important;
  vertical-align: middle !important;
}
.cp-table-wrap .rendered-table td {
  font-size: 13px !important;
  font-weight: 700 !important;
  color: #fafafa !important;
  line-height: 1.35 !important;
  padding: 6px 8px !important;
  text-align: center !important;
  vertical-align: middle !important;
}
.rendered-table th.cp-tophead {
  text-align: center !important;
  background: #17314b !important;
  color: #f0f4f8 !important;
  font-size: 18px !important;
  font-weight: 700 !important;
}
/* Центрирование заголовков вех и подстолбцов */
.cp-table-wrap .rendered-table th.cp-ghead {
  text-align: center !important;
  vertical-align: middle !important;
  background: #1a3328 !important;
  font-size: 17px !important;
  font-weight: 700 !important;
  padding: 10px 10px !important;
  color: #f0f4f8 !important;
}
.cp-table-wrap .rendered-table th.cp-sub {
  text-align: center !important;
  vertical-align: middle !important;
  font-size: 16px !important;
  color: #f0f4f8 !important;
  font-weight: 700 !important;
  padding: 8px 8px !important;
  background: #17314b !important;
}
.cp-table-wrap .rendered-table th.cp-col-project {
  text-align: center !important;
  vertical-align: middle !important;
  position: sticky !important;
  left: 0 !important;
  z-index: 3 !important;
  background: #161f2b !important;
  color: #f0f4f8 !important;
  font-size: 17px !important;
}
.cp-col-project {
  position: sticky !important;
  left: 0 !important;
  z-index: 2 !important;
  background: #161f2b !important;
  border-right: 3px solid #ffffff !important;
  font-size: 15px !important;
  font-weight: 700 !important;
  color: #ffffff !important;
  text-align: left !important;
  padding: 6px 10px !important;
}
.cp-table-wrap .rendered-table tbody td.cp-col-project {
  font-size: 15px !important;
}
.cp-table-wrap .rendered-table thead th.cp-col-project {
  border-top: 3px solid #ffffff !important;
  border-left: 3px solid #ffffff !important;
  border-bottom: 3px solid #ffffff !important;
}
/* Блок вехи (● / План / Факт / Откл.): толстая белая рамка по краям группы */
.cp-table-wrap .rendered-table th.cp-ghead.cp-ms-block {
  border-left: 3px solid #ffffff !important;
  border-right: 3px solid #ffffff !important;
}
.cp-table-wrap .rendered-table th.cp-ms-first,
.cp-table-wrap .rendered-table td.cp-ms-first {
  border-left: 3px solid #ffffff !important;
}
.cp-table-wrap .rendered-table th.cp-ms-last,
.cp-table-wrap .rendered-table td.cp-ms-last {
  border-right: 3px solid #ffffff !important;
}
.cp-table-wrap .rendered-table th.cp-ghead.cp-ms-block {
  box-shadow: inset 3px 0 0 #ffffff, inset -3px 0 0 #ffffff;
}
.cp-table-wrap .rendered-table th.cp-ms-first,
.cp-table-wrap .rendered-table td.cp-ms-first {
  box-shadow: inset 3px 0 0 #ffffff;
}
.cp-table-wrap .rendered-table th.cp-ms-last,
.cp-table-wrap .rendered-table td.cp-ms-last {
  box-shadow: inset -3px 0 0 #ffffff;
}
.cp-table-wrap .rendered-table thead th.cp-col-project,
.cp-table-wrap .rendered-table tbody td.cp-col-project {
  box-shadow: inset -3px 0 0 #ffffff;
}
/* Зазор между блоками вех (горизонтальный) */
.cp-table-wrap .rendered-table th.cp-ms-sep,
.cp-table-wrap .rendered-table td.cp-ms-sep {
  border-left: 16px solid #121a24 !important;
}
.cp-table-wrap .rendered-table th.cp-ghead.cp-ms-block.cp-ms-sep {
  box-shadow: inset 3px 0 0 #ffffff, inset -3px 0 0 #ffffff;
}
.cp-table-wrap .rendered-table th.cp-ms-first.cp-ms-sep,
.cp-table-wrap .rendered-table td.cp-ms-first.cp-ms-sep {
  box-shadow: inset 3px 0 0 #ffffff;
}
/* Закрыто на 100% — оранжевый текст #f09355 в План/Факт */
.cp-table-wrap .rendered-table td.cp-td-pct-done {
  background: transparent !important;
  color: #f09355 !important;
  font-weight: 700 !important;
}
/* Отклонение: зелёный / красный (как dev-tz-otkl-ok / dev-tz-otkl-bad) */
.cp-table-wrap .rendered-table td.cp-otkl-ok {
  color: #28a745 !important;
  font-weight: 700 !important;
}
.cp-table-wrap .rendered-table td.cp-otkl-late {
  color: #d9534f !important;
  font-weight: 700 !important;
}
.cp-table-wrap .rendered-table td.cp-otkl-ok.cp-td-pct-done {
  color: #28a745 !important;
}
.cp-table-wrap .rendered-table td.cp-otkl-late.cp-td-pct-done {
  color: #d9534f !important;
}
.cp-table-wrap .rendered-table thead th.cp-sortable {
  cursor: pointer;
  user-select: none;
}
.cp-table-wrap .rendered-table thead th.cp-sortable:hover {
  filter: brightness(1.08);
}
.cp-status-cell { text-align: center; vertical-align: middle; }
.cp-status-dot { display: inline-block; width: 14px; height: 14px; border-radius: 50%; vertical-align: middle; }
.cp-status-ok { background: #22c55e; box-shadow: 0 0 6px rgba(34,197,94,0.45); }
.cp-status-bad { background: #ef4444; box-shadow: 0 0 6px rgba(239,68,68,0.45); }
.cp-status-warn { background: #f59e0b; box-shadow: 0 0 7px rgba(245,158,11,0.7); }
</style>
"""

_CONTROL_POINTS_CSS_LIGHT = """
<style>
.cp-tables-stack {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 40px;
  width: 100%;
  padding: 8px 8px 18px;
  box-sizing: border-box;
}
.cp-table-wrap {
  overflow-x: auto;
  min-width: 0;
  max-width: 100%;
  scrollbar-width: thin;
  scrollbar-color: #64748b #e5e7eb;
}
.cp-table-wrap.cp-table-block {
  background: #ffffff;
  border: 2px solid #cbd5e1;
  border-radius: 10px;
  padding: 12px 14px;
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.08);
  isolation: isolate;
}
.cp-table-wrap::-webkit-scrollbar { height: 10px; }
.cp-table-wrap::-webkit-scrollbar-track { background: #e5e7eb; border-radius: 5px; }
.cp-table-wrap::-webkit-scrollbar-thumb {
  background: #94a3b8; border-radius: 5px; border: 2px solid #e5e7eb;
}
.cp-table-wrap::-webkit-scrollbar-thumb:hover { background: #64748b; }
.cp-table-wrap .rendered-table {
  border: 3px solid #94a3b8;
  border-collapse: separate !important;
  border-spacing: 0 !important;
  font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
  font-size: 13px;
  font-weight: 700;
}
.cp-table-wrap .rendered-table th,
.cp-table-wrap .rendered-table td {
  border-width: 1px !important;
  border-style: solid !important;
  border-color: #cbd5e1 !important;
  background-clip: padding-box;
}
.cp-table-wrap .rendered-table tbody td {
  background-color: #ffffff !important;
  color: #111827 !important;
}
.cp-table-wrap .rendered-table th {
  font-size: 17px !important;
  font-weight: 700 !important;
  color: #111827 !important;
  background: #e8f0fe !important;
  padding: 10px 10px !important;
  text-align: center !important;
  vertical-align: middle !important;
}
.cp-table-wrap .rendered-table td {
  font-size: 13px !important;
  font-weight: 700 !important;
  color: #111827 !important;
  line-height: 1.35 !important;
  padding: 6px 8px !important;
  text-align: center !important;
  vertical-align: middle !important;
}
.cp-table-wrap .rendered-table th.cp-ghead {
  text-align: center !important;
  vertical-align: middle !important;
  background: #dcfce7 !important;
  font-size: 17px !important;
  font-weight: 700 !important;
  padding: 10px 10px !important;
  color: #14532d !important;
}
.cp-table-wrap .rendered-table th.cp-sub {
  text-align: center !important;
  vertical-align: middle !important;
  font-size: 16px !important;
  color: #111827 !important;
  font-weight: 700 !important;
  padding: 8px 8px !important;
  background: #f9fafb !important;
}
.cp-table-wrap .rendered-table th.cp-col-project {
  text-align: center !important;
  vertical-align: middle !important;
  position: sticky !important;
  left: 0 !important;
  z-index: 3 !important;
  background: #e8f0fe !important;
  color: #111827 !important;
  font-size: 17px !important;
}
.cp-col-project {
  position: sticky !important;
  left: 0 !important;
  z-index: 2 !important;
  background: #f9fafb !important;
  border-right: 3px solid #94a3b8 !important;
  font-size: 15px !important;
  font-weight: 700 !important;
  color: #111827 !important;
  text-align: left !important;
  padding: 6px 10px !important;
}
.cp-table-wrap .rendered-table tbody td.cp-col-project { font-size: 15px !important; }
.cp-table-wrap .rendered-table thead th.cp-col-project {
  border-top: 3px solid #94a3b8 !important;
  border-left: 3px solid #94a3b8 !important;
  border-bottom: 3px solid #94a3b8 !important;
}
.cp-table-wrap .rendered-table th.cp-ghead.cp-ms-block {
  border-left: 3px solid #94a3b8 !important;
  border-right: 3px solid #94a3b8 !important;
}
.cp-table-wrap .rendered-table th.cp-ms-first,
.cp-table-wrap .rendered-table td.cp-ms-first { border-left: 3px solid #94a3b8 !important; }
.cp-table-wrap .rendered-table th.cp-ms-last,
.cp-table-wrap .rendered-table td.cp-ms-last { border-right: 3px solid #94a3b8 !important; }
.cp-table-wrap .rendered-table th.cp-ghead.cp-ms-block {
  box-shadow: inset 3px 0 0 #94a3b8, inset -3px 0 0 #94a3b8;
}
.cp-table-wrap .rendered-table th.cp-ms-first,
.cp-table-wrap .rendered-table td.cp-ms-first { box-shadow: inset 3px 0 0 #94a3b8; }
.cp-table-wrap .rendered-table th.cp-ms-last,
.cp-table-wrap .rendered-table td.cp-ms-last { box-shadow: inset -3px 0 0 #94a3b8; }
.cp-table-wrap .rendered-table thead th.cp-col-project,
.cp-table-wrap .rendered-table tbody td.cp-col-project { box-shadow: inset -3px 0 0 #94a3b8; }
.cp-table-wrap .rendered-table th.cp-ms-sep,
.cp-table-wrap .rendered-table td.cp-ms-sep { border-left: 16px solid #ffffff !important; }
.cp-table-wrap .rendered-table th.cp-ghead.cp-ms-block.cp-ms-sep {
  box-shadow: inset 3px 0 0 #94a3b8, inset -3px 0 0 #94a3b8;
}
.cp-table-wrap .rendered-table th.cp-ms-first.cp-ms-sep,
.cp-table-wrap .rendered-table td.cp-ms-first.cp-ms-sep { box-shadow: inset 3px 0 0 #94a3b8; }
.cp-table-wrap .rendered-table td.cp-td-pct-done {
  background: transparent !important;
  color: #ea580c !important;
  font-weight: 700 !important;
}
.cp-table-wrap .rendered-table td.cp-otkl-ok {
  color: #15803d !important;
  font-weight: 700 !important;
}
.cp-table-wrap .rendered-table td.cp-otkl-late {
  color: #b91c1c !important;
  font-weight: 700 !important;
}
.cp-table-wrap .rendered-table td.cp-otkl-ok.cp-td-pct-done { color: #15803d !important; }
.cp-table-wrap .rendered-table td.cp-otkl-late.cp-td-pct-done { color: #b91c1c !important; }
.cp-table-wrap .rendered-table thead th.cp-sortable { cursor: pointer; user-select: none; }
.cp-table-wrap .rendered-table thead th.cp-sortable:hover { filter: brightness(0.97); }
.cp-status-cell { text-align: center; vertical-align: middle; }
.cp-status-dot { display: inline-block; width: 14px; height: 14px; border-radius: 50%; vertical-align: middle; }
.cp-status-ok { background: #22c55e; box-shadow: 0 0 6px rgba(34,197,94,0.35); }
.cp-status-bad { background: #ef4444; box-shadow: 0 0 6px rgba(239,68,68,0.35); }
.cp-status-warn { background: #f59e0b; box-shadow: 0 0 7px rgba(245,158,11,0.5); }
</style>
"""


def _control_points_css_raw(theme: str = "dark") -> str:
    css = _CONTROL_POINTS_CSS_LIGHT if str(theme or "").strip().lower() == "light" else _CONTROL_POINTS_CSS
    return css.replace("<style>", "").replace("</style>", "")


def _control_points_iframe_sticky_css(theme: str = "dark") -> str:
    if str(theme or "").strip().lower() == "light":
        return """
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:#ffffff;color:#111827;overflow-x:hidden;overflow-y:auto;
  font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  opacity:1!important;filter:none!important;isolation:isolate}
.matrix-fs-root,.matrix-fs-body{min-width:0!important;max-width:100%!important;width:100%!important}
.cp-tables-stack{display:flex!important;flex-direction:column!important;align-items:stretch!important;
  gap:40px!important;width:100%!important;padding:8px 8px 18px!important;box-sizing:border-box!important}
.cp-table-wrap.cp-table-block{background:#ffffff!important;border:2px solid #cbd5e1!important;
  border-radius:10px!important;padding:12px 14px!important;box-shadow:0 4px 14px rgba(15,23,42,0.08)!important;
  isolation:isolate!important}
.cp-table-wrap{width:100%!important;max-width:100%!important;min-width:0!important;
  overflow-x:auto!important;overflow-y:hidden!important;
  -webkit-overflow-scrolling:touch;overscroll-behavior-x:contain;
  scrollbar-width:thin;scrollbar-color:#64748b #e5e7eb}
.cp-table-wrap::-webkit-scrollbar{height:10px}
.cp-table-wrap::-webkit-scrollbar-track{background:#e5e7eb;border-radius:5px}
.cp-table-wrap::-webkit-scrollbar-thumb{background:#94a3b8;border-radius:5px;border:2px solid #e5e7eb}
.cp-table-wrap::-webkit-scrollbar-thumb:hover{background:#64748b}
.cp-table-wrap .rendered-table{
  border-collapse:separate!important;border-spacing:0!important;
  width:max-content!important;min-width:100%!important;
  font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif!important;
  font-size:13px!important;font-weight:700!important;border:3px solid #94a3b8!important}
.cp-table-wrap .rendered-table tbody td{
  font-size:13px!important;font-weight:700!important;line-height:1.35!important;
  color:#111827!important;padding:6px 8px!important;text-align:center!important;
  background-color:#ffffff!important}
.cp-table-wrap .rendered-table th{
  font-size:17px!important;font-weight:700!important;color:#111827!important;padding:10px 10px!important}
.cp-table-wrap .rendered-table th.cp-sub{color:#111827!important;font-size:16px!important;background:#f9fafb!important}
.cp-table-wrap .rendered-table th.cp-ghead{font-size:17px!important;color:#14532d!important;background:#dcfce7!important}
.cp-table-wrap .rendered-table thead th.cp-col-project{font-size:17px!important;color:#111827!important;background:#e8f0fe!important}
.cp-table-wrap .rendered-table th,
.cp-table-wrap .rendered-table td{
  border-width:1px!important;border-style:solid!important;
  border-color:#cbd5e1!important;background-clip:padding-box!important}
.cp-table-wrap .rendered-table th.cp-col-project,
.cp-table-wrap .rendered-table td.cp-col-project{
  position:sticky!important;left:0!important;
  width:200px!important;min-width:200px!important;max-width:200px!important;
  white-space:normal!important;word-break:break-word!important;
  border-right:3px solid #94a3b8!important}
.cp-table-wrap .rendered-table thead th.cp-col-project{
  border-top:3px solid #94a3b8!important;border-left:3px solid #94a3b8!important;
  border-bottom:3px solid #94a3b8!important}
.cp-table-wrap .rendered-table th.cp-col-project{z-index:5!important;background:#e8f0fe!important}
.cp-table-wrap .rendered-table td.cp-col-project{
  z-index:4!important;background:#f9fafb!important;
  text-align:left!important;color:#111827!important;padding:6px 10px!important;
  font-size:15px!important}
.cp-table-wrap .rendered-table td.cp-td-pct-done{color:#ea580c!important}
.cp-table-wrap .rendered-table td.cp-otkl-ok{color:#15803d!important}
.cp-table-wrap .rendered-table td.cp-otkl-late{color:#b91c1c!important}
.cp-table-wrap .rendered-table th.cp-sub-status,
.cp-table-wrap .rendered-table td.cp-col-cell-status{
  width:34px!important;min-width:34px!important;
  text-align:center!important;padding:4px 4px!important}
.cp-table-wrap .rendered-table th.cp-sub,
.cp-table-wrap .rendered-table td{min-width:96px;white-space:nowrap}
.cp-table-wrap .rendered-table th.cp-sub-status,
.cp-table-wrap .rendered-table td.cp-col-cell-status{min-width:34px!important}
.cp-table-wrap .rendered-table th.cp-col-project,
.cp-table-wrap .rendered-table td.cp-col-project{min-width:200px!important;white-space:normal!important}
.cp-table-wrap .rendered-table th.cp-ghead.cp-ms-block{
  border-left:3px solid #94a3b8!important;border-right:3px solid #94a3b8!important;
  box-shadow:inset 3px 0 0 #94a3b8,inset -3px 0 0 #94a3b8}
.cp-table-wrap .rendered-table th.cp-ms-first,
.cp-table-wrap .rendered-table td.cp-ms-first{
  border-left:3px solid #94a3b8!important;box-shadow:inset 3px 0 0 #94a3b8}
.cp-table-wrap .rendered-table th.cp-ms-last,
.cp-table-wrap .rendered-table td.cp-ms-last{
  border-right:3px solid #94a3b8!important;box-shadow:inset -3px 0 0 #94a3b8}
.cp-table-wrap .rendered-table thead th.cp-col-project,
.cp-table-wrap .rendered-table tbody td.cp-col-project{box-shadow:inset -3px 0 0 #94a3b8}
.cp-table-wrap .rendered-table th.cp-ms-sep,
.cp-table-wrap .rendered-table td.cp-ms-sep{border-left:16px solid #ffffff!important}
.cp-table-wrap .rendered-table th.cp-ghead.cp-ms-block.cp-ms-sep{
  box-shadow:inset 3px 0 0 #94a3b8,inset -3px 0 0 #94a3b8}
.cp-table-wrap .rendered-table th.cp-ms-first.cp-ms-sep,
.cp-table-wrap .rendered-table td.cp-ms-first.cp-ms-sep{box-shadow:inset 3px 0 0 #94a3b8}
"""
    return """
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:#0e1520;overflow-x:hidden;overflow-y:auto;
  font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  opacity:1!important;filter:none!important;isolation:isolate}
.matrix-fs-root,.matrix-fs-body{min-width:0!important;max-width:100%!important;width:100%!important}
.cp-tables-stack{display:flex!important;flex-direction:column!important;align-items:stretch!important;
  gap:40px!important;width:100%!important;padding:8px 8px 18px!important;box-sizing:border-box!important}
.cp-table-wrap.cp-table-block{background:#121a24!important;border:2px solid rgba(255,255,255,0.42)!important;
  border-radius:10px!important;padding:12px 14px!important;box-shadow:0 6px 18px rgba(0,0,0,0.42)!important;
  isolation:isolate!important}
.cp-table-wrap{width:100%!important;max-width:100%!important;min-width:0!important;
  overflow-x:auto!important;overflow-y:hidden!important;
  -webkit-overflow-scrolling:touch;overscroll-behavior-x:contain;
  scrollbar-width:thin;scrollbar-color:rgba(121,154,192,0.5) #141820}
.cp-table-wrap::-webkit-scrollbar{height:10px}
.cp-table-wrap::-webkit-scrollbar-track{background:#141820;border-radius:5px}
.cp-table-wrap::-webkit-scrollbar-thumb{background:rgba(121,154,192,0.42);border-radius:5px;border:2px solid #141820}
.cp-table-wrap::-webkit-scrollbar-thumb:hover{background:rgba(121,154,192,0.65)}
.cp-table-wrap .rendered-table{
  border-collapse:separate!important;border-spacing:0!important;
  width:max-content!important;min-width:100%!important;
  font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif!important;
  font-size:13px!important;font-weight:700!important}
.cp-table-wrap .rendered-table tbody td{
  font-size:13px!important;font-weight:700!important;line-height:1.35!important;
  color:#fafafa!important;padding:6px 8px!important;text-align:center!important}
.cp-table-wrap .rendered-table th{
  font-size:17px!important;font-weight:700!important;color:#f0f4f8!important;padding:10px 10px!important}
.cp-table-wrap .rendered-table th.cp-sub{color:#f0f4f8!important;font-size:16px!important}
.cp-table-wrap .rendered-table th.cp-ghead{font-size:17px!important;color:#f0f4f8!important}
.cp-table-wrap .rendered-table thead th.cp-col-project{font-size:17px!important;color:#f0f4f8!important}
.cp-table-wrap .rendered-table{border:3px solid #ffffff!important}
.cp-table-wrap .rendered-table th,
.cp-table-wrap .rendered-table td{
  border-width:1px!important;border-style:solid!important;
  border-color:#5a6f82!important;background-clip:padding-box!important}
.cp-table-wrap .rendered-table tbody td{background-color:#0c1219!important}
.cp-table-wrap .rendered-table th.cp-col-project,
.cp-table-wrap .rendered-table td.cp-col-project{
  position:sticky!important;left:0!important;
  width:200px!important;min-width:200px!important;max-width:200px!important;
  white-space:normal!important;word-break:break-word!important;
  border-right:3px solid #ffffff!important}
.cp-table-wrap .rendered-table thead th.cp-col-project{
  border-top:3px solid #ffffff!important;border-left:3px solid #ffffff!important;
  border-bottom:3px solid #ffffff!important}
.cp-table-wrap .rendered-table th.cp-col-project{
  z-index:5!important;background:#161f2b!important}
.cp-table-wrap .rendered-table td.cp-col-project{
  z-index:4!important;background:#161f2b!important;
  text-align:left!important;color:#ffffff!important;padding:6px 10px!important;
  font-size:15px!important}
.cp-table-wrap .rendered-table td.cp-td-pct-done{color:#f09355!important}
.cp-table-wrap .rendered-table td.cp-otkl-ok{color:#28a745!important}
.cp-table-wrap .rendered-table td.cp-otkl-late{color:#d9534f!important}
.cp-table-wrap .rendered-table th.cp-sub-status,
.cp-table-wrap .rendered-table td.cp-col-cell-status{
  width:34px!important;min-width:34px!important;
  text-align:center!important;padding:4px 4px!important}
.cp-table-wrap .rendered-table th.cp-sub,
.cp-table-wrap .rendered-table td{
  min-width:96px;white-space:nowrap}
.cp-table-wrap .rendered-table th.cp-sub-status,
.cp-table-wrap .rendered-table td.cp-col-cell-status{
  min-width:34px!important}
.cp-table-wrap .rendered-table th.cp-col-project,
.cp-table-wrap .rendered-table td.cp-col-project{
  min-width:200px!important;white-space:normal!important}
.cp-table-wrap .rendered-table th.cp-ghead.cp-ms-block{
  border-left:3px solid #ffffff!important;border-right:3px solid #ffffff!important;
  box-shadow:inset 3px 0 0 #fff,inset -3px 0 0 #fff}
.cp-table-wrap .rendered-table th.cp-ms-first,
.cp-table-wrap .rendered-table td.cp-ms-first{
  border-left:3px solid #ffffff!important;box-shadow:inset 3px 0 0 #fff}
.cp-table-wrap .rendered-table th.cp-ms-last,
.cp-table-wrap .rendered-table td.cp-ms-last{
  border-right:3px solid #ffffff!important;box-shadow:inset -3px 0 0 #fff}
.cp-table-wrap .rendered-table thead th.cp-col-project,
.cp-table-wrap .rendered-table tbody td.cp-col-project{box-shadow:inset -3px 0 0 #fff}
.cp-table-wrap .rendered-table th.cp-ms-sep,
.cp-table-wrap .rendered-table td.cp-ms-sep{border-left:16px solid #121a24!important}
.cp-table-wrap .rendered-table th.cp-ghead.cp-ms-block.cp-ms-sep{
  box-shadow:inset 3px 0 0 #fff,inset -3px 0 0 #fff}
.cp-table-wrap .rendered-table th.cp-ms-first.cp-ms-sep,
.cp-table-wrap .rendered-table td.cp-ms-first.cp-ms-sep{box-shadow:inset 3px 0 0 #fff}
"""


def _apply_control_points_msp_filters(
    st, mdf: pd.DataFrame
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Фильтр по проекту (ур.1): единственный фильтр на дашборде «Контрольные точки».
    Возвращает датафрейм для расчёта вех и метаданные (число строк после фильтра).
    """
    meta: Dict[str, Any] = {}
    if mdf is None or getattr(mdf, "empty", True):
        return pd.DataFrame(), meta
    df = mdf.copy()
    pcol = _project_name_column(df)
    gk_to_raws: Dict[str, List[str]] = {}
    gk_to_lab: Dict[str, str] = {}
    ordered_gks: List[str] = []
    if pcol and pcol in df.columns:
        ordered_gks, gk_to_raws, gk_to_lab = _control_points_project_filter_options(df)
        # Стабильный порядок «крупных» проектов сверху, затем остальное (если будут).
        # Сравниваем по префиксу подписи (gk_to_lab), иначе «Дмитровский 1» в данных не матчится с
        # шаблоном «Дмитровский» и проект пропадает из выпадающего списка фильтра.
        preferred_prefixes = ["Дмитровский", "Есипово", "Завод", "Ленинский"]
        matched: list[str] = []
        for pref in preferred_prefixes:
            for gk in ordered_gks:
                lab = str(gk_to_lab.get(gk, "") or "")
                if lab.lower().startswith(pref.lower()) and gk not in matched:
                    matched.append(gk)
                    break
        if matched:
            rest = [gk for gk in ordered_gks if gk not in matched]
            ordered_gks = matched + rest
        opts = ordered_gks

        def _cp_proj_select_label(opt: str) -> str:
            return str(gk_to_lab.get(opt, opt))

        from .ui_quiet import filters_grid, filters_popover

        _cp_reset_keys = ["cp_msp_filter_projects"]
        _pre_sel = st.session_state.get("cp_msp_filter_projects") or []
        if not isinstance(_pre_sel, list):
            _pre_sel = []
        with filters_popover(
            st,
            reset_keys=_cp_reset_keys,
            active_count=len(_pre_sel),
        ) as _fp:
            with filters_grid(st, 1) as _cols:
                with _cols[0]:
                    sel_gks = st.multiselect(
                        "Проект",
                        opts,
                        format_func=_cp_proj_select_label,
                        key="cp_msp_filter_projects",
                        placeholder="Все проекты",
                    )
            _chips = []
            for _gk in sel_gks or []:
                _chips.append(("Проект", _cp_proj_select_label(_gk)))
            _fp.set_chips(_chips)
    else:
        sel_gks = []

    out = df
    if sel_gks and pcol and pcol in out.columns and gk_to_raws:
        _raws_union: list[str] = []
        for _gk in sel_gks:
            _raws_union.extend(gk_to_raws.get(str(_gk).strip(), []) or [])
        _raws_union = sorted(set(_raws_union))
        if _raws_union:
            out = out[out[pcol].astype(str).str.strip().isin(_raws_union)]

    meta["subtree_rows"] = int(len(out))
    return out, meta


CONTROL_POINTS_GROUPS_DEFAULT_SLUGS: List[List[str]] = [
    ["gpzu", "exp_pd", "fin_start", "rd_stage"],
    ["rs", "smr_finish", "power_on", "gas_on"],
    ["zos", "rv", "pravo1", "vykup_zu", "pravo2"],
]


def _control_points_split_groups(
    ms_specs: List[Tuple[str, str]],
) -> List[List[Tuple[str, str]]]:
    """Разбивка списка вех на 3 блока по ТЗ заказчика 2026-05-06.

    Если набор slug совпадает с CONTROL_POINTS_GROUPS_DEFAULT_SLUGS — используем
    зафиксированную группировку. Иначе fallback: чанки по 4 в исходном порядке
    (или одна большая таблица, если вех ≤ 4).
    """
    by_slug = {s: (t, s) for t, s in ms_specs}
    if all(s in by_slug for grp in CONTROL_POINTS_GROUPS_DEFAULT_SLUGS for s in grp):
        return [
            [by_slug[s] for s in grp]
            for grp in CONTROL_POINTS_GROUPS_DEFAULT_SLUGS
        ]
    if not ms_specs:
        return []
    if len(ms_specs) <= 4:
        return [list(ms_specs)]
    chunks: List[List[Tuple[str, str]]] = []
    n = len(ms_specs)
    size = (n + 2) // 3
    for i in range(0, n, size):
        chunks.append(list(ms_specs[i : i + size]))
    return chunks


def _control_points_project_label_to_raw_names(mdf: pd.DataFrame) -> Dict[str, List[str]]:
    """Как в build_control_points_df: подпись проекта → список исходных имён в колонке проекта."""
    out: Dict[str, List[str]] = {}
    pcol = _project_name_column(mdf)
    if pcol is None or mdf is None or mdf.empty:
        return out
    work = mdf.copy()
    raw_vals = work[pcol].dropna().astype(str).str.strip().unique().tolist()
    key_to_raws: Dict[str, List[str]] = defaultdict(list)
    for p in raw_vals:
        key_to_raws[_control_points_project_group_key(p)].append(str(p).strip())
    for gk, raws in key_to_raws.items():
        raws_u = sorted(set(raws))
        lab = _control_points_project_label(gk, raws_u)
        sub = work[work[pcol].astype(str).str.strip().isin(raws_u)]
        sections = _detect_plot_sections_from_msp(sub)
        if gk == "unified_dmitrovsky1":
            sections = []
        if sections:
            for sec in sections:
                out[f"{lab} ({sec} этап)"] = raws_u
        else:
            out[lab] = raws_u
    return out


def _cp_detail_panel_inner_html(
    hit: pd.DataFrame,
    milestone_title: str,
    *,
    pct_scale_max: Any = None,
) -> str:
    """HTML фрагмент для модального окна: задачи MSP, попавшие под веху."""
    esc = html_module.escape
    title = esc(str(milestone_title or "").strip() or "Веха")
    if hit is None or getattr(hit, "empty", True):
        return (
            f'<div class="cp-tip-hdr">{title}</div>'
            f'<p class="cp-tip-empty">{esc("Нет строк MSP, попадающих под правило этой вехи.")}</p>'
        )

    tc = _task_name_col(hit)
    rows_html: List[str] = []
    for _, rr in hit.iterrows():
        tnm = esc(str(rr.get(tc, "") or "")) if tc and tc in hit.columns else ""
        be = rr.get("base end") if "base end" in hit.columns else None
        pe = rr.get("plan end") if "plan end" in hit.columns else None
        pbe = _fmt_date_ru(be)
        ppe = _fmt_date_ru(pe)
        pct_s = ""
        if "pct complete" in hit.columns:
            raw_pct = rr.get("pct complete")
            try:
                pv = _normalized_pct_0_100(raw_pct, pct_scale_max=pct_scale_max)
            except Exception:
                pv = None
            if pv is not None:
                pct_s = f"{pv:.0f}%"
        rows_html.append(
            "<tr>"
            f"<td>{tnm}</td>"
            f"<td>{esc(pbe)}</td>"
            f"<td>{esc(ppe)}</td>"
            f"<td>{esc(pct_s)}</td>"
            "</tr>"
        )
    thead = (
        "<tr>"
        "<th>Задача</th><th>Базовое окончание</th><th>Окончание (факт)</th><th>% выполнения</th>"
        "</tr>"
    )
    return (
        f'<div class="cp-tip-hdr">{title}</div>'
        f'<table class="cp-tip-tbl"><thead>{thead}</thead><tbody>'
        + "".join(rows_html)
        + "</tbody></table>"
    )


_CONTROL_POINTS_POPOVER_FRAGMENT = (
    """
<style>
.cp-tip-overlay{position:fixed;inset:0;background:rgba(0,0,0,0.58);z-index:2147483000;
  display:none;align-items:center;justify-content:center;padding:max(10px,2vw);
  box-sizing:border-box;-webkit-overflow-scrolling:touch}
.cp-tip-overlay.is-open{display:flex!important}
.cp-tip-panel{position:relative;width:min(1120px,96vw);max-height:min(92vh,900px);
  display:flex;flex-direction:column;background:#0f141c;border:1px solid rgba(121,154,192,0.55);
  border-radius:12px;box-shadow:0 18px 60px rgba(0,0,0,0.55);overflow:hidden}
.cp-tip-toolbar{flex:0 0 auto;display:flex;align-items:center;justify-content:space-between;
  gap:10px;padding:10px 12px;border-bottom:1px solid rgba(121,154,192,0.35);
  background:linear-gradient(180deg,rgba(32,58,92,0.95),rgba(20,32,48,0.92))}
.cp-tip-title{font:600 14px/1.2 Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:#eaf2fb}
.cp-tip-close{box-sizing:border-box;width:34px;height:34px;margin:0;padding:0;border-radius:8px;
  border:1px solid rgba(121,154,192,0.45);background:rgba(35,43,56,0.96);color:#e8eef5;cursor:pointer;font-size:18px;line-height:1}
.cp-tip-close:hover{background:rgba(55,65,82,0.98)}
.cp-tip-content{flex:1 1 auto;min-height:0;overflow:auto;padding:12px 14px;color:#e8eef5;font-size:12px;
  font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.cp-tip-hdr{font:700 13px/1.35 Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:#cfe9fa;margin:0 0 10px 0}
.cp-tip-tbl{width:100%;border-collapse:separate;border-spacing:0;
  font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.cp-tip-tbl th,.cp-tip-tbl td{border:1px solid rgba(121,154,192,0.38);padding:6px 8px;text-align:left;vertical-align:top}
.cp-tip-tbl th{background:#17314b;color:#eaf2fb;font-weight:700}
.cp-tip-tbl tr:nth-child(even) td{background:rgba(255,255,255,0.02)}
.cp-tip-empty{opacity:0.92;margin:0}
.cp-status-hit{display:inline-flex;align-items:center;justify-content:center;min-width:28px;min-height:28px;
  cursor:pointer;border-radius:6px;padding:2px}
.cp-status-hit:hover,.cp-status-hit:focus-visible{outline:2px solid rgba(121,154,192,0.65);outline-offset:1px;background:rgba(121,154,192,0.08)}
</style>
<div id="cp-tip-overlay" class="cp-tip-overlay" aria-hidden="true">
  <div class="cp-tip-panel" role="dialog" aria-modal="true">
    <div class="cp-tip-toolbar">
      <span class="cp-tip-title">Детализация по вехе</span>
      <button type="button" class="cp-tip-close" id="cp-tip-close" title="Закрыть">×</button>
    </div>
    <div id="cp-tip-content" class="cp-tip-content"></div>
  </div>
</div>
<script>
(function(){
  function padB64(s){ var p=s.length%4; if(!p) return s; return s+'===='.slice(p); }
  function utf8FromB64(b64){
    try{
      b64=padB64(String(b64).replace(/-/g,'+').replace(/_/g,'/'));
      var bin=atob(b64);
      var bytes=new Uint8Array(bin.length);
      for(var i=0;i<bin.length;i++) bytes[i]=bin.charCodeAt(i);
      return new TextDecoder('utf-8').decode(bytes);
    }catch(e){
      return '<p class="cp-tip-empty">Не удалось открыть детализацию.</p>';
    }
  }
  function openTip(html){
    var ov=document.getElementById('cp-tip-overlay');
    var bd=document.getElementById('cp-tip-content');
    if(!ov||!bd) return;
    bd.innerHTML=html;
    ov.classList.add('is-open');
    ov.setAttribute('aria-hidden','false');
  }
  function closeTip(){
    var ov=document.getElementById('cp-tip-overlay');
    if(!ov) return;
    ov.classList.remove('is-open');
    ov.setAttribute('aria-hidden','true');
  }
  function openFromEl(el){
    var b64=el.getAttribute('data-cp-b64');
    if(!b64) return;
    openTip(utf8FromB64(b64));
  }
  document.addEventListener('click',function(e){
    var t=e.target;
    if(t&&t.id==='cp-tip-overlay'){ closeTip(); }
  },true);
  document.addEventListener('keydown',function(e){
    if(e.key==='Escape') closeTip();
  },true);
  document.addEventListener('click',function(e){
    var x=e.target&&e.target.closest&&e.target.closest('#cp-tip-close');
    if(x) closeTip();
  },true);
  document.addEventListener('click',function(e){
    var el=e.target&&e.target.closest&&e.target.closest('.cp-status-hit');
    if(!el) return;
    e.preventDefault(); e.stopPropagation();
    openFromEl(el);
  },true);
  document.addEventListener('keydown',function(e){
    if(e.key!=='Enter'&&e.key!==' ') return;
    var el=e.target&&e.target.closest&&e.target.closest('.cp-status-hit');
    if(!el) return;
    e.preventDefault();
    openFromEl(el);
  },true);
})();
</script>
"""
)


_CONTROL_POINTS_POPOVER_FRAGMENT_LIGHT = (
    """
<style>
.cp-tip-overlay{position:fixed;inset:0;background:rgba(15,23,42,0.35);z-index:2147483000;
  display:none;align-items:center;justify-content:center;padding:max(10px,2vw);
  box-sizing:border-box;-webkit-overflow-scrolling:touch}
.cp-tip-overlay.is-open{display:flex!important}
.cp-tip-panel{position:relative;width:min(1120px,96vw);max-height:min(92vh,900px);
  display:flex;flex-direction:column;background:#ffffff;border:1px solid #cbd5e1;
  border-radius:12px;box-shadow:0 18px 48px rgba(15,23,42,0.18);overflow:hidden}
.cp-tip-toolbar{flex:0 0 auto;display:flex;align-items:center;justify-content:space-between;
  gap:10px;padding:10px 12px;border-bottom:1px solid #e5e7eb;background:#f9fafb}
.cp-tip-title{font:600 14px/1.2 Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:#111827}
.cp-tip-close{box-sizing:border-box;width:34px;height:34px;margin:0;padding:0;border-radius:8px;
  border:1px solid #cbd5e1;background:#ffffff;color:#111827;cursor:pointer;font-size:18px;line-height:1}
.cp-tip-close:hover{background:#f3f4f6}
.cp-tip-content{flex:1 1 auto;min-height:0;overflow:auto;padding:12px 14px;color:#111827;font-size:12px;
  font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.cp-tip-hdr{font:700 13px/1.35 Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:#111827;margin:0 0 10px 0}
.cp-tip-tbl{width:100%;border-collapse:separate;border-spacing:0;
  font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.cp-tip-tbl th,.cp-tip-tbl td{border:1px solid #cbd5e1;padding:6px 8px;text-align:left;vertical-align:top;color:#111827}
.cp-tip-tbl th{background:#f3f4f6;color:#111827;font-weight:700}
.cp-tip-tbl tr:nth-child(even) td{background:#f9fafb}
.cp-tip-empty{opacity:0.92;margin:0;color:#374151}
.cp-status-hit{display:inline-flex;align-items:center;justify-content:center;min-width:28px;min-height:28px;
  cursor:pointer;border-radius:6px;padding:2px}
.cp-status-hit:hover,.cp-status-hit:focus-visible{outline:2px solid #94a3b8;outline-offset:1px;background:rgba(148,163,184,0.12)}
</style>
<div id="cp-tip-overlay" class="cp-tip-overlay" aria-hidden="true">
  <div class="cp-tip-panel" role="dialog" aria-modal="true">
    <div class="cp-tip-toolbar">
      <span class="cp-tip-title">Детализация по вехе</span>
      <button type="button" class="cp-tip-close" id="cp-tip-close" title="Закрыть">×</button>
    </div>
    <div id="cp-tip-content" class="cp-tip-content"></div>
  </div>
</div>
<script>
(function(){
  function padB64(s){ var p=s.length%4; if(!p) return s; return s+'===='.slice(p); }
  function utf8FromB64(b64){
    try{
      b64=padB64(String(b64).replace(/-/g,'+').replace(/_/g,'/'));
      var bin=atob(b64);
      var bytes=new Uint8Array(bin.length);
      for(var i=0;i<bin.length;i++) bytes[i]=bin.charCodeAt(i);
      return new TextDecoder('utf-8').decode(bytes);
    }catch(e){
      return '<p class="cp-tip-empty">Не удалось открыть детализацию.</p>';
    }
  }
  function openTip(html){
    var ov=document.getElementById('cp-tip-overlay');
    var bd=document.getElementById('cp-tip-content');
    if(!ov||!bd) return;
    bd.innerHTML=html;
    ov.classList.add('is-open');
    ov.setAttribute('aria-hidden','false');
  }
  function closeTip(){
    var ov=document.getElementById('cp-tip-overlay');
    if(!ov) return;
    ov.classList.remove('is-open');
    ov.setAttribute('aria-hidden','true');
  }
  function openFromEl(el){
    var b64=el.getAttribute('data-cp-b64');
    if(!b64) return;
    openTip(utf8FromB64(b64));
  }
  document.addEventListener('click',function(e){
    var t=e.target;
    if(t&&t.id==='cp-tip-overlay'){ closeTip(); }
  },true);
  document.addEventListener('keydown',function(e){
    if(e.key==='Escape') closeTip();
  },true);
  document.addEventListener('click',function(e){
    var x=e.target&&e.target.closest&&e.target.closest('#cp-tip-close');
    if(x) closeTip();
  },true);
  document.addEventListener('click',function(e){
    var el=e.target&&e.target.closest&&e.target.closest('.cp-status-hit');
    if(!el) return;
    e.preventDefault(); e.stopPropagation();
    openFromEl(el);
  },true);
  document.addEventListener('keydown',function(e){
    if(e.key!=='Enter'&&e.key!==' ') return;
    var el=e.target&&e.target.closest&&e.target.closest('.cp-status-hit');
    if(!el) return;
    e.preventDefault();
    openFromEl(el);
  },true);
})();
</script>
"""
)


def _control_points_popover_fragment(theme: str = "dark") -> str:
    if str(theme or "").strip().lower() == "light":
        return _CONTROL_POINTS_POPOVER_FRAGMENT_LIGHT
    return _CONTROL_POINTS_POPOVER_FRAGMENT


_CONTROL_POINTS_SORT_SCRIPT = """
<script>
(function(){
  function parseNum(t){
    var s=String(t||"").replace(/\\s/g,"").replace(/\\u00a0/g,"").replace(",",".");
    var m=s.match(/-?\\d+(?:\\.\\d+)?/);
    return m?parseFloat(m[0]):NaN;
  }
  function cellKey(tr,colIdx){
    if(!tr||!tr.cells||!tr.cells[colIdx]) return "";
    return (tr.cells[colIdx].textContent||"").trim();
  }
  function compare(at,bt,dir){
    var an=parseNum(at), bn=parseNum(bt), cmp=0;
    if(!isNaN(an)&&!isNaN(bn)) cmp=an-bn;
    else cmp=String(at).localeCompare(String(bt),"ru",{numeric:true,sensitivity:"base"});
    return dir>0?cmp:-cmp;
  }
  function initTable(tbl){
    if(!tbl||tbl.getAttribute("data-cp-sort-ready")==="1") return;
    tbl.setAttribute("data-cp-sort-ready","1");
    var tbody=tbl.querySelector("tbody");
    if(!tbody) return;
    var projTh=tbl.querySelector("thead th.cp-col-project");
    if(projTh){
      projTh.classList.add("cp-sortable");
      var plab=(projTh.textContent||"Проект").trim();
      projTh.setAttribute("data-sort-label", plab);
      projTh.title="Клик — сортировка по проекту";
      projTh.addEventListener("click",function(ev){
        ev.preventDefault();
        var cur=projTh.getAttribute("data-sort-dir");
        var dir=cur==="1"?-1:1;
        tbl.querySelectorAll("thead th.cp-sortable").forEach(function(x){
          x.removeAttribute("data-sort-dir");
          x.textContent=x.getAttribute("data-sort-label")||"";
        });
        projTh.setAttribute("data-sort-dir", String(dir));
        projTh.textContent=plab+(dir>0?" \\u25B2":" \\u25BC");
        var rows=Array.prototype.slice.call(tbody.querySelectorAll("tr"));
        rows.sort(function(a,b){return compare(cellKey(a,0),cellKey(b,0),dir);});
        rows.forEach(function(r){tbody.appendChild(r);});
      });
    }
    tbl.querySelectorAll("thead tr:nth-child(2) th.cp-sub").forEach(function(th){
      th.classList.add("cp-sortable");
      var lab=(th.textContent||"").trim();
      th.setAttribute("data-sort-label", lab);
      th.title="Клик — сортировка по колонке";
      var colIdx=(th.cellIndex||0)+1;
      th.addEventListener("click",function(ev){
        ev.preventDefault();
        var cur=th.getAttribute("data-sort-dir");
        var dir=cur==="1"?-1:1;
        tbl.querySelectorAll("thead th.cp-sortable").forEach(function(x){
          x.removeAttribute("data-sort-dir");
          x.textContent=x.getAttribute("data-sort-label")||"";
        });
        th.setAttribute("data-sort-dir", String(dir));
        th.textContent=lab+(dir>0?" \\u25B2":" \\u25BC");
        var rows=Array.prototype.slice.call(tbody.querySelectorAll("tr"));
        rows.sort(function(a,b){return compare(cellKey(a,colIdx),cellKey(b,colIdx),dir);});
        rows.forEach(function(r){tbody.appendChild(r);});
      });
    });
  }
  document.querySelectorAll(".cp-table-wrap table.rendered-table").forEach(initTable);
})();
</script>
"""


def render_control_points_dashboard(st, mdf: pd.DataFrame, table_css: str) -> None:
    """Таблица «Контрольные точки проектов»: 3 блока по 4 вехи.

    ТЗ заказчика 2026-05-06:
    - Дашборд разбит на 3 отдельные таблицы (по 4 вехи в каждой).
    - В каждой таблице слева от названия проекта — общий **статус блока**
      (зелёный, если все 4 вехи блока в срок; иначе красный). Колонка
      «Статус» внутри ячеек вех **убрана**.
    - В ячейке вехи остаются 3 колонки: План / Факт / Откл.
    - При `% выполнения = 100%` — оранжевый текст `#f09355` в План/Факт; иначе белый.
    - При просрочке (Откл < 0) — красный текст `cp-otkl-late`.
    - Индикатор ●: по клику или Enter/Пробел открывается таблица задач MSP по вехе
      (без открытия при наведении мыши).
    """
    esc = html_module.escape
    if mdf is None or getattr(mdf, "empty", True):
        st.warning("Нет строк в данных MSP.")
        return

    filtered_mdf, _cp_filter_info = _apply_control_points_msp_filters(st, mdf)
    if filtered_mdf is None or getattr(filtered_mdf, "empty", True):
        st.info("Нет строк по выбранным фильтрам.")
        return

    df = build_control_points_df(filtered_mdf, hide_completed=False)
    if df.empty:
        st.warning("Нет строк проектов в данных MSP.")
        return
    view = df.copy()
    _proj_lab_to_raws = _control_points_project_label_to_raw_names(filtered_mdf)
    pcol_cp = _project_name_column(filtered_mdf)
    try:
        _cp_pct_global_max = _pct_scale_max_from_frame(filtered_mdf)
    except Exception:
        _cp_pct_global_max = None
    slug_kw_map = {s: (t, kw) for t, s, kw in get_control_point_milestones_effective()}

    ms_specs_full = [(t, s) for t, s, _k in get_control_point_milestones_effective()]
    groups = _control_points_split_groups(ms_specs_full)

    import streamlit.components.v1 as _components

    _cp_theme = "dark"
    try:
        from dashboards.light_theme import is_light_preview_active

        if is_light_preview_active():
            _cp_theme = "light"
    except Exception:
        pass

    _cp_css_raw = _control_points_css_raw(_cp_theme)
    _sticky_css = _control_points_iframe_sticky_css(_cp_theme)
    _head_styles = _cp_css_raw + _sticky_css

    project_w = "width:200px;min-width:200px;max-width:200px"
    table_blocks: List[str] = []
    _n_rows = len(view)
    _table_h_each = max(130, 96 + _n_rows * 38)

    for gi, grp in enumerate(groups, start=1):
        if not grp:
            continue

        thead1 = [
            f'<th rowspan="2" class="cp-col-project" style="{project_w}">Проект</th>',
        ]
        for _i, (title, _slug) in enumerate(grp):
            # На каждую веху — 4 подколонки: ● (статус) | План | Факт | Откл.
            _sep = " cp-ms-sep" if _i > 0 else ""
            thead1.append(
                f'<th colspan="4" class="cp-ghead cp-ms-block{_sep}">{esc(title)}</th>'
            )
        sub_headers: List[str] = []
        for _i, (_title, _slug) in enumerate(grp):
            _sep = " cp-ms-sep" if _i > 0 else ""
            sub_headers.extend(
                [
                    f'<th class="cp-sub cp-sub-status cp-ms-first{_sep}" title="Статус вехи">●</th>',
                    f'<th class="cp-sub">{esc("План")}</th>',
                    f'<th class="cp-sub">{esc("Факт")}</th>',
                    f'<th class="cp-sub cp-ms-last">{esc("Откл.")}</th>',
                ]
            )
        thead_html = (
            "<thead><tr>"
            + "".join(thead1)
            + "</tr><tr>"
            + "".join(sub_headers)
            + "</tr></thead>"
        )

        body: List[str] = ["<tbody>"]
        for _, r in view.iterrows():
            cells = [
                f'<td class="cp-col-project">{esc(str(r.get("project", "")))}</td>',
            ]
            for i, (_t, slug) in enumerate(grp):
                pct100 = bool(r.get(f"{slug}_pct100"))
                m_ok = bool(r.get(f"{slug}_ok", False))
                otkl_txt = str(r.get(f"{slug}_otkl", "") or "")
                _od = _parse_otkl_days_display(otkl_txt)
                otk_late = _od is not None and _od < 0
                # Колонка-статус вехи (кружок) — зелёный/красный.
                dot_cls = "cp-status-ok" if m_ok else "cp-status-bad"
                dot_al = (
                    "Веха в срок: факт не позже плана."
                    if m_ok
                    else "Просрочка: факт позже плана или нет дат."
                )
                _proj_disp = str(r.get("project", "")).strip()
                _plot_sec = _control_points_stage_from_project_label(_proj_disp)
                if pcol_cp and pcol_cp in getattr(filtered_mdf, "columns", []):
                    _raws = _proj_lab_to_raws.get(_proj_disp, [])
                    if not _raws:
                        _raws = _proj_lab_to_raws.get(
                            _control_points_base_project_label(_proj_disp), []
                        )
                    sub_proj = filtered_mdf[
                        filtered_mdf[pcol_cp].astype(str).str.strip().isin(_raws)
                    ]
                else:
                    sub_proj = filtered_mdf
                skel = slug_kw_map.get(slug)
                if skel:
                    mhit = _match_milestone_tasks(sub_proj, skel[1])
                    if _plot_sec:
                        mhit = _filter_milestone_tasks_by_plot_section(
                            mhit, str(_plot_sec)
                        )
                else:
                    mhit = pd.DataFrame()
                _detail_html = _cp_detail_panel_inner_html(
                    mhit, _t, pct_scale_max=_cp_pct_global_max
                )
                _b64_attr = html_module.escape(
                    base64.b64encode(_detail_html.encode("utf-8")).decode("ascii"),
                    quote=True,
                )
                _tip = f"Таблица задач по вехе. {dot_al} Откройте кликом или клавишей Enter."
                _sep = " cp-ms-sep" if i > 0 else ""
                status_cell_cls = f"cp-col-cell-status cp-ms-first{_sep}"
                cells.append(
                    f'<td class="{status_cell_cls}" title="{esc(_tip)}">'
                    f'<span class="cp-status-hit" data-cp-b64="{_b64_attr}" tabindex="0" role="button" '
                    f'aria-label="{esc(_tip)}">'
                    f'<span class="cp-status-dot {dot_cls}" aria-hidden="true"></span></span></td>'
                )
                plan_parts: List[str] = []
                fact_parts: List[str] = []
                otkl_parts: List[str] = []
                if pct100:
                    plan_parts.append("cp-td-pct-done")
                    fact_parts.append("cp-td-pct-done")
                if otk_late:
                    otkl_parts.append("cp-otkl-late")
                elif m_ok or (_od is not None and _od >= 0):
                    otkl_parts.append("cp-otkl-ok")
                otkl_parts.append("cp-ms-last")
                wc_plan = (' class="' + " ".join(plan_parts) + '"') if plan_parts else ""
                wc_fact = (' class="' + " ".join(fact_parts) + '"') if fact_parts else ""
                wc_otkl = ' class="' + " ".join(otkl_parts) + '"'
                cells.append(f"<td{wc_plan}>{esc(str(r.get(f'{slug}_plan', '')))}</td>")
                cells.append(f"<td{wc_fact}>{esc(str(r.get(f'{slug}_fact', '')))}</td>")
                cells.append(f"<td{wc_otkl}>{esc(otkl_txt)}</td>")
            body.append("<tr>" + "".join(cells) + "</tr>")
        body.append("</tbody>")

        html_tbl = (
            '<table class="rendered-table" border="0">'
            + thead_html
            + "".join(body)
            + "</table>"
        )
        table_blocks.append(
            '<div class="rendered-table-wrap cp-table-wrap cp-table-block">' + html_tbl + "</div>"
        )

    if not table_blocks:
        st.info("Нет блоков вех для отображения.")
        return

    _scroll_block = '<div class="cp-tables-stack">' + "".join(table_blocks) + "</div>"
    _iframe_html = _matrix_iframe_html_document(
        _head_styles,
        _scroll_block,
        extra_body_suffix=_control_points_popover_fragment(_cp_theme) + _CONTROL_POINTS_SORT_SCRIPT,
        body_class="cp-body-stack",
        color_scheme=_cp_theme,
    )
    _gap = 40 * max(0, len(table_blocks) - 1)
    _card_pad = 24 * len(table_blocks)
    _iframe_h = min(3200, 52 + len(table_blocks) * _table_h_each + _gap + _card_pad)
    if _cp_theme == "light":
        st.markdown(_DEV_MATRIX_STREAMLIT_HOST_CSS_LIGHT, unsafe_allow_html=True)
    _components.html(_iframe_html, height=_iframe_h, scrolling=False)

    drop_ok = [
        c
        for c in view.columns
        if str(c).endswith("_ok") or str(c).endswith("_warn_pct")
    ]
    export = view.drop(columns=drop_ok, errors="ignore")
    from utils import render_dataframe_excel_csv_downloads

    render_dataframe_excel_csv_downloads(
        export,
        file_stem="control_points",
        key_prefix="cp_msp_table",
        csv_label="Скачать таблицу (CSV, для Excel)",
    )


# ── Session-level кэш для матрицы ───────────────────────────────────────────
#
# Зачем: пересчёт `dedupe_msp_for_developer_projects` + `build_dev_tz_matrix_rows`
# на каждом изменении фильтра «Проект» был тяжёлым (десятки секунд на больших
# выгрузках MSP) → пользователя успевало выкидывать по разрыву websocket.
# Сами входные DataFrame не меняются между переключениями фильтра в рамках
# одной сессии — кэшируем по «отпечатку» кадра + ключу проекта + версии prefs.

_DEV_MATRIX_CACHE_KEY = "_dev_matrix_cache_v1"
# Инкремент при изменении логики `dedupe_msp_for_developer_projects` (сброс session-кэша dedupe).
_DEV_DEDUPE_CACHE_VER = 7


def _matrix_project_scope_tag(df: pd.DataFrame) -> str:
    """Уникальный тег набора проектов в куске MSP — усиливает ключ кэша матрицы (обход ложных попаданий)."""
    if df is None or getattr(df, "empty", True):
        return ""
    pc = _find_col(df, ["project name", "Проект", "Project", "проект"])
    if not pc or pc not in df.columns:
        return ""
    try:
        u = sorted({str(x).strip() for x in df[pc].dropna().astype(str).tolist() if str(x).strip()})
        return "|".join(u)[:800]
    except Exception:
        return ""


def _df_fingerprint(df: Optional[pd.DataFrame]) -> Tuple[Any, ...]:
    """Дешёвый, но достаточно уникальный отпечаток DataFrame для in-session кэша.

    Не использует hash содержимого (дорого на больших MSP). Берёт shape, id
    объекта и хэш кортежа из (первый/последний индекс, первое/последнее
    значение в первом столбце). Если DataFrame подменён — отпечаток меняется.
    Включает max(snapshot_date) и набор source-файлов — иначе после подмешивания
    старого MSP-месяца кэш мог отдавать матрицу со «старыми» нулевыми Откл.
    """
    if df is None:
        return ("none",)
    try:
        if getattr(df, "empty", True):
            return ("empty", id(df))
        cols = tuple(map(str, df.columns[:8]))
        first_idx = df.index[0]
        last_idx = df.index[-1]
        c0 = df.columns[0] if len(df.columns) else None
        first_val = "" if c0 is None else str(df.iloc[0, 0])[:64]
        last_val = "" if c0 is None else str(df.iloc[-1, 0])[:64]
        snap_max = ""
        if "snapshot_date" in df.columns:
            try:
                _sm = pd.to_datetime(df["snapshot_date"], errors="coerce").max()
                if pd.notna(_sm):
                    snap_max = pd.Timestamp(_sm).strftime("%Y-%m-%d")
            except Exception:
                snap_max = ""
        src_tag = ""
        src_col = next(
            (c for c in ("__source_file", "source_file", "_source_file") if c in df.columns),
            None,
        )
        if src_col is not None:
            try:
                srcs = sorted(
                    {
                        str(x).replace("\\", "/").split("/")[-1].strip().lower()
                        for x in df[src_col].dropna().astype(str).tolist()
                        if str(x).strip()
                    }
                )
                src_tag = "|".join(srcs)[:400]
            except Exception:
                src_tag = ""
        return (
            id(df),
            tuple(df.shape),
            cols,
            str(first_idx),
            str(last_idx),
            first_val,
            last_val,
            snap_max,
            src_tag,
        )
    except Exception:
        return ("err", id(df))


def _prefs_fingerprint() -> str:
    """Отпечаток текущих prefs матрицы (если поменяли подписи/маппинг — кэш сбросится)."""
    try:
        prefs = load_developer_projects_matrix_prefs()
        return json.dumps(prefs, ensure_ascii=False, sort_keys=True)[:512]
    except Exception:
        return ""


def _dev_matrix_cache(ss: Any) -> Dict[Any, Any]:
    if ss is None:
        return {}
    try:
        cache = ss.get(_DEV_MATRIX_CACHE_KEY)
    except Exception:
        return {}
    if not isinstance(cache, dict):
        cache = {}
        try:
            ss[_DEV_MATRIX_CACHE_KEY] = cache
        except Exception:
            pass
    return cache


def dedupe_msp_for_developer_projects_cached(
    df: pd.DataFrame, ss: Any = None
) -> pd.DataFrame:
    """In-session кэш для dedupe — переключение фильтра «Проект» не пересчитывает дубли заново."""
    if df is None or getattr(df, "empty", True):
        return df
    if ss is None:
        return dedupe_msp_for_developer_projects(df)
    cache = _dev_matrix_cache(ss)
    key = ("dedupe", _DEV_DEDUPE_CACHE_VER, _df_fingerprint(df))
    cached = cache.get(key)
    if isinstance(cached, pd.DataFrame):
        return cached
    out = dedupe_msp_for_developer_projects(df)
    try:
        cache[key] = out
    except Exception:
        pass
    return out


def build_dev_tz_matrix_rows_cached(
    mdf: pd.DataFrame,
    project_data: Optional[pd.DataFrame],
    ss: Any,
    *,
    project_label_for_scope: str = "",
) -> Tuple[List[Dict[str, Any]], str]:
    """In-session кэш для тяжёлой матрицы: ключ = отпечатки кадров + label + prefs."""
    if mdf is None or getattr(mdf, "empty", True):
        return [], ""
    if ss is None:
        return build_dev_tz_matrix_rows(
            mdf,
            project_data,
            ss,
            project_label_for_scope=project_label_for_scope,
        )
    cache = _dev_matrix_cache(ss)
    key = (
        "rows",
        _df_fingerprint(mdf),
        _matrix_project_scope_tag(mdf),
        _df_fingerprint(project_data),
        str(project_label_for_scope or ""),
        _prefs_fingerprint(),
    )
    cached = cache.get(key)
    if isinstance(cached, tuple) and len(cached) == 2:
        return cached  # type: ignore[return-value]
    res = build_dev_tz_matrix_rows(
        mdf,
        project_data,
        ss,
        project_label_for_scope=project_label_for_scope,
    )
    try:
        cache[key] = res
    except Exception:
        pass
    return res
