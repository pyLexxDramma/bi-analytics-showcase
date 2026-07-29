from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import API_TITLE, API_VERSION, CORS_ORIGINS, DATA_MODE, WEB_DATA_DIR
from app.routers import admin, approved_budget, bdds, bdr, debit_credit, developer_projects
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
app.include_router(admin.router)


@app.get("/api/health")
def health():
    st = sync_status()
    return {
        "ok": True,
        "version": API_VERSION,
        "data_mode": DATA_MODE,
        "web_data_dir": str(WEB_DATA_DIR),
        "web_data_exists": WEB_DATA_DIR.is_dir(),
        "files": st.get("files"),
        "ftp_configured": st.get("ftp_configured"),
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
                "id": "menu",
                "title": "Меню как на ai.conall.ru",
                "status": "nav",
                "note": "Остальные экраны — заглушки, контент по одному",
            },
        ]
    }
