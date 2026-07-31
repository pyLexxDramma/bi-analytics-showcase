"""График проекта — паритет с [main] dashboard_project_schedule_chart, данные из web_data.db."""
from __future__ import annotations

import math
import re
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from app.config import DATA_MODE, WEB_DB_PATH
from app.services.core_bridge import (
    import_dashboard_module,
    load_msp_frame,
    prepare_web_db,
)
from app.services.db_ingest import db_status
from app.services.report_cache import cache_get, cache_set

GANTT_CAP = 600
PLAN_COLOR = "#14b8a6"
FACT_COLOR = "#fb923c"
_DATE_BAR_FMT = "%d-%m-%y"
_DATE_TBL_FMT = "%d.%m.%Y"
_GENERIC_BLOCK = re.compile(r"(?i)^блок\s*\d+$")
_LOT_BLANK = frozenset({"", "nan", "none", "null", "<na>", "-", "—"})


def _robust_date_window(
    dates: list[date],
    *,
    min_points: int = 8,
    gap_days: float = 366.0,
    anomaly_days: float = 366 * 4,
) -> tuple[date | None, date | None]:
    """Как main `_gantt_robust_date_window`: отсекает изолированные выбросы (2006/2028)."""
    pts = sorted({d.toordinal() for d in dates if isinstance(d, date)})
    if len(pts) < min_points:
        return None, None
    lo_full, hi_full = pts[0], pts[-1]
    if (hi_full - lo_full) <= anomaly_days:
        return None, None
    lo_i = 0
    while lo_i < len(pts) - 1 and (pts[lo_i + 1] - pts[lo_i]) > gap_days:
        lo_i += 1
    hi_i = len(pts) - 1
    while hi_i > 0 and (pts[hi_i] - pts[hi_i - 1]) > gap_days:
        hi_i -= 1
    if hi_i <= lo_i:
        return None, None
    if pts[lo_i] == pts[0] and pts[hi_i] == pts[-1]:
        return None, None
    return date.fromordinal(pts[lo_i]), date.fromordinal(pts[hi_i])


def _gantt_row_dates(row: dict[str, Any]) -> list[date]:
    out: list[date] = []
    for lane in ("baseline", "current"):
        for key in ("start", "end"):
            raw = (row.get(lane) or {}).get(key)
            if not raw:
                continue
            try:
                out.append(date.fromisoformat(str(raw)[:10]))
            except ValueError:
                continue
    return out


def _filter_gantt_outlier_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Убрать с диаграммы выбросы дат и нулевые полосы (начало = конец); таблица без изменений."""

    def _has_zero_span(row: dict[str, Any]) -> bool:
        """Скрыть, если план или факт — точка (начало = конец)."""
        for lane in ("baseline", "current"):
            block = row.get(lane) or {}
            s, e = block.get("start"), block.get("end")
            if not s or not e:
                continue
            try:
                ds = date.fromisoformat(str(s)[:10])
                de = date.fromisoformat(str(e)[:10])
            except ValueError:
                continue
            if ds == de:
                return True
        return False

    all_dates: list[date] = []
    for row in rows:
        all_dates.extend(_gantt_row_dates(row))
    lo, hi = _robust_date_window(all_dates)

    def _keep(row: dict[str, Any]) -> bool:
        if _has_zero_span(row):
            return False
        ds = _gantt_row_dates(row)
        if not ds:
            return True
        if lo is not None and hi is not None:
            if any(d < lo or d > hi for d in ds):
                return False
        elif min(ds).year < 2015 or (max(ds) - min(ds)).days > 366 * 8:
            return False
        if (max(ds) - min(ds)).days > 366 * 8:
            return False
        return True

    return [row for row in rows if _keep(row)]


def _normalize(value: Any) -> str:
    text = str(value or "").casefold().replace("_", " ")
    return re.sub(r"\s+", " ", text).strip()


def _clean_task_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.casefold() in {"nan", "none"}:
        return ""
    text = re.sub(r"(?i)^\s*задача\s+\d+\s+", "", text)
    text = re.sub(r"(?i)^\s*задача\s+", "", text)
    return text.strip()


def _as_level(value: Any) -> int | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        return int(float(str(value).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return None


def _fmt_dev(days: int | float | None) -> str:
    if days is None or (isinstance(days, float) and pd.isna(days)):
        return ""
    try:
        n = int(round(float(days)))
    except (TypeError, ValueError):
        return str(days).strip()
    if n == 0:
        return "0 дн."
    return f"{n:+d} дн." if n > 0 else f"{n} дн."


def _is_blank_block(value: Any) -> bool:
    text = str(value or "").strip()
    return not text or text.casefold() in {"nan", "none", "null", "-"}


def _is_covenant_block(value: str | None) -> bool:
    text = (value or "").casefold()
    return any(tok in text for tok in ("ковенант", "ковен", "covenant", "coven"))


def _is_generic_block_name(value: Any) -> bool:
    text = str(value or "").strip()
    if not text or text.casefold() in {"nan", "none"}:
        return True
    return bool(_GENERIC_BLOCK.match(text))


def _cmp_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _sched_col(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    cols = {_normalize(c): str(c) for c in frame.columns}
    for name in candidates:
        hit = cols.get(_normalize(name))
        if hit:
            return hit
    return None


def _wbs_tuple(val: Any) -> tuple[int, ...]:
    try:
        if val is None or pd.isna(val):
            return ()
    except Exception:
        if val is None:
            return ()
    parts = [p for p in re.split(r"[.\s/|>\\-]+", str(val).strip()) if p]
    out: list[int] = []
    for part in parts:
        try:
            out.append(int(float(part)))
        except (TypeError, ValueError):
            continue
    return tuple(out)


def _coerce_pct(series: pd.Series) -> pd.Series:
    num = pd.to_numeric(series, errors="coerce").astype("float64")
    need = num.isna() & series.notna()

    def _parse(value: Any) -> float:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return np.nan
        text = str(value)
        for ch in ("\ufeff", "\u00a0", "\u202f", "\u2007", " ", "\t", "%"):
            text = text.replace(ch, "")
        text = text.replace(",", ".")
        if not text or text.casefold() in {"nan", "nat", "none", "-", "—"}:
            return np.nan
        try:
            return float(text)
        except (TypeError, ValueError):
            return np.nan

    if need.any():
        num.loc[need] = series.loc[need].map(_parse)
    if num.notna().any():
        mx = float(num.max(skipna=True))
        mn = float(num.min(skipna=True))
        if mx <= 1.000001 and mn >= 0.0:
            num = num * 100.0
    return num


def _level_target(ln: pd.Series, level_sel: str) -> int | None:
    lvl_map = {"Верхний уровень": 4, "Детальный уровень": 5, "4": 4, "5": 5}
    target = lvl_map.get(str(level_sel).strip())
    if target is None:
        return None
    nums = pd.to_numeric(ln, errors="coerce").dropna()
    if nums.empty:
        return target
    levels = sorted({int(round(float(x))) for x in nums})
    if target in levels:
        return target
    if level_sel in {"Верхний уровень", "4"}:
        mid = [lv for lv in levels if 3 <= lv <= 4]
        if mid:
            return max(mid)
        deeper = [lv for lv in levels if lv > 2]
        return max(deeper) if deeper else target
    for lv in (5, 4, 3):
        if lv in levels:
            return lv
    return target


def _fmt_iso(ts: Any) -> str | None:
    if ts is None or (isinstance(ts, float) and pd.isna(ts)):
        return None
    try:
        if pd.isna(ts):
            return None
        return pd.Timestamp(ts).strftime("%Y-%m-%d")
    except Exception:
        return None


def _fmt_display(ts: Any, fmt: str) -> str:
    iso = _fmt_iso(ts)
    if not iso:
        return ""
    return pd.Timestamp(iso).strftime(fmt)


def _empty_payload(*, error: str | None = None) -> dict[str, Any]:
    return {
        "meta": {
            "source": "web_data.db",
            "data_mode": DATA_MODE,
            "parity": "main_project_schedule",
            "version_id": None,
            "rows": 0,
            "gantt_rows": 0,
            "gantt_cap": GANTT_CAP,
            "error": error,
            "banner": None,
            "db": db_status(),
            "rule": "План = базовые даты; Факт = текущий план (Начало/Окончание)",
        },
        "filters": {
            "projects": ["Все"],
            "blocks": ["Все"],
            "buildings": ["Все"],
            "levels": [
                {"id": "Верхний уровень", "label": "Верхний уровень"},
                {"id": "Детальный уровень", "label": "Детальный уровень"},
            ],
            "applied": {
                "project": "Все",
                "block": "Все",
                "building": "Все",
                "level": "Верхний уровень",
                "show_reasons": False,
                "show_lots": False,
                "label_pct": False,
                "hide_completed": False,
                "only_delay": False,
                "level_skipped": False,
                "multi_project": True,
            },
        },
        "gantt": {
            "range_start": None,
            "range_end": None,
            "capped": False,
            "plan_color": PLAN_COLOR,
            "fact_color": FACT_COLOR,
            "label_pct": False,
            "rows": [],
        },
        "rows": [],
        "columns": [],
    }


def _block_values(frame: pd.DataFrame, block_col: str | None) -> list[str]:
    if not block_col or block_col not in frame.columns:
        return []
    values = (
        frame[block_col]
        .dropna()
        .astype(str)
        .map(lambda x: str(x).strip())
        .tolist()
    )
    uniq = sorted(
        {
            v
            for v in values
            if v and v.casefold() not in {"nan", "none"} and not _is_generic_block_name(v)
        },
        key=str.casefold,
    )
    return uniq


def _building_values(frame: pd.DataFrame, level_col: str | None, task_col: str | None) -> list[str]:
    if frame is None or getattr(frame, "empty", True) or not level_col or not task_col:
        return []
    if level_col not in frame.columns or task_col not in frame.columns:
        return []
    ln = pd.to_numeric(frame[level_col], errors="coerce")
    names = [
        _clean_task_label(x)
        for x in frame.loc[ln == 3.0, task_col].dropna().astype(str).tolist()
    ]
    return sorted(
        {n for n in names if n and n.casefold() not in {"nan", "none"}},
        key=str.casefold,
    )


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
    names = frame[task_col].astype(str).map(_clean_task_label)
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


def _aggregate_by_lot(
    frame: pd.DataFrame,
    *,
    lot_col: str,
    task_col: str,
    proj_col: str | None,
) -> pd.DataFrame:
    work = frame.copy()
    lot = work[lot_col].astype(str).str.strip()
    mask = (~lot.str.casefold().isin(_LOT_BLANK)) & work[lot_col].notna()
    work = work.loc[mask].copy()
    if work.empty:
        return work
    lot = lot.loc[mask]
    multi_proj = (
        proj_col
        and proj_col in work.columns
        and work[proj_col].astype(str).str.strip().nunique() > 1
    )
    if multi_proj:
        work["_lot_grp"] = work[proj_col].astype(str).str.strip() + "\x1f" + lot
    else:
        work["_lot_grp"] = lot
    for col in ("plan start", "plan end", "base start", "base end"):
        if col in work.columns:
            work[col] = pd.to_datetime(work[col], errors="coerce")
    rows: list[dict[str, Any]] = []
    for _, group in work.groupby("_lot_grp", sort=True):
        rec: dict[str, Any] = {}
        label = str(group[lot_col].iloc[0]).strip()
        rec[lot_col] = label
        rec[task_col] = label
        if proj_col and proj_col in group.columns:
            ser = group[proj_col].dropna()
            rec[proj_col] = ser.iloc[0] if not ser.empty else None
        for col in ("plan start", "base start"):
            if col in group.columns:
                rec[col] = group[col].min()
        for col in ("plan end", "base end"):
            if col in group.columns:
                rec[col] = group[col].max()
        if "pct complete" in group.columns:
            rec["pct complete"] = pd.to_numeric(group["pct complete"], errors="coerce").max()
        rows.append(rec)
    return pd.DataFrame(rows) if rows else work.iloc[0:0].copy()


def build_project_schedule_payload(
    *,
    project: str | None = None,
    level: str | None = "Верхний уровень",
    block: str | None = None,
    building: str | None = None,
    hide_completed: bool = False,
    only_delay: bool = False,
    show_reasons: bool = False,
    show_lots: bool = False,
    label_pct: bool = False,
) -> dict[str, Any]:
    cache_key = (
        f"v3|p={project or 'Все'}|l={level}|b={block or 'Все'}|bd={building or 'Все'}"
        f"|hc={int(hide_completed)}|od={int(only_delay)}|sr={int(show_reasons)}"
        f"|sl={int(show_lots)}|lp={int(label_pct)}|db={WEB_DB_PATH}|mtime={db_status().get('mtime')}"
    )
    cached = cache_get("project-schedule", cache_key, max_age_sec=3600)
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

        proj_col = _sched_col(work, ["project name", "Проект", "проект", "Project"])
        if proj_col:
            work = labels_mod.apply_unified_project_column(work, proj_col)

        if "plan start" not in work.columns or "plan end" not in work.columns:
            return _empty_payload(error="Нужны колонки plan start / plan end в MSP")

        work["plan start"] = pd.to_datetime(work["plan start"], errors="coerce")
        work["plan end"] = pd.to_datetime(work["plan end"], errors="coerce")
        for col in ("base start", "base end"):
            if col in work.columns:
                work[col] = pd.to_datetime(work[col], errors="coerce")

        plot_df = work[work["plan start"].notna() & work["plan end"].notna()].copy()
        if plot_df.empty:
            return _empty_payload(error="Нет строк с заполненными Начало/Окончание")

        block_col = _sched_col(plot_df, ["block", "БЛОК", "Блок", "Функциональный блок"])
        level_col = _sched_col(
            plot_df,
            ["level", "outline level", "Уровень", "уровень структуры", "Исходный уровень"],
        )
        task_col = _sched_col(plot_df, ["task name", "Task Name", "Название"]) or "task name"
        if task_col not in plot_df.columns:
            plot_df[task_col] = plot_df.index.astype(str)
        lot_col = _sched_col(plot_df, ["lot", "Лот", "ЛОТ"])
        wbs_col = _sched_col(plot_df, ["outline number", "wbs", "код wbs"])

        available_projects = ["Все"]
        if proj_col:
            available_projects += labels_mod.project_labels_for_filter(plot_df[proj_col])
        applied_project = project if project in available_projects else "Все"
        if applied_project != "Все" and proj_col:
            plot_df = labels_mod.filter_dataframe_by_project_labels(
                plot_df, [applied_project], col=proj_col
            )

        after_project = plot_df.copy()
        available_blocks = ["Все"] + _block_values(plot_df, block_col)
        applied_block = block if block in available_blocks else "Все"
        if applied_block != "Все" and block_col and block_col in plot_df.columns:
            plot_df = plot_df.loc[
                plot_df[block_col].astype(str).map(_cmp_key) == _cmp_key(applied_block)
            ].copy()

        covenant = _is_covenant_block(applied_block)
        bld_source = after_project if covenant else plot_df
        available_buildings = ["Все"] + _building_values(bld_source, level_col, task_col)
        applied_building = building if building in available_buildings else "Все"
        if applied_building != "Все" and level_col and task_col:
            sliced = _apply_building_slice(
                bld_source,
                building=applied_building,
                level_col=level_col,
                task_col=task_col,
            )
            if covenant and applied_block != "Все" and block_col and block_col in sliced.columns:
                sliced = sliced.loc[
                    sliced[block_col].astype(str).map(_cmp_key) == _cmp_key(applied_block)
                ].copy()
            plot_df = sliced

        level_sel = level if level in {"Верхний уровень", "Детальный уровень", "4", "5"} else "Верхний уровень"
        if level_sel == "4":
            level_sel = "Верхний уровень"
        elif level_sel == "5":
            level_sel = "Детальный уровень"

        level_skipped = False
        if show_reasons and level_col and level_col in plot_df.columns:
            ln_all = pd.to_numeric(plot_df[level_col], errors="coerce")
            leaf = ln_all == 5.0
            if bool(leaf.any()) and wbs_col and wbs_col in plot_df.columns:
                wbs_all = plot_df[wbs_col].map(_wbs_tuple)
                ancestors: set[tuple[int, ...]] = set()
                for item in wbs_all[leaf].tolist():
                    if not item:
                        continue
                    for k in range(1, len(item) + 1):
                        ancestors.add(item[:k])
                plot_df = (
                    plot_df.loc[wbs_all.isin(ancestors)].copy()
                    if ancestors
                    else plot_df.loc[leaf | (ln_all <= 5)].copy()
                )
            elif bool(leaf.any()):
                plot_df = plot_df.loc[ln_all.notna() & (ln_all <= 5)].copy()
            level_skipped = True
        elif covenant or show_lots:
            level_skipped = True
        elif level_col and level_col in plot_df.columns:
            ln = pd.to_numeric(plot_df[level_col], errors="coerce")
            target = _level_target(ln, level_sel)
            if target is not None and ln.notna().any():
                plot_df = plot_df.loc[ln == float(target)].copy()

        pct_raw = _sched_col(plot_df, ["pct complete", "% complete", "Процент выполнения", "% завершения"])
        if pct_raw:
            plot_df["pct complete"] = _coerce_pct(plot_df[pct_raw])
        else:
            plot_df["pct complete"] = np.nan

        if hide_completed:
            plot_df = plot_df.loc[~(_coerce_pct(plot_df["pct complete"]) >= 99.999)].copy()

        if only_delay and "base end" in plot_df.columns and "plan end" in plot_df.columns:
            be = pd.to_datetime(plot_df["base end"], errors="coerce")
            fe = pd.to_datetime(plot_df["plan end"], errors="coerce")
            fin_dev = (be - fe).dt.days
            plot_df = plot_df.loc[fin_dev.notna() & (fin_dev < 0)].copy()

        if show_lots:
            if not lot_col or lot_col not in plot_df.columns:
                plot_df = plot_df.iloc[0:0].copy()
            else:
                plot_df = _aggregate_by_lot(
                    plot_df, lot_col=lot_col, task_col=task_col, proj_col=proj_col
                )

        if plot_df.empty:
            payload = _empty_payload()
            payload["meta"]["version_id"] = int(version_id)
            payload["meta"]["error"] = None
            payload["filters"]["projects"] = available_projects
            payload["filters"]["blocks"] = available_blocks
            payload["filters"]["buildings"] = available_buildings
            payload["filters"]["applied"] = {
                "project": applied_project,
                "block": applied_block,
                "building": applied_building,
                "level": level_sel,
                "show_reasons": show_reasons,
                "show_lots": show_lots,
                "label_pct": label_pct,
                "hide_completed": hide_completed,
                "only_delay": only_delay,
                "level_skipped": level_skipped,
                "multi_project": applied_project == "Все",
            }
            cache_set("project-schedule", cache_key, payload)
            return payload

        sort_cols: list[str] = []
        sort_asc: list[bool] = []
        if applied_project == "Все" and proj_col and proj_col in plot_df.columns:
            sort_cols.append(proj_col)
            sort_asc.append(True)
        if level_col and level_col in plot_df.columns and not show_lots:
            plot_df = plot_df.copy()
            plot_df["_sort_lvl"] = pd.to_numeric(plot_df[level_col], errors="coerce")
            sort_cols.append("_sort_lvl")
            sort_asc.append(True)
        if block_col and block_col in plot_df.columns:
            sort_cols.append(block_col)
            sort_asc.append(True)
        sort_cols.append(task_col)
        sort_asc.append(True)
        sort_cols.append("plan start")
        sort_asc.append(True)
        pairs = [(c, a) for c, a in zip(sort_cols, sort_asc) if c in plot_df.columns]
        if pairs:
            sc, sa = zip(*pairs)
            plot_df = plot_df.sort_values(list(sc), ascending=list(sa), na_position="last")

        if only_delay and "base end" in plot_df.columns and "plan end" in plot_df.columns:
            be = pd.to_datetime(plot_df["base end"], errors="coerce")
            fe = pd.to_datetime(plot_df["plan end"], errors="coerce")
            plot_df = (
                plot_df.assign(_dd=(be - fe).dt.days)
                .sort_values("_dd", ascending=True, na_position="last")
                .drop(columns=["_dd"])
            )

        table_df = plot_df.copy()
        total_rows = len(table_df)
        gantt_df = table_df.head(GANTT_CAP)
        capped = total_rows > GANTT_CAP
        multi_project = applied_project == "Все"
        banner = None
        if multi_project and proj_col:
            banner = (
                "Выбрано несколько проектов: данных много, построение может занять время. "
                f"На диаграмме показываются первые {GANTT_CAP} задач "
                "(защита от зависания браузера); в таблице ниже — полный список. "
                "Для ускорения выберите один проект."
            )
        elif capped:
            banner = (
                f"На диаграмме показаны первые {GANTT_CAP} из {total_rows} задач после фильтров. "
                "В таблице ниже — полный список. Уточните фильтры для более узкой выборки."
            )

        id_col = _sched_col(
            table_df,
            ["task id seq", "Ид", "ID", "task id", "unique id", "Уникальный_идентификатор"],
        )
        reason_col = _sched_col(
            table_df,
            ["reason of deviation", "причины отклонений", "причина отклонения"],
        )
        notes_col = _sched_col(table_df, ["notes", "заметки"])

        gantt_rows: list[dict[str, Any]] = []
        for _, row in gantt_df.iterrows():
            task = _clean_task_label(row.get(task_col))
            project_name = (
                str(row.get(proj_col, "") or "").strip() if proj_col else ""
            )
            label = f"{project_name}: {task}" if multi_project and project_name else task
            base_start = row.get("base start")
            base_end = row.get("base end")
            plan_start = row.get("plan start")
            plan_end = row.get("plan end")
            pct = row.get("pct complete")
            pct_val = None
            if pct is not None and not (isinstance(pct, float) and pd.isna(pct)):
                try:
                    pct_val = round(float(pct), 1)
                except (TypeError, ValueError):
                    pct_val = None
            gantt_rows.append(
                {
                    "project": project_name or None,
                    "task": task,
                    "label": label,
                    "pct_complete": pct_val,
                    "baseline": {
                        "start": _fmt_iso(base_start) or _fmt_iso(plan_start),
                        "end": _fmt_iso(base_end) or _fmt_iso(plan_end),
                        "start_label": _fmt_display(base_start if pd.notna(base_start) else plan_start, _DATE_BAR_FMT),
                        "end_label": _fmt_display(base_end if pd.notna(base_end) else plan_end, _DATE_BAR_FMT),
                    },
                    "current": {
                        "start": _fmt_iso(plan_start),
                        "end": _fmt_iso(plan_end),
                        "start_label": _fmt_display(plan_start, _DATE_BAR_FMT),
                        "end_label": _fmt_display(plan_end, _DATE_BAR_FMT),
                    },
                }
            )
        gantt_rows = _filter_gantt_outlier_rows(gantt_rows)

        table_rows: list[dict[str, Any]] = []
        for _, row in table_df.iterrows():
            plan_start = row.get("plan start")
            plan_end = row.get("plan end")
            base_start = row.get("base start") if "base start" in table_df.columns else None
            base_end = row.get("base end") if "base end" in table_df.columns else None
            start_dev = None
            end_dev = None
            if pd.notna(plan_start) and pd.notna(base_start):
                start_dev = int((pd.Timestamp(plan_start) - pd.Timestamp(base_start)).days)
            if pd.notna(plan_end) and pd.notna(base_end):
                end_dev = int((pd.Timestamp(plan_end) - pd.Timestamp(base_end)).days)
            pct = row.get("pct complete")
            pct_val = None
            if pct is not None and not (isinstance(pct, float) and pd.isna(pct)):
                try:
                    pct_val = int(round(float(pct)))
                except (TypeError, ValueError):
                    pct_val = None
            task_id = None
            if id_col and id_col in table_df.columns:
                raw_id = row.get(id_col)
                if raw_id is not None and not (isinstance(raw_id, float) and pd.isna(raw_id)):
                    try:
                        task_id = str(int(float(raw_id)))
                    except (TypeError, ValueError):
                        text = str(raw_id).strip()
                        task_id = None if text.casefold() in {"nan", "none"} else text
            lvl = _as_level(row.get(level_col)) if level_col else None
            project_name = (
                str(row.get(proj_col, "") or "").strip() if proj_col else ""
            )
            item: dict[str, Any] = {
                "project": project_name if multi_project else (project_name or applied_project),
                "task_id": task_id,
                "level": lvl,
                "task": _clean_task_label(row.get(lot_col if show_lots and lot_col else task_col)),
                "pct_complete": pct_val,
                "plan_start": _fmt_display(plan_start, _DATE_TBL_FMT) or None,
                "base_start": _fmt_display(base_start, _DATE_TBL_FMT) or None,
                "dev_start": _fmt_dev(start_dev),
                "dev_start_days": start_dev,
                "plan_end": _fmt_display(plan_end, _DATE_TBL_FMT) or None,
                "base_end": _fmt_display(base_end, _DATE_TBL_FMT) or None,
                "dev_end": _fmt_dev(end_dev),
                "dev_end_days": end_dev,
            }
            if show_reasons:
                reason = ""
                notes = ""
                if reason_col and reason_col in table_df.columns:
                    reason = str(row.get(reason_col) or "").strip()
                    if reason.casefold() == "nan":
                        reason = ""
                if notes_col and notes_col in table_df.columns:
                    notes = str(row.get(notes_col) or "").strip()
                    if notes.casefold() == "nan":
                        notes = ""
                item["reason"] = reason
                item["notes"] = notes
            table_rows.append(item)

        columns = [
            "Проект",
            "ИД",
            "Ур",
            "Название задачи" if not show_lots else "Лот",
            "% завершения",
            "Начало",
            "Базовое начало",
            "Отклонение начала",
            "Окончание",
            "Базовое окончание",
            "Отклонение окончания",
        ]
        if show_reasons:
            columns.extend(["Причины отклонений", "Заметки"])

        range_dates: list[date] = []
        for row in gantt_rows:
            for lane in ("baseline", "current"):
                for key in ("start", "end"):
                    raw = row[lane].get(key)
                    if raw:
                        range_dates.append(date.fromisoformat(str(raw)))

        payload = {
            "meta": {
                "source": "web_data.db",
                "data_mode": DATA_MODE,
                "parity": "main_project_schedule",
                "version_id": int(version_id),
                "rows": total_rows,
                "gantt_rows": len(gantt_rows),
                "gantt_cap": GANTT_CAP,
                "error": None,
                "banner": banner,
                "db": db_status(),
                "rule": "План = базовые даты; Факт = текущий план (Начало/Окончание)",
            },
            "filters": {
                "projects": available_projects,
                "blocks": available_blocks,
                "buildings": available_buildings,
                "levels": [
                    {"id": "Верхний уровень", "label": "Верхний уровень"},
                    {"id": "Детальный уровень", "label": "Детальный уровень"},
                ],
                "applied": {
                    "project": applied_project,
                    "block": applied_block,
                    "building": applied_building,
                    "level": level_sel,
                    "show_reasons": show_reasons,
                    "show_lots": show_lots,
                    "label_pct": label_pct,
                    "hide_completed": hide_completed,
                    "only_delay": only_delay,
                    "level_skipped": level_skipped,
                    "multi_project": multi_project,
                },
            },
            "gantt": {
                "range_start": min(range_dates).isoformat() if range_dates else None,
                "range_end": max(range_dates).isoformat() if range_dates else None,
                "capped": capped,
                "plan_color": PLAN_COLOR,
                "fact_color": FACT_COLOR,
                "label_pct": label_pct,
                "rows": gantt_rows,
            },
            "rows": table_rows,
            "columns": columns,
        }
        cache_set("project-schedule", cache_key, payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        return _empty_payload(error=str(exc))
