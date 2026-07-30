from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import API_TITLE, API_VERSION, CORS_ORIGINS, DATA_MODE, WEB_DATA_DIR
from app.routers import (
    admin,
    approved_budget,
    baseline_deviation,
    bdds,
    bdds_plan_fact,
    bdr,
    control_points,
    debit_credit,
    developer_projects,
    deviation_reasons,
    executive_docs,
    gdrs_equipment,
    gdrs_people,
    prescriptions,
    project_documentation,
    project_schedule,
    working_documentation,
)
from app.services.ftp_ingest import sync_status

app = FastAPI(title=API_TITLE, version=API_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(debit_credit.router)
app.include_router(developer_projects.router)
app.include_router(bdds.router)
app.include_router(bdr.router)
app.include_router(approved_budget.router)
app.include_router(bdds_plan_fact.router)
app.include_router(control_points.router)
app.include_router(project_schedule.router)
app.include_router(deviation_reasons.router)
app.include_router(baseline_deviation.router)
app.include_router(project_documentation.router)
app.include_router(working_documentation.router)
app.include_router(gdrs_people.router)
app.include_router(gdrs_equipment.router)
app.include_router(prescriptions.router)
app.include_router(executive_docs.router)
app.include_router(admin.router)


@app.get("/api/health")
def health():
    st = sync_status()
    db = st.get("db") or {}
    return {
        "ok": True,
        "version": API_VERSION,
        "data_mode": DATA_MODE,
        "web_data_dir": str(WEB_DATA_DIR),
        "web_data_exists": WEB_DATA_DIR.is_dir(),
        "files": st.get("files"),
        "ftp_configured": st.get("ftp_configured"),
        "web_db_path": db.get("web_db_path"),
        "web_db_exists": db.get("exists"),
        "active_version_id": db.get("active_version_id"),
    }


@app.get("/api/dashboards")
def list_dashboards():
    return {
        "items": [
            {
                "id": "debit-credit",
                "title": "Дебиторская и кредиторская задолженность подрядчиков",
                "section": "Дебиторская и кредиторская задолженность",
                "status": "ready",
                "path": "/debit-credit",
                "api": "/api/debit-credit",
            },
            {
                "id": "developer-projects",
                "title": "Девелоперские проекты",
                "section": "Девелоперские проекты",
                "status": "ready",
                "path": "/developer-projects",
                "api": "/api/developer-projects",
            },
            {
                "id": "bdds",
                "title": "БДДС (расходы)",
                "section": "Финансы",
                "status": "ready",
                "path": "/finance/bdds",
                "api": "/api/bdds",
            },
            {
                "id": "bdr",
                "title": "БДР (расходы)",
                "section": "Финансы",
                "status": "ready",
                "path": "/finance/bdr",
                "api": "/api/bdr",
            },
            {
                "id": "approved-budget",
                "title": "Утверждённый бюджет план/факт",
                "section": "Финансы",
                "status": "ready",
                "path": "/finance/approved-budget",
                "api": "/api/approved-budget",
            },
            {
                "id": "bdds-plan-fact",
                "title": "БДДС расходы (план, факт, уточненный план)",
                "section": "Финансы",
                "status": "ready",
                "path": "/finance/bdds-plan-fact",
                "api": "/api/bdds-plan-fact",
            },
            {
                "id": "control-points",
                "title": "Контрольные точки",
                "section": "Сроки",
                "status": "ready",
                "path": "/timeline/control-points",
                "api": "/api/control-points",
            },
            {
                "id": "project-schedule",
                "title": "График проекта",
                "section": "Сроки",
                "status": "ready",
                "path": "/timeline/project-schedule",
                "api": "/api/project-schedule",
            },
            {
                "id": "deviation-reasons",
                "title": "Причины отклонений",
                "section": "Сроки",
                "status": "ready",
                "path": "/timeline/deviation-reasons",
                "api": "/api/deviation-reasons",
            },
            {
                "id": "baseline-deviation",
                "title": "Отклонение от базового плана",
                "section": "Сроки",
                "status": "ready",
                "path": "/timeline/baseline-deviation",
                "api": "/api/baseline-deviation",
            },
            {
                "id": "project-documentation",
                "title": "Проектная документация",
                "section": "Проектные работы",
                "status": "ready",
                "path": "/docs/project-documentation",
                "api": "/api/project-documentation",
            },
            {
                "id": "working-documentation",
                "title": "Рабочая документация",
                "section": "Проектные работы",
                "status": "ready",
                "path": "/docs/working-documentation",
                "api": "/api/working-documentation",
            },
            {
                "id": "gdrs-people",
                "title": "ГДРС (люди)",
                "section": "ГДРС",
                "status": "ready",
                "path": "/gdrs/people",
                "api": "/api/gdrs-people",
            },
            {
                "id": "gdrs-equipment",
                "title": "ГДРС (техника)",
                "section": "ГДРС",
                "status": "ready",
                "path": "/gdrs/equipment",
                "api": "/api/gdrs-equipment",
            },
            {
                "id": "prescriptions",
                "title": "Предписания по подрядчикам",
                "section": "Предписания",
                "status": "ready",
                "path": "/prescriptions",
                "api": "/api/prescriptions",
            },
            {
                "id": "executive-docs",
                "title": "Исполнительная документация",
                "section": "Исполнительная документация",
                "status": "ready",
                "path": "/executive-docs",
                "api": "/api/executive-docs",
            },
            {
                "id": "menu",
                "title": "Меню как на ai.conall.ru",
                "status": "nav",
                "note": "Остальные экраны — заглушки, контент по одному",
            },
        ]
    }
