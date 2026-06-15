"""
Точка входа для Streamlit Community Cloud (алиас showcase).

В настройках приложения укажите Main file path: ``showcase_app.py``
или ``streamlit_app.py`` — оба запускают демо-инстанс.
"""
from __future__ import annotations

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent / "showcase_app.py"), run_name="__main__")
