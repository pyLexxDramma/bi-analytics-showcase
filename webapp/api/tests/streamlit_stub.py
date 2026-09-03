# -*- coding: utf-8 -*-
"""Стаб Streamlit для api-тестов без установленного пакета / без polluting stub."""
from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock


def ensure_streamlit_stub() -> None:
    """Стаб Streamlit как package + components.v1 (достаточно для импорта core)."""
    st = sys.modules.get("streamlit")
    needs_rebuild = st is None or not getattr(st, "__path__", None)
    if needs_rebuild:
        st = ModuleType("streamlit")
        st.__path__ = []  # type: ignore[attr-defined]
        st.cache_data = lambda **_kw: (lambda f: f)  # type: ignore[attr-defined]
        st.cache_resource = lambda **_kw: (lambda f: f)  # type: ignore[attr-defined]
        st.session_state = {}  # type: ignore[attr-defined]
        st.sidebar = MagicMock()
        for name in (
            "write",
            "markdown",
            "caption",
            "info",
            "warning",
            "error",
            "success",
            "button",
            "checkbox",
            "selectbox",
            "multiselect",
            "radio",
            "slider",
            "text_input",
            "number_input",
            "dataframe",
            "plotly_chart",
            "metric",
            "columns",
            "container",
            "expander",
            "empty",
            "spinner",
            "rerun",
            "stop",
            "set_page_config",
            "html",
            "download_button",
            "form",
            "form_submit_button",
            "tabs",
            "divider",
            "header",
            "subheader",
            "title",
            "code",
            "json",
            "image",
            "progress",
            "status",
        ):
            setattr(st, name, MagicMock())
        sys.modules["streamlit"] = st
    else:
        if not hasattr(st, "cache_data"):
            st.cache_data = lambda **_kw: (lambda f: f)  # type: ignore[attr-defined]
        if not hasattr(st, "cache_resource"):
            st.cache_resource = lambda **_kw: (lambda f: f)  # type: ignore[attr-defined]

    components = sys.modules.get("streamlit.components")
    if components is None or not getattr(components, "__path__", None):
        components = ModuleType("streamlit.components")
        components.__path__ = []  # type: ignore[attr-defined]
        sys.modules["streamlit.components"] = components
    st.components = components  # type: ignore[attr-defined]

    v1 = sys.modules.get("streamlit.components.v1")
    if v1 is None:
        v1 = ModuleType("streamlit.components.v1")
        v1.html = MagicMock()
        v1.iframe = MagicMock()
        sys.modules["streamlit.components.v1"] = v1
    components.v1 = v1  # type: ignore[attr-defined]
