"""
Настройка окружения для демо-инстанса (showcase).

Вызывается из ``showcase_app.py`` до ``runpy`` основного приложения.
Production ``streamlit_app.py`` этот модуль не импортирует.
"""
from __future__ import annotations

import os
from pathlib import Path


def apply(*, repo_root: Path, app_dir: Path) -> Path:
    """
    Выставляет env для showcase и возвращает путь к ``showcase_data/web``.

    Повторный вызов после ``load_dotenv`` перекрывает ключи из ``.env`` клиента.
    """
    showcase_web = (repo_root / "showcase_data" / "web").resolve()
    showcase_web.mkdir(parents=True, exist_ok=True)

    _flags = {
        "BI_ANALYTICS_SHOWCASE_MODE": "1",
        "BI_ANALYTICS_AUTO_INGEST": "0",
        "BI_ANALYTICS_AUTO_INGEST_FTP": "0",
        "BI_ANALYTICS_AUTO_FTP_ON_START": "0",
        "BI_ANALYTICS_HIDE_DEV_DIAGNOSTICS": "1",
        "BI_ANALYTICS_RELEASE_MODE": "1",
        "BI_ANALYTICS_WEB_INCLUDE_SIBLING": "0",
        "AI_ASSISTANT_TARGET": "off",
    }
    for key, val in _flags.items():
        os.environ[key] = val

    # Отдельные SQLite — не смешивать сессии/версии данных с основным дашбордом.
    showcase_data = (repo_root / "showcase_data").resolve()
    showcase_data.mkdir(parents=True, exist_ok=True)
    os.environ["BI_ANALYTICS_DB_PATH"] = str(showcase_data / "users.db")
    os.environ["WEB_DB_PATH"] = str(showcase_data / "web_data.db")

    # Не сканируем клиентский web/ — только showcase_data (см. web_loader._iter_web_scan_roots).
    os.environ.pop("BI_ANALYTICS_WEB_EXTRA_PATHS", None)

    return showcase_web
