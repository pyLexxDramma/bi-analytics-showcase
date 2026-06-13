"""
Точка входа для демо-инстанса (showcase) на Streamlit Cloud / локально.

Main file path в настройках второго приложения: ``showcase_app.py``
(основной клиентский дашборд по-прежнему: ``streamlit_app.py``).

Данные: ``showcase_data/web/`` (фейковые выгрузки), без доступа к ``bi-analytics-v-5-main/web/``.
"""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_APP_DIR = _ROOT / "bi-analytics-v-5-main"
_MAIN = _APP_DIR / "project_visualization_app.py"

if not _MAIN.is_file():
    raise FileNotFoundError(
        f"Не найден {_MAIN}. Проверьте структуру репозитория."
    )

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from showcase.bootstrap import apply as _apply_showcase_bootstrap

try:
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv(_ROOT / ".env", override=False)
    _load_dotenv(_APP_DIR / ".env", override=True)
except ImportError:
    pass

_apply_showcase_bootstrap(repo_root=_ROOT, app_dir=_APP_DIR)

os.chdir(_APP_DIR)
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from showcase.theme import apply_streamlit_light_config

apply_streamlit_light_config()

runpy.run_path(str(_MAIN), run_name="__main__")
