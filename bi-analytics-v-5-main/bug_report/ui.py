"""UI баг-репорта в сайдбаре Streamlit."""

from __future__ import annotations

from typing import Any

import streamlit as st

from app_version import get_app_version
from auth import is_streamlit_context
from bug_report.service import submit_bug_report
from bug_report.settings import get_bug_report_settings


def _collect_page_context(user: dict[str, Any]) -> dict[str, Any]:
    report_tab = str(st.session_state.get("current_dashboard", "") or "")
    theme = "dark"
    try:
        from dashboards.light_theme import is_light_preview_report

        if report_tab and is_light_preview_report(report_tab):
            theme = "light"
    except Exception:
        pass

    page_url = ""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        ctx = get_script_run_ctx()
        if ctx and getattr(ctx, "session_id", None):
            page_url = st.context.url if hasattr(st, "context") else ""
    except Exception:
        page_url = ""

    version_id = None
    try:
        from web_db_read import resolve_version_id

        version_id = resolve_version_id()
    except Exception:
        pass

    build = get_app_version().get("label", "")

    return {
        "username": user.get("username", ""),
        "user_role": user.get("role", ""),
        "report_tab": report_tab,
        "page_url": page_url,
        "theme": theme,
        "version_id": version_id,
        "app_build": build,
    }


@st.dialog("Сообщить о проблеме", width="large")
def _bug_report_dialog(user: dict[str, Any]) -> None:
    ctx = _collect_page_context(user)
    st.caption(
        "Опишите проблему или пожелание. Контекст вкладки и пользователя прикрепится автоматически."
    )
    if ctx["report_tab"]:
        st.markdown(f"**Вкладка:** {ctx['report_tab']}")
    if ctx["theme"]:
        st.markdown(f"**Тема:** {ctx['theme']}")

    with st.form("bug_report_form", clear_on_submit=True):
        text = st.text_area(
            "Описание",
            placeholder="Например: на вкладке БДР не сходятся итоги за март…",
            height=140,
            max_chars=4000,
        )
        screenshot = st.file_uploader(
            "Скриншот (необязательно)",
            type=["png", "jpg", "jpeg", "webp", "gif"],
            accept_multiple_files=False,
        )
        submitted = st.form_submit_button("Отправить", type="primary", width="stretch")

    if not submitted:
        return
    if not (text or "").strip():
        st.error("Введите описание.")
        return

    attachment = None
    if screenshot is not None:
        attachment = (screenshot.name, screenshot.getvalue(), screenshot.type or "image/png")

    with st.spinner("Отправляем…"):
        result = submit_bug_report(
            user_text=text,
            username=ctx["username"],
            user_role=ctx["user_role"],
            report_tab=ctx["report_tab"],
            page_url=ctx["page_url"],
            theme=ctx["theme"],
            version_id=ctx["version_id"],
            app_build=ctx["app_build"],
            attachment=attachment,
        )

    if result.ok:
        st.success(result.message)
        if result.trello_card_url:
            st.link_button("Открыть карточку Trello", result.trello_card_url)
    else:
        st.error(result.message)


def render_bug_report_sidebar_entry(user: dict[str, Any]) -> None:
    """Кнопка в сайдбаре; вызывать из render_sidebar_menu."""
    if not is_streamlit_context():
        return
    settings = get_bug_report_settings()
    if not settings.enabled:
        return

    if st.button(
        "Сообщить о проблеме",
        width="stretch",
        icon="🐞",
        key="sidebar_bug_report",
        help="Отправить баг или пожелание (Trello).",
    ):
        _bug_report_dialog(user)
