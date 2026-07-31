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
from typing import Any, Generator, List, Mapping, Optional, Sequence, Tuple

Chip = Tuple[str, str]


def suppress_caption(*_args, **_kwargs) -> None:
    """No-op вместо `st.caption` — не рендерить мелкий серый текст под виджетами."""
    return None


# --- Единый блок фильтров ---------------------------------------------------------

_SESSION_CSS_FLAG_KEY = "_bi_unified_filters_css_v12"
_DEFAULT_FIELD_MIN_PX = 260

UNIFIED_FILTERS_CSS = """
<style>
[data-testid="stMain"] .bi-filters-scope {
    --bi-filter-rhythm: 8px;
}
/* Не схлопывать selectbox в узкой 5-колоночной строке (Есипово и др.) */
.bi-filters-selectors [data-testid="stSelectbox"],
.bi-filters-scope [data-testid="stSelectbox"],
.bi-filters-selectors [data-testid="stDateInput"],
.bi-filters-scope [data-testid="stDateInput"] {
    min-width: 0 !important;
    min-height: 4.25rem !important;
    overflow: visible !important;
    opacity: 1 !important;
    visibility: visible !important;
}
.bi-filters-selectors [data-testid="stSelectbox"] [data-baseweb="select"],
.bi-filters-scope [data-testid="stSelectbox"] [data-baseweb="select"],
.bi-filters-selectors [data-testid="stSelectbox"] [data-baseweb="select"] > div,
.bi-filters-scope [data-testid="stSelectbox"] [data-baseweb="select"] > div {
    min-height: 2.4rem !important;
    width: 100% !important;
    max-width: 100% !important;
    opacity: 1 !important;
    visibility: visible !important;
}
.bi-filters-selectors [data-testid="stWidgetLabel"],
.bi-filters-scope [data-testid="stWidgetLabel"] {
    display: block !important;
    visibility: visible !important;
    opacity: 1 !important;
    overflow: visible !important;
    white-space: normal !important;
    line-height: 1.25 !important;
    margin-bottom: 0.15rem !important;
}
/* Явный wrap селекта «Функциональный блок» в «Причины отклонений» */
div[class*="st-key-devcombo_block_wrap"],
div[class*="st-key-devcombo_block"] {
    min-width: 0 !important;
    width: 100% !important;
    overflow: visible !important;
}
div[class*="st-key-devcombo_block_wrap"] [data-testid="stSelectbox"],
div[class*="st-key-devcombo_block"] [data-baseweb="select"],
div[class*="st-key-devcombo_block"] [data-baseweb="select"] > div {
    display: block !important;
    width: 100% !important;
    min-height: 2.4rem !important;
    opacity: 1 !important;
    visibility: visible !important;
}
/* Popover: равные колонки с ограничением ширины поля */
[data-testid="stMain"] [data-testid="stPopoverBody"] div[data-testid="stHorizontalBlock"] > div[data-testid="column"],
[data-testid="stMain"] div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stHorizontalBlock"] > div[data-testid="column"],
[data-testid="stMain"] .bi-filters-scope div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
    flex: 1 1 0% !important;
    min-width: """ + str(_DEFAULT_FIELD_MIN_PX) + """px !important;
    max-width: 320px !important;
}
/* Expander «Фilters»: строка селекторов — равные колонки (не чекбоксы!) */
[data-testid="stMain"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] .bi-filters-selectors div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(5):last-child),
[data-testid="stMainBlockContainer"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] .bi-filters-selectors div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(5):last-child),
[data-testid="stMain"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] .bi-filters-selectors div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(6):last-child),
[data-testid="stMainBlockContainer"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] .bi-filters-selectors div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(6):last-child) {
    display: flex !important;
    flex-wrap: nowrap !important;
    gap: 12px !important;
    column-gap: 12px !important;
    width: 100% !important;
}
[data-testid="stMain"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] .bi-filters-selectors div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(5):last-child) > div[data-testid="column"],
[data-testid="stMainBlockContainer"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] .bi-filters-selectors div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(5):last-child) > div[data-testid="column"],
[data-testid="stMain"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] .bi-filters-selectors div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(6):last-child) > div[data-testid="column"],
[data-testid="stMainBlockContainer"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] .bi-filters-selectors div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(6):last-child) > div[data-testid="column"] {
    flex: 1 1 0% !important;
    min-width: 0 !important;
    max-width: none !important;
    width: 0 !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
}
[data-testid="stMain"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] .bi-filters-selectors div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(5):last-child) [data-testid="stSelectbox"],
[data-testid="stMain"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] .bi-filters-selectors div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(5):last-child) [data-testid="stMultiSelect"],
[data-testid="stMain"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] .bi-filters-selectors div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(5):last-child) [data-testid="stDateInput"],
[data-testid="stMainBlockContainer"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] .bi-filters-selectors div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(5):last-child) [data-testid="stSelectbox"],
[data-testid="stMainBlockContainer"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] .bi-filters-selectors div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(5):last-child) [data-testid="stMultiSelect"],
[data-testid="stMainBlockContainer"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] .bi-filters-selectors div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(5):last-child) [data-testid="stDateInput"],
[data-testid="stMain"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] .bi-filters-selectors div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(6):last-child) [data-testid="stSelectbox"],
[data-testid="stMain"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] .bi-filters-selectors div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(6):last-child) [data-testid="stMultiSelect"],
[data-testid="stMain"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] .bi-filters-selectors div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(6):last-child) [data-testid="stDateInput"],
[data-testid="stMainBlockContainer"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] .bi-filters-selectors div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(6):last-child) [data-testid="stSelectbox"],
[data-testid="stMainBlockContainer"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] .bi-filters-selectors div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(6):last-child) [data-testid="stMultiSelect"],
[data-testid="stMainBlockContainer"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] .bi-filters-selectors div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"]:nth-child(6):last-child) [data-testid="stDateInput"] {
    max-width: none !important;
    width: 100% !important;
}
/* Чекбоксы в expander: ширина колонок — auto (перебивает общие правила) */
html body section.main [data-testid="stExpanderDetails"] div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] [data-testid="stCheckbox"]) > div[data-testid="column"],
html body section.main div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] [data-testid="stCheckbox"]) > div[data-testid="column"],
[data-testid="stExpanderDetails"] .bi-filters-toggles div[data-testid="stHorizontalBlock"] > div[data-testid="column"],
[data-testid="stExpanderDetails"] .bi-filters-scope div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] [data-testid="stCheckbox"]) > div[data-testid="column"] {
    flex: 1 1 14rem !important;
    min-width: 10rem !important;
    max-width: none !important;
    width: auto !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
}
[data-testid="stExpanderDetails"] .bi-filters-toggles [data-testid="stCheckbox"] label[data-baseweb="checkbox"],
html body section.main [data-testid="stExpanderDetails"] [data-testid="stCheckbox"] label[data-baseweb="checkbox"],
html body section.main [data-testid="stCheckbox"] label[data-baseweb="checkbox"] {
    display: inline-flex !important;
    flex-direction: row !important;
    align-items: flex-start !important;
    gap: 0.5rem !important;
    width: 100% !important;
    max-width: none !important;
}
[data-testid="stExpanderDetails"] .bi-filters-toggles [data-testid="stCheckbox"] label[data-baseweb="checkbox"] p,
[data-testid="stExpanderDetails"] .bi-filters-toggles [data-testid="stCheckbox"] label[data-baseweb="checkbox"] > div:last-child,
html body section.main [data-testid="stCheckbox"] label[data-baseweb="checkbox"] p {
    flex: 1 1 auto !important;
    width: auto !important;
    max-width: none !important;
    white-space: normal !important;
    word-break: normal !important;
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
    margin: 4px 0 3px 0;
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
    flex: 1 1 14rem !important;
    min-width: 10rem !important;
    max-width: none !important;
    width: auto !important;
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
    flex: 1 1 14rem !important;
    min-width: 10rem !important;
    max-width: none !important;
    width: auto !important;
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
    _light = False
    try:
        from dashboards.light_theme import is_light_preview_active

        _light = is_light_preview_active()
    except Exception:
        pass
    if st.session_state.get(_SESSION_CSS_FLAG_KEY) and not _light:
        return
    st.markdown(UNIFIED_FILTERS_CSS, unsafe_allow_html=True)
    st.session_state[_SESSION_CSS_FLAG_KEY] = True
    try:
        from dashboards.light_theme import maybe_inject_light_filter_widgets

        maybe_inject_light_filter_widgets(st)
    except Exception:
        pass


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


def _collapse_filters_expander_on_dashboard_open(
    st: Any,
    expander_key: str,
    *,
    default_expanded: bool = False,
) -> None:
    """При переходе на другой дашборд — задать состояние expander «Фильтры».

    По умолчанию свёрнут; для РД/ПД передают ``default_expanded=True``,
    чтобы фильтры снова были видны как раньше (не «исчезли»).
    """
    if not hasattr(st, "session_state"):
        return
    cur_dash = str(st.session_state.get("current_dashboard") or "")
    if st.session_state.get(_FILTERS_LAST_DASHBOARD_KEY) != cur_dash:
        st.session_state[_FILTERS_LAST_DASHBOARD_KEY] = cur_dash
        st.session_state[expander_key] = bool(default_expanded)


def _infer_filter_reset_value(key: str, previous: Any) -> Any:
    """Подобрать дефолт после сброса, если явный ``defaults`` не задан.

    Streamlit после ``pop`` по key часто оставляет прежний выбор в UI —
    нужно явно записать значение в session_state (особенно multiselect/selectbox).
    """
    if isinstance(previous, list):
        return []
    if isinstance(previous, bool):
        kl = str(key).lower()
        # hide_zero / hide_overdue в дашбордах по умолчанию включены (True)
        if "hide_zero" in kl or "hide_overdue" in kl:
            return True
        return False
    if isinstance(previous, str):
        kl = str(key).lower()
        if previous in (FILTER_ALL, "Все", "Все проекты", PROJECT_FILTER_PLACEHOLDER):
            return FILTER_ALL
        for tip in (
            "project",
            "block",
            "building",
            "contractor",
            "counterparty",
            "kontr",
            "reason",
            "section",
            "stage",
            "object",
            "contr",
            "kind",
        ):
            if tip in kl:
                return FILTER_ALL
        if previous in ("Месяц", "Квартал", "Год", "День"):
            return "Месяц"
        if previous in ("По месяцам", "Накопительно"):
            return "По месяцам"
        if previous in (PERIOD_MODE_ALL_TIME, PERIOD_MODE_CUSTOM):
            return PERIOD_MODE_ALL_TIME
        if previous == "Весь период":
            return "Весь период"
    # date range / числа / служебные tuple — не трогаем: виджет возьмёт свой value=
    return None


def reset_filter_widgets(
    st: Any,
    keys: Sequence[str],
    *,
    defaults: Optional[Mapping[str, Any]] = None,
) -> None:
    """Сбросить значения виджетов по ключам session_state.

    Ключ, оканчивающийся на ``*`` или ``_``, трактуется как префикс: чистятся все
    ключи session_state с таким началом. Это нужно для дашбордов с динамическими
    ключами (напр. Гант: ``gantt_block_filter_v2_{хэш_проекта}``), где точное имя
    заранее неизвестно.

    ``defaults`` — явные значения после очистки (selectbox в Streamlit иначе
    может сохранить последний выбор в UI). Если не переданы — для list/bool и
    типичных фильтров («Проект» → «Все») значения выводятся автоматически.
    """
    if not hasattr(st, "session_state"):
        return
    prefixes: list[str] = []
    exact: list[str] = []
    for k in keys:
        s = str(k)
        if s.endswith("*"):
            prefixes.append(s[:-1])
        elif s.endswith("_"):
            prefixes.append(s)
        else:
            exact.append(s)

    cleared: dict[str, Any] = {}
    for k in exact:
        if k in st.session_state:
            cleared[k] = st.session_state[k]
        st.session_state.pop(k, None)
    if prefixes:
        for existing in list(st.session_state.keys()):
            es = str(existing)
            if any(es.startswith(p) for p in prefixes):
                cleared[es] = st.session_state[existing]
                st.session_state.pop(existing, None)

    inferred: dict[str, Any] = {}
    for k, prev in cleared.items():
        cand = _infer_filter_reset_value(k, prev)
        if cand is not None:
            inferred[k] = cand
    if defaults:
        for k, v in defaults.items():
            inferred[str(k)] = v
    for k, v in inferred.items():
        st.session_state[k] = v


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
    reset_defaults: Optional[Mapping[str, Any]] = None,
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
    _collapse_filters_expander_on_dashboard_open(
        st, _exp_key, default_expanded=bool(expanded)
    )
    with st.expander(pop_label, expanded=expanded, key=_exp_key):
        if reset_keys:
            _rk = [str(k) for k in reset_keys]
            _rd = dict(reset_defaults) if reset_defaults else None

            def _on_filters_reset(
                _keys: Sequence[str] = _rk,
                _defs: Optional[Mapping[str, Any]] = _rd,
            ) -> None:
                # on_click выполняется до отрисовки виджетов — так session_state
                # успевает обновиться до multiselect/selectbox.
                reset_filter_widgets(st, _keys, defaults=_defs)

            _rb_col, _ = st.columns([1, 4])
            with _rb_col:
                st.button(
                    "Сбросить",
                    key=_reset_button_key(_rk),
                    help="Сбросить фильтры этого отчёта к значениям по умолчанию",
                    on_click=_on_filters_reset,
                )
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
    reset_defaults: Optional[Mapping[str, Any]] = None,
    panel_key: Optional[str] = None,
    expanded: bool = False,
) -> Generator[None, None, None]:
    """
    Совместимость: виджеты в ``filters_popover`` (без чипов).
    Новые отчёты с чипами — ``filters_popover`` напрямую.
    """
    with filters_popover(
        st,
        label=title,
        reset_keys=reset_keys,
        reset_defaults=reset_defaults,
        panel_key=panel_key,
        expanded=expanded,
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


def _normalize_date_like(value: Any) -> Optional[date]:
    """Привести значение к ``datetime.date`` или ``None`` (для session_state / date_input)."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.casefold() == "today":
            return date.today()
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "to_pydatetime"):
        try:
            dt = value.to_pydatetime()
            if isinstance(dt, datetime):
                return dt.date()
        except Exception:
            return None
    if hasattr(value, "date") and callable(value.date):
        try:
            d = value.date()
            if isinstance(d, datetime):
                return d.date()
            if isinstance(d, date):
                return d
        except Exception:
            return None
    return None


def _clamp_date_to_bounds(value: Any, min_value: Any, max_value: Any) -> Optional[date]:
    d = _normalize_date_like(value)
    if d is None:
        return None
    min_d = _normalize_date_like(min_value)
    max_d = _normalize_date_like(max_value)
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
    if isinstance(pair, (tuple, list)) and len(pair) == 2:
        start = _clamp_date_to_bounds(pair[0], min_value, max_value)
        end = _clamp_date_to_bounds(pair[1], min_value, max_value)
        if start is not None and end is not None and start > end:
            start, end = end, start
        return start, end
    single = _clamp_date_to_bounds(pair, min_value, max_value)
    if single is not None:
        return single, single
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
    if min_value is None or max_value is None:
        return None, None
    ss = getattr(st, "session_state", {})
    if key in ss:
        start, end = _clamp_date_range_pair(ss[key], min_value, max_value)
        if start is None or end is None:
            ss.pop(key, None)
        else:
            ss[key] = (start, end)
    if default is not None:
        default = _clamp_date_range_pair(default, min_value, max_value)
        if default[0] is None or default[1] is None:
            default = None
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
