from __future__ import annotations

import sqlite3
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import USERS_DB_PATH
from app.services.auth_context import require_admin_user
from app.services.default_filters_web import (
    catalog_report_titles,
    format_filter_value_display,
    is_garbled_report_name,
    report_display_name,
    report_name_matches,
)
from app.services.users_bridge import (
    format_russian_datetime,
    import_auth,
    import_filters,
    import_logger,
    import_settings_module,
    user_payload,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _require_admin(authorization: str | None) -> dict:
    return require_admin_user(authorization)


class CreateUserBody(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)
    role: str
    email: str | None = None


class ChangeRoleBody(BaseModel):
    user_id: int
    new_role: str


class DeleteUserBody(BaseModel):
    user_id: int


class FilterBody(BaseModel):
    role: str
    report_name: str
    filter_key: str
    filter_value: str | None = None
    filter_type: str = "string"


class DeleteFilterBody(BaseModel):
    role: str
    report_name: str
    filter_key: str


class CopyFiltersBody(BaseModel):
    source_role: str
    target_role: str
    report_name: str | None = None


class ReportConfigBody(BaseModel):
    admin_notification_email: str | None = None
    baseline_plan_task_for_metrics: str | None = None
    control_points_milestones_json: str | None = None
    developer_projects_matrix_json: str | None = None


class CreateRoleBody(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=200)
    reports: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    can_admin: bool = False


class UpdateRoleBody(BaseModel):
    label: str | None = None
    reports: list[str] | None = None
    projects: list[str] | None = None
    can_admin: bool | None = None


class UserProjectsBody(BaseModel):
    projects: list[str] = Field(default_factory=list)


@router.get("/report-catalog")
def report_catalog(authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    auth = import_auth()
    items = []
    for row in auth.get_nav_catalog():
        items.append(
            {
                "id": row.get("id"),
                "title": row.get("title") or row.get("id"),
                "path": row.get("path") or "",
            }
        )
    if not items:
        try:
            from app.services.ask_ai_reports import SCREENS

            for nav_id, meta in SCREENS.items():
                items.append(
                    {
                        "id": nav_id,
                        "title": str(meta.get("title") or nav_id),
                        "path": str(meta.get("src") or ""),
                    }
                )
        except Exception:
            pass
    return {"items": items}


@router.get("/roles")
def list_roles(authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    auth = import_auth()
    return {"items": auth.list_roles()}


@router.post("/roles")
def create_role(
    body: CreateRoleBody,
    authorization: str | None = Header(default=None),
):
    _require_admin(authorization)
    auth = import_auth()
    ok = auth.create_role(
        body.code.strip(),
        body.label.strip(),
        body.reports,
        can_admin=body.can_admin,
        projects=body.projects,
    )
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="Не удалось создать роль (код занят или некорректен).",
        )
    return {"ok": True, "item": next(r for r in auth.list_roles() if r["code"] == body.code.strip().lower())}


@router.patch("/roles/{code}")
def update_role(
    code: str,
    body: UpdateRoleBody,
    authorization: str | None = Header(default=None),
):
    _require_admin(authorization)
    auth = import_auth()
    ok, err = auth.update_role(
        code,
        label=body.label,
        reports=body.reports,
        projects=body.projects,
        can_admin=body.can_admin,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=err or "Ошибка обновления роли")
    item = next((r for r in auth.list_roles() if r["code"] == code.strip().lower()), None)
    return {"ok": True, "item": item}


@router.delete("/roles/{code}")
def delete_role(code: str, authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    auth = import_auth()
    ok, err = auth.delete_role(code)
    if not ok:
        raise HTTPException(status_code=400, detail=err or "Ошибка удаления роли")
    return {"ok": True}


@router.get("/users/{user_id}/projects")
def get_user_projects(user_id: int, authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    auth = import_auth()
    projects = auth.get_user_projects(user_id)
    return {
        "user_id": user_id,
        "projects": projects or [],
        "unrestricted": projects is None,
    }


@router.put("/users/{user_id}/projects")
def put_user_projects(
    user_id: int,
    body: UserProjectsBody,
    authorization: str | None = Header(default=None),
):
    actor = _require_admin(authorization)
    auth = import_auth()
    ok, err = auth.set_user_projects(user_id, body.projects, actor.get("username"))
    if not ok:
        raise HTTPException(status_code=400, detail=err or "Ошибка сохранения проектов")
    projects = auth.get_user_projects(user_id)
    return {
        "ok": True,
        "user_id": user_id,
        "projects": projects or [],
        "unrestricted": projects is None,
    }


@router.get("/users")
def list_users(authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    auth = import_auth()
    conn = sqlite3.connect(str(USERS_DB_PATH))
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, username, role, email, created_at, last_login, is_active
        FROM users
        ORDER BY created_at DESC
        """
    )
    rows = cur.fetchall()
    conn.close()
    items = []
    for row in rows:
        items.append(
            {
                "id": row[0],
                "username": row[1],
                "role": row[2],
                "role_label": auth.get_user_role_display(row[2]),
                "email": row[3],
                "created_at": row[4],
                "created_at_fmt": format_russian_datetime(row[4]),
                "last_login": row[5],
                "last_login_fmt": format_russian_datetime(row[5])
                if row[5]
                else "Никогда",
                "is_active": bool(row[6]),
            }
        )
    return {"items": items}


@router.post("/users")
def create_user(
    body: CreateUserBody,
    authorization: str | None = Header(default=None),
):
    actor = _require_admin(authorization)
    auth = import_auth()
    if body.role == "superadmin":
        conn = sqlite3.connect(str(USERS_DB_PATH))
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'superadmin' AND is_active = 1"
        )
        if int(cur.fetchone()[0]) >= 1:
            conn.close()
            raise HTTPException(
                status_code=400,
                detail="В системе уже есть суперадминистратор. Допускается только один.",
            )
        conn.close()
    if not auth.role_exists(body.role):
        raise HTTPException(status_code=400, detail="Неизвестная роль")
    ok = auth.create_user(
        body.username.strip(),
        body.password,
        body.role,
        body.email.strip() if body.email else None,
        actor["username"],
    )
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="Ошибка при создании пользователя. Возможно, имя уже занято.",
        )
    return {"ok": True}


@router.post("/users/change-role")
def change_user_role(
    body: ChangeRoleBody,
    authorization: str | None = Header(default=None),
):
    actor = _require_admin(authorization)
    auth = import_auth()
    if not auth.role_exists(body.new_role):
        raise HTTPException(status_code=400, detail="Неизвестная роль")
    conn = sqlite3.connect(str(USERS_DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT username, role FROM users WHERE id = ?", (body.user_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    target_username, current_role = row[0], row[1]
    if body.new_role == current_role:
        conn.close()
        raise HTTPException(status_code=400, detail="Выберите другую роль")
    cur.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'superadmin' AND is_active = 1"
    )
    superadmin_count = int(cur.fetchone()[0])
    if (
        body.new_role == "superadmin"
        and current_role != "superadmin"
        and superadmin_count >= 1
    ):
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="В системе уже есть суперадминистратор. Допускается только один.",
        )
    if (
        current_role == "superadmin"
        and body.new_role != "superadmin"
        and superadmin_count <= 1
    ):
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="Нельзя снять роль у единственного суперадминистратора.",
        )
    cur.execute(
        "UPDATE users SET role = ? WHERE id = ?",
        (body.new_role, body.user_id),
    )
    conn.commit()
    conn.close()
    logger = import_logger()
    logger.log_action(
        actor["username"],
        "change_role",
        f"Изменена роль пользователя {target_username} с {auth.get_user_role_display(current_role)} на {auth.get_user_role_display(body.new_role)}",
    )
    return {"ok": True}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    authorization: str | None = Header(default=None),
):
    actor = _require_admin(authorization)
    if actor["role"] != "superadmin":
        raise HTTPException(
            status_code=403,
            detail="Удалять пользователей может только суперадминистратор",
        )
    auth = import_auth()
    ok, message = auth.delete_user(user_id, actor["username"])
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"ok": True, "message": message}


@router.get("/stats")
def system_stats(authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    auth = import_auth()
    logger = import_logger()
    conn = sqlite3.connect(str(USERS_DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = int(cur.fetchone()[0])
    cur.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
    active_users = int(cur.fetchone()[0])
    cur.execute("SELECT COUNT(*) FROM users WHERE last_login IS NOT NULL")
    users_with_login = int(cur.fetchone()[0])
    cur.execute(
        """
        SELECT role, COUNT(*) as count
        FROM users
        GROUP BY role
        """
    )
    role_stats = cur.fetchall()
    conn.close()
    total_logs = logger.get_logs_count()
    return {
        "total_users": total_users,
        "active_users": active_users,
        "users_with_login": users_with_login,
        "total_logs": total_logs,
        "roles": [
            {
                "role": r[0],
                "role_label": auth.get_user_role_display(r[0]),
                "count": int(r[1]),
            }
            for r in role_stats
        ],
    }


@router.get("/logs")
def activity_logs(
    authorization: str | None = Header(default=None),
    username: str | None = None,
    action: str | None = None,
    limit: int = Query(default=100, ge=10, le=1000),
    date_from: date | None = None,
    date_to: date | None = None,
):
    _require_admin(authorization)
    logger = import_logger()
    created_after = None
    created_before = None
    if date_from:
        created_after = datetime.combine(
            date_from, time.min, tzinfo=timezone.utc
        ).isoformat()
    if date_to:
        created_before = datetime.combine(
            date_to, time.max, tzinfo=timezone.utc
        ).isoformat()
    logs = logger.get_logs(
        limit=limit,
        username=username if username and username != "Все" else None,
        action=action if action and action != "Все" else None,
        created_after=created_after,
        created_before=created_before,
    )
    conn = sqlite3.connect(str(USERS_DB_PATH))
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT username FROM user_activity_logs ORDER BY username"
    )
    usernames = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT DISTINCT action FROM user_activity_logs ORDER BY action")
    actions = [r[0] for r in cur.fetchall()]
    conn.close()
    items = []
    for log in logs:
        items.append(
            {
                "id": log.get("id"),
                "username": log.get("username"),
                "action": log.get("action"),
                "action_key": log.get("action_key"),
                "details": log.get("details") or "-",
                "ip_address": log.get("ip_address") or "-",
                "created_at": log.get("created_at"),
                "created_at_fmt": format_russian_datetime(log.get("created_at")),
            }
        )
    return {
        "items": items,
        "filters": {"usernames": usernames, "actions": actions},
        "action_labels": logger.ACTION_LABELS,
    }


def _volume_default_filter_rows(
    role: str | None = None,
) -> list[dict]:
    """Читает default_filters из volume users.db, не из /core/users.db."""
    path = USERS_DB_PATH
    if not path.is_file():
        return []
    sql = """
        SELECT role, report_name, filter_key, filter_value, filter_type, updated_at, updated_by
        FROM default_filters
    """
    params: tuple = ()
    if role:
        sql += " WHERE role = ?"
        params = (role,)
    sql += " ORDER BY role, report_name, filter_key"
    try:
        conn = sqlite3.connect(str(path))
        conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return list(rows or [])
    except sqlite3.Error:
        return []


@router.get("/filters")
def list_filters(
    authorization: str | None = Header(default=None),
    role: str | None = None,
    report_name: str | None = None,
):
    _require_admin(authorization)
    auth = import_auth()
    filters_mod = import_filters()
    role_code = None if not role or role == "Все" else role
    rows = _volume_default_filter_rows(role_code)
    if not rows:
        rows = filters_mod.get_all_default_filters(
            role=role_code,
            report_name=None,
        )
    selected_report = None if not report_name or report_name == "Все" else report_name
    if selected_report:
        rows = [
            f for f in rows if report_name_matches(f.get("report_name"), selected_report)
        ]
    extra_titles: list[str] = []
    seen_extra: set[str] = set()
    for f in rows:
        raw = (f.get("report_name") or "").strip()
        decoded = report_display_name(raw)
        for cand in (raw, decoded):
            if (
                cand
                and not is_garbled_report_name(cand)
                and cand not in seen_extra
            ):
                seen_extra.add(cand)
                extra_titles.append(cand)
    items = []
    for f in rows:
        stored_name = f["report_name"]
        stored_type = (f.get("filter_type") or "string").lower()
        type_label = filters_mod.FILTER_TYPES.get(stored_type, stored_type)
        if stored_type == "json":
            type_label = "Список"
        items.append(
            {
                "role": f["role"],
                "role_label": auth.get_user_role_display(f["role"]),
                "report_name": stored_name,
                "report_label": report_display_name(
                    stored_name, extra_titles=extra_titles
                ),
                "filter_key": f["filter_key"],
                "filter_value": format_filter_value_display(f["filter_value"]),
                "filter_type": f["filter_type"],
                "filter_type_label": type_label,
                "updated_at": f.get("updated_at"),
                "updated_by": f.get("updated_by"),
            }
        )
    reports: list[str] = []
    seen: set[str] = set()
    for name in list(catalog_report_titles()) + list(
        getattr(filters_mod, "AVAILABLE_REPORTS", None) or []
    ):
        label = report_display_name(name)
        if not label or is_garbled_report_name(label) or label in seen:
            continue
        seen.add(label)
        reports.append(label)
    for item in items:
        label = item.get("report_label") or report_display_name(item.get("report_name"))
        if not label or is_garbled_report_name(label) or label in seen:
            continue
        seen.add(label)
        reports.append(label)
    return {
        "items": items,
        "reports": reports,
        "filter_types": filters_mod.FILTER_TYPES,
        "roles": {r["code"]: r["label"] for r in auth.list_roles()},
    }


@router.post("/filters")
def save_filter(
    body: FilterBody,
    authorization: str | None = Header(default=None),
):
    actor = _require_admin(authorization)
    filters_mod = import_filters()
    auth = import_auth()
    if not body.filter_key or not auth.role_exists(body.role):
        raise HTTPException(status_code=400, detail="Заполните обязательные поля")
    ok = filters_mod.set_default_filter(
        body.role,
        body.report_name,
        body.filter_key,
        body.filter_value or "",
        body.filter_type,
        actor["username"],
    )
    if not ok:
        raise HTTPException(status_code=400, detail="Ошибка при сохранении фильтра")
    logger = import_logger()
    logger.log_action(
        actor["username"],
        "set_default_filter",
        f"Установлен фильтр {body.filter_key} для роли {auth.get_user_role_display(body.role)} в отчете {body.report_name}",
    )
    return {"ok": True}


@router.delete("/filters")
def remove_filter(
    body: DeleteFilterBody,
    authorization: str | None = Header(default=None),
):
    actor = _require_admin(authorization)
    filters_mod = import_filters()
    auth = import_auth()
    stored_names = {
        str(f.get("report_name") or "")
        for f in filters_mod.get_all_default_filters(role=body.role)
        if f.get("filter_key") == body.filter_key
        and report_name_matches(f.get("report_name"), body.report_name)
    }
    if body.report_name:
        stored_names.add(body.report_name)
    ok = False
    for stored in stored_names:
        if not stored:
            continue
        if filters_mod.delete_default_filter(body.role, stored, body.filter_key):
            ok = True
    if not ok:
        raise HTTPException(status_code=400, detail="Ошибка при удалении фильтра")
    logger = import_logger()
    logger.log_action(
        actor["username"],
        "delete_default_filter",
        f"Удален фильтр {body.filter_key} для роли {auth.get_user_role_display(body.role)} в отчете {body.report_name}",
    )
    return {"ok": True}


@router.post("/filters/copy")
def copy_filters(
    body: CopyFiltersBody,
    authorization: str | None = Header(default=None),
):
    actor = _require_admin(authorization)
    if body.source_role == body.target_role:
        raise HTTPException(
            status_code=400,
            detail="Исходная и целевая роли не могут быть одинаковыми",
        )
    filters_mod = import_filters()
    auth = import_auth()
    ok = filters_mod.copy_filters_to_role(
        body.source_role,
        body.target_role,
        body.report_name,
    )
    if not ok:
        raise HTTPException(status_code=400, detail="Ошибка при копировании фильтров")
    logger = import_logger()
    logger.log_action(
        actor["username"],
        "copy_filters",
        f"Скопированы фильтры из роли {auth.get_user_role_display(body.source_role)} в роль {auth.get_user_role_display(body.target_role)}"
        + (f" для отчета {body.report_name}" if body.report_name else " для всех отчетов"),
    )
    return {"ok": True}


def _report_json_defaults() -> dict[str, str]:
    fallback = {
        "control_points_milestones_json": "[]",
        "developer_projects_matrix_json": (
            '{\n  "subcolumns": {\n    "plan": "План",\n    "fact": "Факт",'
            '\n    "otkl": "Откл."\n  },\n  "default_vertical_dates": false,'
            '\n  "titles": {},\n  "matches": {}\n}'
        ),
    }
    try:
        from app.services.core_bridge import import_dashboard_module, prepare_core_env

        prepare_core_env()
        mtx = import_dashboard_module("dev_projects_tz_matrix")
        return {
            "control_points_milestones_json": mtx.control_point_milestones_default_json(),
            "developer_projects_matrix_json": mtx.developer_projects_matrix_default_prefs_json(),
        }
    except Exception:
        return fallback


@router.get("/report-config")
def get_report_config(
    authorization: str | None = Header(default=None),
):
    _require_admin(authorization)
    settings_mod = import_settings_module()
    keys = [
        "admin_notification_email",
        "baseline_plan_task_for_metrics",
        "control_points_milestones_json",
        "developer_projects_matrix_json",
    ]
    values = {k: settings_mod.get_setting(k) or "" for k in keys}
    return {
        "values": values,
        "descriptions": {
            k: settings_mod.SETTING_KEYS.get(k, k) for k in keys
        },
        "defaults": _report_json_defaults(),
    }


@router.put("/report-config")
def put_report_config(
    body: ReportConfigBody,
    authorization: str | None = Header(default=None),
):
    actor = _require_admin(authorization)
    settings_mod = import_settings_module()
    logger = import_logger()
    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if value is None:
            continue
        settings_mod.set_setting(
            key,
            str(value).strip(),
            description=settings_mod.SETTING_KEYS.get(key, ""),
            updated_by=actor["username"],
        )
        logger.log_action(actor["username"], "admin_setting", key)
    return {"ok": True}
