"""Маппинг статусов документов TESSA (KrState / KrStateID) → русские подписи."""
from __future__ import annotations

import re
from typing import Any, Optional

import pandas as pd

_KRSTATE_ID_TO_LABEL: dict[int, str] = {
    0: "Проект",
    1: "На согласовании",
    2: "Согласован",
    4: "На доработке",
    5: "Отмена",
    8: "Подписан",
    9: "Отказ",
    10: "На подписании",
    12: "На ознакомлении",
    13: "Снято",
    14: "На проверке",
    25: "Данные загружены",
}

# Фолбэк, если reference_krstates не загружен в session_state.
_KRSTATE_STATIC_MAP: dict[str, str] = {}
for _name, _ru in (
    ("KrStates_Doc_Active", "На согласовании"),
    ("Approving", "На согласовании"),
    ("KrStates_Doc_Approved", "Согласован"),
    ("Approved", "Согласован"),
    ("KrStates_Doc_Canceled", "Отмена"),
    ("Cancelled", "Отмена"),
    ("Canceled", "Отмена"),
    ("KrStates_Doc_Declined", "Отказ"),
    ("Declined", "Отказ"),
    ("KrStates_Doc_Disapproved", "Не согласован"),
    ("Not approved", "Не согласован"),
    ("KrStates_Doc_Draft", "Проект"),
    ("Draft", "Проект"),
    ("KrStates_Doc_Editing", "На доработке"),
    ("Amending", "На доработке"),
    ("KrStates_Doc_Registered", "Зарегистрирован"),
    ("Registered", "Зарегистрирован"),
    ("KrStates_Doc_Registration", "На регистрации"),
    ("Registration", "На регистрации"),
    ("KrStates_Doc_Signed", "Подписан"),
    ("Signed", "Подписан"),
    ("KrStates_Doc_Signing", "На подписании"),
    ("Signing", "На подписании"),
):
    _KRSTATE_STATIC_MAP[_name] = _ru
    _KRSTATE_STATIC_MAP[_name.casefold()] = _ru

_NUMERIC_STATUS_RE = re.compile(r"^\d+(?:\.0+)?$")


def krstate_id_to_label(val: Any) -> str:
    """KrStateID из tessa_*-id.csv → русское название статуса."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "Неизвестно"
    try:
        n = int(float(val))
    except (TypeError, ValueError):
        s = str(val).strip()
        return s if s and s.lower() not in ("nan", "none", "<na>", "nat") else "Неизвестно"
    return _KRSTATE_ID_TO_LABEL.get(n, str(n))


def _is_numeric_status_label(val: Any) -> bool:
    s = str(val).strip()
    return bool(s) and bool(_NUMERIC_STATUS_RE.fullmatch(s))


_KRSTATE_NAME_MAP_CACHE: dict[tuple, dict[str, str]] = {}


def tessa_krstate_name_map(krstates_df: Optional[pd.DataFrame] = None) -> dict[str, str]:
    if krstates_df is None:
        try:
            import streamlit as st

            krstates_df = st.session_state.get("reference_krstates")
        except Exception:
            krstates_df = None
    # Кеш: функция вызывается на каждую строку через krstate_raw_to_label (тысячи
    # раз за рендер), а сборка идёт iterrows по справочнику. Ключ — id+размер df
    # (в рамках одного рендера объект справочника из session стабилен).
    try:
        _key = (id(krstates_df), int(len(krstates_df))) if krstates_df is not None else (0, 0)
    except Exception:
        _key = None
    if _key is not None:
        _hit = _KRSTATE_NAME_MAP_CACHE.get(_key)
        if _hit is not None:
            return dict(_hit)
    out = dict(_KRSTATE_STATIC_MAP)
    if krstates_df is not None and not getattr(krstates_df, "empty", True):
        for _, row in krstates_df.iterrows():
            name = str(row.get("Название", "")).strip()
            ru = str(row.get("ru", "")).strip()
            en = str(row.get("en", "")).strip()
            if name and ru:
                out[name] = ru
                out[name.casefold()] = ru
            if en and ru:
                out[en] = ru
                out[en.casefold()] = ru
    if _key is not None:
        if len(_KRSTATE_NAME_MAP_CACHE) > 8:
            _KRSTATE_NAME_MAP_CACHE.clear()
        _KRSTATE_NAME_MAP_CACHE[_key] = dict(out)
    return out


def krstate_raw_to_label(raw: Any, status_map: Optional[dict[str, str]] = None) -> str:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return ""
    s = str(raw).strip()
    if not s or s.lower() in ("nan", "none", "<na>", "nat"):
        return ""
    if _is_numeric_status_label(s):
        return krstate_id_to_label(int(float(s)))
    sm = status_map or tessa_krstate_name_map()
    if s in sm:
        return sm[s]
    sl = s.casefold()
    if sl in sm:
        return sm[sl]
    for key, ru in sorted(sm.items(), key=lambda kv: len(kv[0]), reverse=True):
        if key and key in sl:
            return ru
    return s


def tessa_resolve_status_series(
    df: pd.DataFrame,
    krstates_df: Optional[pd.DataFrame] = None,
) -> pd.Series:
    """Текстовый статус документа: KrState (+ справочник) или KrStateID."""
    if df is None or getattr(df, "empty", True):
        return pd.Series(dtype=object)
    status_map = tessa_krstate_name_map(krstates_df)
    if "KrState" in df.columns:
        st_s = df["KrState"].map(lambda x: krstate_raw_to_label(x, status_map))
        bad = st_s.map(_is_numeric_status_label).fillna(False)
        if bad.any():
            st_s = st_s.where(~bad, st_s.map(krstate_id_to_label))
        if "KrStateID" in df.columns:
            miss = (
                st_s.eq("")
                | st_s.isna()
                | df["KrState"].isna()
                | bad
            )
            st_s = st_s.where(~miss, df["KrStateID"].map(krstate_id_to_label))
        still_bad = st_s.map(_is_numeric_status_label).fillna(False)
        if still_bad.any() and "KrStateID" in df.columns:
            st_s = st_s.where(~still_bad, df["KrStateID"].map(krstate_id_to_label))
        return st_s.replace("", "Неизвестно")
    if "KrStateID" in df.columns:
        return df["KrStateID"].map(krstate_id_to_label)
    return pd.Series(["Неизвестно"] * len(df), index=df.index)


def tessa_format_status_display_df(df: pd.DataFrame) -> pd.DataFrame:
    """Колонка «Статус» для таблиц; KrState — текст; KrStateID скрыт."""
    if df is None or getattr(df, "empty", True):
        return df
    out = df.copy()
    out["Статус"] = tessa_resolve_status_series(out)
    if "KrState" in out.columns:
        out["KrState"] = out["Статус"]
    if "KrStateID" in out.columns:
        out = out.drop(columns=["KrStateID"])
    return out
