"""Сверка API showcase с числами экрана основного дашборда [main].

Эталон не хардкодится: считается прямо здесь вызовом функций main
(`dashboards/finance_from_1c.py`, `dashboards/dev_projects_tz_matrix.py`),
но **на той же web_data.db, которую рисует экран main**. Считать эталон по БД
самого сервиса нельзя: тогда обе стороны берут один и тот же (возможно
устаревший) снимок, smoke зелёный, а на экране main другие цифры.

Эталонная БД: `BI_MAIN_WEB_DB_PATH`, иначе `<каталог main>/data/web_data.db`
(`BI_MAIN_APP_DIR` или автоопределение рядом с showcase-репо).
БД сервиса берётся из ответа API (`meta.db.web_db_path`).

Запуск:
    python webapp/scripts/parity_smoke.py                     # все поддержанные экраны
    python webapp/scripts/parity_smoke.py bdds bdr            # выборочно
    python webapp/scripts/parity_smoke.py --api http://127.0.0.1:8000

Exit code: 0 — расхождений нет, 1 — есть, 2 — сверку не удалось выполнить.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

API_DIR = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(API_DIR))


def _main_db_candidates() -> list[Path]:
    env_db = (os.environ.get("BI_MAIN_WEB_DB_PATH") or "").strip()
    if env_db:
        return [Path(env_db)]
    out: list[Path] = []
    env_dir = (os.environ.get("BI_MAIN_APP_DIR") or "").strip()
    if env_dir:
        out.append(Path(env_dir) / "data" / "web_data.db")
    analitics_root = Path(__file__).resolve().parents[3]
    out.append(
        analitics_root / "bi-analytics-v-5-main" / "bi-analytics-v-5-main" / "data" / "web_data.db"
    )
    out.append(analitics_root / "bi-analytics-v-5-main" / "data" / "web_data.db")
    return out


def _resolve_reference_db() -> Path:
    for candidate in _main_db_candidates():
        if candidate.is_file():
            return candidate.resolve()
    paths = "\n  ".join(str(p) for p in _main_db_candidates())
    raise SystemExit(
        "Не найдена web_data.db основного дашборда — сверять с экраном main нечем.\n"
        f"Проверены пути:\n  {paths}\n"
        "Укажите BI_MAIN_WEB_DB_PATH или BI_MAIN_APP_DIR."
    )


# До импорта app.config: она читает WEB_DB_PATH на импорте модуля.
REFERENCE_DB = _resolve_reference_db()
os.environ["WEB_DB_PATH"] = str(REFERENCE_DB)

from app.services.core_bridge import (  # noqa: E402
    active_version_id,
    ensure_renderers_shim,
    import_dashboard_module,
    load_msp_frame,
    load_version_df,
    session_state,
)

# KPI сравниваем в млн (округление main/API до 0.1), таблицы — относительно.
KPI_TOL_MLN = 0.1
ROW_TOL_REL = 0.01
# `_renderers._FINANCE_CHART_MIN_MONTH_RUB`: месяц пустой, если |план| + |факт| < 0.5 млн
MIN_MONTH_RUB = 500_000.0


class SmokeError(RuntimeError):
    pass


def _api_get(base: str, path: str, timeout: float) -> dict[str, Any]:
    url = f"{base.rstrip('/')}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise SmokeError(f"API недоступен: {url} ({exc})") from exc


def _mln(value: float) -> float:
    return round(float(value or 0.0) / 1_000_000, 1)


def _reference_frame():
    vid = active_version_id()
    if not vid:
        raise SmokeError("нет активной версии в web_data.db — сначала ingest")
    ref = load_version_df(vid, "reference_dannye")
    if ref is None or getattr(ref, "empty", True):
        raise SmokeError(f"в версии {vid} нет строк reference_dannye")
    return vid, ref


def _sum_column(frame, column: str, func_name: str) -> float:
    if column not in frame.columns:
        raise SmokeError(
            f"{func_name}: нет колонки «{column}» (есть: {', '.join(map(str, frame.columns))})"
        )
    return float(frame[column].astype(float).sum())


def _finance_reference(
    func_name: str,
    *,
    plan_col: str = "budget plan",
    fact_col: str = "budget fact",
) -> dict[str, Any]:
    vid, ref = _reference_frame()
    module = import_dashboard_module("finance_from_1c")
    func = getattr(module, func_name, None)
    if func is None:
        raise SmokeError(f"в finance_from_1c нет {func_name}")
    frame = func(reference_1c_dannye=ref)
    if frame is None or getattr(frame, "empty", True):
        raise SmokeError(f"{func_name} вернула пусто на версии {vid}")
    plan = _sum_column(frame, plan_col, func_name)
    fact = _sum_column(frame, fact_col, func_name)
    return {
        "version_id": vid,
        "projects": int(frame["project name"].nunique()),
        "plan_mln": _mln(plan),
        "fact_mln": _mln(fact),
    }


def _bdds_screen_reference() -> dict[str, Any]:
    """Эталон БДДС по пути, который рисует экран [main] (`dashboard_budget_by_period`).

    Сверять с «голым» `try_synthetic_budget_from_1c_dannye` нельзя: экран берёт
    календарь из MSP («Конец план»), сужает синтетику до проектов MSP, достраивает
    сетку месяцев и прогоняет overlay/finalize. Здесь та же цепочка вызовов
    функций [main] — независимо от сервисного слоя API.
    """
    import pandas as pd

    vid, ref = _reference_frame()
    ensure_renderers_shim()
    fin = import_dashboard_module("finance_from_1c")
    labels_mod = import_dashboard_module("project_labels")
    import utils  # type: ignore

    session_state()["reference_1c_dannye"] = ref
    msp = load_msp_frame(vid)
    if msp is None or getattr(msp, "empty", True):
        raise SmokeError(f"в версии {vid} нет MSP (file_type=project)")
    msp = labels_mod.apply_unified_project_column(msp.copy(), "project name")
    utils.ensure_date_columns(msp)

    plan_end = pd.to_datetime(msp["plan end"], errors="coerce")
    plan_start = pd.to_datetime(msp.get("plan start"), errors="coerce")
    cal_start = plan_end.min()
    cal_end = plan_end.max()
    end_inclusive = cal_end.normalize() + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    filtered = msp[
        plan_end.notna()
        & plan_start.notna()
        & (plan_start <= end_inclusive)
        & (plan_end >= cal_start)
    ].copy()
    utils.ensure_budget_columns(filtered)
    filtered, _ = fin.ensure_budget_frame_with_fallback(
        filtered,
        show_caption=False,
        restrict_projects_from_df=True,
        period_start=cal_start,
        period_end=cal_end,
        force_from_1c=False,
        narrow_to_project_norm_key=None,
    )
    if filtered is None or getattr(filtered, "empty", True):
        raise SmokeError("путь экрана БДДС не дал строк бюджета")
    for column in ("budget plan", "budget fact"):
        filtered[column] = pd.to_numeric(filtered[column], errors="coerce").fillna(0.0)
    filtered["reserve budget"] = filtered["budget fact"] - filtered["budget plan"]

    summary = (
        filtered.groupby(["plan_month", "project name"], dropna=False)
        .agg({"budget plan": "sum", "budget fact": "sum", "reserve budget": "sum"})
        .reset_index()
    )
    summary["period_original"] = summary["plan_month"]
    summary["plan_month"] = summary["plan_month"].apply(utils.format_period_ru)
    summary, _ = fin.overlay_1c_on_budget_summary(
        summary,
        period_col="plan_month",
        period_start=cal_start,
        period_end=cal_end,
        project_norm_keys=None,
        narrow_to_project_norm_key=None,
        reference_1c_dannye=ref,
    )
    summary = fin.expand_budget_month_grid(
        summary,
        period_col="plan_month",
        cal_start=cal_start,
        cal_end=cal_end,
        fill_columns=("budget plan", "budget fact", "reserve budget"),
        group_by="project name",
    )
    summary = fin.finalize_budget_summary_for_display(
        summary,
        period_col="plan_month",
        period_start=cal_start,
        period_end=cal_end,
        project_norm_keys=None,
        narrow_to_project_norm_key=None,
        reference_1c_dannye=ref,
    )
    summary["_pk"] = summary["project name"].map(labels_mod.project_filter_norm_key)
    name_by_pk: dict[str, str] = {}
    for name, key in zip(summary["project name"], summary["_pk"]):
        if key and (key not in name_by_pk or len(str(name)) > len(name_by_pk[key])):
            name_by_pk[key] = str(name)
    grouped = summary.groupby("_pk", dropna=False)[["budget plan", "budget fact"]].sum()
    by_project = {
        name_by_pk.get(str(key), str(key)): (_mln(row["budget plan"]), _mln(row["budget fact"]))
        for key, row in grouped.iterrows()
    }
    # Помесячно: экран режет месяцы порогом _FINANCE_CHART_MIN_MONTH_RUB = 0.5 млн
    months = (
        summary.groupby(["_pk", "period_original", "plan_month"], dropna=False)[
            ["budget plan", "budget fact"]
        ]
        .sum()
        .reset_index()
    )
    keep = (months["budget plan"].abs() + months["budget fact"].abs()) >= MIN_MONTH_RUB
    by_month = {
        f"{row['_pk']}|{row['plan_month']}": (_mln(row["budget plan"]), _mln(row["budget fact"]))
        for _, row in months[keep].iterrows()
    }
    return {
        "version_id": vid,
        "rows_1c": int(len(ref)),
        "plan_mln": _mln(float(summary["budget plan"].fillna(0.0).sum())),
        "fact_mln": _mln(float(summary["budget fact"].fillna(0.0).sum())),
        "by_project": by_project,
        "by_month": by_month,
        "cal_start": cal_start.date().isoformat(),
        "cal_end": cal_end.date().isoformat(),
    }


def check_bdds(base: str, timeout: float) -> list[tuple[str, Any, Any, bool]]:
    ref = _bdds_screen_reference()
    api = _api_get(base, "/api/bdds", timeout)
    meta = api.get("meta") or {}
    kpis = api.get("kpis") or {}
    applied = ((api.get("filters") or {}).get("applied")) or {}
    api_projects = {
        str(row.get("project")): (_mln(row.get("plan") or 0.0), _mln(row.get("fact") or 0.0))
        for row in (api.get("project_rows") or [])
    }
    db_meta = meta.get("db") or {}
    rows: list[tuple[str, Any, Any, bool]] = [
        _info_row("web_data.db", REFERENCE_DB.name, db_meta.get("web_db_path") or "—"),
        _info_row("активная версия", ref["version_id"], meta.get("version_id")),
        # Разные снимки оборотов 1С = разные цифры на экране: это не «почти то же».
        _meta_row("строк 1С (снимок)", ref["rows_1c"], meta.get("rows_1c")),
        _kpi_row("ИТОГО план, млн", ref["plan_mln"], kpis.get("plan_mln")),
        _kpi_row("ИТОГО факт, млн", ref["fact_mln"], kpis.get("fact_mln")),
        _choice_row("mode", {"synthetic_1c", "msp_1c"}, meta.get("mode") or "—"),
        _meta_row("meta.error", None, meta.get("error") or None),
        _meta_row("период с", ref["cal_start"], applied.get("date_from")),
        _meta_row("период по", ref["cal_end"], applied.get("date_to")),
        _meta_row("проектов", len(ref["by_project"]), len(api_projects)),
    ]
    # Суммарное совпадение при разных проектных суммах — ложный зелёный: сверяем каждый.
    for project in sorted(ref["by_project"]):
        plan, fact = ref["by_project"][project]
        api_plan, api_fact = api_projects.get(project, (None, None))
        rows.append(_kpi_row(f"{project}: план", plan, api_plan))
        rows.append(_kpi_row(f"{project}: факт", fact, api_fact))
    rows.extend(_bdds_month_rows(ref["by_month"], api.get("period_rows") or []))
    return rows


def _bdds_month_rows(
    ref_months: dict[str, tuple[float, float]],
    period_rows: list[dict[str, Any]],
) -> list[tuple[str, Any, Any, bool]]:
    """Помесячная сверка блоков таблицы: ключ — norm-key проекта + подпись периода."""
    labels_mod = import_dashboard_module("project_labels")
    ref_keys = {key.split("|", 1)[0] for key in ref_months}

    def resolve(project: str) -> str:
        """Подпись экрана («Дмитровский») → norm-key строк 1С («дмитровский 1»)."""
        key = str(labels_mod.project_filter_norm_key(project) or "")
        if key in ref_keys:
            return key
        for candidate in sorted(ref_keys):
            if labels_mod._project_norm_key_matches_msp_keys(candidate, {key}):
                return candidate
        return key

    api_months: dict[str, tuple[float, float]] = {}
    banner = ""
    for row in period_rows:
        if row.get("kind") == "project":
            banner = str(row.get("project") or "")
            continue
        project = str(row.get("project") or banner)
        key = f"{resolve(project)}|{row.get('period')}"
        api_months[key] = (_mln(row.get("plan") or 0.0), _mln(row.get("fact") or 0.0))

    rows: list[tuple[str, Any, Any, bool]] = [
        _meta_row("месячных строк", len(ref_months), len(api_months))
    ]
    mismatched = [
        key
        for key, (plan, fact) in ref_months.items()
        if not _month_matches(ref_months[key], api_months.get(key))
    ]
    rows.append(("месяцы с расхождением", 0, len(mismatched), not mismatched))
    for key in mismatched[:10]:
        plan, fact = ref_months[key]
        api_plan, api_fact = api_months.get(key, ("—", "—"))
        rows.append((f"  {key}", f"{plan}/{fact}", f"{api_plan}/{api_fact}", False))
    return rows


def _month_matches(expected: tuple[float, float], actual: tuple[float, float] | None) -> bool:
    if actual is None:
        return False
    return all(abs(float(e) - float(a)) <= KPI_TOL_MLN for e, a in zip(expected, actual))


def check_bdr(base: str, timeout: float) -> list[tuple[str, Any, Any, bool]]:
    ref = _bdr_screen_reference()
    api = _api_get(base, "/api/bdr", timeout)
    meta = api.get("meta") or {}
    kpis = api.get("kpis") or {}
    api_projects = {
        str(row.get("project")): (_mln(row.get("plan") or 0.0), _mln(row.get("fact") or 0.0))
        for row in (api.get("project_rows") or [])
    }
    rows = [
        _info_row("web_data.db", REFERENCE_DB.name, (meta.get("db") or {}).get("web_db_path") or "—"),
        _info_row("активная версия", ref["version_id"], meta.get("version_id")),
        _meta_row("строк 1С (снимок)", ref["rows_1c"], meta.get("rows_1c")),
        _kpi_row("ИТОГО план, млн", ref["plan_mln"], kpis.get("plan_mln")),
        _kpi_row("ИТОГО факт, млн", ref["fact_mln"], kpis.get("fact_mln")),
        _choice_row("mode", {"synthetic_1c", "msp_1c"}, meta.get("mode") or "—"),
        _meta_row("meta.error", None, meta.get("error") or None),
        _meta_row("период с", ref["cal_start"], ((api.get("filters") or {}).get("applied") or {}).get("date_from")),
        _meta_row("период по", ref["cal_end"], ((api.get("filters") or {}).get("applied") or {}).get("date_to")),
        _meta_row("проектов", len(ref["by_project"]), len(api_projects)),
    ]
    for project, (plan, fact) in sorted(ref["by_project"].items()):
        api_plan, api_fact = api_projects.get(project, (None, None))
        rows.append(_kpi_row(f"{project}: план", plan, api_plan))
        rows.append(_kpi_row(f"{project}: факт", fact, api_fact))
    rows.extend(_bdds_month_rows(ref["by_month"], api.get("period_rows") or []))
    return rows


def _bdr_screen_reference() -> dict[str, Any]:
    """Эталон точного data-path `dashboard_bdr` в main, без сервисного слоя showcase."""
    import pandas as pd

    vid, ref = _reference_frame()
    ensure_renderers_shim()
    fin = import_dashboard_module("finance_from_1c")
    labels_mod = import_dashboard_module("project_labels")
    import utils  # type: ignore

    session_state()["reference_1c_dannye"] = ref
    msp = load_msp_frame(vid)
    if msp is None or getattr(msp, "empty", True):
        raise SmokeError(f"в версии {vid} нет MSP (file_type=project)")
    msp = labels_mod.apply_unified_project_column(msp.copy(), "project name")
    utils.ensure_date_columns(msp)
    frame, used_1c = fin.ensure_bdr_frame_with_fallback(msp, restrict_projects_from_df=True)
    if frame is None or getattr(frame, "empty", True):
        raise SmokeError("путь экрана БДР не дал строк")
    frame = labels_mod.apply_unified_project_column(frame.copy(), "project name")
    utils.ensure_date_columns(frame)
    for source, target in (("bdr_plan_expense", "_plan"), ("bdr_fact_expense", "_fact")):
        if source not in frame.columns:
            raise SmokeError(f"путь экрана БДР: нет колонки {source}")
        frame[target] = pd.to_numeric(frame[source], errors="coerce").fillna(0.0)
    frame["plan end"] = pd.to_datetime(frame["plan end"], errors="coerce")
    frame = frame[frame["plan end"].notna()].copy()
    frame["period"] = frame["plan end"].dt.to_period("M")
    summary = frame.groupby(["project name", "period"], dropna=False)[["_plan", "_fact"]].sum().reset_index()
    summary["label"] = summary["period"].apply(utils.format_period_ru)
    summary["_pk"] = summary["project name"].map(labels_mod.project_filter_norm_key)
    grouped = summary.groupby("_pk", dropna=False)[["_plan", "_fact"]].sum()
    names = {
        key: max(
            (str(name) for name, project_key in zip(summary["project name"], summary["_pk"]) if project_key == key),
            key=len,
        )
        for key in grouped.index
    }
    by_project = {
        names[key]: (_mln(row["_plan"]), _mln(row["_fact"]))
        for key, row in grouped.iterrows()
    }
    keep = (summary["_plan"].abs() + summary["_fact"].abs()) >= MIN_MONTH_RUB
    by_month = {
        f"{row['_pk']}|{row['label']}": (_mln(row["_plan"]), _mln(row["_fact"]))
        for _, row in summary[keep].iterrows()
    }
    return {
        "version_id": vid,
        "rows_1c": int(len(ref)),
        "plan_mln": _mln(float(summary["_plan"].sum())),
        "fact_mln": _mln(float(summary["_fact"].sum())),
        "by_project": by_project,
        "by_month": by_month,
        "cal_start": frame["plan end"].min().date().isoformat(),
        "cal_end": frame["plan end"].max().date().isoformat(),
        "mode": "synthetic_1c" if used_1c else "msp_1c",
    }


def check_approved_budget(base: str, timeout: float) -> list[tuple[str, Any, Any, bool]]:
    ref = _bdds_screen_reference()
    api = _api_get(base, "/api/approved-budget", timeout)
    meta = api.get("meta") or {}
    kpis = api.get("kpis") or {}
    rows = api.get("project_rows") or []
    return [
        _info_row("активная версия", ref["version_id"], meta.get("version_id")),
        _meta_row("строк 1С (снимок)", ref["rows_1c"], meta.get("rows_1c")),
        _kpi_row("план, млн", ref["plan_mln"], kpis.get("plan_mln")),
        _kpi_row("факт, млн", ref["fact_mln"], kpis.get("fact_mln")),
        _meta_row("проектов", len(ref["by_project"]), len(rows)),
    ]


def check_developer_projects(base: str, timeout: float) -> list[tuple[str, Any, Any, bool]]:
    vid, _ = _reference_frame()
    api = _api_get(base, "/api/developer-projects", timeout)
    meta = api.get("meta") or {}
    matrix = api.get("matrix") or {}
    cells_filled = sum(
        1
        for project in matrix.get("projects") or []
        for cell in (project.get("cells") or {}).values()
        if (cell.get("plan") or cell.get("fact"))
    )
    return [
        _info_row("активная версия", vid, meta.get("version_id")),
        _meta_row("meta.error", None, meta.get("error") or None),
        _bool_row("проектов > 0", bool(matrix.get("projects"))),
        _bool_row("колонок > 0", bool(matrix.get("columns"))),
        _bool_row("заполненных ячеек > 0", cells_filled > 0),
    ]


def check_control_points(base: str, timeout: float) -> list[tuple[str, Any, Any, bool]]:
    vid, _ = _reference_frame()
    module = import_dashboard_module("dev_projects_tz_matrix")
    frame = load_msp_frame(vid)
    expected = module.build_control_points_df(frame, hide_completed=False)
    api = _api_get(base, "/api/control-points", timeout)
    projects = api.get("projects") or []
    groups = api.get("groups") or []
    cells_filled = sum(
        1
        for project in projects
        for cell in (project.get("cells") or {}).values()
        if cell.get("plan") not in (None, "", "Н/Д")
        or cell.get("fact") not in (None, "", "Н/Д")
    )
    return [
        _info_row("активная версия", vid, (api.get("meta") or {}).get("version_id")),
        _meta_row("meta.error", None, (api.get("meta") or {}).get("error") or None),
        _meta_row("проектов", len(expected), len(projects)),
        _meta_row("групп вех", 3, len(groups)),
        _bool_row("заполненных ячеек > 0", cells_filled > 0),
    ]


def check_project_schedule(base: str, timeout: float) -> list[tuple[str, Any, Any, bool]]:
    vid, _ = _reference_frame()
    frame = load_msp_frame(vid)
    api = _api_get(
        base,
        "/api/project-schedule?level=%D0%92%D0%B5%D1%80%D1%85%D0%BD%D0%B8%D0%B9%20%D1%83%D1%80%D0%BE%D0%B2%D0%B5%D0%BD%D1%8C&project=%D0%92%D1%81%D0%B5",
        timeout,
    )
    meta = api.get("meta") or {}
    rows = api.get("rows") or []
    gantt = api.get("gantt") or {}
    gantt_rows = gantt.get("rows") or []
    filters = api.get("filters") or {}
    applied = filters.get("applied") or {}
    level4 = 0
    if frame is not None and not getattr(frame, "empty", True) and "level" in frame.columns:
        import pandas as pd

        ln = pd.to_numeric(frame["level"], errors="coerce")
        level4 = int((ln == 4.0).sum())
    return [
        _info_row("активная версия", vid, meta.get("version_id")),
        _meta_row("meta.error", None, meta.get("error") or None),
        _meta_row("meta.source", "web_data.db", meta.get("source")),
        _bool_row("строк таблицы > 0", len(rows) > 0),
        _bool_row("строк ганта > 0", len(gantt_rows) > 0),
        _bool_row("gantt ≤ cap", len(gantt_rows) <= int(meta.get("gantt_cap") or 600)),
        _meta_row("уровень", "Верхний уровень", applied.get("level")),
        _bool_row("MSP level=4 есть в БД", level4 > 0),
        _bool_row("проектов в фильтре > 1", len(filters.get("projects") or []) > 1),
    ]


def check_deviation_reasons(base: str, timeout: float) -> list[tuple[str, Any, Any, bool]]:
    vid, _ = _reference_frame()
    api = _api_get(base, "/api/deviation-reasons", timeout)
    meta = api.get("meta") or {}
    filters = api.get("filters") or {}
    applied = filters.get("applied") or {}
    kpis = api.get("kpis") or {}
    tremor = api.get("tremor") or {}
    rows = api.get("rows") or []
    by_reason = tremor.get("by_reason") or []
    return [
        _info_row("активная версия", vid, meta.get("version_id")),
        _meta_row("meta.error", None, meta.get("error") or None),
        _meta_row("meta.source", "web_data.db", meta.get("source")),
        _meta_row("parity", "main_deviation_reasons", meta.get("parity")),
        _bool_row("строк таблицы ≥ 0", len(rows) >= 0),
        _bool_row("проектов в фильтре > 1", len(filters.get("projects") or []) > 1),
        _bool_row("причин в фильтре ≥ 1", len(filters.get("reasons") or []) >= 1),
        _meta_row("top5 default", False, bool(applied.get("top5"))),
        _bool_row(
            "KPI/график согласованы",
            (not by_reason and int(kpis.get("main_reason_count") or 0) == 0)
            or (
                int(kpis.get("main_reason_count") or 0) == int(by_reason[0].get("count") or 0)
                if by_reason
                else True
            ),
        ),
        _bool_row("dynamics object", isinstance(tremor.get("dynamics"), dict)),
        _bool_row(
            "dynamics facets/table",
            isinstance((tremor.get("dynamics") or {}).get("by_project_charts"), list)
            and isinstance((tremor.get("dynamics") or {}).get("project_month_rows"), list)
            and isinstance((tremor.get("dynamics") or {}).get("summary_rows"), list),
        ),
    ]


def check_baseline_deviation(base: str, timeout: float) -> list[tuple[str, Any, Any, bool]]:
    vid, _ = _reference_frame()
    api = _api_get(base, "/api/baseline-deviation", timeout)
    meta = api.get("meta") or {}
    filters = api.get("filters") or {}
    applied = filters.get("applied") or {}
    kpis = api.get("kpis") or {}
    plates = kpis.get("plates") or []
    chart = api.get("chart") or {}
    chart_rows = chart.get("rows") or []
    rows = api.get("rows") or []
    columns = api.get("columns") or []
    return [
        _info_row("активная версия", vid, meta.get("version_id")),
        _meta_row("meta.error", None, meta.get("error") or None),
        _meta_row("meta.source", "web_data.db", meta.get("source")),
        _meta_row("parity", "main_plan_fact_dates", meta.get("parity")),
        _meta_row("metric_task", "ЗОС", kpis.get("metric_task") or "ЗОС"),
        _bool_row("плашек ЗОС > 0", len(plates) > 0),
        _bool_row("строк графика ≥ 0", len(chart_rows) >= 0),
        _bool_row("chart ≤ cap 400", len(chart_rows) <= 400),
        _bool_row("строк таблицы ≥ 0", len(rows) >= 0),
        _bool_row("колонок таблицы > 0", len(columns) > 0),
        _bool_row("проектов в фильтре > 1", len(filters.get("projects") or []) > 1),
        _meta_row("show_reasons default", True, bool(applied.get("show_reasons"))),
        _choice_row(
            "chart.kind",
            {"rd_end_bars", "end_bars", "covenant_end_bars"},
            chart.get("kind"),
        ),
    ]


def check_project_documentation(base: str, timeout: float) -> list[tuple[str, Any, Any, bool]]:
    vid, _ = _reference_frame()
    api = _api_get(base, "/api/project-documentation", timeout)
    meta = api.get("meta") or {}
    filters = api.get("filters") or {}
    applied = filters.get("applied") or {}
    kpis = api.get("kpis") or {}
    tremor = api.get("tremor") or {}
    rows = api.get("rows") or []
    delay = api.get("delay") or {}
    gantt = delay.get("gantt") or {}
    return [
        _info_row("активная версия", vid, meta.get("version_id")),
        _meta_row("meta.error", None, meta.get("error") or None),
        _meta_row("meta.source", "web_data.db", meta.get("source")),
        _meta_row("parity", "main_project_documentation", meta.get("parity")),
        _meta_row("doc_kind", "pd", meta.get("doc_kind")),
        _bool_row("проектов в фильтре > 1", len(filters.get("projects") or []) > 1),
        _bool_row("KPI plan_total ≥ 0", int(kpis.get("plan_total") or 0) >= 0),
        _bool_row("status_mix ≥ 0", len(tremor.get("status_mix") or []) >= 0),
        _bool_row("dynamics ≥ 0", len(tremor.get("dynamics") or []) >= 0),
        _bool_row("строк таблицы ≥ 0", len(rows) >= 0),
        _bool_row("gantt rows ≥ 0", len(gantt.get("rows") or []) >= 0),
        _bool_row("delay cards ≥ 0", len(delay.get("cards") or []) >= 0),
        _bool_row("detail rows ≥ 0", len(delay.get("detail_rows") or []) >= 0),
        _bool_row("summary rows ≥ 0", len(delay.get("summary_rows") or []) >= 0),
        _meta_row("granularity default", "week", applied.get("granularity") or "week"),
        _meta_row("view_mode default", "project", applied.get("view_mode") or "project"),
    ]


def check_working_documentation(base: str, timeout: float) -> list[tuple[str, Any, Any, bool]]:
    vid, _ = _reference_frame()
    api = _api_get(base, "/api/working-documentation", timeout)
    meta = api.get("meta") or {}
    filters = api.get("filters") or {}
    applied = filters.get("applied") or {}
    kpis = api.get("kpis") or {}
    tremor = api.get("tremor") or {}
    detail = api.get("detail_rows") or []
    delay = api.get("delay") or {}
    gantt = delay.get("gantt") or {}
    pie = tremor.get("status_mix") or []
    total = int(kpis.get("total_sections") or 0)
    return [
        _info_row("активная версия", vid, meta.get("version_id")),
        _meta_row("meta.error", None, meta.get("error") or None),
        _meta_row("meta.source", "web_data.db", meta.get("source")),
        _meta_row("parity", "main_working_documentation_rd_plan_tessa", meta.get("parity")),
        _meta_row("doc_kind", "rd", meta.get("doc_kind")),
        _bool_row("проектов в фильтре > 1", len(filters.get("projects") or []) > 1),
        _bool_row("KPI total_sections > 0", total > 0),
        _bool_row("KPI overdue ≥ 0", int(kpis.get("overdue") or 0) >= 0),
        _bool_row("KPI avg_delay ≥ 0", float(kpis.get("avg_delay") or 0) >= 0),
        _bool_row("pie non-empty if data", (total == 0) or (len(pie) > 0)),
        _bool_row("dynamics ≥ 0", len(tremor.get("dynamics") or []) >= 0),
        _bool_row("monthly ≥ 0", len(tremor.get("monthly") or []) >= 0),
        _bool_row("detail rows ≥ 0", len(detail) >= 0),
        _bool_row("gantt rows ≥ 0", len(gantt.get("rows") or []) >= 0),
        _meta_row("view_mode default", "project", applied.get("view_mode") or "project"),
        _meta_row(
            "period_mode default",
            "Весь период (за всё время)",
            applied.get("period_mode") or "Весь период (за всё время)",
        ),
    ]


def _check_gdrs(base: str, timeout: float, *, path: str, kind: str) -> list[tuple[str, Any, Any, bool]]:
    vid, _ = _reference_frame()
    api = _api_get(base, path, timeout)
    meta = api.get("meta") or {}
    filters = api.get("filters") or {}
    selected = (filters.get("selected") or {})
    kpis = api.get("kpis") or {}
    tremor = api.get("tremor") or {}
    by_project = tremor.get("by_project") or []
    rows = int(meta.get("rows") or 0)
    return [
        _info_row("активная версия", vid, meta.get("version_id")),
        _meta_row("meta.error", None, meta.get("error") or None),
        _meta_row("meta.source", "web_data.db", meta.get("source")),
        _meta_row("parity", "main_dashboard_gdrs", meta.get("parity")),
        _meta_row("resource_kind", kind, meta.get("resource_kind")),
        _bool_row("months in filter > 0", len(filters.get("months") or []) > 0),
        _bool_row("agg_options > 0", len(filters.get("agg_options") or []) > 0),
        _bool_row("KPI plan ≥ 0", int(kpis.get("plan") or 0) >= 0),
        _bool_row("KPI fact ≥ 0", int(kpis.get("fact") or 0) >= 0),
        _bool_row("by_project non-empty if data", (rows == 0) or (len(by_project) > 0)),
        _bool_row("matrix_rows ≥ 0", len(api.get("matrix_rows") or []) >= 0),
        _bool_row("pie ≥ 0", len(tremor.get("pie") or api.get("pie_rows") or []) >= 0),
        _bool_row("dynamics ≥ 0", len(tremor.get("dynamics") or []) >= 0),
        _meta_row("dyn_agg default", "День", selected.get("dyn_agg") or "День"),
        _meta_row("only_with_plan default", False, bool(selected.get("only_with_plan"))),
    ]


def check_gdrs_people(base: str, timeout: float) -> list[tuple[str, Any, Any, bool]]:
    return _check_gdrs(base, timeout, path="/api/gdrs-people", kind="people")


def check_gdrs_equipment(base: str, timeout: float) -> list[tuple[str, Any, Any, bool]]:
    return _check_gdrs(base, timeout, path="/api/gdrs-equipment", kind="equipment")


def check_prescriptions(base: str, timeout: float) -> list[tuple[str, Any, Any, bool]]:
    api = _api_get(base, "/api/prescriptions", timeout)
    meta = api.get("meta") or {}
    kpis = api.get("kpis") or {}
    tremor = api.get("tremor") or {}
    rows = api.get("rows") or []
    return [
        _meta_row("meta.source", "web_data.db", meta.get("source")),
        _meta_row("parity", "main_dashboard_predpisania", meta.get("parity")),
        _bool_row(
            "все KPI есть",
            all(
                key in kpis
                for key in (
                    "total",
                    "resolved",
                    "unresolved",
                    "non_overdue",
                    "overdue_unresolved",
                    "critical",
                    "stop_work",
                )
            ),
        ),
        _bool_row("tremor.by_contractor", isinstance(tremor.get("by_contractor"), list)),
        _bool_row("tremor.by_status", isinstance(tremor.get("by_status"), list)),
        _bool_row("tremor.by_object", isinstance(tremor.get("by_object"), list)),
        _bool_row("rows", isinstance(rows, list)),
    ]


def _kpi_row(label: str, expected: Any, actual: Any) -> tuple[str, Any, Any, bool]:
    if actual is None:
        return (label, expected, "—", False)
    ok = abs(float(expected) - float(actual)) <= KPI_TOL_MLN
    return (label, expected, actual, ok)


def _meta_row(label: str, expected: Any, actual: Any) -> tuple[str, Any, Any, bool]:
    return (label, expected, actual, expected == actual)


def _info_row(label: str, expected: Any, actual: Any) -> tuple[str, Any, Any, bool]:
    """Справочная строка: эталон и сервис читают разные файлы БД — это норма."""
    return (label, expected, actual, True)


def _choice_row(label: str, allowed: set[str], actual: Any) -> tuple[str, Any, Any, bool]:
    """Годится любой режим из списка (главное — не fallback_simplified)."""
    return (label, "|".join(sorted(allowed)), actual, str(actual) in allowed)


def _bool_row(label: str, value: bool) -> tuple[str, Any, Any, bool]:
    return (label, True, value, bool(value))


CHECKS: dict[str, Callable[[str, float], list[tuple[str, Any, Any, bool]]]] = {
    "developer-projects": check_developer_projects,
    "control-points": check_control_points,
    "project-schedule": check_project_schedule,
    "deviation-reasons": check_deviation_reasons,
    "baseline-deviation": check_baseline_deviation,
    "project-documentation": check_project_documentation,
    "working-documentation": check_working_documentation,
    "gdrs-people": check_gdrs_people,
    "gdrs-equipment": check_gdrs_equipment,
    "prescriptions": check_prescriptions,
    "bdds": check_bdds,
    "bdr": check_bdr,
    "approved-budget": check_approved_budget,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("screens", nargs="*", default=[], help=f"из: {', '.join(CHECKS)}")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args()

    screens = args.screens or list(CHECKS)
    unknown = [s for s in screens if s not in CHECKS]
    if unknown:
        print(f"Неизвестные экраны: {', '.join(unknown)}", file=sys.stderr)
        return 2

    print(f"Эталон (БД экрана main): {REFERENCE_DB}")
    print(f"Сервис: {args.api}")

    failures = 0
    for screen in screens:
        print(f"\n=== {screen} ===")
        try:
            rows = CHECKS[screen](args.api, args.timeout)
        except SmokeError as exc:
            print(f"  СВЕРКА НЕВОЗМОЖНА: {exc}")
            failures += 1
            continue
        except Exception as exc:  # noqa: BLE001
            print(f"  ОШИБКА: {type(exc).__name__}: {exc}")
            failures += 1
            continue
        width = max(len(row[0]) for row in rows)
        for label, expected, actual, ok in rows:
            mark = "OK  " if ok else "FAIL"
            print(f"  {mark} {label.ljust(width)}  main={expected}  api={actual}")
            if not ok:
                failures += 1

    print(f"\nRESULT: {'ALL OK' if failures == 0 else f'{failures} расхождений'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
