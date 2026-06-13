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
    u.TABLE_CELL_BORDER_CSS = f"border: {u.TABLE_CELL_BORDER};"
    u.CHART_BG_COLOR = "rgba(255, 255, 255, 0.96)"
    u.TABLE_TOTAL_ROW_FONT_CSS = (
        "font-weight:800;font-size:1.32em;text-transform:uppercase;"
        "letter-spacing:0.05em;color:#111827;"
    )


def matrix_iframe_palette() -> Dict[str, str]:
    """Цвета iframe-матриц (девелоперские проекты, контрольные точки)."""
    if _is_showcase():
        return {
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
    """Showcase: переключает встроенную тему Streamlit на light (чекбоксы, календарь и др.)."""
    if not _is_showcase():
        return
    try:
        from streamlit import config as _cfg

        for key, val in (
            ("theme.base", "light"),
            ("theme.primaryColor", "#2563eb"),
            ("theme.backgroundColor", "#f8fafc"),
            ("theme.secondaryBackgroundColor", "#ffffff"),
            ("theme.textColor", "#111827"),
            ("theme.linkColor", "#1d4ed8"),
        ):
            try:
                _cfg.set_option(key, val)
            except Exception:
                pass
    except Exception:
        pass


def load_showcase_theme() -> None:
    """Светлая оболочка демо: таблицы, виджеты, сайдбар (без production style.css)."""
    if not _is_showcase():
        return
    apply_streamlit_light_config()
    apply_table_constants()
    from dashboards.gdrs_theme import inject_gdrs_light_preview_css

    inject_gdrs_light_preview_css(st)
    _inject_sidebar_light_css()
    extra = _REPO_ROOT / "showcase" / "theme" / "showcase_light.css"
    if extra.is_file():
        st.markdown(
            f"<style id='showcase-light-extra'>{extra.read_text(encoding='utf-8')}</style>",
            unsafe_allow_html=True,
        )
