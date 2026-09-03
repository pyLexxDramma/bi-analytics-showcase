# -*- coding: utf-8 -*-
"""Общие фикстуры/стабы для api tests.

Ставит package-aware stub Streamlit до импорта тестов, которые тянут
`dashboards._renderers` (иначе лёгкий stub ломает `streamlit.components`).
"""
from __future__ import annotations

from streamlit_stub import ensure_streamlit_stub

ensure_streamlit_stub()
