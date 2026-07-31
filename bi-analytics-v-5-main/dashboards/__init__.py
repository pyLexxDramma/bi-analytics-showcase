"""
Регистр дашбордов: имя отчёта -> функция отрисовки.
Функции отрисовки импортируются из dashboards._renderers.
"""
from typing import Callable, Dict, List, Tuple

from dashboards.export_wrap import run_dashboard_with_auto_export, slug_report_name

# Категории для трёх блоков радиокнопок на главной странице (не путать с порядком REPORT_CATEGORIES).
MAIN_PANEL_TIMELINE_CATEGORY = "Сроки"
MAIN_PANEL_FINANCE_CATEGORY = "Финансы"


def get_report_categories() -> List[Tuple[str, List[str]]]:
    """Категории отчётов для меню (одна вкладка на экран, светлая тема)."""
    from dashboards.light_theme import filter_reports_hide_light_preview

    out: List[Tuple[str, List[str]]] = []
    for title, reports in REPORT_CATEGORIES:
        filtered = filter_reports_hide_light_preview(list(reports))
        if filtered:
            out.append((title, filtered))
    return out


def get_main_panel_report_lists(role: str) -> Tuple[List[str], List[str], List[str]]:
    """
    Возвращает (отчёты «Сроки», отчёты «Финансы», все остальные отчёты) с учётом RBAC.
    Единый источник — REPORT_CATEGORIES; не зависит от порядка категорий в списке.
    """
    from auth import filter_reports_for_role

    timeline: List[str] = []
    finance: List[str] = []
    for title, reps in get_report_categories():
        if title == MAIN_PANEL_TIMELINE_CATEGORY:
            timeline = list(reps)
        elif title == MAIN_PANEL_FINANCE_CATEGORY:
            finance = list(reps)
    all_flat: List[str] = []
    for _, reps in get_report_categories():
        all_flat.extend(list(reps))
    other = [r for r in all_flat if r not in timeline and r not in finance]
    return (
        filter_reports_for_role(role, timeline),
        filter_reports_for_role(role, finance),
        filter_reports_for_role(role, other),
    )


REPORT_CATEGORIES: List[Tuple[str, List[str]]] = [
    ("Девелоперские проекты", [
        "Девелоперские проекты",
    ]),
    (
        "Финансы",
        [
            "БДДС (расходы)",
            "БДР (расходы)",
            "Утверждённый бюджет план/факт",
            "БДДС расходы (план, факт, уточненный план)",
        ],
    ),
    (
        "Сроки",
        [
            "Контрольные точки",
            "График проекта",
            "Причины отклонений",
            "Отклонение от базового плана",
        ],
    ),
    (
        "Проектные работы",
        [
            "Проектная документация",
            "Рабочая документация",
        ],
    ),
    (
        "ГДРС",
        [
            "ГДРС (люди)",
            "ГДРС (техника)",
        ],
    ),
    (
        "Предписания",
        [
            "Предписания по подрядчикам",
        ],
    ),
    (
        "Исполнительная документация",
        [
            "Исполнительная документация",
        ],
    ),
    (
        "Дебиторская и кредиторская задолженность",
        [
            "Дебиторская и кредиторская задолженность подрядчиков",
        ],
    ),
]


def _get_dashboards() -> Dict[str, Callable]:
    """Строит словарь имя_отчёта -> render(df). Импорт из dashboards._renderers."""
    import os
    import sys
    import streamlit as st
    # Родительская папка (bi-analytics) должна быть в sys.path для config, utils и т.д.
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    _parent = os.path.dirname(_this_dir)
    if _parent and _parent not in sys.path:
        sys.path.insert(0, _parent)
    try:
        from dashboards import _renderers
    except Exception as e:
        import traceback
        _tb = traceback.format_exc()
        # Печатаем причину в stderr, чтобы она не терялась при обрезке логов
        import sys
        print(f"[dashboards] Ошибка загрузки _renderers: {e!r}", file=sys.stderr)
        print(_tb, file=sys.stderr)
        raise RuntimeError(
            f"Ошибка при загрузке дашбордов (dashboards._renderers): {e!r}. "
            f"Проверьте: 1) наличие config.py и utils.py в корне проекта; "
            f"2) что проект запускается из корня bi-analytics (или он в sys.path). "
            f"Полный traceback:\n{_tb}"
        ) from e

    dashboard_deviations_combined = _renderers.dashboard_deviations_combined
    dashboard_plan_fact_dates = _renderers.dashboard_plan_fact_dates
    dashboard_deviation_by_tasks_current_month = _renderers.dashboard_deviation_by_tasks_current_month
    dashboard_dynamics_of_reasons = _renderers.dashboard_dynamics_of_reasons
    dashboard_budget_by_period = _renderers.dashboard_budget_by_period
    dashboard_budget_by_section = _renderers.dashboard_budget_by_section
    dashboard_bdr = getattr(_renderers, "dashboard_bdr", None)
    if dashboard_bdr is None:

        def _stub_bdr(df):
            st.error(
                "Дашборд БДР не найден в dashboards/_renderers.py. "
                "Убедитесь, что функция dashboard_bdr определена в файле."
            )

        dashboard_bdr = _stub_bdr
    dashboard_budget_by_type = _renderers.dashboard_budget_by_type
    dashboard_approved_budget = _renderers.dashboard_approved_budget
    dashboard_forecast_budget = _renderers.dashboard_forecast_budget
    dashboard_rd_delay = _renderers.dashboard_rd_delay
    dashboard_documentation = _renderers.dashboard_documentation
    dashboard_working_documentation = getattr(
        _renderers, "dashboard_working_documentation", dashboard_documentation
    )
    dashboard_project_documentation = getattr(
        _renderers, "dashboard_project_documentation", dashboard_documentation
    )
    dashboard_technique = _renderers.dashboard_technique
    dashboard_technique_tabs = getattr(_renderers, "dashboard_technique_tabs", None)
    if dashboard_technique_tabs is None:
        dashboard_technique_tabs = _renderers.dashboard_technique
    dashboard_workforce_movement = _renderers.dashboard_workforce_movement
    # R23-05 стр.14: восстановленный отчёт «Техника» (legacy, оставлен для совместимости).
    dashboard_gdrs_equipment = getattr(_renderers, "dashboard_gdrs_equipment", None)
    if dashboard_gdrs_equipment is None:
        dashboard_gdrs_equipment = dashboard_technique_tabs
    # ТЗ заказчика 2026-05-07: новые дашборды ГДРС — люди и техника как отдельные пункты меню
    # (см. docs/TZ_GDRS_2026-05-07.md). Общая реализация в dashboards/_renderers.dashboard_gdrs;
    # обёртки dashboard_gdrs_people / dashboard_gdrs_equipment_v2 фиксируют параметр vid.
    dashboard_gdrs = getattr(_renderers, "dashboard_gdrs", None)
    dashboard_gdrs_people = getattr(_renderers, "dashboard_gdrs_people", None)
    dashboard_gdrs_equipment_v2 = getattr(_renderers, "dashboard_gdrs_equipment_v2", None)
    dashboard_gdrs_people_preview_light = getattr(_renderers, "dashboard_gdrs_people_preview_light", None)
    dashboard_gdrs_equipment_preview_light = getattr(_renderers, "dashboard_gdrs_equipment_preview_light", None)
    if dashboard_gdrs_people is None and dashboard_gdrs is not None:
        dashboard_gdrs_people = lambda df: dashboard_gdrs(df)  # noqa: E731
    if dashboard_gdrs_equipment_v2 is None and dashboard_gdrs is not None:
        dashboard_gdrs_equipment_v2 = lambda df: dashboard_gdrs(df)  # noqa: E731
    if dashboard_gdrs is None:
        dashboard_gdrs = dashboard_technique_tabs
    if dashboard_gdrs_people is None:
        dashboard_gdrs_people = dashboard_technique_tabs
    if dashboard_gdrs_equipment_v2 is None:
        dashboard_gdrs_equipment_v2 = dashboard_gdrs_equipment
    if dashboard_gdrs_people_preview_light is None and dashboard_gdrs is not None:
        dashboard_gdrs_people_preview_light = lambda df: dashboard_gdrs(df, vid_locked="Рабочие", theme="light")  # noqa: E731
    if dashboard_gdrs_equipment_preview_light is None and dashboard_gdrs is not None:
        dashboard_gdrs_equipment_preview_light = lambda df: dashboard_gdrs(df, vid_locked="Техника", theme="light")  # noqa: E731
    dashboard_executive_documentation = getattr(_renderers, "dashboard_executive_documentation", None)
    if dashboard_executive_documentation is None:

        def _stub_executive(df):
            st.info("Раздел в разработке.")

        dashboard_executive_documentation = _stub_executive
    dashboard_debit_credit = getattr(_renderers, "dashboard_debit_credit", None)
    if dashboard_debit_credit is None:

        def _stub_debit(df):
            st.info("Загрузите файл с данными по задолженности подрядчиков.")

        dashboard_debit_credit = _stub_debit

    dashboard_predpisania = _renderers.dashboard_predpisania
    dashboard_developer_projects = _renderers.dashboard_developer_projects
    dashboard_developer_projects_preview_light = getattr(
        _renderers, "dashboard_developer_projects_preview_light", None
    )
    if dashboard_developer_projects_preview_light is None and dashboard_developer_projects is not None:
        dashboard_developer_projects_preview_light = lambda df: dashboard_developer_projects(  # noqa: E731
            df, theme="light"
        )
    dashboard_control_points = getattr(_renderers, "dashboard_control_points", None)
    dashboard_project_schedule_chart = getattr(_renderers, "dashboard_project_schedule_chart", None)
    dashboard_pravki_report_hidden = getattr(_renderers, "dashboard_pravki_report_hidden", None)
    dashboard_pd_delay = getattr(_renderers, "dashboard_pd_delay", None)

    if dashboard_control_points is None:

        def _stub_cp(df):
            st.info("Модуль в разработке (правки 04.2026).")

        dashboard_control_points = _stub_cp

    if dashboard_project_schedule_chart is None:

        def _stub_psc(df):
            st.info("Модуль в разработке (правки 04.2026).")

        dashboard_project_schedule_chart = _stub_psc

    if dashboard_pravki_report_hidden is None:

        def _stub_hidden(df):
            st.info("Отчёт скрыт по правкам заказчика.")

        dashboard_pravki_report_hidden = _stub_hidden

    if dashboard_pd_delay is None:
        dashboard_pd_delay = dashboard_rd_delay

    raw: Dict[str, Callable] = {
        # Сроки: каноническое имя «Причины отклонений» + обратная совместимость
        "Причины отклонений": dashboard_deviations_combined,
        "Причины отклонений (превью — светлая)": dashboard_deviations_combined,
        "Динамика отклонений": dashboard_deviations_combined,
        "Динамика причин отклонений": dashboard_deviations_combined,
        "Контрольные точки": dashboard_control_points,
        "Контрольные точки (превью — светлая)": dashboard_control_points,
        "График проекта": dashboard_project_schedule_chart,
        "График проекта (превью — светлая)": dashboard_project_schedule_chart,
        "БДДС (расходы)": dashboard_budget_by_period,
        "БДДС (расходы) (превью — светлая)": dashboard_budget_by_period,
        "БДДС": dashboard_budget_by_period,
        "БДДС (превью — светлая)": dashboard_budget_by_period,
        "БДДС по месяцам": dashboard_budget_by_period,
        "БДР (расходы)": dashboard_bdr,
        "БДР (расходы) (превью — светлая)": dashboard_bdr,
        "БДР": dashboard_bdr,
        "БДР (превью — светлая)": dashboard_bdr,
        "Бюджет по лотам": dashboard_budget_by_period,
        # «Утверждённый бюджет план/факт» — каноническое имя по ТЗ заказчика (2026-05-07).
        # Старые имена «Бюджет план/факт» / «Бюджет План/Прогноз/Факт» оставлены как алиасы,
        # чтобы не сломать сохранённые deep-link'и/закладки/настройки.
        "Утверждённый бюджет план/факт": dashboard_budget_by_type,
        "Утверждённый бюджет план/факт (превью — светлая)": dashboard_budget_by_type,
        "Бюджет план/факт": dashboard_budget_by_type,
        "Бюджет План/Прогноз/Факт": dashboard_budget_by_type,
        # Правки куратора 08.05.2026: вкладка «Утверждённый бюджет» удалена,
        # её графики (план/факт по месяцам + сводная таблица) перенесены в
        # «Утверждённый бюджет план/факт». Алиасы оставлены, чтобы не ломать
        # сохранённые ссылки/закладки/настройки пользователей.
        "Утвержденный бюджет": dashboard_budget_by_type,
        "Бюджет по проекту": dashboard_budget_by_type,
        "БДДС (утверждённый/прогнозный)": dashboard_forecast_budget,
        "Прогнозный БДДС": dashboard_forecast_budget,
        "БДДС расходы (план, факт, уточненный план)": dashboard_forecast_budget,
        "БДДС расходы (план, факт, уточненный план) (превью — светлая)": dashboard_forecast_budget,
        "Прогнозный бюджет": dashboard_forecast_budget,
        "Прогнозный бюджет (превью — светлая)": dashboard_forecast_budget,
        "Отклонение от базового плана": dashboard_plan_fact_dates,
        "Отклонение от базового плана (превью — светлая)": dashboard_plan_fact_dates,
        "Значения отклонений от базового плана": dashboard_pravki_report_hidden,
        "Рабочая/Проектная документация": dashboard_documentation,
        "Рабочая документация": dashboard_working_documentation,
        "Рабочая документация (превью — светлая)": dashboard_working_documentation,
        "Проектная документация": dashboard_project_documentation,
        "Проектная документация (превью — светлая)": dashboard_project_documentation,
        # ГДРС: общий экран (выбор люди/техника) + отдельные пункты «(люди)» / «(техника)».
        "ГДРС": dashboard_gdrs,
        "ГДРС (люди)": dashboard_gdrs_people_preview_light or dashboard_gdrs_people,
        "ГДРС (техника)": dashboard_gdrs_equipment_preview_light or dashboard_gdrs_equipment_v2,
        "ГДРС (превью — светлая, люди)": dashboard_gdrs_people_preview_light,
        "ГДРС (превью — светлая, техника)": dashboard_gdrs_equipment_preview_light,
        # Алиасы (старые deep-link/настройки).
        "График движения рабочей силы (люди)": dashboard_gdrs_people,
        "График движения рабочей силы (техника)": dashboard_gdrs_equipment_v2,
        "График движения рабочей силы": dashboard_gdrs,
        "ГДРС Техника": dashboard_gdrs_equipment_v2,
        # Legacy: старый пункт «Проектные работы» (техника) — не в меню, только для сохранённых ссылок.
        "Проектные работы": dashboard_technique,
        "Дебиторская и кредиторская задолженность": dashboard_debit_credit,
        "Дебиторская и кредиторская задолженность подрядчиков": dashboard_debit_credit,
        "Дебиторская и кредиторская задолженность подрядчиков (превью — светлая)": dashboard_debit_credit,
        "Исполнительная документация": dashboard_executive_documentation,
        "Исполнительная документация (превью — светлая)": dashboard_executive_documentation,
        "Просрочка выдачи РД": dashboard_rd_delay,
        "Просрочка выдачи ПД": dashboard_pd_delay,
        "Неустраненные предписания": dashboard_predpisania,
        # Обратная совместимость со старым именем отчёта.
        "Предписания по подрядчикам": dashboard_predpisania,
        "Предписания по подрядчикам (превью — светлая)": dashboard_predpisania,
        "Девелоперские проекты": dashboard_developer_projects_preview_light or dashboard_developer_projects,
        "Девелоперские проекты (превью — светлая)": dashboard_developer_projects_preview_light,
    }
    return raw


# Ленивая загрузка, чтобы при импорте dashboards не тянуть project_visualization_app
# Увеличьте версию при изменении реестра отчётов — иначе долгоживущий процесс Streamlit
# может держать устаревший словарь в памяти.
_DASHBOARDS_REGISTRY_VERSION = 110
_dashboards_cache: Dict[str, Callable] = {}
_dashboards_cache_version: int = 0
_renderers_mtime: float = 0.0


def _dev_hot_reload_enabled() -> bool:
    """Dev-only: подхватывать правки _renderers/gantt без рестарта процесса.

    В проде выключено — иначе на каждый rerun (при малейшем сдвиге mtime, напр.
    при деплое/checkout) выполняется ``importlib.reload`` модуля _renderers на
    ~47k строк, что даёт заметную задержку прогрузки дашбордов. Включается
    переменной окружения ``BI_ANALYTICS_DEV_RELOAD=1``.
    """
    import os

    return str(os.environ.get("BI_ANALYTICS_DEV_RELOAD", "")).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _reload_renderer_dependencies() -> None:
    """Hot-reload модулей, от которых зависит _renderers (только dev, см. _dev_hot_reload_enabled).

    ``importlib.reload(_renderers)`` перечитывает только сам _renderers; функции
    внутри него делают ленивый ``from dashboards.gantt_grouped_figure import ...``,
    поэтому без явной перезагрузки этих модулей в памяти остаётся старый код
    (например, построение полос Ганта), и правки не видны без рестарта процесса.
    """
    import importlib
    import sys

    for _mod_name in ("dashboards.gantt_grouped_figure",):
        _mod = sys.modules.get(_mod_name)
        if _mod is not None:
            try:
                importlib.reload(_mod)
            except Exception:
                pass


def get_dashboards() -> Dict[str, Callable]:
    """Возвращает словарь DASHBOARDS (кэшируется)."""
    global _dashboards_cache, _dashboards_cache_version, _renderers_mtime
    import importlib
    import os

    from dashboards import _renderers

    _path = getattr(_renderers, "__file__", None)
    _mt = float(os.path.getmtime(_path)) if _path else 0.0
    _stale = (
        not _dashboards_cache
        or _dashboards_cache_version != _DASHBOARDS_REGISTRY_VERSION
    )
    if _stale:
        # Первичное построение: _renderers уже импортирован выше — повторный
        # importlib.reload здесь только тратит время (перечитывание ~47k строк).
        _renderers_mtime = _mt
        _dashboards_cache = _get_dashboards()
        _dashboards_cache_version = _DASHBOARDS_REGISTRY_VERSION
    elif _dev_hot_reload_enabled():
        # Dev: подхватываем правки _renderers.py без ручного рестарта.
        try:
            _mt_live = float(os.path.getmtime(_path)) if _path else 0.0
        except OSError:
            _mt_live = _renderers_mtime
        if _mt_live > _renderers_mtime:
            _reload_renderer_dependencies()
            importlib.reload(_renderers)
            _renderers_mtime = _mt_live
            _dashboards_cache = _get_dashboards()
    return _dashboards_cache


def get_dashboard_renderer(name: str) -> Callable:
    """Возвращает функцию отрисовки по имени отчёта или None."""
    return get_dashboards().get(name)


def get_all_report_names() -> List[str]:
    """Возвращает плоский список всех имён отчётов (для report_params, filters и т.д.)."""
    return [r for _, reports in get_report_categories() for r in reports]



