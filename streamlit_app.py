"""
Точка входа в корне репозитория для Streamlit Community Cloud.

Укажите в настройках приложения Main file path: streamlit_app.py
(так Cloud гарантированно находит модуль; внутри делегируем реальному приложению).
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
        f"Не найден {_MAIN}. Проверьте структуру репозитория на GitHub."
    )

# Переменные для кнопки «ИИ помощник» и прочего: корневой .env (рядом с этим файлом),
# затем .env в каталоге приложения (перекрывает корень). Иначе при запуске
# ``streamlit run streamlit_app.py`` не подхватится только вложенный ``.env``.
try:
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv(_ROOT / ".env", override=False)
    _load_dotenv(_APP_DIR / ".env", override=True)
except ImportError:
    pass

# Главной точкой входа остаётся этот файл; multipage-страницы Streamlit видит в
# <корень>/pages/ — см. прокси рядом с этим скриптом (делегирование в bi-analytics-v-5-main/pages/).

os.chdir(_APP_DIR)
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

# Production (8501, main, release, Streamlit Cloud): только FTP/web/, не showcase_data.
from config import enforce_production_data_isolation

enforce_production_data_isolation()

runpy.run_path(str(_MAIN), run_name="__main__")
