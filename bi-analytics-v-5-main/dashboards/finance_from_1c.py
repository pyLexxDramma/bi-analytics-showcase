# -*- coding: utf-8 -*-
"""
Подстановка план/факт бюджета из оборотов 1С (session reference_1c_dannye),
когда в MSP нет колонок budget plan / budget fact.
"""
from __future__ import annotations

import re
from typing import Any, Optional

import numpy as np
import pandas as pd


def _turnover_article_has_lot_and_sublot(raw) -> bool:
    """
    ТЗ БДДС/БДР (1С): в расчёт включаются строки, где в «СтатьяОборотов» явно
    указан лот (родитель) или его подлот (дочерняя статья).

    B-2.2/B-06 (2026-05-07): расширены распознаваемые форматы — раньше regex
    `r"лот\\s*[\\.\\-]\\s*\\d"` не ловил «Лот №NN» (между «лот» и цифрой стоит «№»),
    а формат «NN.M» / «NN.M.K» (без слова «лот») не учитывался вовсе. В реальных
    выгрузках 1С (`web/1с_*_dannye.json`, тип статьи «БДДС») 60 уникальных
    статей делятся на:
      • «Лот №NN. <название>»  — родительская позиция (1339 строк в `Лот №08…`,
        1312 в `Лот №21…`, 504 в `Лот №11…`, 587 в `Лот №01…` и т.п.);
      • «NN.M[.K] <название>»  — дочерние подлоты этого NN-го лота
        (3957 в `8.5. Металлические…`, 3003 в `8.1. Фундаменты…`,
        857 в `21.1. Внутриплощадочные…` и т.п.);
      • прочие общехозяйственные («Поступления по основной деятельности»,
        «Услуги банка», «Оплата труда», …) — не лоты, отбрасываются.
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return False
    s = (
        str(raw)
        .replace("\xa0", " ")
        .replace("\u200b", "")
        .replace("\ufeff", "")
        .strip()
        .casefold()
        .replace("ё", "е")
    )
    if not s:
        return False
    # 1) Явное упоминание «лот <NN>», «лот №<NN>», «лот <NN>.<M>», «лот NN/N»,
    #    с любыми пробелами/дефисами/точками между токенами.
    if re.search(r"\bлот\b\s*[№#]?\s*\d", s):
        return True
    if re.search(r"\blots?\b\s*[#№]?\s*\d", s):  # eng: «lot 7», «lot #7»
        return True
    # 2) Подлот без слова «лот»: статья начинается с «NN.M[.K] » (как «8.5. …»,
    #    «21.1. …», «17.1.1 …»). Минимум один уровень подлота → две
    #    числовые группы через точку.
    if re.match(r"^\d+\.\d+(?:\.\d+)?\b", s):
        return True
    # 3) Маркеры «sublot/подлот».
    sublot_markers = ("подлот", "под лот", "сублот", "sub lot", "sublot")
    if any(m in s for m in sublot_markers):
        return True
    return False


def _filter_1c_frame_by_article_lot_sublot(frame: pd.DataFrame, *, art_col: Optional[str]) -> pd.DataFrame:
    if frame is None or getattr(frame, "empty", True) or not art_col or art_col not in frame.columns:
        return frame
    # «СтатьяОборотов» имеет низкую кардинальность (~60 уникальных) при тысячах строк —
    # считаем regex-предикат один раз на уникальное значение, затем map по словарю.
    col = frame[art_col]
    lut = {v: _turnover_article_has_lot_and_sublot(v) for v in pd.unique(col)}
    m = col.map(lut).fillna(False).astype(bool)
    if not bool(m.any()):
        return frame.iloc[0:0].copy()
    return frame.loc[m].copy()


def _turnover_rows_in_full_rubles(frame: pd.DataFrame) -> pd.Series:
    """
    Эвристика масштаба сумм: JSON 1С (*_dannye) — в тыс. руб.; demo CSV (new_csv/sample_budget) — в руб.

    Колонка ``__source_file`` (SQLite) помечает только demo-строки как уже в рублях; для 1С JSON
    по-прежнему используется median(Сумма) ≥ 500_000.
    """
    if frame is None or getattr(frame, "empty", True):
        return pd.Series(dtype=bool)
    idx = frame.index
    demo_mask = pd.Series(False, index=idx)
    src_col = None
    for c in frame.columns:
        cl = str(c).strip().casefold()
        if cl in ("__source_file", "source_file", "_source_file"):
            src_col = c
            break
    if src_col is not None:
        src = frame[src_col].fillna("").astype(str).str.lower()
        demo_mask = (
            src.str.contains("sample_budget")
            | src.str.contains("/new_csv/")
            | src.str.startswith("new_csv/")
        )
    amt_col = _pick_col(frame, ("Сумма", "amount"))
    if not amt_col:
        return demo_mask
    check_idx = idx[~demo_mask] if bool(demo_mask.any()) else idx
    if len(check_idx) == 0:
        return demo_mask
    med = float(
        _coerce_1c_money_series(frame.loc[check_idx, amt_col]).abs().median() or 0.0
    )
    full_rub = demo_mask.copy()
    full_rub.loc[check_idx] = med >= 500_000.0
    return full_rub


def _amount_series_to_rubles(frame: pd.DataFrame, amt_col: str) -> pd.Series:
    raw = _coerce_1c_money_series(frame[amt_col]).fillna(0.0)
    full_rub = _turnover_rows_in_full_rubles(frame)
    out = raw.copy()
    if bool((~full_rub).any()):
        out.loc[~full_rub] = out.loc[~full_rub] * 1000.0
    return out


def _demo_budget_source_mask(frame: pd.DataFrame) -> pd.Series:
    """Строки из new_csv/sample_budget, а не реальные budget-CSV из web/."""
    if frame is None or getattr(frame, "empty", True):
        return pd.Series(dtype=bool)
    src_col = None
    for c in frame.columns:
        cl = str(c).strip().casefold()
        if cl in ("__source_file", "source_file", "_source_file"):
            src_col = c
            break
    if src_col is None:
        return pd.Series(False, index=frame.index)
    src = frame[src_col].fillna("").astype(str).str.lower()
    return (
        src.str.contains("sample_budget")
        | src.str.contains("/new_csv/")
        | src.str.startswith("new_csv/")
    )


def _load_demo_budget_turnover_df() -> Optional[pd.DataFrame]:
    """Демо-обороты БДДС из SQLite (file_type=budget) или session project_data."""
    try:
        from config import ignore_demo_data_files

        if ignore_demo_data_files():
            return None
    except Exception:
        pass

    import streamlit as st

    try:
        from web_loader import _load_version_data, _web_db_mtime

        vid = st.session_state.get("web_version_id") or st.session_state.get(
            "active_web_version_id"
        )
        if not vid:
            try:
                from web_schema import get_active_version_id

                vid = get_active_version_id()
            except Exception:
                vid = None
        if vid:
            loaded = _load_version_data(int(vid), "budget", _web_db_mtime())
            if loaded is not None and not loaded.empty:
                demo_mask = _demo_budget_source_mask(loaded)
                if bool(demo_mask.any()):
                    out = loaded.loc[demo_mask].copy()
                    if "__source_file" not in out.columns:
                        out["__source_file"] = "new_csv/sample_budget_data.csv"
                    return out
    except Exception:
        pass
    pd_obj = st.session_state.get("project_data")
    if isinstance(pd_obj, pd.DataFrame) and not pd_obj.empty:
        demo_mask = _demo_budget_source_mask(pd_obj)
        if bool(demo_mask.any()):
            return pd_obj.loc[demo_mask].copy()
        art = _pick_col(pd_obj, ("СтатьяОборотов", "Статья оборотов", "article"))
        scen = _pick_col(pd_obj, ("Сценарий", "scenario"))
        per = _pick_col(pd_obj, ("Период", "period"))
        if art and scen and per:
            src_col = None
            for c in pd_obj.columns:
                if str(c).strip().casefold() in ("__source_file", "source_file", "_source_file"):
                    src_col = c
                    break
            if src_col is not None:
                src = pd_obj[src_col].fillna("").astype(str).str.lower()
                if src.str.contains("sample_|new_csv", regex=True).any():
                    return pd_obj.copy()
    return None


def _coerce_1c_money_series(raw: pd.Series) -> pd.Series:
    """Нормализация денежных сумм из выгрузки 1С (пробелы тысяч, скобки, ₽)."""
    if raw is None:
        return pd.Series(dtype="float64")
    s = raw.astype(str).str.strip()
    s = s.replace({"": np.nan, "nan": np.nan, "None": np.nan, "null": np.nan})
    s = s.str.replace(r"^\((.*)\)$", r"-\1", regex=True)
    s = s.str.replace(r"[^0-9,\.\-]", "", regex=True)
    mixed = s.str.contains(",", na=False) & s.str.contains(r"\.", na=False)
    s.loc[mixed] = s.loc[mixed].str.replace(".", "", regex=False)
    only_comma = s.str.contains(",", na=False) & ~s.str.contains(r"\.", na=False)
    s.loc[only_comma] = s.loc[only_comma].str.replace(",", ".", regex=False)
    multi_dot = s.str.count(r"\.").fillna(0) > 1
    if bool(multi_dot.any()):
        s.loc[multi_dot] = s.loc[multi_dot].str.replace(r"\.(?=.*\.)", "", regex=True)
    return pd.to_numeric(s, errors="coerce")


def _parse_1c_period_series(raw: pd.Series) -> pd.Series:
    """
    Период из 1С в *_dannye.json чаще всего в month-first формате:
    M/D/YYYY h:mm:ss AM/PM.
    Сначала парсим как month-first, затем добираем остаток day-first.
    """
    if raw is None:
        return pd.Series(dtype="datetime64[ns]")
    s = raw.astype(str).str.strip()
    # Даты периодов 1С сильно повторяются (помесячные обороты) — парсим только
    # уникальные значения dateutil-ом, затем разворачиваем обратно по позициям.
    uniq, inverse = np.unique(s.to_numpy(), return_inverse=True)
    parsed = pd.to_datetime(uniq, errors="coerce", dayfirst=False)
    need_fallback = parsed.isna()
    if bool(np.asarray(need_fallback).any()):
        fb = pd.to_datetime(uniq[np.asarray(need_fallback)], errors="coerce", dayfirst=True)
        parsed_vals = parsed.to_numpy(copy=True)
        parsed_vals[np.asarray(need_fallback)] = fb.to_numpy()
        parsed = pd.DatetimeIndex(parsed_vals)
    return pd.Series(parsed.to_numpy()[inverse], index=s.index)


def _pick_col(df: pd.DataFrame, needles: tuple[str, ...]) -> Optional[str]:
    cols_exact: dict[str, str] = {}
    for c in df.columns:
        cs = str(c).strip()
        if not cs:
            continue
        cols_exact[cs.casefold()] = cs
    for n in needles:
        k = str(n).strip().casefold()
        if k in cols_exact:
            return cols_exact[k]
    for c in df.columns:
        cs = str(c).strip()
        if not cs:
            continue
        cl = cs.casefold()
        for n in needles:
            nk = str(n).strip().casefold()
            if nk and nk in cl:
                return cs
    return None


def _guess_1c_period_column(df: pd.DataFrame) -> Optional[str]:
    """Если нет колонки «Период», ищем столбец с датами в первых строках."""
    if df is None or getattr(df, "empty", True):
        return None
    n = min(500, len(df))
    if n < 1:
        return None
    money_hints = ("сумма", "amount", "оборот", "оплат", "остаток")
    best_col: Optional[str] = None
    best_ok = 0
    for c in df.columns:
        cs = str(c).strip()
        cl = cs.casefold()
        if any(h in cl for h in money_hints):
            continue
        parsed = pd.to_datetime(df[c].head(n).astype(str).str.strip(), errors="coerce")
        ok = int(parsed.notna().sum())
        if ok > best_ok:
            best_ok = ok
            best_col = cs
    if best_col is not None and best_ok >= max(3, n // 25):
        return best_col
    return None


def _bddds_route_unassigned_plan_fact(
    t: pd.DataFrame,
    *,
    plan_mask: pd.Series,
    fact_mask: pd.Series,
) -> None:
    """
    После article-split строки со сценарием «ПЛАН»/«ФАКТ» без «Бюджет» в тексте сценария
    остаются с нулевыми __plan/__fact; fallback по fact_mask при этом не срабатывает,
    если хотя бы одна строка попала в fact_hit. Добираем такие суммы теми же масками сценария,
    что и в ветке без разнесения по статье «ФАКТ».
    """
    amt = pd.to_numeric(t["_amt"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    pl = pd.to_numeric(t["__plan"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    fc = pd.to_numeric(t["__fact"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    pm = np.asarray(plan_mask, dtype=bool)
    fm = np.asarray(fact_mask, dtype=bool)
    eps = 1e-9
    un = (np.abs(pl) < eps) & (np.abs(fc) < eps) & (np.abs(amt) > eps)
    if not bool(un.any()):
        return
    only_p = un & pm & ~fm
    only_f = un & fm & ~pm
    both = un & pm & fm
    pl = np.where(only_p, amt, pl)
    fc = np.where(only_f | both, amt, fc)
    t["__plan"] = pl
    t["__fact"] = fc


def _bddds_impute_missing_plan_from_fact_ratio(odf: pd.DataFrame) -> pd.DataFrame:
    """
    Если в `*_dannye.json` за часть месяцев есть только сценарий «ФАКТ» без строк «ПЛАН»
    (часто прошлый год), то после агрегации «budget plan» обнуляется при ненулевом факте.

    Оценка плана для таких строк: факт × (Σплан/Σфакт) по месяцам, где обе величины > 0,
    только внутри проекта и только если у проекта уже есть хотя бы один месяц с планом > 0.
    Межпроектная подстановка (глобальный коэффициент) не применяется — иначе проекты без
    сценария «План» (например, Есипово) получали бы искусственный план на графике.
    """
    if odf is None or getattr(odf, "empty", True):
        return odf
    out = odf.copy()
    imputed_any = False
    for _proj, chunk in out.groupby("project name"):
        idx = chunk.index
        bp = pd.to_numeric(out.loc[idx, "budget plan"], errors="coerce").fillna(0.0)
        bf = pd.to_numeric(out.loc[idx, "budget fact"], errors="coerce").fillna(0.0)
        if float(bp.sum()) <= 0.0:
            continue
        sel = (bp > 0.0) & (bf > 0.0)
        ratio: float | None = None
        if bool(sel.any()):
            sp = float(bp.loc[sel].sum())
            sf = float(bf.loc[sel].sum())
            if sf > 0.0 and np.isfinite(sp):
                ratio = sp / sf
        if ratio is None or not np.isfinite(ratio) or ratio <= 0.0:
            continue
        need = (bp <= 0.0) & (bf > 0.0)
        if not bool(need.any()):
            continue
        fill = bf.loc[need].to_numpy(dtype=float) * float(ratio)
        out.loc[idx[need], "budget plan"] = fill
        imputed_any = True
    if imputed_any:
        out.attrs["bddds_plan_imputed_ratio"] = True
    return out


def bddds_project_norm_keys_without_plan_scenario(
    reference_1c_dannye: Optional[pd.DataFrame] = None,
) -> set[str]:
    """
    Ключи проектов (_project_filter_norm_key), у которых в 1С есть обороты БДДС,
    но нет ни одной строки сценария «План» (план=0 по всем месяцам до impute).
    """
    syn = try_synthetic_budget_from_1c_dannye(
        reference_1c_dannye=reference_1c_dannye,
        impute_plan=False,
    )
    if syn is None or syn.empty or "project name" not in syn.columns:
        return set()
    from dashboards._renderers import _project_filter_norm_key

    out: set[str] = set()
    for _proj, chunk in syn.groupby("project name", dropna=False):
        bp = pd.to_numeric(chunk.get("budget plan"), errors="coerce").fillna(0.0)
        bf = pd.to_numeric(chunk.get("budget fact"), errors="coerce").fillna(0.0)
        if float(bf.abs().sum()) <= 0.0 and float(bp.abs().sum()) <= 0.0:
            continue
        if float(bp.sum()) <= 0.0:
            pk = _project_filter_norm_key(_proj)
            if pk:
                out.add(pk)
    return out


def zero_budget_plan_for_projects_without_1c_plan(
    summary: pd.DataFrame,
    *,
    reference_1c_dannye: Optional[pd.DataFrame] = None,
    project_norm_keys: set[str] | None = None,
) -> pd.DataFrame:
    """Обнуляет budget plan в сводке для проектов без сценария «План» в 1С."""
    if summary is None or summary.empty or "project name" not in summary.columns:
        return summary
    no_plan = project_norm_keys if project_norm_keys is not None else bddds_project_norm_keys_without_plan_scenario(
        reference_1c_dannye
    )
    if not no_plan:
        return summary
    from dashboards._renderers import (
        _project_filter_norm_key,
        _project_norm_key_matches_msp_keys,
    )

    out = summary.copy()
    for pk in no_plan:
        mask = out["project name"].map(_project_filter_norm_key).map(
            lambda rk: _project_norm_key_matches_msp_keys(rk, {pk})
        )
        if not bool(mask.any()):
            continue
        out.loc[mask, "budget plan"] = 0.0
        if "reserve budget" in out.columns and "budget fact" in out.columns:
            out.loc[mask, "reserve budget"] = pd.to_numeric(
                out.loc[mask, "budget fact"], errors="coerce"
            ).fillna(0.0)
    return out


# ==================== B-08/09 (2026-05-07): Утверждённый бюджет план/факт ====================
# ТЗ заказчика (скрин «ФИНАНСЫ» от 2026-05-07):
#
#     Утверждённый бюджет (=План)
#         = строки  ТипСтатьи == «БДДС»  ∧  Сценарий == «ПЛАН»
#                 ∧ «Статья оборотов»  БЕЗ маркера «(БДР)»
#           SUM(Сумма) × 1000   (1С отдаёт в тыс.руб → приводим к руб)
#
#     Фактические расходы (=Факт)
#         = строки  ТипСтатьи == «БДДС»  ∧  Сценарий == «ФАКТ»
#           SUM(Сумма) × 1000
#
# В отличие от `try_synthetic_budget_from_1c_dannye` (БДДС/БДР) — НЕ применяется фильтр
# `_turnover_article_has_lot_and_sublot` (заказчик хочет ВСЕ статьи, кроме (БДР)),
# и НЕ выполняется article-split / impute по коэффициенту план/факт. Сводка идёт по проекту.
def try_approved_budget_from_1c_dannye(
    *,
    reference_1c_dannye: Optional[pd.DataFrame] = None,
) -> Optional[pd.DataFrame]:
    """
    Возвращает DataFrame для отчёта «Утверждённый бюджет план/факт»:
    columns = [project name, budget plan, budget fact].
    Один row per project (агрегат). Денежные значения — в РУБЛЯХ.

    Возвращает None, если нет нужных колонок или нет ни одной БДДС-строки.
    """
    if reference_1c_dannye is not None:
        ref = reference_1c_dannye
    else:
        import streamlit as st

        ref = st.session_state.get("reference_1c_dannye")
    if ref is None or not isinstance(ref, pd.DataFrame) or ref.empty:
        return None

    t = ref.copy()
    c_typ = _pick_col(t, ("ТипСтатьи", "article_type", "Тип статьи"))
    c_scen = _pick_col(t, ("Сценарий", "scenario"))
    c_art = _pick_col(t, ("СтатьяОборотов", "Статья оборотов", "article"))
    c_amt = _pick_col(t, ("Сумма", "amount"))
    c_proj = _pick_col(
        t,
        ("Проект", "project", "проект", "проектдляотчетов", "проект для отчетов", "ИмяПроекта"),
    )
    if not (c_typ and c_scen and c_art and c_amt):
        return None

    typ_norm = t[c_typ].astype(str).str.strip().str.casefold()
    bdds = t[typ_norm.eq("бддс")].copy()
    if bdds.empty:
        return None

    scen = bdds[c_scen].astype(str).str.strip().str.casefold()
    art_norm = (
        bdds[c_art]
        .astype(str)
        .str.replace("\xa0", " ", regex=False)
        .str.replace("\u200b", "", regex=False)
        .str.strip()
        .str.casefold()
    )
    has_bdr_marker = art_norm.str.contains(r"\(бдр\)", regex=True, na=False) | art_norm.eq("бдр")
    amt = _amount_series_to_rubles(bdds, c_amt)

    plan_mask = scen.eq("план") & ~has_bdr_marker
    fact_mask = scen.eq("факт")

    bdds["__plan"] = np.where(plan_mask.to_numpy(), amt.to_numpy(), 0.0)
    bdds["__fact"] = np.where(fact_mask.to_numpy(), amt.to_numpy(), 0.0)

    if c_proj and c_proj in bdds.columns:
        grp = (
            bdds.groupby(c_proj, dropna=False, sort=True)[["__plan", "__fact"]]
            .sum()
            .reset_index()
            .rename(columns={c_proj: "project name"})
        )
    else:
        grp = pd.DataFrame(
            [
                {
                    "project name": "—",
                    "__plan": float(bdds["__plan"].sum()),
                    "__fact": float(bdds["__fact"].sum()),
                }
            ]
        )

    out = pd.DataFrame(
        {
            "project name": grp["project name"],
            "budget plan": grp["__plan"].astype(float),
            "budget fact": grp["__fact"].astype(float),
        }
    )
    out.attrs["data_source_1c_approved_budget"] = True
    return out


def _ref_1c_fingerprint(df: Optional[pd.DataFrame]) -> tuple:
    """Дешёвый отпечаток кадра оборотов 1С для in-session мемоизации (без хэша содержимого)."""
    if df is None:
        return ("none",)
    try:
        if getattr(df, "empty", True):
            return ("empty",)
        c0 = df.columns[0] if len(df.columns) else None
        return (
            tuple(df.shape),
            tuple(map(str, df.columns[:8])),
            str(df.index[0]),
            str(df.index[-1]),
            "" if c0 is None else str(df.iloc[0, 0])[:48],
            "" if c0 is None else str(df.iloc[-1, 0])[:48],
        )
    except Exception:
        return ("err", id(df))


def try_synthetic_budget_from_1c_dannye(
    *,
    reference_1c_dannye: Optional[pd.DataFrame] = None,
    impute_plan: bool = True,
) -> Optional[pd.DataFrame]:
    """In-session мемо-обёртка: за один рендер БДДС/Девелоперских функция зовётся
    5–8 раз с тем же кадром 1С. Кешируем результат по дешёвому отпечатку кадра
    (+ флаг impute_plan); сама сборка — в _try_synthetic_budget_from_1c_dannye_uncached.
    """
    ref = reference_1c_dannye
    if ref is None:
        try:
            import streamlit as st

            ref = st.session_state.get("reference_1c_dannye")
        except Exception:
            ref = None
    if ref is None or not isinstance(ref, pd.DataFrame) or ref.empty:
        return None
    _memo = None
    _key = None
    try:
        import streamlit as st

        _memo = st.session_state.setdefault("_syn_budget_memo_v1", {})
        _key = (_ref_1c_fingerprint(ref), bool(impute_plan))
        if _key in _memo:
            _c = _memo[_key]
            return _c.copy() if isinstance(_c, pd.DataFrame) else _c
    except Exception:
        _memo = None
        _key = None
    _res = _try_synthetic_budget_from_1c_dannye_uncached(
        reference_1c_dannye=ref, impute_plan=impute_plan
    )
    if _memo is not None and _key is not None:
        try:
            _memo[_key] = _res.copy() if isinstance(_res, pd.DataFrame) else _res
        except Exception:
            pass
    return _res


def _try_synthetic_budget_from_1c_dannye_uncached(
    *,
    reference_1c_dannye: Optional[pd.DataFrame] = None,
    impute_plan: bool = True,
) -> Optional[pd.DataFrame]:
    """
    Собирает DataFrame в формате дашборда БДДС: project name, plan end, budget plan, budget fact,
    plan_month / plan_quarter / plan_year, section.

    Строки без колонки периода или с неразобранной датой исключаются (не подставляются на max-дату).
    Статьи оборотов БДР не включаются в БДДС (как в прогнозном бюджете).

    ТЗ: в агрегацию попадают строки, где в «СтатьяОборотов» одновременно отражены лот и подлот
    (`_turnover_article_has_lot_and_sublot`). При отсутствии таких строк результат пустой → None.

    ТЗ БДДС (обороты 1С): план — сценарий содержит «Бюджет», статья не «ФАКТ» и не (БДР);
    факт — тот же бюджетный сценарий и статья оборотов ровно «ФАКТ». Если колонки статьи нет
    или по правилам выше не получается ни одной строки — используется прежнее разделение по словам
    в поле «Сценарий» (план/факт). Смешанные выгрузки («Бюджет»+статья и отдельные «ПЛАН»/«ФАКТ»):
    не попавшие в article-split строки добираются масками сценария. Если для месяца нет строк «ПЛАН»,
    но есть «ФАКТ», план может быть оценён коэффициентом Σплан/Σфакт по месяцам с полными данными (`_bddds_impute_missing_plan_from_fact_ratio`).

    Возвращает None, если в reference_1c_dannye нет сценария+суммы или не удаётся агрегировать.

    ``reference_1c_dannye``: если передан (например из CLI-скрипта), session_state не используется.
    """
    if reference_1c_dannye is not None:
        ref = reference_1c_dannye
    else:
        import streamlit as st

        ref = st.session_state.get("reference_1c_dannye")
    if ref is None or not isinstance(ref, pd.DataFrame) or ref.empty:
        return None
    t = ref.copy()
    scen = _pick_col(t, ("Сценарий", "scenario"))
    amt = _pick_col(
        t,
        ("Сумма", "amount", "суммаоборот", "сумма оборот", "суммавруб", "суммавруб"),
    )
    if not scen or not amt:
        return None
    art = _pick_col(t, ("СтатьяОборотов", "Статья оборотов", "article"))
    typ = _pick_col(t, ("ТипСтатьи", "article_type", "Тип статьи"))
    per = _pick_col(
        t,
        ("Период", "period", "месяц", "дата", "date", "периодитогов"),
    )
    proj = _pick_col(
        t,
        ("Проект", "project", "проект", "проектдляотчетов", "проект для отчетов"),
    )
    if not per:
        return None

    # Векторный эквивалент построчного _no_bdr (исключаем статьи (БДР)/«бдр» и
    # тип статьи с «бдр» без «бддс»). Раньше — t.apply(..., axis=1) по всему кадру.
    keep = pd.Series(True, index=t.index)
    if art and art in t.columns:
        a = t[art].astype(str).str.casefold()
        keep &= ~(a.str.contains("(бдр)", regex=False) | a.str.strip().eq("бдр"))
    if typ and typ in t.columns:
        tl = t[typ].astype(str).str.casefold()
        keep &= ~(tl.str.contains("бдр", regex=False) & ~tl.str.contains("бддс", regex=False))
    t = t[keep].copy()
    if t.empty:
        return None
    if art:
        t = _filter_1c_frame_by_article_lot_sublot(t, art_col=art)
    if t.empty:
        return None

    t["_amt"] = _amount_series_to_rubles(t, amt)
    sser = t[scen].astype(str)
    # Выгрузки 1С: по ТЗ план/факт из бюджетного сценария и статьи «ФАКТ» для факта; иначе — по сценарию.
    plan_mask = (
        sser.str.contains("бюджет", case=False, na=False)
        | sser.str.contains("budget", case=False, na=False)
        | (
            sser.str.contains("план", case=False, na=False)
            & ~sser.str.contains("факт", case=False, na=False)
        )
    )
    fact_mask = sser.str.contains("факт", case=False, na=False) | sser.str.contains(
        "fact", case=False, na=False
    )
    _norm_scen = sser.str.strip().str.casefold()
    plan_mask = plan_mask | _norm_scen.eq("план")
    fact_mask = fact_mask | _norm_scen.eq("факт")

    use_article_split = bool(art and art in t.columns)
    plan_hit = pd.Series(False, index=t.index)
    fact_hit = pd.Series(False, index=t.index)
    if use_article_split:
        scen_budget = sser.str.contains("бюджет", case=False, na=False) | sser.str.contains(
            "budget", case=False, na=False
        )
        art_norm = (
            t[art]
            .astype(str)
            .str.replace("\xa0", " ", regex=False)
            .str.replace("\u200b", "", regex=False)
            .str.strip()
            .str.casefold()
        )
        is_fact_article = art_norm.eq("факт")
        plan_hit = scen_budget & (~is_fact_article)
        fact_hit = scen_budget & is_fact_article
        if not (bool(plan_hit.any()) or bool(fact_hit.any())):
            use_article_split = False

    if use_article_split:
        amt_np = t["_amt"].to_numpy()
        t["__plan"] = np.where(plan_hit.to_numpy(), amt_np, 0.0)
        t["__fact"] = np.where(fact_hit.to_numpy(), amt_np, 0.0)
        if not bool(fact_hit.any()) and bool(fact_mask.any()):
            t["__fact"] = np.where(fact_mask.to_numpy(), amt_np, t["__fact"].to_numpy())
        _bddds_route_unassigned_plan_fact(t, plan_mask=plan_mask, fact_mask=fact_mask)
    else:
        if not plan_mask.any() and not fact_mask.any():
            return None
        t["__plan"] = np.where(plan_mask.to_numpy(), t["_amt"].to_numpy(), 0.0)
        t["__fact"] = np.where(fact_mask.to_numpy(), t["_amt"].to_numpy(), 0.0)
    t["_d"] = _parse_1c_period_series(t[per])
    t = t[t["_d"].notna()].copy()
    if t.empty:
        return None
    t["_m"] = t["_d"].dt.to_period("M")
    if proj and proj in t.columns:
        grp = t.groupby([proj, "_m"], dropna=False, sort=True)[["__plan", "__fact"]].sum().reset_index()
        grp = grp.rename(columns={proj: "project name"})
    else:
        grp = t.groupby("_m", dropna=False, sort=True)[["__plan", "__fact"]].sum().reset_index()
        grp["project name"] = "—"
    out_rows = []
    for _, r in grp.iterrows():
        m = r["_m"]
        if pd.isna(m):
            continue
        try:
            pe = m.to_timestamp(how="end")
        except Exception:
            continue
        out_rows.append(
            {
                "project name": r["project name"],
                "plan end": pe,
                "section": "—",
                "budget plan": float(r["__plan"]),
                "budget fact": float(r["__fact"]),
            }
        )
    if not out_rows:
        return None
    odf = pd.DataFrame(out_rows)
    _pe = pd.to_datetime(odf["plan end"], errors="coerce")
    odf["plan_month"] = _pe.dt.to_period("M")
    odf["plan_quarter"] = _pe.dt.to_period("Q")
    odf["plan_year"] = _pe.dt.to_period("Y")
    _no_plan_before_impute = set(
        odf.groupby("project name")["budget plan"]
        .sum()
        .loc[lambda s: pd.to_numeric(s, errors="coerce").fillna(0.0) <= 0.0]
        .index.astype(str)
    )
    if impute_plan:
        odf = _bddds_impute_missing_plan_from_fact_ratio(odf)
        if _no_plan_before_impute:
            odf.loc[odf["project name"].astype(str).isin(_no_plan_before_impute), "budget plan"] = 0.0
    odf.attrs["data_source_1c_synthetic"] = True
    return odf


def try_synthetic_bdr_from_1c_dannye(
    *,
    reference_1c_dannye: Optional[pd.DataFrame] = None,
) -> Optional[pd.DataFrame]:
    """
    БДР из `reference_1c_dannye` по ТЗ заказчика (расходы):

    - План: «Сценарий» содержит «Бюджет» / «План» / budget и «Статья оборотов» содержит «(БДР)»
      (или тип статьи БДР без БДДС).
    - Факт: «Сценарий» содержит «ФАКТ» / fact и та же статья БДР.

    В каждой строке в сумму расходов попадает только оборот по «РасходДоход» с признаком расходования;
    неклассифицированные отрицательные суммы трактуются как расход (как в прежней версии).

    Дополнительно выставляются legacy-колонки bdr_income=0, bdr_expense=fact, bdr_saldo=plan−fact.

    Отбор сумм только по строкам «СтатьяОборотов» с лотом и подлотом — см.
    `_turnover_article_has_lot_and_sublot`.

    ``reference_1c_dannye``: если передан (например из CLI-скрипта), session_state не используется.
    """
    if reference_1c_dannye is not None:
        ref = reference_1c_dannye
    else:
        import streamlit as st

        ref = st.session_state.get("reference_1c_dannye")
    if ref is None or not isinstance(ref, pd.DataFrame) or ref.empty:
        return None
    t = ref.copy()
    scen = _pick_col(
        t,
        (
            "Сценарий",
            "scenario",
            "сценарий",
            "видплана",
            "вид плана",
            "режим",
        ),
    )
    amt = _pick_col(
        t,
        (
            "Сумма",
            "amount",
            "суммаоборот",
            "сумма оборот",
            "суммавруб",
            "оборот",
            "суммаоборотов",
            "sum",
        ),
    )
    per = _pick_col(
        t,
        (
            "Период",
            "period",
            "месяц",
            "дата",
            "date",
            "периодитогов",
            "месяцитогов",
            "итоговыйпериод",
            "периодпрописью",
        ),
    )
    if not per:
        per = _guess_1c_period_column(t)
    proj = _pick_col(
        t,
        (
            "Проект",
            "project",
            "проект",
            "проектдляотчетов",
            "проект для отчетов",
            "наименованиепроекта",
        ),
    )
    rd = _pick_col(
        t,
        (
            "РасходДоход",
            "Расходдоход",
            "ПриходРасход",
            "приходрасход",
            "виддвижения",
            "вид движения",
            "видоборота",
            "вид оборота",
            "направление",
            "движение",
            "поступлениерасход",
            "дебеткредит",
        ),
    )
    art = _pick_col(
        t,
        (
            "СтатьяОборотов",
            "Статья оборотов",
            "article",
            "статьяоборотов",
            "статья",
        ),
    )
    typ = _pick_col(t, ("ТипСтатьи", "article_type", "Тип статьи", "типстатьи"))
    rd_synthetic = False
    if rd is None:
        t = t.copy()
        t["__bdr_rd_syn"] = "Расходование"
        rd = "__bdr_rd_syn"
        rd_synthetic = True
    if not scen or not amt or not per:
        return None

    def _bdr_article_or_type(fr: pd.DataFrame) -> pd.Series:
        m = pd.Series(False, index=fr.index)
        if art and art in fr.columns:
            a = fr[art].astype(str).fillna("")
            al = a.str.casefold()
            m = m | al.str.contains(r"\(бдр\)|^бдр$|^бдр\s", regex=True)
            m = m | (al.str.contains("бдр", regex=False) & (~al.str.contains("бддс", regex=False)))
        if typ and typ in fr.columns:
            tl = fr[typ].astype(str).fillna("").str.casefold()
            m = m | (tl.str.contains("бдр", regex=False) & (~tl.str.contains("бддс", regex=False)))
        return m

    strict_m = _bdr_article_or_type(t)
    approx_no_bdr_marker = not bool(strict_m.any())
    if approx_no_bdr_marker:
        pass
    else:
        t = t.loc[strict_m].copy()
    if t.empty:
        return None

    if art:
        t_before_lot = t
        t_f = _filter_1c_frame_by_article_lot_sublot(t, art_col=art)
        if getattr(t_f, "empty", True) and not getattr(t_before_lot, "empty", True):
            # Иначе синтетика БДР = None при несовпадении маркеров лота: график не строится.
            t = t_before_lot.copy()
            t.attrs = dict(getattr(t_before_lot, "attrs", {}) or {})
            t.attrs["bdr_article_lot_sublot_skipped_empty"] = True
        else:
            t = t_f
    if t.empty:
        return None

    scm = t[scen].astype(str).str.casefold()
    fact_rows = scm.str.contains("факт", na=False) | scm.str.contains("fact", na=False)
    plan_rows = (
        scm.str.contains("бюджет", na=False)
        | scm.str.contains("budget", na=False)
        | scm.str.contains("план", na=False)
    ) & ~fact_rows

    t["_amt"] = _amount_series_to_rubles(t, amt)

    rs = t[rd].astype(str).str.casefold()
    is_inc = rs.str.contains("поступ", na=False)
    is_exp = rs.str.contains("расход", na=False)
    amt_np = t["_amt"].to_numpy(dtype=float)
    exp_amt = np.zeros(len(t), dtype=float)
    exp_amt[is_exp.to_numpy()] = np.abs(amt_np[is_exp.to_numpy()])
    uncls = ~(is_inc.to_numpy() | is_exp.to_numpy())
    neg_other = uncls & (amt_np < 0)
    exp_amt[neg_other] = np.abs(amt_np[neg_other])

    scenario_unsplit = not bool(plan_rows.any()) and not bool(fact_rows.any())
    if scenario_unsplit:
        fe_amt = exp_amt
        pe_amt = np.zeros(len(t), dtype=float)
    else:
        pe_amt = np.where(plan_rows.to_numpy(), exp_amt, 0.0)
        fe_amt = np.where(fact_rows.to_numpy(), exp_amt, 0.0)
    t["_plan_exp"] = pe_amt
    t["_fact_exp"] = fe_amt

    t["_d"] = _parse_1c_period_series(t[per])
    t = t[t["_d"].notna()].copy()
    if t.empty:
        return None
    t["_m"] = t["_d"].dt.to_period("M")

    if proj and proj in t.columns:
        grp = (
            t.groupby([proj, "_m"], dropna=False, sort=True)[["_plan_exp", "_fact_exp"]]
            .sum()
            .reset_index()
        )
        grp = grp.rename(columns={proj: "project name"})
    else:
        grp = (
            t.groupby("_m", dropna=False, sort=True)[["_plan_exp", "_fact_exp"]]
            .sum()
            .reset_index()
        )
        grp["project name"] = "—"

    out_rows = []
    for _, r in grp.iterrows():
        m = r["_m"]
        if pd.isna(m):
            continue
        try:
            pe = m.to_timestamp(how="end")
        except Exception:
            continue
        pl = float(r["_plan_exp"])
        fc = float(r["_fact_exp"])
        dev = fc - pl
        out_rows.append(
            {
                "project name": r["project name"],
                "plan end": pe,
                "section": "—",
                "bdr_plan_expense": pl,
                "bdr_fact_expense": fc,
                "bdr_expense_deviation": dev,
                "bdr_income": 0.0,
                "bdr_expense": fc,
                "bdr_saldo": pl - fc,
            }
        )
    if not out_rows:
        return None
    odf = pd.DataFrame(out_rows)
    _pe = pd.to_datetime(odf["plan end"], errors="coerce")
    odf["plan_month"] = _pe.dt.to_period("M")
    odf["plan_quarter"] = _pe.dt.to_period("Q")
    odf["plan_year"] = _pe.dt.to_period("Y")
    odf.attrs["data_source_1c_synthetic_bdr"] = True
    odf.attrs["bdr_tz_plan_fact_expense"] = True
    if getattr(t, "attrs", None) and dict(getattr(t, "attrs") or {}).get(
        "bdr_article_lot_sublot_skipped_empty"
    ):
        odf.attrs["bdr_article_lot_sublot_skipped_empty"] = True
    if approx_no_bdr_marker:
        odf.attrs["bdr_approx_no_bdr_marker"] = True
    if rd_synthetic:
        odf.attrs["bdr_synthetic_rd_column"] = True
    if scenario_unsplit:
        odf.attrs["bdr_scenario_unsplit_all_to_fact"] = True
    return odf


def restrict_project_filter_labels_to_finance_data(
    labels: list[str],
    msp_df: Optional[pd.DataFrame] = None,
    *,
    kind: str = "bdds",
) -> list[str]:
    """
    Оставить в фильтре БДДС/БДР только проекты с ненулевыми суммами:
    в колонках MSP и/или в синтетике из ``reference_1c_dannye``.

    Иначе в списке остаются MSP-проекты без оборотов 1С (например «Новорижский»).
    Если ни MSP, ни 1С не дают сумм — возвращает labels без изменений.
    """
    if not labels:
        return list(labels or [])

    from dashboards._renderers import (
        _project_filter_norm_key,
        _project_norm_key_matches_msp_keys,
    )

    data_keys: set[str] = set()
    kind_l = (kind or "bdds").strip().lower()

    if msp_df is not None and not getattr(msp_df, "empty", True):
        if "project name" in msp_df.columns:
            if kind_l == "bdr":
                money_cols = [
                    c
                    for c in (
                        "bdr_plan_expense",
                        "bdr_fact_expense",
                        "bdr_income",
                        "bdr_expense",
                        "доходы",
                        "расходы",
                        "доход",
                        "расход",
                        "income",
                        "expense",
                    )
                    if c in msp_df.columns
                ]
            else:
                money_cols = [
                    c
                    for c in ("budget plan", "budget fact")
                    if c in msp_df.columns
                ]
            if money_cols:
                tmp = msp_df[["project name", *money_cols]].copy()
                amt = None
                for c in money_cols:
                    s = pd.to_numeric(tmp[c], errors="coerce").fillna(0.0).abs()
                    amt = s if amt is None else (amt + s)
                tmp["_amt"] = amt if amt is not None else 0.0
                for pname, total in (
                    tmp.groupby("project name", dropna=False)["_amt"].sum().items()
                ):
                    if float(total) <= 0.0:
                        continue
                    pk = _project_filter_norm_key(pname)
                    if pk:
                        data_keys.add(pk)

    try:
        syn = (
            try_synthetic_bdr_from_1c_dannye()
            if kind_l == "bdr"
            else try_synthetic_budget_from_1c_dannye()
        )
    except Exception:
        syn = None
    if syn is not None and not getattr(syn, "empty", True) and "project name" in syn.columns:
        for pname in syn["project name"].dropna().unique():
            pk = _project_filter_norm_key(pname)
            if pk:
                data_keys.add(pk)

    if not data_keys:
        return list(labels)

    out: list[str] = []
    for lab in labels:
        s = str(lab).strip()
        if not s:
            continue
        lk = _project_filter_norm_key(s)
        if not lk:
            continue
        if _project_norm_key_matches_msp_keys(lk, data_keys):
            out.append(s)
    return out


def ensure_budget_frame_with_fallback(
    df: pd.DataFrame,
    *,
    show_caption: bool = True,
    restrict_projects_from_df: bool = True,
    period_start: Any | None = None,
    period_end: Any | None = None,
    force_from_1c: bool = False,
    narrow_to_project_norm_key: Optional[str] = None,
) -> tuple[pd.DataFrame, bool]:
    """
    Возвращает (df_for_budget, used_fallback_1c).
    Если в исходном df нет непустых budget plan/fact, пытается собрать их из 1С.
    При force_from_1c=True всегда предпочитает синтетику из 1С.

    После сборки синтетики из 1С можно сузить строки до проектов из текущего MSP-фрейма
    и до интервала дат календаря (поле «plan end» в синтетике = конец месяца из «Период» JSON).

    narrow_to_project_norm_key: если задан (нормализованный ключ из _project_filter_norm_key),
    синтетика дополнительно сужается до этого проекта (и дочернего «… 1» и т.п.), чтобы таблицы
    БДДС не подтягивали остальные проекты при расхождении MSP и 1С.
    """
    import streamlit as st

    work = df.copy()
    has_cols = "budget plan" in work.columns and "budget fact" in work.columns
    if has_cols and not force_from_1c:
        bp = pd.to_numeric(work["budget plan"], errors="coerce").fillna(0.0)
        bf = pd.to_numeric(work["budget fact"], errors="coerce").fillna(0.0)
        msp_total = float(bp.abs().sum()) + float(bf.abs().sum())
        # MSP-задачи часто дают «копейки» (630k на весь проект) — не блокируем overlay 1С+demo.
        if msp_total >= 5_000_000.0:
            return work, False
    ref = resolve_reference_1c_dannye()
    syn = try_synthetic_budget_from_1c_dannye(reference_1c_dannye=ref)
    if syn is None or syn.empty:
        return work, False

    from dashboards._renderers import (
        _project_filter_norm_key,
        _project_norm_key_matches_msp_keys,
    )

    nt = (narrow_to_project_norm_key or "").strip()
    if restrict_projects_from_df and "project name" in work.columns:
        nz = work["project name"].dropna()
        # MSP пуст после фильтра периода, но выбран проект — тянем 1С по narrow key.
        if nz.empty and not nt:
            return work, False

        keys = {_project_filter_norm_key(x) for x in nz.unique()} if not nz.empty else set()
        keys.discard("")
        if nt:
            keys.add(nt)
        if keys:
            _rk = syn["project name"].map(_project_filter_norm_key)
            syn = syn[
                _rk.map(lambda rk: _project_norm_key_matches_msp_keys(rk, keys))
            ].copy()

    if nt and not syn.empty and "project name" in syn.columns:
        _rk_n = syn["project name"].map(_project_filter_norm_key)
        syn = syn[
            _rk_n.map(lambda rk: _project_norm_key_matches_msp_keys(rk, {nt}))
        ].copy()

    ps = period_start
    pe = period_end
    if ps is not None and pe is not None and not syn.empty:
        ts = pd.to_datetime(ps, errors="coerce")
        te = pd.to_datetime(pe, errors="coerce")
        if pd.notna(ts) and pd.notna(te):
            pe_col = pd.to_datetime(syn["plan end"], errors="coerce")
            syn = syn[
                pe_col.notna()
                & (pe_col >= ts.normalize())
                & (
                    pe_col
                    <= (te.normalize() + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))
                )
            ].copy()

    if syn.empty:
        return work, False

    return syn, True


def _filter_1c_budget_syn(
    syn: pd.DataFrame,
    *,
    project_norm_keys: set[str] | None = None,
    narrow_to_project_norm_key: str | None = None,
    period_start: Any | None = None,
    period_end: Any | None = None,
) -> pd.DataFrame:
    """Сужает синтетику 1С по проектам и календарному диапазону plan end."""
    if syn is None or syn.empty:
        return syn
    from dashboards._renderers import (
        _project_filter_norm_key,
        _project_norm_key_matches_msp_keys,
    )

    out = syn.copy()
    keys = {k for k in (project_norm_keys or set()) if k}
    if keys and "project name" in out.columns:
        _rk = out["project name"].map(_project_filter_norm_key)
        out = out[_rk.map(lambda rk: _project_norm_key_matches_msp_keys(rk, keys))].copy()
    nt = (narrow_to_project_norm_key or "").strip()
    if nt and not out.empty and "project name" in out.columns:
        _rk_n = out["project name"].map(_project_filter_norm_key)
        out = out[_rk_n.map(lambda rk: _project_norm_key_matches_msp_keys(rk, {nt}))].copy()
    ps = period_start
    pe = period_end
    if ps is not None and pe is not None and not out.empty:
        ts = pd.to_datetime(ps, errors="coerce")
        te = pd.to_datetime(pe, errors="coerce")
        if pd.notna(ts) and pd.notna(te):
            plan_end_series = pd.to_datetime(out["plan end"], errors="coerce")
            out = out[
                plan_end_series.notna()
                & (plan_end_series >= ts.normalize())
                & (
                    plan_end_series
                    <= (te.normalize() + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))
                )
            ].copy()
    return out


def expand_budget_month_grid(
    df: pd.DataFrame,
    *,
    period_col: str,
    period_original_col: str = "period_original",
    cal_start: Any | None = None,
    cal_end: Any | None = None,
    fill_columns: tuple[str, ...] = ("budget plan", "budget fact", "reserve budget"),
    group_by: str | None = "project name",
    format_period=None,
) -> pd.DataFrame:
    """
    Дополняет помесячный фрейм нулевыми строками на весь выбранный календарный диапазон.
    Исправляет потерю имени индекса после ``reindex`` (иначе сетка месяцев молча не строится).
    """
    if df is None or df.empty or cal_start is None or cal_end is None:
        return df
    if period_original_col not in df.columns:
        return df
    try:
        p0 = pd.Timestamp(cal_start).to_period("M")
        p1 = pd.Timestamp(cal_end).to_period("M")
        if p0 > p1:
            return df
        month_idx = pd.period_range(p0, p1, freq="M")
    except Exception:
        return df

    if format_period is None:
        from utils import format_period_ru as format_period

    def _expand_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
        out = (
            chunk.set_index(period_original_col)
            .reindex(month_idx)
            .rename_axis(period_original_col)
            .reset_index()
        )
        for col in fill_columns:
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
        if period_col:
            out[period_col] = out[period_original_col].apply(format_period)
        return out

    if group_by and group_by in df.columns:
        parts: list[pd.DataFrame] = []
        for _gval, chunk in df.groupby(group_by, dropna=False):
            expanded = _expand_chunk(chunk)
            expanded[group_by] = _gval
            parts.append(expanded)
        if not parts:
            return df
        cols = list(df.columns)
        merged = pd.concat(parts, ignore_index=True)
        for col in cols:
            if col not in merged.columns:
                merged[col] = df[col].iloc[0] if len(df) else None
        return merged[cols]

    return _expand_chunk(df)


def merge_budget_summary_by_norm_project_month(
    summary: pd.DataFrame,
    *,
    period_col: str,
    period_original_col: str = "period_original",
    project_col: str = "project name",
    fill_columns: tuple[str, ...] = ("budget plan", "budget fact", "reserve budget"),
    canonical_project_name: str | None = None,
) -> pd.DataFrame:
    """Склеивает строки MSP и 1С с разными подписями проекта в одну серию по месяцам."""
    if summary is None or summary.empty or project_col not in summary.columns:
        return summary
    if period_original_col not in summary.columns:
        return summary
    from dashboards._renderers import _project_filter_norm_key

    out = summary.copy()
    out["_norm_pk"] = out[project_col].map(_project_filter_norm_key)
    name_map: dict[str, str] = {}
    for nm in out[project_col].dropna().unique():
        pk = _project_filter_norm_key(nm)
        if pk and pk not in name_map:
            name_map[pk] = str(nm)
    if canonical_project_name:
        canon = str(canonical_project_name).strip()
        if canon:
            pk = _project_filter_norm_key(canon)
            if pk:
                name_map[pk] = canon

    agg: dict[str, str] = {period_col: "first", project_col: "first"}
    for col in fill_columns:
        if col in out.columns:
            agg[col] = "sum"
    for col in out.columns:
        if col.startswith("budget ") and col not in agg and col not in (period_col, project_col, period_original_col, "_norm_pk"):
            agg[col] = "sum"

    merged = (
        out.groupby([period_original_col, "_norm_pk"], dropna=False)
        .agg(agg)
        .reset_index()
    )
    merged[project_col] = merged["_norm_pk"].map(lambda k: name_map.get(k, k))
    merged = merged.drop(columns=["_norm_pk"], errors="ignore")
    cols = [c for c in summary.columns if c in merged.columns]
    return merged[cols] if cols else merged


def _is_parent_project_norm_key(parent_pk: str, child_pk: str) -> bool:
    """True, если parent_pk - базовое имя MSP, а child_pk - тот же проект с номером/суффиксом."""
    if not parent_pk or not child_pk or parent_pk == child_pk:
        return False
    from dashboards._renderers import _project_norm_key_matches_msp_keys

    if not _project_norm_key_matches_msp_keys(child_pk, {parent_pk}):
        return False
    if child_pk.startswith(parent_pk + " "):
        return True
    return len(child_pk) > len(parent_pk)


def consolidate_budget_summary_parent_child_aliases(
    summary: pd.DataFrame,
    *,
    period_col: str,
    period_original_col: str = "period_original",
    project_col: str = "project name",
) -> pd.DataFrame:
    """Ubrat roditelskie MSP-stroki, esli na tot zhe mesyac est dochernij klyuch 1S."""
    if summary is None or summary.empty or project_col not in summary.columns:
        return summary
    if period_original_col not in summary.columns:
        return summary
    from dashboards._renderers import _project_filter_norm_key

    out = summary.copy()
    out["_norm_pk"] = out[project_col].map(_project_filter_norm_key)
    drop_idx: list[Any] = []

    for _, grp in out.groupby(period_original_col, dropna=False):
        pks = {pk for pk in grp["_norm_pk"].tolist() if pk}
        if len(pks) < 2:
            continue
        parent_pks = {
            pk
            for pk in pks
            if any(_is_parent_project_norm_key(pk, other) for other in pks if other != pk)
        }
        if not parent_pks:
            continue
        drop_idx.extend(grp.index[grp["_norm_pk"].isin(parent_pks)].tolist())

    if drop_idx:
        out = out.drop(index=drop_idx)
    return out.drop(columns=["_norm_pk"], errors="ignore").reset_index(drop=True)


def finalize_budget_summary_for_display(
    summary: pd.DataFrame,
    *,
    period_col: str,
    period_start: Any | None = None,
    period_end: Any | None = None,
    reference_1c_dannye: Optional[pd.DataFrame] = None,
    project_norm_keys: set[str] | None = None,
    narrow_to_project_norm_key: str | None = None,
) -> pd.DataFrame:
    """Normalizaciya svodki pered grafikom i tablicami BDDS."""
    if summary is None or summary.empty:
        return summary
    out, _ = overlay_1c_on_budget_summary(
        summary,
        period_col=period_col,
        period_start=period_start,
        period_end=period_end,
        project_norm_keys=project_norm_keys,
        narrow_to_project_norm_key=narrow_to_project_norm_key,
        reference_1c_dannye=reference_1c_dannye,
    )
    out = consolidate_budget_summary_parent_child_aliases(
        out,
        period_col=period_col,
    )
    out = merge_budget_summary_by_norm_project_month(
        out,
        period_col=period_col,
    )
    return zero_budget_plan_for_projects_without_1c_plan(
        out,
        reference_1c_dannye=reference_1c_dannye,
    )


def resolve_reference_1c_dannye(
    reference_1c_dannye: Optional[pd.DataFrame] = None,
) -> Optional[pd.DataFrame]:
    """reference из аргумента или session_state (для overlay/синтетики БДДС)."""
    if reference_1c_dannye is not None and isinstance(reference_1c_dannye, pd.DataFrame):
        if not reference_1c_dannye.empty:
            return reference_1c_dannye
    import streamlit as st

    ref = st.session_state.get("reference_1c_dannye")
    if ref is not None and isinstance(ref, pd.DataFrame) and not ref.empty:
        return ref
    try:
        from web_loader import _load_version_data, _web_db_mtime

        vid = st.session_state.get("web_version_id") or st.session_state.get(
            "active_web_version_id"
        )
        if not vid:
            from web_schema import get_active_version_id

            vid = get_active_version_id()
        if vid:
            loaded = _load_version_data(int(vid), "reference_dannye", _web_db_mtime())
            if loaded is not None and not loaded.empty:
                st.session_state["reference_1c_dannye"] = loaded
                return loaded
    except Exception:
        pass
    try:
        from web_loader import (
            _load_1c_json_spravochniki,
            pick_latest_snapshot_files,
            scan_web_files,
        )

        files, _ = pick_latest_snapshot_files(scan_web_files(extensions=(".json",)))
        for fi in reversed(files):
            if not str(fi.get("name", "")).lower().endswith(".json"):
                continue
            probe = _load_1c_json_spravochniki(fi["path"])
            if probe is not None and not probe.empty:
                st.session_state["reference_1c_dannye"] = probe
                return probe
    except Exception:
        pass
    return None


def _normalize_turnover_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Приводит demo CSV и JSON 1С к общим именам колонок."""
    if frame is None or getattr(frame, "empty", True):
        return frame
    out = frame.copy()
    renames: dict[str, str] = {}
    for c in list(out.columns):
        cl = str(c).strip().casefold()
        if cl in ("статьяоборотов", "статья оборотов", "article"):
            renames[c] = "СтатьяОборотов"
        elif cl in ("сценарий", "scenario"):
            renames[c] = "Сценарий"
        elif cl in ("период", "period"):
            renames[c] = "Период"
        elif cl in ("сумма", "amount"):
            renames[c] = "Сумма"
        elif cl in ("проект", "project"):
            renames[c] = "Проект"
        elif cl in ("типстатьи", "тип статьи", "article_type"):
            renames[c] = "ТипСтатьи"
        elif cl in ("расходдоход", "приходрасход", "вид движения"):
            renames[c] = "РасходДоход"
    if renames:
        out = out.rename(columns=renames)
    return out


def resolve_budget_turnover_dannye(
    reference_1c_dannye: Optional[pd.DataFrame] = None,
) -> Optional[pd.DataFrame]:
    """
    Обороты БДДС для синтетики/overlay: 1С reference_dannye + demo budget (new_csv/sample_budget_data.csv).
    """
    ref = resolve_reference_1c_dannye(reference_1c_dannye)
    demo = _load_demo_budget_turnover_df()
    parts: list[pd.DataFrame] = []
    if ref is not None and not ref.empty:
        parts.append(_normalize_turnover_columns(ref.copy()))
    if demo is not None and not demo.empty:
        parts.append(_normalize_turnover_columns(demo.copy()))
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    merged = pd.concat(parts, ignore_index=True, sort=False)
    merged.attrs["budget_turnover_merged_demo"] = True
    return merged


def _bdds_month_label_short(ts: pd.Timestamp) -> str:
    if ts is None or pd.isna(ts):
        return ""
    return pd.Timestamp(ts).strftime("%m.%y")


def bdds_project_turnover_date_bounds(
    project_name: str,
    *,
    reference_1c_dannye: Optional[pd.DataFrame] = None,
) -> tuple[Any | None, Any | None]:
    """Мин/макс даты оборотов 1С по проекту (для дефолта периода БДДС)."""
    ref = resolve_budget_turnover_dannye(reference_1c_dannye)
    if ref is None or ref.empty or not str(project_name or "").strip():
        return None, None
    from dashboards._renderers import _project_filter_norm_key, _project_norm_key_matches_msp_keys

    proj = _pick_col(ref, ("Проект", "project", "проект"))
    per = _pick_col(ref, ("Период", "period"))
    if not proj or not per:
        return None, None
    pk = _project_filter_norm_key(project_name)
    t = ref[
        ref[proj]
        .map(_project_filter_norm_key)
        .map(lambda rk: _project_norm_key_matches_msp_keys(rk, {pk}))
    ].copy()
    if t.empty:
        return None, None
    d = _parse_1c_period_series(t[per]).dropna()
    if d.empty:
        return None, None
    return d.min().date(), d.max().date()


def _bdds_turnover_g_for_project(
    *,
    project_name: str,
    period_start: Any | None = None,
    period_end: Any | None = None,
    reference_1c_dannye: Optional[pd.DataFrame] = None,
    max_months: int = 24,
    prefer_budget_scenario: bool = False,
) -> Optional[tuple[pd.DataFrame, list, str, Any]]:
    """
    Общая подготовка оборотов БДДС для матрицы и помесячной сводки:
    возвращает (g, months, art_col, project_name).
    """
    ref = resolve_budget_turnover_dannye(reference_1c_dannye)
    if ref is None or ref.empty:
        return None
    from dashboards._renderers import _project_filter_norm_key, _project_norm_key_matches_msp_keys

    t = ref.copy()
    scen = _pick_col(t, ("Сценарий", "scenario"))
    amt = _pick_col(t, ("Сумма", "amount"))
    art = _pick_col(t, ("СтатьяОборотов", "Статья оборотов", "article"))
    per = _pick_col(t, ("Период", "period"))
    proj = _pick_col(t, ("Проект", "project", "проект"))
    rd = _pick_col(t, ("РасходДоход", "ПриходРасход", "вид движения"))
    typ = _pick_col(t, ("ТипСтатьи", "article_type", "Тип статьи"))
    if not scen or not amt or not art or not per or not proj:
        return None

    pk = _project_filter_norm_key(project_name)
    t = t[t[proj].map(_project_filter_norm_key).map(lambda rk: _project_norm_key_matches_msp_keys(rk, {pk}))].copy()
    if t.empty:
        return None

    # Векторный эквивалент построчного _no_bdr (см. try_synthetic_budget_from_1c_dannye).
    keep = pd.Series(True, index=t.index)
    if art and art in t.columns:
        a = t[art].astype(str).str.casefold()
        keep &= ~(a.str.contains("(бдр)", regex=False) | a.str.strip().eq("бдр"))
    if typ and typ in t.columns:
        tl = t[typ].astype(str).str.casefold()
        keep &= ~(tl.str.contains("бдр", regex=False) & ~tl.str.contains("бддс", regex=False))
    t = t[keep].copy()
    if art:
        t = _filter_1c_frame_by_article_lot_sublot(t, art_col=art)
    if t.empty:
        return None

    t["_amt"] = _amount_series_to_rubles(t, amt)
    t["_d"] = _parse_1c_period_series(t[per])
    t = t[t["_d"].notna()].copy()
    if period_start is not None and period_end is not None:
        ts = pd.to_datetime(period_start, errors="coerce")
        te = pd.to_datetime(period_end, errors="coerce")
        if pd.notna(ts) and pd.notna(te):
            te_inc = te + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
            t = t[(t["_d"] >= ts.normalize()) & (t["_d"] <= te_inc)].copy()
    if t.empty:
        return None

    sser = t[scen].astype(str)
    if prefer_budget_scenario:
        plan_mask = sser.str.contains("бюджет", case=False, na=False) | sser.str.contains(
            "budget", case=False, na=False
        )
        fact_mask = sser.str.contains("факт", case=False, na=False) | sser.str.contains(
            "fact", case=False, na=False
        )
    else:
        plan_mask = (
            sser.str.contains("бюджет", case=False, na=False)
            | sser.str.contains("budget", case=False, na=False)
            | (
                sser.str.contains("план", case=False, na=False)
                & ~sser.str.contains("факт", case=False, na=False)
            )
        )
        fact_mask = sser.str.contains("факт", case=False, na=False) | sser.str.contains(
            "fact", case=False, na=False
        )
    t["_plan"] = np.where(plan_mask.to_numpy(), t["_amt"].to_numpy(), 0.0)
    t["_fact"] = np.where(fact_mask.to_numpy(), t["_amt"].to_numpy(), 0.0)
    t["__plan"] = t["_plan"]
    t["__fact"] = t["_fact"]
    _bddds_route_unassigned_plan_fact(t, plan_mask=plan_mask, fact_mask=fact_mask)
    t["_plan"] = pd.to_numeric(t["__plan"], errors="coerce").fillna(0.0)
    t["_fact"] = pd.to_numeric(t["__fact"], errors="coerce").fillna(0.0)

    t["_m"] = t["_d"].dt.to_period("M")
    months = sorted(t["_m"].dropna().unique())
    if not months:
        return None
    month_totals = (
        t.groupby("_m")[["_plan", "_fact"]]
        .sum()
        .assign(_abs=lambda df: df["_plan"].abs() + df["_fact"].abs())
    )
    months_active: list = []
    for m in sorted(month_totals.index):
        pl = float(month_totals.loc[m, "_plan"])
        fc = float(month_totals.loc[m, "_fact"])
        if pl + fc <= 0.0:
            continue
        # Подозрительный «план без факта» (демо/ошибочная выгрузка) — обнуляем план.
        if pl > 500_000_000.0 and fc < pl * 0.05:
            pl = 0.0
        if pl + fc <= 0.0:
            continue
        months_active.append(m)
    # Все активные месяцы (раньше ошибочно брали только 2024+2026 и резали
    # суммы >100 млн за 2025+ — «Ленинский» и др. проекты с оборотами 2025+ ломались).
    months = months_active[: max(1, int(max_months))]
    if not months:
        return None

    if rd and rd in t.columns:
        rs = t[rd].astype(str).str.casefold()
        t["_section"] = np.where(
            rs.str.contains("поступ", na=False),
            "Поступления",
            "Платежи",
        )
    else:
        t["_section"] = "Платежи"

    g = (
        t.groupby(["_section", art, "_m"], dropna=False)[["_plan", "_fact"]]
        .sum()
        .reset_index()
    )
    demo_rows = _turnover_rows_in_full_rubles(t)
    t_ratio_src = t.loc[~demo_rows] if bool((~demo_rows).any()) else t
    pairs = t_ratio_src.groupby("_m")[["_plan", "_fact"]].sum()
    sel = (pairs["_plan"] > 0) & (pairs["_fact"] > 0) & (pairs["_plan"] < 5e8) & (pairs["_fact"] < 5e8)
    global_ratio = None
    if bool(sel.any()):
        sp = float(pairs.loc[sel, "_plan"].sum())
        sf = float(pairs.loc[sel, "_fact"].sum())
        if sf > 0:
            global_ratio = sp / sf
    for m in months:
        need = (g["_m"] == m) & (g["_plan"] <= 0) & (g["_fact"] > 0)
        if not bool(need.any()) or global_ratio is None:
            continue
        g.loc[need, "_plan"] = g.loc[need, "_fact"] * float(global_ratio)

    return g, months, art, project_name


def build_bdds_plan_fact_analysis_table(
    *,
    project_name: str,
    period_start: Any | None = None,
    period_end: Any | None = None,
    reference_1c_dannye: Optional[pd.DataFrame] = None,
    max_months: int = 24,
) -> Optional[pd.DataFrame]:
    """
    План-фактный анализ БДДС: по месяцам (заголовок) → статьи с П/Ф/Δ.
    Длинный формат (не широкая матрица), чтобы не было пустых колонок слева.
    """
    prep = _bdds_turnover_g_for_project(
        project_name=project_name,
        period_start=period_start,
        period_end=period_end,
        reference_1c_dannye=reference_1c_dannye,
        max_months=max_months,
    )
    if prep is None:
        return None
    g, months, art, _proj_nm = prep
    from utils import format_million_rub, format_period_ru

    if not months:
        return None

    g = g[g["_m"].isin(months)].copy()
    if g.empty:
        return None

    _min_show = 50_000.0

    def _fmt(v: float) -> str:
        return format_million_rub(v, decimals=1) if abs(v) >= _min_show else ""

    rows: list[dict] = []
    for m in months:
        chunk_m = g[g["_m"] == m]
        m_plan = float(chunk_m["_plan"].sum())
        m_fact = float(chunk_m["_fact"].sum())
        if abs(m_plan) + abs(m_fact) < _min_show:
            continue
        try:
            m_lbl = format_period_ru(m)
        except Exception:
            m_lbl = _bdds_month_label_short(m.to_timestamp())

        rows.append(
            {
                "Статья": m_lbl,
                "План, млн. руб.": "",
                "Факт, млн. руб.": "",
                "Отклонение, млн. руб.": "",
                "_row_kind": "project",
            }
        )

        # Статьи месяца с ненулевым оборотом (родители и подлоты).
        arts = (
            chunk_m.groupby(art, dropna=False)[["_plan", "_fact"]]
            .sum()
            .reset_index()
        )
        arts["_abs"] = arts["_plan"].abs() + arts["_fact"].abs()
        arts = arts[arts["_abs"] >= _min_show].sort_values("_abs", ascending=False)
        for _, ar in arts.iterrows():
            pl = float(ar["_plan"])
            fc = float(ar["_fact"])
            rows.append(
                {
                    "Статья": f"  {ar[art]}",
                    "План, млн. руб.": _fmt(pl),
                    "Факт, млн. руб.": _fmt(fc),
                    "Отклонение, млн. руб.": _fmt(fc - pl),
                    "_row_kind": "",
                }
            )

        rows.append(
            {
                "Статья": f"  Итого {m_lbl}",
                "План, млн. руб.": _fmt(m_plan),
                "Факт, млн. руб.": _fmt(m_fact),
                "Отклонение, млн. руб.": _fmt(m_fact - m_plan),
                "_row_kind": "total",
            }
        )

    if not rows:
        return None

    # Общий итог
    all_plan = float(g["_plan"].sum())
    all_fact = float(g["_fact"].sum())
    rows.append(
        {
            "Статья": "ИТОГО",
            "План, млн. руб.": _fmt(all_plan),
            "Факт, млн. руб.": _fmt(all_fact),
            "Отклонение, млн. руб.": _fmt(all_fact - all_plan),
            "_row_kind": "total",
        }
    )
    return pd.DataFrame(rows)


def overlay_turnover_monthly_on_budget_summary(
    summary: pd.DataFrame,
    *,
    period_col: str,
    project_name: str,
    period_start: Any | None = None,
    period_end: Any | None = None,
    reference_1c_dannye: Optional[pd.DataFrame] = None,
    project_norm_keys: set[str] | None = None,
    narrow_to_project_norm_key: str | None = None,
) -> tuple[pd.DataFrame, bool]:
    """
    Подмешивает в сводку месяцы из merged turnover (demo+1С) по той же логике, что матрица «План-факт».
    Не перезаписывает месяцы, где уже есть данные 1С/MSP (сумма > 500 тыс. руб.).
    """
    if summary is None or summary.empty or not str(project_name or "").strip():
        return summary, False
    prep = _bdds_turnover_g_for_project(
        project_name=project_name,
        period_start=period_start,
        period_end=period_end,
        reference_1c_dannye=reference_1c_dannye,
    )
    if prep is None:
        return summary, False
    g, months, _art, canon_proj = prep
    if not months:
        return summary, False

    from dashboards._renderers import (
        _project_filter_norm_key,
        _project_norm_key_matches_msp_keys,
    )
    from utils import format_period_ru

    keys = {k for k in (project_norm_keys or set()) if k}
    nt = (narrow_to_project_norm_key or "").strip()
    if nt:
        keys.add(nt)
    syn_pk = _project_filter_norm_key(canon_proj)

    out = summary.copy()
    if "period_original" not in out.columns and period_col in out.columns:
        out["period_original"] = out[period_col]

    def _to_month_period(x):
        if isinstance(x, pd.Period):
            return x.asfreq("M") if x.freq != "M" else x
        if pd.isna(x):
            return pd.NaT
        try:
            return pd.Period(str(x), freq="M")
        except Exception:
            pass
        try:
            ts = pd.Timestamp(x)
            if pd.notna(ts):
                return ts.to_period("M")
        except Exception:
            pass
        return pd.NaT

    merged_any = False
    extra_rows: list[dict] = []
    for m in months:
        chunk_m = g[g["_m"] == m]
        syn_plan = float(chunk_m["_plan"].sum())
        syn_fact = float(chunk_m["_fact"].sum())
        if syn_plan + syn_fact <= 50_000.0:
            continue

        if "project name" in out.columns:
            row_mask = out["project name"].map(_project_filter_norm_key).map(
                lambda rk: _project_norm_key_matches_msp_keys(rk, {syn_pk})
            )
        else:
            row_mask = pd.Series(False, index=out.index)

        per_vals = out["period_original"].map(_to_month_period)
        hit = row_mask & (per_vals == m)
        if bool(hit.any()):
            existing_pl = float(out.loc[hit, "budget plan"].fillna(0.0).sum())
            existing_fc = float(out.loc[hit, "budget fact"].fillna(0.0).sum())
            if existing_pl + existing_fc > 500_000.0:
                continue
            out.loc[hit, "budget plan"] = syn_plan
            out.loc[hit, "budget fact"] = syn_fact
            if "reserve budget" in out.columns:
                out.loc[hit, "reserve budget"] = syn_fact - syn_plan
            merged_any = True
        else:
            if keys and not _project_norm_key_matches_msp_keys(syn_pk, keys):
                continue
            _proj_nm = canon_proj
            if "project name" in out.columns:
                for nm in out["project name"].dropna().unique():
                    if _project_norm_key_matches_msp_keys(_project_filter_norm_key(nm), {syn_pk}):
                        _proj_nm = str(nm)
                        break
            extra_rows.append(
                {
                    "project name": _proj_nm,
                    period_col: format_period_ru(m),
                    "period_original": m,
                    "budget plan": syn_plan,
                    "budget fact": syn_fact,
                    "reserve budget": syn_fact - syn_plan,
                }
            )
            merged_any = True

    if extra_rows:
        out = pd.concat([out, pd.DataFrame(extra_rows)], ignore_index=True)

    if not merged_any:
        return summary, False

    canon = None
    if nt and "project name" in out.columns:
        for nm in out["project name"].dropna().unique():
            if _project_norm_key_matches_msp_keys(_project_filter_norm_key(nm), {nt}):
                canon = str(nm)
                break
    out = merge_budget_summary_by_norm_project_month(
        out,
        period_col=period_col,
        canonical_project_name=canon,
    )
    return out, True


def overlay_demo_turnover_on_budget_summary(
    summary: pd.DataFrame,
    *,
    period_col: str,
    period_start: Any | None = None,
    period_end: Any | None = None,
    project_norm_keys: set[str] | None = None,
    narrow_to_project_norm_key: str | None = None,
    max_year: int = 2024,
) -> tuple[pd.DataFrame, bool]:
    """
    Добавляет в сводку месяцы из demo budget (sample_budget_data), где ещё нет данных 1С/MSP.
    План для fact-only месяцев оценивается по коэффициенту из строк 1С (без demo bulk).
    По умолчанию подмешиваются только месяцы до ``max_year`` включительно (MSP/demo 2024),
    чтобы не раздувать итоги demo-оборотами 2025+.
    """
    if summary is None or summary.empty:
        return summary, False
    demo = _load_demo_budget_turnover_df()
    if demo is None or demo.empty:
        return summary, False
    syn = try_synthetic_budget_from_1c_dannye(reference_1c_dannye=demo)
    if syn is None or syn.empty:
        return summary, False
    syn = _filter_1c_budget_syn(
        syn,
        project_norm_keys=project_norm_keys,
        narrow_to_project_norm_key=narrow_to_project_norm_key,
        period_start=period_start,
        period_end=period_end,
    )
    if syn is None or syn.empty:
        return summary, False

    from dashboards._renderers import (
        _project_filter_norm_key,
        _project_norm_key_matches_msp_keys,
    )
    from utils import format_period_ru

    out = summary.copy()
    if "period_original" not in out.columns and period_col in out.columns:
        out["period_original"] = out[period_col]

    _pl_sm = pd.to_numeric(out.get("budget plan", 0), errors="coerce").fillna(0.0)
    _fc_sm = pd.to_numeric(out.get("budget fact", 0), errors="coerce").fillna(0.0)
    _sel_sm = (_pl_sm > 0) & (_fc_sm > 0) & (_pl_sm < 5e8) & (_fc_sm < 5e8)
    _plan_fact_ratio: float | None = None
    if bool(_sel_sm.any()):
        _sp = float(_pl_sm.loc[_sel_sm].sum())
        _sf = float(_fc_sm.loc[_sel_sm].sum())
        if _sf > 0:
            _plan_fact_ratio = _sp / _sf

    keys = {k for k in (project_norm_keys or set()) if k}
    nt = (narrow_to_project_norm_key or "").strip()
    if nt:
        keys.add(nt)

    merged_any = False
    extra_rows: list[dict] = []
    for _, sr in syn.iterrows():
        syn_pk = _project_filter_norm_key(sr.get("project name"))
        if keys and not _project_norm_key_matches_msp_keys(syn_pk, keys):
            continue
        syn_month = sr.get("plan_month")
        if pd.isna(syn_month):
            continue
        try:
            syn_month = (
                pd.Period(syn_month, freq="M")
                if not isinstance(syn_month, pd.Period)
                else syn_month
            )
        except Exception:
            continue
        try:
            syn_year = int(syn_month.year)
        except Exception:
            syn_year = 0
        if max_year is not None and syn_year > int(max_year):
            continue
        syn_plan = float(pd.to_numeric(sr.get("budget plan"), errors="coerce") or 0.0)
        syn_fact = float(pd.to_numeric(sr.get("budget fact"), errors="coerce") or 0.0)
        if syn_plan > 500_000_000.0 and syn_fact < syn_plan * 0.05:
            syn_plan = 0.0
        if int(syn_year) >= 2025 and max(syn_plan, syn_fact) > 100_000_000.0:
            continue
        if syn_plan <= 0.0 and syn_fact > 0.0 and _plan_fact_ratio is not None:
            syn_plan = syn_fact * float(_plan_fact_ratio)
        if syn_plan + syn_fact <= 0.0:
            continue

        if "project name" in out.columns:
            row_mask = out["project name"].map(_project_filter_norm_key).map(
                lambda rk: _project_norm_key_matches_msp_keys(rk, {syn_pk})
            )
        else:
            row_mask = pd.Series(False, index=out.index)

        def _to_month_period(x):
            if isinstance(x, pd.Period):
                return x.asfreq("M") if x.freq != "M" else x
            if pd.isna(x):
                return pd.NaT
            try:
                return pd.Period(str(x), freq="M")
            except Exception:
                pass
            try:
                ts = pd.Timestamp(x)
                if pd.notna(ts):
                    return ts.to_period("M")
            except Exception:
                pass
            return pd.NaT

        per_vals = out["period_original"].map(_to_month_period)
        hit = row_mask & (per_vals == syn_month)
        if bool(hit.any()):
            existing_pl = float(out.loc[hit, "budget plan"].fillna(0.0).sum())
            existing_fc = float(out.loc[hit, "budget fact"].fillna(0.0).sum())
            if existing_pl + existing_fc > 500_000.0:
                continue
            out.loc[hit, "budget plan"] = syn_plan
            out.loc[hit, "budget fact"] = syn_fact
            if "reserve budget" in out.columns:
                out.loc[hit, "reserve budget"] = syn_fact - syn_plan
            merged_any = True
        else:
            _proj_nm = str(sr.get("project name") or "")
            if "project name" in out.columns:
                for nm in out["project name"].dropna().unique():
                    if _project_norm_key_matches_msp_keys(
                        _project_filter_norm_key(nm), {syn_pk}
                    ):
                        _proj_nm = str(nm)
                        break
            extra_rows.append(
                {
                    "project name": _proj_nm,
                    period_col: format_period_ru(syn_month),
                    "period_original": syn_month,
                    "budget plan": syn_plan,
                    "budget fact": syn_fact,
                    "reserve budget": syn_fact - syn_plan,
                }
            )
            merged_any = True

    if extra_rows:
        out = pd.concat([out, pd.DataFrame(extra_rows)], ignore_index=True)

    if not merged_any:
        return summary, False

    canon = None
    if nt and "project name" in out.columns:
        for nm in out["project name"].dropna().unique():
            if _project_norm_key_matches_msp_keys(_project_filter_norm_key(nm), {nt}):
                canon = str(nm)
                break
    out = merge_budget_summary_by_norm_project_month(
        out,
        period_col=period_col,
        canonical_project_name=canon,
    )
    return out, True


def overlay_1c_on_budget_summary(
    summary: pd.DataFrame,
    *,
    period_col: str,
    period_start: Any | None = None,
    period_end: Any | None = None,
    project_norm_keys: set[str] | None = None,
    narrow_to_project_norm_key: str | None = None,
    reference_1c_dannye: Optional[pd.DataFrame] = None,
) -> tuple[pd.DataFrame, bool]:
    """
    Подмешивает помесячные план/факт из 1С в сводку MSP (по project + month).
    MSP остаётся основой по срокам; 1С уточняет месяцы, где есть обороты.
    """
    if summary is None or summary.empty:
        return summary, False
    ref = resolve_reference_1c_dannye(reference_1c_dannye)
    syn = try_synthetic_budget_from_1c_dannye(reference_1c_dannye=ref)
    if syn is None or syn.empty:
        return summary, False
    # Сначала только календарь; проект — в цикле (иначе двойной фильтр может обнулить syn).
    syn = _filter_1c_budget_syn(
        syn,
        project_norm_keys=None,
        narrow_to_project_norm_key=None,
        period_start=period_start,
        period_end=period_end,
    )
    if syn is None or syn.empty:
        return summary, False

    from dashboards._renderers import (
        _project_filter_norm_key,
        _project_norm_key_matches_msp_keys,
    )

    keys = {k for k in (project_norm_keys or set()) if k}
    nt = (narrow_to_project_norm_key or "").strip()
    if nt:
        keys.add(nt)

    out = summary.copy()
    if "project name" in out.columns:
        summary_keys = {
            _project_filter_norm_key(x) for x in out["project name"].dropna().unique()
        }
        summary_keys.discard("")
        if summary_keys:
            keys = keys | summary_keys if keys else summary_keys
    if "period_original" not in out.columns and period_col in out.columns:
        out["period_original"] = out[period_col]

    def _canonical_name_for_syn_pk(syn_pk: str, fallback: str = "") -> str:
        if not syn_pk or "project name" not in out.columns:
            return fallback
        _mask = out["project name"].map(_project_filter_norm_key).map(
            lambda rk: _project_norm_key_matches_msp_keys(rk, {syn_pk})
        )
        if bool(_mask.any()):
            return str(out.loc[_mask, "project name"].iloc[0])
        nt = (narrow_to_project_norm_key or "").strip()
        if nt and _project_norm_key_matches_msp_keys(syn_pk, {nt}):
            for nm in out["project name"].dropna().unique():
                if _project_norm_key_matches_msp_keys(_project_filter_norm_key(nm), {nt}):
                    return str(nm)
        return fallback

    extra_rows: list[dict] = []
    merged_any = False
    for _, sr in syn.iterrows():
        syn_pk = _project_filter_norm_key(sr.get("project name"))
        if keys and not _project_norm_key_matches_msp_keys(syn_pk, keys):
            continue
        syn_month = sr.get("plan_month")
        if pd.isna(syn_month):
            continue
        try:
            syn_month = pd.Period(syn_month, freq="M") if not isinstance(syn_month, pd.Period) else syn_month
        except Exception:
            continue
        syn_plan = float(pd.to_numeric(sr.get("budget plan"), errors="coerce") or 0.0)
        syn_fact = float(pd.to_numeric(sr.get("budget fact"), errors="coerce") or 0.0)
        if "project name" in out.columns:
            row_mask = out["project name"].map(_project_filter_norm_key).map(
                lambda rk: _project_norm_key_matches_msp_keys(rk, {syn_pk})
            )
        else:
            row_mask = pd.Series(True, index=out.index)
        def _to_month_period(x):
            if isinstance(x, pd.Period):
                return x.asfreq("M") if x.freq != "M" else x
            if pd.isna(x):
                return pd.NaT
            try:
                return pd.Period(str(x), freq="M")
            except Exception:
                pass
            try:
                ts = pd.Timestamp(x)
                if pd.notna(ts):
                    return ts.to_period("M")
            except Exception:
                pass
            return pd.NaT

        per_vals = out["period_original"].map(_to_month_period)
        hit = row_mask & (per_vals == syn_month)
        if bool(hit.any()):
            out.loc[hit, "budget plan"] = syn_plan
            out.loc[hit, "budget fact"] = syn_fact
            if "reserve budget" in out.columns:
                out.loc[hit, "reserve budget"] = syn_fact - syn_plan
            merged_any = True
        else:
            from utils import format_period_ru

            _proj_nm = _canonical_name_for_syn_pk(syn_pk, str(sr.get("project name") or ""))
            extra_rows.append(
                {
                    "project name": _proj_nm,
                    period_col: format_period_ru(syn_month),
                    "period_original": syn_month,
                    "budget plan": syn_plan,
                    "budget fact": syn_fact,
                    "reserve budget": syn_fact - syn_plan,
                }
            )
            merged_any = True
    if extra_rows:
        out = pd.concat([out, pd.DataFrame(extra_rows)], ignore_index=True)
    if not merged_any:
        return summary, False
    canon = None
    nt = (narrow_to_project_norm_key or "").strip()
    if nt and "project name" in out.columns:
        for nm in out["project name"].dropna().unique():
            if _project_norm_key_matches_msp_keys(_project_filter_norm_key(nm), {nt}):
                canon = str(nm)
                break
    out = merge_budget_summary_by_norm_project_month(
        out,
        period_col=period_col,
        canonical_project_name=canon,
    )
    out = zero_budget_plan_for_projects_without_1c_plan(
        out,
        reference_1c_dannye=ref,
    )
    return out, True


def ensure_bdr_frame_with_fallback(
    df: pd.DataFrame,
    *,
    restrict_projects_from_df: bool = True,
) -> tuple[pd.DataFrame, bool]:
    """
    Для БДР: если в входном MSP-фрейме нет столбцов доходов/расходов с данными —
    собирает доходы, расходы и сальдо из `*_dannye.json` через `reference_1c_dannye`.

    Не подмешивает логику БДДС (budget plan/fact).
    """
    work = df.copy()

    def _has_bdr_amounts(frame: pd.DataFrame) -> bool:
        for a, b in (
            ("bdr_plan_expense", "bdr_fact_expense"),
            ("bdr_income", "bdr_expense"),
            ("доходы", "расходы"),
            ("доход", "расход"),
            ("income", "expense"),
        ):
            if a in frame.columns and b in frame.columns:
                x = pd.to_numeric(frame[a], errors="coerce").fillna(0.0)
                y = pd.to_numeric(frame[b], errors="coerce").fillna(0.0)
                if float(x.abs().sum() + y.abs().sum()) > 0.0:
                    return True
        return False

    if _has_bdr_amounts(work):
        return work, False

    syn = try_synthetic_bdr_from_1c_dannye()
    if syn is None or syn.empty:
        return work, False

    syn_use = syn
    if restrict_projects_from_df and "project name" in work.columns:
        nz = work["project name"].dropna()
        if not nz.empty:
            from dashboards._renderers import (
                _project_filter_norm_key,
                _project_norm_key_matches_msp_keys,
            )

            keys = {_project_filter_norm_key(x) for x in nz.unique()}
            keys.discard("")
            if keys:
                _rk = syn["project name"].map(_project_filter_norm_key)
                syn_f = syn[
                    _rk.map(lambda rk: _project_norm_key_matches_msp_keys(rk, keys))
                ].copy()
                if not syn_f.empty:
                    syn_use = syn_f
                # Иначе имена проектов в 1С не сопоставились с MSP — показываем всю синтетику 1С.

    if syn_use.empty:
        return work, False

    syn_use.attrs.update(dict(getattr(syn, "attrs", {}) or {}))
    syn_use.attrs.setdefault("data_source_1c_synthetic_bdr", True)
    return syn_use, True
