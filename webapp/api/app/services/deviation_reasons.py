"""Причины отклонений — паритет с [main] dashboard_deviations_combined, данные из web_data.db."""
from __future__ import annotations

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

REASON_BUCKET_COLORS: dict[str, str] = {
    "Изменение объемов": "#cddc39",
    "Изменение расценки": "#fbc02d",
    "Не передан фронт работ": "#26c6da",
    "Нет оплаты Подрядчику": "#ff9800",
    "Переделка за предыдущим подрядчиком": "#8bc34a",
    "Увеличение сроков по вине подрядчика": "#9e9e9e",
    "Расторжение Договора": "#ff7043",
    "Превышение срока по договору": "#ab47bc",
    "Корректировка РД": "#5c6bc0",
    "Длительное согласование договора": "#78909c",
    "Прочее": "#e91e63",
}

_MONTHS_RU = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}

_PLOTLY_QUALITATIVE = (
    "#636EFA",
    "#EF553B",
    "#00CC96",
    "#AB63FA",
    "#FFA15A",
    "#19D3F3",
    "#FF6692",
    "#B6E880",
    "#FF97FF",
    "#FECB52",
)

_BLANK = frozenset({"", "nan", "none", "null", "<na>", "-", "—", "нд", "nd", "nat"})
_GENERIC_BLOCK = re.compile(r"(?i)^блок\s*\d+$")


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


def _fmt_date(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.strftime("%d.%m.%Y")


def _period_label(period: pd.Period) -> str:
    try:
        return f"{_MONTHS_RU.get(int(period.month), 'Н/Д')} {int(period.year)}"
    except Exception:
        return str(period)


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


def _resolve_reason_col(frame: pd.DataFrame) -> str | None:
    hit = _col(
        frame,
        [
            "reason of deviation",
            "reason_of_deviation",
            "Причины отклонений",
            "Причина отклонения",
            "причины отклонений",
            "причина отклонения",
        ],
    )
    if hit:
        return hit
    for col in frame.columns:
        s = _normalize(col)
        if "причин" in s and "отклон" in s:
            if any(
                x in s
                for x in (
                    "отклонение окончания",
                    "отклонение начала",
                    "deviation in days",
                    "deviation start",
                )
            ):
                continue
            return str(col)
        if "reason" in s and "deviat" in s and "day" not in s:
            return str(col)
    return None


def _resolve_notes_col(frame: pd.DataFrame) -> str | None:
    return _col(
        frame,
        ["notes", "note", "Заметки", "заметки", "remarks", "комментарий", "Комментарии", "Куратор"],
    )


def _block_values(frame: pd.DataFrame, block_col: str | None) -> list[str]:
    if not block_col or block_col not in frame.columns:
        return []
    vals = [
        _clean(v)
        for v in frame[block_col].dropna().astype(str).tolist()
        if not _is_generic_block(v)
    ]
    return sorted({v for v in vals if v}, key=str.casefold)


def _building_values(frame: pd.DataFrame, level_col: str | None, task_col: str | None) -> list[str]:
    if frame is None or frame.empty or not level_col or not task_col:
        return []
    if level_col not in frame.columns or task_col not in frame.columns:
        return []
    ln = pd.to_numeric(frame[level_col], errors="coerce")
    names = [_clean(x) for x in frame.loc[ln == 3.0, task_col].dropna().astype(str).tolist()]
    return sorted({n for n in names if n}, key=str.casefold)


def _outline_levels(series: pd.Series) -> pd.Series:
    num = pd.to_numeric(series, errors="coerce")
    mask_na = num.isna()
    if not bool(mask_na.any()):
        return num
    ext = series[mask_na].astype(str).str.strip().str.extract(r"(-?\d+)", expand=False)
    out = num.copy()
    out.loc[mask_na] = pd.to_numeric(ext, errors="coerce").values
    return out


def _enrich_ancestor_keys(
    frame: pd.DataFrame, level_col: str | None, task_col: str
) -> pd.DataFrame:
    """Как main: «Строение» = предок с Уровень=3 (не лот)."""
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
            l2_keys.append(next((n for l, n in reversed(stack) if l == 2.0), ""))
            l3_keys.append(next((n for l, n in reversed(stack) if l == 3.0), ""))
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
    # Позиционно — иначе срезы с чужим index ломают «Строение».
    work["_dt_lvl2_key"] = pd.Series(l2_keys, dtype=object).to_numpy()
    work["_dt_lvl3_key"] = pd.Series(l3_keys, dtype=object).to_numpy()
    return work


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


def _maket_prepare(frame: pd.DataFrame) -> pd.DataFrame:
    """Как main `_deviations_maket_prepare_df`: ур.5, причина, base−plan < 0."""
    if frame is None or getattr(frame, "empty", True):
        return pd.DataFrame()
    work = frame.copy()
    reason_col = _resolve_reason_col(work)
    if reason_col and reason_col != "reason of deviation":
        work = work.rename(columns={reason_col: "reason of deviation"})
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
    else:
        lvl = _col(work, ["level", "outline level", "Уровень", "уровень структуры"])
        if lvl:
            mask_l = pd.to_numeric(work[lvl], errors="coerce") == 5

    mask_neg = pd.Series(False, index=work.index)
    if "_end_diff" in work.columns:
        mask_neg = mask_neg | (work["_end_diff"].notna() & (work["_end_diff"] < 0))
    if "deviation in days" in work.columns:
        did = pd.to_numeric(work["deviation in days"], errors="coerce")
        mask_neg = mask_neg | (did.notna() & (did < 0))
    if "base end" in work.columns:
        be_txt = work["base end"].astype(str).str.strip().str.upper()
        be_missing = work["base end"].isna() | be_txt.isin(
            {"", "НД", "ND", "NAN", "NONE", "NAT", "-"}
        )
        pe_ok = work["plan end"].notna() if "plan end" in work.columns else pd.Series(True, index=work.index)
        mask_neg = mask_neg | (mask_r & mask_l & be_missing & pe_ok)

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
        maket = maket.sort_values("_end_diff", ascending=False).reset_index(drop=True)
    return maket


def _empty_payload(*, error: str | None = None) -> dict[str, Any]:
    return {
        "meta": {
            "rows": 0,
            "source": "web_data.db",
            "data_mode": DATA_MODE,
            "parity": "main_deviation_reasons",
            "version_id": None,
            "rule": "Ур.5 · причина · (база−план)<0",
            "error": error,
            "db": db_status(),
        },
        "filters": {
            "projects": ["Все"],
            "blocks": ["Все"],
            "buildings": ["Все"],
            "reasons": ["Все"],
            "period": {"min": None, "max": None},
            "applied": {
                "project": "Все",
                "block": "Все",
                "building": "Все",
                "reason": "Все",
                "date_from": None,
                "date_to": None,
                "top5": False,
            },
        },
        "kpis": {
            "main_reason": "—",
            "main_reason_share_pct": 0.0,
            "main_reason_count": 0,
            "tasks": 0,
        },
        "tremor": {
            "by_reason": [],
            "reason_mix": [],
            "dynamics": {
                "by_project_charts": [],
                "project_month_rows": [],
                "project_month_total": 0,
                "by_project_stack": [],
                "stack_projects": [],
                "stack_colors": {},
                "summary_rows": [],
                "summary_totals": {"count": 0, "days": 0},
                "period_label": "Период (месяц)",
            },
        },
        "rows": [],
        "columns": [
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
        ],
    }


def build_deviation_reasons_payload(
    *,
    project: str | None = None,
    block: str | None = None,
    building: str | None = None,
    reason: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    top5: bool = False,
) -> dict[str, Any]:
    cache_key = (
        f"v4|p={project or 'Все'}|b={block or 'Все'}|bd={building or 'Все'}"
        f"|r={reason or 'Все'}|df={date_from or ''}|dt={date_to or ''}"
        f"|t5={int(bool(top5))}|db={WEB_DB_PATH}|mtime={db_status().get('mtime')}"
    )
    cached = cache_get("deviation-reasons", cache_key, max_age_sec=3600)
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
        applied_block = block if block in available_blocks else "Все"
        if applied_block != "Все" and block_col and block_col in scoped.columns:
            scoped = scoped[
                scoped[block_col].astype(str).map(_cmp_key) == _cmp_key(applied_block)
            ].copy()

        # До date/maket-среза: иначе предки ур.3 выпадают и «Строение» падает в лот.
        scoped = _enrich_ancestor_keys(scoped, level_col, task_col)

        available_buildings = ["Все"] + _building_values(scoped, level_col, task_col)
        applied_building = building if building in available_buildings else "Все"
        if (
            applied_building != "Все"
            and level_col
            and task_col
            and level_col in scoped.columns
            and task_col in scoped.columns
        ):
            scoped = _apply_building_slice(
                scoped,
                building=applied_building,
                level_col=level_col,
                task_col=task_col,
            )

        if "plan end" in scoped.columns:
            pe_all = pd.to_datetime(scoped["plan end"], errors="coerce").dropna()
        else:
            pe_all = pd.Series(dtype="datetime64[ns]")
        period_min = pe_all.min().date() if not pe_all.empty else None
        period_max = pe_all.max().date() if not pe_all.empty else None

        def _parse_bound(raw: str | None, fallback: date | None) -> date | None:
            if not raw:
                return fallback
            try:
                return date.fromisoformat(raw[:10])
            except ValueError:
                return fallback

        applied_from = _parse_bound(date_from, period_min)
        applied_to = _parse_bound(date_to, period_max)
        if applied_from and applied_to and applied_from > applied_to:
            applied_from, applied_to = applied_to, applied_from

        if applied_from and applied_to and "plan end" in scoped.columns:
            pe = pd.to_datetime(scoped["plan end"], errors="coerce")
            start = pd.Timestamp(applied_from)
            end = pd.Timestamp(applied_to) + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
            scoped = scoped[pe.notna() & (pe >= start) & (pe <= end)].copy()

        maket = _maket_prepare(scoped)
        if maket.empty:
            empty = _empty_payload()
            empty["meta"]["version_id"] = int(version_id)
            empty["filters"] = {
                "projects": available_projects,
                "blocks": available_blocks,
                "buildings": available_buildings,
                "reasons": ["Все"],
                "period": {
                    "min": period_min.isoformat() if period_min else None,
                    "max": period_max.isoformat() if period_max else None,
                },
                "applied": {
                    "project": applied_project,
                    "block": applied_block,
                    "building": applied_building,
                    "reason": "Все",
                    "date_from": applied_from.isoformat() if applied_from else None,
                    "date_to": applied_to.isoformat() if applied_to else None,
                    "top5": bool(top5),
                },
            }
            cache_set("deviation-reasons", cache_key, empty)
            return empty

        reason_series = maket["reason of deviation"].astype(str).str.strip()
        available_reasons = ["Все"] + sorted(
            {r for r in reason_series.tolist() if r and r.casefold() not in _BLANK},
            key=str.casefold,
        )
        applied_reason = reason if reason in available_reasons else "Все"

        chart_df = maket
        table_df = maket
        if applied_reason != "Все":
            table_df = maket[reason_series == applied_reason].copy()

        counts = reason_series.value_counts()
        total = int(len(maket))
        main_reason = str(counts.index[0]).strip() if not counts.empty else "—"
        main_count = int(counts.iloc[0]) if not counts.empty else 0
        main_pct = round(main_count / total * 100, 1) if total else 0.0

        ranked = [(str(name), int(cnt)) for name, cnt in counts.items()]
        if top5:
            ranked = ranked[:5]

        by_reason = []
        reason_mix = []
        for name, count in ranked:
            pct = round(count / total * 100, 1) if total else 0.0
            short = name if len(name) <= 48 else f"{name[:45]}…"
            by_reason.append(
                {
                    "reason": short,
                    "reason_full": name,
                    "count": count,
                    "pct": pct,
                    "label": f"{count} ({pct}%)",
                }
            )
            reason_mix.append(
                {
                    "name": name if len(name) <= 40 else f"{name[:37]}…",
                    "value": count,
                    "color": REASON_BUCKET_COLORS.get(_reason_bucket(name), "#e91e63"),
                }
            )

        dyn = maket.copy()
        if applied_reason != "Все":
            dyn = dyn[
                dyn["reason of deviation"].astype(str).str.strip() == applied_reason
            ].copy()

        dynamics_payload: dict[str, Any] = {
            "by_project_charts": [],
            "project_month_rows": [],
            "project_month_total": 0,
            "by_project_stack": [],
            "stack_projects": [],
            "stack_colors": {},
            "summary_rows": [],
            "summary_totals": {"count": 0, "days": 0},
            "period_label": "Период (месяц)",
        }

        if not dyn.empty and "plan end" in dyn.columns:
            pe = pd.to_datetime(dyn["plan end"], errors="coerce")
            dyn = dyn[pe.notna()].copy()
            pe = pe.loc[dyn.index]
            today_m = pd.Timestamp(date.today()).to_period("M")
            pe_m = pe.dt.to_period("M")
            dyn = dyn[pe_m <= today_m].copy()
            pe = pe.loc[dyn.index]
            if not dyn.empty:
                dyn["_period"] = pe.dt.to_period("M")
                dyn["_bucket"] = dyn["reason of deviation"].map(_reason_bucket)
                dyn["_maket_cnt"] = 1
                dyn["deviation in days"] = pd.to_numeric(
                    dyn["_end_diff"], errors="coerce"
                ).abs()
                if "project name" not in dyn.columns:
                    dyn["project name"] = ""

                periods_sorted = sorted(dyn["_period"].dropna().unique())
                period_labels = [_period_label(p) for p in periods_sorted]
                period_map = {p: _period_label(p) for p in periods_sorted}

                # --- фасеты: график на проект, стек по причинам ---
                by_project_charts: list[dict[str, Any]] = []
                projects_sorted = sorted(
                    {
                        _clean(p)
                        for p in dyn["project name"].astype(str).tolist()
                        if _clean(p)
                    },
                    key=str.casefold,
                )
                for pname in projects_sorted:
                    sub = dyn[
                        dyn["project name"].astype(str).str.strip().map(_cmp_key)
                        == _cmp_key(pname)
                    ].copy()
                    if sub.empty:
                        continue
                    g = (
                        sub.groupby(["_period", "_bucket"], observed=False)
                        .size()
                        .reset_index(name="count")
                    )
                    present = [
                        b
                        for b in REASON_BUCKET_ORDER
                        if b in set(g["_bucket"].astype(str).tolist())
                    ]
                    present += [
                        b
                        for b in sorted(g["_bucket"].astype(str).unique().tolist())
                        if b not in present
                    ]
                    psums = g.groupby("_period", observed=False)["count"].sum()
                    periods_p = [p for p in periods_sorted if float(psums.get(p, 0)) > 0]
                    if not periods_p:
                        continue
                    rows_p: list[dict[str, Any]] = []
                    for period in periods_p:
                        row: dict[str, Any] = {
                            "period": period_map[period],
                            "period_key": str(period),
                        }
                        total_p = 0
                        for bucket in present:
                            hit = g[(g["_period"] == period) & (g["_bucket"] == bucket)]
                            val = int(hit["count"].iloc[0]) if not hit.empty else 0
                            row[bucket] = val
                            total_p += val
                        row["total"] = total_p
                        if total_p > 0:
                            rows_p.append(row)
                    if not rows_p:
                        continue
                    by_project_charts.append(
                        {
                            "project": pname,
                            "categories": present,
                            "colors": {
                                b: REASON_BUCKET_COLORS.get(b, "#e91e63") for b in present
                            },
                            "rows": rows_p,
                        }
                    )
                dynamics_payload["by_project_charts"] = by_project_charts

                # --- таблица «Число отклонений по проекту и месяцу» ---
                pm = (
                    dyn.groupby(["project name", "_period"], observed=False)["_maket_cnt"]
                    .sum()
                    .reset_index()
                )
                pm_rows = []
                for _, rr in pm.iterrows():
                    cnt = int(rr["_maket_cnt"])
                    if cnt <= 0:
                        continue
                    pm_rows.append(
                        {
                            "project": _clean(rr["project name"]),
                            "period": period_map.get(rr["_period"], str(rr["_period"])),
                            "period_key": str(rr["_period"]),
                            "count": cnt,
                        }
                    )
                pm_rows.sort(
                    key=lambda r: (
                        r["project"].casefold(),
                        r["period_key"],
                    )
                )
                dynamics_payload["project_month_rows"] = pm_rows
                dynamics_payload["project_month_total"] = int(
                    sum(r["count"] for r in pm_rows)
                )

                # --- общий стек: период × проект ---
                stack_projects = sorted(
                    {r["project"] for r in pm_rows if r["project"]},
                    key=str.casefold,
                )
                stack_periods = []
                seen_p: set[str] = set()
                for p in periods_sorted:
                    lbl = period_map[p]
                    if any(r["period"] == lbl for r in pm_rows) and lbl not in seen_p:
                        stack_periods.append(lbl)
                        seen_p.add(lbl)
                stack_rows: list[dict[str, Any]] = []
                for lbl in stack_periods:
                    row = {"period": lbl}
                    total_p = 0
                    for pname in stack_projects:
                        val = sum(
                            r["count"]
                            for r in pm_rows
                            if r["project"] == pname and r["period"] == lbl
                        )
                        row[pname] = val
                        total_p += val
                    row["total"] = total_p
                    if total_p > 0:
                        stack_rows.append(row)
                dynamics_payload["by_project_stack"] = stack_rows
                dynamics_payload["stack_projects"] = stack_projects
                dynamics_payload["stack_colors"] = {
                    pname: _PLOTLY_QUALITATIVE[i % len(_PLOTLY_QUALITATIVE)]
                    for i, pname in enumerate(stack_projects)
                }

                # --- сводная: проект × причина ---
                summary = (
                    dyn.groupby(["project name", "reason of deviation"], observed=False)
                    .agg(
                        count=("_maket_cnt", "sum"),
                        days=("deviation in days", "sum"),
                    )
                    .reset_index()
                )
                summary = summary.sort_values("days", ascending=False)
                summary_rows = []
                for _, rr in summary.iterrows():
                    summary_rows.append(
                        {
                            "project": _clean(rr["project name"]),
                            "reason": _clean(rr["reason of deviation"]),
                            "count": int(rr["count"]),
                            "days": int(round(float(rr["days"] or 0))),
                        }
                    )
                dynamics_payload["summary_rows"] = summary_rows
                dynamics_payload["summary_totals"] = {
                    "count": int(sum(r["count"] for r in summary_rows)),
                    "days": int(sum(r["days"] for r in summary_rows)),
                }

        id_col = _task_id_col(table_df)
        notes_col = _resolve_notes_col(table_df)
        rows_out: list[dict[str, Any]] = []
        for _, rr in table_df.iterrows():
            tid = ""
            if id_col and id_col in table_df.columns:
                raw_id = rr.get(id_col)
                if pd.notna(raw_id) and str(raw_id).strip().casefold() not in _BLANK:
                    tid = str(raw_id).strip()
            fb = ""
            if block_col and block_col in table_df.columns:
                fb = _clean(rr.get(block_col))
            stv = ""
            if "_dt_lvl3_key" in table_df.columns:
                stv = _clean(rr.get("_dt_lvl3_key"))
            if not stv:
                # Без lot: в «Строение» только название строения (ур.3 / колонка building).
                bld_col = _col(
                    table_df,
                    ["строение", "Строение", "корпус", "здание", "building", "объект"],
                )
                if bld_col:
                    stv = _clean(rr.get(bld_col))
            tn = _clean(rr.get(task_col)) if task_col in table_df.columns else ""
            pe = rr.get("plan end")
            be = rr.get("base end")
            ed = rr.get("_end_diff")
            reason_text = _clean(rr.get("reason of deviation"))
            notes = _clean(rr.get(notes_col)) if notes_col else ""
            bucket = _reason_bucket(reason_text)
            end_diff = int(round(float(ed))) if pd.notna(ed) else None
            rows_out.append(
                {
                    "task_id": tid or None,
                    "project": _clean(rr.get("project name")),
                    "block": fb or None,
                    "task": tn or None,
                    "building": stv or None,
                    "plan_end": _fmt_date(pe),
                    "base_end": _fmt_date(be),
                    "end_diff_days": end_diff,
                    "reason": reason_text,
                    "bucket": bucket,
                    "bucket_color": REASON_BUCKET_COLORS.get(bucket, "#e91e63"),
                    "notes": notes or None,
                }
            )

        payload = {
            "meta": {
                "rows": len(rows_out),
                "chart_rows": total,
                "source": "web_data.db",
                "data_mode": DATA_MODE,
                "parity": "main_deviation_reasons",
                "version_id": int(version_id),
                "rule": "Ур.5 · причина · (база−план)<0",
                "error": None,
                "db": db_status(),
            },
            "filters": {
                "projects": available_projects,
                "blocks": available_blocks,
                "buildings": available_buildings,
                "reasons": available_reasons,
                "period": {
                    "min": period_min.isoformat() if period_min else None,
                    "max": period_max.isoformat() if period_max else None,
                },
                "applied": {
                    "project": applied_project,
                    "block": applied_block,
                    "building": applied_building,
                    "reason": applied_reason,
                    "date_from": applied_from.isoformat() if applied_from else None,
                    "date_to": applied_to.isoformat() if applied_to else None,
                    "top5": bool(top5),
                },
            },
            "kpis": {
                "main_reason": main_reason[:50] + ("…" if len(main_reason) > 50 else ""),
                "main_reason_share_pct": main_pct,
                "main_reason_count": main_count,
                "tasks": total,
            },
            "tremor": {
                "by_reason": by_reason,
                "reason_mix": reason_mix,
                "dynamics": dynamics_payload,
            },
            "rows": rows_out,
            "columns": [
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
            ],
        }
        cache_set("deviation-reasons", cache_key, payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        return _empty_payload(error=str(exc))
