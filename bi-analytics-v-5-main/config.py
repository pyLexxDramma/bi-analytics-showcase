"""
Общая конфигурация приложения BI Analytics.
Единый источник для путей, констант и при необходимости переменных окружения.
"""
import os
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional

try:
    from dotenv import load_dotenv as _load_dotenv
except ImportError:  # pragma: no cover
    _load_dotenv = None  # type: ignore[misc, assignment]


def _apply_simple_env_file(path: Path, *, override: bool) -> None:
    """Минимальная подстановка KEY=VALUE из .env без пакета python-dotenv."""
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if not key:
            continue
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        if override or key not in os.environ:
            os.environ[key] = val


_APP_DIR = Path(__file__).resolve().parent
_parent_env = _APP_DIR.parent / ".env"
_local_env = _APP_DIR / ".env"
if _load_dotenv is not None:
    # Родительский .env (корень репо рядом с корневым streamlit_app.py), затем каталог приложения — второй перекрывает ключи.
    if _parent_env.is_file():
        _load_dotenv(_parent_env, override=False)
    _load_dotenv(_local_env, override=True)
else:
    _apply_simple_env_file(_parent_env, override=False)
    _apply_simple_env_file(_local_env, override=True)


def switch_page_app(path: str) -> None:
    """
    Переход на страницу multipage. ``path`` — как в ``st.switch_page``, относительно
    каталога **главного скрипта** Streamlit.

    - Запуск ``bi-analytics-v-5-main/project_visualization_app.py`` — страницы во
      вложенном приложении, путь ``pages/_admin.py`` / ``pages/_analyst_params.py`` валиден.

    - Запуск ``streamlit_app.py`` из корня репозитория: Streamlit регистрирует только
      ``<корень>/pages/*.py``. Рядом с ``streamlit_app.py`` добавлены прокси-файлы,
      делегирующие во ``bi-analytics-v-5-main/pages/`` (см. корневой каталог ``pages/``).
    """
    import streamlit as st
    from streamlit.errors import StreamlitAPIException

    normalized = path.replace("\\", "/").lstrip("/")
    candidates: list[str] = [normalized]

    # Streamlit Cloud / обертка через streamlit_app.py:
    # страница дашбордов может быть зарегистрирована под корневым файлом.
    if normalized.endswith("project_visualization_app.py"):
        candidates.append("streamlit_app.py")

    # Для совместимости добавляем вариант по basename для страниц из папки pages/.
    if "/" in normalized:
        candidates.append(normalized.split("/")[-1])

    tried: set[str] = set()
    last_err: Exception | None = None
    for cand in candidates:
        if not cand or cand in tried:
            continue
        tried.add(cand)
        try:
            st.switch_page(cand)
            return
        except StreamlitAPIException as e:
            last_err = e
            continue

    if last_err is not None:
        raise last_err

# Пути
BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
BASE_PATH: Path = Path(BASE_DIR).resolve()


def include_analytics_sibling_web_dir() -> bool:
    """
    Сканировать ``.../Analitics/web`` рядом с репозиторием.

    По умолчанию выключено — local/dev/release читают только ``web/`` внутри приложения
    (как Streamlit Cloud и VPS после FTP-sync). Включить: ``BI_ANALYTICS_WEB_INCLUDE_SIBLING=1``.
    """
    return _env_truthy("BI_ANALYTICS_WEB_INCLUDE_SIBLING")


def get_analytics_sibling_web_dir() -> Optional[Path]:
    """
    Каталог данных «Analitics/web»: на уровень выше вложенного репозитория.

    Если приложение лежит в ``.../Analitics/bi-analytics-v-5-main/bi-analytics-v-5-main/``,
    возвращает ``.../Analitics/web``, если эта папка существует.

    Так можно хранить большие выгрузки вне Git рядом с проектом и подгружать их вместе с локальным ``web/``.
    """
    try:
        cand = BASE_PATH.parent.parent / "web"
        if cand.is_dir():
            return cand
    except (OSError, ValueError):
        pass
    return None


def get_extra_web_dirs_from_env() -> List[Path]:
    """
    Дополнительные корни для CSV/JSON (разделители ``;`` или ``,``).

    Переменная окружения: ``BI_ANALYTICS_WEB_EXTRA_PATHS``.
    Относительные пути разрешаются от текущего рабочего каталога процесса.
    """
    raw = os.environ.get("BI_ANALYTICS_WEB_EXTRA_PATHS", "").strip()
    if not raw:
        return []
    out: List[Path] = []
    seen: set = set()
    for part in raw.replace(";", ",").split(","):
        p = part.strip()
        if not p:
            continue
        try:
            path = Path(p).expanduser()
            if not path.is_absolute():
                path = (Path.cwd() / path).resolve()
            else:
                path = path.resolve()
            if path.is_dir():
                key = str(path)
                if key not in seen:
                    seen.add(key)
                    out.append(path)
        except (OSError, ValueError):
            continue
    return out


def _read_env_or_secret(name: str) -> str:
    """Значение переменной из ``os.environ`` или (fallback) из ``st.secrets``.

    На Streamlit Cloud переменные верхнего уровня ``secrets.toml`` копируются
    в ``os.environ`` только после первого обращения к ``st.secrets`` (lazy
    load). До этого момента ``os.environ.get("BI_ANALYTICS_RELEASE_MODE")``
    возвращает пустую строку — даже если в secrets написано ``= "1"``.
    Из-за этого ``is_release_client_mode()`` возвращал False на release →
    был виден тумблер «Подмешивать демо-данные» и в БД попадали sample_*.

    Здесь сначала читаем env (быстро, без импорта streamlit при cold-start),
    а если пусто — пытаемся прочитать ``st.secrets[name]`` (что заодно
    тригерит lazy-load и заполняет os.environ для последующих вызовов).
    """
    val = os.environ.get(name, "")
    if val:
        return str(val).strip()
    try:
        import streamlit as st  # type: ignore
        # st.secrets — Mapping; .get() безопасен при отсутствии ключа.
        v = st.secrets.get(name, None) if hasattr(st, "secrets") else None
    except Exception:
        v = None
    return str(v).strip() if v is not None else ""


def _env_truthy(name: str) -> bool:
    return _read_env_or_secret(name).lower() in ("1", "true", "yes", "on")


def _env_falsy(name: str) -> bool:
    return _read_env_or_secret(name).lower() in ("0", "false", "no", "off")


@lru_cache(maxsize=1)
def _git_current_branch() -> str:
    """Текущая git-ветка приложения. Кешируется на процесс. На сервере без git вернёт ''."""
    try:
        br = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(BASE_PATH),
            capture_output=True,
            text=True,
            timeout=1.5,
        )
        return (br.stdout or "").strip().lower()
    except Exception:
        return ""



def _streamlit_request_host() -> str:
    try:
        import streamlit as st  # type: ignore

        ctx = getattr(st, "context", None)
        headers = getattr(ctx, "headers", None) if ctx is not None else None
        if headers is not None:
            try:
                h = str(headers.get("Host") or headers.get("host") or "").strip().lower()
                if h:
                    return h
            except Exception:
                pass
        try:
            return str(getattr(ctx, "url", "") or "").strip().lower()
        except Exception:
            return ""
    except Exception:
        return ""


def _is_streamlit_dev_deployment() -> bool:
    """Streamlit Cloud dev app (не client release)."""
    if _env_truthy("BI_ANALYTICS_DEV_MODE"):
        return True
    host = _streamlit_request_host()
    if "bi-analytics-dev" in host:
        return True
    pub = _read_env_or_secret("BI_STREAMLIT_PUBLIC_URL").strip().lower()
    return "bi-analytics-dev" in pub


def is_release_client_mode() -> bool:
    """
    Единый предикат «клиентского релиза».

    True, если выполнено ЛЮБОЕ из:

    - ``BI_ANALYTICS_HIDE_DEV_DIAGNOSTICS=1`` — явный флаг для деплоя на хостинге без git
      (Streamlit Cloud, Docker, systemd unit). Рекомендуется для production.
    - ``BI_ANALYTICS_RELEASE_MODE=1`` — синоним явного флага.
    - текущая git-ветка приложения = ``release`` — чтобы при работе из этой ветки локально
      поведение совпадало с production.

    Используется:
    - ``project_visualization_app.py`` — скрытие dev-диагностики в UI.
    - ``ignore_demo_data_files()`` — демо ``new_csv/`` не подмешиваются.
    """
    if _env_truthy("BI_ANALYTICS_HIDE_DEV_DIAGNOSTICS"):
        return True
    if _env_truthy("BI_ANALYTICS_RELEASE_MODE"):
        return True
    if _git_current_branch() == "release":
        return True
    host = _streamlit_request_host()
    if "streamlit.app" in host:
        return not _is_streamlit_dev_deployment()
    return False


def use_light_theme_globally() -> bool:
    """
    Единственная светлая тема (cutover 2026-06, решение заказчика).

    Откат на тёмную: ``BI_ANALYTICS_DARK_THEME=1``.
    """
    if _env_truthy("BI_ANALYTICS_DARK_THEME"):
        return False
    return True


def show_light_preview_reports() -> bool:
    """
    Дубли вкладок «(превью — светлая)» — отключены после cutover.

    Dev-only dual-tab: ``BI_ANALYTICS_LIGHT_PREVIEW=1``.
    """
    if _env_truthy("BI_ANALYTICS_LIGHT_PREVIEW"):
        return True
    return False


def show_data_ops_ui_for_role(role: Optional[str]) -> bool:
    """
    Показывать панель «Источник данных», FTP, «Загрузить из web/», «Версия данных».

    Только admin / superadmin / analyst; на release (клиент) — False.
    """
    if is_release_client_mode():
        return False
    try:
        from auth import user_can_ftp_sync

        return bool(user_can_ftp_sync(role))
    except Exception:
        return False


def is_dev_branch() -> bool:
    """Текущая git-ветка = ``dev`` (или содержит «dev» в начале/как префикс)."""
    br = _git_current_branch()
    return br == "dev" or br.startswith("dev/") or br.startswith("dev-")


def _xca_workspace_dir() -> str:
    ws = _read_env_or_secret("XCA_WORKSPACE_DIR").strip()
    return ws or "/workspace"


def _opencode_ui_url_module():
    import sys
    from pathlib import Path as _Path

    ow = _Path(__file__).resolve().parent / "opencode_web"
    if not ow.is_dir():
        return None
    ow_s = str(ow)
    if ow_s not in sys.path:
        sys.path.insert(0, ow_s)
    import opencode_ui_url as mod

    return mod


def _opencode_workspace_url(public_base: str) -> str:
    """Public OpenCode Web UI URL (/workspace)."""
    base = (public_base or "").strip().rstrip("/")
    if not base:
        return ""
    try:
        mod = _opencode_ui_url_module()
        if mod is not None:
            return mod.normalize_opencode_browser_url(base, _xca_workspace_dir())
    except Exception:
        pass
    return f"{base}/L3dvcmtzcGFjZQ/"


# OpenCode Web UI: slug /workspace — первый сегмент пути, поддомен в корне.
AI_ASSISTANT_URL_SUBDOMAIN_DEFAULT = "https://opencode.conall.ru/L3dvcmtzcGFjZQ/"
AI_ASSISTANT_URL_PATH_FALLBACK = "https://ai.conall.ru/opencode/L3dvcmtzcGFjZQ/"
AI_ASSISTANT_WEB_UI_DEFAULT = AI_ASSISTANT_URL_SUBDOMAIN_DEFAULT
AI_ASSISTANT_URL_DEV_DEFAULT = AI_ASSISTANT_WEB_UI_DEFAULT
AI_ASSISTANT_URL_PROD_DEFAULT = AI_ASSISTANT_WEB_UI_DEFAULT
AI_ASSISTANT_URL_EMBEDDED_DEFAULT = "https://bi-analytics-dev.streamlit.app/_opencode_ai"

AI_ASSISTANT_PAGE = "pages/_opencode_ai.py"


def _is_streamlit_cloud_deployment() -> bool:
    return "streamlit.app" in _streamlit_request_host()


def _ai_ssh_tunnel_configured() -> bool:
    return _env_truthy("ENABLE_SSH_TUNNEL") and bool(_read_env_or_secret("AI_SSH_HOST").strip())


def _embedded_ai_url_for_current_app() -> str:
    embedded = _read_env_or_secret("AI_ASSISTANT_URL_EMBEDDED").strip()
    if embedded:
        return embedded
    host = _streamlit_request_host()
    if host:
        h = host.split("/")[0].split(":")[0].strip()
        if h.endswith(".streamlit.app"):
            return f"https://{h}/_opencode_ai"
    pub = _read_env_or_secret("BI_STREAMLIT_PUBLIC_URL").strip().rstrip("/")
    if pub:
        return f"{pub}/_opencode_ai"
    return AI_ASSISTANT_URL_EMBEDDED_DEFAULT


def _normalize_ai_assistant_public_url(url: str) -> str:
    """OpenCode Web UI: slug /workspace первым сегментом пути (поддомен в корне)."""
    u = (url or "").strip()
    if not u or "_opencode_ai" in u.lower():
        return u
    try:
        mod = _opencode_ui_url_module()
        if mod is not None and mod.is_opencode_web_ui_url(u):
            return mod.normalize_opencode_browser_url(u, _xca_workspace_dir())
    except Exception:
        pass
    return u


def _ai_assistant_use_streamlit_embedded() -> bool:
    """
    Streamlit-страница /_opencode_ai — только явный opt-in (локальная отладка чата).

    ``AI_ASSISTANT_TARGET=embedded`` на Streamlit Cloud / release больше не включает обёртку:
    кнопка открывает нативный Web UI OpenCode (поддомен).
    """
    if not _env_truthy("AI_ASSISTANT_USE_EMBEDDED"):
        return False
    target = _read_env_or_secret("AI_ASSISTANT_TARGET").strip().lower()
    return target in ("embedded", "streamlit", "wrap", "wrapper")


def is_ai_assistant_embedded_page() -> bool:
    """True only for in-app Streamlit chat (/_opencode_ai), not native OpenCode Web UI."""
    if not _ai_assistant_use_streamlit_embedded():
        return False
    url = (get_ai_assistant_open_url() or "").strip().lower()
    return "_opencode_ai" in url


def get_ai_assistant_open_url() -> str:
    """
    URL кнопки «ИИ помощник».

    Приоритет:
    1. AI_ASSISTANT_URL (или XCA_AI_CHAT_URL / AI_CHAT_PUBLIC_URL)
    2. AI_ASSISTANT_TARGET=dev|prod|embedded|off|auto (по умолчанию auto)
       - dev → AI_ASSISTANT_URL_DEV; release → AI_ASSISTANT_URL_PROD (Web UI OpenCode, поддомен)
       - embedded без AI_ASSISTANT_USE_EMBEDDED=1 → тот же Web UI, не Streamlit /_opencode_ai
       - Streamlit-обёртка: AI_ASSISTANT_USE_EMBEDDED=1 и AI_ASSISTANT_TARGET=embedded (локально)
    """
    for key in ("AI_ASSISTANT_URL", "XCA_AI_CHAT_URL", "AI_CHAT_PUBLIC_URL"):
        u = _read_env_or_secret(key).strip()
        if u:
            return _normalize_ai_assistant_public_url(u)

    target = _read_env_or_secret("AI_ASSISTANT_TARGET").strip().lower() or "auto"
    if target in ("off", "none", "0", "false"):
        return ""

    prod_url = _normalize_ai_assistant_public_url(
        _read_env_or_secret("AI_ASSISTANT_URL_PROD").strip() or AI_ASSISTANT_URL_PROD_DEFAULT
    )
    dev_url = _normalize_ai_assistant_public_url(
        _read_env_or_secret("AI_ASSISTANT_URL_DEV").strip() or AI_ASSISTANT_URL_DEV_DEFAULT
    )

    if target == "prod" or _env_truthy("AI_ASSISTANT_USE_PROD"):
        return prod_url

    if target == "embedded":
        if _ai_assistant_use_streamlit_embedded():
            return _embedded_ai_url_for_current_app()
        if is_release_client_mode():
            return prod_url
        if _is_streamlit_dev_deployment() or _is_streamlit_cloud_deployment():
            return dev_url
        return dev_url

    if target == "dev":
        return dev_url

    # dev / local — Web UI OpenCode
    if _is_streamlit_dev_deployment() or (not is_release_client_mode()):
        return dev_url

    # release (auto и пр.) — Web UI OpenCode, как на dev
    return prod_url



def default_include_demo_data() -> bool:
    """Демо-данные отключены — только выгрузки из web/."""
    return False


def ignore_demo_data_files() -> bool:
    """Не подмешивать ``new_csv/``, ``sample_*.csv`` и пути с ``…/new_csv/`` в web/."""
    return True


def web_load_latest_snapshots_only() -> bool:
    """
    При загрузке из ``web/``: оставлять только последний снимок по дате в имени файла
    (1С, TESSA, MSP, выгрузки с датой в названии), чтобы не раздувать SQLite и память.

    По умолчанию включено (не задано или ``1``/``true``/``yes``/``on``).
    Полная история всех файлов: ``BI_ANALYTICS_WEB_LATEST_ONLY=0`` (или ``false``/``no``/``off``).
    """
    v = os.environ.get("BI_ANALYTICS_WEB_LATEST_ONLY", "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    if v in ("1", "true", "yes", "on"):
        return True
    return True


DB_PATH: str = os.path.join(BASE_DIR, "users.db")
ETL_DB_ENGINE: str = os.environ.get("DB_ENGINE", "sqlite").strip().lower()
ETL_SQLITE_DB_PATH: str = os.environ.get(
    "SQLITE_DB_PATH",
    os.path.join(BASE_DIR, "data", "etl.db"),
)
DATA_MODE: str = os.environ.get("DATA_MODE", "auto").strip().lower()

# Точные подписи «project name», которые не показываем в фильтрах (устаревший дубликат написания).
# Важно: сравнение по строке, не по norm-key — иначе скрывались бы и «Дмитровский 1», если в исключении «Дмитровский-1».
MSP_PROJECT_FILTER_EXCLUDE_NAMES: FrozenSet[str] = frozenset({"Дмитровский-1", "Барышы 2"})

MSP_PROJECT_NAME_MAP: Dict[str, str] = {
    "dmitrovsky1": "Дмитровский-1",
    "dmitrovsky": "Дмитровский",
    # 1С Projekts.json / dannye: «Дмитровский-1», лат. I вместо 1
    "дмитровский-1": "Дмитровский-1",
    "дмитровскийi": "Дмитровский-1",
    "esipovo5": "Есипово-5",
    "esipovo": "Есипово",
    "leninsky": "Ленинский",
    "leninsky1": "Ленинский",
    "koledino": "Коледино",
    "novorizhskiy": "Новорижский",
    "zhukovsky1": "Жуковский",
    "zhukovsky": "Жуковский",
    "дмитровский1": "Дмитровский-1",
    "дмитровский": "Дмитровский",
    "есипово5": "Есипово-5",
    "есипово": "Есипово",
    "ленинский": "Ленинский",
    "новорижский": "Новорижский",
    "жуковский1": "Жуковский",
    "жуковский": "Жуковский",
    # Короткие коды из шапок MSP-выгрузок (колонка «project name» у корневой задачи).
    # Без этого маппинга в фильтре «Проект (ур. 1)» появляются D1/E5/Л1 вместо
    # нормальных русских названий из 1с_*_Projekts.json.
    "d1": "Дмитровский-1",
    "е1": "Дмитровский-1",
    "e1": "Дмитровский-1",
    "e5": "Есипово-5",
    "е5": "Есипово-5",
    "л1": "Ленинский",
    "l1": "Ленинский",
}

# Выгрузка файлов на FTP (1С / MSP / TESSA) — согласованное расписание заказчика.
FTP_EXPORT_HOUR_MSK: int = int(os.environ.get("BI_FTP_EXPORT_HOUR_MSK", "7") or 7)
FTP_EXPORT_MINUTE_MSK: int = int(os.environ.get("BI_FTP_EXPORT_MINUTE_MSK", "0") or 0)
FTP_EXPORT_GRACE_MINUTES: int = int(os.environ.get("BI_FTP_EXPORT_GRACE_MIN", "15") or 15)


def ftp_export_schedule_label() -> str:
    """Человекочитаемое расписание выгрузки на FTP."""
    return f"ежедневно в {FTP_EXPORT_HOUR_MSK:02d}:{FTP_EXPORT_MINUTE_MSK:02d} (МСК)"


def _moscow_now():
    from datetime import datetime

    try:
        import pytz

        return datetime.now(pytz.timezone("Europe/Moscow"))
    except Exception:
        from datetime import timedelta, timezone

        return datetime.now(timezone(timedelta(hours=3)))


def is_before_today_ftp_export_window(*, grace_minutes: Optional[int] = None) -> bool:
    """True, если по МСК ещё рано ждать сегодняшнюю выгрузку на FTP."""
    grace = FTP_EXPORT_GRACE_MINUTES if grace_minutes is None else int(grace_minutes)
    now = _moscow_now()
    export_min = FTP_EXPORT_HOUR_MSK * 60 + FTP_EXPORT_MINUTE_MSK + max(0, grace)
    cur_min = now.hour * 60 + now.minute
    return cur_min < export_min


# Русские названия месяцев (для графиков и отчётов)
RUSSIAN_MONTHS: Dict[int, str] = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}
