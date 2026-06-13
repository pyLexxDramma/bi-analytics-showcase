"""
Production UI: скрытие «серых» служебных подписей Streamlit (`st.caption`) в дашбордах;
единый блок фильтров (popover, сетка фиксированной ширины, чипы активных значений).

См. `mapping_spec_v2` — раздел про отсутствие дебаг/сервисных подсказок в UI.
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
from datetime import date, datetime
from html import escape as html_escape
from typing import Any, Generator, List, Optional, Sequence, Tuple

Chip = Tuple[str, str]


def suppress_caption(*_args, **_kwargs) -> None:
    """No-op вместо `st.caption` — не рендерить мелкий серый текст под виджетами."""
    return None


# --- Единый блок фильтров ---------------------------------------------------------

_SESSION_CSS_FLAG_KEY = "_bi_unified_filters_css_v6"
_DEFAULT_FIELD_MIN_PX = 260

UNIFIED_FILTERS_CSS = """
<style>
[data-testid="stMain"] .bi-filters-scope {
    --bi-filter-rhythm: 16px;
}
/* Popover: равные колонки с ограничением ширины поля */
[data-testid="stMain"] [data-testid="stPopoverBody"] div[data-testid="stHorizontalBlock"] > div[data-testid="column"],
[data-testid="stMain"] div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stHorizontalBlock"] > div[data-testid="column"],
[data-testid="stMain"] .bi-filters-scope div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
    flex: 1 1 0% !important;
    min-width: """ + str(_DEFAULT_FIELD_MIN_PX) + """px !important;
    max-width: 320px !important;
}
/* Expander «Фilters»: строка селекторов — равные колонки и одинаковый gap */
[data-testid="stMain"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(5):last-child),
[data-testid="stMainBlockContainer"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(5):last-child),
[data-testid="stMain"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(6):last-child),
[data-testid="stMainBlockContainer"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(6):last-child) {
    display: flex !important;
    flex-wrap: nowrap !important;
    gap: 12px !important;
    column-gap: 12px !important;
    width: 100% !important;
}
[data-testid="stMain"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(5):last-child) > div[data-testid="column"],
[data-testid="stMainBlockContainer"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(5):last-child) > div[data-testid="column"],
[data-testid="stMain"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(6):last-child) > div[data-testid="column"],
[data-testid="stMainBlockContainer"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(6):last-child) > div[data-testid="column"] {
    flex: 1 1 0% !important;
    min-width: 0 !important;
    max-width: none !important;
    width: 0 !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
}
[data-testid="stMain"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(5):last-child) [data-testid="stSelectbox"],
[data-testid="stMain"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(5):last-child) [data-testid="stMultiSelect"],
[data-testid="stMainBlockContainer"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(5):last-child) [data-testid="stSelectbox"],
[data-testid="stMainBlockContainer"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(5):last-child) [data-testid="stMultiSelect"],
[data-testid="stMain"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(6):last-child) [data-testid="stSelectbox"],
[data-testid="stMain"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(6):last-child) [data-testid="stMultiSelect"],
[data-testid="stMainBlockContainer"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(6):last-child) [data-testid="stSelectbox"],
[data-testid="stMainBlockContainer"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(6):last-child) [data-testid="stMultiSelect"] {
    max-width: none !important;
    width: 100% !important;
}
[data-testid="stMain"] [data-testid="stPopoverBody"] [data-testid="stVerticalBlock"] > label,
[data-testid="stMain"] .bi-filters-scope [data-testid="stVerticalBlock"] > label {
    font-size: 13px !important;
    font-weight: 600 !important;
}
.bi-filter-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 8px;
    align-items: center;
    min-height: 2rem;
    padding: 2px 0 4px 0;
}
.bi-filter-chip {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 600;
    line-height: 1.35;
    color: #e8eef5;
    background: rgba(30, 58, 92, 0.95);
    border: 1px solid rgba(121, 154, 192, 0.45);
    white-space: nowrap;
}
.bi-filter-chip b {
    color: #86efac;
    font-weight: 700;
}
.bi-filters-section-title {
    font-size: 12px;
    font-weight: 700;
    color: #86efac;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin: 8px 0 6px 0;
}

.bi-filters-selectors {
    margin: 0 0 var(--bi-filter-rhythm, 14px) 0;
}
.bi-filters-selectors div[data-testid="column"] [data-testid="stSelectbox"],
.bi-filters-selectors div[data-testid="column"] [data-testid="stMultiSelect"],
.bi-filters-selectors div[data-testid="column"] [data-testid="stDateInput"] {
    width: 100%;
}
.bi-filters-selectors div[data-testid="column"] [data-testid="stRadio"] {
    width: 100%;
}
.bi-filters-selectors div[data-testid="stHorizontalBlock"] {
    display: flex !important;
    flex-wrap: nowrap !important;
    gap: 12px !important;
    column-gap: 12px !important;
    width: 100% !important;
}
.bi-filters-selectors div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
    flex: 1 1 0% !important;
    min-width: 0 !important;
    max-width: none !important;
    width: 0 !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
}
.bi-filters-selectors div[data-testid="column"] [data-testid="stSelectbox"],
.bi-filters-selectors div[data-testid="column"] [data-testid="stMultiSelect"],
.bi-filters-selectors div[data-testid="column"] [data-testid="stDateInput"] {
    max-width: none !important;
    width: 100% !important;
}
.bi-filters-toggles div[data-testid="stHorizontalBlock"] {
    display: flex !important;
    flex-wrap: nowrap !important;
    gap: 12px !important;
    column-gap: 12px !important;
    width: 100% !important;
}
.bi-filters-toggles div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
    flex: 1 1 0% !important;
    min-width: 0 !important;
    max-width: none !important;
    width: 0 !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
}

.bi-filters-toggles {
    margin: var(--bi-filter-rhythm, 14px) 0 0;
    padding: var(--bi-filter-rhythm, 14px) 0 0;
    border-top: 1px solid rgba(148,163,184,.18);
}
.bi-filters-toggles [data-testid="stCheckbox"] {
    min-height: 2.75rem;
    display: flex;
    align-items: flex-start;
}
.bi-filters-toggles [data-testid="stCheckbox"] label {
    align-items: flex-start;
    width: 100%;
}
.bi-filters-toggles [data-testid="stCheckbox"] label p,
.bi-filters-toggles [data-testid="stRadio"] label p {
    font-size: 0.92rem;
    line-height: 1.35;
    margin: 0;
}
.bi-filters-toggles [data-testid="column"] {
    min-height: 2.75rem;
}

/* bi-filters-scope: единая сетка селекторов и чекбоксов во всех дашбордах */
.bi-filters-scope div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] [data-testid="stSelectbox"]),
.bi-filters-scope div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] [data-testid="stMultiSelect"]),
.bi-filters-scope div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] [data-testid="stDateInput"]) {
    display: flex !important;
    flex-wrap: nowrap !important;
    gap: 12px !important;
    column-gap: 12px !important;
    width: 100% !important;
    align-items: flex-start !important;
}
.bi-filters-scope div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] [data-testid="stSelectbox"]) > div[data-testid="column"],
.bi-filters-scope div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] [data-testid="stMultiSelect"]) > div[data-testid="column"],
.bi-filters-scope div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] [data-testid="stDateInput"]) > div[data-testid="column"] {
    flex: 1 1 0% !important;
    min-width: 0 !important;
    max-width: none !important;
    width: 0 !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
}
.bi-filters-scope div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] [data-testid="stCheckbox"]) {
    display: flex !important;
    flex-wrap: nowrap !important;
    gap: 12px !important;
    column-gap: 12px !important;
    width: 100% !important;
    align-items: flex-start !important;
}
.bi-filters-scope div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] [data-testid="stCheckbox"]) > div[data-testid="column"] {
    flex: 1 1 0% !important;
    min-width: 0 !important;
    max-width: none !important;
    width: 0 !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
}
.bi-filters-scope div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] [data-testid="stSelectbox"]) [data-testid="stSelectbox"],
.bi-filters-scope div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] [data-testid="stMultiSelect"]) [data-testid="stMultiSelect"],
.bi-filters-scope div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] [data-testid="stDateInput"]) [data-testid="stDateInput"] {
    max-width: none !important;
    width: 100% !important;
}

</style>
"""


def inject_unified_filters_css(st: Any) -> None:
    """Подключить общие стили сетки фильтров (идемпотентно по session_state)."""
    if not hasattr(st, "session_state"):
        return
    if st.session_state.get(_SESSION_CSS_FLAG_KEY):
        return
    st.markdown(UNIFIED_FILTERS_CSS, unsafe_allow_html=True)
    st.session_state[_SESSION_CSS_FLAG_KEY] = True


def _reset_button_key(keys: Sequence[str]) -> str:
    raw = "|".join(sorted(str(k) for k in keys))
    return "bi_filters_reset_" + hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


_FILTERS_LAST_DASHBOARD_KEY = "_bi_filters_last_dashboard"


def _filters_expander_session_key(
    st: Any,
    label: str,
    reset_keys: Optional[Sequence[str]],
    panel_key: Optional[str],
) -> str:
    if panel_key:
        raw = str(panel_key)
    elif reset_keys:
        raw = "|".join(sorted(str(k) for k in reset_keys))
    else:
        raw = str(label or "Фильтры")
    dash = ""
    if hasattr(st, "session_state"):
        dash = str(st.session_state.get("current_dashboard") or "").strip()
    digest = hashlib.md5(f"{dash}|{raw}".encode("utf-8")).hexdigest()[:12]
    return f"bi_filters_exp_{digest}"


def _collapse_filters_expander_on_dashboard_open(st: Any, expander_key: str) -> None:
    """При переходе на другой дашборд — блок «Фильтры» свёрнут."""
    if not hasattr(st, "session_state"):
        return
    cur_dash = str(st.session_state.get("current_dashboard") or "")
    if st.session_state.get(_FILTERS_LAST_DASHBOARD_KEY) != cur_dash:
        st.session_state[_FILTERS_LAST_DASHBOARD_KEY] = cur_dash
        st.session_state[expander_key] = False


def reset_filter_widgets(st: Any, keys: Sequence[str]) -> None:
    """Сбросить значения виджетов по ключам session_state."""
    if not hasattr(st, "session_state"):
        return
    for k in keys:
        st.session_state.pop(str(k), None)


def render_filter_chips(st: Any, chips: Optional[Sequence[Chip]]) -> None:
    """Строка чипов «Поле: значение» (пустой список — ничего не рисуем)."""
    if not chips:
        return
    parts: List[str] = []
    for label, value in chips:
        lab = html_escape(str(label or "").strip())
        val = html_escape(str(value or "").strip())
        if not lab or not val:
            continue
        parts.append(f'<span class="bi-filter-chip"><b>{lab}:</b> {val}</span>')
    if not parts:
        return
    inject_unified_filters_css(st)
    st.markdown(
        '<div class="bi-filter-chips">' + "".join(parts) + "</div>",
        unsafe_allow_html=True,
    )


def filters_section_title(st: Any, title: str) -> None:
    """Подзаголовок секции внутри popover (Иерархия / Отображение / …)."""
    inject_unified_filters_css(st)
    st.markdown(
        f'<p class="bi-filters-section-title">{html_escape(str(title or "").strip())}</p>',
        unsafe_allow_html=True,
    )




@contextmanager
def filters_selectors(st: Any) -> Generator[None, None, None]:
    """Селекторы (selectbox/multiselect/date/radio-режимы) — отдельным блоком сверху."""
    inject_unified_filters_css(st)
    st.markdown('<div class="bi-filters-selectors">', unsafe_allow_html=True)
    try:
        yield
    finally:
        st.markdown("</div>", unsafe_allow_html=True)


@contextmanager
def filters_toggles(st: Any) -> Generator[None, None, None]:
    """Чекбоксы и переключатели отображения — отдельным блоком ниже селекторов."""
    inject_unified_filters_css(st)
    st.markdown('<div class="bi-filters-toggles">', unsafe_allow_html=True)
    try:
        yield
    finally:
        st.markdown("</div>", unsafe_allow_html=True)


@contextmanager
def filters_grid(st: Any, columns: int = 3) -> Generator[List[Any], None, None]:
    """N колонок одинаковой ширины для selectbox/checkbox внутри popover."""
    inject_unified_filters_css(st)
    n = max(1, int(columns))
    yield st.columns(n)


class _FiltersPopoverHandle:
    """Ручка для отрисовки чипов после виджетов внутри popover."""

    def __init__(self, st: Any, chip_column: Any) -> None:
        self._st = st
        self._chip_column = chip_column

    def set_chips(self, chips: Optional[Sequence[Chip]]) -> None:
        with self._chip_column:
            render_filter_chips(self._st, chips)


@contextmanager
def filters_popover(
    st: Any,
    label: str = "Фильтры",
    *,
    active_count: int = 0,
    reset_keys: Optional[Sequence[str]] = None,
    panel_key: Optional[str] = None,
    expanded: bool = False,
) -> Generator[_FiltersPopoverHandle, None, None]:
    """
    Верхняя панель отчёта: чипы сверху, фильтры в свёрнутом expander, «Сбросить» внутри.
    Тело фильтров — внутри ``with filters_popover(...) as fp:`` … ``fp.set_chips([...])``.
    """
    inject_unified_filters_css(st)
    pop_label = str(label or "Фильтры").strip() or "Фильтры"
    if active_count > 0:
        pop_label = f"{pop_label} ({int(active_count)})"
    chip_slot = st.empty()
    handle = _FiltersPopoverHandle(st, chip_slot)
    _exp_key = _filters_expander_session_key(st, pop_label, reset_keys, panel_key)
    _collapse_filters_expander_on_dashboard_open(st, _exp_key)
    with st.expander(pop_label, expanded=expanded, key=_exp_key):
        if reset_keys:
            _rb_col, _ = st.columns([1, 4])
            with _rb_col:
                if st.button(
                    "Сбросить",
                    key=_reset_button_key(reset_keys),
                    help="Сбросить фильтры этого отчёта к значениям по умолчанию",
                ):
                    reset_filter_widgets(st, reset_keys)
                    st.rerun()
        yield handle


@contextmanager
def filter_columns(st: Any, n: int = 5):
    """Равные колонки для строки селекторов или чекбоксов (по умолчанию 5)."""
    inject_unified_filters_css(st)
    return st.columns(max(1, int(n)), gap="small")


@contextmanager
def filters_panel(
    st: Any,
    title: str = "Фильтры",
    *,
    reset_keys: Optional[Sequence[str]] = None,
    panel_key: Optional[str] = None,
    expanded: bool = False,
) -> Generator[None, None, None]:
    """
    Совместимость: виджеты в ``filters_popover`` (без чипов).
    Новые отчёты с чипами — ``filters_popover`` напрямую.
    """
    with filters_popover(
        st, label=title, reset_keys=reset_keys, panel_key=panel_key, expanded=expanded
    ) as _fp:
        inject_unified_filters_css(st)
        st.markdown('<div class="bi-filters-scope">', unsafe_allow_html=True)
        try:
            yield
        finally:
            st.markdown("</div>", unsafe_allow_html=True)
        _fp.set_chips([])


PROJECT_FILTER_PLACEHOLDER = "Все"
PROJECT_FILTER_LABEL = "Проект"

# Единые подписи фильтров (все дашборды)
FILTER_PANEL_TITLE = "Фильтры"
FILTER_RESET_LABEL = "Сбросить"
FILTER_ALL = "Все"
LABEL_PROJECT = "Проект"
LABEL_BLOCK = "Функциональный блок"
LABEL_BUILDING = "Строение"
LABEL_CONTRACTOR = "Подрядчик"
LABEL_COUNTERPARTY = "Контрагент"
LABEL_STAGE = "Этап"
LABEL_SECTION = "Раздел"
LABEL_REASON = "Причина"
LABEL_GROUP_BY = "Группировать по"
LABEL_VIEW = "Представление"
LABEL_PERIOD = "Период"
LABEL_GRANULARITY = "Гранулярность"
PERIOD_MODE_ALL_TIME = "Весь период (за всё время)"
PERIOD_MODE_CUSTOM = "Выбор диапазона дат"


PERIOD_MODE_CUSTOM = "Выбор диапазона дат"


def _ui_showcase_mode() -> bool:
    try:
        from config import is_showcase_mode

        return is_showcase_mode()
    except Exception:
        return False


def _normalize_date_bound(value: Any) -> Optional[date]:
    """Приводит значение к ``datetime.date`` для ``st.date_input``."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        import pandas as pd

        if isinstance(value, pd.Period):
            ts = value.to_timestamp(how="end")
            if pd.notna(ts):
                return ts.date()
        if isinstance(value, pd.Timestamp):
            if pd.notna(value):
                return value.date()
    except Exception:
        pass
    if hasattr(value, "to_pydatetime"):
        try:
            return value.to_pydatetime().date()
        except Exception:
            pass
    if hasattr(value, "date") and callable(value.date):
        try:
            d = value.date()
            if isinstance(d, date):
                return d
        except Exception:
            pass
    if isinstance(value, str):
        s = value.strip()
        if not s or s.lower() in ("nat", "none", "nan"):
            return None
        try:
            import pandas as pd

            ts = pd.to_datetime(s, dayfirst=True, errors="coerce")
            if pd.notna(ts):
                return ts.date()
        except Exception:
            pass
    return None


def _normalize_date_range_pair(
    pair: Any,
) -> Optional[Tuple[Optional[date], Optional[date]]]:
    if isinstance(pair, (list, tuple)) and len(pair) == 2:
        start = _normalize_date_bound(pair[0])
        end = _normalize_date_bound(pair[1])
        if start is None and end is None:
            return None
        return start, end
    one = _normalize_date_bound(pair)
    if one is None:
        return None
    return one, one


def _clamp_date_to_bounds(value: Any, min_value: Any, max_value: Any) -> Optional[date]:
    d = _normalize_date_bound(value)
    if d is None:
        return None
    min_d = _normalize_date_bound(min_value)
    max_d = _normalize_date_bound(max_value)
    if min_d is not None and d < min_d:
        return min_d
    if max_d is not None and d > max_d:
        return max_d
    return d


def _clamp_date_range_pair(
    pair: Any,
    min_value: Any,
    max_value: Any,
) -> Tuple[Optional[date], Optional[date]]:
    norm = _normalize_date_range_pair(pair)
    if norm is None:
        return None, None
    start = _clamp_date_to_bounds(norm[0], min_value, max_value)
    end = _clamp_date_to_bounds(norm[1], min_value, max_value)
    if start is not None and end is not None and start > end:
        start, end = end, start
    return start, end


def _clamp_date_to_bounds_legacy(value: Any, min_value: Any, max_value: Any) -> Any:
    if value is None:
        return value
    d = value.date() if hasattr(value, "date") and callable(value.date) else value
    if min_value is not None and d < min_value:
        return min_value
    if max_value is not None and d > max_value:
        return max_value
    return d


def _clamp_date_range_pair_legacy(
    pair: Any,
    min_value: Any,
    max_value: Any,
) -> Tuple[Any, Any]:
    if isinstance(pair, tuple) and len(pair) == 2:
        start = _clamp_date_to_bounds_legacy(pair[0], min_value, max_value)
        end = _clamp_date_to_bounds_legacy(pair[1], min_value, max_value)
        if start is not None and end is not None and start > end:
            start, end = end, start
        return start, end
    if hasattr(pair, "year"):
        d = _clamp_date_to_bounds_legacy(pair, min_value, max_value)
        return d, d
    return pair, pair


def _period_date_range_input_showcase(
    st: Any,
    key: str,
    *,
    min_value: Any,
    max_value: Any,
    default: Optional[Tuple[Any, Any]] = None,
    label: str = LABEL_PERIOD,
    help: Optional[str] = None,
    date_format: str = "DD.MM.YYYY",
) -> Tuple[Optional[date], Optional[date]]:
    min_d = _normalize_date_bound(min_value)
    max_d = _normalize_date_bound(max_value)
    if min_d is None or max_d is None:
        return None, None
    if min_d > max_d:
        min_d, max_d = max_d, min_d
    ss = getattr(st, "session_state", {})
    if key in ss:
        start, end = _clamp_date_range_pair(ss[key], min_d, max_d)
        if start is None or end is None:
            ss.pop(key, None)
        else:
            ss[key] = (start, end)
    default_pair: Optional[Tuple[date, date]] = None
    if default is not None:
        ds, de = _clamp_date_range_pair(default, min_d, max_d)
        if ds is not None and de is not None:
            default_pair = (ds, de)
    kw: dict = {
        "label": label,
        "min_value": min_d,
        "max_value": max_d,
        "key": key,
        "format": date_format,
    }
    if default_pair is not None and key not in ss:
        kw["value"] = default_pair
    dr = st.date_input(**kw, help=help)
    if isinstance(dr, tuple) and len(dr) == 2:
        return _normalize_date_bound(dr[0]), _normalize_date_bound(dr[1])
    one = _normalize_date_bound(dr)
    if one is not None:
        return one, one
    return None, None


def _period_date_range_input_legacy(
    st: Any,
    key: str,
    *,
    min_value: Any,
    max_value: Any,
    default: Optional[Tuple[Any, Any]] = None,
    label: str = LABEL_PERIOD,
    help: Optional[str] = None,
    date_format: str = "DD.MM.YYYY",
) -> Tuple[Optional[Any], Optional[Any]]:
    if min_value is None or max_value is None:
        return None, None
    ss = getattr(st, "session_state", {})
    if key in ss:
        start, end = _clamp_date_range_pair_legacy(ss[key], min_value, max_value)
        ss[key] = (start, end)
    if default is not None:
        default = _clamp_date_range_pair_legacy(default, min_value, max_value)
    kw: dict = {
        "label": label,
        "min_value": min_value,
        "max_value": max_value,
        "key": key,
        "format": date_format,
    }
    if default is not None and key not in ss:
        kw["value"] = default
    dr = st.date_input(**kw, help=help)
    if isinstance(dr, tuple) and len(dr) == 2:
        return dr[0], dr[1]
    if hasattr(dr, "year"):
        return dr, dr
    return None, None


def period_date_range_input(
    st: Any,
    key: str,
    *,
    min_value: Any,
    max_value: Any,
    default: Optional[Tuple[Any, Any]] = None,
    label: str = LABEL_PERIOD,
    help: Optional[str] = None,
    date_format: str = "DD.MM.YYYY",
) -> Tuple[Optional[Any], Optional[Any]]:
    """
    Единый фильтр периода: один ``st.date_input`` с календарём и выбором диапазона.
    Возвращает (start, end) или (None, None), если даты недоступны.
    """
    if _ui_showcase_mode():
        return _period_date_range_input_showcase(
            st,
            key,
            min_value=min_value,
            max_value=max_value,
            default=default,
            label=label,
            help=help,
            date_format=date_format,
        )
    return _period_date_range_input_legacy(
        st,
        key,
        min_value=min_value,
        max_value=max_value,
        default=default,
        label=label,
        help=help,
        date_format=date_format,
    )


def period_mode_and_range(
    st: Any,
    *,
    mode_key: str,
    range_key: str,
    min_value: Any,
    max_value: Any,
    default_range: Optional[Tuple[Any, Any]] = None,
    label: str = LABEL_PERIOD,
) -> Tuple[bool, Optional[Any], Optional[Any]]:
    """
    Режим «весь период» или календарный диапазон. Возвращает (all_time, start, end).
    """
    mode = st.selectbox(
        label,
        [PERIOD_MODE_ALL_TIME, PERIOD_MODE_CUSTOM],
        key=mode_key,
    )
    if mode != PERIOD_MODE_CUSTOM:
        return True, None, None
    start, end = period_date_range_input(
        st,
        range_key,
        min_value=min_value,
        max_value=max_value,
        default=default_range,
        label="",
    )
    return False, start, end


def migrate_project_multiselect_state(
    st: Any, key: str, options: Sequence[str]
) -> None:
    """Пустой список в session_state = все проекты (placeholder «Все»)."""
    if not hasattr(st, "session_state"):
        return
    opts_set = {str(o).strip() for o in options if str(o).strip()}
    try:
        raw = st.session_state.get(key)
        if isinstance(raw, str):
            s = raw.strip()
            st.session_state[key] = (
                []
                if s in ("", PROJECT_FILTER_PLACEHOLDER, "Все", "Все проекты")
                else [s]
            )
        elif isinstance(raw, list):
            cleaned = [x for x in raw if str(x).strip() in opts_set]
            raw_labels = {str(x).strip() for x in raw}
            if raw_labels & {
                PROJECT_FILTER_PLACEHOLDER,
                "Все",
                "Все проекты",
            }:
                st.session_state[key] = []
            elif cleaned and opts_set and set(cleaned) == opts_set:
                st.session_state[key] = []
            else:
                st.session_state[key] = cleaned
    except Exception:
        pass


def migrate_gdrs_month_multiselect_state(
    st: Any,
    key: str,
    month_labels: Sequence[str],
    *,
    default_labels: Optional[Sequence[str]] = None,
) -> None:
    """Убрать из session_state месяцы, которых нет в актуальном списке опций."""
    if not hasattr(st, "session_state"):
        return
    opts_set = {str(o).strip() for o in month_labels if str(o).strip()}
    if not opts_set:
        return
    fallback = [str(x).strip() for x in (default_labels or []) if str(x).strip() in opts_set]
    try:
        raw = st.session_state.get(key)
        if not isinstance(raw, list):
            return
        cleaned = [x for x in raw if str(x).strip() in opts_set]
        if raw and not cleaned:
            st.session_state[key] = list(fallback)
        elif cleaned != raw:
            st.session_state[key] = cleaned
    except Exception:
        pass


def project_filter_multiselect(
    st: Any,
    options: Sequence[str],
    key: str,
    *,
    label: str = PROJECT_FILTER_LABEL,
    help: Optional[str] = None,
) -> tuple[list[str], bool]:
    """
    Фильтр проектов: пустой выбор → все проекты, в поле показывается «Все»;
    при выборе — теги с крестиком (стандартный st.multiselect).
    """
    opts = [str(o).strip() for o in options if str(o).strip()]
    migrate_project_multiselect_state(st, key, opts)
    selected = st.multiselect(
        label,
        options=opts,
        key=key,
        placeholder=PROJECT_FILTER_PLACEHOLDER,
        help=help or "По умолчанию — все проекты. Отметьте один или несколько.",
    )
    sel = list(selected) if selected else []
    return sel, not bool(sel)


def count_chips(chips: Optional[Sequence[Chip]]) -> int:
    """Число непустых чипов для подписи на кнопке popover."""
    if not chips:
        return 0
    n = 0
    for label, value in chips:
        if str(label or "").strip() and str(value or "").strip():
            n += 1
    return n


# --- Универсальный QA debug-блок (виден на dev/локалке, скрыт в release) ---------

def _is_release_mode() -> bool:
    """True, если запущен release-режим — debug-блоки должны быть скрыты."""
    try:
        from config import is_release_client_mode
        return bool(is_release_client_mode())
    except Exception:
        import os
        for key in ("BI_ANALYTICS_HIDE_DEV_DIAGNOSTICS", "BI_ANALYTICS_RELEASE_MODE"):
            if str(os.environ.get(key, "")).strip().lower() in ("1", "true", "yes", "on"):
                return True
        return False


@contextmanager
def qa_debug_block(
    st: Any,
    title: str = "🔬 Сверка данных с эталоном (debug)",
    expanded: bool = False,
) -> Generator[bool, None, None]:
    """
    Контекст-менеджер для отладочного блока QA на дашборде.

    - На localhost / dev (ветка main) — рендерит ``st.expander(title)``.
    - На release (ветка release / env BI_ANALYTICS_HIDE_DEV_DIAGNOSTICS=1) —
      ничего не рендерит, тело блока не выполняется (yield False).
    """
    if _is_release_mode():
        yield False
        return
    with st.expander(title, expanded=expanded):
        yield True
