"""Сверка API showcase с эталоном [main] на одной и той же web_data.db.

Эталон не хардкодится: считается прямо здесь вызовом функций main
(`dashboards/finance_from_1c.py`, `dashboards/dev_projects_tz_matrix.py`)
по активной версии БД. Числа из чатов устаревают после каждого ingest.

Запуск:
    python webapp/scripts/parity_smoke.py                     # все поддержанные экраны
    python webapp/scripts/parity_smoke.py bdds bdr            # выборочно
    python webapp/scripts/parity_smoke.py --api http://127.0.0.1:8000

Exit code: 0 — расхождений нет, 1 — есть, 2 — сверку не удалось выполнить.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

API_DIR = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(API_DIR))

from app.services.core_bridge import (  # noqa: E402
    active_version_id,
    import_dashboard_module,
    load_version_df,
)

# KPI сравниваем в млн (округление main/API до 0.1), таблицы — относительно.
KPI_TOL_MLN = 0.1
ROW_TOL_REL = 0.01


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


def check_bdds(base: str, timeout: float) -> list[tuple[str, Any, Any, bool]]:
    ref = _finance_reference("try_synthetic_budget_from_1c_dannye")
    api = _api_get(base, "/api/bdds", timeout)
    kpis = api.get("kpis") or {}
    return [
        _kpi_row("план, млн", ref["plan_mln"], kpis.get("plan_mln")),
        _kpi_row("факт, млн", ref["fact_mln"], kpis.get("fact_mln")),
        _meta_row("version_id", ref["version_id"], (api.get("meta") or {}).get("version_id")),
        _meta_row("mode", "msp_1c|synthetic", (api.get("meta") or {}).get("mode") or "—"),
    ]


def check_bdr(base: str, timeout: float) -> list[tuple[str, Any, Any, bool]]:
    # БДР возвращает помесячные строки с собственными колонками расходов
    ref = _finance_reference(
        "try_synthetic_bdr_from_1c_dannye",
        plan_col="bdr_plan_expense",
        fact_col="bdr_fact_expense",
    )
    api = _api_get(base, "/api/bdr", timeout)
    kpis = api.get("kpis") or {}
    return [
        _kpi_row("план, млн", ref["plan_mln"], kpis.get("plan_mln")),
        _kpi_row("факт, млн", ref["fact_mln"], kpis.get("fact_mln")),
        _meta_row("version_id", ref["version_id"], (api.get("meta") or {}).get("version_id")),
    ]


def check_approved_budget(base: str, timeout: float) -> list[tuple[str, Any, Any, bool]]:
    ref = _finance_reference("try_approved_budget_from_1c_dannye")
    api = _api_get(base, "/api/approved-budget", timeout)
    kpis = api.get("kpis") or {}
    rows = api.get("project_rows") or []
    return [
        _kpi_row("план, млн", ref["plan_mln"], kpis.get("plan_mln")),
        _kpi_row("факт, млн", ref["fact_mln"], kpis.get("fact_mln")),
        _meta_row("проектов", ref["projects"], len(rows)),
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
        _meta_row("version_id", vid, meta.get("version_id")),
        _meta_row("meta.error", None, meta.get("error") or None),
        _bool_row("проектов > 0", bool(matrix.get("projects"))),
        _bool_row("колонок > 0", bool(matrix.get("columns"))),
        _bool_row("заполненных ячеек > 0", cells_filled > 0),
    ]


def _kpi_row(label: str, expected: Any, actual: Any) -> tuple[str, Any, Any, bool]:
    if actual is None:
        return (label, expected, "—", False)
    ok = abs(float(expected) - float(actual)) <= KPI_TOL_MLN
    return (label, expected, actual, ok)


def _meta_row(label: str, expected: Any, actual: Any) -> tuple[str, Any, Any, bool]:
    return (label, expected, actual, expected == actual)


def _bool_row(label: str, value: bool) -> tuple[str, Any, Any, bool]:
    return (label, True, value, bool(value))


CHECKS: dict[str, Callable[[str, float], list[tuple[str, Any, Any, bool]]]] = {
    "developer-projects": check_developer_projects,
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
