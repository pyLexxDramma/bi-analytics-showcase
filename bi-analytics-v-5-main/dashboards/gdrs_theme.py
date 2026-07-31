# -*- coding: utf-8 -*-
"""Локальные палитры ГДРС (тёмная / светлая) без смены глобальных констант utils."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GdrsTheme:
    name: str
    page_bg: str
    surface: str
    text: str
    muted: str
    border: str
    table_bg: str
    table_text: str
    table_header_bg: str
    table_header_text: str
    table_header_font_css: str
    chart_bg: str
    chart_axis: str
    chart_grid: str
    bar_plan: str
    bar_fact: str
    bar_plan_text: str
    bar_fact_text: str
    line_plan: str
    line_fact: str
    bad: str
    good: str
    neutral: str
    pie_text_in: str
    pie_text_out: str
    pie_legend: str
    pie_line: str


GDRS_THEME_DARK = GdrsTheme(
    name="dark",
    page_bg="#0e1117",
    surface="#161f2b",
    text="#fafafa",
    muted="#8899aa",
    border="rgba(255,255,255,0.3)",
    table_bg="#161f2b",
    table_text="#fafafa",
    table_header_bg="#17314b",
    table_header_text="#86efac",
    table_header_font_css="color:#86efac;font-weight:800;",
    chart_bg="#161f2b",
    chart_axis="rgba(255,255,255,0.25)",
    chart_grid="rgba(255,255,255,0.08)",
    bar_plan="#29b6f6",
    bar_fact="#46d68a",
    bar_plan_text="#cfe9fa",
    bar_fact_text="#cfe9fa",
    line_plan="#29b6f6",
    line_fact="#ff8c2d",
    bad="#ff5454",
    good="#46d68a",
    neutral="#8899aa",
    pie_text_in="#ffffff",
    pie_text_out="#e8eef5",
    pie_legend="#e8eef5",
    pie_line="rgba(15,23,42,0.9)",
)

GDRS_THEME_LIGHT = GdrsTheme(
    name="light",
    page_bg="#ffffff",
    surface="#ffffff",
    text="#111827",
    muted="#6b7280",
    border="#e5e7eb",
    table_bg="#ffffff",
    table_text="#111827",
    table_header_bg="#f9fafb",
    table_header_text="#111827",
    table_header_font_css="color:#111827;font-weight:800;",
    chart_bg="#ffffff",
    chart_axis="#cbd5e1",
    chart_grid="#e5e7eb",
    bar_plan="#2563eb",
    bar_fact="#15803d",
    bar_plan_text="#1e3a8a",
    bar_fact_text="#14532d",
    line_plan="#2563eb",
    line_fact="#ea580c",
    bad="#b91c1c",
    good="#15803d",
    neutral="#6b7280",
    pie_text_in="#ffffff",
    pie_text_out="#111827",
    pie_legend="#111827",
    pie_line="#ffffff",
)


def get_gdrs_theme(name: str = "dark") -> GdrsTheme:
    if str(name or "").strip().lower() == "light":
        return GDRS_THEME_LIGHT
    return GDRS_THEME_DARK


def gdrs_deviation_vs_plan_text_and_color(plan_v, fact_v, theme: GdrsTheme) -> tuple[str, str]:
    """Подпись отклонения (факт − план) с цветами палитры."""
    import pandas as pd

    p = float(pd.to_numeric(plan_v, errors="coerce") or 0)
    f = float(pd.to_numeric(fact_v, errors="coerce") or 0)
    d = int(round(f - p))
    if f < p:
        return f"{d:d}", theme.bad
    if f > p:
        return f"{d:+d}", theme.good
    return "0", theme.neutral


def is_gdrs_light_preview_report(report_name: str) -> bool:
    """True на светлой теме (в т.ч. канонические имена без суффикса превью)."""
    from dashboards.light_theme import is_light_preview_active

    return is_light_preview_active()



def gdrs_section_heading_html(text: str, *, theme: str = "dark", level: int = 3) -> str:
    """Заголовок секции ГДРС: на ~2–3pt крупнее основного текста таблиц (14–15px)."""
    import html as _html

    safe = _html.escape(str(text or "").strip())
    if not safe:
        return ""
    is_light = str(theme or "").strip().lower() == "light"
    color = "#111827" if is_light else "#fafafa"
    sizes = {2: ("1.375rem", "1.5rem"), 3: ("1.1875rem", "1.25rem"), 4: ("1.0625rem", "1.125rem")}
    sz_dark, sz_light = sizes.get(level, sizes[3])
    sz = sz_light if is_light else sz_dark
    cls = "gdrs-light-heading" if is_light else "gdrs-section-heading"
    return (
        f'<h{level} class="{cls}" '
        f'style="color:{color}!important;-webkit-text-fill-color:{color}!important;'
        f"font-weight:700!important;font-size:{sz}!important;"
        f'margin:1rem 0 0.5rem 0!important;opacity:1!important;">{safe}</h{level}>'
    )


def gdrs_light_heading_html(text: str, *, level: int = 3) -> str:
    return gdrs_section_heading_html(text, theme="light", level=level)


def gdrs_render_subheader(st, text: str, *, theme: str = "dark", level: int = 3) -> None:
    html = gdrs_section_heading_html(text, theme=theme, level=level)
    if html:
        st.markdown(html, unsafe_allow_html=True)


def gdrs_render_table_subheader(
    st, name: str, *, theme: str = "dark", filters_suffix: str | None = None
) -> None:
    from utils import format_table_title

    title = format_table_title(name, filters_suffix)
    gdrs_render_subheader(st, title, theme=theme)



def inject_gdrs_light_preview_css(st) -> None:
    """CSS preview ГДРС — перебивает static/css/style.css (tёмная тема)."""
    # На каждый rerun Streamlit заново отдаёт страницу; в Яндекс.Браузере
    # <style> из прошлого run может пропасть — inject повторяем каждый script run.
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        _ctx = get_script_run_ctx()
        _run_id = getattr(_ctx, "script_run_id", None) if _ctx else None
    except Exception:
        _run_id = None
    if _run_id is not None and st.session_state.get("_gdrs_light_css_run") == _run_id:
        return
    if _run_id is not None:
        st.session_state["_gdrs_light_css_run"] = _run_id
    th = GDRS_THEME_LIGHT
    g_surface = "#f3f4f6"
    g_hover = "#e5e7eb"
    g_border = "#cbd5e1"
    g_text = "#111827"
    g_white = "#ffffff"
    st.markdown(
        f"""
<style id="gdrs-light-preview-css">
html body .stApp,
html body [data-testid="stAppViewContainer"],
html body [data-testid="stAppViewContainer"] > section {{
  background-color: {th.page_bg} !important;
  color-scheme: light !important;
}}
html body .stApp,
html body [data-testid="stAppViewContainer"],
html body.gdrs-light-preview,
html body.gdrs-light-preview .stApp {{
  --themeFontColor: {g_text} !important;
  --themeBackgroundColor: {g_white} !important;
  --themeDarkBackgroundColor: #f3f4f6 !important;
  --themeSecondaryBackgroundColor: #f3f4f6 !important;
  --primary-color: #16a34a !important;
  --secondary-background-color: #e5e7eb !important;
  --theColor: 220, 13%, 18% !important;
  color-scheme: light !important;
}}
html body .main,
html body section.main,
html body .main .block-container,
html body .main .element-container {{
  background-color: {th.page_bg} !important;
}}
html body .main .block-container h1.main-header,
html body .main h1.main-header,
html body section.main h1.main-header,
html body .main h1,
html body section.main h1,
html body .main h1.Buquhununee,
html body .main [data-testid="stMarkdownContainer"] h1,
html body .main [data-testid="stMarkdownContainer"] h1 * {{
  color: #000000 !important;
  -webkit-text-fill-color: #000000 !important;
  font-weight: 800 !important;
  font-size: 1.85rem !important;
  opacity: 1 !important;
}}
/* Отступы заголовков и фильтров — style.css на превью не грузится */
html body.gdrs-light-preview [data-testid="stMain"],
html body.gdrs-light-preview [data-testid="stMainBlockContainer"] {{
  --bi-filter-rhythm: 8px;
  --bi-page-top-gap: 8px;
}}
html body.gdrs-light-preview [data-testid="stMainBlockContainer"] {{
  padding-top: var(--bi-page-top-gap) !important;
}}
html body.gdrs-light-preview [data-testid="stMainBlockContainer"] > div[data-testid="stVerticalBlock"] {{
  gap: var(--bi-filter-rhythm) !important;
  row-gap: var(--bi-filter-rhythm) !important;
}}
html body.gdrs-light-preview [data-testid="stMainBlockContainer"] [data-testid="stHeadingWithActionElements"] {{
  margin-bottom: var(--bi-filter-rhythm) !important;
  padding-bottom: 0 !important;
}}
html body.gdrs-light-preview h1.main-header,
html body.gdrs-light-preview h1.bi-light-preview-heading,
html body.gdrs-light-preview [data-testid="stMainBlockContainer"] h1.main-header {{
  margin-top: 0 !important;
  margin-bottom: var(--bi-filter-rhythm) !important;
}}
html body.gdrs-light-preview [data-testid="stMainBlockContainer"] [data-testid="stExpander"] {{
  margin-top: 0 !important;
  margin-bottom: var(--bi-filter-rhythm) !important;
}}
html body.gdrs-light-preview [data-testid="stMainBlockContainer"] [data-testid="stExpander"] summary {{
  padding: 5px 14px !important;
}}
html body.gdrs-light-preview [data-testid="stMainBlockContainer"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] {{
  padding: var(--bi-filter-rhythm) 16px var(--bi-filter-rhythm) !important;
}}
html body.gdrs-light-preview [data-testid="stMainBlockContainer"] [data-testid="stExpander"] details [data-testid="stVerticalBlock"],
html body.gdrs-light-preview [data-testid="stMainBlockContainer"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] [data-testid="stVerticalBlock"] {{
  gap: var(--bi-filter-rhythm) !important;
  row-gap: var(--bi-filter-rhythm) !important;
}}
html body .main h2,
html body .main h3,
html body section.main h2,
html body section.main h3,
html body .main h2.Duquhununee,
html body .main h3.Duquhununee,
html body .main [data-testid="stMarkdownContainer"] h2,
html body .main [data-testid="stMarkdownContainer"] h3,
html body .main [data-testid="stMarkdownContainer"] h2 *,
html body .main [data-testid="stMarkdownContainer"] h3 * {{
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  font-weight: 700 !important;
}}
/* Подписи виджетов (радио, чекбоксы) — без .main и без body-класса */
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] [data-testid="stWidgetLabel"],
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] [data-testid="stWidgetLabel"] *,
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] [data-testid="stRadio"],
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] [data-testid="stRadio"] label,
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] [data-testid="stRadio"] label *,
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] [data-testid="stRadio"] p,
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] [data-testid="stRadio"] span,
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] [data-testid="stRadio"] div,
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] [data-testid="stRadio"] [data-testid="stMarkdownContainer"],
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] [data-testid="stRadio"] [data-testid="stMarkdownContainer"] *,
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] [data-testid="stRadio"] div[role="radiogroup"],
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] [data-testid="stRadio"] div[role="radiogroup"] *,
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] div[data-baseweb="radio"],
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] div[data-baseweb="radio"] label,
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] div[data-baseweb="radio"] label *,
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] div[data-baseweb="radio"] p,
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] div[data-baseweb="radio"] span,
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] [data-testid="stCheckbox"],
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] [data-testid="stCheckbox"] label,
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] [data-testid="stCheckbox"] label *,
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] div[data-baseweb="checkbox"] label,
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] div[data-baseweb="checkbox"] label *,
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] .stRadio label,
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] .stRadio label *,
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] .stCheckbox label,
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] .stCheckbox label * {{
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  opacity: 1 !important;
}}
html body.gdrs-light-preview [data-testid="stCheckbox"] label[data-baseweb="checkbox"] p,
html body.gdrs-light-preview [data-testid="stCheckbox"] label[data-baseweb="checkbox"] [data-testid="stMarkdownContainer"],
html body.gdrs-light-preview [data-testid="stCheckbox"] label[data-baseweb="checkbox"] [data-testid="stMarkdownContainer"] * {{
  background: transparent !important;
  background-color: transparent !important;
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
}}
html body.gdrs-light-preview [data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input:checked) > input + div:not(:has(p)) {{
  width: 16px !important;
  height: 16px !important;
  min-width: 16px !important;
  max-width: 16px !important;
  background-color: #2563eb !important;
  border: 2px solid #2563eb !important;
  border-radius: 4px !important;
}}
html body.gdrs-light-preview [data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input:checked) > input + div:has(p) {{
  background: transparent !important;
  background-color: transparent !important;
  border: none !important;
  width: auto !important;
  height: auto !important;
  max-width: none !important;
}}
html body.gdrs-light-preview [data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input:checked) > input + div:has(p) > div:first-child:not(:has(p)) {{
  width: 16px !important;
  height: 16px !important;
  min-width: 16px !important;
  max-width: 16px !important;
  background-color: #2563eb !important;
  border: 2px solid #2563eb !important;
  border-radius: 4px !important;
}}
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] [data-testid="stWidgetLabel"],
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] [data-testid="stWidgetLabel"] * {{
  font-weight: 700 !important;
  font-size: 14px !important;
}}
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] [data-testid="stCaption"],
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] [data-testid="stCaption"] * {{
  display: block !important;
  color: #374151 !important;
  -webkit-text-fill-color: #374151 !important;
  opacity: 1 !important;
}}
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] [data-testid="stHorizontalBlock"] [data-testid="stRadio"] * {{
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  opacity: 1 !important;
}}
/* Радиокнопки: серые кружки как в ГДРС */
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] [data-testid="stRadio"] label[data-baseweb="radio"] {{
  background-color: transparent !important;
  align-items: center !important;
}}
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] [data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child {{
  width: 16px !important;
  height: 16px !important;
  min-width: 16px !important;
  min-height: 16px !important;
  margin-top: 0 !important;
  margin-right: 8px !important;
  border: 2px solid #64748b !important;
  border-radius: 50% !important;
  background-color: #f3f4f6 !important;
  box-sizing: border-box !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  flex-shrink: 0 !important;
}}
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] [data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) > div:first-child {{
  border-color: #2563eb !important;
  background-color: #ffffff !important;
}}
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] [data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child > div {{
  border-radius: 50% !important;
  background-color: transparent !important;
}}
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] [data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) > div:first-child > div {{
  width: 8px !important;
  height: 8px !important;
  background-color: #2563eb !important;
}}
html body [data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"] [data-testid="stRadio"] [data-testid="stRadioGroup"] {{
  gap: 0.75rem !important;
}}

/* Фильтры: белый/серый — перебивает style.css (#e8eef5 на белом) */
html body.gdrs-light-preview,
html body.gdrs-light-preview .stApp {{
  --themeFontColor: {g_text} !important;
}}
html body [data-testid="stMainBlockContainer"] [data-testid="stExpander"] details,
html body .main [data-testid="stExpander"] details,
html body section.main [data-testid="stExpander"] details {{
  background-color: {g_white} !important;
  border: 1px solid {g_border} !important;
  border-radius: 8px !important;
}}
html body [data-testid="stMainBlockContainer"] [data-testid="stExpander"] summary,
html body .main [data-testid="stExpander"] summary,
html body section.main [data-testid="stExpander"] summary {{
  background-color: {g_surface} !important;
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  font-weight: 700 !important;
  font-size: 15px !important;
  border: 1px solid {g_border} !important;
  border-radius: 8px !important;
}}
html body [data-testid="stMainBlockContainer"] [data-testid="stExpander"] summary:hover,
html body .main [data-testid="stExpander"] summary:hover,
html body section.main [data-testid="stExpander"] summary:hover {{
  background-color: {g_hover} !important;
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
}}
html body [data-testid="stMainBlockContainer"] [data-testid="stExpander"] summary *,
html body [data-testid="stMainBlockContainer"] [data-testid="stExpander"] summary span,
html body [data-testid="stMainBlockContainer"] [data-testid="stExpander"] summary p,
html body [data-testid="stMainBlockContainer"] [data-testid="stExpander"] summary [data-testid="stMarkdownContainer"],
html body [data-testid="stMainBlockContainer"] [data-testid="stExpander"] summary [data-testid="stMarkdownContainer"] *,
html body .main [data-testid="stExpander"] summary *,
html body section.main [data-testid="stExpander"] summary *,
html body .main [data-testid="stExpander"] summary [data-testid="stMarkdownContainer"],
html body .main [data-testid="stExpander"] summary [data-testid="stMarkdownContainer"] * {{
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  font-weight: 700 !important;
}}
html body [data-testid="stMainBlockContainer"] [data-testid="stExpander"] summary svg,
html body .main [data-testid="stExpander"] summary svg,
html body section.main [data-testid="stExpander"] summary svg {{
  fill: {g_text} !important;
  color: {g_text} !important;
}}
html body [data-testid="stMainBlockContainer"] [data-testid="stExpanderDetails"],
html body .main [data-testid="stExpanderDetails"],
html body section.main [data-testid="stExpanderDetails"],
html body [data-testid="stMainBlockContainer"] [data-testid="stExpander"] [data-testid="stVerticalBlock"],
html body .main [data-testid="stExpander"] [data-testid="stVerticalBlock"],
html body section.main [data-testid="stExpander"] [data-testid="stVerticalBlock"] {{
  background-color: {g_white} !important;
}}
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stMarkdownContainer"],
html body.gdrs-light-preview [data-testid="stExpanderDetails"] [data-testid="stMarkdownContainer"] *,
html body.gdrs-light-preview section.main [data-testid="stExpander"] [data-testid="stExpanderDetails"] p,
html body.gdrs-light-preview section.main [data-testid="stExpander"] [data-testid="stExpanderDetails"] li,
html body.gdrs-light-preview section.main [data-testid="stExpander"] [data-testid="stExpanderDetails"] strong,
html body.gdrs-light-preview section.main [data-testid="stExpander"] [data-testid="stExpanderDetails"] em,
html body.gdrs-light-preview section.main [data-testid="stExpander"] [data-testid="stExpanderDetails"] ol,
html body.gdrs-light-preview section.main [data-testid="stExpander"] [data-testid="stExpanderDetails"] ul {{
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  opacity: 1 !important;
}}
html body [data-testid="stSelectbox"] [data-baseweb="select"] > div,
html body [data-baseweb="select"] > div,
html body [data-testid="stMultiSelect"] [data-baseweb="select"] > div,
html body [data-testid="stMultiSelect"] [data-baseweb="input"] input {{
  background-color: {g_white} !important;
  border-color: {g_border} !important;
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  font-weight: 600 !important;
}}
html body [data-testid="stSelectbox"] [data-baseweb="select"] span,
html body [data-baseweb="select"] span,
html body [data-testid="stMultiSelect"] [data-baseweb="select"] span,
html body [data-testid="stMultiSelect"] span {{
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  font-weight: 600 !important;
}}
html body div[data-baseweb="popover"] ul,
html body div[data-baseweb="popover"] li,
html body div[data-baseweb="menu"] li,
html body div[data-baseweb="menu"] li span {{
  background-color: {g_white} !important;
  color: {g_text} !important;
}}
html body div[data-baseweb="popover"] li:hover,
html body div[data-baseweb="popover"] li[data-highlighted="true"],
html body div[data-baseweb="popover"] li[aria-selected="true"],
html body div[data-baseweb="menu"] li:hover,
html body div[data-baseweb="menu"] li[data-highlighted="true"],
html body div[data-baseweb="menu"] li[aria-selected="true"] {{
  background-color: {g_hover} !important;
  color: {g_text} !important;
}}
html body [data-baseweb="tag"] {{
  background-color: {g_surface} !important;
  border: 1px solid {g_border} !important;
}}
html body [data-baseweb="tag"] span {{
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  font-weight: 600 !important;
}}

/* Кнопки в контенте: «Скачать таблицу», «Сбросить» в фильтрах и др. */
html body .main .stButton > button,
html body .main [data-testid="stButton"] button,
html body section.main [data-testid="stButton"] button,
html body [data-testid="stMainBlockContainer"] [data-testid="stButton"] button,
html body [data-testid="stExpander"] [data-testid="stButton"] button,
html body [data-testid="stExpanderDetails"] [data-testid="stButton"] button,
html body [data-testid="stPopover"] > button,
html body [data-testid="stPopover"] button,
html body [data-testid="stPopoverBody"] .stButton > button,
html body [data-testid="stPopoverBody"] [data-testid="stButton"] button {{
  background-color: {g_surface} !important;
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  border: 1px solid {g_border} !important;
  font-weight: 600 !important;
}}
html body .main .stButton > button:hover,
html body .main [data-testid="stButton"] button:hover,
html body section.main [data-testid="stButton"] button:hover,
html body [data-testid="stMainBlockContainer"] [data-testid="stButton"] button:hover,
html body [data-testid="stExpander"] [data-testid="stButton"] button:hover,
html body [data-testid="stExpanderDetails"] [data-testid="stButton"] button:hover,
html body [data-testid="stPopover"] > button:hover,
html body [data-testid="stPopover"] button:hover,
html body [data-testid="stPopoverBody"] .stButton > button:hover,
html body [data-testid="stPopoverBody"] [data-testid="stButton"] button:hover {{
  background-color: {g_hover} !important;
  color: {g_text} !important;
  border-color: #94a3b8 !important;
}}

/* Primary-кнопки в контенте: админка, профиль, формы (зелёный акцент светлой темы) */
html body .main .stButton > button[kind="primary"],
html body .main [data-testid="stButton"] button[kind="primary"],
html body section.main [data-testid="stButton"] button[kind="primary"],
html body [data-testid="stMainBlockContainer"] [data-testid="stButton"] button[kind="primary"],
html body [data-testid="stMainBlockContainer"] button[data-testid^="stBaseButton-primary"],
html body [data-testid="stMainBlockContainer"] [data-testid^="stBaseButton-primary"],
html body [data-testid="stMainBlockContainer"] [data-testid="stFormSubmitButton"] button[data-testid^="stBaseButton-primary"],
html body [data-testid="stExpander"] [data-testid="stButton"] button[kind="primary"],
html body [data-testid="stExpanderDetails"] [data-testid="stButton"] button[kind="primary"],
html body [data-testid="stExpander"] button[data-testid^="stBaseButton-primary"],
html body [data-testid="stExpanderDetails"] button[data-testid^="stBaseButton-primary"] {{
  background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%) !important;
  background-color: #ecfdf5 !important;
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  border: 1.5px solid #6ee7b7 !important;
  border-left: 5px solid #16a34a !important;
  font-weight: 700 !important;
  box-shadow: 0 1px 6px rgba(22, 163, 74, 0.18) !important;
}}
html body .main .stButton > button[kind="primary"] *,
html body .main [data-testid="stButton"] button[kind="primary"] *,
html body section.main [data-testid="stButton"] button[kind="primary"] *,
html body [data-testid="stMainBlockContainer"] [data-testid="stButton"] button[kind="primary"] *,
html body [data-testid="stMainBlockContainer"] button[data-testid^="stBaseButton-primary"] *,
html body [data-testid="stMainBlockContainer"] [data-testid^="stBaseButton-primary"] *,
html body [data-testid="stMainBlockContainer"] [data-testid="stFormSubmitButton"] button[data-testid^="stBaseButton-primary"] *,
html body [data-testid="stExpander"] [data-testid="stButton"] button[kind="primary"] *,
html body [data-testid="stExpanderDetails"] [data-testid="stButton"] button[kind="primary"] *,
html body [data-testid="stExpander"] button[data-testid^="stBaseButton-primary"] *,
html body [data-testid="stExpanderDetails"] button[data-testid^="stBaseButton-primary"] * {{
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  font-weight: 700 !important;
}}
html body .main .stButton > button[kind="primary"]:hover,
html body .main [data-testid="stButton"] button[kind="primary"]:hover,
html body section.main [data-testid="stButton"] button[kind="primary"]:hover,
html body [data-testid="stMainBlockContainer"] [data-testid="stButton"] button[kind="primary"]:hover,
html body [data-testid="stMainBlockContainer"] button[data-testid^="stBaseButton-primary"]:hover,
html body [data-testid="stMainBlockContainer"] [data-testid^="stBaseButton-primary"]:hover,
html body [data-testid="stMainBlockContainer"] [data-testid="stFormSubmitButton"] button[data-testid^="stBaseButton-primary"]:hover,
html body [data-testid="stExpander"] [data-testid="stButton"] button[kind="primary"]:hover,
html body [data-testid="stExpanderDetails"] [data-testid="stButton"] button[kind="primary"]:hover,
html body [data-testid="stExpander"] button[data-testid^="stBaseButton-primary"]:hover,
html body [data-testid="stExpanderDetails"] button[data-testid^="stBaseButton-primary"]:hover {{
  background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%) !important;
  background-color: #d1fae5 !important;
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  border-color: #34d399 !important;
  box-shadow: 0 2px 8px rgba(22, 163, 74, 0.28) !important;
}}
html body .main .bi-filter-chip,
html body section.main .bi-filter-chip {{
  color: {g_text} !important;
  background: {g_surface} !important;
  border: 1px solid {g_border} !important;
  font-weight: 600 !important;
}}
html body .main .bi-filters-section-title,
html body section.main .bi-filters-section-title {{
  color: {g_text} !important;
}}

/* Sidebar preview: белый фон, серый hover */
html body [data-testid="stSidebar"],
html body [data-testid="stSidebar"] > div:first-child,
html body [data-testid="stSidebarContent"] {{
  background-color: {g_white} !important;
  color: {g_text} !important;
  border-right: 1px solid {g_border} !important;
}}
html body [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
html body [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
html body [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3,
html body [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 * {{
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
}}
html body [data-testid="stSidebar"] p.sidebar-section-title,
html body [data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] p.sidebar-section-title {{
  color: #374151 !important;
  -webkit-text-fill-color: #374151 !important;
  font-weight: 800 !important;
}}
html body [data-testid="stSidebar"] div[class*="st-key-web_version_pick_scope"] [data-testid="stSelectbox"] [data-baseweb="select"] > div,
html body [data-testid="stSidebar"] div[class*="st-key-web_version_pick_scope"] [data-testid="stSelectbox"] div[data-baseweb="select"] > div {{
  border: 2px solid #92400e !important;
  border-color: #92400e !important;
  border-radius: 6px !important;
  box-shadow: 0 0 0 1px rgba(146, 64, 14, 0.12) !important;
}}
html body [data-testid="stSidebar"] hr {{
  border-color: {g_border} !important;
}}
html body [data-testid="stSidebar"] [data-testid="stExpander"],
html body [data-testid="stSidebar"] [data-testid="stExpander"] > div,
html body [data-testid="stSidebar"] [data-testid="stExpander"] details {{
  background-color: {g_white} !important;
  border: 1px solid {g_border} !important;
  border-radius: 8px !important;
}}
html body [data-testid="stSidebar"] [data-testid="stExpander"] summary {{
  background-color: {g_surface} !important;
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  font-weight: 700 !important;
}}
html body [data-testid="stSidebar"] [data-testid="stExpander"] summary:hover {{
  background-color: {g_hover} !important;
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
}}
html body [data-testid="stSidebar"] [data-testid="stExpander"] summary *,
html body [data-testid="stSidebar"] [data-testid="stExpander"] summary span,
html body [data-testid="stSidebar"] [data-testid="stExpander"] summary p,
html body [data-testid="stSidebar"] [data-testid="stExpander"] summary [data-testid="stMarkdownContainer"],
html body [data-testid="stSidebar"] [data-testid="stExpander"] summary [data-testid="stMarkdownContainer"] * {{
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  font-weight: 700 !important;
}}
html body [data-testid="stSidebar"] [data-testid="stExpander"] summary svg {{
  fill: {g_text} !important;
  color: {g_text} !important;
}}
html body [data-testid="stSidebar"] [data-testid="stExpanderDetails"],
html body [data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stVerticalBlock"] {{
  background-color: {g_white} !important;
}}
html body [data-testid="stSidebar"] .stButton > button,
html body [data-testid="stSidebar"] [data-testid="stButton"] button,
html body [data-testid="stSidebar"] [data-testid="stLinkButton"] a,
html body [data-testid="stSidebar"] [data-testid="stLinkButton"] button {{
  background-color: {g_surface} !important;
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  border: 1px solid {g_border} !important;
  font-weight: 600 !important;
}}
html body [data-testid="stSidebar"] .stButton > button:hover,
html body [data-testid="stSidebar"] [data-testid="stButton"] button:hover,
html body [data-testid="stSidebar"] [data-testid="stLinkButton"] a:hover,
html body [data-testid="stSidebar"] [data-testid="stLinkButton"] button:hover {{
  background-color: {g_hover} !important;
  color: {g_text} !important;
  border-color: #94a3b8 !important;
}}
html body.gdrs-light-preview [data-testid="stSidebar"] .stButton > button[kind="primary"],
html body.gdrs-light-preview [data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"],
html body.gdrs-light-preview [data-testid="stSidebar"] button[data-testid="stBaseButton-primary"],
html body.gdrs-light-preview [data-testid="stSidebar"] [data-testid="stBaseButton-primary"],
html body.gdrs-light-preview [data-testid="stSidebar"] [data-testid="stButton"] button[data-testid="stBaseButton-primary"] {{
  background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%) !important;
  background-color: #ecfdf5 !important;
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  border: 1.5px solid #6ee7b7 !important;
  border-left: 5px solid #16a34a !important;
  font-weight: 700 !important;
  box-shadow: 0 1px 6px rgba(22, 163, 74, 0.18) !important;
}}
html body.gdrs-light-preview [data-testid="stSidebar"] .stButton > button[kind="primary"] *,
html body.gdrs-light-preview [data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] *,
html body.gdrs-light-preview [data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] *,
html body.gdrs-light-preview [data-testid="stSidebar"] [data-testid="stBaseButton-primary"] *,
html body.gdrs-light-preview [data-testid="stSidebar"] [data-testid="stButton"] button[data-testid="stBaseButton-primary"] * {{
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  font-weight: 700 !important;
}}
html body.gdrs-light-preview [data-testid="stSidebar"] .stButton > button[kind="primary"]:hover,
html body.gdrs-light-preview [data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"]:hover,
html body.gdrs-light-preview [data-testid="stSidebar"] button[data-testid="stBaseButton-primary"]:hover,
html body.gdrs-light-preview [data-testid="stSidebar"] [data-testid="stBaseButton-primary"]:hover,
html body.gdrs-light-preview [data-testid="stSidebar"] [data-testid="stButton"] button[data-testid="stBaseButton-primary"]:hover {{
  background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%) !important;
  background-color: #d1fae5 !important;
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  border-color: #34d399 !important;
  box-shadow: 0 2px 8px rgba(22, 163, 74, 0.28) !important;
}}
html body.gdrs-light-preview [data-testid="stSidebar"] .stButton > button[kind="primary"]:disabled,
html body.gdrs-light-preview [data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"]:disabled,
html body.gdrs-light-preview [data-testid="stSidebar"] button[data-testid="stBaseButton-primary"]:disabled,
html body.gdrs-light-preview [data-testid="stSidebar"] [data-testid="stBaseButton-primary"]:disabled,
html body.gdrs-light-preview [data-testid="stSidebar"] [data-testid="stButton"] button[data-testid="stBaseButton-primary"]:disabled {{
  background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%) !important;
  background-color: #ecfdf5 !important;
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  border: 1.5px solid #6ee7b7 !important;
  border-left: 5px solid #16a34a !important;
  opacity: 1 !important;
  cursor: default !important;
  box-shadow: 0 1px 6px rgba(22, 163, 74, 0.18) !important;
}}
html body.gdrs-light-preview [data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"],
html body.gdrs-light-preview [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"],
html body.gdrs-light-preview [data-testid="stSidebar"] .stButton > button[kind="secondary"],
html body.gdrs-light-preview [data-testid="stSidebar"] [data-testid="stButton"] button[kind="secondary"],
html body.gdrs-light-preview [data-testid="stSidebar"] [data-testid="stButton"] button[data-testid="stBaseButton-secondary"] {{
  background-color: {g_white} !important;
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  border: 1px solid {g_border} !important;
  font-weight: 600 !important;
  box-shadow: none !important;
}}

/* Sidebar: «ИИ помощник» — мягкий акцент светлой темы (не путать с active report) */
html body [data-testid="stSidebar"] div[class*="sidebar_ai_assistant"] button,
html body [data-testid="stSidebar"] div[class*="sidebar_ai_assistant"] [data-testid="stLinkButton"] a,
html body [data-testid="stSidebar"] div[class*="sidebar_ai_assistant"] [data-testid="stLinkButton"] button {{
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%) !important;
  background-color: #eff6ff !important;
  color: #1e40af !important;
  -webkit-text-fill-color: #1e40af !important;
  border: 1.5px solid #60a5fa !important;
  border-left: 5px solid #2563eb !important;
  font-weight: 700 !important;
  box-shadow: 0 1px 6px rgba(37, 99, 235, 0.18) !important;
}}
html body [data-testid="stSidebar"] div[class*="sidebar_ai_assistant"] button *,
html body [data-testid="stSidebar"] div[class*="sidebar_ai_assistant"] [data-testid="stLinkButton"] a *,
html body [data-testid="stSidebar"] div[class*="sidebar_ai_assistant"] [data-testid="stLinkButton"] button * {{
  color: #1e40af !important;
  -webkit-text-fill-color: #1e40af !important;
  font-weight: 700 !important;
}}
html body [data-testid="stSidebar"] div[class*="sidebar_ai_assistant"] button:hover,
html body [data-testid="stSidebar"] div[class*="sidebar_ai_assistant"] [data-testid="stLinkButton"] a:hover,
html body [data-testid="stSidebar"] div[class*="sidebar_ai_assistant"] [data-testid="stLinkButton"] button:hover {{
  background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%) !important;
  background-color: #dbeafe !important;
  color: #1e3a8a !important;
  -webkit-text-fill-color: #1e3a8a !important;
  border-color: #3b82f6 !important;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.28) !important;
}}
html body [data-testid="stSidebar"] div[class*="sidebar_ai_assistant"] button:hover *,
html body [data-testid="stSidebar"] div[class*="sidebar_ai_assistant"] [data-testid="stLinkButton"] a:hover *,
html body [data-testid="stSidebar"] div[class*="sidebar_ai_assistant"] [data-testid="stLinkButton"] button:hover * {{
  color: #1e3a8a !important;
  -webkit-text-fill-color: #1e3a8a !important;
}}

/* Sidebar: «Выйти» — мягкий красный акцент */
html body [data-testid="stSidebar"] div[class*="sidebar_logout"] button,
html body [data-testid="stSidebar"] div[class*="sidebar_logout"] [data-testid="stBaseButton-secondary"],
html body [data-testid="stSidebar"] div[class*="sidebar_logout"] button[data-testid^="stBaseButton-"] {{
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%) !important;
  background-color: #fef2f2 !important;
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  border: 1.5px solid #fca5a5 !important;
  border-left: 5px solid #dc2626 !important;
  font-weight: 700 !important;
  box-shadow: 0 1px 6px rgba(220, 38, 38, 0.18) !important;
}}
html body [data-testid="stSidebar"] div[class*="sidebar_logout"] button *,
html body [data-testid="stSidebar"] div[class*="sidebar_logout"] [data-testid="stBaseButton-secondary"] * {{
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  font-weight: 700 !important;
}}
html body [data-testid="stSidebar"] div[class*="sidebar_logout"] button:hover,
html body [data-testid="stSidebar"] div[class*="sidebar_logout"] button[data-testid^="stBaseButton-"]:hover {{
  background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%) !important;
  background-color: #fee2e2 !important;
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  border-color: #f87171 !important;
  box-shadow: 0 2px 8px rgba(220, 38, 38, 0.28) !important;
}}
html body [data-testid="stSidebar"] div[class*="sidebar_logout"] button:hover * {{
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
}}

/* Login form: «Войти» / «Забыли пароль?» — зелёный акцент светлой темы */
html body div[class*="login_form"] [data-testid="stFormSubmitButton"] button {{
  background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%) !important;
  background-color: #ecfdf5 !important;
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  border: 1.5px solid #6ee7b7 !important;
  border-left: 5px solid #16a34a !important;
  font-weight: 700 !important;
  box-shadow: 0 1px 6px rgba(22, 163, 74, 0.18) !important;
}}
html body div[class*="login_form"] [data-testid="stFormSubmitButton"] button * {{
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  font-weight: 700 !important;
}}
html body div[class*="login_form"] [data-testid="stFormSubmitButton"] button:hover {{
  background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%) !important;
  background-color: #d1fae5 !important;
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
  border-color: #34d399 !important;
  box-shadow: 0 2px 8px rgba(22, 163, 74, 0.28) !important;
}}
html body div[class*="login_form"] [data-testid="stFormSubmitButton"] button:hover * {{
  color: {g_text} !important;
  -webkit-text-fill-color: {g_text} !important;
}}

/* Заголовки графиков/таблиц (st.subheader, emotion-классы Streamlit) */
html body .stApp {{
  --themeFontColor: #111827 !important;
}}
html body .main h2.Duquhununee,
html body .main h3.Muquhununee,
html body .main h3.Duquhununee,
html body section.main h2.Duquhununee,
html body section.main h3.Muquhununee,
html body .main [data-testid="stHeading"],
html body .main [data-testid="stHeading"] *,
html body .main [data-testid="stMarkdownContainer"] h4,
html body .main [data-testid="stMarkdownContainer"] h5,
html body .main [data-testid="stMarkdownContainer"] h6,
html body .main [data-testid="stMarkdownContainer"] p,
html body .main h3.bi-table-caption,
html body .main .bi-table-caption {{
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
  opacity: 1 !important;
}}
html body .main [data-testid="stCaption"],
html body .main [data-testid="stCaption"] *,
html body .stApp .stCaption {{
  color: #374151 !important;
  -webkit-text-fill-color: #374151 !important;
}}

html body [data-testid="stMainBlockContainer"] h1,
html body [data-testid="stMainBlockContainer"] h2,
html body [data-testid="stMainBlockContainer"] h3,
html body [data-testid="stMainBlockContainer"] h4,
html body [data-testid="stMainBlockContainer"] [data-testid="stHeading"],
html body [data-testid="stMainBlockContainer"] [data-testid="stHeading"] *,
html body [data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"] h1,
html body [data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"] h2,
html body [data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"] h3,
html body [data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"] h4,
html body .gdrs-light-heading,
html body .gdrs-light-heading * {{
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
  opacity: 1 !important;
}}
html body.gdrs-light-preview [data-testid="stPlotlyChart"] .plotly text,
html body.gdrs-light-preview [data-testid="stPlotlyChart"] .js-plotly-plot text,
html body.gdrs-light-preview [data-testid="stPlotlyChart"] svg text,
html body.gdrs-light-preview [data-testid="stPlotlyChart"] .annotation-text-g text {{
  text-shadow: none !important;
  stroke: none !important;
  stroke-width: 0 !important;
  paint-order: fill !important;
  font-weight: 400 !important;
  -webkit-text-stroke: 0 !important;
}}
html body.gdrs-light-preview [data-testid="stPlotlyChart"] .xtick text,
html body.gdrs-light-preview [data-testid="stPlotlyChart"] .ytick text,
html body.gdrs-light-preview [data-testid="stPlotlyChart"] .legend text,
html body.gdrs-light-preview [data-testid="stPlotlyChart"] g.xtitle text,
html body.gdrs-light-preview [data-testid="stPlotlyChart"] g.ytitle text,
html body.gdrs-light-preview [data-testid="stPlotlyChart"] .barlayer text,
html body.gdrs-light-preview [data-testid="stPlotlyChart"] g.textpoint text,
html body.gdrs-light-preview [data-testid="stPlotlyChart"] .bartext text {{
  fill: #111827 !important;
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}}
html body [data-testid="stPlotlyChart"] {{

  background-color: {g_white} !important;
  border: 1px solid {g_border} !important;
  isolation: isolate !important;
}}
html body.gdrs-light-preview [data-testid="stPlotlyChart"] .modebar,
html body.gdrs-light-preview [data-testid="stPlotlyChart"] .modebar-container,
html body.gdrs-light-preview [data-testid="stPlotlyChart"] .modebar-group {{
  opacity: 1 !important;
  visibility: visible !important;
  pointer-events: auto !important;
  display: flex !important;
}}
html body.gdrs-light-preview [data-testid="stPlotlyChart"] .modebar {{
  background: rgba(255, 255, 255, 0.92) !important;
}}
html body.gdrs-light-preview [data-testid="stPlotlyChart"] .modebar-btn,
html body.gdrs-light-preview [data-testid="stPlotlyChart"] a.modebar-btn {{
  opacity: 1 !important;
  visibility: visible !important;
  display: inline-block !important;
}}
html body.gdrs-light-preview [data-testid="stPlotlyChart"] .modebar-btn path,
html body.gdrs-light-preview [data-testid="stPlotlyChart"] .modebar-btn svg path,
html body.gdrs-light-preview [data-testid="stPlotlyChart"] a.modebar-btn path {{
  fill: #334155 !important;
  stroke: #334155 !important;
  opacity: 1 !important;
}}
html body.gdrs-light-preview [data-testid="stPlotlyChart"] .modebar-btn:hover path,
html body.gdrs-light-preview [data-testid="stPlotlyChart"] .modebar-btn.active path,
html body.gdrs-light-preview [data-testid="stPlotlyChart"] a.modebar-btn:hover path,
html body.gdrs-light-preview [data-testid="stPlotlyChart"] a.modebar-btn.active path {{
  fill: #0f766e !important;
  stroke: #0f766e !important;
}}
html body.gdrs-light-preview .gdrs-summary-table-wrap tr.gdrs-total-row td,
html body.gdrs-light-preview .gdrs-summary-table-wrap tr.bd-total-row td {{
  background-color: {g_hover} !important;
  border-top: 2px solid {g_border} !important;
  font-weight: 800 !important;
  text-transform: uppercase !important;
}}

/* Шапка Streamlit — inject только на светлом превью ГДРС */
header[data-testid="stHeader"],
[data-testid="stHeader"],
.stApp > header,
div[data-testid="stHeader"],
.stHeader,
.stHeader > div,
header[data-testid="stHeader"] > div,
div[data-testid="stHeader"] > div {{
  display: none !important;
  visibility: hidden !important;
  height: 0 !important;
  min-height: 0 !important;
  max-height: 0 !important;
  overflow: hidden !important;
  pointer-events: none !important;
  opacity: 0 !important;
  background: #ffffff !important;
  background-color: #ffffff !important;
  border: none !important;
}}
[data-testid="stDecoration"] {{
  display: none !important;
  background: transparent !important;
}}
.stApp [data-testid="stAppViewContainer"] > section.main,
section.main.stMain,
.stMain {{
  top: 0 !important;
  padding-top: 0 !important;
}}
.stApp {{
  margin-top: 0 !important;
}}


html.gdrs-light-preview,
html.gdrs-light-preview body,
html.gdrs-light-preview body .stApp,
html.gdrs-light-preview body [data-testid="stAppViewContainer"],
html.gdrs-light-preview body [data-testid="stAppViewContainer"] > section,
html.gdrs-light-preview body [data-testid="stMainBlockContainer"],
html.gdrs-light-preview body section.main,
html.gdrs-light-preview body .stMain,
html.gdrs-light-preview body .main,
html.gdrs-light-preview body .main .block-container {{
  background-color: #ffffff !important;
  background: #ffffff !important;
  color-scheme: light !important;
}}
html body .gdrs-loading-banner {{
  display: flex;
  align-items: center;
  gap: 0.65rem;
  margin: 0 0 var(--bi-filter-rhythm, 8px) 0;
  padding: 0.65rem 1rem;
  background: #eff6ff;
  border: 1px solid #93c5fd;
  border-radius: 8px;
  color: #1e3a8a;
  font-size: 0.95rem;
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
}}
html body .gdrs-loading-icon {{
  display: inline-block;
  font-size: 1.25rem;
  line-height: 1;
  animation: gdrs-loading-spin 1.1s linear infinite;
}}
@keyframes gdrs-loading-spin {{
  from {{ transform: rotate(0deg); }}
  to {{ transform: rotate(360deg); }}
}}
/* st.tabs — на светлом превью без style.css подписи иначе белые на белом */
html body section.main [data-testid="stTabs"] button[data-baseweb="tab"],
html body .stTabs button[data-baseweb="tab"] {{
  color: #4b5563 !important;
  -webkit-text-fill-color: #4b5563 !important;
}}
html body section.main [data-testid="stTabs"] button[data-baseweb="tab"]:hover,
html body .stTabs button[data-baseweb="tab"]:hover {{
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}}
html body section.main [data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"],
html body .stTabs button[data-baseweb="tab"][aria-selected="true"] {{
  color: #16a34a !important;
  -webkit-text-fill-color: #16a34a !important;
}}
html body section.main [data-testid="stTabs"] button[data-baseweb="tab"] p,
html body .stTabs button[data-baseweb="tab"] p {{
  color: inherit !important;
  -webkit-text-fill-color: inherit !important;
}}
html body section.main [data-testid="stTabs"] div[data-baseweb="tab-highlight"],
html body .stTabs div[data-baseweb="tab-highlight"] {{
  background-color: #16a34a !important;
}}
html body section.main [data-testid="stTabs"] div[data-baseweb="tab-border"],
html body .stTabs div[data-baseweb="tab-border"] {{
  background-color: #cbd5e1 !important;
}}
html body section.main [data-testid="stTabs"] [data-baseweb="tab-panel"],
html body .stTabs [data-baseweb="tab-panel"] {{
  margin-top: 1rem !important;
}}
</style>
<script>
(function(){{
  document.documentElement.classList.add("gdrs-light-preview");
  if (document.body) document.body.classList.add("gdrs-light-preview");
  document.querySelectorAll(".stApp,[data-testid=\"stAppViewContainer\"],section.main,.stMain,.main").forEach(function(el) {{
    el.style.setProperty("background-color", "#ffffff", "important");
    el.style.setProperty("background", "#ffffff", "important");
  }});
  function _gdrsHideStreamlitHeader() {{
    var sel = '[data-testid="stHeader"], .stHeader, header[data-testid="stHeader"]';
    document.querySelectorAll(sel).forEach(function(el) {{
      el.style.setProperty("display", "none", "important");
      el.style.setProperty("height", "0", "important");
      el.style.setProperty("min-height", "0", "important");
      el.style.setProperty("visibility", "hidden", "important");
    }});
    document.querySelectorAll('[data-testid="stDecoration"]').forEach(function(el) {{
      el.style.setProperty("display", "none", "important");
    }});
    document.querySelectorAll("section.main, .stMain").forEach(function(el) {{
      el.style.setProperty("top", "0", "important");
    }});
  }}
  _gdrsHideStreamlitHeader();
  setTimeout(_gdrsHideStreamlitHeader, 100);
  setTimeout(_gdrsHideStreamlitHeader, 500);
}})();
</script>
""",
        unsafe_allow_html=True,
    )


def gdrs_loading_banner_html(message: str = "Идёт загрузка дашборда…") -> str:
    import html as _html

    msg = _html.escape(str(message or "Идёт загрузка дашборда…").strip())
    return (
        f'<div class="gdrs-loading-banner" role="status" aria-live="polite">'
        f'<span class="gdrs-loading-icon" aria-hidden="true">🕐</span>'
        f'<span class="gdrs-loading-text">{msg}</span>'
        f"</div>"
    )


def gdrs_show_loading_banner(st, message: str = "Идёт загрузка дашборда…", slot=None):
    """Верхний баннер загрузки для светлого превью ГДРС."""
    target = slot if slot is not None else st.empty()
    target.markdown(gdrs_loading_banner_html(message), unsafe_allow_html=True)
    return target


def gdrs_clear_loading_banner(holder) -> None:
    if holder is None:
        return
    try:
        holder.empty()
    except Exception:
        pass


def gdrs_bar_label_size(theme: GdrsTheme) -> int:
    """Размер подписей над столбцами (светлое превью ~16px)."""
    return 16 if theme.name == "light" else 12


def gdrs_bar_label_yshift(theme: GdrsTheme) -> int:
    """Отступ подписи над столбцом (px), как у Plotly textposition=outside."""
    sz = gdrs_bar_label_size(theme)
    return max(14, int(round(sz * 1.125)))


def _gdrs_bar_label_texts(texts: list, ys: list) -> list[str]:
    out: list[str] = []
    for txt, y in zip(texts, ys):
        if txt is None or str(txt).strip() == "":
            out.append("")
            continue
        try:
            yf = float(y)
        except (TypeError, ValueError):
            yf = 0.0
        if yf <= 0 and str(txt).strip() in ("0", "0.0", "+0", "-0"):
            out.append("")
            continue
        out.append(str(txt))
    return out


def _gdrs_bar_label_font(sz: int, color: Any) -> dict:
    ff = "Arial, Helvetica, sans-serif"
    base = dict(size=sz, family=ff, color=color)
    return base


def gdrs_apply_grouped_bar_labels(
    fig: Any,
    theme: GdrsTheme,
    xs: list,
    series: list[tuple[list, Any]],
    *,
    bar_indices: list[int] | None = None,
) -> Any:
    """Подписи строго над столбцами — нативный bar.text (Plotly сам центрирует в group)."""
    sz = gdrs_bar_label_size(theme)
    for seq, (texts, color) in enumerate(series):
        if bar_indices is not None:
            if seq >= len(bar_indices):
                break
            ti = int(bar_indices[seq])
        else:
            ti = seq
        if ti >= len(fig.data):
            break
        tr = fig.data[ti]
        if getattr(tr, "type", None) != "bar":
            continue
        ys = list(tr.y) if tr.y is not None else []
        label_texts = _gdrs_bar_label_texts(list(texts), ys)
        # Если заранее переданные text пустые, но y есть — подпись из y.
        if not any(str(t).strip() for t in label_texts) and ys:
            label_texts = []
            for y in ys:
                try:
                    yf = float(y)
                except (TypeError, ValueError):
                    label_texts.append("")
                    continue
                label_texts.append(f"{yf:.1f}" if abs(yf) >= 0.05 else "")
        if isinstance(color, (list, tuple)):
            cols = list(color)
        else:
            cols = color
        tf = _gdrs_bar_label_font(sz, cols)
        tr.update(
            text=label_texts,
            textposition="outside",
            texttemplate=None,
            cliponaxis=False,
            constraintext="none",
            textfont=tf,
            outsidetextfont=tf,
        )
    fig.update_layout(annotations=[])
    return fig


def gdrs_apply_bar_outside_labels(fig: Any, theme: GdrsTheme) -> Any:
    """Подписи bar: нормализует text/outsidetextfont (не затирает text при сбое)."""
    bar_idx: list[int] = []
    for i, tr in enumerate(fig.data):
        if getattr(tr, "type", None) != "bar":
            continue
        # Не используем bool(tr.text): у ndarray это ValueError.
        raw = getattr(tr, "text", None)
        if raw is None:
            continue
        try:
            texts = list(raw)
        except Exception:
            texts = [raw]
        bar_idx.append(i)
    if not bar_idx:
        return fig
    xs = list(fig.data[bar_idx[0]].x) if fig.data[bar_idx[0]].x is not None else []
    series: list[tuple[list, Any]] = []
    for ti in bar_idx:
        tr = fig.data[ti]
        try:
            texts = list(tr.text) if tr.text is not None else []
        except Exception:
            texts = []
        col = theme.text
        try:
            if tr.textfont is not None and getattr(tr.textfont, "color", None) is not None:
                col = tr.textfont.color
        except Exception:
            pass
        series.append((texts, col))
    return gdrs_apply_grouped_bar_labels(fig, theme, xs, series, bar_indices=bar_idx)


def gdrs_sanitize_bar_text_labels(fig: Any, theme: GdrsTheme) -> Any:
    """Совместимость: annotations вместо bar.text."""
    return gdrs_apply_bar_outside_labels(fig, theme)


def gdrs_apply_bottom_chart_legend(
    fig: Any,
    theme: GdrsTheme,
    *,
    min_margin_b: float | None = None,
) -> Any:
    """Горизонтальная легенда под осью X (после всех правок layout)."""
    from utils import (
        CHART_LEGEND_FONT_SIZE,
        _fig_legend_trace_count,
        chart_layout_for_bottom_legend,
        standard_chart_legend,
    )

    layout = fig.layout
    prev_m = getattr(layout, "margin", None)
    margin_l = float(getattr(prev_m, "l", 56) or 56)
    margin_r = float(getattr(prev_m, "r", 24) or 24)
    margin_t = float(getattr(prev_m, "t", 88) or 88)
    margin_b = float(getattr(prev_m, "b", 72) or 72)
    if min_margin_b is not None:
        margin_b = max(margin_b, float(min_margin_b))
    n_leg = _fig_legend_trace_count(fig)
    chart_lo = chart_layout_for_bottom_legend(n_leg)
    # ГДРС: крупные подписи проектов на оси X — легенду ниже стандартного отступа.
    legend_y = float(chart_lo["legend_y"]) - 0.18
    extra_b = 52
    if min_margin_b is not None and float(min_margin_b) >= 100:
        legend_y -= 0.06
        extra_b += 24
    margin_b = max(margin_b, float(chart_lo["margin_bottom"])) + extra_b
    fig.update_layout(
        showlegend=True,
        legend=standard_chart_legend(
            font=dict(color=theme.text, size=CHART_LEGEND_FONT_SIZE),
            y=legend_y,
        ),
        margin=dict(l=margin_l, r=margin_r, t=margin_t, b=margin_b),
    )
    return fig


def apply_gdrs_chart_background(fig: Any, theme: GdrsTheme, *, skip_uniformtext: bool = False) -> Any:
    """Локальный аналог apply_chart_background с палитрой ГДРС."""
    from utils import (
        CHART_AXIS_TICK_FONT_SIZE,
        CHART_AXIS_TITLE_FONT_SIZE,
        CHART_LAYOUT_FONT_SIZE,
        CHART_LEGEND_FONT_SIZE,
        CHART_UNIFORMTEXT_MINSIZE,
        _fig_has_pie_trace,
        _fig_legend_trace_count,
        _merge_prev_legend_title,
        chart_layout_for_bottom_legend,
        standard_chart_legend,
        standard_pie_chart_legend,
    )

    layout = fig.layout
    prev_leg = getattr(layout, "legend", None) if layout is not None else None
    prev_m = getattr(layout, "margin", None) if layout is not None else None
    margin_l, margin_r, margin_t, margin_b = 60, 30, 72, 72
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

    prev_title = getattr(layout, "title", None) if layout is not None else None
    prev_title_text = ""
    prev_title_size = 15
    if prev_title is not None:
        _pt = getattr(prev_title, "text", None)
        if _pt is not None and str(_pt).strip():
            prev_title_text = str(_pt)
        _ps = getattr(getattr(prev_title, "font", None), "size", None)
        if _ps is not None:
            try:
                prev_title_size = int(float(_ps))
            except (TypeError, ValueError):
                pass

    legend_kwargs = dict(font=dict(color=theme.text, size=CHART_LEGEND_FONT_SIZE))
    if prev_leg is not None:
        prev_font = getattr(prev_leg, "font", None)
        if prev_font is not None:
            for fk in ("color", "family"):
                fv = getattr(prev_font, fk, None)
                if fv is not None:
                    legend_kwargs.setdefault("font", {})[fk] = fv
        _merge_prev_legend_title(prev_leg, legend_kwargs)

    showlegend = getattr(layout, "showlegend", True) if layout is not None else True

    is_pie = _fig_has_pie_trace(fig)
    _fig_w = getattr(layout, "width", None) if layout is not None else None
    _fig_h = getattr(layout, "height", None) if layout is not None else None
    _pie_fixed_size = (
        is_pie
        and _fig_w is not None
        and _fig_h is not None
        and float(_fig_w) > 0
        and float(_fig_h) > 0
    )
    if is_pie:
        leg_out = standard_pie_chart_legend(**legend_kwargs)
        if prev_leg is not None:
            py = getattr(prev_leg, "y", None)
            try:
                if py is not None and float(py) < 0.2:
                    leg_out["y"] = float(py)
            except (TypeError, ValueError):
                pass
        if margin_t > 60 and not _pie_fixed_size:
            margin_t = max(44.0, min(margin_t, 56.0))
    elif showlegend:
        n_leg = _fig_legend_trace_count(fig)
        chart_lo = chart_layout_for_bottom_legend(n_leg)
        leg_out = standard_chart_legend(**legend_kwargs, y=chart_lo["legend_y"])
        if prev_leg is not None:
            py = getattr(prev_leg, "y", None)
            try:
                if py is not None and float(py) < 0.2:
                    leg_out["y"] = float(py)
            except (TypeError, ValueError):
                pass
        if float(margin_b) < float(chart_lo["margin_bottom"]):
            margin_b = float(chart_lo["margin_bottom"])
    else:
        leg_out = standard_chart_legend(**legend_kwargs)

    layout_kwargs = dict(
        template=None,
        plot_bgcolor=theme.chart_bg,
        paper_bgcolor=theme.chart_bg,
        autosize=not _pie_fixed_size,
        font=dict(
            family="Inter, system-ui, sans-serif",
            color=theme.text,
            size=CHART_LAYOUT_FONT_SIZE,
        ),
        title=dict(
            text=prev_title_text,
            font=dict(color=theme.text, size=prev_title_size),
            pad=dict(t=4),
        ),
        margin=dict(l=margin_l, r=margin_r, t=margin_t, b=margin_b),
        legend=leg_out,
        showlegend=bool(showlegend),
    )
    if _pie_fixed_size:
        layout_kwargs["width"] = float(_fig_w)
        layout_kwargs["height"] = float(_fig_h)
    if not skip_uniformtext:
        layout_kwargs["uniformtext"] = dict(minsize=CHART_UNIFORMTEXT_MINSIZE, mode="show")
    fig.update_layout(**layout_kwargs)
    fig.update_layout(hovermode=False)
    try:
        fig.update_traces(hovertemplate="", hoverinfo="skip")
    except Exception:
        try:
            fig.update_traces(hoverinfo="skip")
        except Exception:
            pass
    if not is_pie:
        fig.update_xaxes(
            gridcolor=theme.chart_grid,
            linecolor=theme.chart_axis,
            tickfont=dict(color=theme.text, size=CHART_AXIS_TICK_FONT_SIZE),
            title=dict(font=dict(color=theme.text, size=CHART_AXIS_TITLE_FONT_SIZE)),
            zerolinecolor=theme.chart_axis,
            automargin=True,
            ticklabelstandoff=8,
        )
        fig.update_yaxes(
            gridcolor=theme.chart_grid,
            linecolor=theme.chart_axis,
            tickfont=dict(color=theme.text, size=CHART_AXIS_TICK_FONT_SIZE),
            title=dict(font=dict(color=theme.text, size=CHART_AXIS_TITLE_FONT_SIZE)),
            zerolinecolor=theme.chart_axis,
            automargin=True,
        )
    return fig


def gdrs_matrix_table_css(wrap_id: str, theme: GdrsTheme) -> str:
    if theme.name == "light":
        return _gdrs_matrix_table_css_light(wrap_id, theme)
    return _gdrs_matrix_table_css_dark(wrap_id)


def _gdrs_matrix_table_css_dark(wrap_id: str) -> str:
    from dashboards.gdrs_resursi import _gdrs_matrix_table_css

    return _gdrs_matrix_table_css(wrap_id)


def _gdrs_matrix_table_css_light(w: str, th: GdrsTheme) -> str:
    return f"""
<style>
html, body {{
  background: #ffffff !important;
  color: {th.text} !important;
  overflow-x: hidden !important;
  width: 100% !important;
  max-width: 100% !important;
  box-sizing: border-box !important;
}}
.bi-sortable-html-root {{
  background: #ffffff !important;
  color: {th.text} !important;
  width: 100% !important;
  max-width: 100% !important;
  overflow-x: hidden !important;
  box-sizing: border-box !important;
}}
#{w} h3.bi-table-caption,
#{w} .bi-table-caption {{
  color: {th.text} !important;
  -webkit-text-fill-color: {th.text} !important;
}}
#{w}.gdrs-table-wrap {{
  display: block !important;
  overflow-x: auto !important;
  overflow-y: visible !important;
  min-width: 0 !important;
  width: 100% !important;
  max-width: 100% !important;
  margin: 0.5rem 0;
  -webkit-overflow-scrolling: touch !important;
  scrollbar-width: thin;
  scrollbar-color: #64748b #ffffff;
}}
#{w}.gdrs-table-wrap::-webkit-scrollbar {{
  height: 10px;
}}
#{w}.gdrs-table-wrap::-webkit-scrollbar-thumb {{
  background: #94a3b8;
  border-radius: 5px;
}}
#{w} .gdrs-matrix-table {{
  border: 2px solid #94a3b8;
  border-collapse: separate !important;
  border-spacing: 0 !important;
  width: 100%;
  min-width: 100%;
  table-layout: fixed;
  font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 14px;
  background: #ffffff;
  color: {th.text};
}}
#{w} .gdrs-matrix-table th.gdrs-col-equal,
#{w} .gdrs-matrix-table td.gdrs-col-equal {{
  width: 5.25rem;
  min-width: 4.5rem;
  max-width: 6.5rem;
  white-space: nowrap !important;
  box-sizing: border-box;
}}
#{w} .gdrs-matrix-table th.gdrs-td-text,
#{w} .gdrs-matrix-table td.gdrs-td-text {{
  width: auto;
  min-width: 9rem;
  max-width: 22rem;
  white-space: normal !important;
}}
#{w} .gdrs-matrix-table th,
#{w} .gdrs-matrix-table td {{
  border: 1px solid #cbd5e1 !important;
  padding: 7px 10px !important;
  vertical-align: middle !important;
  background-clip: padding-box;
  text-align: center !important;
  overflow: visible !important;
  text-overflow: clip !important;
  color: {th.text} !important;
  font-size: 14px !important;
  line-height: 1.35 !important;
}}
#{w} .gdrs-matrix-table thead th {{
  white-space: normal !important;
  word-wrap: break-word !important;
  overflow-wrap: anywhere !important;
  line-height: 1.25 !important;
  max-width: 11em !important;
  vertical-align: bottom !important;
}}
#{w} .gdrs-matrix-table tbody td {{
  white-space: normal !important;
  word-wrap: break-word !important;
  overflow-wrap: anywhere !important;
  max-width: 28em !important;
}}
#{w} .gdrs-matrix-table tbody td.gdrs-col-plan,
#{w} .gdrs-matrix-table tbody td.gdrs-col-skud,
#{w} .gdrs-matrix-table tbody td.gdrs-col-dev {{
  white-space: nowrap !important;
  max-width: none !important;
}}
#{w} .gdrs-matrix-table th *,
#{w} .gdrs-matrix-table td *,
#{w} .gdrs-matrix-table .bi-sort-label {{
  color: inherit !important;
}}
#{w} .gdrs-matrix-table thead th {{
  position: sticky !important;
  top: 0 !important;
  z-index: 5 !important;
  background: #e5e7eb !important;
  color: #111827 !important;
  font-size: 14px !important;
  font-weight: 800 !important;
  text-align: center !important;
}}
#{w} .gdrs-matrix-table thead tr.gdrs-h-title th,
#{w} .gdrs-matrix-table thead tr.gdrs-h-period th {{
  background: #e5e7eb !important;
  color: #111827 !important;
  font-weight: 800 !important;
}}
#{w} .gdrs-matrix-table thead tr.gdrs-h-title th {{
  font-size: 18px !important;
}}
#{w} .gdrs-matrix-table thead tr.gdrs-h-period th {{
  font-size: 16px !important;
}}
#{w} .gdrs-matrix-table thead th.gdrs-h-plan-group {{
  background: #bbf7d0 !important;
  color: #14532d !important;
  font-size: 15px !important;
}}
#{w} .gdrs-matrix-table thead th.gdrs-h-skud-group {{
  background: #e2e8f0 !important;
  color: #1f2937 !important;
  font-size: 15px !important;
}}
#{w} .gdrs-matrix-table thead th.gdrs-h-week-plan {{
  background: #dcfce7 !important;
  color: #14532d !important;
  font-size: 14px !important;
}}
#{w} .gdrs-matrix-table thead th.gdrs-h-week-skud {{
  background: #f1f5f9 !important;
  color: #1f2937 !important;
  font-size: 14px !important;
}}
#{w} .gdrs-matrix-table tbody td {{
  background-color: #ffffff !important;
  color: #111827 !important;
  font-weight: 700 !important;
  text-align: center !important;
}}
#{w} .gdrs-matrix-table tbody td.gdrs-col-plan {{
  background-color: #ecfdf5 !important;
  color: #14532d !important;
}}
#{w} .gdrs-matrix-table tbody td.gdrs-col-skud {{
  background-color: #f8fafc !important;
  color: #1e293b !important;
}}
#{w} .gdrs-matrix-table tbody td.gdrs-col-dev {{
  background-color: #f1f5f9 !important;
  color: #111827 !important;
}}
#{w} .gdrs-matrix-table tbody td.gdrs-td-contractor {{
  color: #1d4ed8 !important;
  font-weight: 700 !important;
}}
#{w} .gdrs-matrix-table tbody td.gdrs-td-text {{
  text-align: left !important;
  color: #111827 !important;
  font-weight: 600 !important;
  min-width: 10rem;
  max-width: 28rem;
  white-space: normal !important;
}}
#{w} .gdrs-sep-l-strong {{
  box-shadow: inset 3px 0 0 #64748b;
}}
#{w} .gdrs-sep-r-strong {{
  box-shadow: inset -3px 0 0 #64748b;
}}
#{w} tr.gdrs-rk-project td,
#{w} tr.gdrs-rk-subtotal td {{
  font-size: 15px !important;
  font-weight: 800 !important;
}}
#{w} tr.gdrs-rk-project td:not(.gdrs-col-plan):not(.gdrs-col-skud):not(.gdrs-col-dev),
#{w} tr.gdrs-rk-subtotal td:not(.gdrs-col-plan):not(.gdrs-col-skud):not(.gdrs-col-dev) {{
  background: #f3f4f6 !important;
  color: #111827 !important;
}}
#{w} tr.gdrs-rk-project td.gdrs-col-plan,
#{w} tr.gdrs-rk-subtotal td.gdrs-col-plan {{
  background-color: #bbf7d0 !important;
  color: #14532d !important;
}}
#{w} tr.gdrs-rk-project td.gdrs-col-skud,
#{w} tr.gdrs-rk-subtotal td.gdrs-col-skud {{
  background-color: #e2e8f0 !important;
  color: #1f2937 !important;
}}
#{w} tr.gdrs-rk-total td,
#{w} tr.gdrs-rk-grand td {{
  font-size: 15px !important;
  font-weight: 800 !important;
}}
#{w} tr.gdrs-rk-total td:not(.gdrs-col-plan):not(.gdrs-col-skud):not(.gdrs-col-dev),
#{w} tr.gdrs-rk-grand td:not(.gdrs-col-plan):not(.gdrs-col-skud):not(.gdrs-col-dev) {{
  background: #bfdbfe !important;
  color: #1e3a8a !important;
}}
#{w} td.gdrs-u, #{w} td.gdrs-u span {{ color: #b91c1c !important; font-weight: 800 !important; }}
#{w} td.gdrs-o, #{w} td.gdrs-o span {{ color: #15803d !important; font-weight: 800 !important; }}
#{w} td.gdrs-z, #{w} td.gdrs-z span {{ color: #374151 !important; font-weight: 700 !important; }}
#{w} .bi-sort-filter {{
  background: #ffffff !important;
  color: #111827 !important;
  border: 1px solid #94a3b8 !important;
}}
</style>
"""
