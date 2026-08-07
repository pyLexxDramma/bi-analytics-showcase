from __future__ import annotations

import os
import secrets
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

# CSV lookup `other_*_rd.csv` / `other_*_pd.csv` в core `_r23_12_load_rd_plan_lookup`
# читает BI_ANALYTICS_WEB_EXTRA_PATHS — прокидываем staging web/ при старте API.
try:
    _web_resolved = str(WEB_DATA_DIR.expanduser().resolve())
except Exception:
    _web_resolved = str(WEB_DATA_DIR)
if _web_resolved and Path(_web_resolved).is_dir():
    _extra = os.environ.get("BI_ANALYTICS_WEB_EXTRA_PATHS", "")
    _parts = [p.strip() for p in _extra.replace(";", ",").split(",") if p.strip()]
    _resolved: set[str] = set()
    for _p in _parts:
        try:
            _resolved.add(str(Path(_p).expanduser().resolve()))
        except Exception:
            _resolved.add(_p)
    if _web_resolved not in _resolved:
        _parts.append(_web_resolved)
        os.environ["BI_ANALYTICS_WEB_EXTRA_PATHS"] = ",".join(_parts)

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
# Состояние фоновых jobs — рядом с кэшем, но отдельно: cache_clear() чистит только кэш.
JOBS_DIR = Path(
    os.environ.get(
        "WEBAPP_JOBS_DIR",
        str(REPORT_CACHE_DIR.parent / "jobs"),
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
USERS_DB_PATH = Path(
    os.environ.get(
        "BI_USERS_DB",
        str(WEBAPP_ROOT / "data" / "users.db"),
    )
)
BOOTSTRAP_ADMIN_USERNAME = (
    os.environ.get("BI_BOOTSTRAP_ADMIN_USERNAME") or "admin"
).strip()
BOOTSTRAP_ADMIN_PASSWORD = (
    os.environ.get("BI_BOOTSTRAP_ADMIN_PASSWORD") or ""
).strip()
AUTH_SECRET_CONFIGURED = bool((os.environ.get("WEBAPP_AUTH_SECRET") or "").strip())
AUTH_SECRET = (
    (os.environ.get("WEBAPP_AUTH_SECRET") or "").strip()
    or secrets.token_urlsafe(32)
)
AUTH_TOKEN_TTL_SECONDS = int(os.environ.get("WEBAPP_AUTH_TOKEN_TTL_SECONDS", "28800"))
OPENCODE_BASE_URL = (
    os.environ.get("SHOWCASE_OPENCODE_URL") or "http://127.0.0.1:4096"
).rstrip("/")
OPENCODE_WORKSPACE = os.environ.get("SHOWCASE_OPENCODE_WORKSPACE", "/workspace").strip()
OPENCODE_TIMEOUT_SECONDS = float(
    os.environ.get("SHOWCASE_OPENCODE_TIMEOUT_SECONDS", "30")
)
VLLM_BASE_URL = (os.environ.get("SHOWCASE_VLLM_BASE_URL") or "").rstrip("/")
VLLM_API_KEY = (os.environ.get("SHOWCASE_VLLM_API_KEY") or "").strip()
VLLM_MODEL = (os.environ.get("SHOWCASE_VLLM_MODEL") or "").strip()
ASSISTANT_PENDING_TIMEOUT_SECONDS = int(
    os.environ.get("SHOWCASE_ASSISTANT_PENDING_TIMEOUT_SECONDS", "600")
)
AI_ENABLED = (os.environ.get("SHOWCASE_AI_ENABLED") or "0").strip() == "1"
ASSISTANT_DB_PATH = Path(
    os.environ.get(
        "SHOWCASE_ASSISTANT_DB",
        str(WEBAPP_ROOT / "data" / "db" / "assistant.db"),
    )
)
ASSISTANT_OUTPUT_DIR = Path(
    os.environ.get(
        "SHOWCASE_ASSISTANT_OUTPUT_DIR",
        str(WEBAPP_ROOT / "data" / "assistant_output"),
    )
)
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

# Свежесть данных: старше N часов → stale; авто-синк не чаще 1 раза за cooldown.
DATA_STALE_HOURS = float(os.environ.get("WEBAPP_DATA_STALE_HOURS", "26"))
ENSURE_FRESH_COOLDOWN_HOURS = float(os.environ.get("WEBAPP_ENSURE_FRESH_COOLDOWN_H", "4"))
ENSURE_FRESH_MARKER = Path(
    os.environ.get(
        "WEBAPP_ENSURE_FRESH_MARKER",
        str(WEBAPP_ROOT / "data" / ".ensure_fresh_last"),
    )
)
