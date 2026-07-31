"""Единая точка входа в код [main] (bi-analytics-v-5-main) из FastAPI-сервисов.

Здесь и только здесь: streamlit-stub, sys.path на core, подготовка web_data.db,
загрузка модулей dashboards.* и чтение версий из БД.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from app.config import CORE_APP_DIR, WEB_DB_PATH

_STUB_FLAG = "__bi_showcase_stub__"


class _NullNode:
    """Заглушка любого st.<...>: вызов, `with`, атрибут — no-op.

    Сервисы ничего не рендерят, но модули [main] дёргают st.* на уровне модуля.
    """

    def __call__(self, *args: Any, **kwargs: Any) -> "_NullNode":
        return self

    def __enter__(self) -> "_NullNode":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def __getattr__(self, name: str) -> "_NullNode":
        return self

    def __bool__(self) -> bool:
        return False

    def __iter__(self):
        return iter(())

    def __len__(self) -> int:
        return 0

    def __getitem__(self, key: Any) -> "_NullNode":
        return self


class _SessionState(dict):
    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value

    def __delattr__(self, name: str) -> None:
        self.pop(name, None)


def _cache_decorator(*args: Any, **kwargs: Any):
    def decorator(fn):
        return fn

    if len(args) == 1 and callable(args[0]) and not kwargs:
        return args[0]
    return decorator


def _real_streamlit_importable() -> bool:
    """find_spec без падения: по битому модулю в sys.modules он кидает ValueError."""
    if "streamlit" in sys.modules:
        return False
    try:
        return importlib.util.find_spec("streamlit") is not None
    except (ImportError, ValueError, AttributeError):
        return False


def _ensure_streamlit_submodules() -> None:
    """Подмодули, которые [main] импортирует напрямую (напр. streamlit.components.v1)."""
    parent = sys.modules.get("streamlit")
    if parent is None:
        return
    components = sys.modules.get("streamlit.components")
    if components is None:
        components = ModuleType("streamlit.components")
        sys.modules["streamlit.components"] = components
        parent.components = components  # type: ignore[attr-defined]
    v1 = sys.modules.get("streamlit.components.v1")
    if v1 is None:
        v1 = ModuleType("streamlit.components.v1")
        v1.html = _NullNode()  # type: ignore[attr-defined]
        v1.iframe = _NullNode()  # type: ignore[attr-defined]
        v1.declare_component = lambda *a, **k: _NullNode()  # type: ignore[attr-defined]
        sys.modules["streamlit.components.v1"] = v1
        components.v1 = v1  # type: ignore[attr-defined]


def _fill_stub(module: ModuleType) -> ModuleType:
    if getattr(module, "session_state", None) is None:
        module.session_state = _SessionState()  # type: ignore[attr-defined]
    for name in ("cache_data", "cache_resource"):
        if getattr(module, name, None) is None:
            setattr(module, name, _cache_decorator)
    if getattr(module, "__getattr__", None) is None:
        module.__getattr__ = lambda name: _NullNode()  # type: ignore[attr-defined]
    setattr(module, _STUB_FLAG, True)
    sys.modules["streamlit"] = module
    _ensure_streamlit_submodules()
    return module


def ensure_streamlit_stub() -> ModuleType:
    """Настоящий streamlit, если он есть; иначе полноценный stub (идемпотентно)."""
    existing = sys.modules.get("streamlit")
    if existing is not None:
        is_real = bool(getattr(existing, "__version__", None)) and getattr(
            existing, "cache_data", None
        ) is not None
        if is_real:
            return existing
        # чужой/урезанный stub (или наш) — дозаполняем недостающее
        return _fill_stub(existing)

    if _real_streamlit_importable():
        try:
            import streamlit  # noqa: F401

            return sys.modules["streamlit"]
        except Exception:  # noqa: BLE001 — падать из-за UI-зависимости нельзя
            sys.modules.pop("streamlit", None)

    stub = ModuleType("streamlit")
    stub.error = lambda *a, **kw: None  # type: ignore[attr-defined]
    stub.warning = lambda *a, **kw: None  # type: ignore[attr-defined]
    stub.info = lambda *a, **kw: None  # type: ignore[attr-defined]
    stub.success = lambda *a, **kw: None  # type: ignore[attr-defined]
    stub.write = lambda *a, **kw: None  # type: ignore[attr-defined]
    return _fill_stub(stub)


def ensure_core_path() -> Path:
    core = CORE_APP_DIR.resolve()
    if str(core) not in sys.path:
        sys.path.insert(0, str(core))
    return core


def ensure_renderers_shim() -> ModuleType:
    """`dashboards._renderers` как тонкий прокси на `dashboards.project_labels`.

    `dashboards/finance_from_1c.py` берёт из `_renderers` ровно два имени —
    `_project_filter_norm_key` и `_project_norm_key_matches_msp_keys`, — и оба
    в [main] являются алиасами функций из `dashboards/project_labels.py`.
    Настоящий `_renderers` тянет `streamlit.components.v1` и `plotly`, которых
    в образе API нет, поэтому регистрируем прокси всегда: локально и на стенде
    финансовый пайплайн идёт одним и тем же кодом.
    """
    existing = sys.modules.get("dashboards._renderers")
    if existing is not None:
        return existing
    labels = import_dashboard_module("project_labels")
    shim = ModuleType("dashboards._renderers")
    shim.__bi_showcase_renderers_shim__ = True  # type: ignore[attr-defined]
    shim._project_filter_norm_key = labels.project_filter_norm_key  # type: ignore[attr-defined]
    shim._project_norm_key_matches_msp_keys = labels._project_norm_key_matches_msp_keys  # type: ignore[attr-defined]
    sys.modules["dashboards._renderers"] = shim
    package = sys.modules.get("dashboards")
    if package is not None:
        package._renderers = shim  # type: ignore[attr-defined]
    return shim


def prepare_core_env() -> Path:
    """stub + sys.path + env-флаги ETL. Возвращает каталог core."""
    ensure_streamlit_stub()
    core = ensure_core_path()
    if not (core / "web_loader.py").is_file():
        raise FileNotFoundError(f"web_loader.py не найден в {core}")

    db_path = WEB_DB_PATH.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    os.environ["WEB_DB_PATH"] = str(db_path)
    # не сканировать соседний Analitics/web и не дёргать FTP на импорте
    os.environ["BI_ANALYTICS_WEB_INCLUDE_SIBLING"] = "0"
    os.environ["BI_ANALYTICS_AUTO_FTP_ON_START"] = "0"
    os.environ.pop("BI_ANALYTICS_WEB_EXTRA_PATHS", None)
    return core


def prepare_web_db() -> str:
    """prepare_core_env + web_schema.WEB_DB_PATH. Возвращает путь к БД."""
    prepare_core_env()
    db_path = str(WEB_DB_PATH.resolve())
    import web_schema  # type: ignore

    web_schema.WEB_DB_PATH = db_path
    return db_path


def import_dashboard_module(name: str) -> ModuleType:
    """dashboards.<name> без выполнения dashboards/__init__.py (тянет streamlit UI)."""
    ensure_streamlit_stub()
    ensure_core_path()
    full = f"dashboards.{name}"
    existing = sys.modules.get(full)
    if existing is not None:
        return existing
    if "dashboards" not in sys.modules:
        pkg = ModuleType("dashboards")
        pkg.__path__ = [str((CORE_APP_DIR / "dashboards").resolve())]  # type: ignore[attr-defined]
        sys.modules["dashboards"] = pkg
    path = CORE_APP_DIR / "dashboards" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(full, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(full, None)
        raise
    return module


def active_version_id() -> int | None:
    prepare_web_db()
    import web_schema  # type: ignore

    vid = web_schema.get_active_version_id()
    return int(vid) if vid else None


def load_version_df(version_id: int, file_type: str):
    """DataFrame строк web_data по (version_id, file_type) — единственный источник UI."""
    prepare_web_db()
    from web_db_read import load_version_dataframe  # type: ignore

    return load_version_dataframe(int(version_id), file_type)


def load_msp_frame(version_id: int):
    """Кадр MSP как `st.session_state.project_data` в [main] (project + budget, дедуп снимков)."""
    prepare_web_db()
    from web_loader import _build_project_frames, _web_db_mtime  # type: ignore

    _, frame = _build_project_frames(int(version_id), _web_db_mtime())
    return frame


def session_state() -> Any:
    """`st.session_state` активного stub/streamlit: код [main] читает оттуда `reference_1c_dannye`."""
    return ensure_streamlit_stub().session_state
