# -*- coding: utf-8 -*-
"""
Содержимое вкладок административной панели (без Streamlit bootstrap страницы).

Импортируется из pages/profile.py и pages/_admin.py.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date, time, timezone

_TABLE_CSS_DARK = (
    "<style>"
    ".ht-wrap{overflow-x:auto;min-width:0;margin:.5rem 0 1rem}"
    ".ht{width:100%;border-collapse:collapse;font-size:13px;font-family:Inter,system-ui,sans-serif}"
    ".ht th{text-align:center!important;vertical-align:bottom;position:sticky;top:0;background:#1a1c23;color:#fafafa;padding:6px 8px;"
    "border-bottom:2px solid #444;font-weight:600;white-space:normal;word-wrap:break-word;overflow-wrap:anywhere;line-height:1.25;max-width:11em;overflow:visible;text-overflow:clip;vertical-align:bottom}"
    ".ht td{text-align:center;vertical-align:middle;padding:5px 8px;border-bottom:1px solid #333;color:#e0e0e0;white-space:normal;"
    "word-wrap:break-word;overflow-wrap:anywhere;max-width:28em;overflow:visible;text-overflow:clip;vertical-align:top}"
    ".ht th.col-text,.ht td.col-text{text-align:left;vertical-align:top}"
    ".ht th{text-align:center!important}"
    ".ht tr:hover td{background:#262833}"
    "</style>"
)

_TABLE_CSS_LIGHT = (
    "<style>"
    ".ht-wrap{overflow-x:auto;min-width:0;margin:.5rem 0 1rem}"
    ".ht{width:100%;border-collapse:collapse;font-size:13px;font-family:Inter,system-ui,sans-serif}"
    ".ht th{text-align:center!important;vertical-align:bottom;position:sticky;top:0;background:#f3f4f6;color:#111827;padding:6px 8px;"
    "border-bottom:2px solid #cbd5e1;font-weight:700;white-space:normal;word-wrap:break-word;overflow-wrap:anywhere;line-height:1.25;max-width:11em;overflow:visible;text-overflow:clip;vertical-align:bottom}"
    ".ht td{text-align:center;vertical-align:middle;padding:5px 8px;border-bottom:1px solid #e5e7eb;color:#111827;white-space:normal;"
    "word-wrap:break-word;overflow-wrap:anywhere;max-width:28em;overflow:visible;text-overflow:clip;vertical-align:top}"
    ".ht th.col-text,.ht td.col-text{text-align:left;vertical-align:top}"
    ".ht th{text-align:center!important}"
    ".ht tr:hover td{background:#f9fafb}"
    "</style>"
)


def _admin_table_css() -> str:
    try:
        from config import is_showcase_mode

        if is_showcase_mode():
            from showcase.theme import is_showcase_contrast_theme

            if not is_showcase_contrast_theme():
                return _TABLE_CSS_LIGHT
    except Exception:
        pass
    return _TABLE_CSS_DARK


def _html_table(df, max_rows=300):
    show = df.head(max_rows).copy()
    for col in show.columns:
        show[col] = [str(v) if pd.notna(v) else "" for v in show[col]]
    html = show.to_html(index=False, classes="ht", escape=True, border=0)
    st.markdown(_admin_table_css() + '<div class="ht-wrap">' + html + '</div>', unsafe_allow_html=True)
import sqlite3

from auth import (
    get_user_role_display,
    delete_user,
    ROLES,
)
from config import DB_PATH, switch_page_app
from logger import log_action, get_logs, get_logs_count
from settings import get_setting, set_setting, get_all_settings, SETTING_KEYS
from utils import (
    format_dataframe_as_html,
    load_custom_css,
    outline_level_numeric,
    render_dataframe_excel_csv_downloads,
    render_report_html_table,
)
try:
    from filters import (
        get_default_filters,
        set_default_filter,
        delete_default_filter,
        get_all_default_filters,
        copy_filters_to_role,
        AVAILABLE_REPORTS,
        FILTER_TYPES,
    )
except ImportError as e:
    # Определяем заглушки для избежания ошибок
    AVAILABLE_REPORTS = []
    FILTER_TYPES = {}

    def get_default_filters(*args, **kwargs):
        return {}

    def set_default_filter(*args, **kwargs):
        return False

    def delete_default_filter(*args, **kwargs):
        return False

    def get_all_default_filters(*args, **kwargs):
        return []

    def copy_filters_to_role(*args, **kwargs):
        return False

    # Логируем ошибку, но не используем st, так как он может быть не инициализирован
    import warnings


def _render_control_points_msp_tab(user: dict) -> None:
    """
    Администратор: вкладка «Конфигурация настроек отчетов».
    Вехи, заголовки и соответствие MSP для «Контрольных точек»; задача MSP для «Отклонения от базового плана».
    """
    def _find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
        if df is None or getattr(df, "empty", True):
            return None
        for cand in candidates:
            for col in df.columns:
                if str(col).strip().lower() == cand.lower():
                    return col
        for cand in candidates:
            for col in df.columns:
                if cand.lower() in str(col).strip().lower():
                    return col
        return None

    def _msp_metric_task_options() -> tuple[list[tuple[int, str]], str | None, str | None]:
        df = st.session_state.get("project_data")
        if df is None or getattr(df, "empty", True):
            return [], None, "MSP-данные еще не загружены в текущую сессию."
        task_col = _find_col(df, ["task name", "Task Name", "Название", "Задача"])
        level_col = _find_col(df, ["level structure", "outline level", "level", "Уровень"])
        if not task_col or not level_col:
            return [], task_col, "Не найдены колонки MSP с названием задачи и уровнем."
        levels = outline_level_numeric(df[level_col])
        li = pd.to_numeric(levels, errors="coerce").round()
        mask = li.isin([2, 3])
        sub = df.loc[mask, [task_col, level_col]].copy()
        sub["_msp_lvl"] = li.loc[sub.index].astype(float).round().astype(int)
        if sub.empty:
            return [], task_col, "В текущей выгрузке MSP нет задач уровней 2 и 3."
        sub[task_col] = sub[task_col].astype(str).str.strip()
        sub = sub[sub[task_col].ne("") & sub[task_col].str.lower().ne("nan")]
        sub = sub.drop_duplicates(subset=[task_col, "_msp_lvl"]).sort_values(
            ["_msp_lvl", task_col], kind="stable"
        )
        options = [(int(row["_msp_lvl"]), str(row[task_col])) for _, row in sub.iterrows()]
        if not options:
            return [], task_col, "В MSP не найдено ни одной валидной задачи уровней 2 и 3."
        return options, task_col, None

    st.subheader("Email администратора")
    cur_em = (get_setting("admin_notification_email") or "").strip()
    new_em = st.text_input(
        "Email администратора",
        value=cur_em,
        placeholder="например, admin@company.ru",
        key="admin_notification_email_field",
    )
    if st.button("Сохранить email администратора", type="secondary", key="admin_save_notification_email_btn"):
        set_setting(
            "admin_notification_email",
            str(new_em).strip(),
            description=SETTING_KEYS.get("admin_notification_email", ""),
            updated_by=user.get("username"),
        )
        log_action(
            user.get("username") or "admin",
            "admin_setting",
            "admin_notification_email updated",
        )
        st.success("Сохранено.")
        st.rerun()

    st.divider()

    st.subheader("Контрольные точки: вехи, столбцы, MSP")
    from dashboards._renderers import render_control_points_milestones_admin_settings

    render_control_points_milestones_admin_settings(key_prefix="admin_cp_msp")

    st.subheader("Девелоперские проекты: матрица контрольных точек")
    from dashboards._renderers import render_developer_projects_matrix_admin_settings

    render_developer_projects_matrix_admin_settings(key_prefix="admin_dev_matrix")

    st.divider()
    st.markdown(
        "<h2 class='Duquhununee'>Конфигурация настроек отчетов</h2>",
        unsafe_allow_html=True,
    )

    st.markdown("### Отчёт «Отклонение от базового плана» — задача для KPI")
    _cur_task = (get_setting("baseline_plan_task_for_metrics") or "ЗОС").strip()
    task_options, task_col, task_options_hint = _msp_metric_task_options()
    if task_options:
        selected_option = None
        for opt in task_options:
            if opt[1] == _cur_task:
                selected_option = opt
                break
        if selected_option is None:
            for opt in task_options:
                if opt[1].casefold() == "зос":
                    selected_option = opt
                    break
        if selected_option is None:
            selected_option = task_options[0]
        try:
            _sel_idx = task_options.index(selected_option)
        except ValueError:
            _sel_idx = 0
        _selected_task = st.selectbox(
            "Задача для расчёта окончания проекта (MSP)",
            task_options,
            index=_sel_idx,
            key="admin_baseline_task_for_metrics_select",
            format_func=lambda opt: f"Уровень {opt[0]} - {opt[1]}",
        )
        _tf_task = _selected_task[1]
    else:
        _tf_task = st.text_input(
            "Задача для расчёта окончания проекта (MSP)",
            value=_cur_task,
            key="admin_baseline_task_for_metrics",
        )
        if task_options_hint:
            st.warning(task_options_hint)
    if st.button("Сохранить задачу для метрик", type="primary", key="admin_save_baseline_task"):
        set_setting(
            "baseline_plan_task_for_metrics",
            str(_tf_task).strip() or "ЗОС",
            description=SETTING_KEYS.get("baseline_plan_task_for_metrics", ""),
            updated_by=user.get("username"),
        )
        log_action(
            user.get("username") or "admin",
            "admin_setting",
            "baseline_plan_task_for_metrics",
        )
        st.success("Сохранено.")
        st.rerun()


# ┌──────────────────────────────────────────────────────────────────────────┐ #
# │ ⊗ Красивый формат даты ¤ Start                                           │ #
# └──────────────────────────────────────────────────────────────────────────┘ #

def format_russian_datetime(dt_str):

    """Преобразует ISO-строку в формат '12 фев. 2026, 14:35' с неразрывными пробелами"""

    if not dt_str or dt_str in ("-", None, ""):

        return "-"

    try:
        import pytz
        from datetime import timezone

        dt_str_clean = dt_str.split('.')[0]
        dt = datetime.fromisoformat(dt_str_clean)

        # Если дата без timezone — считаем её UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        # Конвертируем в московское время
        moscow_tz = pytz.timezone("Europe/Moscow")
        dt = dt.astimezone(moscow_tz)

        months_ru = ["янв.", "фев.", "мар.", "апр.", "май", "июн.",
                     "июл.", "авг.", "сен.", "окт.", "ноя.", "дек."]
        month = months_ru[dt.month - 1]
        nbsp = "\u00A0"
        return f"{dt.day}{nbsp}{month}{nbsp}{dt.year},{nbsp}{dt:%H:%M}"

    except Exception:

        return dt_str


# ── Админка: кэш справочников логов + изоляция вкладок (st.fragment) ─────────


@st.cache_data(ttl=45, show_spinner=False)
def _cached_activity_log_filter_lists() -> tuple[list[str], list[str]]:
    """Списки для фильтров вкладки «Логи»: один коннект к SQLite, короткий TTL."""
    conn = sqlite3.connect(DB_PATH)
    try:
        usernames = (
            pd.read_sql_query(
                "SELECT DISTINCT username FROM user_activity_logs ORDER BY username",
                conn,
            )["username"]
            .astype(str)
            .tolist()
        )
        actions = (
            pd.read_sql_query(
                "SELECT DISTINCT action FROM user_activity_logs ORDER BY action",
                conn,
            )["action"]
            .astype(str)
            .tolist()
        )
        return usernames, actions
    finally:
        conn.close()


@st.fragment
def _admin_tab1_users_fragment(user: dict) -> None:
        st.markdown("<h2 class='Duquhununee'>Управление пользователями</h2>", unsafe_allow_html=True)

        # Список пользователей
        st.markdown("<h3 class='Muquhununee'>Список пользователей</h3>", unsafe_allow_html=True)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, username, role, email, created_at, last_login, is_active
            FROM users
            ORDER BY created_at DESC
        """
        )

        users = cursor.fetchall()

        conn.close()

        if users:
            users_data = []
            for u in users:
                created_formatted = format_russian_datetime(u[4]) if u[4] else "-"
                last_login_formatted = format_russian_datetime(u[5]) if u[5] else "Никогда"

                users_data.append(
                    {
                        "ID": u[0],
                        "Имя пользователя": u[1],
                        "Роль": get_user_role_display(u[2]),
                        "Email": u[3] or "-",
                        "Создан": created_formatted,
                        "Последний вход": last_login_formatted,
                        "Активен": "✅" if u[6] else "❌",
                    }
                )

            df_users = pd.DataFrame(users_data)
            html_table = format_dataframe_as_html(df_users)
            st.markdown(html_table, unsafe_allow_html=True)
        else:
            st.info("Пользователи не найдены")

        # st.markdown("---")

        # Добавление нового пользователя
        st.markdown("### Добавить нового пользователя")

        with st.form("add_user_form"):

            # ─── Ловушки для автозаполнения браузера ────────────────────────────────
            st.markdown('<input type="text"     name="fake_username"    style="display:none" autocomplete="username">',     unsafe_allow_html=True)
            st.markdown('<input type="password" name="fake_password"    style="display:none" autocomplete="new-password">', unsafe_allow_html=True)

            col1, col2 = st.columns(2)

            with col1:
                new_username = st.text_input("Имя пользователя *")
                new_email = st.text_input("Email")

            with col2:
                new_password = st.text_input("Пароль *", type="password")
                new_role = st.selectbox(
                    "Роль *", options=list(ROLES.keys()), format_func=lambda x: ROLES[x]
                )

            submitted = st.form_submit_button("Добавить пользователя", type="primary")

            if submitted:
                if new_username and new_password:
                    if new_role == "superadmin":
                        conn = sqlite3.connect(DB_PATH)
                        cursor = conn.cursor()
                        cursor.execute(
                            "SELECT COUNT(*) FROM users WHERE role = 'superadmin' AND is_active = 1"
                        )
                        superadmin_count = cursor.fetchone()[0]
                        conn.close()
                        if superadmin_count >= 1:
                            st.error("В системе уже есть суперадминистратор. Допускается только один.")
                            st.stop()
                    from auth import create_user

                    if create_user(
                        new_username,
                        new_password,
                        new_role,
                        new_email if new_email else None,
                        user["username"],
                    ):
                        st.success(f"Пользователь {new_username} успешно создан!")
                        st.rerun()
                    else:
                        st.error(
                            "Ошибка при создании пользователя. Возможно, пользователь с таким именем уже существует."
                        )
                else:
                    st.warning("Заполните обязательные поля (отмечены *)")

        # st.markdown("---")

        # Изменение роли пользователя
        st.markdown("### Изменить роль пользователя")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, role FROM users WHERE is_active = 1 ORDER BY username"
        )
        active_users = cursor.fetchall()
        conn.close()

        if active_users:
            with st.form("change_role_form"):
                user_options = {
                    f"{u[1]} ({get_user_role_display(u[2])})": u[0]
                    for u in active_users
                }
                selected_user_display = st.selectbox(
                    "Выберите пользователя", options=list(user_options.keys())
                )
                selected_user_id = user_options[selected_user_display]

                # Получаем текущую роль
                selected_username = selected_user_display.split(" (")[0]
                current_role = None
                for u in active_users:
                    if u[0] == selected_user_id:
                        current_role = u[2]
                        break

                new_role = st.selectbox(
                    "Новая роль *",
                    options=list(ROLES.keys()),
                    format_func=lambda x: ROLES[x],
                    index=list(ROLES.keys()).index(current_role) if current_role else 0,
                )

                submitted = st.form_submit_button("Изменить роль", type="primary")

                if submitted:
                    if new_role != current_role:
                        conn = sqlite3.connect(DB_PATH)
                        cursor = conn.cursor()
                        cursor.execute(
                            "SELECT COUNT(*) FROM users WHERE role = 'superadmin' AND is_active = 1"
                        )
                        superadmin_count = cursor.fetchone()[0]
                        conn.close()
                        if new_role == "superadmin" and current_role != "superadmin" and superadmin_count >= 1:
                            st.error("В системе уже есть суперадминистратор. Допускается только один.")
                            st.stop()
                        if current_role == "superadmin" and new_role != "superadmin" and superadmin_count <= 1:
                            st.error("Нельзя снять роль у единственного суперадминистратора.")
                            st.stop()
                        conn = sqlite3.connect(DB_PATH)
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE users SET role = ? WHERE id = ?",
                            (new_role, selected_user_id),
                        )
                        conn.commit()
                        conn.close()

                        log_action(
                            user["username"],
                            "change_role",
                            f"Изменена роль пользователя {selected_username} с {get_user_role_display(current_role)} на {get_user_role_display(new_role)}",
                        )
                        if selected_username == user["username"]:
                            session_user = st.session_state.get("user") or {}
                            session_user["role"] = new_role
                            st.session_state["user"] = session_user
                            user["role"] = new_role
                        st.success(
                            # f"✅ Роль пользователя {selected_username} успешно изменена на {get_user_role_display(new_role)}!"
                            f"Роль пользователя {selected_username} успешно изменена на {get_user_role_display(new_role)}!"
                        )
                        st.rerun()
                    else:
                        st.warning("Выберите другую роль")
        else:

            st.info("Нет активных пользователей")

        # Удаление пользователя (только для суперадминистратора)
        if user["role"] == "superadmin":
            st.markdown("### Удалить пользователя")

            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, username, role FROM users WHERE username != ? AND role != 'superadmin' ORDER BY username",
                (user["username"],),
            )
            deletable_users = cursor.fetchall()
            conn.close()

            if deletable_users:
                del_options = {
                    f"{u[1]} ({get_user_role_display(u[2])})": u[0]
                    for u in deletable_users
                }
                del_selected = st.selectbox(
                    "Выберите пользователя для удаления",
                    options=list(del_options.keys()),
                    key="del_user_select",
                )
                del_user_id = del_options[del_selected]
                del_username = del_selected.split(" (")[0]

                confirm = st.checkbox(
                    f"Подтверждаю удаление пользователя «{del_username}» и всех его данных",
                    key="del_user_confirm",
                )

                if st.button(
                    "Удалить пользователя",
                    type="primary",
                    disabled=not confirm,
                    key="del_user_btn",
                ):
                    ok, msg = delete_user(del_user_id, user["username"])
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
            else:
                st.info("Нет пользователей, доступных для удаления")

    # ┌──────────────────────────────────────────────────────────────────────┐ #
    # │ ⊗ TAB 1: Управление пользователями ¤ End                             │ #
    # └──────────────────────────────────────────────────────────────────────┘ #

    # ┌──────────────────────────────────────────────────────────────────────┐ #
    # │ ⊗ TAB 2: Статистика ¤ Start                                          │ #
    # └──────────────────────────────────────────────────────────────────────┘ #



@st.fragment
def _admin_tab2_stats_fragment() -> None:
        st.markdown("<h2 class='Duquhununee'>Статистика системы</h2>", unsafe_allow_html=True)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Общая статистика
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
        active_users = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM users WHERE last_login IS NOT NULL")
        users_with_login = cursor.fetchone()[0]

        # Статистика по ролям
        cursor.execute(
            """
            SELECT role, COUNT(*) as count
            FROM users
            GROUP BY role
        """
        )
        role_stats = cursor.fetchall()

        # Статистика логов
        total_logs = get_logs_count()
        recent_logs = get_logs_count(action="login")

        conn.close()

        col1, col2, col3, col4 = st.columns(4)

        with col1:

            st.metric("Всего пользователей", total_users)

        with col2:

            st.metric("Активных пользователей", active_users)

        with col3:

            st.metric("Пользователей с входом", users_with_login)

        with col4:

            st.metric("Всего действий в логах", total_logs)

        st.markdown("---")

        # Статистика по ролям
        st.markdown("### Распределение по ролям")
        if role_stats:
            role_data = [
                {"Роль": get_user_role_display(r[0]), "Количество": r[1]}
                for r in role_stats
            ]
            df_roles = pd.DataFrame(role_data)
            html_table = format_dataframe_as_html(df_roles)
            st.markdown(html_table, unsafe_allow_html=True)
        else:
            st.info("Нет данных")

    # ┌──────────────────────────────────────────────────────────────────────┐ #
    # │ ⊗ TAB 2: Статистика ¤ End                                            │ #
    # └──────────────────────────────────────────────────────────────────────┘ #

    # ┌──────────────────────────────────────────────────────────────────────┐ #
    # │ ⊗ TAB 3: Логи действий ¤ Start                                       │ #
    # └──────────────────────────────────────────────────────────────────────┘ #



@st.fragment
def _admin_tab3_logs_fragment() -> None:
        st.markdown("<h2 class='Duquhununee'>Логи действий пользователей</h2>", unsafe_allow_html=True)

        # Фильтры
        _u, _a = _cached_activity_log_filter_lists()
        col1, col2, col3 = st.columns(3)
        col4, col5 = st.columns(2)

        with col1:
            filter_username = st.selectbox(
                "Фильтр по пользователю",
                ["Все"] + list(_u),
            )

        with col2:
            filter_action = st.selectbox("Фильтр по действию", ["Все"] + list(_a))

        with col3:

            log_limit = st.number_input("Количество записей", 10, 1000, 100, 10)

        with col4:
            date_from = st.date_input("С даты (UTC)", value=None, key="log_date_from")
        with col5:
            date_to = st.date_input("По дату (UTC)", value=None, key="log_date_to")

        username_filter = None if filter_username == "Все" else filter_username
        action_filter = None if filter_action == "Все" else filter_action
        created_after_iso = None
        created_before_iso = None
        if date_from:
            created_after_iso = datetime.combine(date_from, time.min, tzinfo=timezone.utc).isoformat()
        if date_to:
            created_before_iso = datetime.combine(date_to, time.max, tzinfo=timezone.utc).isoformat()

        # Получаем логи
        logs = get_logs(
            limit=log_limit,
            username=username_filter,
            action=action_filter,
            created_after=created_after_iso,
            created_before=created_before_iso,
        )

        if logs:

            logs_data = []

            for log in logs:

                created_at = log.get("created_at", None)

                formatted_time = format_russian_datetime(log.get("created_at")) if log.get("created_at") else "-"

                ip = log.get("ip_address") or "-"

                logs_data.append({
                    "ID": log.get("id", "-"),
                    "Пользователь": log.get("username", "-"),
                    "Действие": log.get("action", "-"),
                    "Детали": log.get("details") or "-",
                    "IP\u00A0адрес": ip,
                    "Дата\u00A0и\u00A0время": formatted_time,
                })

            df_logs = pd.DataFrame(logs_data)

            # Если хочешь красивую дату ещё и в сортировке — можно добавить скрытую колонку
            # df_logs["sort_time"] = pd.to_datetime(df_logs["Время"], format=..., errors="coerce")
            # но обычно достаточно просто сортировки по строке

            _logs_stem = f"logs_{datetime.now():%Y%m%d_%H%M%S}"
            render_report_html_table(
                format_dataframe_as_html(df_logs),
                export_df=df_logs,
                file_stem=_logs_stem,
                key_prefix="admin_action_logs",
            )

        else:
            st.info("Логи не найдены")

    # ┌──────────────────────────────────────────────────────────────────────┐ #
    # │ ⊗ TAB 3: Логи действий ¤ End                                         │ #
    # └──────────────────────────────────────────────────────────────────────┘ #

    # ┌──────────────────────────────────────────────────────────────────────┐ #
    # │ ⊗ TAB 4: Права доступа к проектам ¤ Start                            │ #
    # └──────────────────────────────────────────────────────────────────────┘ #



@st.fragment
def _admin_tab4_access_fragment() -> None:
        st.markdown("<h2 class='Duquhununee'>Права доступа</h2>", unsafe_allow_html=True)
        st.info(
            "Разрезка прав по отдельным проектам отключена. "
            "Доступ определяется только ролью пользователя."
        )
        roles_df = pd.DataFrame(
            [
                {"Код роли": code, "Роль": title}
                for code, title in ROLES.items()
            ]
        )
        _html_table(roles_df)

    # ┌──────────────────────────────────────────────────────────────────────┐ #
    # │ ⊗ TAB 4: Права доступа к проектам ¤ End                              │ #
    # └──────────────────────────────────────────────────────────────────────┘ #

@st.fragment
def _admin_tab6_msp_fragment(user: dict) -> None:
        _render_control_points_msp_tab(user)



def render_admin_panel_tabs(user: dict) -> None:
    """Скрипт автоскролла вкладок + вкладки админки."""

    # JavaScript для автоматического скролла к содержимому выбранной вкладки
    st.markdown(
        """
        <script>
        (function() {
            function scrollToActiveTabContent() {
                setTimeout(function() {
                    // Находим активную панель вкладки (содержимое, не заголовок)
                    const activePanel = document.querySelector('[role="tabpanel"][aria-hidden="false"]');
                    if (!activePanel) return;

                    // Находим первый значимый элемент контента внутри панели
                    // Пропускаем заголовки вкладок и ищем реальное содержимое
                    const contentElements = activePanel.querySelectorAll('div[data-testid="stVerticalBlock"] > div, h1, h2, h3, .stSubheader');
                    let targetElement = null;

                    // Ищем первый элемент, который не является частью заголовка вкладки
                    for (let i = 0; i < contentElements.length; i++) {
                        const elem = contentElements[i];
                        // Проверяем, что элемент не находится в заголовке вкладки
                        if (!elem.closest('[data-baseweb="tab-list"]') &&
                            !elem.closest('[data-baseweb="tab"]')) {
                            targetElement = elem;
                            break;
                        }
                    }

                    // Если не нашли, используем саму панель, но с отступом
                    if (!targetElement) {
                        targetElement = activePanel;
                    }

                    // Вычисляем позицию с учетом отступа от верха
                    const elementPosition = targetElement.getBoundingClientRect().top;
                    const offsetPosition = elementPosition + window.pageYOffset - 100; // 100px отступ от верха

                    // Плавный скролл
                    window.scrollTo({
                        top: offsetPosition,
                        behavior: 'smooth'
                    });
                }, 200);
            }

            // Выполняем скролл при загрузке
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', scrollToActiveTabContent);
            } else {
                scrollToActiveTabContent();
            }

            // Отслеживаем клики по вкладкам
            document.addEventListener('click', function(e) {
                if (e.target.closest('[data-baseweb="tab"]')) {
                    scrollToActiveTabContent();
                }
            });

            // Отслеживаем изменения активной вкладки через MutationObserver
            const observer = new MutationObserver(function(mutations) {
                mutations.forEach(function(mutation) {
                    if (mutation.type === 'attributes') {
                        // Проверяем изменения aria-selected или aria-hidden
                        if ((mutation.attributeName === 'aria-selected' &&
                             mutation.target.getAttribute('aria-selected') === 'true') ||
                            (mutation.attributeName === 'aria-hidden' &&
                             mutation.target.getAttribute('aria-hidden') === 'false' &&
                             mutation.target.getAttribute('role') === 'tabpanel')) {
                            scrollToActiveTabContent();
                        }
                    }
                });
            });

            // Наблюдаем за вкладками и панелями
            setTimeout(function() {
                const tabs = document.querySelectorAll('[data-baseweb="tab"]');
                const panels = document.querySelectorAll('[role="tabpanel"]');

                tabs.forEach(tab => {
                    observer.observe(tab, {
                        attributes: true,
                        attributeFilter: ['aria-selected']
                    });
                });

                panels.forEach(panel => {
                    observer.observe(panel, {
                        attributes: true,
                        attributeFilter: ['aria-hidden']
                    });
                });
            }, 500);
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )
    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        [
            "Пользователи",
            "Статистика",
            "Логи",
            "Права доступа",
            "Конфигурация настроек отчетов",
        ]
    )

    # ┌──────────────────────────────────────────────────────────────────────┐ #
    # │ ⊗ TAB 1: Управление пользователями ¤ Start                           │ #
    # └──────────────────────────────────────────────────────────────────────┘ #

    with tab1:
        _admin_tab1_users_fragment(user)
    with tab2:
        _admin_tab2_stats_fragment()
    with tab3:
        _admin_tab3_logs_fragment()
    with tab4:
        _admin_tab4_access_fragment()
    with tab5:
        _admin_tab6_msp_fragment(user)
