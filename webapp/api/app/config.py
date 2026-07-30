from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# webapp/api/.env (local FTP etc.) — before reading os.environ
_API_DIR = Path(__file__).resolve().parents[1]
load_dotenv(_API_DIR / ".env", override=False)

_APP_FILE = Path(__file__).resolve()


def _detect_showcase_root() -> Path:
    for p in _APP_FILE.parents:
        if (p / "showcase_data" / "web").is_dir() or (p / "showcase_app.py").is_file():
            return p
    # fallback: webapp/api/app → parents[3]
    try:
        return _APP_FILE.parents[3]
    except IndexError:
        return Path.cwd()


SHOWCASE_ROOT = Path(os.environ.get("SHOWCASE_ROOT", str(_detect_showcase_root())))
WEBAPP_ROOT = Path(
    os.environ.get(
        "WEBAPP_ROOT",
        str(
            SHOWCASE_ROOT / "webapp"
            if (SHOWCASE_ROOT / "webapp").is_dir()
            else _APP_FILE.parents[1]
        ),
    )
)

# synthetic (default): showcase_data/web — публичное демо без клиентских данных
# ftp: webapp/data/web — выгрузки как на ai.conall.ru (секреты BI_FTP_*)
DATA_MODE = (os.environ.get("WEBAPP_DATA_MODE") or "synthetic").strip().lower()
if DATA_MODE not in ("synthetic", "ftp"):
    DATA_MODE = "synthetic"

_default_web = (
    SHOWCASE_ROOT / "showcase_data" / "web"
    if DATA_MODE == "synthetic"
    else WEBAPP_ROOT / "data" / "web"
)
WEB_DATA_DIR = Path(os.environ.get("SHOWCASE_WEB_DIR", str(_default_web)))

# SQLite как в [main]: после FTP/web → load_all_from_web()
WEB_DB_PATH = Path(
    os.environ.get(
        "WEB_DB_PATH",
        str(WEBAPP_ROOT / "data" / "web_data.db"),
    )
)
REPORT_CACHE_DIR = Path(
    os.environ.get(
        "WEBAPP_REPORT_CACHE_DIR",
        str(WEBAPP_ROOT / "data" / "report_cache"),
    )
)

CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "WEBAPP_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if o.strip()
]
API_TITLE = "BI Analytics Showcase API"
API_VERSION = "0.19.0"
ADMIN_SYNC_TOKEN = (os.environ.get("WEBAPP_ADMIN_TOKEN") or "").strip()
def _detect_core_app_dir() -> Path:
    env = (os.environ.get("BI_CORE_APP_DIR") or "").strip()
    if env:
        return Path(env)
    candidates = [
        SHOWCASE_ROOT.parent / "bi-analytics-v-5-main" / "bi-analytics-v-5-main",
        SHOWCASE_ROOT / "bi-analytics-v-5-main",
    ]
    for c in candidates:
        if (c / "web_loader.py").is_file() and (c / "web_db_read.py").is_file():
            return c
    for c in candidates:
        if (c / "web_loader.py").is_file():
            return c
    return candidates[-1]


CORE_APP_DIR = _detect_core_app_dir()
