"""
Светлая тема для showcase-инстанса (демо внешним клиентам).

Production не импортирует при обычном ``streamlit_app.py``.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict

import streamlit as st

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _is_showcase() -> bool:
    try:
        from config import is_showcase_mode

        return is_showcase_mode()
    except Exception:
        return os.environ.get("BI_ANALYTICS_SHOWCASE_MODE", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )


_SHOWCASE_THEMES: Dict[str, str] = {
    "default": "Светлая",
    "warm": "Тёплая",
    "cool": "Мятная",
    "slate": "Серо-синяя",
}

_THEME_PALETTES: Dict[str, Dict[str, str]] = {
    "default": {
        "bg": "#f8fafc",
        "surface": "#ffffff",
        "text": "#111827",
        "muted": "#6b7280",
        "accent": "#2563eb",
        "accent_soft": "#dbeafe",
        "border": "#cbd5e1",
        "sidebar_bg": "#f8fafc",
        "banner_bg": "linear-gradient(135deg, #eff6ff 0%, #f0f9ff 100%)",
        "banner_border": "#bfdbfe",
        "banner_text": "#1e3a8a",
        "banner_strong": "#1d4ed8",
        "kpi_surface": "#ffffff",
    },
    "warm": {
        "bg": "#faf6f1",
        "surface": "#fffdfb",
        "text": "#292524",
        "muted": "#78716c",
        "accent": "#b45309",
        "accent_soft": "#fff7ed",
        "border": "#e7e5e4",
        "sidebar_bg": "#faf6f1",
        "banner_bg": "linear-gradient(135deg, #fff7ed 0%, #ffedd5 100%)",
        "banner_border": "#fdba74",
        "banner_text": "#9a3412",
        "banner_strong": "#c2410c",
        "kpi_surface": "#fffdfb",
    },
    "cool": {
        "bg": "#f0fdfa",
        "surface": "#ffffff",
        "text": "#134e4a",
        "muted": "#5b9088",
        "accent": "#0d9488",
        "accent_soft": "#ccfbf1",
        "border": "#99f6e4",
        "sidebar_bg": "#f0fdfa",
        "banner_bg": "linear-gradient(135deg, #ecfeff 0%, #ccfbf1 100%)",
        "banner_border": "#5eead4",
        "banner_text": "#115e59",
        "banner_strong": "#0f766e",
        "kpi_surface": "#ffffff",
    },
    "slate": {
        "bg": "#e2e8f0",
        "surface": "#f8fafc",
        "text": "#0f172a",
        "muted": "#64748b",
        "accent": "#475569",
        "accent_soft": "#e2e8f0",
        "border": "#cbd5e1",
        "sidebar_bg": "#e2e8f0",
        "banner_bg": "linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%)",
        "banner_border": "#94a3b8",
        "banner_text": "#334155",
        "banner_strong": "#1e293b",
        "kpi_surface": "#f8fafc",
    },
}


def get_showcase_theme_key() -> str:
    key = str(st.session_state.get("showcase_theme", "default") or "default")
    return key if key in _THEME_PALETTES else "default"


def is_showcase_contrast_theme() -> bool:
    return _is_showcase() and get_showcase_theme_key() == "contrast"


_LIGHT_MATRIX_PALETTE: Dict[str, str] = {
    "page_bg": "#f8fafc",
    "page_text": "#111827",
    "surface": "#ffffff",
    "surface_alt": "#f3f4f6",
    "head_text": "#111827",
    "body_text": "#111827",
    "cell_bg": "#ffffff",
    "project_head_bg": "#e8f0fe",
    "project_col_bg": "#f9fafb",
    "project_col_text": "#111827",
    "block_bg": "#ffffff",
    "block_border": "rgba(15,23,42,0.12)",
    "block_shadow": "0 6px 18px rgba(15,23,42,0.08)",
    "grid_border": "#cbd5e1",
    "strong_border": "#111827",
    "sep_gap": "#f8fafc",
    "scrollbar_track": "#e5e7eb",
    "scrollbar_thumb": "rgba(100,116,139,0.45)",
}


def apply_table_constants() -> None:
    """Патчит палитру HTML-таблиц и Plotly в ``utils`` (inline-стили)."""
    if not _is_showcase():
        return
    import utils as u

    u.TABLE_BG_COLOR = "#ffffff"
    u.TABLE_HEADER_BG_COLOR = "#f3f4f6"
    u.TABLE_GROUP_ROW_BG_COLOR = "#e8ecf1"
    u.TABLE_TOTAL_ROW_BG_COLOR = "#e5e7eb"
    u.TABLE_TEXT_COLOR = "#111827"
    u.TABLE_CELL_BORDER = "1px solid #cbd5e1"
    u.FINANCE_TABLE_CELL_BORDER = "1px solid #94a3b8"
    u.CHART_BG_COLOR = "rgba(255, 255, 255, 0.96)"
    u.CHART_GRID_COLOR = "rgba(148, 163, 184, 0.45)"
    u.CHART_AXIS_LINE_COLOR = "rgba(100, 116, 139, 0.65)"
    u.CHART_ZEROLINE_COLOR = "rgba(100, 116, 139, 0.55)"
    u.TABLE_TOTAL_ROW_FONT_CSS = (
        "font-weight:800;font-size:1.32em;text-transform:uppercase;"
        "letter-spacing:0.05em;color:#111827;"
    )
    u.TABLE_CELL_BORDER_CSS = f"border: {u.TABLE_CELL_BORDER};"


def matrix_iframe_palette() -> Dict[str, str]:
    """Цвета iframe-матриц (девелоперские проекты, контрольные точки)."""
    if _is_showcase():
        key = get_showcase_theme_key()
        if key == "contrast":
            return dict(_LIGHT_MATRIX_PALETTE)
        try:
            p = _THEME_PALETTES.get(key, _THEME_PALETTES["default"])
            return {
                "page_bg": p["bg"],
                "page_text": p["text"],
                "surface": p["surface"],
                "surface_alt": p["accent_soft"],
                "head_text": p["text"],
                "body_text": p["text"],
                "cell_bg": p["surface"],
                "project_head_bg": p["accent_soft"],
                "project_col_bg": p["bg"],
                "project_col_text": p["text"],
                "block_bg": p["surface"],
                "block_border": p["border"],
                "block_shadow": "0 6px 18px rgba(15,23,42,0.08)",
                "grid_border": p["border"],
                "strong_border": p["text"],
                "sep_gap": p["bg"],
                "scrollbar_track": p["border"],
                "scrollbar_thumb": p["muted"],
            }
        except Exception:
            pass
        return dict(_LIGHT_MATRIX_PALETTE)
    return {
        "page_bg": "#0e1520",
        "page_text": "#e6edf3",
        "surface": "#121a24",
        "surface_alt": "#161f2b",
        "head_text": "#f0f4f8",
        "body_text": "#fafafa",
        "cell_bg": "#0c1219",
        "project_head_bg": "#1a3328",
        "project_col_bg": "#161f2b",
        "project_col_text": "#ffffff",
        "block_bg": "#121a24",
        "block_border": "rgba(255,255,255,0.42)",
        "block_shadow": "0 6px 18px rgba(0,0,0,0.42)",
        "grid_border": "#5a6f82",
        "strong_border": "#ffffff",
        "sep_gap": "#121a24",
        "scrollbar_track": "#141820",
        "scrollbar_thumb": "rgba(121,154,192,0.42)",
    }


def _inject_sidebar_light_css() -> None:
    st.markdown(
        """
<style id="showcase-sidebar-light">
html body [data-testid="stSidebar"],
html body [data-testid="stSidebar"] > div:first-child,
html body [data-testid="stSidebarContent"] {
  background-color: #f8fafc !important;
  color: #111827 !important;
}
html body [data-testid="stSidebar"] *,
html body [data-testid="stSidebarNav"] a,
html body [data-testid="stSidebarNav"] a span,
html body [data-testid="stSidebarNavLink"],
html body [data-testid="stSidebarNavLink"] span {
  color: #111827 !important;
  -webkit-text-fill-color: #111827 !important;
}
html body [data-testid="stSidebar"] .stButton > button {
  background-color: #ffffff !important;
  color: #111827 !important;
  border: 1px solid #cbd5e1 !important;
}
html body [data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] > div,
html body [data-testid="stSidebar"] [data-baseweb="select"] > div {
  background-color: #ffffff !important;
  color: #111827 !important;
  border-color: #cbd5e1 !important;
}
html body [data-testid="stSidebar"] input,
html body [data-testid="stSidebar"] label,
html body [data-testid="stSidebar"] p,
html body [data-testid="stSidebar"] span {
  color: #111827 !important;
}
</style>
""",
        unsafe_allow_html=True,
    )


def apply_streamlit_light_config() -> None:
    """Showcase: встроенная тема Streamlit (чекбоксы, календарь и др.)."""
    if not _is_showcase():
        return
    try:
        from streamlit import config as _cfg

        dark = get_showcase_theme_key() == "contrast"
        if dark:
            opts = (
                ("theme.base", "dark"),
                ("theme.primaryColor", "#38bdf8"),
                ("theme.backgroundColor", "#0f172a"),
                ("theme.secondaryBackgroundColor", "#1e293b"),
                ("theme.textColor", "#f8fafc"),
                ("theme.linkColor", "#38bdf8"),
            )
        else:
            p = _THEME_PALETTES.get(get_showcase_theme_key(), _THEME_PALETTES["default"])
            opts = (
                ("theme.base", "light"),
                ("theme.primaryColor", p["accent"]),
                ("theme.backgroundColor", p["bg"]),
                ("theme.secondaryBackgroundColor", p["surface"]),
                ("theme.textColor", p["text"]),
                ("theme.linkColor", p["accent"]),
            )
        for key, val in opts:
            try:
                _cfg.set_option(key, val)
            except Exception:
                pass
    except Exception:
        pass


def _selection_highlight_css(p: Dict[str, str], is_contrast: bool) -> str:
    """Выделение активных пунктов — цвета текущей темы (accent_soft + accent)."""
    if is_contrast:
        return ""
    accent = p["accent"]
    accent_soft = p["accent_soft"]
    text = p["text"]
    return f"""
html body [data-testid="stSidebar"] .stButton > button[kind="primary"],
html body [data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"],
html body [data-testid="stSidebar"] [data-testid="stBaseButton-primary"],
html body [data-testid="stMain"] div[class*="st-key-showcase_theme_"] .stButton > button[kind="primary"],
html body [data-testid="stMain"] div[class*="st-key-showcase_theme_"] [data-testid="stBaseButton-primary"],
html body [data-testid="stMain"] div[class*="st-key-showcase_theme_"] [data-testid="baseButton-primary"] {{
  background-color: {accent_soft} !important;
  color: {text} !important;
  -webkit-text-fill-color: {text} !important;
  border-color: {accent} !important;
  box-shadow: none !important;
  font-weight: 700 !important;
}}
html body [data-testid="stSidebar"] [data-testid="stExpander"] details[open] > summary,
html body [data-testid="stSidebar"] [data-testid="stExpander"] details[open] summary {{
  background-color: {accent_soft} !important;
  color: {text} !important;
  -webkit-text-fill-color: {text} !important;
  border-color: {accent} !important;
}}
"""


def _build_active_theme_css(theme_key: str) -> str:
    """CSS активной темы — без JS (Streamlit блокирует script на body)."""
    p = _THEME_PALETTES.get(theme_key, _THEME_PALETTES["default"])
    bg, surface, text = p["bg"], p["surface"], p["text"]
    muted, accent, border = p["muted"], p["accent"], p["border"]
    sidebar = p["sidebar_bg"]
    is_contrast = theme_key == "contrast"
    scheme = "dark" if is_contrast else "light"
    btn_bg = "#334155" if is_contrast else "#ffffff"
    input_bg = surface if is_contrast else "#ffffff"
    main_scope = "[data-testid=\"stMain\"]" if is_contrast else "html body"
    global_label_rule = "" if is_contrast else f"""
html body label, html body p, html body span {{
  color: {text} !important;
  -webkit-text-fill-color: {text} !important;
}}"""

    return f"""
<style id="showcase-active-theme">
html, html body {{
  color-scheme: {scheme} !important;
}}
html body,
html body .stApp,
html body [data-testid="stAppViewContainer"],
html body [data-testid="stMain"],
html body [data-testid="stMainBlockContainer"],
html body section.main,
html body [data-testid="stSidebar"],
html body [data-testid="stSidebar"] > div:first-child,
html body [data-testid="stSidebarContent"] {{
  background-color: {bg} !important;
  color: {text} !important;
}}
html body [data-testid="stSidebar"],
html body [data-testid="stSidebar"] > div:first-child,
html body [data-testid="stSidebarContent"] {{
  background-color: {sidebar} !important;
}}
html body .stApp {{
  --themeBackgroundColor: {bg} !important;
  --themeDarkBackgroundColor: {surface} !important;
  --themeFontColor: {text} !important;
  --showcase-bg: {bg};
  --showcase-surface: {surface};
  --showcase-text: {text};
  --showcase-accent: {accent};
  --showcase-accent-soft: {p["accent_soft"]};
  color-scheme: {scheme} !important;
}}
html body h1, html body h2, html body h3,
html body h1.main-header, html body .main-header,
html body [data-testid="stMarkdownContainer"] p,
html body [data-testid="stMarkdownContainer"] span,
html body [data-testid="stMarkdownContainer"] li,
html body [data-testid="stCaptionContainer"],
html body .stMarkdown, html body .stMarkdown p {{
  color: {text} !important;
  -webkit-text-fill-color: {text} !important;
}}
html body [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
html body [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
html body [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3,
html body [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 *,
html body [data-testid="stSidebarNav"] a,
html body [data-testid="stSidebarNav"] a span,
html body [data-testid="stSidebarNavLink"],
html body [data-testid="stSidebarNavLink"] span,
html body [data-testid="stSidebarNavItems"] *,
html body [data-testid="stSidebarUserContent"] *,
html body [data-testid="stSidebar"] label,
html body [data-testid="stSidebar"] p,
html body [data-testid="stSidebar"] span,
html body [data-testid="stSidebar"] div {{
  color: {text} !important;
  -webkit-text-fill-color: {text} !important;
}}
html body [data-testid="stSidebar"] p.sidebar-section-title,
html body [data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] p.sidebar-section-title {{
  color: {muted} !important;
  -webkit-text-fill-color: {muted} !important;
}}
html body [data-testid="stSidebar"] [data-testid="stExpander"],
html body [data-testid="stSidebar"] [data-testid="stExpander"] > div,
html body [data-testid="stSidebar"] [data-testid="stExpander"] details {{
  background-color: {surface} !important;
  border: 1px solid {border} !important;
  border-radius: 8px !important;
}}
html body [data-testid="stSidebar"] [data-testid="stExpander"] summary,
html body [data-testid="stSidebar"] [data-testid="stExpander"] summary *,
html body [data-testid="stSidebar"] [data-testid="stExpander"] summary span,
html body [data-testid="stSidebar"] [data-testid="stExpander"] summary p {{
  background-color: transparent !important;
  color: {text} !important;
  -webkit-text-fill-color: {text} !important;
  font-weight: 700 !important;
}}
html body [data-testid="stSidebar"] [data-testid="stExpanderDetails"],
html body [data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stVerticalBlock"] {{
  background-color: {surface} !important;
}}
html body [data-testid="stSidebar"] .stButton > button,
html body [data-testid="stSidebar"] [data-testid="stButton"] button,
html body [data-testid="stSidebar"] [data-testid="stLinkButton"] a,
html body [data-testid="stSidebar"] [data-testid="stLinkButton"] button {{
  background-color: {btn_bg} !important;
  color: {text} !important;
  -webkit-text-fill-color: {text} !important;
  border: 1px solid {border} !important;
  font-weight: 600 !important;
}}
html body [data-testid="stSidebar"] div[class*="st-key-menu_report_"] .stButton > button,
html body [data-testid="stSidebar"] div[class*="st-key-menu_report_"] [data-testid="stButton"] button,
html body [data-testid="stSidebar"] div[class*="st-key-menu_report_"] [data-testid="stBaseButton-primary"],
html body [data-testid="stSidebar"] div[class*="st-key-menu_report_"] [data-testid="stBaseButton-secondary"],
html body [data-testid="stSidebar"] div[class*="st-key-menu_report_"] button [data-testid="stMarkdownContainer"],
html body [data-testid="stSidebar"] div[class*="st-key-menu_report_"] button [data-testid="stMarkdownContainer"] *,
html body [data-testid="stSidebar"] div[class*="st-key-menu_report_"] [data-testid^="stBaseButton"] [data-testid="stMarkdownContainer"],
html body [data-testid="stSidebar"] div[class*="st-key-menu_report_"] [data-testid^="stBaseButton"] [data-testid="stMarkdownContainer"] * {{
  font-weight: 700 !important;
}}
html body [data-testid="stSidebar"] [data-testid="stExpanderDetails"] div[class*="st-key-menu_report_"] .stButton > button,
html body [data-testid="stSidebar"] [data-testid="stExpanderDetails"] div[class*="st-key-menu_report_"] [data-testid="stButton"] button,
html body [data-testid="stSidebar"] [data-testid="stExpanderDetails"] div[class*="st-key-menu_report_"] [data-testid^="stBaseButton"],
html body [data-testid="stSidebar"] [data-testid="stExpanderDetails"] div[class*="st-key-menu_report_"] button [data-testid="stMarkdownContainer"],
html body [data-testid="stSidebar"] [data-testid="stExpanderDetails"] div[class*="st-key-menu_report_"] button [data-testid="stMarkdownContainer"] * {{
  font-weight: 500 !important;
}}
html body {main_scope} [data-testid="stWidgetLabel"],
html body {main_scope} [data-testid="stWidgetLabel"] p,
html body {main_scope} [data-testid="stCheckbox"] label,
html body {main_scope} [data-testid="stCheckbox"] label p,
html body {main_scope} [data-testid="stRadio"] label,
html body {main_scope} [data-testid="stRadio"] label p,
html body {main_scope} [data-testid="stToggle"] label,
html body {main_scope} [data-testid="stToggle"] label p,
html body {main_scope} [data-testid="stSlider"] label,
html body {main_scope} [data-testid="stSlider"] label p {{
  color: {text} !important;
  -webkit-text-fill-color: {text} !important;
}}
{global_label_rule}
html body {main_scope} [data-testid="stSelectbox"] [data-baseweb="select"] > div,
html body {main_scope} [data-testid="stMultiSelect"] [data-baseweb="select"] > div,
html body {main_scope} [data-testid="stMultiSelect"] [data-baseweb="input"] input,
html body {main_scope} [data-testid="stSelectbox"] [data-baseweb="select"] span,
html body {main_scope} [data-testid="stMultiSelect"] span {{
  background-color: {input_bg} !important;
  color: {text} !important;
  border-color: {border} !important;
  -webkit-text-fill-color: {text} !important;
}}
html body {main_scope} [data-testid="stTextInput"] input,
html body {main_scope} [data-testid="stNumberInput"] input,
html body {main_scope} [data-testid="stDateInput"] input,
html body {main_scope} [data-baseweb="input"] input,
html body {main_scope} [data-baseweb="textarea"] textarea {{
  background-color: {input_bg} !important;
  color: {text} !important;
  border-color: {border} !important;
  -webkit-text-fill-color: {text} !important;
}}
html body {main_scope} [data-testid="stTextInput"] input::placeholder,
html body {main_scope} [data-baseweb="input"] input::placeholder {{
  color: {muted} !important;
  -webkit-text-fill-color: {muted} !important;
}}
html body [data-testid="stSidebar"] .stButton > button,
html body {main_scope} .stButton > button[kind="secondary"] {{
  background-color: {btn_bg} !important;
  color: {text} !important;
  border: 1px solid {border} !important;
}}
html body .stButton > button[kind="primary"],
html body .stButton > button[kind="primaryFormSubmit"],
html body [data-testid="stBaseButton-primary"],
html body [data-testid="baseButton-primary"],
html body [data-testid="stFormSubmitButton"] button,
html body [data-testid="stForm"] [data-testid="stBaseButton-primary"],
html body [data-testid="stForm"] [data-testid="baseButton-primary"] {{
  background-color: {accent} !important;
  border-color: {accent} !important;
  color: #ffffff !important;
  -webkit-text-fill-color: #ffffff !important;
}}
html body [data-testid="stBaseButton-primary"]:hover,
html body [data-testid="baseButton-primary"]:hover,
html body [data-testid="stFormSubmitButton"] button:hover,
html body [data-testid="stForm"] [data-testid="stBaseButton-primary"]:hover,
html body .stButton > button[kind="primary"]:hover,
html body .stButton > button[kind="primaryFormSubmit"]:hover {{
  background-color: color-mix(in srgb, {accent} 88%, #000000) !important;
  border-color: color-mix(in srgb, {accent} 88%, #000000) !important;
}}
{_selection_highlight_css(p, is_contrast)}
html body .showcase-demo-banner {{
  background: {p["banner_bg"]} !important;
  border: 1px solid {p["banner_border"]} !important;
  color: {p["banner_text"]} !important;
}}
html body .showcase-demo-banner strong {{
  color: {p["banner_strong"]} !important;
}}
html body .showcase-kpi {{
  background: linear-gradient(180deg, {p["accent_soft"]} 0%, {p["kpi_surface"]} 100%) !important;
  border: 1px solid {border} !important;
}}
html body .showcase-kpi-label,
html body .showcase-kpi-hint {{
  color: {muted} !important;
  -webkit-text-fill-color: {muted} !important;
}}
html body .showcase-kpi-value {{
  color: {text} !important;
  -webkit-text-fill-color: {text} !important;
}}
html body {main_scope} [data-testid="stExpander"] summary,
html body {main_scope} [data-testid="stExpander"] summary p,
html body {main_scope} [data-testid="stExpander"] summary span {{
  background-color: {surface if is_contrast else "#ffffff"} !important;
  color: {text} !important;
  border-color: {border} !important;
  -webkit-text-fill-color: {text} !important;
}}
html body [data-testid="stTabs"] [data-baseweb="tab-list"] {{
  background: color-mix(in srgb, {surface} 88%, {border}) !important;
  border-color: {border} !important;
}}
</style>
"""


def inject_showcase_active_theme_css(theme_key: str | None = None) -> None:
    if not _is_showcase():
        return
    key = theme_key or get_showcase_theme_key()
    st.markdown(_build_active_theme_css(key), unsafe_allow_html=True)


_SHOWCASE_LOGIN_BTN_CSS = """
@keyframes showcase-login-btn-shimmer {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}
html body div[class*="FormSubmitter-login_form"] button[kind="primaryFormSubmit"],
html body div[class*="FormSubmitter-login_form"] [data-testid="stBaseButton-primaryFormSubmit"],
html body .stFormSubmitButton[class*="login_form"] button[kind="primaryFormSubmit"] {
  background: linear-gradient(
    120deg,
    #2563eb 0%,
    #6366f1 16%,
    #a855f7 32%,
    #ec4899 48%,
    #f97316 64%,
    #14b8a6 80%,
    #2563eb 100%
  ) !important;
  background-color: transparent !important;
  background-size: 320% 320% !important;
  animation: showcase-login-btn-shimmer 5s ease infinite !important;
  border: none !important;
  color: #ffffff !important;
  -webkit-text-fill-color: #ffffff !important;
  font-weight: 700 !important;
  box-shadow: 0 4px 16px rgba(99, 102, 241, 0.35) !important;
}
html body div[class*="FormSubmitter-login_form"] button[kind="primaryFormSubmit"] [data-testid="stMarkdownContainer"],
html body div[class*="FormSubmitter-login_form"] button[kind="primaryFormSubmit"] [data-testid="stMarkdownContainer"] p,
html body div[class*="FormSubmitter-login_form"] [data-testid="stBaseButton-primaryFormSubmit"] [data-testid="stMarkdownContainer"],
html body div[class*="FormSubmitter-login_form"] [data-testid="stBaseButton-primaryFormSubmit"] [data-testid="stMarkdownContainer"] p {
  color: #ffffff !important;
  -webkit-text-fill-color: #ffffff !important;
}
html body div[class*="FormSubmitter-login_form"] button[kind="primaryFormSubmit"]:hover,
html body div[class*="FormSubmitter-login_form"] [data-testid="stBaseButton-primaryFormSubmit"]:hover,
html body .stFormSubmitButton[class*="login_form"] button[kind="primaryFormSubmit"]:hover {
  filter: brightness(1.06) saturate(1.08);
  box-shadow: 0 6px 20px rgba(99, 102, 241, 0.45) !important;
}
"""


def inject_showcase_login_button_css() -> None:
    """Кнопка «Войти» на экране входа — анимированный многоцветный градиент (только showcase)."""
    if not _is_showcase():
        return
    try:
        if get_showcase_theme_key() == "contrast":
            return
    except Exception:
        pass
    st.markdown(
        f'<style id="showcase-login-btn">{_SHOWCASE_LOGIN_BTN_CSS}</style>',
        unsafe_allow_html=True,
    )


def render_theme_switcher() -> None:
    """Переключатель цветовой темы (как в presentation HTML)."""
    if not _is_showcase():
        return
    if "showcase_theme" not in st.session_state:
        st.session_state["showcase_theme"] = "default"
    current = get_showcase_theme_key()
    cols = st.columns([1, 1, 1, 1, 2])
    for i, (key, label) in enumerate(_SHOWCASE_THEMES.items()):
        with cols[i]:
            if st.button(
                label,
                key=f"showcase_theme_{key}",
                type="primary" if current == key else "secondary",
                use_container_width=True,
            ):
                st.session_state["showcase_theme"] = key
                st.rerun()


def load_showcase_theme() -> None:
    """Светлая оболочка демо: таблицы, виджеты, сайдбар (без production style.css)."""
    if not _is_showcase():
        return
    apply_streamlit_light_config()
    apply_table_constants()
    theme_key = get_showcase_theme_key()
    if theme_key != "contrast":
        from dashboards.gdrs_theme import inject_gdrs_light_preview_css

        inject_gdrs_light_preview_css(st)
    # showcase_light.css жёстко задаёт #111827 — для «Контраста» не подключаем.
    if theme_key != "contrast":
        _inject_sidebar_light_css()
        extra = _REPO_ROOT / "showcase" / "theme" / "showcase_light.css"
        if extra.is_file():
            st.markdown(
                f"<style id='showcase-light-extra'>{extra.read_text(encoding='utf-8')}</style>",
                unsafe_allow_html=True,
            )
    themes = _REPO_ROOT / "showcase" / "theme" / "showcase_themes.css"
    if themes.is_file():
        st.markdown(
            f"<style id='showcase-themes'>{themes.read_text(encoding='utf-8')}</style>",
            unsafe_allow_html=True,
        )
    inject_showcase_active_theme_css(theme_key)
    inject_showcase_login_button_css()
    if theme_key == "contrast":
        contrast_data = _REPO_ROOT / "showcase" / "theme" / "showcase_contrast_data.css"
        if contrast_data.is_file():
            st.markdown(
                f"<style id='showcase-contrast-data'>{contrast_data.read_text(encoding='utf-8')}</style>",
                unsafe_allow_html=True,
            )
