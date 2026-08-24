"""Отклонение от базового плана — паритет с [main] dashboard_plan_fact_dates, данные из web_data.db."""
from __future__ import annotations

import math
import re
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from app.config import DATA_MODE, WEB_DB_PATH
from app.services.core_bridge import import_dashboard_module, load_msp_frame, prepare_web_db
from app.services.db_ingest import db_status
from app.services.project_scope import applied_project_label, resolve_selected_projects
from app.services.report_cache import cache_get, cache_set

CHART_CAP = 400
_BLANK = frozenset({"", "nan", "none", "null", "<na>", "-", "—", "нд", "nd", "nat"})
_GENERIC_BLOCK = re.compile(r"(?i)^блок\s*\d+$")
_ZOS_WORD_RE = re.compile(
    r"(?<![а-яёa-z0-9])зос(?![а-яёa-z0-9])",
    flags=re.IGNORECASE,
)
_COVENANT_TOKENS = (
    "ковенант",
    "ковенанты",
    "ковен",
    "финковенант",
    "covenant",
    "covenants",
    "coven",
)
REASON_BUCKET_ORDER: tuple[str, ...] = (
    "Изменение объемов",
    "Изменение расценки",
    "Не передан фронт работ",
    "Нет оплаты Подрядчику",
    "Переделка за предыдущим подрядчиком",
    "Увеличение сроков по вине подрядчика",
    "Расторжение Договора",
    "Превышение срока по договору",
    "Корректировка РД",
    "Длительное согласование договора",
    "Прочее",
)


def _normalize(value: Any) -> str:
    text = str(value or "").casefold().replace("_", " ")
    return re.sub(r"\s+", " ", text).strip()


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.casefold() in _BLANK:
        return ""
    return re.sub(r"\s+", " ", text)


def _cmp_key(value: Any) -> str:
    return _normalize(value)


def _unique_ci_labels(values: list[str]) -> list[str]:
    """Уникальные подписи без учёта регистра (КОВЕНАНТЫ / Ковенанты → одна)."""
    best: dict[str, str] = {}
    freq: dict[str, dict[str, int]] = {}
    for raw in values:
        v = _clean(raw)
        if not v:
            continue
        k = v.casefold()
        bucket = freq.setdefault(k, {})
        bucket[v] = bucket.get(v, 0) + 1
    for k, bucket in freq.items():
        def _rank(s: str) -> tuple[int, int, str]:
            # чаще → с строчными (не ALL CAPS) → стабильный tie-break
            has_lower = 1 if any(ch.islower() for ch in s) else 0
            return (bucket[s], has_lower, s)

        best[k] = max(bucket.keys(), key=_rank)
    return sorted(best.values(), key=str.casefold)


def _pick_label(requested: str | None, available: list[str], *, default: str = "Все") -> str:
    if not requested or requested == default:
        return default
    if requested in available:
        return requested
    key = _cmp_key(requested)
    for opt in available:
        if opt != default and _cmp_key(opt) == key:
            return opt
    return default


def _col(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    cols = {_normalize(c): str(c) for c in frame.columns}
    for name in candidates:
        hit = cols.get(_normalize(name))
        if hit:
            return hit
    return None


def _is_blank(value: Any) -> bool:
    return not _clean(value)


def _is_generic_block(value: Any) -> bool:
    text = _clean(value)
    return (not text) or bool(_GENERIC_BLOCK.match(text))


def _is_covenant_text(value: Any) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    t = str(value).lower()
    return any(tok in t for tok in _COVENANT_TOKENS)


def _fmt_date(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.strftime("%d.%m.%Y")


def _fmt_dev_days(days: Any) -> str | None:
    if days is None or (isinstance(days, float) and pd.isna(days)):
        return None
    try:
        n = int(round(float(days)))
    except (TypeError, ValueError):
        return None
    if n > 0:
        return f"+{n}"
    return str(n)


def _fmt_int_days(days: Any) -> str | None:
    if days is None or (isinstance(days, float) and pd.isna(days)):
        return None
    try:
        return str(int(round(float(days))))
    except (TypeError, ValueError):
        return None


def _fmt_task_id(raw: Any) -> str:
    """MSP unique id → целое без «.0» (570, не 570.0)."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return ""
    text = str(raw).strip()
    if not text or text.casefold() in _BLANK:
        return ""
    try:
        return str(int(float(text.replace(",", "."))))
    except (TypeError, ValueError):
        return text


def _reason_bucket(raw: Any) -> str:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return "Прочее"
    s = str(raw).strip().lower()
    if not s:
        return "Прочее"
    if "измен" in s and "объем" in s:
        return "Изменение объемов"
    if "измен" in s and ("расцен" in s or "стоим" in s or "цен" in s):
        return "Изменение расценки"
    if "не передан фронт" in s or ("фронт" in s and "не передан" in s):
        return "Не передан фронт работ"
    if "нет оплат" in s or ("оплат" in s and "подрядчик" in s):
        return "Нет оплаты Подрядчику"
    if "переделк" in s:
        return "Переделка за предыдущим подрядчиком"
    if "увеличение срок" in s and "подрядчик" in s:
        return "Увеличение сроков по вине подрядчика"
    if "расторжен" in s and "договор" in s:
        return "Расторжение Договора"
    if "превышение" in s and ("договор" in s or "срок" in s):
        return "Превышение срока по договору"
    if "корректиров" in s and "рд" in s:
        return "Корректировка РД"
    if "согласован" in s and "договор" in s:
        return "Длительное согласование договора"
    return "Прочее"


def _resolve_reason_col(frame: pd.DataFrame) -> str | None:
    hit = _col(
        frame,
        [
            "reason of deviation",
            "reason_of_deviation",
            "Причины отклонений",
            "Причина отклонения",
        ],
    )
    if hit:
        return hit
    for col in frame.columns:
        s = _normalize(col)
        if "причин" in s and "отклон" in s:
            return str(col)
        if "reason" in s and "deviat" in s and "day" not in s:
            return str(col)
    return None


def _resolve_notes_col(frame: pd.DataFrame) -> str | None:
    return _col(
        frame,
        ["notes", "note", "Заметки", "заметки", "remarks", "комментарий", "Комментарии"],
    )


def _task_id_col(frame: pd.DataFrame) -> str | None:
    return _col(
        frame,
        [
            "unique id",
            "unique_id",
            "task id seq",
            "task id",
            "ид",
            "id",
            "уникальный идентификатор",
            "external task id",
        ],
    )


def _block_values(frame: pd.DataFrame, block_col: str | None) -> list[str]:
    if not block_col or block_col not in frame.columns:
        return []
    vals = [
        _clean(v)
        for v in frame[block_col].dropna().astype(str).tolist()
        if not _is_generic_block(v)
    ]
    return _unique_ci_labels(vals)


def _building_values(frame: pd.DataFrame, level_col: str | None, task_col: str | None) -> list[str]:
    if frame is None or frame.empty or not level_col or not task_col:
        return []
    if level_col not in frame.columns or task_col not in frame.columns:
        return []
    ln = pd.to_numeric(frame[level_col], errors="coerce")
    names = [_clean(x) for x in frame.loc[ln == 3.0, task_col].dropna().astype(str).tolist()]
    return _unique_ci_labels(names)


def _apply_building_slice(
    frame: pd.DataFrame,
    *,
    building: str,
    level_col: str,
    task_col: str,
) -> pd.DataFrame:
    if building == "Все" or frame.empty:
        return frame
    ln = pd.to_numeric(frame[level_col], errors="coerce")
    names = frame[task_col].astype(str).map(_clean)
    keys = names.map(_cmp_key)
    sel = _cmp_key(building)
    mask = (ln == 3.0) & (keys == sel)
    if not bool(mask.any()):
        return frame.iloc[0:0].copy()
    positions = list(range(len(frame)))
    idx_pos = frame.index.get_indexer(frame.index[mask])
    start = int(min(idx_pos))
    end = len(frame)
    for pos in positions[start + 1 :]:
        lv = ln.iloc[pos]
        if pd.notna(lv) and int(lv) <= 3:
            end = pos
            break
    return frame.iloc[start:end].copy()


def _is_zos_task(name: object) -> bool:
    text = str(name or "").strip()
    if not text or text.lower() in ("nan", "none", "<na>"):
        return False
    lower = text.casefold()
    if "заключение о соответствии" in lower:
        return True
    return bool(_ZOS_WORD_RE.search(text))


def _zos_rank(name: object) -> int:
    if not _is_zos_task(name):
        return 99
    lower = str(name or "").casefold().strip()
    if lower == "зос" or lower.startswith("зос"):
        return 0
    if "заключение о соответствии" in lower:
        return 1
    if "до зос" in lower:
        return 8
    return 2


DEFAULT_METRIC_TASK = "ЗОС"


def resolve_metric_task() -> str:
    """Задача для KPI из админки (`baseline_plan_task_for_metrics`), по умолчанию ЗОС."""
    try:
        from app.services.users_bridge import import_settings_module

        value = import_settings_module().get_setting("baseline_plan_task_for_metrics")
    except Exception:  # noqa: BLE001
        return DEFAULT_METRIC_TASK
    return (value or "").strip() or DEFAULT_METRIC_TASK


def _pick_metric_row(
    frame: pd.DataFrame, task_col: str, metric_task: str
) -> pd.Series | None:
    if frame is None or frame.empty or task_col not in frame.columns:
        return None
    names = frame[task_col].astype(str).str.strip()
    task = (metric_task or "").strip()

    if task:
        exact = frame.loc[names.str.casefold() == task.casefold()]
        if not exact.empty:
            return exact.iloc[0]
        if not _is_zos_task(task):
            # Настроена своя задача: ищем по вхождению, но на ЗОС не откатываемся —
            # иначе плитки молча покажут KPI совсем другой задачи.
            try:
                rx = re.compile(re.escape(task), flags=re.IGNORECASE)
            except re.error:
                return None
            cand = frame.loc[names.map(lambda x: bool(rx.search(str(x))))]
            return cand.iloc[0] if not cand.empty else None

    zos = frame.loc[names.map(_is_zos_task)].copy()
    if zos.empty:
        return None
    zos["_rank"] = zos[task_col].map(_zos_rank)
    return zos.sort_values("_rank", ascending=True).iloc[0]


def _outline_levels(series: pd.Series) -> pd.Series:
    num = pd.to_numeric(series, errors="coerce")
    mask_na = num.isna()
    if not bool(mask_na.any()):
        return num
    ext = series[mask_na].astype(str).str.strip().str.extract(r"(-?\d+)", expand=False)
    out = num.copy()
    out.loc[mask_na] = pd.to_numeric(ext, errors="coerce").values
    return out


def _immediate_parent_names(frame: pd.DataFrame, level_col: str, name_col: str) -> pd.Series:
    lv = _outline_levels(frame[level_col])
    nm = frame[name_col].map(lambda x: "" if pd.isna(x) else str(x))
    stack: list[tuple[float, str]] = []
    out: list[str] = []
    for i in range(len(frame)):
        raw_l = lv.iloc[i]
        n = nm.iloc[i] or ""
        if pd.isna(raw_l):
            out.append("")
            continue
        level = float(raw_l)
        while stack and stack[-1][0] >= level:
            stack.pop()
        out.append(stack[-1][1] if stack else "")
        stack.append((level, n))
    return pd.Series(out, index=frame.index)


def _enrich_ancestor_keys(frame: pd.DataFrame, level_col: str | None, task_col: str) -> pd.DataFrame:
    work = frame.copy()
    if "_dt_lvl2_key" in work.columns and "_dt_lvl3_key" in work.columns:
        return work
    work["_dt_lvl2_key"] = ""
    work["_dt_lvl3_key"] = ""
    if not level_col or level_col not in work.columns or task_col not in work.columns:
        return work
    lv = _outline_levels(work[level_col])
    names = work[task_col].map(_clean)
    stack: list[tuple[float, str]] = []
    l2_keys: list[str] = []
    l3_keys: list[str] = []
    for i in range(len(work)):
        raw_l = lv.iloc[i]
        name = names.iloc[i]
        if pd.isna(raw_l):
            l2_keys.append(stack[-1][1] if stack else "")
            l3 = next((n for l, n in reversed(stack) if l == 3.0), "")
            l3_keys.append(l3)
            continue
        level = float(raw_l)
        while stack and stack[-1][0] >= level:
            stack.pop()
        l2 = next((n for l, n in reversed(stack) if l == 2.0), "")
        l3 = next((n for l, n in reversed(stack) if l == 3.0), "")
        if level == 2.0:
            l2 = name
        if level == 3.0:
            l3 = name
        l2_keys.append(l2)
        l3_keys.append(l3)
        stack.append((level, name))
    work["_dt_lvl2_key"] = l2_keys
    work["_dt_lvl3_key"] = l3_keys
    return work


def _cipher_filled_mask(frame: pd.DataFrame) -> pd.Series:
    cipher_col = _col(
        frame,
        [
            "abbreviation",
            "Шифр_ПД_и_РД",
            "Шифр ПД и РД",
            "шифр пд и рд",
            "Шифр ПД РД",
            "Шифр ПД/РД",
            "ШифрПДРД",
            "Cipher PD RD",
            "Шифр",
            "Cipher",
        ],
    )
    if not cipher_col or cipher_col not in frame.columns:
        return pd.Series(False, index=frame.index)
    cs = frame[cipher_col].astype(str).str.strip()
    return cs.ne("") & ~cs.str.casefold().isin(_BLANK)


def _parent_is_rd_stage(parent_name: str) -> bool:
    s = str(parent_name or "").casefold().replace("ё", "е")
    if "рабоч" not in s or "документ" not in s:
        return False
    if "корректиров" in s:
        return False
    if "проектная документация" in s and "рабоч" not in s:
        return False
    return True


def _build_rd_deadline_chart_df(scope_df: pd.DataFrame) -> pd.DataFrame:
    """Как main `_plan_fact_build_rd_deadline_chart_df`: max дат по разделам РД ур.5+шифр."""
    cols = ["task name", "project name", "plan end", "base end", "plan_end_diff", "_rd_parent"]
    if scope_df is None or getattr(scope_df, "empty", True):
        return pd.DataFrame(columns=cols)
    work = scope_df.copy()
    try:
        from utils import ensure_date_columns, ensure_msp_hierarchy_columns  # type: ignore

        ensure_msp_hierarchy_columns(work)
        ensure_date_columns(work)
    except Exception:  # noqa: BLE001
        pass
    if "plan end" not in work.columns or "base end" not in work.columns:
        return pd.DataFrame(columns=cols)
    if "task name" not in work.columns:
        return pd.DataFrame(columns=cols)

    hier_col = "level structure" if "level structure" in work.columns else None
    level_col = "level" if "level" in work.columns else hier_col
    stack_col = hier_col or level_col
    if not stack_col or stack_col not in work.columns:
        return pd.DataFrame(columns=cols)

    lv = pd.to_numeric(work[level_col if level_col in work.columns else stack_col], errors="coerce")
    parents = _immediate_parent_names(work, stack_col, "task name")
    parent_rd = parents.map(_parent_is_rd_stage).fillna(False)
    cipher_ok = _cipher_filled_mask(work)
    mask = lv.eq(5) & cipher_ok.fillna(False) & parent_rd
    if not bool(mask.any()):
        return pd.DataFrame(columns=cols)

    sub = work.loc[mask].copy()
    sub["_rd_parent"] = parents.loc[mask].astype(str).str.strip()
    sub["plan end"] = pd.to_datetime(sub["plan end"], errors="coerce")
    sub["base end"] = pd.to_datetime(sub["base end"], errors="coerce")
    sub = sub[sub["plan end"].notna() | sub["base end"].notna()].copy()
    if sub.empty:
        return pd.DataFrame(columns=cols)
    if "project name" not in sub.columns:
        sub["project name"] = ""

    rows: list[dict[str, Any]] = []
    for (proj, parent), g in sub.groupby(["project name", "_rd_parent"], sort=False, dropna=False):
        pe_max = g["plan end"].max()
        be_max = g["base end"].max()
        if pd.isna(pe_max) and pd.isna(be_max):
            continue
        deadline = pd.concat([g["plan end"], g["base end"]], axis=1).max(axis=1, skipna=True)
        if deadline.notna().any():
            pick = g.loc[deadline.idxmax()]
            label = str(pick.get("task name") or "").strip()
        else:
            label = ""
        if not label:
            label = str(parent or "").strip() or "Рабочая документация"
        dev = np.nan
        if pd.notna(be_max) and pd.notna(pe_max):
            dev = (pd.Timestamp(be_max) - pd.Timestamp(pe_max)).total_seconds() / 86400.0
        rows.append(
            {
                "task name": label,
                "project name": str(proj).strip() if pd.notna(proj) else "",
                "plan end": pe_max,
                "base end": be_max,
                "plan_end_diff": dev,
                "_rd_parent": str(parent or "").strip(),
            }
        )
    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows)
    return out.sort_values("plan_end_diff", ascending=True, na_position="last").reset_index(drop=True)


def _maket_prepare(frame: pd.DataFrame) -> pd.DataFrame:
    """Как main `_deviations_maket_prepare_df`: ур.5, причина, base−plan < 0."""
    if frame is None or getattr(frame, "empty", True):
        return pd.DataFrame()
    work = frame.copy()
    reason_col = _resolve_reason_col(work)
    if reason_col and reason_col != "reason of deviation":
        work = work.rename(columns={reason_col: "reason of deviation"})
    lvl_col = "level" if "level" in work.columns else _col(
        work, ["level", "outline level", "Уровень", "уровень структуры", "level structure"]
    )
    task_col = "task name" if "task name" in work.columns else _col(work, ["task name", "Название"])
    if task_col:
        work = _enrich_ancestor_keys(work, lvl_col, task_col)
    if "plan end" in work.columns:
        work["plan end"] = pd.to_datetime(work["plan end"], errors="coerce")
    if "base end" in work.columns:
        work["base end"] = pd.to_datetime(work["base end"], errors="coerce")
    work["_end_diff"] = np.nan
    if "plan end" in work.columns and "base end" in work.columns:
        both = work["plan end"].notna() & work["base end"].notna()
        work.loc[both, "_end_diff"] = (
            work.loc[both, "base end"] - work.loc[both, "plan end"]
        ).dt.total_seconds() / 86400.0

    mask_r = pd.Series(True, index=work.index)
    if "reason of deviation" in work.columns:
        mask_r = (
            work["reason of deviation"].notna()
            & (work["reason of deviation"].astype(str).str.strip() != "")
            & ~work["reason of deviation"].astype(str).str.strip().str.casefold().isin(_BLANK)
        )

    mask_l = pd.Series(True, index=work.index)
    if "level" in work.columns and pd.to_numeric(work["level"], errors="coerce").notna().any():
        mask_l = pd.to_numeric(work["level"], errors="coerce") == 5
    elif lvl_col and lvl_col in work.columns:
        mask_l = pd.to_numeric(work[lvl_col], errors="coerce") == 5

    mask_neg = pd.Series(False, index=work.index)
    if "_end_diff" in work.columns:
        mask_neg = mask_neg | (work["_end_diff"].notna() & (work["_end_diff"] < 0))
    if "deviation in days" in work.columns:
        did = pd.to_numeric(work["deviation in days"], errors="coerce")
        mask_neg = mask_neg | (did.notna() & (did < 0))

    maket = work[mask_r & mask_l & mask_neg].copy()
    key_cols = [
        c
        for c in ["project name", "task name", "plan end", "base end", "reason of deviation"]
        if c in maket.columns
    ]
    if key_cols and not maket.empty:
        tmp = maket.copy()
        for c in key_cols:
            tmp[c] = tmp[c].astype(str).str.strip()
        maket = maket[~tmp.duplicated(subset=key_cols, keep="first")].copy()
    if not maket.empty:
        # как chart: наибольшее (самое отрицательное) отклонение сверху
        maket = maket.sort_values("_end_diff", ascending=True).reset_index(drop=True)
    return maket


def _coerce_pct(series: pd.Series) -> pd.Series:
    raw = series.astype(str).str.replace("%", "", regex=False).str.replace(",", ".", regex=False)
    num = pd.to_numeric(raw, errors="coerce")
    # доли 0..1 → проценты
    as_frac = num.notna() & (num > 0) & (num <= 1.0001)
    num = num.copy()
    num.loc[as_frac] = num.loc[as_frac] * 100.0
    return num


def _covenant_row_mask(frame: pd.DataFrame, notes_col: str | None) -> pd.Series:
    m = pd.Series(False, index=frame.index)
    cols = ["section", "block", "task name", "reason of deviation"]
    if notes_col:
        cols.append(notes_col)
    for col in cols:
        if col in frame.columns:
            m = m | frame[col].map(_is_covenant_text)
    return m


def _empty_payload(*, error: str | None = None) -> dict[str, Any]:
    return {
        "meta": {
            "rows": 0,
            "chart_rows": 0,
            "source": "web_data.db",
            "data_mode": DATA_MODE,
            "parity": "main_plan_fact_dates",
            "version_id": None,
            "rule": "Откл. = база − план; default: причины (ур.5)",
            "error": error,
            "mode": "reasons",
            "db": db_status(),
        },
        "filters": {
            "projects": ["Все"],
            "blocks": ["Все"],
            "buildings": ["Все"],
            "levels": [
                {"id": "4", "label": "Уровень 4 (укрупнённо)"},
                {"id": "5", "label": "Уровень 5 (детально)"},
            ],
            "reasons": ["Все"],
            "label_modes": [
                {"id": "name", "label": "По наименованию MSP"},
                {"id": "lot", "label": "По лоту"},
            ],
            "has_lot": False,
            "applied": {
                "project": "Все",
                "block": "Все",
                "building": "Все",
                "level": "4",
                "reason": "Все",
                "show_reasons": True,
                "hide_completed": False,
                "only_covenants": False,
                "only_neg_end": False,
                "show_dur": True,
                "label_mode": "name",
                "level_skipped": True,
            },
        },
        "kpis": {
            "metric_task": DEFAULT_METRIC_TASK,
            "max_abs_dev_days": 0,
            "plates": [],
        },
        "chart": {
            "range_start": None,
            "range_end": None,
            "rows": [],
            "capped": False,
            "kind": "rd_end_bars",
            "caption": "",
            "base_color": "#14b8a6",
            "plan_color": "#fb923c",
        },
        "covenant_table": {"columns": [], "rows": []},
        "columns": [],
        "rows": [],
    }


def build_baseline_deviation_payload(
    *,
    project: str | None = None,
    block: str | None = None,
    building: str | None = None,
    level: str | None = "4",
    reason: str | None = None,
    show_reasons: bool = True,
    hide_completed: bool = False,
    only_covenants: bool = False,
    only_neg_end: bool = False,
    show_dur: bool = True,
    label_mode: str | None = "name",
) -> dict[str, Any]:
    metric_task = resolve_metric_task()
    cache_key = (
        f"v9|p={project or 'Все'}|b={block or 'Все'}|bd={building or 'Все'}"
        f"|l={level or '4'}|r={reason or 'Все'}|sr={int(bool(show_reasons))}"
        f"|hc={int(bool(hide_completed))}|oc={int(bool(only_covenants))}"
        f"|on={int(bool(only_neg_end))}|sd={int(bool(show_dur))}"
        f"|lm={label_mode or 'name'}|mt={metric_task}"
        f"|db={WEB_DB_PATH}|mtime={db_status().get('mtime')}"
    )
    cached = cache_get("baseline-deviation", cache_key, max_age_sec=3600)
    if cached is not None:
        return cached

    if not WEB_DB_PATH.is_file():
        return _empty_payload(error="web_data.db нет — выполните POST /api/admin/ingest (или sync).")

    try:
        prepare_web_db()
        import web_schema  # type: ignore

        labels_mod = import_dashboard_module("project_labels")
        version_id = web_schema.get_active_version_id()
        if not version_id:
            return _empty_payload(error="Нет active version_id в web_data.db")

        work = load_msp_frame(int(version_id))
        if work is None or getattr(work, "empty", True):
            return _empty_payload(error="Нет MSP (file_type=project) в активной версии")

        work = work.copy()
        if "__source_file" in work.columns:
            src = work["__source_file"].astype(str).str.lower()
            is_msp = (
                src.str.startswith("msp_")
                | src.str.contains("/msp_", na=False)
                | src.str.contains(r"\\msp_", na=False, regex=True)
            )
            if bool(is_msp.any()):
                work = work.loc[is_msp].copy()

        proj_col = _col(work, ["project name", "Проект", "проект", "Project"])
        if proj_col:
            work = labels_mod.apply_unified_project_column(work, proj_col)
            if proj_col != "project name" and "project name" not in work.columns:
                work = work.rename(columns={proj_col: "project name"})
            elif proj_col != "project name" and "project name" in work.columns:
                work["project name"] = work[proj_col]

        block_col = _col(work, ["block", "БЛОК", "Блок", "Функциональный блок", "section"])
        level_col = _col(
            work,
            ["level", "outline level", "Уровень", "уровень структуры", "Исходный уровень"],
        )
        task_col = _col(work, ["task name", "Task Name", "Название", "Задача"]) or "task name"
        if task_col not in work.columns:
            work[task_col] = work.index.astype(str)
        if task_col != "task name":
            work["task name"] = work[task_col]
            task_col = "task name"

        notes_col = _resolve_notes_col(work)
        reason_col = _resolve_reason_col(work)
        if reason_col and reason_col != "reason of deviation":
            work = work.rename(columns={reason_col: "reason of deviation"})
            reason_col = "reason of deviation"
        lot_col = _col(work, ["lot", "ЛОТ", "Лот", "lot name"])
        pct_col = _col(
            work,
            [
                "pct complete",
                "percent complete",
                "% complete",
                "Процент выполнения",
                "Процент_завершения",
                "% выполнения",
            ],
        )
        id_col = _task_id_col(work)

        for col in ("plan start", "plan end", "base start", "base end"):
            if col in work.columns:
                work[col] = pd.to_datetime(work[col], errors="coerce")

        available_projects = ["Все"]
        if "project name" in work.columns:
            available_projects += labels_mod.project_labels_for_filter(work["project name"])
        selected_projects = resolve_selected_projects(project, available_projects)
        applied_project = applied_project_label(selected_projects)

        scoped = work
        if selected_projects and "project name" in scoped.columns:
            scoped = labels_mod.filter_dataframe_by_project_labels(
                scoped, selected_projects, col="project name"
            )

        available_blocks = ["Все"] + _block_values(scoped, block_col)
        applied_block = _pick_label(block, available_blocks)
        if applied_block != "Все" and block_col and block_col in scoped.columns:
            scoped = scoped[
                scoped[block_col].astype(str).map(_cmp_key) == _cmp_key(applied_block)
            ].copy()

        covenant_block = bool(
            only_covenants
            or (applied_block != "Все" and _is_covenant_text(applied_block))
        )
        after_block = scoped.copy()
        bld_source = work if (covenant_block and not selected_projects) else (
            work if (covenant_block and selected_projects) else after_block
        )
        if covenant_block and selected_projects and "project name" in work.columns:
            bld_source = labels_mod.filter_dataframe_by_project_labels(
                work, selected_projects, col="project name"
            )
        elif covenant_block and not selected_projects:
            bld_source = work

        available_buildings = ["Все"] + _building_values(bld_source, level_col, task_col)
        applied_building = _pick_label(building, available_buildings)
        if (
            applied_building != "Все"
            and level_col
            and task_col
            and level_col in bld_source.columns
            and task_col in bld_source.columns
        ):
            sliced = _apply_building_slice(
                bld_source,
                building=applied_building,
                level_col=level_col,
                task_col=task_col,
            )
            if covenant_block and applied_block != "Все" and block_col and block_col in sliced.columns:
                sliced = sliced[
                    sliced[block_col].astype(str).map(_cmp_key) == _cmp_key(applied_block)
                ].copy()
            scoped = sliced

        # KPI plates — срез до фильтра уровня (как main `_zos_source_df`)
        zos_scope = scoped.copy()
        scoped = _enrich_ancestor_keys(scoped, level_col, task_col)
        zos_scope = _enrich_ancestor_keys(zos_scope, level_col, task_col)

        applied_level = level if level in {"4", "5"} else "4"
        level_skipped = bool(show_reasons or covenant_block)
        if covenant_block:
            pass
        elif show_reasons:
            if "level" in scoped.columns and pd.to_numeric(scoped["level"], errors="coerce").notna().any():
                scoped = scoped[pd.to_numeric(scoped["level"], errors="coerce") == 5].copy()
            elif level_col and level_col in scoped.columns:
                scoped = scoped[pd.to_numeric(scoped[level_col], errors="coerce") == 5].copy()
        elif level_col and level_col in scoped.columns:
            target = 4 if applied_level == "4" else 5
            ln = pd.to_numeric(scoped[level_col], errors="coerce")
            scoped = scoped[ln == float(target)].copy()

        has_plan = (
            scoped["plan start"].notna() & scoped["plan end"].notna()
            if "plan start" in scoped.columns and "plan end" in scoped.columns
            else pd.Series(False, index=scoped.index)
        )
        has_base = (
            scoped["base start"].notna() & scoped["base end"].notna()
            if "base start" in scoped.columns and "base end" in scoped.columns
            else pd.Series(False, index=scoped.index)
        )
        scoped = scoped[has_plan | has_base].copy()

        scoped["plan_start_diff"] = np.nan
        scoped["plan_end_diff"] = np.nan
        if "plan start" in scoped.columns and "base start" in scoped.columns:
            both_s = scoped["plan start"].notna() & scoped["base start"].notna()
            scoped.loc[both_s, "plan_start_diff"] = (
                scoped.loc[both_s, "base start"] - scoped.loc[both_s, "plan start"]
            ).dt.total_seconds() / 86400.0
        if "plan end" in scoped.columns and "base end" in scoped.columns:
            both_e = scoped["plan end"].notna() & scoped["base end"].notna()
            scoped.loc[both_e, "plan_end_diff"] = (
                scoped.loc[both_e, "base end"] - scoped.loc[both_e, "plan end"]
            ).dt.total_seconds() / 86400.0

        if hide_completed and pct_col and pct_col in scoped.columns:
            pct = _coerce_pct(scoped[pct_col])
            scoped = scoped.loc[pct.isna() | (pct < 99.9995)].copy()

        reason_buckets: list[str] = []
        if (not only_covenants) and "reason of deviation" in work.columns:
            raw_reasons = work["reason of deviation"].dropna().astype(str).str.strip()
            raw_reasons = raw_reasons[raw_reasons.ne("") & ~raw_reasons.str.casefold().isin(_BLANK)]
            reason_buckets = sorted(
                {_reason_bucket(v) for v in raw_reasons.tolist() if _reason_bucket(v)},
                key=lambda x: (
                    REASON_BUCKET_ORDER.index(x) if x in REASON_BUCKET_ORDER else 99,
                    x.casefold(),
                ),
            )
        available_reasons = ["Все"] + reason_buckets
        applied_reason = reason if reason in available_reasons else "Все"
        if applied_reason != "Все" and "reason of deviation" in scoped.columns:
            buckets = scoped["reason of deviation"].map(_reason_bucket)
            scoped = scoped[buckets == applied_reason].copy()

        if only_covenants:
            scoped = scoped.loc[_covenant_row_mask(scoped, notes_col)].copy()

        applied_label = label_mode if label_mode in {"name", "lot"} else "name"
        if applied_label == "lot" and lot_col and lot_col in scoped.columns:
            lc = scoped[lot_col].astype(str).str.strip()
            scoped = scoped[
                scoped[lot_col].notna() & lc.ne("") & ~lc.str.casefold().isin(_BLANK)
            ].copy()

        # KPI plates
        plates: list[dict[str, Any]] = []
        max_abs_global = 0
        multi_project = len(selected_projects) != 1
        plate_projects: list[str]
        if multi_project and "project name" in zos_scope.columns:
            plate_projects = labels_mod.project_labels_for_filter(zos_scope["project name"])
        else:
            plate_projects = list(selected_projects)

        def _plate_for(scope: pd.DataFrame, pname: str | None) -> dict[str, Any]:
            nonlocal max_abs_global
            max_abs = 0
            if "plan_end_diff" in scope.columns or (
                "plan end" in scope.columns and "base end" in scope.columns
            ):
                pe = pd.to_datetime(scope.get("plan end"), errors="coerce")
                be = pd.to_datetime(scope.get("base end"), errors="coerce")
                both = pe.notna() & be.notna()
                if bool(both.any()):
                    diffs = ((be - pe).dt.total_seconds() / 86400.0).loc[both]
                    if not diffs.empty:
                        max_abs = int(round(float(diffs.abs().max())))
                        max_abs_global = max(max_abs_global, max_abs)
            zrow = _pick_metric_row(scope, task_col, metric_task)
            plan_end = _fmt_date(zrow.get("base end")) if zrow is not None else None
            fact_end = _fmt_date(zrow.get("plan end")) if zrow is not None else None
            dev_days = None
            if zrow is not None:
                pe = pd.to_datetime(zrow.get("plan end"), errors="coerce")
                be = pd.to_datetime(zrow.get("base end"), errors="coerce")
                if pd.notna(pe) and pd.notna(be):
                    dev_days = int(round(float((be - pe).total_seconds() / 86400.0)))
            return {
                "project": pname,
                "plan_end": plan_end,
                "fact_end": fact_end,
                "dev_days": dev_days,
                "dev": _fmt_int_days(dev_days),
                "max_abs_dev_days": max_abs,
                "task": _clean(zrow.get(task_col)) if zrow is not None else None,
            }

        if multi_project and plate_projects:
            for pn in plate_projects:
                sub = labels_mod.filter_dataframe_by_project_labels(
                    zos_scope, [pn], col="project name"
                ) if "project name" in zos_scope.columns else zos_scope
                plates.append(_plate_for(sub, pn))
        else:
            plates.append(
                _plate_for(
                    zos_scope,
                    selected_projects[0] if selected_projects else None,
                )
            )

        mode = "covenant" if covenant_block else ("reasons" if show_reasons else "dates")

        if show_reasons and not covenant_block:
            table_df = _maket_prepare(scoped)
        else:
            table_df = scoped.copy()
            if not covenant_block:
                table_df = table_df[
                    table_df["plan_end_diff"].notna() & (table_df["plan_end_diff"] < -1e-9)
                ].copy()

        # График: как main — РД-дедлайны из среза ДО фильтра уровня (zos_scope),
        # независимо от «Показать причины»; при ковенантах — точки начало/окончание.
        chart_kind = "rd_end_bars"
        chart_caption = (
            "Столбцы от начала шкалы до «Базового окончания» и «Окончания» "
            "по последнему сроку разделов РД (ур.5 с шифром под «Рабочая документация»); "
            "сверху — наибольшее отклонение."
        )
        if covenant_block:
            chart_df = scoped.copy()
            chart_kind = "covenant_points"
            chart_caption = (
                "Блок «Ковенанты»: начало и окончание — точками на шкале дат."
            )
            if only_neg_end:
                chart_df = chart_df[
                    chart_df["plan_end_diff"].notna() & (chart_df["plan_end_diff"] < -1e-9)
                ].copy()
        else:
            chart_df = _build_rd_deadline_chart_df(zos_scope)
            if chart_df.empty:
                chart_df = scoped.copy()
                chart_kind = "end_bars"
                chart_caption = (
                    "Столбцы от начала шкалы до «Базового окончания» и «Окончания»; "
                    "сверху — наибольшее отклонение."
                )
            if only_neg_end and "plan_end_diff" in chart_df.columns:
                chart_df = chart_df[
                    chart_df["plan_end_diff"].notna() & (chart_df["plan_end_diff"] < -1e-9)
                ].copy()

        chart_source = chart_df.copy()
        sort_by: list[str] = []
        ascending: list[bool] = []
        if multi_project and "project name" in chart_source.columns:
            chart_source = chart_source.copy()
            chart_source["_proj_sort"] = (
                chart_source["project name"].map(_clean).astype(str).str.casefold()
            )
            sort_by.append("_proj_sort")
            ascending.append(True)
        if "plan_end_diff" in chart_source.columns:
            sort_by.append("plan_end_diff")
            ascending.append(True)
        if sort_by:
            chart_source = chart_source.sort_values(
                sort_by, ascending=ascending, na_position="last"
            )
        chart_capped = len(chart_source) > CHART_CAP
        chart_source = chart_source.head(CHART_CAP)

        range_dates: list[date] = []
        chart_rows: list[dict[str, Any]] = []
        for _, row in chart_source.iterrows():
            task = _clean(row.get("task name") if "task name" in chart_source.columns else row.get(task_col))
            if (
                applied_label == "lot"
                and lot_col
                and lot_col in chart_source.columns
                and chart_kind != "rd_end_bars"
            ):
                lot_v = _clean(row.get(lot_col))
                if lot_v:
                    task = lot_v if lot_v.casefold().startswith("лот") else f"Лот {lot_v}"
            pname = (
                _clean(row.get("project name"))
                if "project name" in chart_source.columns
                else ""
            )
            if not multi_project:
                label = task
            else:
                label = f"{pname}: {task}" if pname else task
            bs = row.get("base start") if "base start" in chart_source.columns else None
            ps = row.get("plan start") if "plan start" in chart_source.columns else None
            be = row.get("base end")
            pe = row.get("plan end")
            bs_ts = pd.to_datetime(bs, errors="coerce")
            ps_ts = pd.to_datetime(ps, errors="coerce")
            be_ts = pd.to_datetime(be, errors="coerce")
            pe_ts = pd.to_datetime(pe, errors="coerce")
            bs_iso = bs_ts.date().isoformat() if pd.notna(bs_ts) else None
            ps_iso = ps_ts.date().isoformat() if pd.notna(ps_ts) else None
            be_iso = be_ts.date().isoformat() if pd.notna(be_ts) else None
            pe_iso = pe_ts.date().isoformat() if pd.notna(pe_ts) else None
            if covenant_block:
                if not any((bs_iso, ps_iso, be_iso, pe_iso)):
                    continue
            elif not be_iso and not pe_iso:
                continue
            for iso in (bs_iso, ps_iso, be_iso, pe_iso):
                if iso:
                    range_dates.append(date.fromisoformat(iso))
            end_diff = row.get("plan_end_diff")
            if end_diff is None or (isinstance(end_diff, float) and pd.isna(end_diff)):
                end_diff = row.get("_end_diff")
            try:
                end_diff_n = int(round(float(end_diff))) if pd.notna(end_diff) else None
            except (TypeError, ValueError):
                end_diff_n = None
            chart_rows.append(
                {
                    "project": pname or None,
                    "task": task,
                    "label": label,
                    "base_start": bs_iso,
                    "base_start_label": _fmt_date(bs_ts),
                    "plan_start": ps_iso,
                    "plan_start_label": _fmt_date(ps_ts),
                    "base_end": be_iso,
                    "base_end_label": _fmt_date(be_ts),
                    "plan_end": pe_iso,
                    "plan_end_label": _fmt_date(pe_ts),
                    "dev_end_days": end_diff_n,
                }
            )

        range_start = min(range_dates).isoformat() if range_dates else None
        range_end = max(range_dates).isoformat() if range_dates else None

        # Таблица «Ковенанты (таблица)» как main
        covenant_table: dict[str, Any] = {"columns": [], "rows": []}
        if covenant_block:
            cov_cols = (
                ["Проект", "Задача", "ID задачи", "Базовое окончание", "Окончание", "Отклонение окончания (дней)"]
                if multi_project
                else ["Задача", "ID задачи", "Базовое окончание", "Окончание", "Отклонение окончания (дней)"]
            )
            cov_rows: list[dict[str, Any]] = []
            cov_src = chart_df.copy()
            if "plan_end_diff" in cov_src.columns:
                cov_src = cov_src.sort_values(
                    "plan_end_diff", ascending=True, na_position="last"
                )
            for _, crow in cov_src.iterrows():
                be_ts = pd.to_datetime(crow.get("base end"), errors="coerce")
                pe_ts = pd.to_datetime(crow.get("plan end"), errors="coerce")
                if pd.isna(be_ts) and pd.isna(pe_ts):
                    continue
                tid = ""
                if id_col and id_col in cov_src.columns:
                    tid = _fmt_task_id(crow.get(id_col))
                ped = crow.get("plan_end_diff")
                try:
                    ped_n = int(round(float(ped))) if pd.notna(ped) else None
                except (TypeError, ValueError):
                    ped_n = None
                if ped_n is None and pd.notna(be_ts) and pd.notna(pe_ts):
                    ped_n = int(round((be_ts - pe_ts).total_seconds() / 86400.0))
                item: dict[str, Any] = {
                    "task": _clean(crow.get("task name") if "task name" in cov_src.columns else crow.get(task_col)),
                    "task_id": tid or None,
                    "base_end": _fmt_date(be_ts),
                    "plan_end": _fmt_date(pe_ts),
                    "dev_end_days": ped_n,
                    "dev_end": _fmt_int_days(ped_n),
                }
                if multi_project:
                    item["project"] = _clean(crow.get("project name")) if "project name" in cov_src.columns else ""
                cov_rows.append(item)
            covenant_table = {"columns": cov_cols, "rows": cov_rows}

        # Table rows
        rows_out: list[dict[str, Any]] = []
        columns: list[str]

        if show_reasons and not covenant_block:
            columns = [
                "ID задачи",
                "Проект",
                "Функциональный блок",
                "Название",
                "Строение",
                "Окончание",
                "Базовое окончание",
                "Отклонение",
                "Причина отклонения",
                "Заметки",
            ]
            for _, row in table_df.iterrows():
                tid = ""
                if id_col and id_col in table_df.columns:
                    tid = _fmt_task_id(row.get(id_col))
                fb = ""
                if block_col and block_col in table_df.columns:
                    fb = _clean(row.get(block_col))
                if not fb and "_dt_lvl2_key" in table_df.columns:
                    fb = _clean(row.get("_dt_lvl2_key"))
                bld = ""
                if "_dt_lvl3_key" in table_df.columns:
                    bld = _clean(row.get("_dt_lvl3_key"))
                if not bld:
                    bld_col = _col(table_df, ["building", "строение", "корпус", "объект"])
                    if bld_col:
                        bld = _clean(row.get(bld_col))
                end_diff = row.get("_end_diff")
                try:
                    end_diff_n = int(round(float(end_diff))) if pd.notna(end_diff) else None
                except (TypeError, ValueError):
                    end_diff_n = None
                rows_out.append(
                    {
                        "task_id": tid or None,
                        "project": _clean(row.get("project name")),
                        "block": fb or None,
                        "task": _clean(row.get(task_col)),
                        "building": bld or None,
                        "plan_end": _fmt_date(row.get("plan end")),
                        "base_end": _fmt_date(row.get("base end")),
                        "dev_end_days": end_diff_n,
                        "dev_end": _fmt_int_days(end_diff_n),
                        "reason": _clean(row.get("reason of deviation")),
                        "notes": _clean(row.get(notes_col)) if notes_col else None,
                        "base_start": None,
                        "plan_start": None,
                        "dev_start_days": None,
                        "dev_start": None,
                        "base_dur_days": None,
                        "plan_dur_days": None,
                        "dev_dur_days": None,
                        "dev_dur": None,
                        "level": 5,
                    }
                )
        else:
            columns = []
            if multi_project:
                columns.append("Проект")
            columns.extend(
                [
                    "Задача",
                    "ID задачи",
                    "Функц. блок",
                    "Строение",
                    "Базовое начало",
                    "Начало",
                    "Откл. начала",
                    "Базовое окончание",
                    "Окончание",
                    "Откл. окончания",
                    "Длительность",
                    "Баз. длит.",
                ]
            )
            if show_dur:
                columns.append("Откл. длит.")

            for _, row in table_df.iterrows():
                task = _clean(row.get(task_col))
                if applied_label == "lot" and lot_col and lot_col in table_df.columns:
                    lot_v = _clean(row.get(lot_col))
                    if lot_v:
                        task = lot_v if lot_v.casefold().startswith("лот") else f"Лот {lot_v}"
                tid = ""
                if id_col and id_col in table_df.columns:
                    tid = _fmt_task_id(row.get(id_col))
                fb = _clean(row.get(block_col)) if block_col and block_col in table_df.columns else ""
                if not fb and "_dt_lvl2_key" in table_df.columns:
                    fb = _clean(row.get("_dt_lvl2_key"))
                bld = ""
                if "_dt_lvl3_key" in table_df.columns:
                    bld = _clean(row.get("_dt_lvl3_key"))
                if not bld:
                    bld_col = _col(table_df, ["building", "строение", "корпус", "объект"])
                    bld = _clean(row.get(bld_col)) if bld_col else ""

                ps = row.get("plan start")
                pe = row.get("plan end")
                bs = row.get("base start")
                be = row.get("base end")
                pdur = None
                bdur = None
                if isinstance(ps, pd.Timestamp) and isinstance(pe, pd.Timestamp) and pd.notna(ps) and pd.notna(pe):
                    pdur = int(round((pe - ps).total_seconds() / 86400.0))
                if isinstance(bs, pd.Timestamp) and isinstance(be, pd.Timestamp) and pd.notna(bs) and pd.notna(be):
                    bdur = int(round((be - bs).total_seconds() / 86400.0))
                dur_diff = (pdur - bdur) if pdur is not None and bdur is not None else None

                def _num(v: Any) -> int | None:
                    if v is None or (isinstance(v, float) and pd.isna(v)):
                        return None
                    try:
                        return int(round(float(v)))
                    except (TypeError, ValueError):
                        return None

                sd = _num(row.get("plan_start_diff"))
                ed = _num(row.get("plan_end_diff"))
                rows_out.append(
                    {
                        "project": _clean(row.get("project name")),
                        "task": task,
                        "task_id": tid or None,
                        "block": fb or None,
                        "building": bld or None,
                        "base_start": _fmt_date(bs),
                        "plan_start": _fmt_date(ps),
                        "dev_start_days": sd,
                        "dev_start": _fmt_int_days(sd),
                        "base_end": _fmt_date(be),
                        "plan_end": _fmt_date(pe),
                        "dev_end_days": ed,
                        "dev_end": _fmt_int_days(ed),
                        "base_dur_days": bdur,
                        "plan_dur_days": pdur,
                        "dev_dur_days": dur_diff,
                        "dev_dur": _fmt_int_days(dur_diff),
                        "reason": _clean(row.get("reason of deviation")) if "reason of deviation" in table_df.columns else None,
                        "notes": _clean(row.get(notes_col)) if notes_col else None,
                        "level": _num(row.get(level_col)) if level_col else None,
                    }
                )

        payload = {
            "meta": {
                "rows": len(rows_out),
                "chart_rows": len(chart_rows),
                "source": "web_data.db",
                "data_mode": DATA_MODE,
                "parity": "main_plan_fact_dates",
                "version_id": int(version_id),
                "rule": (
                    "Режим «Причины»: ур.5 · причина · (база−план)<0"
                    if show_reasons and not covenant_block
                    else "Откл. = база − план; таблица: откл. окончания < 0"
                ),
                "error": None,
                "mode": mode,
                "db": db_status(),
            },
            "filters": {
                "projects": available_projects,
                "blocks": available_blocks,
                "buildings": available_buildings,
                "levels": [
                    {"id": "4", "label": "Уровень 4 (укрупнённо)"},
                    {"id": "5", "label": "Уровень 5 (детально)"},
                ],
                "reasons": available_reasons,
                "label_modes": [
                    {"id": "name", "label": "По наименованию MSP"},
                    {"id": "lot", "label": "По лоту"},
                ],
                "has_lot": bool(lot_col),
                "applied": {
                    "project": applied_project,
                    "block": applied_block,
                    "building": applied_building,
                    "level": applied_level,
                    "reason": applied_reason,
                    "show_reasons": bool(show_reasons),
                    "hide_completed": bool(hide_completed),
                    "only_covenants": bool(only_covenants),
                    "only_neg_end": bool(only_neg_end),
                    "show_dur": bool(show_dur),
                    "label_mode": applied_label,
                    "level_skipped": level_skipped,
                },
            },
            "kpis": {
                "metric_task": metric_task,
                "max_abs_dev_days": max_abs_global,
                "plates": plates,
            },
            "chart": {
                "range_start": range_start,
                "range_end": range_end,
                "rows": chart_rows,
                "capped": chart_capped,
                "kind": chart_kind,
                "caption": chart_caption,
                "base_color": "#14b8a6",
                "plan_color": "#fb923c",
            },
            "covenant_table": covenant_table,
            "columns": columns,
            "rows": rows_out,
        }
        cache_set("baseline-deviation", cache_key, payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        return _empty_payload(error=f"baseline-deviation: {exc}")
