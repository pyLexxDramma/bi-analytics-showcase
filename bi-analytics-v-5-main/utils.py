
"""
Общие утилиты для дашбордов и приложения.
"""
import html as html_module
import io
import re
from datetime import datetime
from typing import Any, Dict, Optional, Union

import numpy as np
import pandas as pd
import pytz
import streamlit as st

from config import RUSSIAN_MONTHS

# ── Smart datetime parsing ──────────────────────────────────────────────────
# pandas (включая 3.x) с `dayfirst=True` для ISO-строки '2025-04-01' выдаёт
# 4 января 2025 (переворачивает день/месяц), а с `format='mixed', dayfirst=True`
# то же самое. У нас в данных одновременно встречаются оба формата:
#   • CSV из 1С / MSP / TESSA — в основном DMY ('01.04.2025'),
#   • поля JSON 1С и сохранённые в БД даты — ISO ('2025-04-01').
# Этот helper парсит каждое значение по форме строки: ISO → без dayfirst,
# DMY → с dayfirst=True. Иначе план/факт менялись местами в матрице вех.
_ISO_DATE_PREFIX_RE = re.compile(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}")


def smart_to_datetime(value: Any) -> pd.Timestamp:
    """Скаляр → ``pd.Timestamp`` с корректным определением ISO vs DMY."""
    if value is None:
        return pd.NaT
    if isinstance(value, pd.Timestamp):
        return value
    if isinstance(value, (datetime,)):
        return pd.Timestamp(value)
    try:
        if pd.isna(value):
            return pd.NaT
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        s = value.strip()
        if not s or s.lower() in ("nan", "nat", "none"):
            return pd.NaT
        if _ISO_DATE_PREFIX_RE.match(s):
            return pd.to_datetime(s, errors="coerce", dayfirst=False)
        return pd.to_datetime(s, errors="coerce", dayfirst=True)
    return pd.to_datetime(value, errors="coerce", dayfirst=True)


def smart_to_datetime_series(
    series: Union[pd.Series, list, tuple, np.ndarray, Any],
) -> pd.Series:
    """Серия → ``pd.Series[datetime64[ns]]`` с поэлементным smart-парсингом.

    Векторизованная попытка через ``format='mixed'`` была бы быстрее, но
    в pandas 3.0 она ломается на ISO-строках при ``dayfirst=True``.
    Поэтому проходим apply’ом — для матрицы вех / контрольных точек
    объёмы данных небольшие, потеря производительности приемлема.
    """
    if not isinstance(series, pd.Series):
        series = pd.Series(series)
    if series.empty:
        return pd.to_datetime(series, errors="coerce")
    return series.apply(smart_to_datetime)

# Часовой пояс Москвы (UTC+3, без перехода на летнее время)
MOSCOW_TZ = pytz.timezone("Europe/Moscow")
UTC_TZ = pytz.UTC

# Маппинг англоязычных названий колонок на русские для отображения в таблицах
TABLE_COLUMN_EN_TO_RU = {
    "project name": "Проект",
    "task name": "Задача",
    "reason of deviation": "Причина отклонений",
    "deviation in days": "Отклонений в днях",
    "plan end": "Конец план",
    "base end": "Конец факт",
    "plan start": "Старт план",
    "base start": "Старт факт",
    "period": "Период",
    "deviation": "Отклонение",
    "section": "Раздел",
    "plan_month": "План (месяц)",
    # Доп. варианты (регистр / экспорт Plotly)
    "project": "Проект",
    "task": "Задача",
    "month": "Месяц",
    "count": "Количество",
    "quantity": "Количество",
    "start": "Начало",
    "end": "Окончание",
    "duration": "Длительность",
    "type": "Тип",
    "value": "Значение",
    "budget plan": "Плановый бюджет",
    "budget fact": "Фактический бюджет",
    "forecast budget": "Прогнозный бюджет",
    "approved budget": "Утверждённый бюджет",
}


def ru_column_header(col: Any) -> str:
    """Заголовок колонки для HTML/таблиц: англ. → рус., иначе как есть."""
    if col is None:
        return ""
    s = str(col).strip()
    if s in TABLE_COLUMN_EN_TO_RU:
        return TABLE_COLUMN_EN_TO_RU[s]
    low = s.lower()
    if low in TABLE_COLUMN_EN_TO_RU:
        return TABLE_COLUMN_EN_TO_RU[low]
    for en, ru in TABLE_COLUMN_EN_TO_RU.items():
        if en.lower() == low:
            return ru
    return s

# Фон HTML-таблиц (чуть темнее карточки контента для контраста)
TABLE_BG_COLOR = "hsl(209,67%,12%)"
# Шапка и строки-разделители проектов — темнее, чтобы блоки визуально отделялись
TABLE_HEADER_BG_COLOR = "hsl(209, 72%, 6%)"
TABLE_GROUP_ROW_BG_COLOR = "hsl(209, 70%, 7%)"
TABLE_TOTAL_ROW_BG_COLOR = "hsl(208, 58%, 18%)"
TABLE_HEADER_FONT_CSS = "font-weight:700;font-size:1.05em;"
TABLE_TOTAL_ROW_FONT_CSS = (
    "font-weight:800;font-size:1.32em;text-transform:uppercase;"
    "letter-spacing:0.05em;color:#f8fbff;"
)
# Фон области графиков Plotly — как карточка контента (.main .block-container: rgba(18,56,92,0.8))
CHART_BG_COLOR = "rgba(18, 56, 92, 0.88)"
CHART_GRID_COLOR = "rgba(255,255,255,0.08)"
CHART_AXIS_LINE_COLOR = "rgba(255,255,255,0.25)"
CHART_ZEROLINE_COLOR = "rgba(255,255,255,0.2)"
TABLE_TEXT_COLOR = "#ffffff"
TABLE_CELL_BORDER = "1px solid #5a7a9a"
FINANCE_TABLE_CELL_BORDER = "1px solid #7a9ec4"
TABLE_CELL_BORDER_CSS = f"border: {TABLE_CELL_BORDER};"


def _table_cell_style(background: str, color: str, *, extra: str = "") -> str:
    """Inline-стиль ячейки Styler: фон + цвет + граница (apply() затирает set_properties)."""
    parts = [f"background-color: {background}", f"color: {color}", TABLE_CELL_BORDER_CSS]
    if extra:
        parts.append(extra.strip())
    return "; ".join(parts)
# ТЗ: факт vs план — цвет шрифта (без светофоров ●)
DEVIATION_NEUTRAL_PCT = 0.10
DEVIATION_CLASS_RED = "bd-cell-red"
DEVIATION_CLASS_GREEN = "bd-cell-green"
DEVIATION_CLASS_YELLOW = "bd-cell-yellow"
BD_CELL_GREEN_COLOR = "hsl(148,100%,63%)"
BD_CELL_GREEN_COLOR_LIGHT = "hsl(148, 72%, 36%)"
BD_CELL_GREEN_READABILITY_CSS = (
    "-webkit-text-stroke: 0.28px #111827; paint-order: stroke fill; "
    "text-shadow: -0.28px 0 #111827, 0.28px 0 #111827, 0 -0.28px #111827, 0 0.28px #111827;"
)
BD_CELL_RED_COLOR_LIGHT = "hsl(348, 82%, 42%)"
SHOWCASE_TABLE_BG_COLOR = "#ffffff"
SHOWCASE_TABLE_TEXT_COLOR = "#111827"
SHOWCASE_TABLE_HEADER_BG_COLOR = "#f3f4f6"
SHOWCASE_TABLE_GROUP_ROW_BG_COLOR = "#e8ecf1"
SHOWCASE_TABLE_CELL_BORDER = "1px solid #cbd5e1"


def _budget_table_use_light_theme() -> bool:
    try:
        from config import is_showcase_mode

        return bool(is_showcase_mode())
    except Exception:
        return False


def _bd_cell_green_css(*, light_bg: bool) -> str:
    color = BD_CELL_GREEN_COLOR_LIGHT if light_bg else BD_CELL_GREEN_COLOR
    stroke = BD_CELL_GREEN_READABILITY_CSS if light_bg else ""
    return f"color: {color} !important; -webkit-text-fill-color: {color} !important; {stroke}"

# Единый размер колонок HTML-таблиц (format_dataframe_as_html, plan_fact_dates и т.д.)
HTML_TABLE_TH_MAX_EM = 24
HTML_TABLE_TD_MAX_EM = 22
HTML_TABLE_COL_MIN_EM = 11
HTML_TABLE_TH_WRAP_CSS = (
    "white-space:normal;word-wrap:break-word;overflow-wrap:anywhere;line-height:1.25;"
    "overflow:visible;text-overflow:clip;vertical-align:bottom;"
)
HTML_TABLE_TD_TEXT_CSS = (
    "white-space:normal;word-wrap:break-word;overflow-wrap:anywhere;"
    "overflow:visible;text-overflow:clip;vertical-align:top;"
)
HTML_TABLE_TD_COMPACT_CSS = (
    "white-space:nowrap;overflow:visible;text-overflow:clip;"
)

# Общие правила вёрстки HTML-таблиц (сортировка + выравнивание + перенос заголовков).
BI_TABLE_LAYOUT_CSS = """
<style>
.bi-sortable-html-root table.bi-sortable-table th,
table.bi-sortable-table th {
  text-align: center !important;
  vertical-align: middle !important;
  white-space: normal !important;
  word-wrap: break-word !important;
  overflow-wrap: anywhere !important;
  line-height: 1.25 !important;
  max-width: 11em !important;
  overflow: visible !important;
  text-overflow: clip !important;
}
.bi-sortable-html-root table.bi-sortable-table td,
table.bi-sortable-table td {
  text-align: center !important;
  vertical-align: middle !important;
  white-space: normal !important;
  word-wrap: break-word !important;
  overflow-wrap: anywhere !important;
  overflow: visible !important;
  text-overflow: clip !important;
  max-width: 28em !important;
}
.bi-sortable-html-root table.bi-sortable-table td.col-text,
table.bi-sortable-table td.col-text {
  text-align: left !important;
  vertical-align: top !important;
  max-width: 36em !important;
}
.bi-sortable-html-root table.bi-sortable-table th.col-text,
table.bi-sortable-table th.col-text {
  text-align: center !important;
  vertical-align: middle !important;
}
.bi-sortable-html-root table.bi-sortable-table th.col-pf-start,
.bi-sortable-html-root table.bi-sortable-table th.col-pf-end,
.bi-sortable-html-root table.bi-sortable-table th.col-pf-dur,
.bi-sortable-html-root table.bi-sortable-table td.col-pf-start,
.bi-sortable-html-root table.bi-sortable-table td.col-pf-end,
.bi-sortable-html-root table.bi-sortable-table td.col-pf-dur,
table.bi-sortable-table th.col-pf-start,
table.bi-sortable-table th.col-pf-end,
table.bi-sortable-table th.col-pf-dur,
table.bi-sortable-table td.col-pf-start,
table.bi-sortable-table td.col-pf-end,
table.bi-sortable-table td.col-pf-dur {
  white-space: nowrap !important;
  word-wrap: normal !important;
  overflow-wrap: normal !important;
  word-break: normal !important;
  max-width: none !important;
  text-align: center !important;
  vertical-align: middle !important;
}
.bi-sortable-html-root table.bi-sortable-table th.col-pf-start .bi-sort-label,
.bi-sortable-html-root table.bi-sortable-table th.col-pf-end .bi-sort-label,
.bi-sortable-html-root table.bi-sortable-table th.col-pf-dur .bi-sort-label,
table.bi-sortable-table th.col-pf-start .bi-sort-label,
table.bi-sortable-table th.col-pf-end .bi-sort-label,
table.bi-sortable-table th.col-pf-dur .bi-sort-label {
  white-space: nowrap !important;
  word-wrap: normal !important;
  overflow-wrap: normal !important;
  text-align: center !important;
  display: inline-block;
}
</style>
"""

BI_RESPONSIVE_DASHBOARD_CSS = """
<style>
/* BI Analytics: узкие экраны — таблицы и графики (все дашборды) */
.rendered-table-wrap,.bi-styled-table-wrap,.exec-doc-table-wrap,.pf-dates-table-wrap,
.budget-deviation-table-wrap,.budget-table-scroll,.dev-reasons-wrap,.pred-detail-wrap,
.gdrs-table-wrap,.gdrs-summary-table-wrap,.fc-table-scroll-wrap,.bi-sortable-html-root,
div[data-testid="stElementContainer"]:has(iframe[title="streamlit_components_v1"]),
div[data-testid="stHtml"]{max-width:100%!important;min-width:0!important;box-sizing:border-box!important}
.rendered-table-wrap,.pf-dates-table-wrap,.exec-doc-table-wrap,.bi-styled-table-wrap,
.budget-deviation-table-wrap,.budget-table-scroll,.dev-reasons-wrap,.pred-detail-wrap,
.fc-table-scroll-wrap,.gdrs-table-wrap,.gdrs-summary-table-wrap{overflow-x:auto!important;-webkit-overflow-scrolling:touch!important}
table.bi-sortable-table th,.bi-sortable-html-root table.bi-sortable-table th{
  text-align:center!important;vertical-align:middle!important}
table.bi-sortable-table thead th>div,.bi-sortable-html-root table.bi-sortable-table thead th>div{
  justify-content:center!important;align-items:center!important}
table.bi-sortable-table thead th .bi-sort-label{text-align:center!important}
[data-testid="stPlotlyChart"],[data-testid="stPlotlyChart"]>div,[data-testid="stPlotlyChart"] iframe{
  max-width:100%!important;width:100%!important;box-sizing:border-box!important}
.pf-fbar-wrap,.pf-gantt-view{overflow-x:auto!important;max-width:100%!important;-webkit-overflow-scrolling:touch!important}
div[data-testid="stElementContainer"]:has(iframe[title="streamlit_components_v1"]){
  overflow:visible!important;width:100%!important;max-width:100%!important}
@media (max-width:1100px){
  .rendered-table-wrap,.budget-deviation-table-wrap,.budget-table-scroll,
  .pf-dates-table-wrap,.pf-dates-scroll-wrap,.exec-doc-table-wrap,.bi-styled-table-wrap,
  .dev-reasons-wrap,.gdrs-table-wrap,.gdrs-summary-table-wrap,.fc-table-scroll-wrap,
  .pred-detail-wrap,.bi-sortable-html-root:has(table.bi-sortable-table){
    overflow-x:auto!important;overflow-y:auto!important;
    max-height:min(70vh,640px)!important;
    -webkit-overflow-scrolling:touch!important;scrollbar-gutter:stable}
  .rendered-table-wrap .rendered-table,.rendered-table-wrap table,
  .budget-deviation-table-wrap table,.budget-table-scroll table,
  .pf-dates-table-wrap .pf-dates-table,.pf-dates-table-wrap table,
  .exec-doc-table-wrap table,.bi-styled-table-wrap table,.dev-reasons-wrap table,
  .gdrs-table-wrap table,.gdrs-summary-table-wrap table,.fc-table-scroll-wrap table,
  .pred-detail-wrap table{
    width:max-content!important;min-width:100%!important;table-layout:auto!important}
  .rendered-table-wrap thead th,.budget-deviation-table-wrap thead th,
  .budget-table-scroll thead th,.pf-dates-table-wrap thead th,.pf-dates-scroll-wrap thead th,
  .exec-doc-table-wrap thead th,.bi-styled-table-wrap thead th,.dev-reasons-wrap thead th,
  .gdrs-table-wrap thead th,.fc-table-scroll-wrap thead th,.pred-detail-wrap thead th,
  table.bi-sortable-table thead th,.bi-sortable-html-root table.bi-sortable-table thead th{
    position:sticky!important;top:0!important;z-index:5!important}
  table.bi-sortable-table th,.bi-sortable-html-root table.bi-sortable-table th{
    font-size:9px!important;padding:6px 4px!important;white-space:normal!important;word-wrap:break-word!important;max-width:none!important}
  table.bi-sortable-table td{font-size:11px!important;padding:5px 6px!important}
  [data-testid="stPlotlyChart"]{min-height:280px!important}
  [data-testid="stPlotlyChart"] iframe{min-height:260px!important}
  .pred-detail-wrap{height:min(55vh,420px)!important;max-height:min(55vh,420px)!important}
  .fc-table-scroll-wrap{height:100%!important;max-height:100%!important}
}
.fc-table-scroll-wrap{height:100%!important;max-height:100%!important;overflow-y:auto!important;overflow-x:auto!important;-webkit-overflow-scrolling:touch!important;scrollbar-gutter:stable}
.fc-table-scroll-wrap thead th{position:sticky!important;top:0!important;z-index:5!important;background:hsl(209,72%,6%)!important}
@media (max-width:700px){
  .main .block-container{padding-left:.75rem!important;padding-right:.75rem!important}
  [data-testid="stPlotlyChart"]{min-height:240px!important}
}

</style>
"""


# Размерность сумм: млн рублей
MILLION = 1_000_000

TABLE_CAPTION_STYLE = (
    "margin:0.75em 0 0.35em 0;font-size:1.05rem;font-weight:700;color:#e8eef5;"
)
TABLE_CAPTION_STYLE_LIGHT = (
    "margin:0.75em 0 0.35em 0;font-size:1.05rem;font-weight:700;color:#111827;"
)


def format_table_title(name: str, filters_suffix: str | None = None) -> str:
    """«Таблица …» + опционально фильтры в скобках."""
    s = str(name or "").strip()
    if not s:
        s = "данные"
    if not s.casefold().startswith("таблица"):
        s = f"Таблица {s}"
    if filters_suffix:
        fs = str(filters_suffix).strip().strip("()")
        if fs and f"({fs})" not in s:
            s = f"{s} ({fs})"
    return sanitize_display_label(s)


def render_table_subheader(st: Any, name: str, filters_suffix: str | None = None) -> None:
    """Заголовок таблицы по ТЗ: слово «Таблица» в начале."""
    st.subheader(format_table_title(name, filters_suffix))


def _html_table_caption(caption: str | None, *, light: bool = False) -> str:
    if not caption or not str(caption).strip():
        return ""
    cap = html_module.escape(sanitize_display_label(str(caption).strip()))
    style = TABLE_CAPTION_STYLE_LIGHT if light else TABLE_CAPTION_STYLE
    return f'<h3 class="bi-table-caption" style="{style}">{cap}</h3>'


def _row_is_table_total(row: pd.Series, *, skip_cols: set[str] | None = None) -> bool:
    """Строка «Итого» / «ИТОГО» в первой текстовой колонке."""
    skip = skip_cols or set()
    for col in row.index:
        if col in skip:
            continue
        v = str(row[col]).strip().casefold()
        if v in ("итого", "итог", "total"):
            return True
    return False


def mark_html_table_sortable(html: str) -> str:
    """Добавляет класс для клиентской сортировки (см. table_sort_inject)."""
    if not html or "<table" not in html:
        return html

    def _patch_table_tag(match: re.Match) -> str:
        tag = match.group(0)
        if "bi-sortable-table" in tag:
            if "bi-sort-click-only" not in tag:
                if re.search(r'\bclass=["\']', tag, flags=re.I):
                    return re.sub(
                        r'class=(["\'])([^"\']*)\1',
                        lambda m: f'class={m.group(1)}{m.group(2)} bi-sort-click-only{m.group(1)}',
                        tag,
                        count=1,
                        flags=re.I,
                    )
                return tag[:-1] + ' class="bi-sort-click-only"' + tag[-1]
            return tag
        if re.search(r'\bclass=["\']', tag, flags=re.I):
            return re.sub(
                r'class=(["\'])([^"\']*)\1',
                lambda m: f'class={m.group(1)}{m.group(2)} bi-sortable-table bi-sort-click-only{m.group(1)}',
                tag,
                count=1,
                flags=re.I,
            )
        return tag[:-1] + ' class="bi-sortable-table bi-sort-click-only"' + tag[-1]

    return re.sub(r"<table\b[^>]*>", _patch_table_tag, html, flags=re.I)



def render_dataframe_sortable(
    df: pd.DataFrame,
    *,
    file_stem: str = "table_export",
    key_prefix: str | None = None,
    use_styler: bool = True,
    hide_index: bool = True,
    **style_kwargs,
) -> None:
    """DataFrame с клиентской сортировкой по клику на заголовок."""
    if df is None or getattr(df, "empty", True):
        st.info("Нет данных для отображения.")
        return
    if use_styler:
        styler = (
            style_dataframe_for_dark_theme(df, **style_kwargs)
            if style_kwargs
            else style_dataframe_for_dark_theme(df)
        )
        html = render_styled_table_to_html(styler, hide_index=hide_index)
    else:
        html = format_dataframe_as_html(df)
    render_report_html_table(
        html,
        export_df=df,
        file_stem=file_stem,
        key_prefix=key_prefix or f"df_sort_{abs(id(df))}",
    )



TABLE_COL_TEXT_KEYS = (
    "задач", "проект", "лот", "раздел", "блок", "строен", "причин", "замет", "назван",
    "контрагент", "подряд", "шифр", "объект", "ковенант", "функц", "наимен", "документ",
    "предпис", "договор", "исполнит", "мероприят", "описан", "коммент", "этап", "вех", "вид", "note", "name",
    "task", "partner", "контраг", "секци", "подраздел", "строение", "участок", "работ",
)


def table_column_css_class(col: str) -> str:
    """col-text — длинные подписи (td слева); иначе col-num — числа/даты (td по центру). th всегда центрируют CSS."""
    cl = str(col or "").strip().casefold()
    if any(k in cl for k in TABLE_COL_TEXT_KEYS):
        return "col-text"
    return "col-num"


def sanitize_display_label(value: Any) -> str:
    """
    Убирает хвостовые точки/многоточие в подписях («Проект.», «Название..») для UI.
    Не трогает чисто числовые значения.
    """
    if value is None:
        return ""
    s = str(value).strip()
    if not s or s.lower() in ("nan", "nat", "none"):
        return s
    try:
        _t = s.replace(" ", "").replace("\u00a0", "").replace(",", ".")
        if re.match(r"^[-+]?\d+(?:[.,]\d+)?$", _t):
            return s
    except Exception:
        pass
    s = re.sub(r"[.\u2026…]+$", "", s).strip()
    return s


def norm_partner_join_key(val: Any) -> str:
    """
    Ключ для сопоставления наименований контрагентов между файлами (1С ДтКт, справочник, обороты).
    Нижний регистр, пробелы, без кавычек «» и лишних хвостов вроде ООО.
    """
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    s = s.replace("«", "").replace("»", "").replace('"', "").replace("'", "")
    s = s.lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(
        r"\s*(\bооо\b|\bзао\b|\bоао\b|\bпао\b|\bип\b)\s*$",
        "",
        s,
        flags=re.IGNORECASE,
    )
    return s.strip()


def format_russian_datetime(dt_str: str | None, with_seconds: bool = False) -> str:
    """
    Форматирует ISO-строку времени (предположительно в UTC) в русское представление
    в часовом поясе Москвы (Europe/Moscow).

    Args:
        dt_str: строка в формате ISO 8601 (например '2026-02-18T04:15:00+00:00')
        with_seconds: показывать секунды или только часы:минуты

    Returns:
        Строка вида "18 фев. 2026, 07:15" или "18 фев. 2026, 07:15:23"
    """
    if not dt_str:
        return "-"

    try:
        # Поддержка как с Z, так и с +00:00
        dt_str_clean = dt_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(dt_str_clean)

        # Если нет информации о часовом поясе → считаем UTC
        if dt.tzinfo is None:
            dt = UTC_TZ.localize(dt)

        # Конвертируем в московское время
        local_dt = dt.astimezone(MOSCOW_TZ)

        day = local_dt.day
        month_ru = RUSSIAN_MONTHS.get(local_dt.month, local_dt.strftime("%B"))
        year = local_dt.year
        time_fmt = "%H:%M:%S" if with_seconds else "%H:%M"
        time_str = local_dt.strftime(time_fmt)

        return f"{day} {month_ru} {year}, {time_str}"

    except (ValueError, TypeError) as e:
        # Если парсинг не удался — возвращаем исходную строку или заглушку
        return dt_str or "-"


def ensure_budget_columns(df: Optional[pd.DataFrame]) -> None:
    """Добавляет budget plan / budget fact из русских/альтернативных названий, если их ещё нет."""
    if df is None or not hasattr(df, "columns"):
        return
    if "budget plan" not in df.columns:
        for name in ("Бюджет План", "Бюджет план", "Budget Plan", "budget_plan"):
            if name in df.columns:
                df["budget plan"] = df[name]
                break
    if "budget fact" not in df.columns:
        for name in ("Бюджет Факт", "Бюджет факт", "Budget Fact", "budget_fact"):
            if name in df.columns:
                df["budget fact"] = df[name]
                break


def outline_level_numeric(series: pd.Series) -> pd.Series:
    """
    Числовой уровень иерархии MSP (outline): 2, «2», «Уровень 2».
    Используется в фильтрах «Функциональный блок»/«Строение» и при заполнении level structure.
    """
    if series is None or len(series) == 0:
        return pd.Series(dtype=float)
    num = pd.to_numeric(series, errors="coerce")
    mask_na = num.isna()
    if not mask_na.any():
        return num
    s_rest = series[mask_na].astype(str).str.strip()
    ext = s_rest.str.extract(r"(-?\d+)", expand=False)
    num2 = pd.to_numeric(ext, errors="coerce")
    out = num.copy()
    out.loc[mask_na] = num2.values
    return out


def ensure_date_columns(df: Optional[pd.DataFrame]) -> None:
    """
    Добавляет plan start, plan end, base start, base end из русских названий,
    если английских колонок ещё нет.
    """
    if df is None or not hasattr(df, "columns"):
        return
    date_mapping = [
        ("plan start", ["Старт План", "План Старт", "Plan Start"]),
        ("plan end", ["Конец План", "План Конец", "Plan End"]),
        ("base start", ["Старт Факт", "Факт Старт", "Base Start"]),
        ("base end", ["Конец Факт", "Факт Конец", "Base End"]),
    ]
    for en_name, ru_names in date_mapping:
        if en_name not in df.columns:
            for ru in ru_names:
                if ru in df.columns:
                    df[en_name] = df[ru].copy()
                    break


def ensure_msp_hierarchy_columns(df: Optional[pd.DataFrame]) -> None:
    """
    Добавляет canonical-колонки MSP для дерева задач: task name, level structure, level.

    Ручная загрузка через data_loader не применяет web_loader._MSP_COLUMN_REMAP — без этого
    нет «Уровень_структуры» → level structure, и фильтры «Функциональный блок»/«Строение»
    остаются на колонке block («Блок 1»…).
    """
    if df is None or not hasattr(df, "columns") or getattr(df, "empty", True):
        return

    def _col_by_exact(names: tuple[str, ...]):
        lower_map = {str(c).strip().lower(): c for c in df.columns}
        for n in names:
            key = str(n).strip().lower()
            if key in lower_map:
                return lower_map[key]
        return None

    if "task name" not in df.columns:
        src = _col_by_exact(
            (
                "Название задачи",
                "Название",
                "Task Name",
                "Имя",
                "Имя задачи",
                "Задача",
            )
        )
        if src is not None:
            df["task name"] = df[src]

    src_outline = _col_by_exact(
        (
            "Уровень_структуры",
            "Уровень структуры",
            "Outline Level",
            "outline level",
            "WBS Level",
            "Исходный уровень",
        )
    )
    if src_outline is None:
        for c in df.columns:
            sl = re.sub(r"\s+", " ", str(c).replace("\ufeff", "").strip().lower())
            sl = sl.replace("_", " ")
            if re.search(r"(уровень.*структ|структ.*уровень|outline\s*level|wbs\s*level)", sl):
                if "приоритет" in sl or "риск" in sl:
                    continue
                src_outline = c
                break
    src_level = _col_by_exact(("Уровень", "Level"))

    if "level structure" not in df.columns:
        if src_outline is not None:
            df["level structure"] = outline_level_numeric(df[src_outline])
        elif src_level is not None:
            df["level structure"] = outline_level_numeric(df[src_level])
    elif src_outline is not None and df["level structure"].notna().sum() == 0:
        df["level structure"] = outline_level_numeric(df[src_outline])

    if "level" not in df.columns:
        if src_level is not None:
            df["level"] = outline_level_numeric(df[src_level])
        elif "level structure" in df.columns:
            df["level"] = df["level structure"]
    elif src_level is not None and df["level"].notna().sum() == 0:
        df["level"] = outline_level_numeric(df[src_level])

    for _col in ("level structure", "level"):
        if _col in df.columns:
            df[_col] = outline_level_numeric(df[_col])

    normalize_plan_month_column(df)


def normalize_plan_month_column(df: Optional[pd.DataFrame]) -> None:
    """
    Приводит колонку plan_month к месячным Period (избегает TypeError str vs Period при фильтрах).
    """
    if df is None or not hasattr(df, "columns") or getattr(df, "empty", True):
        return
    if "plan_month" not in df.columns:
        return
    s = df["plan_month"]
    try:
        if isinstance(s.dtype, pd.PeriodDtype):
            return
    except Exception:
        pass
    if str(getattr(s, "dtype", "")).startswith("period"):
        return

    def _one(v: Any) -> Any:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return pd.NaT
        if isinstance(v, pd.Period):
            fs = getattr(v, "freqstr", None) or ""
            if fs == "M" or str(fs).startswith("M"):
                return v
            try:
                return v.asfreq("M")
            except Exception:
                return v
        if isinstance(v, pd.Timestamp):
            return v.to_period("M")
        vs = str(v).strip()
        if not vs or vs.lower() in ("nan", "nat", "none"):
            return pd.NaT
        try:
            if re.match(r"^\d{4}-\d{2}", vs):
                return pd.Period(vs[:7], freq="M")
        except Exception:
            pass
        try:
            ts = pd.to_datetime(vs, errors="coerce", dayfirst=True)
            if pd.notna(ts):
                return ts.to_period("M")
        except Exception:
            pass
        return pd.NaT

    try:
        df["plan_month"] = s.map(_one)
    except Exception:
        return


def get_russian_month_name(period_val: Any) -> str:
    """Возвращает русское название месяца для Period, Timestamp или строки."""
    if isinstance(period_val, pd.Period):
        if period_val.freqstr == "M" or (getattr(period_val, "freqstr", "") or "").startswith("M"):
            month_num = period_val.month
            return RUSSIAN_MONTHS.get(month_num, period_val.strftime("%B"))
        try:
            month_num = period_val.month
            return RUSSIAN_MONTHS.get(month_num, "")
        except Exception:
            return ""
    elif isinstance(period_val, (int, pd.Timestamp)):
        month_num = period_val.month if hasattr(period_val, "month") else period_val
        return RUSSIAN_MONTHS.get(month_num, "")
    elif isinstance(period_val, str):
        try:
            if "-" in period_val:
                parts = period_val.split("-")
                if len(parts) >= 2:
                    month_num = int(parts[1])
                    return RUSSIAN_MONTHS.get(month_num, "")
        except Exception:
            pass
    return ""


def format_period_ru(period_val) -> str:
    if period_val is None or (isinstance(period_val, float) and pd.isna(period_val)):
        return "Н/Д"
    try:
        if pd.isna(period_val):
            return "Н/Д"
    except (TypeError, ValueError):
        pass
    try:
        if isinstance(period_val, pd.Period):
            freq = getattr(period_val, "freq", None)
            try:
                if isinstance(freq, pd.offsets.QuarterEnd):
                    return f"К{int(period_val.quarter)} {int(period_val.year)}"
                if isinstance(
                    freq,
                    (pd.offsets.YearEnd, pd.offsets.YearBegin),
                ):
                    return str(int(period_val.year))
            except Exception:
                pass
            fs = str(getattr(period_val, "freqstr", "") or "")
            if fs.startswith("Q"):
                try:
                    return f"К{int(period_val.quarter)} {int(period_val.year)}"
                except Exception:
                    pass
            if fs.startswith("A") or fs.startswith("Y"):
                try:
                    return str(int(period_val.year))
                except Exception:
                    pass
            month_num = period_val.month
            year = period_val.year
            return f"{RUSSIAN_MONTHS.get(month_num, 'Н/Д')} {year}"
        if isinstance(period_val, pd.Timestamp):
            return f"{RUSSIAN_MONTHS.get(period_val.month, 'Н/Д')} {period_val.year}"
        if isinstance(period_val, str):
            s = period_val.strip()
            if not s or s.lower() in ("nan", "nat", "none"):
                return "Н/Д"
            if "-" in s:
                parts = s.split("-")
                if len(parts) >= 2:
                    try:
                        year = int(parts[0])
                        month = int(parts[1])
                        return f"{RUSSIAN_MONTHS.get(month, 'Н/Д')} {year}"
                    except (ValueError, TypeError):
                        pass
            try:
                ts = pd.Timestamp(s)
                if pd.notna(ts):
                    return f"{RUSSIAN_MONTHS.get(ts.month, 'Н/Д')} {ts.year}"
            except Exception:
                pass
            return s
        if hasattr(period_val, "month") and hasattr(period_val, "year"):
            return f"{RUSSIAN_MONTHS.get(period_val.month, 'Н/Д')} {period_val.year}"
    except Exception:
        pass
    out = str(period_val) if period_val is not None else "Н/Д"
    if isinstance(out, str) and out.strip().lower() in ("nan", "nat", "none"):
        return "Н/Д"
    return out


def apply_chart_background(fig, *, skip_uniformtext: bool = False):
    """
    Применяет единый стиль (тёмная тема) ко всем графикам Plotly.
    Вызывается перед st.plotly_chart() в каждом дашборде.

    skip_uniformtext: если True — не задаётся uniformtext (по умолчанию mode=show).
    Нужно для Ганта с подписями textposition='outside' у концов полос, если
    внешние настройки не подходят.
    """
    # Если дашборд уже задал вертикальную легенду и/или увеличенные поля — не затираем
    # (иначе глобальная горизонтальная легенда и margin b=100/r=30 ломают вёрстку).
    layout = fig.layout
    prev_leg = getattr(layout, "legend", None) if layout is not None else None
    prev_m = getattr(layout, "margin", None) if layout is not None else None
    keep_vertical_legend = (
        prev_leg is not None and getattr(prev_leg, "orientation", None) == "v"
    )
    margin_l = 60
    margin_r = 30
    margin_t = 62
    margin_b = 118
    if prev_m is not None:
        for attr, default in (("l", margin_l), ("r", margin_r), ("t", margin_t), ("b", margin_b)):
            v = getattr(prev_m, attr, None)
            if v is not None and float(v) > float(default):
                if attr == "l":
                    margin_l = float(v)
                elif attr == "r":
                    margin_r = float(v)
                elif attr == "t":
                    margin_t = float(v)
                elif attr == "b":
                    margin_b = float(v)

    # Базовый стиль
    layout_kwargs = dict(
        template=None,
        plot_bgcolor=CHART_BG_COLOR,
        paper_bgcolor=CHART_BG_COLOR,
        autosize=True,
        font=dict(
            family="Inter, system-ui, sans-serif",
            color=TABLE_TEXT_COLOR,
            size=13,
        ),
        # text обязателен: иначе во фронтенде Plotly иногда показывает строку «undefined»
        title=dict(
            text="",
            font=dict(color=TABLE_TEXT_COLOR, size=15),
            pad=dict(t=4),
        ),
        margin=dict(l=margin_l, r=margin_r, t=margin_t, b=margin_b),
    )
    if not skip_uniformtext:
        layout_kwargs["uniformtext"] = dict(minsize=8, mode="show")
    if keep_vertical_legend:
        legend_merged = dict(
            font=dict(color=TABLE_TEXT_COLOR, size=12),
            bgcolor="rgba(0,0,0,0)",
            orientation="v",
        )
        if prev_leg is not None:
            for key in (
                "x", "y", "xanchor", "yanchor", "xref", "yref",
                "orientation", "title", "traceorder", "itemsizing",
            ):
                val = getattr(prev_leg, key, None)
                if val is None:
                    continue
                if key == "title" and hasattr(val, "to_plotly_json"):
                    legend_merged[key] = val.to_plotly_json()
                else:
                    legend_merged[key] = val
        layout_kwargs["legend"] = legend_merged
        prev_showlegend = getattr(layout, "showlegend", None) if layout is not None else None
        if prev_showlegend is not None:
            layout_kwargs["showlegend"] = bool(prev_showlegend)
    else:
        # Дефолт — полоска легенды под графиком. Если дашборд уже задал y/yanchor (напр. y<0, yanchor=top),
        # не затирать — иначе легенда снова уезжает «вверх»/в центр после этого вызова.
        legend_base = dict(
            font=dict(color=TABLE_TEXT_COLOR, size=12),
            bgcolor="rgba(0,0,0,0)",
            orientation="h",
            yanchor="bottom",
            y=-0.25,
            xanchor="center",
            x=0.5,
        )
        if prev_leg is not None:
            py = getattr(prev_leg, "y", None)
            ya = getattr(prev_leg, "yanchor", None)
            try:
                py_f = float(py) if py is not None else None
            except (TypeError, ValueError):
                py_f = None
            # Легенда под графиком (y<0) или спец. якорь — не затираем.
            custom_below = (py_f is not None and py_f < 0) or ya == "top"
            # Легенда НАД графиком (типично y≈1…1.15, yanchor=bottom) — тоже сохраняем,
            # иначе глобальный y=-0.25 наезжает на наклонные подписи оси X (ГДРС и т.п.).
            legend_above_plot = (
                py_f is not None
                and py_f >= 0.85
                and str(ya or "").lower() == "bottom"
                and getattr(prev_leg, "orientation", None) == "h"
            )
            if custom_below or legend_above_plot:
                for key in ("x", "y", "xanchor", "yanchor", "xref", "yref", "orientation"):
                    val = getattr(prev_leg, key, None)
                    if val is not None:
                        legend_base[key] = val
            if legend_above_plot:
                margin_t = max(margin_t, 90.0)
                tick_angle = 0.0
                try:
                    xa = fig.layout.xaxis
                    ta = getattr(xa, "tickangle", None) if xa is not None else None
                    if ta is not None:
                        tick_angle = float(ta)
                except (TypeError, ValueError):
                    tick_angle = 0.0
                need_x_pad = abs(tick_angle) >= 25
                user_b = None
                if prev_m is not None and getattr(prev_m, "b", None) is not None:
                    try:
                        user_b = float(prev_m.b)
                    except (TypeError, ValueError):
                        user_b = None
                if need_x_pad:
                    margin_b = max(margin_b, 188.0)
                else:
                    floor_b = 52.0
                    if user_b is not None:
                        margin_b = max(floor_b, user_b)
                    else:
                        margin_b = min(margin_b, 72.0)
        layout_kwargs["margin"] = dict(l=margin_l, r=margin_r, t=margin_t, b=margin_b)
        layout_kwargs["legend"] = legend_base
    fig.update_layout(**layout_kwargs)
    # Подписи на графике — без всплывающих подсказок (требование UX).
    fig.update_layout(hovermode=False)
    try:
        fig.update_traces(hovertemplate="", hoverinfo="skip")
    except Exception:
        try:
            fig.update_traces(hoverinfo="skip")
        except Exception:
            pass

    # Оси X
    fig.update_xaxes(
        showgrid=True,
        gridcolor=CHART_GRID_COLOR,
        linecolor=CHART_AXIS_LINE_COLOR,
        tickfont=dict(color=TABLE_TEXT_COLOR, size=11),
        title=dict(font=dict(color=TABLE_TEXT_COLOR, size=12)),
        zerolinecolor=CHART_ZEROLINE_COLOR,
        automargin=True,
        ticklabelstandoff=8,
    )

    # Оси Y
    fig.update_yaxes(
        showgrid=True,
        gridcolor=CHART_GRID_COLOR,
        linecolor=CHART_AXIS_LINE_COLOR,
        tickfont=dict(color=TABLE_TEXT_COLOR, size=11),
        title=dict(font=dict(color=TABLE_TEXT_COLOR, size=12)),
        zerolinecolor=CHART_ZEROLINE_COLOR,
        automargin=True,
    )

    return fig


def format_million_rub(value, *, decimals: int = 2) -> str:
    """Форматирует сумму в рублях как млн руб. (по умолчанию 2 знака)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    try:
        x = float(value) / MILLION
        d = max(0, int(decimals))
        return f"{x:.{d}f} млн. руб."
    except (TypeError, ValueError):
        return ""


def to_million_rub(value):
    """Возвращает значение в млн руб. (для осей графиков)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value) / MILLION
    except (TypeError, ValueError):
        return None


def _parse_date_cell(v):
    """Парсит ячейку с датой (строка dd.mm.yyyy, yyyy-mm-dd или datetime) в date для сравнения."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, pd.Timestamp):
        return v.date() if pd.notna(v) else None
    if hasattr(v, "date") and callable(getattr(v, "date", None)):
        try:
            return v.date()
        except (TypeError, ValueError):
            pass
    s = str(v).strip()
    if not s or s.lower() in ("nan", "nat", "none", ""):
        return None
    try:
        parsed = pd.to_datetime(s, format="%d.%m.%Y", errors="coerce")
        if pd.notna(parsed):
            return parsed.date() if hasattr(parsed, "date") else parsed
    except (TypeError, ValueError):
        pass
    try:
        parsed = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
        if pd.notna(parsed):
            return parsed.date() if hasattr(parsed, "date") else parsed
    except (TypeError, ValueError):
        pass
    try:
        parsed = pd.to_datetime(s, errors="coerce")
        if pd.notna(parsed):
            return parsed.date() if hasattr(parsed, "date") else parsed
    except (TypeError, ValueError):
        pass
    return None


def style_dataframe_for_dark_theme(
    df: pd.DataFrame,
    days_column: Optional[str] = None,
    finance_deviation_column: Optional[str] = None,
    plan_date_column: Optional[str] = None,
    fact_date_column: Optional[str] = None,
    percent_deviation_gradient_column: Optional[str] = None,
    *,
    extra_days_columns: Optional[tuple] = None,
    days_positive_is_ahead: bool = False,
    days_deviation_gradient: bool = False,
    finance_deviation_abs_min_mln: float = 0.01,
):
    """
    Styler для тёмной темы (`st.dataframe` / `st.table`): фон, контраст, **§4.8** — плотные ячейки.
    """
    if df is None or df.empty:
        return df.style

    # Переименование англоязычных колонок в русские
    rename_map = {c: TABLE_COLUMN_EN_TO_RU.get(c, c) for c in df.columns}
    df = df.rename(columns=rename_map)

    _cell_dense = {
        "background-color": TABLE_BG_COLOR,
        "color": TABLE_TEXT_COLOR,
        "font-size": "13px",
        "padding": "5px 8px",
        "max-width": "28em",
        "white-space": "normal",
        "overflow": "visible",
        "text-overflow": "clip",
        "word-wrap": "break-word",
        "border": TABLE_CELL_BORDER,
    }
    base = df.style.set_properties(**_cell_dense).set_table_styles(
        [
            {
                "selector": "table",
                "props": [
                    ("border-collapse", "collapse"),
                    ("border", "2px solid #799ac0"),
                ],
            },
            {
                "selector": "th",
                "props": [
                    ("background-color", TABLE_HEADER_BG_COLOR),
                    ("color", TABLE_TEXT_COLOR),
                    ("border", TABLE_CELL_BORDER),
                    ("font-size", "13px"),
                    ("padding", "6px 8px"),
                    ("max-width", "11em"),
                    ("white-space", "normal"),
                    ("overflow", "visible"),
                    ("text-overflow", "clip"),
                    ("word-wrap", "break-word"),
                    ("line-height", "1.25"),
                    ("text-align", "center"),
                    ("vertical-align", "bottom"),
                ],
            },
            {"selector": "th *, td *", "props": [("color", TABLE_TEXT_COLOR)]},
        ]
    )

    for _col in df.columns:
        _cc = table_column_css_class(_col)
        if _cc == "col-text":
            base = base.set_properties(
                subset=pd.IndexSlice[:, [_col]],
                **{
                    "text-align": "left",
                    "vertical-align": "top",
                    "white-space": "normal",
                    "overflow": "visible",
                    "text-overflow": "clip",
                    "word-wrap": "break-word",
                },
            )
        else:
            base = base.set_properties(
                subset=pd.IndexSlice[:, [_col]],
                **{
                    "text-align": "center",
                    "vertical-align": "middle",
                    "white-space": "nowrap",
                    "overflow": "visible",
                    "text-overflow": "clip",
                },
            )

    # Подсветка по дням отклонения (одна или несколько колонок «дней»)
    def _parse_signed_days_display(v):
        if v is None:
            return None
        s = str(v).strip()
        if not s or s.lower() in ("nan", "none", "—"):
            return None
        s_num = s.replace("\u2212", "-").replace(",", ".")
        num = pd.to_numeric(s_num, errors="coerce")
        if pd.notna(num):
            return int(round(float(num)))
        m = re.search(r"([+-]?)\s*(\d+)", s)
        if not m:
            return pd.to_numeric(s, errors="coerce")
        val = int(m.group(2))
        sg = m.group(1) or ""
        if sg == "-":
            return -val
        if sg == "+":
            return val
        return val

    def _days_cell_color(series):
        result = []
        for v in series:
            num = _parse_signed_days_display(v)
            if num is None or (isinstance(num, float) and pd.isna(num)):
                result.append(_table_cell_style(TABLE_BG_COLOR, TABLE_TEXT_COLOR))
            elif days_positive_is_ahead:
                if float(num) > 0:
                    result.append(_table_cell_style("#27ae60", "#ffffff"))
                elif float(num) < 0:
                    result.append(_table_cell_style("#c0392b", "#ffffff"))
                else:
                    result.append(_table_cell_style(TABLE_BG_COLOR, TABLE_TEXT_COLOR))
            elif float(num) > 0:
                result.append(_table_cell_style("#c0392b", "#ffffff"))
            else:
                result.append(_table_cell_style("#27ae60", "#ffffff"))
        return result

    def _days_gradient_style(series):
        nums = series.map(_parse_signed_days_display)
        valid = pd.to_numeric(nums, errors="coerce").dropna()
        vmax = float(valid.abs().max()) if not valid.empty else 1.0
        vmax = max(vmax, 1.0)
        out = []
        for v in series:
            num = _parse_signed_days_display(v)
            if num is None or (isinstance(num, float) and pd.isna(num)) or float(num) == 0.0:
                out.append(_table_cell_style(TABLE_BG_COLOR, TABLE_TEXT_COLOR))
                continue
            t = min(abs(float(num)) / vmax, 1.0)
            if days_positive_is_ahead and float(num) > 0:
                r = int(46 + (39 - 46) * t)
                g = int(204 + (174 - 204) * t)
                b = int(113 + (96 - 113) * t)
            elif float(num) < 0 or not days_positive_is_ahead:
                r = int(255 + (192 - 255) * t)
                g = int(179 + (57 - 179) * t)
                b = int(179 + (43 - 179) * t)
            else:
                r, g, b = 46, 204, 113
            fg = "#ffffff"
            out.append(
                _table_cell_style(f"rgb({r},{g},{b})", fg, extra="font-weight: 600")
            )
        return out

    _dev_day_cols = []
    if days_column and days_column in df.columns:
        _dev_day_cols.append(days_column)
    if extra_days_columns:
        for _c in extra_days_columns:
            if _c and _c in df.columns and _c not in _dev_day_cols:
                _dev_day_cols.append(_c)
    for _dc in _dev_day_cols:
        if days_deviation_gradient:
            base = base.apply(
                lambda c, _name=_dc: _days_gradient_style(c)
                if c.name == _name
                else [""] * len(c),
                axis=0,
            )
        else:
            base = base.apply(
                lambda c, _name=_dc: _days_cell_color(c)
                if c.name == _name
                else [""] * len(c),
                axis=0,
            )

    # Подсветка финансовых отклонений
    if finance_deviation_column and finance_deviation_column in df.columns:
        _fin_dev_min = float(finance_deviation_abs_min_mln)

        def _finance_cell_color(series):
            result = []
            for v in series:
                num = None
                try:
                    s = str(v).strip().replace(",", ".")
                    if s and s not in ("", "nan", "None"):
                        num = float(s)
                    else:
                        match = re.search(r"[+-]?\d+[.,]?\d*", str(v))
                        if match:
                            num = float(match.group().replace(",", "."))
                except (TypeError, ValueError):
                    pass
                if num is None or pd.isna(num):
                    result.append(_table_cell_style(TABLE_BG_COLOR, TABLE_TEXT_COLOR))
                elif _fin_dev_min > 0 and abs(float(num)) < _fin_dev_min:
                    result.append(_table_cell_style(TABLE_BG_COLOR, TABLE_TEXT_COLOR))
                elif num >= 0:
                    result.append(_table_cell_style("#c0392b", "#ffffff"))
                else:
                    result.append(_table_cell_style("#27ae60", "#ffffff"))
            return result
        base = base.apply(
            lambda c: _finance_cell_color(c) if c.name == finance_deviation_column else [""] * len(c),
            axis=0,
        )

    # Подсветка дат план/факт
    if plan_date_column and fact_date_column and plan_date_column in df.columns and fact_date_column in df.columns:
        plan_series = df[plan_date_column]
        fact_series = df[fact_date_column]

        def _plan_fact_cell_color(idx):
            plan_val = _parse_date_cell(plan_series.iloc[idx])
            fact_val = _parse_date_cell(fact_series.iloc[idx])
            if plan_val is None or fact_val is None:
                return _table_cell_style(TABLE_BG_COLOR, TABLE_TEXT_COLOR)
            if fact_val < plan_val:
                return _table_cell_style("#27ae60", "#ffffff")
            if fact_val > plan_val:
                return _table_cell_style("#c0392b", "#ffffff")
            return _table_cell_style(TABLE_BG_COLOR, TABLE_TEXT_COLOR)

        def _plan_fact_row_style(series):
            styles = [_plan_fact_cell_color(i) for i in range(len(series))]
            return pd.Series(styles, index=series.index)

        def _apply_plan_fact_style(column):
            if column.name in (plan_date_column, fact_date_column):
                return _plan_fact_row_style(column)
            return pd.Series([""] * len(column), index=column.index)

        base = base.apply(_apply_plan_fact_style, axis=0)

    # Градиент по числовому % отклонения (светло-зелёный → красный) для колонки вроде «Отклонение %»
    if percent_deviation_gradient_column and percent_deviation_gradient_column in df.columns:

        def _pct_gradient_style(series):
            out = []
            nums = pd.to_numeric(series, errors="coerce")
            valid = nums.dropna()
            if valid.empty:
                vmin, vmax = -100.0, 100.0
            else:
                vmin = float(valid.min())
                vmax = float(valid.max())
            span = (vmax - vmin) if vmax != vmin else 1.0
            for v in series:
                num = pd.to_numeric(v, errors="coerce")
                if pd.isna(num):
                    out.append(_table_cell_style(TABLE_BG_COLOR, TABLE_TEXT_COLOR))
                    continue
                t = (float(num) - vmin) / span
                t = max(0.0, min(1.0, t))
                # зелёный → жёлтый → красный
                if t <= 0.5:
                    r = int(46 + (241 - 46) * (t / 0.5))
                    g = int(204 + (196 - 204) * (t / 0.5))
                    b = int(113 + (15 - 113) * (t / 0.5))
                else:
                    u = (t - 0.5) / 0.5
                    r = int(241 + (192 - 241) * u)
                    g = int(196 + (57 - 196) * u)
                    b = int(15 + (43 - 15) * u)
                out.append(
                    _table_cell_style(
                        f"rgb({r},{g},{b})", "#ffffff", extra="font-weight: 600"
                    )
                )
            return out

        base = base.apply(
            lambda c: _pct_gradient_style(c)
            if c.name == percent_deviation_gradient_column
            else [""] * len(c),
            axis=0,
        )

    return base


def _extract_plan_fact_from_row(row: pd.Series, columns: list) -> tuple[Optional[float], Optional[float]]:
    """Числовые план/факт из строки таблицы (по подписи колонки)."""
    plan_n: Optional[float] = None
    fact_n: Optional[float] = None
    for col in columns:
        cl = str(col).casefold()
        if "отклон" in cl:
            continue
        if plan_n is None and "план" in cl and "факт" not in cl:
            plan_n = _parse_finance_value(row.get(col))
        if fact_n is None and "факт" in cl:
            fact_n = _parse_finance_value(row.get(col))
    return plan_n, fact_n


def _fact_vs_plan_font_class(
    *,
    deviation: Optional[float] = None,
    plan: Optional[float] = None,
    fact: Optional[float] = None,
    deviation_is_plan_minus_fact: bool = False,
    neutral_pct: float = DEVIATION_NEUTRAL_PCT,
    abs_neutral_mln: float = 0.01,
) -> Optional[str]:
    """
    ТЗ (стройка / БДДС / БДР): факт < план — красный; ≈ план (±neutral_pct) — жёлтый;
    факт > план — зелёный. Только цвет шрифта, без индикаторов-светофоров.
    """
    rel: Optional[float] = None
    if plan is not None and fact is not None and abs(float(plan)) > 1e-12:
        rel = (float(fact) - float(plan)) / abs(float(plan))
    elif deviation is not None:
        dv = float(deviation)
        if deviation_is_plan_minus_fact:
            dv = -dv
        if plan is not None and abs(float(plan)) > 1e-12:
            rel = dv / abs(float(plan))
        elif abs_neutral_mln > 0:
            if abs(dv) < float(abs_neutral_mln):
                return DEVIATION_CLASS_YELLOW
            return DEVIATION_CLASS_RED if dv < 0 else DEVIATION_CLASS_GREEN
    if rel is None:
        return None
    if rel < -neutral_pct:
        return DEVIATION_CLASS_RED
    if rel > neutral_pct:
        return DEVIATION_CLASS_GREEN
    return DEVIATION_CLASS_YELLOW


def _column_uses_fact_plan_colors(
    col: Any,
    finance_deviation_column: Optional[str],
    *,
    color_fact_column: bool = True,
) -> bool:
    cl = str(col).casefold()
    if finance_deviation_column and col == finance_deviation_column:
        return True
    if "отклон" in cl or "\u0394" in str(col) or " δ" in cl:
        return True
    if "факт" in cl and "план" not in cl:
        return bool(color_fact_column)
    return False


def _is_table_label_column(col: Any) -> bool:
    cl = str(col).casefold().strip()
    return cl in ("проект", "период")


def _parse_finance_value(v) -> Optional[float]:
    """Извлекает число из ячейки (например '0.94 млн руб.' или '-1.20')."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        s = str(v).strip().replace(",", ".")
        if s and s not in ("", "nan", "None"):
            return float(s)
    except (TypeError, ValueError):
        pass
    match = re.search(r"[+-]?\d+[.,]?\d*", str(v))
    if match:
        try:
            return float(match.group().replace(",", "."))
        except (TypeError, ValueError):
            pass
    return None


def _html_cell_sort_attr(val) -> str:
    """data-sort-val для клиентской сортировки (числа, даты как timestamp)."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    if isinstance(val, pd.Timestamp):
        if pd.isna(val):
            return ""
        return f' data-sort-val="{float(val.timestamp())}"'
    num = _parse_finance_value(val)
    if num is not None:
        return f' data-sort-val="{num}"'
    if isinstance(val, (int, float, np.integer, np.floating)):
        fv = float(val)
        if not pd.isna(fv):
            return f' data-sort-val="{fv}"'
    try:
        ts = pd.to_datetime(val, errors="coerce", dayfirst=True)
        if ts is not None and pd.notna(ts) and not isinstance(val, (int, float, np.integer, np.floating)):
            return f' data-sort-val="{float(ts.timestamp())}"'
    except Exception:
        pass
    s = str(val).strip()
    if s and s.lower() not in ("nan", "none", "nat", ""):
        return f' data-sort-val="{html_module.escape(s, quote=True)}"'
    return ""


def budget_table_to_html(
    df: pd.DataFrame,
    finance_deviation_column: Optional[str] = None,
    *,
    deviation_red_if_positive_only: bool = False,
    deviation_red_if_negative: bool = False,
    deviation_color_fact_vs_plan: bool = False,
    expense_overrun_style: bool = False,
    deviation_abs_min_mln: float = 0.01,
    deviation_semaphore_style: bool = False,
    row_kind_column: Optional[str] = None,
    emphasize_row_kinds: tuple[str, ...] = ("project", "total"),
    emphasize_row_font_em: float = 1.12,
    table_caption: str | None = None,
    color_fact_column: bool = True,
    header_font_css: str | None = None,
    group_row_font_css: str | None = None,
    label_columns_font_css: str | None = None,
    total_row_bg_color: str | None = None,
    total_row_font_css: str | None = None,
    table_font_size_px: int = 15,
    table_scroll_max_height_vh: float | None = None,
    table_cell_padding_px: int | None = None,
) -> str:
    """
    Строит HTML таблицы бюджета с раскраской колонки отклонения.

    По умолчанию (финансы бюджета, отклонение = факт − план): значение ≥ 0 — красный шрифт, < 0 — зелёный.

    Если ``deviation_red_if_positive_only=True`` (например, отклонение = план − факт в графике рабочей силы):
    значение > 0 — красный, ≤ 0 — зелёный.

    Раскраска факт/план/отклонение: красный (факт < план), жёлтый (≈ план ±10%), зелёный (факт > план) — только цвет шрифта.

    Если ``deviation_red_if_positive_only=True`` (БДДС/БДР: отклонение = план − факт):
    значение > 0 (факт < план) — красный, ≤ 0 (факт ≥ план) — зелёный.

    Если ``|число| < deviation_abs_min_mln`` (по умолчанию 0.01 млн руб.), ячейка без акцентного цвета — как обычный текст.
    """
    if df is None or df.empty:
        return "<p>Нет данных для отображения.</p>"

    _light_tbl = _budget_table_use_light_theme()
    _tbl_bg = SHOWCASE_TABLE_BG_COLOR if _light_tbl else TABLE_BG_COLOR
    _tbl_text = SHOWCASE_TABLE_TEXT_COLOR if _light_tbl else TABLE_TEXT_COLOR
    _hdr_bg = SHOWCASE_TABLE_HEADER_BG_COLOR if _light_tbl else TABLE_HEADER_BG_COLOR
    _grp_bg = SHOWCASE_TABLE_GROUP_ROW_BG_COLOR if _light_tbl else TABLE_GROUP_ROW_BG_COLOR
    _hdr_css = header_font_css or TABLE_HEADER_FONT_CSS
    _grp_css = group_row_font_css or f"font-weight:700;font-size:{float(emphasize_row_font_em or 1.12):.2f}em;"
    _tot_bg = total_row_bg_color or TABLE_TOTAL_ROW_BG_COLOR
    _tot_font = total_row_font_css or TABLE_TOTAL_ROW_FONT_CSS
    _tbl_px = max(12, int(table_font_size_px or 15))
    _pad_y, _pad_x = (5, 10) if _tbl_px <= 16 else (7, 14)
    if table_cell_padding_px is not None:
        _pad_y = _pad_x = max(2, int(table_cell_padding_px))
    _lbl_col_css = label_columns_font_css or ""
    _scroll_vh = float(table_scroll_max_height_vh) if table_scroll_max_height_vh else None
    wrap_id = "bdt_" + str(id(df))
    _cell_border = SHOWCASE_TABLE_CELL_BORDER if _light_tbl else FINANCE_TABLE_CELL_BORDER
    _green_css = _bd_cell_green_css(light_bg=_light_tbl)
    _red_color = BD_CELL_RED_COLOR_LIGHT if _light_tbl else "hsl(348,100%,63%)"
    _style_css = (
        f'#{wrap_id} table {{ table-layout: auto; font-size: {_tbl_px}px; width: max-content; min-width: 100%; '
        f'border-collapse: separate !important; border-spacing: 0 !important; border: {_cell_border} !important; }}'
        f'#{wrap_id} th, #{wrap_id} td {{ min-width: 11em; max-width: 24em; padding: {_pad_y}px {_pad_x}px; box-sizing: border-box; '
        f'border-right: {_cell_border} !important; border-bottom: {_cell_border} !important; '
        f'border-top: none !important; border-left: none !important; }}'
        f'#{wrap_id} thead tr:first-child th {{ border-top: {_cell_border} !important; }}'
        f'#{wrap_id} tr th:first-child, #{wrap_id} tr td:first-child {{ border-left: {_cell_border} !important; }}'
        f'#{wrap_id} th:first-child, #{wrap_id} td:first-child {{ min-width: 14em; max-width: 32em; }}'
        f'#{wrap_id} th:not(:first-child), #{wrap_id} td:not(:first-child) {{ min-width: 9em; max-width: 16em; }}'
        f'#{wrap_id} td.bd-cell-red, #{wrap_id} td.bd-cell-red * {{ color: {_red_color} !important; }} '
        f'#{wrap_id} td.bd-cell-green, #{wrap_id} td.bd-cell-green * {{ {_green_css} }}'
        f'#{wrap_id} td.bd-cell-yellow, #{wrap_id} td.bd-cell-yellow * {{ color: hsl(48,95%,62%) !important; }}'
        f'#{wrap_id} thead th {{ background-color: {_hdr_bg} !important; color: {_tbl_text} !important; {_hdr_css}; {HTML_TABLE_TH_WRAP_CSS} max-width:11em; }}'
        f'#{wrap_id} tr.bd-group-row td {{ background-color: {_grp_bg} !important; color: {_tbl_text} !important; }}'
        f'#{wrap_id} tbody td {{ {HTML_TABLE_TD_TEXT_CSS} max-width:28em; color: {_tbl_text}; }}'
        f'{f"#{wrap_id} tbody td:first-child, #{wrap_id} tbody td:nth-child(2) {{ {_lbl_col_css} }}" if _lbl_col_css else ""}'
        f'#{wrap_id} tr.bd-total-row td {{ background-color: {_tot_bg} !important; {_tot_font} }}'
        f'#{wrap_id} tr.bd-total-row td, #{wrap_id} tr.bd-total-row td * {{ {_tot_font} }}'
        + (
            f'#{wrap_id} th.bd-fin-dev-col, #{wrap_id} td.bd-fin-dev-col '
            f'{{ min-width: 10.5em; max-width: 12em; {HTML_TABLE_TD_COMPACT_CSS} isolation: isolate; }}'
            if finance_deviation_column
            else ""
        )
        + (
            f'#{wrap_id} .budget-table-scroll {{ height: 100%; max-height: 100%; min-height: 0; '
            f'overflow: auto; -webkit-overflow-scrolling: touch; scrollbar-gutter: stable; }}'
            f'#{wrap_id}.budget-deviation-table-wrap {{ display: flex; flex-direction: column; '
            f'height: 100%; min-height: 0; overflow: hidden; width: 100%; }}'
            f'#{wrap_id} thead th {{ position: sticky; top: 0; z-index: 5; }}'
            f'#{wrap_id} tr.bd-total-row td {{ position: sticky; bottom: 0; z-index: 4; '
            f'box-shadow: 0 -3px 10px rgba(0,0,0,0.35); }}'
            f'#{wrap_id} .budget-table-scroll table {{ width: max-content; min-width: 100%; }}'
            if _scroll_vh
            else ""
        )
        + (
            f'#{wrap_id} th.bd-fin-delta-col, #{wrap_id} td.bd-fin-delta-col '
            f'{{ min-width: 10.5em; max-width: 12em; {HTML_TABLE_TD_COMPACT_CSS} isolation: isolate; }}'
        )
    )
    _wrap_style = (
        "overflow: hidden; min-width: 0; max-width: 100%; margin: 0; padding: 0; height: 100%;"
        if _scroll_vh
        else "overflow-x: auto; overflow-y: visible; min-width: 0; max-width: 100%; margin: 0; padding: 0;"
    )
    parts = [
        _html_table_caption(table_caption),
        f'<div id="{wrap_id}" class="budget-deviation-table-wrap" data-bi-rows="{len(df)}" style="{_wrap_style}">',
        f"<style>{_style_css}</style>",
        (
            f'<div class="budget-table-scroll" data-scroll-vh="{_scroll_vh:.1f}">' if _scroll_vh else ""
        ),
        f'<table class="bi-sortable-table bi-sort-click-only" style="width:100%; border-collapse: collapse; background-color: {_tbl_bg}; color: {_tbl_text}; font-size: {_tbl_px}px;">',
        "<thead><tr>",
    ]
    header_cols = [c for c in df.columns if c != row_kind_column]
    for col in header_cols:
        col_esc = html_module.escape(str(col))
        _col_cls = ""
        if finance_deviation_column and col == finance_deviation_column:
            _col_cls = "bd-fin-dev-col"
        elif "кс-2" in str(col).casefold() and "аванс" in str(col).casefold():
            _col_cls = "bd-fin-delta-col"
        _cc = table_column_css_class(col)
        _col_cls = f"{_col_cls} {_cc}".strip()
        parts.append(
            f'<th class="{_col_cls}" style="padding: {_pad_y}px {_pad_x}px; background-color: {_hdr_bg}; color: {_tbl_text}; {_hdr_css} text-align:center;vertical-align:bottom;" data-sort-label="{col_esc}">'
            f'<span class="bi-sort-label">{col_esc} \u21c5</span></th>'
        )
    parts.append("</tr></thead><tbody>")
    visible_cols = [c for c in df.columns if c != row_kind_column]
    for _, row in df.iterrows():
        row_kind = ""
        if row_kind_column and row_kind_column in df.columns:
            try:
                row_kind = str(row.get(row_kind_column, "")).strip().casefold()
            except Exception:
                row_kind = ""
        is_total_row_st = row_kind == "total" or (
            not row_kind and _row_is_table_total(row, skip_cols={row_kind_column} if row_kind_column else set())
        )
        is_emphasized_row = is_total_row_st or row_kind in {
            str(x).strip().casefold() for x in (emphasize_row_kinds or ())
        }
        _cell_bg = (
            _tot_bg
            if is_total_row_st
            else (TABLE_GROUP_ROW_BG_COLOR if is_emphasized_row else TABLE_BG_COLOR)
        )
        if is_total_row_st:
            row_style = (
                ' class="bd-total-row bd-group-row" style="'
                f"{_tot_font} border-top:3px solid rgba(255,255,255,0.55);"
                'border-bottom:2px solid rgba(255,255,255,0.35);"'
            )
        elif is_emphasized_row:
            row_style = (
                ' class="bd-group-row" style="'
                f"{_grp_css} border-top:1px solid rgba(255,255,255,0.35);\""
            )
        else:
            row_style = ""
        parts.append(f"<tr{row_style}>")
        _plan_n, _fact_n = _extract_plan_fact_from_row(row, visible_cols)
        _dev_is_plan_minus = bool(deviation_red_if_positive_only and not deviation_red_if_negative)
        for col in visible_cols:
            val = row[col]
            val_str = "" if (val is None or (isinstance(val, float) and pd.isna(val))) else str(val)
            val_esc = html_module.escape(val_str)
            _sort_attr = _html_cell_sort_attr(val)
            _is_row_label_col = col == visible_cols[0] or _is_table_label_column(col)
            _label_css = (
                label_columns_font_css
                if label_columns_font_css and _is_row_label_col
                else ""
            )
            if _column_uses_fact_plan_colors(
                col, finance_deviation_column, color_fact_column=color_fact_column
            ):
                num = _parse_finance_value(val)
                cl = str(col).casefold()
                if (
                    finance_deviation_column
                    and col == finance_deviation_column
                    and deviation_color_fact_vs_plan
                    and _plan_n is not None
                    and _fact_n is not None
                ):
                    if abs(float(_fact_n) - float(_plan_n)) < float(deviation_abs_min_mln):
                        cell_class = None
                    elif float(_fact_n) < float(_plan_n):
                        cell_class = DEVIATION_CLASS_GREEN
                    elif float(_fact_n) > float(_plan_n):
                        cell_class = DEVIATION_CLASS_RED
                    else:
                        cell_class = None
                elif (
                    finance_deviation_column
                    and col == finance_deviation_column
                    and deviation_red_if_positive_only
                    and num is not None
                ):
                    if abs(float(num)) < float(deviation_abs_min_mln):
                        cell_class = None
                    else:
                        cell_class = (
                            DEVIATION_CLASS_RED
                            if float(num) > 0
                            else DEVIATION_CLASS_GREEN
                        )
                elif (
                    finance_deviation_column
                    and col == finance_deviation_column
                    and deviation_red_if_negative
                    and num is not None
                ):
                    if abs(float(num)) < float(deviation_abs_min_mln):
                        cell_class = None
                    else:
                        cell_class = (
                            DEVIATION_CLASS_RED
                            if float(num) < 0
                            else DEVIATION_CLASS_GREEN
                        )
                elif "факт" in cl and "план" not in cl:
                    if expense_overrun_style and _plan_n is not None and num is not None:
                        if abs(float(num) - float(_plan_n)) < float(deviation_abs_min_mln):
                            cell_class = None
                        elif float(num) > float(_plan_n):
                            cell_class = DEVIATION_CLASS_RED
                        elif float(num) < float(_plan_n):
                            cell_class = DEVIATION_CLASS_GREEN
                        else:
                            cell_class = DEVIATION_CLASS_YELLOW
                    else:
                        cell_class = _fact_vs_plan_font_class(
                            plan=_plan_n,
                            fact=num,
                            abs_neutral_mln=float(deviation_abs_min_mln),
                        )
                else:
                    cell_class = _fact_vs_plan_font_class(
                        deviation=num,
                        plan=_plan_n,
                        fact=_fact_n,
                        deviation_is_plan_minus_fact=_dev_is_plan_minus,
                        abs_neutral_mln=float(deviation_abs_min_mln),
                    )
                if cell_class:
                    _extra_cls = ""
                    if finance_deviation_column and col == finance_deviation_column:
                        _extra_cls = " bd-fin-dev-col"
                    elif "кс-2" in str(col).casefold() and "аванс" in str(col).casefold():
                        _extra_cls = " bd-fin-delta-col"
                    _cc = table_column_css_class(col)
                    _td_css = HTML_TABLE_TD_COMPACT_CSS if _cc == "col-num" else HTML_TABLE_TD_TEXT_CSS
                    _align = "text-align:center;vertical-align:middle;" if _cc == "col-num" else "text-align:left;vertical-align:top;"
                    parts.append(
                        f'<td class="{cell_class}{_extra_cls} {_cc}" style="padding: {_pad_y}px {_pad_x}px; font-weight: bold; '
                        f'background-color: {_cell_bg}; {_td_css} {_align} '
                        f'box-sizing: border-box;"{_sort_attr}>{val_esc}</td>'
                    )
                else:
                    _cc = table_column_css_class(col)
                    _td_css = HTML_TABLE_TD_COMPACT_CSS if _cc == "col-num" else HTML_TABLE_TD_TEXT_CSS
                    _align = "text-align:center;vertical-align:middle;" if _cc == "col-num" else "text-align:left;vertical-align:top;"
                    _plain_color = "inherit" if is_total_row_st else TABLE_TEXT_COLOR
                    parts.append(
                        f'<td class="{_cc}" style="padding: {_pad_y}px {_pad_x}px; color: {_plain_color}; '
                        f'background-color: {_cell_bg}; {_td_css} {_align} {_label_css}"{_sort_attr}>{val_esc}</td>'
                    )
            else:
                _cc = table_column_css_class(col)
                _td_css = HTML_TABLE_TD_COMPACT_CSS if _cc == "col-num" else HTML_TABLE_TD_TEXT_CSS
                _align = "text-align:center;vertical-align:middle;" if _cc == "col-num" else "text-align:left;vertical-align:top;"
                _plain_color = "inherit" if is_total_row_st else TABLE_TEXT_COLOR
                parts.append(
                    f'<td class="{_cc}" style="padding: {_pad_y}px {_pad_x}px; color: {_plain_color}; background-color: {_cell_bg}; {_td_css} {_align} {_label_css}"{_sort_attr}>{val_esc}</td>'
                )
        parts.append("</tr>")
    parts.append("</tbody></table>")
    if _scroll_vh:
        parts.append("</div>")
    parts.append("</div>")
    return mark_html_table_sortable("".join(parts))


def plan_fact_dates_table_to_html(
    df: pd.DataFrame,
    plan_date_column: str,
    fact_date_column: str,
) -> str:
    """
    Строит HTML таблицы «План и факт окончания ПД/РД» с раскраской только колонки «Факт»:
    факт > план — красный шрифт, факт <= план — зелёный шрифт.
    """
    if df is None or df.empty:
        return "<p>Нет данных для отображения.</p>"
    if plan_date_column not in df.columns or fact_date_column not in df.columns:
        return "<p>Нет колонок плана/факта дат.</p>"

    plan_series = df[plan_date_column]
    fact_series = df[fact_date_column]
    row_styles = []
    for i in range(len(df)):
        plan_val = _parse_date_cell(plan_series.iloc[i])
        fact_val = _parse_date_cell(fact_series.iloc[i])
        if plan_val is None or fact_val is None:
            row_styles.append(None)
        elif fact_val > plan_val:
            row_styles.append("red")
        else:
            row_styles.append("green")

    red_color = "#c0392b"
    green_color = "#27ae60"
    parts = [
        '<div style="overflow-x: auto; min-width: 0; margin: 1em 0;">',
        f'<table class="bi-sortable-table bi-sort-click-only" style="width:100%; border-collapse: collapse; background-color: {TABLE_BG_COLOR}; color: {TABLE_TEXT_COLOR}; font-size: 13px;">',
        "<thead><tr>",
    ]
    for col in df.columns:
        col_esc = html_module.escape(str(col))
        _cc = table_column_css_class(col)
        parts.append(
            f'<th class="{_cc}" style="border: 1px solid rgba(255,255,255,0.3); padding: 6px 8px; min-width: {HTML_TABLE_COL_MIN_EM}em; max-width: 11em; '
            f'{HTML_TABLE_TH_WRAP_CSS} background-color: {TABLE_HEADER_BG_COLOR}; text-align:center;vertical-align:bottom;" data-sort-label="{col_esc}">'
            f'<span class="bi-sort-label">{col_esc} \u21c5</span></th>'
        )
    parts.append("</tr></thead><tbody>")
    for i, (_, row) in enumerate(df.iterrows()):
        parts.append("<tr>")
        row_style = row_styles[i] if i < len(row_styles) else None
        for col in df.columns:
            val = row[col]
            val_str = "" if (val is None or (isinstance(val, float) and pd.isna(val))) else str(val)
            val_esc = html_module.escape(val_str)
            if col == fact_date_column and row_style:
                text_color = red_color if row_style == "red" else green_color
                _cc = table_column_css_class(col)
                parts.append(
                    f'<td class="{_cc}" style="border: 1px solid rgba(255,255,255,0.2); padding: 5px 8px; min-width: {HTML_TABLE_COL_MIN_EM}em; max-width: 14em; '
                    f'{HTML_TABLE_TD_COMPACT_CSS} background-color: {TABLE_BG_COLOR}; color: {text_color}; font-weight: bold; text-align:center;vertical-align:middle;">{val_esc}</td>'
                )
            else:
                _cc = table_column_css_class(col)
                _align = "text-align:left;vertical-align:top;" if _cc == "col-text" else "text-align:center;vertical-align:middle;"
                _tdc = HTML_TABLE_TD_TEXT_CSS if _cc == "col-text" else HTML_TABLE_TD_COMPACT_CSS
                parts.append(
                    f'<td class="{_cc}" style="border: 1px solid rgba(255,255,255,0.2); padding: 5px 8px; min-width: {HTML_TABLE_COL_MIN_EM}em; max-width: 28em; '
                    f'{_tdc} background-color: {TABLE_BG_COLOR}; color: {TABLE_TEXT_COLOR}; {_align}">{val_esc}</td>'
                )
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    return mark_html_table_sortable("".join(parts))


def render_styled_table_to_html(styler, hide_index: bool = True) -> str:
    """
    Возвращает HTML строку стилизованной таблицы для вывода через st.markdown(..., unsafe_allow_html=True).
    """
    if styler is None or (hasattr(styler, "data") and styler.data.empty):
        return "<p>Нет данных для отображения.</p>"
    try:
        _sty = styler
        if hide_index:
            try:
                _sty = styler.hide(axis="index")
            except Exception:
                _sty = styler
        html = _sty.to_html()
        html = mark_html_table_sortable(html)
        border_css = (
            "<style>"
            ".bi-styled-table-wrap table{border-collapse:collapse!important;"
            "border:2px solid #799ac0!important;}"
            ".bi-styled-table-wrap thead th,.bi-styled-table-wrap tbody td{"
            "border:" + TABLE_CELL_BORDER + "!important;}"
            ".bi-styled-table-wrap thead th{text-align:center!important;vertical-align:bottom;}"
            ".bi-styled-table-wrap tbody td{text-align:center;vertical-align:middle;}"
            ".bi-styled-table-wrap tbody td.col-text{text-align:left;vertical-align:top;}"
            "</style>"
        )
        return (
            border_css
            + '<div class="bi-styled-table-wrap" style="overflow-x:auto;min-width:0;margin:0.35em 0 0 0;'
            + "-webkit-overflow-scrolling:touch;\">"
            f"{html}</div>"
        )
    except Exception:
        return ""


def get_report_param_value(report_name: str, parameter_key: str, default: Any = None) -> Any:
    """Возвращает значение параметра отчёта из report_params."""
    try:
        from report_params import get_report_parameter
        param = get_report_parameter(report_name, parameter_key)
        if param and param.get("value") is not None:
            return param["value"]
    except ImportError:
        pass
    return default


def apply_default_filters(report_name: str, user_role: str, filter_widgets: dict) -> dict:
    """Применяет фильтры по умолчанию для отчёта и роли."""
    try:
        from filters import get_default_filters
        default_filters = get_default_filters(user_role, report_name)
        for filter_key, default_value in default_filters.items():
            if filter_key in filter_widgets and filter_widgets[filter_key] is None:
                filter_widgets[filter_key] = default_value
            elif filter_key not in filter_widgets:
                filter_widgets[filter_key] = default_value
    except ImportError:
        pass
    return filter_widgets


def _ru_column_is_integer_days(col) -> bool:
    """Колонки с длительностью/отклонением в днях или разделах — целые, без .00."""
    col_lower = str(col).lower()
    if col_lower.startswith("отклонение ") and any(
        w in col_lower for w in ("начала", "окончания", "длительности")
    ):
        return True
    if "дней" in col_lower or "в днях" in col_lower:
        return True
    if "днях" in col_lower and "отклон" in col_lower:
        return True
    if "отклонение разделов" in col_lower:
        return True
    if "число отклонений" in col_lower:
        return True
    return False


def format_dataframe_as_html(
    df: Optional[pd.DataFrame],
    conditional_cols: Optional[Dict[str, Dict[str, str]]] = None,
    column_colors: Optional[Dict[str, str]] = None,
    cell_color: Optional[pd.DataFrame] = None,
    cell_background: Optional[pd.DataFrame] = None,
    *,
    finance_decimal_places: int = 2,
    bold_row_indices: Optional[set] = None,
    table_scroll_max_height_vh: float | None = None,
) -> str:
    """Форматирует DataFrame в HTML-таблицу для отображения в Streamlit."""
    if df is None or df.empty:
        return "<p>Нет данных для отображения.</p>"

    _fin_dec = max(0, int(finance_decimal_places))
    _bold_ix = bold_row_indices or set()

    def _is_finance_like_column(col_name: Any) -> bool:
        s = str(col_name).lower()
        return any(
            token in s
            for token in (
                "млн",
                "руб",
                "бюджет",
                "budget",
                "%",
                "процент",
                "стоим",
                "сумм",
                "bdds",
                "бддс",
                "бдр",
            )
        )

    def _sanitize_if_name_column(col_name: Any, text: str) -> str:
        cl = str(col_name).lower()
        if any(
            k in cl
            for k in (
                "проект",
                "project",
                "задача",
                "task",
                "назван",
                "name",
                "контрагент",
                "подряд",
                "объект",
            )
        ):
            return sanitize_display_label(text)
        return text

    # §4.8: плотные ячейки — как `budget_table_to_html` / `style_dataframe_for_dark_theme`
    _th = (
        f"padding:6px 8px;background-color:{TABLE_HEADER_BG_COLOR};color:{TABLE_TEXT_COLOR};"
        f"min-width:{HTML_TABLE_COL_MIN_EM}em;max-width:11em;"
        f"{TABLE_HEADER_FONT_CSS}{HTML_TABLE_TH_WRAP_CSS}"
    )
    _td_base = (
        f"padding:5px 8px;border:1px solid rgba(255,255,255,0.15);background-color:{TABLE_BG_COLOR};"
        f"color:{TABLE_TEXT_COLOR};font-size:13px;min-width:{HTML_TABLE_COL_MIN_EM}em;max-width:{HTML_TABLE_TD_MAX_EM}em;"
        f"{HTML_TABLE_TD_TEXT_CSS}"
    )
    _td_group = _td_base.replace(TABLE_BG_COLOR, TABLE_GROUP_ROW_BG_COLOR)
    _scroll_vh = float(table_scroll_max_height_vh) if table_scroll_max_height_vh else None
    if _scroll_vh:
        _scroll_vh = max(30.0, min(85.0, _scroll_vh))
    _tbl_open = (
        f"<table class='bi-sortable-table bi-sort-click-only' style='width:100%;min-width:max-content;border-collapse:collapse;background-color:{TABLE_BG_COLOR};"
        f"color:{TABLE_TEXT_COLOR};font-size:13px;'>"
    )
    if _scroll_vh:
        html_table = (
            f'<div class="fc-table-scroll-wrap" data-bi-rows="{len(df)}">'
            f"<style>"
            f".fc-table-scroll-wrap{{display:block;width:100%;max-width:100%;margin:0.35em 0 0 0;"
            f"height:100%;max-height:100%;min-height:0;"
            f"overflow-x:auto;overflow-y:auto;-webkit-overflow-scrolling:touch;"
            f"scrollbar-gutter:stable;scrollbar-width:thin;scrollbar-color:#4a5568 #1a1c23;"
            f"border:1px solid rgba(255,255,255,0.25);border-radius:10px;}}"
            f".fc-table-scroll-wrap thead th{{position:sticky;top:0;z-index:5;"
            f"background-color:{TABLE_HEADER_BG_COLOR}!important;}}"
            f"</style>"
            f"<div class='fc-table-scroll-inner' style='min-width:0;'>"
            + _tbl_open
        )
    else:
        html_table = (
            "<div class='bd-table-wrap' style='width:100%;overflow-x:auto;min-width:0;-webkit-overflow-scrolling:touch;'>"
            + _tbl_open
        )
    html_table += "<thead><tr>"
    for col in df.columns:
        col_escaped = html_module.escape(ru_column_header(col))
        _cc = table_column_css_class(col)
        html_table += (
            f"<th class='{_cc}' style='{_th}' data-sort-label='{col_escaped}'>"
            f"<span class='bi-sort-label'>{col_escaped} \u21c5</span></th>"
        )
    html_table += "</tr></thead><tbody>"
    for idx, row in df.iterrows():
        _is_tot = idx in _bold_ix or _row_is_table_total(row)
        if _is_tot:
            html_table += f"<tr class='bd-total-row' style='{TABLE_TOTAL_ROW_FONT_CSS}'>"
        else:
            html_table += "<tr>"
        for col in df.columns:
            value = row[col]
            is_scalar = pd.api.types.is_scalar(value)
            if conditional_cols and col in conditional_cols:
                cond_config = conditional_cols[col]
                pos_color = cond_config.get("positive_color", "#ff4444")
                neg_color = cond_config.get("negative_color", "#44ff44")
                col_lower = str(col).lower()
                if is_scalar and not (isinstance(value, (int, float)) and pd.isna(value)):
                    if isinstance(value, (int, float)):
                        if value > 0:
                            color = pos_color
                        elif value < 0:
                            color = neg_color
                        else:
                            color = TABLE_TEXT_COLOR
                        if _ru_column_is_integer_days(col):
                            formatted_value = f"{int(round(float(value), 0))}"
                        elif isinstance(value, float):
                            formatted_value = (
                                f"{float(value):.{_fin_dec}f}"
                                if _is_finance_like_column(col_lower)
                                else f"{value:.2f}"
                            )
                        else:
                            formatted_value = f"{int(value)}"
                    else:
                        if _ru_column_is_integer_days(col):
                            try:
                                fv = float(str(value).replace(",", ".").replace(" ", ""))
                                formatted_value = f"{int(round(fv, 0))}"
                                color = (
                                    pos_color
                                    if fv > 0
                                    else (neg_color if fv < 0 else TABLE_TEXT_COLOR)
                                )
                            except (TypeError, ValueError):
                                formatted_value = str(value) if value != "" else "0"
                                color = TABLE_TEXT_COLOR
                        else:
                            formatted_value = str(value) if value != "" else "0"
                            color = TABLE_TEXT_COLOR
                else:
                    formatted_value = "0" if (is_scalar and pd.isna(value)) else str(value)
                    color = neg_color
                formatted_value = html_module.escape(
                    _sanitize_if_name_column(col, str(formatted_value))
                )
                _bg_extra = ""
                if cell_background is not None and col in cell_background.columns:
                    try:
                        _bg = cell_background.at[idx, col]
                        if isinstance(_bg, str):
                            _bg_s = _bg.strip()
                            if _bg_s.startswith("#") or _bg_s.startswith("rgba") or _bg_s.startswith("rgb"):
                                _bg_extra = f"background-color:{_bg_s}!important;"
                    except Exception:
                        pass
                _cc_td = table_column_css_class(col)
                if _is_tot:
                    # Итоговая строка: фон и шрифт как у соседних итоговых ячеек,
                    # но цвет значения оставляем красным/зелёным.
                    _cond_base = (
                        _td_group.replace(
                            TABLE_GROUP_ROW_BG_COLOR, TABLE_TOTAL_ROW_BG_COLOR
                        )
                        + TABLE_TOTAL_ROW_FONT_CSS
                    )
                    _td_st = _cond_base + _bg_extra + f"color:{color};"
                else:
                    _td_st = _td_base + _bg_extra + f"color:{color};font-weight:bold;"
                if _cc_td == "col-num":
                    _td_st = _td_st.replace(HTML_TABLE_TD_TEXT_CSS, HTML_TABLE_TD_COMPACT_CSS) + "text-align:center;vertical-align:middle;"
                else:
                    _td_st += "text-align:left;vertical-align:top;"
                html_table += f"<td class='{_cc_td}' style='{_td_st}'>{formatted_value}</td>"
            else:
                if isinstance(value, (int, float)) and is_scalar and not pd.isna(value):
                    col_lower = str(col).lower()
                    # Сначала «в днях» — иначе «отклонения» попадут под денежное .2f
                    if _ru_column_is_integer_days(col):
                        formatted_value = f"{int(round(float(value), 0))}"
                    elif _is_finance_like_column(col_lower):
                        formatted_value = f"{float(value):.{_fin_dec}f}"
                    elif "отклонен" in col_lower or "deviation" in col_lower:
                        formatted_value = f"{int(round(float(value), 0))}"
                    elif isinstance(value, float) and (value % 1 != 0 or abs(value) < 1):
                        formatted_value = f"{value:.2f}"
                    else:
                        formatted_value = f"{int(value)}"
                elif _ru_column_is_integer_days(col) and is_scalar and value not in ("", None) and not (
                    isinstance(value, (int, float)) and pd.isna(value)
                ):
                    try:
                        fv = float(str(value).replace(",", ".").replace(" ", ""))
                        formatted_value = f"{int(round(fv, 0))}"
                    except (TypeError, ValueError):
                        formatted_value = "" if pd.isna(value) else str(value)
                else:
                    formatted_value = "" if (is_scalar and pd.isna(value)) else str(value)
                formatted_value = html_module.escape(
                    _sanitize_if_name_column(col, str(formatted_value))
                )
                cell_style = _td_group if _is_tot else _td_base
                if _is_tot:
                    cell_style = _td_group.replace(
                        TABLE_GROUP_ROW_BG_COLOR, TABLE_TOTAL_ROW_BG_COLOR
                    )
                    cell_style += TABLE_TOTAL_ROW_FONT_CSS
                if column_colors and col in column_colors:
                    cell_style += f"color:{column_colors[col]};"
                if cell_color is not None and col in cell_color.columns:
                    try:
                        _cc = cell_color.at[idx, col]
                        if isinstance(_cc, str) and _cc.startswith("#"):
                            cell_style += f"color:{_cc};font-weight:600;"
                    except Exception:
                        pass
                if cell_background is not None and col in cell_background.columns:
                    try:
                        _bg = cell_background.at[idx, col]
                        if isinstance(_bg, str):
                            _bg_s = _bg.strip()
                            if _bg_s.startswith("#") or _bg_s.startswith("rgba") or _bg_s.startswith("rgb"):
                                cell_style += f"background-color:{_bg_s}!important;"
                    except Exception:
                        pass
                _cc = table_column_css_class(col)
                if _cc == "col-num":
                    cell_style = cell_style.replace(HTML_TABLE_TD_TEXT_CSS, HTML_TABLE_TD_COMPACT_CSS) + "text-align:center;vertical-align:middle;"
                else:
                    cell_style += "text-align:left;vertical-align:top;"
                html_table += f"<td class='{_cc}' style='{cell_style}'>{formatted_value}</td>"
        html_table += "</tr>"
    if _scroll_vh:
        html_table += "</tbody></table></div></div>"
    else:
        html_table += "</tbody></table></div>"
    return mark_html_table_sortable(html_table)


def load_custom_css() -> None:
    """Загружает CSS. В showcase — светлая тема (``showcase/theme.py``), иначе production."""
    from pathlib import Path

    try:
        from config import is_showcase_mode
    except Exception:
        is_showcase_mode = lambda: False  # type: ignore[assignment,misc]

    if is_showcase_mode():
        try:
            from showcase.theme import load_showcase_theme

            load_showcase_theme()
        except Exception:
            pass
        base = Path(__file__).resolve().parent
        for name in ("bi-responsive.css",):
            css_path = base / "static" / "css" / name
            if css_path.exists():
                with open(css_path, encoding="utf-8") as f:
                    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
        st.markdown(BI_TABLE_LAYOUT_CSS + BI_RESPONSIVE_DASHBOARD_CSS, unsafe_allow_html=True)
        return

    base = Path(__file__).resolve().parent
    for name in ("style.css", "bi-responsive.css"):
        css_path = base / "static" / "css" / name
        if css_path.exists():
            with open(css_path, encoding="utf-8") as f:
                st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    st.markdown(BI_TABLE_LAYOUT_CSS + BI_RESPONSIVE_DASHBOARD_CSS, unsafe_allow_html=True)


def dataframe_to_csv_bytes_for_excel(
    df: pd.DataFrame,
    *,
    sep: str = ";",
) -> bytes:
    """
    CSV для открытия в Microsoft Excel: UTF-8 с BOM и разделитель «;»
    (типичные региональные настройки RU — запятая как десятичный разделитель).
    """
    buf = io.BytesIO()
    df.to_csv(buf, index=False, sep=sep, encoding="utf-8-sig")
    return buf.getvalue()


def _excel_safe_sheet_name(name: str) -> str:
    """Имя листа Excel ≤31 символа, без символов []:*?/\\."""
    s = str(name or "Данные").strip() or "Данные"
    for ch in r"[]:*?/\ ":
        s = s.replace(ch, "_")
    s = "".join(c for c in s if ord(c) >= 32)[:31]
    return s or "Data"


def dataframe_to_xlsx_bytes(df: pd.DataFrame, *, sheet_name: str = "Данные") -> bytes:
    """Таблица в формате .xlsx (движок openpyxl из зависимостей проекта)."""
    buf = io.BytesIO()
    safe = _excel_safe_sheet_name(sheet_name)
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=safe)
    return buf.getvalue()


def _export_file_stem(name: str) -> str:
    """Имя файла без пути и без расширения .csv/.xlsx (для пары выгрузок)."""
    from pathlib import Path

    s = str(name or "export").strip()
    s = Path(s).name
    for suf in (".csv", ".xlsx", ".xls"):
        if s.lower().endswith(suf):
            s = s[: -len(suf)]
            break
    return s or "export"


def _download_button_compat(
    *,
    label: str,
    data: bytes,
    file_name: str,
    mime: str,
    key: str,
    help: Optional[str] = None,
    on_click=None,
) -> None:
    """st.download_button с опциональным on_click; без on_click на старых Streamlit."""
    kw: Dict[str, Any] = {
        "label": label,
        "data": data,
        "file_name": file_name,
        "mime": mime,
        "key": key,
    }
    if help is not None:
        kw["help"] = help
    if on_click is not None:
        try:
            st.download_button(**kw, on_click=on_click)
        except TypeError:
            st.download_button(**kw)
    else:
        st.download_button(**kw)


def _html_body_without_style(html: str) -> str:
    return re.sub(r"<style[^>]*>.*?</style>", "", html or "", flags=re.I | re.S)


def _scroll_box_table_html(html: str) -> bool:
    """Таблицы с вертикальной прокруткой: единый scroll-box + кнопка сразу под ним."""
    b = _html_body_without_style(html)
    return (
        "fc-table-scroll-wrap" in b
        or "pd-dynamics-scroll-wrap" in b
        or "pred-detail-wrap" in b
        or ("budget-deviation-table-wrap" in b and "budget-table-scroll" in b)
    )


def _scroll_box_height_px(html: str, *, cap: int = 640) -> int:
    """Высота scroll-box под iframe: для budget-table-scroll — по vh из разметки таблицы."""
    _body = html or ""
    if "budget-table-scroll" in _body:
        _m_vh = re.search(r'data-scroll-vh="([\d.]+)"', _body) or re.search(
            r"max-height:\s*([\d.]+)vh", _body
        )
        if _m_vh:
            _vh = float(_m_vh.group(1))
            return int(min(cap, max(280, _vh * 10 + 56)))
    if "pd-dynamics-scroll-wrap" in _body:
        _rows_m = re.search(r'data-bi-rows="(\d+)"', html or "")
        _rows_n = int(_rows_m.group(1)) if _rows_m else 0
        _est = 84 + _rows_n * 34
        return int(min(720, max(520, _est)))
    _rows_m = re.search(r'data-bi-rows="(\d+)"', html or "")
    _rows_n = int(_rows_m.group(1)) if _rows_m else 0
    _est = 84 + _rows_n * 34
    return min(cap, max(220, _est))




def _render_pd_dynamics_html_table(
    html: str,
    export_df: pd.DataFrame | None,
    *,
    file_stem: str,
    key_prefix: str,
    popover_key: str,
) -> None:
    """Таблица ПД: фиксированная высота iframe до кнопки «Скачать таблицу»."""
    from dashboards.table_sort_inject import render_sortable_html_block

    _pd_h = int(_scroll_box_height_px(html))
    _wrap_key = "bitblwrap_" + str(key_prefix).replace(" ", "_")
    if "data-pd-box-h=" not in (html or ""):
        html = (html or "").replace(
            "pd-dynamics-scroll-wrap",
            f'pd-dynamics-scroll-wrap" data-pd-box-h="{_pd_h}',
            1,
        )
    st.markdown(
        "<style>"
        f"div[class*='st-key-{_wrap_key}'] div[data-testid='stVerticalBlock']{{gap:0!important;}}"
        f"div[class*='st-key-{_wrap_key}'] div[data-testid='stElementContainer']:has(iframe){{"
        f"height:{_pd_h}px!important;min-height:{_pd_h}px!important;max-height:{_pd_h}px!important;"
        "margin:0!important;padding:0!important;overflow:hidden!important;width:100%!important;}}"
        f"div[class*='st-key-{_wrap_key}'] iframe{{"
        f"height:{_pd_h}px!important;min-height:{_pd_h}px!important;width:100%!important;"
        "max-width:100%!important;display:block!important;border:0!important;}}"
        f"div[class*='st-key-{_wrap_key}'] [data-testid='stPopover']{{margin-top:8px!important;}}"
        "</style>",
        unsafe_allow_html=True,
    )
    try:
        _outer = st.container(border=False, gap=None, key=_wrap_key)
    except TypeError:
        _outer = st.container(border=False)
    with _outer:
        try:
            render_sortable_html_block(html, compact_iframe=True)
        except Exception:
            st.markdown(html, unsafe_allow_html=True)
        if export_df is not None:
            render_dataframe_excel_csv_downloads(
                export_df,
                file_stem=file_stem,
                key_prefix=key_prefix,
                popover_key=popover_key,
            )

def render_report_html_table(
    html: str,
    *,
    export_df: pd.DataFrame | None = None,
    file_stem: str = "table_export",
    key_prefix: str | None = None,
) -> None:
    """HTML-таблица: клиентская сортировка по колонкам + экспорт CSV/XLSX."""
    if not html or not str(html).strip():
        return
    html = mark_html_table_sortable(html)
    if "bi_report_table_responsive_css" not in st.session_state:
        st.session_state.bi_report_table_responsive_css = True
        st.markdown(
            "<style>"
            "div[data-testid='stElementContainer']:has(iframe){max-width:100%!important;overflow:visible!important;}"
            "iframe[title='streamlit_components_v1']{max-width:100%!important;}"
            ".rendered-table-wrap,.exec-doc-table-wrap,.bi-styled-table-wrap,.gdrs-table-wrap{"
            "overflow-x:auto!important;-webkit-overflow-scrolling:touch;}"
            "</style>",
            unsafe_allow_html=True,
        )
    _kp = key_prefix or f"tbl_{_export_file_stem(file_stem)}"
    _pop_key = f"{_kp}_dl"
    _wrap_key = "bitblwrap_" + str(_kp).replace(' ', '_')
    if file_stem == "pd_dynamics_table":
        _render_pd_dynamics_html_table(
            html,
            export_df,
            file_stem=file_stem,
            key_prefix=_kp,
            popover_key=_pop_key,
        )
        return
    if "bi_tbl_wrap_scoped_css" not in st.session_state:
        st.session_state.bi_tbl_wrap_scoped_css = True
        st.markdown(
            "<style>"
            'div[class*="st-key-bitblwrap_"] div[data-testid="stVerticalBlock"]{gap:0.1rem!important;}'
            'div[class*="st-key-bitblwrap_"] div[data-testid="stElementContainer"]:has(iframe){margin-bottom:0!important;padding-bottom:0!important;}'
            'div[class*="st-key-bitblwrap_"] div[data-testid="stElementContainer"]:has([data-testid="stHtml"]){margin-bottom:0!important;padding-bottom:0!important;}'
            'div[class*="st-key-bitblwrap_"] [data-testid="stPopover"]{margin-top:0!important;padding-top:0!important;}'
            "</style>",
            unsafe_allow_html=True,
        )
    _compact_tbl = (
        "pf-covenant-table-wrap" in (html or "")
        or "pf-dates-scroll-wrap" in (html or "")
        or "pf-dates-table-wrap" in (html or "")
        or "pred-detail-wrap" in (html or "")
        or (
            "budget-deviation-table-wrap" in (html or "")
            and "budget-table-scroll" in (html or "")
        )
        or file_stem in (
            "plan_fact_dates", "plan_fact_covenant", "predpisania", "debit_credit", "executive_docs",
            "forecast_bddcs_financier_status", "gdrs", "budget", "dev_reasons", "gantt_schedule",
        )
        or "exec-doc-table-wrap" in (html or "")
        or "bi-styled-table-wrap" in (html or "")
        or "rendered-table-wrap" in (html or "")
        or "dev-reasons-wrap" in (html or "")
        or "gdrs-table-wrap" in (html or "")
        or "gdrs-summary-table-wrap" in (html or "")
        or "gdrs-matrix-table" in (html or "")
        or "bi-sortable-table" in (html or "")
        or "fc-table-scroll-wrap" in (html or "")
    )

    def _render_table_block() -> None:
        try:
            from dashboards.table_sort_inject import render_sortable_html_block

            render_sortable_html_block(html, compact_iframe=_compact_tbl)
        except Exception:
            st.markdown(html, unsafe_allow_html=True)

    if _compact_tbl and _scroll_box_table_html(html):
        _scroll_tbl = True
        st.markdown(
            "<style>"
            ".bi-sortable-html-root:has(.pred-detail-wrap),.bi-sortable-html-root:has(.fc-table-scroll-wrap),.bi-sortable-html-root:has(.budget-table-scroll){overflow:visible!important;overflow-x:hidden!important;}"
            ".pred-detail-wrap{height:min(70vh,520px)!important;max-height:min(70vh,520px)!important;"
            "overflow-y:scroll!important;overflow-x:auto!important;scrollbar-gutter:stable;-webkit-overflow-scrolling:touch;}"
            ".fc-table-scroll-wrap{height:100%!important;max-height:100%!important;min-height:0!important;"
            "overflow-y:auto!important;overflow-x:auto!important;scrollbar-gutter:stable;-webkit-overflow-scrolling:touch;}"
            ".pd-dynamics-scroll-wrap{height:100%!important;max-height:100%!important;min-height:100%!important;"
            "overflow-y:auto!important;overflow-x:auto!important;scrollbar-gutter:stable;-webkit-overflow-scrolling:touch;"
            "box-sizing:border-box!important;}"
            "div[data-testid='stElementContainer']:has(iframe){overflow:visible!important;margin:0!important;padding:0!important;"
            "max-width:100%!important;height:auto!important;min-height:0!important;}"
            "div[data-testid='stElementContainer']:has(iframe) iframe{display:block!important;margin:0!important;padding:0!important;"
            "overflow:hidden!important;max-width:100%!important;vertical-align:top!important;}"
            "div[data-testid='stElementContainer']:has(iframe){margin-bottom:0!important;padding-bottom:0!important;}"
            "[data-testid='stPopover']{margin-top:0.05rem!important;margin-bottom:0.5rem!important;padding:0!important;}"
            "@media (max-width:900px){.pred-detail-wrap{height:min(55vh,420px)!important;max-height:min(55vh,420px)!important;}"
            ".fc-table-scroll-wrap{height:100%!important;max-height:100%!important;}}"
            "</style>",
            unsafe_allow_html=True,
        )
    if _compact_tbl and "pf-covenant-table-wrap" in (html or ""):
        st.markdown(
            "<style>"
            "div[data-testid='stElementContainer']:has(iframe){width:100%!important;max-width:100%!important;"
            "min-width:0!important;margin:0!important;padding:0!important;}"
            "iframe[title='streamlit_components_v1']{width:100%!important;max-width:100%!important;display:block!important;}"
            "div[data-testid='stVerticalBlock']:has(iframe){width:100%!important;max-width:100%!important;}"
            "</style>",
            unsafe_allow_html=True,
        )
    if _compact_tbl and file_stem == "pd_dynamics_table":
        st.markdown(
            "<style>"
            "[data-testid='stMainBlockContainer'] div[class*='st-key-bitblwrap_pd_dyn_tbl'],"
            "div[class*='st-key-bitblwrap_pd_dyn_tbl'],"
            "div[class*='st-key-bitblwrap_pd_dyn_tbl'] div[data-testid='stVerticalBlock'],"
            "div[class*='st-key-bitblwrap_pd_dyn_tbl'] div[data-testid='stElementContainer'],"
            "div[class*='st-key-bitblwrap_pd_dyn_tbl'] div[data-testid='stElementContainer']:has(iframe),"
            "div[class*='st-key-bitblwrap_pd_dyn_tbl'] iframe,"
            "div[class*='st-key-bitblwrap_pd_dyn_tbl'] iframe[title='streamlit_components_v1']"
            "{width:100%!important;max-width:100%!important;min-width:0!important;display:block!important;}"
            "</style>",
            unsafe_allow_html=True,
        )
    if _compact_tbl:
        _scroll_box = _scroll_box_table_html(html)
        st.markdown(
            "<style>"
            "div[data-testid='stHtml'],div[data-testid='stElementContainer']:has(iframe){"
            "margin:0!important;padding:0!important;max-width:100%!important;min-width:0!important;}"
            "div[data-testid='stHtml'] iframe,iframe[title='streamlit_components_v1']{"
            "display:block!important;margin:0!important;padding:0!important;border:0!important;"
            "width:100%!important;max-width:100%!important;min-width:0!important;vertical-align:top!important;}"
            "div[data-testid='stElementContainer']:has(iframe[title='streamlit_components_v1']),"
            "div[data-testid='stElementContainer']:has([data-testid='stHtml']) "
            "{margin:0!important;padding:0!important;overflow:visible!important;}"
            "div[data-testid='stExpander'] details[open]>div{padding-bottom:0!important;"
            "max-width:100%!important;overflow-x:auto!important;min-width:0!important;}"
            "</style>",
            unsafe_allow_html=True,
        )
        if _scroll_box and "pd-dynamics-scroll-wrap" not in _html_body_without_style(html):
            # a29a014: scroll-box + кнопка сразу под нim (fc / pred / budget scroll).
            _fc_box_h = _scroll_box_height_px(html)
            try:
                _tbl_outer = st.container(border=False, gap=None, key=_wrap_key)
            except TypeError:
                _tbl_outer = st.container(border=False)
            with _tbl_outer:
                try:
                    _tbl_box = st.container(border=False, height=_fc_box_h, gap=None)
                except TypeError:
                    _tbl_box = st.container(border=False)
                with _tbl_box:
                    _render_table_block()
                if export_df is not None:
                    render_dataframe_excel_csv_downloads(
                        export_df,
                        file_stem=file_stem,
                        key_prefix=_kp,
                        popover_key=_pop_key,
                    )
            return
        try:
            _tbl_block = st.container(border=False, gap="xxsmall", key=_wrap_key)
        except TypeError:
            try:
                _tbl_block = st.container(border=False, gap=None)
            except TypeError:
                _tbl_block = st.container(border=False)
        with _tbl_block:
            _render_table_block()
            if export_df is not None:
                render_dataframe_excel_csv_downloads(
                    export_df,
                    file_stem=file_stem,
                    key_prefix=_kp,
                    popover_key=_pop_key,
                )
        return

    if "budget-deviation-table-wrap" in (html or ""):
        st.markdown(
            "<style>"
            "div[data-testid='stHtml']{margin:0!important;padding:0!important;}"
            "div[data-testid='stHtml'] iframe{display:block;margin:0!important;padding:0!important;}"
            "div[data-testid='stElementContainer']:has([data-testid='stHtml']) "
            "{margin-bottom:0!important;padding-bottom:0!important;}"
            "div[data-testid='stVerticalBlock']:has([data-testid='stPopover']) "
            "{margin-top:0!important;padding-top:0!important;}"
            "</style>",
            unsafe_allow_html=True,
        )

    try:
        _tbl_block = st.container(border=False, gap="xxsmall", key=_wrap_key)
    except TypeError:
        try:
            _tbl_block = st.container(border=False, gap=None)
        except TypeError:
            _tbl_block = st.container(border=False)
    with _tbl_block:
        _render_table_block()
        if export_df is not None:
            render_dataframe_excel_csv_downloads(
                export_df,
                file_stem=file_stem,
                key_prefix=_kp,
                popover_key=_pop_key,
            )


def render_dataframe_excel_csv_downloads(
    df: pd.DataFrame,
    *,
    file_stem: str,
    key_prefix: str,
    csv_label: str = "Скачать CSV (для Excel)",
    popover_label: str = "Скачать таблицу",
    popover_key: str | None = None,
    on_csv_click=None,
    on_xlsx_click=None,
) -> None:
    """
    Одна кнопка-поповер «Скачать таблицу»: внутри — выбор формата (CSV для Excel или .xlsx).
    CSV: UTF-8 BOM и разделитель «;» (типичные региональные настройки RU).
    """
    if df is None or not hasattr(df, "columns"):
        return
    try:
        if df.empty:
            return
    except Exception:
        return
    stem = _export_file_stem(file_stem)
    csv_bytes = dataframe_to_csv_bytes_for_excel(df)
    xlsx_bytes = dataframe_to_xlsx_bytes(df, sheet_name="Данные")
    _pk = (popover_key or f"{key_prefix}_dl").replace(" ", "_")
    with st.popover(popover_label, key=_pk):
        _download_button_compat(
            label=csv_label,
            data=csv_bytes,
            file_name=f"{stem}.csv",
            mime="text/csv",
            key=f"{key_prefix}_csv",
            on_click=on_csv_click,
        )
        _download_button_compat(
            label="Скачать Excel (.xlsx)",
            data=xlsx_bytes,
            file_name=f"{stem}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}_xlsx",
            on_click=on_xlsx_click,
        )
